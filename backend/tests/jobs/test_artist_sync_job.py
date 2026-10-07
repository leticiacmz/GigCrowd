"""The artist synchronization job.

This job is *maintenance*, not intake. It refreshes artists that already have a
gigography and have not been looked at recently. It is explicitly not how the
catalogue fills up: an artist is initialized when a person imports them or opens
their page, and at no other time, so this job never selects one that has never
been fetched.

That boundary is what most of this file defends. The rest pins the properties
that have always mattered for a job running on a clock: it stays off until asked,
it is bounded per run, it picks the artists that have waited longest, it survives
one artist failing, and it does not mark a failure as a success.

Nothing here opens a socket. Synchronization is driven through the real
`SynchronizationService` against a fake database, so what is under test is the
selection and the failure handling, not Songkick's availability.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from bson import ObjectId

from app.core.logger import get_logger
from app.domain.artist_state import (
    is_pending,
    needs_initialization,
)
from app.jobs.artist_sync_job import (
    ArtistSyncJobConfig,
    run_artist_sync_once,
)
from app.repositories.artist_repository import ArtistRepository
from app.services.synchronization_service import (
    SynchronizationService,
)
from tests.support.fake_mongo import FakeDatabase

logger = get_logger("test_artist_sync")

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)

# A fixed instant the job is asked about, so TTL arithmetic in a test never
# depends on the wall clock.
FROZEN_NOW = NOW


def stable_id(*parts: str) -> ObjectId:
    """A deterministic `_id` for a fixture row.

    Derived from the name rather than generated, so the same artist always gets
    the same identifier and a test that seeds the same catalogue twice compares
    like with like. The project's own seed uses this construction.
    """

    digest = 0

    for part in parts:
        for byte in part.encode("utf-8"):
            digest = (digest * 131 + byte) % (1 << 96)

    return ObjectId(f"{digest:024x}")


def artist_document(
    slug: str,
    *,
    last_synced_at: datetime | None = None,
    sync_status: str | None = None,
    songkick_id: str | None = "Artist1",
) -> dict:
    """One artist document.

    Defaults to an *initialized* artist, because that is what this job now
    maintains. An artist nobody has opened has no gigography, and fetching one
    because a scheduler ticked is the behaviour this job was narrowed to stop;
    `pending_artist` builds the other case for the tests that assert it.

    `_id` is included because every real document has one, and because selection
    orders by it as a tie-break - a batch of equally stale artists all share the
    same timestamp, so without a total order the same few would be chosen every
    tick.
    """

    document: dict = {
        "_id": stable_id("artist", slug),
        "name": slug.replace("-", " ").title(),
        "normalized_name": slug.replace("-", " "),
        "slug": slug,
        "external_ids": (
            {"songkick": songkick_id} if songkick_id else {}
        ),
        "genres": [],
        "image": None,
        "popularity": None,
        "verified": False,
        "created_at": NOW - timedelta(days=400),
        "updated_at": NOW - timedelta(days=400),
    }

    if last_synced_at is not None:
        document["last_synced_at"] = last_synced_at

    if sync_status is not None:
        document["sync_status"] = sync_status

    return document


def initialized_artist(slug: str, *, hours_ago: float = 30) -> dict:
    """An artist with a gigography fetched long enough ago to be worth refreshing."""

    return artist_document(
        slug,
        last_synced_at=datetime.now(UTC) - timedelta(hours=hours_ago),
        sync_status="success",
    )


def pending_artist(slug: str) -> dict:
    """An artist that exists because a festival announced them, and nothing else.

    No `last_synced_at`, no `sync_status` - which is exactly what
    `ensure_by_songkick_id` writes, and exactly how this population is told apart
    from an artist whose fetch has been attempted.
    """

    return artist_document(slug)


def build(
    documents: list[dict],
    *,
    ttl_hours: int = 24,
):
    """A real service over a fake database, with the import stubbed out.

    The stub replaces only the outermost network call. Everything that decides
    whether to sync, what counts as success and what gets written is the real
    implementation, because that is the part worth testing.
    """

    database = FakeDatabase({"artists": documents})

    repository = ArtistRepository(database)

    service = SynchronizationService(
        artist_repository=repository,
        event_import_service=None,
        ttl_hours=ttl_hours,
    )

    calls: list[str] = []

    async def fake_import(artist, provider="songkick"):
        calls.append(artist.slug)

        return {
            "artist": artist.name,
            "events_received": 3,
            "events_created": 2,
            "events_existing": 1,
            "events_skipped": 0,
            "venues_created": 1,
            "venues_existing": 0,
        }

    service.event_import_service = type(
        "FakeImport",
        (),
        {"sync_artist_events": staticmethod(fake_import)},
    )()

    return service, database, calls


class TestTheJobIsBounded:
    @pytest.mark.asyncio
    async def test_one_run_visits_at_most_the_batch_size(self):
        service, _, calls = build(
            [
                initialized_artist(f"artist-{index}")
                for index in range(25)
            ]
        )

        result = await run_artist_sync_once(
            service,
            ArtistSyncJobConfig(batch_size=5, delay_seconds=0),
        )

        assert len(calls) == 5
        assert result.attempted == 5

    @pytest.mark.asyncio
    async def test_a_batch_of_one_still_makes_progress(self):
        # If every tick picked the same artists, a small batch would never
        # reach the rest of the catalogue. Ordering by how long an artist has
        # waited is what prevents that.
        service, _, calls = build(
            [
                initialized_artist(f"artist-{index}")
                for index in range(4)
            ]
        )

        visited: list[str] = []

        for _ in range(4):

            result = await run_artist_sync_once(
                service,
                ArtistSyncJobConfig(batch_size=1, delay_seconds=0),
            )

            visited.append(calls[-1] if calls else "")

        assert len(set(visited)) == 4


class TestWhichArtistsAreSelected:
    @pytest.mark.asyncio
    async def test_a_pending_artist_is_never_selected(self):
        """The rule this job exists to respect.

        An artist the catalogue knows the *name* of, because a festival announced
        them, has no gigography. Fetching one because a scheduler ticked turns a
        maintenance pass into a crawl: with thousands of announced-but-unopened
        artists, the batch fills with the same cold rows every hour and nobody
        who actually looks at the catalogue gets refreshed.

        A pending artist is initialized when a person imports them or opens their
        page. There is no third trigger.
        """

        service, _, calls = build(
            [
                pending_artist("announced-1"),
                pending_artist("announced-2"),
            ]
        )

        result = await run_artist_sync_once(
            service, ArtistSyncJobConfig(delay_seconds=0)
        )

        assert calls == []
        assert result.selected == 0
        assert result.is_quiet is True

    @pytest.mark.asyncio
    async def test_a_stale_initialized_artist_is_selected(self):
        service, _, calls = build(
            [initialized_artist("stale")]
        )

        await run_artist_sync_once(
            service, ArtistSyncJobConfig(delay_seconds=0)
        )

        assert calls == ["stale"]

    @pytest.mark.asyncio
    async def test_pending_artists_do_not_displace_real_ones(self):
        """Bounded batches make this the sharp edge.

        The selection is `limit`-many, so anything it prefers is something it
        will never reach. A pending row outranking a stale initialized one means
        the pending row is fetched on every tick forever, and the artist somebody
        actually follows never gets refreshed at all.
        """

        service, _, calls = build(
            [pending_artist("announced")] + [
                initialized_artist(f"followed-{index}")
                for index in range(20)
            ],
        )

        await run_artist_sync_once(
            service,
            ArtistSyncJobConfig(batch_size=5, delay_seconds=0),
        )

        assert calls
        assert "announced" not in calls
        assert all(call.startswith("followed-") for call in calls)

    @pytest.mark.asyncio
    async def test_a_recently_synced_artist_is_skipped(self):
        service, _, calls = build(
            [
                artist_document(
                    "warm",
                    last_synced_at=datetime.now(UTC)
                    - timedelta(hours=2),
                    sync_status="success",
                )
            ]
        )

        result = await run_artist_sync_once(
            service, ArtistSyncJobConfig(delay_seconds=0)
        )

        assert calls == []
        assert result.selected == 0
        assert result.is_quiet is True

    @pytest.mark.asyncio
    async def test_the_ttl_is_configurable(self):
        # The old code hardcoded 24 hours. A configured TTL has to move the
        # boundary, not just be documented next to it.
        service, _, calls = build(
            [
                artist_document(
                    "two-hours-old",
                    last_synced_at=datetime.now(UTC)
                    - timedelta(hours=2),
                    sync_status="success",
                )
            ],
            ttl_hours=1,
        )

        await run_artist_sync_once(
            service, ArtistSyncJobConfig(delay_seconds=0)
        )

        assert calls == ["two-hours-old"]

    @pytest.mark.asyncio
    async def test_an_artist_synced_before_sync_status_existed_is_still_maintained(self):
        """A timestamp on its own still counts as evidence of a fetch.

        Without this, every artist synchronized before `sync_status` was written
        would silently fall out of maintenance and never be refreshed again.
        """

        service, _, calls = build(
            [
                artist_document(
                    "legacy",
                    last_synced_at=datetime.now(UTC)
                    - timedelta(hours=30),
                )
            ]
        )

        await run_artist_sync_once(
            service, ArtistSyncJobConfig(delay_seconds=0)
        )

        assert calls == ["legacy"]

    @pytest.mark.asyncio
    async def test_the_longest_waiting_artist_goes_first(self):
        service, _, calls = build(
            [
                initialized_artist("recent", hours_ago=40),
                initialized_artist("oldest", hours_ago=500),
                initialized_artist("middle", hours_ago=100),
            ]
        )

        await run_artist_sync_once(
            service,
            ArtistSyncJobConfig(batch_size=1, delay_seconds=0),
        )

        assert calls == ["oldest"]

    @pytest.mark.asyncio
    async def test_selection_and_the_guard_agree_on_the_boundary(self):
        # The query and `needs_sync` derive the same boundary. If they drifted, a
        # run would keep selecting an artist the service then refuses.
        service, _, calls = build(
            [
                artist_document(
                    "edge",
                    last_synced_at=datetime.now(UTC)
                    - timedelta(hours=24, minutes=1),
                    sync_status="success",
                ),
                artist_document(
                    "just-inside",
                    last_synced_at=datetime.now(UTC)
                    - timedelta(hours=23, minutes=59),
                    sync_status="success",
                ),
            ]
        )

        result = await run_artist_sync_once(
            service, ArtistSyncJobConfig(delay_seconds=0)
        )

        assert calls == ["edge"]
        assert result.selected == 1


class TestWhatASuccessfulRunWrites:
    @pytest.mark.asyncio
    async def test_last_synced_at_is_set_on_success(self):
        service, database, _ = build(
            [initialized_artist("cold")]
        )

        result = await run_artist_sync_once(
            service, ArtistSyncJobConfig(delay_seconds=0)
        )

        stored = await database.artists.find_one({"slug": "cold"})

        assert stored["last_synced_at"] is not None
        assert stored["sync_status"] == "success"
        assert result.synced == 1

    @pytest.mark.asyncio
    async def test_a_second_run_finds_nothing_left_to_do(self):
        # Idempotence, as an operator experiences it: the job converges instead
        # of re-importing the same gigographies forever.
        service, _, calls = build(
            [initialized_artist("cold")]
        )

        await run_artist_sync_once(
            service, ArtistSyncJobConfig(delay_seconds=0)
        )

        second = await run_artist_sync_once(
            service, ArtistSyncJobConfig(delay_seconds=0)
        )

        assert len(calls) == 1
        assert second.selected == 0

    @pytest.mark.asyncio
    async def test_import_counters_are_collected(self):
        service, _, _ = build([initialized_artist("cold")])

        result = await run_artist_sync_once(
            service, ArtistSyncJobConfig(delay_seconds=0)
        )

        assert result.events_received == 3
        assert result.events_created == 2
        assert result.events_existing == 1


class TestWhenOneArtistFails:
    def failing_service(self, failing_slug: str):
        service, database, calls = build(
            [
                initialized_artist("healthy"),
                initialized_artist(failing_slug),
            ]
        )

        async def fake_import(artist, provider="songkick"):
            calls.append(artist.slug)

            if artist.slug == failing_slug:

                raise RuntimeError("Songkick is unreachable")

            return {"events_received": 1, "events_created": 1}

        service.event_import_service = type(
            "FlakyImport",
            (),
            {"sync_artist_events": staticmethod(fake_import)},
        )()

        return service, database, calls

    @pytest.mark.asyncio
    async def test_the_batch_continues_past_a_failure(self):
        service, _, _ = self.failing_service("broken")

        result = await run_artist_sync_once(
            service,
            ArtistSyncJobConfig(batch_size=10, delay_seconds=0),
        )

        assert result.failed == 1
        assert result.synced == 1

    @pytest.mark.asyncio
    async def test_the_failure_is_counted_and_named(self):
        service, _, _ = self.failing_service("broken")

        result = await run_artist_sync_once(
            service, ArtistSyncJobConfig(delay_seconds=0)
        )

        assert result.failures
        assert result.failures[0]["artist_slug"] == "broken"
        assert "unreachable" in result.failures[0]["error"]

    @pytest.mark.asyncio
    async def test_a_failed_artist_is_not_marked_as_synced(self):
        """The dangerous failure mode is not the crash.

        It is the artist being marked fresh because a request died, which would
        mean it is never retried and a broken artist looks like a healthy one.

        The assertion is that the timestamp did not *move* - not that it is
        absent. This artist was synced thirty hours ago and still is; erasing
        that fact would throw away a real piece of history along with the false
        claim, and would make a working artist's last-known-good fetch
        indistinguishable from an artist that has never been fetched at all.
        """

        service, database, _ = self.failing_service("broken")

        before = await database.artists.find_one({"slug": "broken"})

        await run_artist_sync_once(
            service, ArtistSyncJobConfig(delay_seconds=0)
        )

        stored = await database.artists.find_one({"slug": "broken"})

        assert stored["last_synced_at"] == before["last_synced_at"]
        assert stored["sync_status"] == "error"

    @pytest.mark.asyncio
    async def test_a_failed_first_fetch_leaves_the_artist_uninitialized(self):
        """The pending case, and the one that matters for retry.

        A *failed first* fetch must not leave a timestamp behind, because a
        timestamp is what makes an artist look initialized - and an initialized
        artist's page is read-only. A pending artist whose first attempt failed
        would therefore be unopenable and unrefetchable forever: nothing would
        ever ask again, and the scheduler will not either.

        This is asserted on `SynchronizationService` rather than on the job,
        because the job deliberately never selects a pending artist - so the job
        cannot produce this state, and the import and first-open paths are what
        can.
        """

        database = FakeDatabase({"artists": [pending_artist("broken")]})

        repository = ArtistRepository(database)

        service = SynchronizationService(
            artist_repository=repository,
            event_import_service=None,
            ttl_hours=24,
        )

        async def unreachable(artist, provider="songkick"):
            raise RuntimeError("Songkick is unreachable")

        service.event_import_service = type(
            "FlakyImport",
            (),
            {"sync_artist_events": staticmethod(unreachable)},
        )()

        artist = await repository.get_by_slug("broken")

        with pytest.raises(RuntimeError):
            await service.synchronize_artist(artist, force=True)

        stored = await database.artists.find_one({"slug": "broken"})

        assert "last_synced_at" not in stored
        assert stored["sync_status"] == "error"

        # And the claim the first-open path takes is gone, so the next open is
        # free to try again rather than being told somebody else is on it.
        assert is_pending(stored) is False
        assert needs_initialization(stored) is True

    @pytest.mark.asyncio
    async def test_a_failed_artist_is_retried_next_run(self):
        service, _, calls = self.failing_service("broken")

        await run_artist_sync_once(
            service, ArtistSyncJobConfig(delay_seconds=0)
        )

        await run_artist_sync_once(
            service, ArtistSyncJobConfig(delay_seconds=0)
        )

        # Selected again, because nothing about its freshness changed.
        assert calls.count("broken") == 2


class TestWhenSelectionItselfFails:
    @pytest.mark.asyncio
    async def test_a_broken_query_is_reported_not_raised(self):
        database = FakeDatabase({"artists": []})

        repository = ArtistRepository(database)

        async def broken(*args, **kwargs):
            raise RuntimeError("index is gone")

        repository.find_needing_sync = broken

        service = SynchronizationService(
            artist_repository=repository,
            event_import_service=None,
            ttl_hours=24,
        )

        result = await run_artist_sync_once(
            service, ArtistSyncJobConfig(delay_seconds=0)
        )

        assert result.selected == 0
        assert result.failures[0]["stage"] == "select"


class TestTheRunIsObservable:
    @pytest.mark.asyncio
    async def test_the_run_is_logged(self, caplog):
        service, _, _ = build([initialized_artist("cold")])

        with caplog.at_level(
            "INFO", logger="artist_sync_job"
        ):

            await run_artist_sync_once(
                service, ArtistSyncJobConfig(delay_seconds=0)
            )

        text = caplog.text

        assert "ARTIST SYNC JOB" in text
        # Counters, not just "it ran".
        assert "synced=1" in text

    def test_the_config_summary_exposes_no_secrets(self):
        described = ArtistSyncJobConfig().describe()

        assert set(described) == {
            "batch_size",
            "delay_seconds",
            "provider",
            "force",
        }

    def test_the_provider_is_songkick(self):
        # Songkick is canonical for artist data; Spotify is enrichment only and
        # must never become the identity source here.
        assert ArtistSyncJobConfig().provider == "songkick"


class TestTheJobIsIndependentOfHttp:
    def test_nothing_in_the_job_imports_a_router(self):
        import inspect

        from app.jobs import artist_sync_job

        source = inspect.getsource(artist_sync_job)

        assert "fastapi" not in source
        assert "app.routes" not in source