"""``companion-vault`` entry point."""

from __future__ import annotations

import argparse
import sys

from companion_core.config import load_config
from companion_core.errors import ConfigError
from companion_core.logging import configure_logging, get_logger

log = get_logger("companion_vault")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="companion-vault", description="Memory vault service")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("serve", help="run the HTTP vault service (vault.mode: remote)")
    run.add_argument("--config")
    mig = sub.add_parser("migrate", help="apply pending migrations and exit")
    mig.add_argument("--config")
    re = sub.add_parser("reindex", help="rebuild chunks and FTS index from originals")
    re.add_argument("--config")
    st = sub.add_parser("stats", help="print vault statistics")
    st.add_argument("--config")
    args = parser.parse_args(argv)

    try:
        cfg = load_config(args.config)
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    configure_logging(cfg.logging.level, cfg.logging.format)

    from .app import build_service

    if args.cmd == "serve":
        import uvicorn

        from .app import create_app

        uvicorn.run(create_app(cfg), host=cfg.vault.host, port=cfg.vault.port, log_config=None)
        return 0
    svc = build_service(cfg)
    if args.cmd == "migrate":
        print(f"schema at {svc.db.schema_version()} ({cfg.vault_db_path})")
    elif args.cmd == "reindex":
        print(f"rebuilt {svc.rebuild_index()} chunks")
    elif args.cmd == "stats":
        import json

        print(json.dumps(svc.stats(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
