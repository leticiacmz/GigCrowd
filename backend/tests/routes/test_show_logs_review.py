"""HTTP-level behaviour of the doors that write a review.

The router is mounted on a bare app with the session dependency
overridden and both databases pointed at the in-memory one, so status
codes and the stored shape are asserted honestly without a live MongoDB
or a signed token. The scenarios mirror the service-level file: an
opinion is a rating or some words at every door, and what the door
accepts is what the feed is told happened.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_active_user
from app.models.activity import ActivityType
from app.routes.show_logs import router as show_logs_router
from app.services import activity_service as activity_module
from tests.support.fake_mongo import FakeDatabase

ALICE = "aaaaaaaaaaaaaaaaaaaaaaa1"

EVENT_ID = "6a0000000000000000000001"

PHOTO = "https://example.test/p.jpg"

NEEDS_AN_OPINION = "rating or some words"


@pytest.fixture
def app():
    """A minimal app exposing only the show-log endpoints."""

    application = FastAPI()
    application.include_router(show_logs_router)

    return application


@pytest.fixture
def db(monkeypatch):

    now = datetime.now(UTC)
    past = now - timedelta(days=30)

    database = FakeDatabase(
        {
            "events": [
                {
                    "_id": ObjectId(EVENT_ID),
                    "title": "Some Concert",
                    "artist_slug": "some-artist",
                    "artist_slugs": [],
                    "venue_slug": "some-venue",
                    "event_type": "Concert",
                    "starts_at": past,
                    "ends_at": past,
                    "going_count": 0,
                    "maybe_count": 0,
                    "went_count": 1,
                }
            ],
            "show_logs": [
                {
                    "_id": f"log-{ALICE}-{EVENT_ID}",
                    "user_id": ALICE,
                    "event_id": EVENT_ID,
                    "status": "went",
                    "date": past,
                    "created_at": past,
                    "updated_at": past,
                }
            ],
            "activities": [],
            "notifications": [],
            "follows": [],
            "users": [],
        }
    )

    monkeypatch.setattr(
        "app.routes.show_logs.get_database",
        lambda: database,
    )
    monkeypatch.setattr(
        activity_module,
        "get_database",
        lambda: database,
    )

    return database


def _sign_in_as(client: TestClient, app: FastAPI):
    """Attach a fake session for `ALICE` to this client only."""

    async def override():
        return {
            "_id": ALICE,
            "id": ALICE,
            "username": "tester",
        }

    app.dependency_overrides[get_current_active_user] = override
    return client


def _refusal_detail(response) -> str:
    """The refusal text, whether validation reported it as list or string."""

    return str(response.json()["detail"])


class TestTheReviewEndpointHoldsTheRule:
    """`PUT /show-logs/{event_id}/review` - where the dialog saves."""

    def test_a_rating_alone_is_accepted(self, app, db):
        with TestClient(app) as client:
            _sign_in_as(client, app)

            response = client.put(
                f"/show-logs/{EVENT_ID}/review",
                json={"rating": 4},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["rating"] == 4
        assert body["review"] is None

    def test_a_text_alone_is_accepted_and_reports_no_rating(
        self,
        app,
        db,
    ):
        with TestClient(app) as client:
            _sign_in_as(client, app)

            response = client.put(
                f"/show-logs/{EVENT_ID}/review",
                json={"review": "Worth every minute"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["review"] == "Worth every minute"
        # Absence is exposed as absence, never as a fabricated zero.
        assert body["rating"] is None

    def test_a_photo_alone_is_refused(self, app, db):
        with TestClient(app) as client:
            _sign_in_as(client, app)

            response = client.put(
                f"/show-logs/{EVENT_ID}/review",
                json={"photo_url": PHOTO},
            )

        assert response.status_code == 422
        assert NEEDS_AN_OPINION in _refusal_detail(response)

    def test_an_empty_submission_is_refused(self, app, db):
        with TestClient(app) as client:
            _sign_in_as(client, app)

            response = client.put(
                f"/show-logs/{EVENT_ID}/review",
                json={},
            )

        assert response.status_code == 422
        assert NEEDS_AN_OPINION in _refusal_detail(response)

    def test_a_text_that_says_nothing_is_refused(self, app, db):
        with TestClient(app) as client:
            _sign_in_as(client, app)

            response = client.put(
                f"/show-logs/{EVENT_ID}/review",
                json={"review": "   "},
            )

        assert response.status_code == 422
        assert NEEDS_AN_OPINION in _refusal_detail(response)

    def test_a_rating_outside_the_stars_is_refused(self, app, db):
        with TestClient(app) as client:
            _sign_in_as(client, app)

            response = client.put(
                f"/show-logs/{EVENT_ID}/review",
                json={"rating": 0},
            )

        assert response.status_code == 422

    def test_a_rating_only_review_reaches_the_feed_as_a_review(
        self,
        app,
        db,
    ):
        with TestClient(app) as client:
            _sign_in_as(client, app)

            client.put(
                f"/show-logs/{EVENT_ID}/review",
                json={"rating": 4},
            )

        recorded = _activities(db)

        assert [
            item["activity_type"]
            for item in recorded
        ] == [ActivityType.CREATE_REVIEW.value]

        assert recorded[0]["metadata"]["rating"] == 4


class TestCreatingALogHoldsTheSameRule:
    """`POST /show-logs` - attendance with an opinion in one call."""

    def _create(self, app, db, **fields):
        with TestClient(app) as client:
            _sign_in_as(client, app)

            return client.post(
                "/show-logs",
                json={
                    "event_id": EVENT_ID,
                    "status": "went",
                    **fields,
                },
            )

    def test_a_rating_alone_is_accepted(self, app, db):
        response = self._create(app, db, rating=4)

        assert response.status_code == 200
        assert response.json()["rating"] == 4

    def test_a_text_alone_keeps_the_rating_absent(self, app, db):
        response = self._create(app, db, review="Worth every minute")

        assert response.status_code == 200
        assert response.json()["rating"] is None

    def test_a_photo_alone_is_refused(self, app, db):
        response = self._create(app, db, photo_url=PHOTO)

        assert response.status_code == 422
        assert NEEDS_AN_OPINION in _refusal_detail(response)

    def test_nothing_to_say_is_plain_attendance(self, app, db):
        response = self._create(app, db)

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "went"
        assert body["rating"] is None
        assert body["review"] is None

    def test_plain_attendance_reaches_the_feed_as_attendance(
        self,
        app,
        db,
    ):
        self._create(app, db)

        recorded = _activities(db)

        assert [
            item["activity_type"]
            for item in recorded
        ] == [ActivityType.ATTEND_EVENT.value]


def _activities(db) -> list[dict]:
    """Every activity written during a test, read back synchronously.

    The tests drive HTTP synchronously through `TestClient`, so the
    in-memory database is read on a fresh loop after the fact rather than
    turning the whole file async.
    """

    return asyncio.run(
        db.activities.find({}).to_list(length=100)
    )
