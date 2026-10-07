"""Backfilling how each event's date was resolved.

The classification rules are the whole content of this migration, so they are
tested directly rather than through the script. Two of them are the ones that
would quietly corrupt the enrichment system if they were wrong: an event with no
date must not be filed as a parser failure, and a migration must never move an
event in time.
"""
from __future__ import annotations

from datetime import UTC, datetime

from app.migrations.backfill_date_status import (
    VALID_STATUSES,
    classify,
)
from app.services.event_enrichment_service import (
    DATE_FROM_SOURCE,
    DATE_PARSER_FAILED,
    DATE_UNAVAILABLE,
)


SONGKICK_DATE = datetime(2022, 10, 31, tzinfo=UTC)


class TestAnEventThatHasADate:
    """A date the importer read off the provider's page."""

    def test_a_dated_songkick_event_is_recorded_as_coming_from_the_source(self):
        status, _ = classify({
            "starts_at": SONGKICK_DATE,
            "source": {
                "url": "https://www.songkick.com/festivals/x/id/1"
            },
            "external_ids": {"songkick": "1"},
        })

        assert status == DATE_FROM_SOURCE

    def test_a_dated_event_without_a_recorded_source_is_still_from_the_source(self):
        # Some older rows never had their source written down. They were still
        # read from a provider page, and inventing a fourth status for them
        # would make them indistinguishable in every later report.
        status, reason = classify({
            "starts_at": SONGKICK_DATE,
        })

        assert status == DATE_FROM_SOURCE
        assert "no provider source" in reason

    def test_an_end_date_alone_counts_as_having_a_date(self):
        status, _ = classify({
            "ends_at": SONGKICK_DATE,
        })

        assert status == DATE_FROM_SOURCE


class TestAnEventWithoutADate:
    """The case that must not be confused with a parser failure."""

    def test_an_undated_event_with_a_source_is_unavailable(self):
        status, _ = classify({
            "starts_at": None,
            "source": {
                "url": "https://www.songkick.com/festivals/x/id/1"
            },
        })

        assert status == DATE_UNAVAILABLE

    def test_an_undated_event_with_no_source_is_unavailable(self):
        status, reason = classify({
            "starts_at": None,
        })

        assert status == DATE_UNAVAILABLE
        assert "nothing to re-read" in reason

    def test_nothing_is_ever_backfilled_as_a_parser_failure(self):
        """A parser failure means a date was stated and could not be read.

        Only a read of the page can establish that. Backfilling it from the
        absence of a date would tell the enrichment system to retry events that
        can never succeed, and would make "we could not parse it" and "there is
        no date" the same thing - which is precisely what the field exists to
        prevent.
        """

        for document in (
            {"starts_at": None},
            {"starts_at": None, "ends_at": None},
            {"starts_at": None, "source": {"url": "https://x.test"}},
            {},
            {"starts_at": None, "external_ids": {"songkick": "1"}},
        ):

            status, _ = classify(document)

            assert status != DATE_PARSER_FAILED, document

    def test_a_source_with_an_empty_url_is_not_treated_as_a_source(self):
        status, _ = classify({
            "starts_at": None,
            "source": {"url": ""},
            "external_ids": {"songkick": ""},
        })

        assert status == DATE_UNAVAILABLE


class TestTheThreeStatesStayDistinct:
    def test_the_migration_only_writes_valid_states(self):
        assert set(VALID_STATUSES) == {
            DATE_FROM_SOURCE,
            DATE_UNAVAILABLE,
            DATE_PARSER_FAILED,
        }

    def test_dated_and_undated_records_land_in_different_states(self):
        dated, _ = classify({"starts_at": SONGKICK_DATE})
        undated, _ = classify({"starts_at": None})

        assert dated != undated

    def test_every_document_classifies_to_a_valid_state(self):
        documents = [
            {"starts_at": SONGKICK_DATE},
            {"starts_at": None},
            {},
            {"ends_at": SONGKICK_DATE, "starts_at": None},
            {"starts_at": None, "source": {"url": "https://x.test"}},
        ]

        for document in documents:

            status, reason = classify(document)

            assert status in VALID_STATUSES
            assert reason
