"""FastAPI dependencies for client authentication and permission checks."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from companion_core.auth import ClientIdentity, Permission
from companion_core.errors import AuthenticationError, PermissionDenied
from companion_core.logging import client_id_var
from fastapi import Depends, Request


def get_identity(request: Request) -> ClientIdentity:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise AuthenticationError("missing bearer token")
    token = header.split(" ", 1)[1].strip()
    if not token:
        raise AuthenticationError("empty bearer token")
    identity = request.app.state.companion.tokens.lookup(token)
    if identity is None:
        raise AuthenticationError("invalid token")
    client_id_var.set(identity.client_id)
    return identity


Identity = Annotated[ClientIdentity, Depends(get_identity)]


def require(perm: Permission) -> Callable[[ClientIdentity], ClientIdentity]:
    def _dep(identity: Identity) -> ClientIdentity:
        if not identity.has(perm):
            raise PermissionDenied(f"client {identity.client_id!r} (role {identity.role}) lacks {perm.value}")
        return identity

    return _dep
