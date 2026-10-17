"""The deferred lineup pass: states, claims, and what it may change.

The catalogue persists a festival event the moment its listing arrives, and
this is the pass that later reads the edition's own page for the rest of the
bill. These tests pin the four properties everything else leans on:

* **The event comes first and survives every outcome.** A fetch error, an
  unreadable page, a lost claim - each one leaves the stored row exactly as
  it was and lands a state that says what happened.
* **The state is the queue and the lock.** One atomic claim per event: a
  second worker finds it taken, an abandoned claim expires into a
  takeover, and an attempt budget stops a broken page from being hammered.
* **The pass only ever adds.** A page that states less never shrinks a
  stored lineup, artist slugs join with `$addToSet`, and a stored date is
  never replaced.
* **A pass finishes the bill.** Every performer the page states is stored,
  and every stored performer is held as an artist, in the pass that read
  it - nothing waits for a run that may never come.
* **What the festival page is told never flatters the data.** A stored
  state is reported as it stands; a row nobody read keeps `unknown`.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.services.festival_service import (
    _lineup_state,
    _lineup_state_updated_at,
)
from app.services.lineup_enrichment_service import (
    LineupEnrichmentService,
    STATE_ACTIVE,
    STATE_COMPLETE,
    STATE_EMPTY,
    STATE_FAILED,
    STATE_PARTIAL,
    STATE_PENDING,
)
from tests.support.fake_mongo import FakeDatabase


ADDRESS = (
    "https://www.songkick.com/festivals/"
    "1235-lollapalooza/id/43456086-lollapalooza-2027"
)

ARCTIC = {
    "name": "Arctic Monkeys",
    "songkick_id": "520117",
    "url": None,
    "slug": "arctic-monkeys",
    "image": None,
    "genres": [],
    "order": 0,
}


def festival_event(_id: str = "e1", **overrides) -> dict:
    document = {
        "_id": _id,
        "title": "Lollapalooza 2027",
        "event_type": "FestivalInstance",
        "starts_at": None,
        "ends_at": None,
        "lineup": [],
        "artist_slugs": ["headliner"],
        "external_ids": {"songkick": "43456086"},
        "source": {
            "provider": "songkick",
            "event_id": "43456086",
            "url": ADDRESS,
        },
        "festival": {"series_id": "1235"},
    }

    document.update(overrides)

    return document


def artist(slug: str = "newcomer", songkick_id: str = "222") -> dict:
    """A locally imported artist, in the stored id form the resolver asks for."""

    return {
        "_id": slug,
        "slug": slug,
        "name": slug.replace("-", " ").title(),
        "external_ids": {"songkick": f"Artist{songkick_id}"},
    }


class PageClient:
    """Stands in for the single request `enrich_event_details` makes."""

    def __init__(self, answer: dict | None = None, error: Exception | None = None):
        self.answer = {} if answer is None else answer
        self.error = error
        self.requests: list[dict] = []

    async def enrich_event_details(self, event):
        self.requests.append(dict(event))

        if self.error is not None:
            raise self.error

        # A new dict, the way the real client answers: the same payload
        # object handed back means "nothing could be read" and is refused.
        return dict(self.answer)


class ImportReport:
    def __init__(self, failed: int = 0):
        self.failed = failed


class StubImporter:
    """Records which entries were turned into artist stubs."""

    def __init__(self, failed: int = 0, error: Exception | None = None):
        self.calls: list[list] = []
        self.failed = failed
        self.error = error

    async def ensure_for_entries(self, entries):
        batch = list(entries)
        self.calls.append(batch)

        if self.error is not None:
            raise self.error

        return ImportReport(self.failed)


class ArtistRepositoryStub:
    """The slice of the artist repository the resolver reads."""

    def __init__(self, database):
        self.collection = database["artists"]


def build(
    events: list[dict],
    *,
    artists: list[dict] | None = None,
    client: PageClient | None = None,
    importer: StubImporter | None = None,
    **service_kwargs,
):
    database = FakeDatabase({"events": events, "artists": artists or []})

    client = client or PageClient()
    importer = importer if importer is not None else StubImporter()

    service = LineupEnrichmentService(
        db=database,
        client_factory=lambda: client,
        artist_repository=ArtistRepositoryStub(database),
        lineup_importer=importer,
        **service_kwargs,
    )

    return service, database, client, importer


class TestEnqueue:
    @pytest.mark.asyncio
    async def test_a_legacy_edition_joins_the_queue(self):
        service, database, _, _ = build([festival_event()])

        state = await service.enqueue("e1")

        assert state == STATE_PENDING

        stored = await database.events.find_one({"_id": "e1"})
        assert stored["lineup_state"] == STATE_PENDING
        assert isinstance(stored["lineup_state_updated_at"], datetime)

    @pytest.mark.asyncio
    async def test_finished_work_is_not_re_enqueued(self):
        service, database, _, _ = build(
            [festival_event(lineup_state=STATE_COMPLETE)]
        )

        state = await service.enqueue("e1")

        assert state == STATE_COMPLETE

        stored = await database.events.find_one({"_id": "e1"})
        assert stored["lineup_state"] == STATE_COMPLETE

    @pytest.mark.asyncio
    async def test_a_missing_event_has_no_state_to_report(self):
        service, _, _, _ = build([festival_event()])

        assert await service.enqueue("nope") is None

    @pytest.mark.asyncio
    async def test_a_forced_retry_re_enqueues_and_resets_the_budget(self):
        service, database, _, _ = build(
            [
                festival_event(
                    lineup_state=STATE_FAILED,
                    lineup_enrichment={
                        "owner": "dead",
                        "attempts": 3,
                        "error": "boom",
                        "updated_at": datetime.now(UTC),
                    },
                )
            ]
        )

        state = await service.enqueue("e1", force=True)

        assert state == STATE_PENDING

        stored = await database.events.find_one({"_id": "e1"})
        assert stored["lineup_state"] == STATE_PENDING
        assert stored["lineup_enrichment"]["attempts"] == 0

    @pytest.mark.asyncio
    async def test_a_forced_retry_never_steals_a_fresh_claim(self):
        service, database, _, _ = build(
            [
                festival_event(
                    lineup_state=STATE_ACTIVE,
                    lineup_enrichment={
                        "owner": "reading-now",
                        "attempts": 1,
                        "updated_at": datetime.now(UTC),
                    },
                )
            ]
        )

        state = await service.enqueue("e1", force=True)

        assert state == STATE_ACTIVE

        stored = await database.events.find_one({"_id": "e1"})
        assert stored["lineup_state"] == STATE_ACTIVE
        assert stored["lineup_enrichment"]["owner"] == "reading-now"

    @pytest.mark.asyncio
    async def test_a_stale_claim_can_be_requeued(self):
        service, database, _, _ = build(
            [
                festival_event(
                    lineup_state=STATE_ACTIVE,
                    lineup_enrichment={
                        "owner": "died-reading",
                        "attempts": 1,
                        "updated_at": datetime.now(UTC) - timedelta(hours=2),
                    },
                )
            ],
            lease_seconds=600,
        )

        state = await service.enqueue("e1", force=True)

        assert state == STATE_PENDING

    @pytest.mark.asyncio
    async def test_only_festival_editions_are_queued_from_a_run(self):
        concert = festival_event(
            _id="c1",
            event_type="Concert",
            external_ids={"songkick": "999"},
        )
        service, database, _, _ = build([festival_event(), concert])

        queued = await service.enqueue_events(["43456086", "999", "unknown"])

        assert queued == ["e1"]

        stored_concert = await database.events.find_one({"_id": "c1"})
        assert "lineup_state" not in stored_concert


class TestClaiming:
    @pytest.mark.asyncio
    async def test_the_claim_moves_pending_to_active_with_an_owner(self):
        service, database, _, _ = build(
            [festival_event(lineup_state=STATE_PENDING)]
        )

        claimed = await service._claim("e1", "worker-a")

        assert claimed is not None
        assert claimed["lineup_state"] == STATE_ACTIVE
        assert claimed["lineup_enrichment"]["owner"] == "worker-a"
        assert claimed["lineup_enrichment"]["attempts"] == 1

    @pytest.mark.asyncio
    async def test_a_second_worker_finds_the_event_taken(self):
        service, _, _, _ = build(
            [festival_event(lineup_state=STATE_PENDING)]
        )

        assert await service._claim("e1", "worker-a") is not None
        assert await service._claim("e1", "worker-b") is None

    @pytest.mark.asyncio
    async def test_an_abandoned_claim_is_taken_over_and_counted(self):
        service, _, _, _ = build(
            [
                festival_event(
                    lineup_state=STATE_ACTIVE,
                    lineup_enrichment={
                        "owner": "died",
                        "attempts": 1,
                        "updated_at": datetime.now(UTC) - timedelta(hours=2),
                    },
                )
            ],
            lease_seconds=600,
        )

        claimed = await service._claim("e1", "worker-b")

        assert claimed is not None
        assert claimed["lineup_enrichment"]["owner"] == "worker-b"
        assert claimed["lineup_enrichment"]["attempts"] == 2

    @pytest.mark.asyncio
    async def test_a_failed_event_stops_retrying_itself_at_the_budget(self):
        service, _, _, _ = build(
            [
                festival_event(
                    lineup_state=STATE_FAILED,
                    lineup_enrichment={
                        "owner": "dead",
                        "attempts": 3,
                        "updated_at": datetime.now(UTC),
                    },
                )
            ],
            max_attempts=3,
        )

        assert await service._claim("e1", "worker-a") is None

    @pytest.mark.asyncio
    async def test_a_missing_event_is_not_claimable(self):
        service, _, _, _ = build([festival_event()])

        assert await service._claim("nope", "worker-a") is None


class TestThePass:
    @pytest.mark.asyncio
    async def test_a_page_read_adds_what_it_announces(self):
        service, database, client, importer = build(
            [festival_event(lineup=[dict(ARCTIC)])],
            artists=[artist()],
            client=PageClient(
                {
                    "lineup": [
                        dict(ARCTIC),
                        {
                            "name": "Newcomer",
                            "songkick_id": "222",
                            "url": None,
                            "slug": None,
                            "image": None,
                            "genres": [],
                            "order": 1,
                        },
                    ],
                    "date_status": "source",
                }
            ),
        )

        state = await service.process("e1")

        assert state == STATE_COMPLETE

        stored = await database.events.find_one({"_id": "e1"})
        names = [entry["name"] for entry in stored["lineup"]]
        assert names == ["Arctic Monkeys", "Newcomer"]
        assert "newcomer" in stored["artist_slugs"]
        # The stored association is never replaced, only extended.
        assert "headliner" in stored["artist_slugs"]
        assert stored["lineup_enrichment"]["error"] is None

        # The whole merged bill is handed to the importer, and it is the
        # importer's own resolve step - not this pass - that skips the
        # artists that already exist: the known name is never re-checked
        # with a fetch, and the new one is created in this same pass.
        handed_over = [
            entry["name"] for entry in importer.calls[0]
        ]
        assert handed_over == ["Arctic Monkeys", "Newcomer"]

        # The request carried the event's own address.
        assert client.requests[0]["url"] == ADDRESS

    @pytest.mark.asyncio
    async def test_a_page_that_states_less_never_shrinks_the_bill(self):
        stored_before = [
            dict(ARCTIC),
            {**dict(ARCTIC), "songkick_id": "7", "name": "Second Act", "order": 1},
        ]
        service, database, _, importer = build(
            [festival_event(lineup=stored_before)],
            client=PageClient({"lineup": [dict(ARCTIC)]}),
        )

        state = await service.process("e1")

        assert state == STATE_COMPLETE

        stored = await database.events.find_one({"_id": "e1"})
        names = [entry["name"] for entry in stored["lineup"]]
        assert names == ["Arctic Monkeys", "Second Act"]
        # The page stated nothing new, but the stored bill still goes to
        # the importer: if any of its artists were missing, this read is
        # where they are made real. The importer skips what already exists.
        assert [
            entry["name"] for entry in importer.calls[0]
        ] == ["Arctic Monkeys", "Second Act"]

    @pytest.mark.asyncio
    async def test_a_finished_read_that_announces_no_one_is_empty(self):
        service, database, _, _ = build([festival_event()])

        state = await service.process("e1")

        assert state == STATE_EMPTY

        stored = await database.events.find_one({"_id": "e1"})
        assert stored["lineup"] == []

    @pytest.mark.asyncio
    async def test_a_fetch_error_marks_failed_and_keeps_the_event(self):
        service, database, client, _ = build(
            [festival_event(lineup=[dict(ARCTIC)], starts_at=None)],
            client=PageClient(error=RuntimeError("boom")),
        )

        state = await service.process("e1")

        assert state == STATE_FAILED

        stored = await database.events.find_one({"_id": "e1"})
        assert stored["lineup_state"] == STATE_FAILED
        assert "RuntimeError" in stored["lineup_enrichment"]["error"]
        # The event row itself is exactly as it was.
        assert [entry["name"] for entry in stored["lineup"]] == ["Arctic Monkeys"]
        assert stored["starts_at"] is None
        assert stored["lineup_enrichment"]["attempts"] == 1
        assert len(client.requests) == 1

    @pytest.mark.asyncio
    async def test_an_unreadable_page_marks_failed(self):
        service, database, _, _ = build(
            [festival_event()],
            client=PageClient({"date_status": "parser_failed"}),
        )

        state = await service.process("e1")

        assert state == STATE_FAILED

        stored = await database.events.find_one({"_id": "e1"})
        assert "structured data" in stored["lineup_enrichment"]["error"]

    @pytest.mark.asyncio
    async def test_an_edition_without_any_address_fails_without_a_request(self):
        service, database, client, _ = build(
            [
                festival_event(
                    source={"provider": "songkick", "event_id": "43456086"},
                    festival={"series_id": "1235"},
                )
            ],
        )

        state = await service.process("e1")

        assert state == STATE_FAILED
        assert client.requests == []

        stored = await database.events.find_one({"_id": "e1"})
        assert "no source address" in stored["lineup_enrichment"]["error"]

    @pytest.mark.asyncio
    async def test_an_undated_edition_gets_the_date_the_page_states(self):
        service, database, _, _ = build(
            [festival_event()],
            client=PageClient(
                {"start_date": "2027-07-24", "date_status": "source"}
            ),
        )

        await service.process("e1")

        stored = await database.events.find_one({"_id": "e1"})
        assert stored["starts_at"] == datetime(2027, 7, 24, tzinfo=UTC)
        assert stored["date_status"] == "source"

    @pytest.mark.asyncio
    async def test_a_stored_date_is_never_replaced(self):
        stored_date = datetime(2026, 1, 1, tzinfo=UTC)
        service, database, _, _ = build(
            [festival_event(starts_at=stored_date)],
            client=PageClient(
                {"start_date": "2027-07-24", "date_status": "source"}
            ),
        )

        await service.process("e1")

        stored = await database.events.find_one({"_id": "e1"})
        assert stored["starts_at"] == stored_date

    @pytest.mark.asyncio
    async def test_a_page_read_that_states_no_date_records_that(self):
        service, database, _, _ = build(
            [festival_event()],
            client=PageClient({"date_status": "unavailable"}),
        )

        await service.process("e1")

        stored = await database.events.find_one({"_id": "e1"})
        assert stored["starts_at"] is None
        assert stored["date_status"] == "unavailable"

    @pytest.mark.asyncio
    async def test_a_lost_claim_is_not_overwritten(self):
        service, database, _, _ = build(
            [festival_event(lineup_state=STATE_PENDING)]
        )

        assert await service._claim("e1", "worker-a") is not None

        # Somebody took the event over while worker-a was still reading.
        await database.events.update_one(
            {"_id": "e1"},
            {"$set": {"lineup_enrichment.owner": "worker-b"}},
        )

        outcome = await service._finish("e1", "worker-a", STATE_COMPLETE)

        assert outcome == "lost"

        stored = await database.events.find_one({"_id": "e1"})
        # The newer owner's view of the event stands.
        assert stored["lineup_state"] == STATE_ACTIVE
        assert stored["lineup_enrichment"]["owner"] == "worker-b"

    @pytest.mark.asyncio
    async def test_the_first_pass_makes_every_announced_artist_real(self):
        second = {**dict(ARCTIC), "songkick_id": "222", "name": "Newcomer", "slug": None, "order": 1}
        third = {**dict(ARCTIC), "songkick_id": "333", "name": "Third Act", "slug": None, "order": 2}
        service, database, _, importer = build(
            [festival_event(lineup=[dict(ARCTIC)])],
            artists=[artist()],
            client=PageClient(
                {"lineup": [dict(ARCTIC), second, third]}
            ),
        )

        state = await service.process("e1")

        # The whole bill is stored and the whole bill is made real in one
        # pass. Nothing is left "for the next pass": a later pass would find
        # these names already stored, see nothing fresh, and create no
        # artist for them ever.
        assert state == STATE_COMPLETE

        stored = await database.events.find_one({"_id": "e1"})
        assert [entry["name"] for entry in stored["lineup"]] == [
            "Arctic Monkeys",
            "Newcomer",
            "Third Act",
        ]

        assert len(importer.calls) == 1
        assert [entry["name"] for entry in importer.calls[0]] == [
            "Arctic Monkeys",
            "Newcomer",
            "Third Act",
        ]

    @pytest.mark.asyncio
    async def test_a_stored_bill_missing_its_artists_completes_on_a_read(self):
        # The shape an earlier per-run cap left behind: the bill is stored,
        # its artists are not, and the page states nothing new. A pass that
        # looked only at fresh names would create nothing; the importer is
        # handed the stored bill instead, and the missing artist is made
        # real on this read.
        stored_entry = {
            **dict(ARCTIC),
            "songkick_id": "777",
            "name": "Early Name",
            "slug": "early-name",
        }
        service, database, _, importer = build(
            [festival_event(lineup=[stored_entry])],
            client=PageClient({"lineup": [stored_entry]}),
        )

        state = await service.process("e1")

        assert state == STATE_COMPLETE
        assert len(importer.calls) == 1
        assert [entry["name"] for entry in importer.calls[0]] == [
            "Early Name",
        ]

    @pytest.mark.asyncio
    async def test_an_importer_failure_keeps_the_bill_and_marks_partial(self):
        service, database, _, _ = build(
            [festival_event()],
            artists=[artist()],
            client=PageClient(
                {
                    "lineup": [
                        {
                            "name": "Newcomer",
                            "songkick_id": "222",
                            "url": None,
                            "slug": None,
                            "image": None,
                            "genres": [],
                            "order": 0,
                        }
                    ]
                }
            ),
            importer=StubImporter(error=RuntimeError("stub down")),
        )

        state = await service.process("e1")

        assert state == STATE_PARTIAL

        stored = await database.events.find_one({"_id": "e1"})
        assert [entry["name"] for entry in stored["lineup"]] == ["Newcomer"]

    @pytest.mark.asyncio
    async def test_attempts_stop_at_the_budget_until_a_forced_retry(self):
        service, database, client, _ = build(
            [festival_event()],
            client=PageClient(error=RuntimeError("down")),
            max_attempts=3,
        )

        assert await service.process("e1") == STATE_FAILED
        assert await service.process("e1") == STATE_FAILED
        assert await service.process("e1") == STATE_FAILED
        requests_so_far = len(client.requests)
        assert requests_so_far == 3

        # Out of budget: the next pass is not even started.
        assert await service.process("e1") == STATE_FAILED
        assert len(client.requests) == requests_so_far

        # A person asks for a retry, and the budget starts over.
        await service.enqueue("e1", force=True)
        assert await service.process("e1") == STATE_FAILED
        assert len(client.requests) == requests_so_far + 1

    @pytest.mark.asyncio
    async def test_a_run_processes_every_edition_it_was_given(self):
        service, database, client, _ = build(
            [
                festival_event(_id="e1"),
                festival_event(_id="e2", external_ids={"songkick": "43456088"}),
            ],
            client=PageClient({"date_status": "unavailable"}),
        )

        outcomes = await service.process_batch(["e1", "e2"])

        assert outcomes == {
            "e1": STATE_EMPTY,
            "e2": STATE_EMPTY,
        }
        assert len(client.requests) == 2

        # And a second run over the same, finished editions reads nothing.
        outcomes = await service.process_batch(["e1", "e2"])
        assert outcomes == {"e1": STATE_EMPTY, "e2": STATE_EMPTY}
        assert len(client.requests) == 2


    @pytest.mark.asyncio
    async def test_a_batch_logs_one_line_with_size_and_duration(self, caplog):
        """The drain used to run for minutes without a trace.

        One summary line per batch is what lets a reader tell a normal pass
        from a queue that has become a scraper - without a write per event.
        """
        service, database, client, _ = build(
            [
                festival_event(_id="e1"),
                festival_event(_id="e2", external_ids={"songkick": "43456088"}),
            ],
            client=PageClient({"date_status": "unavailable"}),
        )

        with caplog.at_level("INFO", logger="lineup_enrichment"):
            await service.process_batch(["e1", "e2"])

        lines = [
            record.message
            for record in caplog.records
            if "batch finished" in record.message
        ]

        assert len(lines) == 1
        assert "2 edition(s)" in lines[0]
        assert " in " in lines[0] and "s |" in lines[0]
        assert "empty=2" in lines[0]


class TestWhatThePageIsTold:
    """The festival page's `lineup_state` never flatters the data."""

    def test_a_finished_pass_reads_as_ok(self):
        assert _lineup_state([], {"lineup_state": STATE_COMPLETE}) == "ok"

    @pytest.mark.parametrize(
        "stored",
        [STATE_PENDING, STATE_ACTIVE, STATE_PARTIAL, STATE_FAILED, STATE_EMPTY],
    )
    def test_work_in_progress_is_reported_as_it_stands(self, stored):
        assert _lineup_state([], {"lineup_state": stored}) == stored

    def test_a_legacy_lineup_keeps_the_old_reading(self):
        assert _lineup_state([{"name": "Arctic Monkeys"}], {}) == "ok"

    def test_a_legacy_empty_lineup_is_still_unknown(self):
        # No state means nobody recorded the work - it never means the
        # source announced no one.
        assert _lineup_state([], {}) == "unknown"
        assert _lineup_state([], None) == "unknown"

    def test_an_unrecognized_stored_state_never_upgrades_the_reading(self):
        assert _lineup_state([], {"lineup_state": "mystery"}) == "unknown"

    def test_the_moment_is_reported_only_when_recorded(self):
        moment = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)

        assert _lineup_state_updated_at({"lineup_state_updated_at": moment}) is moment
        assert _lineup_state_updated_at({"lineup_state": "complete"}) is None
        assert _lineup_state_updated_at({"lineup_state_updated_at": "yesterday"}) is None
        assert _lineup_state_updated_at(None) is None
