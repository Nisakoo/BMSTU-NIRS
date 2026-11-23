import io
import wave

import pytest

from smeshariki_ai.speech.encoder import wav_duration_ms
from smeshariki_ai.speech.errors import SpeechSynthesisError
from smeshariki_ai.speech.silero import SileroSpeechProvider


class FakeSileroModel:
    speakers = ("baya", "aidar")

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def apply_tts(self, **kwargs: object) -> list[float]:
        self.calls.append(kwargs)
        return [0.0] * 80


@pytest.mark.asyncio
async def test_silero_adapter_returns_valid_wav_and_passes_the_voice() -> None:
    model = FakeSileroModel()
    provider = SileroSpeechProvider(
        model,
        model_version="silero-v5:test",
        sample_rate=8000,
    )

    audio = await provider.synthesize("Привет", voice="baya")

    assert provider.model_version == "silero-v5:test"
    assert provider.voices == ("baya", "aidar")
    assert wav_duration_ms(audio) == 10
    assert model.calls == [
        {
            "text": "Привет",
            "speaker": "baya",
            "sample_rate": 8000,
            "put_accent": True,
            "put_yo": True,
        }
    ]


@pytest.mark.asyncio
async def test_silero_adapter_rejects_unknown_voice() -> None:
    provider = SileroSpeechProvider(
        FakeSileroModel(),
        model_version="silero-v5:test",
    )

    with pytest.raises(SpeechSynthesisError):
        await provider.synthesize("Привет", voice="unknown")


def test_silero_model_without_speakers_is_rejected() -> None:
    class EmptyModel:
        speakers: tuple[str, ...] = ()

    with pytest.raises(SpeechSynthesisError):
        SileroSpeechProvider(EmptyModel(), model_version="silero-v5:test")


def test_missing_silero_file_is_reported_safely() -> None:
    with pytest.raises(SpeechSynthesisError):
        SileroSpeechProvider.from_path("/missing/v5_ru.pt")


@pytest.mark.asyncio
async def test_silero_adapter_rejects_empty_waveform() -> None:
    class EmptyWaveform:
        speakers = ("baya",)

        def apply_tts(self, **kwargs: object) -> list[float]:
            return []

    provider = SileroSpeechProvider(EmptyWaveform(), model_version="silero-v5:test")

    with pytest.raises(SpeechSynthesisError):
        await provider.synthesize("Привет", voice="baya")


def test_wav_helper_keeps_pcm_header_readable() -> None:
    # The helper is private, but its output must remain a normal WAV stream.
    from smeshariki_ai.speech.silero import _wav_bytes

    data = _wav_bytes([0.0, 0.5, -0.5], 8000)
    with wave.open(io.BytesIO(data), "rb") as stream:
        assert stream.getframerate() == 8000
        assert stream.getnchannels() == 1
        assert stream.getsampwidth() == 2


@pytest.mark.asyncio
async def test_silero_adapter_flattens_a_two_dimensional_waveform() -> None:
    class TwoDimensionalModel:
        speakers = ("baya",)

        def apply_tts(self, **kwargs: object) -> list[list[float]]:
            return [[0.0, 0.1], [0.2, 0.3]]

    provider = SileroSpeechProvider(
        TwoDimensionalModel(),
        model_version="silero-v5:test",
        sample_rate=8000,
    )

    audio = await provider.synthesize("Привет", voice="baya")

    assert wav_duration_ms(audio) == 0
