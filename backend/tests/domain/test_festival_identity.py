"""What a festival identity may expose, and what a name must refuse.

Three rules are pinned here, all of them about what a page will render:

* a URL is exposed only in the shape a browser can open - a relative path or
  a malformed string degrades to no link rather than to a broken one;
* a festival's name is never an artist's appearance title - "Demi Lovato
  Rock In Rio 2022" names the artist's page, not the festival;
* the festival type is read case-insensitively, so a row written before the
  canonicalisation still reads as a festival.
"""
from app.domain.festival import (
    festival_identity,
    festival_name,
    http_url_or_none,
)


SONGKICK_URL = (
    "https://www.songkick.com/festivals/91231-harvest/"
    "id/23537708-harvest-festival-2015"
)

RELATIVE_URL = "/festivals/91231-harvest/id/23537708-harvest-festival-2015"


def festival_event(**overrides) -> dict:
    """An imported festival date, in the shape the mapper stores it."""

    event = {
        "title": "alt-J Harvest Festival 2015",
        "event_type": "FestivalInstance",
        "artist_slugs": ["alt-j"],
        "lineup": [],
        "festival": {
            "series_id": "91231",
            "name": "Harvest Festival",
            "url": SONGKICK_URL,
            "edition": "2015",
        },
        "source": {
            "provider": "songkick",
            "external_id": "23537708",
            "url": SONGKICK_URL,
        },
    }

    event.update(overrides)

    return event


# ============================================================
# URL SHAPE
# ============================================================


def test_an_absolute_http_url_is_exposed_as_it_is():
    assert http_url_or_none(SONGKICK_URL) == SONGKICK_URL


def test_a_relative_path_is_not_a_url_a_browser_can_open():
    """A relative href would link into GigCrowd itself, not back to the source."""

    assert http_url_or_none(RELATIVE_URL) is None


def test_a_malformed_scheme_is_refused_rather_than_repaired():
    assert http_url_or_none("javascript:alert(1)") is None
    assert http_url_or_none("www.songkick.com/festivals/91231") is None
    assert http_url_or_none("not a url at all") is None


def test_an_empty_value_is_absent():
    assert http_url_or_none(None) is None
    assert http_url_or_none("") is None


def test_the_identity_exposes_only_openable_urls():
    """A stored relative path still yields a series id, but no broken link."""

    event = festival_event(
        festival={
            "series_id": "91231",
            "name": "Harvest Festival",
            "url": RELATIVE_URL,
        }
    )

    identity = festival_identity(event)

    assert identity["series_id"] == "91231"
    assert identity["url"] is None


def test_the_identity_carries_a_valid_url_through():
    identity = festival_identity(festival_event())

    assert identity["url"] == SONGKICK_URL


def test_the_identity_validates_the_official_url_separately():
    event = festival_event()
    event["festival"]["official_url"] = "not-a-url"

    identity = festival_identity(event)

    assert identity["official_url"] is None
    assert identity["url"] == SONGKICK_URL


# ============================================================
# FESTIVAL NAME REFUSES AN ARTIST-SHAPED TITLE
# ============================================================


def test_the_metadata_name_wins():
    assert festival_name(festival_event()) == "Harvest Festival"


def test_a_metadata_name_with_a_venue_suffix_is_kept():
    """Songkick names an edition "Festival @ Venue"; that is a real name.

    The artist-shape guard applies to a *title* fallback, not to a name read
    off the festival's own metadata, so an edition like "Rock In Rio 2022 @
    Barra Olympic Park" - which the local data holds dozens of - is returned
    unchanged rather than refused as if it were an artist's appearance page.
    """

    event = festival_event(
        festival={
            "series_id": "91231",
            "name": "Rock In Rio 2022 @ Barra Olympic Park",
            "url": SONGKICK_URL,
            "edition": "2022",
        },
        artist_slugs=["demi-lovato"],
        lineup=[{"name": "Demi Lovato", "songkick_id": "520117"}],
    )

    assert festival_name(event) == "Rock In Rio 2022 @ Barra Olympic Park"


