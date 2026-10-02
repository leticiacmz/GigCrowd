"""Profile statistics must be counted from the rows that back them.

The contract these tests pin down:

* a profile accepts either a username or a user id, because
  `/users/me/stats` holds an id and `/users/profile/{username}/stats` holds a
  username, and both report the same figures
* every number is counted from persisted documents, so a profile can never
  show a figure that has no row behind it
* follower and following counts come from the `follows` collection itself, so
  the count on the profile always matches the list behind it
* posts are counted in the collection that actually holds community posts
* artists seen and upcoming shows are resolved in one batched query, so the
  query count does not grow with the number of show logs
* identifiers are matched in either storage form, because older rows keep them
  as strings and newer ones as ObjectId
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from bson import ObjectId

from app.repositories.follow_repository import FollowRepository
from app.repositories.show_log_repository import ShowLogRepository
from app.repositories.user_repository import UserRepository
from app.services.user_profile_service import UserProfileService
from app.services.user_stats_service import UserStatsService
from tests.support.fake_mongo import FakeDatabase, make_user

ALICE = "aaaaaaaaaaaaaaaaaaaaaaa1"
BOB = "bbbbbbbbbbbbbbbbbbbbbbb2"
CAROL = "ccccccccccccccccccccccc3"

NOVA = "nova-band"
STATIC = "static-hearts"


def build_service(db: FakeDatabase) -> UserStatsService:
    return UserStatsService(
        user_repository=UserRepository(db),
        show_log_repository=ShowLogRepository(db),
        follow_repository=FollowRepository(db),
        db=db,
    )


@pytest.fixture
def now():
    return datetime.now(UTC)


@pytest.fixture
def db(now):
    """A database where every statistic has a real row behind it."""
    return FakeDatabase(
        {
            "users": [
                make_user(ALICE, "alice"),
                make_user(BOB, "bob"),
                make_user(CAROL, "carol"),
            ],
            "follows": [
                {"follower_id": BOB, "following_id": ALICE},
                {"follower_id": CAROL, "following_id": ALICE},
            ],
            "community_posts": [
                {"_id": "post-1", "artist_slug": NOVA, "user_id": ALICE},
                {"_id": "post-2", "artist_slug": NOVA, "user_id": ALICE},
                {"_id": "post-3", "artist_slug": STATIC, "user_id": BOB},
            ],
            "show_logs": [
                {
                    "_id": "log-1",
                    "user_id": ALICE,
                    "event_id": "event-past",
                    "status": "went",
                },
                {
                    "_id": "log-2",
                    "user_id": ALICE,
                    "event_id": "event-upcoming",
                    "status": "going",
                },
                {
                    "_id": "log-3",
                    "user_id": ALICE,
                    "event_id": "event-maybe",
                    "status": "maybe",
                },
            ],
            "events": [
                {
                    "_id": "event-past",
                    "title": "Nova at Warehouse",
                    "artist_slug": NOVA,
                    "artist_slugs": [NOVA],
                    "starts_at": now - timedelta(days=10),
                },
                {
                    "_id": "event-upcoming",
                    "title": "Static Hearts tour",
                    "artist_slugs": [STATIC],
                    "starts_at": now + timedelta(days=5),
                },
                {
                    "_id": "event-maybe",
                    "title": "Nova encore",
                    "artist_slugs": [NOVA, STATIC],
                    "starts_at": now + timedelta(days=9),
                },
            ],
        }
    )


class TestRealStatistics:
    @pytest.mark.asyncio
    async def test_attendance_counts_come_from_show_logs(self, db):
        stats = await build_service(db).get_user_stats("alice")

        assert stats["shows_attended"] == 1
        assert stats["shows_going"] == 1
        assert stats["shows_maybe"] == 1

    @pytest.mark.asyncio
    async def test_posts_are_counted_in_the_community_collection(self, db):
        """The collection that holds community posts is the one counted.

        `posts` is a separate, near-empty legacy collection, so counting it
        would report a number with nothing behind it.
        """
        stats = await build_service(db).get_user_stats("alice")

        assert stats["total_posts"] == 2

    @pytest.mark.asyncio
    async def test_social_counts_come_from_the_follows_collection(self, db):
        stats = await build_service(db).get_user_stats("alice")

        assert stats["followers_count"] == 2
        assert stats["following_count"] == 0

    @pytest.mark.asyncio
    async def test_artists_seen_counts_distinct_artist_slugs(self, db):
        """Both the single slug and the array form are counted, once each."""
        stats = await build_service(db).get_user_stats("alice")

        assert stats["artists_seen"] == 2

    @pytest.mark.asyncio
    async def test_upcoming_counts_only_events_still_to_come(self, db):
        stats = await build_service(db).get_user_stats("alice")

        assert stats["upcoming_events"] == 2

    @pytest.mark.asyncio
    async def test_a_user_with_no_activity_reports_zeroes(self, db):
        stats = await build_service(db).get_user_stats("bob")

        assert stats["shows_attended"] == 0
        assert stats["shows_going"] == 0
        assert stats["shows_maybe"] == 0
        assert stats["artists_seen"] == 0
        assert stats["upcoming_events"] == 0
        assert stats["total_posts"] == 1


class TestIdentifierForms:
    @pytest.mark.asyncio
    async def test_an_unknown_identifier_returns_nothing(self, db):
        assert await build_service(db).get_user_stats("nobody") is None

    @pytest.mark.asyncio
    async def test_a_user_id_resolves_the_same_user_as_the_username(self, db):
        """`/users/me/stats` holds an id, not a username."""
        service = build_service(db)

        by_name = await service.get_user_stats("alice")
        by_id = await service.get_user_stats(ALICE)

        assert by_id == by_name
        assert by_id["total_posts"] == 2

    @pytest.mark.asyncio
    async def test_an_object_id_id_resolves(self, db):
        stats = await build_service(db).get_user_stats(
            ObjectId(ALICE)
        )

        assert stats["username"] == "alice"


class TestMixedStorageForms:
    """Older rows keep identifiers as strings, newer ones as ObjectId."""

    @pytest.fixture
    def mixed_db(self, now):
        return FakeDatabase(
            {
                "users": [
                    make_user(ALICE, "alice"),
                    make_user(BOB, "bob"),
                ],
                "follows": [
                    # legacy string row
                    {"follower_id": BOB, "following_id": ALICE},
                    # ObjectId row
                    {
                        "follower_id": ObjectId(CAROL),
                        "following_id": ObjectId(ALICE),
                    },
                ],
                "show_logs": [
                    {
                        "_id": "log-string",
                        "user_id": ALICE,
                        "event_id": "event-a",
                        "status": "went",
                    },
                    {
                        "_id": "log-object-id",
                        "user_id": ObjectId(ALICE),
                        "event_id": ObjectId("ddddddddddddddddddddddd4"),
                        "status": "going",
                    },
                ],
                "events": [
                    {
                        "_id": "event-a",
                        "artist_slug": NOVA,
                        "starts_at": now - timedelta(days=1),
                    },
                    {
                        "_id": ObjectId("ddddddddddddddddddddddd4"),
                        "artist_slug": STATIC,
                        "starts_at": now - timedelta(days=2),
                    },
                ],
                "community_posts": [
                    {"_id": "p1", "user_id": ALICE},
                    {
                        "_id": "p2",
                        "user_id": ObjectId(ALICE),
                    },
                ],
            }
        )

    @pytest.mark.asyncio
    async def test_both_follow_rows_are_counted(self, mixed_db):
        stats = await build_service(mixed_db).get_user_stats("alice")

        assert stats["followers_count"] == 2

    @pytest.mark.asyncio
    async def test_both_show_log_rows_are_counted(self, mixed_db):
        stats = await build_service(mixed_db).get_user_stats("alice")

        assert stats["shows_attended"] == 1
        assert stats["shows_going"] == 1

    @pytest.mark.asyncio
    async def test_both_event_rows_are_resolved(self, mixed_db):
        stats = await build_service(mixed_db).get_user_stats("alice")

        assert stats["artists_seen"] == 2

    @pytest.mark.asyncio
    async def test_both_post_rows_are_counted(self, mixed_db):
        stats = await build_service(mixed_db).get_user_stats("alice")

        assert stats["total_posts"] == 2


class TestNoPerRowQueries:
    @pytest.mark.asyncio
    async def test_event_lookups_do_not_scale_with_show_logs(self, db, monkeypatch):
        """The events behind many logs are resolved in a single query."""
        service = build_service(db)

        calls = []
        original_find = db.events.find

        def counting_find(*args, **kwargs):
            calls.append(args[0] if args else kwargs.get("filter"))
            return original_find(*args, **kwargs)

        monkeypatch.setattr(db.events, "find", counting_find)

        stats = await service.get_user_stats("alice")

        assert stats["shows_attended"] == 1
        assert len(calls) == 1, (
            "expected exactly one events query, got "
            f"{len(calls)}"
        )


class TestProfileCountsMatchConnections:
    @pytest.mark.asyncio
    async def test_profile_counts_agree_with_the_connections_list(self, db):
        """The number on the header and the list behind it cannot disagree."""
        service = UserProfileService(
            user_repository=UserRepository(db),
            follow_repository=FollowRepository(db),
        )

        profile = await service.get_profile("alice")
        followers = await service.get_connections(
            "alice",
            direction="followers",
        )

        assert profile["followers_count"] == len(followers)

    @pytest.mark.asyncio
    async def test_a_stale_counter_is_not_reported(self, db):
        """A denormalized counter with no row behind it is ignored."""
        document = await db.users.find_one({"username": "alice"})
        document["followers_count"] = 99
        document["following_count"] = 99

        service = UserProfileService(
            user_repository=UserRepository(db),
            follow_repository=FollowRepository(db),
        )

        profile = await service.get_profile("alice")

        assert profile["followers_count"] == 2
        assert profile["following_count"] == 0


class TestFollowRepositoryStorageForms:
    @pytest.fixture
    def repository(self):
        db = FakeDatabase(
            {
                "users": [make_user(ALICE, "alice"), make_user(BOB, "bob")],
                "follows": [
                    {"follower_id": ObjectId(BOB), "following_id": ObjectId(ALICE)},
                    {"follower_id": CAROL, "following_id": ALICE},
                ],
            }
        )

        return FollowRepository(db)

    @pytest.mark.asyncio
    async def test_exists_finds_a_relationship_stored_either_way(self, repository):
        assert await repository.exists(BOB, ALICE) is True
        assert await repository.exists(CAROL, ALICE) is True

    @pytest.mark.asyncio
    async def test_delete_removes_a_relationship_stored_either_way(self, repository):
        assert await repository.delete(BOB, ALICE) is True
        assert await repository.exists(BOB, ALICE) is False

        assert await repository.delete(CAROL, ALICE) is True
        assert await repository.exists(CAROL, ALICE) is False

    @pytest.mark.asyncio
    async def test_counts_include_both_storage_forms(self, repository):
        assert await repository.count_followers(ALICE) == 2
        assert await repository.count_followers(BOB) == 0