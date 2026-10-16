"""Give the festival dates that never got one their series id.

An imported festival date can arrive without `festival.series_id`: the listing
wrote the festival's own address, or the event's source address, but never the
structured series field - so the canonical festival address
`/festivals/series/{id}` cannot find that date among its editions. This reports
those records and, only when asked, stores the series id their own address
already states.

Three rules the script holds itself to:

1. Nothing is invented. The series id written is parsed from the record's own
   address by `festival_data_from_url` - the same structured-source rule
   `festival_identity` applies - and never from a title, a name or a
   neighbouring event.
2. Nothing else is touched. Only a *missing* `festival.series_id` is written;
   the stored block, the lineup, the artist associations and the dates stay
   exactly as they are. A record that already stores a series id is excluded
   from the candidate set, and the write re-checks it, so a second run finds
   nothing and a race cannot overwrite a series somebody else stored. One
   shape of record needs its own write: a row whose festival field is a
   `null` placeholder. Mongo cannot write `festival.series_id` into a null,
   so those rows get the minimal block `{series_id}` in place of the
   placeholder - nothing more is added, and the write only happens while the
   field is still null.
3. Nothing is deleted, and an address that parses to no series is left alone
   and reported instead.

Dry-run by default:

    python -m app.scripts.backfill_festival_series
    python -m app.scripts.backfill_festival_series --limit 500
    python -m app.scripts.backfill_festival_series --apply
"""
from __future__ import annotations

import argparse
import asyncio
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings
from app.domain.festival import festival_data_from_url

# One of these addresses may state the series. Read in the precedence
# `festival_identity` reads them: the festival block's own address first, then
# its official site, then the event's own source address - so the script
# writes exactly what identity resolution would have read.
ADDRESS_RULES = (
    ("festival", "url"),
    ("festival", "official_url"),
    ("source", "url"),
)

# A festival address, broad on purpose: this only narrows the candidate set,
# and the parse decides whether a series is really stated.
ADDRESS_PATTERN = r"/festivals/\d"

# "No series id stored" - every spelling of missing the field can have.
MISSING_SERIES = {
    "$or": [
        {"festival.series_id": {"$exists": False}},
        {"festival.series_id": None},
        {"festival.series_id": ""},
    ]
}


def series_stated_by(document: dict) -> Optional[str]:
    """The series id the record's own addresses state, or `None`.

    The first address that parses wins, in the precedence `festival_identity`
    applies, so the script writes exactly what identity resolution would read
    from the same record.
    """

    for parent, field in ADDRESS_RULES:

        block = document.get(parent)

        if not isinstance(block, dict):
            continue

        address = block.get(field)

        if not address:
            continue

        data = festival_data_from_url(address)

        if data and data.get("series_id"):
            return str(data["series_id"])

    return None


def candidates_query() -> dict:
    """Festival records with no stored series id whose own address states one.

    Records that already store a series id are excluded: they are already
    findable by the canonical address, and rewriting one would be a change
    nobody asked for.
    """

    return {
        "$and": [
            MISSING_SERIES,
            {
                "$or": [
                    {
                        "festival.url": {
                            "$regex": ADDRESS_PATTERN
                        }
                    },
                    {
                        "festival.official_url": {
                            "$regex": ADDRESS_PATTERN
                        }
                    },
                    {
                        "source.url": {
                            "$regex": ADDRESS_PATTERN
                        }
                    },
                ]
            },
        ]
    }


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "store the series ids (without this, nothing is changed)"
        ),
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="how many records to visit in one run",
    )

    args = parser.parse_args()

    client = AsyncIOMotorClient(
        settings.MONGODB_URL, tz_aware=True
    )

    database = client[settings.DATABASE_NAME]

    records = await database.events.find(
        candidates_query()
    ).limit(max(args.limit, 0)).to_list(length=None)

    resolvable = []
    unparseable = []

    for document in records:

        series_id = series_stated_by(document)

        if series_id:
            resolvable.append((document, series_id))
        else:
            unparseable.append(document)

    print("=" * 72)
    print("CANDIDATES")
    print("=" * 72)
    print(f"   without a stored series id : {len(records)}")
    print(f"   an address states a series : {len(resolvable)}")
    print(f"   no address parses a series : {len(unparseable)}")

    if resolvable:

        print()
        print(f"   {'_id':28} {'series':8} title")

        for document, series_id in resolvable[:25]:
            print(
                f"   {str(document['_id']):28} {series_id:8} "
                f"{document.get('title') or ''}"
            )

        if len(resolvable) > 25:
            print(f"   ...and {len(resolvable) - 25} more")

    if unparseable:

        print()
        print("   Left alone, nothing to write:")

        for document in unparseable[:10]:
            print(
                f"   {str(document['_id']):28} "
                f"{document.get('title') or ''}"
            )

        if len(unparseable) > 10:
            print(f"   ...and {len(unparseable) - 10} more")

    if not args.apply:

        print()
        print("DRY RUN - nothing was changed. Re-run with --apply to store")
        print(f"the {len(resolvable)} series ids listed above.")

        client.close()
        return 0

    written = 0
    skipped = 0
    placeholder = 0

    for document, series_id in resolvable:

        block = document.get("festival")

        if isinstance(block, dict):

            # The missing-field condition travels with the write, so a series
            # id stored between the read and here is never replaced by this
            # script's parse of the same address, and the block must still be
            # a block: a placeholder that became one between read and write is
            # somebody else's document, and this write steps aside.
            result = await database.events.update_one(
                {
                    "_id": document["_id"],
                    **MISSING_SERIES,
                    "festival": {"$type": "object"},
                },
                {"$set": {"festival.series_id": series_id}},
            )

        else:

            # A `null` (or absent) festival field cannot hold a subfield, so
            # the series id lands as the minimal block in the placeholder's
            # place - and only while the field is still null, so a block
            # written in the meantime is never replaced.
            result = await database.events.update_one(
                {
                    "_id": document["_id"],
                    **MISSING_SERIES,
                    "festival": None,
                },
                {"$set": {"festival": {"series_id": series_id}}},
            )

            placeholder += result.modified_count

        written += result.modified_count
        skipped += 1 - result.modified_count

    print()
    print("APPLIED")
    print(f"   series ids stored : {written}")
    print(f"   already there     : {skipped}")
    print(f"   of which minimal blocks replaced null placeholders: "
          f"{placeholder}")

    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
