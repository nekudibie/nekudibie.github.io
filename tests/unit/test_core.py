from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from companion_core import ids
from companion_core.auth import ROLE_PERMISSIONS, Permission, TokenStore, generate_token, hash_token
from companion_core.clock import FakeClock, iso, parse_iso
from companion_core.config import AppConfig
from companion_core.db import Database, split_sql
from companion_core.envfile import parse_env_text
from companion_core.errors import ConfigError
from companion_core.logging import JsonFormatter, redact, register_secret


def test_ids_are_prefixed_and_time_sortable():
    a = ids.new_id("doc")
    time.sleep(0.002)
    b = ids.new_id("doc")
    assert a.startswith("doc_") and ids.is_id(a, "doc") and not ids.is_id(a, "msg")
    assert a < b


def test_iso_roundtrip_requires_aware():
    dt = datetime(2026, 3, 29, 1, 30, tzinfo=UTC)
    assert iso(dt) == "2026-03-29T01:30:00.000Z"
    assert parse_iso(iso(dt)) == dt
    with pytest.raises(ValueError):
        iso(datetime(2026, 1, 1))


def test_fake_clock_advances():
    c = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    c.advance(hours=2)
    assert c.now().hour == 2


def test_env_parser_handles_quotes_comments_and_export():
    text = 'A=1\n# comment\nexport B="two words"\nC=\'x\' \nD=val # trailing\nBAD\n'
    assert parse_env_text(text) == {"A": "1", "B": "two words", "C": "x", "D": "val"}


def test_redaction_masks_tokens_and_registered_secrets():
    register_secret("supersecretvalue123")
    line = 'Authorization: Bearer abc.def-ghi token="xyz123" and supersecretvalue123 ya29.AbCdEf'
    out = redact(line)
    assert "abc.def" not in out and "xyz123" not in out and "supersecretvalue123" not in out and "AbCdEf" not in out
    assert "[REDACTED]" in out


def test_json_formatter_emits_valid_json_with_extra_fields():
    rec = logging.LogRecord("t", logging.INFO, "f", 1, "hello %s", ("world",), None)
    rec.tool = "memory_search"
    import json

    data = json.loads(JsonFormatter().format(rec))
    assert data["msg"] == "hello world" and data["tool"] == "memory_search" and data["level"] == "INFO"


def test_token_store_and_hashing():
    tok = generate_token()
    assert len(tok) > 30
    store = TokenStore()
    from companion_core.auth import ClientIdentity

    store.add(hash_token(tok), ClientIdentity("desk", "desk", ROLE_PERMISSIONS["desk"]))
    assert store.lookup(tok) is not None and store.lookup(tok + "x") is None


def test_roles_are_strictly_narrower_than_owner():
    owner = ROLE_PERMISSIONS["owner"]
    for role, perms in ROLE_PERMISSIONS.items():
        assert perms <= owner
        if role != "owner":
            assert Permission.ADMIN not in perms
    assert Permission.HOME_CONTROL not in ROLE_PERMISSIONS["rover"]
    assert Permission.MEMORY_DELETE not in ROLE_PERMISSIONS["carried"]


def test_config_rejects_ollama_without_model_and_bad_clients():
    with pytest.raises(Exception, match="llm.model is required"):
        AppConfig.model_validate({"llm": {"provider": "ollama"}})
    with pytest.raises(Exception, match="unknown role"):
        AppConfig.model_validate({"clients": [{"id": "x", "role": "god", "token_env": "X"}]})
    with pytest.raises(Exception, match="exactly one of"):
        AppConfig.model_validate({"clients": [{"id": "x", "role": "desk", "token_env": "X", "token_sha256": "ab"}]})
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AppConfig.model_validate({"unknown_section": {}})


def test_config_warns_on_missing_or_short_tokens(monkeypatch):
    monkeypatch.setenv("SHORT", "abc")
    monkeypatch.delenv("MISSING", raising=False)
    cfg = AppConfig.model_validate({"clients": [{"id": "a", "role": "desk", "token_env": "SHORT"}, {"id": "b", "role": "desk", "token_env": "MISSING"}]})
    store, warnings = cfg.build_token_store()
    assert len(store) == 0 and len(warnings) == 2


def test_load_config_missing_file(tmp_path: Path):
    from companion_core.config import load_config

    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.yaml")


def test_split_sql_keeps_trigger_bodies_whole():
    script = """-- c
CREATE TABLE t(x);
CREATE TRIGGER tr AFTER INSERT ON t BEGIN
  INSERT INTO t VALUES (1);
  INSERT INTO t VALUES (2);
END;
"""
    stmts = split_sql(script)
    assert len(stmts) == 2 and stmts[1].startswith("CREATE TRIGGER") and stmts[1].rstrip().endswith("END;")


def test_migrations_apply_once_and_rollback_on_failure(tmp_path: Path):
    mig = tmp_path / "m"
    mig.mkdir()
    (mig / "001_a.sql").write_text("CREATE TABLE a(x INTEGER);")
    db = Database(tmp_path / "t.db")
    assert db.migrate(mig) == ["001_a.sql"]
    assert db.migrate(mig) == []
    (mig / "002_bad.sql").write_text("CREATE TABLE b(x INTEGER); CREATE TABLE a(x INTEGER);")
    import sqlite3

    with pytest.raises(sqlite3.Error):
        db.migrate(mig)
    assert db.schema_version() == "001_a.sql"
    assert db.query_one("SELECT name FROM sqlite_master WHERE name='b'") is None


def test_backup_is_consistent_copy(tmp_path: Path):
    db = Database(tmp_path / "src.db")
    db.execute("CREATE TABLE t(x)")
    db.execute("INSERT INTO t VALUES (42)")
    out = db.backup_to(tmp_path / "bk" / "copy.db")
    other = Database(out)
    assert other.query_one("SELECT x FROM t")[0] == 42
