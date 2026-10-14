"""Extraction is the first lever: read what the paid-for pages already say.

An import buys a fixed set of pages - the artist page, the calendar, the
gigography - and each of them carries structured data about the events it
renders. Joining that data onto the listing rows costs nothing, because the
scripts were already inside the responses. Fetching each event's own page
afterwards to recover the same facts costs one request per event, and it is
the reason an import used to be both slower and thinner than the pages it had
already read.

Two properties make the join safe, and both are pinned here:

* it is done by event id, never by position or by name, because the listing
  and the structured block do not necessarily appear in the same order;
* it fills gaps rather than overwriting, so a resync cannot lose a field the
  previous read had found - with one stated exception, where a *rendered*
  reading ("Greenwich, UK The O2") is replaced by the value the source
  publishes for that id.

The third property is the one an operator feels: the request budget. One
festival page is fetched once, and a full artist scrape stays inside the
pages it already reads.
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

ARTIST_ID = "34230"
ARTIST_URL = f"https://www.songkick.com/artists/{ARTIST_ID}-the-strokes"

START = "2027-03-25T19:00:00+0000"

IMAGE = (
    "https://images.sk-static.com/images/media/img/events/"
    "43155855/huge_avatar"
)

# What the event's own structured block states: a title, a venue with an
# address, a description, a photograph, a status and the announced bill.
CONCERT_JSONLD = {
    "@context": "http://schema.org",
    "@type": "MusicEvent",
    "name": "The Strokes at The O2",
    "url": EVENT_URL,
    "startDate": START,
    "eventStatus": "https://schema.org/EventScheduled",
    "description": "The Strokes play The O2 with special guests.",
    "image": IMAGE,
    "location": {
        "@type": "Place",
        "name": "The O2",
        "address": {
            "@type": "PostalAddress",
            "streetAddress": "Peninsula Square",
            "addressLocality": "London",
            "addressCountry": "United Kingdom",
            "postalCode": "SE10 0DX",
        },
    },
    "performer": [
        {
            "@type": "MusicGroup",
            "name": "The Strokes",
            "genre": ["indie_rock"],
            "sameAs": (
                "https://www.songkick.com/artists/"
                "34230-the-strokes"
            ),
        },
        {
            "@type": "MusicGroup",
            "name": "The Hives",
            "genre": ["garage_rock"],
            "sameAs": (
                "https://www.songkick.com/artists/"
                "115276-the-hives"
            ),
        },
    ],
    "offers": {
        "@type": "Offer",
        "url": f"{EVENT_URL}/tickets",
    },
}

# The listing row for the same event: a date, a URL, and link text that is a
# city, a country and a venue written as one string.
CALENDAR_ROW = f"""
<li class="event-listing-item" title="Thursday 25 March 2027">
  <time datetime="{START}"></time>
  <a href="{EVENT_PATH}">Greenwich, UK The O2</a>
</li>
"""


def calendar_page(*, with_structured_data: bool = True) -> str:
    """A calendar page as the artist's /calendar returns it.

    The row appears twice, because Songkick renders every entry twice; the
    parser deduplicates by event id and must still join the structured block
    to the surviving row.
    """

    block = (
        (
            '<script type="application/ld+json">'
            f"{json.dumps(CONCERT_JSONLD)}"
            "</script>"
        )
        if with_structured_data
        else ""
    )

    return f"""
    <html><head>{block}</head><body>
      <ul class="event-listings">
        {CALENDAR_ROW}
        {CALENDAR_ROW}
      </ul>
    </body></html>
    """


def artist_page() -> str:
    """The artist's own page: a #coming-up preview and the same block."""

    return f"""
    <html><head>
      <meta property="og:title" content="The Strokes">
      <script type="application/ld+json">
        {json.dumps(CONCERT_JSONLD)}
      </script>
    </head><body>
      <div id="coming-up">
        <ul>
          <li class="event-listing-item">
            <a class="event-details" href="{EVENT_PATH}">
              Greenwich, UK The O2
            </a>
          </li>
        </ul>
      </div>
    </body></html>
    """


def pages() -> dict:
    """Everything a full scrape reads, and nothing else."""

    return {
        ARTIST_URL: artist_page(),
        f"{ARTIST_URL}/calendar": calendar_page(),
        f"{ARTIST_URL}/gigography": (
            "<html><body></body></html>"
        ),
    }


class StubClient(SongkickClient):
    """A client whose site is a dict of canned responses.

    Every request is recorded, which is what makes the request budget
    assertable: a test can say how many times a URL was asked for, not just
    what came back.
    """

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
                {
                    "status_code": 404,
                    "text": "",
                    "url": url,
                },
            )()

        return type(
            "Response",
            (),
            {
                "status_code": 200,
                "text": body,
                "url": url,
            },
        )()

    async def search_artist_full(self, query: str) -> dict:
        return {"artists": [], "top_results": []}


