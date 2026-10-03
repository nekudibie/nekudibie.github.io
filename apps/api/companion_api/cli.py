"""``companion-api`` entry point."""

from __future__ import annotations

import argparse
import json
import sys

from companion_core.auth import generate_token, hash_token
from companion_core.config import load_config
from companion_core.errors import ConfigError
from companion_core.logging import configure_logging


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="companion-api", description="Companion orchestration API")
    sub = parser.add_subparsers(dest="cmd", required=True)

    serve = sub.add_parser("serve", help="run the API (serves the desk UI when built)")
    serve.add_argument("--config")
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)
    serve.add_argument("--reload", action="store_true", help="development auto-reload")

    tok = sub.add_parser("make-token", help="print a new client token and its sha256")
    tok.add_argument("--count", type=int, default=1)

    chk = sub.add_parser("check-config", help="validate configuration and print a redacted summary")
    chk.add_argument("--config")

    mig = sub.add_parser("migrate", help="apply pending brain/vault migrations and exit")
    mig.add_argument("--config")

    args = parser.parse_args(argv)

    if args.cmd == "make-token":
        for _ in range(args.count):
            t = generate_token()
            print(f"token:  {t}\nsha256: {hash_token(t)}\n")
        print("Put the token in .env (COMPANION_DESK_TOKEN=...) or the sha256 in config clients[].token_sha256.")
        return 0

    try:
        cfg = load_config(args.config)
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    configure_logging(cfg.logging.level, cfg.logging.format)

    if args.cmd == "check-config":
        from companion_core.config import config_summary

        _, warnings = cfg.build_token_store()
        print(json.dumps({"summary": config_summary(cfg), "warnings": warnings, "paths": {
            "brain_db": str(cfg.brain_db_path), "vault_db": str(cfg.vault_db_path), "media": str(cfg.media_dir), "desk_dist": str(cfg.desk_dist_dir)}}, indent=2))
        return 1 if warnings and cfg.instance.environment == "production" else 0

    if args.cmd == "migrate":
        from companion_core.db import Database

        from .store import ConversationStore

        store = ConversationStore(Database(cfg.brain_db_path))
        print("brain:", store.migrate() or "up to date", f"({store.db.schema_version()})")
        if cfg.vault.mode == "embedded":
            from companion_vault.service import VaultService

            svc = VaultService(Database(cfg.vault_db_path))
            print("vault:", svc.migrate() or "up to date", f"({svc.db.schema_version()})")
        return 0

    if args.cmd == "serve":
        import uvicorn

        host = args.host or cfg.api.host
        port = args.port or cfg.api.port
        if args.reload:
            import os

            os.environ.setdefault("COMPANION_CONFIG", str(cfg.source_path))
            uvicorn.run("companion_api.asgi:app", host=host, port=port, reload=True, log_config=None)
        else:
            from .app import create_app

            uvicorn.run(create_app(cfg), host=host, port=port, log_config=None)
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
