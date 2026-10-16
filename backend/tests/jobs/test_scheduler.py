"""The scheduler: two passes, and nothing else.

A tick may perform exactly two things - refresh the artist catalogue, and
advance the event lifecycle - and this file is where that narrowness is pinned.

The pass that used to come back for incomplete events is not disabled and not
merely unconfigured: it is absent from the module. A disabled pass would still
be one `create_scheduler` away from running again, and a reader of the status
endpoint could not tell the difference. Extraction reports a gap where it finds
it, in the run that finds it; the scheduler is never the thing that comes back
for it later.

What an operator can still do by hand lives in `app.scripts` and is covered
there. Nothing in this file opens a socket, so the suite never depends on
Songkick being reachable.
"""
from __future__ import annotations

import asyncio

import pytest

from app.jobs.scheduler import (
    ARTIST_SYNC_JOB_ID,
    JOB_ID,
    BackgroundScheduler,
)



class TestTheSchedulerIsOffUnlessAsked:
    """The development-safety rule."""

    @pytest.mark.asyncio
    async def test_a_disabled_scheduler_does_not_start(self):
        calls: list[int] = []

        async def runner(*_):
            calls.append(1)
            return None

        scheduler = BackgroundScheduler(
            enabled=False,
            artist_sync_enabled=True,
            artist_sync_runner=runner,
        )

        started = scheduler.start()

        assert started is False
        assert scheduler.get_status()["running"] is False

        # No timer was registered, so nothing can fire on its own however long
        # the process runs. This is the development-safety guarantee: starting
        # the API locally must not begin outbound requests.
        assert scheduler.get_status()["next_run_at"] is None

        await asyncio.sleep(0.02)

        assert calls == []

        scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_a_disabled_scheduler_can_still_be_run_by_hand(self):
        """Disabling turns off the timer, not the ability to do the work.

        An operator asking for one pass explicitly is not the same as the
        process deciding to make requests on its own, and a deliberate trigger
        is what a runbook and a test both rely on.
        """

        calls: list[int] = []

        async def runner(*_):
            calls.append(1)
            return None

        scheduler = BackgroundScheduler(
            enabled=False,
            artist_sync_enabled=True,
            artist_sync_runner=runner,
        )

        await scheduler.run()

        assert calls == [1]

        scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_a_disabled_scheduler_reports_itself_as_off(self):
        scheduler = BackgroundScheduler(enabled=False)

        status = scheduler.get_status()

        assert status["enabled"] is False
        assert status["running"] is False
        assert status["next_run_at"] is None

    @pytest.mark.asyncio
    async def test_an_enabled_scheduler_starts(self):
        scheduler = BackgroundScheduler(
            enabled=True,
            interval_minutes=60,
        )

        try:
            assert scheduler.start() is True

            status = scheduler.get_status()

            assert status["running"] is True
            assert status["next_run_at"] is not None
            assert status["interval_minutes"] == 60

        finally:
            scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_starting_twice_does_not_start_a_second_scheduler(self):
        scheduler = BackgroundScheduler(enabled=True)

        try:
            assert scheduler.start() is True
            assert scheduler.start() is False

        finally:
            scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_shutting_down_before_starting_is_safe(self):
        scheduler = BackgroundScheduler(enabled=True)

        # Startup can fail after the scheduler exists; shutdown must not then
        # raise on the way out.
        scheduler.shutdown()
        scheduler.shutdown()


