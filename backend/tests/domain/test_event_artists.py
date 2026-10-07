"""Which artists an event belongs to.

These are the rules that decide whether an artist appears on a person's concert
history at all, so they are tested directly rather than through a route. The
cases that matter are the ones that were previously wrong: a festival's
performers are only reachable through its lineup, and a lineup can repeat.
"""
from __future__ import annotations

import pytest

from app.domain.event_artists import (
    artist_membership_filter,
    artist_slugs_of,
    bare_songkick_id,
    count_attended_shows_per_artist,
    direct_artist_slugs,
    event_artists,
    lineup_artist_slugs,
    lineup_songkick_ids,
    personal_artist_slugs,
    prefixed_songkick_id,
)


def concert(slug: str | None = None, slugs: list | None = None) -> dict:
    document = {
        "_id": "event-1",
        "event_type": "Concert",
        "title": "Nova at the Warehouse",
        "artist_slug": slug,
        "artist_slugs": slugs or [],
    }

    return document


def festival(lineup: list, event_id: str = "event-2") -> dict:
    return {
        "_id": event_id,
        "event_type": "FestivalInstance",
        "title": "Festival Vale",
        "artist_slug": None,
        "artist_slugs": [],
        "lineup": lineup,
    }


def entry(
    name: str,
    songkick_id: str | None = None,
) -> dict:
    from app.utils.slug import generate_slug

    return {
        "name": name,
        "songkick_id": songkick_id,
        "slug": generate_slug(name),
        "order": 0,
    }


class TestIdentifierForms:
    def test_the_two_spellings_describe_one_artist(self):
        assert bare_songkick_id("Artist976211") == "976211"
        assert prefixed_songkick_id("976211") == "Artist976211"

    def test_either_spelling_survives_a_round_trip(self):
        for value in ("976211", "Artist976211"):
            assert prefixed_songkick_id(
                bare_songkick_id(value)
            ) == prefixed_songkick_id(value)

    def test_nothing_becomes_an_empty_string_rather_than_a_value(self):
        assert bare_songkick_id(None) is None
        assert bare_songkick_id("") is None
        assert bare_songkick_id("   ") is None


class TestDirectReferences:
    def test_a_single_headline_is_read(self):
        assert direct_artist_slugs(concert(slug="nova")) == {"nova"}

    def test_a_multi_artist_bill_is_read(self):
        document = concert(slug="nova", slugs=["nova", "support"])

        assert direct_artist_slugs(document) == {"nova", "support"}

    def test_an_older_row_with_only_the_headline_still_works(self):
        assert artist_slugs_of(concert(slug="nova")) == {"nova"}

    def test_a_repeated_slug_is_one_artist(self):
        document = concert(slug="nova", slugs=["nova", "nova"])

        assert direct_artist_slugs(document) == {"nova"}


class TestLineupReferences:
    def test_a_festival_names_its_performers_in_the_lineup(self):
        # This is the case the whole module exists for: a festival has no
        # headline, so without the lineup Marina Sena would not be on the event
        # at all.
        document = festival([
            entry("Marina Sena", "3090429"),
            entry("Tim Bernardes", "2668421"),
        ])

        assert lineup_artist_slugs(document) == {
            "marina-sena",
            "tim-bernardes",
        }

        assert direct_artist_slugs(document) == set()

        assert artist_slugs_of(document) == {
            "marina-sena",
            "tim-bernardes",
        }

    def test_a_repeated_performer_is_one_artist_of_that_event(self):
        # The same act twice on one bill is one performer of that event.
        document = festival([
            entry("O Terno", "2921978"),
            entry("O Terno", "2921978"),
        ])

        assert lineup_artist_slugs(document) == {"o-terno"}

    def test_lineup_ids_are_read_in_their_bare_form(self):
        document = festival([
            entry("Marina Sena", "Artist3090429"),
        ])

        assert lineup_songkick_ids(document) == {"3090429"}

    def test_an_entry_without_an_id_is_still_a_performer(self):
        document = festival([entry("Unknown Act", None)])

        assert artist_slugs_of(document) == {"unknown-act"}
        assert lineup_songkick_ids(document) == set()

    def test_a_malformed_lineup_is_ignored_rather_than_crashing(self):
        document = festival(["not a dict", None, entry("Nova", "1")])

        assert artist_slugs_of(document) == {"nova"}

    def test_an_event_with_no_lineup_is_simply_empty(self):
        assert lineup_artist_slugs({"_id": "e"}) == set()


