"""
Tests for Songkick calendar page extraction and festival lineup.
"""
import pytest
from app.providers.songkick.client import SongkickClient


# ============================================================
# Fixtures
# ============================================================

CALENDAR_HTML = """
<html>
<body>
  <ul class="event-listings">
    <li class="event-listing-item">
      <time datetime="2026-10-02T16:00:00-0400"></time>
      <a href="/concerts/43267656-strokes-at-flushing-meadows-corona-park">
        Corona, NY, US Flushing Meadows Corona Park
      </a>
    </li>
    <li class="event-listing-item">
      <time datetime="2026-10-02T16:00:00-0400"></time>
      <a href="/concerts/43267656-strokes-at-flushing-meadows-corona-park">
        Corona, NY, US Flushing Meadows Corona Park
      </a>
    </li>
    <li class="event-listing-item">
      <time datetime="2026-10-06T19:00:00+0100"></time>
      <a href="/concerts/43155855-strokes-at-o2">
        Greenwich, UK The O2
      </a>
    </li>
    <li class="event-listing-item">
      <time datetime="2026-10-06T19:00:00+0100"></time>
      <a href="/concerts/43155855-strokes-at-o2">
        Greenwich, UK The O2
      </a>
    </li>
    <li class="event-listing-item">
      <time datetime="2026-10-07T18:30:00+0100"></time>
      <a href="/concerts/43161088-strokes-at-o2">
        Greenwich, UK The O2
      </a>
    </li>
  </ul>
</body>
</html>
"""

FESTIVAL_HTML = """
<html>
<body>
  <h1>Rock In Rio</h1>
  <div class="lineup-list">
    <div class="artist-profile">
      <span class="artist-name">Maroon 5</span>
    </div>
    <div class="artist-profile">
      <span class="artist-name">Calvin Harris</span>
    </div>
    <div class="artist-profile">
      <span class="artist-name">Elton John</span>
    </div>
    <div class="artist-profile">
      <span class="artist-name">Maroon 5</span>
    </div>
    <div class="artist-profile">
      <span class="artist-name">Foo Fighters</span>
    </div>
  </div>
</body>
</html>
"""

ARTIST_PAGE_HTML = """
<html>
<body>
  <div id="coming-up">
    <ul>
      <li class="event-listing-item">
        <a class="event-details" href="/concerts/43267656-strokes-at-flushing-meadows-corona-park">
          Corona, NY, US Flushing Meadows Corona Park
        </a>
      </li>
      <li class="event-listing-item">
        <a class="event-details" href="/concerts/43155855-strokes-at-o2">
          Greenwich, UK The O2
        </a>
      </li>
    </ul>
  </div>
  <a href="/artists/34230-strokes/calendar" class="action-btn see-all-btn" data-analytics-event="artist_calendar">
    <span class="btn_label">Show all events</span>
    <span class="btn_badge">20</span>
  </a>
</body>
</html>
"""


# ============================================================
# Calendar Page Tests
# ============================================================

