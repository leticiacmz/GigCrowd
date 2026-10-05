"""Label the development fixture's events as fixtures, in place.

Why this exists
---------------
The development seed writes its events with the provider name and a
Songkick-shaped URL, because those are the fields the rest of the system reads
and a fixture has to satisfy them to be usable. Nothing recorded that the rows
were the project's own.

The consequence was concrete: the fixture includes a 2026 show for Gal Costa
and a 2027 festival edition. Both were presented as upcoming events, and both
resolve to HTTP 404 on Songkick. A valid date and a plausible URL are not
provenance.

What this does
--------------
It adds `source.provenance = "fixture"` to those rows and nothing else. No
dates, names, lineups, attendance or references are touched, and no row is
deleted or deactivated: the fixture is what the development database and the
manual test accounts are built on, so removing it would take the product's own
test data with it. The point is that the row says what it is.

Rows are matched by the fixture id block declared once in the domain module, so
this is a lookup rather than a list of names, and no artist is special-cased.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

sys.path.insert(0, ".")

from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings
from app.domain.event_provenance import (
    PROVENANCE_FIXTURE,
    classify,
)


async def audit() -> list[dict]:
    client = AsyncIOMotorClient(settings.MONGODB_URL, tz_aware=True)

    db = client[settings.DATABASE_NAME]

    rows = []

    async for document in db.events.find(
        {"source.provenance": {"$ne": PROVENANCE_FIXTURE}}
    ):
        if classify(document) == PROVENANCE_FIXTURE:
            rows.append(document)

    client.close()

    return rows


async def apply(rows: list[dict]) -> int:
    client = AsyncIOMotorClient(settings.MONGODB_URL, tz_aware=True)

    db = client[settings.DATABASE_NAME]

    changed = 0

    for document in rows:
        await db.events.update_one(
            {"_id": document["_id"]},
            {"$set": {"source.provenance": PROVENANCE_FIXTURE}},
        )

        changed += 1

    client.close()

    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the label. Without it nothing is changed.",
    )

    args = parser.parse_args()

    rows = asyncio.run(audit())

    print(f"fixture events detected: {len(rows)}")

    for document in sorted(rows, key=lambda e: str(e.get("starts_at"))):
        print(
            f"   {str(document.get('starts_at'))[:10]}  "
            f"sk={str((document.get('external_ids') or {}).get('songkick')):10} "
            f"{(document.get('title') or '')[:44]}"
        )

    if not args.apply:
        print()
        print("dry run - nothing written. Re-run with --apply.")

        return

    changed = asyncio.run(apply(rows))

    print()
    print(f"labelled: {changed}")


if __name__ == "__main__":
    main()
