"""A newly imported event must not need a later backfill to become complete.

These tests describe the rule the whole enrichment lifecycle exists to enforce:

    Songkick listing
        -> event discovered
        -> event created
        -> if required fields are incomplete
        -> the concrete event page is fetched
        -> the event is enriched and the recovered fields persisted
        -> complete event

The failing case they pin down is a festival listed without a date. Songkick's
gigography states no date for many festival appearances, yet each of those has a
page of its own carrying the real `startDate` and `endDate`. Writing the
listing and stopping produced `starts_at = null` with `date_status = null` and a
source nobody had read - a record that is not merely incomplete but
indistinguishable from one that was never checked, and so was never retried.

Nothing here needs MongoDB or the network. The provider, the repositories and
the enrichment service are all doubles, because the property under test is the
*order and the wiring*: that the import asks, the concrete page is fetched, and
the recovered date reaches storage inside the same call that created the event.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.artist import Artist
from app.services.event_enrichment_service import (
    DATE_FIELDS,
    DATE_FROM_SOURCE,
    DATE_PARSER_FAILED,
    DATE_UNAVAILABLE,
    LINEUP_FIELDS,
    LOCATION_FIELDS,
    EventEnrichmentService,
)
from app.services.songkick_event_import_service import (
    SongkickEventImportService,
)


# ==============================================================
# FIXTURES
# ==============================================================


def an_artist() -> Artist:
    return Artist(
        name="Marina Sena",
        normalized_name="marina sena",
        slug="marina-sena",
        external_ids={"songkick": "Artist3090429"},
    )


def an_undated_listing(event_id: str = "8100001") -> dict:
    """What Songkick's gigography actually says about a festival appearance.

    A name, a URL and an identity - and no date anywhere. This shape is the
    reason the enrichment lifecycle exists.
    """

    return {
        "songkick_id": event_id,
        "name": "Marina Sena at Villa Sound",
        "event_type": "festival",
        "url": (
            f"https://www.songkick.com/festivals/"
            f"{event_id}-villa-sound"
        ),
        "start_date": None,
        "end_date": None,
        "venue": {
            "name": "Parque de la Ciudad",
            "url": (
                "https://www.songkick.com/venues/9001-"
                "parque-de-la-ciudad"
            ),
            "address": {
                "addressLocality": "Buenos Aires",
                "addressCountry": "AR",
            },
        },
        "festival": {
            "series_id": "44001",
            "name": "Villa Sound",
            "url": (
                f"https://www.songkick.com/festivals/"
                f"{event_id}-villa-sound"
            ),
        },
        "lineup": [],
        "artist_ids": [3090429],
    }


def the_concrete_page(start: str, end: str) -> dict:
    """What the event's own page states, as `enrich_event_details` returns it."""

    return {
        "url": (
            "https://www.songkick.com/festivals/8100001-villa-sound"
        ),
        "start_date": start,
        "end_date": end,
        "date_status": DATE_FROM_SOURCE,
        "festival": {"series_id": "44001", "name": "Villa Sound"},
    }


