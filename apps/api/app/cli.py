"""`gridline` command: gridline sync all | scheduler | cleanup-runs | seed | media-coverage | identity-report | identity-apply"""

from __future__ import annotations

import argparse
import sys

from .config import get_settings
from .logging_setup import configure_logging


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gridline")
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sync", help="sync one source or 'all'")
    s.add_argument("source")
    s.add_argument("--fixtures", action="store_true")
    sch = sub.add_parser("scheduler", help="run the periodic sync loop")
    sch.add_argument("--once", action="store_true")
    c = sub.add_parser("cleanup-runs", help="prune old SourceRun rows (never SessionChange)")
    c.add_argument("--keep-days", type=int, default=None)
    sub.add_parser("seed", help="load dev fixtures + sample roster (NOT for production)")
    sub.add_parser("media-coverage", help="compare teams in the database with the logo registry (--fail-under PCT)")
    sub.add_parser("identity-report", help="canonical entities, aliases and likely duplicates (read-only)")
    sub.add_parser("identity-apply", help="apply curated aliases and backfill canonical rows for existing data")
    args, rest = parser.parse_known_args(argv)

    if args.cmd == "sync":
        from .sources.sync import main as sync_main
        return sync_main([args.source] + (["--fixtures"] if args.fixtures else []))
    if args.cmd == "scheduler":
        from .scheduler import main as sched_main
        sys.argv = ["scheduler"] + (["--once"] if args.once else [])
        return sched_main()
    if args.cmd == "cleanup-runs":
        from .maintenance import cleanup_source_runs
        configure_logging(get_settings().log_level)
        n = cleanup_source_runs(args.keep_days or get_settings().source_run_retention_days)
        print(f"deleted {n} old source runs")
        return 0
    if args.cmd == "media-coverage":
        from .media_coverage import main as coverage_main
        return coverage_main(rest)
    if args.cmd == "identity-report":
        from .identity_report import main as report_main
        return report_main(rest)
    if args.cmd == "identity-apply":
        from .db import SessionLocal
        from .services.identity import ensure_identity
        with SessionLocal() as db:
            c = ensure_identity(db)
            db.commit()
        print(f"merged drivers: {c.merged_drivers or 'none'}; merged teams: {c.merged_teams or 'none'}; "
              f"aliases added: {c.aliases_added}; entries linked: {c.entries_linked}")
        return 0
    from .seed import main as seed_main
    return seed_main()


if __name__ == "__main__":
    raise SystemExit(main())
