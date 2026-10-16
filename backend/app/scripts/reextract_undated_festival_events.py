"""Re-read, as bounded background work, the undated editions that can answer.

The undated rows in this database are past festival editions: the listing
wrote the row, and the run's per-pass page-read bound
(`SONGKICK_EVENT_PAGE_READS_PER_SCRAPE`) meant the edition's own page was
never opened, so no date and no full lineup was ever stored
(`date_status = None`). They are history, not hidden future rows - the
catalogue is honest about them, and nothing about upcoming search changes
by touching them.

What a page read can still add is the edition's own date and performers:
Songkick keeps past edition pages readable, and the lineup enrichment reads
exactly that page through exactly that path. This script runs the
enrichment over a bounded tail of those rows - the ones whose title names
2024 or 2025, the most recent editions, where a stored date is still worth
having - and reports what each pass obtained.

The rules it holds itself to:

1. Bounded by construction: only undated rows that are festival editions,
   whose title names 2024 or 2025, that carry a stored Songkick address
   for their own page, and only up to `--limit` of them. Nothing older,
   nothing dated, nothing future, nothing else.
2. Additive only, by the enrichment service's own rules: a date is written
   where none is stored (these rows have none), the lineup merge keeps
   every stored entry and appends what the page adds, and a failure costs
   the attempt and leaves the row as it was - `failed` is a state, not a
   deletion.
3. Non-force enqueue: a row already waiting, running, or finished is left
   to its state and reported, and a row with no readable address is never
   enqueued at all - the outcome for it is known in advance, and stamping
   a state onto a legacy row for an answer nobody can change would be
   noise.

Dry-run by default:

    python -m app.scripts.reextract_undated_festival_events
    python -m app.scripts.reextract_undated_festival_events --limit 10
    python -m app.scripts.reextract_undated_festival_events --apply
"""
from __future__ import annotations

import argparse
import asyncio
import re
from typing import Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings
from app.domain.event_provenance import SONGKICK_URL_PREFIX
from app.domain.festival import http_url_or_none
from app.services.lineup_enrichment_service import service_for_database

# Undated, in the only spelling this catalogue has: neither endpoint of
# the interval was ever stored.
UNDATED = {"starts_at": None, "ends_at": None}

# The recent tail worth a page read: editions whose title names 2024 or
# 2025. Older undated rows are the same history with less to gain, and a
# bounded pass is the whole point.
RECENT_TITLES = {"$regex": r"\b(2024|2025)\b"}

# Where a readable address for the edition's own page may already be, in
# the precedence the identity block uses. Re-validated per row below.
ADDRESS_FIELDS = (
    ("source", "url"),
    ("festival", "url"),
    ("festival", "official_url"),
)

# The only shape the enrichment's provider client can read - the same
# prefix `has_concrete_source` tests, escaped for a query.
ADDRESS_PATTERN = "^" + re.escape(SONGKICK_URL_PREFIX)


def candidates_query() -> dict:
    """Undated festival editions from the recent tail, with an address.

    The event-type test is the same case-insensitive match the enrichment
    itself applies: a concert's lineup is its one artist and has nothing
    to enrich. The address test is what keeps a row whose page cannot be
    opened out of the queue entirely - it would only be stamped `failed`
    for a reason this script already knows.
    """

    return {
        "$and": [
            UNDATED,
            {"title": RECENT_TITLES},
            {"event_type": {"$regex": "festival", "$options": "i"}},
            {
                "$or": [
                    {f"{parent}.{field}": {"$regex": ADDRESS_PATTERN}}
                    for parent, field in ADDRESS_FIELDS
                ]
            },
        ]
    }