class TestMembershipFilter:
    def test_it_matches_direct_references_and_lineup_entries(self):
        clause = artist_membership_filter("marina-sena")

        clauses = clause["$or"]

        assert {"artist_slug": "marina-sena"} in clauses
        assert {"artist_slugs": "marina-sena"} in clauses
        assert {"lineup.slug": "marina-sena"} in clauses

    def test_a_known_songkick_id_is_matched_on_the_lineup(self):
        # The provider identifier is the stronger link, so a lineup row whose
        # slug disagrees is still found.
        clause = artist_membership_filter(
            "marina-sena", "3090429"
        )

        clauses = clause["$or"]

        assert {"lineup.songkick_id": "3090429"} in clauses
        assert {"lineup.songkick_id": "Artist3090429"} in clauses

    def test_no_id_means_no_id_clauses(self):
        clauses = artist_membership_filter("nova")["$or"]

        assert not [
            c for c in clauses
            if "lineup.songkick_id" in c
        ]

    def test_it_never_searches_the_title(self):
        # Matching a title would claim an artist played a show whose bill never
        # said so.
        rendered = str(artist_membership_filter("marina-sena"))

        assert "title" not in rendered


class TestPersonalAttendance:
    """A lineup is not a record of what someone watched.

    These are the rules that decide whose name appears on someone's concert
    history. They are deliberately stricter than `artist_slugs_of`, which
    answers a different question: which acts an event belongs to.
    """

    def test_a_concert_counts_for_its_own_artist(self):
        assert count_attended_shows_per_artist(
            [concert(slug="marina-sena")]
        ) == {"marina-sena": 1}

    def test_attending_a_festival_date_counts_for_nobody(self):
        # Someone can buy a festival ticket and see one act on it. Attendance at
        # the festival is not attendance at every performance.
        events = [festival([
            entry("Marina Sena", "3090429"),
            entry("Tim Bernardes", "2668421"),
            entry("O Terno", "2921978"),
        ])]

        assert count_attended_shows_per_artist(events) == {}

    def test_two_festival_dates_count_for_nobody_either(self):
        events = [
            festival([entry("Marina Sena", "1")], "day-1"),
            festival([entry("Marina Sena", "1")], "day-2"),
        ]

        assert count_attended_shows_per_artist(events) == {}

    def test_a_support_act_on_a_concert_is_not_the_headline_attendance(self):
        # A Marina Sena show can carry a four-act bill. The event belongs to
        # Marina Sena, so that is what attending it means.
        document = {
            "_id": "event-1",
            "event_type": "Concert",
            "artist_slug": "marina-sena",
            "artist_slugs": ["marina-sena"],
            "lineup": [
                entry("Anitta", "1"),
                entry("Marina Sena", "3090429"),
                entry("Kamisa 10", "2"),
            ],
        }

        assert personal_artist_slugs(document) == {"marina-sena"}

        assert count_attended_shows_per_artist([document]) == {
            "marina-sena": 1
        }

    def test_a_lineup_that_mirrors_the_headline_adds_nothing(self):
        # Most imported concerts carry a lineup that simply repeats the artist.
        # Reading it must not produce a second count.
        document = {
            "_id": "event-1",
            "event_type": "Concert",
            "artist_slug": "gal-costa",
            "artist_slugs": ["gal-costa"],
            "lineup": [entry("Gal Costa", "1")],
        }

        assert count_attended_shows_per_artist([document]) == {
            "gal-costa": 1
        }

    def test_each_attended_concert_counts_once(self):
        events = [
            {**concert(slug="marina-sena"), "_id": "a"},
            {**concert(slug="marina-sena"), "_id": "b"},
            {**concert(slug="marina-sena"), "_id": "c"},
        ]

        assert count_attended_shows_per_artist(events) == {
            "marina-sena": 3
        }

    def test_an_artist_repeated_on_one_bill_counts_once(self):
        document = {
            "_id": "event-1",
            "event_type": "Concert",
            "artist_slug": "o-terno",
            "artist_slugs": ["o-terno", "o-terno"],
        }

        assert count_attended_shows_per_artist([document]) == {
            "o-terno": 1
        }

    def test_a_multi_artist_bill_counts_each_headline(self):
        document = concert(
            slug="nova", slugs=["nova", "support"]
        )

        assert count_attended_shows_per_artist([document]) == {
            "nova": 1,
            "support": 1,
        }

    def test_a_concert_and_a_festival_date_together_count_only_the_concert(self):
        events = [
            concert(slug="nova"),
            festival([entry("Nova", "1")], "day-1"),
        ]

        assert count_attended_shows_per_artist(events) == {"nova": 1}

    def test_an_event_with_no_direct_artist_contributes_nothing(self):
        assert count_attended_shows_per_artist([festival([])]) == {}

    def test_no_events_is_no_counts(self):
        assert count_attended_shows_per_artist([]) == {}

    def test_membership_and_personal_attendance_disagree_on_a_festival(self):
        # The two questions really are different, and the festival is where they
        # come apart.
        document = festival([
            entry("Marina Sena", "3090429"),
            entry("Tim Bernardes", "2668421"),
        ])

        assert artist_slugs_of(document) == {
            "marina-sena",
            "tim-bernardes",
        }

        assert personal_artist_slugs(document) == set()


