import asyncio
import hashlib
import io
import wave
from array import array
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from smeshariki_ai.speech.errors import SpeechSynthesisError
from smeshariki_ai.speech.provider import SpeechProvider

SILERO_SAMPLE_RATE = 48_000


class SileroSpeechProvider(SpeechProvider):
    """Local CPU-only Silero v5 adapter.

    The model object is injected so the unit tests can exercise the adapter
    without installing torch or downloading the model.
    """

    def __init__(
        self,
        model: Any,
        *,
        model_version: str,
        sample_rate: int = SILERO_SAMPLE_RATE,
    ) -> None:
        voices = tuple(getattr(model, "speakers", ()))
        if not voices:
            raise SpeechSynthesisError("Silero model has no speakers.")
        self._model = model
        self._model_version = model_version
        self._sample_rate = sample_rate
        self._voices = voices

    @property
    def model_version(self) -> str:
        return self._model_version

    @property
    def voices(self) -> tuple[str, ...]:
        return self._voices

    @classmethod
    def from_path(cls, path: str | Path) -> "SileroSpeechProvider":
        model_path = Path(path)
        if not model_path.is_file():
            raise SpeechSynthesisError("Silero model file is missing.")
        try:
            import torch  # type: ignore[import-not-found]
        except ImportError as error:
            raise SpeechSynthesisError("Silero runtime is unavailable.") from error
        try:
            package = torch.package.PackageImporter(str(model_path))
            model = package.load_pickle("tts_models", "model")
            model.to(torch.device("cpu"))
        except Exception as error:
            raise SpeechSynthesisError("Silero model cannot be loaded.") from error
        return cls(
            model,
            model_version=f"silero-v5:{_file_digest(model_path)[:16]}",
        )

    async def synthesize(self, text: str, *, voice: str) -> bytes:
        if voice not in self._voices:
            raise SpeechSynthesisError("Unknown Silero voice.")
        return await asyncio.to_thread(self._synthesize_sync, text, voice)

    def _synthesize_sync(self, text: str, voice: str) -> bytes:
        try:
            waveform = self._model.apply_tts(
                text=text,
                speaker=voice,
                sample_rate=self._sample_rate,
                put_accent=True,
                put_yo=True,
            )
            samples = _float_samples(waveform)
            return _wav_bytes(samples, self._sample_rate)
        except SpeechSynthesisError:
            raise
        except Exception as error:
            raise SpeechSynthesisError("Silero synthesis failed.") from error


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _float_samples(waveform: Any) -> Sequence[float]:
    if hasattr(waveform, "detach"):
        waveform = waveform.detach()
    if hasattr(waveform, "cpu"):
        waveform = waveform.cpu()
    if hasattr(waveform, "tolist"):
        waveform = waveform.tolist()
    if not isinstance(waveform, (list, tuple)):
        raise SpeechSynthesisError("Silero returned an unsupported waveform.")
    if waveform and isinstance(waveform[0], (list, tuple)):
        return tuple(sample for row in waveform for sample in row)
    return waveform


def _wav_bytes(samples: Sequence[float], sample_rate: int) -> bytes:
    if not samples:
        raise SpeechSynthesisError("Silero returned empty audio.")
    pcm = array(
        "h",
        (max(-32768, min(32767, round(float(sample) * 32767))) for sample in samples),
    )
    if pcm.itemsize != 2:
        raise SpeechSynthesisError("Unsupported PCM sample size.")
    output = io.BytesIO()
    with wave.open(output, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        stream.writeframes(pcm.tobytes())
    return output.getvalue()
