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
        artist_slug: str,
        artist_name: str,
    ):

        logger.info(
            f"Importing events for '{artist_name}'"
        )

        payloads = await self.provider_manager.get_artist_events(
            artist_name
        )

        venues_created = 0

        events_created = 0

        venues_existing = 0
        

        for payload in payloads:

            event, venue = BandsintownEventMapper.to_domain(
                payload,
                artist_slug,
            )

            #
            # Venue
            #

            existing_venue = await self.venue_repository.get_by_name(
                venue.name
            )

            if existing_venue:

                venue.slug = existing_venue["slug"]
                venues_existing += 1

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

                continue

            await self.event_repository.insert_event(
                event
            )

            events_created += 1

        logger.info(

            f"Imported {events_created} events and "

            f"{venues_created} venues."

        )

        return {

            "venues_created": venues_created,

            "events_created": events_created,

        }