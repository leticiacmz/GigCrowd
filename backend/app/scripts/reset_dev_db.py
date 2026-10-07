"""Wipe the local development database and put the indexes back.

This is destructive and therefore refuses to run until it has *proved* it is
pointing at a local development database. A misconfigured `MONGODB_URL` is the
one way this script could destroy something that matters, so proving locality is
not a formality.

    # Show what would be dropped. Fetches nothing, drops nothing.
    python -m app.scripts.reset_dev_db

    # Actually reset, then recreate every declared index.
    python -m app.scripts.reset_dev_db --apply

The guard has three parts, and all three must hold:

1. The URI resolves to a loopback host. `localhost`, `127.0.0.1` and `::1` are
   accepted; a hostname, an IP in any range, or `mongodb+srv://` is refused.
2. The database name is one this project uses for development.
3. `--apply` was passed explicitly. There is no "just do it" path.

System collections are never touched, and only collections that actually exist
in this database are dropped - the list is read, not assumed.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from urllib.parse import urlparse

from app.config import settings
from app.database.connection import db
from app.database.indexes import ensure_indexes

# Hosts that can only mean "this machine".
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]", "0.0.0.0"}

# Database names this project is allowed to reset. A deployment that renamed
# the database therefore cannot be wiped by running this.
RESETTABLE_DATABASES = {"gigcrowd", "gigcrowd_dev", "gigcrowd_test"}


class UnsafeTarget(Exception):
    """The configured database cannot be proven to be local development."""


def verify_local_development_target(
    uri: str,
    database_name: str,
) -> str:
    """Return a human-readable confirmation, or refuse.

    The message names what was checked, because "it said it was fine" is not
    something anyone should have to take on trust when a script deletes data.
    """

    parsed = urlparse(uri)

    if parsed.scheme not in {"mongodb", "mongodb+srv"}:
        raise UnsafeTarget(
            f"MONGODB_URL scheme {parsed.scheme!r} is not a MongoDB URI: {uri!r}"
        )

    if parsed.scheme == "mongodb+srv":
        raise UnsafeTarget(
            "MONGODB_URL is a hosted deployment (mongodb+srv). "
            "Refusing to reset a remote database."
        )

    if not parsed.hostname:
        raise UnsafeTarget(f"MONGODB_URL has no host: {uri!r}")

    if parsed.hostname.lower() not in LOCAL_HOSTS:
        raise UnsafeTarget(
            f"MONGODB_URL host {parsed.hostname!r} is not a loopback address. "
            "Refusing to reset what may be a shared or remote database."
        )

    if database_name not in RESETTABLE_DATABASES:
        raise UnsafeTarget(
            f"DATABASE_NAME {database_name!r} is not a recognised development "
            f"database. Expected one of: "
            f"{', '.join(sorted(RESETTABLE_DATABASES))}"
        )

    return (
        f"target verified as local development: "
        f"{parsed.hostname}:{parsed.port or 27017}/{database_name}"
    )


async def survey(database) -> dict:
    """What is in the database right now, and what a reset would remove."""

    names = await database.list_collection_names()

    # `system.*` is MongoDB's own bookkeeping and is never ours to delete.
    application = sorted(
        name for name in names if not name.startswith("system.")
    )

    counts = {
        name: await database[name].count_documents({})
        for name in application
    }

    return {
        "collections": application,
        "counts": counts,
        "documents": sum(counts.values()),
    }


async def reset(database) -> dict:
    """Drop every application collection, then recreate the declared indexes."""

    before = await survey(database)

    for name in before["collections"]:
        await database.drop_collection(name)

    indexes = await ensure_indexes(database)

    after = await survey(database)

    return {
        "dropped": before["counts"],
        "dropped_documents": before["documents"],
        "remaining": after["counts"],
        "indexes": indexes,
    }


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Reset the local development GigCrowd database. "
            "Refuses to run against anything but a loopback address."
        )
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Actually drop the collections. Without this nothing "
            "is deleted."
        ),
    )

    args = parser.parse_args()

    try:
        confirmation = verify_local_development_target(
            settings.MONGODB_URL,
            settings.DATABASE_NAME,
        )
    except UnsafeTarget as exc:
        print()
        print("REFUSING TO RESET")
        print("-" * 52)
        print(f"  {exc}")
        print()
        print(
            "No data was touched. Point MONGODB_URL at a local "
            "development database, or reset it by hand if you are "
            "certain that is what you want."
        )
        return 2

    await db.connect()

    try:
        database = db.get_database()

        if database.name != settings.DATABASE_NAME:  # pragma: no cover
            raise UnsafeTarget(
                f"Connected to {database.name!r} but "
                f"DATABASE_NAME is {settings.DATABASE_NAME!r}"
            )

        print()
        print("Local development database reset")
        print("-" * 52)
        print(f"  {confirmation}")
        print(f"  DEBUG={settings.DEBUG}")

        before = await survey(database)

        print()
        print(f"  {len(before['collections'])} collection(s), "
              f"{before['documents']} document(s):")

        for name, count in before["counts"].items():
            print(f"    {name:24} {count}")

        if not args.apply:
            print()
            print(
                "Nothing was dropped. Re-run with --apply to reset."
            )
            return 0

        result = await reset(database)

        print()
        print(f"  dropped {result['dropped_documents']} document(s) "
              f"from {len(result['dropped'])} collection(s)")

        print()
        print("  indexes recreated:")

        for collection, names in result["indexes"].items():
            print(f"    {collection:20} {', '.join(names)}")

        print()
        print(
            "Database is empty and indexed. Run the seed next:\n"
            "  python -m app.scripts.seed_dev_data --apply"
        )

        return 0

    finally:
        await db.disconnect()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
