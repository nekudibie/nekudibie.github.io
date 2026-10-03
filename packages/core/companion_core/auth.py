"""Client identity, roles and permissions.

Authentication is independent of the language model: a request carries a bearer
token that maps to a configured *client* (desk, carried, rover, admin, ...). The
client's *role* fixes the permission set server-side. Tool execution checks these
permissions in the gateway, so no prompt or model output can widen them.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from enum import StrEnum


class Permission(StrEnum):
    ADMIN = "admin"
    CONVERSE = "converse"
    MEMORY_READ = "memory.read"
    MEMORY_WRITE = "memory.write"
    MEMORY_DELETE = "memory.delete"
    HOME_READ = "home.read"
    HOME_CONTROL = "home.control"
    CAMERA_VIEW = "camera.view"
    MEETING_RECORD = "meeting.record"
    MEETING_READ = "meeting.read"
    EMAIL_READ = "email.read"
    WEATHER_READ = "weather.read"
    MATHS_USE = "maths.use"
    MTG_READ = "mtg.read"
    TUTOR_USE = "tutor.use"
    SCHEDULE_WRITE = "schedule.write"
    JOBS_READ = "jobs.read"
    AUDIO_STT = "audio.stt"
    AUDIO_TTS = "audio.tts"
    ROBOT_COMMAND = "robot.command"
    ROBOT_STATUS = "robot.status"


ALL_PERMISSIONS: frozenset[Permission] = frozenset(Permission)

# Role -> permissions. Narrower roles get strictly less; the owner's desk session is the
# only one that can delete memory or manage admin functions.
ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "owner": ALL_PERMISSIONS,
    "desk": ALL_PERMISSIONS - {Permission.ADMIN},
    "carried": frozenset(
        {
            Permission.CONVERSE,
            Permission.MEMORY_READ,
            Permission.MEMORY_WRITE,
            Permission.HOME_READ,
            Permission.HOME_CONTROL,
            Permission.WEATHER_READ,
            Permission.MATHS_USE,
            Permission.MTG_READ,
            Permission.TUTOR_USE,
            Permission.EMAIL_READ,
            Permission.MEETING_READ,
            Permission.JOBS_READ,
            Permission.AUDIO_STT,
            Permission.AUDIO_TTS,
        }
    ),
    "rover": frozenset(
        {
            Permission.CONVERSE,
            Permission.MEMORY_READ,
            Permission.WEATHER_READ,
            Permission.MATHS_USE,
            Permission.ROBOT_COMMAND,
            Permission.ROBOT_STATUS,
            Permission.AUDIO_STT,
            Permission.AUDIO_TTS,
        }
    ),
    "guest": frozenset({Permission.CONVERSE, Permission.WEATHER_READ, Permission.MATHS_USE}),
    "service": frozenset({Permission.MEMORY_READ, Permission.MEMORY_WRITE, Permission.JOBS_READ}),
}


@dataclass(frozen=True)
class ClientIdentity:
    client_id: str
    role: str
    permissions: frozenset[Permission]
    label: str = ""
    # Resource allowlists narrow what a permission may touch (e.g. which home entities).
    home_entities: frozenset[str] | None = None  # None = role default (all allowed entities)
    memory_scopes: frozenset[str] = field(default_factory=lambda: frozenset({"owner", "shared"}))

    def has(self, perm: Permission) -> bool:
        return Permission.ADMIN in self.permissions or perm in self.permissions

    def can_touch_entity(self, entity_id: str) -> bool:
        return self.home_entities is None or entity_id in self.home_entities


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_matches(presented: str, expected_sha256: str) -> bool:
    return hmac.compare_digest(hash_token(presented), expected_sha256.lower())


def generate_token(prefix: str = "cmp") -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


class TokenStore:
    """Looks up a client by bearer token. Tokens are only ever held hashed."""

    def __init__(self) -> None:
        self._by_hash: dict[str, ClientIdentity] = {}

    def add(self, token_sha256: str, identity: ClientIdentity) -> None:
        self._by_hash[token_sha256.lower()] = identity

    def lookup(self, token: str) -> ClientIdentity | None:
        digest = hash_token(token)
        for stored, identity in self._by_hash.items():
            if hmac.compare_digest(stored, digest):
                return identity
        return None

    def by_client_id(self, client_id: str) -> ClientIdentity | None:
        for identity in self._by_hash.values():
            if identity.client_id == client_id:
                return identity
        return None

    def __len__(self) -> int:
        return len(self._by_hash)
