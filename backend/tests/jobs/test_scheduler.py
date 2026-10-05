"""The background enrichment scheduler.

These tests drive the real scheduler, the real job and the real enrichment
service against a fake database and a fake provider client. Nothing here opens
a socket, so the suite never depends on Songkick being reachable.

What is being pinned down is the behaviour a scheduler is trusted to have:
it stays off until configuration turns it on, it only visits events that are
genuinely missing something, it stays inside its batch, it paces itself, and it
keeps going when a single event fails.
"""
from __future__ import annotations

import asyncio

from datetime import UTC, datetime

import pytest
from bson import ObjectId

from app.jobs.enrichment_job import (
    EnrichmentJobConfig,
    resolve_fields,
    run_enrichment_once,
)
from app.jobs.scheduler import EnrichmentScheduler
from app.services.event_enrichment_service import (
    DATE_FROM_SOURCE,
    DATE_PARSER_FAILED,
    DATE_UNAVAILABLE,
    EventEnrichmentService,
)
from tests.support.fake_mongo import FakeDatabase


SOURCE_READ = {
    "start_date": "2022-10-31",
    "end_date": "2022-11-06",
    "lineup": [
        {
            "name": "Arctic Monkeys",
            "songkick_id": "520117",
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


class RecordingClient:
    """Stands in for Songkick and records every visit.

    The suite must never reach the network, and the number of visits is itself
    an assertion in several tests below, so the client counts as well as
    responds.
    """

    def __init__(self, source=None, errors=None):
        self.source = SOURCE_READ if source is None else source
        # Keyed by the event id in the URL, so one event can fail while the
        # rest of the batch succeeds.
        self.errors = errors or {}
        self.calls: list[str] = []

    async def enrich_event_details(self, event):
        url = (event or {}).get("url") or ""

        self.calls.append(url)

        if url in self.errors:
            raise self.errors[url]

        return dict(self.source)


class RecordingRepository:
    """The slice of the event repository the enrichment service uses."""

    def __init__(self, db):
        self.db = db
        self.collection = db["events"]


def build(documents, client=None):
    database = FakeDatabase({"events": list(documents)})

    service = EventEnrichmentService(
        RecordingRepository(database),
        client=client or RecordingClient(),
    )

    return service, database


def undated_event(index: int = 1, **overrides) -> dict:
    """A festival date with a re-readable source and no date."""

    event_id = f"507f1f77bcf86cd7994390{index:02d}"

    document = {
        "_id": ObjectId(event_id),
        "title": f"Festival day {index}",
        "event_type": "FestivalInstance",
        "starts_at": None,
        "ends_at": None,
        "venue_slug": "distrito-anhembi",
        "source": {
            "url": f"https://www.songkick.com/festivals/x/id/{event_id}"
        },
        "external_ids": {"songkick": event_id},
    }

    document.update(overrides)

    return document


def complete_event(index: int = 1) -> dict:
    """An event enrichment has nothing left to do on."""

    from datetime import UTC, datetime

    return undated_event(
        index,
        date_status=DATE_FROM_SOURCE,
        starts_at=datetime(2022, 10, 31, tzinfo=UTC),
        ends_at=datetime(2022, 11, 6, tzinfo=UTC),
        lineup=[{"name": "Arctic Monkeys", "songkick_id": "520117"}],
        location={"city": "São Paulo", "country": "Brazil"},
    )


class TestTheJobRunsTheExistingService:
    """The scheduler orchestrates; the service decides."""

    @pytest.mark.asyncio
    async def test_a_pass_reaches_the_source_and_writes_the_date(self):
        service, database = build([undated_event()])

        result = await run_enrichment_once(
            service,
            EnrichmentJobConfig(delay_seconds=0),
        )

        assert result.selected == 1
        assert result.attempted == 1
        assert result.updated == 1

        stored = await database["events"].find_one(
            {"title": "Festival day 1"}
        )

        assert stored["date_status"] == DATE_FROM_SOURCE
        assert stored["starts_at"] is not None

    @pytest.mark.asyncio
    async def test_the_job_never_reimplements_the_field_merge(self):
        """A valid stored value must survive a scheduled pass untouched."""

        from datetime import UTC, datetime

        existing = datetime(2019, 5, 1, tzinfo=UTC)

        service, database = build([
            undated_event(starts_at=existing)
        ])

        await run_enrichment_once(
            service,
            EnrichmentJobConfig(delay_seconds=0),
        )

        stored = await database["events"].find_one(
            {"title": "Festival day 1"}
        )

        # The source said 2022. The stored 2019 date is kept, and the end date
        # is filled in beside it.
        assert stored["starts_at"] == existing
        assert stored["ends_at"] is not None

    @pytest.mark.asyncio
    async def test_a_complete_event_is_not_visited(self):
        client = RecordingClient()
        service, _ = build([complete_event()], client=client)

        result = await run_enrichment_once(
            service,
            EnrichmentJobConfig(
                delay_seconds=0,
                fields=None,
                include_dated=True,
            ),
        )

        # Nothing was missing, so nothing was selected and the provider was
        # never asked.
        assert result.selected == 0
        assert result.attempted == 0
        assert client.calls == []


class TestSelection:
    """What a pass is allowed to choose."""

    @pytest.mark.asyncio
    async def test_an_undated_event_is_selected_for_dates(self):
        service, _ = build([undated_event()])

        result = await run_enrichment_once(
            service,
            EnrichmentJobConfig(
                delay_seconds=0,
                fields=["starts_at", "ends_at"],
            ),
        )

        assert result.selected == 1

    @pytest.mark.asyncio
    async def test_a_parser_failure_is_selected_again(self):
        """A parser problem is exactly what a later pass should retry."""

        service, _ = build([
            undated_event(date_status=DATE_PARSER_FAILED)
        ])

        result = await run_enrichment_once(
            service,
            EnrichmentJobConfig(
                delay_seconds=0,
                fields=["starts_at", "ends_at"],
            ),
        )

        assert result.selected == 1

    @pytest.mark.asyncio
    async def test_a_genuinely_undated_source_is_not_asked_again(self):
        """A source read that confirmed no date is not asked again.

        Selecting it again would spend a request every pass to be told the same
        thing, which is the difference between a scheduler that makes progress
        and one that hammers Songkick forever.

        Settling takes both halves: `unavailable` says the source has no date,
        and `date_source_checked_at` says somebody went and looked. The importer
        writes the first on its own, from a listing that merely carried no date,
        so only the pair settles a row.
        """

        client = RecordingClient()
        service, _ = build(
            [
                undated_event(
                    date_status=DATE_UNAVAILABLE,
                    date_source_checked_at=datetime(
                        2026, 1, 1, tzinfo=UTC
                    ),
                )
            ],
            client=client,
        )

        result = await run_enrichment_once(
            service,
            EnrichmentJobConfig(
                delay_seconds=0,
                fields=["starts_at", "ends_at"],
            ),
        )

        assert result.selected == 0
        assert client.calls == []

    @pytest.mark.asyncio
    async def test_an_unavailable_date_no_one_checked_is_asked(self):
        """`unavailable` on its own is not the end of the road.

        This is the case that left fifty festival dates permanently unrecoverable:
        the importer stamped them from an artist gigography listing, and the
        scheduler trusted it, so their own pages - which carry the real dates -
        were never read.
        """

        client = RecordingClient()
        service, _ = build(
            [undated_event(date_status=DATE_UNAVAILABLE)],
            client=client,
        )

        result = await run_enrichment_once(
            service,
            EnrichmentJobConfig(
                delay_seconds=0,
                fields=["starts_at", "ends_at"],
            ),
        )

        assert result.selected == 1
        assert len(client.calls) == 1

    @pytest.mark.asyncio
    async def test_a_dated_event_is_left_alone_by_a_date_pass(self):
        """Re-reading a dated event would be a request with nothing to gain."""

        client = RecordingClient()
        service, _ = build([complete_event()], client=client)

        result = await run_enrichment_once(
            service,
            EnrichmentJobConfig(
                delay_seconds=0,
                fields=["starts_at", "ends_at"],
            ),
        )

        assert result.selected == 0
        assert client.calls == []

    @pytest.mark.asyncio
    async def test_a_dated_event_can_still_be_asked_for_a_lineup(self):
        """A dated festival with no lineup is exactly the lower-priority work."""

        from datetime import UTC, datetime

        service, database = build([
            undated_event(
                date_status=DATE_FROM_SOURCE,
                starts_at=datetime(2022, 10, 31, tzinfo=UTC),
                ends_at=datetime(2022, 11, 6, tzinfo=UTC),
            )
        ])

        result = await run_enrichment_once(
            service,
            EnrichmentJobConfig(
                delay_seconds=0,
                fields=["lineup"],
                include_dated=True,
            ),
        )

        assert result.selected == 1

        stored = await database["events"].find_one(
            {"title": "Festival day 1"}
        )

        assert stored["lineup"][0]["songkick_id"] == "520117"

    @pytest.mark.asyncio
    async def test_a_dated_event_can_still_be_asked_for_a_location(self):
        from datetime import UTC, datetime

        service, database = build([
            undated_event(
                date_status=DATE_FROM_SOURCE,
                starts_at=datetime(2022, 10, 31, tzinfo=UTC),
                ends_at=datetime(2022, 11, 6, tzinfo=UTC),
                lineup=[{"name": "Arctic Monkeys"}],
            )
        ])

        result = await run_enrichment_once(
            service,
            EnrichmentJobConfig(
                delay_seconds=0,
                fields=["location"],
                include_dated=True,
            ),
        )

        assert result.selected == 1

        stored = await database["events"].find_one(
            {"title": "Festival day 1"}
        )

        assert stored["location"]["city"] == "São Paulo"

    @pytest.mark.asyncio
    async def test_a_concert_is_not_asked_for_a_lineup(self):
        """Only a festival page carries a lineup, so only a festival is asked.

        Fetching a concert's page to discover it has no lineup would cost a
        request and return nothing.
        """

        client = RecordingClient()
        service, _ = build([
            undated_event(event_type="Concert"),
        ], client=client)

        result = await run_enrichment_once(
            service,
            EnrichmentJobConfig(
                delay_seconds=0,
                fields=["lineup"],
                include_dated=True,
            ),
        )

        assert result.selected == 0
        assert client.calls == []

    @pytest.mark.asyncio
    async def test_an_event_with_no_source_is_reported_separately(self):
        """Unfixable and unlucky are different problems."""

        service, _ = build([
            undated_event(source={}, external_ids={}),
        ])

        result = await run_enrichment_once(
            service,
            EnrichmentJobConfig(delay_seconds=0),
        )

        assert result.selected == 1
        assert result.attempted == 0
        assert result.source_missing == 1


class TestBoundingAndPacing:
    """A scheduled pass must be small and must not rush."""

    @pytest.mark.asyncio
    async def test_a_pass_never_exceeds_its_batch_size(self):
        client = RecordingClient()
        service, _ = build(
            [undated_event(index) for index in range(1, 9)],
            client=client,
        )

        result = await run_enrichment_once(
            service,
            EnrichmentJobConfig(batch_size=3, delay_seconds=0),
        )

        assert result.selected == 3
        assert result.attempted == 3
        assert len(client.calls) == 3

    @pytest.mark.asyncio
    async def test_the_configured_delay_is_observed_between_requests(self):
        slept: list[float] = []

        async def record(seconds):
            slept.append(seconds)

        original = asyncio.sleep

        asyncio.sleep = record

        try:
            service, _ = build(
                [undated_event(index) for index in range(1, 4)]
            )

            await run_enrichment_once(
                service,
                EnrichmentJobConfig(
                    batch_size=3,
                    delay_seconds=0.25,
                ),
            )

        finally:
            asyncio.sleep = original

        # Three events means two gaps: the pass must not sleep before its
        # first request.
        assert slept == [0.25, 0.25]

    @pytest.mark.asyncio
    async def test_a_single_event_pass_does_not_sleep_at_all(self):
        original = asyncio.sleep

        async def fail(*args, **kwargs):
            raise AssertionError("a pass must not sleep before its first request")

        asyncio.sleep = fail

        try:
            service, _ = build([undated_event()])

            result = await run_enrichment_once(
                service,
                EnrichmentJobConfig(delay_seconds=5),
            )

        finally:
            asyncio.sleep = original

        assert result.updated == 1

    @pytest.mark.asyncio
    async def test_a_dry_run_writes_nothing(self):
        service, database = build([undated_event()])

        result = await run_enrichment_once(
            service,
            EnrichmentJobConfig(
                delay_seconds=0,
                dry_run=True,
            ),
        )

        stored = await database["events"].find_one(
            {"title": "Festival day 1"}
        )

        assert stored["starts_at"] is None
        assert result.updated == 1


class TestFailureTolerance:
    """One bad event must not end a pass over a batch."""

    @pytest.mark.asyncio
    async def test_a_pass_continues_after_an_unreachable_source(self):
        broken = undated_event(1)["source"]["url"]

        client = RecordingClient(
            errors={broken: RuntimeError("connection reset")}
        )

        service, database = build(
            [undated_event(1), undated_event(2), undated_event(3)],
            client=client,
        )

        result = await run_enrichment_once(
            service,
            EnrichmentJobConfig(delay_seconds=0),
        )

        assert result.attempted == 3
        assert result.request_failed == 1
        assert result.updated == 2

        # The two healthy events were still written.
        stored = await database["events"].find_one(
            {"title": "Festival day 3"}
        )

        assert stored["date_status"] == DATE_FROM_SOURCE

    @pytest.mark.asyncio
    async def test_a_pass_continues_after_an_unparseable_response(self):
        """A source read that yields nothing is a parse failure, not a crash."""

        client = RecordingClient(source={})

        service, _ = build(
            [undated_event(1), undated_event(2)],
            client=client,
        )

        result = await run_enrichment_once(
            service,
            EnrichmentJobConfig(delay_seconds=0),
        )

        assert result.attempted == 2
        assert result.parse_failed == 2

    @pytest.mark.asyncio
    async def test_an_unexpected_error_on_one_event_does_not_end_the_pass(self):
        """A failure outside the source call must still be survivable."""

        service, _ = build([undated_event(1)])

        original = service.enrich_one

        async def sometimes_broken(plan, dry_run=False):
            raise RuntimeError("database went away")

        service.enrich_one = sometimes_broken

        result = await run_enrichment_once(
            service,
            EnrichmentJobConfig(delay_seconds=0),
        )

        assert result.request_failed == 1
        assert result.attempted == 1

        service.enrich_one = original

    @pytest.mark.asyncio
    async def test_a_failure_to_select_is_reported_rather_than_raised(self):
        """The database being unreachable must not become an unhandled error."""

        service, _ = build([undated_event()])

        async def broken_plan(*args, **kwargs):
            raise RuntimeError("mongo is down")

        service.plan = broken_plan

        result = await run_enrichment_once(
            service,
            EnrichmentJobConfig(delay_seconds=0),
        )

        assert result.selected == 0
        assert result.failures[0]["stage"] == "select"

    @pytest.mark.asyncio
    async def test_a_rejected_write_is_counted_as_a_write_failure(self):
        """A database rejection is a different problem from a bad page."""

        from pymongo.errors import DuplicateKeyError

        service, _ = build([undated_event()])

        original = service._update_event

        async def rejected(event_id, patch):
            raise DuplicateKeyError("duplicate")

        service._update_event = rejected

        result = await run_enrichment_once(
            service,
            EnrichmentJobConfig(delay_seconds=0),
        )

        assert result.write_failed == 1

        service._update_event = original


class TestRepeatedPasses:
    """A pass must converge rather than repeat itself."""

    @pytest.mark.asyncio
    async def test_a_second_pass_finds_nothing_left_to_do(self):
        service, _ = build([undated_event(1), undated_event(2)])

        first = await run_enrichment_once(
            service,
            EnrichmentJobConfig(
                delay_seconds=0,
                fields=["starts_at", "ends_at"],
            ),
        )

        assert first.updated == 2

        second = await run_enrichment_once(
            service,
            EnrichmentJobConfig(
                delay_seconds=0,
                fields=["starts_at", "ends_at"],
            ),
        )

        # The work left the candidate set, so the next pass costs nothing and
        # asks the provider nothing.
        assert second.selected == 0
        assert second.attempted == 0
        assert second.is_quiet

    @pytest.mark.asyncio
    async def test_a_failed_event_is_still_a_candidate_next_pass(self):
        """Resumability: a row that failed is retried, not abandoned."""

        broken = undated_event(1)["source"]["url"]

        client = RecordingClient(
            errors={broken: RuntimeError("temporary failure")}
        )

        service, _ = build(
            [undated_event(1), undated_event(2)],
            client=client,
        )

        first = await run_enrichment_once(
            service,
            EnrichmentJobConfig(delay_seconds=0),
        )

        assert first.request_failed == 1
        assert first.updated == 1

        # The source recovers; the pass that failed is now ordinary work.
        client.errors = {}

        second = await run_enrichment_once(
            service,
            EnrichmentJobConfig(delay_seconds=0),
        )

        assert second.selected == 1
        assert second.updated == 1


class TestFieldModes:
    """The scheduler speaks the enrichment service's own vocabulary."""

    def test_each_mode_maps_to_the_service_field_lists(self):
        from app.services.event_enrichment_service import (
            ALL_ENRICHABLE_FIELDS,
            DATE_FIELDS,
            LINEUP_FIELDS,
            LOCATION_FIELDS,
        )

        assert resolve_fields("dates") == DATE_FIELDS
        assert resolve_fields("lineup") == LINEUP_FIELDS
        assert resolve_fields("location") == LOCATION_FIELDS
        assert resolve_fields("all") == ALL_ENRICHABLE_FIELDS

    def test_an_unset_mode_means_every_field(self):
        assert resolve_fields(None) is None

    def test_the_mode_is_not_case_or_space_sensitive(self):
        assert resolve_fields("  Dates ") == ["starts_at", "ends_at"]

    def test_an_unknown_mode_is_refused(self):
        # Spending Songkick requests on the wrong fields is worse than refusing
        # to start.
        with pytest.raises(ValueError):
            resolve_fields("everything")

    def test_a_scheduler_with_a_bad_mode_refuses_to_be_built(self):
        with pytest.raises(ValueError):
            EnrichmentScheduler(enabled=True, fields="everything")


class TestTheSchedulerIsOffUnlessAsked:
    """The development-safety rule."""

    @pytest.mark.asyncio
    async def test_a_disabled_scheduler_does_not_start(self):
        calls: list[int] = []

        async def runner(service, config):
            calls.append(1)
            return None

        scheduler = EnrichmentScheduler(
            enabled=False,
            service_factory=lambda: object(),
            job_runner=runner,
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

        An operator asking for one pass explicitly is not the same as the process
        deciding to make requests on its own, and the manual path is what the
        runbook and the CLI both rely on.
        """

        calls: list[int] = []

        async def runner(service, config):
            calls.append(1)
            return None

        scheduler = EnrichmentScheduler(
            enabled=False,
            service_factory=lambda: object(),
            job_runner=runner,
        )

        await scheduler.run()

        assert calls == [1]

        scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_a_disabled_scheduler_reports_itself_as_off(self):
        scheduler = EnrichmentScheduler(enabled=False)

        status = scheduler.get_status()

        assert status["enabled"] is False
        assert status["running"] is False
        assert status["next_run_at"] is None

    @pytest.mark.asyncio
    async def test_an_enabled_scheduler_starts(self):
        scheduler = EnrichmentScheduler(
            enabled=True,
            interval_minutes=60,
            service_factory=lambda: object(),
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
        scheduler = EnrichmentScheduler(
            enabled=True,
            service_factory=lambda: object(),
        )

        try:
            assert scheduler.start() is True
            assert scheduler.start() is False

        finally:
            scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_shutting_down_before_starting_is_safe(self):
        scheduler = EnrichmentScheduler(enabled=True)

        # Startup can fail after the scheduler exists; shutdown must not then
        # raise on the way out.
        scheduler.shutdown()
        scheduler.shutdown()


class TestTheSchedulerDrivesTheJob:
    """The wiring between the scheduler, the job and the service."""

    @pytest.mark.asyncio
    async def test_a_pass_invokes_the_enrichment_service(self):
        client = RecordingClient()
        service, database = build([undated_event()], client=client)

        scheduler = EnrichmentScheduler(
            enabled=False,
            service_factory=lambda: service,
        )

        result = await scheduler.run()

        assert result is not None
        assert result.updated == 1
        assert len(client.calls) == 1

        stored = await database["events"].find_one(
            {"title": "Festival day 1"}
        )

        assert stored["starts_at"] is not None

        scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_the_scheduler_passes_its_configuration_to_the_job(self):
        seen: list[EnrichmentJobConfig] = []

        async def runner(service, config):
            seen.append(config)
            return None

        scheduler = EnrichmentScheduler(
            enabled=True,
            batch_size=7,
            delay_seconds=0.1,
            fields="lineup",
            include_dated=True,
            service_factory=lambda: object(),
            job_runner=runner,
        )

        try:
            await scheduler.run()

        finally:
            scheduler.shutdown()

        config = seen[0]

        assert config.batch_size == 7
        assert config.delay_seconds == 0.1
        assert config.fields == ["lineup"]
        assert config.include_dated is True

    @pytest.mark.asyncio
    async def test_passes_do_not_overlap(self):
        """A pass that overruns must not be joined by a second one."""

        started = 0
        finished = 0

        async def slow_runner(service, config):
            nonlocal started, finished

            started += 1

            await asyncio.sleep(0.05)

            finished += 1

        scheduler = EnrichmentScheduler(
            enabled=True,
            service_factory=lambda: object(),
            job_runner=slow_runner,
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
    async def test_a_broken_job_does_not_propagate(self):
        """A scheduler must never raise into its own executor."""

        async def runner(service, config):
            raise RuntimeError("the job is broken")

        scheduler = EnrichmentScheduler(
            enabled=True,
            service_factory=lambda: object(),
            job_runner=runner,
        )

        try:
            assert await scheduler.run() is None

        finally:
            scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_a_service_that_cannot_be_built_is_reported(self):
        def broken_factory():
            raise RuntimeError("no database")

        scheduler = EnrichmentScheduler(
            enabled=True,
            service_factory=broken_factory,
        )

        try:
            assert await scheduler.run() is None

        finally:
            scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_the_status_reports_the_last_pass_without_secrets(self):
        service, _ = build([undated_event()])

        scheduler = EnrichmentScheduler(
            enabled=False,
            fields="dates",
            service_factory=lambda: service,
        )

        await scheduler.run()

        status = scheduler.get_status()

        assert status["last_run"]["updated"] == 1
        assert status["last_run"]["selected"] == 1

        # The reported payload must not carry a source URL or any credential.
        rendered = repr(status)

        assert "songkick.com" not in rendered
        assert "password" not in rendered.lower()

        scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_a_pass_on_startup_runs_once_and_then_waits(self):
        calls: list[int] = []

        async def runner(service, config):
            calls.append(1)
            return None

        scheduler = EnrichmentScheduler(
            enabled=True,
            interval_minutes=60,
            run_on_startup=True,
            service_factory=lambda: object(),
            job_runner=runner,
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


class TestTheApplicationWiresItUp:
    """The scheduler has to be real in the running app, not just in a test."""

    def test_the_application_builds_one_scheduler_from_settings(self):
        from app.main import app, scheduler

        assert scheduler is not None
        assert isinstance(scheduler, EnrichmentScheduler)

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
        from app.jobs.scheduler import create_scheduler

        # Settings defaults are the development-safety guarantee, so they are
        # asserted directly rather than through the environment.
        defaults = Settings.model_fields

        assert (
            defaults["ENRICHMENT_SCHEDULER_ENABLED"].default is False
        )
        assert (
            defaults["ENRICHMENT_SCHEDULER_RUN_ON_STARTUP"].default is False
        )

    def test_every_scheduler_setting_exists_and_has_a_default(self):
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
        ):
            assert name in fields, name
