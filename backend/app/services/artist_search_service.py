from app.core.logger import get_logger

from app.schemas.artist_search import (
    ArtistSearchItem,
)

from app.services.provider_manager import (
    ProviderManager,
)

from app.repositories.artist_repository import (
    ArtistRepository,
)

from app.mappers.artist_response_mapper import (
    ArtistResponseMapper,
)


logger = get_logger(
    "artist_search"
)


class ArtistSearchService:

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

    async def search_artist(
        self,
        query: str,
    ) -> list[ArtistSearchItem]:
        """Find artists to import, from Songkick.

        Songkick is the source of truth here. It is what GigCrowd's catalogue is
        built from - every lineup entry, every event, every artist row resolves
        through a Songkick id - so an artist discovered here can be imported and
        then given real events without a second provider being consulted.

        Spotify used to be the only source for this, which made artist discovery
        fail outright whenever Spotify refused to answer. Development-mode access
        needs a Premium account, so that was not a hypothetical: search returned
        nothing and importing was impossible.

        Spotify is still asked, because a persisted Spotify id and image on an
        artist are worth keeping and a Spotify-only act is still worth
        surfacing. It is asked second and its failure is swallowed, so a 403 from
        Spotify now costs the reader some extra rows rather than the whole
        feature.
        """

        logger.info(
            f"Searching artists for discovery: {query}"
        )

        songkick_results = (
            await self.provider_manager.search_artist(
                query,
                provider="songkick",
            )
        )

        results: list[ArtistSearchItem] = []

        for artist in songkick_results:

            response = (
                ArtistResponseMapper
                .from_search_item(artist)
            )

            existing = await self.artist_repository.get_by_external_id(
                "songkick",
                artist.provider_artist_id,
            )

            if existing:

                response.is_imported = True

                response.id = existing.id

                response.slug = existing.slug

                # The stored image, when there is one. This row has already
                # been through import, so what the catalogue holds is the
                # picture the reader sees everywhere else in the product;
                # the provider's search image remains the fallback for the
                # artists stored without one.
                response.image = (
                    existing.image or response.image
                )

            # An artist imported before discovery was Songkick-first may carry
            # only a Spotify id. There is deliberately no second lookup for it:
            # matching a Songkick result to a Spotify-only row means comparing
            # names, which is the guessing this flow exists to avoid. Such a row
            # is reconciled properly when the catalogue is expanded by Songkick
            # id, not by a search-time coincidence.

            results.append(response)

        results.extend(
            await self._spotify_extras(query, results)
        )

        return results

    async def _spotify_extras(
        self,
        query: str,
        existing: list[ArtistSearchItem],
    ) -> list[ArtistSearchItem]:
        """Spotify results for acts Songkick did not return.

        An optional contribution. Spotify answering with a 403, or not being
        configured at all, must not affect discovery - which is the entire point
        of making it optional - so every failure here returns nothing and is
        logged rather than raised.
        """

        try:
            spotify_results = (
                await self.provider_manager.search_artist(
                    query,
                    provider="spotify",
                )
            )

        except Exception as error:
            logger.info(
                "Spotify did not contribute to artist search: "
                f"{type(error).__name__}: {error}"
            )

            return []

        seen = {
            item.provider_artist_id
            for item in existing
            if item.provider == "songkick"
        }

        seen_names = {
            (item.name or "").casefold()
            for item in existing
        }

        extras: list[ArtistSearchItem] = []

        for artist in spotify_results:

            # Songkick already answered for this act, in a result the reader can
            # actually import, so the Spotify row would only be a second door to
            # the same artist.
            if artist.provider_artist_id in seen:
                continue

            if (artist.name or "").casefold() in seen_names:
                continue

            response = (
                ArtistResponseMapper
                .from_search_item(artist)
            )

            imported = await self.artist_repository.get_by_external_id(
                "spotify",
                artist.provider_artist_id,
            )

            if imported:

                response.is_imported = True

                response.id = imported.id

                response.slug = imported.slug

                # Same rule as the Songkick half: the persisted picture
                # first, the provider's as fallback.
                response.image = (
                    imported.image or response.image
                )

            extras.append(response)

        return extras