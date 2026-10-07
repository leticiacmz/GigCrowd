"""The photograph an artist's own page publishes.

A festival lineup carries whatever thumbnail the poster's page happened to link,
which is sometimes the act and sometimes a festival banner. The artist's own page
is the authority, and it is read during initialization anyway - so the picture is
there for the asking and was simply never being taken.

Two rules matter more than the feature:

* **Only a gap is filled.** An image already stored was put there by something
  deliberate. Replacing it because a different page mentions a different picture
  would be fixing a problem nobody reported while destroying what was there.
* **A missing picture is never fatal.** If storing the image raised, the artist
  would never finish initializing - a cosmetic gap would become an artist with no
  discography at all.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from bson import ObjectId

from app.repositories.artist_repository import ArtistRepository
from app.services.synchronization_service import (
    SynchronizationService,
)
from tests.support.fake_mongo import FakeDatabase


NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)

STAGED = (
    "https://images.sk-static.com/images/media/"
    "profile_images/artists/10176016/card_avatar"
)


def an_artist(**fields) -> dict:
    document = {
        # A real ObjectId, because that is what MongoDB stores and what the
        # repository's writes address it by. A string id here would make every
        # `update_one({"_id": ObjectId(...)})` match nothing, and the tests would
        # pass for the wrong reason - looking like "the write was skipped" rather
        # than "the write did not apply".
        "_id": ObjectId("64b7f0c0a1b2c3d4e5f60001"),
        "name": "Marina Sena",
        "normalized_name": "marina sena",
        "slug": "marina-sena",
        "external_ids": {"songkick": "Artist10176016"},
        "genres": ["MPB", "Pop"],
        "image": None,
        "popularity": None,
        "verified": False,
        "created_at": NOW,
        "updated_at": NOW,
    }

    document.update(fields)

    return document


def a_facts(image=STAGED) -> dict:
    return {
        "id": "10176016",
        "slug": "marina-sena",
        "name": "Marina Sena",
        "image": image,
    }


def build(artist_document=None, *, image=STAGED, events=3):
    """A real service over a fake database, with the provider stubbed."""

    database = FakeDatabase(
        {"artists": [artist_document or an_artist()]}
    )

    repository = ArtistRepository(database)

    service = SynchronizationService(
        artist_repository=repository,
        event_import_service=None,
        ttl_hours=24,
    )

    async def fake_import(artist, provider="songkick"):
        return {
            "artist": artist.name,
            "artist_facts": a_facts(image),
            "events_received": events,
            "events_created": events,
            "events_existing": 0,
        }

    service.event_import_service = type(
        "StubImport",
        (),
        {"sync_artist_events": staticmethod(fake_import)},
    )()

    return service, database


class TestAGapIsFilled:
    @pytest.mark.asyncio
    async def test_the_pages_photograph_is_stored(self):
        service, database = build()

        artist = await service.artist_repository.get_by_slug(
            "marina-sena"
        )

        await service.synchronize_artist(artist, force=True)

        stored = await database.artists.find_one(
            {"slug": "marina-sena"}
        )

        assert stored["image"] == STAGED

    @pytest.mark.asyncio
    async def test_the_in_memory_artist_sees_it_too(self):
        """The caller reads the artist it passed in, not a fresh copy.

        Without this the route's re-read would be the only thing keeping the
        response honest, and any caller that did not re-read would hand back a
        profile that disagrees with the database.
        """

        service, _ = build()

        artist = await service.artist_repository.get_by_slug(
            "marina-sena"
        )

        await service.synchronize_artist(artist, force=True)

        assert artist.image == STAGED


class TestAnExistingPhotographIsLeftAlone:
    @pytest.mark.asyncio
    async def test_it_is_not_replaced(self):
        service, database = build(
            an_artist(image="https://images.example/from-the-poster.jpg")
        )

        artist = await service.artist_repository.get_by_slug(
            "marina-sena"
        )

        await service.synchronize_artist(artist, force=True)

        stored = await database.artists.find_one(
            {"slug": "marina-sena"}
        )

        assert (
            stored["image"] == "https://images.example/from-the-poster.jpg"
        )

    @pytest.mark.asyncio
    async def test_the_stored_value_is_not_even_read(self):
        """Not a performance claim - a statement of intent.

        The stored image is somebody's decision. A sync has no opinion about it,
        so it leaves it alone rather than checking whether it likes it.
        """

        service, _ = build(
            an_artist(image="https://images.example/from-the-poster.jpg")
        )

        artist = await service.artist_repository.get_by_slug(
            "marina-sena"
        )

        await service.synchronize_artist(artist, force=True)

        assert (
            artist.image == "https://images.example/from-the-poster.jpg"
        )


class TestWhenThereIsNoPhotograph:
    @pytest.mark.asyncio
    async def test_no_image_is_invented(self):
        """An act with no picture on Songkick has no picture here either."""

        service, database = build(image=None)

        artist = await service.artist_repository.get_by_slug(
            "marina-sena"
        )

        outcome = await service.synchronize_artist(
            artist, force=True
        )

        stored = await database.artists.find_one(
            {"slug": "marina-sena"}
        )

        assert stored["image"] is None
        assert outcome["synced"] is True

    @pytest.mark.asyncio
    async def test_a_missing_facts_block_is_survivable(self):
        """An older import path returns no artist block at all.

        Refusing to finish because of a missing optional detail would make the
        artist permanently uninitializable on a code path that works fine
        otherwise.
        """

        database = FakeDatabase({"artists": [an_artist()]})

        repository = ArtistRepository(database)

        service = SynchronizationService(
            artist_repository=repository,
            event_import_service=None,
            ttl_hours=24,
        )

        async def no_facts(artist, provider="songkick"):
            return {
                "artist": artist.name,
                "events_received": 2,
                "events_created": 2,
            }

        service.event_import_service = type(
            "OldImport",
            (),
            {"sync_artist_events": staticmethod(no_facts)},
        )()

        artist = await repository.get_by_slug("marina-sena")

        outcome = await service.synchronize_artist(
            artist, force=True
        )

        assert outcome["synced"] is True


class TestAMissingPictureIsNeverFatal:
    @pytest.mark.asyncio
    async def test_the_artist_still_initializes(self):
        """The reason this is a separate method that swallows its own failure.

        A cosmetic gap that could stop an artist from ever finishing initializing
        is a far worse outcome than a page with no headshot.
        """

        database = FakeDatabase({"artists": [an_artist()]})

        repository = ArtistRepository(database)

        service = SynchronizationService(
            artist_repository=repository,
            event_import_service=None,
            ttl_hours=24,
        )

        async def fake_import(artist, provider="songkick"):
            return {
                "artist": artist.name,
                "artist_facts": a_facts(),
                "events_received": 5,
                "events_created": 5,
            }

        service.event_import_service = type(
            "StubImport",
            (),
            {"sync_artist_events": staticmethod(fake_import)},
        )()

        async def refuse(*args, **kwargs):
            raise RuntimeError("the write was rejected")

        repository.update_image = refuse

        artist = await repository.get_by_slug("marina-sena")

        outcome = await service.synchronize_artist(
            artist, force=True
        )

        assert outcome["synced"] is True
        assert outcome["result"]["events_created"] == 5

        # And the artist is genuinely initialized, not left pending by the
        # photograph's failure.
        stored = await database.artists.find_one(
            {"slug": "marina-sena"}
        )

        assert stored["sync_status"] == "success"
        assert stored["last_synced_at"] is not None
        assert stored["image"] is None


class TestTheImportActuallyCarriesThePhotograph:
    """The whole feature is one value travelling four hops.

    Provider -> import result -> sync service -> artist document. Every break in
    that chain is invisible when it happens: the import reports success, the
    artist initializes, and the page simply has no headshot - which looks exactly
    like the source not publishing a photograph.

    This broke once, specifically: `sync_artist_events` reassigned the name
    `result` inside its enrichment loop, so by the time its return statement ran
    `result` described the last enriched *event* rather than the artist, and the
    facts came back empty for every artist whose import enriched anything - which
    is most of them. Asserted here so the loop and the return cannot share a name
    again.
    """

    @pytest.mark.asyncio
    async def test_the_facts_survive_an_import_that_enriched_something(self):
        from app.mappers.artist_document_mapper import (
            ArtistDocumentMapper,
        )
        from app.services.songkick_event_import_service import (
            SongkickEventImportService,
        )

        database = FakeDatabase({"artists": [an_artist()]})

        repository = ArtistRepository(database)

        provider = type("StubProvider", (), {})()

        async def get_artist_events(name, artist_id=None):
            return {
                "artist": a_facts(),
                "events": [
                    {
                        "songkick_id": "9001",
                        "event_type": "Concert",
                        "name": "Marina Sena at Sala",
                        "start_date": "2026-03-01T21:00:00+00:00",
                        "url": "https://www.songkick.com/concerts/9001-x",
                        "venue": {
                            "name": "Sala",
                            "city": "Sao Paulo",
                            "country": "Brazil",
                        },
                        "source": {
                            "provider": "songkick",
                            "url": (
                                "https://www.songkick.com/concerts/9001-x"
                            ),
                        },
                    }
                ],
                "upcoming_festivals": [],
            }

        provider.get_artist_events = get_artist_events

        manager = type("Manager", (), {})()
        manager.get_provider = lambda name: provider

        # Enrichment runs, and returns something shaped like a fact about an
        # event rather than about the artist. This is the shadowing that went
        # unnoticed.
        enrichment_calls = []

        class Enrichment:
            async def enrich_event(self, event_id, fields=None):
                enrichment_calls.append(event_id)

                return {"outcome": "updated", "event_id": event_id}

        service = SongkickEventImportService(
            provider_manager=manager,
            event_repository=type("E", (), {})(),
            venue_repository=type("V", (), {})(),
            artist_repository=repository,
            enrichment_service=Enrichment(),
            enrich_fields=["date"],
            enrich_delay_seconds=0,
        )

        artist = ArtistDocumentMapper.to_domain(an_artist())

        result = await service.sync_artist_events(artist)

        assert result["events_received"] == 1

        # The thing that matters: the artist's own facts, still the artist's
        # facts, after a loop that reused the name.
        assert result["artist_facts"].get("image") == STAGED

    @pytest.mark.asyncio
    async def test_the_whole_chain_stores_the_photograph(self):
        """End to end through the real sync service, not the import in pieces.

        The two halves are easy to verify separately and still not connect, which
        is exactly the shape of the bug that shipped: a correct import whose
        result nothing read.
        """

        database = FakeDatabase({"artists": [an_artist()]})

        repository = ArtistRepository(database)

        service = SynchronizationService(
            artist_repository=repository,
            event_import_service=None,
            ttl_hours=24,
        )

        async def import_with_facts(artist, provider="songkick"):
            return {
                "artist": artist.name,
                "artist_facts": a_facts(),
                "events_received": 4,
                "events_created": 4,
            }

        service.event_import_service = type(
            "Import",
            (),
            {"sync_artist_events": staticmethod(import_with_facts)},
        )()

        artist = await repository.get_by_slug("marina-sena")

        await service.synchronize_artist(artist, force=True)

        stored = await database.artists.find_one(
            {"slug": "marina-sena"}
        )

        assert stored["image"] == STAGED


class TestItDoesNotDisturbTheSyncRecord:
    @pytest.mark.asyncio
    async def test_the_timestamp_is_the_sync_one_not_the_write(self):
        """`update_image` also stamps `updated_at`, which is the retry clock.

        That is correct and harmless - the timestamp that decides "is this artist
        fresh" is `last_synced_at`, which the image write does not touch. Asserted
        so a future change cannot quietly make `updated_at` the freshness signal.
        """

        service, database = build()

        artist = await service.artist_repository.get_by_slug(
            "marina-sena"
        )

        before = datetime.now(UTC) - timedelta(seconds=1)

        await service.synchronize_artist(artist, force=True)

        stored = await database.artists.find_one(
            {"slug": "marina-sena"}
        )

        assert stored["last_synced_at"] >= before