class TestStableOrder:
    def test_the_same_event_always_yields_the_same_list(self):
        document = festival([
            entry("Rubel", "2"),
            entry("Marina Sena", "1"),
        ])

        assert event_artists(document) == event_artists(document)
        assert event_artists(document) == [
            "marina-sena",
            "rubel",
        ]


class TestAnEventNeverShowsAnActTwice:
    """One performer is one row on a bill.

    Ingest already deduplicates, but a lineup also arrives from imports,
    fixtures and partial patches. Enforcing it on the domain value means no
    response can print the same act twice, and it is the same rule the counting
    above relies on, applied where a reader sees it.
    """

    def test_a_repeated_performer_collapses_to_one_row(self):
        from app.domain.event import Event

        event = Event(
            id="event-1",
            title="Festival Vale 2026 - Day 1",
            event_type="FestivalInstance",
            venue_slug="festival-vale",
            lineup=[
                entry("Marina Sena", "3090429"),
                entry("O Terno", "2921978"),
                entry("O Terno", "2921978"),
            ],
        )

        assert [row.name for row in event.lineup] == [
            "Marina Sena",
            "O Terno",
        ]

    def test_the_first_appearance_keeps_its_place(self):
        from app.domain.event import Event

        event = Event(
            title="Festival Vale 2026 - Day 1",
            venue_slug="festival-vale",
            lineup=[
                entry("Marina Sena", "1"),
                entry("Rubel", "2"),
                entry("Marina Sena", "1"),
            ],
        )

        assert [row.order for row in event.lineup] == [0, 1]

    def test_two_rows_sharing_an_id_are_one_even_with_different_names(self):
        from app.domain.event import Event

        # The id is the identity, so a source that spells the act two ways does
        # not put it on the bill twice.
        event = Event(
            title="Festival Vale 2026 - Day 1",
            venue_slug="festival-vale",
            lineup=[
                {"name": "Marina Sena", "songkick_id": "3090429"},
                {"name": "MARINA SENA", "songkick_id": "3090429"},
            ],
        )

        assert len(event.lineup) == 1
        assert event.lineup[0].name == "Marina Sena"
