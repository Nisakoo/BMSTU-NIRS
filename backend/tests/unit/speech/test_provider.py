import io
import wave

import pytest

from smeshariki_ai.speech.encoder import join_wav_chunks, wav_duration_ms
from smeshariki_ai.speech.errors import SpeechSynthesisError


def wav(sample_rate: int = 8000, duration_ms: int = 50) -> bytes:
    frames = round(sample_rate * duration_ms / 1000)
    output = io.BytesIO()
    with wave.open(output, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        stream.writeframes(b"\x00\x00" * frames)
    return output.getvalue()


def test_join_wav_chunks_inserts_silence() -> None:
    joined = join_wav_chunks([wav(duration_ms=50), wav(duration_ms=50)], [100, 0])

    assert wav_duration_ms(joined) == 200


def test_join_rejects_different_formats() -> None:
    with pytest.raises(SpeechSynthesisError):
        join_wav_chunks([wav(), wav(sample_rate=16000)], [0, 0])


def test_wav_duration_rejects_invalid_audio() -> None:
    with pytest.raises(SpeechSynthesisError):
        wav_duration_ms(b"not a wav")
