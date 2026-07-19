from app.services.artist_import_service import (
    ArtistImportService,
)


from app.services.event_import_service import (
    EventImportService,
)


from app.schemas.artist_import import (
    ArtistImportRequest,
)

from app.mappers.artist_response_mapper import ArtistResponseMapper


class ArtistSynchronizationService:


    def __init__(
        self,
        artist_import_service: ArtistImportService,
        event_import_service: EventImportService,
    ):


        self.artist_import_service = (
            artist_import_service
        )


        self.event_import_service = (
            event_import_service
        )




    async def synchronize_artist(
        self,
        request: ArtistImportRequest,
    ):



        result = await self.artist_import_service.import_artist(
            request
        )



        artist = result["artist"]



        if result["is_new"]:


            await self.event_import_service.import_artist_events(
                artist=artist
            )



        return ArtistResponseMapper.from_domain(
            artist
        )