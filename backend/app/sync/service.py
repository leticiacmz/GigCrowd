"""
Synchronization Service

This module implements the SynchronizationService which orchestrates the
synchronization of data from external APIs (Bandsintown) into MongoDB.

Why it exists:
- Orchestrates data synchronization from external APIs to MongoDB
- Centralizes sync logic in one place
- Manages sync metadata (last_synced_at, sync_status)
- Handles deduplication during sync
- Logs sync operations for monitoring
- Provides error handling and retry logic

Responsibility:
- Orchestrate artist synchronization (fetch, normalize, store)
- Orchestrate event synchronization (fetch, normalize, store)
- Orchestrate venue synchronization (fetch, normalize, store)
- Manage sync metadata (last_synced_at, sync_status)
- Handle deduplication (check if entity already exists)
- Log sync operations for monitoring
- Handle sync errors and retry logic

Inputs:
- Artist names (for artist sync)
- Artist IDs (for event sync)
- Venue names and locations (for venue sync)
- Sync status updates

Outputs:
- Synced artist documents
- Synced event documents
- Synced venue documents
- Sync status updates
- Error messages

Dependencies:
- ProviderAdapter (BandsintownAdapter)
- ArtistRepository
- VenueRepository
- EventRepository
- SyncLogRepository (for logging)

Communication:
- Called by routes (on-demand sync) and background jobs (scheduled sync)
- Calls provider adapters to fetch data
- Calls repositories to store data
- Returns synced entities to callers
- Never communicates directly with routes or MongoDB

Why this design is preferable:
- Orchestration: Centralizes sync logic in one place
- Abstraction: Hides sync complexity from business logic
- Testability: Easy to mock providers and repositories
- Maintainability: Sync logic changes isolated to this service
- Reusability: Used by both on-demand and scheduled sync
- Error Handling: Centralized error handling and retry logic
- Logging: Centralized sync operation logging
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, UTC
from app.providers.bandsintown import BandsintownAdapter
from app.repositories.artist_repository import ArtistRepository
from app.repositories.venue_repository import VenueRepository
from app.repositories.event_repository import EventRepository


class SynchronizationService:
    """
    Service for synchronizing data from external providers.
    
    This service orchestrates the synchronization of artists, venues, and
    events from Bandsintown into MongoDB. It handles fetching data from
    the provider, normalizing it, and storing it in the database with
    proper sync metadata.
    
    Design decisions:
    - Provider adapter pattern for flexibility
    - Repository pattern for data access
    - Deduplication by external ID
    - Sync metadata for tracking
    - Error handling with status updates
    - Logging for monitoring and debugging
    
    Sync flow:
    1. Check if entity exists in MongoDB (by external ID)
    2. If exists, update; if not, create
    3. Update sync metadata (last_synced_at, sync_status)
    4. Log sync operation
    5. Return synced entity
    """

    def __init__(
        self,
        artist_repo: ArtistRepository,
        venue_repo: VenueRepository,
        event_repo: EventRepository
    ):
        """
        Initialize the SynchronizationService.
        
        Args:
            artist_repo: ArtistRepository instance
            venue_repo: VenueRepository instance
            event_repo: EventRepository instance
        """
        self.artist_repo = artist_repo
        self.venue_repo = venue_repo
        self.event_repo = event_repo
        self.provider = BandsintownAdapter()

    async def sync_artist(self, artist_name: str) -> Optional[Dict[str, Any]]:
        """
        Synchronize an artist from Bandsintown.
        
        This method fetches an artist from Bandsintown, normalizes the data,
        and stores it in MongoDB. If the artist already exists (by external ID),
        it updates the existing record instead of creating a duplicate.
        
        Args:
            artist_name: Artist name to synchronize
            
        Returns:
            Synced artist document, or None if sync failed
            
        Example:
            >>> service = SynchronizationService(artist_repo, venue_repo, event_repo)
            >>> artist = await service.sync_artist("Metallica")
            >>> print(artist["name"])
            "Metallica"
        """
        try:
            # Fetch artist from Bandsintown
            raw_artist = await self.provider.fetch_artist(artist_name)
            if not raw_artist:
                return None

            # Normalize artist data
            normalized_artist = self.provider.normalize_artist(raw_artist)

            # Check if artist already exists (by external ID)
            existing_artist = await self.artist_repo.find_by_external_id(
                normalized_artist["external_id"]
            )

            if existing_artist:
                # Update existing artist
                await self.artist_repo.update(
                    existing_artist["_id"],
                    normalized_artist
                )
                synced_artist = await self.artist_repo.find_by_id(existing_artist["_id"])
            else:
                # Create new artist
                artist_id = await self.artist_repo.create(normalized_artist)
                synced_artist = await self.artist_repo.find_by_id(artist_id)

            # Update sync metadata
            await self.artist_repo.update_sync_metadata(
                synced_artist["_id"],
                "synced"
            )

            return synced_artist

        except Exception as e:
            # Log error and update sync status
            print(f"Error syncing artist {artist_name}: {e}")
            if synced_artist:
                await self.artist_repo.update_sync_metadata(
                    synced_artist["_id"],
                    "failed",
                    str(e)
                )
            return None

    async def sync_artist_events(
        self,
        artist_id: str
    ) -> List[Dict[str, Any]]:
        """
        Synchronize events for an artist.
        
        This method fetches all events for an artist from Bandsintown,
        normalizes the data, and stores it in MongoDB. It also syncs
        venues referenced by the events.
        
        Args:
            artist_id: Artist ObjectId
            
        Returns:
            List of synced event documents
            
        Example:
            >>> service = SynchronizationService(artist_repo, venue_repo, event_repo)
            >>> events = await service.sync_artist_events("507f1f77bcf86cd799439011")
            >>> print(len(events))
            45
        """
        try:
            # Get artist to fetch external ID
            artist = await self.artist_repo.find_by_id(artist_id)
            if not artist:
                return []

            # Fetch events from Bandsintown
            raw_events = await self.provider.fetch_artist_events(artist["external_id"])
            if not raw_events:
                return []

            synced_events = []

            for raw_event in raw_events:
                try:
                    # Normalize event data
                    normalized_event = self.provider.normalize_event(raw_event)

                    # Sync venue (create or update)
                    venue = await self._sync_venue_from_event(raw_event)

                    if venue:
                        # Add venue reference to event
                        normalized_event["venue_id"] = venue["_id"]

                    # Check if event already exists (by external ID)
                    existing_event = await self.event_repo.find_by_external_id(
                        normalized_event["external_id"]
                    )

                    if existing_event:
                        # Update existing event
                        await self.event_repo.update(
                            existing_event["_id"],
                            normalized_event
                        )
                        synced_event = await self.event_repo.find_by_id(existing_event["_id"])
                    else:
                        # Create new event
                        event_id = await self.event_repo.create(normalized_event)
                        synced_event = await self.event_repo.find_by_id(event_id)

                    # Update sync metadata
                    await self.event_repo.update_sync_metadata(
                        synced_event["_id"],
                        "synced"
                    )

                    synced_events.append(synced_event)

                except Exception as e:
                    print(f"Error syncing event {raw_event.get('id')}: {e}")
                    continue

            # Update artist events count
            await self.artist_repo.update_events_count(artist_id, len(synced_events))

            return synced_events

        except Exception as e:
            print(f"Error syncing events for artist {artist_id}: {e}")
            return []

    async def _sync_venue_from_event(self, raw_event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Sync a venue from event data.
        
        This is a helper method that syncs a venue referenced by an event.
        It extracts venue information from the event and syncs it.
        
        Args:
            raw_event: Raw event data from Bandsintown
            
        Returns:
            Synced venue document, or None if sync failed
        """
        try:
            venue_data = raw_event.get("venue", {})
            if not venue_data:
                return None

            venue_name = venue_data.get("name")
            city = venue_data.get("city")
            country = venue_data.get("country")

            if not venue_name or not city or not country:
                return None

            # Check if venue already exists
            existing_venue = await self.venue_repo.find_by_name_and_location(
                venue_name,
                city,
                country
            )

            if existing_venue:
                return existing_venue

            # Create new venue (Bandsintown doesn't have venue endpoint)
            normalized_venue = {
                "name": venue_name,
                "normalized_name": venue_name.lower(),
                "city": city,
                "country": country,
                "address": venue_data.get("address"),
                "latitude": venue_data.get("latitude"),
                "longitude": venue_data.get("longitude"),
                "capacity": None,
                "website": None,
                "image_url": None,
                "description": None,
                "events_count": 0,
                "source": "bandsintown",
                "external_id": None,  # Bandsintown doesn't provide venue ID
                "last_synced_at": datetime.now(UTC),
                "sync_status": "synced",
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC)
            }

            venue_id = await self.venue_repo.create(normalized_venue)
            return await self.venue_repo.find_by_id(venue_id)

        except Exception as e:
            print(f"Error syncing venue from event: {e}")
            return None

    async def get_artists_needing_sync(
        self,
        threshold_hours: int = 6
    ) -> List[Dict[str, Any]]:
        """
        Get artists that need synchronization.
        
        This method retrieves artists that haven't been synced recently,
        have never been synced, or have failed sync attempts. Used by
        background sync jobs to determine which artists to refresh.
        
        Args:
            threshold_hours: Hours since last sync to consider stale
            
        Returns:
            List of artist documents needing sync
            
        Example:
            >>> service = SynchronizationService(artist_repo, venue_repo, event_repo)
            >>> artists = await service.get_artists_needing_sync(threshold_hours=6)
            >>> print(len(artists))
            45
        """
        return await self.artist_repo.find_needing_sync(threshold_hours)
