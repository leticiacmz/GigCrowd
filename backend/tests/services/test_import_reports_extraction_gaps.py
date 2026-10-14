"""One run reports what it could not obtain, and owes nothing to later.

The model this replaces deferred: an import wrote a festival listing with no
date, counted it, and a scheduled pass came back hours later to read the
event's page. Two things were wrong with that. The report and the fix lived in
different runs, so a summary saying "5 incomplete" was indistinguishable from a
summary saying "5 since fixed"; and the fix depended on a process nobody had
guaranteed would run.

Both halves are gone, and this file pins down what replaced them:

* no collaborator, no parameter and no counter to defer to - the importer has
  nothing to hand a gap to;
* a gap is reported in the run that found it, with the event id, the field and
  the source, in the returned summary *and* in the log;
* the pages that can close a gap are read by extraction during this same run
  (see `tests/providers/songkick/test_first_pass_completion.py`), so what
  survives to this report is a fact about the source, not a backlog.

Nothing here needs MongoDB or the network: the provider and the repositories
are doubles, because the properties under test are the wiring and the report.
"""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.artist import Artist
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

    A name, a URL and an identity - a venue that is stated, and no date and no
    lineup anywhere. This is the shape the whole model exists for: the row has
    everything except the two things a reader notices first.
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


def a_complete_concert(event_id: str = "9001") -> dict:
    """A listing that states everything this report asks about."""

    return {
        "songkick_id": event_id,
        "name": "Marina Sena at Sala",
        "event_type": "Concert",
        "start_date": "2026-03-01T21:00:00+00:00",
        "end_date": None,
        "url": f"https://www.songkick.com/concerts/{event_id}-sala",
        "venue": {
            "name": "Sala Sao Paulo",
            "address": {
                "addressLocality": "Sao Paulo",
                "addressCountry": "BR",
            },
        },
    }