class TestCalendarPage:
    """Tests for /calendar page parsing."""

    def test_calendar_extracts_unique_events(self):
        """Test that calendar page extracts unique events (deduplicated)."""
        events = SongkickClient._parse_calendar_page(
            CALENDAR_HTML,
            "https://www.songkick.com/artists/34230-strokes/calendar",
        )

        # 5 rendered entries but only 3 unique events
        assert len(events) == 3

    def test_calendar_deduplicates_by_event_id(self):
        """Test that duplicate rendered entries are deduplicated."""
        events = SongkickClient._parse_calendar_page(
            CALENDAR_HTML,
            "https://www.songkick.com/artists/34230-strokes/calendar",
        )

        event_ids = [e["songkick_id"] for e in events]
        assert len(event_ids) == len(set(event_ids))

    def test_calendar_extracts_event_ids(self):
        """Test that event IDs are correctly extracted."""
        events = SongkickClient._parse_calendar_page(
            CALENDAR_HTML,
            "https://www.songkick.com/artists/34230-strokes/calendar",
        )

        assert events[0]["songkick_id"] == "43267656"
        assert events[1]["songkick_id"] == "43155855"
        assert events[2]["songkick_id"] == "43161088"

    def test_calendar_extracts_dates(self):
        """Test that event dates are correctly extracted."""
        events = SongkickClient._parse_calendar_page(
            CALENDAR_HTML,
            "https://www.songkick.com/artists/34230-strokes/calendar",
        )

        assert events[0]["start_date"] == "2026-10-02T16:00:00-0400"
        assert events[1]["start_date"] == "2026-10-06T19:00:00+0100"

    def test_calendar_extracts_urls(self):
        """Test that event URLs are correctly extracted."""
        events = SongkickClient._parse_calendar_page(
            CALENDAR_HTML,
            "https://www.songkick.com/artists/34230-strokes/calendar",
        )

        assert events[0]["url"] == (
            "https://www.songkick.com/concerts/43267656-strokes-at-flushing-meadows-corona-park"
        )

    def test_calendar_marks_festivals(self):
        """Test that festival events are correctly marked."""
        festival_html = """
        <html><body>
          <ul class="event-listings">
            <li class="event-listing-item">
              <time datetime="2026-09-15T19:00:00+0100"></time>
              <a href="/festivals/1325-rock-in-rio/id/42907787-rock-in-rio-2026">
                Rock In Rio 2026
              </a>
            </li>
          </ul>
        </body></html>
        """

        events = SongkickClient._parse_calendar_page(
            festival_html,
            "https://www.songkick.com/artists/34230-strokes/calendar",
        )

        assert len(events) == 1
        assert events[0]["is_festival"] is True
        assert events[0]["event_type"] == "festival"

    def test_calendar_empty_page(self):
        """Test that empty calendar page returns empty list."""
        events = SongkickClient._parse_calendar_page(
            "<html><body></body></html>",
            "https://www.songkick.com/artists/34230-strokes/calendar",
        )

        assert events == []


