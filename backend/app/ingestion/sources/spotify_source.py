from typing import List, Dict, Any, Optional
import httpx
from datetime import datetime


class SpotifySource:
    """Source for fetching artist data from Spotify API"""
    
    BASE_URL = "https://api.spotify.com/v1"
    
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = None
    
    async def get_access_token(self) -> str:
        """Get access token from Spotify"""
        if self.access_token:
            return self.access_token
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://accounts.spotify.com/api/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            
            if response.status_code != 200:
                raise Exception("Failed to get Spotify access token")
            
            data = response.json()
            self.access_token = data.get("access_token")
            return self.access_token
    
    async def search_artists(self, query: str) -> List[Dict[str, Any]]:
        """Search for artists by name"""
        token = await self.get_access_token()
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/search",
                params={"q": query, "type": "artist", "limit": 10},
                headers={"Authorization": f"Bearer {token}"}
            )
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            artists = data.get("artists", {}).get("items", [])
            
            return [
                {
                    "id": artist.get("id"),
                    "name": artist.get("name"),
                    "image_url": artist.get("images", [{}])[0].get("url") if artist.get("images") else None,
                    "genres": artist.get("genres", []),
                    "popularity": artist.get("popularity"),
                    "followers": artist.get("followers", {}).get("total", 0)
                }
                for artist in artists
            ]
    
    async def get_artist(self, artist_id: str) -> Optional[Dict[str, Any]]:
        """Get artist details by ID"""
        token = await self.get_access_token()
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/artists/{artist_id}",
                headers={"Authorization": f"Bearer {token}"}
            )
            
            if response.status_code != 200:
                return None
            
            artist = response.json()
            return {
                "id": artist.get("id"),
                "name": artist.get("name"),
                "image_url": artist.get("images", [{}])[0].get("url") if artist.get("images") else None,
                "genres": artist.get("genres", []),
                "popularity": artist.get("popularity"),
                "followers": artist.get("followers", {}).get("total", 0)
            }
    
    async def get_artist_events(self, artist_id: str) -> List[Dict[str, Any]]:
        """Spotify doesn't provide event data directly, this is a placeholder"""
        # Spotify doesn't have a concerts/events API
        # This would need to be implemented using a different source
        return []
    
    async def get_user_top_artists(self, access_token: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get user's top artists from Spotify (requires user token)"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/me/top/artists",
                params={"limit": limit},
                headers={"Authorization": f"Bearer {access_token}"}
            )
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            artists = data.get("items", [])
            
            return [
                {
                    "id": artist.get("id"),
                    "name": artist.get("name"),
                    "image_url": artist.get("images", [{}])[0].get("url") if artist.get("images") else None,
                    "genres": artist.get("genres", []),
                    "popularity": artist.get("popularity")
                }
                for artist in artists
            ]
