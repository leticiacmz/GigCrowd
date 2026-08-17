from app.core.logger import get_logger

from app.repositories.artist_repository import (
    ArtistRepository,
)

from app.schemas.artist_import import (
    ArtistImportRequest,
)

from app.services.provider_manager import (
    ProviderManager,
)

from app.mappers.artist_response_mapper import (
    ArtistResponseMapper,
)

from app.providers.songkick.artist_mapper import (
    SongkickArtistMapper,
)


logger = get_logger(
    "artist_import"
)


class ArtistImportService:

    def __init__(
        self,
        provider_manager: ProviderManager,
        artist_repository: ArtistRepository,
    ):

        self.provider_manager = (
            provider_manager
        )

        self.artist_repository = (
            artist_repository
        )

    # --------------------------------------------------
    # GENERIC IMPORT
    # --------------------------------------------------

    async def import_artist(
        self,
        request: ArtistImportRequest,
    ):

        logger.info(
            f"Import requested for "
            f"{request.provider}: "
            f"{request.provider_artist_id}"
        )

        # --------------------------------------------------
        # SONGKICK
        # --------------------------------------------------

        if request.provider == "songkick":

            return await self.import_songkick_artist(
                artist_name=(
                    request.artist_data.get(
                        "name"
                    )
                    if request.artist_data
                    else None
                ),
                songkick_artist_data=(
                    request.artist_data
                ),
                songkick_id=(
                    request.provider_artist_id
                ),
            )

        # --------------------------------------------------
        # SPOTIFY
        # --------------------------------------------------

        if request.provider == "spotify":

            artist_name = None

            if request.artist_data:

                artist_name = (
                    request.artist_data.get(
                        "name"
                    )
                )

            if not artist_name:

                raise ValueError(
                    "Spotify import requires "
                    "artist_data.name"
                )

            return await self.import_from_spotify(
                artist_name
            )

        raise ValueError(
            f"Unsupported artist provider: "
            f"{request.provider}"
        )

    # --------------------------------------------------
    # IMPORT FROM SPOTIFY
    # --------------------------------------------------

    async def import_from_spotify(
        self,
        artist_name: str,
    ):

        logger.info(
            f"Resolving Spotify artist "
            f"'{artist_name}' through Songkick"
        )

        # Search Songkick using the artist name
        songkick_results = (
            await self.provider_manager.search_artist(
                artist_name,
                provider="songkick",
            )
        )

        if not songkick_results:

            raise ValueError(
                f"Artist '{artist_name}' "
                "was not found on Songkick."
            )

        # Try to find the exact artist name first
        exact_match = None

        normalized_name = (
            artist_name.strip().lower()
        )

        for result in songkick_results:

            if (
                result.name
                and result.name.strip().lower()
                == normalized_name
            ):

                exact_match = result

                break

        # If exact match does not exist,
        # do not blindly import the first result.
        if not exact_match:

            raise ValueError(
                f"Could not find an exact "
                f"Songkick match for '{artist_name}'."
            )

        songkick_id = (
            exact_match.provider_artist_id
        )

        logger.info(
            f"Resolved '{artist_name}' to "
            f"Songkick ID {songkick_id}"
        )

        # --------------------------------------------------
        # IMPORTANT:
        # Check canonical Songkick identity BEFORE
        # generating any slug.
        # --------------------------------------------------

        existing = (
            await self.artist_repository
            .get_by_songkick_id(
                songkick_id
            )
        )

        if existing:

            logger.info(
                f"Artist '{existing.name}' "
                f"already exists with slug "
                f"'{existing.slug}'"
            )

            return {
                "artist": existing,
                "is_new": False,
            }

        # --------------------------------------------------
        # Build Songkick data
        # --------------------------------------------------

        songkick_artist_data = {
            "id": songkick_id,
            "name": exact_match.name,
            "popularity": (
                (
                    exact_match.popularity or 0
                ) / 100
            ),
            "is_valid": (
                exact_match.verified
            ),
        }

        return await self.import_songkick_artist(
            artist_name=exact_match.name,
            songkick_artist_data=(
                songkick_artist_data
            ),
        )

    # --------------------------------------------------
    # SONGKICK IMPORT
    # --------------------------------------------------

    async def import_songkick_artist(
        self,
        artist_name: str,
        songkick_artist_data: dict,
        spotify_image: str | None = None,
    ):
        """
        Import Songkick artist using data obtained from
        the Songkick search result.

        Songkick is the canonical source.

        Spotify is used only as an image fallback when
        Songkick does not provide an image.
        """

        logger.info(
            f"Importing Songkick artist: {artist_name}"
        )

        songkick_id = songkick_artist_data.get(
            "id"
        )

        existing = await self.artist_repository.get_by_external_id(
            "songkick",
            songkick_id
        )

        if existing:

            logger.info(
                f"Artist already imported: {existing.name}"
            )

            return {
                "artist": existing,
                "is_new": False
            }

        artist = SongkickArtistMapper.to_domain(
            songkick_artist_data,
            fallback_image=spotify_image,
        )

        artist.slug = await self.artist_repository.generate_unique_slug(
            artist.name
        )

        await self.artist_repository.insert_artist(
            artist
        )

        logger.info(
            f"Artist '{artist.name}' imported successfully "
            f"with Songkick ID: {songkick_id}"
        )

        return {
            "artist": artist,
            "is_new": True
        }