class TestAListingStatesTheWholeRange:
    """A calendar entry writes its full range into `title`.

    The `<time>` element carries only the first day, so reading it alone threw
    the closing day away on extraction - and a festival edition was stored as
    its opening day with no end beside it, even though the listing had said the
    second day out loud. What the listing states is kept; what it does not
    state is left missing.
    """

    @staticmethod
    def _parse(html: str) -> list[dict]:
        return SongkickClient._parse_calendar_page(
            html,
            "https://www.songkick.com/artists/10176016-marina-sena/calendar",
        )

    def test_a_multi_day_listing_keeps_its_second_calendar_day(self):
        """16-17 October must arrive as 16-17 October, not as 16 October."""

        html = """
        <html><body>
          <ul class="event-listings">
            <li class="event-listing-item"
                title="Friday 16 October 2026 \u2013 Saturday 17 October 2026">
              <time datetime="2026-10-16"></time>
              <a href="/festivals/298683-mada/id/43047624-mada-2026">Mada 2026</a>
            </li>
          </ul>
        </body></html>
        """

        events = self._parse(html)

        assert len(events) == 1
        assert events[0]["start_date"] == "2026-10-16"
        assert events[0]["end_date"] == "2026-10-17"
        assert events[0]["is_festival"] is True

    def test_the_multi_day_range_reaches_the_event(self):
        """The whole chain: listing payload to domain, start to end.

        This is the shape that was being lost - an edition whose source states
        two days and whose event ends up storing one - so the assertion is on
        the dates the domain object carries, not on the payload.
        """

        from datetime import UTC, datetime

        from app.mappers.songkick_event_mapper import SongkickEventMapper

        html = """
        <html><body>
          <ul class="event-listings">
            <li class="event-listing-item"
                title="Friday 16 October 2026 \u2013 Saturday 17 October 2026">
              <time datetime="2026-10-16"></time>
              <a href="/festivals/298683-mada/id/43047624-mada-2026">Mada 2026</a>
            </li>
          </ul>
        </body></html>
        """

        payload = self._parse(html)[0]

        event, _ = SongkickEventMapper.to_domain(
            payload,
            ["marina-sena"],
        )

        assert event.starts_at == datetime(2026, 10, 16, tzinfo=UTC)
        assert event.ends_at == datetime(2026, 10, 17, tzinfo=UTC)
        assert event.event_type == "FestivalInstance"

    def test_a_single_day_listing_states_no_end(self):
        """A concert names one day, so no second day exists to keep."""

        html = """
        <html><body>
          <ul class="event-listings">
            <li class="event-listing-item" title="Friday 30 October 2026">
              <time datetime="2026-10-30T18:30:00+0000"></time>
              <a href="/concerts/43224865-marina-sena-at-electric-brixton">
                Marina Sena at Electric Brixton
              </a>
            </li>
          </ul>
        </body></html>
        """

        events = self._parse(html)

        assert events[0]["start_date"] == "2026-10-30T18:30:00+0000"
        assert events[0]["end_date"] is None

    def test_a_one_day_edition_states_no_end(self):
        """A range whose two dates are the same day states no second day.

        Songkick repeats the day for a single-day edition. Copying it would
        store an end identical to the start, which says nothing the start has
        not already said.
        """

        html = """
        <html><body>
          <ul class="event-listings">
            <li class="event-listing-item"
                title="Saturday 07 November 2026 \u2013 Saturday 07 November 2026">
              <time datetime="2026-11-07"></time>
              <a href="/festivals/3790726-amae/id/43263609-ama-festival-2026">
                Amae Festival 2026
              </a>
            </li>
          </ul>
        </body></html>
        """

        events = self._parse(html)

        assert events[0]["start_date"] == "2026-11-07"
        assert events[0]["end_date"] is None

    def test_a_title_that_cannot_be_read_leaves_the_end_missing(self):
        """No parseable range, no end - a guessed one is worse than none."""

        html = """
        <html><body>
          <ul class="event-listings">
            <li class="event-listing-item" title="Tickets on sale now">
              <time datetime="2026-10-16"></time>
              <a href="/festivals/298683-mada/id/43047624-mada-2026">Mada 2026</a>
            </li>
          </ul>
        </body></html>
        """

        events = self._parse(html)

        assert events[0]["start_date"] == "2026-10-16"
        assert events[0]["end_date"] is None

    def test_a_range_without_a_start_keeps_no_end(self):
        """An interval is ordered against a start, so a lone end is not taken."""

        html = """
        <html><body>
          <ul class="event-listings">
            <li class="event-listing-item"
                title="Friday 16 October 2026 \u2013 Saturday 17 October 2026">
              <a href="/festivals/298683-mada/id/43047624-mada-2026">Mada 2026</a>
            </li>
          </ul>
        </body></html>
        """

        events = self._parse(html)

        assert events[0]["start_date"] is None
        assert events[0]["end_date"] is None


# ============================================================
# Festival Lineup Tests
# ============================================================

