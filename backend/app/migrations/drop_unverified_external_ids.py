"""Remove the external ids their own provider does not confirm.

An external id on an artist record is a claim: "this is me at that
provider". The pages that read the claim - the artist page's links,
anything built on `external_ids` - present it as fact, so an id the
provider does not answer for is worse than no id at all: a link that
lands on somebody else, or on nothing, teaches the reader to distrust
every link on the page.

Each value below was looked up as-is against its own provider by an
exact-key read - never a search, so nothing here is a name match -
while researching the artist links page:

* Spotify, six values: three answer 404 on the catalog lookup
  (Gal Costa, Demi Lovato, Tim Bernardes), two have no public player
  page either (Marina Sena, Rubel), and one answers "Daft Punk"
  (O Terno's id).
* MusicBrainz, seven values: six answer 404, and the one stored on
  Arctic Monkeys resolves to "Various Artists".

Arctic Monkeys' Spotify id (7Ln80lUS6He07XvHI8qqHH) answers with
Arctic Monkeys and is deliberately absent from the list; every
Songkick id is untouched, because the Songkick provider reads those
ids on every request and they are the primary identity. A field is
only unset when the stored value is exactly one of the ids above, so
a verified id that happens to share the field is safe.

The seed writes the same truth now (see `seed_dev_data.py`), so a
fresh environment never carries these values; this migration corrects
environments seeded before that fix.

Usage, from `backend/`:

    # What would change, and why. Reads only, writes nothing.
    python -m app.migrations.drop_unverified_external_ids

    # Actually remove them.
    python -m app.migrations.drop_unverified_external_ids --apply
"""
from __future__ import annotations

import asyncio
import sys

from app.database.connection import db

# value -> why the provider says it is not the artist it is stored on.
BAD_IDS: dict[str, dict[str, str]] = {
    "spotify": {
        "7dGJo4pcD2V6oG8ykP7y6Oz": "stored on Marina Sena; the public "
        "player has no such page",
        "1McMsnEElThX1knmY4oliGf": "stored on Rubel; the public player "
        "has no such page",
        "1r7iV2vcSpEnRgtPDVBb1C": "stored on Gal Costa; the catalog "
        "lookup answers 404",
        "4z6W6TZjkFpxQeKFGW5vUx": "stored on Demi Lovato; the catalog "
        "lookup answers 404",
        "5P7o3k6eRHxaqfXuaC5ZUn": "stored on Tim Bernardes; the catalog "
        "lookup answers 404",
        "4tZwfgrHOc3mvqYlEYSvVi": "stored on O Terno; its own page "
        "answers Daft Punk",
    },
    "musicbrainz": {
        "e9e0d2b8-4d4a-4a5f-9a5a-1f4b8f2c9d31": "stored on Marina "
        "Sena; answers 404",
        "89ad4ac3-39f7-470e-963a-56509c546377": "stored on Arctic "
        "Monkeys; resolves to 'Various Artists'",
        "b2a2e0b6-9d7f-4a52-9c7d-6f2c9a1b4e77": "stored on Gal Costa; "
        "answers 404",
        "6d1f0b7a-2c4e-4a3b-9f8d-0e5b6c7a8d90": "stored on Rubel; "
        "answers 404",
        "9f2c1d3e-4b5a-4c6d-8e9f-0a1b2c3d4e5f": "stored on Tim "
        "Bernardes; answers 404",
        "c1d2e3f4-a5b6-4c7d-8e9f-0a1b2c3d4e5f": "stored on O Terno; "
        "answers 404",
        "b2b2e0f2-6d8e-4c1a-9f77-3a5d6c1e9b02": "stored on Demi "
        "Lovato; answers 404",
    },
}


def offenders_query() -> dict:
    """Artists carrying any of the disproved values, by exact value."""
    return {
        "$or": [
            {
                f"external_ids.{source}": {"$in": list(values)}
            }
            for source, values in BAD_IDS.items()
        ]
    }


async def survey() -> list[tuple[str, str, str]]:
    """Each stored id this migration would remove. Reads only."""

    found: list[tuple[str, str, str]] = []

    cursor = db.get_database().artists.find(
        offenders_query(),
        {"name": 1, "external_ids": 1},
    )

    async for document in cursor:
        external = document.get("external_ids") or {}

        for source, values in BAD_IDS.items():
            value = external.get(source)

            if value in values:
                found.append(
                    (
                        document.get("name") or "?",
                        source,
                        values[value],
                    )
                )

    return found


async def migrate() -> int:
    """Remove exactly the disproved values. Returns documents changed."""

    database = db.get_database()

    changed = 0

    cursor = database.artists.find(
        offenders_query(),
        {"name": 1, "external_ids": 1},
    )

    async for document in cursor:

        external = document.get("external_ids") or {}

        # Only fields whose stored value is one of the disproved ids
        # are unset - never the whole field for the source.
        unset: dict[str, str] = {}

        for source, values in BAD_IDS.items():
            if external.get(source) in values:
                unset[f"external_ids.{source}"] = ""

        if not unset:
            continue

        await database.artists.update_one(
            {"_id": document["_id"]},
            {"$unset": unset},
        )

        changed += 1

    return changed


async def main() -> int:
    await db.connect()

    try:
        print()
        print("unverified external ids - survey")
        print("-" * 52)

        found = await survey()

        print(f"  ids that would be removed: {len(found)}")

        for name, source, reason in sorted(found):
            print(f"    {name:<16} {source:<12} {reason}")

        print()

        if "--apply" not in sys.argv:
            print(
                "Nothing was written. Re-run with --apply to remove "
                "them."
            )
            return 0

        changed = await migrate()

        print(f"Removed disproved ids from {changed} artist(s).")

        # The point of the migration is that no artist record carries an
        # identity its provider refuses, so the figure after is the proof.
        remaining = await db.get_database().artists.count_documents(
            offenders_query()
        )

        print(f"Still carrying a disproved id: {remaining}")

        return 0

    finally:
        await db.disconnect()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
