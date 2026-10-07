from app.core.logger import get_logger

from app.providers.base import BaseProvider
from app.providers.songkick.client import (
    SongkickClient,
)
from app.schemas.artist_search import (
    ArtistSearchItem,
)


logger = get_logger(
    "songkick_provider"
)


class SongkickProvider(BaseProvider):

    def __init__(self):

        self.client = SongkickClient()

    # ==================================================
    # ARTIST SEARCH
    # ==================================================

    async def search_artist(
        self,
        query: str,
    ) -> list[ArtistSearchItem]:

        logger.info(
            f"Searching Songkick artists: {query}"
        )

        data = (
            await self.client.search_artist_full(
                query
            )
        )

        artists_data = data.get(
            "artists",
            [],
        )

        results: list[ArtistSearchItem] = []

        for result in artists_data:

            document = result.get(
                "document",
                {},
            )

            artist_id = document.get(
                "id"
            )

            name = document.get(
                "name"
            )

            if not artist_id or not name:
                continue

            # --------------------------------------------------
            # Popularity
            # --------------------------------------------------

            popularity = document.get(
                "popularity"
            )

            if popularity is not None:

                try:

                    popularity = int(
                        float(
                            popularity
                        ) * 100
                    )

                except (
                    TypeError,
                    ValueError,
                ):

                    popularity = None

            # --------------------------------------------------
            # Genres
            # --------------------------------------------------

            genres = document.get(
                "genres",
                [],
            )

            if genres is None:
                genres = []

            if isinstance(
                genres,
                str,
            ):

                genres = [
                    genres
                ]

            if not isinstance(
                genres,
                list,
            ):

                genres = []

            genres = [
                genre.strip()
                for genre in genres
                if isinstance(
                    genre,
                    str,
                )
                and genre.strip()
            ]

            # --------------------------------------------------
            # Log actual Songkick data
            # --------------------------------------------------

            logger.info(
                "Songkick artist result: "
                f"name='{name}', "
                f"id='{artist_id}', "
                f"genres={genres}"
            )

            results.append(
                ArtistSearchItem(

                    provider="songkick",

                    provider_artist_id=str(
                        artist_id
                    ),

                    name=name,

                    image=document.get(
                        "image"
                    ),

                    popularity=popularity,

                    verified=document.get(
                        "is_valid",
                        False,
                    ),

                    genres=genres,

                    is_imported=False,
                )
            )

        logger.info(
            f"Found {len(results)} "
            "Songkick artists"
        )

        return results

    # ==================================================
    # GET ARTIST
    # ==================================================

    async def get_artist(
        self,
        artist_id: str,
    ):

        logger.info(
            f"Fetching Songkick artist "
            f"{artist_id}"
        )

        if artist_id.startswith(
            "Artist"
        ):

            numeric_id = (
                artist_id.replace(
                    "Artist",
                    "",
                    1,
                )
            )

        else:

            numeric_id = artist_id

        logger.warning(
            "Songkick get_artist by ID is not "
            "directly supported. "
            f"ID: {numeric_id}"
        )

        raise NotImplementedError(
            "Songkick does not provide a direct "
            "get-artist-by-ID endpoint. "
            "Use search_artist() with the artist name."
        )

    # ==================================================
    # EVENT IDENTITY
    # ==================================================

    @staticmethod
    def _event_identity(
        event: dict,
    ) -> tuple[str, str] | None:

        """
        Build a stable identity for a Songkick event.

        Songkick may expose the same event through
        multiple catalogue sections, so we use the
        provider ID first and URL as a fallback.
        """

        event_id = (
            event.get("songkick_id")
            or event.get("id")
        )

        if event_id:

            return (
                "songkick",
                str(event_id),
            )

        url = event.get(
            "url"
        )

        if url:

            return (
                "url",
                str(url).split("?")[0],
            )

        return None

    # ==================================================
    # GET ARTIST EVENTS
    # ==================================================

    async def get_artist_events(
        self,
        artist_name: str,
        artist_id: str | None = None,
    ) -> dict:
        """Every Songkick event for one artist.

        `artist_id` is a trusted Songkick artist ID and decides *which* artist this
        is. The name is for readability and for search-based enrichment only. A
        caller that knows the ID should always pass it: resolving by name alone
        picks whichever same-named act Songkick happens to rank first.
        """

        logger.info(
            "Fetching complete Songkick events "
            f"for {artist_name} "
            f"(artist_id={artist_id})"
        )

        data = (
            await self.client.scrape_artist(
                artist_name,
                artist_id=artist_id,
            )
        )

        events = data.get(
            "events",
            [],
        )

        upcoming = data.get(
            "upcoming",
            [],
        )

        upcoming_festivals = data.get(
            "upcoming_festivals",
            [],
        )

        gigography = data.get(
            "gigography",
            [],
        )

        gigography_festivals = data.get(
            "gigography_festivals",
            [],
        )

        live_streams = data.get(
            "live_streams",
            [],
        )

        # --------------------------------------------------
        # Build canonical import catalogue
        # --------------------------------------------------

        canonical_events = []

        seen_identities: set[
            tuple[str, str]
        ] = set()

        def add_event(
            event: dict,
            source: str,
        ) -> None:

            if not isinstance(
                event,
                dict,
            ):
                return

            identity = (
                self._event_identity(
                    event
                )
            )

            if identity is not None:

                if identity in seen_identities:

                    logger.debug(
                        "Skipping duplicate event "
                        f"from {source}: "
                        f"id={event.get('songkick_id') or event.get('id')}"
                    )

                    return

                seen_identities.add(
                    identity
                )

            canonical_events.append(
                event
            )

        # --------------------------------------------------
        # Regular events
        # --------------------------------------------------

        for event in events:

            add_event(
                event,
                "events",
            )

        # --------------------------------------------------
        # Upcoming festivals
        # --------------------------------------------------

        for festival in upcoming_festivals:

            add_event(
                festival,
                "upcoming_festivals",
            )

        logger.info(
            "Songkick canonical event catalogue: "
            f"regular_events={len(events)}, "
            f"upcoming={len(upcoming)}, "
            f"upcoming_festivals={len(upcoming_festivals)}, "
            f"canonical_events={len(canonical_events)}"
        )

        for event in upcoming_festivals:

            festival = event.get(
                "festival"
            )

            festival_name = None
            festival_series_id = None
            festival_artist_count = 0

            if isinstance(
                festival,
                dict,
            ):

                festival_name = (
                    festival.get(
                        "name"
                    )
                )

                festival_series_id = (
                    festival.get(
                        "series_id"
                    )
                )

                artists = festival.get(
                    "artists",
                    [],
                )

                if isinstance(
                    artists,
                    list,
                ):
                    festival_artist_count = (
                        len(artists)
                    )

            logger.info(
                "[EVENT CATALOG] Upcoming festival "
                "included in canonical catalogue: "
                f"id={event.get('songkick_id') or event.get('id')} | "
                f"name={event.get('name')} | "
                f"festival_name={festival_name} | "
                f"series={festival_series_id} | "
                f"festival_artists={festival_artist_count} | "
                f"start={event.get('start_date')} | "
                f"end={event.get('end_date')}"
            )

        search_data = data.get(
            "search",
            {},
        )

        return {

            "artist_name": artist_name,

            "artist_id": artist_id,

            "artist": data.get(
                "artist"
            ),

            "artists": search_data.get(
                "artists",
                [],
            ),

            # --------------------------------------------------
            # Canonical import catalogue
            # --------------------------------------------------

            "events": canonical_events,

            # --------------------------------------------------
            # Explicit upcoming catalogue
            # --------------------------------------------------

            "upcoming": upcoming,

            "upcoming_festivals": (
                upcoming_festivals
            ),

            # --------------------------------------------------
            # Historical catalogue
            # --------------------------------------------------

            "past_events": [
                event
                for event in gigography
                if not event.get(
                    "is_live_stream"
                )
            ],

            "gigography": gigography,

            "gigography_festivals": (
                gigography_festivals
            ),

            # --------------------------------------------------
            # Livestreams
            # --------------------------------------------------

            "live_streams": live_streams,

            # --------------------------------------------------
            # Other Songkick data
            # --------------------------------------------------

            "festivals": data.get(
                "festivals",
                [],
            ),

            "top_results": search_data.get(
                "top_results",
                [],
            ),

            "pages": data.get(
                "pages"
            ),

            "total_events": data.get(
                "total_events",
                len(canonical_events),
            ),
        }