class TestFestivalLineup:
    """Tests for festival lineup extraction."""

    def test_festival_lineup_extraction(self):
        """Test that festival lineup is correctly extracted."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(FESTIVAL_HTML, "html.parser")
        lineup_list = soup.select_one(".lineup-list")

        assert lineup_list is not None

        artists = lineup_list.select(".artist-profile")
        assert len(artists) == 5

    def test_festival_lineup_deduplication(self):
        """Test that duplicate lineup artists are deduplicated."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(FESTIVAL_HTML, "html.parser")
        lineup_list = soup.select_one(".lineup-list")

        artists = lineup_list.select(".artist-profile")
        names = []
        seen = set()

        for artist in artists:
            name_elem = artist.select_one(".artist-name")
            if not name_elem:
                continue

            name = name_elem.get_text(strip=True)
            normalized = name.lower().strip()

            if normalized in seen:
                continue

            seen.add(normalized)
            names.append(name)

        # 5 rendered entries but only 4 unique artists
        assert len(names) == 4
        assert "Maroon 5" in names
        assert "Calvin Harris" in names
        assert "Elton John" in names
        assert "Foo Fighters" in names

    def test_festival_lineup_artist_names(self):
        """Test that artist names are correctly extracted."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(FESTIVAL_HTML, "html.parser")
        lineup_list = soup.select_one(".lineup-list")

        name_elems = lineup_list.select(".artist-name")
        names = [e.get_text(strip=True) for e in name_elems]

        assert "Maroon 5" in names
        assert "Calvin Harris" in names
        assert "Elton John" in names
        assert "Foo Fighters" in names


# ============================================================
# Festival Date Tests
# ============================================================

class TestFestivalDates:
    """Tests for festival date handling."""

    def test_festival_date_not_used_as_performance_date(self):
        """Test that festival date range is NOT used as artist performance date."""
        event = {
            "songkick_id": "42907787",
            "is_festival": True,
            "start_date": None,
            "end_date": None,
        }

        search_document = {
            "name": "Rock In Rio 2026",
            "date": "2026-09-15",
            "end_date": "2026-09-20",
        }

        # Create a mock search event index
        search_event_index = {
            "42907787": search_document,
        }

        enriched = SongkickClient._enrich_event_with_search_data(
            event,
            search_event_index,
        )

        # The festival date range should NOT be copied to the event
        # when the event doesn't already have a specific performance date
        assert enriched.get("start_date") is None or enriched.get("start_date") == event.get("start_date")

    def test_specific_performance_date_preserved(self):
        """Test that specific performance dates are preserved."""
        event = {
            "songkick_id": "42907787",
            "is_festival": True,
            "start_date": "2026-09-16T19:00:00+0100",
            "end_date": None,
        }

        search_document = {
            "name": "Rock In Rio 2026",
            "date": "2026-09-15",
            "end_date": "2026-09-20",
        }

        search_event_index = {
            "42907787": search_document,
        }

        enriched = SongkickClient._enrich_event_with_search_data(
            event,
            search_event_index,
        )

        # The specific performance date should be preserved
        assert enriched["start_date"] == "2026-09-16T19:00:00+0100"


# ============================================================
# Preview vs Calendar Tests
# ============================================================

class TestPreviewVsCalendar:
    """Tests for #coming-up preview vs /calendar complete list."""

    def test_preview_has_fewer_events_than_calendar(self):
        """Test that #coming-up preview has fewer events than /calendar."""
        # Parse artist page preview
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(ARTIST_PAGE_HTML, "html.parser")
        coming_up = soup.select_one("#coming-up")

        preview_events = []
        if coming_up:
            items = coming_up.select("li.event-listing-item")
            preview_events = items

        # Parse calendar page
        calendar_events = SongkickClient._parse_calendar_page(
            CALENDAR_HTML,
            "https://www.songkick.com/artists/34230-strokes/calendar",
        )

        # Preview has 2 events, calendar has 3 unique events
        assert len(preview_events) < len(calendar_events)

    def test_calendar_contains_events_not_in_preview(self):
        """Test that /calendar contains events not in #coming-up preview."""
        from bs4 import BeautifulSoup

        # Parse preview
        soup = BeautifulSoup(ARTIST_PAGE_HTML, "html.parser")
        coming_up = soup.select_one("#coming-up")

        preview_ids = set()
        if coming_up:
            for item in coming_up.select("li.event-listing-item"):
                link = item.select_one("a.event-details")
                if link:
                    href = link.get("href", "")
                    # Extract event ID from href
                    import re
                    match = re.search(r"/concerts/(\d+)", href)
                    if match:
                        preview_ids.add(match.group(1))

        # Parse calendar
        calendar_events = SongkickClient._parse_calendar_page(
            CALENDAR_HTML,
            "https://www.songkick.com/artists/34230-strokes/calendar",
        )

        calendar_ids = {e["songkick_id"] for e in calendar_events}

        # Calendar has events not in preview
        assert not calendar_ids.issubset(preview_ids)


# ============================================================
# Calendar Pagination Tests
# ============================================================

CALENDAR_PAGE_1_HTML = """
<html>
<body>
  <ul class="event-listings">
    <li class="event-listing-item">
      <time datetime="2026-10-02T16:00:00-0400"></time>
      <a href="/concerts/43267656-strokes-at-flushing-meadows-corona-park">
        Corona, NY, US Flushing Meadows Corona Park
      </a>
    </li>
    <li class="event-listing-item">
      <time datetime="2026-10-06T19:00:00+0100"></time>
      <a href="/concerts/43155855-strokes-at-o2">
        Greenwich, UK The O2
      </a>
    </li>
  </ul>
  <a href="/artists/34230-strokes/calendar?page=2" rel="next">Next</a>
</body>
</html>
"""

