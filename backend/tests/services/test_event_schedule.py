"""The schedule rules that every "has this happened?" question depends on.

Imported events are inconsistent about dates: a concert carries `starts_at`, a
festival carries `ends_at` as well, and a real slice of the collection carries
neither. These tests pin the behaviour that the rest of the application relies
on, including the case that used to crash the show-log service.
"""
from datetime import UTC, datetime, timedelta

import pytest

from app.domain.event_schedule import (
    EVENT_DATE_UNAVAILABLE,
    EventDateUnavailable,
    as_utc,
    event_date,
    event_reference_date,
    has_event_date,
    is_past,
    is_upcoming,
    require_event_date,
)


NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def an_event(**fields) -> dict:
    """A raw stored event, the shape the mappers and services actually read."""

    return {
        "_id": "abc123",
        "title": "Some Concert",
        "artist_slug": "some-artist",
        "venue_slug": "some-venue",
        **fields,
    }


class TestAsUtc:

    def test_naive_datetimes_are_read_as_utc(self):

        # Provider imports store some dates without an offset. Comparing one
        # of those to an aware "now" raises, which is exactly the failure this
        # function exists to prevent.
        assert as_utc(
            datetime(2026, 1, 1, 20, 0)
        ) == datetime(2026, 1, 1, 20, 0, tzinfo=UTC)

    def test_aware_datetimes_are_converted_not_relabelled(self):

        from datetime import timezone

        aware = datetime(
            2026, 1, 1, 20, 0,
            tzinfo=timezone(timedelta(hours=-3)),
        )

        assert as_utc(aware) == datetime(
            2026, 1, 1, 23, 0, tzinfo=UTC,
        )

    @pytest.mark.parametrize(
        "value",
        [None, "", 0, "2026-01-01"],
    )
    def test_anything_that_is_not_a_datetime_is_absent(
        self,
        value,
    ):

        assert as_utc(value) is None


class TestEventDate:

    def test_start_wins_over_end(self):

        event = an_event(
            starts_at=datetime(2026, 3, 1, tzinfo=UTC),
            ends_at=datetime(2026, 3, 4, tzinfo=UTC),
        )

        assert event_date(event) == datetime(
            2026, 3, 1, tzinfo=UTC,
        )

    def test_end_is_used_when_there_is_no_start(self):

        # A festival whose import carried only its end date still has to be
        # placeable in time.
        event = an_event(
            ends_at=datetime(2026, 3, 4, tzinfo=UTC),
        )

        assert event_date(event) == datetime(
            2026, 3, 4, tzinfo=UTC,
        )

    def test_no_dates_is_none_rather_than_a_crash(self):

        assert event_date(an_event()) is None

    def test_none_of_everything_is_none(self):

        assert event_date(
            an_event(starts_at=None, ends_at=None)
        ) is None


class TestEventReferenceDate:

    def test_the_later_date_decides(self):

        # A festival that is still running has not happened yet, so the end
        # date is the one that answers "is it over?".
        event = an_event(
            starts_at=datetime(2026, 3, 1, tzinfo=UTC),
            ends_at=datetime(2026, 3, 4, tzinfo=UTC),
        )

        assert event_reference_date(event) == datetime(
            2026, 3, 4, tzinfo=UTC,
        )

    def test_the_later_of_two_inconsistent_dates_decides(self):

        # Bad imports do exist, with an end date before the start date. Taking
        # the later date keeps the conservative answer in both directions: the
        # show is treated as still ahead, so "I went" stays closed rather than
        # opening on a record nobody can trust.
        event = an_event(
            starts_at=datetime(2026, 7, 1, tzinfo=UTC),
            ends_at=datetime(2026, 2, 1, tzinfo=UTC),
        )

        assert event_reference_date(event) == datetime(
            2026, 7, 1, tzinfo=UTC,
        )
        assert not is_past(event, NOW)
        assert is_upcoming(event, NOW)

    def test_no_dates_is_none(self):

        assert event_reference_date(an_event()) is None


class TestIsPast:

    def test_a_finished_concert_is_past(self):

        event = an_event(
            starts_at=NOW - timedelta(days=1),
        )

        assert is_past(event, NOW)

    def test_an_upcoming_concert_is_not_past(self):

        event = an_event(
            starts_at=NOW + timedelta(days=1),
        )

        assert not is_past(event, NOW)

    def test_a_running_festival_is_not_past(self):

        event = an_event(
            starts_at=NOW - timedelta(days=1),
            ends_at=NOW + timedelta(days=1),
        )

        assert not is_past(event, NOW)

    def test_an_undated_event_is_never_past(self):

        # There is no evidence such a show happened, and guessing would let
        # someone record attendance to an event that is still being announced.
        assert not is_past(an_event(), NOW)

    def test_a_missing_event_is_not_past(self):

        assert not is_past(None, NOW)

    def test_the_boundary_moment_counts_as_upcoming(self):

        # An event that starts exactly now has not finished, so "I went" is
        # not yet available on it.
        event = an_event(starts_at=NOW)

        assert not is_past(event, NOW)


class TestIsUpcoming:

    def test_rejects_an_undated_event(self):

        assert not is_upcoming(an_event(), NOW)

    def test_a_future_concert_is_upcoming(self):

        event = an_event(
            starts_at=NOW + timedelta(hours=1),
        )

        assert is_upcoming(event, NOW)

    def test_a_past_concert_is_not_upcoming(self):

        event = an_event(
            starts_at=NOW - timedelta(hours=1),
        )

        assert not is_upcoming(event, NOW)


class TestHasEventDate:

    @pytest.mark.parametrize(
        "fields",
        [
            {"starts_at": NOW},
            {"ends_at": NOW},
            {"starts_at": None, "ends_at": NOW},
            {
                "starts_at": NOW - timedelta(days=2),
                "ends_at": NOW - timedelta(days=1),
            },
        ],
    )
    def test_any_usable_date_counts(
        self,
        fields,
    ):

        assert has_event_date(an_event(**fields))

    def test_no_dates_is_false(self):

        assert not has_event_date(an_event())

    def test_an_unusable_date_value_is_false(self):

        # The raw stored value is not a datetime at all, so it cannot answer
        # the question either.
        assert not has_event_date(
            an_event(starts_at="not-a-date")
        )


class TestRequireEventDate:

    def test_returns_the_reference_date(self):

        event = an_event(
            starts_at=datetime(2026, 3, 1, tzinfo=UTC),
            ends_at=datetime(2026, 3, 4, tzinfo=UTC),
        )

        assert require_event_date(event) == datetime(
            2026, 3, 4, tzinfo=UTC,
        )

    def test_raises_a_value_error_so_the_route_can_answer_400(self):

        # `EventDateUnavailable` subclasses `ValueError` precisely because the
        # show-log routes already translate `ValueError` into a deliberate
        # 400. A missing date is a product decision, not a server fault.
        with pytest.raises(ValueError) as raised:

            require_event_date(an_event())

        assert str(raised.value) == EVENT_DATE_UNAVAILABLE
        assert isinstance(
            raised.value,
            EventDateUnavailable,
        )

    def test_a_missing_event_also_raises(self):

        with pytest.raises(EventDateUnavailable):

            require_event_date(None)

    def test_the_message_explains_the_product_decision(self):

        # The message reaches the client, so it has to say what to do next
        # rather than leaking a server detail.
        assert "no confirmed date" in EVENT_DATE_UNAVAILABLE
