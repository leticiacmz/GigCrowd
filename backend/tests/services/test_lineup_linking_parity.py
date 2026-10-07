"""An event page and a festival page show the same bill.

They are two routes onto one set of performers, so the same name has to be
pressable on both. For a long while it was not: the festival route resolved
Songkick ids into GigCrowd pages and the event route did not, so an act GigCrowd
had imported - with a discography, a photograph and a follower count - appeared
as a plain unpressable name on the event page and as a link one click away on the
festival page.

The asymmetry is the kind of bug that survives review, because each route looks
correct in isolation and nobody opens both to compare. So the test opens both.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from bson import ObjectId

from app.repositories.artist_repository import ArtistRepository
from app.repositories.event_repository import EventRepository
from app.repositories.venue_repository import VenueRepository
from app.services.event_service import EventService
from app.services.festival_service import FestivalService
from tests.support.fake_mongo import FakeDatabase


NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)

LINEUP = [
    {"name": "Marina Sena", "songkick_id": "10176016"},
    {"name": "Tim Bernardes", "songkick_id": "8618899"},
    # Announced, but never validated into an artist: renders as a plain name.
    {"name": "Victo", "songkick_id": "9988771"},
]

EVENT = {
    # Real ObjectIds, because that is what MongoDB stores and what every lookup
    # in these services addresses by. A string here would make every read return
    # nothing and every test pass for the wrong reason.
    "_id": ObjectId("64b7f0c0a1b2c3d4e5f60010"),
    "title": "Festival Vale 2027",
    "event_type": "FestivalInstance",
    "starts_at": NOW,
    "ends_at": NOW,
    "venue_slug": "sao-paulo-distrito-anhembi",
    "city": "Sao Paulo",
    "country": "Brazil",
    "lineup": LINEUP,
    "festival": {
        "series_id": "9900200",
        "name": "Festival Vale",
        "edition": "2027",
    },
    "source": {
        "provider": "songkick",
        "url": (
            "https://www.songkick.com/festivals/"
            "9900200-festival-vale/id/9900204"
        ),
    },
    "external_ids": {"songkick": "9900204"},
}

VENUE = {
    "_id": ObjectId("64b7f0c0a1b2c3d4e5f60020"),
    "name": "Distrito Anhembi",
    "slug": "sao-paulo-distrito-anhembi",
    "city": "Sao Paulo",
    "country": "Brazil",
    "external_ids": {},
}

ARTISTS = [
    {
        "_id": ObjectId("64b7f0c0a1b2c3d4e5f60001"),
        "name": "Marina Sena",
        "normalized_name": "marina sena",
        "slug": "marina-sena",
        "external_ids": {"songkick": "Artist10176016"},
        "genres": ["MPB"],
        "image": None,
        "popularity": None,
        "verified": False,
        "created_at": NOW,
        "updated_at": NOW,
    },
    {
        "_id": ObjectId("64b7f0c0a1b2c3d4e5f60002"),
        "name": "Tim Bernardes",
        "normalized_name": "tim bernardes",
        "slug": "tim-bernardes",
        "external_ids": {"songkick": "Artist8618899"},
        "genres": ["MPB"],
        "image": None,
        "popularity": None,
        "verified": False,
        "created_at": NOW,
        "updated_at": NOW,
    },
    {
        "_id": ObjectId("64b7f0c0a1b2c3d4e5f60003"),
        "name": "Victo",
        "normalized_name": "victo",
        "slug": "victo",
        # Stored under a different form than the lineup announces it, which is
        # what the resolver exists to reconcile.
        "external_ids": {"songkick": "Artist9988771"},
        "genres": [],
        "image": None,
        "popularity": None,
        "verified": False,
        "created_at": NOW,
        "updated_at": NOW,
    },
]


def a_world():
    return FakeDatabase(
        {
            "events": [dict(EVENT)],
            "venues": [dict(VENUE)],
            "artists": [dict(artist) for artist in ARTISTS],
        }
    )


def services(database):
    artists = ArtistRepository(database)

    events = EventRepository(database)
    venues = VenueRepository(database)

    return (
        EventService(events, venues, artists),
        FestivalService(events, artists),
    )


def event_id() -> str:
    return str(EVENT["_id"])


def by_name(lineup) -> dict:
    return {
        entry.name: entry for entry in (lineup or [])
    }


class TestTheEventPageLinksItsLineup:
    @pytest.mark.asyncio
    async def test_an_artist_with_a_page_is_pressable(self):
        database = a_world()

        event_service, _ = services(database)

        event = await event_service.get_event(event_id())

        entries = by_name(event.lineup)

        assert (
            entries["Marina Sena"].artist_slug == "marina-sena"
        )
        assert (
            entries["Tim Bernardes"].artist_slug
            == "tim-bernardes"
        )

    @pytest.mark.asyncio
    async def test_the_rest_of_the_entry_survives(self):
        """Only `artist_slug` is added. The name is the entry."""

        database = a_world()

        event_service, _ = services(database)

        event = await event_service.get_event(event_id())

        assert event.lineup[0].name == "Marina Sena"
        assert event.lineup[0].songkick_id == "10176016"

    @pytest.mark.asyncio
    async def test_an_id_shown_in_another_form_still_resolves(self):
        """The catalogue stores `Artist10176016`; a lineup says `10176016`.

        Treating those as different identities would leave most of a real lineup
        unpressable, since the two forms come from different parts of the same
        site.
        """

        database = a_world()

        event_service, _ = services(database)

        event = await event_service.get_event(event_id())

        assert (
            by_name(event.lineup)["Victo"].artist_slug == "victo"
        )

    @pytest.mark.asyncio
    async def test_an_artist_gigcrowd_has_never_heard_of_is_left_alone(self):
        """No page, no link - and still a name, not a broken one."""

        database = a_world()

        database.artists.documents = [
            artist
            for artist in database.artists.documents
            if artist["slug"] != "tim-bernardes"
        ]

        event_service, _ = services(database)

        event = await event_service.get_event(event_id())

        entry = by_name(event.lineup)["Tim Bernardes"]

        assert entry.artist_slug is None
        assert entry.name == "Tim Bernardes"

    @pytest.mark.asyncio
    async def test_an_event_with_no_lineup_gets_an_empty_one(self):
        """A solo concert has no bill, and saying so is not an error."""

        database = a_world()

        document = database.events.documents[0]
        document.pop("lineup", None)

        event_service, _ = services(database)

        event = await event_service.get_event(event_id())

        assert list(event.lineup) == []


class TestTheTwoPagesAgree:
    @pytest.mark.asyncio
    async def test_the_same_entry_is_pressable_on_both(self):
        """The check that would have caught this in the first place.

        Two routes, one bill. Comparing them is the whole point - each route on
        its own looks correct, which is why the asymmetry survived.
        """

        database = a_world()

        event_service, festival_service = services(database)

        event = await event_service.get_event(event_id())
        festival = await festival_service.get_festival(event_id())

        def links(entries):
            return {
                entry.name: entry.artist_slug
                for entry in (entries or [])
            }

        assert links(event.lineup) == links(festival.lineup), (
            links(event.lineup),
            links(festival.lineup),
        )

    @pytest.mark.asyncio
    async def test_both_render_every_announced_performer(self):
        database = a_world()

        event_service, festival_service = services(database)

        event = await event_service.get_event(event_id())
        festival = await festival_service.get_festival(event_id())

        assert len(event.lineup) == len(LINEUP)
        assert len(festival.lineup) == len(LINEUP)

    @pytest.mark.asyncio
    async def test_and_neither_says_anything_is_missing(self):
        """The copy this work removed.

        A reader looking at a poster wants to press a name. Being told the
        artist is "not on GigCrowd yet" is both useless and, once the artist does
        exist, false.
        """

        database = a_world()

        event_service, festival_service = services(database)

        event = await event_service.get_event(event_id())
        festival = await festival_service.get_festival(event_id())

        for payload in (event, festival):

            rendered = str(payload).casefold()

            for phrase in (
                "not on gigcrowd",
                "isn't on gigcrowd",
                "not imported",
                "not yet",
            ):
                assert phrase not in rendered, phrase