def build_import(
    payloads: list[dict],
    enrich_event=None,
    enrich_limit: int = 60,
) -> tuple[SongkickEventImportService, dict]:
    """An importer wired to doubles, returning the doubles for inspection."""

    provider_manager = MagicMock()

    songkick_provider = MagicMock()

    songkick_provider.get_artist_events = AsyncMock(
        return_value={
            "events": payloads,
            "upcoming_festivals": [],
        }
    )

    provider_manager.get_provider = MagicMock(
        return_value=songkick_provider
    )

    event_repository = MagicMock()
    event_repository.upsert_event_by_provider = AsyncMock(
        return_value=True
    )
    event_repository.get_id_by_external_id = AsyncMock(
        side_effect=lambda provider, external: f"stored-{external}"
    )

    venue_repository = MagicMock()
    venue_repository.upsert_venue = AsyncMock(return_value=True)
    venue_repository.get_by_external_id = AsyncMock(
        return_value={"slug": "parque-de-la-ciudad"}
    )
    venue_repository.get_by_name = AsyncMock(return_value=None)

    artist_repository = MagicMock()
    artist_repository.get_by_songkick_id = AsyncMock(
        return_value=an_artist()
    )

    enrichment_service = (
        MagicMock(enrich_event=AsyncMock(side_effect=enrich_event))
        if enrich_event is not None
        else None
    )

    service = SongkickEventImportService(
        provider_manager=provider_manager,
        event_repository=event_repository,
        venue_repository=venue_repository,
        artist_repository=artist_repository,
        enrichment_service=enrichment_service,
        enrich_fields=["starts_at", "ends_at"],
        enrich_limit=enrich_limit,
        enrich_delay_seconds=0,
    )

    return service, {
        "provider_manager": provider_manager,
        "songkick_provider": songkick_provider,
        "event_repository": event_repository,
        "enrichment_service": enrichment_service,
    }


# ==============================================================
# 1. THE LISTING HAS NO DATE, SO THE CONCRETE PAGE IS READ
# ==============================================================


@pytest.mark.asyncio
async def test_a_listing_without_a_date_reads_the_concrete_page():
    """The core rule: an undated listing triggers a source read, not silence.

    Nothing about this behaviour is optional. If the import stops at the
    listing, the event is stored undated and the only thing that can fix it is
    something running later - which is precisely the manual backfill this
    replaces.
    """

    async def enrich(event_id, dry_run=False, fields=None):
        # The real service reads the stored document and fetches the page. The
        # import's obligation is to ask, with the id of the row it just wrote.
        assert event_id == "stored-8100001"

        return {
            "event_id": event_id,
            "outcome": "updated",
            "fields": ["starts_at", "ends_at"],
        }

    service, doubles = build_import(
        [an_undated_listing()],
        enrich_event=enrich,
    )

    report = await service.sync_artist_events(an_artist())

    doubles["enrichment_service"].enrich_event.assert_awaited_once()

    assert report["events_incomplete_found"] == 1
    assert report["events_enriched"] == 1


@pytest.mark.asyncio
async def test_the_url_read_is_the_concrete_event_url():
    """The page that gets read is the event's own page, from the listing.

    Not the artist's gigography, not a search result: the URL the listing
    carried. That URL is the only thing tying this record to the page that
    holds its date.
    """

    stored_documents: dict[str, dict] = {}

    enrichment_service = MagicMock()
    enrichment_service.enrich_event = AsyncMock(
        return_value={"outcome": "updated"}
    )

    service, doubles = build_import([an_undated_listing()])

    service.enrichment_service = enrichment_service

    # Capture what the mapper actually wrote, so the source URL can be checked
    # against the payload rather than against a restatement of it.
    async def capture(event, provider):
        stored_documents[event.external_ids[provider]] = {
            "source": event.source,
            "festival": event.festival,
        }

        return True

    doubles["event_repository"].upsert_event_by_provider = AsyncMock(
        side_effect=capture
    )

    await service.sync_artist_events(an_artist())

    written = stored_documents["8100001"]

    assert written["source"]["url"] == (
        "https://www.songkick.com/festivals/8100001-villa-sound"
    )

    enrichment_service.enrich_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_an_event_that_is_already_dated_is_not_re_read():
    """Completeness is the gate, so a dated event costs no request.

    Without this, every import would fetch a page for every event it has ever
    imported, which is both slow and rude to the provider.
    """

    listing = an_undated_listing()
    listing["start_date"] = "2026-03-25T20:00:00+00:00"

    service, doubles = build_import(
        [listing],
        enrich_event=lambda *a, **k: {"outcome": "updated"},
    )

    report = await service.sync_artist_events(an_artist())

    assert report["events_incomplete_found"] == 0

    doubles["enrichment_service"].enrich_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_event_with_no_concrete_source_is_left_for_the_scheduler():
    """Nothing to read means nothing to read.

    An entry the listing gave no URL for cannot be improved by asking again, so
    the import does not invent a source and does not spend a request.
    """

    listing = an_undated_listing()
    listing.pop("url")
    listing["festival"] = {"series_id": "44001", "name": "Villa Sound"}

    service, doubles = build_import(
        [listing],
        enrich_event=lambda *a, **k: {"outcome": "updated"},
    )

    report = await service.sync_artist_events(an_artist())

    assert report["events_incomplete_found"] == 0

    doubles["enrichment_service"].enrich_event.assert_not_awaited()


