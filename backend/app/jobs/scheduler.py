"""The background scheduler.

The project has exactly one scheduler and this is it. It owns a clock and
nothing else: it decides when an enrichment pass runs, hands the pass to
`run_enrichment_once`, and reports what happened. Every decision about *what*
to enrich belongs to `EventEnrichmentService`, and every decision about *what
one run does* belongs to `enrichment_job`.

This file used to be an accidental copy of `main.py` that imported a
`create_scheduler` which had never existed, so importing it raised and nothing
ever did. It was replaced rather than left in place, because the job above
genuinely needs somewhere to be scheduled from and a second, competing scheduler
would be worse than none.

Two behaviours are deliberate and should not be "simplified" away:

1. It is off unless configuration turns it on. Starting the API locally must
   never begin making outbound requests to Songkick.
2. Runs never overlap. A run that overruns its interval is skipped rather than
   stacked behind itself, because two passes over the same rows would double
   the request rate for no benefit.
"""
from __future__ import annotations

import asyncio
from typing import Any, Callable, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.logger import get_logger
from app.jobs.artist_sync_job import (
    ArtistSyncJobConfig,
    ArtistSyncJobResult,
    run_artist_sync_once,
)
from app.jobs.enrichment_job import (
    EnrichmentJobConfig,
    EnrichmentJobResult,
    resolve_fields,
    run_enrichment_once,
)
from app.services.event_enrichment_service import EventEnrichmentService

logger = get_logger("scheduler")

# The name APScheduler knows this job by.
JOB_ID = "songkick_enrichment"


