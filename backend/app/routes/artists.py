"""
Artist Routes

This module implements the artist routes using the new service architecture
with dependency injection.

Why it exists:
- Provides HTTP endpoints for artist operations
- Uses dependency injection for services
- Implements sync-on-demand functionality
- Maintains existing API contracts

Responsibility:
- Handle HTTP requests for artist operations
- Validate request parameters
- Call services for business logic
- Return HTTP responses

Inputs:
- ArtistService (injected via FastAPI Depends)
- Request parameters (query params, path params)

Outputs:
- HTTP responses
- Artist data
- Error responses

Dependencies:
- ArtistService (injected)
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
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from app.services.artist_service import ArtistService
from app.repositories.artist_repository import ArtistRepository
from app.sync.service import SynchronizationService
from app.repositories.venue_repository import VenueRepository
from app.repositories.event_repository import EventRepository


router = APIRouter(prefix="/artists", tags=["artists"])


def get_artist_service() -> ArtistService:
    """
    Dependency function to create ArtistService instance.
    
    This function creates the necessary dependencies and initializes
    the ArtistService. Used by FastAPI's dependency injection.
    
    Returns:
        Configured ArtistService instance
    """
    artist_repo = ArtistRepository()
    venue_repo = VenueRepository()
    event_repo = EventRepository()
    sync_service = SynchronizationService(artist_repo, venue_repo, event_repo)
    return ArtistService(artist_repo, sync_service)


@router.get("")
async def get_artists(
    skip: int = 0,
    limit: int = 50,
    search: Optional[str] = None,
    artist_service: ArtistService = Depends(get_artist_service)
):
    """
    Get artists with optional search.
    
    This endpoint retrieves artists with optional search filtering.
    Uses the ArtistService for business logic.
    
    Args:
        skip: Number of results to skip (pagination)
        limit: Maximum number of results to return
        search: Optional search query for artist names
        artist_service: Injected ArtistService instance
        
    Returns:
        List of artists
    """
    if search:
        artists = await artist_service.search_artists(search, skip, limit)
    else:
        artists = await artist_service.get_artists(skip, limit)
    
    # Convert Pydantic models to dicts
    return [artist.model_dump() for artist in artists]


@router.get("/{artist_id}")
async def get_artist(
    artist_id: str,
    artist_service: ArtistService = Depends(get_artist_service)
):
    """
    Get artist by ID.
    
    This endpoint retrieves a single artist by its ObjectId.
    Uses the ArtistService for business logic.
    
    Args:
        artist_id: Artist ObjectId as string
        artist_service: Injected ArtistService instance
        
    Returns:
        Artist data
        
    Raises:
        HTTPException: If artist not found
    """
    artist = await artist_service.get_artist_by_id(artist_id)
    
    if not artist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artist not found"
        )
    
    return artist.model_dump()


@router.get("/search/{query}")
async def search_artists(
    query: str,
    limit: int = 10,
    artist_service: ArtistService = Depends(get_artist_service)
):
    """
    Search artists by name.
    
    This endpoint performs a fuzzy search on artist names.
    Uses the ArtistService for business logic.
    
    Args:
        query: Search query string
        limit: Maximum number of results to return
        artist_service: Injected ArtistService instance
        
    Returns:
        List of matching artists
    """
    artists = await artist_service.search_artists(query, limit=limit)
    
    return [artist.model_dump() for artist in artists]
