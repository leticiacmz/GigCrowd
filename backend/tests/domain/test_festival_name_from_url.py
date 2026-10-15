"""The edition's name, read only from the official address.

`festival_name_from_url` exists because an import that refused an
artist-shaped name could end up with no name at all, and the official
address still states one - but only in the shape Songkick itself names an
edition. These cases hold the line between reading and inventing: the
edition slug after `/id/` with a year standing as its own word is read
(word for word, plus the venue the source states); everything else - a
series-only address, a slug without the year, a year welded to a word -
answers `None`, because a name nobody stated must not appear.
"""
from app.domain.festival import festival_name_from_url


LOLLAPALOOZA_2027 = (
    "https://www.songkick.com/festivals/1235-lollapalooza"
    "/id/43456089-lollapalooza-2027"
)


def test_the_edition_slug_ending_in_a_year_is_the_name():
    assert festival_name_from_url(
        LOLLAPALOOZA_2027
    ) == "Lollapalooza 2027"


def test_the_stated_venue_is_appended_the_way_songkick_names_editions():
    assert festival_name_from_url(
        LOLLAPALOOZA_2027,
        "Autódromo de Interlagos",
    ) == "Lollapalooza 2027 @ Autódromo de Interlagos"


def test_a_tba_venue_is_absence_and_appends_nothing():
    assert festival_name_from_url(
        LOLLAPALOOZA_2027,
        "TBA",
    ) == "Lollapalooza 2027"

    assert festival_name_from_url(
        LOLLAPALOOZA_2027,
        "tba.",
    ) == "Lollapalooza 2027"


def test_no_venue_means_no_separator():
    assert festival_name_from_url(
        LOLLAPALOOZA_2027,
        None,
    ) == "Lollapalooza 2027"


def test_a_series_only_address_states_no_edition_and_no_name():
    """The series slug names the festival as a whole, not this edition."""

    assert festival_name_from_url(
        "https://www.songkick.com/festivals/1235-lollapalooza"
    ) is None


def test_an_edition_slug_without_a_year_is_not_a_name():
    """`.../id/43456089-lollapalooza-argentina` says what, not which year."""

    assert festival_name_from_url(
        "https://www.songkick.com/festivals/1235-lollapalooza"
        "/id/43456089-lollapalooza-argentina"
    ) is None


def test_a_year_welded_to_a_word_is_not_an_editions_year():
    assert festival_name_from_url(
        "https://www.songkick.com/festivals/1235-lollapalooza"
        "/id/43456089-lollapalooza2027"
    ) is None


def test_query_parameters_are_not_part_of_the_slug():
    assert festival_name_from_url(
        LOLLAPALOOZA_2027 + "?utm_medium=organic"
    ) == "Lollapalooza 2027"


def test_an_encoded_separator_is_refused_rather_than_displayed():
    assert festival_name_from_url(
        "https://www.songkick.com/festivals/1235-lollapalooza"
        "/id/43456089-lollapalooza%2F2027"
    ) is None


def test_no_address_at_all_states_no_name():
    assert festival_name_from_url(None) is None
    assert festival_name_from_url("") is None
