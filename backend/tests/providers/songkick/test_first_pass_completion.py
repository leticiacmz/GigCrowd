"""One extraction finishes what the pages it paid for cannot state.

An import buys a fixed set of pages: the artist page, the calendar, the
gigography and the search results. Between them they carry nearly everything
about nearly every event, joined by id in `test_extraction_first.py`. What they
cannot carry is two things that exist only on an event's own page: a festival's
lineup, and a listing Songkick published with no date on it.

Those pages used to be read by a later, scheduled pass, which meant the run
that created the row was never the run that finished it. They are read here,
during the same run, and this file pins the rules that keep that bounded and
honest:

* an event that arrived complete costs nothing - no request, no count;
* one request per event however many fields it is missing, most incomplete
  first, so the bound is spent where a reader would notice;
* a bound, and an honest count of what the bound left unread;
* the result lands on the event every other list is holding, not on a copy;
* a page that fails is reported where it failed and changes nothing.
"""
from __future__ import annotations

import json

import pytest

from app.providers.songkick.client import SongkickClient


# ============================================================
# FIXTURES
# ============================================================

EVENT_ID = "43155855"
EVENT_PATH = f"/concerts/{EVENT_ID}-strokes-at-o2"
EVENT_URL = f"https://www.songkick.com{EVENT_PATH}"

FESTIVAL_ID = "40385544"
FESTIVAL_PATH = (
    f"/festivals/3441108-primavera-sound/id/{FESTIVAL_ID}-primavera"
)
FESTIVAL_URL = f"https://www.songkick.com{FESTIVAL_PATH}"

ARTIST_ID = "34230"
ARTIST_URL = f"https://www.songkick.com/artists/{ARTIST_ID}-the-strokes"

START = "2027-03-25T19:00:00+0000"


def an_event(**overrides) -> dict:
    """A listing as the calendar leaves it: a URL, a venue, and usually a date."""

    event = {
        "songkick_id": EVENT_ID,
        "name": "The Strokes at The O2",
        "event_type": "Concert",
        "url": EVENT_URL,
        "start_date": START,
        "end_date": None,
        "date_status": "source",
        "venue": {"name": "The O2", "city": "London"},
        "lineup": [],
    }

    event.update(overrides)

    return event


def an_undated_event(**overrides) -> dict:
    """The shape the whole model exists for: no date anywhere in the readings."""

    return an_event(
        start_date=None,
        date_status=None,
        **overrides,
    )


def a_festival(**overrides) -> dict:
    """A festival listing with a date and a venue, and no announced bill."""

    return an_event(
        songkick_id=FESTIVAL_ID,
        name="Primavera Sound",
        url=FESTIVAL_URL,
        event_type="festival",
        is_festival=True,
        lineup=[],
        **overrides,
    )


def a_page(*, start: str | None = START, performers: list | None = None):
    """An event's own page, as its structured block states it."""

    block = {
        "@context": "http://schema.org",
        "@type": "MusicEvent",
        "name": "The Strokes at The O2",
        "url": EVENT_URL,
        "location": {
            "@type": "Place",
            "name": "The O2",
            "address": {
                "addressLocality": "London",
                "addressCountry": "United Kingdom",
            },
        },
    }

    if start:
        block["startDate"] = start

    if performers:
        block["performer"] = performers

    return (
        "<html><head>"
        f'<script type="application/ld+json">{json.dumps(block)}</script>'
        "</head><body></body></html>"
    )


class StubClient(SongkickClient):
    """A client whose site is a dict of canned responses, request by request."""

    def __init__(self, site: dict):
        super().__init__()
        self.site = site
        self.requested: list[str] = []

    async def _request(self, url: str, **kwargs):
        self.requested.append(url)

        body = self.site.get(url)

        if body is None:
            return type(
                "Response",
                (),
                {"status_code": 404, "text": "", "url": url},
            )()

        return type(
            "Response",
            (),
            {"status_code": 200, "text": body, "url": url},
        )()

    async def search_artist_full(self, query: str) -> dict:
        return {"artists": [], "top_results": []}


async def complete(events, site=None) -> tuple[list, dict]:
    """Run the completion step over `events` against a canned site."""

    client = StubClient(site if site is not None else {})

    return await client._complete_missing_fields(events)


# ============================================================
# 1. WHAT IS READ, AND WHAT IS NOT
# ============================================================


