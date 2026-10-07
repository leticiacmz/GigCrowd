"""The reset script's refusal rules.

This is the only piece of code in the project that deletes data, so its
refusals are the part that matters. Each test here corresponds to a way the
configured target could turn out to be something other than a local
development database.

The rule being protected is simple: when in doubt, delete nothing.
"""
from __future__ import annotations

import pytest

from app.scripts.reset_dev_db import (
    RESETTABLE_DATABASES,
    UnsafeTarget,
    verify_local_development_target,
)


LOCAL_URI = "mongodb://localhost:27017"
LOCAL_DB = "gigcrowd"


class TestLocalTargetsAreAccepted:
    def test_the_project_default_is_accepted(self):
        confirmation = verify_local_development_target(LOCAL_URI, LOCAL_DB)

        # The confirmation names what was checked, so the operator can see
        # what was verified instead of taking it on trust.
        assert "localhost:27017/gigcrowd" in confirmation

    @pytest.mark.parametrize(
        "host",
        [
            "localhost",
            "127.0.0.1",
            # An IPv6 literal is bracketed in a URI. The unbracketed spelling
            # is not a URI at all, and is refused below as malformed.
            "[::1]",
        ],
    )
    def test_every_loopback_spelling_is_accepted(self, host):
        verify_local_development_target(f"mongodb://{host}:27017", LOCAL_DB)

    def test_a_missing_port_is_still_local(self):
        confirmation = verify_local_development_target(
            "mongodb://localhost", LOCAL_DB
        )

        assert "localhost:27017" in confirmation


class TestRemoteTargetsAreRefused:
    @pytest.mark.parametrize(
        "uri",
        [
            "mongodb://db.example.com:27017",
            "mongodb://10.0.0.5:27017",
            "mongodb://192.168.1.20:27017",
            # A name that merely contains "localhost" is not localhost.
            "mongodb://localhost.attacker.example:27017",
            "mongodb://mongodb:27017",
        ],
    )
    def test_anything_that_is_not_loopback_is_refused(self, uri):
        # The composed-hostname case is the interesting one: a naive
        # `in` check would accept `localhost.attacker.example`.
        with pytest.raises(UnsafeTarget):
            verify_local_development_target(uri, LOCAL_DB)

    def test_a_hosted_deployment_is_refused(self):
        with pytest.raises(UnsafeTarget) as raised:
            verify_local_development_target(
                "mongodb+srv://user:pass@cluster0.example.mongodb.net",
                LOCAL_DB,
            )

        assert "hosted deployment" in str(raised.value)

    def test_credentials_in_the_uri_do_not_hide_a_remote_host(self):
        with pytest.raises(UnsafeTarget):
            verify_local_development_target(
                "mongodb://admin:hunter2@db.example.com:27017",
                LOCAL_DB,
            )


class TestUnknownDatabasesAreRefused:
    def test_a_deployment_database_name_is_refused(self):
        # A production deployment with its own database name must not be
        # reachable by running this script.
        with pytest.raises(UnsafeTarget) as raised:
            verify_local_development_target(LOCAL_URI, "gigcrowd_production")

        assert "gigcrowd_production" in str(raised.value)

    def test_every_accepted_name_is_on_the_allow_list(self):
        # Guards against the allow-list being widened by accident.
        assert "gigcrowd" in RESETTABLE_DATABASES
        assert "gigcrowd_dev" in RESETTABLE_DATABASES
        assert "gigcrowd_test" in RESETTABLE_DATABASES

        for name in ("gigcrowd_production", "prod", "test", "admin", "local"):
            assert name not in RESETTABLE_DATABASES


class TestMalformedTargetsAreRefused:
    @pytest.mark.parametrize(
        "uri",
        [
            "",
            "localhost:27017",
            "postgres://localhost:27017",
            "http://localhost:27017",
            # An IPv6 literal without brackets is not a parsable URI, so it
            # cannot be shown to be loopback and is refused.
            "mongodb://::1:27017",
        ],
    )
    def test_something_that_is_not_a_mongo_uri_is_refused(self, uri):
        with pytest.raises(UnsafeTarget):
            verify_local_development_target(uri, LOCAL_DB)
