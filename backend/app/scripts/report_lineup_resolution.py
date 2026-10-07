"""Report how much of the stored lineup can be linked to a GigCrowd artist.

Usage, from `backend/`:

    python -m app.scripts.report_lineup_resolution

This is read-only and safe to run at any time. It fetches nothing, writes
nothing and takes no locks, so running it twice returns the same numbers - which
is what makes it usable as a before-and-after measurement.

A lineup entry is linkable when its Songkick artist id matches exactly one
imported GigCrowd artist. Entries with no id, with no imported artist, or with
an id that more than one artist claims are reported as unlinked rather than
guessed at.
"""
import asyncio
import json
import sys

from app.database.connection import db
from app.repositories.artist_repository import ArtistRepository
from app.services.lineup_artist_resolver import LineupArtistResolver


async def main() -> int:
    await db.connect()

    database = db.get_database()

    try:
        resolver = LineupArtistResolver(
            ArtistRepository(database)
        )

        report = await resolver.report(database)

        print()
        print("Lineup artist resolution")
        print("-" * 52)

        for key, value in report.as_dict().items():
            print(f"  {key:30}: {value}")

        if report.ambiguous_detail:
            print()
            print("  ambiguous Songkick ids (linked to nothing):")

            for item in report.ambiguous_detail:
                print(
                    f"    {item['songkick_id']:>10} "
                    f"claimed by {item['slugs']}"
                )

        if report.unresolved_sample:
            print()
            print("  sample of ids with no imported artist:")

            for item in report.unresolved_sample:
                print(
                    f"    {item['songkick_id']:>10}  "
                    f"{item['name']}"
                )

        print()
        print(
            "Nothing was fetched and nothing was written. An "
            "unlinked entry is still shown by name on the "
            "festival page."
        )

        return 0

    finally:
        await db.disconnect()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
