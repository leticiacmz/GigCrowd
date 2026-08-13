from app.core.logger import get_logger

from app.mappers.songkick_event_mapper import SongkickEventMapper
from app.mappers.songkick_venue_mapper import SongkickVenueMapper

from app.repositories.event_repository import (
    EventRepository,
)
from app.repositories.venue_repository import (
    VenueRepository,
)
from app.repositories.artist_repository import ArtistRepository

from app.services.provider_manager import (
    ProviderManager,
)
import time

from app.domain.artist import Artist

logger = get_logger("songkick_event_import")


class SongkickEventImportService:

    def __init__(
        self,
        provider_manager: ProviderManager,
        event_repository: EventRepository,
        venue_repository: VenueRepository,
        artist_repository: ArtistRepository,
    ):

        self.provider_manager = provider_manager
        self.event_repository = event_repository
        self.venue_repository = venue_repository
        self.artist_repository = artist_repository

    async def sync_artist_events(
        self,
        artist: Artist,
    ):
        """
        Synchronize events for an artist from Songkick.
        
        This handles:
        - Fetching events from Songkick
        - Resolving Songkick artist IDs to local artist slugs
        - Multi-artist events (festivals)
        - Venue upsert
        - Event upsert with proper deduplication
        """
        started_at = time.perf_counter()

        logger.info(
            f"🎤 Synchronizing Songkick events for: '{artist.name}'"
        )

        # Get Songkick events
        songkick_provider = self.provider_manager.get_provider("songkick")
        payloads = await songkick_provider.get_artist_events(artist.name)

        logger.info(
            f"Payloads received: {len(payloads)}"
        )

        if payloads:
            logger.info(
                f"First event payload: {payloads[0]}"
            )
        
        logger.info(
            f"📥 Received {len(payloads)} events from Songkick."
        )

        venues_created = 0
        venues_existing = 0
        events_created = 0
        events_existing = 0
        events_skipped = 0

        for payload in payloads:
            # Extract artist IDs from Songkick event
            artist_ids = payload.get("artist_ids", [])
            
            # Resolve Songkick artist IDs to local artist slugs
            artist_slugs = await self._resolve_artist_ids(artist_ids)
            
            if not artist_slugs:
                logger.warning(
                    f"Skipping event {payload.get('id')}: "
                    f"No artists could be resolved from IDs {artist_ids}"
                )
                events_skipped += 1
                continue
            
            # Map event and venue
            event, venue = SongkickEventMapper.to_domain(
                payload,
                artist_slugs
            )
            
            # Venue upsert
            venue_created = await self.venue_repository.upsert_venue(venue)
            if venue_created:
                venues_created += 1
            else:
                venues_existing += 1
            
            event.venue_slug = venue.slug
            
            # Event upsert using Songkick external ID
            try:
                created = await self.event_repository.upsert_event_by_provider(
                    event,
                    "songkick"
                )
                
                if created:
                    events_created += 1
                else:
                    events_existing += 1
            except ValueError as e:
                logger.warning(
                    f"Skipping event without Songkick ID: {e}"
                )
                events_skipped += 1

        elapsed = time.perf_counter() - started_at

        logger.info(
            "──────── Songkick Synchronization Summary ────────"
        )

        logger.info(
            f"🎤 Artist: {artist.name}"
        )

        logger.info(
            f"📥 Events received: {len(payloads)}"
        )

        logger.info(
            f"✅ New events: {events_created}"
        )

        logger.info(
            f"♻️ Existing events: {events_existing}"
        )

        logger.info(
            f"⏭️ Skipped events (no artists resolved): {events_skipped}"
        )

        logger.info(
            f"🏟️ New venues: {venues_created}"
        )

        logger.info(
            f"♻️ Existing venues: {venues_existing}"
        )

        logger.info(
            f"⏱️ Finished in {elapsed:.2f}s"
        )

        logger.info(
            "─────────────────────────────────────────"
        )

        return {
            "artist": artist.name,
            "events_received": len(payloads),
            "events_created": events_created,
            "events_existing": events_existing,
            "events_skipped": events_skipped,
            "venues_created": venues_created,
            "venues_existing": venues_existing,
            "elapsed_seconds": round(elapsed, 2),
        }

    async def _resolve_artist_ids(
        self,
        artist_ids: list[int],
    ) -> list[str]:
        """
        Resolve Songkick numeric artist IDs to local artist slugs.
        
        Example:
            [976211] -> ["demi-lovato"]
            [976211, 22766] -> ["demi-lovato", "foo-fighters"]
        """
        artist_slugs = []
        unresolved_ids = []
        
        for songkick_id in artist_ids:
            # Try to resolve via Songkick ID
            artist = await self.artist_repository.get_by_songkick_id(songkick_id)
            
            if artist:
                artist_slugs.append(artist.slug)
                logger.debug(f"Resolved Songkick ID {songkick_id} to slug {artist.slug}")
            else:
                unresolved_ids.append(songkick_id)
                logger.warning(f"Could not resolve Songkick artist ID: {songkick_id}")
        
        if unresolved_ids:
            logger.warning(
                f"Unresolved Songkick artist IDs: {unresolved_ids}. "
                f"These artists do not exist locally."
            )
        
        return artist_slugs