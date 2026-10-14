"""Report what the stored events are missing, without touching Songkick.

A read-only census: it counts documents, writes nothing, and makes no outbound
request. This is what you run when an import summary reports gaps and you want
the same facts over the whole collection rather than for one artist, or when
you want to know what a manual source read would be looking at before you
decide to spend one.

Usage, from `backend/`:

    python -m app.scripts.report_event_gaps
    python -m app.scripts.report_event_gaps --limit 20

The counts are of stored fields, by the same names the import uses when it
reports a gap: `starts_at`, `ends_at`, `lineup`, `location`. A missing
`ends_at` beside a present `starts_at` is counted apart from a missing start,
because a concert genuinely has no end and reporting the two as one figure
claims far more undated events than there are.
"""
from __future__ import annotations

import argparse
import asyncio
import sys

# The fields this report counts, in the order it counts them. They are plain
# document keys: nothing here asks a service what is missing, because the point
# of the tool is to look at what is actually stored.
COUNTED_FIELDS = ("starts_at", "ends_at", "lineup", "location")


def plan_for(document: dict) -> dict:
    """What one stored event is missing, and whether it could be re-read.

    Mirrors what the extractor looks for, field by field, so the number this
    prints and the number an import summary prints describe the same absence.
    """

    source = document.get("source") or {}

    source_url = source.get("url") or None

    # Some festival rows carry the provider's page URL on the festival identity
    # instead of on `source`, because that is where the importer found it.
    if not source_url:
        festival_url = (document.get("festival") or {}).get("url")

        if festival_url:
            source_url = festival_url

    reasons = [
        field
        for field in COUNTED_FIELDS
        if not document.get(field)
    ]

    return {
        "event_id": str(document.get("_id")),
        "title": document.get("title") or "",
        "missing": reasons,
        "source_url": source_url,
        "songkick_id": (document.get("external_ids") or {}).get(
            "songkick"
        ),
    }


async def census(limit: int | None = None) -> dict:
    """Count the collection. Reads only."""

    from app.database.connection import db

    cursor = db.get_database().events.find(
        {},
        {
            "title": 1,
            "starts_at": 1,
            "ends_at": 1,
            "lineup": 1,
            "location": 1,
            "source.url": 1,
            "festival.url": 1,
            "external_ids.songkick": 1,
            "date_status": 1,
            "event_type": 1,
        },
    )

    documents = await cursor.to_list(length=None)

    plans = [plan_for(document) for document in documents]

    by_status: dict[str, int] = {}

    for document in documents:
        status = document.get("date_status") or "unset"
        by_status[status] = by_status.get(status, 0) + 1

    eligible = [plan for plan in plans if plan["source_url"]]

    return {
        "events_stored": len(documents),
        "total_missing_something": sum(
            1 for plan in plans if plan["missing"]
        ),
        "eligible": len(eligible),
        "no_source": len(plans) - len(eligible),
        "missing_start_date": sum(
            1
            for plan in plans
            if "starts_at" in plan["missing"]
        ),
        "missing_end_date": sum(
            1
            for plan in plans
            if "ends_at" in plan["missing"]
            and "starts_at" not in plan["missing"]
        ),
        "missing_lineup": sum(
            1
            for plan in plans
            if "lineup" in plan["missing"]
        ),
        "missing_location": sum(
            1
            for plan in plans
            if "location" in plan["missing"]
        ),
        "date_status": by_status,
        "sample": [plan for plan in eligible[:limit or 5]],
    }


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Report what the stored events are missing."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="How many eligible examples to print (default: 5).",
    )
    arguments = parser.parse_args()

    from app.database.connection import db

    await db.connect()

    try:
        preview = await census(limit=arguments.limit)

        print("Event gap report (read-only)")
        print("-" * 52)

        for key, value in preview.items():
            if key in {"sample", "date_status"}:
                continue

            print(f"  {key:26}: {value}")

        print(f"  {'date_status':26}: {preview['date_status']}")

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
        print("Nothing was written and nothing was fetched.")
        return 0

    finally:
        await db.disconnect()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
