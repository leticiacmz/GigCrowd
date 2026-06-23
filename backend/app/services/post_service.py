from app.database.connection import get_database
from app.models.post import PostCreate, PostInDB, PostUpdate
from datetime import datetime, UTC
from typing import Optional, List


class PostService:
    @staticmethod
    async def create_post(user_id: str, post_data: PostCreate) -> PostInDB:
        """Create a new post"""
        db = await get_database()
        
        post_dict = post_data.model_dump()
        post_dict["user_id"] = user_id
        post_dict["likes_count"] = 0
        post_dict["comments_count"] = 0
        post_dict["created_at"] = datetime.now(UTC)
        post_dict["updated_at"] = datetime.now(UTC)
        
        result = await db.posts.insert_one(post_dict)
        post_dict["_id"] = str(result.inserted_id)
        
        return PostInDB(**post_dict)
    
    @staticmethod
    async def get_post_by_id(post_id: str) -> Optional[PostInDB]:
        """Get a post by ID"""
        db = await get_database()
        post = await db.posts.find_one({"_id": post_id})
        if post:
            return PostInDB(**post)
        return None
    
    @staticmethod
    async def get_posts(
        skip: int = 0,
        limit: int = 50,
        user_id: Optional[str] = None,
        event_id: Optional[str] = None
    ) -> List[PostInDB]:
        """Get posts with optional filters"""
        db = await get_database()
        
        query = {}
        if user_id:
            query["user_id"] = user_id
        if event_id:
            query["event_id"] = event_id
        
        cursor = db.posts.find(query).sort("created_at", -1).skip(skip).limit(limit)
        posts = await cursor.to_list(length=limit)
        
        return [PostInDB(**post) for post in posts]
    
    @staticmethod
    async def update_post(post_id: str, user_id: str, post_data: PostUpdate) -> Optional[PostInDB]:
        """Update a post"""
        db = await get_database()
        
        # Check if post belongs to user
        post = await db.posts.find_one({"_id": post_id, "user_id": user_id})
        if not post:
            raise ValueError("Post not found or not authorized")
        
        update_dict = post_data.model_dump(exclude_unset=True)
        if not update_dict:
            return await PostService.get_post_by_id(post_id)
        
        update_dict["updated_at"] = datetime.now(UTC)
        
        await db.posts.update_one(
            {"_id": post_id},
            {"$set": update_dict}
        )
        
        return await PostService.get_post_by_id(post_id)
    
    @staticmethod
    async def delete_post(post_id: str, user_id: str) -> bool:
        """Delete a post"""
        db = await get_database()
        
        result = await db.posts.delete_one({
            "_id": post_id,
            "user_id": user_id
        })
        
        return result.deleted_count > 0
    
    @staticmethod
    async def increment_likes_count(post_id: str) -> None:
        """Increment the likes count for a post"""
        db = await get_database()
        await db.posts.update_one(
            {"_id": post_id},
            {"$inc": {"likes_count": 1}}
        )
    
    @staticmethod
    async def decrement_likes_count(post_id: str) -> None:
        """Decrement the likes count for a post"""
        db = await get_database()
        await db.posts.update_one(
            {"_id": post_id},
            {"$inc": {"likes_count": -1}}
        )
    
    @staticmethod
    async def increment_comments_count(post_id: str) -> None:
        """Increment the comments count for a post"""
        db = await get_database()
        await db.posts.update_one(
            {"_id": post_id},
            {"$inc": {"comments_count": 1}}
        )
