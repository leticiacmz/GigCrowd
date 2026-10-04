"""Filling in what stored events are missing, without inventing anything.

The behaviour these cover was settled by two failures during a real run.

First, a venue write that overwrote a stored venue's name collided with another
venue's unique index and raised. Because nothing caught it, that one record
ended a run over hundreds. Second, dates were being read but never written:
the source states them as ISO strings, and the normaliser only accepted
`datetime` objects, so every date was dropped and the event stayed undated
while the log cheerfully reported a successful update.

Both are covered below, along with the rule that matters most: a run must only
ever fill a gap, never overwrite a good value, and must be safe to repeat.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from bson import ObjectId

from app.services.event_enrichment_service import (
    DATE_FIELDS,
    DATE_FROM_SOURCE,
    DATE_UNAVAILABLE,
    DATE_PARSER_FAILED,
    EnrichmentPlan,
    EventEnrichmentService,
)
from tests.support.fake_mongo import FakeDatabase


def undated_event(
    event_id: str = "507f1f77bcf86cd799439011",
    **overrides,
) -> dict:
    """A festival date with a re-readable source and no date at all."""

    document = {
        "_id": ObjectId(event_id),
        "title": "Primavera Sound São Paulo Dia 1",
        "event_type": "FestivalInstance",
        "starts_at": None,
        "ends_at": None,
        "venue_slug": "distrito-anhembi",
        "source": {
            "url": (
                "https://www.songkick.com/festivals/"
                "3441108-primavera/id/40385544-primavera-2022"
            )
        },
        "external_ids": {"songkick": "40385544"},
    }

    document.update(overrides)

    return document


SOURCE_READ = {
    "start_date": "2022-10-31",
    "end_date": "2022-11-06",
    "lineup": [
        {
            "name": "Arctic Monkeys",
            "songkick_id": "520117",
            "slug": "arctic-monkeys",
            "url": (
                "https://www.songkick.com/artists/"
                "520117-arctic-monkeys"
            ),
            "image": None,
            "genres": ["rock"],
            "order": 0,
        }
    ],
    "festival": {
        "series_id": "3441108",
        "name": "Primavera Sound São Paulo",
        "url": (
            "https://www.songkick.com/festivals/"
            "3441108-primavera/id/40385544-primavera-2022"
        ),
        "official_url": None,
        "edition": None,
        "tracking_count": None,
        "artist_ids": [],
        "artists": [],
        "image_url": None,
    },
    "venue": {
        "name": "Distrito Anhembi",
        "city": "São Paulo",
        "country": "Brazil",
        "street": "Av. Olavo Fontoura, 1209",
        "postal_code": "02012-02",
    },
    "location": {
        "city": "São Paulo",
        "country": "Brazil",
    },
}


def complete_event(**overrides) -> dict:
    """An event enrichment has already finished with, under every scope.

    A fully populated event is the strongest form of the repeat-run guarantee:
    there is nothing left for any field scope to fill, so a run must find no work
    at all rather than re-reading the source and reporting a change.
    """

    return undated_event(
        date_status=DATE_FROM_SOURCE,
        starts_at=datetime(2022, 10, 31, tzinfo=UTC),
        ends_at=datetime(2022, 11, 6, tzinfo=UTC),
        lineup=[
            {
                "name": "Arctic Monkeys",
                "songkick_id": "520117",
            }
        ],
        location={
            "city": "São Paulo",
            "country": "Brazil",
        },
        festival=SOURCE_READ["festival"],
        **overrides,
    )


class FakeClient:
    """Stands in for the provider, returning a canned source read."""

    def __init__(self, source=None, error=None):
        self.source = (
            SOURCE_READ
            if source is None
            else source
        )
        self.error = error
        self.calls = []

    async def enrich_event_details(self, event):
        self.calls.append(event)

        if self.error:
            raise self.error

        return dict(self.source)


def build(
    documents,
    client=None,
):
    database = FakeDatabase(
        {"events": documents}
    )

    class Repository:
        def __init__(self, db):
            self.db = db
            self.collection = db["events"]

    service = EventEnrichmentService(
        Repository(database),
        client=client or FakeClient(),
    )

    return service, database


def plan_for(service, document) -> EnrichmentPlan:
    return EnrichmentPlan(
        event_id=str(document["_id"]),
        title=document["title"],
        source_url=(
            document.get("source") or {}
        ).get("url"),
        songkick_id="40385544",
    )


class TestApplyingDates:
    """The reason this service exists."""

    @pytest.mark.asyncio
    async def test_iso_date_strings_are_written_as_datetimes(self):
        """The source states ISO strings; they must become real dates.

        This is the bug that left 685 events showing "Date unavailable" even
        after the parser was fixed: the string reached a normaliser that only
        accepted `datetime`, so it was silently dropped.
        """

        document = undated_event()
        service, database = build([document])

        result = await service.enrich_one(
            plan_for(service, document)
        )

        assert result["outcome"] == "updated"

        stored = await database["events"].find_one(
            {"_id": document["_id"]}
        )

        assert stored["starts_at"] == datetime(
            2022, 10, 31, tzinfo=UTC
        )
        assert stored["ends_at"] == datetime(
            2022, 11, 6, tzinfo=UTC
        )
        assert stored["date_status"] == DATE_FROM_SOURCE

    @pytest.mark.asyncio
    async def test_an_existing_date_is_never_overwritten(self):
        """Enrichment fills gaps; it does not second-guess a good value."""

        existing = datetime(2020, 1, 1, tzinfo=UTC)
        document = undated_event(starts_at=existing)
        service, database = build([document])

        await service.enrich_one(plan_for(service, document))

        stored = await database["events"].find_one(
            {"_id": document["_id"]}
        )

        assert stored["starts_at"] == existing

    @pytest.mark.asyncio
    async def test_only_the_missing_end_date_is_filled(self):
        document = undated_event(
            starts_at=datetime(2022, 10, 31, tzinfo=UTC)
        )
        service, database = build([document])

        await service.enrich_one(plan_for(service, document))

        stored = await database["events"].find_one(
            {"_id": document["_id"]}
        )

        assert stored["ends_at"] == datetime(
            2022, 11, 6, tzinfo=UTC
        )

    @pytest.mark.asyncio
    async def test_a_source_without_a_date_stays_undated(self):
        """No date is not a reason to invent one."""

        document = undated_event()
        service, database = build(
            [document],
            client=FakeClient(
                source={
                    "start_date": None,
                    "end_date": None,
                }
            ),
        )

        result = await service.enrich_one(
            plan_for(service, document)
        )

        stored = await database["events"].find_one(
            {"_id": document["_id"]}
        )

        assert stored["starts_at"] is None
        assert stored["date_status"] == DATE_UNAVAILABLE
        assert result["outcome"] == "updated"

    @pytest.mark.asyncio
    async def test_an_unreadable_date_is_a_parser_failure(self):
        """A date-shaped value that cannot be read must not be reported as read."""

        document = undated_event()
        service, database = build(
            [document],
            client=FakeClient(
                source={
                    "start_date": "next Tuesday",
                    "end_date": None,
                }
            ),
        )

        await service.enrich_one(plan_for(service, document))

        stored = await database["events"].find_one(
            {"_id": document["_id"]}
        )

        assert stored["starts_at"] is None
        assert stored["date_status"] == DATE_PARSER_FAILED


class TestIdempotency:
    """A run must be safe to repeat, which is what makes it resumable."""

    @pytest.mark.asyncio
    async def test_a_second_run_writes_nothing(self):
        document = undated_event()
        service, database = build([document])

        first = await service.enrich_one(
            plan_for(service, document)
        )
        second = await service.enrich_one(
            plan_for(service, document)
        )

        assert first["outcome"] == "updated"
        assert second["outcome"] == "unchanged"
        assert second.get("fields") is None

    @pytest.mark.asyncio
    async def test_date_status_is_not_rewritten_with_the_same_value(self):
        """Rewriting an identical value would make every repeat run a change."""

        document = complete_event()
        service, _ = build([document])

        assert (
            await service.enrich_one(plan_for(service, document))
        )["outcome"] == "unchanged"

    @pytest.mark.asyncio
    async def test_a_full_run_over_enriched_events_reports_no_changes(self):
        document = complete_event()
        service, _ = build([document])

        await service.enrich_one(plan_for(service, document))

        client = FakeClient()
        service, _ = build([document], client=client)

        report = await service.run(
            dry_run=False,
            delay_seconds=0,
            fields=DATE_FIELDS,
        )

        assert report.examined == 0
        assert client.calls == []


class TestFieldLevelMerge:
    """Each field is filled only when it is genuinely missing."""

    @pytest.mark.asyncio
    async def test_lineup_is_stored_when_absent(self):
        document = undated_event()
        service, database = build([document])

        await service.enrich_one(plan_for(service, document))

        stored = await database["events"].find_one(
            {"_id": document["_id"]}
        )

        assert stored["lineup"][0]["songkick_id"] == "520117"

    @pytest.mark.asyncio
    async def test_an_existing_lineup_is_kept(self):
        existing = [
            {"name": "Curated Act", "songkick_id": "1"}
        ]
        document = undated_event(lineup=existing)
        service, database = build([document])

        await service.enrich_one(plan_for(service, document))

        stored = await database["events"].find_one(
            {"_id": document["_id"]}
        )

        assert stored["lineup"] == existing

    @pytest.mark.asyncio
    async def test_festival_identity_is_stored_when_absent(self):
        document = undated_event()
        service, database = build([document])

        await service.enrich_one(plan_for(service, document))

        stored = await database["events"].find_one(
            {"_id": document["_id"]}
        )

        assert stored["festival"]["series_id"] == "3441108"

    @pytest.mark.asyncio
    async def test_an_existing_series_is_kept(self):
        """A stored series is the festival's identity and outranks a re-read."""

        document = undated_event(
            festival={"series_id": "999", "name": "Existing"}
        )
        service, database = build([document])

        await service.enrich_one(plan_for(service, document))

        stored = await database["events"].find_one(
            {"_id": document["_id"]}
        )

        assert stored["festival"]["series_id"] == "999"

    @pytest.mark.asyncio
    async def test_location_is_merged_field_by_field(self):
        document = undated_event(
            location={"city": "Curitiba"}
        )
        service, database = build([document])

        await service.enrich_one(plan_for(service, document))

        stored = await database["events"].find_one(
            {"_id": document["_id"]}
        )

        assert stored["location"] == {
            "city": "Curitiba",
            "country": "Brazil",
        }

    @pytest.mark.asyncio
    async def test_venue_fields_are_only_filled_when_absent(self):
        database = FakeDatabase(
            {
                "events": [undated_event()],
                "venues": [
                    {
                        "slug": "distrito-anhembi",
                        "name": "Distrito Anhembi",
                        "city": None,
                        "country": "Brazil",
                    }
                ],
            }
        )

        class Repository:
            def __init__(self, db):
                self.db = db
                self.collection = db["events"]

        service = EventEnrichmentService(
            Repository(database),
            client=FakeClient(),
        )

        document = await database["events"].find_one(
            {"title": "Primavera Sound São Paulo Dia 1"}
        )

        await service.enrich_one(plan_for(service, document))

        venue = await database["venues"].find_one(
            {"slug": "distrito-anhembi"}
        )

        assert venue["name"] == "Distrito Anhembi"
        assert venue["city"] == "São Paulo"
        assert venue["country"] == "Brazil"

    @pytest.mark.asyncio
    async def test_a_venue_that_already_states_everything_is_untouched(self):
        """The repeat-run guarantee, for the venue half of the write."""

        database = FakeDatabase(
            {
                "events": [undated_event()],
                "venues": [
                    {
                        "slug": "distrito-anhembi",
                        "name": "Distrito Anhembi",
                        "city": "São Paulo",
                        "country": "Brazil",
                        "street_address": "Av. Olavo Fontoura",
                        "postal_code": "02012-02",
                    }
                ],
            }
        )

        class Repository:
            def __init__(self, db):
                self.db = db
                self.collection = db["events"]

        service = EventEnrichmentService(
            Repository(database),
            client=FakeClient(),
        )

        document = await database["events"].find_one(
            {"title": "Primavera Sound São Paulo Dia 1"}
        )

        await service.enrich_one(plan_for(service, document))

        assert (
            await service.enrich_one(plan_for(service, document))
        )["outcome"] == "unchanged"

    @pytest.mark.asyncio
    async def test_a_venue_that_does_not_exist_is_not_invented(self):
        """Pointing at a missing venue is a data problem, not a blank to fill."""

        database = FakeDatabase({"events": [undated_event()]})

        class Repository:
            def __init__(self, db):
                self.db = db
                self.collection = db["events"]

        service = EventEnrichmentService(
            Repository(database),
            client=FakeClient(),
        )

        document = await database["events"].find_one(
            {"title": "Primavera Sound São Paulo Dia 1"}
        )

        result = await service.enrich_one(
            plan_for(service, document)
        )

        assert "venue" not in (result.get("fields") or [])
        assert database["venues"].documents == []