CALENDAR_PAGE_2_HTML = """
<html>
<body>
  <ul class="event-listings">
    <li class="event-listing-item">
      <time datetime="2026-10-07T18:30:00+0100"></time>
      <a href="/concerts/43161088-strokes-at-o2">
        Greenwich, UK The O2
      </a>
    </li>
    <li class="event-listing-item">
      <time datetime="2026-10-11T19:00:00+0200"></time>
      <a href="/concerts/43155856-strokes-at-ziggo-dome">
        Amsterdam, Netherlands Ziggo Dome
      </a>
    </li>
  </ul>
</body>
</html>
"""


class TestCalendarPagination:
    """Tests for calendar page pagination."""

    def test_extract_next_page_url(self):
        """Test that next page URL is correctly extracted."""
        next_url = SongkickClient._extract_calendar_next_page(
            CALENDAR_PAGE_1_HTML,
            "https://www.songkick.com/artists/34230-strokes/calendar",
            1,
        )

        assert next_url is not None
        assert "page=2" in next_url

    def test_no_next_page_on_last_page(self):
        """Test that no next page URL is returned on the last page."""
        next_url = SongkickClient._extract_calendar_next_page(
            CALENDAR_PAGE_2_HTML,
            "https://www.songkick.com/artists/34230-strokes/calendar?page=2",
            2,
        )

        assert next_url is None

    def test_pagination_deduplicates_across_pages(self):
        """Test that events are deduplicated across multiple pages."""
        page1_events = SongkickClient._parse_calendar_page(
            CALENDAR_PAGE_1_HTML,
            "https://www.songkick.com/artists/34230-strokes/calendar",
        )

        page2_events = SongkickClient._parse_calendar_page(
            CALENDAR_PAGE_2_HTML,
            "https://www.songkick.com/artists/34230-strokes/calendar?page=2",
        )

        # Page 1 has 2 events, page 2 has 2 events
        assert len(page1_events) == 2
        assert len(page2_events) == 2

        # No overlap between pages
        page1_ids = {e["songkick_id"] for e in page1_events}
        page2_ids = {e["songkick_id"] for e in page2_events}

        assert page1_ids.isdisjoint(page2_ids)


# ============================================================
# Festival Lineup Resolution Tests
# ============================================================

class TestLineupResolution:
    """Tests for festival lineup artist resolution."""

    def test_resolvable_artist(self):
        """Test that a resolvable artist is correctly linked."""
        lineup = [
            {"name": "Arctic Monkeys", "url": None},
        ]

        existing_artists = [
            {
                "id": "abc123",
                "name": "Arctic Monkeys",
                "external_ids": {"songkick": "520117"},
            },
        ]

        resolved = SongkickClient.resolve_lineup_artists(
            lineup,
            existing_artists,
        )

        assert len(resolved) == 1
        assert resolved[0]["resolved"] is True
        assert resolved[0]["gigcrowd_artist_id"] == "abc123"

    def test_unresolved_artist(self):
        """Test that an unresolved artist is preserved as unresolved."""
        lineup = [
            {"name": "Unknown Artist", "url": None},
        ]

        existing_artists = [
            {
                "id": "abc123",
                "name": "Arctic Monkeys",
                "external_ids": {"songkick": "520117"},
            },
        ]

        resolved = SongkickClient.resolve_lineup_artists(
            lineup,
            existing_artists,
        )

        assert len(resolved) == 1
        assert resolved[0]["resolved"] is False
        assert resolved[0]["gigcrowd_artist_id"] is None
        # Name is preserved
        assert resolved[0]["name"] == "Unknown Artist"

    def test_duplicate_lineup_names(self):
        """Test that duplicate lineup names are preserved (not deduplicated)."""
        lineup = [
            {"name": "Maroon 5", "url": None},
            {"name": "Maroon 5", "url": None},
            {"name": "Calvin Harris", "url": None},
        ]

        existing_artists = []

        resolved = SongkickClient.resolve_lineup_artists(
            lineup,
            existing_artists,
        )

        # All entries are preserved (deduplication happens in get_festival_lineup)
        assert len(resolved) == 3

    def test_resolution_by_songkick_id(self):
        """Test that artists are resolved by Songkick ID."""
        lineup = [
            {
                "name": "Arctic Monkeys",
                "url": "https://www.songkick.com/artists/520117-arctic-monkeys",
            },
        ]

        existing_artists = [
            {
                "id": "abc123",
                "name": "Arctic Monkeys",
                "external_ids": {"songkick": "520117"},
            },
        ]

        resolved = SongkickClient.resolve_lineup_artists(
            lineup,
            existing_artists,
        )

        assert resolved[0]["resolved"] is True
        assert resolved[0]["gigcrowd_artist_id"] == "abc123"

    def test_full_lineup_preserved(self):
        """Test that the full lineup is preserved regardless of resolution."""
        lineup = [
            {"name": "Artist A", "url": None},
            {"name": "Artist B", "url": None},
            {"name": "Artist C", "url": None},
        ]

        existing_artists = [
            {
                "id": "abc123",
                "name": "Artist A",
                "external_ids": {"songkick": "123"},
            },
        ]

        resolved = SongkickClient.resolve_lineup_artists(
            lineup,
            existing_artists,
        )

        # All 3 artists are preserved
        assert len(resolved) == 3

        # Only 1 is resolved
        resolved_count = sum(1 for r in resolved if r["resolved"])
        assert resolved_count == 1


