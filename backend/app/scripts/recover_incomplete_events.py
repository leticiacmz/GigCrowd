"""Recover incomplete events by running the scheduler's own job, repeatedly.

This is not a second enrichment implementation and not a one-off script with its
own idea of what is missing. It calls `run_enrichment_once` - the exact function
`EnrichmentScheduler` calls on every tick - in a loop, because a single tick is
deliberately bounded and a recovery run has to finish a backlog.

That distinction matters for the report at the end of it. A number produced by
this script is a number the scheduler itself produces, so the backlog it clears
is a backlog the scheduler would have cleared on its own, just over more ticks
than one run allows.

    python -m app.scripts.recover_incomplete_events --dry-run
    python -m app.scripts.recover_incomplete_events --apply
    python -m app.scripts.recover_incomplete_events --apply --max-ticks 40

Nothing here resets, wipes or reseeds anything. It reads events, reads their
source pages, and merges back only what is missing.
"""
from __future__ import annotations

import argparse
import asyncio
import json

from app.database.connection import db
from app.jobs.enrichment_job import (
    EnrichmentJobConfig,
    resolve_fields,
    run_enrichment_once,
)
from app.repositories.event_repository import EventRepository
from app.services.event_enrichment_service import (
    EventEnrichmentService,
)


async def census() -> dict:
    """The five questions the report has to answer, counted live.

    Deliberately counts the states separately rather than as one "incomplete"
    number, because they have different causes and different remedies: a missing
    start date is unrecoverable data, a missing `date_status` beside a checked
    source is a settled answer, and a missing status beside an *unchecked*
    source is the bug this whole exercise is about.
    """

    events = db.get_database().events

    total = await events.count_documents({})

    undated = await events.count_documents(
        {
            "$or": [
                {"starts_at": {"$exists": False}},
                {"starts_at": None},
            ]
        }
    )

    missing_status = await events.count_documents(
        {
            "$or": [
                {"date_status": {"$exists": False}},
                {"date_status": None},
            ]
        }
    )

    parser_failed = await events.count_documents(
        {"date_status": "parser_failed"}
    )

    unavailable = await events.count_documents(
        {"date_status": "unavailable"}
    )

    from_source = await events.count_documents(
        {"date_status": "source"}
    )

    # Never inspected at the concrete source. This is the state that must not
    # survive the run: an event whose page nobody has read is an event whose
    # missing date is an assumption.
    never_checked = await events.count_documents(
        {"date_source_checked_at": {"$exists": False}}
    )

    # The failure this work is about, stated as one number: undated, and nobody
    # has confirmed that the source really has no date.
    unexplained = await events.count_documents(
        {
            "$and": [
                {
                    "$or": [
                        {"starts_at": {"$exists": False}},
                        {"starts_at": None},
                    ]
                },
                {
                    "$or": [
                        {
                            "date_source_checked_at": {
                                "$exists": False
                            }
                        },
                        {"date_source_checked_at": None},
                    ]
                },
            ]
        }
    )

    # Undated but properly explained: inspected, and the source has nothing.
    explained = await events.count_documents(
        {
            "$and": [
                {
                    "$or": [
                        {"starts_at": {"$exists": False}},
                        {"starts_at": None},
                    ]
                },
                {"date_source_checked_at": {"$exists": True}},
                {"date_source_checked_at": {"$ne": None}},
            ]
        }
    )

    festival_ranges = await events.count_documents(
        {
            "event_type": "FestivalInstance",
            "starts_at": {"$ne": None},
            "ends_at": {"$ne": None},
        }
    )

    return {
        "events_total": total,
        "missing_starts_at": undated,
        "missing_date_status": missing_status,
        "date_status_parser_failed": parser_failed,
        "date_status_unavailable": unavailable,
        "date_status_from_source": from_source,
        "never_inspected_at_source": never_checked,
        "undated_and_never_inspected": unexplained,
        "undated_and_inspected": explained,
        "festival_instances_with_a_full_range": festival_ranges,
    }


async def undated_detail(limit: int = 25) -> list[dict]:
    """The undated events, with the reason each one is or is not explained."""

    events = db.get_database().events

    rows: list[dict] = []

    async for document in events.find(
        {
            "$or": [
                {"starts_at": {"$exists": False}},
                {"starts_at": None},
            ]
        },
        {
            "title": 1,
            "event_type": 1,
            "date_status": 1,
            "date_source_checked_at": 1,
            "source.url": 1,
            "festival.url": 1,
        },
    ):
        rows.append(
            {
                "title": document.get("title"),
                "event_type": document.get("event_type"),
                "date_status": document.get("date_status"),
                "checked_at": document.get(
                    "date_source_checked_at"
                ),
                "has_source": bool(
                    (document.get("source") or {}).get("url")
                    or (document.get("festival") or {}).get("url")
                ),
            }
        )

        if len(rows) >= limit:
            break

    return rows


async def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the recovered fields. Without it, nothing is written.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change. The default.",
    )
    parser.add_argument(
        "--fields",
        default="dates",
        help="dates, lineup, location or all.",
    )
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument(
        "--delay-seconds", type=float, default=1.5
    )
    parser.add_argument(
        "--max-ticks",
        type=int,
        default=200,
        help="Stop after this many bounded passes.",
    )

    args = parser.parse_args()

    dry_run = not args.apply

    await db.connect()

    database = db.get_database()

    service = EventEnrichmentService(
        EventRepository(database)
    )

    config = EnrichmentJobConfig(
        batch_size=args.batch_size,
        delay_seconds=args.delay_seconds,
        fields=resolve_fields(args.fields),
        include_dated=False,
        dry_run=dry_run,
    )

    try:
        before = await census()

        print(
            json.dumps(
                {"stage": "before", **before},
                indent=2,
                default=str,
            )
        )

        totals = {
            "selected": 0,
            "attempted": 0,
            "updated": 0,
            "unchanged": 0,
            "source_missing": 0,
            "parse_failed": 0,
            "request_failed": 0,
            "write_failed": 0,
            "missing_record": 0,
        }

        ticks = 0

        while ticks < args.max_ticks:
            result = await run_enrichment_once(
                service,
                config,
            )

            ticks += 1

            for name in totals:
                totals[name] += getattr(result, name, 0)

            print(
                f"[TICK {ticks}] selected={result.selected} "
                f"updated={result.updated} "
                f"request_failed={result.request_failed} "
                f"parse_failed={result.parse_failed}"
            )

            # Stop when a pass finds nothing, or when a full pass made no
            # progress at all. The second condition is what stops a backlog of
            # un-reachable events from being re-selected forever.
            if result.selected == 0:
                break

            if result.updated == 0 and result.unchanged == 0:
                break

        after = await census()

        print(
            json.dumps(
                {
                    "stage": "after",
                    "ticks": ticks,
                    "dry_run": dry_run,
                    "totals": totals,
                    **after,
                },
                indent=2,
                default=str,
            )
        )

        detail = await undated_detail()

        if detail:
            print(
                json.dumps(
                    {"stage": "undated_detail", "rows": detail},
                    indent=2,
                    default=str,
                )
            )

    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
