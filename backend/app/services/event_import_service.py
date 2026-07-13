from app.core.logger import get_logger

from app.mappers.bandsintown_event_mapper import (
    BandsintownEventMapper,
)

from app.services.provider_manager import (
    ProviderManager,
)


logger = get_logger("event_import")


class EventImportService:

    def __init__(
        self,
        provider_manager: ProviderManager,
    ):

        self.provider_manager = provider_manager

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

        events = []

        venues = []

        for payload in payloads:

            event, venue = BandsintownEventMapper.to_domain(
                payload,
                artist_slug,
            )

            events.append(event)

            venues.append(venue)

        logger.info(
            f"{len(events)} events mapped."
        )

        return events, venues