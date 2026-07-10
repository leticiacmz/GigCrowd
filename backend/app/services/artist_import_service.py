from app.core.logger import get_logger

from app.repositories.artist_repository import ArtistRepository
from app.schemas.artist_import import ArtistImportRequest
from app.services.provider_manager import ProviderManager


logger = get_logger("artist_import")


class ArtistImportService:

    def __init__(
        self,
        provider_manager: ProviderManager,
        artist_repository: ArtistRepository,
    ):
        self.provider_manager = provider_manager
        self.artist_repository = artist_repository

    async def import_artist(
        self,
        request: ArtistImportRequest,
    ):

        logger.info(
            f"Import requested for {request.provider}: {request.provider_artist_id}"
        )

        artist = await self.provider_manager.get_artist(
            provider=request.provider,
            artist_id=request.provider_artist_id,
        )

        return artist