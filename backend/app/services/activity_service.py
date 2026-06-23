from app.database.connection import get_database
from app.models.activity import ActivityCreate, ActivityInDB
from datetime import datetime, UTC
from typing import Optional, List


class ActivityService:
    @staticmethod
    async def create_activity(user_id: str, activity_data: ActivityCreate) -> ActivityInDB:
        """Create a new activity"""
        db = await get_database()
        
        activity_dict = activity_data.model_dump()
        activity_dict["user_id"] = user_id
        activity_dict["created_at"] = datetime.now(UTC)
        
        result = await db.activities.insert_one(activity_dict)
        activity_dict["_id"] = str(result.inserted_id)
        
        return ActivityInDB(**activity_dict)
    
    @staticmethod
    async def get_user_activities(user_id: str, skip: int = 0, limit: int = 50) -> List[ActivityInDB]:
        """Get activities for a user"""
        db = await get_database()
        cursor = db.activities.find({"user_id": user_id}).sort("created_at", -1).skip(skip).limit(limit)
        activities = await cursor.to_list(length=limit)
        
        return [ActivityInDB(**activity) for activity in activities]
    
    @staticmethod
    async def get_followed_activities(user_id: str, skip: int = 0, limit: int = 100) -> List[dict]:
        """Get activities from users that the current user follows"""
        db = await get_database()
        
        # Get list of followed users
        follows = await db.follows.find({"follower_id": user_id}).to_list(length=None)
        following_ids = [follow["following_id"] for follow in follows]
        
        if not following_ids:
            return []
        
        # Get activities from followed users
        cursor = db.activities.find(
            {"user_id": {"$in": following_ids}}
        ).sort("created_at", -1).skip(skip).limit(limit)
        activities = await cursor.to_list(length=limit)
        
        # Enrich with user information
        for activity in activities:
            user = await db.users.find_one({"_id": activity["user_id"]})
            activity["user"] = {
                "id": user["_id"],
                "username": user["username"],
                "avatar_url": user.get("avatar_url")
            }
        
        return activities