def build_import(
    payloads: list[dict],
    extraction: dict | None = None,
) -> tuple[SongkickEventImportService, dict]:
    """An importer wired to doubles, returning the doubles for inspection."""

    provider_result = {
        "events": payloads,
        "upcoming_festivals": [],
    }

    if extraction is not None:
        provider_result["extraction"] = extraction

    provider_manager = MagicMock()

    songkick_provider = MagicMock()
    songkick_provider.get_artist_events = AsyncMock(
        return_value=provider_result
    )

    provider_manager.get_provider = MagicMock(
        return_value=songkick_provider
    )

    event_repository = MagicMock()
    event_repository.upsert_event_by_provider = AsyncMock(
        return_value=True
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

    service = SongkickEventImportService(
        provider_manager=provider_manager,
        event_repository=event_repository,
        venue_repository=venue_repository,
        artist_repository=artist_repository,
    )

    return service, {
        "provider_manager": provider_manager,
        "songkick_provider": songkick_provider,
        "event_repository": event_repository,
    }


# ==============================================================
# 0. THERE IS NOWHERE TO DEFER TO
# ==============================================================


def test_the_import_has_no_enrichment_parameter():
    """The option to defer is gone, not merely switched off.

    A parameter that defaults to None still invites a caller to pass one, and
    a flag that can be flipped brings the whole model back. The signature is
    where "the import does this itself, or reports it" becomes unfalsifiable.
    """

    with pytest.raises(TypeError):
        SongkickEventImportService(
            provider_manager=MagicMock(),
            event_repository=MagicMock(),
            venue_repository=MagicMock(),
            artist_repository=MagicMock(),
            enrichment_service=object(),
        )


def test_production_is_wired_without_an_enrichment_service():
    """The wiring in the running application, read from the application.

    A removed parameter proves nothing if the route still builds the service
    and the settings still describe a pass, because that is how a reviewer
    concludes that gaps are being handled when nothing is handling them.
    """

    from app.config import settings
    from app.routes import artists

    assert not hasattr(artists, "event_enrichment_service")
    assert not hasattr(
        artists.event_import_service,
        "enrichment_service",
    )
    assert not hasattr(settings, "ENRICH_ON_IMPORT_ENABLED")
    assert not hasattr(settings, "ENRICHMENT_SCHEDULER_ENABLED")


@pytest.mark.asyncio
async def test_an_import_makes_one_provider_call_and_no_event_requests():
    """The request budget of an import, asserted rather than assumed.

    The provider is called once for the catalogue. Nothing else exists to make
    a request: no collaborator, no client, no per-event walk. What extraction
    had to read beyond the pages it pays for anyway arrives already counted, in
    the extraction report the provider passed through.
    """

    service, doubles = build_import(
        [an_undated_listing(), a_complete_concert("9002")],
        extraction={
            "event_pages_read": 2,
            "event_pages_skipped": 1,
            "event_pages_failed": 0,
            "limit": 25,
        },
    )

    report = await service.sync_artist_events(an_artist())

    doubles["songkick_provider"].get_artist_events.assert_awaited_once()
    assert (
        doubles["songkick_provider"].get_artist_events.await_count == 1
    )

    assert report["events_created"] == 2

    # Read by extraction *before* the import ran, never by the import itself.
    assert report["event_pages_read"] == 2
    assert report["event_pages_unread"] == 1
    assert report["event_pages_failed"] == 0

    for enrichment_key in (
        "events_incomplete_found",
        "events_enriched",
        "events_enrichment_failed",
        "events_enrichment_deferred",
    ):
        assert enrichment_key not in report


# ==============================================================
# 1. A GAP IS REPORTED WHERE IT OCCURS
# ==============================================================


@pytest.mark.asyncio
async def test_an_undated_listing_is_reported_as_a_gap_in_the_same_run(
    caplog,
):
    """The core replacement: an owed field is a reported fact, not a work item.

    The event is written, the gap is counted, and the run finishes. Nothing
    waits on anything else, so whoever reads this summary is reading what the
    database now holds.
    """

    service, _ = build_import([an_undated_listing()])

    with caplog.at_level(
        logging.WARNING,
        logger="songkick_event_import",
    ):
        report = await service.sync_artist_events(an_artist())

    assert report["events_created"] == 1
    assert report["events_with_extraction_gaps"] == 1

    # Fixed field order, so two summaries can be compared field by field.
    assert report["extraction_gaps"] == {
        "date": 1,
        "lineup": 1,
    }

    # The id, the fields and the source, at the point of occurrence.
    assert "[EXTRACTION GAP]" in caplog.text
    assert "8100001" in caplog.text
    assert "date, lineup" in caplog.text
    assert "festivals/8100001-villa-sound" in caplog.text
    assert "nothing deferred" in caplog.text


@pytest.mark.asyncio
async def test_a_complete_event_reports_nothing():
    """A listing that states everything costs no attention.

    Without this the report would be a running total of ordinary events, and a
    real gap would be invisible inside it.
    """

    service, _ = build_import([a_complete_concert()])

    report = await service.sync_artist_events(an_artist())

    assert report["events_created"] == 1
    assert report["events_with_extraction_gaps"] == 0
    assert report["extraction_gaps"] == {}
    assert report["events_extraction_failed"] == 0


@pytest.mark.asyncio
async def test_a_livestream_is_not_reported_as_missing_a_venue():
    """An event that is supposed to be placeless is not missing a venue.

    Reporting it would make every livestream a permanent gap, which is how a
    real gap stops being reported at all.
    """

    service, _ = build_import(
        [
            {
                **a_complete_concert("9501"),
                "is_live_stream": True,
                "venue": None,
            }
        ]
    )

    report = await service.sync_artist_events(an_artist())

    assert report["events_with_extraction_gaps"] == 0


@pytest.mark.asyncio
async def test_a_venue_the_source_never_stated_is_a_gap(caplog):
    """The placeholder the mapper writes is what makes this judgeable.

    "Unknown Venue" is written precisely because the payload said no venue
    name; it is the one name an event can carry without the source having said
    it, which is exactly what a gap is.
    """

    payload = a_complete_concert("9502")
    payload["venue"] = None

    service, _ = build_import([payload])

    with caplog.at_level(
        logging.WARNING,
        logger="songkick_event_import",
    ):
        report = await service.sync_artist_events(an_artist())

    assert report["extraction_gaps"] == {"venue": 1}
    assert "venue" in caplog.text


@pytest.mark.asyncio
async def test_a_date_that_could_not_be_read_is_a_failure_not_a_verdict(
    caplog,
):
    """"The page has no date" and "the date could not be read" are different.

    The first is answered by the source. The second is answered by a person
    looking at a parser, so it is counted separately, at error level, with the
    source it came from.
    """

    payload = an_undated_listing("8100007")
    payload["start_date"] = "not-a-date"
    payload["date_status"] = "parser_failed"

    service, _ = build_import([payload])

    with caplog.at_level(
        logging.ERROR,
        logger="songkick_event_import",
    ):
        report = await service.sync_artist_events(an_artist())

    assert report["events_extraction_failed"] == 1
    assert report["events_with_extraction_gaps"] == 1

    assert "[EXTRACTION FAILURE]" in caplog.text
    assert "8100007" in caplog.text
    assert "parser_failed" in caplog.text


@pytest.mark.asyncio
async def test_an_unreachable_source_is_still_just_an_import():
    """A source being down must not change what the import does.

    There is no pass to stop and no remainder to defer, because there was never
    a pass. The events are written, and what they lack is reported.
    """

    service, doubles = build_import(
        [
            an_undated_listing("8100011"),
            an_undated_listing("8100012"),
        ]
    )

    report = await service.sync_artist_events(an_artist())

    assert report["events_created"] == 2
    assert report["events_with_extraction_gaps"] == 2
    assert report["events_skipped"] == 0
    assert doubles["songkick_provider"].get_artist_events.await_count == 1


# ==============================================================
# 2. WHAT THE REPORT DESCRIBES IS WHAT WAS WRITTEN
# ==============================================================


@pytest.mark.asyncio
async def test_the_report_and_the_row_share_one_identity():
    """Every gap the report counts belongs to the row that was written.

    The importer knows the provider's id for the event; that id is what the
    upsert keys on and what the log prints. One identity across the write and
    the report is what makes a logged gap findable in the database.
    """

    service, doubles = build_import([an_undated_listing()])

    report = await service.sync_artist_events(an_artist())

    call = doubles["event_repository"].upsert_event_by_provider.await_args

    assert call.args[1] == "songkick"
    assert call.args[0].external_ids == {"songkick": "8100001"}
    assert report["events_created"] == 1
    assert report["events_with_extraction_gaps"] == 1


@pytest.mark.asyncio
async def test_a_resync_does_not_blank_a_recovered_festival_range():
    """A later run must not be able to undo what an earlier one obtained.

    The listing that produced an undated event produces it again on the next
    sync. If that sync wrote the listing's `None` over dates that came from the
    event's own page, the record would return to the incomplete state every
    time and could never settle.
    """

    from app.domain.event import Event
    from app.repositories.event_repository import EventRepository

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

    stored["1"] = {
        "_id": "1",
        "external_ids": {"songkick": "8100001"},
        "starts_at": "2026-03-25T20:00:00+00:00",
        "ends_at": "2026-03-27T23:00:00+00:00",
        "date_status": "source",
        "date_source_checked_at": "2026-01-01T00:00:00+00:00",
        "title": "Marina Sena at Villa Sound",
        "went_count": 2,
        "going_count": 0,
        "maybe_count": 0,
    }

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
    assert document["date_status"] == "source"

    # Attendance belongs to people. A listing never measured it.
    assert document["went_count"] == 2


@pytest.mark.asyncio
async def test_a_resync_still_corrects_what_the_source_does_state():
    """Refusing to lose data is not the same as refusing to update it.

    The title still comes from the listing on every sync; only the fields the
    listing has no standing to speak for are left alone.
    """

    from app.domain.event import Event
    from app.repositories.event_repository import EventRepository

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
