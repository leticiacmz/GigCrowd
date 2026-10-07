"""HTTP-level behaviour of the feed and notification endpoints.

These mount only the routers under test on a bare app, with the session
dependency overridden. That keeps the assertions about status codes and
response shape honest without needing a live MongoDB or a signed token.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_active_user
from app.models.activity import ActivityType
from app.routes.feed import router as feed_router
from app.routes.notifications import router as notifications_router
from app.services import activity_service as activity_module
from tests.support.fake_mongo import FakeDatabase, make_user

ALICE = "aaaaaaaaaaaaaaaaaaaaaaa1"
BOB = "bbbbbbbbbbbbbbbbbbbbbbb2"

ARTIST_A = "nova-band"


@pytest.fixture
def app():
    """A minimal app exposing only the feed and notification endpoints."""
    application = FastAPI()
    application.include_router(feed_router)
    application.include_router(notifications_router)
    return application


@pytest.fixture
def db(monkeypatch):
    now = datetime.now(UTC)

    database = FakeDatabase(
        {
            "users": [make_user(ALICE, "alice"), make_user(BOB, "bob")],
            "artists": [{"_id": "artist-a", "slug": ARTIST_A, "name": "Nova"}],
            "follows": [],
            "artist_follows": [],
            "community_posts": [
                {
                    "_id": "post-1",
                    "artist_slug": ARTIST_A,
                    "content": "Hello from Nova's community",
                    "likes_count": 2,
                    "comments_count": 0,
                }
            ],
            "show_logs": [],
            "events": [],
            "activities": [
                {
                    "_id": ObjectId(),
                    "user_id": ALICE,
                    "activity_type": ActivityType.CREATE_COMMUNITY_POST.value,
                    "target_id": "post-1",
                    "target_type": "community_post",
                    "metadata": {"artist_slug": ARTIST_A},
                    "created_at": now,
                }
            ],
            "notifications": [
                {
                    "_id": ObjectId(),
                    "recipient_id": ALICE,
                    "actor_id": BOB,
                    "type": "follow",
                    "related_entity_type": None,
                    "related_entity_id": None,
                    "context": {"artist_slug": ARTIST_A},
                    "read": False,
                    "created_at": now,
                }
            ],
        }
    )

    monkeypatch.setattr(activity_module, "get_database", lambda: database)
    return database


def _sign_in_as(client: TestClient, app: FastAPI, user_id: str):
    """Attach a fake session for `user_id` to this client only."""

    async def override():
        return {"_id": user_id, "id": user_id, "username": "tester"}

    app.dependency_overrides[get_current_active_user] = override
    return client


class TestFeedEndpoint:
    def test_requires_authentication(self, app, db):
        with TestClient(app) as client:
            assert client.get("/feed").status_code == 401

    @pytest.mark.parametrize(
        "category",
        ["all", "community", "reviews", "attendance", "events"],
    )
    def test_every_advertised_category_is_accepted(self, app, db, category):
        with TestClient(app) as client:
            _sign_in_as(client, app, ALICE)

            response = client.get("/feed", params={"category": category})

        assert response.status_code == 200
        assert response.json()["category"] == category

    def test_the_social_category_is_not_offered(self, app, db):
        """Follows are not content, so there is nothing for such a filter to hold.

        Rejected rather than answered as an empty timeline: an empty list would
        look like a reader who has done nothing, when in fact the answer is that
        the question is not one the feed answers.
        """
        with TestClient(app) as client:
            _sign_in_as(client, app, ALICE)

            response = client.get("/feed", params={"category": "social"})

        assert response.status_code == 422
        assert "Unknown feed category" in response.json()["detail"]

    def test_unknown_category_is_rejected(self, app, db):
        with TestClient(app) as client:
            _sign_in_as(client, app, ALICE)

            response = client.get("/feed", params={"category": "everything"})

        assert response.status_code == 422
        assert "Unknown feed category" in response.json()["detail"]

    def test_category_is_normalised(self, app, db):
        with TestClient(app) as client:
            _sign_in_as(client, app, ALICE)

            response = client.get("/feed", params={"category": "  REVIEWS "})

        assert response.status_code == 200
        assert response.json()["category"] == "reviews"

    def test_response_carries_the_timeline_and_its_filter(self, app, db):
        with TestClient(app) as client:
            _sign_in_as(client, app, ALICE)

            response = client.get("/feed", params={"category": "community"})

        payload = response.json()

        assert len(payload["activities"]) == 1
        assert payload["activities"][0]["artist"]["name"] == "Nova"
        assert payload["activities"][0]["user"]["username"] == "alice"
        assert payload["skip"] == 0
        assert payload["limit"] == 20

    def test_one_actor_gets_one_timeline_per_filter(self, app, db):
        """The filters select from the same stream, they do not fetch
        separate datasets."""
        with TestClient(app) as client:
            _sign_in_as(client, app, ALICE)

            everything = client.get("/feed").json()["activities"]
            community = client.get(
                "/feed", params={"category": "community"}
            ).json()["activities"]

        community_ids = {item["id"] for item in community}

        assert community_ids <= {item["id"] for item in everything}


class TestNotificationsEndpoint:
    def test_requires_authentication(self, app, db):
        with TestClient(app) as client:
            assert client.get("/notifications").status_code == 401
            assert client.get("/notifications/unread-count").status_code == 401
            assert client.post("/notifications/read-all").status_code == 401
            assert (
                client.post("/notifications/abc/read").status_code == 401
            )

    def test_lists_only_the_callers_notifications(self, app, db):
        with TestClient(app) as client:
            _sign_in_as(client, app, ALICE)

            response = client.get("/notifications")

        assert response.status_code == 200
        payload = response.json()

        assert payload["unread_count"] == 1
        assert payload["total"] == 1

        notification = payload["notifications"][0]
        assert notification["recipient_id"] == ALICE
        assert notification["actor"]["username"] == "bob"
        assert notification["context"]["artist_name"] == "Nova"
        assert notification["read"] is False

    def test_navigation_target_is_serialised(self, app, db):
        """The actor and target must survive response validation, otherwise
        the notifications page cannot link anywhere."""
        with TestClient(app) as client:
            _sign_in_as(client, app, ALICE)

            response = client.get("/notifications")

        notification = response.json()["notifications"][0]

        assert notification["actor"]["id"] == BOB
        assert notification["target"]["kind"] == "artist"
        assert notification["target"]["slug"] == ARTIST_A

    def test_another_user_sees_an_empty_inbox(self, app, db):
        with TestClient(app) as client:
            _sign_in_as(client, app, BOB)

            response = client.get("/notifications")

        payload = response.json()

        assert payload["notifications"] == []
        assert payload["unread_count"] == 0
        assert payload["total"] == 0

    def test_unread_count_endpoint(self, app, db):
        with TestClient(app) as client:
            _sign_in_as(client, app, ALICE)

            response = client.get("/notifications/unread-count")

        assert response.status_code == 200
        assert response.json() == {"unread_count": 1}

    def test_mark_one_as_read(self, app, db):
        with TestClient(app) as client:
            _sign_in_as(client, app, ALICE)

            listed = client.get("/notifications").json()["notifications"][0]
            response = client.post(
                f"/notifications/{listed['id']}/read"
            )

            assert response.status_code == 200
            assert response.json() == {"id": listed["id"], "read": True}
            assert client.get("/notifications/unread-count").json() == {
                "unread_count": 0
            }

    def test_cannot_mark_someone_elses_notification_read(self, app, db):
        with TestClient(app) as client:
            _sign_in_as(client, app, ALICE)
            listed = client.get("/notifications").json()["notifications"][0]

            app.dependency_overrides.clear()
            _sign_in_as(client, app, BOB)

            response = client.post(f"/notifications/{listed['id']}/read")

        assert response.status_code == 404

        app.dependency_overrides.clear()
        with TestClient(app) as client:
            _sign_in_as(client, app, ALICE)
            assert client.get("/notifications/unread-count").json() == {
                "unread_count": 1
            }

    def test_mark_all_as_read(self, app, db):
        with TestClient(app) as client:
            _sign_in_as(client, app, ALICE)

            response = client.post("/notifications/read-all")

            assert response.status_code == 200
            assert response.json() == {"marked_count": 1}
            assert client.get("/notifications/unread-count").json() == {
                "unread_count": 0
            }

    def test_mark_all_as_read_does_not_touch_another_inbox(self, app, db):
        from app.models.activity import NotificationType
        from app.services.activity_service import ActivityService

        # Give Bob an unread notification of his own.
        asyncio_run(
            ActivityService.create_notification(
                BOB, ALICE, NotificationType.LIKE
            )
        )

        with TestClient(app) as client:
            _sign_in_as(client, app, ALICE)
            assert client.post("/notifications/read-all").json() == {
                "marked_count": 1
            }

            app.dependency_overrides.clear()
            _sign_in_as(client, app, BOB)

            assert client.get("/notifications/unread-count").json() == {
                "unread_count": 1
            }


def asyncio_run(coroutine):
    """Run a coroutine from a synchronous test."""
    return asyncio.run(coroutine)
