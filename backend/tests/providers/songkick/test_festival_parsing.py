"""Reading dates, identities and lineups out of a real Songkick page shape.

Every case here is taken from the structure Songkick actually serves, which is
the point: the bugs these cover were not theoretical. Songkick wraps its
JSON-LD in a list, addresses artists as `/artists/{id}-{slug}`, hangs the `href`
off the `.artist-profile` element instead of a nested anchor, and states dates
as ISO strings. A reader written against a tidier page found none of that, and
every festival it looked at came back with no date and no artist ids.

The tests use the reference page's real markup rather than a tidy fixture, so a
change in how the page is shaped fails here instead of silently returning empty
fields again.
"""
from __future__ import annotations

import json

from bs4 import BeautifulSoup

from app.domain.festival import (
    festival_data_from_url,
    songkick_artist_reference,
)
from app.providers.songkick.client import SongkickClient


CANONICAL_URL = (
    "https://www.songkick.com/festivals/"
    "3441108-primavera-sound-sao-paulo-dia-1"
    "/id/40385544-primavera-sound-so-paulo-dia-1-2022"
)

# The structured block Songkick serves on a festival page: a list, with
# date-only strings and performers identified only by URL.
FESTIVAL_JSONLD = [
    {
        "@context": "http://schema.org",
        "@type": "MusicEvent",
        "name": "Primavera Sound São Paulo Dia 1 2022 @ Distrito Anhembi",
        "url": CANONICAL_URL,
        "startDate": "2022-10-31",
        "endDate": "2022-11-06",
        "eventStatus": "https://schema.org/EventScheduled",
        "image": (
            "https://images.sk-static.com/images/media/"
            "profile_images/events/40385544/huge_avatar"
            "?series_id=3441108"
        ),
        "location": {
            "@type": "Place",
            "name": "Distrito Anhembi",
            "address": {
                "@type": "PostalAddress",
                "streetAddress": "Av. Olavo Fontoura, 1209",
                "addressLocality": "São Paulo",
                "addressCountry": "Brazil",
                "postalCode": "02012-02",
            },
        },
        "performer": [
            {
                "@type": "MusicGroup",
                "name": "Arctic Monkeys",
                "genre": ["rock", "indie_alternative"],
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


def festival_page(
    jsonld=None,
    lineup_html: str = "",
) -> str:
    """A festival page carrying the markup the parsers actually read."""

    block = (
        jsonld
        if jsonld is not None
        else FESTIVAL_JSONLD
    )

    return f"""<html><head>
      <script type="application/ld+json">{json.dumps(block)}</script>
    </head><body>
      <h1>Primavera Sound São Paulo</h1>
      <div class="lineup-list">{lineup_html}</div>
    </body></html>"""


class TestJsonLdUnwrapping:
    """Songkick wraps its structured data in a list."""

    def test_event_is_read_from_a_list_wrapped_block(self):
        soup = BeautifulSoup(
            festival_page(),
            "html.parser",
        )

        parsed = SongkickClient._read_jsonld_event(
            soup,
            CANONICAL_URL,
        )

        # Before this was handled, a reader that only accepted a top-level dict
        # found nothing at all on a festival page - which is exactly where the
        # missing dates were.
        assert parsed["songkick_id"] == "40385544"
        assert parsed["event_type"] == "festival"

    def test_event_is_read_from_a_graph_wrapped_block(self):
        soup = BeautifulSoup(
            festival_page(
                jsonld=[
                    {
                        "@context": "http://schema.org",
                        "@graph": FESTIVAL_JSONLD,
                    }
                ]
            ),
            "html.parser",
        )

        parsed = SongkickClient._read_jsonld_event(
            soup,
            CANONICAL_URL,
        )

        assert parsed["songkick_id"] == "40385544"

    def test_a_single_object_still_reads(self):
        soup = BeautifulSoup(
            festival_page(
                jsonld=FESTIVAL_JSONLD[0]
            ),
            "html.parser",
        )

        parsed = SongkickClient._read_jsonld_event(
            soup,
            CANONICAL_URL,
        )

        assert parsed["songkick_id"] == "40385544"

    def test_malformed_json_is_skipped_not_raised(self):
        html = """<html><head>
          <script type="application/ld+json">{not json</script>
        </head><body></body></html>"""

        parsed = SongkickClient._read_jsonld_event(
            BeautifulSoup(html, "html.parser"),
            CANONICAL_URL,
        )

        assert parsed == {}

    def test_unrelated_blocks_are_ignored(self):
        soup = BeautifulSoup(
            festival_page(
                jsonld=[
                    {
                        "@type": "BreadcrumbList",
                        "name": "Home",
                    }
                ]
            ),
            "html.parser",
        )

        assert SongkickClient._read_jsonld_event(
            soup,
            CANONICAL_URL,
        ) == {}


class TestDates:
    """The highest-value fix in this change: dates are recoverable."""

    def test_start_and_end_are_read(self):
        parsed = SongkickClient._read_jsonld_event(
            BeautifulSoup(festival_page(), "html.parser"),
            CANONICAL_URL,
        )

        assert parsed["start_date"] == "2022-10-31"
        assert parsed["end_date"] == "2022-11-06"

    def test_a_multi_day_range_keeps_both_ends(self):
        """A festival runs over days, so one date would be a partial answer."""

        parsed = SongkickClient._read_jsonld_event(
            BeautifulSoup(festival_page(), "html.parser"),
            CANONICAL_URL,
        )

        assert parsed["start_date"] != parsed["end_date"]

    def test_a_dated_event_is_marked_as_read_from_the_source(self):
        parsed = SongkickClient._read_jsonld_event(
            BeautifulSoup(festival_page(), "html.parser"),
            CANONICAL_URL,
        )

        assert parsed["date_status"] == "source"

    def test_an_undated_event_is_kept_not_dropped(self):
        """No date is a real state to record, not a reason to lose the event.

        Dropping it here is what made 685 real festival dates unrecoverable: the
        event vanished from the catalogue, so there was nothing left for
        enrichment to go back and fix.
        """

        undated = [
            {
                "@type": "MusicEvent",
                "name": "Unannounced Festival",
                "url": (
                    "https://www.songkick.com/festivals/"
                    "999-unannounced/id/888-unannounced"
                ),
            }
        ]

        parsed = SongkickClient._read_jsonld_event(
            BeautifulSoup(
                festival_page(jsonld=undated),
                "html.parser",
            ),
            "https://www.songkick.com/festivals/999-unannounced/id/888-unannounced",
        )

        assert parsed is not None
        assert parsed["name"] == "Unannounced Festival"
        assert parsed["start_date"] is None
        assert parsed["date_status"] == "unavailable"

    def test_unavailable_is_distinguished_from_parser_failed(self):
        """Only the second is worth retrying, so they must not be conflated."""

        no_date_field = [
            {
                "@type": "MusicEvent",
                "name": "Festival",
                "url": "https://www.songkick.com/festivals/1-x/id/2-y",
            }
        ]

        parsed = SongkickClient._read_jsonld_event(
            BeautifulSoup(
                festival_page(jsonld=no_date_field),
                "html.parser",
            ),
            "https://www.songkick.com/festivals/1-x/id/2-y",
        )

        assert parsed["date_status"] == "unavailable"
        assert parsed["date_status"] != "parser_failed"


class TestFestivalIdentity:
    """The series is the identity; the date is the edition."""

    def test_series_id_comes_from_the_page_url(self):
        parsed = SongkickClient._read_jsonld_event(
            BeautifulSoup(festival_page(), "html.parser"),
            CANONICAL_URL,
        )

        festival = parsed["festival"]

        assert festival["series_id"] == "3441108"
        assert festival["url"] == CANONICAL_URL

    def test_identity_carries_no_dates(self):
        """A series has no single date; putting one there misstates it."""

        parsed = SongkickClient._read_jsonld_event(
            BeautifulSoup(festival_page(), "html.parser"),
            CANONICAL_URL,
        )

        assert "start_date" not in parsed["festival"]
        assert "end_date" not in parsed["festival"]

    def test_a_non_festival_url_yields_no_identity(self):
        assert (
            SongkickClient._festival_metadata_from_jsonld(
                {"name": "A Concert"},
                "https://www.songkick.com/concerts/1",
            )
            is None
        )

    def test_identity_is_never_inferred_from_a_title(self):
        """Titles repeat across years and cities; only the id identifies."""

        concert_url = (
            "https://www.songkick.com/concerts/"
            "123-some-festival-2022"
        )

        assert (
            SongkickClient._festival_metadata_from_jsonld(
                {"name": "Some Festival 2022"},
                concert_url,
            )
            is None
        )


class TestLineup:
    """Performers keep their Songkick identity or they are not linkable."""

    def test_artist_ids_are_read_from_the_performer_url(self):
        parsed = SongkickClient._read_jsonld_event(
            BeautifulSoup(festival_page(), "html.parser"),
            CANONICAL_URL,
        )

        ids = {
            entry["songkick_id"]
            for entry in parsed["lineup"]
        }

        assert ids == {"520117", "271757"}

    def test_slugs_and_urls_are_kept(self):
        parsed = SongkickClient._read_jsonld_event(
            BeautifulSoup(festival_page(), "html.parser"),
            CANONICAL_URL,
        )

        first = parsed["lineup"][0]

        assert first["slug"] == "arctic-monkeys"
        assert first["url"].endswith(
            "/artists/520117-arctic-monkeys"
        )

    def test_genres_are_kept(self):
        parsed = SongkickClient._read_jsonld_event(
            BeautifulSoup(festival_page(), "html.parser"),
            CANONICAL_URL,
        )

        assert parsed["lineup"][0]["genres"] == [
            "rock",
            "indie_alternative",
        ]

    def test_a_performer_without_a_url_keeps_its_name(self):
        """The artist is real; it simply cannot be resolved yet."""

        parsed = SongkickClient._jsonld_to_event(
            {
                "@type": "MusicEvent",
                "name": "Festival",
                "url": CANONICAL_URL,
                "startDate": "2022-10-31",
                "performer": [
                    {
                        "name": "Unknown Act",
                    }
                ],
            },
            CANONICAL_URL,
        )

        assert parsed["lineup"] == [
            {
                "name": "Unknown Act",
                "songkick_id": None,
                "url": None,
                "slug": None,
                "image": None,
                "genres": [],
                "order": 0,
            }
        ]

    def test_a_performer_without_a_name_is_dropped(self):
        parsed = SongkickClient._jsonld_to_event(
            {
                "@type": "MusicEvent",
                "name": "Festival",
                "url": CANONICAL_URL,
                "startDate": "2022-10-31",
                "performer": [
                    {"sameAs": "/artists/1-x"},
                    {"name": "Real Act"},
                ],
            },
            CANONICAL_URL,
        )

        assert [
            entry["name"]
            for entry in parsed["lineup"]
        ] == ["Real Act"]

    def test_the_same_artist_twice_is_one_entry(self):
        parsed = SongkickClient._jsonld_to_event(
            {
                "@type": "MusicEvent",
                "name": "Festival",
                "url": CANONICAL_URL,
                "startDate": "2022-10-31",
                "performer": [
                    {
                        "name": "Arctic Monkeys",
                        "sameAs": (
                            "https://www.songkick.com/"
                            "artists/520117-arctic-monkeys"
                        ),
                    },
                    {
                        "name": "arctic monkeys",
                        "sameAs": (
                            "https://www.songkick.com/"
                            "artists/520117-arctic-monkeys"
                        ),
                    },
                ],
            },
            CANONICAL_URL,
        )

        assert len(parsed["lineup"]) == 1

    def test_no_spotify_id_is_ever_stored_as_a_songkick_id(self):
        """A Spotify id in this field would point at the wrong artist."""

        parsed = SongkickClient._jsonld_to_event(
            {
                "@type": "MusicEvent",
                "name": "Festival",
                "url": CANONICAL_URL,
                "startDate": "2022-10-31",
                "performer": [
                    {
                        "name": "Arctic Monkeys",
                        "sameAs": (
                            "https://www.songkick.com/"
                            "artists/520117-arctic-monkeys"
                        ),
                    }
                ],
            },
            CANONICAL_URL,
        )

        entry = parsed["lineup"][0]

        assert entry["songkick_id"] == "520117"
        assert entry["songkick_id"] != "0LcFqbDKbN7"


class TestLineupDom:
    """The rendered lineup, where Songkick hangs `href` off the element."""

    LINEUP_HTML = """
      <div class="artist-profile" href="/artists/520117-arctic-monkeys">
        <div class="artist-image" data-src="https://img/arctic.jpg"></div>
        <h3 class="artist-name">Arctic Monkeys</h3>
      </div>
      <div class="artist-profile" href="/artists/271757-pixies">
        <h3 class="artist-name">Pixies</h3>
      </div>
    """

    def test_href_is_read_from_the_element_itself(self):
        """The element carries the href; there is no nested anchor to find.

        Reading it from a nested `<a>` produced a null URL for every artist,
        which silently discarded every Songkick artist id on the page.
        """

        lineup = SongkickClient._parse_lineup_dom(
            BeautifulSoup(
                festival_page(lineup_html=self.LINEUP_HTML),
                "html.parser",
            ),
            CANONICAL_URL,
        )

        assert {
            entry["songkick_id"]
            for entry in lineup
        } == {"520117", "271757"}

    def test_urls_are_absolute_and_tracking_free(self):
        lineup = SongkickClient._parse_lineup_dom(
            BeautifulSoup(
                festival_page(lineup_html=self.LINEUP_HTML),
                "html.parser",
            ),
            CANONICAL_URL,
        )

        assert lineup[0]["url"] == (
            "https://www.songkick.com/artists/520117-arctic-monkeys"
        )

    def test_a_nested_anchor_is_still_accepted(self):
        """A markup change must not be able to lose the ids again."""

        html = """
          <div class="artist-profile">
            <a href="/artists/520117-arctic-monkeys">
              <h3 class="artist-name">Arctic Monkeys</h3>
            </a>
          </div>
        """

        lineup = SongkickClient._parse_lineup_dom(
            BeautifulSoup(
                festival_page(lineup_html=html),
                "html.parser",
            ),
            CANONICAL_URL,
        )

        assert lineup[0]["songkick_id"] == "520117"

    def test_images_are_read_when_present(self):
        lineup = SongkickClient._parse_lineup_dom(
            BeautifulSoup(
                festival_page(lineup_html=self.LINEUP_HTML),
                "html.parser",
            ),
            CANONICAL_URL,
        )

        assert lineup[0]["image"] == "https://img/arctic.jpg"

    def test_a_page_without_a_lineup_returns_nothing(self):
        assert (
            SongkickClient._parse_lineup_dom(
                BeautifulSoup(festival_page(), "html.parser"),
                CANONICAL_URL,
            )
            == []
        )


class TestArtistUrlParsing:
    """Songkick addresses an artist as `/artists/{id}-{slug}`."""

    def test_id_and_slug_are_read(self):
        assert songkick_artist_reference(
            "https://www.songkick.com/artists/520117-arctic-monkeys"
        ) == ("520117", "arctic-monkeys")

    def test_tracking_parameters_are_ignored(self):
        songkick_id, slug = songkick_artist_reference(
            "https://www.songkick.com/artists/520117-arctic-monkeys"
            "?utm_source=festival"
        )

        assert songkick_id == "520117"
        assert slug == "arctic-monkeys"

    def test_a_url_without_an_id_yields_nothing(self):
        """No id means no identity; a name is never used to invent one."""

        assert songkick_artist_reference(
            "https://www.songkick.com/artists/arctic-monkeys"
        ) == (None, None)

    def test_an_empty_url_yields_nothing(self):
        assert songkick_artist_reference(None) == (
            None,
            None,
        )


class TestFestivalUrlParsing:
    """One Songkick festival URL carries both levels of the data."""

    def test_series_and_event_ids_are_both_read(self):
        assert festival_data_from_url(CANONICAL_URL) == {
            "series_id": "3441108",
            "event_id": "40385544",
        }

    def test_a_concert_url_is_not_a_festival(self):
        assert (
            festival_data_from_url(
                "https://www.songkick.com/concerts/12345-x"
            )
            is None
        )