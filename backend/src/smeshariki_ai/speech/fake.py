import io
import wave

from smeshariki_ai.speech.encoder import AudioEncoder


class FakeSpeechProvider:
    def __init__(
        self,
        *,
        model_version: str = "fake-v1",
        sample_rate: int = 8000,
        duration_ms: int = 50,
    ) -> None:
        self._model_version = model_version
        self._sample_rate = sample_rate
        self._duration_ms = duration_ms
        self.calls: list[tuple[str, str]] = []

    @property
    def model_version(self) -> str:
        return self._model_version

    async def synthesize(self, text: str, *, voice: str) -> bytes:
        self.calls.append((text, voice))
        frames = round(self._sample_rate * self._duration_ms / 1000)
        output = io.BytesIO()
        with wave.open(output, "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(self._sample_rate)
            stream.writeframes(b"\x00\x00" * frames)
        return output.getvalue()


class FakeAudioEncoder(AudioEncoder):
    def __init__(self, data: bytes = b"fake-mp3") -> None:
        self._data = data
        self.calls: list[tuple[bytes, float]] = []

    def to_mp3(self, wav: bytes, *, speed: float) -> bytes:
        self.calls.append((wav, speed))
        return self._data
