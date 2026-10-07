from app.core.logger import get_logger

from app.mappers.bandsintown_event_mapper import (
    BandsintownEventMapper,
)
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

from app.services.event_enrichment_service import (
    EventEnrichmentService,
)

import time

from app.domain.artist import Artist

logger = get_logger("event_import")


class EventImportService:

    def __init__(
        self,
        provider_manager: ProviderManager,
        event_repository: EventRepository,
        venue_repository: VenueRepository,
        artist_repository: ArtistRepository,
        enrichment_service: EventEnrichmentService = None,
    ):

        self.provider_manager = provider_manager

        self.event_repository = event_repository

        self.venue_repository = venue_repository
        
        self.artist_repository = artist_repository

        # Shared with the scheduler's enrichment service, so an import-time
        # read and a scheduled read are literally the same code path rather
        # than two implementations that have to be kept in agreement.
        self.enrichment_service = enrichment_service

    async def sync_artist_events(
        self,
        artist: Artist,
        provider: str = "songkick",
    ):
        """
        Synchronize events for an artist from the specified provider.
        
        Phase 4: Defaults to Songkick as the canonical source.
        Bandsintown support retained for backward compatibility.
        """
        started_at = time.perf_counter()

        logger.info(
            f"🎤 Synchronizing artist: '{artist.name}' from {provider}"
        )

        if provider == "songkick":
            # Use Songkick-specific import logic
            from app.services.songkick_event_import_service import SongkickEventImportService
            from app.services.lineup_artist_importer import (
                LineupArtistImporter,
            )
            from app.jobs.enrichment_job import resolve_fields
            from app.config import settings

            songkick_service = SongkickEventImportService(
                self.provider_manager,
                self.event_repository,
                self.venue_repository,
                self.artist_repository,
                # Enrichment on import is the normal path, not an opt-in extra
                # pass. Turning it off is a deliberate choice about network
                # budget, and the events it leaves behind are recovered by the
                # scheduler instead of by a person.
                enrichment_service=(
                    self.enrichment_service
                ),
                enrich_fields=resolve_fields(
                    settings.ENRICH_ON_IMPORT_FIELDS
                ),
                enrich_limit=(
                    settings.ENRICH_ON_IMPORT_MAX_EVENTS
                ),
                enrich_delay_seconds=(
                    settings.ENRICH_ON_IMPORT_DELAY_SECONDS
                ),
                lineup_importer=(
                    LineupArtistImporter(
                        self.artist_repository
                    )
                    if settings.LINEUP_ARTIST_IMPORT_ENABLED
                    else None
                ),
                lineup_artist_limit=(
                    settings.LINEUP_ARTIST_IMPORT_MAX_ARTISTS
                ),
            )
            return await songkick_service.sync_artist_events(artist)
        
        # Bandsintown (existing logic)
        payloads = await self.provider_manager.get_artist_events(
            artist.name,
            provider=provider
        )

        logger.info(
            f"Payloads received: {len(payloads)}"
        )

        if payloads:
            logger.info(
                f"First event payload: {payloads[0]}"
            )
        
        logger.info(
            f"📥 Received {len(payloads)} events from provider."
        )

        venues_created = 0
        events_created = 0
        events_existing = 0

        existing_venues = set()

        for payload in payloads:

            event, venue = BandsintownEventMapper.to_domain(
                payload,
                artist.slug,
            )

            #
            # Venue
            #

            existing_venue = await self.venue_repository.get_by_name(
                venue.name
            )

            if existing_venue:

                venue.slug = existing_venue["slug"]

                existing_venues.add(
                    venue.slug
                )

            else:

                venue.slug = await self.venue_repository.generate_unique_slug(
                    venue.name
                )

                await self.venue_repository.insert_venue(
                    venue
                )

                venues_created += 1

            event.venue_slug = venue.slug

            #
            # Event
            #

            created = await self.event_repository.upsert_event(
                event
            )

            if created:

                events_created += 1

            else:

                events_existing += 1

        elapsed = time.perf_counter() - started_at

        logger.info(
            "──────── Synchronization Summary ────────"
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
            f"🏟️ New venues: {venues_created}"
        )

        logger.info(
            f"♻️ Existing venues: {len(existing_venues)}"
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
            "venues_created": venues_created,
            "venues_existing": len(existing_venues),
            "elapsed_seconds": round(elapsed, 2),
        }