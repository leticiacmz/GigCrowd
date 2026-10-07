"""The scheduler is the safety net, and it has to behave like one.

A scheduled pass has three jobs that are easy to get subtly wrong:

1. It must find events an import left incomplete - including events that were
   written with no date, no status, a failed parse, or a concrete source nobody
   has ever read.
2. It must not re-fetch events that were genuinely inspected and confirmed to
   have no date. A safety net that re-reads the same answer forever is not a
   safety net; it is a way of generating traffic.
3. Running it twice must change nothing the second time.

These tests drive the real `EventEnrichmentService` against an in-memory fake
collection rather than mocking it, so the selector, the write rules and the
idempotence are all exercised together. No MongoDB, no network.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.jobs.enrichment_job import (
    EnrichmentJobConfig,
    resolve_fields,
    run_enrichment_once,
)
from app.services.event_enrichment_service import (
    DATE_FROM_SOURCE,
    DATE_PARSER_FAILED,
    DATE_UNAVAILABLE,
    EventEnrichmentService,
)


# ==============================================================
# FIXTURES
# ==============================================================


class FakeEvents:
    """Just enough of a Mongo collection to drive the real selection query.

    The selector is a `$or`/`$and` over `starts_at`, `ends_at`, `date_status`
    and `date_source_checked_at`. Reimplementing it would risk testing a
    reimplementation, so the operators that matter are honoured directly and
    anything unrecognised raises rather than quietly matching.
    """

    def __init__(self, documents: list[dict]):
        self.documents = {
            str(document["_id"]): dict(document)
            for document in documents
        }

        self.writes: list[dict] = []

    def find(self, query, projection=None):
        """Synchronous, like a motor cursor factory.

        The service calls `collection.find(...)` and only then awaits `.sort()`.
        Making this a coroutine would hand the service an un-awaited object and
        turn a fake's bug into a confusing failure in production code.

        Dotted projection keys are honoured the way MongoDB honours them,
        because the selector projects `source.url` - a nested key - and a fake
        that only understood top-level keys would silently strip the source URL
        off every document and make every event look un-reachable.
        """

        matched = [
            _project(document, projection)
            for document in self.documents.values()
            if _matches(query, document)
        ]

        ordered = sorted(matched, key=lambda d: str(d["_id"]))

        cursor = MagicMock()
        cursor.sort = MagicMock(return_value=cursor)
        cursor.to_list = AsyncMock(return_value=ordered)

        return cursor

    async def find_one(self, query, projection=None):
        for document in self.documents.values():
            if _matches(query, document):
                return dict(document)

        return None

    async def count_documents(self, query):
        return sum(
            1
            for document in self.documents.values()
            if _matches(query, document)
        )

    async def update_one(self, query, update):
        for document in self.documents.values():
            if _matches(query, document):
                document.update(update.get("$set", {}))

                self.writes.append(dict(update.get("$set", {})))

                return

    def stored(self, event_id: str) -> dict:
        return self.documents[str(event_id)]


def _project(document: dict, projection) -> dict:
    """Apply a MongoDB projection, dotted keys included."""

    if projection is None:
        return dict(document)

    result: dict = {}

    for key, value in document.items():

        if key in projection:
            result[key] = value

            continue

        if key == "_id" and "_id" not in projection:
            result[key] = value

            continue

        for requested in projection:

            if not isinstance(requested, str):
                continue

            head, _, tail = requested.partition(".")

            if head != key or not tail:
                continue

            if not isinstance(value, dict):
                continue

            nested = value.get(tail)

            if nested is None:
                continue

            result.setdefault(key, {})[tail] = nested

    return result


def _matches(query, document: dict | None) -> bool:
    """Whether a document satisfies one query node.

    Supports only the operators the enrichment selector actually uses. Anything
    else raises, so a query that grew a new shape could never be silently
    mis-tested as "matched nothing" or "matched everything".
    """

    if document is None:
        return False

    for key, value in query.items():

        if key == "$or":
            if not any(
                _matches(node, document) for node in value
            ):
                return False

            continue

        if key == "$and":
            if not all(
                _matches(node, document) for node in value
            ):
                return False

            continue

        if key.startswith("$"):
            raise AssertionError(
                f"unsupported top-level operator {key!r}"
            )

        # From here the key is a field name. The value decides what kind of
        # condition this is: a bag of operators, a nested document, or a
        # literal to compare against.
        if isinstance(value, dict) and any(
            str(inner).startswith("$") for inner in value
        ):
            for operator, operand in value.items():

                if operator == "$exists":
                    present = document.get(key) is not None

                    if present != bool(operand):
                        return False

                elif operator == "$ne":
                    # A field that is absent satisfies "is not", which is what
                    # MongoDB does and what the selector relies on when it asks
                    # for events whose status is not `unavailable`.
                    if document.get(key) == operand:
                        return False

                elif operator == "$in":
                    if document.get(key) not in operand:
                        return False

                elif operator == "$nin":
                    if document.get(key) in operand:
                        return False

                elif operator == "$type":
                    continue

                else:
                    raise AssertionError(
                        f"unsupported operator {operator!r} on "
                        f"field {key!r}"
                    )

            continue

        if isinstance(value, dict):
            # A nested document match, e.g. `{"source": {"url": "..."}}`.
            if not _matches(
                value,
                document.get(key) or {},
            ):
                return False

            continue

        if document.get(key) != value:
            return False

    return True


def an_event(event_id: str, **overrides) -> dict:
    document = {
        "_id": event_id,
        "title": f"Event {event_id}",
        "event_type": "FestivalInstance",
        "starts_at": None,
        "ends_at": None,
        "date_status": None,
        "lineup": [],
        "location": None,
        "source": {
            "provider": "songkick",
            "external_id": event_id,
            "url": (
                f"https://www.songkick.com/festivals/{event_id}-x"
            ),
        },
    }

    document.update(overrides)

    return document


def build_service(
    documents: list[dict],
    pages: dict | None = None,
) -> tuple[EventEnrichmentService, FakeEvents, MagicMock]:
    fake_db = MagicMock()

    collection = FakeEvents(documents)

    fake_db.events = collection
    fake_db.venues = MagicMock()
    fake_db.venues.find_one = AsyncMock(return_value=None)

    event_repository = MagicMock()
    event_repository.collection = collection
    event_repository.db = fake_db

    client = MagicMock()

    async def enrich(payload):
        page = (pages or {}).get(
            payload["url"],
            {
                "url": payload["url"],
                "start_date": None,
                "end_date": None,
                "date_status": DATE_UNAVAILABLE,
            },
        )

        return page

    client.enrich_event_details = AsyncMock(side_effect=enrich)

    return (
        EventEnrichmentService(
            event_repository,
            client=client,
        ),
        collection,
        client,
    )


# ==============================================================
# 1. THE SCHEDULER FINDS WHAT AN IMPORT MISSED
# ==============================================================


@pytest.mark.asyncio
async def test_an_event_imported_without_a_date_is_picked_up():
    """The backlog an import deferred must not be invisible to the scheduler.

    This is the exact row shape the importer writes for an undated listing: no
    start, no end, no status. If the scheduler cannot find it, the record stays
    undated forever and nothing reports why.
    """

    service, events, client = build_service(
        [an_event("1", title="Villa Sound 2026")],
        pages={
            "https://www.songkick.com/festivals/1-x": {
                "url": "https://www.songkick.com/festivals/1-x",
                "start_date": "2026-03-25T20:00:00+00:00",
                "end_date": "2026-03-27T23:59:00+00:00",
                "date_status": DATE_FROM_SOURCE,
            }
        },
    )

    result = await run_enrichment_once(
        service,
        EnrichmentJobConfig(
            batch_size=25,
            delay_seconds=0,
            fields=["starts_at", "ends_at"],
        ),
    )

    assert result.selected == 1
    assert result.updated == 1

    written = events.stored("1")

    assert written["starts_at"] is not None
    assert written["ends_at"] is not None
    assert written["date_status"] == DATE_FROM_SOURCE
    assert written["date_source_checked_at"] is not None


@pytest.mark.asyncio
async def test_a_parser_failure_is_retried():
    """`parser_failed` is a bug report about our code, not a verdict.

    The shape that broke the parser is the shape a later parser understands, so
    it must stay a candidate indefinitely rather than settling into the
    catalogue as a permanent answer.
    """

    service, events, client = build_service(
        [
            an_event(
                "1",
                event_type="Concert",
                date_status=DATE_PARSER_FAILED,
            )
        ],
        pages={
            "https://www.songkick.com/festivals/1-x": {
                "url": "https://www.songkick.com/festivals/1-x",
                "start_date": "2026-10-11T19:30:00+00:00",
                "date_status": DATE_FROM_SOURCE,
            }
        },
    )

    await run_enrichment_once(
        service,
        EnrichmentJobConfig(
            delay_seconds=0,
            fields=["starts_at", "ends_at"],
        ),
    )

    assert events.stored("1")["date_status"] == DATE_FROM_SOURCE
    assert events.stored("1")["starts_at"] is not None


@pytest.mark.asyncio
async def test_an_event_never_inspected_is_picked_up_despite_unavailable():
    """A listing's guess is not a finding.

    `unavailable` written by the importer from a listing that merely carried no
    date is exactly the state that stranded fifty recoverable festival dates.
    Without a `date_source_checked_at` beside it, that status proves nothing and
    the event stays a candidate.
    """

    service, events, client = build_service(
        [
            an_event(
                "1",
                date_status=DATE_UNAVAILABLE,
            )
        ],
        pages={
            "https://www.songkick.com/festivals/1-x": {
                "url": "https://www.songkick.com/festivals/1-x",
                "start_date": "2026-03-25T20:00:00+00:00",
                "end_date": "2026-03-27T23:59:00+00:00",
                "date_status": DATE_FROM_SOURCE,
            }
        },
    )

    result = await run_enrichment_once(
        service,
        EnrichmentJobConfig(
            delay_seconds=0,
            fields=["starts_at", "ends_at"],
        ),
    )

    assert result.selected == 1
    assert events.stored("1")["date_status"] == DATE_FROM_SOURCE


@pytest.mark.asyncio
async def test_the_batch_is_bounded():
    """A tick must not scan the whole collection.

    An unbounded pass would spend unbounded time inside Songkick's servers and
    could not be reasoned about as "one tick's worth of work".
    """

    documents = [
        an_event(str(index)) for index in range(1, 51)
    ]

    service, events, client = build_service(documents)

    result = await run_enrichment_once(
        service,
        EnrichmentJobConfig(
            batch_size=10,
            delay_seconds=0,
            fields=["starts_at", "ends_at"],
        ),
    )

    assert result.selected == 10
    assert client.enrich_event_details.await_count == 10


# ==============================================================
# 2. WHAT WAS INSPECTED IS NOT INSPECTED AGAIN
# ==============================================================


@pytest.mark.asyncio
async def test_a_confirmed_undated_event_is_never_refetched():
    """A second visit cannot change the answer.

    Without this the scheduler would pay for the same page on every tick,
    forever, for every genuinely undated event - and would look busy while
    accomplishing nothing.
    """

    service, events, client = build_service(
        [
            an_event(
                "1",
                date_status=DATE_UNAVAILABLE,
                date_source_checked_at="2026-01-01T00:00:00+00:00",
            )
        ]
    )

    result = await run_enrichment_once(
        service,
        EnrichmentJobConfig(
            delay_seconds=0,
            fields=["starts_at", "ends_at"],
        ),
    )

    assert result.selected == 0
    assert client.enrich_event_details.await_count == 0


@pytest.mark.asyncio
async def test_a_dated_event_is_not_re_read_by_a_date_pass():
    """A concert with a start and no end is finished, not half-finished.

    Songkick states no end date for a gig. Treating the absent end as a gap
    would send the scheduler to every concert ever imported on every tick.
    """

    service, events, client = build_service(
        [
            an_event(
                "1",
                event_type="Concert",
                starts_at="2026-10-04T12:00:00+00:00",
                ends_at=None,
                date_status=DATE_FROM_SOURCE,
            )
        ]
    )

    result = await run_enrichment_once(
        service,
        EnrichmentJobConfig(
            delay_seconds=0,
            fields=["starts_at", "ends_at"],
        ),
    )

    assert result.selected == 0
    assert client.enrich_event_details.await_count == 0


# ==============================================================
# 3. REPEATED RUNS ARE IDEMPOTENT
# ==============================================================


@pytest.mark.asyncio
async def test_a_second_run_writes_nothing():
    """Idempotence, measured as bytes written rather than as "no crash".

    A second run over the same backlog must produce no write at all. Anything
    less - a rewritten marker, a refreshed timestamp - would make the scheduler
    permanently busy and would mean the first run had not actually settled.
    """

    service, events, client = build_service(
        [an_event("1")],
        pages={
            "https://www.songkick.com/festivals/1-x": {
                "url": "https://www.songkick.com/festivals/1-x",
                "start_date": "2026-03-25T20:00:00+00:00",
                "end_date": "2026-03-27T23:59:00+00:00",
                "date_status": DATE_FROM_SOURCE,
            }
        },
    )

    config = EnrichmentJobConfig(
        delay_seconds=0,
        fields=["starts_at", "ends_at"],
    )

    first = await run_enrichment_once(service, config)

    assert first.updated == 1

    writes_after_first = len(events.writes)

    second = await run_enrichment_once(service, config)

    assert second.selected == 0
    assert second.attempted == 0
    assert len(events.writes) == writes_after_first

    # And the marker was written once, not refreshed.
    assert (
        events.stored("1")["date_source_checked_at"]
        is not None
    )


@pytest.mark.asyncio
async def test_a_confirmed_absence_is_written_once():
    """Recording that there is no date must also settle.

    The first visit writes the status and the marker. A second visit would
    rewrite the same values, so it must not happen - and if it did, the marker
    would drift forward on every tick and the row would never look settled.
    """

    service, events, client = build_service([an_event("1")])

    config = EnrichmentJobConfig(
        delay_seconds=0,
        fields=["starts_at", "ends_at"],
    )

    await run_enrichment_once(service, config)

    assert events.stored("1")["date_status"] == DATE_UNAVAILABLE

    checked_at = events.stored("1")["date_source_checked_at"]

    assert checked_at is not None

    writes_after_first = len(events.writes)

    second = await run_enrichment_once(service, config)

    assert second.selected == 0
    assert len(events.writes) == writes_after_first
    assert events.stored("1")["date_source_checked_at"] == (
        checked_at
    )


# ==============================================================
# 4. ONE FAILURE DOES NOT END THE PASS
# ==============================================================


@pytest.mark.asyncio
async def test_one_unreachable_page_does_not_end_the_pass():
    """A pass over thousands of events must survive one bad URL."""

    def page_for(payload):
        url = payload["url"]

        if url.endswith("2-x"):
            raise RuntimeError("connection reset")

        return {
            "url": url,
            "start_date": "2026-03-25T20:00:00+00:00",
            "date_status": DATE_FROM_SOURCE,
        }

    fake_db = MagicMock()

    collection = FakeEvents(
        [an_event(str(index)) for index in (1, 2, 3)]
    )

    fake_db.events = collection
    fake_db.venues = MagicMock()
    fake_db.venues.find_one = AsyncMock(return_value=None)

    event_repository = MagicMock()
    event_repository.collection = collection
    event_repository.db = fake_db

    client = MagicMock()
    client.enrich_event_details = AsyncMock(
        side_effect=page_for
    )

    service = EventEnrichmentService(
        event_repository,
        client=client,
    )

    events = collection

    result = await run_enrichment_once(
        service,
        EnrichmentJobConfig(
            delay_seconds=0,
            fields=["starts_at", "ends_at"],
        ),
    )

    assert result.request_failed == 1
    assert result.updated == 2

    # The failure left event 2 recoverable, not stranded as "unavailable".
    assert "date_source_checked_at" not in events.stored("2")


# ==============================================================
# 5. THE FESTIVAL RANGE SURVIVES THE SCHEDULER
# ==============================================================


@pytest.mark.asyncio
async def test_the_scheduler_stores_the_whole_festival_range():
    """25-27 March must not become 25 March.

    A festival is one event with several days, and its end date is real
    information about the edition - it is what the event page and the edition
    list both read. Narrowing it to the opening night would make a three-day
    festival look like a single concert.
    """

    service, events, client = build_service(
        [an_event("1", event_type="FestivalInstance")],
        pages={
            "https://www.songkick.com/festivals/1-x": {
                "url": "https://www.songkick.com/festivals/1-x",
                "start_date": "2026-03-25T20:00:00+00:00",
                "end_date": "2026-03-27T23:59:00+00:00",
                "date_status": DATE_FROM_SOURCE,
            }
        },
    )

    await run_enrichment_once(
        service,
        EnrichmentJobConfig(
            delay_seconds=0,
            fields=["starts_at", "ends_at"],
        ),
    )

    stored = events.stored("1")

    assert stored["starts_at"].isoformat().startswith("2026-03-25")
    assert stored["ends_at"].isoformat().startswith("2026-03-27")


@pytest.mark.asyncio
async def test_an_artist_performance_gets_no_festival_range():
    """A festival's range is never an artist's performance date.

    If an artist plays one night of a three-day festival, the only honest date
    is the one a source states for that performance. Assigning the whole range
    would claim the band plays three nights, and would show up on the artist's
    page as a three-day engagement.
    """

    from app.providers.songkick.client import SongkickClient

    source = {
        "url": "https://www.songkick.com/events/1-x",
        "start_date": "2026-03-25T20:00:00+00:00",
        "end_date": "2026-03-25T23:59:00+00:00",
        "date_status": DATE_FROM_SOURCE,
        # The festival this appearance belongs to, with its own wider range.
        "festival": {
            "series_id": "44001",
            "name": "Villa Sound",
            "start_date": "2026-03-25T20:00:00+00:00",
            "end_date": "2026-03-27T23:59:00+00:00",
        },
    }

    document = {
        "starts_at": None,
        "ends_at": None,
        "date_status": None,
    }

    patch = EventEnrichmentService.apply_patch(document, source)

    # The performance's own single-evening span, not the festival's three days.
    # The festival block on the source carries a wider range on purpose: this is
    # the shape that would narrow or widen a performance if the two were
    # confused.
    assert patch["starts_at"] == "2026-03-25T20:00:00+00:00"
    assert patch["ends_at"] == "2026-03-25T23:59:00+00:00"

    # The festival is recorded as an identity, never as a schedule. A stored
    # `festival` block that carried dates would be a second, competing claim
    # about when this event is.
    if "festival" in patch:
        stored_festival = patch["festival"]

        assert "start_date" not in stored_festival
        assert "end_date" not in stored_festival


@pytest.mark.asyncio
async def test_a_festival_identity_already_stored_is_not_replaced():
    """Identity is not a schedule, and is not re-decided by a date pass.

    A document that already knows which festival it belongs to keeps that
    knowledge. Enrichment fills gaps; it does not second-guess.
    """

    document = {
        "starts_at": None,
        "ends_at": None,
        "date_status": None,
        "festival": {"series_id": "44001", "name": "Villa Sound"},
    }

    patch = EventEnrichmentService.apply_patch(
        document,
        {
            "url": "https://www.songkick.com/events/1-x",
            "start_date": "2026-03-25T20:00:00+00:00",
            "festival": {"series_id": "99999", "name": "Something Else"},
        },
    )

    assert "festival" not in patch


@pytest.mark.asyncio
async def test_a_performance_date_is_not_narrowed_or_widened():
    """The stored date is the source's, verbatim.

    Enrichment parses what the source states. It does not round a date to a
    day, shift it to midnight, or extend it to a festival's length.
    """

    from app.domain.event_schedule import parse_source_datetime

    stored = parse_source_datetime("2026-03-26T21:15:00-03:00")

    assert stored.isoformat() == (
        "2026-03-27T00:15:00+00:00"
    )


# ==============================================================
# 6. CONFIGURATION IS THE SWITCH
# ==============================================================


def test_the_field_modes_are_the_services_own():
    """The scheduler is given the service's vocabulary, not a second one."""

    assert resolve_fields("dates") == ["starts_at", "ends_at"]
    assert resolve_fields("all") == [
        "starts_at",
        "ends_at",
        "lineup",
        "location",
    ]

    # Unset means "every field", which the service states as its own default.
    # Passing `None` through rather than expanding it here keeps the service's
    # default in one place.
    assert resolve_fields(None) is None
    assert resolve_fields("") == [
        "starts_at",
        "ends_at",
        "lineup",
        "location",
    ]


def test_an_unknown_field_mode_is_refused_at_startup():
    """A typo must fail loudly, at construction, not silently chase nothing.

    Treating `dateses` as "no fields" would leave the scheduler reporting a
    clean run while doing no work at all - the exact failure mode a safety net
    must not have.
    """

    with pytest.raises(ValueError):
        resolve_fields("dateses")


@pytest.mark.asyncio
async def test_a_dry_run_reports_without_writing():
    """A run that changes the database has to be asked for."""

    service, events, client = build_service(
        [an_event("1")],
        pages={
            "https://www.songkick.com/festivals/1-x": {
                "url": "https://www.songkick.com/festivals/1-x",
                "start_date": "2026-03-25T20:00:00+00:00",
                "date_status": DATE_FROM_SOURCE,
            }
        },
    )

    result = await run_enrichment_once(
        service,
        EnrichmentJobConfig(
            delay_seconds=0,
            dry_run=True,
            fields=["starts_at", "ends_at"],
        ),
    )

    assert result.updated == 1
    assert events.writes == []
    assert events.stored("1")["starts_at"] is None
