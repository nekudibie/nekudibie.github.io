"""``companion-worker``: run persistent jobs on the brain host."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from companion_core.config import load_config
from companion_core.errors import ConfigError
from companion_core.logging import configure_logging


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="companion-worker", description="Persistent job runner")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="run until stopped")
    run.add_argument("--config")
    run.add_argument("--once", action="store_true", help="process what is runnable now, then exit")
    ls = sub.add_parser("list", help="list recent jobs")
    ls.add_argument("--config")
    ls.add_argument("--status", action="append")
    rt = sub.add_parser("retry", help="re-queue a failed/cancelled job")
    rt.add_argument("job_id")
    rt.add_argument("--config")
    cn = sub.add_parser("cancel", help="cancel a job")
    cn.add_argument("job_id")
    cn.add_argument("--config")
    args = parser.parse_args(argv)
    try:
        cfg = load_config(args.config)
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    configure_logging(cfg.logging.level, cfg.logging.format)

    from companion_api.store import ConversationStore  # migrations for brain.db live with the API
    from companion_core.db import Database

    db = Database(cfg.brain_db_path)
    ConversationStore(db).migrate()
    from .handlers import HANDLERS
    from .runner import Worker
    from .services import build_services

    services = build_services(cfg, db=db)
    if args.cmd == "list":
        for j in services.queue.list(status=args.status, limit=50):
            print(f"{j.id}  {j.kind:<22} {j.status:<10} p{j.priority:<3} {j.progress:4.0%}  {j.progress_note or j.error or ''}")
        print(json.dumps(services.queue.counts()))
        return 0
    if args.cmd == "retry":
        print(services.queue.retry(args.job_id).status)
        return 0
    if args.cmd == "cancel":
        print(services.queue.cancel(args.job_id).status)
        return 0
    worker = Worker(services.queue, HANDLERS, services, concurrency=cfg.worker.concurrency, poll_interval_s=cfg.worker.poll_interval_s, lease_s=cfg.worker.lease_s,
                    periodic=[services.scheduler.tick] if services.scheduler else None)
    if args.once:
        print(f"processed {asyncio.run(worker.run_until_idle())} job(s)")
        return 0
    try:
        asyncio.run(worker.run_forever())
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
