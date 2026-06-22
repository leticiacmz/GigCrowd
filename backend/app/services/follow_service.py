from typing import Optional
from app.database.connection import get_database
from app.models.follow import Follow, FollowCreate


class FollowService:
    """Service for managing user follow relationships"""
    
    @staticmethod
    async def follow_user(follower_id: str, follow_data: FollowCreate) -> Follow:
        """Create a follow relationship"""
        db = get_database()
        
        # Check if already following
        existing = await db.follows.find_one({
            "follower_id": follower_id,
            "following_id": follow_data.following_id
        })
        
        if existing:
            raise ValueError("Already following this user")
        
        # Check if trying to follow self
        if follower_id == follow_data.following_id:
            raise ValueError("Cannot follow yourself")
        
        # Create follow relationship
        follow = Follow(
            follower_id=follower_id,
            following_id=follow_data.following_id
        )
        
        result = await db.follows.insert_one(follow.model_dump())
        follow.id = str(result.inserted_id)
        
        # Update follower/following counts
        await db.users.update_one(
            {"_id": follower_id},
            {"$inc": {"following_count": 1}}
        )
        await db.users.update_one(
            {"_id": follow_data.following_id},
            {"$inc": {"followers_count": 1}}
        )
        
        return follow
    
    @staticmethod
    async def unfollow_user(follower_id: str, following_id: str) -> bool:
        """Remove a follow relationship"""
        db = get_database()
        
        # Find and delete follow relationship
        result = await db.follows.delete_one({
            "follower_id": follower_id,
            "following_id": following_id
        })
        
        if result.deleted_count == 0:
            return False
        
        # Update follower/following counts
        await db.users.update_one(
            {"_id": follower_id},
            {"$inc": {"following_count": -1}}
        )
        await db.users.update_one(
            {"_id": following_id},
            {"$inc": {"followers_count": -1}}
        )
        
        return True
    
    @staticmethod
    async def get_following(user_id: str, skip: int = 0, limit: int = 20):
        """Get list of users that a user is following"""
        db = get_database()
        
        follows = await db.follows.find(
            {"follower_id": user_id}
        ).skip(skip).limit(limit).to_list(length=limit)
        
        following_ids = [f["following_id"] for f in follows]
        
        if not following_ids:
            return []
        
        users = await db.users.find(
            {"_id": {"$in": following_ids}}
        ).to_list(length=limit)
        
        return users
    
    @staticmethod
    async def get_followers(user_id: str, skip: int = 0, limit: int = 20):
        """Get list of users that follow a user"""
        db = get_database()
        
        follows = await db.follows.find(
            {"following_id": user_id}
        ).skip(skip).limit(limit).to_list(length=limit)
        
        follower_ids = [f["follower_id"] for f in follows]
        
        if not follower_ids:
            return []
        
        users = await db.users.find(
            {"_id": {"$in": follower_ids}}
        ).to_list(length=limit)
        
        return users
    
    @staticmethod
    async def is_following(follower_id: str, following_id: str) -> bool:
        """Check if a user is following another user"""
        db = get_database()
        
        follow = await db.follows.find_one({
            "follower_id": follower_id,
            "following_id": following_id
        })
        
        return follow is not None
