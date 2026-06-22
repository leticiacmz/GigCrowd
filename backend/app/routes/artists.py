from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from app.database.connection import get_database
from app.auth.dependencies import get_current_active_user

router = APIRouter(prefix="/artists", tags=["artists"])


@router.get("")
async def get_artists(
    skip: int = 0,
    limit: int = 50,
    search: Optional[str] = None
):
    """Get artists with optional search"""
    db = get_database()
    
    query = {}
    if search:
        query["name"] = {"$regex": search, "$options": "i"}
    
    artists = await db.artists.find(query).skip(skip).limit(limit).to_list(length=limit)
    
    # Convert ObjectId to string
    for artist in artists:
        artist["id"] = str(artist["_id"])
        del artist["_id"]
    
    return artists


@router.get("/{artist_id}")
async def get_artist(artist_id: str):
    """Get artist by ID"""
    db = get_database()
    
    artist = await db.artists.find_one({"_id": artist_id})
    
    if not artist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artist not found"
        )
    
    artist["id"] = str(artist["_id"])
    del artist["_id"]
    
    return artist


@router.get("/search/{query}")
async def search_artists(query: str, limit: int = 10):
    """Search artists by name"""
    db = get_database()
    
    artists = await db.artists.find(
        {"name": {"$regex": query, "$options": "i"}}
    ).limit(limit).to_list(length=limit)
    
    # Convert ObjectId to string
    for artist in artists:
        artist["id"] = str(artist["_id"])
        del artist["_id"]
    
    return artists
