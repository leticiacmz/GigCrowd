"""Notifications.

Notifications are recipient scoped: every query filters on the authenticated
user, so one user can never read or mutate another user's notifications.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.dependencies import get_current_active_user
from app.models.activity import NotificationListResponse
from app.services.activity_service import ActivityService

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get(
    "",
    response_model=NotificationListResponse,
    summary="List the current user's notifications",
)
async def list_notifications(
    skip: int = 0,
    limit: int = 30,
    current_user: dict = Depends(get_current_active_user),
):
    """Return the caller's notifications, newest first."""
    return await ActivityService.get_notifications(
        user_id=current_user["_id"],
        skip=skip,
        limit=limit,
    )


@router.get(
    "/unread-count",
    summary="Count the caller's unread notifications",
)
async def get_unread_count(
    current_user: dict = Depends(get_current_active_user),
):
    unread_count = await ActivityService.get_unread_count(
        user_id=current_user["_id"],
    )
    return {"unread_count": unread_count}


@router.post(
    "/read-all",
    summary="Mark every notification as read",
)
async def mark_all_as_read(
    current_user: dict = Depends(get_current_active_user),
):
    marked = await ActivityService.mark_all_as_read(
        user_id=current_user["_id"],
    )
    return {"marked_count": marked}


@router.post(
    "/{notification_id}/read",
    summary="Mark one notification as read",
)
async def mark_as_read(
    notification_id: str,
    current_user: dict = Depends(get_current_active_user),
):
    found = await ActivityService.mark_as_read(
        notification_id=notification_id,
        user_id=current_user["_id"],
    )

    if not found:
        # Same response for "does not exist" and "belongs to someone else",
        # so the endpoint cannot be used to probe other users' notifications.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )

    return {"id": notification_id, "read": True}
