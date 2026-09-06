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

    # ==================================================
    # HELPERS
    # ==================================================

    @staticmethod
    def _merge_genres(
        spotify_genres: list[str] | None,
        songkick_genres: list[str] | None,
    ) -> list[str]:

        """
        Merge Spotify and Songkick genres.

        Deduplication is case-insensitive and ignores
        surrounding whitespace, but preserves the
        original display value.

        Example:

            Spotify:
                ["rock", "Alternative Rock"]

            Songkick:
                ["Rock", "indie"]

            Result:
                ["rock", "Alternative Rock", "indie"]
        """

        result: list[str] = []

        seen: set[str] = set()

        for genre in (
            (spotify_genres or [])
            + (songkick_genres or [])
        ):

            if not isinstance(
                genre,
                str,
            ):
                continue

            normalized = genre.strip().casefold()

            if not normalized:
                continue

            if normalized in seen:
                continue

            seen.add(normalized)

            result.append(
                genre.strip()
            )

        return result

    # ==================================================
    # GENERIC IMPORT
    # ==================================================

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
        # SPOTIFY
        # --------------------------------------------------

        if request.provider == "spotify":

            return await self.import_from_spotify(
                request.provider_artist_id
            )

        # --------------------------------------------------
        # SONGKICK
        # --------------------------------------------------

        if request.provider == "songkick":

            artist_name = None

            if request.artist_data:

                artist_name = (
                    request.artist_data.get(
                        "name"
                    )
                )

            if not artist_name:

                raise ValueError(
                    "Songkick import requires "
                    "artist_data.name"
                )

            return await self.import_songkick_artist(
                artist_name=artist_name,
                songkick_artist_data=(
                    request.artist_data
                ),
                spotify_image=request.image,
            )

        raise ValueError(
            f"Unsupported artist provider: "
            f"{request.provider}"
        )

    # ==================================================
    # IMPORT FROM SPOTIFY
    # ==================================================

    async def import_from_spotify(
        self,
        spotify_artist_id: str,
    ):

        logger.info(
            f"Starting Spotify artist import: "
            f"{spotify_artist_id}"
        )

        # --------------------------------------------------
        # 1. Get complete Spotify artist
        # --------------------------------------------------

        spotify_provider = (
            self.provider_manager.get_provider(
                "spotify"
            )
        )

        spotify_artist = (
            await spotify_provider.get_artist(
                spotify_artist_id
            )
        )

        if not spotify_artist:

            raise ValueError(
                f"Spotify artist "
                f"'{spotify_artist_id}' "
                "could not be found."
            )

        artist_name = spotify_artist.name

        logger.info(
            f"Spotify artist resolved: "
            f"{artist_name}"
        )

        # --------------------------------------------------
        # 2. Resolve canonical artist on Songkick
        # --------------------------------------------------

        logger.info(
            f"Resolving '{artist_name}' "
            "through Songkick"
        )

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

        # --------------------------------------------------
        # 3. Exact name match
        # --------------------------------------------------

        normalized_name = (
            artist_name.strip().casefold()
        )

        exact_match = None

        for result in songkick_results:

            if not result.name:
                continue

            if (
                result.name.strip().casefold()
                == normalized_name
            ):

                exact_match = result

                break

        if not exact_match:

            raise ValueError(
                f"Could not find an exact "
                f"Songkick match for "
                f"'{artist_name}'."
            )

        songkick_id = (
            exact_match.provider_artist_id
        )

        if not songkick_id:

            raise ValueError(
                f"Songkick match for "
                f"'{artist_name}' has no ID."
            )

        logger.info(
            f"Resolved '{artist_name}' to "
            f"Songkick ID {songkick_id}"
        )

        # --------------------------------------------------
        # 4. Check canonical Songkick identity
        # --------------------------------------------------

        existing_by_songkick = (
            await self.artist_repository
            .get_by_songkick_id(
                songkick_id
            )
        )

        # --------------------------------------------------
        # 5. Build Songkick data
        # --------------------------------------------------

        songkick_artist_data = {

            "id": str(
                songkick_id
            ),

            "name": exact_match.name,

            "image": exact_match.image,

            "genres": (
                exact_match.genres
                or []
            ),

            "popularity": (
                (
                    exact_match.popularity
                    / 100
                )
                if exact_match.popularity
                is not None
                else None
            ),

            "is_valid": (
                exact_match.verified
            ),
        }

        logger.info(
            f"Songkick genres for "
            f"'{artist_name}': "
            f"{songkick_artist_data['genres']}"
        )

        # --------------------------------------------------
        # 6. Existing artist
        # --------------------------------------------------

        if existing_by_songkick:

            logger.info(
                f"Artist '{existing_by_songkick.name}' "
                "already exists by Songkick ID. "
                "Applying Spotify enrichment."
            )

            spotify_genres = (
                spotify_artist.genres
                or []
            )

            songkick_genres = (
                songkick_artist_data.get(
                    "genres",
                    [],
                )
                or []
            )

            existing_by_songkick.external_ids[
                "songkick"
            ] = str(songkick_id)

            existing_by_songkick.external_ids[
                "spotify"
            ] = spotify_artist.external_ids.get(
                "spotify",
                spotify_artist_id,
            )

            if (
                spotify_artist.image
                and not existing_by_songkick.image
            ):

                existing_by_songkick.image = (
                    spotify_artist.image
                )

            existing_by_songkick.genres = (
                self._merge_genres(
                    existing_by_songkick.genres,
                    self._merge_genres(
                        spotify_genres,
                        songkick_genres,
                    ),
                )
            )

            if (
                spotify_artist.popularity
                is not None
            ):

                existing_by_songkick.popularity = (
                    spotify_artist.popularity
                )

            # Persist enrichment.
            await self.artist_repository.update_external_data(
                existing_by_songkick.id,
                existing_by_songkick.external_ids,
                existing_by_songkick.image,
                existing_by_songkick.genres,
                existing_by_songkick.popularity,
            )

            refreshed_artist = (
                await self.artist_repository
                .get_by_songkick_id(
                    songkick_id
                )
            )

            return {
                "artist": (
                    refreshed_artist
                    or existing_by_songkick
                ),
                "is_new": False,
            }

        # --------------------------------------------------
        # 7. Create new canonical artist
        # --------------------------------------------------

        return await self.import_songkick_artist(
            artist_name=exact_match.name,
            songkick_artist_data=(
                songkick_artist_data
            ),
            spotify_artist=spotify_artist,
        )

    # ==================================================
    # SONGKICK IMPORT
    # ==================================================

    async def import_songkick_artist(
        self,
        artist_name: str,
        songkick_artist_data: dict,
        spotify_artist=None,
        spotify_image: str | None = None,
    ):

        logger.info(
            f"Importing Songkick artist: "
            f"{artist_name}"
        )

        songkick_id = (
            songkick_artist_data.get(
                "id"
            )
        )

        if not songkick_id:

            raise ValueError(
                "Songkick artist requires an ID."
            )

        songkick_id = str(
            songkick_id
        )

        # --------------------------------------------------
        # Check canonical identity
        # --------------------------------------------------

        existing = (
            await self.artist_repository
            .get_by_songkick_id(
                songkick_id
            )
        )

        if existing:

            logger.info(
                f"Artist already imported: "
                f"{existing.name}"
            )

            return {
                "artist": existing,
                "is_new": False,
            }

        # --------------------------------------------------
        # Build canonical artist
        # --------------------------------------------------

        artist = SongkickArtistMapper.to_domain(
            songkick_artist_data,
            spotify_artist=spotify_artist,
            fallback_image=spotify_image,
        )

        # --------------------------------------------------
        # Canonical slug
        # --------------------------------------------------

        artist.slug = (
            await self.artist_repository
            .generate_unique_slug(
                artist.name
            )
        )

        # --------------------------------------------------
        # Persist
        # --------------------------------------------------

        await self.artist_repository.insert_artist(
            artist
        )

        logger.info(
            f"Artist '{artist.name}' imported "
            f"successfully with Songkick ID: "
            f"{songkick_id}"
        )

        return {
            "artist": artist,
            "is_new": True,
        } 