from app.repositories.base import BaseRepository
from app.mappers.event_document_mapper import EventDocumentMapper
from datetime import datetime, UTC
from app.domain.event import Event
from bson import ObjectId


class EventRepository(BaseRepository):

    def __init__(self, db):
        super().__init__(db, "events")

    async def get_by_id(self, event_id: str):
        document = await self.find_one({"_id": ObjectId(event_id)})
        if not document:
            return None
        return EventDocumentMapper.to_domain(document)

    async def get_by_external_id(self, provider: str, external_id: str):
        document = await self.find_one({f"external_ids.{provider}": external_id})
        if not document:
            return None
        return EventDocumentMapper.to_domain(document)

    async def get_by_artist_slug(self, artist_slug: str):
        cursor = (
            self.collection
            .find({
                "artist_slug": artist_slug,
                "starts_at": {"$gte": datetime.now(UTC)},
            })
            .sort("starts_at", 1)
        )
        documents = await cursor.to_list(length=6)
        return [EventDocumentMapper.to_domain(document) for document in documents]
    
    async def insert_event(self, event: Event):
        await self.insert_one(event.model_dump(exclude={"id"}))

    async def count_by_artist_slug(self, artist_slug: str) -> int:
        return await self.collection.count_documents({"artist_slug": artist_slug})

    async def count_upcoming_by_artist_slug(self, artist_slug: str) -> int:
        return await self.collection.count_documents({
            "artist_slug": artist_slug,
            "starts_at": {"$gte": datetime.now(UTC)},
        })
    
    async def update_attendance_counts(self, event_id: str, going_count: int, maybe_count: int, went_count: int):
        await self.collection.update_one(
            {"_id": ObjectId(event_id)},
            {"$set": {"going_count": going_count, "maybe_count": maybe_count, "went_count": went_count}}
        )

    async def get_upcoming_by_artist_slug(self, artist_slug: str, limit: int = 6):
        cursor = (
            self.collection
            .find({
                "artist_slug": artist_slug,
                "starts_at": {"$gte": datetime.now(UTC)},
            })
            .sort("starts_at", 1)
            .limit(limit)
        )
        documents = await cursor.to_list(length=limit)
        return [EventDocumentMapper.to_domain(document) for document in documents]

    async def get_all_by_artist_slug(self, artist_slug: str):
        cursor = (
            self.collection
            .find({"artist_slug": artist_slug})
            .sort("starts_at", -1)
        )
        documents = await cursor.to_list(length=1000)
        return [EventDocumentMapper.to_domain(document) for document in documents]

    async def update_event(self, event: Event):
        await self.collection.update_one(
            {"external_ids.bandsintown": event.external_ids["bandsintown"]},
            {"$set": event.model_dump(exclude={"id"})}
        )

    async def upsert_event(self, event: Event) -> bool:
        existing = await self.get_by_external_id("bandsintown", event.external_ids["bandsintown"])
        if existing:
            await self.update_event(event)
            return False
        await self.insert_event(event)
        return True

    # NEW: Support artist_slugs queries
    async def get_by_artist_slugs(self, artist_slugs: list[str]):
        cursor = (
            self.collection
            .find({
                "artist_slugs": {"$in": artist_slugs},
                "starts_at": {"$gte": datetime.now(UTC)},
            })
            .sort("starts_at", 1)
        )
        documents = await cursor.to_list(length=6)
        return [EventDocumentMapper.to_domain(document) for document in documents]

    # NEW: Provider-specific upsert
    async def upsert_event_by_provider(self, event: Event, provider: str) -> bool:
        provider_external_id = event.external_ids.get(provider)
        if not provider_external_id:
            raise ValueError(f"No {provider} external ID in event")
        
        existing = await self.get_by_external_id(provider, provider_external_id)
        if existing:
            await self.update_event_by_provider(event, provider)
            return False
        await self.insert_event(event)
        return True

    # NEW: Provider-specific update
    async def update_event_by_provider(self, event: Event, provider: str):
        await self.collection.update_one(
            {f"external_ids.{provider}": event.external_ids[provider]},
            {"$set": event.model_dump(exclude={"id"})}
        )