class TestFailureIsolation:
    """One bad record must not end a run over hundreds."""

    @pytest.mark.asyncio
    async def test_a_failing_source_is_reported_and_the_run_continues(self):
        first = undated_event("507f1f77bcf86cd799439011")
        second = undated_event("507f1f77bcf86cd799439012")

        client = FakeClient(error=RuntimeError("boom"))
        service, _ = build([first, second], client=client)

        report = await service.run(
            dry_run=False,
            delay_seconds=0,
        )

        assert report.examined == 2
        assert report.failed_source == 2
        assert report.updated == 0
        assert len(report.failures) == 2

    @pytest.mark.asyncio
    async def test_a_failing_write_does_not_raise(self):
        """A database error on one record must be reported, not propagated."""

        document = undated_event()
        service, _ = build([document])

        async def explode(*args, **kwargs):
            raise RuntimeError("write refused")

        service._update_event = explode

        result = await service.enrich_one(
            plan_for(service, document)
        )

        assert result["outcome"] == "write_failed"
        assert "write refused" in result["error"]

    @pytest.mark.asyncio
    async def test_a_write_failure_is_counted_in_the_report(self):
        document = undated_event()
        service, _ = build([document])

        async def explode(*args, **kwargs):
            raise RuntimeError("write refused")

        service._update_event = explode

        report = await service.run(
            dry_run=False,
            delay_seconds=0,
        )

        assert report.write_failures == 1
        assert report.examined == 1


