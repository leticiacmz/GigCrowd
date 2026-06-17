from app.database.connection import get_database
from app.models.follow import FollowCreate, FollowInDB
from app.services.user_service import UserService
from datetime import datetime
from typing import Optional, List


class FollowService:
    @staticmethod
    async def follow_user(follower_id: str, follow_data: FollowCreate) -> FollowInDB:
        """Follow a user"""
        db = await get_database()
        
        # Check if already following
        existing_follow = await db.follows.find_one({
            "follower_id": follower_id,
            "following_id": follow_data.following_id
        })
        if existing_follow:
            raise ValueError("Already following this user")
        
        # Cannot follow yourself
        if follower_id == follow_data.following_id:
            raise ValueError("Cannot follow yourself")
        
        # Check if following user exists
        following_user = await UserService.get_user_by_id(follow_data.following_id)
        if not following_user:
            raise ValueError("User to follow not found")
        
        follow_dict = follow_data.model_dump()
        follow_dict["follower_id"] = follower_id
        follow_dict["created_at"] = datetime.utcnow()
        
        result = await db.follows.insert_one(follow_dict)
        follow_dict["_id"] = str(result.inserted_id)
        
        # Update follower counts
        await UserService.increment_followers_count(follow_data.following_id)
        await UserService.increment_following_count(follower_id)
        
        return FollowInDB(**follow_dict)
    
    @staticmethod
    async def unfollow_user(follower_id: str, following_id: str) -> bool:
        """Unfollow a user"""
        db = await get_database()
        
        result = await db.follows.delete_one({
            "follower_id": follower_id,
            "following_id": following_id
        })
        
        if result.deleted_count > 0:
            # Update follower counts
            await UserService.decrement_followers_count(following_id)
            await UserService.decrement_following_count(follower_id)
            return True
        
        return False
    
    @staticmethod
    async def get_followers(user_id: str, skip: int = 0, limit: int = 50) -> List[dict]:
        """Get followers of a user"""
        db = await get_database()
        cursor = db.follows.find({"following_id": user_id}).skip(skip).limit(limit)
        follows = await cursor.to_list(length=limit)
        
        # Get user details for each follower
        follower_ids = [follow["follower_id"] for follow in follows]
        followers = await db.users.find({"_id": {"$in": follower_ids}}).to_list(length=limit)
        
        return followers
    
    @staticmethod
    async def get_following(user_id: str, skip: int = 0, limit: int = 50) -> List[dict]:
        """Get users that a user is following"""
        db = await get_database()
        cursor = db.follows.find({"follower_id": user_id}).skip(skip).limit(limit)
        follows = await cursor.to_list(length=limit)
        
        # Get user details for each following
        following_ids = [follow["following_id"] for follow in follows]
        following = await db.users.find({"_id": {"$in": following_ids}}).to_list(length=limit)
        
        return following
    
    @staticmethod
    async def is_following(follower_id: str, following_id: str) -> bool:
        """Check if a user is following another user"""
        db = await get_database()
        follow = await db.follows.find_one({
            "follower_id": follower_id,
            "following_id": following_id
        })
        return follow is not None
