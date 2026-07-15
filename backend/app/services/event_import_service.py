from app.core.logger import get_logger

from app.mappers.bandsintown_event_mapper import (
    BandsintownEventMapper,
)

from app.repositories.event_repository import (
    EventRepository,
)

from app.repositories.venue_repository import (
    VenueRepository,
)

from app.services.provider_manager import (
    ProviderManager,
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
    ):

        self.provider_manager = provider_manager

        self.event_repository = event_repository

        self.venue_repository = venue_repository

    async def import_artist_events(
        self,
        artist: Artist,
    ):

        started_at = time.perf_counter()

        logger.info(
            f"🎤 Synchronizing artist: '{artist.name}'"
        )

        payloads = await self.provider_manager.get_artist_events(
            artist.name
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

            existing_event = (
                await self.event_repository.get_by_external_id(
                    "bandsintown",
                    event.external_ids["bandsintown"],
                )
            )

            if existing_event:

                events_existing += 1

                continue

            await self.event_repository.insert_event(
                event
            )

            events_created += 1

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