def test_a_metadata_name_beginning_with_an_artist_is_refused():
    """A name written from the artist's appearance page is not the festival's.

    Songkick's artist pages embed a microformat naming each upcoming date
    after the performer ("Charli XCX @ Autódromo ..."), and an import that
    read it stored exactly that as the festival's name. The series id still
    identifies the festival; the name must not present the artist as it, so
    the caller shows a generic label instead.
    """

    event = festival_event(
        festival={
            "series_id": "1235",
            "name": "Charli XCX @ Autódromo José Carlos Pace (Interlagos)",
            "url": SONGKICK_URL,
        },
        title="Charli XCX @ Autódromo José Carlos Pace (Interlagos)",
        artist_slugs=["charli-xcx"],
        lineup=[{"name": "Charli XCX", "songkick_id": "2274326"}],
    )

    assert festival_name(event) is None


def test_the_identity_keeps_the_series_but_drops_an_artist_shaped_name():
    """Identity is the series id; the corrupted name is display-only noise."""

    event = festival_event(
        festival={
            "series_id": "1235",
            "name": "Charli XCX @ Autódromo José Carlos Pace (Interlagos)",
            "url": SONGKICK_URL,
        },
        artist_slugs=["charli-xcx"],
        lineup=[{"name": "Charli XCX", "songkick_id": "2274326"}],
    )

    identity = festival_identity(event)

    assert identity["series_id"] == "1235"
    assert identity["name"] is None


def test_an_official_edition_name_that_merely_shares_a_word_is_kept():
    """"Lollapalooza 2027 @ Interlagos" does not start with an artist name."""

    event = festival_event(
        festival={
            "series_id": "1235",
            "name": "Lollapalooza 2027 @ Autódromo José Carlos Pace",
            "url": SONGKICK_URL,
        },
        artist_slugs=["charli-xcx"],
        lineup=[{"name": "Charli XCX", "songkick_id": "2274326"}],
    )

    assert (
        festival_name(event)
        == "Lollapalooza 2027 @ Autódromo José Carlos Pace"
    )
    assert festival_identity(event)["name"] == (
        "Lollapalooza 2027 @ Autódromo José Carlos Pace"
    )


def test_a_title_beginning_with_a_lineup_artist_is_refused():
    """"Demi Lovato Rock In Rio 2022" names the artist's appearance page."""

    event = festival_event(
        title="Demi Lovato Rock In Rio 2022",
        festival=None,
        artist_slugs=["demi-lovato"],
        lineup=[
            {
                "name": "Demi Lovato",
                "songkick_id": "520117",
            }
        ],
    )

    assert festival_name(event) is None


def test_a_title_beginning_with_the_initiating_artist_slug_is_refused():
    """The initiating artist is on the record even when the lineup is not."""

    event = festival_event(
        title="alt-J Harvest Festival 2015",
        festival=None,
        artist_slugs=["alt-j"],
    )

    assert festival_name(event) is None


def test_an_artist_at_venue_title_is_refused():
    event = festival_event(
        title="Demi Lovato @ Barra Olympic Park",
        festival=None,
        artist_slugs=["demi-lovato"],
    )

    assert festival_name(event) is None


def test_a_title_that_is_not_artist_shaped_is_kept():
    """A title naming the festival, not the artist, is still a usable name."""

    event = festival_event(
        title="Rock In Rio 2022",
        festival=None,
        artist_slugs=["demi-lovato"],
        lineup=[{"name": "Demi Lovato", "songkick_id": "520117"}],
    )

    assert festival_name(event) == "Rock In Rio 2022"


def test_a_non_festival_event_still_has_no_festival_name():
    """A concert is not a festival with one edition."""

    event = festival_event(
        title="Demi Lovato @ Barra Olympic Park",
        event_type="Concert",
        festival=None,
        artist_slugs=["demi-lovato"],
    )

    assert festival_name(event) is None


# ============================================================
# FESTIVAL TYPE IS READ IN EITHER SPELLING
# ============================================================


def test_the_canonical_type_is_a_festival():
    assert festival_identity(festival_event()) is not None


def test_the_legacy_lowercase_type_is_still_a_festival():
    """Rows written before the canonicalisation carry lowercase `festival`."""

    event = festival_event(event_type="festival")

    assert festival_identity(event) is not None
    assert festival_name(event) == "Harvest Festival"


def test_a_concert_is_not_a_festival():
    """A concert whose own address states no series has no festival identity."""

    event = festival_event(
        event_type="Concert",
        festival=None,
        title="Demi Lovato at Barra Olympic Park",
        source={
            "provider": "songkick",
            "external_id": "123456",
            "url": "https://www.songkick.com/concerts/123456",
        },
    )

    assert festival_identity(event) is None
    assert festival_name(event) is None
