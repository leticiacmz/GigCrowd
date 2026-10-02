"""Unified feed timeline.

The feed is a single stream of activities. `category` narrows that same
stream, it does not switch to a different dataset, which is what keeps the
"one timeline, one filter" contract honest.
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.dependencies import get_current_active_user
from app.services.activity_service import FEED_CATEGORIES, ActivityService

router = APIRouter(prefix="/feed", tags=["feed"])


@router.get("")
async def get_feed(
    skip: int = 0,
    limit: int = 20,
    category: str = Query(
        default="all",
        description=(
            "Filter applied to the unified timeline. One of: "
            + ", ".join(sorted(FEED_CATEGORIES))
        ),
    ),
    current_user: dict = Depends(get_current_active_user),
):
    """Get the unified activity feed for the current user."""
    category = category.strip().lower()

    if category not in FEED_CATEGORIES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unknown feed category '{category}'. "
                f"Expected one of: {', '.join(sorted(FEED_CATEGORIES))}"
            ),
        )

    activities = await ActivityService.get_feed_activities(
        current_user["_id"],
        skip=skip,
        limit=limit,
        category=category,
    )

    return {
        "activities": activities,
        "category": category,
        "skip": skip,
        "limit": limit,
    }
