from fastapi import APIRouter, Depends, HTTPException, status
from app.models.user import UserResponse
from app.services.user_service import UserService
from app.auth.dependencies import get_current_active_user
from typing import List, Dict, Any
from datetime import datetime, UTC

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me/stats", response_model=Dict[str, Any])
async def get_user_stats(current_user: dict = Depends(get_current_active_user)):
    """
    Get comprehensive user statistics including:
    - Shows attended
    - Artists seen
    - Upcoming events
    - Recent activity
    """
    from app.database.connection import get_database
    db = get_database()
    
    # Get show logs (events attended)
    show_logs = await db.show_logs.find({"user_id": current_user["_id"]}).to_list(length=None)
    
    # Count shows by status
    going_count = sum(1 for log in show_logs if log.get("status") == "going")
    maybe_count = sum(1 for log in show_logs if log.get("status") == "maybe")
    went_count = sum(1 for log in show_logs if log.get("status") == "went")
    
    # Get unique artists seen
    artists_seen = set()
    for log in show_logs:
        event = await db.events.find_one({"_id": log.get("event_id")})
        if event:
            artists_seen.add(event.get("artist_id"))
    
    # Get upcoming events
    upcoming_events = await db.events.find({
        "_id": {"$in": [log.get("event_id") for log in show_logs if log.get("status") in ["going", "maybe"]]},
        "date": {"$gte": datetime.now(UTC)}
    }).to_list(length=None)
    
    # Get recent posts
    recent_posts = await db.posts.find({"user_id": current_user["_id"]}).sort("created_at", -1).limit(5).to_list(length=None)
    
    return {
        "shows_attended": went_count,
        "shows_going": going_count,
        "shows_maybe": maybe_count,
        "artists_seen": len(artists_seen),
        "upcoming_events": len(upcoming_events),
        "total_posts": len(await db.posts.find({"user_id": current_user["_id"]}).to_list(length=None)),
        "recent_activity": {
            "upcoming_events": upcoming_events,
            "recent_posts": recent_posts
        }
    }


@router.get("/me/history", response_model=List[Dict[str, Any]])
async def get_user_event_history(
    skip: int = 0,
    limit: int = 20,
    status: str = None,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get user's event history with optional filter by status (going, maybe, went)
    """
    from app.database.connection import get_database
    db = get_database()
    
    query = {"user_id": current_user["_id"]}
    if status:
        query["status"] = status
    
    show_logs = await db.show_logs.find(query).sort("created_at", -1).skip(skip).limit(limit).to_list(length=None)
    
    # Enrich with event details
    history = []
    for log in show_logs:
        event = await db.events.find_one({"_id": log.get("event_id")})
        if event:
            history.append({
                "event": event,
                "status": log.get("status"),
                "notes": log.get("notes"),
                "attended_at": log.get("created_at")
            })
    
    return history


@router.put("/me/preferences")
async def update_user_preferences(
    favorite_genres: List[str] = None,
    favorite_artists: List[str] = None,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Update user preferences (favorite genres and artists)
    """
    from app.database.connection import get_database
    db = get_database()
    
    update_data = {"updated_at": datetime.now(UTC)}
    if favorite_genres is not None:
        update_data["favorite_genres"] = favorite_genres
    if favorite_artists is not None:
        update_data["favorite_artists"] = favorite_artists
    
    result = await db.users.update_one(
        {"_id": current_user["_id"]},
        {"$set": update_data}
    )
    
    if result.modified_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to update preferences"
        )
    
    return {"message": "Preferences updated successfully"}


@router.get("/me/artists")
async def get_user_artists(current_user: dict = Depends(get_current_active_user)):
    """
    Get all artists the user has seen or plans to see
    """
    from app.database.connection import get_database
    db = get_database()
    
    # Get all show logs
    show_logs = await db.show_logs.find({"user_id": current_user["_id"]}).to_list(length=None)
    
    # Get unique artists
    artist_ids = set()
    for log in show_logs:
        event = await db.events.find_one({"_id": log.get("event_id")})
        if event:
            artist_ids.add(event.get("artist_id"))
    
    # Get artist details
    artists = []
    for artist_id in artist_ids:
        # For now, return basic info. Could be enhanced with artist API
        events_with_artist = await db.events.find({"artist_id": artist_id}).to_list(length=None)
        artists.append({
            "artist_id": artist_id,
            "events_count": len(events_with_artist),
            "first_seen": min([e.get("date") for e in events_with_artist if e.get("date")], default=None)
        })
    
    return {"artists": artists}
