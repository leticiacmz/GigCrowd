from app.services.artist_import_service import (
    ArtistImportService,
)

from app.schemas.artist_import import (
    ArtistImportRequest,
)


class ArtistSynchronizationService:

    def __init__(
        self,
        artist_import_service: ArtistImportService,
    ):
        self.artist_import_service = (
            artist_import_service
        )

    async def synchronize_artist(
        self,
        request: ArtistImportRequest,
    ):

        artist = (
            await self.artist_import_service.import_artist(
                request
            )
        )

        #
        # Próximos commits:
        #
        # await self.event_import_service...
        #
        # await self.album_import_service...
        #
        # await self.track_import_service...
        #

        return artist