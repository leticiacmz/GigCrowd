"""A read-only integrity census of the deployed database.

This is the inventory that plans the repair work; it measures the database as
it actually is, without any opinion about what it should be. It counts
documents, groups them, and prints capped samples - and it writes nothing,
fetches nothing from Songkick, and starts no job. The only driver calls it
makes are `find` (always with a projection), `count_documents` and
`index_information`; there is no insert, update, delete, index build or
migration anywhere in this module, and a test asserts that against a fake
database whose write methods raise.

Usage, from `backend/`:

    python -m app.scripts.inventory_atlas
    python -m app.scripts.inventory_atlas --limit 10

Running it against production is still a decision to make deliberately: check
that `DATABASE_NAME` names the database you mean before it is run.

What it examines, and why each section exists:

* event types, including the several spellings of "festival" this project has
  written over time (the canonical-type migration plans from these counts);
* duplicate events by Songkick id (the dedup is find-then-insert without a
  unique index, so duplicates are possible and the repair scope is measured
  here, not assumed);
* festival editions grouped by series, separating "no series id" - a
  structural gap, because festival identity requires one - from everything
  else;
* editions whose stored `artist_slugs` cannot be derived from their lineup,
  split into what is *confirmed* (a lineup artist resolved by Songkick id that
  the stored list is missing) and what merely *needs analysis* (a stored slug
  with no lineup entry behind it - the initiating artist is legitimately
  there, so this is never treated as a fault on its own);
* events with no date and no venue reference, where legacy formats count as
  present: an event is only "missing a venue" when it carries neither
  `venue_slug` nor a `location`;
* activities whose show log or event no longer exists (the feed repair plans
  from these counts; both storage forms of an id are matched);
* the legacy `feed_activities` collection, if it still holds documents;
* artists never synced (stub population) and the `artist-<id>` fallback slug;
* venues sharing a name, never asserting that equal names are the same place;
* the indexes actually present on the relevant collections, when the driver
  can report them.
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
from collections import Counter, defaultdict

# The slug `generate_unique_slug` falls back to when a name cannot produce one
# (non-Latin names). Counting these tells the migration how many artist URLs
# are of this shape.
FALLBACK_SLUG = re.compile(r"^artist-\d+$")

# Artists are stored with the provider's own spelling, `Artist12345`; lineup
# entries carry the bare digits. Both spellings are read here for the same
# reason the resolver reads them: matching only one would silently resolve
# nothing on half the catalogue.
SONGKICK_ARTIST_PREFIX = re.compile(r"^Artist(\d+)$")

# Activity rows about a show log. `target_type` is what current writes store;
# the type check is a fallback for rows written before that field existed.
SHOW_LOG_ACTIVITY_TYPES = frozenset({"attend_event", "create_review"})

# Collections whose indexes are reported.
INDEXED_COLLECTIONS = (
    "events",
    "artists",
    "venues",
    "activities",
    "show_logs",
    "feed_activities",
)

EVENT_PROJECTION = {
    "_id": 1,
    "title": 1,
    "event_type": 1,
    "starts_at": 1,
    "date_status": 1,
    "venue_slug": 1,
    "location": 1,
    "artist_slug": 1,
    "artist_slugs": 1,
    "lineup": 1,
    "festival": 1,
    "external_ids.songkick": 1,
}

ARTIST_PROJECTION = {
    "slug": 1,
    "external_ids.songkick": 1,
    "last_synced_at": 1,
}

VENUE_PROJECTION = {"name": 1, "city": 1, "country": 1}

ACTIVITY_PROJECTION = {
    "_id": 1,
    "activity_type": 1,
    "target_id": 1,
    "target_type": 1,
}

SHOW_LOG_PROJECTION = {"_id": 1, "event_id": 1}


def songkick_digits(value) -> str | None:
    """The numeric Songkick id behind either stored spelling.

    `Artist12345` and `12345` are the same artist; anything that cannot be
    reduced to digits is reported as no id rather than guessed at.
    """

    if not isinstance(value, str):
        return None

    prefixed = SONGKICK_ARTIST_PREFIX.match(value)
    if prefixed:
        return prefixed.group(1)

    if value.isdigit():
        return value

    return None


def lineup_songkick_ids(lineup) -> list[str]:
    """Numeric Songkick ids of one lineup, honouring the legacy camelCase key.

    `songkickId` was written by older documents and is still read by the
    event-artists code; ignoring it here would report every legacy lineup as
    unresolvable.
    """

    identifiers: list[str] = []

    for entry in lineup or []:
        if not isinstance(entry, dict):
            continue

        raw = entry.get("songkick_id")
        if raw is None:
            raw = entry.get("songkickId")

        digits = songkick_digits(raw)
        if digits is not None:
            identifiers.append(digits)

    return identifiers


def is_festival_type(event_type) -> bool:
    """Whether a stored `event_type` says "festival", in any spelling.

    The backend matches on the word; the frontend used to require the exact
    `FestivalInstance`. This census counts every value on its own terms rather
    than deciding which spelling is right - that decision is the migration's.
    """

    return isinstance(event_type, str) and "festival" in event_type.casefold()


def stored_artist_slugs(document: dict) -> set[str]:
    """The event's stored artist slugs, across both storage generations.

    `artist_slug` (singular) is the transitional field; an old document may
    carry only it. Reading only the plural list would report every legacy
    document as having no artists.
    """

    plural = document.get("artist_slugs") or []
    singular = document.get("artist_slug") or ""

    return set(plural) | ({singular} if singular else set())


def event_gaps(document: dict) -> dict:
    """What one stored event is missing, counting legacy formats as present."""

    return {
        "no_start_date": not document.get("starts_at"),
        # A venue is missing only when neither generation of the field says
        # anything: `venue_slug` is current, `location` is the legacy shape.
        "no_venue_reference": not (
            document.get("venue_slug") or document.get("location")
        ),
    }


async def collect(database, limit: int = 5) -> dict:
    """Every section of the census. Reads only, against an injected database.

    `database` is a Motor database handle in production and a `FakeDatabase`
    in tests; nothing here depends on which.
    """

    # -- artists: the resolution map, and the stub population ---------------
    artists = await database.artists.find({}, ARTIST_PROJECTION).to_list(
        length=None
    )

    # Digits to the slugs claiming them. Two slugs on one id is the ambiguity
    # the resolver refuses to guess at, so the map refuses it too.
    digits_to_slugs: dict[str, set[str]] = defaultdict(set)

    for artist in artists:
        digits = songkick_digits(
            (artist.get("external_ids") or {}).get("songkick")
        )
        if digits is not None and artist.get("slug"):
            digits_to_slugs[digits].add(artist["slug"])

    ambiguous_ids = sum(
        1 for slugs in digits_to_slugs.values() if len(slugs) > 1
    )

    # Only an id claimed by exactly one slug resolves. The read-time resolver
    # refuses to guess between claimants, and a census that resolved them
    # anyway would report the resolver's refusals as missing links.
    digits_to_slug = {
        digits: next(iter(slugs))
        for digits, slugs in digits_to_slugs.items()
        if len(slugs) == 1
    }

    synced = 0
    key_absent = 0
    stored_null = 0

    for artist in artists:
        if "last_synced_at" not in artist:
            key_absent += 1
        elif artist["last_synced_at"] is None:
            stored_null += 1
        else:
            synced += 1

    fallback_slugs = sorted(
        artist["slug"]
        for artist in artists
        if artist.get("slug") and FALLBACK_SLUG.match(artist["slug"])
    )

    without_songkick = sum(
        1
        for artist in artists
        if songkick_digits(
            (artist.get("external_ids") or {}).get("songkick")
        )
        is None
    )

    # -- events: one scan, every event-side section -------------------------
    events = await database.events.find({}, EVENT_PROJECTION).to_list(
        length=None
    )

    by_type: Counter = Counter()
    festival_variant_values: Counter = Counter()
    songkick_id_to_events: dict[str, list[str]] = defaultdict(list)
    series_to_editions: dict[str, int] = Counter()
    editions_without_series = 0
    type_says_festival_no_block = 0
    block_present_type_not_festival = 0
    missing_start = 0
    missing_venue = 0
    by_date_status: Counter = Counter()

    editions_with_lineup = 0
    confirmed_missing_link = 0
    needs_analysis_slug = 0
    confirmed_samples: list[dict] = []
    analysis_samples: list[dict] = []

    for document in events:
        event_type = document.get("event_type") or "<unset>"
        by_type[event_type] += 1

        if is_festival_type(document.get("event_type")):
            festival_variant_values[document.get("event_type")] += 1

        songkick_id = songkick_digits(
            (document.get("external_ids") or {}).get("songkick")
        )
        if songkick_id is not None:
            songkick_id_to_events[songkick_id].append(
                str(document.get("_id"))
            )

        festival = document.get("festival") or {}
        has_block = bool(festival)

        if has_block:
            series_id = festival.get("series_id")
            if series_id:
                series_to_editions[str(series_id)] += 1
            else:
                # Confirmed structural gap: festival identity requires a
                # series id, so this edition can never join a series page.
                editions_without_series += 1

            if not is_festival_type(document.get("event_type")):
                block_present_type_not_festival += 1
        elif is_festival_type(document.get("event_type")):
            type_says_festival_no_block += 1

        gaps = event_gaps(document)
        if gaps["no_start_date"]:
            missing_start += 1
        if gaps["no_venue_reference"]:
            missing_venue += 1

        by_date_status[document.get("date_status") or "<unset>"] += 1

        # Lineup versus stored artist slugs, on festival editions only.
        lineup = document.get("lineup") or []
        lineup_ids = lineup_songkick_ids(lineup)

        if has_block and lineup_ids:
            editions_with_lineup += 1

            resolved: set[str] = set()
            for digits in lineup_ids:
                slug = digits_to_slug.get(digits)
                if slug is not None:
                    resolved.add(slug)

            stored = stored_artist_slugs(document)

            missing = resolved - stored
            unexplained = stored - resolved

            if missing:
                confirmed_missing_link += 1
                if len(confirmed_samples) < limit:
                    confirmed_samples.append(
                        {
                            "event_id": str(document.get("_id")),
                            "title": str(document.get("title") or "")[:48],
                            "missing_from_artist_slugs": sorted(missing),
                        }
                    )

            if unexplained:
                needs_analysis_slug += 1
                if len(analysis_samples) < limit:
                    analysis_samples.append(
                        {
                            "event_id": str(document.get("_id")),
                            "title": str(document.get("title") or "")[:48],
                            "slugs_with_no_lineup_id": sorted(unexplained),
                        }
                    )

    duplicate_groups = {
        songkick_id: event_ids
        for songkick_id, event_ids in songkick_id_to_events.items()
        if len(event_ids) > 1
    }

    # -- show logs and activities: what still points at what ---------------
    show_logs = await database.show_logs.find(
        {}, SHOW_LOG_PROJECTION
    ).to_list(length=None)

    show_log_event = {
        str(log.get("_id")): log.get("event_id") for log in show_logs
    }

    event_ids = {str(document.get("_id")) for document in events}

    activities = await database.activities.find(
        {}, ACTIVITY_PROJECTION
    ).to_list(length=None)

    activity_types: Counter = Counter()
    orphan_show_logs = 0
    event_reference_missing = 0
    event_not_found = 0
    orphan_samples: list[dict] = []

    for activity in activities:
        activity_types[activity.get("activity_type") or "<unset>"] += 1

        target_type = activity.get("target_type")
        activity_type = activity.get("activity_type")

        is_show_log_row = target_type == "show_log" or (
            target_type is None and activity_type in SHOW_LOG_ACTIVITY_TYPES
        )

        if not is_show_log_row:
            continue

        target_id = str(activity.get("target_id"))

        if target_id not in show_log_event:
            orphan_show_logs += 1
            issue = "show_log_missing"
        else:
            event_id = show_log_event[target_id]

            if not event_id:
                event_reference_missing += 1
                issue = "event_id_absent_on_show_log"
            elif str(event_id) not in event_ids:
                event_not_found += 1
                issue = "event_missing"
            else:
                continue

        if len(orphan_samples) < limit:
            orphan_samples.append(
                {
                    "activity_id": str(activity.get("_id")),
                    "activity_type": activity_type,
                    "issue": issue,
                }
            )

    # -- the legacy feed collection -----------------------------------------
    feed_total = await database["feed_activities"].count_documents({})

    feed_shapes: Counter = Counter()
    if feed_total:
        legacy = await database["feed_activities"].find({}).to_list(
            length=limit
        )
        for document in legacy:
            feed_shapes[tuple(sorted(document))] += 1

    # -- venues: shared names, without assuming they are the same place -----
    venues = await database.venues.find({}, VENUE_PROJECTION).to_list(
        length=None
    )

    name_to_places: dict[str, set[str]] = defaultdict(set)
    name_counts: Counter = Counter()
    missing_place = 0

    for venue in venues:
        name = (venue.get("name") or "").casefold().strip()
        place = f"{venue.get('city') or '?'}/{venue.get('country') or '?'}"

        if not venue.get("city") or not venue.get("country"):
            missing_place += 1

        if name:
            name_to_places[name].add(place)
            name_counts[name] += 1

    shared_names = {
        name: sorted(places)
        for name, places in name_to_places.items()
        if name_counts[name] > 1
    }

    same_place = {
        name: places
        for name, places in shared_names.items()
        if len(places) == 1
    }
    different_places = {
        name: places
        for name, places in shared_names.items()
        if len(places) > 1
    }

    # -- indexes, when the driver can report them ---------------------------
    indexes: dict[str, dict] = {}

    for name in INDEXED_COLLECTIONS:
        try:
            information = await database[name].index_information()
            indexes[name] = {
                "available": True,
                "indexes": {
                    key: value.get("key")
                    for key, value in information.items()
                },
            }
        except Exception:
            # Not every driver surface (or test double) can report indexes.
            # An inventory that refused to run without them would be worse
            # than one that says they could not be read.
            indexes[name] = {"available": False, "indexes": {}}

    duplicate_events = sorted(
        (
            {
                "songkick_id": songkick_id,
                "count": len(event_ids),
                "event_ids": sorted(event_ids)[:limit],
            }
            for songkick_id, event_ids in duplicate_groups.items()
        ),
        key=lambda group: group["count"],
        reverse=True,
    )

    return {
        "events": {
            "total": len(events),
            "by_event_type": dict(by_type.most_common()),
            "festival_type_values": dict(
                festival_variant_values.most_common()
            ),
            "songkick_duplicates": {
                "groups": len(duplicate_groups),
                "events_involved": sum(
                    len(ids) for ids in duplicate_groups.values()
                ),
                "sample": duplicate_events[:limit],
            },
            "missing_start_date": missing_start,
            "missing_venue_reference": missing_venue,
            "by_date_status": dict(by_date_status.most_common()),
        },
        "festivals": {
            "editions_total": sum(
                1 for document in events if document.get("festival")
            ),
            "series_count": len(series_to_editions),
            "editions_without_series_id": editions_without_series,
            "type_says_festival_but_no_block": type_says_festival_no_block,
            "block_present_but_type_not_festival": (
                block_present_type_not_festival
            ),
            "largest_series": [
                {"series_id": series_id, "editions": count}
                for series_id, count in sorted(
                    series_to_editions.items(),
                    key=lambda item: item[1],
                    reverse=True,
                )[:limit]
            ],
            "lineup_vs_artist_slugs": {
                "editions_with_resolvable_lineup": editions_with_lineup,
                # Confirmed: the read-time resolver will link these artists,
                # so the stored list is provably behind the stored lineup.
                "confirmed_lineup_artist_missing_from_artist_slugs": (
                    confirmed_missing_link
                ),
                "confirmed_samples": confirmed_samples,
                # Needs analysis: the initiating artist is legitimately in
                # `artist_slugs`, so a slug with no lineup id is a question,
                # never a fault on its own.
                "needs_analysis_slugs_with_no_lineup_id": (
                    needs_analysis_slug
                ),
                "needs_analysis_samples": analysis_samples,
            },
        },
        "activities": {
            "total": len(activities),
            "by_type": dict(activity_types.most_common()),
            "show_log_missing": orphan_show_logs,
            "event_id_absent_on_show_log": event_reference_missing,
            "event_missing": event_not_found,
            "samples": orphan_samples,
        },
        "feed_activities": {
            "total": feed_total,
            "field_shapes": {
                "+".join(shape): count
                for shape, count in feed_shapes.items()
            },
        },
        "artists": {
            "total": len(artists),
            "synced": synced,
            "never_synced": key_absent + stored_null,
            "never_synced_key_absent": key_absent,
            "never_synced_stored_null": stored_null,
            "fallback_slugs": len(fallback_slugs),
            "fallback_slug_samples": fallback_slugs[:limit],
            "without_songkick_id": without_songkick,
            "ambiguous_songkick_ids": ambiguous_ids,
        },
        "venues": {
            "total": len(venues),
            "missing_city_or_country": missing_place,
            # Same name, same place: a candidate pair that needs analysis -
            # the unique index should prevent it, so its presence also means
            # the index is missing or was added after these rows.
            "same_name_same_place": len(same_place),
            # Same name, different places: expected (two cities have Camden
            # Theatres), reported as information and never as a fault.
            "same_name_different_places": len(different_places),
            "same_name_same_place_samples": [
                {"name": name, "places": places}
                for name, places in sorted(same_place.items())[:limit]
            ],
            "same_name_different_places_samples": [
                {"name": name, "places": places}
                for name, places in sorted(different_places.items())[:limit]
            ],
        },
        "indexes": indexes,
    }


def render(report: dict) -> str:
    """The report as readable text. Counts first, capped samples after."""

    lines: list[str] = []
    add = lines.append

    add("Atlas integrity inventory (read-only)")
    add("=" * 60)

    events = report["events"]
    add("")
    add(f"EVENTS (total: {events['total']})")
    add("-" * 60)
    add("  by event_type:")
    for value, count in events["by_event_type"].items():
        add(f"    {value:40}: {count}")
    add("  festival-spelling values:")
    for value, count in events["festival_type_values"].items():
        add(f"    {value:40}: {count}")

    duplicates = events["songkick_duplicates"]
    add(
        f"  duplicate Songkick ids: {duplicates['groups']} groups, "
        f"{duplicates['events_involved']} events involved"
    )
    for group in duplicates["sample"]:
        add(
            f"    Event{group['songkick_id']} x{group['count']} "
            f"-> {group['event_ids']}"
        )

    add(f"  missing start date: {events['missing_start_date']}")
    add(f"  missing venue reference: {events['missing_venue_reference']}")
    add(f"  by date_status: {events['by_date_status']}")

    festivals = report["festivals"]
    add("")
    add(
        f"FESTIVALS (editions: {festivals['editions_total']}, "
        f"series: {festivals['series_count']})"
    )
    add("-" * 60)
    add(
        "  editions without series_id "
        f"(confirmed structural gap): {festivals['editions_without_series_id']}"
    )
    add(
        "  festival-typed but no festival block: "
        f"{festivals['type_says_festival_but_no_block']}"
    )
    add(
        "  festival block but type not festival: "
        f"{festivals['block_present_but_type_not_festival']}"
    )
    for entry in festivals["largest_series"]:
        add(
            f"    series {entry['series_id']}: "
            f"{entry['editions']} editions"
        )

    lineup = festivals["lineup_vs_artist_slugs"]
    add(
        "  editions with a resolvable lineup: "
        f"{lineup['editions_with_resolvable_lineup']}"
    )
    add(
        "  CONFIRMED lineup artist missing from artist_slugs: "
        f"{lineup['confirmed_lineup_artist_missing_from_artist_slugs']}"
    )
    for sample in lineup["confirmed_samples"]:
        add(
            f"    {sample['event_id']} {sample['title']!r} "
            f"missing={sample['missing_from_artist_slugs']}"
        )
    add(
        "  NEEDS ANALYSIS artist_slugs entries with no lineup id: "
        f"{lineup['needs_analysis_slugs_with_no_lineup_id']}"
    )
    for sample in lineup["needs_analysis_samples"]:
        add(
            f"    {sample['event_id']} {sample['title']!r} "
            f"slugs={sample['slugs_with_no_lineup_id']}"
        )

    activities = report["activities"]
    add("")
    add(f"ACTIVITIES (total: {activities['total']})")
    add("-" * 60)
    add(f"  by type: {activities['by_type']}")
    add(
        f"  CONFIRMED show log missing: {activities['show_log_missing']}"
    )
    add(
        "  CONFIRMED event missing behind an existing show log: "
        f"{activities['event_missing']}"
    )
    add(
        "  NEEDS ANALYSIS show log with no event_id: "
        f"{activities['event_id_absent_on_show_log']}"
    )
    for sample in activities["samples"]:
        add(
            f"    {sample['activity_id']} "
            f"{sample['activity_type']} -> {sample['issue']}"
        )

    feed = report["feed_activities"]
    add("")
    add(f"LEGACY feed_activities (total: {feed['total']})")
    add("-" * 60)
    for shape, count in feed["field_shapes"].items():
        add(f"    {count} document(s) with keys: {shape}")

    artists = report["artists"]
    add("")
    add(f"ARTISTS (total: {artists['total']})")
    add("-" * 60)
    add(f"  synced: {artists['synced']}")
    add(
        f"  never synced (key absent): {artists['never_synced_key_absent']}"
    )
    add(
        "  never synced (stored null): "
        f"{artists['never_synced_stored_null']}"
    )
    add(f"  fallback artist-<id> slugs: {artists['fallback_slugs']}")
    for slug in artists["fallback_slug_samples"]:
        add(f"    {slug}")
    add(f"  without a Songkick id: {artists['without_songkick_id']}")
    add(f"  ambiguous Songkick ids: {artists['ambiguous_songkick_ids']}")

    venues = report["venues"]
    add("")
    add(f"VENUES (total: {venues['total']})")
    add("-" * 60)
    add(
        "  missing city or country: "
        f"{venues['missing_city_or_country']}"
    )
    add(
        "  NEEDS ANALYSIS same name + same place: "
        f"{venues['same_name_same_place']}"
    )
    for sample in venues["same_name_same_place_samples"]:
        add(f"    {sample['name']!r} -> {sample['places']}")
    add(
        "  information, same name in different places: "
        f"{venues['same_name_different_places']}"
    )
    for sample in venues["same_name_different_places_samples"]:
        add(f"    {sample['name']!r} -> {sample['places']}")

    add("")
    add("INDEXES")
    add("-" * 60)
    for name, entry in report["indexes"].items():
        if not entry["available"]:
            add(f"  {name}: could not be read")
            continue

        for index_name, keys in entry["indexes"].items():
            add(f"  {name}.{index_name}: {keys}")

    add("")
    add("Nothing was written, nothing was fetched, no job was started.")
    return "\n".join(lines)


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "A read-only integrity census of the deployed database."
        )
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="How many samples to print per section (default: 5).",
    )
    arguments = parser.parse_args()

    # Imported here rather than at module scope so that importing this module
    # - which the tests do - never loads configuration or touches a driver.
    from app.database.connection import db

    try:
        await db.connect()
    except Exception:
        # The connection failure is reported without the URI or any
        # credential; `connection.connect` already refuses to print them.
        print("Could not connect. Check the database configuration.")
        return 1

    try:
        report = await collect(db.get_database(), limit=arguments.limit)
        print(render(report))
        return 0
    finally:
        await db.disconnect()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
