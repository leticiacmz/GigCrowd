from datetime import datetime, timezone
from typing import Optional, List
from bson import ObjectId

from app.repositories.base import BaseRepository


class CommunityPostRepository(BaseRepository):

    def __init__(self, db):
        super().__init__(db, "community_posts")

    async def create_post(
        self,
        artist_slug: str,
        user_id: str,
        content: str,
        image_url: Optional[str] = None,
    ):
        """Create a new community post for an artist"""

        document = {
            "artist_slug": artist_slug,
            "user_id": ObjectId(user_id),
            "content": content,
            "image_url": image_url,
            "likes_count": 0,
            "comments_count": 0,
            "created_at": datetime.now(timezone.utc),
            "updated_at": None,
        }

        result = await self.insert_one(document)
        document["_id"] = result.inserted_id
        return document

    async def get_posts_by_artist(
        self,
        artist_slug: str,
        limit: int = 50,
        skip: int = 0,
    ):
        """Get community posts for a specific artist"""
        
        cursor = self.collection.find({
            "artist_slug": artist_slug
        }).sort("created_at", -1).skip(skip).limit(limit)

        return await cursor.to_list(length=limit)

    async def get_posts_by_user(
        self,
        user_id: str,
        limit: int = 50,
        skip: int = 0,
    ):
        """Get community posts by a specific user"""

        try:
            user_id = ObjectId(user_id)
        except:
            return []

        cursor = self.collection.find({
            "user_id": user_id
        }).sort("created_at", -1).skip(skip).limit(limit)

        return await cursor.to_list(length=limit)

    async def get_all_posts(
        self,
        limit: int = 50,
        skip: int = 0,
    ):
        """Get all community posts (for community feed)"""

        cursor = self.collection.find({}).sort("created_at", -1).skip(skip).limit(limit)

        return await cursor.to_list(length=limit)

    async def get_post_by_id(
        self,
        post_id: str,
    ):
        """Get a specific post by ID"""
        
        try:
            object_id = ObjectId(post_id)
        except:
            return None

        return await self.find_one({"_id": object_id})

    async def delete_post(
        self,
        post_id: str,
        user_id: str,
    ):
        """Delete a post (only by the author)"""
        
        try:
            object_id = ObjectId(post_id)
            user_id = ObjectId(user_id)
        except:
            return False

        result = await self.collection.delete_one({
            "_id": object_id,
            "user_id": user_id
        })

        return result.deleted_count > 0

    async def increment_likes(
        self,
        post_id: str,
    ):
        """Increment likes count for a post"""
        
        try:
            object_id = ObjectId(post_id)
        except:
            return False

        result = await self.collection.update_one(
            {"_id": object_id},
            {"$inc": {"likes_count": 1}}
        )

        return result.modified_count > 0

    async def decrement_likes(
        self,
        post_id: str,
    ):
        """Decrement likes count for a post"""
        
        try:
            object_id = ObjectId(post_id)
        except:
            return False

        result = await self.collection.update_one(
            {"_id": object_id},
            {"$inc": {"likes_count": -1}}
        )

        return result.modified_count > 0

    async def increment_comments(
        self,
        post_id: str,
    ):
        """Increment comments count for a post"""
        
        try:
            object_id = ObjectId(post_id)
        except:
            return False

        result = await self.collection.update_one(
            {"_id": object_id},
            {"$inc": {"comments_count": 1}}
        )

        return result.modified_count > 0

    async def decrement_comments(
        self,
        post_id: str,
    ):
        """Decrement comments count for a post"""

        try:
            object_id = ObjectId(post_id)
        except:
            return False

        result = await self.collection.update_one(
            {"_id": object_id},
            {"$inc": {"comments_count": -1}}
        )

        return result.modified_count > 0

    async def like_post(
        self,
        post_id: str,
        user_id: str,
    ):
        """Like a post (prevents duplicate likes)"""

        try:
            post_oid = ObjectId(post_id)
            user_oid = ObjectId(user_id)
        except:
            return False

        # Check if user already liked this post
        existing = await self.db.post_likes.find_one({
            "post_id": post_oid,
            "user_id": user_oid
        })

        if existing:
            return False  # Already liked

        # Create like record
        await self.db.post_likes.insert_one({
            "post_id": post_oid,
            "user_id": user_oid,
            "created_at": datetime.now(timezone.utc)
        })

        # Increment likes count
        result = await self.collection.update_one(
            {"_id": post_oid},
            {"$inc": {"likes_count": 1}}
        )

        return result.modified_count > 0

    async def unlike_post(
        self,
        post_id: str,
        user_id: str,
    ):
        """Unlike a post"""

        try:
            post_oid = ObjectId(post_id)
            user_oid = ObjectId(user_id)
        except:
            return False

        # Remove like record
        result = await self.db.post_likes.delete_one({
            "post_id": post_oid,
            "user_id": user_oid
        })

        if result.deleted_count == 0:
            return False  # Wasn't liked

        # Decrement likes count
        await self.collection.update_one(
            {"_id": post_oid},
            {"$inc": {"likes_count": -1}}
        )

        return True

    async def get_like_status(
        self,
        post_id: str,
        user_id: str,
    ):
        """Check if a user has liked a post"""

        try:
            post_oid = ObjectId(post_id)
            user_oid = ObjectId(user_id)
        except:
            return False

        existing = await self.db.post_likes.find_one({
            "post_id": post_oid,
            "user_id": user_oid
        })

        return existing is not None