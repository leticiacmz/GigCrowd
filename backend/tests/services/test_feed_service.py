"""Feed service behaviour: one timeline, one filter, five real categories.

The contract these tests pin down:

* there is a single activity stream, and `category` only narrows it
* every category maps to real activity types, so no filter returns
  placeholder or fabricated content
* the timeline is scoped to the caller: their own actions, the actions of
  users they follow, and activity inside artist communities they follow
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.models.activity import ActivityType
from app.services import activity_service as activity_module
from app.services.activity_service import (
    FEED_CATEGORIES,
    ActivityService,
    object_id_variants,
)
from tests.support.fake_mongo import FakeDatabase, make_user

ALICE = "aaaaaaaaaaaaaaaaaaaaaaa1"
BOB = "bbbbbbbbbbbbbbbbbbbbbbb2"
CAROL = "ccccccccccccccccccccccc3"

ARTIST_A = "nova-band"
ARTIST_B = "static-hearts"


@pytest.fixture
def db(monkeypatch):
    """A database with one user per role and a couple of artists."""
    now = datetime.now(UTC)

    post_a = {"_id": "post-a", "artist_slug": ARTIST_A, "content": "Nova rules"}
    post_b = {"_id": "post-b", "artist_slug": ARTIST_B, "content": "Static rules"}
    show_log = {
        "_id": "show-1",
        "event_id": "event-1",
        "review": "Incredible night",
        "rating": 5,
        "status": "went",
    }
    plain_show_log = {
        "_id": "show-2",
        "event_id": "event-2",
        "review": None,
        "rating": None,
        "status": "going",
    }

    database = FakeDatabase(
        {
            "users": [
                make_user(ALICE, "alice"),
                make_user(BOB, "bob"),
                make_user(CAROL, "carol"),
            ],
            "artists": [
                {"_id": "artist-a", "slug": ARTIST_A, "name": "Nova"},
                {"_id": "artist-b", "slug": ARTIST_B, "name": "Static Hearts"},
            ],
            "follows": [{"follower_id": ALICE, "following_id": BOB}],
            "artist_follows": [
                {"user_id": ALICE, "artist_slug": ARTIST_A},
            ],
            "community_posts": [post_a, post_b],
            "comments": [
                {
                    "_id": "comment-1",
                    "post_id": "post-a",
                    "artist_slug": ARTIST_A,
                    "content": "Saw them last week!",
                }
            ],
            "show_logs": [show_log, plain_show_log],
            "events": [
                {
                    "_id": "event-1",
                    "title": "Nova at Warehouse",
                    "artist_slug": ARTIST_A,
                    "artist_slugs": [ARTIST_A],
                    "starts_at": now + timedelta(days=3),
                    "venue_slug": "warehouse",
                },
                {
                    "_id": "event-2",
                    "title": "Nova encore",
                    "artist_slug": ARTIST_A,
                    "artist_slugs": [ARTIST_A],
                    "starts_at": now + timedelta(days=9),
                    "venue_slug": "hall",
                },
            ],
            "activities": [
                # Alice's own actions.
                {
                    "_id": "act-own-post",
                    "user_id": ALICE,
                    "activity_type": ActivityType.CREATE_COMMUNITY_POST.value,
                    "target_id": "post-a",
                    "target_type": "community_post",
                    "metadata": {"artist_slug": ARTIST_A},
                    "created_at": now,
                },
                {
                    "_id": "act-own-review",
                    "user_id": ALICE,
                    "activity_type": ActivityType.CREATE_REVIEW.value,
                    "target_id": "show-1",
                    "target_type": "show_log",
                    "metadata": {"artist_slug": ARTIST_A},
                    "created_at": now - timedelta(minutes=1),
                },
                # Bob, whom Alice follows.
                {
                    "_id": "act-bob-comment",
                    "user_id": BOB,
                    "activity_type": ActivityType.COMMENT_POST.value,
                    "target_id": "comment-1",
                    "target_type": "comment",
                    "metadata": {"artist_slug": ARTIST_A},
                    "created_at": now - timedelta(minutes=2),
                },
                # Carol, whom Alice does not follow, in an artist she does not
                # follow: must never reach Alice's feed.
                {
                    "_id": "act-carol-like",
                    "user_id": CAROL,
                    "activity_type": ActivityType.LIKE_POST.value,
                    "target_id": "post-b",
                    "target_type": "community_post",
                    "metadata": {"artist_slug": ARTIST_B},
                    "created_at": now - timedelta(minutes=3),
                },
                {
                    "_id": "act-carol-follow",
                    "user_id": CAROL,
                    "activity_type": ActivityType.FOLLOW.value,
                    "target_id": ALICE,
                    "target_type": "user",
                    "metadata": {},
                    "created_at": now - timedelta(minutes=4),
                },
                {
                    "_id": "act-carol-attend",
                    "user_id": CAROL,
                    "activity_type": ActivityType.ATTEND_EVENT.value,
                    "target_id": "show-2",
                    "target_type": "show_log",
                    "metadata": {"artist_slug": ARTIST_B},
                    "created_at": now - timedelta(minutes=5),
                },
            ],
        }
    )

    monkeypatch.setattr(activity_module, "get_database", lambda: database)
    return database


async def _feed(user_id=ALICE, category="all"):
    activities = await ActivityService.get_feed_activities(
        user_id, category=category
    )
    return {activity["id"] for activity in activities}


class TestObjectIdVariants:
    def test_string_id_yields_both_forms(self):
        from bson import ObjectId

        oid = ObjectId()
        variants = object_id_variants(str(oid))

        assert str(oid) in variants
        assert oid in variants

    def test_non_object_id_string_is_returned_unchanged(self):
        assert object_id_variants("not-an-object-id") == ["not-an-object-id"]


class TestUnifiedTimeline:
    @pytest.mark.asyncio
    async def test_all_category_returns_every_relevant_activity(self, db):
        """One timeline, mixing community, reviews, comments and social."""
        found = await _feed()

        assert found == {
            "act-own-post",
            "act-own-review",
            "act-bob-comment",
        }

    @pytest.mark.asyncio
    async def test_timeline_is_ordered_newest_first(self, db):
        activities = await ActivityService.get_feed_activities(ALICE)

        timestamps = [activity["created_at"] for activity in activities]

        assert timestamps == sorted(timestamps, reverse=True)

    @pytest.mark.asyncio
    async def test_unfollowed_users_and_artists_are_excluded(self, db):
        """Carol's activity is invisible: not followed, unrelated artist."""
        found = await _feed()

        assert not found & {
            "act-carol-like",
            "act-carol-follow",
            "act-carol-attend",
        }

    @pytest.mark.asyncio
    async def test_pagination_slices_the_same_timeline(self, db):
        """Skip/limit paginate the unified stream, they do not replace it."""
        page_one = await ActivityService.get_feed_activities(
            ALICE, skip=0, limit=2
        )
        page_two = await ActivityService.get_feed_activities(
            ALICE, skip=2, limit=2
        )

        assert len(page_one) == 2
        assert len(page_two) == 1
        assert not ({item["id"] for item in page_one} & {
            item["id"] for item in page_two
        })


