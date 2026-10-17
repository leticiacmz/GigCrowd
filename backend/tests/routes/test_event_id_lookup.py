"""The event detail address at the HTTP level.

One rule is worth pinning from outside the service: an id that cannot be a
stored event - anything that is not a 24-character ObjectId - is answered
with the "not found" the page already has, not with a server error. A
truncated link or a typed address used to reach `ObjectId()` and raise,
turning the page into a 500 that the browser cannot even read past CORS.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes.events import router as events_router
from tests.support.fake_mongo import FakeDatabase

SONGKICK_ID = "5550901"


@pytest.fixture
def event_id() -> str:
    return str(ObjectId())


@pytest.fixture
def db(event_id):
    starts_at = datetime.now(UTC) + timedelta(days=30)

    return FakeDatabase(
        {
            "events": [
                {
                    "_id": ObjectId(event_id),
                    "title": "Marina Sena at the Warehouse",
                    "event_type": "Concert",
                    "venue_slug": "a-venue",
                    "artist_slug": "marina-sena",
                    "artist_slugs": ["marina-sena"],
                    "starts_at": starts_at,
                    "ends_at": starts_at,
                    "date_status": "source",
                    "lineup": [],
                    "location": None,
                    "external_ids": {"songkick": SONGKICK_ID},
                    "source": {
                        "provider": "songkick",
                        "external_id": SONGKICK_ID,
                        "url": (
                            "https://www.songkick.com/concerts/"
                            f"{SONGKICK_ID}-a-real-show"
                        ),
                        "event_id": SONGKICK_ID,
                        "provenance": "songkick",
                    },
                    "festival": None,
                },
            ],
            "venues": [
                {
                    "slug": "a-venue",
                    "name": "The Warehouse",
                    "city": "Seattle",
                    "country": "US",
                },
            ],
        }
    )


@pytest.fixture
def app(db, monkeypatch):
    # The service constructor reads the database directly, as it does in the
    # running app, so the fake is installed where that call resolves.
    monkeypatch.setattr("app.routes.events.get_database", lambda: db)

    application = FastAPI()
    application.include_router(events_router)
    return application


def test_a_stored_event_is_returned_by_its_id(app, event_id):
    with TestClient(app) as client:
        response = client.get(f"/events/{event_id}")

    assert response.status_code == 200
    assert response.json()["title"] == "Marina Sena at the Warehouse"


def test_a_malformed_id_is_not_found_rather_than_a_server_error(app):
    # The exact shape a truncated link produces: one character short of a
    # real ObjectId. It must stay a 404 - the page's own empty state.
    with TestClient(app) as client:
        response = client.get("/events/6ad29df51aa1d31471d1b4f")

    assert response.status_code == 404
