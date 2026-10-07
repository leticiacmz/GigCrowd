"""A read-only census of what is still incomplete.

Every figure this prints is counted from the database as it is right now, so a
report can be written before anything is changed and compared with a run after.
Nothing here writes.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from app.database.connection import db
from app.providers.songkick.client import SongkickClient


async def event_census() -> dict[str, Any]:
    events = database.events

    total = await events.count_documents({})

    undated = await events.count_documents(
        {
            "$or": [
                {"starts_at": {"$exists": False}},
                {"starts_at": None},
            ]
        }
    )

    missing_date_status = await events.count_documents(
        {
            "$or": [
                {"date_status": {"$exists": False}},
                {"date_status": None},
            ]
        }
    )

    parser_failed = await events.count_documents(
        {"date_status": "parser_failed"}
    )

    date_unavailable = await events.count_documents(
        {"date_status": "unavailable"}
    )

    date_from_source = await events.count_documents(
        {"date_status": "source"}
    )

    missing_lineup = await events.count_documents(
        {
            "$or": [
                {"lineup": {"$exists": False}},
                {"lineup": None},
                {"lineup": []},
            ]
        }
    )

    missing_location = await events.count_documents(
        {
            "$or": [
                {"location": {"$exists": False}},
                {"location": None},
                {"location": {}},
            ]
        }
    )

    # The naive figure above is misleading on its own. An event stores a venue
    # slug, and the place it happens is held by that venue document, so an event
    # with no inline `location` still has a location whenever its venue resolves.
    # Both numbers are reported so the difference is visible rather than
    # mistaken for a backlog.
    venue_slugs = {
        document["slug"]
        for document in await database.venues.find(
            {}, {"slug": 1}
        ).to_list(length=None)
        if document.get("slug")
    }

    without_venue_document = 0

    async for event in events.find(
        {
            "$or": [
                {"location": {"$exists": False}},
                {"location": None},
                {"location": {}},
            ]
        },
        {"venue_slug": 1},
    ):
        slug = event.get("venue_slug")

        if not slug or slug not in venue_slugs:
            without_venue_document += 1

    # A legacy row may hold its place as a plain string instead of an object.
    string_location = await events.count_documents(
        {"location": {"$type": "string"}}
    )

    festivals = await events.count_documents(
        {"event_type": "FestivalInstance"}
    )

    with_festival_identity = await events.count_documents(
        {
            "festival.series_id": {
                "$exists": True,
                "$nin": [None, ""],
            }
        }
    )

    return {
        "events_total": total,
        "events_undated": undated,
        "events_missing_date_status": missing_date_status,
        "date_status_source": date_from_source,
        "date_status_unavailable": date_unavailable,
        "date_status_parser_failed": parser_failed,
        "events_missing_lineup": missing_lineup,
        "events_missing_location": missing_location,
        "events_with_no_resolvable_place": without_venue_document,
        "events_with_string_location": string_location,
        "festival_instances": festivals,
        "events_with_festival_identity": with_festival_identity,
    }


async def lineup_census() -> dict[str, Any]:
    """How the stored lineup looks, and how much of it resolves to an artist."""

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
            }
        },
    ]

    cursor = database.events.aggregate(pipeline)

    entries = 0
    with_songkick = 0
    names: dict[str, int] = {}
    songkick_ids: set[str] = set()
    entries_list: list[dict] = []

    async for item in cursor:
        entries += 1

        name = (item.get("name") or "").strip()
        songkick_id = item.get("songkick_id")

        if songkick_id:
            with_songkick += 1
            songkick_ids.add(str(songkick_id))
        elif name:
            names[name] = names.get(name, 0) + 1

        if len(entries_list) < 3:
            entries_list.append(item)

    # Artists store the Songkick id inside `external_ids`, in the prefixed form
    # a Songkick artist URL uses, rather than in a top-level field.
    artists_with_songkick = await database.artists.count_documents(
        {
            "external_ids.songkick": {
                "$exists": True,
                "$nin": [None, ""],
            }
        }
    )

    artists_total = await database.artists.count_documents({})

    # How many distinct Songkick ids in the lineups already exist on an artist.
    resolved = 0

    if songkick_ids:
        cursor = database.artists.find(
            {
                "external_ids.songkick": {
                    "$in": [
                        f"Artist{songkick_id}"
                        for songkick_id in songkick_ids
                    ]
                }
            },
            {"external_ids.songkick": 1, "slug": 1},
        )
        found = await cursor.to_list(length=None)
        resolved = len(
            {
                str((d.get("external_ids") or {}).get("songkick"))
                for d in found
            }
        )

    return {
        "lineup_entries": entries,
        "lineup_entries_with_songkick_id": with_songkick,
        "lineup_entries_without_songkick_id": entries - with_songkick,
        "distinct_songkick_ids_in_lineups": len(songkick_ids),
        "artists_total": artists_total,
        "artists_with_songkick_id": artists_with_songkick,
        "songkick_ids_resolving_to_an_artist": resolved,
        "distinct_unmatched_names": len(names),
        "sample_entries": entries_list,
    }


async def show_log_census() -> dict[str, Any]:
    pipeline = [
        {"$group": {"_id": "$status", "count": {"$sum": 1}}}
    ]

    counts: dict[str, int] = {}

    cursor = database.show_logs.aggregate(pipeline)

    async for item in cursor:
        counts[str(item.get("_id"))] = item["count"]

    users = await database.users.count_documents({})

    return {
        "users": users,
        "show_logs_total": sum(counts.values()),
        "by_status": counts,
    }


async def artist_field_census() -> dict[str, Any]:
    """The shape of an artist document, for spotting schema drift.

    The Songkick id lives inside `external_ids`, so its presence there is what
    lineup resolution depends on.
    """

    sample = await database.artists.find_one({})

    return {
        "artist_fields": sorted(sample.keys()) if sample else [],
        "external_ids_fields": (
            sorted((sample.get("external_ids") or {}).keys())
            if sample
            else []
        ),
    }


async def main():
    await db.connect()

    # `db` is the project's connection wrapper; the collections live on the
    # motor database it hands back.
    database = db.get_database()

    globals()["database"] = database

    try:
        report = {
            "events": await event_census(),
            "lineup": await lineup_census(),
            "show_logs": await show_log_census(),
            "artists": await artist_field_census(),
        }

        print(json.dumps(report, indent=2, default=str))

    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())

