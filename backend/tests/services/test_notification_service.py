"""Notification behaviour.

Notifications are a real, recipient-scoped backend feature, separate from the
feed. These tests cover the four types the product defines, the unread/read
lifecycle, mark-all-as-read, and the isolation that stops one user from
reading or mutating another user's notifications.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from bson import ObjectId

from app.models.activity import NotificationType
from app.services import activity_service as activity_module
from app.services.activity_service import ActivityService
from tests.support.fake_mongo import FakeDatabase, make_user

ALICE = "aaaaaaaaaaaaaaaaaaaaaaa1"
BOB = "bbbbbbbbbbbbbbbbbbbbbbb2"

ARTIST_A = "nova-band"


@pytest.fixture
def db(monkeypatch):
    """A database where Bob follows Alice and both know the artist."""
    now = datetime.now(UTC)

    database = FakeDatabase(
        {
            "users": [
                make_user(ALICE, "alice"),
                make_user(BOB, "bob", avatar_url="https://cdn.test/bob.png"),
            ],
            "artists": [{"_id": "artist-a", "slug": ARTIST_A, "name": "Nova"}],
            "community_posts": [
                {
                    "_id": "post-1",
                    "artist_slug": ARTIST_A,
                    "user_id": ALICE,
                    "content": "Nova released a banger",
                }
            ],
            "notifications": [],
        }
    )

    monkeypatch.setattr(activity_module, "get_database", lambda: database)
    return database


async def _create(recipient_id, actor_id, notification_type, **kwargs):
    return await ActivityService.create_notification(
        recipient_id,
        actor_id,
        notification_type,
        **kwargs,
    )


class TestNotificationTypes:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "notification_type",
        [
            NotificationType.FOLLOW,
            NotificationType.LIKE,
            NotificationType.COMMENT,
            NotificationType.REPLY,
        ],
    )
    async def test_each_type_is_persisted(self, db, notification_type):
        created = await _create(ALICE, BOB, notification_type)

        assert created is not None
        assert created["type"] == notification_type.value
        assert created["recipient_id"] == ALICE
        assert created["actor_id"] == BOB
        assert created["read"] is False
        assert isinstance(created["created_at"], datetime)

    @pytest.mark.asyncio
    async def test_exactly_four_types_exist(self):
        """The product defines Follow, Like, Comment and Reply, and nothing else."""
        assert {member.value for member in NotificationType} == {
            "follow",
            "like",
            "comment",
            "reply",
        }

    @pytest.mark.asyncio
    async def test_context_is_preserved(self, db):
        created = await _create(
            ALICE,
            BOB,
            NotificationType.COMMENT,
            related_entity_type="comment",
            related_entity_id="comment-9",
            context={"artist_slug": ARTIST_A, "post_id": "post-1"},
        )

        assert created["related_entity_type"] == "comment"
        assert created["related_entity_id"] == "comment-9"
        assert created["context"]["artist_slug"] == ARTIST_A
        assert created["context"]["post_id"] == "post-1"

    @pytest.mark.asyncio
    async def test_self_notification_is_skipped(self, db):
        """Liking your own post is not news to you."""
        created = await _create(ALICE, ALICE, NotificationType.LIKE)

        assert created is None
        assert await db.notifications.count_documents({}) == 0


class TestListing:
    @pytest.mark.asyncio
    async def test_recipient_only_sees_their_own(self, db):
        await _create(ALICE, BOB, NotificationType.FOLLOW)
        await _create(BOB, ALICE, NotificationType.FOLLOW)

        alice_inbox = await ActivityService.get_notifications(ALICE)
        bob_inbox = await ActivityService.get_notifications(BOB)

        assert len(alice_inbox["notifications"]) == 1
        assert len(bob_inbox["notifications"]) == 1
        assert alice_inbox["notifications"][0].actor_id == BOB
        assert bob_inbox["notifications"][0].actor_id == ALICE

    @pytest.mark.asyncio
    async def test_unauthenticated_caller_is_not_consulted(self, db):
        """Listing is driven purely by the id the route passes in."""
        await _create(ALICE, BOB, NotificationType.FOLLOW)

        result = await ActivityService.get_notifications("nobody")

        assert result["notifications"] == []
        assert result["unread_count"] == 0
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_newest_first(self, db):
        await _create(ALICE, BOB, NotificationType.FOLLOW)
        await _create(ALICE, BOB, NotificationType.LIKE)
        await _create(ALICE, BOB, NotificationType.COMMENT)

        # Pin distinct timestamps so the expected order is unambiguous: the
        # most recently created row is also the newest one.
        base = datetime.now(UTC)
        for offset, document in enumerate(db.notifications.documents):
            document["created_at"] = base - timedelta(
                hours=len(db.notifications.documents) - 1 - offset
            )

        result = await ActivityService.get_notifications(ALICE)
        types = [item.type for item in result["notifications"]]

        assert types == [
            NotificationType.COMMENT,
            NotificationType.LIKE,
            NotificationType.FOLLOW,
        ]

    @pytest.mark.asyncio
    async def test_actor_is_enriched_for_navigation(self, db):
        await _create(ALICE, BOB, NotificationType.FOLLOW)

        result = await ActivityService.get_notifications(ALICE)
        actor = result["notifications"][0].actor

        assert actor.id == BOB
        assert actor.username == "bob"
        assert actor.avatar_url == "https://cdn.test/bob.png"

    @pytest.mark.asyncio
    async def test_target_points_at_the_real_community_post(self, db):
        await _create(
            ALICE,
            BOB,
            NotificationType.LIKE,
            context={"artist_slug": ARTIST_A, "post_id": "post-1"},
        )

        result = await ActivityService.get_notifications(ALICE)
        target = result["notifications"][0].target

        assert target["kind"] == "community_post"
        assert target["id"] == "post-1"
        assert target["artist_slug"] == ARTIST_A
        assert target["excerpt"] == "Nova released a banger"

    @pytest.mark.asyncio
    async def test_artist_context_is_resolved_to_a_name(self, db):
        await _create(
            ALICE,
            BOB,
            NotificationType.FOLLOW,
            context={"artist_slug": ARTIST_A},
        )

        result = await ActivityService.get_notifications(ALICE)
        notification = result["notifications"][0]

        assert notification.context["artist_name"] == "Nova"
        assert notification.target["kind"] == "artist"
        assert notification.target["name"] == "Nova"

    @pytest.mark.asyncio
    async def test_counts_are_returned_with_the_page(self, db):
        await _create(ALICE, BOB, NotificationType.FOLLOW)
        await _create(ALICE, BOB, NotificationType.LIKE)
        await _create(ALICE, BOB, NotificationType.REPLY)

        result = await ActivityService.get_notifications(ALICE)

        assert result["total"] == 3
        assert result["unread_count"] == 3


class TestReadLifecycle:
    @pytest.mark.asyncio
    async def test_unread_count_counts_only_unread(self, db):
        first = await _create(ALICE, BOB, NotificationType.FOLLOW)
        await _create(ALICE, BOB, NotificationType.LIKE)

        assert await ActivityService.get_unread_count(ALICE) == 2

        await ActivityService.mark_as_read(first["_id"], ALICE)

        assert await ActivityService.get_unread_count(ALICE) == 1

    @pytest.mark.asyncio
    async def test_mark_as_read_sets_the_flag(self, db):
        created = await _create(ALICE, BOB, NotificationType.FOLLOW)

        assert created["read"] is False

        assert await ActivityService.mark_as_read(created["_id"], ALICE) is True

        stored = await db.notifications.find_one({"_id": ObjectId(created["_id"])})
        assert stored is not None
        assert stored["read"] is True

    @pytest.mark.asyncio
    async def test_mark_as_read_rejects_another_users_notification(self, db):
        created = await _create(ALICE, BOB, NotificationType.FOLLOW)

        # Bob is neither the recipient nor allowed to touch Alice's inbox.
        assert await ActivityService.mark_as_read(created["_id"], BOB) is False

        stored = await db.notifications.find_one({"_id": ObjectId(created["_id"])})
        assert stored is not None
        assert stored["read"] is False

    @pytest.mark.asyncio
    async def test_mark_as_read_rejects_an_unknown_id(self, db):
        assert await ActivityService.mark_as_read(str(ObjectId()), ALICE) is False
        assert await ActivityService.mark_as_read("not-an-id", ALICE) is False

    @pytest.mark.asyncio
    async def test_mark_all_as_read_clears_the_whole_inbox(self, db):
        await _create(ALICE, BOB, NotificationType.FOLLOW)
        await _create(ALICE, BOB, NotificationType.LIKE)
        await _create(ALICE, BOB, NotificationType.COMMENT)

        assert await ActivityService.mark_all_as_read(ALICE) == 3
        assert await ActivityService.get_unread_count(ALICE) == 0

    @pytest.mark.asyncio
    async def test_mark_all_as_read_leaves_other_inboxes_alone(self, db):
        await _create(ALICE, BOB, NotificationType.FOLLOW)
        await _create(BOB, ALICE, NotificationType.FOLLOW)

        assert await ActivityService.mark_all_as_read(ALICE) == 1

        assert await ActivityService.get_unread_count(BOB) == 1

    @pytest.mark.asyncio
    async def test_mark_all_as_read_is_idempotent(self, db):
        await _create(ALICE, BOB, NotificationType.FOLLOW)

        assert await ActivityService.mark_all_as_read(ALICE) == 1
        assert await ActivityService.mark_all_as_read(ALICE) == 0


class TestNotify:
    @pytest.mark.asyncio
    async def test_notify_creates_the_record(self, db):
        await ActivityService.notify(
            ALICE,
            BOB,
            NotificationType.REPLY,
            context={"artist_slug": ARTIST_A},
        )

        stored = await db.notifications.find_one({"recipient_id": ALICE})
        assert stored is not None
        assert stored["type"] == "reply"

    @pytest.mark.asyncio
    async def test_notify_never_breaks_the_calling_action(self, db, monkeypatch):
        """A notification failure must not fail the follow / like / comment."""
        monkeypatch.setattr(
            ActivityService,
            "create_notification",
            _raise,
        )

        await ActivityService.notify(ALICE, BOB, NotificationType.LIKE)

    @pytest.mark.asyncio
    async def test_record_never_breaks_the_calling_action(self, db, monkeypatch):
        """Same guarantee for feed bookkeeping."""
        monkeypatch.setattr(
            activity_module.ActivityService,
            "create_activity",
            _raise,
        )

        await ActivityService.record(ALICE, "create_community_post")


async def _raise(*args, **kwargs):
    raise RuntimeError("storage unavailable")