# ==============================================================
# 2. THE RECOVERED DATE IS PERSISTED
# ==============================================================


@pytest.mark.asyncio
async def test_the_recovered_festival_range_reaches_storage():
    """A real enrichment is a write, not a log line.

    Driven against a real `EventEnrichmentService` over an in-memory fake
    collection, so this covers the whole chain from "the import asked" through
    "the page was fetched" to "the stored document carries the dates".
    """

    fake_db = MagicMock()

    collection = MagicMock()
    stored: dict = {}

    async def find_one(query, projection=None):
        return stored.get(str(query.get("_id")))

    collection.find_one = AsyncMock(side_effect=find_one)
    collection.update_one = AsyncMock(
        side_effect=lambda q, update: stored.__setitem__(
            str(q["_id"]),
            {**stored.get(str(q["_id"]), {}), **update["$set"]},
        )
    )

    fake_db.events = collection
    fake_db.venues = MagicMock()
    fake_db.venues.find_one = AsyncMock(return_value=None)

    event_repository = MagicMock()
    event_repository.collection = collection
    event_repository.db = fake_db

    client = MagicMock()
    client.enrich_event_details = AsyncMock(
        return_value=the_concrete_page(
            "2026-03-25T20:00:00+00:00",
            "2026-03-27T23:59:00+00:00",
        )
    )

    enrichment_service = EventEnrichmentService(
        event_repository,
        client=client,
    )

    service, doubles = build_import([an_undated_listing()])
    service.enrichment_service = enrichment_service

    # The row the import writes, exactly as the mapper leaves it: no dates, and
    # no claim about whether the source has any.
    stored["stored-8100001"] = {
        "_id": "stored-8100001",
        "title": "Marina Sena at Villa Sound",
        "event_type": "FestivalInstance",
        "starts_at": None,
        "ends_at": None,
        "date_status": None,
        "source": {
            "provider": "songkick",
            "external_id": "8100001",
            "url": (
                "https://www.songkick.com/festivals/"
                "8100001-villa-sound"
            ),
        },
        "lineup": [],
        "location": None,
    }

    report = await service.sync_artist_events(an_artist())

    assert report["events_enriched"] == 1

    written = stored["stored-8100001"]

    # The full real range, both ends. A festival is not its opening night.
    assert written["starts_at"].isoformat() == (
        "2026-03-25T20:00:00+00:00"
    )
    assert written["ends_at"].isoformat() == (
        "2026-03-27T23:59:00+00:00"
    )
    assert written["date_status"] == DATE_FROM_SOURCE
    assert written["date_source_checked_at"] is not None


