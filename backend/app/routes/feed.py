from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.auth.dependencies import get_current_active_user
from app.database.connection import get_database
from app.domain.feed_activity import ActivityType
from app.repositories.feed_activity_repository import FeedActivityRepository
from app.repositories.follow_repository import FollowRepository
from app.repositories.user_repository import UserRepository
from app.schemas.feed_activity import FeedPage
from app.services.feed_activity_service import FeedActivityService

router = APIRouter(prefix="/feed", tags=["feed"])


def get_feed_activity_service() -> FeedActivityService:

    db = get_database()

    return FeedActivityService(
        repository=FeedActivityRepository(db),
        follow_repository=FollowRepository(db),
        user_repository=UserRepository(db),
    )


@router.get("", response_model=FeedPage)
async def get_feed(
    limit: int = Query(default=20, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
    activity_type: Optional[list[ActivityType]] = Query(default=None),
    current_user: dict = Depends(get_current_active_user),
    service: FeedActivityService = Depends(get_feed_activity_service),
):
    """Chronological activity feed of the current user and the users they follow"""

    return await service.get_user_feed(
        user_id=current_user["_id"],
        limit=limit,
        skip=skip,
        activity_types=activity_type,
    )


@router.get("/me", response_model=FeedPage)
async def get_own_feed(
    limit: int = Query(default=20, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
    current_user: dict = Depends(get_current_active_user),
    service: FeedActivityService = Depends(get_feed_activity_service),
):
    """Chronological activity feed of the current user only"""

    return await service.get_actor_feed(
        actor_id=current_user["_id"],
        limit=limit,
        skip=skip,
    )