def address_stated_by(document: dict) -> Optional[str]:
    """The first stored address of this edition a browser can open.

    The same precedence and validation the enrichment's own address
    resolution holds, re-checked here rather than trusted from the query:
    the regex narrows the candidate set, this decides whether a real
    Songkick address is actually held.
    """

    for parent, field in ADDRESS_FIELDS:

        block = document.get(parent)

        if not isinstance(block, dict):
            continue

        address = http_url_or_none(block.get(field))

        if address and address.startswith(SONGKICK_URL_PREFIX):
            return address

    return None


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "enqueue the editions and read their pages "
            "(without this, nothing is changed)"
        ),
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="how many editions to visit in one run",
    )

    args = parser.parse_args()

    client = AsyncIOMotorClient(
        settings.MONGODB_URL, tz_aware=True
    )

    database = client[settings.DATABASE_NAME]

    before_total = await database.events.count_documents({})
    before_undated = await database.events.count_documents(UNDATED)

    records = (
        await database.events.find(candidates_query())
        .limit(max(args.limit, 0))
        .to_list(length=None)
    )

    readable = []
    inconclusive = []

    for document in records:

        if address_stated_by(document):
            readable.append(document)
        else:
            inconclusive.append(document)

    print("=" * 72)
    print("CANDIDATES - undated editions whose title names 2024/2025")
    print("=" * 72)
    print(f"   events total (before)         : {before_total}")
    print(f"   undated rows (before)         : {before_undated}")
    print(f"   matching the bounded tail     : {len(records)}")
    print(f"   with a readable page address  : {len(readable)}")
    print(f"   no usable stored address      : {len(inconclusive)}")

    if readable:

        print()
        print(f"   {'_id':28} title")

        for document in readable[:25]:
            print(
                f"   {str(document['_id']):28} "
                f"{document.get('title') or ''}"
            )

        if len(readable) > 25:
            print(f"   ...and {len(readable) - 25} more")

    if inconclusive:

        print()
        print("   Left alone, no trustworthy address to read:")

        for document in inconclusive[:10]:
            print(
                f"   {str(document['_id']):28} "
                f"{document.get('title') or ''}"
            )

        if len(inconclusive) > 10:
            print(f"   ...and {len(inconclusive) - 10} more")

    if not args.apply:

        print()
        print("DRY RUN - nothing was changed. Re-run with --apply to")
        print(
            f"enqueue the {len(readable)} editions listed above and "
            "read their pages."
        )

        client.close()
        return 0

    service = service_for_database(database)

    if service is None:

        print()
        print("NOTHING WAS DONE - lineup enrichment is disabled in this")
        print(
            "configuration (LINEUP_ENRICHMENT_ENABLED). Enable it "
            "and re-run."
        )

        client.close()
        return 1

    # ----------------------------------------------------------
    # Enqueue, non-force: the guard on the service decides, so a row
    # somebody else queued or finished stays exactly where it is.
    # ----------------------------------------------------------

    enqueued: list[str] = []
    left_alone = 0

    for document in readable:

        state = await service.enqueue(
            document["_id"], force=False
        )

        if state == "pending":
            enqueued.append(str(document["_id"]))
        else:
            left_alone += 1

    print()
    print(
        f"ENQUEUED {len(enqueued)} editions for this pass; "
        f"{left_alone} left in their current state."
    )

    outcomes = await service.process_batch(enqueued)

    # ----------------------------------------------------------
    # What each pass obtained, read back from the rows themselves.
    # ----------------------------------------------------------

    print()
    print("=" * 72)
    print("PASS OUTCOMES")
    print("=" * 72)

    by_state: dict[str, int] = {}
    dated_now = 0
    slugs_total = 0

    for event_id in enqueued:

        outcome = outcomes.get(event_id) or "unknown"
        by_state[outcome] = by_state.get(outcome, 0) + 1

        stored = await database.events.find_one(
            {"_id": ObjectId(event_id)},
            {
                "title": 1,
                "starts_at": 1,
                "ends_at": 1,
                "lineup": 1,
                "lineup_state": 1,
                "lineup_enrichment.error": 1,
                "artist_slugs": 1,
            },
        ) or {}

        starts_at = stored.get("starts_at")

        if starts_at:
            dated_now += 1

        lineup_size = len(stored.get("lineup") or [])
        slugs_size = len(stored.get("artist_slugs") or [])
        slugs_total += slugs_size

        print(
            f"   {event_id} "
            f"{outcome:9} "
            f"date={'yes' if starts_at else 'no'} "
            f"lineup={lineup_size} "
            f"artists={slugs_size} | "
            f"{stored.get('title') or ''}"
        )

        error = (
            (stored.get("lineup_enrichment") or {}).get("error")
        )

        if error:
            print(f"      error: {error}")

    after_undated = await database.events.count_documents(UNDATED)

    print()
    print("AFTER")
    print(
        f"   undated rows                  : "
        f"{before_undated} -> {after_undated}"
    )
    print(f"   dated by this pass            : {dated_now}")
    print(f"   outcomes                      : {by_state}")
    print(
        f"   artist slugs across these rows: {slugs_total}"
    )

    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