class TestWhatATickIsAllowedToDo:
    """The scheduler refreshes catalogues. It does not come back for gaps."""

    @pytest.mark.asyncio
    async def test_a_tick_refreshes_catalogues_and_runs_the_lifecycle(self):
        ran: list[str] = []

        async def catalogue(*_):
            ran.append("catalogue")

        async def lifecycle(*_):
            ran.append("lifecycle")

        scheduler = BackgroundScheduler(
            enabled=True,
            artist_sync_enabled=True,
            artist_sync_runner=catalogue,
            lifecycle_enabled=True,
            lifecycle_runner=lifecycle,
        )

        await scheduler.run()

        assert ran == ["catalogue", "lifecycle"]

    @pytest.mark.asyncio
    async def test_a_tick_with_everything_switched_off_touches_nothing(self):
        """There is no third switch and no default pass to fall back on.

        The only way a tick does anything is configuration saying so, which is
        what makes "the scheduler fixes short events later" untrue rather than
        merely unlikely.
        """

        scheduler = BackgroundScheduler(enabled=True)

        assert await scheduler.run() is None
        assert scheduler.get_status()["artist_sync"]["last_run"] is None
        assert scheduler.get_status()["lifecycle"]["last_run"] is None

    def test_the_scheduler_has_no_recovery_pass_to_schedule(self):
        """Not disabled - gone.

        A disabled pass would still be one `create_scheduler` away from running
        again, and a reader of the status endpoint would have no way to tell
        the difference. The source is where the difference is visible.
        """

        import inspect

        from app.jobs import scheduler as module

        source = inspect.getsource(module)

        for symbol in (
            "EventEnrichmentService",
            "run_enrichment_once",
            "EnrichmentJobConfig",
            "resolve_fields",
            "enrichment_job",
        ):

            assert symbol not in source, symbol

    @pytest.mark.asyncio
    async def test_one_pass_failing_does_not_silence_the_other(self):
        ran: list[str] = []

        async def broken_sync(*_):
            raise RuntimeError("artist sync failed")

        async def lifecycle(*_):
            ran.append("lifecycle")

        scheduler = BackgroundScheduler(
            enabled=True,
            artist_sync_enabled=True,
            artist_sync_runner=broken_sync,
            lifecycle_enabled=True,
            lifecycle_runner=lifecycle,
        )

        await scheduler.run()

        assert ran == ["lifecycle"]

    @pytest.mark.asyncio
    async def test_a_broken_pass_does_not_propagate(self):
        """A scheduler must never raise into its own executor."""

        async def runner(*_):
            raise RuntimeError("the job is broken")

        scheduler = BackgroundScheduler(
            enabled=True,
            artist_sync_enabled=True,
            artist_sync_runner=runner,
        )

        try:
            assert await scheduler.run() is None

        finally:
            scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_passes_do_not_overlap(self):
        """A pass that overruns must not be joined by a second one."""

        started = 0
        finished = 0

        async def slow_runner(*_):
            nonlocal started, finished

            started += 1

            await asyncio.sleep(0.05)

            finished += 1

        scheduler = BackgroundScheduler(
            enabled=True,
            artist_sync_enabled=True,
            artist_sync_runner=slow_runner,
        )

        try:
            first = asyncio.create_task(scheduler.run())

            # Arrives while the first pass is still walking.
            await asyncio.sleep(0.01)

            second = await scheduler.run()

            await first

            assert second is None
            assert started == 1
            assert finished == 1

        finally:
            scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_the_status_reports_the_last_pass_without_secrets(self):
        class Result:

            @staticmethod
            def as_dict():
                return {"synced": 3, "discovered": 1}

        async def runner(*_):
            return Result()

        scheduler = BackgroundScheduler(
            enabled=True,
            artist_sync_enabled=True,
            artist_sync_runner=runner,
        )

        await scheduler.run()

        status = scheduler.get_status()

        assert status["artist_sync"]["last_run"] == {
            "synced": 3,
            "discovered": 1,
        }

        # The reported payload must not carry a source URL or any credential.
        rendered = repr(status)

        assert "songkick.com" not in rendered
        assert "password" not in rendered.lower()

    @pytest.mark.asyncio
    async def test_a_startup_pass_runs_once_and_then_waits(self):
        calls: list[int] = []

        async def runner(*_):
            calls.append(1)
            return None

        scheduler = BackgroundScheduler(
            enabled=True,
            interval_minutes=60,
            artist_sync_enabled=True,
            artist_sync_run_on_startup=True,
            artist_sync_runner=runner,
        )

        try:
            scheduler.start()

            # The startup pass is scheduled on the loop, so give it a turn.
            for _ in range(20):
                await asyncio.sleep(0)

                if calls:
                    break

            assert len(calls) == 1

            # The interval is an hour, so nothing else should have fired.
            await asyncio.sleep(0.01)

            assert len(calls) == 1

        finally:
            scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_a_startup_pass_never_runs_the_lifecycle(self):
        """Booting the process must not start notifying people.

        The lifecycle pass works through a backlog of real, finished shows for
        real accounts. Scheduling it on boot would mean a development database
        starts sending prompts the moment an API starts, which is the surprise
        the off-by-default rule exists to prevent.
        """

        ran: list[str] = []

        async def catalogue(*_):
            ran.append("catalogue")

        async def lifecycle(*_):
            ran.append("lifecycle")

        scheduler = BackgroundScheduler(
            enabled=True,
            artist_sync_enabled=True,
            artist_sync_run_on_startup=True,
            artist_sync_runner=catalogue,
            lifecycle_enabled=True,
            lifecycle_runner=lifecycle,
        )

        try:
            scheduler.start()

            for _ in range(20):
                await asyncio.sleep(0)

                if ran:
                    break

            await asyncio.sleep(0.01)

            assert ran == ["catalogue"]

        finally:
            scheduler.shutdown()


