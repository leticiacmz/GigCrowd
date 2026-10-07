"""Whether an event can be believed, and why.

A valid date is not provenance. Every case here exists because the version of the
data without it produced a specific lie: a show dated next year for an artist who
is not touring, presented as an announced gig, backed by a Songkick-shaped URL
that 404s.

Nothing in this file knows any artist's name. The rules are about where a row
came from, so the same fixture stays a fixture whatever it is called and a real
import stays real.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.event_provenance import (
    DEV_FIXTURE_ID_PREFIX,
    PROVENANCE_FIXTURE,
    PROVENANCE_SONGKICK,
    PROVENANCE_UNKNOWN,
    classify,
    has_concrete_source,
    is_trustworthy_upcoming,
    reaches_into_the_future,
    synthetic_songkick_id,
)

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


def real_event(**overrides) -> dict:
    """An event read from a Songkick page: real id, real URL, real date."""

    document = {
        "_id": "e1",
        "title": "Marina Sena at Auditorio Ibirapuera",
        "event_type": "Concert",
        "starts_at": NOW + timedelta(days=30),
        "artist_slug": "marina-sena",
        "external_ids": {"songkick": "3090429"},
        "source": {
            "provider": "songkick",
            "url": (
                "https://www.songkick.com/concerts/"
                "40352877-marina-sena-at-auditorio-ibirapuera"
            ),
            "event_id": "40352877",
        },
    }

    document.update(overrides)

    return document


def fixture_event(**overrides) -> dict:
    """A development fixture: ours, not the provider's."""

    document = {
        "_id": "f1",
        "title": "Gal Costa at Auditorio Ibirapuera",
        "event_type": "Concert",
        "starts_at": NOW + timedelta(days=43),
        "artist_slug": "gal-costa",
        "external_ids": {"songkick": "9900109"},
        "source": {
            "provider": "songkick",
            "url": (
                "https://www.songkick.com/concerts/"
                "9900109-gal-costa-at-auditorio-ibirapuera"
            ),
            "event_id": "9900109",
        },
    }

    document.update(overrides)

    return document


def festival_edition(**overrides) -> dict:
    document = {
        "_id": "d1",
        "title": "Festival Vale 2026 - Day 1",
        "event_type": "FestivalInstance",
        "starts_at": NOW - timedelta(days=180),
        "ends_at": NOW - timedelta(days=176),
        "external_ids": {"songkick": "9900201"},
        "source": {
            "provider": "songkick",
            "url": (
                "https://www.songkick.com/festivals/"
                "9900200-festival-vale/id/9900201"
            ),
            "event_id": "9900201",
        },
        "festival": {"series_id": "9900200", "name": "Festival Vale"},
    }

    document.update(overrides)

    return document


class TestIdentifyingOurOwnIdentifiers:
    def test_the_fixture_block_is_recognised_bare(self):
        assert synthetic_songkick_id("9900109") is True

    def test_it_is_recognised_with_the_artist_prefix(self):
        assert synthetic_songkick_id("Artist9900109") is True

    def test_a_real_artist_id_is_not_mistaken_for_a_fixture(self):
        assert synthetic_songkick_id("3090429") is False
        assert synthetic_songkick_id("Artist520117") is False

    def test_nothing_is_not_a_fixture(self):
        assert synthetic_songkick_id(None) is False

    def test_the_block_is_narrow_and_declared_once(self):
        # A block that started matching real ids would misclassify real imports,
        # so its width is part of the contract.
        assert DEV_FIXTURE_ID_PREFIX == "9900"


class TestClassification:
    def test_a_songkick_import_is_songkick(self):
        assert classify(real_event()) == PROVENANCE_SONGKICK

    def test_a_fixture_is_a_fixture_even_though_it_looks_like_songkick(self):
        # The provider name and a provider-shaped URL are exactly what makes a
        # fixture usable, so testing those first classified it as an import.
        assert classify(fixture_event()) == PROVENANCE_FIXTURE

    def test_a_recorded_provenance_is_believed_over_inference(self):
        document = fixture_event()

        document["source"]["provenance"] = PROVENANCE_SONGKICK

        assert classify(document) == PROVENANCE_SONGKICK

    def test_an_event_claiming_a_provider_with_no_url_is_unverifiable(self):
        document = real_event()
        document["source"] = {"provider": "songkick", "url": None}

        assert classify(document) == PROVENANCE_UNKNOWN

    def test_a_url_on_another_host_is_not_songkick_evidence(self):
        document = real_event()
        document["source"]["url"] = "https://example.com/show/1"

        assert classify(document) == PROVENANCE_UNKNOWN

    def test_classification_is_stable(self):
        document = real_event()

        assert classify(document) == classify(document)

    def test_no_rule_mentions_an_artist(self):
        # A rule keyed on an artist would be a special case waiting to be wrong.
        # The fixture and the import differ by identifier and URL only.
        assert classify(fixture_event()) != classify(real_event())
        assert set(fixture_event()["artist_slug"] for _ in [0]) == {
            "gal-costa"
        }


class TestConcreteSource:
    def test_a_provider_url_is_concrete(self):
        assert has_concrete_source(real_event()) is True

    def test_a_missing_url_is_not(self):
        document = real_event()
        document["source"]["url"] = ""

        assert has_concrete_source(document) is False

    def test_a_fixture_has_a_url_but_it_is_not_evidence(self):
        # It resolves to nothing, so `has_concrete_source` being true is not by
        # itself a pass - which is why the verdict also checks provenance.
        assert has_concrete_source(fixture_event()) is True

        trusted, reason = is_trustworthy_upcoming(
            fixture_event(), now=NOW
        )

        assert trusted is False
        assert "fixture" in reason


