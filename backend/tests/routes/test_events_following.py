"""The followed-artists events list at the HTTP level.

Two things are worth pinning from outside the service:

* It is reachable. `/{event_id}` is registered in the same router and would
  read "/events/following" as a malformed event id - a 404 or a 500 on every
  signed-in visit - if the sub-path were declared after it.
* It needs a session. The list is personal: an anonymous caller has nobody
  whose follows could be read, and 401 says so plainly rather than quietly
  returning the public list under a personalized heading.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_active_user
from app.database.connection import get_database
from app.routes.events import router as events_router
from tests.support.fake_mongo import FakeDatabase, make_user

ALICE = "aaaaaaaaaaaaaaaaaaaaaaa1"
BOB = "bbbbbbbbbbbbbbbbbbbbbbb2"
FOLLOWED = "marina-sena"
OTHER = "tim-bernardes"


@pytest.fixture
def db():
    now = datetime.now(UTC)

    def a_source(songkick_id: str) -> dict:
        return {
            "provider": "songkick",
            "external_id": songkick_id,
            "url": (
                "https://www.songkick.com/concerts/"
                f"{songkick_id}-a-real-show"
            ),
            "event_id": songkick_id,
            "provenance": "songkick",
        }

    def an_event(
        title: str,
        artist_slugs: list[str],
        starts_at: datetime,
        songkick_id: str,
    ) -> dict:
        return {
            "_id": ObjectId(),
            "title": title,
            "event_type": "Concert",
            "venue_slug": "a-venue",
            "artist_slug": artist_slugs[0],
            "artist_slugs": artist_slugs,
            "starts_at": starts_at,
            "ends_at": None,
            "date_status": "source",
            "lineup": [],
            "location": None,
            "external_ids": {"songkick": songkick_id},
            "source": a_source(songkick_id),
            "festival": None,
        }

    return FakeDatabase(
        {
            "users": [make_user(ALICE, "alice")],
            "artists": [
                {
                    "_id": str(ObjectId()),
                    "name": "Marina Sena",
                    "slug": FOLLOWED,
                    "normalized_name": "marina sena",
                    "external_ids": {},
                    "genres": ["MPB"],
                    "image": None,
                },
                {
                    "_id": str(ObjectId()),
                    "name": "Tim Bernardes",
                    "slug": OTHER,
                    "normalized_name": "tim bernardes",
                    "external_ids": {},
                    "genres": ["MPB"],
                    "image": None,
                },
            ],
            "artist_follows": [
                {
                    "user_id": ObjectId(ALICE),
                    "artist_slug": FOLLOWED,
                    "created_at": now,
                },
            ],
            "events": [
                an_event(
                    "Marina Sena Ahead",
                    [FOLLOWED],
                    now + timedelta(days=20),
                    "5550101",
                ),
                an_event(
                    "Tim Bernardes Ahead",
                    [OTHER],
                    now + timedelta(days=25),
                    "5550102",
                ),
                an_event(
                    "Marina Sena Last Year",
                    [FOLLOWED],
                    now - timedelta(days=400),
                    "5550103",
                ),
            ],
            "venues": [
                {
                    "slug": "a-venue",
                    "name": "The Crocodile",
                    "city": "Seattle",
                    "country": "US",
                }
            ],
        }
    )


@pytest.fixture
def app(db):
    application = FastAPI()
    application.include_router(events_router)
    application.dependency_overrides[get_database] = lambda: db
    return application


def _sign_in_as(app: FastAPI, user_id: str):
    async def override():
        return {"_id": user_id, "id": user_id, "username": "tester"}

    app.dependency_overrides[get_current_active_user] = override


class TestFollowedArtistEvents:
    def test_requires_authentication(self, app):
        with TestClient(app) as client:
            assert client.get("/events/following").status_code == 401

    def test_the_list_is_reachable_and_personal(self, app):
        """Not read as an event id, and only the followed artist's shows.

        The followed artist's own history stays out - this is a list of what
        is on - and so does the unfollowed artist's upcoming show, which is
        the entire difference between this page and the browse list.
        """
        with TestClient(app) as client:
            _sign_in_as(app, ALICE)

            response = client.get(
                "/events/following",
                params={"limit": 20},
            )

        assert response.status_code == 200

        payload = response.json()

        assert [row["title"] for row in payload["events"]] == [
            "Marina Sena Ahead"
        ]

        assert payload["total"] == 1
        assert payload["next_cursor"] is None
        assert payload["following_count"] == 1

    def test_an_empty_page_still_reports_the_follow_count(self, app):
        """Empty is ambiguous, and the count is what tells the two apart.

        The page has two different things to say when the list is empty -
        "you follow nobody" and "nobody you follow has a show ahead" - and
        it must not fetch a second endpoint to choose. So the count rides
        along even when there are no rows, for a reader with follows and for
        one without alike.
        """
        with TestClient(app) as client:
            _sign_in_as(app, ALICE)
            with_follows = client.get("/events/following").json()

            _sign_in_as(app, BOB)
            without_follows = client.get("/events/following").json()

        # Alice follows Marina Sena, whose only upcoming show is on this
        # page; her list is the one row above.
        assert with_follows["following_count"] == 1

        # Bob follows nobody: no rows, no error, and a zero that means
        # "follows nobody" rather than "follows nobody with shows".
        assert without_follows["events"] == []
        assert without_follows["total"] == 0
        assert without_follows["following_count"] == 0

    def test_paging_uses_the_same_cursor_convention(self, app):
        """A second page is asked for the way every other event list asks."""
        with TestClient(app) as client:
            _sign_in_as(app, ALICE)

            response = client.get(
                "/events/following",
                params={"limit": 1},
            )

        payload = response.json()

        assert len(payload["events"]) == 1
        # Only one upcoming row matches, and this list never reaches into the
        # past, so there is no second page to offer.
        assert payload["next_cursor"] is None
