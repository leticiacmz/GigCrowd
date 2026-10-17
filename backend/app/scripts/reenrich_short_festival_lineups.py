"""Re-read the editions whose stored lineup is shorter than the bill on file.

A festival edition imported through an artist's page is written with the
listing's own lineup - the artist being browsed, alone - while its whole
bill is a different read: the edition's own page, which the lineup
enrichment performs. A resync (any later import of any artist on the bill)
used to overwrite the enriched bill with its own one-name listing, and the
row was left `complete` with a single artist and no queue willing to re-read
it. The repository now refuses that shrink; this script repairs the rows it
already cost, by re-running the enrichment with the same force the retry
button on the festival page uses.

The rules it holds itself to:

1. Bounded by construction: only festival editions whose own page address
   is stored, and whose stored lineup names fewer artists than the
   catalogue already knows of their bill (`artist_slugs`, or the source's
   own `festival.artist_ids`), and at least two of them. A row the
   catalogue associates with a single artist is not a shortened bill -
   there is no wider bill on file to restore, and the one artist it holds
   is the appearance the source stated - so it is left alone.
2. Additive only, by the enrichment service's own rules: the merge keeps
   every stored entry and appends what the page adds, a date is written
   only where none is stored, and a failure costs the attempt and leaves
   the row as it was - `failed` is a state, not a deletion.
3. A forced re-read, because that is the point: the rows this repairs are
   `complete`, and the non-force guard leaves finished work alone. The
   force is the festival page's retry, applied in one bounded pass.

Dry-run by default:

    python -m app.scripts.reenrich_short_festival_lineups
    python -m app.scripts.reenrich_short_festival_lineups --limit 10
    python -m app.scripts.reenrich_short_festival_lineups --apply
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

# A row the catalogue associates with a single artist is not a shortened
# bill: nothing wider is on file to restore. Only rows the catalogue
# already knows more of than the lineup names are candidates.
MINIMUM_KNOWN_BILL = 2


def candidates_query() -> dict:
    """Festival editions with an address; the size test is done in Python.

    The bill can be stored in two places - the source's own `artist_ids`
    and the catalogue `artist_slugs` - so "shorter than the bill" compares
    two lists per row, which is clearer to say in Python than to spell in a
    query. The hard filters that keep the pass small stay here: it must be
    a festival edition and it must carry a readable address, or the read is
    known in advance to be wasted.
    """

    return {
        "$and": [
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


def known_bill_size(document: dict) -> int:
    """How many artists of this edition the catalogue already holds.

    Two spellings of the same list, and either one may be the wider: the
    source's own bill ids arrive with the search document, while the
    catalogue slugs are what the import resolved them to - and an earlier
    enrichment may have added slugs for names the source never listed. The
    wider of the two is the bill as far as this pass can know it.
    """

    festival = document.get("festival") or {}

    artist_ids = festival.get("artist_ids") or []
    slugs = document.get("artist_slugs") or []

    return max(len(artist_ids), len(slugs))


def stored_lineup_size(document: dict) -> int:
    """How many performers the stored lineup names."""

    return len(document.get("lineup") or [])


def is_short(document: dict) -> bool:
    """Whether the stored lineup names fewer than the bill on file."""

    return (
        known_bill_size(document) >= MINIMUM_KNOWN_BILL
        and stored_lineup_size(document) < known_bill_size(document)
    )


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "force-enqueue the editions and read their pages "
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

    records = (
        await database.events.find(candidates_query())
        .to_list(length=None)
    )

    shorts = []
    unreadable = []

    for document in records:

        if not is_short(document):
            continue

        if address_stated_by(document):
            shorts.append(document)
        else:
            unreadable.append(document)

    print("=" * 72)
    print(
        "CANDIDATES - festival editions whose lineup is shorter "
        "than their bill"
    )
    print("=" * 72)
    print(f"   festival editions with an address : {len(records)}")
    print(f"   shorter than the bill on file     : {len(shorts)}")
    print(f"   no readable stored address        : {len(unreadable)}")

    if shorts:

        print()
        print(
            f"   {'_id':28} {'lineup':>6} {'bill':>5}  title"
        )

        for document in shorts:
            print(
                f"   {str(document['_id']):28} "
                f"{stored_lineup_size(document):>6} "
                f"{known_bill_size(document):>5}  "
                f"{document.get('title') or ''}"
            )

    if unreadable:

        print()
        print("   Left alone, no trustworthy address to read:")

        for document in unreadable[:10]:
            print(
                f"   {str(document['_id']):28} "
                f"{document.get('title') or ''}"
            )

        if len(unreadable) > 10:
            print(f"   ...and {len(unreadable) - 10} more")

    if not args.apply:

        print()
        print("DRY RUN - nothing was changed. Re-run with --apply to")
        print(
            f"force-enqueue the {len(shorts)} editions listed above "
            "and read their pages."
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

    selected = shorts[: max(args.limit, 0)]

    # ----------------------------------------------------------
    # Force-enqueue: these rows are `complete` by their own record,
    # and the retry is what re-opens a finished row. The guard still
    # runs first: a row somebody is actively reading is left to that
    # worker.
    # ----------------------------------------------------------

    enqueued: list[str] = []
    left_alone = 0

    for document in selected:

        state = await service.enqueue(
            document["_id"], force=True
        )

        if state == "pending":
            enqueued.append(str(document["_id"]))
        else:
            left_alone += 1

    print()
    print(
        f"ENQUEUED {len(enqueued)} editions for this pass with force; "
        f"{left_alone} left in their current state."
    )

    outcomes = await service.process_batch(enqueued)

    # ----------------------------------------------------------
    # What each pass obtained, read back from the rows themselves.
    # ----------------------------------------------------------

    before_by_id = {
        str(document["_id"]): stored_lineup_size(document)
        for document in selected
    }

    print()
    print("=" * 72)
    print("PASS OUTCOMES")
    print("=" * 72)

    by_state: dict[str, int] = {}
    repaired = 0

    for event_id in enqueued:

        outcome = outcomes.get(event_id) or "unknown"
        by_state[outcome] = by_state.get(outcome, 0) + 1

        stored = await database.events.find_one(
            {"_id": ObjectId(event_id)},
            {
                "title": 1,
                "lineup": 1,
                "lineup_state": 1,
                "lineup_enrichment.error": 1,
                "artist_slugs": 1,
            },
        ) or {}

        before = before_by_id.get(event_id, 0)
        after = stored_lineup_size(stored)

        if after > before:
            repaired += 1

        print(
            f"   {event_id} "
            f"{outcome:9} "
            f"lineup {before} -> {after} "
            f"| {stored.get('title') or ''}"
        )

        error = (
            (stored.get("lineup_enrichment") or {}).get("error")
        )

        if error:
            print(f"      error: {error}")

    print()
    print("AFTER")
    print(f"   editions whose bill grew      : {repaired}")
    print(f"   outcomes                      : {by_state}")

    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
