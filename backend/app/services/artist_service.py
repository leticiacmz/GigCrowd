from app.database.connection import get_database
from app.models.artist import ArtistCreate, ArtistInDB, ArtistUpdate
from datetime import datetime, UTC
from typing import Optional, List


class ArtistService:
    @staticmethod
    async def create_artist(artist_data: ArtistCreate) -> ArtistInDB:
        """Create a new artist"""
        db = await get_database()
        
        # Check if artist already exists
        existing_artist = await db.artists.find_one({"name": artist_data.name})
        if existing_artist:
            raise ValueError("Artist already exists")
        
        artist_dict = artist_data.model_dump()
        artist_dict["followers_count"] = 0
        artist_dict["events_count"] = 0
        artist_dict["created_at"] = datetime.now(UTC)
        artist_dict["updated_at"] = datetime.now(UTC)
        
        result = await db.artists.insert_one(artist_dict)
        artist_dict["_id"] = str(result.inserted_id)
        
        return ArtistInDB(**artist_dict)
    
    @staticmethod
    async def get_artist_by_id(artist_id: str) -> Optional[ArtistInDB]:
        """Get an artist by ID"""
        db = await get_database()
        artist = await db.artists.find_one({"_id": artist_id})
        if artist:
            return ArtistInDB(**artist)
        return None
    
    @staticmethod
    async def get_artist_by_name(name: str) -> Optional[ArtistInDB]:
        """Get an artist by name"""
        db = await get_database()
        artist = await db.artists.find_one({"name": name})
        if artist:
            return ArtistInDB(**artist)
        return None
    
    @staticmethod
    async def get_artists(skip: int = 0, limit: int = 50) -> List[ArtistInDB]:
        """Get all artists"""
        db = await get_database()
        cursor = db.artists.find().sort("name", 1).skip(skip).limit(limit)
        artists = await cursor.to_list(length=limit)
        
        return [ArtistInDB(**artist) for artist in artists]
    
    @staticmethod
    async def update_artist(artist_id: str, artist_data: ArtistUpdate) -> Optional[ArtistInDB]:
        """Update an artist"""
        db = await get_database()
        
        update_dict = artist_data.model_dump(exclude_unset=True)
        if not update_dict:
            return await ArtistService.get_artist_by_id(artist_id)
        
        update_dict["updated_at"] = datetime.now(UTC)
        
        await db.artists.update_one(
            {"_id": artist_id},
            {"$set": update_dict}
        )
        
        return await ArtistService.get_artist_by_id(artist_id)
    
    @staticmethod
    async def search_artists(query: str, skip: int = 0, limit: int = 50) -> List[ArtistInDB]:
        """Search artists by name"""
        db = await get_database()
        cursor = db.artists.find(
            {"name": {"$regex": query, "$options": "i"}}
        ).sort("name", 1).skip(skip).limit(limit)
        artists = await cursor.to_list(length=limit)
        
        return [ArtistInDB(**artist) for artist in artists]
