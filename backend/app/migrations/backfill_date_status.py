"""Record how each stored event's date was resolved.

`date_status` is how the enrichment system tells three different situations
apart, and records imported before that field existed do not carry it:

* `source` - the date came from the provider's own page.
* `unavailable` - the source was read and genuinely carries no date.
* `parser_failed` - a date was there and could not be read.

Without it, an older record is indistinguishable from an event that has never
been looked at, so a scheduled pass would keep selecting it, and "Date
unavailable" could not be told apart from "we have not checked yet".

Usage, from `backend/`:

    # What would change, and why. Reads only, writes nothing.
    python -m app.migrations.backfill_date_status

    # Actually write it.
    python -m app.migrations.backfill_date_status --apply

The reasoning per record is deliberately conservative:

* An event that already carries a date, and whose date came from a Songkick
  page, is `source`. This is not a guess: the importer read that page and wrote
  that date.
* An event with no date and no Songkick source is `unavailable`. Nothing failed
  and nothing is pending - there is no page to ask.
* Nothing is marked `parser_failed` by this migration. That status means a
  source stated a date that could not be parsed, and only a read can establish
  that. Backfilling it from the absence of a date would be exactly the
  confusion this field exists to prevent, and it would make the scheduled
  enrichment pass retry events that can never succeed.

No stored date is touched. This writes one field and nothing else.
"""
from __future__ import annotations

import asyncio
import sys

from app.database.connection import db
from app.domain.event_schedule import (
    has_event_date,
)
from app.services.event_enrichment_service import (
    DATE_FROM_SOURCE,
    DATE_UNAVAILABLE,
    DATE_PARSER_FAILED,
)

# The valid states, so a typo cannot be written into the collection.
VALID_STATUSES = (
    DATE_FROM_SOURCE,
    DATE_UNAVAILABLE,
    DATE_PARSER_FAILED,
)


def classify(document: dict) -> tuple[str, str]:
    """The status this record should carry, and the reason for it.

    Returns a `(status, reason)` pair so a dry run can explain itself rather
    than only counting.
    """

    has_date = has_event_date(document)

    source_url = (document.get("source") or {}).get("url")

    songkick_id = (document.get("external_ids") or {}).get(
        "songkick"
    )

    has_source = bool(source_url or songkick_id)

    if has_date:
        return (
            DATE_FROM_SOURCE,
            "carries a date, and its source is the provider page "
            "the importer read"
            if has_source
            else "carries a date but records no provider source; "
            "treated as read from the source that produced it",
        )

    if has_source:
        # A source exists but no date was recovered. Whether the page simply has
        # no date or the reader could not understand it is not knowable without
        # reading the page, which is the scheduled enrichment's job and not this
        # migration's. `unavailable` is the honest "there is no date here"; the
        # enrichment pass will revisit anything genuinely undated.
        return (
            DATE_UNAVAILABLE,
            "has a provider source but no date was ever read",
        )

    return (
        DATE_UNAVAILABLE,
        "has no date and no provider source, so there is nothing to re-read",
    )


async def survey() -> dict:
    """Count what the migration would do, and why. Reads only."""

    cursor = db.get_database().events.find(
        {
            "$or": [
                {"date_status": {"$exists": False}},
                {"date_status": None},
            ]
        },
        {
            "title": 1,
            "starts_at": 1,
            "ends_at": 1,
            "source.url": 1,
            "external_ids.songkick": 1,
        },
    )

    documents = await cursor.to_list(length=None)

    by_status: dict[str, int] = {}

    reasons: dict[str, int] = {}

    samples: dict[str, dict] = {}

    for document in documents:

        status, reason = classify(document)

        by_status[status] = by_status.get(status, 0) + 1
        reasons[reason] = reasons.get(reason, 0) + 1

        samples.setdefault(
            status,
            {
                "title": document.get("title"),
                "event_id": str(document.get("_id")),
                "reason": reason,
            },
        )

    return {
        "documents_missing_date_status": len(documents),
        "by_status": by_status,
        "by_reason": reasons,
        "samples": samples,
    }


async def migrate(apply: bool = False) -> int:
    """Write the backfilled status. Returns how many documents changed."""

    database = db.get_database()

    changed = 0

    cursor = database.events.find(
        {
            "$or": [
                {"date_status": {"$exists": False}},
                {"date_status": None},
            ]
        }
    )

    async for document in cursor:

        status, reason = classify(document)

        if status not in VALID_STATUSES:
            raise ValueError(
                f"Refusing to write unknown date_status {status!r}"
            )

        # Only `date_status` is set. A stored date is never rewritten, so a
        # migration can never move an event in time.
        await database.events.update_one(
            {"_id": document["_id"]},
            {"$set": {"date_status": status}},
        )

        changed += 1

        if not apply:
            print(
                f"  would set {status:<14} "
                f"{document.get('title')!r} ({reason})"
            )

    return changed


async def main() -> int:
    await db.connect()

    try:
        print()
        print("date_status backfill - survey")
        print("-" * 52)

        report = await survey()

        print(
            f"  documents missing date_status: "
            f"{report['documents_missing_date_status']}"
        )

        for status, count in sorted(report["by_status"].items()):
            print(f"    -> {status:<14} {count}")

        print()
        print("  reasoning:")

        for reason, count in sorted(
            report["by_reason"].items(), key=lambda i: -i[1]
        ):
            print(f"    {count:>6}  {reason}")

        if report["samples"]:
            print()
            print("  one example per outcome:")

            for status, sample in sorted(report["samples"].items()):
                print(
                    f"    {status:<14} {sample['title']!r}"
                )

        print()

        if "--apply" not in sys.argv:
            print(
                "Nothing was written. Re-run with --apply to "
                "backfill."
            )
            return 0

        changed = await migrate(apply=True)

        print()
        print(f"Backfilled date_status on {changed} event(s).")

        # The point of the migration is that a later pass can tell a settled
        # record from an unexamined one, so the figure afterwards is the proof.
        remaining = await db.get_database().events.count_documents(
            {
                "$or": [
                    {"date_status": {"$exists": False}},
                    {"date_status": None},
                ]
            }
        )

        print(f"Still missing date_status: {remaining}")

        return 0

    finally:
        await db.disconnect()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
