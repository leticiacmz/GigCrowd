"""The development seed must not invent timestamps from the future.

`build_dataset()` is pure - it builds every document in memory and touches no
database - so the whole fixture can be checked here without seeding anything.

The defect this pins down: the dataset's "present" is a *future* scenario anchor,
so deriving history by subtracting from it produced dates that were still in the
future. Three seeded community posts came out on 8, 15 and 17 October against a
present of 5 October, and a newly created post therefore sorted below seeded ones
and appeared to be older than the person who had just written it.

The rule being asserted is narrow and checkable: anything that represents
something a person did is in the past. Shows and announcements are allowed to be
in the future, because that is the point of a want-to-go list.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from app.scripts.seed_dev_data import (
    ANCHOR,
    PAST_ANCHOR,
    build_dataset,
    days_ago,
    days_ahead,
)

# Collections whose timestamps describe something a person already did. A post
# dated next week is not a post; it is a scheduled one, and GigCrowd has no
# concept of that.
HISTORY_COLLECTIONS = (
    "community_posts",
    "posts",
    "comments",
    "post_likes",
    "activities",
    "notifications",
    "users",
    "artists",
    "venues",
    "artist_follows",
    "follows",
    "show_logs",
)

TIMESTAMP_FIELDS = ("created_at", "updated_at", "when")

# Events are the deliberate exception: a want-to-go show is supposed to be ahead of
# the reader. Asserting the whole dataset has no future timestamp would therefore
# be asserting something false, and would push the fix towards flattening the
# fixture into a past that has no upcoming shows in it.
FORWARD_COLLECTIONS = ("events",)


def dataset() -> dict:
    return build_dataset()


class TestTheAnchors:
    def test_the_scenario_present_is_in_the_future(self):
        # The want-to-go and announcement fixtures are meant to be ahead of the
        # reader. Stating it makes the split with history deliberate.
        assert ANCHOR > PAST_ANCHOR

    def test_both_anchors_are_fixed_instants(self):
        # Not read from the clock, so the fixture is reproducible.
        assert isinstance(ANCHOR, datetime)
        assert isinstance(PAST_ANCHOR, datetime)

    def test_history_is_measured_from_the_past_anchor(self):
        assert days_ago(0) == PAST_ANCHOR

    def test_the_future_is_measured_from_the_scenario_anchor(self):
        assert days_ahead(0) == ANCHOR

    def test_more_days_ago_is_always_older(self):
        assert days_ago(30) < days_ago(3)


class TestNothingSeededIsDatedInTheFuture:
    @pytest.mark.parametrize("collection", HISTORY_COLLECTIONS)
    def test_no_history_row_carries_a_future_timestamp(
        self, collection
    ):
        rows = dataset().get(collection) or []

        assert rows, f"{collection} produced no rows to check"

        # A fixed reference rather than `now`, so this test is a statement about
        # the fixture and not about the day it happens to be run. It is set past
        # any plausible present: if a row here were in the future relative to the
        # scenario's own anchor it would be even more certainly wrong.
        reference = datetime.fromtimestamp(
            ANCHOR.timestamp(), tz=ANCHOR.tzinfo
        )

        for row in rows:

            for field in TIMESTAMP_FIELDS:

                value = row.get(field)

                if not isinstance(value, datetime):
                    continue

                assert value <= reference, (
                    f"{collection} row "
                    f"{row.get('_id')} has {field}={value}, "
                    f"which is after the scenario present "
                    f"{reference}"
                )

    def test_the_three_posts_that_broke_it_are_in_the_past(self):
        # The specific failure, named rather than left to the general assertion
        # above so a regression points at the cause.
        posts = dataset()["community_posts"]

        assert len(posts) >= 3

        for post in posts:

            assert post["created_at"] <= PAST_ANCHOR, (
                f"community post {post['_id']} is dated "
                f"{post['created_at']}"
            )

    def test_the_three_posts_are_not_all_the_same_age(self):
        # A cheap way to catch a "fix" that just stamped everything with one
        # constant: the posts have to stay distinct, or the feed stops being a
        # feed.
        posts = dataset()["community_posts"]

        stamps = {post["created_at"] for post in posts}

        assert len(stamps) == len(posts)


class TestWhatIsStillAllowedToBeInTheFuture:
    def test_events_are_still_in_the_future(self):
        # The fix must not flatten the dataset. A development environment with no
        # upcoming shows would test nothing about upcoming behaviour.
        events = dataset()["events"]

        future = [
            event
            for event in events
            if isinstance(event.get("starts_at"), datetime)
            and event["starts_at"] > PAST_ANCHOR
        ]

        assert future, "no seeded event is in the future"

    def test_a_show_somebody_has_not_attended_yet_still_exists(self):
        # The want-to-go and maybe cards have to keep something to render. The
        # seed's vocabulary is `went` / `going` / `maybe`, not the profile's
        # `want_to_go` label.
        logs = dataset()["show_logs"]

        statuses = {log.get("status") for log in logs}

        assert "went" in statuses
        assert statuses & {"going", "maybe"}

    def test_every_seeded_row_belongs_to_a_known_collection(self):
        # Guards the collection list above against drifting out of step with the
        # seed, which would otherwise turn these assertions into no-ops.
        assert set(dataset()) == set(
            HISTORY_COLLECTIONS
        ) | set(FORWARD_COLLECTIONS)


class TestTheDatasetIsStillWellFormed:
    def test_every_document_has_an_id(self):
        rows = dataset()["community_posts"]

        assert all(row.get("_id") is not None for row in rows)

    def test_building_twice_gives_the_same_documents(self):
        # The fixture is reproducible, which is the property that made the seed
        # worth keeping deterministic in the first place.
        first = dataset()["community_posts"]
        second = dataset()["community_posts"]

        assert first == second

    def test_it_touches_no_database(self):
        # `build_dataset` is pure. A test that seeds to check a timestamp would be
        # a test that rewrites the development database.
        import inspect

        from app.scripts import seed_dev_data

        source = inspect.getsource(seed_dev_data.build_dataset)

        for forbidden in ("await", "insert_one", "update_one", "db."):
            assert forbidden not in source