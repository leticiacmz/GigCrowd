"""
Event Routes

This module implements the event routes using the new service architecture
with dependency injection and synchronization-based data access.

Why it exists:
- Provides HTTP endpoints for event operations
- Uses dependency injection for services
- Implements sync-on-demand functionality
- Removes cache-based logic in favor of synchronization

Responsibility:
- Handle HTTP requests for event operations
- Validate request parameters
- Call services for business logic
- Return HTTP responses

Inputs:
- EventService (injected via FastAPI Depends)
- Request parameters (query params, path params)

Outputs:
- HTTP responses
- Event data
- Error responses

Dependencies:
- EventService (injected)
- FastAPI Depends for dependency injection

Communication:
- Called by HTTP requests
- Calls services for business logic
- Returns HTTP responses to clients

Why this design is preferable:
- Dependency Injection: Services injected via FastAPI Depends
- Testability: Easy to mock services for route tests
- Maintainability: Service changes don't require route changes
- Sync Integration: Routes can trigger sync-on-demand
- Type Safety: FastAPI validates injected dependencies
- No Cache: Direct MongoDB access with sync-on-demand
"""

from fastapi import APIRouter, Depends, HTTPException, status
from app.models.event import EventCreate, EventResponse, EventUpdate, EventStatus
from app.services.event_service import EventService
from app.repositories.event_repository import EventRepository
from app.repositories.venue_repository import VenueRepository
from app.repositories.artist_repository import ArtistRepository
from app.sync.service import SynchronizationService
from app.models.show_log import ShowLogCreate, AttendanceStatus
from app.services.show_log_service import ShowLogService
from app.auth.dependencies import get_current_active_user
from app.database.connection import get_database
from typing import List, Optional
from datetime import datetime, UTC


router = APIRouter(prefix="/events", tags=["events"])


def get_event_service() -> EventService:
    """
    Dependency function to create EventService instance.
    
    This function creates the necessary dependencies and initializes
    the EventService. Used by FastAPI's dependency injection.
    
    Returns:
        Configured EventService instance
    """
    event_repo = EventRepository()
    venue_repo = VenueRepository()
    artist_repo = ArtistRepository()
    return EventService(event_repo, venue_repo, artist_repo)


@router.post("", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
async def create_event(
    event_data: EventCreate,
    event_service: EventService = Depends(get_event_service)
):
    """
    Create a new event.
    
    This endpoint creates a new event with the provided data.
    Uses the EventService for business logic.
    
    Args:
        event_data: Event creation data
        event_service: Injected EventService instance
        
    Returns:
        Created event data
    """
    event = await event_service.create_event(event_data)
    return EventResponse(**event.model_dump())


@router.get("", response_model=List[EventResponse])
async def get_events(
    skip: int = 0,
    limit: int = 50,
    artist_id: Optional[str] = None,
    status: Optional[EventStatus] = None,
    event_service: EventService = Depends(get_event_service)
):
    """
    Get events with optional filters.
    
    This endpoint retrieves events with optional filtering by artist
    and status. Supports pagination.
    
    Args:
        skip: Number of results to skip (pagination)
        limit: Maximum number of results to return
        artist_id: Filter by artist ObjectId
        status: Filter by event status
        event_service: Injected EventService instance
        
    Returns:
        List of events
    """
    events = await event_service.get_events(skip, limit, artist_id, status)
    return [EventResponse(**event.model_dump()) for event in events]


@router.get("/upcoming", response_model=List[EventResponse])
async def get_upcoming_events(
    skip: int = 0,
    limit: int = 50,
    event_service: EventService = Depends(get_event_service)
):
    """
    Get upcoming events.
    
    This endpoint retrieves all events with status "upcoming".
    
    Args:
        skip: Number of results to skip (pagination)
        limit: Maximum number of results to return
        event_service: Injected EventService instance
        
    Returns:
        List of upcoming events
    """
    events = await event_service.get_upcoming_events(skip, limit)
    return [EventResponse(**event.model_dump()) for event in events]


@router.get("/{event_id}", response_model=EventResponse)
async def get_event(
    event_id: str,
    event_service: EventService = Depends(get_event_service)
):
    """
    Get event by ID.
    
    This endpoint retrieves a single event by its ObjectId.
    
    Args:
        event_id: Event ObjectId as string
        event_service: Injected EventService instance
        
    Returns:
        Event data
        
    Raises:
        HTTPException: If event not found
    """
    event = await event_service.get_event_by_id(event_id)
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )
    return EventResponse(**event.model_dump())


@router.put("/{event_id}", response_model=EventResponse)
async def update_event(
    event_id: str,
    event_data: EventUpdate,
    event_service: EventService = Depends(get_event_service)
):
    """
    Update event.
    
    This endpoint updates an event with the provided data.
    
    Args:
        event_id: Event ObjectId as string
        event_data: Event update data
        event_service: Injected EventService instance
        
    Returns:
        Updated event data
        
    Raises:
        HTTPException: If event not found
    """
    event = await event_service.update_event(event_id, event_data)
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
    notes: Optional[str] = None,
    current_user: dict = Depends(get_current_active_user),
    event_service: EventService = Depends(get_event_service)
):
    """
    Mark attendance for an event (going, maybe, went).
    
    This endpoint allows users to mark their attendance status for an event.
    Updates attendance counts and creates a show log entry.
    
    Args:
        event_id: Event ObjectId as string
        status: Attendance status (going, maybe, went)
        notes: Optional notes about the event
        current_user: Current authenticated user
        event_service: Injected EventService instance
        
    Returns:
        Success message with show log data
        
    Raises:
        HTTPException: If event not found or invalid status
    """
    db = get_database()
    
    # Verify event exists
    event = await event_service.get_event_by_id(event_id)
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )
    
    show_log_data = ShowLogCreate(event_id=event_id, status=status, notes=notes)
    
    try:
        show_log = await ShowLogService.create_show_log(current_user["_id"], show_log_data)
        
        # Update attendance counts
        if status == "going":
            await event_service.increment_going(event_id)
        elif status == "maybe":
            await event_service.increment_maybe(event_id)
        elif status == "went":
            await event_service.increment_went(event_id)
            # Update user stats
            await db.users.update_one(
                {"_id": current_user["_id"]},
                {"$inc": {"shows_attended": 1}}
            )
            # Add artist to artists_seen if not already present
            if event.artist_id:
                await db.users.update_one(
                    {"_id": current_user["_id"]},
                    {"$addToSet": {"artists_seen": event.artist_id}}
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
    """
    Get attendees for an event.
    
    This endpoint retrieves all show logs for a specific event.
    
    Args:
        event_id: Event ObjectId as string
        skip: Number of results to skip (pagination)
        limit: Maximum number of results to return
        
    Returns:
        List of show logs (attendees)
    """
    show_logs = await ShowLogService.get_event_show_logs(event_id, skip, limit)
    return show_logs