class TestThePassesHaveTheirOwnClocks:
    """The artist interval is a working setting, not a printed number.

    The refresh used to run on the lifecycle tick while its own configured
    interval was merely reported. These tests pin the fix: two jobs, each
    on its own interval, each calling only its own pass.
    """

    @pytest.mark.asyncio
    async def test_the_registered_jobs_carry_their_own_intervals(self):
        scheduler = BackgroundScheduler(
            enabled=True,
            interval_minutes=60,
            artist_sync_enabled=True,
            artist_sync_interval_minutes=90,
        )

        try:
            assert scheduler.start() is True

            lifecycle_job = scheduler._scheduler.get_job(JOB_ID)
            artist_job = scheduler._scheduler.get_job(
                ARTIST_SYNC_JOB_ID
            )

            assert lifecycle_job is not None
            assert artist_job is not None
            assert (
                lifecycle_job.trigger.interval.total_seconds()
                == 60 * 60
            )
            assert (
                artist_job.trigger.interval.total_seconds()
                == 90 * 60
            )

        finally:
            scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_each_job_runs_only_its_own_pass(self):
        ran: list[str] = []

        async def catalogue(*_):
            ran.append("catalogue")

        async def lifecycle(*_):
            ran.append("lifecycle")

        scheduler = BackgroundScheduler(
            enabled=True,
            artist_sync_enabled=True,
            artist_sync_runner=catalogue,
            synchronization_factory=lambda: object(),
            lifecycle_enabled=True,
            lifecycle_runner=lifecycle,
        )

        try:
            assert scheduler.start() is True

            lifecycle_job = scheduler._scheduler.get_job(JOB_ID)
            artist_job = scheduler._scheduler.get_job(
                ARTIST_SYNC_JOB_ID
            )

            # Fired the way APScheduler fires them. One call must produce
            # exactly one entry: if either job still called `run()`, both
            # passes would appear twice.
            await lifecycle_job.func()
            await artist_job.func()

            assert ran == ["lifecycle", "catalogue"]

        finally:
            scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_an_off_artist_pass_has_no_timer_at_all(self):
        # "Off" must be visible as the absence of a next run, not as a next
        # run that will do nothing.
        scheduler = BackgroundScheduler(
            enabled=True,
            artist_sync_enabled=False,
        )

        try:
            assert scheduler.start() is True

            assert (
                scheduler._scheduler.get_job(ARTIST_SYNC_JOB_ID)
                is None
            )

        finally:
            scheduler.shutdown()

    def test_the_default_artist_interval_is_one_day(self):
        from app.config import Settings

        # A catalogue refresh visits Songkick on its own initiative; a day
        # between passes is the explicit intent of the setting, and the
        # scheduler constructor agrees with the field default.
        assert (
            Settings.model_fields[
                "ARTIST_SYNC_SCHEDULER_INTERVAL_MINUTES"
            ].default
            == 1440
        )
        assert (
            BackgroundScheduler().artist_sync_interval_minutes
            == 1440
        )


