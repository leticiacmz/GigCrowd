"""A thinner second reading must not make a venue thinner.

Venues are read from several pages over the life of an import: one reading
brings the name and the address, another brings only the name because the
listing that carried it repeated nothing else. `$set`-ing every field from
every reading meant the thinnest one won - a venue that once had a city,
coordinates and a street lost them to a re-read that simply did not mention
them, and the next reader of that row saw a record that had forgotten what it
used to know.

So an update writes what the incoming reading actually states and nothing
else. Blank means "this page said nothing", never "this is no longer true",
and a provider id is kept for the same reason: an empty id would make the
venue undiscoverable by the very key that found it.
"""
from __future__ import annotations

import pytest
from bson import ObjectId

from app.domain.venue import Venue
from app.repositories.venue_repository import VenueRepository
from tests.support.fake_mongo import FakeDatabase


STORED = {
    "_id": ObjectId("64b7f0c0a1b2c3d4e5f60030"),
    "external_ids": {"songkick": "9001"},
    "name": "Parque de la Ciudad",
    "normalized_name": "parque de la ciudad",
    "slug": "parque-de-la-ciudad",
    "city": "Buenos Aires",
    "country": "AR",
    "region": "CABA",
    "latitude": -34.7856,
    "longitude": -58.4591,
    "street_address": "Av. Cnel. Rafael 10500",
    "postal_code": "1427",
}


def world() -> FakeDatabase:
    return FakeDatabase({"venues": [dict(STORED)]})


def venue_repository(database: FakeDatabase) -> VenueRepository:
    return VenueRepository(database)


def thin_reading(**overrides) -> Venue:
    """The same venue as a listing that named it and nothing else."""

    values = dict(
        external_ids={"songkick": "9001"},
        name="Parque de la Ciudad",
        normalized_name="parque de la ciudad",
        slug="parque-de-la-ciudad",
        city="",
        country="",
        region=None,
        latitude=None,
        longitude=None,
        street_address=None,
        postal_code=None,
    )
    values.update(overrides)
    return Venue(**values)


def stored(database: FakeDatabase) -> dict:
    return database["venues"].documents[0]


class TestAnIncompleteReadingChangesNothingItDidNotMention:

    @pytest.mark.asyncio
    async def test_the_city_survives_a_re_read_that_did_not_carry_it(self):
        database = world()

        updated = await venue_repository(database).upsert_venue(
            thin_reading()
        )

        assert updated is False
        assert stored(database)["city"] == "Buenos Aires"
        assert stored(database)["country"] == "AR"

    @pytest.mark.asyncio
    async def test_the_address_and_the_coordinates_survive_too(self):
        database = world()

        await venue_repository(database).upsert_venue(thin_reading())

        document = stored(database)

        assert document["street_address"] == (
            "Av. Cnel. Rafael 10500"
        )
        assert document["postal_code"] == "1427"
        assert document["latitude"] == -34.7856
        assert document["longitude"] == -58.4591
        assert document["region"] == "CABA"

    @pytest.mark.asyncio
    async def test_an_empty_provider_id_never_masks_a_real_one(self):
        """The id is how this venue is found again.

        Written through, an empty id would leave a row whose stored key had
        been replaced by nothing - discoverable by neither the id nor the
        name the fallback depends on.
        """

        database = world()

        await venue_repository(database).upsert_venue(
            thin_reading(external_ids={"songkick": ""})
        )

        assert stored(database)["external_ids"] == {
            "songkick": "9001"
        }


class TestWhatTheSourceDoesStateStillReachesStorage:

    @pytest.mark.asyncio
    async def test_a_correction_is_written(self):
        """Refusing to lose data is not the same as refusing to update it."""

        database = world()

        await venue_repository(database).upsert_venue(
            thin_reading(
                city="Ciudad Autonoma de Buenos Aires",
                country="Argentina",
            )
        )

        document = stored(database)

        assert document["city"] == (
            "Ciudad Autonoma de Buenos Aires"
        )
        assert document["country"] == "Argentina"

    @pytest.mark.asyncio
    async def test_a_second_provider_id_is_added_alongside_the_first(self):
        database = world()

        await venue_repository(database).upsert_venue(
            thin_reading(external_ids={"bandsintown": "40143"})
        )

        assert stored(database)["external_ids"] == {
            "songkick": "9001",
            "bandsintown": "40143",
        }

    @pytest.mark.asyncio
    async def test_a_reading_that_states_nothing_writes_nothing(self):
        """The degenerate case, and the whole rule in one assertion.

        Every field blank, so there is no `$set` at all rather than a `$set`
        of empty values pretending to be an update.
        """

        database = world()
        collection = database["venues"]

        written = []
        original_update_one = collection.update_one

        async def record(query, update):
            written.append(update)
            return await original_update_one(query, update)

        collection.update_one = record

        await venue_repository(database).upsert_venue(
            Venue(
                external_ids={"songkick": "9001"},
                name="",
                normalized_name="",
                slug="",
                city="",
                country="",
            )
        )

        assert written == []
        assert stored(database)["name"] == "Parque de la Ciudad"


class TestCreationIsStillCreation:

    @pytest.mark.asyncio
    async def test_an_unknown_venue_is_inserted(self):
        database = FakeDatabase({"venues": []})

        created = await venue_repository(database).upsert_venue(
            Venue(
                external_ids={"songkick": "9002"},
                name="Estadio Monumental",
                normalized_name="estadio monumental",
                slug="estadio-monumental",
                city="Buenos Aires",
                country="AR",
            )
        )

        assert created is True
        assert database["venues"].documents[0]["slug"] == (
            "estadio-monumental"
        )

    @pytest.mark.asyncio
    async def test_an_update_reports_itself_as_not_created(self):
        database = world()

        assert (
            await venue_repository(database).upsert_venue(
                thin_reading()
            )
            is False
        )
