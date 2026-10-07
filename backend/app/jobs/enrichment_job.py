"""One scheduled pass over the events that are still incomplete.

This module is the scheduler's only job, and it is deliberately separate from
the scheduler itself. A scheduler decides *when* a run happens; a job decides
*what* one run does. Keeping them apart means the behaviour worth testing - what
gets selected, what happens when one event fails, how the run is paced - can be
exercised without a clock, a background thread or an outbound request.

The job owns no parsing and no database shape of its own. Selection and the
field-level merge both belong to `EventEnrichmentService`, which is where the
rules about what may be overwritten already live. The job's whole
responsibility is to call that service in a bounded, paced, failure-tolerant
loop and then say clearly what happened.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional

from app.core.logger import get_logger
from app.services.event_enrichment_service import (
    ALL_ENRICHABLE_FIELDS,
    DATE_FIELDS,
    LINEUP_FIELDS,
    LOCATION_FIELDS,
)

logger = get_logger("enrichment_job")

# The field selectors a caller may name, mapped to the service's own field
# lists. These are the same four modes `enrich_events.py` offers, deliberately:
# the scheduler is given the vocabulary the enrichment service already defines
# rather than a second set of meanings that would have to be kept in step.
FIELD_MODES: dict[str, list[str]] = {
    "dates": DATE_FIELDS,
    "lineup": LINEUP_FIELDS,
    "location": LOCATION_FIELDS,
    "all": ALL_ENRICHABLE_FIELDS,
}


def resolve_fields(mode: Optional[str]) -> Optional[list[str]]:
    """Turn a configured field mode into the fields it stands for.

    An unset value means "every field the service can enrich", which is the
    service's own default. An unrecognised mode is refused rather than
    silently treated as one of the four, because quietly chasing the wrong
    fields would spend requests on Songkick's servers for nothing.
    """

    if mode is None:
        return None

    key = str(mode).strip().lower()

    if not key or key == "all":
        return ALL_ENRICHABLE_FIELDS

    if key not in FIELD_MODES:
        raise ValueError(
            f"Unknown enrichment fields {mode!r}. Expected one of: "
            + ", ".join(sorted(FIELD_MODES))
        )

    return FIELD_MODES[key]


@dataclass
class EnrichmentJobConfig:
    """How one scheduled run should behave."""

    batch_size: Optional[int] = 25

    delay_seconds: float = 1.5

    fields: Optional[list[str]] = None

    include_dated: bool = False

    dry_run: bool = False

    def describe(self) -> dict[str, Any]:
        """A log-safe summary of the run's settings.

        Only the shape of the work is recorded. No credentials, URLs or page
        content belong in a scheduler log line.
        """

        return {
            "batch_size": self.batch_size,
            "delay_seconds": self.delay_seconds,
            "fields": list(self.fields) if self.fields else "all",
            "include_dated": self.include_dated,
            "dry_run": self.dry_run,
        }


@dataclass
class EnrichmentJobResult:
    """What one run did, split by outcome.

    The counters are the ones a developer needs to tell "there was nothing left
    to do" apart from "everything I tried failed", which a single success figure
    cannot express.
    """

    selected: int = 0
    attempted: int = 0
    updated: int = 0
    unchanged: int = 0
    source_missing: int = 0
    parse_failed: int = 0
    request_failed: int = 0
    write_failed: int = 0
    missing_record: int = 0
    skipped_no_source: int = 0
    failures: list[dict] = field(default_factory=list)
    duration_seconds: float = 0.0
    config: dict[str, Any] = field(default_factory=dict)

    @property
    def is_quiet(self) -> bool:
        """Whether the run found nothing worth doing.

        A scheduler that logs the same "nothing to do" every interval is noise,
        so a caller can stay quiet when a run changes nothing.
        """

        return self.attempted == 0 and self.selected == 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "selected": self.selected,
            "attempted": self.attempted,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "source_missing": self.source_missing,
            "parse_failed": self.parse_failed,
            "request_failed": self.request_failed,
            "write_failed": self.write_failed,
            "missing_record": self.missing_record,
            "failures": self.failures[:20],
            "duration_seconds": round(self.duration_seconds, 2),
            "config": self.config,
        }

    def summary(self) -> str:
        return (
            f"selected={self.selected} "
            f"attempted={self.attempted} "
            f"updated={self.updated} "
            f"unchanged={self.unchanged} "
            f"source_missing={self.source_missing} "
            f"parse_failed={self.parse_failed} "
            f"request_failed={self.request_failed} "
            f"write_failed={self.write_failed}"
        )


async def run_enrichment_once(
    service,
    config: Optional[EnrichmentJobConfig] = None,
) -> EnrichmentJobResult:
    """Select a bounded batch of incomplete events and enrich it.

    Three properties are load-bearing:

    1. Bounded. `batch_size` caps how many events one run may attempt, so a
       scheduled job can never turn into an unbounded crawl.
    2. Resumable and idempotent. Selection asks the enrichment service what is
       missing, and every write is that service's field-level merge, so an event
       that is already complete is simply not selected and an event that fails
       halfway is still a candidate next time.
    3. Failure tolerant. One unreachable page, one unparseable response or one
       rejected write is counted and the run continues. A scheduler job that
       aborts on the first bad row would never get past row one.
    """

    config = config or EnrichmentJobConfig()

    result = EnrichmentJobResult(
        config=config.describe()
    )

    loop = asyncio.get_event_loop()
    started = loop.time()

    # ------------------------------------------------------------------
    # Select
    # ------------------------------------------------------------------

    try:
        plans = await service.plan(
            limit=config.batch_size,
            include_dated=config.include_dated,
            fields=config.fields,
        )

    except Exception as exc:
        # Selection is one query. If it fails there is nothing to walk, and the
        # next scheduled run will try again from a clean state.
        result.duration_seconds = loop.time() - started

        logger.error(
            f"[ENRICH JOB] could not select events: "
            f"{type(exc).__name__}: {exc}"
        )

        result.failures.append({
            "stage": "select",
            "error": f"{type(exc).__name__}: {exc}"[:200],
        })

        return result

    result.selected = len(plans)

    logger.info(
        f"[ENRICH JOB] selected {result.selected} event(s) "
        f"{config.describe()}"
    )

    if not plans:
        result.duration_seconds = loop.time() - started
        return result

    # ------------------------------------------------------------------
    # Walk
    # ------------------------------------------------------------------

    for index, plan in enumerate(plans):

        if not plan.eligible:
            # There is no source to re-read, so this row can never be fixed by
            # enrichment. It is counted separately from a failed request so the
            # difference between "unfixable" and "unlucky" stays visible.
            result.source_missing += 1
            result.skipped_no_source += 1

            continue

        result.attempted += 1

        try:
            outcome = await service.enrich_one(
                plan,
                dry_run=config.dry_run,
            )

        except Exception as exc:
            # `enrich_one` already contains its own failures. Reaching this means
            # something outside the source call blew up - a broken database
            # handle, for instance - and the run still has to continue.
            result.request_failed += 1
            result.failures.append({
                "event_id": plan.event_id,
                "outcome": "job_error",
                "error": f"{type(exc).__name__}: {exc}"[:200],
            })

            logger.warning(
                f"[ENRICH JOB] {plan.event_id} raised "
                f"{type(exc).__name__}: {exc}"
            )

            outcome = {"outcome": "job_error"}

        _count_outcome(result, outcome)

        # Paced after the work, and never before the first request, so a run
        # never opens with a pointless wait.
        if index and config.delay_seconds:
            await asyncio.sleep(config.delay_seconds)

    result.duration_seconds = loop.time() - started

    logger.info(
        f"[ENRICH JOB] {result.summary()} "
        f"in {result.duration_seconds:.1f}s"
    )

    return result


def _count_outcome(
    result: EnrichmentJobResult,
    outcome: dict,
) -> None:
    """Fold one event's outcome into the run's counters."""

    kind = outcome.get("outcome")

    if kind == "updated" or kind == "would_update":
        result.updated += 1
        return

    if kind == "unchanged":
        result.unchanged += 1
        return

    if kind == "skipped":
        result.source_missing += 1
        result.skipped_no_source += 1
        return

    if kind == "parser_failed":
        result.parse_failed += 1
        result.failures.append(outcome)
        return

    if kind == "source_failed":
        result.request_failed += 1
        result.failures.append(outcome)
        return

    if kind == "write_failed":
        result.write_failed += 1
        result.failures.append(outcome)
        return

    if kind == "missing":
        # The row disappeared between selection and the visit. Nothing to do
        # and nothing to retry.
        result.missing_record += 1
        return

    if kind == "job_error":
        return

    result.failures.append({"outcome": str(kind)})