class TestCategories:
    @pytest.mark.asyncio
    async def test_community_filter_returns_posts_and_comments(self, db):
        found = await _feed(category="community")

        assert found == {"act-own-post", "act-bob-comment"}

    @pytest.mark.asyncio
    async def test_reviews_filter_returns_reviews_only(self, db):
        found = await _feed(category="reviews")

        assert found == {"act-own-review"}

    @pytest.mark.asyncio
    async def test_social_filter_returns_follows_only(self, db):
        """No followed follow is visible, so the filter is legitimately empty
        rather than filled with placeholder rows."""
        found = await _feed(category="social")

        assert found == set()

    @pytest.mark.asyncio
    async def test_events_filter_returns_attendance_only(self, db):
        found = await _feed(category="events")

        assert found == set()

    @pytest.mark.asyncio
    async def test_every_category_returns_only_its_own_types(self, db):
        """No category leaks content that belongs to another one."""
        for category, activity_types in FEED_CATEGORIES.items():
            activities = await ActivityService.get_feed_activities(
                ALICE, category=category
            )
            if not activity_types:
                continue

            allowed = {activity_type.value for activity_type in activity_types}
            for activity in activities:
                assert activity["activity_type"] in allowed

    @pytest.mark.asyncio
    async def test_artist_follow_reveals_that_community_to_the_feed(self, db):
        """Following an artist is what pulls their community into the feed."""
        found = await _feed(category="community")

        assert "act-bob-comment" in found

    @pytest.mark.asyncio
    async def test_unknown_category_is_rejected(self, db):
        with pytest.raises(ValueError, match="Unknown feed category"):
            await ActivityService.get_feed_activities(
                ALICE, category="not-a-category"
            )