@pytest.mark.asyncio
async def test_the_import_does_not_remain_permanently_tba():
    """The whole point: no backfill is required to place a new event.

    Read as a property rather than as a field check. After one import call,
    the event must be either dated or explicitly reported as still owed -
    never quietly left in the state that started this work.
    """

    fake_db = MagicMock()

    collection = MagicMock()
    stored: dict = {}

    collection.find_one = AsyncMock(
        side_effect=lambda q, p=None: stored.get(str(q.get("_id")))
    )
    collection.update_one = AsyncMock(
        side_effect=lambda q, update: stored.__setitem__(
            str(q["_id"]),
            {**stored.get(str(q["_id"]), {}), **update["$set"]},
        )
    )

    fake_db.events = collection
    fake_db.venues = MagicMock()
    fake_db.venues.find_one = AsyncMock(return_value=None)

    event_repository = MagicMock()
    event_repository.collection = collection
    event_repository.db = fake_db

    client = MagicMock()
    client.enrich_event_details = AsyncMock(
        return_value=the_concrete_page(
            "2026-03-25T20:00:00+00:00",
            "2026-03-27T23:59:00+00:00",
        )
    )

    service, doubles = build_import([an_undated_listing()])

    service.enrichment_service = EventEnrichmentService(
        event_repository,
        client=client,
    )

    stored["stored-8100001"] = {
        "_id": "stored-8100001",
        "title": "Marina Sena at Villa Sound",
        "event_type": "FestivalInstance",
        "starts_at": None,
        "ends_at": None,
        "date_status": None,
        "source": {
            "url": (
                "https://www.songkick.com/festivals/"
                "8100001-villa-sound"
            )
        },
        "lineup": [],
        "location": None,
    }

    report = await service.sync_artist_events(an_artist())

    written = stored["stored-8100001"]

    assert (
        written["starts_at"] is not None
        or report["events_enrichment_deferred"] > 0
    ), (
        "an imported event must be dated after its import, or "
        "explicitly reported as still owed to the scheduler"
    )


# ==============================================================
# 3. `unavailable` IS NEVER CLAIMED BEFORE THE SOURCE IS READ
# ==============================================================


def test_a_listing_without_a_date_is_not_called_unavailable():
    """Unknown is not unavailable.

    A gigography that carries no date has not established that the event has
    none. Writing `unavailable` asserted something the listing cannot know, and
    the enrichment selector used to take that at face value - so fifty festival
    dates whose dates sat on Songkick the whole time were never re-read.
    """

    from app.mappers.songkick_event_mapper import (
        SongkickEventMapper,
    )

    event, _ = SongkickEventMapper.to_domain(
        an_undated_listing(),
        ["marina-sena"],
    )

    assert event.starts_at is None
    assert event.date_status is None


def test_unavailable_without_a_source_check_is_still_incomplete():
    """The marker only means something next to a record of the visit.

    `is_incomplete` is the one definition both the import and the scheduler
    use, so it has to refuse to accept a bare `unavailable` - that combination
    is exactly the state this work exists to eliminate.
    """

    assert EventEnrichmentService.is_incomplete(
        {
            "starts_at": None,
            "date_status": DATE_UNAVAILABLE,
            "event_type": "FestivalInstance",
        },
        fields=DATE_FIELDS,
    )


def test_unavailable_after_an_inspection_is_finished():
    """A confirmed absence is an answer, and is not chased again.

    Without this, the scheduler would re-read every genuinely undated event on
    every tick forever.
    """

    assert not EventEnrichmentService.is_incomplete(
        {
            "starts_at": None,
            "date_status": DATE_UNAVAILABLE,
            "date_source_checked_at": "2026-01-01T00:00:00+00:00",
            "event_type": "FestivalInstance",
        },
        fields=DATE_FIELDS,
    )


def test_parser_failed_is_always_retriable():
    """A broken shape is a bug to be fixed, not a verdict on the event."""

    assert EventEnrichmentService.is_incomplete(
        {
            "starts_at": None,
            "date_status": DATE_PARSER_FAILED,
            "event_type": "Concert",
        },
        fields=DATE_FIELDS,
    )


def test_a_concert_with_a_start_and_no_end_is_complete():
    """A gig starts and it is over.

    Songkick states no end for a concert, so treating the missing end as a gap
    would send the scheduler to every concert ever imported, forever, and never
    find anything.
    """

    assert not EventEnrichmentService.is_incomplete(
        {
            "starts_at": "2026-10-04T12:00:00+00:00",
            "ends_at": None,
            "date_status": DATE_FROM_SOURCE,
            "event_type": "Concert",
        },
        fields=DATE_FIELDS,
    )


