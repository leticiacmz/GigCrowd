from fastapi import APIRouter, Depends, HTTPException, status, Query
from app.models.event import EventCreate, EventResponse, EventUpdate, EventStatusLiteral, EventTypeLiteral
from app.services.event_service import EventService
from app.models.show_log import ShowLogCreate, AttendanceStatus
from app.services.show_log_service import ShowLogService
from app.auth.dependencies import get_current_active_user
from app.database.connection import get_database
from typing import List, Optional
from datetime import datetime, timedelta, UTC
from app.config import settings
from app.ingestion.sources.bandsintown_source import BandsintownSource

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
    query: str = Query(..., description="Search query (artist name)"),
    event_type: EventTypeLiteral = Query("future", description="Type of events: 'past' or 'future' (ignored if specific_date is provided)"),
    specific_date: Optional[str] = Query(None, description="Specific date in YYYY-MM-DD format (uses intelligent fallback: exact date → ±1 week range → all events)"),
    start_date: Optional[str] = Query(None, description="Start date for search range (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date for search range (ISO format)"),
    skip: int = Query(0, ge=0, description="Number of results to skip"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of results to return"),
    database = Depends(get_database)
):
    """
    Search events from external APIs with intelligent caching and date filtering.
    
    Strategy:
    1. Check cache in MongoDB first (if searched within 7 days)
    2. If not cached or cache expired, fetch from Bandsintown API:
       - If specific_date provided: Use intelligent fallback (exact date → ±1 week → all events)
       - If no specific_date: Use event_type filter (past/future/all)
    3. Normalize events
    4. Store in MongoDB cache with TTL (7 days)
    5. If user interacts with event, it becomes permanent
    
    Cache Strategy:
    - Cache key includes query and date filter for separate caching
    - Cache is valid for 7 days
    - On cache hit, return cached events
    - On cache miss, fetch from API and update cache
    """
    from app.database.connection import get_database
    db = get_database()
    
    # Parse date parameters if provided
    parsed_start_date = None
    parsed_end_date = None
    if start_date:
        try:
            parsed_start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid start_date format. Use ISO format (e.g., 2024-01-01T00:00:00)"
            )
    if end_date:
        try:
            parsed_end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid end_date format. Use ISO format (e.g., 2024-12-31T23:59:59)"
            )
    
    # Determine cache key and date strategy
    if specific_date:
        # Use specific date with intelligent fallback
        cache_key = f"search:{query.lower()}:specific_date:{specific_date}"
        date_strategy = f"specific_date:{specific_date}"
    else:
        # Use event_type filter
        # Set default date ranges based on event_type
        if event_type == "past":
            if not parsed_start_date:
                parsed_start_date = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=730)  # 2 years ago (naive)
            if not parsed_end_date:
                parsed_end_date = datetime.now(UTC).replace(tzinfo=None)  # naive
        else:  # future
            if not parsed_start_date:
                parsed_start_date = datetime.now(UTC).replace(tzinfo=None)  # naive
            if not parsed_end_date:
                parsed_end_date = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=365)  # 1 year ahead (naive)
        
        # Also remove timezone from parsed dates if they were provided
        if parsed_start_date and parsed_start_date.tzinfo:
            parsed_start_date = parsed_start_date.replace(tzinfo=None)
        if parsed_end_date and parsed_end_date.tzinfo:
            parsed_end_date = parsed_end_date.replace(tzinfo=None)
        
        cache_key = f"search:{query.lower()}:{event_type}:{parsed_start_date.isoformat()}:{parsed_end_date.isoformat()}"
        date_strategy = f"event_type:{event_type}"
    
    cached_result = await database.cache.find_one({"_id": cache_key})
    
    if cached_result:
        # Check if cache is still valid
        cache_age = datetime.now(UTC) - cached_result["created_at"]
        if cache_age < timedelta(seconds=settings.CACHE_TTL_SECONDS):
            return {
                "source": "cache",
                "events": cached_result["events"][skip:skip+limit],
                "total": len(cached_result["events"]),
                "cached_at": cached_result["created_at"],
                "date_strategy": date_strategy
            }
    
    # Fetch from external API using Bandsintown
    try:
        raw_events = []
        source = "bandsintown"
        
        # Use Bandsintown API
        if not settings.BANDSINTOWN_APP_ID:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Bandsintown APP_ID not configured"
            )
        
        bandsintown = BandsintownSource()
        
        # Use intelligent date fallback if specific_date provided, otherwise use event_type
        if specific_date:
            raw_events = await bandsintown.search_events_with_date_fallback(query, specific_date=specific_date)
        else:
            # Determine date filter based on event_type
            if event_type == "past":
                date_filter = "past"
            elif event_type == "future":
                date_filter = "upcoming"
            else:
                date_filter = "all"
            
            raw_events = await bandsintown.search_events(query, date_filter=date_filter)
        
        if not raw_events:
            return {
                "source": "bandsintown",
                "events": [],
                "total": 0,
                "date_strategy": date_strategy
            }
        
        # Events are already normalized by BandsintownSource
        # Add cache metadata
        final_events = []
        for event in raw_events:
            event["is_cached"] = True
            event["cached_at"] = datetime.now(UTC)
            final_events.append(event)
        
        # Store in cache collection with TTL
        cache_data = {
            "events": final_events,
            "created_at": datetime.now(UTC),
            "query": query,
            "date_strategy": date_strategy
        }
        
        if specific_date:
            cache_data["specific_date"] = specific_date
        else:
            cache_data["event_type"] = event_type
            cache_data["start_date"] = parsed_start_date.isoformat()
            cache_data["end_date"] = parsed_end_date.isoformat()
        
        await database.cache.update_one(
            {"_id": cache_key},
            {"$set": cache_data},
            upsert=True
        )
        
        # Create TTL index on cache collection if it doesn't exist
        await database.cache.create_index("created_at", expireAfterSeconds=settings.CACHE_TTL_SECONDS)
        
        return {
            "source": "bandsintown",
            "events": final_events[skip:skip+limit],
            "total": len(final_events),
            "cached": False,
            "date_strategy": date_strategy
        }
        
    except HTTPException:
        raise
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
