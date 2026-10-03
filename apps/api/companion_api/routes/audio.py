"""Speech endpoints: transcribe, speak, and a full voice turn.

Audio travels out-of-band as WAV bytes (request body / response body); the turn itself
streams the usual typed events plus a ``transcript`` event. Listening buffers are
ephemeral: nothing here writes audio to disk.
"""

from __future__ import annotations

from typing import Annotated

from companion_contracts.events import ErrorEvent, StateEvent, TranscriptEvent
from companion_core.auth import ClientIdentity, Permission
from companion_core.errors import NotConfigured, PermissionDenied, ValidationFailed
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from ..auth import require
from ..sse import SSE_HEADERS, comment, encode

router = APIRouter(prefix="/v1")
Listener = Annotated[ClientIdentity, Depends(require(Permission.AUDIO_STT))]
Speaker = Annotated[ClientIdentity, Depends(require(Permission.AUDIO_TTS))]

MAX_AUDIO_BYTES = 25 * 1024 * 1024


class SpeakBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=2000)


async def _read_wav(request: Request) -> bytes:
    ctype = request.headers.get("content-type", "")
    if not (ctype.startswith("audio/wav") or ctype.startswith("audio/x-wav") or ctype.startswith("audio/wave") or ctype.startswith("application/octet-stream")):
        raise ValidationFailed("send WAV bytes with Content-Type: audio/wav")
    data = await request.body()
    if len(data) > MAX_AUDIO_BYTES:
        raise ValidationFailed(f"audio larger than {MAX_AUDIO_BYTES // (1024 * 1024)} MB")
    if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValidationFailed("body is not a WAV file")
    return data


@router.get("/audio/status")
async def audio_status(identity: Annotated[ClientIdentity, Depends(require(Permission.CONVERSE))], request: Request):
    st = request.app.state.companion
    out = {"stt": None, "tts": None, "wake_word": {"enabled": st.config.wake_word.enabled, "provider": st.config.wake_word.provider}}
    if st.stt is not None:
        out["stt"] = {"provider": st.stt.name, "model": st.stt.model, "is_fixture": st.stt.is_fixture, "health": (await st.stt.health()).model_dump()}
    if st.tts is not None:
        out["tts"] = {"provider": st.tts.name, "voice": st.tts.voice, "is_fixture": st.tts.is_fixture, "health": (await st.tts.health()).model_dump()}
    return out


@router.post("/audio/transcribe")
async def transcribe(identity: Listener, request: Request, language: str | None = None):
    st = request.app.state.companion
    if st.stt is None:
        raise NotConfigured("stt.provider is disabled")
    wav = await _read_wav(request)
    t = await st.stt.transcribe(wav, language=language)
    return t.model_dump()


@router.post("/audio/speak")
async def speak(body: SpeakBody, identity: Speaker, request: Request):
    st = request.app.state.companion
    if st.tts is None:
        raise NotConfigured("tts.provider is disabled")
    clip = await st.tts.synthesize(body.text)
    return Response(
        content=clip.to_wav(), media_type="audio/wav",
        headers={"X-Companion-Fixture": "true" if clip.is_fixture else "false", "X-Companion-Voice": clip.voice, "Cache-Control": "no-store"},
    )


@router.post("/conversations/{conversation_id}/voice")
async def voice_turn(conversation_id: str, identity: Listener, request: Request, language: str | None = None):
    """WAV in, SSE out: transcribe, then run the turn exactly as a typed message would."""
    st = request.app.state.companion
    if not identity.has(Permission.CONVERSE):
        raise PermissionDenied("client may not converse")
    if st.stt is None:
        raise NotConfigured("stt.provider is disabled")
    conv = st.store.get_conversation(conversation_id)
    if conv.client_id != identity.client_id and not identity.has(Permission.ADMIN):
        raise PermissionDenied("this conversation belongs to another client")
    wav = await _read_wav(request)

    async def gen():
        yield comment("connected")
        yield encode(StateEvent(state="transcribing"))
        try:
            t = await st.stt.transcribe(wav, language=language)
        except ValidationFailed as exc:
            yield encode(ErrorEvent(code="bad_audio", message=exc.message, recoverable=True))
            yield encode(StateEvent(state="idle"))
            return
        except Exception as exc:  # noqa: BLE001 - STT problems must not take the stream down
            yield encode(ErrorEvent(code="stt_unavailable", message=f"speech recognition failed ({exc.__class__.__name__})", recoverable=True))
            yield encode(StateEvent(state="error", detail="stt"))
            return
        yield encode(TranscriptEvent(text=t.text, language=t.language, duration_ms=int(t.duration_s * 1000), provider=t.provider, is_fixture=t.is_fixture))
        if not t.text.strip():
            yield encode(ErrorEvent(code="no_speech", message="I didn't catch any words.", recoverable=True))
            yield encode(StateEvent(state="idle"))
            return
        async for ev in st.orchestrator.run_turn(identity, conversation_id, t.text, input_mode="voice", client_capabilities=["audio"]):
            yield encode(ev)

    return StreamingResponse(gen(), media_type="text/event-stream", headers=SSE_HEADERS)