class TestDryRun:
    """Nothing is written unless a write is asked for."""

    @pytest.mark.asyncio
    async def test_a_dry_run_reports_without_writing(self):
        document = undated_event()
        service, database = build([document])

        result = await service.enrich_one(
            plan_for(service, document),
            dry_run=True,
        )

        assert result["outcome"] == "would_update"
        assert "starts_at" in result["fields"]

        stored = await database["events"].find_one(
            {"_id": document["_id"]}
        )

        assert stored["starts_at"] is None

    @pytest.mark.asyncio
    async def test_a_dry_run_still_reads_the_source(self):
        """Finding out whether a date is recoverable requires asking."""

        document = undated_event()
        client = FakeClient()
        service, _ = build([document], client=client)

        await service.run(dry_run=True, delay_seconds=0)

        assert len(client.calls) == 1


class TestPlanning:
    """Which events are worth a source visit, and which cannot be read."""

    @pytest.mark.asyncio
    async def test_an_event_without_a_source_cannot_be_enriched(self):
        document = undated_event(source={})
        service, _ = build([document])

        plan = await service.plan()

        assert plan[0].eligible is False
        assert "source" in plan[0].skip_reason

    @pytest.mark.asyncio
    async def test_a_missing_date_is_a_reason_to_visit(self):
        service, _ = build([undated_event()])

        plan = await service.plan()

        assert "starts_at" in plan[0].reasons

    @pytest.mark.asyncio
    async def test_a_lineup_is_only_sought_for_festivals(self):
        """A concert page carries no lineup; asking it would cost a fetch."""

        concert = undated_event(
            event_type="Concert",
            starts_at=datetime(2022, 10, 31, tzinfo=UTC),
            ends_at=datetime(2022, 10, 31, tzinfo=UTC),
            lineup=[],
        )

        service, _ = build([concert])

        assert await service.plan() == []

    @pytest.mark.asyncio
    async def test_a_festival_with_no_lineup_is_worth_visiting(self):
        festival = undated_event(
            event_type="FestivalInstance",
            starts_at=datetime(2022, 10, 31, tzinfo=UTC),
            ends_at=datetime(2022, 11, 6, tzinfo=UTC),
            lineup=[],
        )

        service, _ = build([festival])

        # The event already has both dates, so only a run that is allowed to
        # revisit dated events would ever reach for its lineup.
        plan = await service.plan(
            fields=["lineup"],
            include_dated=True,
        )

        assert "lineup" in plan[0].reasons

    @pytest.mark.asyncio
    async def test_a_dated_concert_is_left_alone_when_chasing_dates(self):
        """A concert with a start but no end is normal, not a gap to fill."""

        concert = undated_event(
            event_type="Concert",
            starts_at=datetime(2022, 10, 31, tzinfo=UTC),
            ends_at=None,
        )

        service, _ = build([concert])

        assert await service.plan(fields=DATE_FIELDS) == []

    @pytest.mark.asyncio
    async def test_the_limit_is_applied_after_filtering(self):
        """A query limit would cut off candidates before filtering ran."""

        documents = [
            undated_event(
                f"507f1f77bcf86cd79943901{index}"
            )
            for index in range(5)
        ]

        # A concert missing only its end date sorts first but is not a date gap,
        # so a limit applied before filtering would return one of these.
        documents.insert(
            0,
            undated_event(
                "507f1f77bcf86cd799439099",
                event_type="Concert",
                starts_at=datetime(2022, 1, 1, tzinfo=UTC),
                ends_at=None,
            ),
        )

        service, _ = build(documents)

        plan = await service.plan(limit=3)

        assert len(plan) == 3
        assert all(
            "starts_at" in entry.reasons
            for entry in plan
        )


