from datetime import datetime, UTC
from typing import List, Dict
from app.database.connection import get_database


class FeedAlgorithm:
    """Feed algorithm for generating personalized activity feeds"""
    
    @staticmethod
    async def generate_feed(user_id: str, limit: int = 50) -> List[Dict]:
        """
        Generate a personalized feed for a user based on:
        - Users they follow
        - Recent activities
        - Engagement score
        """
        db = await get_database()
        
        # Get users that the current user follows
        follows = await db.follows.find({"follower_id": user_id}).to_list(length=None)
        following_ids = [follow["following_id"] for follow in follows]
        
        if not following_ids:
            return []
        
        # Get activities from followed users
        activities = await db.activities.find(
            {"user_id": {"$in": following_ids}}
        ).sort("created_at", -1).to_list(length=limit * 2)  # Get more for ranking
        
        # Calculate engagement scores and rank
        ranked_activities = []
        for activity in activities:
            score = FeedAlgorithm._calculate_engagement_score(activity)
            ranked_activities.append({
                "activity": activity,
                "score": score
            })
        
        # Sort by score and recency
        ranked_activities.sort(
            key=lambda x: (x["score"], x["activity"]["created_at"]),
            reverse=True
        )
        
        # Return top activities
        return [item["activity"] for item in ranked_activities[:limit]]
    
    @staticmethod
    def _calculate_engagement_score(activity: Dict) -> float:
        """
        Calculate engagement score for an activity
        Factors:
        - Recency (more recent = higher score)
        - Activity type (some activities are more engaging)
        """
        created_at = activity["created_at"]
        activity_type = activity["activity_type"]
        
        # Recency score (decays over time)
        now = datetime.now(UTC)
        days_old = (now - created_at).total_seconds() / 86400
        recency_score = max(0, 1 - (days_old / 30))  # 0 to 1, decays over 30 days
        
        # Activity type weights
        type_weights = {
            "create_post": 1.0,
            "attend_event": 0.9,
            "follow": 0.7,
            "like_post": 0.5,
            "comment_post": 0.6
        }
        
        type_weight = type_weights.get(activity_type, 0.5)
        
        # Combined score
        return recency_score * type_weight
    
    @staticmethod
    async def get_trending_events(limit: int = 20) -> List[Dict]:
        """Get trending events based on attendance and engagement"""
        db = await get_database()
        
        # Get events sorted by attendance counts
        events = await db.events.find(
            {"status": "upcoming"}
        ).sort([
            ("going_count", -1),
            ("maybe_count", -1),
            ("created_at", -1)
        ]).to_list(length=limit)
        
        return events
    
    @staticmethod
    async def get_recommended_events(user_id: str, limit: int = 20) -> List[Dict]:
        """
        Recommend events based on:
        - User's location
        - Artists user follows (if we had artist follows)
        - Similar users' attendance
        """
        db = await get_database()
        
        # Get user's location
        user = await db.users.find_one({"_id": user_id})
        if not user:
            return []
        
        user_location = user.get("location")
        
        # Get events near user's location
        query = {"status": "upcoming"}
        if user_location:
            query["location"] = {"$regex": user_location, "$options": "i"}
        
        events = await db.events.find(query).sort([
            ("date", 1),
            ("going_count", -1)
        ]).to_list(length=limit)
        
        return events
