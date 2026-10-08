"""The picture on a search result is the one the catalogue stores.

Search exists to lead a reader to an artist GigCrowd already has (or is about
to import), and recognition is visual: someone who knows the act by its
photograph should see that photograph here. The persisted image therefore
rides along with the imported flag, while the provider's image remains the
answer for rows the catalogue does not hold - a second lookup at search time
to find "the" picture would mean guessing which stored artist a result is,
which is the identity guessing this flow exists to avoid.

Both halves behave alike: Songkick-first discovery and the Spotify extras
that append to it read the same rule, because both can land on a row that is
already in the catalogue.
"""
from __future__ import annotations

import pytest

from app.repositories.artist_repository import ArtistRepository
from app.schemas.artist_search import ArtistSearchItem
from app.services.artist_search_service import ArtistSearchService
from tests.support.fake_mongo import FakeDatabase

STORED_IMAGE = "https://cdn.example/stored.jpg"
PROVIDER_IMAGE = "https://cdn.example/provider.jpg"


class AProviderManager:
    """Stands in for the provider layer: answers, never fetches."""

    def __init__(
        self,
        songkick: list[ArtistSearchItem] | None = None,
        spotify: list[ArtistSearchItem] | None = None,
    ):
        self.answers = {
            "songkick": songkick or [],
            "spotify": spotify or [],
        }

    async def search_artist(
        self,
        query: str,
        provider: str = "songkick",
    ):
        return self.answers.get(provider, [])


def a_stored_artist(
    *,
    image: str | None,
    songkick_id: str = "520117",
    spotify_id: str | None = "spotify-artist-1",
) -> dict:
    external_ids: dict[str, str] = {}

    if songkick_id:
        external_ids["songkick"] = songkick_id

    if spotify_id:
        external_ids["spotify"] = spotify_id

    return {
        "_id": "aaaaaaaaaaaaaaaaaaaaaaa1",
        "name": "Marina Sena",
        "normalized_name": "marina sena",
        "slug": "marina-sena",
        "external_ids": external_ids,
        "image": image,
        "genres": ["MPB"],
    }


def a_service(
    artists: list[dict],
    songkick: list[ArtistSearchItem] | None = None,
    spotify: list[ArtistSearchItem] | None = None,
) -> ArtistSearchService:
    database = FakeDatabase({"artists": artists})

    return ArtistSearchService(
        AProviderManager(songkick=songkick, spotify=spotify),
        ArtistRepository(database),
    )


def a_songkick_result(
    provider_artist_id: str,
    name: str,
    image: str | None = None,
) -> ArtistSearchItem:
    return ArtistSearchItem(
        provider="songkick",
        provider_artist_id=provider_artist_id,
        name=name,
        image=image,
    )


class TestTheStoredImageTravelsWithTheImportedFlag:
    @pytest.mark.asyncio
    async def test_an_imported_artist_is_pictured_with_the_stored_image(self):
        """Songkick offers no photograph; the catalogue has one.

        The whole point of surfacing a picture is recognition, and an imported
        artist's picture is the one that has been on their profile, their
        lineup entry and their community page all along.
        """
        service = a_service(
            [a_stored_artist(image=STORED_IMAGE)],
            songkick=[a_songkick_result("520117", "Marina Sena")],
        )

        results = await service.search_artist("Marina Sena")

        imported = [
            item
            for item in results
            if item.is_imported
        ]

        assert len(imported) == 1
        assert imported[0].image == STORED_IMAGE

    @pytest.mark.asyncio
    async def test_a_row_without_a_stored_image_keeps_the_provider_one(self):
        """Fallback, not erasure: two of the artists are stored without a
        picture, and for them the provider's is still the best answer."""
        service = a_service(
            [a_stored_artist(image=None)],
            songkick=[
                a_songkick_result(
                    "520117",
                    "Marina Sena",
                    image=PROVIDER_IMAGE,
                )
            ],
        )

        results = await service.search_artist("Marina Sena")

        assert results[0].is_imported is True
        assert results[0].image == PROVIDER_IMAGE

    @pytest.mark.asyncio
    async def test_an_unimported_result_is_left_as_the_provider_answered(self):
        """No cross-contamination: a stored image belongs to one identity.

        The row the catalogue holds is matched by trusted id, so a result that
        does not carry that id keeps its own picture even when the query
        resembles the stored artist - recognition must never show a reader
        somebody else's face.
        """
        service = a_service(
            [a_stored_artist(image=STORED_IMAGE)],
            songkick=[
                a_songkick_result(
                    "9999999",
                    "Somebody Else",
                    image=PROVIDER_IMAGE,
                )
            ],
        )

        results = await service.search_artist("Marina Sena")

        assert results[0].is_imported is False
        assert results[0].image == PROVIDER_IMAGE

    @pytest.mark.asyncio
    async def test_the_spotify_half_follows_the_same_rule(self):
        """The extras appended to a page obey the same identity and the same
        picture rule - otherwise the second door to an imported act would
        show a different artist than the first."""
        service = a_service(
            [a_stored_artist(image=STORED_IMAGE)],
            spotify=[
                ArtistSearchItem(
                    provider="spotify",
                    provider_artist_id="spotify-artist-1",
                    name="Marina Sena",
                    image=PROVIDER_IMAGE,
                )
            ],
        )

        results = await service.search_artist("Marina Sena")

        assert len(results) == 1
        assert results[0].is_imported is True
        assert results[0].image == STORED_IMAGE
