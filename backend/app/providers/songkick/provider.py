from app.core.logger import get_logger

from app.providers.base import BaseProvider
from app.providers.songkick.client import SongkickClient

from app.schemas.artist_search import ArtistSearchItem


logger = get_logger("songkick_provider")


class SongkickProvider(BaseProvider):

    def __init__(self):

        self.client = SongkickClient()

    # ============================================================
    # ARTIST SEARCH
    # ============================================================

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

        artists_data = data[
            "artists"
        ]

        results = []

        for result in artists_data:

            document = result.get(
                "document",
                {},
            )

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

            results.append(
                ArtistSearchItem(

                    provider="songkick",

                    provider_artist_id=(
                        document.get(
                            "id"
                        )
                    ),

                    name=document.get(
                        "name"
                    ),

                    followers=None,

                    image=document.get(
                        "image"
                    ),

                    popularity=popularity,

                    verified=document.get(
                        "is_valid",
                        False,
                    ),

                    genres=[],

                    is_imported=False,
                )
            )

        logger.info(
            f"Found {len(results)} "
            "Songkick artists"
        )

        return results

    # ============================================================
    # GET ARTIST
    # ============================================================

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

    # ============================================================
    # GET ARTIST EVENTS
    # ============================================================

    async def get_artist_events(
        self,
        artist_name: str,
    ) -> dict:

        logger.info(
            "Fetching complete Songkick events "
            f"for {artist_name}"
        )

        data = (
            await self.client.scrape_artist(
                artist_name
            )
        )

        events = data[
            "events"
        ]

        upcoming = data[
            "upcoming"
        ]

        upcoming_festivals = data[
            "upcoming_festivals"
        ]

        gigography = data[
            "gigography"
        ]

        gigography_festivals = data[
            "gigography_festivals"
        ]

        live_streams = data[
            "live_streams"
        ]

        logger.info(
            "Songkick complete catalogue: "
            f"{len(events)} total events, "
            f"{len(upcoming)} upcoming, "
            f"{len(gigography)} gigography events, "
            f"{len(live_streams)} livestreams"
        )

        return {

            "artist_name": artist_name,

            "artist": data[
                "artist"
            ],

            "artists": data[
                "search"
            ]["artists"],

            "events": events,

            "upcoming": upcoming,

            "upcoming_festivals": (
                upcoming_festivals
            ),

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

            "live_streams": (
                live_streams
            ),

            "festivals": data[
                "festivals"
            ],

            "top_results": data[
                "search"
            ]["top_results"],

            "pages": data[
                "pages"
            ],

            "total_events": data[
                "total_events"
            ],
        }