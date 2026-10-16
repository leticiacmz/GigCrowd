"""Give the provider-claimed events whose source address was never stored one.

An imported event can be persisted with `source.provider = "songkick"` and no
`source.url`: the enrichment that joins a search document onto an event only
stamped the address when the *search document* carried one, while the same
event's own listing URL was written into `festival.url` beside it. The
provenance rule is right to hide a future event whose provider cannot be
checked, so those rows sit in the database invisible to every future listing.

This reports those records and, only when asked, copies the address the
record itself already stores. Three rules it holds itself to:

1. Nothing is invented. The address written is `festival.url` or
   `festival.official_url` as already persisted, and only when it is an
   absolute `https://www.songkick.com/` address - the exact shape
   `has_concrete_source` accepts. A record whose stored candidate would not
   grant checkability is left alone and reported as inconclusive.
2. Nothing else is touched. Only a *missing* `source.url` is written; the
   provider, the festival block, the lineup, the dates and the artist
   associations stay exactly as they are. The write re-checks the missing
   condition, so a second run finds nothing and a race cannot overwrite an
   address somebody else stored.
3. Nothing is deleted, and an address that is already present - even a
   foreign one - is never replaced.

Dry-run by default:

    python -m app.scripts.backfill_event_source_urls
    python -m app.scripts.backfill_event_source_urls --limit 500
    python -m app.scripts.backfill_event_source_urls --apply
"""
from __future__ import annotations

import argparse
import asyncio
import re
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings
from app.domain.event_provenance import SONGKICK_URL_PREFIX
from app.domain.festival import http_url_or_none

# Where a stored address for the event may already be. Read in the order a
# festival date's own address beats the festival's site: the festival block's
# url first, its official site second. Both are re-validated before writing.
ADDRESS_FIELDS = (
    ("festival", "url"),
    ("festival", "official_url"),
)

# The only shape that grants checkability - the same prefix
# `has_concrete_source` tests, escaped for a query.
ADDRESS_PATTERN = "^" + re.escape(SONGKICK_URL_PREFIX)

# "Claims Songkick and offers no address to check" - every spelling of
# missing the field can have.
MISSING_ADDRESS = {
    "source.provider": "songkick",
    "$or": [
        {"source.url": {"$exists": False}},
        {"source.url": None},
        {"source.url": ""},
    ],
}


def candidates_query() -> dict:
    """Provider-claimed records with no address, whose own block states one.

    Records that already store an address are excluded: they are either
    already verifiable or deliberately foreign, and rewriting one would be a
    change nobody asked for.
    """

    return {
        "$and": [
            MISSING_ADDRESS,
            {
                "$or": [
                    {
                        f"{parent}.{field}": {
                            "$regex": ADDRESS_PATTERN
                        }
                    }
                    for parent, field in ADDRESS_FIELDS
                ]
            },
        ]
    }


def address_stated_by(document: dict) -> Optional[str]:
    """The first stored address of this record a browser can open on Songkick.

    The same precedence `festival_identity` applies, re-validated here rather
    than trusted from the query: the regex narrows the candidate set, this
    decides whether a real address is actually held.
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
            "store the source addresses (without this, nothing is changed)"
        ),
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=5000,
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
    inconclusive = []

    for document in records:

        address = address_stated_by(document)

        if address:
            resolvable.append((document, address))
        else:
            inconclusive.append(document)

    print("=" * 72)
    print("CANDIDATES")
    print("=" * 72)
    print(f"   without a source address      : {len(records)}")
    print(f"   a stored address can be copied: {len(resolvable)}")
    print(f"   no usable stored address      : {len(inconclusive)}")

    if resolvable:

        print()
        print(f"   {'_id':28} title")
        print(f"   {'':28} address")

        for document, address in resolvable[:25]:
            print(
                f"   {str(document['_id']):28} "
                f"{document.get('title') or ''}"
            )
            print(f"   {'':28} {address}")

        if len(resolvable) > 25:
            print(f"   ...and {len(resolvable) - 25} more")

    if inconclusive:

        print()
        print("   Left alone, nothing trustworthy to write:")

        for document in inconclusive[:10]:
            festival = document.get("festival")
            stored = (
                festival.get("url")
                if isinstance(festival, dict)
                else None
            )
            print(
                f"   {str(document['_id']):28} "
                f"{document.get('title') or ''} | "
                f"candidate={stored!r}"
            )

        if len(inconclusive) > 10:
            print(f"   ...and {len(inconclusive) - 10} more")

    if not args.apply:

        print()
        print("DRY RUN - nothing was changed. Re-run with --apply to store")
        print(f"the {len(resolvable)} addresses listed above.")

        client.close()
        return 0

    written = 0
    skipped = 0

    for document, address in resolvable:

        # The missing-address condition travels with the write, so an
        # address stored between the read and here is never replaced.
        result = await database.events.update_one(
            {
                "_id": document["_id"],
                **MISSING_ADDRESS,
            },
            {"$set": {"source.url": address}},
        )

        written += result.modified_count
        skipped += 1 - result.modified_count

    print()
    print("APPLIED")
    print(f"   source addresses stored : {written}")
    print(f"   already there           : {skipped}")

    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