def test_a_dated_event_is_not_a_date_candidate_even_with_other_gaps():
    """Asking for dates does not silently become asking for everything.

    An event with a date and no location is incomplete for a *location* pass,
    and only that. If the date check returned True here, a date-only run would
    chase 1,200 events to learn nothing about their dates.
    """

    assert not EventEnrichmentService.is_incomplete(
        {
            "starts_at": "2026-10-04T12:00:00+00:00",
            "date_status": DATE_FROM_SOURCE,
            "event_type": "Concert",
            "location": None,
            "lineup": [],
        },
        fields=DATE_FIELDS,
    )


def test_the_same_event_is_a_candidate_for_a_location_pass():
    """The scope is what decides, so the same event can answer both ways.

    This is why `fields` is part of the question rather than baked into it: the
    import and the scheduler are configured with what they are chasing, and both
    get the same answer for the same configuration.
    """

    assert EventEnrichmentService.is_incomplete(
        {
            "starts_at": "2026-10-04T12:00:00+00:00",
            "date_status": DATE_FROM_SOURCE,
            "event_type": "Concert",
            "location": None,
        },
        fields=LOCATION_FIELDS,
    )


def test_a_lineup_is_only_owed_by_a_festival():
    """A concert page carries no lineup, so asking it for one is waste."""

    assert not EventEnrichmentService.is_incomplete(
        {
            "starts_at": "2026-10-04T12:00:00+00:00",
            "date_status": DATE_FROM_SOURCE,
            "event_type": "Concert",
            "lineup": [],
        },
        fields=LINEUP_FIELDS,
    )

    assert EventEnrichmentService.is_incomplete(
        {
            "starts_at": "2026-03-25T20:00:00+00:00",
            "date_status": DATE_FROM_SOURCE,
            "event_type": "FestivalInstance",
            "lineup": [],
        },
        fields=LINEUP_FIELDS,
    )


# ==============================================================
# 4. FAILURES DEFER TO THE SCHEDULER RATHER THAN BREAKING THE IMPORT
# ==============================================================


@pytest.mark.asyncio
async def test_an_unreachable_page_does_not_end_the_import():
    """One bad page must not cost the other events their recovery."""

    async def enrich(event_id, dry_run=False, fields=None):
        if event_id == "stored-8100001":
            raise RuntimeError("songkick is down")

        return {"outcome": "updated"}

    service, _ = build_import(
        [an_undated_listing()],
        enrich_event=enrich,
    )

    report = await service.sync_artist_events(an_artist())

    assert report["events_created"] == 1
    assert report["events_enrichment_failed"] == 1
    assert report["events_enriched"] == 0


@pytest.mark.asyncio
async def test_the_bound_leaves_the_rest_to_the_scheduler():
    """Bounded work, honestly accounted for.

    A single artist's sync must not be able to spend an unbounded amount of
    time inside someone else's servers. What it leaves behind has to be visible
    rather than quietly dropped.
    """

    payloads = [
        an_undated_listing(str(8100000 + index))
        for index in range(5)
    ]

    service, doubles = build_import(
        payloads,
        enrich_event=lambda *a, **k: {"outcome": "updated"},
        enrich_limit=2,
    )

    report = await service.sync_artist_events(an_artist())

    assert doubles["enrichment_service"].enrich_event.await_count == 2
    assert report["events_incomplete_found"] == 5
    assert report["events_enrichment_deferred"] == 3