def parse(html: str) -> list[dict]:
    return SongkickClient._parse_calendar_page(
        html,
        f"{ARTIST_URL}/calendar",
    )


# ============================================================
# 1. A LISTING AND ITS OWN STRUCTURED DATA ARE JOINED BY ID
# ============================================================


class TestThePageIsReadForWhatItAlreadySays:

    def test_a_calendar_row_gains_the_venue_the_page_states(self):
        events = parse(calendar_page())

        assert len(events) == 1

        venue = events[0]["venue"]

        assert venue["name"] == "The O2"
        assert venue["address"]["addressLocality"] == "London"

    def test_a_calendar_row_gains_the_description_and_the_photograph(self):
        events = parse(calendar_page())

        assert events[0]["description"] == (
            "The Strokes play The O2 with special guests."
        )
        assert events[0]["songkick_image"] == IMAGE
        assert events[0]["event_status"] == (
            "https://schema.org/EventScheduled"
        )

    def test_the_title_is_the_one_the_source_publishes(self):
        """The link text is rendered for the reader, not written as a title.

        "Greenwich, UK The O2" is a place, not an event name, and it is what
        every calendar-derived event used to be called.
        """

        events = parse(calendar_page())

        assert events[0]["name"] == "The Strokes at The O2"

    def test_the_listing_keeps_the_date_it_stated(self):
        events = parse(calendar_page())

        assert events[0]["start_date"] == START

    def test_the_announced_bill_arrives_with_the_row(self):
        events = parse(calendar_page())

        lineup = events[0]["lineup"]

        assert [entry["name"] for entry in lineup] == [
            "The Strokes",
            "The Hives",
        ]
        assert lineup[0]["songkick_id"] == ARTIST_ID

    def test_the_joined_reading_reaches_the_domain_object(self):
        """The whole chain, because a field that stops at the payload is lost.

        Description, photograph and status used to be written straight onto
        the document by enrichment, so the domain object never knew about
        them and a resync could not carry them forward.
        """

        from app.mappers.songkick_event_mapper import (
            SongkickEventMapper,
        )

        payload = parse(calendar_page())[0]

        event, venue = SongkickEventMapper.to_domain(
            payload,
            ["the-strokes"],
        )

        assert event.description == (
            "The Strokes play The O2 with special guests."
        )
        assert event.image_url == IMAGE
        assert event.event_status == (
            "https://schema.org/EventScheduled"
        )
        assert event.location == {
            "city": "London",
            "country": "United Kingdom",
        }
        assert venue.name == "The O2"
        assert venue.city == "London"
        assert venue.external_ids == {}  # no address-derived id is invented

    def test_two_renderings_of_one_row_still_collapse_to_one_event(self):
        events = parse(calendar_page())

        assert len(events) == 1
        assert events[0]["songkick_id"] == EVENT_ID

    def test_a_page_without_structured_data_states_nothing_it_did_not_say(self):
        """Absence has to stay absence: no description, no photograph.

        Otherwise a client would render an empty image where the source simply
        published none, and the field would stop meaning anything.
        """

        events = parse(calendar_page(with_structured_data=False))

        assert len(events) == 1
        assert events[0]["description"] is None
        assert events[0]["songkick_image"] is None
        assert events[0]["event_status"] is None
        assert events[0]["start_date"] == START


# ============================================================
# 2. THE JOIN FILLS GAPS AND NEVER OVERWRITES
# ============================================================


