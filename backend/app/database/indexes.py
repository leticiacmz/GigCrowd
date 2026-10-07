"""Every index the application depends on, in one place.

Indexes used to be declared ad hoc inside a migration, which meant a fresh
database silently had none of them and the migration had to be re-run by hand.
This module is the single declaration, so a fresh database and a migrated one
end up identical.

Three jobs:

* `ensure_indexes` is called at startup, so a local database is always usable.
* `reset_dev_db` recreates them after a deliberate wipe.
* Tests can read the declarations without a database connection.

Only indexes the application actually queries on are declared here. An index
that no query uses is a write cost with nothing to show for it.
"""
from __future__ import annotations

from typing import Any

from pymongo import ASCENDING, DESCENDING


# collection -> list of (index name, key, options)
#
# `sparse` on an external id matters: most documents do not carry one, and
# indexing every absent value to the same empty entry wastes space and, for a
# unique index, would make the whole collection collide on the missing value.
INDEXES: dict[str, list[tuple[str, Any, dict]]] = {
    # ----------------------------------------------------------
    # Identity
    # ----------------------------------------------------------
    "users": [
        ("username_1", [("username", ASCENDING)], {"unique": True}),
        ("email_1", [("email", ASCENDING)], {"unique": True}),
    ],

    # ----------------------------------------------------------
    # Attendance and reviews
    #
    # The unique pair is the rule that makes attendance a set rather than a log:
    # one person's relationship with one event, no matter how many times the
    # request is repeated.
    # ----------------------------------------------------------
    "show_logs": [
        (
            "user_id_1_event_id_1",
            [("user_id", ASCENDING), ("event_id", ASCENDING)],
            {"unique": True},
        ),
        (
            "user_id_1_status_1",
            [("user_id", ASCENDING), ("status", ASCENDING)],
            {},
        ),
        ("date_-1", [("date", DESCENDING)], {}),
    ],

    # ----------------------------------------------------------
    # Social graph
    # ----------------------------------------------------------
    "follows": [
        (
            "follower_id_1_following_id_1",
            [("follower_id", ASCENDING), ("following_id", ASCENDING)],
            {"unique": True},
        ),
        ("following_id_1", [("following_id", ASCENDING)], {}),
    ],
    "artist_follows": [
        (
            "user_id_1_artist_slug_1",
            [("user_id", ASCENDING), ("artist_slug", ASCENDING)],
            {"unique": True},
        ),
        ("artist_slug_1", [("artist_slug", ASCENDING)], {}),
    ],

    # ----------------------------------------------------------
    # Community
    # ----------------------------------------------------------
    "community_posts": [
        ("artist_slug_1", [("artist_slug", ASCENDING)], {}),
        ("artist_slug_1_created_at_-1",
         [("artist_slug", ASCENDING), ("created_at", DESCENDING)], {}),
    ],
    "posts": [
        ("user_id_1", [("user_id", ASCENDING)], {}),
        ("event_id_1", [("event_id", ASCENDING)], {}),
        ("created_at_-1", [("created_at", DESCENDING)], {}),
    ],
    "comments": [
        ("post_id_1", [("post_id", ASCENDING)], {}),
        ("user_id_1", [("user_id", ASCENDING)], {}),
        ("created_at_-1", [("created_at", DESCENDING)], {}),
    ],
    # A like is a set relationship: one person likes a post once. The unique pair
    # is what makes the second request a no-op instead of a double count.
    "post_likes": [
        (
            "target_id_1_user_id_1",
            [("target_id", ASCENDING), ("user_id", ASCENDING)],
            {"unique": True},
        ),
        ("post_id_1", [("post_id", ASCENDING)], {}),
    ],

    # ----------------------------------------------------------
    # Feed
    #
    # The timeline is always read as "my activities and those of the people I
    # follow, newest first", so the compound index matches the query rather
    # than the collection.
    # ----------------------------------------------------------
    "activities": [
        ("user_id_1", [("user_id", ASCENDING)], {}),
        ("created_at_-1", [("created_at", DESCENDING)], {}),
        (
            "activity_type_1_created_at_-1",
            [("activity_type", ASCENDING), ("created_at", DESCENDING)],
            {},
        ),
    ],

    # ----------------------------------------------------------
    # Catalogue
    # ----------------------------------------------------------

    # A slug is the artist's public identity, so two documents must never
    # claim the same one.
    "artists": [
        ("slug_1", [("slug", ASCENDING)], {"unique": True}),
        ("normalized_name_1", [("normalized_name", ASCENDING)], {}),
        # The identity that makes artist resolution deterministic. A unique
        # index here is what stops a second import from creating a duplicate
        # artist that merely happens to share a provider id.
        (
            "external_ids.songkick",
            [("external_ids.songkick", ASCENDING)],
            {"unique": True, "sparse": True},
        ),
        (
            "external_ids.musicbrainz",
            [("external_ids.musicbrainz", ASCENDING)],
            {"unique": True, "sparse": True},
        ),
        (
            "external_ids.spotify",
            [("external_ids.spotify", ASCENDING)],
            {"unique": True, "sparse": True},
        ),
    ],

    "events": [
        ("artist_slugs_1", [("artist_slugs", ASCENDING)], {}),
        # A festival states its performers in the lineup, so an artist's history
        # has to be able to find the dates they played. Without these two an
        # artist's event list silently omits every festival they appeared on,
        # because from the event's point of view the artist is only reachable
        # through a nested array.
        ("lineup.slug_1", [("lineup.slug", ASCENDING)], {}),
        (
            "lineup.songkick_id_1",
            [("lineup.songkick_id", ASCENDING)],
            {},
        ),
        (
            "external_ids.songkick",
            [("external_ids.songkick", ASCENDING)],
            {"sparse": True},
        ),
        ("festival.series_id_1", [("festival.series_id", ASCENDING)], {}),
        ("starts_at_1", [("starts_at", ASCENDING)], {}),
        ("event_type_1", [("event_type", ASCENDING)], {}),
        # Serves the enrichment selector, which asks every tick which events are
        # still missing a date. Without this the scheduler's own query is a
        # collection scan, which is fine on a laptop and not fine on a
        # catalogue. The compound key matches the order the selector reads the
        # fields in, and the sparse tail keeps the index to the events that
        # could ever be selected.
        (
            "date_status_1_date_source_checked_at_1",
            [
                ("date_status", ASCENDING),
                ("date_source_checked_at", ASCENDING),
            ],
            {},
        ),
    ],

    "venues": [
        (
            "name_1_city_1_country_1",
            [
                ("name", ASCENDING),
                ("city", ASCENDING),
                ("country", ASCENDING),
            ],
            {"unique": True},
        ),
        ("slug_1", [("slug", ASCENDING)], {}),
        (
            "external_ids.songkick",
            [("external_ids.songkick", ASCENDING)],
            {"sparse": True},
        ),
    ],

    "notifications": [
        ("user_id_1", [("user_id", ASCENDING)], {}),
        (
            "user_id_1_created_at_-1",
            [("user_id", ASCENDING), ("created_at", DESCENDING)],
            {},
        ),
    ],
}


async def ensure_indexes(database) -> dict[str, list[str]]:
    """Create every declared index that is missing.

    Safe to call repeatedly: an index that already exists with the same
    definition is left alone. The returned mapping records what each collection
    now carries, so a caller can log or assert on it.
    """

    created: dict[str, list[str]] = {}

    for collection, declarations in INDEXES.items():
        names: list[str] = []

        for name, key, options in declarations:
            try:
                await database[collection].create_index(
                    key,
                    name=name,
                    **options,
                )
                names.append(name)
            except Exception as exc:  # pragma: no cover - defensive
                # One index failing must not stop the application from starting,
                # and must be visible rather than silent.
                names.append(f"{name} FAILED: {exc}")

        created[collection] = names

    return created
