"""
Event Service

This module implements the EventService which provides business logic for
event operations, using the repository pattern for data access.

Why it exists:
- Provides business logic for event operations
- Separates business logic from data access
- Uses EventRepository and VenueRepository for data access
- Implements attendance tracking logic
- Validates business rules

Responsibility:
- Validate business rules for event operations
- Orchestrate event creation, updates, and queries
- Handle attendance tracking (going, maybe, went)
- Maintain business logic (validation, orchestration)

Inputs:
- EventRepository (injected dependency)
- VenueRepository (injected dependency)
- ArtistRepository (injected dependency for events count updates)
- Business parameters (event data, attendance updates)

Outputs:
- Business entities (Pydantic models)
- Validation errors
- Attendance count updates

Dependencies:
- EventRepository (for event data access)
- VenueRepository (for venue data access)
- ArtistRepository (for artist events count updates)
- Pydantic models (for validation)

Communication:
- Called by routes
- Calls repositories for data access
- Returns business entities to routes
- Never communicates directly with MongoDB or providers

Why this design is preferable:
- Separation of Concerns: Data access isolated to repositories
- Testability: Easy to mock repositories for unit tests
- Maintainability: Data access changes isolated to repositories
- Business Logic Focus: Service focuses on business rules, not data access
- Attendance Tracking: Atomic operations for attendance counts
"""

from app.repositories.event_repository import EventRepository
from app.repositories.venue_repository import VenueRepository
from app.repositories.artist_repository import ArtistRepository
from app.models.event import EventCreate, EventInDB, EventUpdate, EventStatus
from datetime import datetime, UTC
from typing import Optional, List