@pytest.mark.asyncio
async def test_a_dead_source_ends_the_pass_and_defers_the_rest():
    """A source that stops answering ends the attempt, not the import.

    A failure costs minutes - the client retries rather than give up on
    the first timeout - so a pass over an unreachable Songkick would burn
    the whole bound one timeout at a time. Five failures in a row is a
    source that is down, not five unlucky events: the walk stops, the
    events it never reached are counted as deferred, and the import
    itself still finishes.
    """

    async def enrich(event_id, dry_run=False, fields=None):
        raise RuntimeError("songkick is unreachable")

    payloads = [
        an_undated_listing(str(8100000 + index))
        for index in range(8)
    ]

    service, doubles = build_import(
        payloads,
        enrich_event=enrich,
    )

    report = await service.sync_artist_events(an_artist())

    assert (
        doubles["enrichment_service"].enrich_event.await_count == 5
    )
    assert report["events_enrichment_failed"] == 5
    assert report["events_enrichment_deferred"] == 3
    assert report["events_enriched"] == 0
    assert report["events_created"] == 8


@pytest.mark.asyncio
async def test_import_without_enrichment_still_imports():
    """The degraded path stays available.

    With enrichment switched off the importer still writes events; they are
    simply incomplete, and the scheduler is told so rather than the import
    pretending otherwise.
    """

    service, doubles = build_import([an_undated_listing()])

    assert service.enrichment_service is None

    report = await service.sync_artist_events(an_artist())

    assert report["events_created"] == 1
    assert report["events_incomplete_found"] == 1
    assert report["events_enrichment_deferred"] == 1
    assert report["events_enriched"] == 0


@pytest.mark.asyncio
async def test_repeated_imports_do_not_keep_reading_a_confirmed_event():
    """Idempotent, from the import side.

    Once a source visit has recorded that the event really has no date, a
    resync must not pay for the same answer again.
    """

    fake_db = MagicMock()

    collection = MagicMock()
    stored: dict = {}

    collection.find_one = AsyncMock(
        side_effect=lambda q, p=None: stored.get(str(q.get("_id")))
    )
    collection.update_one = AsyncMock(
        side_effect=lambda q, update: stored.__setitem__(
            str(q["_id"]),
            {**stored.get(str(q["_id"]), {}), **update["$set"]},
        )
    )

    fake_db.events = collection
    fake_db.venues = MagicMock()
    fake_db.venues.find_one = AsyncMock(return_value=None)

    event_repository = MagicMock()
    event_repository.collection = collection
    event_repository.db = fake_db

    client = MagicMock()
    client.enrich_event_details = AsyncMock(
        return_value={"url": "x", "start_date": None, "end_date": None}
    )

    enrichment_service = EventEnrichmentService(
        event_repository,
        client=client,
    )

    service, _ = build_import([an_undated_listing()])
    service.enrichment_service = enrichment_service

    stored["stored-8100001"] = {
        "_id": "stored-8100001",
        "title": "Marina Sena at Villa Sound",
        "event_type": "FestivalInstance",
        "starts_at": None,
        "ends_at": None,
        "date_status": None,
        "source": {
            "url": (
                "https://www.songkick.com/festivals/"
                "8100001-villa-sound"
            )
        },
        "lineup": [],
        "location": None,
    }

    await service.sync_artist_events(an_artist())

    assert client.enrich_event_details.await_count == 1

    # The record now says the source was read and holds no date.
    assert stored["stored-8100001"]["date_status"] == (
        DATE_UNAVAILABLE
    )
    assert stored["stored-8100001"]["date_source_checked_at"]

    # A second import asks again - the listing is still undated - but the
    # stored record answers without a second page fetch.
    await service.sync_artist_events(an_artist())

    assert client.enrich_event_details.await_count == 1


# ==============================================================
# 5. A RESYNC MUST NOT ERASE WHAT WAS RECOVERED
# ==============================================================


