"""Encrypted-at-rest OAuth token storage (Fernet, key from COMPANION_TOKEN_KEY)."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

from companion_core.errors import ConfigError
from cryptography.fernet import Fernet, InvalidToken


def fernet_from_secret(secret: str) -> Fernet:
    if len(secret) < 16:
        raise ConfigError("COMPANION_TOKEN_KEY must be at least 16 characters")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


class TokenVault:
    def __init__(self, path: Path, secret: str) -> None:
        self.path = path
        self._f = fernet_from_secret(secret)

    def _read_all(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {}
        try:
            return json.loads(self._f.decrypt(self.path.read_bytes()).decode("utf-8"))
        except InvalidToken as exc:
            raise ConfigError("token file cannot be decrypted with the current COMPANION_TOKEN_KEY") from exc

    def _write_all(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_bytes(self._f.encrypt(json.dumps(data).encode("utf-8")))
        tmp.chmod(0o600)
        tmp.replace(self.path)

    def load(self, account: str) -> dict[str, Any] | None:
        return self._read_all().get(account)

    def save(self, account: str, tokens: dict[str, Any]) -> None:
        data = self._read_all()
        data[account] = tokens
        self._write_all(data)

    def delete(self, account: str) -> bool:
        data = self._read_all()
        if account in data:
            del data[account]
            self._write_all(data)
            return True
        return False
