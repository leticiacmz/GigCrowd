"""The register endpoint hands back a session, not just a user row.

Registering already means the person is signed in: the client stores the
answer as its session and goes on to the page the form sent them to. The
route used to answer with the bare user document, so a client had no token
to store - the response looked successful and the visitor arrived signed
out. These tests pin the session shape `/auth/login` returns, that the
token it carries names the created user, and that the account it creates
is immediately usable for a login.
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.security import decode_access_token
from app.routes.auth import router as auth_router
from tests.support.fake_mongo import FakeDatabase

EMAIL = "newfan@gigcrowd.com"
USERNAME = "newfan"
PASSWORD = "SecurePass123!"


@pytest.fixture
def db() -> FakeDatabase:
    return FakeDatabase({"users": []})


@pytest.fixture
def app(db, monkeypatch) -> FastAPI:
    # The route creates the user through the service, which reads the
    # module-level database; the patch points that read at the in-memory one.
    monkeypatch.setattr(
        "app.services.user_service.get_database",
        lambda: db,
    )

    application = FastAPI()
    application.include_router(auth_router)

    return application


def _payload(**overrides) -> dict:
    payload = {
        "email": EMAIL,
        "username": USERNAME,
        "password": PASSWORD,
    }
    payload.update(overrides)

    return payload


class TestRegisterSession:
    def test_the_answer_is_the_session_shape_login_returns(self, app):
        with TestClient(app) as client:
            response = client.post("/auth/register", json=_payload())

        assert response.status_code == 201

        body = response.json()

        assert set(body) == {"access_token", "token_type", "user"}
        assert body["token_type"] == "bearer"
        assert body["access_token"]

        user = body["user"]

        assert user["email"] == EMAIL
        assert user["username"] == USERNAME
        assert user["id"]

        # The session carries the public user, never the hash.
        assert "hashed_password" not in user
        assert "password" not in user

    def test_the_token_names_the_user_that_was_created(self, app):
        with TestClient(app) as client:
            response = client.post("/auth/register", json=_payload())

        body = response.json()
        claims = decode_access_token(body["access_token"])

        assert claims is not None
        assert claims["sub"] == body["user"]["id"]

    def test_the_created_account_can_log_in_with_the_same_credentials(
        self, app
    ):
        with TestClient(app) as client:
            created = client.post("/auth/register", json=_payload())

            signed_in = client.post(
                "/auth/login",
                data={"username": EMAIL, "password": PASSWORD},
            )

        assert created.status_code == 201
        assert signed_in.status_code == 200

        session = signed_in.json()

        assert set(session) == {"access_token", "token_type", "user"}
        assert session["user"]["id"] == created.json()["user"]["id"]

    def test_a_duplicate_email_is_refused_with_a_reason(self, app):
        with TestClient(app) as client:
            client.post("/auth/register", json=_payload())

            response = client.post(
                "/auth/register",
                json=_payload(username="somebody-else"),
            )

        assert response.status_code == 400
        assert isinstance(response.json()["detail"], str)
        assert response.json()["detail"]

    def test_a_password_that_is_too_short_never_reaches_a_write(self, app, db):
        with TestClient(app) as client:
            response = client.post(
                "/auth/register",
                json=_payload(password="short"),
            )

        assert response.status_code == 422

        # Nothing was created, so the address is still free.
        stored = asyncio.run(db["users"].find_one({"email": EMAIL}))

        assert stored is None