@pytest.mark.asyncio
async def test_a_resync_does_not_blank_a_recovered_festival_range():
    """Recovery must be durable, or it is not recovery.

    The listing that produced an undated event will produce it again on the next
    sync. If that sync wrote the listing's `None` over the recovered dates, the
    record would return to the incomplete state every single time and could
    never settle.
    """

    from app.domain.event import Event
    from app.repositories.event_repository import (
        EventRepository,
    )

    collection = MagicMock()
    stored: dict = {}

    async def update_one(query, update):
        document = stored.get("1")

        for name, value in update.get("$set", {}).items():
            document[name] = value

        for name in update.get("$unset", {}):
            document.pop(name, None)

        return MagicMock()

    collection.update_one = AsyncMock(side_effect=update_one)

    repository = EventRepository.__new__(EventRepository)
    repository.collection = collection

    # The stored record, as enrichment left it: a full festival range.
    stored["1"] = {
        "_id": "1",
        "external_ids": {"songkick": "8100001"},
        "starts_at": "2026-03-25T20:00:00+00:00",
        "ends_at": "2026-03-27T23:00:00+00:00",
        "date_status": DATE_FROM_SOURCE,
        "date_source_checked_at": "2026-01-01T00:00:00+00:00",
        "title": "Marina Sena at Villa Sound",
        "went_count": 2,
        "going_count": 0,
        "maybe_count": 0,
    }

    # What the next sync maps: the same listing, still carrying no date.
    incoming = Event(
        external_ids={"songkick": "8100001"},
        artist_slugs=["marina-sena"],
        artist_slug="marina-sena",
        venue_slug="parque-de-la-ciudad",
        title="Marina Sena at Villa Sound",
        starts_at=None,
        ends_at=None,
        event_type="FestivalInstance",
        date_status=None,
        source={"url": "https://www.songkick.com/x"},
        went_count=0,
        going_count=0,
        maybe_count=0,
    )

    await repository.update_event_by_provider(incoming, "songkick")

    document = stored["1"]

    assert document["starts_at"] == "2026-03-25T20:00:00+00:00"
    assert document["ends_at"] == "2026-03-27T23:00:00+00:00"
    assert document["date_status"] == DATE_FROM_SOURCE

    # Attendance belongs to people. A listing never measured it.
    assert document["went_count"] == 2


@pytest.mark.asyncio
async def test_a_resync_still_corrects_what_the_source_does_state():
    """Refusing to lose data is not the same as refusing to update it.

    The title still comes from the listing on every sync; only the fields the
    listing has no standing to speak for are left alone.
    """

    from app.domain.event import Event
    from app.repositories.event_repository import (
        EventRepository,
    )

    collection = MagicMock()
    stored: dict = {"1": {"_id": "1", "external_ids": {"songkick": "9"}}}

    async def update_one(query, update):
        stored["1"].update(update.get("$set", {}))

        for name in update.get("$unset", {}):
            stored["1"].pop(name, None)

        return MagicMock()

    collection.update_one = AsyncMock(side_effect=update_one)

    repository = EventRepository.__new__(EventRepository)
    repository.collection = collection

    await repository.update_event_by_provider(
        Event(
            external_ids={"songkick": "9"},
            artist_slugs=["marina-sena"],
            artist_slug="marina-sena",
            venue_slug="parque-de-la-ciudad",
            title="A corrected title",
        ),
        "songkick",
    )

    assert stored["1"]["title"] == "A corrected title"


@pytest.mark.asyncio
async def test_the_stored_id_is_read_rather_than_guessed():
    """Enrichment is pointed at the row that exists.

    The importer knows the provider's id for the event; only the database knows
    its own. Reading it is what guarantees the recovered fields land on the
    stored document rather than on an id that was reconstructed.
    """

    service, doubles = build_import(
        [an_undated_listing()],
        enrich_event=lambda *a, **k: {"outcome": "updated"},
    )

    await service.sync_artist_events(an_artist())

    doubles["event_repository"].get_id_by_external_id.assert_awaited_with(
        "songkick",
        "8100001",
    )