class TestReportOnly:
    """Answering "what could be recovered" without asking the source."""

    @pytest.mark.asyncio
    async def test_the_report_fetches_nothing(self):
        document = undated_event()
        client = FakeClient()
        service, _ = build([document], client=client)

        report = await service.report_only(
            fields=DATE_FIELDS
        )

        assert client.calls == []
        assert report["eligible"] == 1
        assert report["missing_start_date"] == 1

    @pytest.mark.asyncio
    async def test_a_missing_end_date_is_not_reported_as_undated(self):
        """A concert has a start and no end; that is not a date problem.

        Reporting the two as one figure claimed 191 undated events when exactly
        one was undated, which is the kind of number that makes an operator stop
        trusting the report.
        """

        concert = undated_event(
            event_type="Concert",
            starts_at=datetime(2022, 10, 31, tzinfo=UTC),
            ends_at=None,
        )

        service, _ = build([concert])

        report = await service.report_only(
            fields=DATE_FIELDS
        )

        assert report["missing_start_date"] == 0

    @pytest.mark.asyncio
    async def test_an_undated_event_is_reported_as_undated(self):
        service, _ = build([undated_event()])

        report = await service.report_only(
            fields=DATE_FIELDS
        )

        assert report["missing_start_date"] == 1

    @pytest.mark.asyncio
    async def test_unreadable_events_are_counted_separately(self):
        documents = [
            undated_event("507f1f77bcf86cd799439011"),
            undated_event(
                "507f1f77bcf86cd799439012",
                source={},
            ),
        ]

        service, _ = build(documents)

        report = await service.report_only(
            fields=DATE_FIELDS
        )

        assert report["eligible"] == 1
        assert report["no_source"] == 1