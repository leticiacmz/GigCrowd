from app.core.logger import get_logger

from app.repositories.artist_repository import ArtistRepository

from app.schemas.artist_import import ArtistImportRequest

logger = get_logger("artist_import")


class ArtistImportService:

    def __init__(
        self,
        artist_repository: ArtistRepository,
    ):
        self.artist_repository = artist_repository

    async def import_artist(
        self,
        request: ArtistImportRequest,
    ):

        logger.info(
            f"Import requested for {request.provider}: {request.provider_artist_id}"
        )

        raise NotImplementedError(
            "Testing. Spotify import will be implemented in the next commit."
        )