from datetime import datetime, timezone
from typing import Optional, List
from bson import ObjectId

from app.repositories.base import BaseRepository


class FeedActivityRepository(BaseRepository):

    def __init__(self, db):
        super().__init__(db, "feed_activities")

    async def create_activity(
        self,
        actor_id: str,
        actor_username: str,
        actor_avatar_url: Optional[str],
        activity_type: str,
        target_user_id: Optional[str] = None,
        target_user_username: Optional[str] = None,
        target_artist_slug: Optional[str] = None,
        target_artist_name: Optional[str] = None,
        target_event_id: Optional[str] = None,
        target_event_title: Optional[str] = None,
        target_post_id: Optional[str] = None,
        target_post_content: Optional[str] = None,
        metadata: Optional[dict] = None,
    ):
        """Create a new feed activity"""
        
        document = {
            "actor_id": ObjectId(actor_id),
            "actor_username": actor_username,
            "actor_avatar_url": actor_avatar_url,
            "activity_type": activity_type,
            "target_user_id": ObjectId(target_user_id) if target_user_id else None,
            "target_user_username": target_user_username,
            "target_artist_slug": target_artist_slug,
            "target_artist_name": target_artist_name,
            "target_event_id": target_event_id,
            "target_event_title": target_event_title,
            "target_post_id": target_post_id,
            "target_post_content": target_post_content,
            "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc),
        }

        return await self.insert_one(document)

    async def get_feed_for_user(
        self,
        user_id: str,
        limit: int = 50,
        skip: int = 0,
    ):
        """Get feed activities for a user (based on who they follow)"""
        
        try:
            user_id = ObjectId(user_id)
        except:
            return []

        # Get users that the current user follows
        from app.repositories.follow_repository import FollowRepository
        follow_repo = FollowRepository(self.db)
        
        following = await follow_repo.get_following(user_id, limit=1000, skip=0)
        followed_user_ids = [rel["following_id"] for rel in following]
        
        # Get artists that the current user follows
        from app.repositories.artist_follow_repository import ArtistFollowRepository
        artist_follow_repo = ArtistFollowRepository(self.db)
        
        followed_artists = await artist_follow_repo.get_following_artists(user_id, limit=1000, skip=0)
        followed_artist_slugs = [rel["artist_slug"] for rel in followed_artists]
        
        # Build query for activities from followed users OR about followed artists
        query = {
            "$or": [
                {"actor_id": {"$in": followed_user_ids}},
                {"target_artist_slug": {"$in": followed_artist_slugs}},
            ]
        }
        
        cursor = self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
        
        return await cursor.to_list(length=limit)

    async def get_activities_by_user(
        self,
        user_id: str,
        limit: int = 50,
        skip: int = 0,
    ):
        """Get activities performed by a specific user"""
        
        try:
            user_id = ObjectId(user_id)
        except:
            return []

        cursor = self.collection.find({
            "actor_id": user_id
        }).sort("created_at", -1).skip(skip).limit(limit)

        return await cursor.to_list(length=limit)

    async def get_activities_by_artist(
        self,
        artist_slug: str,
        limit: int = 50,
        skip: int = 0,
    ):
        """Get activities related to a specific artist"""
        
        cursor = self.collection.find({
            "target_artist_slug": artist_slug
        }).sort("created_at", -1).skip(skip).limit(limit)

        return await cursor.to_list(length=limit)