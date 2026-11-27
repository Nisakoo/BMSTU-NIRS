import pytest
from pydantic import ValidationError

from smeshariki_ai.speech import (
    DEFAULT_MODEL_PATH,
    DEFAULT_SPEECH_VOICE,
    SpeechConfig,
    SpeechStatus,
)
from smeshariki_ai.speech.models import AudioRecord


def test_speech_config_has_safe_defaults() -> None:
    config = SpeechConfig()

    assert config.enabled is True
    assert config.voice == DEFAULT_SPEECH_VOICE == "baya"
    assert config.speed == 1.0
    assert config.max_concurrency == 1
    assert config.max_text_chars == 20_000
    assert config.model_path == DEFAULT_MODEL_PATH


def test_speech_config_normalizes_and_accepts_a_known_voice() -> None:
    assert SpeechConfig(voice="  AIDAR ").voice == "aidar"


@pytest.mark.parametrize(
    "values",
    [
        {"voice": "unknown"},
        {"voice": " "},
        {"speed": 0.4},
        {"speed": 2.1},
        {"max_concurrency": 0},
        {"max_text_chars": 0},
        {"max_text_chars": 100_001},
        {"model_path": " "},
        {"unexpected": True},
    ],
)
def test_speech_config_rejects_invalid_values(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        SpeechConfig.model_validate(values)


def test_audio_record_reports_only_complete_audio_as_ready() -> None:
    ready = AudioRecord(
        message_id=1,
        voice_id="aidar",
        status=SpeechStatus.READY,
        text_hash="hash",
        voice_version="v1",
        object_key="audio.mp3",
        mime_type="audio/mpeg",
        duration_ms=1000,
    )
    pending = AudioRecord(
        message_id=2,
        voice_id="aidar",
        status=SpeechStatus.PENDING,
        text_hash="hash",
        voice_version="v1",
    )

    assert ready.has_audio is True
    assert pending.has_audio is False
