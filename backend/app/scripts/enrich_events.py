"""Re-read Songkick to fill in the fields existing events are missing.

Usage, from `backend/`:

    # What is missing and what can be re-read. Fetches nothing, writes nothing.
    python -m app.scripts.report_event_gaps

    # See what the first run would change. Still writes nothing.
    python -m app.scripts.enrich_events --dry-run --limit 25

    # Actually write. Rate limited, resumable, safe to repeat.
    python -m app.scripts.enrich_events --apply --limit 200 --delay 1.5

`--dry-run` is the default on purpose: a run that changes the database has to
be asked for explicitly.
"""
import argparse
import asyncio
import sys

from app.database.connection import db
from app.repositories.event_repository import EventRepository
from app.services.event_enrichment_service import (
    ALL_ENRICHABLE_FIELDS,
    DATE_FIELDS,
    LINEUP_FIELDS,
    LOCATION_FIELDS,
    EventEnrichmentService,
)


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fill in missing event fields from Songkick."
        )
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum events to examine in this run.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help=(
            "Seconds to wait between source requests. The "
            "cost is a page fetch per event on Songkick's "
            "servers, so this is not optional politeness."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Write to the database. Without this nothing is "
            "written."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Re-read each source and report what it would "
            "change, writing nothing. This is how you find "
            "out whether a date is actually recoverable "
            "before paying for a real run."
        ),
    )
    parser.add_argument(
        "--fields",
        default="dates",
        choices=["dates", "lineup", "location", "all"],
        help=(
            "Which missing fields to chase. 'dates' is the "
            "urgent one; 'all' also revisits dated events to "
            "fill in a lineup or location."
        ),
    )
    parser.add_argument(
        "--include-dated",
        action="store_true",
        help=(
            "Also revisit events that already have a date. "
            "Only useful together with --fields all."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print each event's outcome.",
    )

    args = parser.parse_args()

    fields = {
        "dates": DATE_FIELDS,
        "lineup": LINEUP_FIELDS,
        "location": LOCATION_FIELDS,
        "all": ALL_ENRICHABLE_FIELDS,
    }[args.fields]

    await db.connect()

    try:
        service = EventEnrichmentService(
            EventRepository(db.get_database())
        )

        if not args.apply and not args.dry_run:

            preview = await service.report_only(
                limit=args.limit,
                fields=fields,
            )

            print("Event gap report")
            print("-" * 52)

            for key, value in preview.items():
                if key == "sample":
                    continue

                print(f"  {key:26}: {value}")

            if preview["sample"]:
                print()
                print("  eligible examples:")

                for plan in preview["sample"]:
                    print(
                        f"    {plan['event_id']} "
                        f"{plan['title'][:38]!r} "
                        f"missing={plan['missing']}"
                    )

            print()
            print(
                "Nothing was fetched and nothing was written. "
                "Re-run with --dry-run to see what the "
                "sources would give, or --apply to enrich."
            )

            return 0

        report = await service.run(
            limit=args.limit,
            dry_run=not args.apply,
            delay_seconds=args.delay,
            include_dated=args.include_dated,
            fields=fields,
        )

        print()
        print("Enrichment run complete")
        print("-" * 52)
        print(f"  {report.summary()}")

        if report.failures:
            print()
            print("  failures:")
            print(f"    {report.failures[:10]}")

        return 0

    finally:
        await db.disconnect()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))