class EnrichmentScheduler:
    """Runs event enrichment on an interval, when it has been asked to.

    `service_factory` is how the scheduler gets hold of the enrichment service.
    It is a callable rather than a service so the wiring can be decided by the
    application - and so a test can hand in a service whose source client never
    touches the network.
    """

    def __init__(
        self,
        *,
        enabled: bool = False,
        interval_minutes: int = 360,
        batch_size: Optional[int] = 25,
        delay_seconds: float = 1.5,
        fields: Optional[str] = "dates",
        include_dated: bool = False,
        run_on_startup: bool = False,
        service_factory: Optional[Callable[[], Any]] = None,
        job_runner: Optional[Callable] = None,
        lifecycle_enabled: bool = False,
        lifecycle_batch_size: int = 50,
        lifecycle_lookback_hours: int = 48,
        lifecycle_runner: Optional[Callable] = None,
        artist_sync_enabled: bool = False,
        artist_sync_batch_size: int = 10,
        artist_sync_delay_seconds: float = 1.5,
        artist_sync_interval_minutes: int = 360,
        artist_sync_run_on_startup: bool = False,
        artist_sync_provider: str = "songkick",
        synchronization_factory: Optional[Callable[[], Any]] = None,
        artist_sync_runner: Optional[Callable] = None,
    ):
        self.enabled = bool(enabled)
        self.interval_minutes = interval_minutes
        self.include_dated = include_dated
        self.run_on_startup = run_on_startup
        self.service_factory = service_factory
        self.job_runner = job_runner or run_enrichment_once

        # A second job, on the same schedule and in the same tick, rather than a
        # second scheduler: one clock, one switch, one status endpoint.
        #
        # It is off unless configuration turns it on. A lifecycle pass notifies
        # real people, so on a development database it must never surprise
        # anybody by working through a backlog the moment a process boots.
        self.lifecycle_enabled = bool(lifecycle_enabled)
        self.lifecycle_batch_size = int(lifecycle_batch_size)
        self.lifecycle_lookback_hours = int(lifecycle_lookback_hours)
        self.lifecycle_runner = lifecycle_runner

        # A third job, on the same clock, rather than a second scheduler. Artist
        # synchronization is here because it used to happen inside a GET request;
        # giving it its own scheduler would have been a second thing to remember to
        # start, stop and reason about.
        #
        # Off unless configuration turns it on, for the reason the others are off: a
        # pass visits Songkick without anybody asking, so booting the API locally
        # must never start one.
        self.artist_sync_enabled = bool(artist_sync_enabled)
        self.artist_sync_interval_minutes = artist_sync_interval_minutes
        self.artist_sync_run_on_startup = bool(
            artist_sync_run_on_startup
        )
        self.synchronization_factory = synchronization_factory
        self.artist_sync_runner = (
            artist_sync_runner or run_artist_sync_once
        )

        self.artist_sync_config = ArtistSyncJobConfig(
            batch_size=artist_sync_batch_size,
            delay_seconds=artist_sync_delay_seconds,
            provider=artist_sync_provider,
        )

        # An unrecognised field mode is a configuration mistake. It is resolved
        # once here rather than on every run, so a typo is reported at startup
        # instead of silently degrading every run that follows.
        self.job_config = EnrichmentJobConfig(
            batch_size=batch_size,
            delay_seconds=delay_seconds,
            fields=resolve_fields(fields),
            include_dated=include_dated,
            dry_run=False,
        )

        self._scheduler: Optional[AsyncIOScheduler] = None

        # Guards against a second run starting while one is still walking. The
        # APScheduler job itself also refuses to overlap, but this flag is what
        # protects a manual `run_now` from colliding with a scheduled run.
        self._running = False

        self.last_result: Optional[EnrichmentJobResult] = None

        self.last_lifecycle_result: Optional[dict] = None

        self.last_artist_sync_result: Optional[
            ArtistSyncJobResult
        ] = None

    # ============================================================
    # LIFECYCLE
    # ============================================================

    def start(self) -> bool:
        """Begin scheduling. Returns whether the scheduler is now running.

        Calling this when the scheduler is disabled, or when it is already
        running, is a no-op that returns False. Startup must not be able to
        start two schedulers by accident.
        """

        if not self.enabled:
            logger.info(
                "[SCHEDULER] enrichment scheduler is disabled; "
                "no background work will run"
            )
            return False

        if self._scheduler is not None:
            logger.warning(
                "[SCHEDULER] enrichment scheduler is already running"
            )
            return False

        try:
            scheduler = AsyncIOScheduler(
                event_loop=asyncio.get_running_loop()
            )

            scheduler.add_job(
                self.run,
                trigger=IntervalTrigger(
                    minutes=max(1, self.interval_minutes)
                ),
                id=JOB_ID,
                name="Songkick event enrichment",
                # One pass at a time. If a pass overruns the interval the next
                # one is dropped, never queued behind it.
                max_instances=1,
                coalesce=True,
                # A pass missed while the process was down is not worth
                # replaying on restart; the next tick plans from the current
                # state of the database anyway.
                misfire_grace_time=None,
                replace_existing=True,
            )

            scheduler.start()

        except Exception as exc:
            # A scheduler that cannot start must not take the API down with it.
            # The application is perfectly usable without enrichment.
            logger.error(
                f"[SCHEDULER] could not start the enrichment "
                f"scheduler: {type(exc).__name__}: {exc}"
            )
            return False

        self._scheduler = scheduler

        logger.info(
            f"[SCHEDULER] enrichment scheduler started; "
            f"every {max(1, self.interval_minutes)} minute(s), "
            f"batch={self.job_config.batch_size}, "
            f"delay={self.job_config.delay_seconds}s, "
            f"fields={self.job_config.describe()['fields']}"
        )

        if self.run_on_startup:
            logger.info(
                "[SCHEDULER] running one pass immediately on startup"
            )
            asyncio.create_task(self.run())

        return True

    def shutdown(self, wait: bool = False) -> None:
        """Stop scheduling. Safe to call when never started."""

        scheduler = self._scheduler

        self._scheduler = None

        if scheduler is None:
            return

        try:
            # `wait=False` on purpose: shutdown should not block on an
            # in-flight enrichment pass, which may be waiting on a slow source.
            scheduler.shutdown(wait=wait)

        except Exception as exc:
            logger.warning(
                f"[SCHEDULER] error while shutting down: {exc}"
            )

        else:
            logger.info("[SCHEDULER] enrichment scheduler stopped")

    # ============================================================
    # RUNNING
    # ============================================================

    async def run(self) -> Optional[EnrichmentJobResult]:
        """Run one enrichment pass, if one is not already running."""

        if self._running:
            logger.info(
                "[SCHEDULER] a pass is already running; "
                "skipping this tick"
            )
            return None

        self._running = True

        try:
            service = self._service()

        except Exception as exc:
            self._running = False

            logger.error(
                f"[SCHEDULER] could not build the enrichment service: "
                f"{type(exc).__name__}: {exc}"
            )
            return None

        result: Optional[EnrichmentJobResult] = None

        try:
            result = await self.job_runner(
                service,
                self.job_config,
            )

        except Exception as exc:
            # The runner contains its own per-event failures. Reaching here
            # means the run itself broke, and a broken run must not propagate
            # into APScheduler's executor or into an unhandled task warning.
            logger.error(
                f"[SCHEDULER] enrichment pass failed: "
                f"{type(exc).__name__}: {exc}"
            )

        finally:
            # The other passes run whatever happened above. A failed enrichment
            # pass - a dead Songkick request, say - must not silence the prompts
            # that are already overdue for real people, and must not leave
            # artist gigographies stale.
            try:
                await self._run_lifecycle()
            except Exception as exc:  # pragma: no cover - defensive
                logger.error(
                    f"[SCHEDULER] lifecycle pass failed: "
                    f"{type(exc).__name__}: {exc}"
                )

            try:
                await self.run_artist_sync()
            except Exception as exc:  # pragma: no cover - defensive
                logger.error(
                    f"[SCHEDULER] artist sync pass failed: "
                    f"{type(exc).__name__}: {exc}"
                )

            self._running = False

        if result is not None:
            self.last_result = result

        return result

    async def run_artist_sync(
        self,
    ) -> Optional[ArtistSyncJobResult]:
        """One artist-sync pass, if it is switched on.

        Public and callable on its own so a pass can be triggered deliberately -
        from a script, a test or an operator - rather than only waiting for the
        next tick.
        """

        if not self.artist_sync_enabled:
            return None

        try:
            service = self._synchronization_service()

        except Exception as exc:
            logger.error(
                f"[SCHEDULER] could not build the synchronization "
                f"service: {type(exc).__name__}: {exc}"
            )
            return None

        result: Optional[ArtistSyncJobResult] = None

        try:
            result = await self.artist_sync_runner(
                service,
                self.artist_sync_config,
            )

        except Exception as exc:
            # The runner contains its own per-artist failures. Reaching here means
            # the run itself broke, which must not propagate into APScheduler.
            logger.error(
                f"[SCHEDULER] artist sync pass failed: "
                f"{type(exc).__name__}: {exc}"
            )

        if result is not None:
            self.last_artist_sync_result = result

        return result

    def _synchronization_service(self) -> Any:
        """The synchronization service this scheduler drives.

        Built from the application's own services rather than reassembled here, so
        there is one configured `SynchronizationService` in the process and one
        place that decides how it is wired.
        """

        if self.synchronization_factory is not None:
            return self.synchronization_factory()

        from app.routes.artists import (
            synchronization_service as shared_service,
        )

        return shared_service

    async def _run_lifecycle(self) -> None:
        """One lifecycle pass, if it is switched on.

        Separate from enrichment rather than inside it: the two have nothing to
        do with each other beyond sharing a tick, and a failure in one must not
        stop the other.
        """

        if not self.lifecycle_enabled:
            return

        service = self._lifecycle_service()

        runner = self.lifecycle_runner or _default_lifecycle_runner

        result = await runner(
            service,
            self.lifecycle_batch_size,
            self.lifecycle_lookback_hours,
        )

        self.last_lifecycle_result = (
            result.as_dict()
            if hasattr(result, "as_dict")
            else result
        )

    def _lifecycle_service(self) -> Any:
        from app.database.connection import db
        from app.services.event_lifecycle_service import (
            EventLifecycleService,
        )

        return EventLifecycleService(db.get_database())

    def _service(self) -> Any:
        """The enrichment service this scheduler drives."""

        if self.service_factory is not None:
            return self.service_factory()

        from app.database.connection import db
        from app.repositories.event_repository import EventRepository

        return EventEnrichmentService(
            EventRepository(db.get_database())
        )

    # ============================================================
    # REPORTING
    # ============================================================

    def get_status(self) -> dict[str, Any]:
        """What the scheduler is doing, for a human reading a log or health check.

        Only scheduling facts are reported. No credentials, no source URLs and
        no page content, so this is safe to expose on an operational endpoint.
        """

        next_run = None

        if self._scheduler is not None:
            job = self._scheduler.get_job(JOB_ID)

            if job is not None and job.next_run_time:
                next_run = job.next_run_time.isoformat()

        return {
            "enabled": self.enabled,
            "running": self._scheduler is not None,
            "in_progress": self._running,
            "interval_minutes": self.interval_minutes,
            "next_run_at": next_run,
            "config": self.job_config.describe(),
            "lifecycle": {
                "enabled": self.lifecycle_enabled,
                "batch_size": self.lifecycle_batch_size,
                "lookback_hours": self.lifecycle_lookback_hours,
                "last_run": self.last_lifecycle_result,
            },
            "artist_sync": {
                "enabled": self.artist_sync_enabled,
                "interval_minutes": self.artist_sync_interval_minutes,
                "run_on_startup": self.artist_sync_run_on_startup,
                "config": self.artist_sync_config.describe(),
                "last_run": (
                    self.last_artist_sync_result.as_dict()
                    if self.last_artist_sync_result is not None
                    else None
                ),
            },
            "last_run": (
                self.last_result.as_dict()
                if self.last_result is not None
                else None
            ),
        }


