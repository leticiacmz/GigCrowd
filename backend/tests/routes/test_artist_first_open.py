"""The first open of a pending artist, and every open after it.

A festival announced an act, their Songkick identity was checked against their
own page, and a minimal record was written so their name in the lineup would be
pressable. That record knows who they are and nothing about when they play.

Two things then have to be true, and they pull in opposite directions:

* Somebody who opens that page expects a discography. Rendering an empty page and
  an apology is not the answer; fetching the shows is.
* An artist page must never be a way to scrape a provider. The previous version
  of this application fetched a gigography on *every* view, which made browsing
  slow, cost an unbounded number of calls inside Songkick, and grew the
  catalogue under a reader who had only looked at it.

So the distinction is the artist's state, checked before anything is fetched:

    pending / errored  -> may initialize, exactly once, under a claim
    initialized        -> read-only, every time

These tests hold both halves of that, because a test that only checks the
exciting one will happily pass an implementation that scrapes on every read.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.artist_profile_response import ArtistProfileResponse


client = TestClient(app)


def an_artist(
    slug: str = "tim-bernardes",
    *,
    sync_status: str | None = None,
    last_synced_at=None,
    updated_at=None,
) -> MagicMock:
    artist = MagicMock()

    artist.id = f"mongo-id-{slug}"
    artist.slug = slug
    artist.name = slug.replace("-", " ").title()
    artist.sync_status = sync_status
    artist.last_synced_at = last_synced_at

    # Set explicitly rather than left as an auto-created mock attribute: the
    # route reads this to decide whether a failed fetch may be retried, and a
    # MagicMock standing in for a datetime would make that comparison raise
    # rather than mean something.
    artist.updated_at = updated_at

    return artist


def a_profile(slug: str = "tim-bernardes", **events) -> ArtistProfileResponse:
    """A real response object, not a dict.

    The route sets `sync` on whatever the service returned, so a double that
    returns a plain dict would make the route look broken when it is behaving
    correctly. Doubles that differ from the real thing in type rather than in
    value test the wrong thing.
    """

    return ArtistProfileResponse(
        id=f"mongo-id-{slug}",
        slug=slug,
        name=slug.replace("-", " ").title(),
        external_ids={"songkick": "2668421"},
        genres=[],
        followers_count=0,
        popularity=None,
        verified=False,
        events=events or {"upcoming": 4, "total": 212},
    )


def a_sync_service(**result):
    service = MagicMock()

    service.synchronize_artist = AsyncMock(
        return_value={
            "synced": True,
            "result": {
                "events_received": result.get("received", 212),
                "events_created": result.get("created", 205),
                "events_existing": result.get("existing", 7),
            },
        }
    )

    return service


def a_repository(
    artist,
    *,
    claimable: bool = True,
) -> MagicMock:
    repository = MagicMock()

    repository.get_by_slug = AsyncMock(return_value=artist)

    repository.claim_initialization = AsyncMock(
        return_value=claimable
    )

    repository.release_initialization_claim = AsyncMock(
        return_value=None
    )

    return repository


def a_service(profile: ArtistProfileResponse) -> MagicMock:
    """A profile service that builds a fresh response per call.

    The real service constructs a new object every time, and the route sets
    `sync` on whatever it gets back. A double that handed back the same instance
    twice would carry the first call's `sync` into the second response and make
    a read look like a write.
    """

    service = MagicMock()

    async def get_artist_profile(slug):
        return profile.model_copy(deep=True)

    service.get_artist_profile = AsyncMock(
        side_effect=get_artist_profile
    )

    return service


class TestAPendingArtistIsInitializedOnFirstOpen:
    def test_opening_it_fetches_the_gigography(self):
        artist = an_artist(sync_status=None)
        sync = a_sync_service()

        with patch("app.routes.artists.artist_service",
                   a_service(a_profile())), \
                patch("app.routes.artists.artist_repository",
                      a_repository(artist)), \
                patch("app.routes.artists.synchronization_service", sync):
            response = client.get("/artists/tim-bernardes")

        assert response.status_code == 200

        sync.synchronize_artist.assert_awaited_once()

        # Forced. The TTL exists to stop a *scheduler* re-fetching an artist it
        # read recently; applying it here would mean a person's first visit
        # silently returned nothing.
        assert sync.synchronize_artist.await_args.kwargs.get("force") is True

    def test_the_response_carries_what_was_fetched(self):
        artist = an_artist(sync_status=None)

        with patch("app.routes.artists.artist_service",
                   a_service(a_profile())), \
                patch("app.routes.artists.artist_repository",
                      a_repository(artist)), \
                patch("app.routes.artists.synchronization_service",
                      a_sync_service()):
            body = client.get("/artists/tim-bernardes").json()

        assert body["sync"]["attempted"] is True
        assert body["sync"]["succeeded"] is True
        assert body["sync"]["events_received"] == 212

        # The point of re-reading after the fetch: the page describes what was
        # stored, not what was there a minute ago.
        assert body["events"]["total"] == 212

    def test_the_artist_is_reread_after_the_fetch(self):
        """Otherwise the response describes a record the fetch has already
        superseded, and the reader sees an empty discography on the one page load
        that actually went and got one."""

        artist = an_artist(sync_status=None)
        repository = a_repository(artist)

        with patch("app.routes.artists.artist_service",
                   a_service(a_profile())), \
                patch("app.routes.artists.artist_repository", repository), \
                patch("app.routes.artists.synchronization_service",
                      a_sync_service()):
            client.get("/artists/tim-bernardes")

        # Once to decide the state, once to describe the result.
        assert repository.get_by_slug.await_count == 2

    def test_the_claim_is_taken_before_anything_is_fetched(self):
        """The claim is what makes "once" true rather than merely likely."""

        artist = an_artist(sync_status=None)
        repository = a_repository(artist)
        sync = a_sync_service()

        with patch("app.routes.artists.artist_service",
                   a_service(a_profile())), \
                patch("app.routes.artists.artist_repository", repository), \
                patch("app.routes.artists.synchronization_service", sync):
            client.get("/artists/tim-bernardes")

        repository.claim_initialization.assert_awaited_once_with(
            artist.id
        )


class TestAnInitializedArtistIsReadOnly:
    @pytest.mark.parametrize(
        "state",
        ["success", "empty", "initializing"],
    )
    def test_no_state_ever_fetches(self, state):
        artist = an_artist(sync_status=state)
        sync = a_sync_service()
        repository = a_repository(artist)

        with patch("app.routes.artists.artist_service",
                   a_service(a_profile())), \
                patch("app.routes.artists.artist_repository", repository), \
                patch("app.routes.artists.synchronization_service", sync):
            response = client.get("/artists/tim-bernardes")

        assert response.status_code == 200

        sync.synchronize_artist.assert_not_awaited()

        # Not even a claim attempt: an initialized artist is not up for grabs.
        repository.claim_initialization.assert_not_awaited()

        # And only one read, because nothing was fetched to re-read after.
        assert repository.get_by_slug.await_count == 1

    def test_the_response_carries_no_sync_block(self):
        """A read that did not sync should not claim one happened.

        `sync` is absent rather than present-and-empty, so a caller can tell "no
        fetch was attempted" from "a fetch was attempted and found nothing".
        """

        artist = an_artist(sync_status="success")

        with patch("app.routes.artists.artist_service",
                   a_service(a_profile())), \
                patch("app.routes.artists.artist_repository",
                      a_repository(artist)), \
                patch("app.routes.artists.synchronization_service",
                      a_sync_service()):
            body = client.get("/artists/tim-bernardes").json()

        assert "sync" not in body or body["sync"] is None

    def test_a_repeated_read_never_fetches(self):
        """Stated as an observation rather than inferred from one read.

        The bug this whole distinction exists to prevent is cumulative: one read
        that fetches is a small thing, five hundred reads is a catalogue-wide
        scrape nobody asked for.
        """

        artist = an_artist(sync_status="success")
        sync = a_sync_service()

        with patch("app.routes.artists.artist_service",
                   a_service(a_profile())), \
                patch("app.routes.artists.artist_repository",
                      a_repository(artist)), \
                patch("app.routes.artists.synchronization_service", sync):
            for _ in range(25):
                client.get("/artists/tim-bernardes")

        sync.synchronize_artist.assert_not_awaited()


class TestTwoPeopleOpeningAtOnce:
    def test_only_one_of_them_fetches(self):
        """A cold artist opened twice in the same instant must cost one fetch.

        Without a compare-and-set both requests decide nobody has claimed the
        artist and both spend a full gigography scrape to produce the same rows.
        The loser of the race does nothing at all.
        """

        artist = an_artist(sync_status=None)
        sync = a_sync_service()

        # Nobody holds the claim - somebody else got there first.
        repository = a_repository(artist, claimable=False)

        with patch("app.routes.artists.artist_service",
                   a_service(a_profile())), \
                patch("app.routes.artists.artist_repository", repository), \
                patch("app.routes.artists.synchronization_service", sync):
            body = client.get("/artists/tim-bernardes").json()

        assert sync.synchronize_artist.assert_not_awaited() is None

        assert body["sync"]["attempted"] is False
        assert body["sync"]["reason"] == "already being initialized"

    def test_a_refused_request_is_not_a_refused_page(self):
        """The reader still gets the artist.

        Somebody else's fetch is not this reader's problem, and a 409 here would
        turn a race into a visible error for someone who did nothing wrong.
        """

        artist = an_artist(sync_status=None)

        with patch("app.routes.artists.artist_service",
                   a_service(a_profile())), \
                patch("app.routes.artists.artist_repository",
                      a_repository(artist, claimable=False)), \
                patch("app.routes.artists.synchronization_service",
                      a_sync_service()):
            response = client.get("/artists/tim-bernardes")

        assert response.status_code == 200
        assert response.json()["name"] == "Tim Bernardes"


class TestWhenTheFetchFails:
    def test_the_page_is_still_served(self):
        """The artist exists. That is a fact the fetch does not change.

        Returning an error here would mean a provider outage took every pending
        artist's page down with it.
        """

        artist = an_artist(sync_status=None)

        sync = MagicMock()
        sync.synchronize_artist = AsyncMock(
            side_effect=RuntimeError("Songkick API error: 503")
        )

        with patch("app.routes.artists.artist_service",
                   a_service(a_profile())), \
                patch("app.routes.artists.artist_repository",
                      a_repository(artist)), \
                patch("app.routes.artists.synchronization_service", sync):
            response = client.get("/artists/tim-bernardes")

        assert response.status_code == 200

        body = response.json()

        assert body["slug"] == "tim-bernardes"
        assert body["sync"]["succeeded"] is False
        assert "503" in body["sync"]["reason"]

    def test_the_reader_is_not_told_the_artist_is_broken(self):
        """No error-shaped copy on the page.

        The state is reported in `sync`, for a caller that has somewhere to put
        it. The profile itself is a page about a musician, and a visitor who
        opened it during a provider blip should see a musician.
        """

        artist = an_artist(sync_status=None)

        sync = MagicMock()
        sync.synchronize_artist = AsyncMock(
            side_effect=RuntimeError("Songkick API error: 503")
        )

        with patch("app.routes.artists.artist_service",
                   a_service(a_profile()), \
              ) as service, \
                patch("app.routes.artists.artist_repository",
                      a_repository(artist)), \
                patch("app.routes.artists.synchronization_service", sync):
            response = client.get("/artists/tim-bernardes")

        profile = service.get_artist_profile.await_args

        assert profile is not None

        body = response.json()

        for key in body:
            assert "error" not in key

    def test_an_errored_artist_may_be_retried_by_the_next_open(self):
        """A failed fetch is retryable by a person, and by nobody else.

        Two paths may initialize an artist: an explicit import and a first open.
        The scheduler is not one of them. So if an open did not retry a failed
        fetch, the only remaining retry would be one that is not permitted - and
        an artist whose provider was briefly unreachable would stay permanently
        uninitialized, which is a worse outcome than re-asking.

        The cost is bounded and self-limiting: one fetch per page load, only while
        the fetch is actually failing, and the first success makes the artist
        initialized, after which it is read-only like any other.
        """

        artist = an_artist(sync_status="error")
        repository = a_repository(artist)
        sync = a_sync_service()

        with patch("app.routes.artists.artist_service",
                   a_service(a_profile())), \
                patch("app.routes.artists.artist_repository", repository), \
                patch("app.routes.artists.synchronization_service", sync):
            client.get("/artists/tim-bernardes")

        sync.synchronize_artist.assert_awaited_once()

    def test_an_errored_artist_stops_retrying_once_it_succeeds(self):
        """The other half of the same rule.

        A retry that never stops is not a retry, it is the original bug wearing a
        smaller hat. So what stops it is that the successful fetch moves the
        artist to `initialized` - and the route re-reads the artist, so the second
        open sees the new state rather than the one it started from.
        """

        artist = an_artist(sync_status="error")
        repository = a_repository(artist)

        sync = a_sync_service()

        # The real service writes the outcome on the artist as its last act.
        # Reproduced here so the double behaves like the thing it stands in for,
        # rather than being frozen in the state the test started it in.
        async def succeed_and_record(target, **kwargs):
            target.sync_status = "success"
            target.last_synced_at = datetime.now(UTC)

            return {
                "synced": True,
                "result": {
                    "events_received": 212,
                    "events_created": 212,
                    "events_existing": 0,
                },
            }

        sync.synchronize_artist = AsyncMock(
            side_effect=succeed_and_record
        )

        with patch("app.routes.artists.artist_service",
                   a_service(a_profile())), \
                patch("app.routes.artists.artist_repository", repository), \
                patch("app.routes.artists.synchronization_service", sync):
            first = client.get("/artists/tim-bernardes").json()
            second = client.get("/artists/tim-bernardes").json()

        assert first["sync"]["succeeded"] is True

        assert sync.synchronize_artist.await_count == 1

        # And the second open is an ordinary read with nothing to report.
        assert "sync" not in second or second["sync"] is None


class TestAnErroredArtistIsNotRetriedForever:
    """The failure mode of "retry on every open", stated as a test.

    An identity that is permanently broken - an act deleted from the provider, an
    id that has been reassigned - takes one failed outbound request and one write
    per page view, forever. That is a page load scraping a provider, which is the
    thing this whole model exists to stop, reached from the other direction.

    So a failure backs off for the TTL. A pending artist does not, because it has
    never been asked and there is nothing to wait for.
    """

    def _attempted(self, minutes_ago: int = 1):
        return an_artist(
            sync_status="error",
            updated_at=datetime.now(UTC) - timedelta(
                minutes=minutes_ago
            ),
        )

    def test_an_errored_artist_is_not_retried_within_the_cooldown(self):
        artist = self._attempted(minutes_ago=1)

        sync = a_sync_service()

        with patch("app.routes.artists.artist_service",
                   a_service(a_profile())), \
                patch("app.routes.artists.artist_repository",
                      a_repository(artist)), \
                patch("app.routes.artists.synchronization_service", sync):
            body = client.get("/artists/tim-bernardes").json()

        sync.synchronize_artist.assert_not_awaited()

        # Reported honestly: nothing was attempted, and that is not a success.
        assert body["sync"] is None or body["sync"]["attempted"] is False

    def test_a_repeated_view_does_not_accumulate_failures(self):
        """Ten views, one attempt - not ten."""

        artist = self._attempted(minutes_ago=1)
        sync = a_sync_service()

        with patch("app.routes.artists.artist_service",
                   a_service(a_profile())), \
                patch("app.routes.artists.artist_repository",
                      a_repository(artist)), \
                patch("app.routes.artists.synchronization_service", sync):
            for _ in range(10):
                client.get("/artists/tim-bernardes")

        sync.synchronize_artist.assert_not_awaited()

    def test_the_retry_happens_once_the_cooldown_has_passed(self):
        artist = self._attempted(minutes_ago=60 * 48)

        sync = a_sync_service()

        with patch("app.routes.artists.artist_service",
                   a_service(a_profile())), \
                patch("app.routes.artists.artist_repository",
                      a_repository(artist)), \
                patch("app.routes.artists.synchronization_service", sync):
            client.get("/artists/tim-bernardes")

        sync.synchronize_artist.assert_awaited_once()

    def test_a_pending_artist_is_never_cooled_down(self):
        """Otherwise the first fetch is delayed and the reader gets nothing.

        A pending artist's `updated_at` was written when the festival announced
        them, which may be any time at all. Treating that as "an attempt just
        failed" would leave a freshly announced artist unopenable.
        """

        artist = an_artist(sync_status=None)

        artist.updated_at = datetime.now(UTC)

        sync = a_sync_service()

        with patch("app.routes.artists.artist_service",
                   a_service(a_profile())), \
                patch("app.routes.artists.artist_repository",
                      a_repository(artist)), \
                patch("app.routes.artists.synchronization_service", sync):
            client.get("/artists/tim-bernardes")

        sync.synchronize_artist.assert_awaited_once()

    def test_an_artist_with_no_timestamp_at_all_is_retried(self):
        """Nothing recorded means nothing to wait for."""

        artist = an_artist(sync_status="error", updated_at=None)

        sync = a_sync_service()

        with patch("app.routes.artists.artist_service",
                   a_service(a_profile())), \
                patch("app.routes.artists.artist_repository",
                      a_repository(artist)), \
                patch("app.routes.artists.synchronization_service", sync):
            client.get("/artists/tim-bernardes")

        sync.synchronize_artist.assert_awaited_once()


class TestAnUnknownArtist:
    def test_it_is_a_404(self):
        reads = a_service(a_profile())

        repository = MagicMock()
        repository.get_by_slug = AsyncMock(return_value=None)

        with patch("app.routes.artists.artist_service", reads), \
                patch("app.routes.artists.artist_repository", repository), \
                patch("app.routes.artists.synchronization_service",
                      a_sync_service()):
            response = client.get("/artists/nobody-here")

        assert response.status_code == 404

        reads.get_artist_profile.assert_not_awaited()