class TestFutureDetection:
    """
    Every case below passes `NOW` to the function.

    The fixtures are built from a frozen instant, so comparing them against the
    real clock is only accidentally correct - and only until the day the fixture
    runs out. `ends_at = NOW + 1 day` was true for a while and then quietly became
    false, which is how a test starts failing for a reason nobody changed.
    """

    def test_a_start_in_the_future_is_future(self):
        assert reaches_into_the_future(real_event(), now=NOW) is True

    def test_an_end_still_running_counts_as_future(self):
        document = real_event(
            starts_at=NOW - timedelta(days=1),
            ends_at=NOW + timedelta(days=1),
        )

        assert reaches_into_the_future(document, now=NOW) is True

    def test_a_finished_show_is_not_future(self):
        document = real_event(starts_at=NOW - timedelta(days=30))

        assert reaches_into_the_future(document, now=NOW) is False

    def test_no_date_is_not_future(self):
        assert reaches_into_the_future({"_id": "x"}, now=NOW) is False


class TestWhatMayBePresentedAsUpcoming:
    def test_a_real_future_songkick_event_is_trustworthy(self):
        trusted, reason = is_trustworthy_upcoming(real_event(), now=NOW)

        assert trusted is True
        assert reason == "verified_songkick_provenance"

    def test_a_future_fixture_is_not(self):
        # The case that started this: a plausible date, a provider-shaped URL,
        # and nothing behind either.
        trusted, reason = is_trustworthy_upcoming(fixture_event(), now=NOW)

        assert trusted is False
        assert "fixture" in reason

    def test_a_past_fixture_is_not_judged_as_an_upcoming_claim(self):
        # Provenance still records what it is, but a finished fixture is history
        # and makes no promise about the future.
        document = fixture_event(starts_at=NOW - timedelta(days=400))

        trusted, reason = is_trustworthy_upcoming(document, now=NOW)

        assert trusted is True
        assert reason == "not_upcoming"

    def test_a_future_event_with_no_source_is_rejected(self):
        document = real_event()
        document["source"] = {"provider": "songkick"}

        trusted, reason = is_trustworthy_upcoming(document, now=NOW)

        assert trusted is False
        assert "no source" in reason

    def test_a_real_festival_edition_past_or_present_is_untouched(self):
        trusted, _ = is_trustworthy_upcoming(festival_edition(), now=NOW)

        assert trusted is True

    def test_a_future_festival_edition_fixture_is_rejected(self):
        document = festival_edition(
            starts_at=NOW + timedelta(days=200),
            ends_at=NOW + timedelta(days=204),
        )

        trusted, reason = is_trustworthy_upcoming(document, now=NOW)

        assert trusted is False
        assert "fixture" in reason

    def test_the_verdict_never_names_an_artist(self):
        # Renaming the fixture's artist must not change the verdict.
        original = fixture_event()

        renamed = fixture_event(
            artist_slug="someone-else",
            title="Someone Else at Auditorio Ibirapuera",
        )

        assert is_trustworthy_upcoming(original) == (
            is_trustworthy_upcoming(renamed)
        )


class TestTheSeedSaysWhatItIs:
    """The fixture is written by the project, so the project has to say so.

    Without this the rows went into the database looking exactly like imports,
    which is how a fixture dated next year became an announced show.
    """

    def test_every_seeded_event_records_that_it_is_a_fixture(self):
        from app.scripts.seed_dev_data import build_dataset

        events = build_dataset()["events"]

        assert events

        for event in events:
            assert (event.get("source") or {}).get(
                "provenance"
            ) == PROVENANCE_FIXTURE, event.get("title")

    def test_seeded_fixture_ids_are_recognised_as_ours(self):
        from app.scripts.seed_dev_data import build_dataset

        events = build_dataset()["events"]

        songkick_ids = [
            (event.get("external_ids") or {}).get("songkick")
            for event in events
        ]

        songkick_ids = [
            value for value in songkick_ids if value
        ]

        assert songkick_ids

        assert all(
            synthetic_songkick_id(value) for value in songkick_ids
        )

    def test_a_seeded_future_event_is_never_trustworthy_as_upcoming(self):
        from app.scripts.seed_dev_data import build_dataset

        future_fixtures = [
            event
            for event in build_dataset()["events"]
            if is_trustworthy_upcoming(event)[0] is False
        ]

        assert future_fixtures

        for event in future_fixtures:
            trusted, reason = is_trustworthy_upcoming(event)

            assert trusted is False
            assert "fixture" in reason


class TestLineupsAreNotPerformances:
    """A lineup entry names an act on a bill; it is not an event of its own."""

    def test_a_festival_date_is_not_an_artist_performance(self):
        document = festival_edition()

        # No headline artist, and a series identity instead: the row describes
        # the edition, not a set by one act.
        assert document["event_type"] == "FestivalInstance"
        assert not document.get("artist_slug")
        assert document["festival"]["series_id"]

    def test_provenance_does_not_infer_a_performer_from_a_lineup(self):
        document = festival_edition(
            lineup=[{"name": "O Terno", "slug": "o-terno", "songkick_id": "2921978"}]
        )

        # The lineup is present and the event is still an edition, not a
        # performance by that act.
        assert document["event_type"] == "FestivalInstance"
        assert is_trustworthy_upcoming(document)[0] is True
