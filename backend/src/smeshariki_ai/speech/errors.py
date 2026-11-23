class SpeechError(Exception):
    """Base error of the local voiceover component."""


class SpeechUnavailableError(SpeechError):
    """Voiceover cannot be used or its storage is unavailable."""


class SpeechStoreUnavailableError(SpeechUnavailableError):
    """The message audio store failed."""


class SpeechSynthesisError(SpeechError):
    """The local synthesis or MP3 encoding failed."""


class SpeechTextTooLongError(SpeechError):
    """The answer is too long for the configured synthesis limit."""


class SpeechObjectStoreError(SpeechUnavailableError):
    """Ceph or another object store failed."""


class SpeechVoiceError(SpeechError):
    """The requested narrator voice is not a built-in Silero voice."""
