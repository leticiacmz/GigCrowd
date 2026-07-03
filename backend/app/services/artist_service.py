"""
Artist Service

This module implements the ArtistService which provides business logic for
artist operations, using the repository pattern for data access.

Why it exists:
- Provides business logic for artist operations
- Separates business logic from data access
- Uses ArtistRepository for all data access
- Implements sync-on-demand when artist not found
- Validates business rules

Responsibility:
- Validate business rules for artist operations
- Orchestrate artist creation, updates, and queries
- Handle sync-on-demand when artist not found
- Maintain business logic (validation, orchestration)

Inputs:
- ArtistRepository (injected dependency)
- Business parameters (artist names, data)
- Optional SynchronizationService (for sync-on-demand)

Outputs:
- Business entities (Pydantic models)
- Validation errors
- Sync status

Dependencies:
- ArtistRepository (for data access)
- SynchronizationService (for sync-on-demand)
- Pydantic models (for validation)

Communication:
- Called by routes
- Calls repositories for data access
- Optionally calls sync service for on-demand sync
- Returns business entities to routes

Why this design is preferable:
- Separation of Concerns: Data access isolated to repositories
- Testability: Easy to mock repositories for unit tests
- Maintainability: Data access changes isolated to repositories
- Sync Integration: Seamless sync-on-demand when data not found
- Business Logic Focus: Service focuses on business rules, not data access
"""

from app.repositories.artist_repository import ArtistRepository
from app.models.artist import ArtistCreate, ArtistInDB, ArtistUpdate
from app.sync.service import SynchronizationService
from datetime import datetime, UTC
from typing import Optional, List


