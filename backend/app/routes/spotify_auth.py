from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from app.config import settings
from app.ingestion.sources.spotify_source import SpotifySource
from app.auth.dependencies import get_current_active_user
from app.models.user import UserResponse
from app.services.user_service import UserService
from typing import Dict, Any
import httpx
from datetime import datetime, UTC

router = APIRouter(prefix="/auth/spotify", tags=["spotify-auth"])


@router.get("/login")
async def spotify_login():
    """
    Redirect user to Spotify OAuth login page
    """
    if not settings.SPOTIFY_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Spotify client ID not configured"
        )
    
    # Spotify OAuth scopes
    scopes = "user-read-private user-read-email user-top-read user-library-read"
    
    # Construct Spotify authorization URL
    auth_url = (
        f"https://accounts.spotify.com/authorize"
        f"?client_id={settings.SPOTIFY_CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri=http://localhost:8000/auth/spotify/callback"
        f"&scope={scopes}"
    )
    
    return RedirectResponse(url=auth_url)


@router.get("/callback")
async def spotify_callback(code: str):
    """
    Handle Spotify OAuth callback
    """
    if not settings.SPOTIFY_CLIENT_ID or not settings.SPOTIFY_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Spotify credentials not configured"
        )
    
    # Exchange authorization code for access token
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://accounts.spotify.com/api/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": "http://localhost:8000/auth/spotify/callback",
                "client_id": settings.SPOTIFY_CLIENT_ID,
                "client_secret": settings.SPOTIFY_SECRET
            }
        )
        
        if token_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to exchange authorization code"
            )
        
        token_data = token_response.json()
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No access token received"
            )
        
        # Get user's Spotify profile
        profile_response = await client.get(
            "https://api.spotify.com/v1/me",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        
        if profile_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to get Spotify profile"
            )
        
        profile_data = profile_response.json()
        
        # Get user's top artists
        top_artists_response = await client.get(
            "https://api.spotify.com/v1/me/top/artists?limit=50",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        
        top_artists = []
        if top_artists_response.status_code == 200:
            top_artists_data = top_artists_response.json()
            top_artists = top_artists_data.get("items", [])
        
        return {
            "spotify_id": profile_data.get("id"),
            "spotify_display_name": profile_data.get("display_name"),
            "spotify_email": profile_data.get("email"),
            "spotify_country": profile_data.get("country"),
            "spotify_images": profile_data.get("images", []),
            "access_token": access_token,
            "refresh_token": refresh_token,
            "top_artists": [
                {
                    "id": artist.get("id"),
                    "name": artist.get("name"),
                    "genres": artist.get("genres", []),
                    "popularity": artist.get("popularity"),
                    "images": artist.get("images", [])
                }
                for artist in top_artists
            ]
        }


@router.post("/connect")
async def connect_spotify(
    access_token: str,
    refresh_token: str,
    top_artists: list,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Connect Spotify account to user profile and save artist preferences
    """
    from app.database.connection import get_database
    db = get_database()
    
    # Update user with Spotify data
    update_data = {
        "spotify_id": current_user.get("spotify_id"),
        "spotify_access_token": access_token,
        "spotify_refresh_token": refresh_token,
        "spotify_connected_at": datetime.now(UTC),
        "favorite_artists": [artist.get("id") for artist in top_artists],
        "favorite_genres": list(set([
            genre 
            for artist in top_artists 
            for genre in artist.get("genres", [])
        ])),
        "updated_at": datetime.now(UTC)
    }
    
    result = await db.users.update_one(
        {"_id": current_user["_id"]},
        {"$set": update_data}
    )
    
    if result.modified_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to connect Spotify account"
        )
    
    return {
        "message": "Spotify account connected successfully",
        "artists_count": len(top_artists),
        "genres_count": len(update_data["favorite_genres"])
    }


@router.get("/recommendations")
async def get_spotify_recommendations(
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get event recommendations based on user's Spotify artists
    """
    from app.database.connection import get_database
    db = get_database()
    
    # Get user's favorite artists
    user = await db.users.find_one({"_id": current_user["_id"]})
    favorite_artists = user.get("favorite_artists", [])
    
    if not favorite_artists:
        return {
            "message": "No favorite artists found. Connect Spotify to get recommendations.",
            "events": []
        }
    
    # Search for events for each favorite artist
    from app.ingestion.sources.setlistfm_source import SetlistFmSource
    from app.ingestion.sources.ticketmaster_source import TicketMasterSource
    from app.ingestion.sources.bandsintown_source import BandsintownSource
    from app.ingestion.normalizers.event_normalizer import EventNormalizer
    
    all_events = []
    normalizer = EventNormalizer()
    
    # Try Setlist.fm first
    if settings.SETLIST_FM_API_KEY:
        setlistfm = SetlistFmSource(api_key=settings.SETLIST_FM_API_KEY)
        for artist_id in favorite_artists[:5]:  # Limit to 5 artists
            try:
                events = await setlistfm.get_artist_events(artist_id, limit=5)
                for event in events:
                    normalized = normalizer.normalize(event, source="setlistfm")
                    all_events.append(normalized)
            except Exception as e:
                continue
    
    # Try TicketMaster if no results
    if not all_events and settings.TICKETMASTER_CONSUMER_KEY:
        ticketmaster = TicketMasterSource(
            api_key=settings.TICKETMASTER_CONSUMER_KEY,
            api_secret=settings.TICKETMASTER_CONSUMER_SECRET
        )
        for artist_id in favorite_artists[:5]:
            try:
                events = await ticketmaster.search_events(artist_id)
                for event in events:
                    normalized = normalizer.normalize(event, source="ticketmaster")
                    all_events.append(normalized)
            except Exception as e:
                continue
    
    # Try Bandsintown if still no results
    if not all_events:
        bandsintown = BandsintownSource()
        for artist_id in favorite_artists[:5]:
            try:
                events = await bandsintown.get_artist_events(artist_id, limit=5)
                for event in events:
                    normalized = normalizer.normalize(event, source="bandsintown")
                    all_events.append(normalized)
            except Exception as e:
                continue
    
    # Deduplicate and sort by date
    seen_ids = set()
    unique_events = []
    for event in all_events:
        if event.get("_id") not in seen_ids:
            seen_ids.add(event.get("_id"))
            unique_events.append(event)
    
    # Sort by date (upcoming first)
    unique_events.sort(key=lambda x: x.get("date", datetime.now(UTC)), reverse=False)
    
    return {
        "source": "spotify_recommendations",
        "events": unique_events[:20],  # Limit to 20 events
        "total_found": len(unique_events)
    }


@router.get("/disconnect")
async def disconnect_spotify(current_user: dict = Depends(get_current_active_user)):
    """
    Disconnect Spotify account from user profile
    """
    from app.database.connection import get_database
    db = get_database()
    
    # Remove Spotify data from user
    result = await db.users.update_one(
        {"_id": current_user["_id"]},
        {
            "$unset": {
                "spotify_id": "",
                "spotify_access_token": "",
                "spotify_refresh_token": "",
                "spotify_connected_at": ""
            },
            "$set": {"updated_at": datetime.now(UTC)}
        }
    )
    
    if result.modified_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to disconnect Spotify account"
        )
    
    return {"message": "Spotify account disconnected successfully"}
