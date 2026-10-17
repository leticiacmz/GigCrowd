"""The series' own name, and how a date's name is told apart from it.

`festival_name_from_url` reads one level of a Songkick address - the edition
slug, which names one date - and the functions here read the other: the
series slug, which names the festival as a whole. The series profile heads
itself with that name, and the stored per-date names ("Lollapalooza 2027 @
Hipódromo de San Isidro") must never pass for it, so both the reading and
the shapes it must refuse are pinned here.
"""
from __future__ import annotations

from app.domain.festival import (
    festival_series_name_from_edition_name,
    festival_series_name_from_url,
    is_edition_name,
)


EDITION_URL = (
    "https://www.songkick.com/festivals/"
    "1235-lollapalooza/id/43456089-lollapalooza-2027"
)


def test_the_series_slug_is_the_series_name():
    assert festival_series_name_from_url(
        "https://www.songkick.com/festivals/1235-lollapalooza"
    ) == "Lollapalooza"


def test_an_edition_address_states_its_series_too():
    assert festival_series_name_from_url(EDITION_URL) == "Lollapalooza"


def test_a_bare_series_id_states_no_name():
    assert (
        festival_series_name_from_url(
            "https://www.songkick.com/festivals/1235"
        )
        is None
    )


def test_an_encoded_separator_is_refused_rather_than_displayed():
    assert (
        festival_series_name_from_url(
            "https://www.songkick.com/festivals/"
            "1235-lolla%2Fpalooza"
        )
        is None
    )


def test_no_address_states_no_name():
    assert festival_series_name_from_url(None) is None
    assert festival_series_name_from_url("") is None


def test_a_yearly_edition_name_is_recognised_as_one_date():
    assert is_edition_name("Lollapalooza 2027") is True


def test_a_venue_suffix_is_recognised_as_one_date():
    assert (
        is_edition_name(
            "Reading Festival 2026 @ Richfield Avenue"
        )
        is True
    )


def test_a_series_name_is_not_a_date():
    assert is_edition_name("Primavera Sound São Paulo") is False
    assert is_edition_name("Amf") is False


def test_a_year_inside_a_word_is_not_a_date_signature():
    assert is_edition_name("Rock in Rio 40 Anos") is False
    assert is_edition_name("Studio 2026 Sessions") is False


def test_the_edition_name_is_trimmed_to_its_series_part():
    assert (
        festival_series_name_from_edition_name(
            "Lollapalooza 2027 @ Hipódromo de San Isidro"
        )
        == "Lollapalooza"
    )


def test_a_trailing_year_alone_is_trimmed_too():
    assert (
        festival_series_name_from_edition_name(
            "AMF Festival 2026"
        )
        == "AMF Festival"
    )


def test_the_series_words_keep_their_own_spelling():
    """The trim removes the date's signature, never a letter of the name."""

    assert (
        festival_series_name_from_edition_name(
            "Festival Estéreo Picnic 2027 @ Parque Simón Bolívar"
        )
        == "Festival Estéreo Picnic"
    )


def test_a_series_name_has_nothing_to_trim():
    assert (
        festival_series_name_from_edition_name(
            "Primavera Sound São Paulo"
        )
        is None
    )


def test_a_name_that_is_only_a_date_leaves_nothing():
    assert festival_series_name_from_edition_name("2027") is None
