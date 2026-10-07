"""Artist synchronization on the real scheduler.

It shares one clock, one switch and one status endpoint with the enrichment and
lifecycle passes, and it earns its place there because that is where the work it
replaced used to hide - inside a GET request. The properties that matter are that
it is off unless configuration turns it on, that it cannot be started twice, that
it survives a broken pass, and that a pass can be triggered deliberately rather
than only on the next tick.
"""
from __future__ import annotations

from typing import Any, Optional

import pytest

from app.jobs.artist_sync_job import ArtistSyncJobConfig
from app.jobs.scheduler import EnrichmentScheduler


class Boom(RuntimeError):
    pass


async def no_op_enrichment(*_):
    """An enrichment pass that does nothing.

    Async because the scheduler awaits its runner, and a synchronous stub would
    fail in the executor rather than testing anything about artist sync.
    """


async def no_op_artist_sync(*_):
    """An artist-sync pass that does nothing."""


def scheduler_with(
    *,
    job_runner=None,
    artist_sync_enabled: bool = False,
    artist_sync_runner=None,
    synchronization_service: Any = None,
    synchronization_factory=None,
    **kwargs,
) -> EnrichmentScheduler:
    if synchronization_factory is None:

        service = (
            object()
            if synchronization_service is None
            else synchronization_service
        )

        synchronization_factory = lambda: service

    return EnrichmentScheduler(
        enabled=False,
        service_factory=lambda: object(),
        job_runner=job_runner or no_op_enrichment,
        artist_sync_enabled=artist_sync_enabled,
        artist_sync_runner=artist_sync_runner or no_op_artist_sync,
        synchronization_factory=synchronization_factory,
        **kwargs,
    )


class TestArtistSyncIsOffByDefault:
    @pytest.mark.asyncio
    async def test_it_does_not_run_when_it_was_not_switched_on(self):
        calls: list[str] = []

        scheduler = scheduler_with(
            artist_sync_enabled=False,
            artist_sync_runner=lambda *_: calls.append("ran"),
        )

        await scheduler.run()

        assert calls == []

    @pytest.mark.asyncio
    async def test_calling_it_directly_respects_the_switch(self):
        # `run_artist_sync` is public so a pass can be triggered deliberately.
        # Public must not mean "runs whatever the configuration says".
        calls: list[str] = []

        scheduler = scheduler_with(
            artist_sync_enabled=False,
            artist_sync_runner=lambda *_: calls.append("ran"),
        )

        result = await scheduler.run_artist_sync()

        assert result is None
        assert calls == []

    def test_it_is_off_unless_configuration_says_otherwise(self):
        from app.config import settings

        # A local run of the API must never begin scraping on its own. This is the
        # same guarantee the other two passes make, and it is the reason the
        # synchronization that used to happen in a request is safe to move.
        assert settings.ARTIST_SYNC_SCHEDULER_ENABLED is False
        assert settings.ARTIST_SYNC_SCHEDULER_BATCH_SIZE > 0
        assert settings.ARTIST_SYNC_TTL_HOURS > 0