async def _default_lifecycle_runner(
    service: Any,
    batch_size: int,
    lookback_hours: int,
) -> Any:
    """One lifecycle pass with the scheduler's own bounds.

    A named function rather than a closure so a test can point the scheduler at
    the same shape without repeating the call.
    """

    return await service.run(
        batch_size=batch_size,
        lookback_hours=lookback_hours,
    )


def create_scheduler(
    service_factory: Optional[Callable[[], Any]] = None,
) -> EnrichmentScheduler:
    """Build the scheduler from application settings.

    Settings are read here rather than at import time so that a test can build a
    scheduler with its own values without touching the environment.
    """

    from app.config import settings

    return EnrichmentScheduler(
        enabled=settings.ENRICHMENT_SCHEDULER_ENABLED,
        interval_minutes=settings.ENRICHMENT_SCHEDULER_INTERVAL_MINUTES,
        batch_size=settings.ENRICHMENT_SCHEDULER_BATCH_SIZE,
        delay_seconds=settings.ENRICHMENT_SCHEDULER_REQUEST_DELAY_SECONDS,
        fields=settings.ENRICHMENT_SCHEDULER_FIELDS,
        include_dated=settings.ENRICHMENT_SCHEDULER_INCLUDE_DATED,
        run_on_startup=settings.ENRICHMENT_SCHEDULER_RUN_ON_STARTUP,
        lifecycle_enabled=settings.EVENT_LIFECYCLE_SCHEDULER_ENABLED,
        lifecycle_batch_size=settings.EVENT_LIFECYCLE_SCHEDULER_BATCH_SIZE,
        lifecycle_lookback_hours=settings.EVENT_LIFECYCLE_SCHEDULER_LOOKBACK_HOURS,
        artist_sync_enabled=settings.ARTIST_SYNC_SCHEDULER_ENABLED,
        artist_sync_batch_size=settings.ARTIST_SYNC_SCHEDULER_BATCH_SIZE,
        artist_sync_delay_seconds=(
            settings.ARTIST_SYNC_SCHEDULER_REQUEST_DELAY_SECONDS
        ),
        artist_sync_interval_minutes=(
            settings.ARTIST_SYNC_SCHEDULER_INTERVAL_MINUTES
        ),
        artist_sync_run_on_startup=(
            settings.ARTIST_SYNC_SCHEDULER_RUN_ON_STARTUP
        ),
        service_factory=service_factory,
    )
