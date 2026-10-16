"""The festival page's retry button, at the HTTP boundary.

The service behind it is a stub, so what these tests pin is what the
endpoint *does*: which event it accepts, that it never waits for a page
read, that the trigger is asked to re-run (`force`), and that a worker
already reading the edition is not robbed by a second click. No test here
can reach Songkick - if the route ever built its own real collaborator
instead of asking for one, the stub would simply not be called and the
assertions below would fail loudly.
"""
from __future__ import annotations

import pytest
from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.database.connection import get_database
from app.routes.festivals import router
from tests.support.fake_mongo import FakeDatabase


FESTIVAL_ID = ObjectId("64b000000000000000000001")
CONCERT_ID = ObjectId("64b000000000000000000002")


class StubService:
    """Records the retry without running any enrichment at all."""

    def __init__(self, state: str = "pending"):
        self.state = state
        self.enqueued: list[tuple] = []
        self.scheduled: list[list] = []

    async def enqueue(self, event_id, *, force: bool = False):
        self.enqueued.append((event_id, force))
        return self.state

    def schedule(self, event_ids):
        self.scheduled.append(list(event_ids))
        return None


@pytest.fixture
def database() -> FakeDatabase:
    return FakeDatabase(
        {
            "events": [
                {
                    "_id": FESTIVAL_ID,
                    "title": "Lollapalooza 2027",
                    "event_type": "FestivalInstance",
                    "lineup_state": "failed",
                },
                {
                    "_id": CONCERT_ID,
                    "title": "Some Act @ A Room",
                    "event_type": "Concert",
                },
            ]
        }
    )


def client_for(database: FakeDatabase, service: StubService, monkeypatch):
    monkeypatch.setattr(
        "app.routes.festivals.service_for_database",
        lambda db: service,
    )

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_database] = lambda: database

    return TestClient(app)


def test_a_retry_of_a_failed_edition_asks_for_a_rerun(
    database, monkeypatch
):
    service = StubService()
    client = client_for(database, service, monkeypatch)

    response = client.post(f"/festivals/lineup/{FESTIVAL_ID}/retry")

    assert response.status_code == 200
    body = response.json()
    assert body["event_id"] == str(FESTIVAL_ID)
    assert body["lineup_state"] == "pending"

    assert service.enqueued == [(FESTIVAL_ID, True)]
    assert service.scheduled == [[str(FESTIVAL_ID)]]


def test_a_retry_that_needs_nothing_schedules_nothing(
    database, monkeypatch
):
    """A fresh worker mid-read keeps its claim: enqueued, not scheduled."""

    service = StubService(state="active")
    client = client_for(database, service, monkeypatch)

    response = client.post(f"/festivals/lineup/{FESTIVAL_ID}/retry")

    assert response.status_code == 200
    assert response.json()["lineup_state"] == "active"
    assert service.scheduled == []


def test_a_concert_has_no_lineup_to_enrich(database, monkeypatch):
    service = StubService()
    client = client_for(database, service, monkeypatch)

    response = client.post(f"/festivals/lineup/{CONCERT_ID}/retry")

    assert response.status_code == 400
    assert service.enqueued == []


def test_an_unknown_edition_is_not_found(database, monkeypatch):
    service = StubService()
    client = client_for(database, service, monkeypatch)

    response = client.post(
        "/festivals/lineup/64b000000000000000000099/retry"
    )

    assert response.status_code == 404
    assert service.enqueued == []


def test_an_id_that_is_not_an_id_is_not_found(database, monkeypatch):
    service = StubService()
    client = client_for(database, service, monkeypatch)

    response = client.post("/festivals/lineup/not-an-id/retry")

    assert response.status_code == 404
    assert service.enqueued == []


def test_a_disabled_feature_refuses_without_starting_anything(
    database, monkeypatch
):
    service = StubService()
    monkeypatch.setattr(
        settings, "LINEUP_ENRICHMENT_ENABLED", False
    )
    client = client_for(database, service, monkeypatch)

    response = client.post(f"/festivals/lineup/{FESTIVAL_ID}/retry")

    assert response.status_code == 409
    assert service.enqueued == []
    assert service.scheduled == []
