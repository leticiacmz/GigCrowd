"""Give each event the artist slugs its own lineup already resolves to.

A festival edition stores two views of the same fact: the structured `lineup`
the source announced, and the `artist_slugs` that make those performers
findable through the artist-event association. A resync that carried a lineup
but whose slug derivation had not yet run - or a lineup entry that arrived
after the association was written - leaves the two disagreeing: the artist
exists locally under a Songkick id, the event names them, and the association
still misses them, so the performer never appears on their own GigCrowd page
under that event.

This reports those records and, only when asked, adds the missing slugs.
Three rules it holds itself to:

1. Nothing is invented. A slug is written only when the lineup entry carries
   a Songkick id that resolves, in the artists collection, to exactly one
   slug - the same refusal-to-guess rule the read-time resolver applies
   (`inventory_atlas.digits_to_slug` mirrors it). An id claimed by two slugs
   is ambiguous and stays untouched.
2. Nothing else is touched, nothing is ever removed. The write is a single
   `$addToSet`: the lineup, the dates, the singular legacy `artist_slug` and
   every stored slug stay exactly as they are, and a second run finds
   nothing to add.
3. No artist is created and no event is deleted. Lineup entries that do not
   resolve locally are counted and left alone.

Dry-run by default:

    python -m app.scripts.backfill_artist_lineup_slugs
    python -m app.scripts.backfill_artist_lineup_slugs --limit 500
    python -m app.scripts.backfill_artist_lineup_slugs --apply
"""
from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict

from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings
from app.scripts.inventory_atlas import (
    ARTIST_PROJECTION,
    lineup_songkick_ids,
    songkick_digits,
)


def digits_to_slug_map(artists: list[dict]) -> tuple[dict, int]:
    """Songkick digits to the single slug claiming them, plus ambiguity count.

    Two slugs on one id is the ambiguity the resolver refuses to guess at;
    the map refuses it too, so this backfill never writes a guess.
    """

    digits_to_slugs: dict[str, set[str]] = defaultdict(set)

    for artist in artists:

        digits = songkick_digits(
            (artist.get("external_ids") or {}).get("songkick")
        )

        if digits is not None and artist.get("slug"):
            digits_to_slugs[digits].add(artist["slug"])

    ambiguous = sum(
        1 for slugs in digits_to_slugs.values() if len(slugs) > 1
    )

    digits_to_slug = {
        digits: next(iter(slugs))
        for digits, slugs in digits_to_slugs.items()
        if len(slugs) == 1
    }

    return digits_to_slug, ambiguous


def missing_slugs_for(document: dict, digits_to_slug: dict) -> list[str]:
    """The lineup's locally resolved slugs this event does not store yet.

    Legacy spellings are honoured (`songkickId`, singular `artist_slug`) by
    the helpers this reuses, so an older document is not reported as missing
    what it stores under the old key.
    """

    stored = set(document.get("artist_slugs") or [])

    singular = document.get("artist_slug") or ""

    if singular:
        stored.add(singular)

    resolved = {
        digits_to_slug[digits]
        for digits in lineup_songkick_ids(document.get("lineup"))
        if digits in digits_to_slug
    }

    return sorted(resolved - stored)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--apply",
        action="store_true",
        help="store the missing slugs (without this, nothing is changed)",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=5000,
        help="how many events to visit in one run",
    )

    args = parser.parse_args()

    client = AsyncIOMotorClient(
        settings.MONGODB_URL, tz_aware=True
    )

    database = client[settings.DATABASE_NAME]

    artists = await database.artists.find(
        {}, ARTIST_PROJECTION
    ).to_list(length=None)

    digits_to_slug, ambiguous_ids = digits_to_slug_map(artists)

    events = await database.events.find(
        {"lineup": {"$exists": True, "$ne": []}},
        {
            "_id": 1,
            "title": 1,
            "lineup": 1,
            "artist_slugs": 1,
            "artist_slug": 1,
        },
    ).limit(max(args.limit, 0)).to_list(length=None)

    resolvable: list[tuple[dict, list[str]]] = []
    nothing_to_add = 0
    entries_without_local_artist = 0

    for document in events:

        missing = missing_slugs_for(document, digits_to_slug)

        if missing:
            resolvable.append((document, missing))
        else:
            nothing_to_add += 1

        lineup_ids = lineup_songkick_ids(document.get("lineup"))

        entries_without_local_artist += sum(
            1
            for digits in lineup_ids
            if digits not in digits_to_slug
        )

    print("=" * 72)
    print("CANDIDATES")
    print("=" * 72)
    print(f"   events with a lineup visited     : {len(events)}")
    print(f"   slugs already complete           : {nothing_to_add}")
    print(f"   events missing a resolved slug   : {len(resolvable)}")
    print(f"   lineup entries without one local "
          f"artist (left alone) : {entries_without_local_artist}")
    print(f"   ambiguous artist ids (refused)   : {ambiguous_ids}")

    if resolvable:

        print()
        print(f"   {'_id':28} would gain")
        print(f"   {'':28} title")

        for document, missing in resolvable[:25]:
            print(
                f"   {str(document['_id']):28} "
                f"{', '.join(missing)}"
            )
            print(
                f"   {'':28} "
                f"{document.get('title') or ''}"
            )

        if len(resolvable) > 25:
            print(f"   ...and {len(resolvable) - 25} more")

    if not args.apply:

        print()
        print("DRY RUN - nothing was changed. Re-run with --apply to store")
        print(f"the slugs for {len(resolvable)} events listed above.")

        client.close()
        return 0

    written = 0

    for document, missing in resolvable:

        # `$addToSet` is the whole safety story: it can only add, adding an
        # already-stored slug is a no-op, and no other field is named, so
        # the lineup, the dates and the legacy singular slug are outside
        # this write by construction.
        result = await database.events.update_one(
            {"_id": document["_id"]},
            {"$addToSet": {"artist_slugs": {"$each": missing}}},
        )

        written += result.modified_count

    print()
    print("APPLIED")
    print(f"   events updated              : {written}")
    print(f"   slugs written in total      : "
          f"{sum(len(m) for _, m in resolvable)}")

    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
