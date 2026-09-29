from fastapi import APIRouter, Depends
from bson import ObjectId
from app.services.activity_service import ActivityService
from app.auth.dependencies import get_current_active_user

router = APIRouter(prefix="/feed", tags=["feed"])


@router.get("")
async def get_feed(
    skip: int = 0,
    limit: int = 50,
    activity_type: str = None,
    current_user: dict = Depends(get_current_active_user)
):
    """Get activity feed from followed users"""
    activities = await ActivityService.get_followed_activities(
        current_user["_id"],
        skip,
        limit,
        activity_type=activity_type,
    )
    
    # Enrich activities with related data
    from app.database.connection import get_database
    db = get_database()
    
    enriched_activities = []
    for activity in activities:
        enriched_activity = {
            "id": str(activity["_id"]),
            "user": {
                "id": str(activity["user"]["id"]),
                "username": activity["user"]["username"],
                "avatar_url": activity["user"].get("avatar_url"),
            },
            "activity_type": activity["activity_type"],
            "target_id": activity.get("target_id"),
            "target_type": activity.get("target_type"),
            "metadata": activity.get("metadata"),
            "created_at": activity["created_at"],
        }

        # Add related object data based on target type
        if activity.get("target_id") and activity.get("target_type"):
            if activity["target_type"] == "event":
                try:
                    event = await db.events.find_one({"_id": ObjectId(activity["target_id"])})
                except Exception:
                    event = None
                if event:
                    enriched_activity["event"] = {
                        "id": str(event["_id"]),
                        "title": event["title"],
                        "date": event["date"],
                        "location": event["location"],
                        "image_url": event.get("image_url"),
                    }
            elif activity["target_type"] == "post":
                try:
                    post = await db.posts.find_one({"_id": ObjectId(activity["target_id"])})
                except Exception:
                    post = None
                if post:
                    enriched_activity["post"] = {
                        "id": str(post["_id"]),
                        "content": post.get("content"),
                        "media_url": post.get("media_url"),
                        "media_type": post.get("media_type"),
                        "created_at": post["created_at"],
                    }

        enriched_activities.append(enriched_activity)
    
    return enriched_activities
