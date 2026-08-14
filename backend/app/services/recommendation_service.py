from app.core.logger import get_logger
from app.providers.spotify.client import SpotifyClient
from app.providers.spotify.artist_mapper import SpotifyArtistMapper
from app.domain.artist import Artist
from typing import Optional, List, Dict, Any
import httpx


logger = get_logger("recommendation")


class RecommendationService:
    """
    Spotify-based recommendation and discovery service.
    
    This service uses Spotify for:
    - Artist discovery/recommendations
    - Related artists
    - Enrichment of existing canonical artists
    
    It does NOT create canonical artists - that responsibility belongs to Songkick.
    """

    def __init__(self):
        self.client = SpotifyClient()

    async def get_related_artists(
        self,
        artist_name: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Get related artists from Spotify based on artist name.
        
        This is for discovery/recommendation purposes only.
        Returns Spotify artist data without creating GigCrowd artists.
        """
        logger.info(f"Finding related artists for: {artist_name}")
        
        try:
            # Search for the artist first to get Spotify ID
            search_results = await self.client.search_artist(artist_name)
            artists = search_results.get("artists", {}).get("items", [])
            
            if not artists:
                logger.warning(f"No Spotify artist found for: {artist_name}")
                return []
            
            # Get the first matching artist's ID
            spotify_artist_id = artists[0]["id"]
            
            # Get related artists using direct httpx call
            from app.providers.spotify.auth import spotify_auth
            token = await spotify_auth.get_access_token()
            
            async with httpx.AsyncClient() as http_client:
                related_response = await http_client.get(
                    f"https://api.spotify.com/v1/artists/{spotify_artist_id}/related-artists",
                    params={"limit": limit},
                    headers={"Authorization": f"Bearer {token}"}
                )
            
            related_response.raise_for_status()
            related_data = related_response.json()
            related_artists = related_data.get("artists", [])
            
            logger.info(f"Found {len(related_artists)} related artists")
            
            return [
                {
                    "spotify_id": artist["id"],
                    "name": artist["name"],
                    "genres": artist.get("genres", []),
                    "popularity": artist.get("popularity"),
                    "followers": artist.get("followers", {}).get("total", 0),
                    "image": artist.get("images", [{}])[0].get("url") if artist.get("images") else None,
                }
                for artist in related_artists
            ]
            
        except Exception as e:
            logger.error(f"Failed to get related artists for {artist_name}: {e}")
            return []

    async def enrich_artist_with_spotify(
        self,
        artist: Artist,
    ) -> Optional[Dict[str, Any]]:
        """
        Enrich an existing canonical GigCrowd Artist with Spotify metadata.
        
        This adds Spotify external ID and optional enrichment fields
        without modifying the canonical Songkick identity.
        
        Returns Spotify enrichment data or None if enrichment fails.
        """
        logger.info(f"Enriching artist {artist.name} with Spotify data")
        
        try:
            # Search for the artist on Spotify
            search_results = await self.client.search_artist(artist.name)
            artists = search_results.get("artists", {}).get("items", [])
            
            if not artists:
                logger.info(f"No Spotify match found for: {artist.name}")
                return None
            
            # Use the best matching artist (first result)
            spotify_artist = artists[0]
            
            enrichment = {
                "spotify_id": spotify_artist["id"],
                "genres": spotify_artist.get("genres", []),
                "followers": spotify_artist.get("followers", {}).get("total"),
                "popularity": spotify_artist.get("popularity"),
                "image": spotify_artist.get("images", [{}])[0].get("url") if spotify_artist.get("images") else None,
            }
            
            logger.info(f"Successfully enriched {artist.name} with Spotify ID: {enrichment['spotify_id']}")
            
            return enrichment
            
        except Exception as e:
            logger.error(f"Failed to enrich artist {artist.name} with Spotify: {e}")
            return None

    async def search_spotify_artists(
        self,
        query: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Search Spotify for artists.
        
        This is for discovery/matching purposes only.
        Does not create canonical artists.
        """
        logger.info(f"Searching Spotify for: {query}")
        
        try:
            response = await self.client.search_artist(query)
            artists = response.get("artists", {}).get("items", [])
            
            return [
                {
                    "spotify_id": artist["id"],
                    "name": artist["name"],
                    "genres": artist.get("genres", []),
                    "popularity": artist.get("popularity"),
                    "followers": artist.get("followers", {}).get("total", 0),
                    "image": artist.get("images", [{}])[0].get("url") if artist.get("images") else None,
                }
                for artist in artists[:limit]
            ]
            
        except Exception as e:
            logger.error(f"Failed to search Spotify for {query}: {e}")
            return []