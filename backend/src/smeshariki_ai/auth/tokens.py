import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt

from smeshariki_ai.auth.config import AuthConfig
from smeshariki_ai.auth.models import AccessClaims, Role, UnauthorizedError

_ALGORITHM = "HS256"
_REQUIRED_CLAIMS = ["sub", "role", "jti", "sid", "iat", "exp", "iss"]


class TokenCodec:
    def __init__(self, config: AuthConfig) -> None:
        self._secret = config.jwt_secret.get_secret_value()
        self._issuer = config.issuer
        self._access_ttl = timedelta(seconds=config.access_ttl_seconds)

    def encode_access(
        self,
        user_id: UUID,
        role: Role,
        session_id: UUID,
        now: datetime,
    ) -> tuple[str, AccessClaims]:
        issued_at = now.replace(microsecond=0)
        claims = AccessClaims(
            user_id=user_id,
            role=role,
            jti=uuid4().hex,
            session_id=session_id,
            issued_at=issued_at,
            expires_at=issued_at + self._access_ttl,
        )
        payload = {
            "sub": str(claims.user_id),
            "role": claims.role.value,
            "jti": claims.jti,
            "sid": str(claims.session_id),
            "iat": int(claims.issued_at.timestamp()),
            "exp": int(claims.expires_at.timestamp()),
            "iss": self._issuer,
        }
        return jwt.encode(payload, self._secret, algorithm=_ALGORITHM), claims

    def decode_access(self, token: str, now: datetime) -> AccessClaims:
        try:
            # Expiry is checked against the injected clock below.
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[_ALGORITHM],
                issuer=self._issuer,
                options={
                    "require": _REQUIRED_CLAIMS,
                    "verify_exp": False,
                    "verify_iat": False,
                },
            )
            claims = AccessClaims(
                user_id=UUID(payload["sub"]),
                role=Role(payload["role"]),
                jti=_non_empty(payload["jti"]),
                session_id=UUID(payload["sid"]),
                issued_at=datetime.fromtimestamp(int(payload["iat"]), UTC),
                expires_at=datetime.fromtimestamp(int(payload["exp"]), UTC),
            )
        except (jwt.PyJWTError, KeyError, TypeError, ValueError) as error:
            raise UnauthorizedError from error
        if claims.expires_at <= now:
            raise UnauthorizedError
        return claims


def new_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> bytes:
    return hashlib.sha256(token.encode("utf-8")).digest()


def _non_empty(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("Claim must be a non-empty string.")
    return value