class TestWhatIsWorthOneRequest:

    @pytest.mark.asyncio
    async def test_an_undated_event_has_its_own_page_read_in_the_same_run(
        self,
    ):
        """The core rule: the run that creates the row finishes it.

        A listing with no date is not a decision to store an undated event; it
        is an event whose date lives one page away. Reading it here means
        nobody has to come back, and the report says what was done.
        """

        events = [an_undated_event()]

        completed, extraction = await complete(
            events,
            site={EVENT_URL: a_page()},
        )

        assert completed[0]["start_date"] == START
        assert completed[0]["date_status"] == "source"

        assert extraction["event_pages_read"] == 1
        assert extraction["event_pages_skipped"] == 0
        assert extraction["event_pages_failed"] == 0
        assert extraction["limit"] == 25

    @pytest.mark.asyncio
    async def test_a_complete_event_costs_nothing(self):
        """The request budget the whole design exists to protect.

        A scrape of a complete catalogue must stay inside the pages it pays
        for anyway, or the fix for a rare gap becomes a cost on every event.
        """

        completed, extraction = await complete(
            [an_event(), an_event(songkick_id="43155856")],
            site={EVENT_URL: a_page()},
        )

        assert extraction["event_pages_read"] == 0
        assert extraction["event_pages_skipped"] == 0

        assert completed[0]["start_date"] == START

    @pytest.mark.asyncio
    async def test_one_request_covers_every_field_that_is_missing(self):
        """Three missing fields are one page, not three.

        The page either states them or it does not; asking twice for the same
        document would buy nothing but a second chance to fail.
        """

        events = [
            an_undated_event(
                venue=None,
                lineup=[],
                event_type="festival",
                is_festival=True,
            )
        ]

        client = StubClient({EVENT_URL: a_page(performers=[])})

        _, extraction = await client._complete_missing_fields(events)

        assert client.requested == [EVENT_URL]
        assert extraction["event_pages_read"] == 1

    @pytest.mark.asyncio
    async def test_a_festival_bill_arrives_from_its_own_page(self):
        """The lineup is the reason festivals are worth the request.

        A calendar row announces a festival; the festival page announces who
        is playing. Without this read, a lineup could never be complete on the
        run that imported it - only on some later one.
        """

        performers = [
            {
                "@type": "MusicGroup",
                "name": "The Hives",
                "sameAs": (
                    "https://www.songkick.com/artists/115276-the-hives"
                ),
            }
        ]

        completed, extraction = await complete(
            [a_festival()],
            site={
                FESTIVAL_URL: a_page(performers=performers).replace(
                    EVENT_URL,
                    FESTIVAL_URL,
                )
            },
        )

        assert extraction["event_pages_read"] == 1
        assert [entry["name"] for entry in completed[0]["lineup"]] == [
            "The Hives"
        ]

    @pytest.mark.asyncio
    async def test_a_livestream_is_never_asked_for_a_venue(self):
        """An event that is supposed to be placeless is not missing one.

        Without this, every livestream in the catalogue would spend the bound
        on a page that cannot help it.
        """

        events = [
            an_event(
                is_live_stream=True,
                venue=None,
                location={"city": None},
            )
        ]

        completed, extraction = await complete(events)

        assert extraction["event_pages_read"] == 0
        assert completed[0]["venue"] is None

    @pytest.mark.asyncio
    async def test_an_event_with_no_url_is_not_invented_a_source(self):
        """Nothing to read means nothing to read.

        A listing that carried no URL cannot be completed by asking again, and
        the run must not synthesise an address to visit.
        """

        events = [an_undated_event(url=None)]

        completed, extraction = await complete(events)

        assert extraction["event_pages_read"] == 0
        assert completed[0]["start_date"] is None


# ============================================================
# 2. THE BOUND
# ============================================================


class TestTheBoundIsSpentAndHonest:

    @pytest.mark.asyncio
    async def test_reads_stop_at_the_bound_and_the_rest_are_counted(
        self,
        monkeypatch,
    ):
        """A catalogue full of undated listings must not become a flood.

        The bound is a promise about one scrape, so the events past it are
        reported as unread - counted, not silently dropped, and never queued
        for a later pass.
        """

        from app.config import settings

        monkeypatch.setattr(
            settings,
            "SONGKICK_EVENT_PAGE_READS_PER_SCRAPE",
            2,
        )

        events = [
            an_undated_event(songkick_id=str(4000 + index))
            for index in range(5)
        ]

        completed, extraction = await complete(
            events,
            site={EVENT_URL: a_page()},
        )

        assert extraction["event_pages_read"] == 2
        assert extraction["event_pages_skipped"] == 3
        assert extraction["limit"] == 2

        # Read or not, every event still holds what the listings stated.
        assert all(
            event["venue"]["name"] == "The O2" for event in completed
        )

    @pytest.mark.asyncio
    async def test_the_bound_spends_itself_on_the_most_incomplete_first(
        self,
        monkeypatch,
    ):
        """Spending the bound on an ordinary event is spending it wrong."""

        from app.config import settings

        monkeypatch.setattr(
            settings,
            "SONGKICK_EVENT_PAGE_READS_PER_SCRAPE",
            1,
        )

        ordinary = an_event(songkick_id="4001")
        ordinary["venue"] = None

        thorough = an_undated_event(
            songkick_id="4002",
            venue=None,
            lineup=[],
            event_type="festival",
            is_festival=True,
        )

        completed, extraction = await complete(
            [ordinary, thorough],
            site={EVENT_URL: a_page()},
        )

        assert extraction["event_pages_read"] == 1

        # The festival was the one read: it is the one now holding a date.
        assert completed[1]["start_date"] == START
        assert completed[0]["venue"] is None

    @pytest.mark.asyncio
    async def test_a_zero_bound_reads_only_the_pages_already_paid_for(
        self,
        monkeypatch,
    ):
        """The escape hatch, and its cost made explicit.

        With the bound at zero the scrape is exactly what it costs today, and
        the events that needed a page are still reported rather than quietly
        considered complete.
        """

        from app.config import settings

        monkeypatch.setattr(
            settings,
            "SONGKICK_EVENT_PAGE_READS_PER_SCRAPE",
            0,
        )

        _, extraction = await complete([an_undated_event()])

        assert extraction["event_pages_read"] == 0
        assert extraction["limit"] == 0


