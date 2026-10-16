from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from pydantic import ValidationError

from smeshariki_ai.auth import AuthConfig, Role, UnauthorizedError
from smeshariki_ai.auth.tokens import (
    TokenCodec,
    hash_refresh_token,
    new_refresh_token,
)

SECRET = "test-secret-with-at-least-32-bytes!!"
NOW = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)


def read_payload(token: str) -> dict[str, object]:
    return jwt.decode(
        token,
        SECRET,
        algorithms=["HS256"],
        options={"verify_exp": False, "verify_iat": False, "verify_iss": False},
    )


def make_codec(**overrides: object) -> TokenCodec:
    return TokenCodec(AuthConfig.model_validate({"jwt_secret": SECRET, **overrides}))


def test_access_token_round_trip_contains_expected_claims() -> None:
    codec = make_codec(access_ttl_seconds=60)
    user_id, session_id = uuid4(), uuid4()

    token, claims = codec.encode_access(user_id, Role.USER, session_id, NOW)
    decoded = codec.decode_access(token, NOW + timedelta(seconds=59))

    assert decoded == claims
    assert decoded.user_id == user_id
    assert decoded.session_id == session_id
    assert decoded.expires_at == NOW + timedelta(seconds=60)
    payload = read_payload(token)
    assert set(payload) == {"sub", "role", "jti", "sid", "iat", "exp", "iss"}


def test_decode_rejects_expired_token_by_injected_clock() -> None:
    codec = make_codec(access_ttl_seconds=60)
    token, _ = codec.encode_access(uuid4(), Role.USER, uuid4(), NOW)

    with pytest.raises(UnauthorizedError):
        codec.decode_access(token, NOW + timedelta(seconds=60))


@pytest.mark.parametrize(
    "payload_change",
    [
        {"iss": "someone-else"},
        {"sub": "not-a-uuid"},
        {"role": "root"},
        {"jti": None},
    ],
)
def test_decode_rejects_tampered_claims(payload_change: dict[str, object]) -> None:
    codec = make_codec()
    token, _ = codec.encode_access(uuid4(), Role.USER, uuid4(), NOW)
    payload = read_payload(token)
    payload.update(payload_change)
    payload = {key: value for key, value in payload.items() if value is not None}
    forged = jwt.encode(payload, SECRET, algorithm="HS256")

    with pytest.raises(UnauthorizedError):
        codec.decode_access(forged, NOW)


def test_decode_rejects_none_algorithm() -> None:
    codec = make_codec()
    token, _ = codec.encode_access(uuid4(), Role.USER, uuid4(), NOW)
    payload = read_payload(token)
    unsigned = jwt.encode(payload, None, algorithm="none")

    with pytest.raises(UnauthorizedError):
        codec.decode_access(unsigned, NOW)


def test_refresh_tokens_are_random_and_hashed() -> None:
    first, second = new_refresh_token(), new_refresh_token()

    assert first != second
    assert len(first) >= 43
    assert hash_refresh_token(first) == hash_refresh_token(first)
    assert len(hash_refresh_token(first)) == 32
    assert first.encode() not in hash_refresh_token(first)


@pytest.mark.parametrize(
    "values",
    [
        {"jwt_secret": "too-short"},
        {"jwt_secret": SECRET, "access_ttl_seconds": 0},
        {"jwt_secret": SECRET, "refresh_ttl_seconds": -1},
    ],
)
def test_auth_config_rejects_invalid_values(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError) as error:
        AuthConfig.model_validate(values)

    assert "too-short" not in str(error.value)


def test_auth_config_hides_secret() -> None:
    config = AuthConfig(jwt_secret=SECRET)

    assert SECRET not in repr(config)