class TestArtistSyncRunsOnATick:
    @pytest.mark.asyncio
    async def test_a_tick_runs_the_pass(self):
        calls: list[str] = []

        scheduler = scheduler_with(
            artist_sync_enabled=True,
            artist_sync_runner=lambda *_: calls.append("ran"),
        )

        await scheduler.run()

        assert calls == ["ran"]

    @pytest.mark.asyncio
    async def test_the_pass_receives_the_configured_bounds(self):
        seen: dict[str, Any] = {}

        async def capture(service, config):

            seen["batch"] = config.batch_size
            seen["delay"] = config.delay_seconds
            seen["provider"] = config.provider

        scheduler = scheduler_with(
            artist_sync_enabled=True,
            artist_sync_batch_size=3,
            artist_sync_delay_seconds=0.25,
            artist_sync_runner=capture,
        )

        await scheduler.run()

        assert seen == {
            "batch": 3,
            "delay": 0.25,
            "provider": "songkick",
        }

    @pytest.mark.asyncio
    async def test_a_broken_pass_does_not_break_the_tick(self):
        # The runner's own per-artist failures are its business. A pass that
        # blows up entirely must still be logged and must not propagate into
        # APScheduler's executor.
        async def broken(*_):

            raise Boom("the pass fell over")

        scheduler = scheduler_with(
            artist_sync_enabled=True,
            artist_sync_runner=broken,
        )

        assert await scheduler.run() is None

    @pytest.mark.asyncio
    async def test_a_failing_service_build_is_survivable(self):
        def broken_factory():

            raise Boom("cannot build the service")

        scheduler = scheduler_with(
            artist_sync_enabled=True,
            synchronization_factory=broken_factory,
        )

        assert await scheduler.run_artist_sync() is None

    @pytest.mark.asyncio
    async def test_one_pass_does_not_stop_the_others(self):
        # The passes are independent. A broken artist sync must not silence the
        # enrichment pass or the lifecycle prompts.
        ran: list[str] = []

        async def broken_sync(*_):

            raise Boom("artist sync failed")

        scheduler = scheduler_with(
            artist_sync_enabled=True,
            artist_sync_runner=broken_sync,
            job_runner=(
                lambda svc, config: ran.append("enrichment")
            ),
            lifecycle_enabled=True,
            lifecycle_runner=lambda *_: ran.append("lifecycle"),
        )

        await scheduler.run()

        assert ran == ["enrichment", "lifecycle"]


class TestArtistSyncResultsAreReported:
    @pytest.mark.asyncio
    async def test_the_last_run_is_kept_for_the_status_endpoint(self):
        class Result:

            @staticmethod
            def as_dict():

                return {"synced": 4}

        async def returns_result(*_):

            return Result()

        scheduler = scheduler_with(
            artist_sync_enabled=True,
            artist_sync_runner=returns_result,
        )

        await scheduler.run()

        status = scheduler.get_status()

        assert status["artist_sync"]["last_run"] == {"synced": 4}

    def test_the_status_endpoint_reports_the_switch_and_the_bounds(self):
        status = scheduler_with(
            artist_sync_enabled=True,
            artist_sync_batch_size=7,
            artist_sync_interval_minutes=90,
        ).get_status()

        section = status["artist_sync"]

        assert section["enabled"] is True
        assert section["interval_minutes"] == 90
        assert section["config"]["batch_size"] == 7

    def test_the_status_endpoint_carries_no_credentials_or_urls(self):
        status = scheduler_with(
            artist_sync_enabled=True,
        ).get_status()

        text = str(status)

        for secret in ("password", "token", "secret", "api_key"):
            assert secret not in text.lower()

        assert "http" not in text


class TestRunsCannotOverlap:
    @pytest.mark.asyncio
    async def test_a_second_tick_is_skipped_while_one_is_running(self):
        # The flag is what protects a deliberately triggered pass from colliding
        # with a scheduled one, which APScheduler alone would not do.
        started = []

        async def slow(*_):

            started.append("begin")

            # Yields control so a second tick can arrive mid-pass.
            import asyncio

            await asyncio.sleep(0.05)

            started.append("end")

        scheduler = scheduler_with(
            artist_sync_enabled=True,
            artist_sync_runner=slow,
            job_runner=(
                lambda svc, config: started.append("enrichment")
            ),
        )

        import asyncio

        await asyncio.gather(
            scheduler.run(), scheduler.run()
        )

        # Two passes were requested; only one ran to completion, and the other
        # returned without starting.
        assert started.count("end") <= 1


class TestTheDefaultConfigurationIsSane:
    def test_the_batch_is_bounded(self):
        config = ArtistSyncJobConfig()

        assert config.batch_size > 0

    def test_the_provider_is_songkick(self):
        assert ArtistSyncJobConfig().provider == "songkick"

    def test_force_is_off(self):
        # A scheduled pass must not bypass the TTL; that is what would turn a tick
        # into a full-catalog scrape.
        assert ArtistSyncJobConfig().force is False


class TestTheSchedulerSharesOneClock:
    def test_artist_sync_does_not_start_its_own_scheduler(self):
        import inspect

        from app.jobs import scheduler as module

        source = inspect.getsource(module)

        # One APScheduler in the project. A second one for artist sync would be a
        # second switch to remember and a second thing that can outlive its
        # shutdown.
        assert source.count("AsyncIOScheduler(") == 1