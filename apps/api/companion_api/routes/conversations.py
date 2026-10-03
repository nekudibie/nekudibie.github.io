from __future__ import annotations

from typing import Any

from companion_contracts.conversation import Conversation, ConversationCreate, SendMessage
from companion_core.auth import ClientIdentity, Permission
from companion_core.errors import PermissionDenied
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ..auth import Identity
from ..sse import SSE_HEADERS, comment, encode

router = APIRouter(prefix="/v1/conversations")


def _own(st: Any, identity: ClientIdentity, conversation_id: str) -> Conversation:
    conv = st.store.get_conversation(conversation_id)
    if conv.client_id != identity.client_id and not identity.has(Permission.ADMIN):
        raise PermissionDenied("this conversation belongs to another client")
    return conv


@router.post("", response_model=Conversation, status_code=201)
async def create(body: ConversationCreate, identity: Identity, request: Request):
    st = request.app.state.companion
    if not identity.has(Permission.CONVERSE):
        raise PermissionDenied("client may not converse")
    return st.store.create_conversation(identity.client_id, body.title)


@router.get("", response_model=list[Conversation])
async def list_(identity: Identity, request: Request, limit: int = 30):
    st = request.app.state.companion
    return st.store.list_conversations(identity.client_id, limit=min(max(limit, 1), 200))


@router.get("/{conversation_id}")
async def get(conversation_id: str, identity: Identity, request: Request):
    st = request.app.state.companion
    conv = _own(st, identity, conversation_id)
    return {"conversation": conv.model_dump(), "messages": [m.model_dump() for m in st.store.list_messages(conversation_id)]}


@router.post("/{conversation_id}/messages")
async def send(conversation_id: str, body: SendMessage, identity: Identity, request: Request):
    st = request.app.state.companion
    if not identity.has(Permission.CONVERSE):
        raise PermissionDenied("client may not converse")
    _own(st, identity, conversation_id)

    async def gen():
        yield comment("connected")
        async for ev in st.orchestrator.run_turn(
            identity, conversation_id, body.content, input_mode=body.input_mode, client_capabilities=body.client_capabilities
        ):
            yield encode(ev)

    return StreamingResponse(gen(), media_type="text/event-stream", headers=SSE_HEADERS)


@router.post("/{conversation_id}/cancel")
async def cancel(conversation_id: str, identity: Identity, request: Request):
    st = request.app.state.companion
    _own(st, identity, conversation_id)
    return {"cancelled_turns": st.orchestrator.cancel(conversation_id)}
