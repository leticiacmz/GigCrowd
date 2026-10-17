"""Enriching a festival edition's lineup, as work that follows the row.

The catalogue persists a festival event the moment its listing arrives, so
an event page is never held hostage to the lineup being complete - that
rule stands. What a listing states is often only part of the bill, though:
the headliner the artist's gigography mentioned, and nothing else. The full
performers list lives on the event's own page.

This module reads that page as background work *on the event row*, and it
is the one deliberate addition to the "nothing is queued for later"
architecture this project otherwise holds (see `jobs/README.md`). The
difference is worth stating plainly: nothing here replaces the in-run
completion or the extraction-gap report - an event is written, reported and
visible with whatever the run obtained, and the pass then reads the page the
row names and finishes the edition: every performer the page states is
stored, and every stored performer exists as an artist, in the pass that
read it. No part of that waits for a later run.

The rules it holds itself to:

* **The event row exists first and stays usable.** Enrichment only adds: a
  lineup merge keeps every stored entry and appends what the page adds,
  artist slugs join with `$addToSet`, and a date is written only where none
  is stored. Nothing here can blank a field a resync would protect.
* **The state is the queue and the lock.** Each event carries
  `lineup_state`; claiming it is one atomic update, so two processes never
  read the same page for the same event, and an abandoned claim expires by
  itself (the lease is a freshness bound on `lineup_enrichment.updated_at`).
* **A failure costs nothing but the attempt.** Any error leaves the event
  exactly as it was and marks it `failed`; the next claim - or the retry
  button on the festival page - re-runs it.
* **Nothing is invented.** The lineup comes from the event's own page, via
  the same parser the import uses. An artist id resolves locally through the
  same resolver the festival page renders with; an unresolvable id stays an
  unlinked name.

States, and what each one means:

    pending    enqueued, not claimed yet
    active     a worker holds the claim and is reading the page
    partial    the page was read but some artist records could not be
               created; the stored lineup is kept and a retry re-runs it
    complete   the event's own page was read and its lineup is stored,
               with every stored performer held as an artist
    failed     the last attempt errored; retry re-runs it
    empty      the page was read and it names no performer

A legacy row carries no state at all. Read time keeps calling a lineup with
performers `ok` and an empty one `unknown`, exactly as before: the absence
of a state is not evidence of anything, and stamping `complete` on a row
nobody read would be the dishonesty this design exists to avoid.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Iterable, Optional

from bson import ObjectId
from pymongo import ReturnDocument

from app.core.logger import get_logger
from app.domain.event_schedule import (
    parse_source_datetime,
    valid_interval_end,
)
from app.domain.lineup import LineupEntry
from app.mappers.songkick_event_mapper import SongkickEventMapper
from app.services.lineup_artist_resolver import (
    LineupArtistResolver,
    stored_id_of,
)

logger = get_logger("lineup_enrichment")


# The states an event's `lineup_state` can hold. Documented in the module
# docstring; kept here as the single spelling every writer and reader agrees
# on.
STATE_PENDING = "pending"
STATE_ACTIVE = "active"
STATE_PARTIAL = "partial"
STATE_COMPLETE = "complete"
STATE_FAILED = "failed"
STATE_EMPTY = "empty"

#: A stored state, or its absence (a legacy row that was never enqueued).
#: `None` in the `$in` list is what makes a missing field match, in Mongo
#: and in the test double alike.
CLAIMABLE_STATES = [None, STATE_PENDING, STATE_FAILED, STATE_PARTIAL]


def _object_id(value: Any):
    """The stored `_id` behind an event id, without guessing.

    Ids arrive as strings from routes and scripts; a value that is not an
    ObjectId is returned unchanged rather than raising, so a caller holding
    a non-standard id gets a clean "not found" instead of a crash.
    """

    if isinstance(value, ObjectId):
        return value

    try:
        return ObjectId(str(value))
    except Exception:
        return value


def _identity_of(entry: Any) -> str:
    """The dedup key of one lineup entry, across both storage shapes.

    Stored entries are plain documents; fresh ones are domain objects. Both
    spellings of a Songkick id collapse here (bare digits and `Artist123`),
    and the normalized name is only ever a fallback - never an identifier.
    """

    def read(name: str):
        if isinstance(entry, dict):
            return entry.get(name)
        return getattr(entry, name, None)

    songkick_id = read("songkick_id") or read("songkickId")

    if songkick_id:
        return f"id:{stored_id_of(str(songkick_id))}"

    name = str(read("name") or "").strip()

    return f"name:{' '.join(name.casefold().split())}"


def _entry_document(entry: LineupEntry) -> dict:
    """One fresh lineup entry in the shape the stored lineup already uses.

    `model_dump` is the same serialization `insert_event` applies to the
    domain lineup, so a document written here is indistinguishable from one
    the import wrote - which is what lets the read path and the never-blank
    merge treat them identically.
    """

    return entry.model_dump()


def _is_festival_event(document: dict) -> bool:
    """Whether a stored row is a festival edition, in any stored spelling.

    The same case-insensitive match the frontend applies; the several
    spellings this catalogue has written all mean the edition of a
    festival.
    """

    event_type = document.get("event_type")

    return (
        isinstance(event_type, str)
        and "festival" in event_type.casefold()
    )


class LineupEnrichmentService:
    """Read a festival edition's own page and add what it announces."""

    def __init__(
        self,
        db,
        client_factory=None,
        artist_repository=None,
        lineup_importer=None,
        lease_seconds: int = 600,
        max_attempts: int = 3,
        max_concurrent: int = 2,
    ):
        self.db = db
        self.events = db.events
        self.client_factory = client_factory
        self.artist_repository = artist_repository
        self.lineup_importer = lineup_importer
        self.lease_seconds = int(lease_seconds)
        self.max_attempts = int(max_attempts)
        self._semaphore = asyncio.Semaphore(
            max(1, int(max_concurrent))
        )

    # ============================================================
    # ENQUEUEING
    # ============================================================

    async def enqueue(
        self,
        event_id,
        *,
        force: bool = False,
    ) -> Optional[str]:
        """Mark one festival edition's lineup enrichment as waiting to run.

        Returns the event's state after this call, or `None` when no such
        event exists. Finished work (`complete`, `empty`) and running work
        (`pending`, `active`) are left alone unless `force` says to re-run -
        which is exactly what the retry button on the festival page means,
        and what makes a re-import of the same event idempotent.

        A forced retry also resets the attempt counter: "try again" means
        try again, not "stay exhausted".
        """

        identifier = _object_id(event_id)

        now = datetime.now(UTC)

        stale_before = now - timedelta(
            seconds=self.lease_seconds
        )

        if force:
            # A retry means "run it again", never "steal it from the worker
            # that is reading it right now": a fresh `active` claim is left
            # alone, and only one whose lease expired (a dead worker) joins
            # the queue. Everything else - finished, exhausted, queued -
            # is re-enqueued, with its attempt counter reset below.
            guard = {
                "$or": [
                    {"lineup_state": {"$ne": STATE_ACTIVE}},
                    {
                        "lineup_enrichment.updated_at": {
                            "$lte": stale_before
                        }
                    },
                ]
            }
        else:

            guard = {
                "lineup_state": {
                    "$nin": [
                        STATE_PENDING,
                        STATE_ACTIVE,
                        STATE_COMPLETE,
                        STATE_EMPTY,
                    ]
                }
            }

        update: dict = {
            "$set": {
                "lineup_state": STATE_PENDING,
                "lineup_state_updated_at": now,
            }
        }

        if force:

            update["$set"]["lineup_enrichment.attempts"] = 0

        result = await self.events.update_one(
            {"_id": identifier, **guard},
            update,
        )

        if result.matched_count:
            return STATE_PENDING

        existing = await self.events.find_one(
            {"_id": identifier},
            {"lineup_state": 1},
        )

        return (
            (existing or {}).get("lineup_state")
            if existing
            else None
        )

    async def enqueue_events(
        self,
        songkick_ids: Iterable[str],
        *,
        force: bool = False,
    ) -> list[str]:
        """Enqueue every festival edition in one run of an import.

        Takes the Songkick event ids the import already holds, resolves them
        to stored rows in one query, and enqueues only what really is a
        festival edition - a concert's lineup is its one artist, already
        associated, and has nothing to enrich.

        Returns the stored ids of the events this call queued.
        """

        ids = {
            str(value).strip()
            for value in songkick_ids
            if value and str(value).strip()
        }

        if not ids:
            return []

        documents = await self.events.find(
            {"external_ids.songkick": {"$in": sorted(ids)}},
            {"external_ids.songkick": 1, "event_type": 1},
        ).to_list(length=None)

        queued: list[str] = []

        for document in documents:

            if not _is_festival_event(document):
                continue

            state = await self.enqueue(
                document["_id"],
                force=force,
            )

            if state:
                queued.append(str(document["_id"]))

        return queued

    # ============================================================
    # RUNNING
    # ============================================================

    def schedule(self, event_ids: Iterable[str]) -> asyncio.Task:
        """Start a background pass over these events.

        The caller - an import that just wrote the rows - carries on
        without waiting: the response is not held hostage to a page read.
        The task itself swallows nothing silently; every failure lands on
        the event as a `failed` state with its reason.
        """

        identifiers = [str(value) for value in event_ids]

        return asyncio.create_task(
            self.process_batch(identifiers),
            name="lineup-enrichment",
        )

    async def process_batch(self, event_ids: Iterable[str]) -> dict:
        """Enrich a list of events, one at a time, within one process.

        Sequential on purpose: the semaphore bounds how many page reads are
        in flight across this process, and the claim on each event bounds
        them across processes. A result is skipped when the event is not
        claimable - already finished, already running elsewhere, or out of
        attempts - which is the dedup working, not a failure.

        One summary line closes the batch: the drain is background work that
        used to run for tens of minutes without a trace, and its size and
        length are the two facts a reader needs to tell a normal pass from a
        queue that has become a scraper.
        """

        started_at = time.perf_counter()

        outcomes: dict[str, str] = {}

        for event_id in event_ids:

            outcomes[str(event_id)] = await self.process(event_id)

        counts: dict[str, int] = {}

        for state in outcomes.values():

            counts[state] = counts.get(state, 0) + 1

        by_state = ", ".join(
            f"{state}={count}"
            for state, count in sorted(counts.items())
        )

        logger.info(
            "[LINEUP ENRICHMENT] batch finished: "
            f"{len(outcomes)} edition(s) in "
            f"{time.perf_counter() - started_at:.2f}s "
            f"| {by_state}"
        )

        return outcomes

    async def process(self, event_id) -> str:
        """Run one edition's enrichment to its next state.

        Never raises: an error is a state (`failed`), not an exception, so a
        background task cannot die quietly with the event stuck in `active`.
        """

        identifier = _object_id(event_id)
        owner = uuid.uuid4().hex

        document = await self._claim(identifier, owner)

        if document is None:

            current = await self.events.find_one(
                {"_id": identifier},
                {"lineup_state": 1},
            )

            return (
                (current or {}).get("lineup_state")
                or "unknown"
            )

        try:

            async with self._semaphore:
                return await self._run(identifier, owner, document)

        except Exception as exc:

            logger.warning(
                "[LINEUP ENRICHMENT] attempt for event "
                f"{identifier} errored: {type(exc).__name__}: {exc}"
            )

            return await self._finish(
                identifier,
                owner,
                STATE_FAILED,
                error=f"{type(exc).__name__}: {exc}",
            )

    # ============================================================
    # CLAIMING
    # ============================================================

    async def _claim(
        self,
        identifier,
        owner: str,
    ) -> Optional[dict]:
        """Take the event's enrichment claim, or report it as taken.

        Claimable: never run (`pending`, or no state at all), failed or
        partial and within its attempt budget, or `active` whose lease has
        expired - a worker died mid-read. The read before the atomic claim
        only computes the attempt number; the claim itself decides, so two
        workers never both believe they hold the event.
        """

        current = await self.events.find_one(
            {"_id": identifier},
            {
                "lineup_state": 1,
                "lineup_enrichment.attempts": 1,
                "lineup_enrichment.updated_at": 1,
            },
        )

        if current is None:
            return None

        attempts = (
            (current.get("lineup_enrichment") or {}).get(
                "attempts"
            )
            or 0
        )

        state = current.get("lineup_state")

        if (
            state == STATE_FAILED
            and attempts >= self.max_attempts
        ):

            logger.info(
                "[LINEUP ENRICHMENT] event {identifier} has "
                f"exhausted {self.max_attempts} attempts; a "
                "forced retry resets the counter"
            )

            return None

        now = datetime.now(UTC)

        stale_before = now - timedelta(
            seconds=self.lease_seconds
        )

        return await self.events.find_one_and_update(
            {
                "_id": identifier,
                "$or": [
                    {"lineup_state": {"$in": CLAIMABLE_STATES}},
                    {
                        "lineup_state": STATE_ACTIVE,
                        "lineup_enrichment.updated_at": {
                            "$lte": stale_before
                        },
                    },
                ],
            },
            {
                "$set": {
                    "lineup_state": STATE_ACTIVE,
                    "lineup_state_updated_at": now,
                    "lineup_enrichment.owner": owner,
                    "lineup_enrichment.updated_at": now,
                    "lineup_enrichment.attempts": attempts + 1,
                    "lineup_enrichment.error": None,
                }
            },
            return_document=ReturnDocument.AFTER,
        )

    # ============================================================
    # THE PASS ITSELF
    # ============================================================

    async def _run(
        self,
        identifier,
        owner: str,
        document: dict,
    ) -> str:
        """One claimed pass: read the page, add what it states, finish."""

        address = self._address_of(document)

        if not address:

            return await self._finish(
                identifier,
                owner,
                STATE_FAILED,
                error=(
                    "no source address to read: neither "
                    "source.url nor festival.url states one"
                ),
            )

        if self.client_factory is None:

            return await self._finish(
                identifier,
                owner,
                STATE_FAILED,
                error="no provider client configured for enrichment",
            )

        payload = {
            "id": (
                (document.get("external_ids") or {}).get(
                    "songkick"
                )
            ),
            "name": document.get("title"),
            "url": address,
        }

        client = self.client_factory()

        enriched = await client.enrich_event_details(payload)

        if (
            not isinstance(enriched, dict)
            or enriched is payload
        ):

            return await self._finish(
                identifier,
                owner,
                STATE_FAILED,
                error="no usable answer from the event's page",
            )

        if enriched.get("date_status") == "parser_failed":

            return await self._finish(
                identifier,
                owner,
                STATE_FAILED,
                error=(
                    "no readable structured data on the event's page"
                ),
            )

        # --------------------------------------------------
        # The lineup the page states
        # --------------------------------------------------
        #
        # Parsed by the same parser the import uses - one parser for one
        # shape of markup - and merged into the stored lineup without ever
        # removing an entry: a page that answers with less than an earlier
        # read stored must not be able to shrink the bill.

        parsed = SongkickEventMapper._parse_lineup(
            enriched.get("lineup")
            or enriched.get("performers")
        )

        stored = [
            entry
            for entry in (document.get("lineup") or [])
            if isinstance(entry, dict)
        ]

        merged = list(stored)

        known = {
            _identity_of(entry)
            for entry in stored
        }

        fresh: list[LineupEntry] = []

        for entry in parsed:

            identity = _identity_of(entry)

            if identity in known:
                continue

            known.add(identity)
            fresh.append(entry)
            merged.append(_entry_document(entry))

        # The stored order is the source's; new names join at the end in
        # the order the page stated them, and the whole list is numbered
        # the way `dedupe_lineup` numbers one it just parsed.
        for position, entry in enumerate(merged):
            entry["order"] = position

        # --------------------------------------------------
        # The artists behind the names
        # --------------------------------------------------
        #
        # Every performer the stored bill names must exist as an artist by the
        # end of this pass. The candidates are the whole merged bill, not just
        # the names this read added: the importer skips the ids that already
        # resolve, creates the ones that do not, and never creates one twice -
        # so a bill whose artist records were lost to an earlier cap, a crash
        # or an older code path is completed on this read instead of staying
        # short forever.
        #
        # There is no per-pass cap here, and its absence is deliberate. A cap
        # deferred the tail to "the next pass" - and the next pass found those
        # names already stored, saw nothing fresh, and created nothing, so the
        # tail was never created at all. Creating a stub is one local write
        # with no fetch behind it; the run that reads the bill finishes it.

        importer_failed = 0

        if merged and self.lineup_importer is not None:

            try:

                report = await (
                    self.lineup_importer
                    .ensure_for_entries(merged)
                )

                importer_failed = report.failed

            except Exception as exc:

                # The lineup itself is already going to be stored; one bad
                # artist must not cost the bill it was announced on.
                logger.warning(
                    "[LINEUP ENRICHMENT] artist stubs for event "
                    f"{identifier} could not be created: {exc}"
                )

                importer_failed = 1

        added_slugs: list[str] = []

        if fresh and self.artist_repository is not None:

            resolver = LineupArtistResolver(
                self.artist_repository
            )

            resolved = await resolver.resolve(
                stored_id_of(str(entry.songkick_id))
                for entry in fresh
                if entry.songkick_id
            )

            added_slugs = sorted(set(resolved.values()))

        # --------------------------------------------------
        # Dates the page states, where the row has none
        # --------------------------------------------------
        #
        # A festival listing arrives undated by design - the gigography
        # states the appearance, not the calendar - and the row's own page
        # is where the date lives. Written only where nothing is stored, so
        # a date an earlier read obtained is never replaced.

        dates: dict = {}

        if not document.get("starts_at") and not document.get(
            "ends_at"
        ):

            starts_at = parse_source_datetime(
                enriched.get("start_date")
                or enriched.get("date")
            )

            ends_at = valid_interval_end(
                starts_at,
                parse_source_datetime(
                    enriched.get("end_date")
                ),
            )

            if starts_at or ends_at:

                dates = {
                    "starts_at": starts_at,
                    "ends_at": ends_at,
                    "date_status": "source",
                    "date_source_checked_at": datetime.now(UTC),
                }

            elif enriched.get("date_status") == "unavailable":

                # The page was read and it states no date. Recording that
                # is the honest answer, and it stops the row from looking
                # like nobody ever checked.
                dates = {
                    "date_status": "unavailable",
                    "date_source_checked_at": datetime.now(UTC),
                }

        # --------------------------------------------------
        # The state this pass earned
        # --------------------------------------------------

        if not merged:

            state = STATE_EMPTY

        elif importer_failed:

            state = STATE_PARTIAL

        else:

            state = STATE_COMPLETE

        update: dict = {
            "lineup": merged,
            "lineup_state": state,
            "lineup_state_updated_at": datetime.now(UTC),
            "lineup_enrichment.finished_at": datetime.now(UTC),
            "lineup_enrichment.error": None,
        }

        if added_slugs:
            update["artist_slugs_add"] = added_slugs

        if dates:
            update.update(dates)

        return await self._write(
            identifier,
            owner,
            update,
            state,
        )

    # ============================================================
    # FINISHING
    # ============================================================

    async def _finish(
        self,
        identifier,
        owner: str,
        state: str,
        *,
        error: Optional[str] = None,
    ) -> str:
        """Land a terminal (or retryable) state, refusing a lost claim."""

        return await self._write(
            identifier,
            owner,
            {
                "lineup_state": state,
                "lineup_state_updated_at": datetime.now(UTC),
                "lineup_enrichment.finished_at": datetime.now(
                    UTC
                ),
                "lineup_enrichment.error": error,
            },
            state,
        )

    async def _write(
        self,
        identifier,
        owner: str,
        values: dict,
        state: str,
    ) -> str:
        """Write one pass's outcome, but only while still the owner.

        The owner token travels with the write: if a takeover happened while
        this worker was reading - its lease expired and another worker
        claimed the event - the write finds a different owner and refuses,
        so a slow, stale pass can never overwrite a newer result.
        """

        update: dict = {
            "$set": {
                key: value
                for key, value in values.items()
                if key != "artist_slugs_add"
            }
        }

        added = values.get("artist_slugs_add")

        if added:

            # `$addToSet` beside the `$set`: the slugs this pass resolved
            # join what is stored, never replacing anything.
            update["$addToSet"] = {
                "artist_slugs": {"$each": added}
            }

        result = await self.events.update_one(
            {
                "_id": identifier,
                "lineup_enrichment.owner": owner,
            },
            update,
        )

        if not result.matched_count:

            logger.warning(
                "[LINEUP ENRICHMENT] claim on event "
                f"{identifier} was lost mid-pass; the newer "
                "owner's result stands"
            )

            return "lost"

        logger.info(
            f"[LINEUP ENRICHMENT] event {identifier} -> {state}"
        )

        return state

    # ============================================================
    # HELPERS
    # ============================================================

    @staticmethod
    def _address_of(document: dict) -> Optional[str]:
        """The event's own page address, or the festival block's.

        The same precedence the rest of the catalogue reads addresses in:
        the event's own source address first, the festival block's beside
        it. Only an address a browser can open counts, so a relative or
        malformed value is skipped rather than requested.
        """

        from app.domain.festival import http_url_or_none

        source = document.get("source")

        candidates = []

        if isinstance(source, dict):
            candidates.append(source.get("url"))

        festival = document.get("festival")

        if isinstance(festival, dict):
            candidates.append(festival.get("url"))

        for candidate in candidates:

            address = http_url_or_none(candidate)

            if address:
                return address

        return None