class TestTheApplicationWiresItUp:
    """The scheduler has to be real in the running app, not just in a test."""

    def test_the_application_builds_one_scheduler_from_settings(self):
        from app.main import app, scheduler

        assert scheduler is not None
        assert isinstance(scheduler, BackgroundScheduler)

        # Exposed on the health check so it can be confirmed on in production
        # and off everywhere else.
        paths = {
            getattr(route, "path", None)
            for route in app.routes
        }

        assert "/health" in paths

    def test_the_lifespan_starts_and_stops_the_scheduler(self):
        """The scheduler is only real if the application actually drives it."""

        import inspect

        from app.main import lifespan

        source = inspect.getsource(lifespan)

        assert "scheduler.start()" in source
        assert "scheduler.shutdown()" in source

    def test_the_scheduler_is_off_by_default(self):
        from app.config import Settings

        # Settings defaults are the development-safety guarantee, so they are
        # asserted directly rather than through the environment.
        defaults = Settings.model_fields

        assert defaults["SCHEDULER_ENABLED"].default is False
        assert (
            defaults["ARTIST_SYNC_SCHEDULER_ENABLED"].default is False
        )
        assert (
            defaults["EVENT_LIFECYCLE_SCHEDULER_ENABLED"].default is False
        )
        assert (
            defaults["SONGKICK_EVENT_PAGE_READS_PER_SCRAPE"].default >= 0
        )

    def test_every_scheduler_setting_exists_and_has_a_default(self):
        from app.config import Settings

        fields = Settings.model_fields

        for name in (
            "SCHEDULER_ENABLED",
            "SCHEDULER_INTERVAL_MINUTES",
            "ARTIST_SYNC_SCHEDULER_ENABLED",
            "ARTIST_SYNC_SCHEDULER_INTERVAL_MINUTES",
            "ARTIST_SYNC_SCHEDULER_BATCH_SIZE",
            "ARTIST_SYNC_SCHEDULER_REQUEST_DELAY_SECONDS",
            "ARTIST_SYNC_SCHEDULER_RUN_ON_STARTUP",
            "EVENT_LIFECYCLE_SCHEDULER_ENABLED",
            "EVENT_LIFECYCLE_SCHEDULER_BATCH_SIZE",
            "EVENT_LIFECYCLE_SCHEDULER_LOOKBACK_HOURS",
            "SONGKICK_EVENT_PAGE_READS_PER_SCRAPE",
        ):
            assert name in fields, name

    def test_the_recovery_settings_are_gone(self):
        """Configuration that only ever existed to defer work is removed.

        Leaving them behind would mean an operator could still set them, watch
        them do nothing, and conclude that extraction gaps were being handled.
        """

        from app.config import Settings

        fields = Settings.model_fields

        for name in (
            "ENRICHMENT_SCHEDULER_ENABLED",
            "ENRICHMENT_SCHEDULER_INTERVAL_MINUTES",
            "ENRICHMENT_SCHEDULER_BATCH_SIZE",
            "ENRICHMENT_SCHEDULER_REQUEST_DELAY_SECONDS",
            "ENRICHMENT_SCHEDULER_FIELDS",
            "ENRICHMENT_SCHEDULER_INCLUDE_DATED",
            "ENRICHMENT_SCHEDULER_RUN_ON_STARTUP",
            "ENRICH_ON_IMPORT_ENABLED",
            "ENRICH_ON_IMPORT_FIELDS",
            "ENRICH_ON_IMPORT_MAX_EVENTS",
            "ENRICH_ON_IMPORT_DELAY_SECONDS",
        ):
            assert name not in fields, name
