"""Bring the seeded development rows in line with the corrected seed.

The seed's definition was fixed: history is now measured from a past anchor, so
`days_ago(3)` no longer lands in the future. Three community posts already in the
development database were written from the old definition and are still dated 8,15
and 17 October against a present of 5 October.

This is not a reseed and not a migration of user data. It touches only documents
whose `_id` is one the seed itself derives from `stable_id`, so anything a person
or the browser suite created is untouched by construction. Re-running it is a
no-op once the rows agree.

Run with --apply. Without it, this only reports.
"""
import asyncio
import sys

sys.path.insert(0, ".")

from datetime import datetime

from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings
from app.scripts.seed_dev_data import PAST_ANCHOR, build_dataset


def seeded_rows() -> dict:
    """The seed's own documents, keyed by collection and id."""

    return build_dataset()


def repaired_timestamps() -> dict[str, dict[str, datetime]]:
    """The timestamp fields every seeded row should carry, keyed by `_id`."""

    wanted: dict[str, dict[str, datetime]] = {}

    for rows in seeded_rows().values():

        for row in rows:

            if not isinstance(row, dict):
                continue

            ident = row.get("_id")

            if ident is None:
                continue

            stamps = {
                field: row[field]
                for field in ("created_at", "updated_at", "when")
                if isinstance(row.get(field), datetime)
            }

            if stamps:
                wanted[str(ident)] = stamps

    return wanted


async def main() -> None:
    apply = "--apply" in sys.argv

    client = AsyncIOMotorClient(settings.MONGODB_URL, tz_aware=True)

    db = client[settings.DATABASE_NAME]

    wanted = repaired_timestamps()

    # Read from the clock here and nowhere else. This script repairs rows that are
    # wrong *relative to now*; the seed's own dates are fixed instants and must
    # stay that way, or the fixture stops being reproducible.
    moment = datetime.now(tz=PAST_ANCHOR.tzinfo)

    print(f"seed defines {len(wanted)} timestamped rows")
    print(f"seed history anchor: {PAST_ANCHOR}")
    print(f"repairing rows dated after: {moment}")
    print()

    total_changed = 0
    untouched = 0

    for collection in await db.list_collection_names():

        # Only collections the seed writes, so this can never reach data the seed
        # does not own.
        if collection not in seeded_rows():
            continue

        rows = await db[collection].find({}).to_list(length=5000)

        for row in rows:

            ident = str(row.get("_id"))

            target = wanted.get(ident)

            if target is None:
                untouched += 1
                continue

            changes = {
                field: value
                for field, value in target.items()
                # Only rows that are actually wrong are touched.
                #
                # Moving the seed's history anchor shifted every seeded date by a
                # fixed offset, so "differs from the seed" is true for 68 rows and
                # true for none of the problem. A row already in the past is not
                # broken, and rewriting it would churn data for no gain. The defect
                # was a timestamp in the *future*, so that is the only condition
                # repaired here.
                if isinstance(row.get(field), datetime)
                and row[field] > moment
                and row[field] != value
            }

            if not changes:
                continue

            total_changed += 1

            print(f"{collection} {ident}")
            print(f"   now : "
                  f"{ {f: str(row.get(f)) for f in changes} }")
            print(f"   seed: "
                  f"{ {f: str(v) for f, v in changes.items()} }")

            if apply:
                await db[collection].update_one(
                    {"_id": row["_id"]},
                    {"$set": changes},
                )

    print()
    print(f"rows needing repair: {total_changed}")
    print(f"rows left alone (not seed-owned): {untouched}")

    if apply:
        print("applied")
    else:
        print("dry run - pass --apply to write")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())