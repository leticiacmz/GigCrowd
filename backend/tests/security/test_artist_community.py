"""Artist-scoped community permissions.

The product rule the community is built around:

* reading is public, for everyone, signed in or not
* writing (post, like, comment, reply) needs a session *and* a follow of that
  specific artist
* a signed-in non-follower is refused with 403, never redirected to login:
  they already have a session, the missing piece is the follow
* an artist's community is isolated: nothing from one artist is reachable
  through another artist's URL
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_active_user, get_optional_user
from app.models.activity import ActivityType, NotificationType
from app.routes import artist_community as community_module
from app.routes.artist_community import router as community_router
from app.services import activity_service as activity_module
from tests.support.fake_mongo import FakeDatabase, make_user

ALICE = "aaaaaaaaaaaaaaaaaaaaaaa1"
BOB = "bbbbbbbbbbbbbbbbbbbbbbb2"

ARTIST_A = "nova-band"
ARTIST_B = "static-hearts"


def run(coroutine):
    """Run a coroutine from a synchronous test."""
    return asyncio.run(coroutine)


@pytest.fixture
def app():
    application = FastAPI()
    application.include_router(community_router)
    return application


@pytest.fixture
def db(monkeypatch):
    """Two artists, Alice following one of them, and one seeded post."""
    now = datetime.now(UTC)

    post_a = {
        "_id": ObjectId(),
        "artist_slug": ARTIST_A,
        "user_id": ObjectId(ALICE),
        "content": "Nova's community welcome post",
        "image_url": None,
        "likes_count": 0,
        "comments_count": 0,
        "created_at": now,
        "updated_at": None,
    }

    database = FakeDatabase(
        {
            "users": [
                make_user(ALICE, "alice"),
                make_user(BOB, "bob"),
            ],
            "artists": [
                {
                    "_id": "artist-a",
                    "slug": ARTIST_A,
                    "name": "Nova",
                    "normalized_name": "nova",
                    "followers_count": 0,
                },
                {
                    "_id": "artist-b",
                    "slug": ARTIST_B,
                    "name": "Static Hearts",
                    "normalized_name": "static hearts",
                    "followers_count": 0,
                },
            ],
            "artist_follows": [
                {
                    "_id": ObjectId(),
                    "user_id": ObjectId(ALICE),
                    "artist_slug": ARTIST_A,
                    "created_at": now,
                }
            ],
            "community_posts": [post_a],
            "comments": [],
            "post_likes": [],
            "activities": [],
            "notifications": [],
        }
    )

    monkeypatch.setattr(activity_module, "get_database", lambda: database)
    # The router imports `get_database` directly, so patch it there too.
    monkeypatch.setattr(
        community_module, "get_database", lambda: database
    )
    return database


def sign_in(app, user_id, username):
    """Make `user_id` the current user for protected endpoints."""
    user = {"_id": user_id, "id": user_id, "username": username}

    async def active():
        return user

    async def optional():
        return user

    app.dependency_overrides[get_current_active_user] = active
    app.dependency_overrides[get_optional_user] = optional


def sign_out(app):
    """Make every request anonymous."""
    app.dependency_overrides.clear()


def post_id(db):
    return str(db.community_posts.documents[0]["_id"])


class TestPublicReading:
    def test_signed_out_visitors_can_read_posts(self, app, db):
        sign_out(app)

        with TestClient(app) as client:
            response = client.get(f"/artists/{ARTIST_A}/community/posts")

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["artist_slug"] == ARTIST_A
        assert body[0]["username"] == "alice"

    def test_signed_out_visitors_can_read_comments(self, app, db):
        sign_out(app)

        with TestClient(app) as client:
            response = client.get(
                f"/artists/{ARTIST_A}/community/posts/{post_id(db)}/comments"
            )

        assert response.status_code == 200
        assert response.json() == []

    def test_non_follower_can_read_posts(self, app, db):
        """Bob does not follow Nova, and can still read the community."""
        sign_in(app, BOB, "bob")

        with TestClient(app) as client:
            response = client.get(f"/artists/{ARTIST_A}/community/posts")

        assert response.status_code == 200
        assert len(response.json()) == 1

    def test_posts_carry_the_author_username(self, app, db):
        """`@name` is resolvable from the read payload alone, so the UI never
        needs a per-author request."""
        sign_out(app)

        with TestClient(app) as client:
            body = client.get(
                f"/artists/{ARTIST_A}/community/posts"
            ).json()

        assert body[0]["username"] == "alice"


class TestNonFollowerIsRefusedNotRedirected:
    """A signed-in non-follower gets 403, not a login redirect."""

    def test_posting_without_following_is_403(self, app, db):
        sign_in(app, BOB, "bob")

        with TestClient(app) as client:
            response = client.post(
                f"/artists/{ARTIST_A}/community/posts",
                json={"content": "Let me in"},
            )

        assert response.status_code == 403
        assert "must follow this artist" in response.json()["detail"]

    def test_commenting_without_following_is_403(self, app, db):
        sign_in(app, BOB, "bob")

        with TestClient(app) as client:
            response = client.post(
                f"/artists/{ARTIST_A}/community/comments",
                json={"post_id": post_id(db), "content": "Nice post"},
            )

        assert response.status_code == 403
        assert "must follow this artist" in response.json()["detail"]

    def test_replying_without_following_is_403(self, app, db):
        sign_in(app, ALICE, "alice")
        with TestClient(app) as client:
            created = client.post(
                f"/artists/{ARTIST_A}/community/comments",
                json={"post_id": post_id(db), "content": "First"},
            ).json()

        sign_in(app, BOB, "bob")
        with TestClient(app) as client:
            response = client.post(
                f"/artists/{ARTIST_A}/community/comments",
                json={
                    "post_id": post_id(db),
                    "content": "Reply from a non-follower",
                    "parent_comment_id": created["id"],
                },
            )

        assert response.status_code == 403

    def test_liking_without_following_is_403(self, app, db):
        sign_in(app, BOB, "bob")

        with TestClient(app) as client:
            response = client.post(
                f"/artists/{ARTIST_A}/community/posts/{post_id(db)}/like"
            )

        assert response.status_code == 403

    def test_nothing_is_written_when_refused(self, app, db):
        sign_in(app, BOB, "bob")

        with TestClient(app) as client:
            client.post(
                f"/artists/{ARTIST_A}/community/posts",
                json={"content": "Let me in"},
            )
            client.post(
                f"/artists/{ARTIST_A}/community/comments",
                json={"post_id": post_id(db), "content": "Nice post"},
            )

        assert len(db.community_posts.documents) == 1
        assert db.comments.documents == []


class TestSignedOutIsRefused:
    def test_posting_without_a_session_is_401(self, app, db):
        sign_out(app)

        with TestClient(app) as client:
            response = client.post(
                f"/artists/{ARTIST_A}/community/posts",
                json={"content": "Anonymous"},
            )

        assert response.status_code == 401

    def test_commenting_without_a_session_is_401(self, app, db):
        sign_out(app)

        with TestClient(app) as client:
            response = client.post(
                f"/artists/{ARTIST_A}/community/comments",
                json={"post_id": post_id(db), "content": "Anonymous"},
            )

        assert response.status_code == 401


class TestFollowGrantsParticipation:
    def test_follower_can_post(self, app, db):
        sign_in(app, ALICE, "alice")

        with TestClient(app) as client:
            response = client.post(
                f"/artists/{ARTIST_A}/community/posts",
                json={"content": "Following means I can post"},
            )

        assert response.status_code == 200
        assert response.json()["artist_slug"] == ARTIST_A
        assert len(db.community_posts.documents) == 2

    def test_follower_can_comment(self, app, db):
        sign_in(app, ALICE, "alice")

        with TestClient(app) as client:
            response = client.post(
                f"/artists/{ARTIST_A}/community/comments",
                json={"post_id": post_id(db), "content": "Great post"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["content"] == "Great post"
        assert body["username"] == "alice"
        assert len(db.comments.documents) == 1

    def test_following_a_second_artist_grants_only_that_community(self, app, db):
        """The grant is per artist, never global."""
        sign_in(app, ALICE, "alice")

        with TestClient(app) as client:
            assert (
                client.post(
                    f"/artists/{ARTIST_B}/community/posts",
                    json={"content": "Nova fan, new here"},
                ).status_code
                == 403
            )

            from app.repositories.artist_follow_repository import (
                ArtistFollowRepository,
            )

            run(
                ArtistFollowRepository(db).create_follow(ALICE, ARTIST_B)
            )

            assert (
                client.post(
                    f"/artists/{ARTIST_B}/community/posts",
                    json={"content": "Now allowed"},
                ).status_code
                == 200
            )

    def test_comment_is_sanitised(self, app, db):
        sign_in(app, ALICE, "alice")

        with TestClient(app) as client:
            response = client.post(
                f"/artists/{ARTIST_A}/community/comments",
                json={
                    "post_id": post_id(db),
                    "content": "<script>alert(1)</script>safe",
                },
            )

        assert response.status_code == 200
        assert "<script>" not in response.json()["content"]


class TestArtistIsolation:
    def test_post_from_another_artist_is_not_reachable(self, app, db):
        """Nova's post is invisible through Static Hearts' URL."""
        sign_out(app)

        with TestClient(app) as client:
            response = client.get(
                f"/artists/{ARTIST_B}/community/posts/{post_id(db)}/comments"
            )

        assert response.status_code == 404
        assert "this artist's community" in response.json()["detail"]

    def test_commenting_across_artists_is_404(self, app, db):
        sign_in(app, ALICE, "alice")

        with TestClient(app) as client:
            response = client.post(
                f"/artists/{ARTIST_B}/community/comments",
                json={"post_id": post_id(db), "content": "Wrong artist"},
            )

        assert response.status_code == 404
        assert db.comments.documents == []

    def test_liking_across_artists_is_404(self, app, db):
        sign_in(app, ALICE, "alice")

        with TestClient(app) as client:
            response = client.post(
                f"/artists/{ARTIST_B}/community/posts/{post_id(db)}/like"
            )

        assert response.status_code == 404
        assert db.post_likes.documents == []

    def test_each_artist_lists_only_its_own_posts(self, app, db):
        sign_in(app, ALICE, "alice")

        with TestClient(app) as client:
            nova = client.get(
                f"/artists/{ARTIST_A}/community/posts"
            ).json()
            static_hearts = client.get(
                f"/artists/{ARTIST_B}/community/posts"
            ).json()

        assert [post["artist_slug"] for post in nova] == [ARTIST_A]
        assert static_hearts == []

    def test_posting_to_an_unknown_artist_is_404(self, app, db):
        sign_in(app, ALICE, "alice")

        with TestClient(app) as client:
            response = client.post(
                "/artists/does-not-exist/community/posts",
                json={"content": "Hello?"},
            )

        assert response.status_code == 404


class TestCommunitySideEffects:
    def test_new_post_is_recorded_in_the_unified_feed(self, app, db):
        sign_in(app, ALICE, "alice")

        with TestClient(app) as client:
            client.post(
                f"/artists/{ARTIST_A}/community/posts",
                json={"content": "Watch the new video"},
            )

        activities = db.activities.documents

        assert len(activities) == 1
        assert activities[0]["activity_type"] == (
            ActivityType.CREATE_COMMUNITY_POST.value
        )
        assert activities[0]["metadata"]["artist_slug"] == ARTIST_A

    def test_like_notifies_the_post_author(self, app, db):
        sign_in(app, BOB, "bob")
        from app.repositories.artist_follow_repository import (
            ArtistFollowRepository,
        )

        run(ArtistFollowRepository(db).create_follow(BOB, ARTIST_A))

        with TestClient(app) as client:
            response = client.post(
                f"/artists/{ARTIST_A}/community/posts/{post_id(db)}/like"
            )

        assert response.status_code == 200
        assert len(db.notifications.documents) == 1

        notification = db.notifications.documents[0]
        assert notification["recipient_id"] == ALICE
        assert notification["actor_id"] == BOB
        assert notification["type"] == NotificationType.LIKE.value

    def test_top_level_comment_notifies_the_post_author(self, app, db):
        sign_in(app, BOB, "bob")
        from app.repositories.artist_follow_repository import (
            ArtistFollowRepository,
        )

        run(ArtistFollowRepository(db).create_follow(BOB, ARTIST_A))

        with TestClient(app) as client:
            client.post(
                f"/artists/{ARTIST_A}/community/comments",
                json={"post_id": post_id(db), "content": "Agreed"},
            )

        notification = db.notifications.documents[0]

        assert notification["recipient_id"] == ALICE
        assert notification["type"] == NotificationType.COMMENT.value

    def test_replying_to_your_own_comment_notifies_nobody(self, app, db):
        sign_in(app, ALICE, "alice")
        with TestClient(app) as client:
            first = client.post(
                f"/artists/{ARTIST_A}/community/comments",
                json={"post_id": post_id(db), "content": "My comment"},
            ).json()

            client.post(
                f"/artists/{ARTIST_A}/community/comments",
                json={
                    "post_id": post_id(db),
                    "content": "Adding to my own point",
                    "parent_comment_id": first["id"],
                },
            )

        # Alice commented on her own post and then replied to herself.
        assert db.notifications.documents == []

    def test_reply_to_another_users_comment_notifies_them(self, app, db):
        sign_in(app, ALICE, "alice")
        with TestClient(app) as client:
            first = client.post(
                f"/artists/{ARTIST_A}/community/comments",
                json={"post_id": post_id(db), "content": "Alice here"},
            ).json()

        from app.repositories.artist_follow_repository import (
            ArtistFollowRepository,
        )

        run(ArtistFollowRepository(db).create_follow(BOB, ARTIST_A))
        sign_in(app, BOB, "bob")

        with TestClient(app) as client:
            client.post(
                f"/artists/{ARTIST_A}/community/comments",
                json={
                    "post_id": post_id(db),
                    "content": "Answering Alice",
                    "parent_comment_id": first["id"],
                },
            )

        notification = db.notifications.documents[0]

        assert notification["recipient_id"] == ALICE
        assert notification["actor_id"] == BOB
        assert notification["type"] == NotificationType.REPLY.value
        assert notification["context"]["post_id"] == post_id(db)

    def test_replies_are_returned_nested_under_their_comment(self, app, db):
        sign_in(app, ALICE, "alice")

        with TestClient(app) as client:
            first = client.post(
                f"/artists/{ARTIST_A}/community/comments",
                json={"post_id": post_id(db), "content": "Top level"},
            ).json()

            client.post(
                f"/artists/{ARTIST_A}/community/comments",
                json={
                    "post_id": post_id(db),
                    "content": "A reply",
                    "parent_comment_id": first["id"],
                },
            )

            thread = client.get(
                f"/artists/{ARTIST_A}/community/posts/{post_id(db)}/comments"
            ).json()

        assert len(thread) == 1
        assert thread[0]["content"] == "Top level"
        assert thread[0]["replies_count"] == 1
        assert [reply["content"] for reply in thread[0]["replies"]] == [
            "A reply"
        ]