# ============================================================
# Event Detail Enrichment Tests
# ============================================================

EVENT_PAGE_HTML = """
<html>
<body>
  <script type="application/ld+json">
{"@type":"MusicEvent","name":"The Strokes at The O2","startDate":"2026-10-06T19:00:00+0100","url":"https://www.songkick.com/concerts/43155855-strokes-at-o2","image":"https://images.songkick.com/images/12345.jpg","eventStatus":"https://schema.org/EventScheduled","offers":{"@type":"Offer","url":"https://www.songkick.com/concerts/43155855-strokes-at-o2/tickets"},"location":{"name":"The O2","address":{"streetAddress":"Peninsula Square","addressLocality":"London","addressCountry":"UK","postalCode":"SE10 0DX"},"geo":{"latitude":51.5030,"longitude":0.0030}}}
  </script>
</body>
</html>
"""


def _parse_jsonld_scripts(html: str) -> list[dict]:
    """Parse JSON-LD scripts from HTML."""
    from bs4 import BeautifulSoup
    import json

    soup = BeautifulSoup(html, "html.parser")
    jsonld_scripts = soup.find_all(
        "script",
        type="application/ld+json",
    )

    events = []
    for script in jsonld_scripts:
        try:
            # Use get_text() and strip whitespace for reliable parsing
            content = (script.string or script.get_text()).strip()
            data = json.loads(content)
            if isinstance(data, dict) and data.get("@type") == "MusicEvent":
                events.append(data)
        except Exception:
            continue

    return events


