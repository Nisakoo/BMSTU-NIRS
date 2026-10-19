import pytest

from smeshariki_ai.rag.cli import ConfigurationError, postgres_store


async def test_missing_environment_is_a_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Only the variable that keeps LiteLLM from fetching its price map is kept.
    for name in ("DATABASE_URL", "REDIS_URL", "LLM_MODEL", "AUTH_JWT_SECRET"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "True")

    with pytest.raises(ConfigurationError):
        async with postgres_store():
            pass
