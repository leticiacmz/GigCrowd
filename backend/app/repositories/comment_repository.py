from datetime import datetime, timezone
from typing import Optional
from bson import ObjectId

from app.repositories.base import BaseRepository


class CommentRepository(BaseRepository):

    def __init__(self, db):
        super().__init__(db, "comments")

    async def create_comment(
        self,
        post_id: str,
        user_id: str,
        content: str,
        parent_comment_id: Optional[str] = None,
    ):
        """Create a new comment or reply"""

        document = {
            "post_id": ObjectId(post_id),
            "user_id": ObjectId(user_id),
            "content": content,
            "parent_comment_id": ObjectId(parent_comment_id) if parent_comment_id else None,
            "created_at": datetime.now(timezone.utc),
            "updated_at": None,
        }

        result = await self.insert_one(document)
        document["_id"] = result.inserted_id

        # Increment comments count on the post
        db = self.collection.database
        await db.community_posts.update_one(
            {"_id": ObjectId(post_id)},
            {"$inc": {"comments_count": 1}}
        )

        return document

    async def get_comments_by_post(
        self,
        post_id: str,
        limit: int = 50,
        skip: int = 0,
    ):
        """Get top-level comments for a post"""

        cursor = self.collection.find({
            "post_id": ObjectId(post_id),
            "parent_comment_id": None,
        }).sort("created_at", -1).skip(skip).limit(limit)

        return await cursor.to_list(length=limit)

    async def get_replies(
        self,
        parent_comment_id: str,
        limit: int = 50,
        skip: int = 0,
    ):
        """Get replies for a specific comment"""

        cursor = self.collection.find({
            "parent_comment_id": ObjectId(parent_comment_id),
        }).sort("created_at", 1).skip(skip).limit(limit)

        return await cursor.to_list(length=limit)

    async def get_comment_by_id(
        self,
        comment_id: str,
    ):
        """Get a specific comment by ID"""

        try:
            object_id = ObjectId(comment_id)
        except Exception:
            return None

        return await self.find_one({"_id": object_id})

    async def update_comment(
        self,
        comment_id: str,
        user_id: str,
        content: str,
    ):
        """Update a comment (only by author)"""

        try:
            object_id = ObjectId(comment_id)
            user_oid = ObjectId(user_id)
        except Exception:
            return None

        result = await self.collection.find_one_and_update(
            {"_id": object_id, "user_id": user_oid},
            {
                "$set": {
                    "content": content,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            return_document=True,
        )

        return result

    async def delete_comment(
        self,
        comment_id: str,
        user_id: str,
    ):
        """Delete a comment (only by author)"""

        try:
            object_id = ObjectId(comment_id)
            user_oid = ObjectId(user_id)
        except Exception:
            return False

        # Get the comment first to check if it has replies
        comment = await self.find_one({"_id": object_id, "user_id": user_oid})
        if not comment:
            return False

        # Delete the comment
        result = await self.collection.delete_one({
            "_id": object_id,
            "user_id": user_oid,
        })

        if result.deleted_count == 0:
            return False

        # Decrement comments count on the post
        db = self.collection.database
        await db.community_posts.update_one(
            {"_id": comment["post_id"]},
            {"$inc": {"comments_count": -1}}
        )

        return True
