"""The three artist states, and the one decision each of them is allowed to cause.

`pending` and `initialized` are easy to keep apart. The dangerous pair is
`initialized` and `error`, because they look alike in a log and behave
completely differently: one page view may fetch for the second and must never for
the first.

Every derivation here reads `sync_status` and `last_synced_at`, and nothing
else. That is the whole design - the fields already existed, and adding an
`availability` column beside them would mean two sources of truth for one fact,
where the one nobody remembers to update is the one that decides whether a page
view performs a gigography scrape.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.artist_state import (
    ERROR,
    INITIALIZED,
    INITIALIZING,
    PENDING,
    artist_state,
    is_initialized,
    is_pending,
    needs_initialization,
)


def an_artist(**fields) -> dict:
    return fields


NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


class TestAPendingArtist:
    def test_nothing_at_all_is_pending(self):
        """The shape `ensure_by_songkick_id` writes.

        A festival announced them, the identity was checked, and a minimal record
        exists. No fetch has been attempted, so this is the state in which opening
        the page is allowed to fetch.
        """

        assert artist_state(an_artist()) == PENDING

    def test_a_stored_null_is_still_pending(self):
        """Absent is not the same as stored-null, and the code must say so.

        `ensure_by_songkick_id` leaves the fields *absent* rather than present and
        null precisely because a null is a weaker, easier-to-miss version of "never
        fetched" - a query filtering on `$ne: null` would skip the artist, and a
        stub that reads as "already handled" is how a lineup quietly becomes a list
        of artists nobody ever opened. A reader that conflated the two would undo
        that.
        """

        assert (
            artist_state(
                an_artist(sync_status=None, last_synced_at=None)
            )
            == PENDING
        )

    def test_it_may_be_initialized(self):
        assert needs_initialization(an_artist()) is True
        assert is_pending(an_artist()) is True

    def test_it_is_not_read_only(self):
        assert is_initialized(an_artist()) is False


class TestAnInitializedArtist:
    @pytest.mark.parametrize(
        "status", ["success", "empty"]
    )
    def test_a_completed_fetch_is_initialized(self, status):
        artist = an_artist(
            sync_status=status,
            last_synced_at=NOW,
        )

        assert artist_state(artist) == INITIALIZED

    def test_empty_counts_as_initialized_and_this_is_the_subtle_one(self):
        """"The provider was asked and there is nothing" is an answer.

        Treating it as "not really initialized" would mean a genuinely unbooked
        artist is re-fetched every time somebody opens the page, forever - and it
        would look identical in the logs to an artist whose fetch keeps failing.
        The two failures are worth telling apart, and the way to tell them apart
        is for `empty` to be initialized and `error` not to be.
        """

        artist = an_artist(
            sync_status="empty",
            last_synced_at=NOW,
        )

        assert is_initialized(artist) is True
        assert needs_initialization(artist) is False

    def test_a_timestamp_alone_is_enough(self):
        """For artists synchronized before `sync_status` was ever written.

        Without this they would silently fall out of maintenance and never be
        refreshed again - a quiet, permanent loss.
        """

        assert (
            artist_state(an_artist(last_synced_at=NOW)) == INITIALIZED
        )

    def test_it_is_read_only(self):
        artist = an_artist(sync_status="success", last_synced_at=NOW)

        assert is_initialized(artist) is True
        assert needs_initialization(artist) is False
        assert is_pending(artist) is False


class TestAnErroredArtist:
    def test_a_failed_fetch_is_an_error(self):
        artist = an_artist(sync_status="error")

        assert artist_state(artist) == ERROR

    def test_it_may_be_retried_by_a_person(self):
        """Retryable - and by a person, because nobody else is permitted to.

        The only two paths that initialize an artist are an explicit import and a
        first open. If an open did not retry a failed fetch, the only remaining
        retry would be the scheduler, which deliberately does not drain unopened
        artists - and the artist would be stuck uninitialized for good.
        """

        assert needs_initialization(an_artist(sync_status="error")) is True

    def test_it_is_not_pending(self):
        """The distinction that keeps an outage from looking like a cold start.

        `pending` means "nobody has asked". `error` means "somebody asked and the
        answer was lost". Merging them makes a provider outage look like a
        catalogue of artists nobody wants.
        """

        assert is_pending(an_artist(sync_status="error")) is False

    def test_it_is_not_read_only(self):
        assert is_initialized(an_artist(sync_status="error")) is False


class TestAClaimInFlight:
    def test_it_is_its_own_state(self):
        assert (
            artist_state(an_artist(sync_status=INITIALIZING))
            == INITIALIZING
        )

    def test_a_second_open_does_not_fetch_over_it(self):
        """Somebody is already spending a full gigography scrape.

        A second fetch would produce the same rows twice over. Reading as
        initialized for this decision is what prevents it - the artist *is* being
        handled.
        """

        assert needs_initialization(
            an_artist(sync_status=INITIALIZING)
        ) is False

    def test_but_it_still_reads_as_initialized(self):
        """A page served during the claim must not be re-fetched either."""

        assert is_initialized(
            an_artist(sync_status=INITIALIZING)
        ) is True


class TestAnUnknownStatus:
    def test_it_is_never_treated_as_pending(self):
        """The direction of the mistake matters more than its size.

        An unrecognised `sync_status` is more likely to be a newer, more complete
        state than a missing one. Guessing "pending" would turn it into a
        gigography scrape on every page view - the exact bug this model exists to
        prevent - whereas guessing "initialized" costs at worst a slow refresh.
        """

        assert (
            artist_state(an_artist(sync_status="imported_v2"))
            == INITIALIZED
        )

        assert needs_initialization(
            an_artist(sync_status="imported_v2")
        ) is False


class TestItReadsDocumentsAndObjectsAlike:
    def test_a_domain_object_works(self):
        class FakeArtist:
            sync_status = "success"
            last_synced_at = NOW

        assert artist_state(FakeArtist()) == INITIALIZED

    def test_a_raw_document_works(self):
        """Every caller holds one or the other, and neither should have to
        convert first just to ask a question."""

        assert (
            artist_state({"sync_status": "success", "last_synced_at": NOW})
            == INITIALIZED
        )

    def test_something_with_neither_field_is_pending_not_an_error(self):
        """Absence of the object itself is absence of evidence."""

        assert artist_state(object()) == PENDING

    def test_a_timestamp_is_not_read_as_a_date(self):
        """Only presence is asked about.

        The value is somebody else's problem - `SynchronizationService` owns what
        staleness means, and a state reader that also judged age would be a second
        place for the TTL to live.
        """

        long_ago = NOW - timedelta(days=900)

        assert artist_state(an_artist(last_synced_at=long_ago)) == INITIALIZED
