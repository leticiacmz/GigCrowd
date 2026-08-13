from app.core.logger import get_logger

from app.repositories.artist_repository import ArtistRepository

from app.schemas.artist_import import ArtistImportRequest

from app.services.provider_manager import ProviderManager
from app.mappers.artist_response_mapper import ArtistResponseMapper
from app.providers.songkick.artist_mapper import SongkickArtistMapper


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


        existing = await self.artist_repository.get_by_external_id(
            request.provider,
            request.provider_artist_id,
        )


        if existing:


            logger.info(
                "Artist already imported."
            )


            return {
                "artist": existing,
                "is_new": False,
            }


        # Songkick doesn't support get_artist by ID, so we need special handling
        if request.provider == "songkick":
            # For Songkick, we need to search and use the artist data from search results
            # This is a limitation of Songkick's API
            # In practice, the caller should have the artist name from search results
            logger.warning(
                f"Songkick import by ID not directly supported. "
                f"Use search results from ArtistSearchService instead."
            )
            raise NotImplementedError(
                "Songkick import by ID not supported. "
                "Use ArtistSearchService to get artist data, then import "
                "using the name and SongkickArtistMapper directly."
            )


        artist = await self.provider_manager.get_artist(
            provider=request.provider,
            artist_id=request.provider_artist_id,
        )


        artist.slug = await self.artist_repository.generate_unique_slug(
            artist.name
        )


        await self.artist_repository.insert_artist(
            artist
        )


        logger.info(
            f"Artist '{artist.name}' imported successfully."
        )


        return {
            "artist": artist,
            "is_new": True,
        }

    async def import_songkick_artist(
        self,
        artist_name: str,
        songkick_artist_data: dict,
    ):
        """
        Import Songkick artist using the artist data from search results.
        
        This is needed because Songkick doesn't support get_artist by ID.
        The caller should have the artist data from ArtistSearchService.
        """
        logger.info(f"Importing Songkick artist: {artist_name}")
        
        # Check if already exists by Songkick ID
        songkick_id = songkick_artist_data.get("id")
        existing = await self.artist_repository.get_by_external_id(
            "songkick",
            songkick_id
        )
        
        if existing:
            logger.info(f"Artist already imported: {existing.name}")
            return {
                "artist": existing,
                "is_new": False
            }
        
        # Map to domain
        artist = SongkickArtistMapper.to_domain(songkick_artist_data)
        
        # Generate unique slug
        artist.slug = await self.artist_repository.generate_unique_slug(
            artist.name
        )
        
        # Insert
        await self.artist_repository.insert_artist(artist)
        
        logger.info(f"Artist '{artist.name}' imported successfully with Songkick ID: {songkick_id}")
        
        return {
            "artist": artist,
            "is_new": True
        }