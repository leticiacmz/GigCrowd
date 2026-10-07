"""One scheduled pass over the artists whose data has gone stale.

This is the job that `GET /artists/{slug}` used to be. Synchronization used to
happen because somebody opened a page, which meant the catalogue depended on who
happened to look, a single request could spend an unbounded number of outbound
calls inside Songkick, and a cold artist stayed empty until someone was curious
enough to visit it. Moving the work here makes all three properties explicit:
bounded per run, on a clock, and visible in a log line nobody has to reproduce a
browser session to read.

Like `enrichment_job`, this module decides *what one run does* and nothing about
*when* - the scheduler owns that. It also deliberately owns no synchronization
logic. Selection is `ArtistRepository.find_needing_sync`, the decision to skip a
fresh artist is `SynchronizationService.needs_sync`, and the work itself is
`SynchronizationService.synchronize_artist`. There is exactly one implementation
of synchronizing an artist and this job only calls it.

Two properties are load-bearing:

1. Bounded. `batch_size` caps how many artists one run may visit, so a tick can
   never turn into a full-catalog scrape.
2. Failure tolerant. One unreachable artist page must not abandon the rest of the
   batch, and must not leave that artist looking successfully synced. The
   underlying service already records the failure on the artist; this job counts
   it, logs it, and moves on.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional

from app.core.logger import get_logger

logger = get_logger("artist_sync_job")


# The provider an artist is synchronised from. Songkick is canonical for events;
# Spotify is enrichment only, so it is not a candidate here.
DEFAULT_PROVIDER = "songkick"


@dataclass
class ArtistSyncJobConfig:
    """How one scheduled artist-sync run should behave."""

    batch_size: int = 10

    delay_seconds: float = 1.5

    provider: str = DEFAULT_PROVIDER

    force: bool = False

    def describe(self) -> dict[str, Any]:
        """A log-safe summary of the run's settings.

        The shape of the work only. No credentials, no source URLs, no page
        content belong in a scheduler log line.
        """

        return {
            "batch_size": self.batch_size,
            "delay_seconds": self.delay_seconds,
            "provider": self.provider,
            "force": self.force,
        }


@dataclass
class ArtistSyncJobResult:
    """What one run did, split by outcome.

    `selected` and `attempted` are kept apart because "nothing was due" and
    "everything I tried failed" are different days for whoever reads the log, and
    a single success counter cannot tell them apart.
    """

    selected: int = 0
    attempted: int = 0
    synced: int = 0
    cache_valid: int = 0
    empty: int = 0
    failed: int = 0
    failures: list[dict] = field(default_factory=list)
    events_received: int = 0
    events_created: int = 0
    events_existing: int = 0
    duration_seconds: float = 0.0
    config: dict[str, Any] = field(default_factory=dict)

    @property
    def is_quiet(self) -> bool:
        """Whether the run found nothing worth doing.

        A scheduler that logs the same "nothing to do" every interval is noise, so
        a caller can stay quiet when a run changed nothing.
        """

        return self.attempted == 0 and self.selected == 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "selected": self.selected,
            "attempted": self.attempted,
            "synced": self.synced,
            "cache_valid": self.cache_valid,
            "empty": self.empty,
            "failed": self.failed,
            "failures": self.failures[:20],
            "events_received": self.events_received,
            "events_created": self.events_created,
            "events_existing": self.events_existing,
            "duration_seconds": round(self.duration_seconds, 2),
            "config": self.config,
        }

    def summary(self) -> str:
        return (
            f"selected={self.selected} "
            f"attempted={self.attempted} "
            f"synced={self.synced} "
            f"cache_valid={self.cache_valid} "
            f"empty={self.empty} "
            f"failed={self.failed}"
        )


async def run_artist_sync_once(
    service,
    config: Optional[ArtistSyncJobConfig] = None,
    *,
    artist_repository=None,
) -> ArtistSyncJobResult:
    """Select a bounded batch of stale artists and synchronize it.

    `service` is a `SynchronizationService`, which is also what supplies the
    staleness boundary, so the query and the per-artist guard are guaranteed to
    agree. `artist_repository` is passed separately only so a caller that already
    holds one - the application's wiring, or a test - can reuse it instead of
    opening a second handle on the same collection.

    Failure handling is deliberate at two levels. Per artist, an exception is
    counted, logged and survived: `synchronize_artist` has already marked that
    artist as errored and left `last_synced_at` alone, so the next run will
    naturally retry it and no failure is mistaken for success. For the run as a
    whole, a failure to even select is recorded and returns, because there is
    nothing to walk.
    """

    config = config or ArtistSyncJobConfig()

    result = ArtistSyncJobResult(
        config=config.describe()
    )

    loop = asyncio.get_event_loop()
    started = loop.time()

    repository = (
        artist_repository
        if artist_repository is not None
        else service.artist_repository
    )

    # ------------------------------------------------------------------
    # Select
    # ------------------------------------------------------------------

    try:
        artists = await repository.find_needing_sync(
            service.stale_before(),
            limit=config.batch_size,
        )

    except Exception as exc:
        result.duration_seconds = loop.time() - started

        logger.error(
            f"[ARTIST SYNC JOB] could not select artists: "
            f"{type(exc).__name__}: {exc}"
        )

        result.failures.append({
            "stage": "select",
            "error": f"{type(exc).__name__}: {exc}"[:200],
        })

        return result

    result.selected = len(artists)

    if not artists:
        result.duration_seconds = loop.time() - started

        logger.info(
            "[ARTIST SYNC JOB] every artist is within the TTL; "
            "nothing to synchronize"
        )

        return result

    logger.info(
        f"[ARTIST SYNC JOB] selected {result.selected} artist(s) "
        f"{config.describe()}"
    )

    # ------------------------------------------------------------------
    # Walk
    # ------------------------------------------------------------------

    for index, artist in enumerate(artists):

        result.attempted += 1

        try:
            outcome = await service.synchronize_artist(
                artist,
                force=config.force,
                provider=config.provider,
            )

        except Exception as exc:
            # `synchronize_artist` records its own failure on the artist and
            # re-raises, so reaching here is expected and not a bug in the job.
            # The artist stays eligible for the next run, which is what we want.
            result.failed += 1
            result.failures.append({
                "artist_slug": artist.slug,
                "error": f"{type(exc).__name__}: {exc}"[:200],
            })

            logger.warning(
                f"[ARTIST SYNC JOB] {artist.slug} failed: "
                f"{type(exc).__name__}: {exc}"
            )

        else:
            _count_outcome(result, artist, outcome)

        # Paced after the work, and never before the first request, so a run never
        # opens with a pointless wait.
        if index and config.delay_seconds:
            await asyncio.sleep(config.delay_seconds)

    result.duration_seconds = loop.time() - started

    logger.info(
        f"[ARTIST SYNC JOB] {result.summary()} "
        f"in {result.duration_seconds:.1f}s"
    )

    return result


def _count_outcome(
    result: ArtistSyncJobResult,
    artist,
    outcome: dict,
) -> None:
    """Fold one artist's outcome into the run's counters."""

    if not outcome.get("synced"):

        # The service declined because the artist was still fresh. Counted
        # separately from a sync so a selection race is visible rather than
        # looking like work that quietly did nothing.
        result.cache_valid += 1
        return

    result.synced += 1

    detail = outcome.get("result") or {}

    result.events_received += int(
        detail.get("events_received", 0) or 0
    )
    result.events_created += int(
        detail.get("events_created", 0) or 0
    )
    result.events_existing += int(
        detail.get("events_existing", 0) or 0
    )

    if int(detail.get("events_received", 0) or 0) == 0:

        # The service kept the previous sync timestamp, so this artist stays
        # eligible and will be retried. Worth its own counter: an artist that
        # keeps returning nothing is a different problem from one that imported.
        result.empty += 1