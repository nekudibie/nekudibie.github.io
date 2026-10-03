from .meetings import summarise_recording, transcribe_recording

HANDLERS = {
    "transcribe_recording": transcribe_recording,
    "summarise_recording": summarise_recording,
}

__all__ = ["HANDLERS"]
