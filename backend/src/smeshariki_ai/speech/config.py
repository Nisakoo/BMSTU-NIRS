from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

DEFAULT_SPEECH_VOICE = "baya"
DEFAULT_MODEL_PATH = "/models/silero/v5_ru.pt"
SILERO_VOICES = frozenset({"aidar", "baya", "kseniya", "xenia", "eugene"})


class SpeechConfig(BaseModel):
    """Settings owned by the local narrator voiceover component."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = True
    voice: str = DEFAULT_SPEECH_VOICE
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    max_concurrency: int = Field(default=1, gt=0)
    max_text_chars: int = Field(default=20_000, gt=0, le=100_000)
    model_path: str = DEFAULT_MODEL_PATH

    @field_validator("voice")
    @classmethod
    def require_known_voice(cls, value: str) -> str:
        voice = value.strip().lower()
        if voice not in SILERO_VOICES:
            raise ValueError(f"Unknown Silero voice: {value!r}.")
        return voice

    @field_validator("model_path")
    @classmethod
    def require_model_path(cls, value: str) -> str:
        path = value.strip()
        if not path:
            raise ValueError("The Silero model path must not be empty.")
        return path


class CephS3Config(BaseModel):
    """Private S3-compatible Ceph RGW endpoint used for MP3 objects."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    endpoint: str = "http://ceph-rgw:7480"
    bucket: str = "smeshariki-audio"
    access_key: str = "smeshariki"
    secret_key: SecretStr = SecretStr("replace-with-ceph-secret")
    region: str = "us-east-1"
    prefix: str = "smeshariki-audio"

    @field_validator("endpoint")
    @classmethod
    def require_http_endpoint(cls, value: str) -> str:
        endpoint = value.strip().rstrip("/")
        if not endpoint.startswith(("http://", "https://")):
            raise ValueError("Ceph endpoint must be an HTTP(S) URL.")
        return endpoint

    @field_validator("bucket", "access_key", "region", "prefix")
    @classmethod
    def require_non_empty(cls, value: str) -> str:
        result = value.strip()
        if not result:
            raise ValueError("Ceph setting must not be empty.")
        return result

    @field_validator("secret_key")
    @classmethod
    def require_secret(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("Ceph secret key must not be empty.")
        return value
