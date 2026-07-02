from app.database.connection import get_database
from app.models.event import EventCreate, EventInDB, EventUpdate, EventStatus
from datetime import datetime, UTC
from typing import Optional, List


class EventService:
    @staticmethod
    async def create_event(event_data: EventCreate) -> EventInDB:
        """Create a new event"""
        db = get_database()
        
        event_dict = event_data.model_dump()
        event_dict["status"] = EventStatus.UPCOMING
        event_dict["attendees_count"] = 0
        event_dict["going_count"] = 0
        event_dict["maybe_count"] = 0
        event_dict["went_count"] = 0
        event_dict["created_at"] = datetime.now(UTC)
        event_dict["updated_at"] = datetime.now(UTC)
        
        result = await db.events.insert_one(event_dict)
        event_dict["_id"] = str(result.inserted_id)
        
        # Update artist events count
        await db.artists.update_one(
            {"_id": event_data.artist_id},
            {"$inc": {"events_count": 1}}
        )
        
        return EventInDB(**event_dict)
    
    @staticmethod
    async def get_event_by_id(event_id: str) -> Optional[EventInDB]:
        """Get an event by ID"""
        db = get_database()
        event = await db.events.find_one({"_id": event_id})
        if event:
            return EventInDB(**event)
        return None
    
    @staticmethod
    async def get_events(
        skip: int = 0,
        limit: int = 50,
        artist_id: Optional[str] = None,
        location: Optional[str] = None,
        status: Optional[EventStatus] = None
    ) -> List[EventInDB]:
        """Get events with optional filters"""
        db = get_database()
        
        query = {}
        if artist_id:
            query["artist_id"] = artist_id
        if location:
            query["location"] = {"$regex": location, "$options": "i"}
        if status:
            query["status"] = status
        
        cursor = db.events.find(query).sort("date", 1).skip(skip).limit(limit)
        events = await cursor.to_list(length=limit)
        
        return [EventInDB(**event) for event in events]
    
    @staticmethod
    async def update_event(event_id: str, event_data: EventUpdate) -> Optional[EventInDB]:
        """Update an event"""
        db = get_database()
        
        update_dict = event_data.model_dump(exclude_unset=True)
        if not update_dict:
            return await EventService.get_event_by_id(event_id)
        
        update_dict["updated_at"] = datetime.now(UTC)
        
        await db.events.update_one(
            {"_id": event_id},
            {"$set": update_dict}
        )
        
        return await EventService.get_event_by_id(event_id)
    
    @staticmethod
    async def update_event_status(event_id: str, status: EventStatus) -> None:
        """Update event status"""
        db = get_database()
        await db.events.update_one(
            {"_id": event_id},
            {"$set": {"status": status, "updated_at": datetime.now(UTC)}}
        )
    
    @staticmethod
    async def increment_attendees_count(event_id: str) -> None:
        """Increment the attendees count for an event"""
        db = get_database()
        await db.events.update_one(
            {"_id": event_id},
            {"$inc": {"attendees_count": 1}}
        )
    
    @staticmethod
    async def update_attendance_counts(event_id: str, status: str, increment: bool = True) -> None:
        """Update attendance counts based on status"""
        db = get_database()
        field = f"{status}_count"
        operation = "$inc" if increment else "$dec"
        value = 1 if increment else -1
        
        await db.events.update_one(
            {"_id": event_id},
            {operation: {field: value}}
        )
