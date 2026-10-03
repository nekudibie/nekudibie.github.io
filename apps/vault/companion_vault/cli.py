"""``companion-vault`` entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

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
    bk = sub.add_parser("backup", help="consistent backup of vault.db (+ files) into a timestamped folder")
    bk.add_argument("--config")
    bk.add_argument("--dest", help="backup root (default: vault.backup_dir or data/backups)")
    bk.add_argument("--keep", type=int, default=14)
    bk.add_argument("--include-brain", action="store_true", help="also back up brain.db when it is on this host")
    rs = sub.add_parser("restore", help="restore from a backup folder (live files are moved aside, never deleted)")
    rs.add_argument("backup_dir")
    rs.add_argument("--config")
    rs.add_argument("--yes", action="store_true", help="confirm; services must be stopped first")
    ev = sub.add_parser("eval", help="run the retrieval evaluation and print recall@k / MRR")
    ev.add_argument("--config")
    ev.add_argument("--corpus")
    ev.add_argument("--queries")
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
    if args.cmd in {"backup", "restore"}:
        from .backup import BackupTarget, list_backups, make_backup, restore_backup

        targets = [BackupTarget("vault", cfg.vault_db_path, cfg.vault_files_dir)]
        if getattr(args, "include_brain", False) or args.cmd == "restore":
            targets.append(BackupTarget("brain", cfg.brain_db_path, None))
        if args.cmd == "backup":
            dest = Path(args.dest) if args.dest else cfg.vault_backup_dir
            out = make_backup(targets, dest, keep=args.keep)
            print(f"backup written: {out}  (sets kept: {len(list_backups(dest))})")
            return 0
        if not args.yes:
            print("refusing: add --yes after stopping companion-api/companion-vault/companion-worker", file=sys.stderr)
            return 2
        done = restore_backup(Path(args.backup_dir), targets)
        print(f"restored: {', '.join(done) or 'nothing matched'}; previous files kept as *.pre-restore-*")
        return 0
    if args.cmd == "eval":
        import json

        from .evaluation import default_fixture_dir, load_jsonl, run_evaluation

        d = default_fixture_dir()
        corpus = load_jsonl(Path(args.corpus) if args.corpus else d / "corpus.jsonl")
        queries = load_jsonl(Path(args.queries) if args.queries else d / "queries.jsonl")
        print(json.dumps(run_evaluation(corpus, queries).to_dict(), indent=2))
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