def service_for_database(db):
    """The enrichment service for one database handle, from configuration.

    The single place the collaborators are wired - the provider client that
    reads event pages, the artist repository and importer behind the stubs,
    and the bounds that keep a pass small - so the import path and the retry
    endpoint cannot drift apart in what they consider a valid run.

    Returns `None` when the feature is disabled: a caller that receives a
    service knows enrichment will actually run, and a caller that receives
    `None` simply has no collaborator, exactly as before the feature
    existed. Lazy imports keep importing this module free of the provider
    stack it may never use.
    """

    from app.config import settings

    if not settings.LINEUP_ENRICHMENT_ENABLED:
        return None

    from app.providers.songkick.client import SongkickClient
    from app.repositories.artist_repository import (
        ArtistRepository,
    )
    from app.services.lineup_artist_importer import (
        LineupArtistImporter,
    )

    artist_repository = ArtistRepository(db)

    return LineupEnrichmentService(
        db=db,
        client_factory=lambda: SongkickClient(),
        artist_repository=artist_repository,
        lineup_importer=(
            LineupArtistImporter(artist_repository)
            if settings.LINEUP_ARTIST_IMPORT_ENABLED
            else None
        ),
        lease_seconds=(
            settings.LINEUP_ENRICHMENT_LEASE_SECONDS
        ),
        max_attempts=settings.LINEUP_ENRICHMENT_MAX_ATTEMPTS,
        max_concurrent=(
            settings.LINEUP_ENRICHMENT_MAX_CONCURRENT
        ),
    )
