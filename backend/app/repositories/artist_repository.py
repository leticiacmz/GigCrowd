from pymongo import ASCENDING
from datetime import datetime, UTC
from bson import ObjectId
from app.domain.artist import Artist
from app.mappers.artist_document_mapper import (
    ArtistDocumentMapper,
)
from app.repositories.base import BaseRepository
from app.utils.slug import generate_slug
from app.utils.text import normalize_text


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
                f"external_ids.{provider}": external_id,
            }
        )

        if not document:
            return None

        return ArtistDocumentMapper.to_domain(
            document
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

        return await self.insert_one(
            artist.model_dump()
        )

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

    async def update_last_synced(
        self,
        artist_id: str,
    ):

        await self.collection.update_one(
            {
                "_id": ObjectId(artist_id),
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
                "_id": ObjectId(artist_id),
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
                "_id": ObjectId(artist_id),
            },
            {
                "$set": {
                    "sync_status": "empty",
                    "updated_at": datetime.now(UTC),
                }
            },
        )