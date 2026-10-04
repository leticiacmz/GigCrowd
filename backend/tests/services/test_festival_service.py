"""The festival page: identity, dates and lineup, kept apart.

Two things are easy to get wrong here and both produce a page that looks fine
while stating something false. The first is collapsing a festival into one of
its dates, so a six-day festival is described by whichever night the reader
arrived on. The second is borrowing one date's lineup for the whole series,
which claims the same performers play every night.

These tests pin the separation, and the decision that an edition exists only
because it was imported rather than because a title looked like a year.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from bson import ObjectId

from app.services.festival_service import FestivalService
from tests.support.fake_mongo import FakeDatabase


SERIES = "3441108"

CANONICAL = (
    "https://www.songkick.com/festivals/"
    "3441108-primavera/id/40385544-primavera-2022"
)


def festival_document(
    object_id: str,
    title: str,
    starts_at=None,
    ends_at=None,
    lineup=None,
    series_id: str = SERIES,
    **overrides,
) -> dict:
    document = {
        "_id": ObjectId(object_id),
        "title": title,
        "event_type": "FestivalInstance",
        "starts_at": starts_at,
        "ends_at": ends_at,
        "lineup": lineup if lineup is not None else [],
        "date_status": "source",
        "venue_slug": "distrito-anhembi",
        "festival": {
            "series_id": series_id,
            "name": "Primavera Sound São Paulo",
            "url": CANONICAL,
        },
    }

    document.update(overrides)

    return document


LINEUP_DAY_ONE = [
    {
        "name": "Arctic Monkeys",
        "songkick_id": "520117",
        "slug": "arctic-monkeys",
        "url": (
            "https://www.songkick.com/artists/"
            "520117-arctic-monkeys"
        ),
        "image": None,
        "genres": ["rock"],
        "order": 0,
    },
    {
        "name": "Nobody Imported",
        "songkick_id": "999999",
        "slug": "nobody-imported",
        "url": None,
        "image": None,
        "genres": [],
        "order": 1,
    },
]


class Repository:
    """Just enough of `EventRepository` for the service under test."""

    def __init__(self, db):
        self.db = db
        self.collection = db["events"]

    async def get_document_by_id(self, event_id):
        if not ObjectId.is_valid(event_id):
            return None

        return await self.collection.find_one(
            {"_id": ObjectId(event_id)}
        )


class Artists:
    def __init__(self, db):
        self.collection = db["artists"]


def build(documents, artists=None):
    database = FakeDatabase(
        {
            "events": documents,
            "artists": artists or [],
        }
    )

    return FestivalService(
        Repository(database),
        artist_repository=Artists(database),
    )


DAY_ONE = festival_document(
    "507f1f77bcf86cd799439011",
    "Primavera Sound Dia 1 2022",
    starts_at=datetime(2022, 10, 31, 19, tzinfo=UTC),
    ends_at=datetime(2022, 11, 1, 2, tzinfo=UTC),
    lineup=LINEUP_DAY_ONE,
)

DAY_TWO = festival_document(
    "507f1f77bcf86cd799439012",
    "Primavera Sound Dia 2 2022",
    starts_at=datetime(2022, 11, 2, 19, tzinfo=UTC),
    ends_at=datetime(2022, 11, 3, 2, tzinfo=UTC),
    lineup=[
        {
            "name": "Pixies",
            "songkick_id": "271757",
            "slug": "pixies",
            "url": None,
            "image": None,
            "genres": ["rock"],
            "order": 0,
        }
    ],
)


class TestIdentity:
    """The series, which is not any one of its dates."""

    @pytest.mark.asyncio
    async def test_the_series_id_is_returned(self):
        service = build([DAY_ONE])

        festival = await service.get_festival(
            "507f1f77bcf86cd799439011"
        )

        assert festival.identity.series_id == SERIES

    @pytest.mark.asyncio
    async def test_the_identity_carries_no_single_date(self):
        """A six-day festival does not have one date to show."""

        service = build([DAY_ONE, DAY_TWO])

        festival = await service.get_festival(
            "507f1f77bcf86cd799439011"
        )

        # The span is stated as a range of the editions' own dates, and no
        # single date is presented as the festival's date.
        assert festival.identity.first_date == datetime(
            2022, 10, 31, 19, tzinfo=UTC
        )
        assert festival.identity.last_date == datetime(
            2022, 11, 3, 2, tzinfo=UTC
        )

    @pytest.mark.asyncio
    async def test_a_concert_has_no_festival_page(self):
        concert = festival_document(
            "507f1f77bcf86cd799439013",
            "A Concert",
            starts_at=datetime(2022, 5, 1, tzinfo=UTC),
            festival=None,
            event_type="Concert",
        )

        service = build([concert])

        assert (
            await service.get_festival(
                "507f1f77bcf86cd799439013"
            )
            is None
        )

    @pytest.mark.asyncio
    async def test_a_missing_event_has_no_festival_page(self):
        service = build([DAY_ONE])

        assert (
            await service.get_festival("507f1f77bcf86cd799439099")
            is None
        )

    @pytest.mark.asyncio
    async def test_an_id_that_is_not_an_id_has_no_festival_page(self):
        """A bad id is a missing event, not a database error."""

        service = build([DAY_ONE])

        assert await service.get_festival("not-an-id") is None

    @pytest.mark.asyncio
    async def test_two_series_are_never_merged(self):
        """Names repeat across cities and years; ids do not."""

        other = festival_document(
            "507f1f77bcf86cd799439014",
            "Primavera Sound Madrid 2022",
            starts_at=datetime(2022, 6, 2, tzinfo=UTC),
            festival={
                "series_id": "9999999",
                "name": "Primavera Sound São Paulo",
                "url": None,
            },
        )

        service = build([DAY_ONE, other])

        festival = await service.get_festival(
            "507f1f77bcf86cd799439011"
        )

        assert festival.identity.editions_count == 1
        assert festival.identity.series_id == SERIES


class TestEditions:
    """Every date held for the series, each as its own row."""

    @pytest.mark.asyncio
    async def test_both_dates_are_listed(self):
        service = build([DAY_ONE, DAY_TWO])

        festival = await service.get_festival(
            "507f1f77bcf86cd799439011"
        )

        assert festival.identity.editions_count == 2
        assert {
            entry.event.id
            for entry in festival.editions
        } == {
            "507f1f77bcf86cd799439011",
            "507f1f77bcf86cd799439012",
        }

    @pytest.mark.asyncio
    async def test_dates_are_listed_nearest_first(self):
        """The page is read to answer "when can I still get there"."""

        service = build([DAY_ONE, DAY_TWO])

        festival = await service.get_festival(
            "507f1f77bcf86cd799439011"
        )

        assert festival.editions[0].event.id == (
            "507f1f77bcf86cd799439012"
        )

    @pytest.mark.asyncio
    async def test_the_arrived_date_is_marked_as_selected(self):
        service = build([DAY_ONE, DAY_TWO])

        festival = await service.get_festival(
            "507f1f77bcf86cd799439012"
        )

        assert festival.selected_event_id == (
            "507f1f77bcf86cd799439012"
        )

    @pytest.mark.asyncio
    async def test_every_edition_keeps_its_own_dates(self):
        service = build([DAY_ONE, DAY_TWO])

        festival = await service.get_festival(
            "507f1f77bcf86cd799439011"
        )

        for entry in festival.editions:
            assert entry.event.starts_at is not None
            assert entry.event.ends_at is not None

    @pytest.mark.asyncio
    async def test_an_undated_edition_is_still_listed(self):
        """Hiding it would hide the records that most need attention."""

        undated = festival_document(
            "507f1f77bcf86cd799439015",
            "Primavera Sound Dia 3 2022",
        )

        service = build([DAY_ONE, undated])

        festival = await service.get_festival(
            "507f1f77bcf86cd799439011"
        )

        assert festival.identity.editions_count == 2

    @pytest.mark.asyncio
    async def test_an_undated_edition_sorts_last(self):
        undated = festival_document(
            "507f1f77bcf86cd799439015",
            "Primavera Sound Dia 3 2022",
        )

        service = build([undated, DAY_ONE])

        festival = await service.get_festival(
            "507f1f77bcf86cd799439011"
        )

        assert festival.editions[-1].event.id == (
            "507f1f77bcf86cd799439015"
        )

    @pytest.mark.asyncio
    async def test_only_the_arrived_date_is_listed_when_it_is_alone(self):
        service = build([DAY_ONE])

        festival = await service.get_festival(
            "507f1f77bcf86cd799439011"
        )

        assert festival.identity.editions_count == 1

    @pytest.mark.asyncio
    async def test_the_arrived_event_is_found_among_many_dates(self):
        """The page must be able to say which date the reader came from."""

        service = build([DAY_ONE, DAY_TWO])

        festival = await service.get_festival(
            "507f1f77bcf86cd799439011"
        )

        # The first date, not the one that happens to sort first.
        assert festival.selected_event_id == (
            "507f1f77bcf86cd799439011"
        )
        assert festival.lineup[0].name == "Arctic Monkeys"


class TestLineup:
    """The lineup belongs to one date, and links only where a page exists."""

    @pytest.mark.asyncio
    async def test_the_lineup_is_the_arrived_dates_own(self):
        """Not the newest date's, and not a union of every date."""

        service = build([DAY_ONE, DAY_TWO])

        festival = await service.get_festival(
            "507f1f77bcf86cd799439011"
        )

        assert [
            entry.name
            for entry in festival.lineup
        ] == ["Arctic Monkeys", "Nobody Imported"]

    @pytest.mark.asyncio
    async def test_the_other_dates_lineup_is_its_own(self):
        service = build([DAY_ONE, DAY_TWO])

        festival = await service.get_festival(
            "507f1f77bcf86cd799439011"
        )

        by_id = {
            entry.event.id: entry
            for entry in festival.editions
        }

        assert [
            entry.name
            for entry in by_id[
                "507f1f77bcf86cd799439012"
            ].lineup
        ] == ["Pixies"]

    @pytest.mark.asyncio
    async def test_an_imported_artist_resolves_to_its_page(self):
        artists = [
            {
                "_id": 1,
                "slug": "arctic-monkeys-gigcrowd",
                "external_ids": {"songkick": "Artist520117"},
            }
        ]

        service = build([DAY_ONE], artists=artists)

        festival = await service.get_festival(
            "507f1f77bcf86cd799439011"
        )

        assert festival.lineup[0].artist_slug == (
            "arctic-monkeys-gigcrowd"
        )

    @pytest.mark.asyncio
    async def test_an_unimported_artist_resolves_to_nothing(self):
        """A wrong link is worse than no link, and no artist is created."""

        service = build([DAY_ONE])

        festival = await service.get_festival(
            "507f1f77bcf86cd799439011"
        )

        assert festival.lineup[1].artist_slug is None

    @pytest.mark.asyncio
    async def test_a_spotify_id_is_never_matched_against_a_songkick_id(self):
        """The two id spaces are unrelated; matching across them is a bug."""

        artists = [
            {
                "_id": 1,
                "slug": "wrong-artist",
                "external_ids": {
                    "spotify": "0LcFqbDKbN7",
                    "songkick": "Artist0LcFqbDKbN7",
                },
            }
        ]

        service = build([DAY_ONE], artists=artists)

        festival = await service.get_festival(
            "507f1f77bcf86cd799439011"
        )

        # The Songkick id 520117 is not 0LcFqbDKbN7, so nothing matches.
        assert festival.lineup[0].artist_slug is None

    @pytest.mark.asyncio
    async def test_every_lineup_entry_is_resolved_in_one_query(self):
        """Resolution must not become a request per performer."""

        artists = [
            {
                "_id": 1,
                "slug": "arctic-monkeys-gigcrowd",
                "external_ids": {"songkick": "Artist520117"},
            }
        ]

        database = FakeDatabase(
            {"events": [DAY_ONE], "artists": artists}
        )

        queries: list[dict] = []
        original = database["artists"].find

        def counting_find(query=None, projection=None):
            queries.append(query or {})
            return original(query, projection)

        database["artists"].find = counting_find

        service = FestivalService(
            Repository(database),
            artist_repository=Artists(database),
        )

        await service.get_festival("507f1f77bcf86cd799439011")

        assert len(queries) == 1

    @pytest.mark.asyncio
    async def test_a_festival_without_a_lineup_returns_an_empty_one(self):
        """An empty lineup is different from a lineup that could not be read."""

        empty = festival_document(
            "507f1f77bcf86cd799439016",
            "Primavera Sound Dia 4 2022",
            starts_at=datetime(2022, 11, 4, tzinfo=UTC),
        )

        service = build([empty])

        festival = await service.get_festival(
            "507f1f77bcf86cd799439016"
        )

        assert festival.lineup == []

    @pytest.mark.asyncio
    async def test_a_performer_without_an_id_keeps_its_name(self):
        named_only = festival_document(
            "507f1f77bcf86cd799439017",
            "Primavera Sound Dia 5 2022",
            starts_at=datetime(2022, 11, 5, tzinfo=UTC),
            lineup=[
                {
                    "name": "Unidentified Act",
                    "songkick_id": None,
                    "slug": None,
                    "url": None,
                    "image": None,
                    "genres": [],
                    "order": 0,
                }
            ],
        )

        service = build([named_only])

        festival = await service.get_festival(
            "507f1f77bcf86cd799439017"
        )

        assert festival.lineup[0].name == "Unidentified Act"
        assert festival.lineup[0].artist_slug is None

    @pytest.mark.asyncio
    async def test_the_same_performer_is_not_listed_twice(self):
        duplicated = festival_document(
            "507f1f77bcf86cd799439018",
            "Primavera Sound Dia 6 2022",
            starts_at=datetime(2022, 11, 6, tzinfo=UTC),
            lineup=[
                LINEUP_DAY_ONE[0],
                dict(LINEUP_DAY_ONE[0]),
            ],
        )

        service = build([duplicated])

        festival = await service.get_festival(
            "507f1f77bcf86cd799439018"
        )

        assert len(festival.lineup) == 2