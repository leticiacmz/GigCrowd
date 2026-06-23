from fastapi import APIRouter, Depends, HTTPException, status, Query
from app.models.event import EventCreate, EventResponse, EventUpdate, EventStatusLiteral
from app.services.event_service import EventService
from app.models.show_log import ShowLogCreate, AttendanceStatus
from app.services.show_log_service import ShowLogService
from app.auth.dependencies import get_current_active_user
from typing import List, Optional
from datetime import datetime, timedelta, UTC
from app.config import settings
from app.ingestion.sources.setlistfm_source import SetlistFmSource
from app.ingestion.sources.ticketmaster_source import TicketMasterSource
from app.ingestion.sources.bandsintown_source import BandsintownSource
from app.ingestion.sources.spotify_source import SpotifySource
from app.ingestion.normalizers.event_normalizer import EventNormalizer
from app.ingestion.deduplicator.event_deduplicator import EventDeduplicator

router = APIRouter(prefix="/events", tags=["events"])


@router.post("", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
async def create_event(event_data: EventCreate):
    """Create a new event"""
    event = await EventService.create_event(event_data)
    return EventResponse(**event.model_dump())


@router.get("", response_model=List[EventResponse])
async def get_events(
    skip: int = 0,
    limit: int = 50,
    artist_id: str = None,
    location: str = None,
    status: EventStatusLiteral = None
):
    """Get events with optional filters"""
    events = await EventService.get_events(skip, limit, artist_id, location, status)
    return [EventResponse(**event.model_dump()) for event in events]


@router.get("/{event_id}", response_model=EventResponse)
async def get_event(event_id: str):
    """Get event by ID"""
    event = await EventService.get_event_by_id(event_id)
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )
    return EventResponse(**event.model_dump())


@router.put("/{event_id}", response_model=EventResponse)
async def update_event(event_id: str, event_data: EventUpdate):
    """Update event"""
    event = await EventService.update_event(event_id, event_data)
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )
    return EventResponse(**event.model_dump())


@router.post("/{event_id}/attend")
async def attend_event(
    event_id: str,
    status: AttendanceStatus,
    notes: str = None,
    current_user: dict = Depends(get_current_active_user)
):
    """Mark attendance for an event (going, maybe, went). Imports cached events to permanent storage."""
    from app.database.connection import get_database
    db = get_database()
    
    # Check if event is cached and import if needed
    cached_event = await db.cache.find_one({"events._id": event_id})
    if cached_event:
        # Import to permanent storage
        event_data = None
        for event in cached_event["events"]:
            if event.get("_id") == event_id:
                event_data = event
                break
        
        if event_data:
            event_data.pop("is_cached", None)
            event_data.pop("cached_at", None)
            
            existing = await db.events.find_one({"_id": event_id})
            if not existing:
                await db.events.insert_one(event_data)
                
                # Update user stats if this is the first time seeing this artist
                artist_id = event_data.get("artist_id")
                if artist_id:
                    await db.users.update_one(
                        {"_id": current_user["_id"]},
                        {"$addToSet": {"artists_seen": artist_id}}
                    )
    
    show_log_data = ShowLogCreate(event_id=event_id, status=status, notes=notes)
    
    try:
        show_log = await ShowLogService.create_show_log(current_user["_id"], show_log_data)
        
        # Update user stats
        if status == "went":
            await db.users.update_one(
                {"_id": current_user["_id"]},
                {"$inc": {"shows_attended": 1}}
            )
        
        # Create activity
        from app.services.activity_service import ActivityService
        from app.models.activity import ActivityCreate, ActivityType
        await ActivityService.create_activity(
            user_id=current_user["_id"],
            activity_data=ActivityCreate(
                activity_type=ActivityType.ATTEND_EVENT,
                target_id=event_id,
                target_type="event",
                metadata={"status": status}
            )
        )
        
        return {"message": "Attendance marked successfully", "show_log": show_log}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/{event_id}/attendees")
async def get_event_attendees(event_id: str, skip: int = 0, limit: int = 50):
    """Get attendees for an event"""
    show_logs = await ShowLogService.get_event_show_logs(event_id, skip, limit)
    return show_logs


