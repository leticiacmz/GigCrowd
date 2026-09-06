from datetime import datetime, UTC

from bson import ObjectId
from pymongo import ASCENDING

from app.core.logger import get_logger

from app.domain.artist import Artist

from app.mappers.artist_document_mapper import (
    ArtistDocumentMapper,
)

from app.repositories.base import BaseRepository

from app.utils.slug import generate_slug
from app.utils.text import normalize_text


logger = get_logger(
    "artist_repository"
)


class ArtistRepository(BaseRepository):

    def __init__(self, db):

        super().__init__(
            db,
            "artists",
        )

    async def get_by_slug(
        self,
        slug: str,
    ) -> Artist | None:

        document = await self.find_one(
            {
                "slug": slug,
            }
        )

        if not document:
            return None

        return ArtistDocumentMapper.to_domain(
            document
        )

    async def get_by_name(
        self,
        name: str,
    ) -> Artist | None:

        normalized = normalize_text(
            name
        )

        document = await self.find_one(
            {
                "normalized_name": normalized,
            }
        )

        if not document:
            return None

        return ArtistDocumentMapper.to_domain(
            document
        )

    async def get_by_external_id(
        self,
        provider: str,
        external_id: str,
    ) -> Artist | None:

        document = await self.find_one(
            {
                f"external_ids.{provider}": str(
                    external_id
                ),
            }
        )

        if not document:
            return None

        return ArtistDocumentMapper.to_domain(
            document
        )

    async def get_by_songkick_id(
        self,
        songkick_id: int | str,
    ) -> Artist | None:

        songkick_id = str(
            songkick_id
        )

        if not songkick_id.startswith(
            "Artist"
        ):

            songkick_id = (
                f"Artist{songkick_id}"
            )

        return await self.get_by_external_id(
            "songkick",
            songkick_id,
        )

    async def generate_unique_slug(
        self,
        name: str,
    ) -> str:

        base_slug = generate_slug(
            name
        )

        slug = base_slug

        counter = 2

        while await self.get_by_slug(
            slug
        ):

            slug = (
                f"{base_slug}-{counter}"
            )

            counter += 1

        return slug

    async def insert_artist(
        self,
        artist: Artist,
    ):

        result = await self.insert_one(
            artist.model_dump()
        )

        artist.id = str(
            result.inserted_id
        )

        return artist

    async def get_all(
        self,
        limit: int = 20,
        skip: int = 0,
    ) -> list[Artist]:

        documents = await self.find_many(
            {},
            sort=[
                (
                    "normalized_name",
                    ASCENDING,
                )
            ],
            skip=skip,
            limit=limit,
        )

        return [
            ArtistDocumentMapper.to_domain(
                document
            )
            for document in documents
        ]

    async def update_external_data(
        self,
        artist_id: str,
        external_ids: dict[str, str],
        image: str | None,
        genres: list[str],
        popularity: int | None,
    ):
        """
        Update external provider data for an existing artist.

        This method is intentionally limited to enrichment data.

        Canonical identity fields such as name, slug and
        Songkick ID are not modified here.

        GigCrowd follower counts are not stored in the
        artists collection.
        """

        update_data = {
            "external_ids": external_ids,
            "image": image,
            "genres": genres,
            "popularity": popularity,
            "updated_at": datetime.now(UTC),
        }

        await self.collection.update_one(
            {
                "_id": ObjectId(
                    artist_id
                ),
            },
            {
                "$set": update_data,
            },
        )

        logger.info(
            f"Updated external data for artist "
            f"{artist_id}"
        )

    async def update_spotify_data(
        self,
        artist_id: str,
        spotify_artist: Artist,
    ):
        """
        Backwards-compatible Spotify enrichment method.

        Followers are intentionally not stored.

        Prefer update_external_data() for new import flows.
        """

        spotify_id = (
            spotify_artist.external_ids.get(
                "spotify"
            )
        )

        update_data = {
            "image": spotify_artist.image,
            "genres": spotify_artist.genres,
            "popularity": spotify_artist.popularity,
            "updated_at": datetime.now(UTC),
        }

        if spotify_id:

            update_data[
                "external_ids.spotify"
            ] = spotify_id

        await self.collection.update_one(
            {
                "_id": ObjectId(
                    artist_id
                ),
            },
            {
                "$set": update_data,
            },
        )

        logger.info(
            f"Updated Spotify data for artist "
            f"{artist_id}"
        )

    async def update_image(
        self,
        artist_id: str,
        image: str,
    ):

        await self.collection.update_one(
            {
                "_id": ObjectId(
                    artist_id
                ),
            },
            {
                "$set": {
                    "image": image,
                    "updated_at": datetime.now(UTC),
                }
            },
        )

        logger.info(
            f"Updated image for artist "
            f"{artist_id}"
        )

    async def update_last_synced(
        self,
        artist_id: str,
    ):

        await self.collection.update_one(
            {
                "_id": ObjectId(
                    artist_id
                ),
            },
            {
                "$set": {
                    "last_synced_at": datetime.now(UTC),
                    "sync_status": "success",
                    "updated_at": datetime.now(UTC),
                }
            },
        )

    async def update_sync_error(
        self,
        artist_id: str,
    ):

        await self.collection.update_one(
            {
                "_id": ObjectId(
                    artist_id
                ),
            },
            {
                "$set": {
                    "sync_status": "error",
                    "updated_at": datetime.now(UTC),
                }
            },
        )

    async def update_sync_empty(
        self,
        artist_id: str,
    ):

        await self.collection.update_one(
            {
                "_id": ObjectId(
                    artist_id
                ),
            },
            {
                "$set": {
                    "sync_status": "empty",
                    "updated_at": datetime.now(UTC),
                }
            },
        )