# ============================================================
# 3. WHAT COMES BACK IS PUT WHERE EVERYONE CAN SEE IT
# ============================================================


class TestTheResultLandsOnTheEventItself:

    @pytest.mark.asyncio
    async def test_the_completion_updates_the_dict_the_other_lists_hold(self):
        """A response holds one event in several lists.

        Replacing the dict would leave `upcoming` and `upcoming_festivals`
        describing the event as it was before the page was read, which is how
        two parts of one response disagree about the same event id.
        """

        original = an_undated_event()

        upcoming = [original]
        merged = upcoming  # the same object, as scrape_artist holds it

        completed, _ = await complete(
            merged,
            site={EVENT_URL: a_page()},
        )

        assert completed[0] is original
        assert upcoming[0]["start_date"] == START

    @pytest.mark.asyncio
    async def test_a_page_that_states_no_date_does_not_contradict_the_date_we_hold(
        self,
    ):
        """The status follows the dates actually held.

        The event's page may simply not repeat a date the calendar stated.
        Recording "unavailable" beside a real date is the contradiction the
        rest of the lifecycle treats as a settled answer, so the status is
        repaired rather than left to disagree with the record.
        """

        listing = an_event(
            venue=None,
            date_status="source",
        )

        completed, extraction = await complete(
            [listing],
            site={EVENT_URL: a_page(start=None)},
        )

        assert completed[0]["start_date"] == START
        assert completed[0]["date_status"] == "source"
        assert extraction["event_pages_read"] == 1

    @pytest.mark.asyncio
    async def test_a_failed_page_changes_nothing_and_is_counted(self):
        """A source that does not answer is reported where it happened.

        Nothing is invented in its place, the event keeps what the listings
        said, and the failure is a number the import can report rather than a
        silence an operator has to notice.
        """

        event = an_undated_event()

        completed, extraction = await complete([event], site={})

        assert extraction["event_pages_read"] == 1
        assert extraction["event_pages_failed"] == 1
        assert completed[0]["start_date"] is None


# ============================================================
# 4. A FULL SCRAPE, REQUEST BY REQUEST
# ============================================================


def a_site() -> dict:
    """The artist's pages, with a listing whose date is not on any of them."""

    undated_row = (
        f'<li class="event-listing-item">'
        f'<a href="{EVENT_PATH}">London, UK The O2</a></li>'
    )

    dateless_block = {
        "@context": "http://schema.org",
        "@type": "MusicEvent",
        "name": "The Strokes at The O2",
        "url": EVENT_URL,
        "location": {"@type": "Place", "name": "The O2"},
    }

    return {
        ARTIST_URL: (
            "<html><head>"
            '<meta property="og:title" content="The Strokes">'
            f'<script type="application/ld+json">'
            f"{json.dumps(dateless_block)}"
            "</script></head><body></body></html>"
        ),
        f"{ARTIST_URL}/calendar": (
            "<html><head>"
            f'<script type="application/ld+json">'
            f"{json.dumps(dateless_block)}"
            "</script></head>"
            f"<body><ul>{undated_row}</ul></body></html>"
        ),
        f"{ARTIST_URL}/gigography": (
            "<html><body></body></html>"
        ),
        EVENT_URL: a_page(),
    }


class TestTheScrapeFinishesWhatTheListingCannot:

    @pytest.mark.asyncio
    async def test_the_undated_listing_is_completed_in_the_same_run(self):
        """End to end: the row, the read, and the date, in one scrape.

        The four pages the scrape pays for cannot date this event, so the
        event's own page is read once - inside this call - and the event
        comes back dated. Nobody is owed anything afterwards.
        """

        client = StubClient(a_site())

        data = await client.scrape_artist(
            "The Strokes", artist_id=f"Artist{ARTIST_ID}"
        )

        assert len(data["events"]) == 1

        event = data["events"][0]

        assert event["start_date"] == START
        assert event["date_status"] == "source"

        # Exactly one extra request, for the one event that needed it.
        assert client.requested.count(EVENT_URL) == 1
        assert len(client.requested) == 4

        assert data["extraction"]["event_pages_read"] == 1
        assert data["extraction"]["event_pages_skipped"] == 0
        assert data["extraction"]["event_pages_failed"] == 0