class TestTheJoinOnlyFillsGaps:

    @staticmethod
    def reading(**overrides) -> dict:
        """A structured reading of one event."""

        payload = {
            "id": EVENT_ID,
            "songkick_id": EVENT_ID,
            "name": "A title",
            "start_date": START,
            "end_date": None,
            "date_status": "source",
            "description": None,
            "songkick_image": None,
            "venue": None,
            "raw": {"@type": "MusicEvent"},
        }
        payload.update(overrides)
        return payload

    @staticmethod
    def listing(**overrides) -> dict:
        """A listing row: what the markup renders, no raw block at all."""

        payload = {
            "id": EVENT_ID,
            "songkick_id": EVENT_ID,
            "name": "Greenwich, UK The O2",
            "start_date": START,
            "end_date": None,
            "description": None,
            "songkick_image": None,
            "venue": {"name": "Greenwich, UK The O2"},
            "raw": None,
        }
        payload.update(overrides)
        return payload

    def test_a_field_the_first_reading_already_stated_is_kept(self):
        merged = SongkickClient._merge_event_details(
            self.listing(start_date="2027-03-25T19:00:00+0000"),
            self.reading(
                start_date="2027-03-26T19:00:00+0000",
                description="from the structured block",
            ),
        )

        assert merged["start_date"] == "2027-03-25T19:00:00+0000"
        assert merged["description"] == (
            "from the structured block"
        )

    def test_a_rendered_title_yields_to_a_structured_one(self):
        merged = SongkickClient._merge_event_details(
            self.listing(),
            self.reading(name="The Strokes at The O2"),
        )

        assert merged["name"] == "The Strokes at The O2"

    def test_a_rendered_venue_yields_to_a_structured_one(self):
        """The link text is not a venue name, so it must not survive one.

        Left alone, a calendar-derived event kept a venue called
        "Greenwich, UK The O2" even though the page beside it said "The O2"
        with a full address - the join would have added the address to a
        venue the source never named.
        """

        merged = SongkickClient._merge_event_details(
            self.listing(),
            self.reading(
                venue={
                    "name": "The O2",
                    "address": {"addressLocality": "London"},
                },
            ),
        )

        assert merged["venue"]["name"] == "The O2"

    def test_two_structured_readings_keep_the_first(self):
        first = self.reading(description="first")
        second = self.reading(description="second")

        merged = SongkickClient._merge_event_details(first, second)

        assert merged["description"] == "first"

    def test_the_merge_is_idempotent(self):
        """Reading the same page twice must not change the answer.

        An import runs again on every sync, so a merge that drifted on the
        second application would make each resync disagree with the last.
        """

        base = self.listing()
        extra = self.reading(
            description="from the block",
            venue={"name": "The O2"},
        )

        once = SongkickClient._merge_event_details(base, extra)
        twice = SongkickClient._merge_event_details(once, extra)

        assert twice == once

    def test_nothing_is_invented_when_there_is_no_second_reading(self):
        base = self.listing()

        merged = SongkickClient._merge_event_details(base, None)

        assert merged is base

    def test_a_dateless_block_does_not_call_a_dated_listing_unavailable(self):
        """A status is a claim about *these* dates.

        A structured block that carries no `startDate` reports "unavailable",
        which is correct for it. Inherited onto a listing whose `<time>` did
        state a date, the same word would file a dated event as dateless -
        and "unavailable" beside a real date is exactly the contradiction the
        rest of the lifecycle treats as a settled answer.
        """

        merged = SongkickClient._merge_event_details(
            self.listing(date_status=None),
            self.reading(
                start_date=None,
                end_date=None,
                date_status="unavailable",
            ),
        )

        assert merged["start_date"] == START
        assert merged.get("date_status") in (None, "source")

    def test_a_status_is_inherited_when_neither_reading_has_a_date(self):
        merged = SongkickClient._merge_event_details(
            self.listing(start_date=None, date_status=None),
            self.reading(
                start_date=None,
                end_date=None,
                date_status="unavailable",
            ),
        )

        assert merged["date_status"] == "unavailable"
        assert merged["start_date"] is None


# ============================================================
# 3. ONE PAGE, ONE REQUEST
# ============================================================


FESTIVAL_URL = (
    "https://www.songkick.com/festivals/"
    "3441108-primavera-sound-sao-paulo-dia-1"
    "/id/40385544-primavera-sound-so-paulo-dia-1-2022"
)

FESTIVAL_JSONLD = [
    {
        "@context": "http://schema.org",
        "@type": "MusicEvent",
        "name": "Primavera Sound Sao Paulo Dia 1",
        "url": FESTIVAL_URL,
        "startDate": "2027-10-31",
        "endDate": "2027-11-06",
        "eventStatus": "https://schema.org/EventScheduled",
        "location": {
            "@type": "Place",
            "name": "Distrito Anhembi",
            "address": {
                "@type": "PostalAddress",
                "addressLocality": "Sao Paulo",
                "addressCountry": "Brazil",
            },
        },
        "performer": [
            {
                "@type": "MusicGroup",
                "name": "Arctic Monkeys",
                "genre": ["rock"],
                "sameAs": (
                    "https://www.songkick.com/artists/"
                    "520117-arctic-monkeys"
                ),
            },
            {
                "@type": "MusicGroup",
                "name": "Pixies",
                "genre": ["rock"],
                "sameAs": (
                    "https://www.songkick.com/artists/"
                    "271757-pixies"
                ),
            },
        ],
    }
]

# The rendered lineup, in the order the page shows it, with the ids hanging
# off the element itself rather than a nested anchor.
FESTIVAL_LINEUP_HTML = """
<div class="artist-profile" href="/artists/520117-arctic-monkeys">
  <span class="artist-name">Arctic Monkeys</span>
</div>
<div class="artist-profile" href="/artists/271757-pixies">
  <span class="artist-name">Pixies</span>
</div>
"""