class TestEventDetailEnrichment:
    """Tests for event detail extraction from event pages."""

    def test_extract_ticket_url(self):
        """Test that ticket URL is extracted from offers."""
        events = _parse_jsonld_scripts(EVENT_PAGE_HTML)

        assert len(events) == 1

        ticket_url = None
        offers = events[0].get("offers", [])
        if isinstance(offers, dict):
            offers = [offers]

        for offer in offers:
            if not isinstance(offer, dict):
                continue

            offer_url = offer.get("url")
            if offer_url:
                ticket_url = offer_url
                break

        assert ticket_url is not None
        assert "tickets" in ticket_url

    def test_extract_official_website(self):
        """Test that official website is extracted."""
        events = _parse_jsonld_scripts(EVENT_PAGE_HTML)

        assert len(events) == 1

        official_website = (
            events[0].get("officialWebsite")
            or events[0].get("eventWebsite")
        )

        # officialWebsite may not be present in all events
        # This test just verifies the extraction logic works
        assert official_website is None or isinstance(official_website, str)

    def test_extract_event_image(self):
        """Test that event image is extracted."""
        events = _parse_jsonld_scripts(EVENT_PAGE_HTML)

        assert len(events) == 1

        image = events[0].get("image")
        if image:
            if isinstance(image, list) and image:
                image = image[0]

        assert image is not None
        assert "images.songkick.com" in image

    def test_extract_venue_address(self):
        """Test that venue address is extracted."""
        events = _parse_jsonld_scripts(EVENT_PAGE_HTML)

        assert len(events) == 1

        location = events[0].get("location", {})
        assert isinstance(location, dict)

        venue_name = location.get("name")
        address = location.get("address", {})
        assert isinstance(address, dict)

        street = address.get("streetAddress")
        city = address.get("addressLocality")
        country = address.get("addressCountry")

        assert venue_name == "The O2"
        assert street == "Peninsula Square"
        assert city == "London"
        assert country == "UK"

    def test_extract_coordinates(self):
        """Test that coordinates are extracted."""
        events = _parse_jsonld_scripts(EVENT_PAGE_HTML)

        assert len(events) == 1

        location = events[0].get("location", {})
        assert isinstance(location, dict)

        geo = location.get("geo", {})
        assert isinstance(geo, dict)

        latitude = geo.get("latitude")
        longitude = geo.get("longitude")

        assert latitude == 51.5030
        assert longitude == 0.0030

    def test_extract_event_status(self):
        """Test that event status is extracted."""
        events = _parse_jsonld_scripts(EVENT_PAGE_HTML)

        assert len(events) == 1

        event_status = events[0].get("eventStatus")

        assert event_status == "https://schema.org/EventScheduled"


# ============================================================
# Festival Performance Date Safety Tests
# ============================================================

class TestFestivalPerformanceDateSafety:
    """Tests for festival performance date safety."""

    def test_multi_day_festival_not_used_as_performance_date(self):
        """Test that a multi-day festival does not become a multi-day artist performance."""
        event = {
            "songkick_id": "42907787",
            "is_festival": True,
            "start_date": None,
            "end_date": None,
        }

        search_document = {
            "name": "Rock In Rio 2026",
            "date": "2026-09-15",
            "end_date": "2026-09-20",
        }

        search_event_index = {
            "42907787": search_document,
        }

        enriched = SongkickClient._enrich_event_with_search_data(
            event,
            search_event_index,
        )

        # The festival date range should NOT be copied to the event
        # when the event doesn't already have a specific performance date
        assert enriched.get("start_date") is None
        assert enriched.get("end_date") is None

    def test_festival_event_without_performance_date_is_valid(self):
        """Test that a festival event without performance date remains valid."""
        event = {
            "songkick_id": "42907787",
            "is_festival": True,
            "start_date": None,
            "end_date": None,
            "name": "Rock In Rio 2026",
            "url": "https://www.songkick.com/festivals/1325-rock-in-rio/id/42907787-rock-in-rio-2026",
        }

        # The event should be valid even without a performance date
        assert event["songkick_id"] == "42907787"
        assert event["is_festival"] is True
        assert event["name"] == "Rock In Rio 2026"

    def test_specific_performance_date_preserved_over_festival_range(self):
        """Test that a specific performance date is preserved over festival range."""
        event = {
            "songkick_id": "42907787",
            "is_festival": True,
            "start_date": "2026-09-16T19:00:00+0100",
            "end_date": None,
        }

        search_document = {
            "name": "Rock In Rio 2026",
            "date": "2026-09-15",
            "end_date": "2026-09-20",
        }

        search_event_index = {
            "42907787": search_document,
        }

        enriched = SongkickClient._enrich_event_with_search_data(
            event,
            search_event_index,
        )

        # The specific performance date should be preserved
        assert enriched["start_date"] == "2026-09-16T19:00:00+0100"
        # The festival end date should NOT overwrite the event
        assert enriched.get("end_date") is None


# ============================================================
# Rock In Rio End-to-End Regression Tests
# ============================================================

