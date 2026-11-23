import io
import subprocess
import wave
from typing import Protocol

from smeshariki_ai.speech.errors import SpeechSynthesisError


class AudioEncoder(Protocol):
    """Encode synthesized WAV into the browser-facing MP3 format."""

    def to_mp3(self, wav: bytes, *, speed: float) -> bytes: ...


class FfmpegAudioEncoder:
    def __init__(self, executable: str = "ffmpeg", bitrate: str = "64k") -> None:
        self._executable = executable
        self._bitrate = bitrate

    def to_mp3(self, wav: bytes, *, speed: float) -> bytes:
        if not wav:
            raise SpeechSynthesisError("Synthesized audio is empty.")
        command = [
            self._executable,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "wav",
            "-i",
            "pipe:0",
            "-filter:a",
            f"atempo={speed:.3f}",
            "-codec:a",
            "libmp3lame",
            "-b:a",
            self._bitrate,
            "-ac",
            "1",
            "-f",
            "mp3",
            "pipe:1",
        ]
        try:
            completed = subprocess.run(
                command,
                input=wav,
                capture_output=True,
                check=False,
                timeout=120,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise SpeechSynthesisError("MP3 encoder is unavailable.") from error
        if completed.returncode != 0 or not completed.stdout:
            raise SpeechSynthesisError("MP3 encoding failed.")
        return completed.stdout


def wav_duration_ms(wav: bytes) -> int:
    """Read one WAV file duration; synthesized chunks are always WAV."""

    try:
        with wave.open(io.BytesIO(wav), "rb") as stream:
            frames = stream.getnframes()
            rate = stream.getframerate()
    except (wave.Error, EOFError, KeyError) as error:
        raise SpeechSynthesisError("Synthesized WAV is invalid.") from error
    if rate <= 0:
        raise SpeechSynthesisError("Synthesized WAV has no sample rate.")
    return round(frames * 1000 / rate)


def join_wav_chunks(chunks: list[bytes], pause_ms: list[int]) -> bytes:
    """Join equal-format WAV chunks and insert silence between them."""

    if not chunks:
        raise SpeechSynthesisError("No synthesized chunks to join.")
    if len(chunks) != len(pause_ms):
        raise ValueError("Each WAV chunk needs one pause value.")

    with wave.open(io.BytesIO(chunks[0]), "rb") as first:
        params = first.getparams()
    output = io.BytesIO()
    with wave.open(output, "wb") as target:
        target.setparams(params)
        for index, chunk in enumerate(chunks):
            with wave.open(io.BytesIO(chunk), "rb") as source:
                source_params = source.getparams()
                if source_params[:3] != params[:3] or source_params[4:] != params[4:]:
                    raise SpeechSynthesisError("Synthesized WAV formats differ.")
                target.writeframes(source.readframes(source.getnframes()))
            pause = pause_ms[index]
            if pause > 0 and index < len(chunks) - 1:
                target.writeframes(_silence(params, pause))
    return output.getvalue()


def _silence(params: wave._wave_params, pause_ms: int) -> bytes:
    frames = round(params.framerate * pause_ms / 1000)
    return b"\x00" * (frames * params.nchannels * params.sampwidth)
