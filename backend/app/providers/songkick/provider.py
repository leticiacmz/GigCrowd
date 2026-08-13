from app.core.logger import get_logger

from app.providers.base import BaseProvider
from app.providers.songkick.client import SongkickClient
from app.providers.songkick.artist_mapper import SongkickArtistMapper
from app.services.artist_matching_service import ArtistMatchingService

from app.schemas.artist_search import ArtistSearchItem


logger = get_logger("songkick_provider")


class SongkickProvider(BaseProvider):

    def __init__(self):

        self.client = SongkickClient()

    async def search_artist(
        self,
        query: str,
    ) -> list[ArtistSearchItem]:

        logger.info(
            f"Searching Songkick artists: {query}"
        )

        raw_data = await self.client.search_artist(query)
        
        # Extract artist data from nested response structure
        attributes = raw_data.get("data", {}).get("attributes", {})
        search_results = attributes.get("search_results", {})
        artists_data = search_results.get("artists", [])
        
        results = []
        for result in artists_data:
            document = result.get("document", {})
            
            results.append(ArtistSearchItem(
                provider="songkick",
                provider_artist_id=document.get("id"),
                name=document.get("name"),
                followers=None,
                image=None,
                popularity=int(document.get("popularity", 0) * 100) if document.get("popularity") else None,
                verified=document.get("is_valid", False),
                genres=[],
                is_imported=False
            ))
        
        return results

    async def get_artist(
        self,
        artist_id: str,
    ):
        """
        Get artist details by Songkick ID.
        
        Since Songkick doesn't have a direct get-artist-by-ID endpoint,
        this implementation:
        1. Searches for the artist by extracting name from search results
        2. In practice, the caller should have the name from search results
        3. For now, we need to search and match by ID
        
        This is a limitation of Songkick's API - they don't expose
        a direct artist-by-ID endpoint.
        """
        logger.info(f"Fetching Songkick artist {artist_id}")
        
        # Extract numeric ID from prefixed format if needed
        # Artist976211 -> 976211
        if artist_id.startswith("Artist"):
            numeric_id = artist_id.replace("Artist", "")
        else:
            numeric_id = artist_id
        
        # We need to search to get artist data
        # This is inefficient but Songkick doesn't provide a direct endpoint
        # In practice, the caller should have the artist name from search results
        # For now, we'll need to require the name to be passed separately
        # or implement a search-by-ID mechanism
        
        # As a fallback, we'll need to search and match by ID
        # This requires searching and then filtering results by ID
        # But we don't have the artist name to search with
        
        logger.warning(
            f"Songkick get_artist by ID not directly supported. "
            f"ID: {artist_id}. "
            f"Use search_artist() and ArtistMatchingService instead."
        )
        
        raise NotImplementedError(
            "Songkick does not provide a direct artist-by-ID endpoint. "
            "Use search_artist() with the artist name, then use the "
            "returned artist data directly."
        )

    async def get_artist_events(
        self,
        artist_name: str,
    ):
        """
        Get artist events from Songkick.
        
        Songkick's search endpoint returns both artists and events together.
        This method searches for the artist and extracts events from the response.
        """
        logger.info(f"Fetching Songkick events for {artist_name}")
        
        raw_data = await self.client.search_artist(artist_name)
        
        # Extract event data from nested response structure
        attributes = raw_data.get("data", {}).get("attributes", {})
        search_results = attributes.get("search_results", {})
        events_data = search_results.get("events", [])
        
        logger.info(f"Found {len(events_data)} events for {artist_name}")
        
        return events_data