"""The profile update at the HTTP level, for the avatar specifically.

Three things are worth pinning from outside:

* `avatar_url` survives the update. The profile fields pass through a
  whitelist in the service, and a field the schema accepts but the
  whitelist drops is a photo that uploads and then never appears - the
  exact gap this endpoint had.
* The update only ever touches the caller's own document: the path is
  `/users/me` and carries no other user id to aim at, so "only the owner
  may modify" holds by construction rather than by an extra check.
* A URL a browser would *act on* rather than display (`javascript:` etc.)
  is refused at the schema, before any repository sees it.
"""
from __future__ import annotations

import asyncio

import pytest
from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.auth.dependencies import get_current_active_user
from app.repositories.follow_repository import FollowRepository
from app.repositories.user_repository import UserRepository
from app.routes.users import get_profile_service, router as users_router
from app.schemas.user_update import UserUpdateRequest
from app.services.user_profile_service import UserProfileService
from tests.support.fake_mongo import FakeDatabase, make_user

ALICE = "aaaaaaaaaaaaaaaaaaaaaaa1"
BOB = "bbbbbbbbbbbbbbbbbbbbbbb2"

AVATAR = "https://res.cloudinary.com/gigcrowd/image/upload/alice_zk2.png"


@pytest.fixture
def db() -> FakeDatabase:
    return FakeDatabase(
        {
            "users": [
                make_user(ALICE, "alice"),
                make_user(
                    BOB,
                    "bob",
                    avatar_url="https://example.com/bob.jpg",
                ),
            ],
        }
    )


@pytest.fixture
def app(db):
    application = FastAPI()
    application.include_router(users_router)

    # The route builds its service from the module-level database; the
    # override points the same service at the in-memory one.
    application.dependency_overrides[get_profile_service] = (
        lambda: UserProfileService(
            user_repository=UserRepository(db),
            follow_repository=FollowRepository(db),
        )
    )
    return application


def _sign_in_as(app: FastAPI, user_id: str, username: str):
    async def override():
        return {"_id": user_id, "id": user_id, "username": username}

    app.dependency_overrides[get_current_active_user] = override


def _stored(db: FakeDatabase, user_id: str) -> dict:
    """The document as it stands after the request, read back directly."""
    return asyncio.run(
        db["users"].find_one({"_id": ObjectId(user_id)})
    )


class TestAvatarUpdate:
    def test_avatar_url_survives_the_whitelisted_update(self, app, db):
        """Saved, persisted and echoed - not silently filtered out.

        The service only forwards a known set of fields, and `avatar_url`
        was missing from it: the schema declared the field, the UI showed
        it, and the update dropped it on the way to the document.
        """
        with TestClient(app) as client:
            _sign_in_as(app, ALICE, "alice")
            response = client.put(
                "/users/me",
                json={"avatar_url": AVATAR},
            )

        assert response.status_code == 200
        assert response.json()["user"]["avatar_url"] == AVATAR

        stored = _stored(db, ALICE)
        assert stored["avatar_url"] == AVATAR

    def test_the_update_only_touches_the_callers_own_document(
        self, app, db
    ):
        """There is no other user id in the path to aim at.

        The same update run as Alice leaves Bob's document exactly as it
        was - his photo, his name - because `/users/me` never names anyone
        but the caller.
        """
        with TestClient(app) as client:
            _sign_in_as(app, ALICE, "alice")
            client.put(
                "/users/me",
                json={"avatar_url": AVATAR, "full_name": "Alice"},
            )

        bob = _stored(db, BOB)
        assert bob["avatar_url"] == "https://example.com/bob.jpg"
        assert bob["full_name"] == "Bob"

    def test_unknown_fields_are_still_dropped(self, app, db):
        """The whitelist is not widened into a general patch endpoint."""
        with TestClient(app) as client:
            _sign_in_as(app, ALICE, "alice")
            response = client.put(
                "/users/me",
                json={"role": "admin", "avatar_url": AVATAR},
            )

        assert response.status_code == 200

        stored = _stored(db, ALICE)
        assert "role" not in stored
        assert stored["avatar_url"] == AVATAR

    def test_a_scheme_the_browser_would_act_on_is_refused(self, app, db):
        """Refused at the schema, so no repository ever sees the value.

        The avatar lands on public pages; a scheme a browser executes
        rather than displays must not be a stored profile field.
        """
        with TestClient(app) as client:
            _sign_in_as(app, ALICE, "alice")
            response = client.put(
                "/users/me",
                json={"avatar_url": "javascript:alert(document.cookie)"},
            )

        assert response.status_code == 422

        stored = _stored(db, ALICE)
        assert stored.get("avatar_url") is None

    def test_the_schema_accepts_a_plain_https_url_and_trims_it(self):
        """Ordinary values pass through untouched, whitespace and all."""
        update = UserUpdateRequest(
            avatar_url=f"  {AVATAR}  "
        )

        assert update.avatar_url == AVATAR

        with pytest.raises(ValidationError):
            UserUpdateRequest(avatar_url="data:image/svg+xml,<svg/>")