class ArtistService:
    """
    Service for artist business logic.
    
    This class provides business logic for artist operations, using the
    repository pattern for data access. It handles validation, orchestration,
    and sync-on-demand logic.
    
    Design decisions:
    - Dependency injection for repositories
    - Sync-on-demand when artist not found
    - Business logic validation
    - Returns Pydantic models for type safety
    """

    def __init__(
        self,
        artist_repo: ArtistRepository,
        sync_service: Optional[SynchronizationService] = None
    ):
        """
        Initialize the ArtistService.
        
        Args:
            artist_repo: ArtistRepository instance for data access
            sync_service: Optional SynchronizationService for sync-on-demand
        """
        self.artist_repo = artist_repo
        self.sync_service = sync_service

    async def create_artist(self, artist_data: ArtistCreate) -> ArtistInDB:
        """
        Create a new artist.
        
        This method validates business rules and creates a new artist.
        It checks if an artist with the same name already exists.
        
        Args:
            artist_data: Artist creation data
            
        Returns:
            Created artist as ArtistInDB model
            
        Raises:
            ValueError: If artist already exists
            
        Example:
            >>> service = ArtistService(artist_repo, sync_service)
            >>> artist = await service.create_artist(ArtistCreate(name="Metallica"))
            >>> print(artist.name)
            "Metallica"
        """
        # Check if artist already exists
        existing_artist = await self.artist_repo.find_by_name(artist_data.name)
        if existing_artist:
            raise ValueError("Artist already exists")
        
        artist_dict = artist_data.model_dump()
        artist_dict["normalized_name"] = artist_data.name.lower()
        artist_dict["followers_count"] = 0
        artist_dict["events_count"] = 0
        artist_dict["source"] = "manual"  # Created manually, not synced
        artist_dict["external_id"] = None
        artist_dict["last_synced_at"] = None
        artist_dict["sync_status"] = "synced"
        artist_dict["created_at"] = datetime.now(UTC)
        artist_dict["updated_at"] = datetime.now(UTC)
        
        artist_id = await self.artist_repo.create(artist_dict)
        artist_dict["_id"] = artist_id
        
        return ArtistInDB(**artist_dict)

    async def get_artist_by_id(self, artist_id: str) -> Optional[ArtistInDB]:
        """
        Get an artist by ID.
        
        This method retrieves an artist by its ObjectId. Returns None if
        the artist is not found.
        
        Args:
            artist_id: Artist ObjectId as string
            
        Returns:
            Artist as ArtistInDB model, or None if not found
            
        Example:
            >>> service = ArtistService(artist_repo, sync_service)
            >>> artist = await service.get_artist_by_id("507f1f77bcf86cd799439011")
            >>> print(artist.name)
            "Metallica"
        """
        artist = await self.artist_repo.find_by_id(artist_id)
        if artist:
            return ArtistInDB(**artist)
        return None

    async def get_artist_by_name(
        self,
        name: str,
        sync_if_not_found: bool = True
    ) -> Optional[ArtistInDB]:
        """
        Get an artist by name with optional sync-on-demand.
        
        This method retrieves an artist by name. If the artist is not found
        and sync_if_not_found is True, it will sync the artist from Bandsintown.
        
        Args:
            name: Artist name
            sync_if_not_found: Whether to sync from Bandsintown if not found
            
        Returns:
            Artist as ArtistInDB model, or None if not found
            
        Example:
            >>> service = ArtistService(artist_repo, sync_service)
            >>> artist = await service.get_artist_by_name("Metallica", sync_if_not_found=True)
            >>> print(artist.name)
            "Metallica"
        """
        artist = await self.artist_repo.find_by_name(name)
        
        if artist:
            return ArtistInDB(**artist)
        
        # Sync-on-demand if artist not found
        if sync_if_not_found and self.sync_service:
            synced_artist = await self.sync_service.sync_artist(name)
            if synced_artist:
                return ArtistInDB(**synced_artist)
        
        return None

    async def get_artists(
        self,
        skip: int = 0,
        limit: int = 50
    ) -> List[ArtistInDB]:
        """
        Get all artists with pagination.
        
        This method retrieves all artists with pagination support.
        
        Args:
            skip: Number of results to skip
            limit: Maximum number of results to return
            
        Returns:
            List of artists as ArtistInDB models
            
        Example:
            >>> service = ArtistService(artist_repo, sync_service)
            >>> artists = await service.get_artists(skip=0, limit=10)
            >>> print(len(artists))
            10
        """
        artists = await self.artist_repo.find_many(
            {},
            skip=skip,
            limit=limit,
            sort=[("name", 1)]
        )
        
        return [ArtistInDB(**artist) for artist in artists]

    async def update_artist(
        self,
        artist_id: str,
        artist_data: ArtistUpdate
    ) -> Optional[ArtistInDB]:
        """
        Update an artist.
        
        This method updates an artist with the provided data. Only updates
        fields that are set in the ArtistUpdate model.
        
        Args:
            artist_id: Artist ObjectId as string
            artist_data: Artist update data
            
        Returns:
            Updated artist as ArtistInDB model, or None if not found
            
        Example:
            >>> service = ArtistService(artist_repo, sync_service)
            >>> artist = await service.update_artist(
            ...     "507f1f77bcf86cd799439011",
            ...     ArtistUpdate(bio="Updated bio")
            ... )
            >>> print(artist.bio)
            "Updated bio"
        """
        update_dict = artist_data.model_dump(exclude_unset=True)
        if not update_dict:
            return await self.get_artist_by_id(artist_id)
        
        # Add normalized_name if name is being updated
        if "name" in update_dict:
            update_dict["normalized_name"] = update_dict["name"].lower()
        
        update_dict["updated_at"] = datetime.now(UTC)
        
        success = await self.artist_repo.update(artist_id, update_dict)
        if success:
            return await self.get_artist_by_id(artist_id)
        
        return None

    async def search_artists(
        self,
        query: str,
        skip: int = 0,
        limit: int = 50
    ) -> List[ArtistInDB]:

        artists = await self.artist_repo.search_by_name(
            query,
            skip,
            limit
        )

        if artists:
            return [
                ArtistInDB(**artist)
                for artist in artists
            ]

        if self.sync_service:
            synced_artist = await self.sync_service.sync_artist(query)

            if synced_artist:
                artists = await self.artist_repo.search_by_name(
                    query,
                    skip,
                    limit
                )

                return [
                    ArtistInDB(**artist)
                    for artist in artists
                ]

        return []