def festival_page() -> str:
    return f"""<html><head>
      <script type="application/ld+json">{json.dumps(FESTIVAL_JSONLD)}</script>
    </head><body>
      <h1>Primavera Sound Sao Paulo</h1>
      <div class="lineup-list">{FESTIVAL_LINEUP_HTML}</div>
    </body></html>"""


class TestAFestivalPageIsReadOnce:

    @pytest.mark.asyncio
    async def test_the_lineup_comes_from_the_page_already_fetched(self):
        """Two requests for one document was the normal case.

        Enrichment fetched an event's page, saw it was a festival, and then
        requested that exact same URL again to read its lineup - a second
        chance to time out, for a byte that was already in hand.
        """

        client = StubClient({FESTIVAL_URL: festival_page()})

        enriched = await client.enrich_event_details(
            {"url": FESTIVAL_URL, "lineup": []}
        )

        assert client.requested == [FESTIVAL_URL]

        assert [entry["name"] for entry in enriched["lineup"]] == [
            "Arctic Monkeys",
            "Pixies",
        ]
        assert enriched["lineup"][0]["songkick_id"] == "520117"
        assert enriched["start_date"] == "2027-10-31"
        assert enriched["date_status"] == "source"
        assert enriched["is_festival"] is True

    @pytest.mark.asyncio
    async def test_a_page_read_in_hand_and_a_page_fetched_agree(self):
        """One parser, so a caller holding the page is not a different reader.

        Splitting the read out of the fetch is only safe if both produce the
        same lineup; otherwise the import and the enrichment pass would
        announce different bills for the same festival.
        """

        from bs4 import BeautifulSoup

        in_hand = SongkickClient._festival_lineup_from_soup(
            BeautifulSoup(festival_page(), "html.parser"),
            FESTIVAL_URL,
        )

        fetched = await StubClient(
            {FESTIVAL_URL: festival_page()}
        ).get_festival_lineup(FESTIVAL_URL)

        assert in_hand["lineup"] == fetched["lineup"]
        assert in_hand["festival_name"] == fetched["festival_name"]

    @pytest.mark.asyncio
    async def test_a_failing_festival_page_costs_one_request_not_two(self):
        """A second request is also a second way to fail.

        With nothing served at the URL, the read gives up after asking once
        rather than asking again for the same missing document.
        """

        client = StubClient({})

        enriched = await client.enrich_event_details(
            {"url": FESTIVAL_URL, "lineup": []}
        )

        assert client.requested == [FESTIVAL_URL]
        assert enriched["lineup"] == []


# ============================================================
# 4. A FULL SCRAPE STAYS INSIDE THE PAGES IT ALREADY READS
# ============================================================


class TestTheScrapeFillsGapsWithoutAskingForMore:

    @pytest.mark.asyncio
    async def test_every_page_read_is_one_the_import_pays_for_anyway(self):
        client = StubClient(pages())

        await client.scrape_artist(
            "The Strokes", artist_id=f"Artist{ARTIST_ID}"
        )

        assert client.requested == [
            ARTIST_URL,
            f"{ARTIST_URL}/calendar",
            f"{ARTIST_URL}/gigography",
        ]
        assert EVENT_URL not in client.requested

    @pytest.mark.asyncio
    async def test_the_event_arrives_with_what_every_page_stated(self):
        """One event, read by two pages, arrives whole.

        The calendar row states the date; the artist page's structured block
        states the title, the venue, the description and the photograph. Both
        readings are of the same event id, and before the join the second one
        was discarded during deduplication - which is why an imported event
        arrived with a date and nothing else, and why its own page then had
        to be fetched to recover what the scrape was holding.
        """

        client = StubClient(pages())

        data = await client.scrape_artist(
            "The Strokes", artist_id=f"Artist{ARTIST_ID}"
        )

        assert len(data["events"]) == 1

        event = data["events"][0]

        # From the calendar listing.
        assert event["start_date"] == START

        # From the artist page's structured block.
        assert event["name"] == "The Strokes at The O2"
        assert event["description"] == (
            "The Strokes play The O2 with special guests."
        )
        assert event["songkick_image"] == IMAGE
        assert event["venue"]["name"] == "The O2"
        assert [entry["name"] for entry in event["lineup"]] == [
            "The Strokes",
            "The Hives",
        ]

    @pytest.mark.asyncio
    async def test_the_identity_is_the_event_id_never_the_title(self):
        """Two acts can share a name; an id cannot be shared.

        The join is keyed on the id both readings carry, so a differently
        titled reading of the same event merges and a same-titled reading of
        a different one does not.
        """

        client = StubClient(pages())

        data = await client.scrape_artist(
            "The Strokes", artist_id=f"Artist{ARTIST_ID}"
        )

        event = data["events"][0]

        assert event["songkick_id"] == EVENT_ID
        assert event["url"] == EVENT_URL
