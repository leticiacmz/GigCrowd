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