class EventService:
    """
    Service for event business logic.
    
    This class provides business logic for event operations, using the
    repository pattern for data access. It handles validation, orchestration,
    and attendance tracking logic.
    
    Design decisions:
    - Dependency injection for repositories
    - Atomic attendance count operations
    - Business logic validation
    - Returns Pydantic models for type safety
    """

    def __init__(
        self,
        event_repo: EventRepository,
        venue_repo: VenueRepository,
        artist_repo: ArtistRepository
    ):
        """
        Initialize the EventService.
        
        Args:
            event_repo: EventRepository instance for data access
            venue_repo: VenueRepository instance for venue operations
            artist_repo: ArtistRepository instance for artist operations
        """
        self.event_repo = event_repo
        self.venue_repo = venue_repo
        self.artist_repo = artist_repo

    async def create_event(self, event_data: EventCreate) -> EventInDB:
        """
        Create a new event.
        
        This method validates business rules and creates a new event.
        It updates the artist's events count.
        
        Args:
            event_data: Event creation data
            
        Returns:
            Created event as EventInDB model
            
        Example:
            >>> service = EventService(event_repo, venue_repo, artist_repo)
            >>> event = await service.create_event(EventCreate(title="Metallica Tour"))
            >>> print(event.title)
            "Metallica Tour"
        """
        event_dict = event_data.model_dump()
        event_dict["status"] = EventStatus.UPCOMING
        event_dict["going_count"] = 0
        event_dict["maybe_count"] = 0
        event_dict["went_count"] = 0
        event_dict["source"] = "manual"  # Created manually, not synced
        event_dict["external_id"] = None
        event_dict["last_synced_at"] = None
        event_dict["sync_status"] = "synced"
        event_dict["created_at"] = datetime.now(UTC)
        event_dict["updated_at"] = datetime.now(UTC)
        
        event_id = await self.event_repo.create(event_dict)
        event_dict["_id"] = event_id
        
        # Update artist events count
        await self.artist_repo.update_events_count(
            event_data.artist_id,
            1  # Increment by 1
        )
        
        return EventInDB(**event_dict)

    async def get_event_by_id(self, event_id: str) -> Optional[EventInDB]:
        """
        Get an event by ID.
        
        This method retrieves an event by its ObjectId. Returns None if
        the event is not found.
        
        Args:
            event_id: Event ObjectId as string
            
        Returns:
            Event as EventInDB model, or None if not found
            
        Example:
            >>> service = EventService(event_repo, venue_repo, artist_repo)
            >>> event = await service.get_event_by_id("507f1f77bcf86cd799439013")
            >>> print(event.title)
            "Metallica Tour"
        """
        event = await self.event_repo.find_by_id(event_id)
        if event:
            return EventInDB(**event)
        return None

    async def get_events(
        self,
        skip: int = 0,
        limit: int = 50,
        artist_id: Optional[str] = None,
        status: Optional[EventStatus] = None
    ) -> List[EventInDB]:
        """
        Get events with optional filters.
        
        This method retrieves events with optional filtering by artist
        and status. Supports pagination.
        
        Args:
            skip: Number of results to skip
            limit: Maximum number of results to return
            artist_id: Filter by artist ObjectId
            status: Filter by event status
            
        Returns:
            List of events as EventInDB models
            
        Example:
            >>> service = EventService(event_repo, venue_repo, artist_repo)
            >>> events = await service.get_events(artist_id="507f1f77bcf86cd799439011")
            >>> print(len(events))
            45
        """
        query = {}
        if artist_id:
            query["artist_id"] = artist_id
        if status:
            query["status"] = status
        
        events = await self.event_repo.find_many(
            query,
            skip=skip,
            limit=limit,
            sort=[("date", 1)]
        )
        
        return [EventInDB(**event) for event in events]

    async def get_events_by_venue(
        self,
        venue_id: str,
        skip: int = 0,
        limit: int = 50
    ) -> List[EventInDB]:
        """
        Get events for a specific venue.
        
        This method retrieves all events for a given venue.
        
        Args:
            venue_id: Venue ObjectId as string
            skip: Number of results to skip
            limit: Maximum number of results to return
            
        Returns:
            List of events as EventInDB models
            
        Example:
            >>> service = EventService(event_repo, venue_repo, artist_repo)
            >>> events = await service.get_events_by_venue("507f1f77bcf86cd799439012")
            >>> print(len(events))
            128
        """
        events = await self.event_repo.find_by_venue(venue_id, skip, limit)
        
        return [EventInDB(**event) for event in events]

    async def get_upcoming_events(
        self,
        skip: int = 0,
        limit: int = 50
    ) -> List[EventInDB]:
        """
        Get upcoming events.
        
        This method retrieves all events with status "upcoming".
        
        Args:
            skip: Number of results to skip
            limit: Maximum number of results to return
            
        Returns:
            List of upcoming events as EventInDB models
            
        Example:
            >>> service = EventService(event_repo, venue_repo, artist_repo)
            >>> events = await service.get_upcoming_events()
            >>> print(len(events))
            50
        """
        events = await self.event_repo.find_upcoming(skip, limit)
        
        return [EventInDB(**event) for event in events]

    async def update_event(
        self,
        event_id: str,
        event_data: EventUpdate
    ) -> Optional[EventInDB]:
        """
        Update an event.
        
        This method updates an event with the provided data. Only updates
        fields that are set in the EventUpdate model.
        
        Args:
            event_id: Event ObjectId as string
            event_data: Event update data
            
        Returns:
            Updated event as EventInDB model, or None if not found
            
        Example:
            >>> service = EventService(event_repo, venue_repo, artist_repo)
            >>> event = await service.update_event(
            ...     "507f1f77bcf86cd799439013",
            ...     EventUpdate(description="Updated description")
            ... )
            >>> print(event.description)
            "Updated description"
        """
        update_dict = event_data.model_dump(exclude_unset=True)
        if not update_dict:
            return await self.get_event_by_id(event_id)
        
        update_dict["updated_at"] = datetime.now(UTC)
        
        success = await self.event_repo.update(event_id, update_dict)
        if success:
            return await self.get_event_by_id(event_id)
        
        return None

    async def update_event_status(
        self,
        event_id: str,
        status: EventStatus
    ) -> bool:
        """
        Update event status.
        
        This method updates the event status (upcoming, ongoing, past, cancelled).
        
        Args:
            event_id: Event ObjectId as string
            status: New event status
            
        Returns:
            True if update was successful, False otherwise
            
        Example:
            >>> service = EventService(event_repo, venue_repo, artist_repo)
            >>> success = await service.update_event_status(
            ...     "507f1f77bcf86cd799439013",
            ...     EventStatus.PAST
            ... )
            >>> print(success)
            True
        """
        return await self.event_repo.update_status(event_id, status)

    async def increment_going(self, event_id: str) -> bool:
        """
        Increment the going count for an event.
        
        This method atomically increments the going_count field.
        Used when a user marks themselves as "going" to an event.
        
        Args:
            event_id: Event ObjectId as string
            
        Returns:
            True if increment was successful, False otherwise
            
        Example:
            >>> service = EventService(event_repo, venue_repo, artist_repo)
            >>> success = await service.increment_going("507f1f77bcf86cd799439013")
            >>> print(success)
            True
        """
        return await self.event_repo.increment_going(event_id)

    async def decrement_going(self, event_id: str) -> bool:
        """
        Decrement the going count for an event.
        
        This method atomically decrements the going_count field.
        Used when a user unmarks themselves as "going" to an event.
        
        Args:
            event_id: Event ObjectId as string
            
        Returns:
            True if decrement was successful, False otherwise
        """
        return await self.event_repo.decrement_going(event_id)

    async def increment_maybe(self, event_id: str) -> bool:
        """
        Increment the maybe count for an event.
        
        This method atomically increments the maybe_count field.
        Used when a user marks themselves as "maybe" to an event.
        
        Args:
            event_id: Event ObjectId as string
            
        Returns:
            True if increment was successful, False otherwise
        """
        return await self.event_repo.increment_maybe(event_id)

    async def decrement_maybe(self, event_id: str) -> bool:
        """
        Decrement the maybe count for an event.
        
        This method atomically decrements the maybe_count field.
        Used when a user unmarks themselves as "maybe" to an event.
        
        Args:
            event_id: Event ObjectId as string
            
        Returns:
            True if decrement was successful, False otherwise
        """
        return await self.event_repo.decrement_maybe(event_id)

    async def increment_went(self, event_id: str) -> bool:
        """
        Increment the went count for an event.
        
        This method atomically increments the went_count field.
        Used when a user marks themselves as having attended an event.
        
        Args:
            event_id: Event ObjectId as string
            
        Returns:
            True if increment was successful, False otherwise
        """
        return await self.event_repo.increment_went(event_id)
