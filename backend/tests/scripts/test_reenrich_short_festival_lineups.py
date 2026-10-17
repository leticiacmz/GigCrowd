"""What the short-lineup repair pass counts, and what it refuses to count.

The pass force-re-enqueues festival editions whose stored lineup is shorter
than the bill the catalogue already holds, so the classification is the whole
safety story: a row it accepts is one where a wider bill is already on file
and the edition's own page can state it; a row it refuses - no readable
address, a single known artist, a lineup already at the bill's size - is one
a read could not repair or never needed to. These tests pin that boundary
against documents shaped like the ones the incident left behind.
"""
from __future__ import annotations

from bson import ObjectId

from app.scripts.reenrich_short_festival_lineups import (
    address_stated_by,
    candidates_query,
    is_short,
    known_bill_size,
)


ADDRESS = (
    "https://www.songkick.com/festivals/"
    "1235-lollapalooza/id/43456089-lollapalooza-2027"
)


def an_edition(**overrides) -> dict:
    document = {
        "_id": ObjectId(),
        "title": "Charli XCX @ Autódromo José Carlos Pace (Interlagos)",
        "event_type": "FestivalInstance",
        "lineup": [{"name": "Charli XCX"}],
        "artist_slugs": ["charli-xcx"],
        "festival": {
            "series_id": "1235",
            "artist_ids": ["2274326"],
            "url": ADDRESS,
        },
        "source": {"url": ADDRESS},
    }

    document.update(overrides)

    return document


class TestTheKnownBill:
    """The bill is whichever of the two spellings is wider."""

    def test_the_catalogue_slugs_can_be_the_wider_list(self):
        document = an_edition(
            artist_slugs=["charli-xcx", "the-killers"],
            festival={"artist_ids": [], "url": None},
        )

        assert known_bill_size(document) == 2

    def test_the_sources_own_ids_can_be_the_wider_list(self):
        document = an_edition(
            artist_slugs=[],
            festival={"artist_ids": ["2274326", "11651"], "url": None},
        )

        assert known_bill_size(document) == 2


class TestShortness:
    def test_a_one_name_lineup_under_a_full_bill_is_short(self):
        document = an_edition(
            artist_slugs=[
                "charli-xcx",
                "the-killers",
                "david-guetta",
            ],
        )

        assert is_short(document) is True

    def test_a_lineup_at_the_bills_size_is_not_short(self):
        document = an_edition()

        assert is_short(document) is False

    def test_a_single_known_artist_is_not_a_shortened_bill(self):
        """Nothing wider is on file; there is no bill to restore."""

        document = an_edition()

        assert known_bill_size(document) == 1
        assert is_short(document) is False


class TestReadableAddress:
    def test_the_stored_source_address_is_read(self):
        assert address_stated_by(an_edition()) == ADDRESS

    def test_the_festival_block_is_tried_after_the_source(self):
        document = an_edition(
            source={"url": None},
            festival={
                "artist_ids": ["1", "2"],
                "url": "https://www.songkick.com/festivals/1-x",
            },
        )

        assert (
            address_stated_by(document)
            == "https://www.songkick.com/festivals/1-x"
        )

    def test_a_foreign_address_is_not_readable(self):
        document = an_edition(
            source={"url": "https://example.com/festivals/1"},
            festival={"artist_ids": ["1"], "url": None},
        )

        assert address_stated_by(document) is None

    def test_an_edition_with_no_address_at_all(self):
        document = an_edition(
            source=None,
            festival={"artist_ids": ["1"], "url": None},
        )

        assert address_stated_by(document) is None


class TestTheCandidateQuery:
    def test_it_asks_for_festival_editions_with_a_songkick_address(self):
        query = candidates_query()

        assert query["$and"][0] == {
            "event_type": {"$regex": "festival", "$options": "i"}
        }

        fields = [
            next(iter(clause))
            for clause in query["$and"][1]["$or"]
        ]

        assert fields == [
            "source.url",
            "festival.url",
            "festival.official_url",
        ]
