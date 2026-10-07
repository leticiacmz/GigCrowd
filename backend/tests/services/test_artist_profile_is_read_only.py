"""Opening an artist page must not change anything.

`GET /artists/{slug}` used to call `synchronize_artist`, which scraped Songkick,
inserted events and wrote `last_synced_at`. A read that writes is the kind of bug
that survives a long time precisely because it usually looks like it works: the
page renders, the numbers look right, and the only symptom is a catalogue that
grows when people browse and a burst of outbound traffic nobody scheduled.

These tests pin the read path down against the real repositories and a fake
database, so they exercise the actual query that would perform the write rather
than a mock that could be asserted about in isolation.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.artist import Artist
from app.mappers.artist_document_mapper import (
    ArtistDocumentMapper,
)
from app.repositories.artist_follow_repository import (
    ArtistFollowRepository,
)
from app.repositories.artist_repository import ArtistRepository
from app.repositories.event_repository import EventRepository
from app.services.artist_service import ArtistService
from tests.support.fake_mongo import FakeDatabase

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


def artist_document(
    slug: str,
    *,
    songkick_id: str | None = None,
    last_synced_at: datetime | None = None,
) -> dict:
    document: dict = {
        "_id": f"{hash(slug) & 0xFFFFFF:06x}0000000000000000000000",
        "name": slug.replace("-", " ").title(),
        "normalized_name": slug.replace("-", " "),
        "slug": slug,
        "external_ids": {},
        "genres": [],
        "image": None,
        "popularity": None,
        "verified": False,
        "created_at": NOW - timedelta(days=400),
        "updated_at": NOW - timedelta(days=400),
    }

    if songkick_id:
        document["external_ids"] = {"songkick": songkick_id}

    if last_synced_at is not None:
        document["last_synced_at"] = last_synced_at

    return document


def event_document(
    slug: str,
    songkick_id: str,
    *,
    starts_at: datetime,
    created_at: datetime | None = None,
) -> dict:
    document = {
        "title": f"{slug} show",
        "event_type": "Concert",
        "venue_slug": "a-venue",
        "artist_slug": slug,
        "artist_slugs": [slug],
        "starts_at": starts_at,
        "ends_at": None,
        "external_ids": {"songkick": songkick_id},
        "source": {
            "provider": "songkick",
            "url": f"https://www.songkick.com/concerts/{songkick_id}",
        },
        "date_status": "source",
    }

    if created_at is not None:
        document["created_at"] = created_at

    return document


@pytest.fixture
def world():
    """A database with one never-synced artist and no events at all.

    Never synced is the state that used to trigger an import: `_needs_sync`
    returns True for a missing `last_synced_at`, so this is the exact shape that
    grew the catalogue by a thousand rows when somebody opened a page.
    """

    database = FakeDatabase(
        {
            "artists": [
                artist_document(
                    "never-synced",
                    songkick_id="Artist123",
                )
            ],
            "events": [],
            "artist_follows": [],
        }
    )

    service = ArtistService(
        artist_repository=ArtistRepository(database),
        event_repository=EventRepository(database),
        artist_follow_repository=ArtistFollowRepository(
            database
        ),
    )

    return service, database


class TestReadingAnArtistChangesNothing:
    @pytest.mark.asyncio
    async def test_the_event_count_is_identical_afterwards(
        self, world
    ):
        service, database = world

        before = await database.events.count_documents({})

        await service.get_artist_profile("never-synced")

        assert await database.events.count_documents({}) == before

    @pytest.mark.asyncio
    async def test_last_synced_at_is_not_written(self, world):
        service, database = world

        await service.get_artist_profile("never-synced")

        stored = await database.artists.find_one(
            {"slug": "never-synced"}
        )

        # Still absent. Setting it is how the old path recorded that a page visit
        # had scraped a gigography, and it is what silently marked the artist
        # "fresh" for the next 24 hours.
        assert "last_synced_at" not in stored

    @pytest.mark.asyncio
    async def test_sync_status_is_not_written(self, world):
        service, database = world

        await service.get_artist_profile("never-synced")

        stored = await database.artists.find_one(
            {"slug": "never-synced"}
        )

        assert "sync_status" not in stored

    @pytest.mark.asyncio
    async def test_updated_at_is_not_touched(self, world):
        service, database = world

        stored_before = await database.artists.find_one(
            {"slug": "never-synced"}
        )

        await service.get_artist_profile("never-synced")

        stored_after = await database.artists.find_one(
            {"slug": "never-synced"}
        )

        assert stored_after["updated_at"] == stored_before["updated_at"]

    @pytest.mark.asyncio
    async def test_repeated_reads_stay_read_only(self, world):
        # One read could be accidental. Ten reads is a habit, and a habit is what
        # a browser suite does to a developer.
        service, database = world

        for _ in range(10):

            await service.get_artist_profile("never-synced")

        assert await database.events.count_documents({}) == 0

        stored = await database.artists.find_one(
            {"slug": "never-synced"}
        )

        assert "last_synced_at" not in stored

    @pytest.mark.asyncio
    async def test_nothing_is_written_to_any_collection(self, world):
        service, database = world

        before = {
            name: await database[name].count_documents({})
            for name in ("artists", "events", "artist_follows")
        }

        await service.get_artist_profile("never-synced")

        after = {
            name: await database[name].count_documents({})
            for name in ("artists", "events", "artist_follows")
        }

        assert after == before

    @pytest.mark.asyncio
    async def test_the_profile_is_still_returned(self, world):
        # A read-only path is only correct if it still reads.
        service, _ = world

        profile = await service.get_artist_profile(
            "never-synced"
        )

        assert profile.slug == "never-synced"
        assert profile.external_ids["songkick"] == "Artist123"

    @pytest.mark.asyncio
    async def test_a_missing_artist_is_still_a_404(self, world):
        from fastapi import HTTPException

        service, _ = world

        with pytest.raises(HTTPException) as caught:

            await service.get_artist_profile("nobody")

        assert caught.value.status_code == 404


class TestTheServiceCannotSynchronizeEvenByAccident:
    def test_it_holds_no_synchronization_service(self):
        """The dependency is gone, not merely unused.

        Leaving the constructor argument in place would have made the read path
        look unchanged while making it one line away from writing again. Removing
        it means the next person to add a side effect has to add the dependency
        back on purpose, in a diff that says so.
        """

        import inspect

        parameters = inspect.signature(
            ArtistService.__init__
        ).parameters

        assert "synchronization_service" not in parameters

    def test_the_route_builds_it_without_one(self):
        """The wiring cannot smuggle the dependency back in."""

        import inspect

        from app.routes import artists

        source = inspect.getsource(artists)

        assert "synchronization_service=synchronization_service" not in source


class TestExistingEventsAreUntouchedByARead:
    @pytest.mark.asyncio
    async def test_a_real_event_keeps_its_created_at(self):
        # The read path never wrote created_at, so this is a guard on the
        # repository rather than on the reader: an event with a created_at must
        # still have exactly that value after being read.
        stamped = NOW - timedelta(days=30)

        database = FakeDatabase(
            {
                "artists": [
                    artist_document(
                        "marina-sena",
                        songkick_id="Artist1",
                        last_synced_at=NOW,
                    )
                ],
                "events": [
                    event_document(
                        "marina-sena",
                        "40352877",
                        starts_at=NOW - timedelta(days=30),
                        created_at=stamped,
                    )
                ],
                "artist_follows": [],
            }
        )

        service = ArtistService(
            artist_repository=ArtistRepository(database),
            event_repository=EventRepository(database),
            artist_follow_repository=ArtistFollowRepository(
                database
            ),
        )

        before = await database.events.find_one({})

        await service.get_artist_profile("marina-sena")

        after = await database.events.find_one({})

        assert after["created_at"] == stamped
        assert after == before


class TestTheArtistDomainStillCarriesSyncMetadata:
    def test_last_synced_at_still_exists_on_the_model(self):
        """Removing the read does not remove the metadata the job needs.

        This is the regression that would follow from "just delete the sync": the
        field the scheduler selects on has to survive, or the job has nothing to
        order by.
        """

        assert "last_synced_at" in Artist.model_fields


class TestCreatingALineupArtistDoesNotStartASync:
    """A new requirement reopens the risk this file exists to keep closed.

    Announced performers now become artists, so there is a new write on a path
    that did not have one. The rule that keeps it safe is that creating an artist
    is not importing one: a stub gets a name, an id and a slug, and nothing marks
    it as synced. If that boundary blurred, a festival page would start costing a
    gigography fetch per name on the bill.
    """

    @pytest.mark.asyncio
    async def test_a_created_artist_carries_no_sync_marker(self):
        from app.services.lineup_artist_importer import (
            LineupArtistImporter,
        )

        database = FakeDatabase({"artists": []})

        importer = LineupArtistImporter(
            ArtistRepository(database),
            validate=False,
        )

        await importer.ensure_for_entries(
            [
                {
                    "name": "Tim Bernardes",
                    "songkick_id": "2668421",
                }
            ]
        )

        stored = await database.artists.find_one({})

        assert stored is not None

        # Absent, not zero and not false. `last_synced_at` is what the sync job
        # selects on, so writing anything there would claim this artist had been
        # fetched when it had not.
        assert "last_synced_at" not in stored
        assert "sync_status" not in stored

        # And therefore the artist is still eligible for a sync, which is the
        # artist's own business and not this module's.
        from app.services.synchronization_service import (
            SynchronizationService,
        )

        service = SynchronizationService(
            artist_repository=ArtistRepository(database),
            event_import_service=None,
        )

        assert service.needs_sync(
            ArtistDocumentMapper.to_domain(stored)
        )

    @pytest.mark.asyncio
    async def test_creating_a_lineup_artist_writes_no_events(self):
        from app.services.lineup_artist_importer import (
            LineupArtistImporter,
        )

        database = FakeDatabase({"artists": []})

        importer = LineupArtistImporter(
            ArtistRepository(database),
            validate=False,
        )

        await importer.ensure_for_entries(
            [
                {
                    "name": f"Act {index}",
                    "songkick_id": str(1000 + index),
                }
                for index in range(25)
            ]
        )

        assert await database.artists.count_documents({}) == 25
        assert await database.events.count_documents({}) == 0

    @pytest.mark.asyncio
    async def test_reading_a_artist_page_still_writes_nothing_with_a_lineup_importer_in_the_process(self):
        """The guarantee is about the page, not about who else is running.

        Stated as a test rather than as a comment because the lineup importer is
        the first new write capability this service shares a process with, and
        the question it invites is exactly this one: could reading a page reach
        it? It cannot, and the test is what says so.
        """

        from app.services.lineup_artist_importer import (
            LineupArtistImporter,
        )

        database = FakeDatabase(
            {
                "artists": [
                    artist_document(
                        "marina-sena",
                        songkick_id="Artist3090429",
                    )
                ],
                "events": [],
                "artist_follows": [],
            }
        )

        artist_repository = ArtistRepository(database)

        # Built, configured and ready. Nothing calls it, which is the point.
        # Validation is off because this test is about whether a *read* can reach
        # an importer at all; whether an importer validates an identity is covered
        # in the importer's own suite.
        LineupArtistImporter(
            artist_repository,
            validate=False,
        )

        service = ArtistService(
            artist_repository=artist_repository,
            event_repository=EventRepository(database),
            artist_follow_repository=ArtistFollowRepository(
                database
            ),
        )

        before = await database.artists.count_documents({})

        await service.get_artist_profile("marina-sena")

        assert await database.artists.count_documents({}) == before