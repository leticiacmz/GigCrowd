"""Make the artists already stored in festival lineups real GigCrowd artists.

The lineup importer runs during an import, so a festival imported from now on
gets its artists as it goes. This covers the ones already in the catalogue: the
lineups that were stored before artists were created for them.

It is the same `LineupArtistImporter` the import path uses, over bounded batches
of distinct Songkick ids. There is no second matching rule here because there is
no second matching rule anywhere.

    python -m app.scripts.import_lineup_artists --dry-run
    python -m app.scripts.import_lineup_artists --apply --limit 500

Read-only unless `--apply`. It creates artist records and nothing else: no
gigography is fetched and no `last_synced_at` is written, so the artist sync job
stays in charge of deciding what gets imported.
"""
from __future__ import annotations

import argparse
import asyncio
import json

from app.database.connection import db
from app.repositories.artist_repository import ArtistRepository
from app.services.lineup_artist_importer import (
    LineupArtistImporter,
)
from app.services.lineup_artist_resolver import (
    external_id_for,
    stored_id_of,
)


async def distinct_lineup_artists(
    limit: int,
    after: str | None = None,
) -> tuple[list[dict], str | None]:
    """The next batch of distinct performers, by Songkick id.

    Read from the events collection with an aggregation rather than by walking
    every event, because a festival's bill is stored once per date and a series
    with thirty artists on three dates would otherwise be read ninety times to
    learn three things.

    Paged by the id rather than by an offset: the batch is derived from a
    `$group`, and an offset over a grouping whose size changes between reads
    skips entries silently.
    """

    events = db.get_database().events

    pipeline = [
        {"$unwind": "$lineup"},
        {
            "$project": {
                "name": "$lineup.name",
                "songkick_id": {
                    "$ifNull": [
                        "$lineup.songkick_id",
                        "$lineup.songkickId",
                    ]
                },
                "image": "$lineup.image",
                "genres": "$lineup.genres",
            }
        },
        {"$match": {"songkick_id": {"$nin": [None, ""]}}},
        {
            "$group": {
                "_id": "$songkick_id",
                "name": {"$first": "$name"},
                "image": {"$first": "$image"},
                "genres": {"$first": "$genres"},
            }
        },
        {"$sort": {"_id": 1}},
    ]

    if after:
        pipeline.append({"$match": {"_id": {"$gt": after}}})

    pipeline.append({"$limit": max(1, int(limit))})

    rows = await events.aggregate(pipeline).to_list(length=None)

    entries = [
        {
            "songkick_id": stored_id_of(str(row["_id"])),
            "name": row.get("name") or "",
            "image": row.get("image"),
            "genres": row.get("genres") or [],
        }
        for row in rows
        if row.get("_id")
    ]

    cursor = (
        str(rows[-1]["_id"]) if rows else after
    )

    return entries, cursor


async def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Create the artists. Without it, nothing is written.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be created. The default.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=250,
        help="Distinct performers per batch.",
    )
    parser.add_argument(
        "--max-batches",
        type=int,
        default=200,
        help="Stop after this many batches.",
    )

    args = parser.parse_args()

    dry_run = not args.apply

    await db.connect()

    database = db.get_database()

    repository = ArtistRepository(database)

    importer = LineupArtistImporter(repository)

    totals = {
        "performers_seen": 0,
        "already_imported": 0,
        "created": 0,
        "skipped_without_a_songkick_id": 0,
        "failed": 0,
    }

    try:
        after: str | None = None

        for batch_number in range(1, args.max_batches + 1):

            entries, after = await distinct_lineup_artists(
                args.batch_size,
                after,
            )

            if not entries:
                break

            if dry_run:
                # Counted, not written. The count is what makes a dry run worth
                # running: it is the number of records the next line would add.
                resolved = await importer.resolver.resolve(
                    [
                        entry["songkick_id"]
                        for entry in entries
                    ]
                )

                already = len(resolved)

                totals["performers_seen"] += len(entries)
                totals["already_imported"] += already
                totals["created"] += len(entries) - already

                print(
                    f"[BATCH {batch_number}] seen={len(entries)} "
                    f"already={already} "
                    f"would_create={len(entries) - already}"
                )

                # A short batch means the ids ran out, not that the work is
                # done. The apply path below stops on "created nothing and
                # failed nothing", which cannot be used here because a dry run
                # creates nothing by design.
                if len(entries) < args.batch_size:
                    break

                continue

            report = await importer.ensure_for_entries(entries)

            totals["performers_seen"] += report.entries
            totals["already_imported"] += (
                report.resolved_existing
            )
            totals["created"] += report.created
            totals["skipped_without_a_songkick_id"] += (
                report.skipped_no_id
            )
            totals["failed"] += report.failed

            print(
                f"[BATCH {batch_number}] {report.summary()}"
            )

            # A batch that added nothing new and did not fail has reached the
            # end of the ids rather than running out of work.
            if report.created == 0 and report.failed == 0:
                break

        after_report = {
            "artists_total": await database.artists.count_documents(
                {}
            ),
            "artists_with_a_songkick_id": (
                await database.artists.count_documents(
                    {
                        "external_ids.songkick": {
                            "$exists": True,
                            "$nin": [None, ""],
                        }
                    }
                )
            ),
        }

        print(
            json.dumps(
                {
                    "stage": "summary",
                    "dry_run": dry_run,
                    **totals,
                    **after_report,
                },
                indent=2,
                default=str,
            )
        )

    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
