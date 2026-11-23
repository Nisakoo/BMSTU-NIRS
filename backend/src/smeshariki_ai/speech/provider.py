from typing import Protocol


class SpeechProvider(Protocol):
    """Turn one text chunk into WAV audio with a selected Silero voice."""

    @property
    def model_version(self) -> str: ...

    async def synthesize(self, text: str, *, voice: str) -> bytes: ...
