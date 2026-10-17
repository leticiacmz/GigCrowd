from datetime import datetime, timedelta, timezone

import httpx

from app.config import settings
from app.core.logger import get_logger

from app.providers.base import BaseProvider
from app.providers.spotify.client import SpotifyClient
from app.providers.spotify.artist_mapper import SpotifyArtistMapper

from app.schemas.artist_search import ArtistSearchItem


logger = get_logger("spotify")


class SpotifyProvider(BaseProvider):

    def __init__(self):

        self.client = SpotifyClient()

        # A refused search is an answer about this app's access, not about
        # the query, so it quiets the search for a bounded window instead of
        # letting every later search spend one more call that cannot
        # succeed. One provider instance serves the whole process (the
        # registry), so this one clock covers discovery from every route.
        # `get_artist` is never quieted: an explicit import still tries, and
        # its answer is the reader's. The quiet is never permanent - the
        # first search after the window asks again, and a success clears
        # the clock.
        self._search_quiet_until: datetime | None = None

    async def search_artist(
        self,
        query: str,
    ) -> list[ArtistSearchItem]:

        now = datetime.now(timezone.utc)

        if (
            self._search_quiet_until is not None
            and now < self._search_quiet_until
        ):

            logger.info(
                "Spotify search skipped while quiet (until "
                f"{self._search_quiet_until.isoformat(timespec='seconds')}): "
                f"{query!r}"
            )

            return []

        logger.info(
            f"Searching Spotify artists: {query}"
        )

        try:
            response = await self.client.search_artist(
                query
            )

        except httpx.HTTPStatusError as error:

            minutes = max(
                0,
                int(settings.SPOTIFY_SEARCH_COOLDOWN_MINUTES),
            )

            self._search_quiet_until = now + timedelta(
                minutes=minutes
            )

            logger.warning(
                "Spotify refused the search (HTTP "
                f"{error.response.status_code}); quieting Spotify "
                f"search for {minutes}min, until "
                f"{self._search_quiet_until.isoformat(timespec='seconds')} "
                "- later searches will not pay for the same refusal; the "
                "first search after the window asks again"
            )

            raise

        self._search_quiet_until = None

        return SpotifyArtistMapper.map_search_results(
            response
        )

    async def get_artist(
        self,
        artist_id: str,
    ):

        logger.info(
            f"Fetching Spotify artist {artist_id}"
        )

        response = await self.client.get_artist(
            artist_id
        )

        return SpotifyArtistMapper.map_artist(
            response
        )