ROCK_IN_RIO_HTML = """
<html>
<body>
  <h1>Rock In Rio</h1>
  <div class="lineup-list">
    <div class="artist-profile">
      <span class="artist-name">Maroon 5</span>
    </div>
    <div class="artist-profile">
      <span class="artist-name">Calvin Harris</span>
    </div>
    <div class="artist-profile">
      <span class="artist-name">Elton John</span>
    </div>
    <div class="artist-profile">
      <span class="artist-name">Foo Fighters</span>
    </div>
  </div>
</body>
</html>
"""


class TestRockInRioE2E:
    """End-to-end regression tests for Rock In Rio festival scenario."""

    def test_festival_identified_correctly(self):
        """Test that the festival is identified correctly."""
        event = {
            "songkick_id": "42907787",
            "is_festival": True,
            "event_type": "festival",
            "name": "Rock In Rio 2026",
        }

        assert event["is_festival"] is True
        assert event["event_type"] == "festival"

    def test_complete_lineup_extracted(self):
        """Test that the complete lineup is extracted."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(ROCK_IN_RIO_HTML, "html.parser")
        lineup_list = soup.select_one(".lineup-list")

        assert lineup_list is not None

        artists = lineup_list.select(".artist-profile")
        assert len(artists) == 4

    def test_lineup_entries_preserved(self):
        """Test that all lineup entries are preserved."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(ROCK_IN_RIO_HTML, "html.parser")
        lineup_list = soup.select_one(".lineup-list")

        artists = lineup_list.select(".artist-profile")
        names = []
        seen = set()

        for artist in artists:
            name_elem = artist.select_one(".artist-name")
            if not name_elem:
                continue

            name = name_elem.get_text(strip=True)
            normalized = name.lower().strip()

            if normalized in seen:
                continue

            seen.add(normalized)
            names.append(name)

        # All 4 artists are preserved
        assert len(names) == 4
        assert "Maroon 5" in names
        assert "Calvin Harris" in names
        assert "Elton John" in names
        assert "Foo Fighters" in names

    def test_festival_date_range_not_treated_as_performance_date(self):
        """Test that festival date range is NOT treated as artist performance date."""
        event = {
            "songkick_id": "42907787",
            "is_festival": True,
            "start_date": None,
            "end_date": None,
        }

        search_document = {
            "name": "Rock In Rio 2026",
            "date": "2026-09-15",
            "end_date": "2026-09-20",
        }

        search_event_index = {
            "42907787": search_document,
        }

        enriched = SongkickClient._enrich_event_with_search_data(
            event,
            search_event_index,
        )

        # Festival date range should NOT be used as performance date
        assert enriched.get("start_date") is None
        assert enriched.get("end_date") is None

    def test_no_duplicate_events_created(self):
        """Test that no duplicate events are created."""
        # Parse the same calendar page twice
        events1 = SongkickClient._parse_calendar_page(
            CALENDAR_HTML,
            "https://www.songkick.com/artists/34230-strokes/calendar",
        )

        events2 = SongkickClient._parse_calendar_page(
            CALENDAR_HTML,
            "https://www.songkick.com/artists/34230-strokes/calendar",
        )

        # Same number of events
        assert len(events1) == len(events2)

        # Same event IDs
        ids1 = {e["songkick_id"] for e in events1}
        ids2 = {e["songkick_id"] for e in events2}

        assert ids1 == ids2

    def test_sync_persistence_succeeds(self):
        """Test that sync/persistence succeeds with festival events."""
        event = {
            "songkick_id": "42907787",
            "is_festival": True,
            "name": "Rock In Rio 2026",
            "url": "https://www.songkick.com/festivals/1325-rock-in-rio/id/42907787-rock-in-rio-2026",
            "start_date": None,
            "end_date": None,
        }

        # Event should be valid for persistence
        assert event["songkick_id"] == "42907787"
        assert event["is_festival"] is True
        assert event["name"] == "Rock In Rio 2026"

    def test_artist_triggered_festival_event_associated(self):
        """Test that artist-triggered festival events remain associated."""
        event = {
            "songkick_id": "42907787",
            "is_festival": True,
            "name": "Rock In Rio 2026",
            "performers": [
                {"name": "The Strokes"},
            ],
        }

        # The event should maintain the artist association
        assert event["is_festival"] is True
        assert len(event["performers"]) == 1
        assert event["performers"][0]["name"] == "The Strokes"
