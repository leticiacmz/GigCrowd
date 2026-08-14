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
from app.core.logger import get_logger

logger = get_logger("artist_repository")


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

    # NEW: Lookup artist by Songkick ID (handles multiple ID formats)
    async def get_by_songkick_id(
        self,
        songkick_id: int | str,
    ) -> Artist | None:
        """
        Lookup artist by Songkick ID.
        Handles multiple formats:
        - 976211 (numeric)
        - "976211" (string numeric)
        - "Artist976211" (prefixed string)
        """
        # Normalize to prefixed format
        if isinstance(songkick_id, int):
            songkick_id = str(songkick_id)
        
        # If already prefixed, use as-is
        if songkick_id.startswith("Artist"):
            prefixed_id = songkick_id
        else:
            prefixed_id = f"Artist{songkick_id}"
        
        document = await self.find_one({
            "external_ids.songkick": prefixed_id
        })
        
        if not document:
            return None
        
        return ArtistDocumentMapper.to_domain(document)

    async def enrich_with_spotify(
        self,
        artist_id: str,
        spotify_enrichment: dict,
    ):
        """
        Enrich an existing artist with Spotify metadata.
        
        This merges Spotify enrichment fields without overwriting
        canonical Songkick identity fields.
        """
        # Get current artist to preserve existing external_ids
        current_artist = await self.find_one({"_id": ObjectId(artist_id)})
        
        if not current_artist:
            logger.warning(f"Artist {artist_id} not found for enrichment")
            return
        
        # Prepare enrichment data
        enrichment_updates = {}
        
        # Merge external_ids (preserve existing)
        existing_external_ids = current_artist.get("external_ids", {})
        spotify_external_ids = spotify_enrichment.get("external_ids", {})
        
        enrichment_updates["external_ids"] = {
            **existing_external_ids,
            **spotify_external_ids
        }
        
        # Add optional enrichment fields only if not already set
        if spotify_enrichment.get("image") and not current_artist.get("image"):
            enrichment_updates["image"] = spotify_enrichment["image"]
        
        if spotify_enrichment.get("genres"):
            enrichment_updates["genres"] = spotify_enrichment["genres"]
        
        if spotify_enrichment.get("followers"):
            enrichment_updates["followers"] = spotify_enrichment["followers"]
        
        if spotify_enrichment.get("popularity"):
            enrichment_updates["popularity"] = spotify_enrichment["popularity"]
        
        if enrichment_updates:
            enrichment_updates["updated_at"] = datetime.now(UTC)
            
            await self.collection.update_one(
                {"_id": ObjectId(artist_id)},
                {"$set": enrichment_updates}
            )
            
            logger.info(f"Enriched artist {artist_id} with Spotify data, preserved external_ids: {enrichment_updates['external_ids']}")