@router.get("/search/external")
async def search_external_events(
    query: str = Query(..., description="Search query (artist name, venue, or city)"),
    skip: int = 0,
    limit: int = 20
):
    """
    Search events from external API (Setlist.fm) with intelligent caching.
    
    Strategy:
    1. Check cache in MongoDB first (if searched within 7 days)
    2. If not cached, fetch from Setlist.fm API
    3. Normalize and deduplicate
    4. Store in MongoDB with TTL (7 days)
    5. If user interacts with event, it becomes permanent
    """
    if not settings.SETLISTFM_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Setlist.fm API key not configured"
        )
    
    # Check cache first
    from app.database.connection import get_database
    db = get_database()
    
    cache_key = f"search:{query.lower()}"
    cached_result = await db.cache.find_one({"_id": cache_key})
    
    if cached_result:
        # Check if cache is still valid
        cache_age = datetime.now(UTC) - cached_result["created_at"]
        if cache_age < timedelta(seconds=settings.CACHE_TTL_SECONDS):
            return {
                "source": "cache",
                "events": cached_result["events"],
                "cached_at": cached_result["created_at"]
            }
    
    # Fetch from external API with fallback strategy
    try:
        # Strategy:
        # - Past events: Setlist.fm (historical data)
        # - Upcoming events (TicketMaster sales): TicketMaster API
        # - Upcoming events (general): Bandsintown scraper
        
        raw_events = []
        source = "unknown"
        
        # Try Setlist.fm first (good for both past and upcoming)
        if settings.SETLIST_FM_API_KEY:
            setlistfm = SetlistFmSource(api_key=settings.SETLIST_FM_API_KEY)
            raw_events = await setlistfm.search_events(query)
            source = "setlistfm"
        
        # If Setlist.fm returns no results, try TicketMaster (upcoming events with sales)
        if not raw_events and settings.TICKETMASTER_CONSUMER_KEY:
            ticketmaster = TicketMasterSource(
                api_key=settings.TICKETMASTER_CONSUMER_KEY,
                api_secret=settings.TICKETMASTER_CONSUMER_SECRET
            )
            raw_events = await ticketmaster.search_events(query)
            source = "ticketmaster"
        
        # If TicketMaster also returns no results, try Bandsintown scraper (upcoming events general)
        if not raw_events:
            bandsintown = BandsintownSource()
            raw_events = await bandsintown.search_events(query)
            source = "bandsintown"
        
        if not raw_events:
            return {"source": "external", "events": []}
        
        # Normalize events based on source
        normalizer = EventNormalizer()
        normalized_events = []
        for event in raw_events:
            normalized = normalizer.normalize(event, source=source)
            normalized_events.append(normalized)
        
        # Deduplicate against existing events
        deduplicator = EventDeduplicator(db)
        final_events = []
        
        for event in normalized_events:
            # Check if event already exists in permanent storage
            existing = await deduplicator.find_duplicate(event)
            if existing:
                final_events.append(existing)
            else:
                # Add to cache with temporary flag
                event["is_cached"] = True
                event["cached_at"] = datetime.now(UTC)
                final_events.append(event)
        
        # Store in cache collection with TTL
        await db.cache.update_one(
            {"_id": cache_key},
            {
                "$set": {
                    "events": final_events,
                    "created_at": datetime.now(UTC),
                    "query": query
                }
            },
            upsert=True
        )
        
        # Create TTL index on cache collection
        await db.cache.create_index("created_at", expireAfterSeconds=settings.CACHE_TTL_SECONDS)
        
        return {
            "source": "external",
            "events": final_events,
            "cached": False
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching events from external API: {str(e)}"
        )


@router.post("/import/{event_id}")
async def import_event(
    event_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Import a cached event to permanent storage.
    Called when user marks attendance or interacts with event.
    """
    from app.database.connection import get_database
    db = get_database()
    
    # Find event in cache
    cached_event = await db.cache.find_one({"events._id": event_id})
    if not cached_event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found in cache"
        )
    
    # Find the specific event
    event_data = None
    for event in cached_event["events"]:
        if event.get("_id") == event_id:
            event_data = event
            break
    
    if not event_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )
    
    # Remove cache-specific fields
    event_data.pop("is_cached", None)
    event_data.pop("cached_at", None)
    
    # Check if already in permanent storage
    existing = await db.events.find_one({"_id": event_id})
    if existing:
        return {"message": "Event already in permanent storage", "event_id": event_id}
    
    # Import to permanent storage
    await db.events.insert_one(event_data)
    
    return {"message": "Event imported successfully", "event_id": event_id}