class TestEnrichment:
    @pytest.mark.asyncio
    async def test_actor_is_resolved(self, db):
        activities = await ActivityService.get_feed_activities(ALICE)

        by_id = {activity["id"]: activity for activity in activities}

        assert by_id["act-own-post"]["user"]["username"] == "alice"
        assert by_id["act-bob-comment"]["user"]["username"] == "bob"

    @pytest.mark.asyncio
    async def test_community_post_carries_artist_and_content(self, db):
        activities = await ActivityService.get_feed_activities(
            ALICE, category="community"
        )
        post_activity = next(
            item for item in activities if item["id"] == "act-own-post"
        )

        assert post_activity["artist"] == {"slug": ARTIST_A, "name": "Nova"}
        assert post_activity["target"]["kind"] == "community_post"
        assert post_activity["target"]["id"] == "post-a"
        assert post_activity["content"] == "Nova rules"

    @pytest.mark.asyncio
    async def test_review_carries_event_context(self, db):
        activities = await ActivityService.get_feed_activities(
            ALICE, category="reviews"
        )

        assert len(activities) == 1
        review = activities[0]

        assert review["rating"] == 5
        assert review["target"]["kind"] == "event"
        assert review["target"]["title"] == "Nova at Warehouse"
        assert review["target"]["artist_slug"] == ARTIST_A

    @pytest.mark.asyncio
    async def test_comment_target_points_at_its_post(self, db):
        activities = await ActivityService.get_feed_activities(
            ALICE, category="community"
        )
        comment_activity = next(
            item for item in activities if item["id"] == "act-bob-comment"
        )

        assert comment_activity["target"]["kind"] == "comment"
        assert comment_activity["target"]["post_id"] == "post-a"
        assert comment_activity["target"]["artist_slug"] == ARTIST_A

    @pytest.mark.asyncio
    async def test_follow_target_resolves_to_a_profile(self, db):
        """A social row must name and link the person who was followed."""
        db.activities.documents.append(
            {
                "_id": "act-bob-follow",
                "user_id": BOB,
                "activity_type": ActivityType.FOLLOW.value,
                "target_id": ALICE,
                "target_type": "user",
                "metadata": {},
                "created_at": datetime.now(UTC) - timedelta(minutes=6),
            }
        )

        activities = await ActivityService.get_feed_activities(
            ALICE, category="social"
        )
        follow = next(
            item for item in activities if item["id"] == "act-bob-follow"
        )

        assert follow["target"]["kind"] == "profile"
        assert follow["target"]["username"] == "alice"
        assert set(follow["target"]) == {"kind", "id", "username"}

    @pytest.mark.asyncio
    async def test_follow_target_never_exposes_private_fields(self, db):
        """The target lookup is projected: no email, no password hash."""
        loaded = await ActivityService._load_followed_users(db, [ALICE, BOB])

        assert set(loaded) == {ALICE, BOB}
        for entry in loaded.values():
            assert set(entry) == {"id", "username", "full_name", "avatar_url"}

    @pytest.mark.asyncio
    async def test_enrichment_uses_batched_queries(self, db, monkeypatch):
        """Enrichment must not issue a query per activity."""
        calls: list[str] = []

        original_find = type(db.users).find

        def counting_find(self, query=None, projection=None):
            calls.append(self.name)
            return original_find(self, query, projection)

        monkeypatch.setattr(type(db.users), "find", counting_find)
        monkeypatch.setattr(type(db["community_posts"]), "find", counting_find)
        monkeypatch.setattr(type(db.comments), "find", counting_find)
        monkeypatch.setattr(type(db["show_logs"]), "find", counting_find)
        monkeypatch.setattr(type(db.events), "find", counting_find)
        monkeypatch.setattr(type(db.artists), "find", counting_find)

        # Include a follow so both user lookups run: actors and targets.
        db.activities.documents.append(
            {
                "_id": "act-bob-follow",
                "user_id": BOB,
                "activity_type": ActivityType.FOLLOW.value,
                "target_id": ALICE,
                "target_type": "user",
                "metadata": {},
                "created_at": datetime.now(UTC) - timedelta(minutes=6),
            }
        )

        activities = await ActivityService.get_feed_activities(ALICE)

        assert len(activities) == 4
        # One pass per purpose, never per activity. The users collection is
        # read twice: once for the actors, once for the follow targets.
        assert calls.count("users") == 2
        assert calls.count("community_posts") <= 1
        assert calls.count("comments") <= 1
        assert calls.count("artists") == 1
