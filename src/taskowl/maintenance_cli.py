"""CLI entry point for one-off retention pruning.

Runs a single prune pass and exits. For continuous pruning, leave it to the
consumer's periodic retention loop.
"""

import argparse
import asyncio
import logging
from collections.abc import Sequence

from taskowl.config import settings
from taskowl.maintenance import run_prune

logger = logging.getLogger(__name__)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="taskowl-prune",
        description=(
            "Delete TaskOwl event rows older than the configured retention "
            "windows (EVENT_RETENTION_DAYS / AUTOMATION_RUN_RETENTION_DAYS)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report how many rows would be deleted without deleting anything.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Override EVENT_RETENTION_DAYS for this run (0 = keep forever).",
    )
    return parser.parse_args(argv)


async def _run(dry_run: bool, days: int | None) -> dict[str, int]:
    """Configure logging and run a single prune pass."""
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    return await run_prune(dry_run=dry_run, event_retention_days=days)


def main() -> None:
    """Main entry point for the taskowl-prune CLI."""
    args = _parse_args()
    counts = asyncio.run(_run(args.dry_run, args.days))
    verb = "Would delete" if args.dry_run else "Deleted"
    for table, count in counts.items():
        print(f"{verb} {count} row(s) from {table}")


if __name__ == "__main__":
    main()
