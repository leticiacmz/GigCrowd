from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import get_current_active_user
from app.models.follow import FollowCreate, FollowResponse
from app.services.follow_service import FollowService


router = APIRouter(
    prefix="/follows",
    tags=["follows"],
)


def get_follow_service() -> FollowService:
    """
    Dependency Injection for FollowService.
    """

    return FollowService()


@router.post(
    "",
    response_model=FollowResponse,
    status_code=status.HTTP_201_CREATED,
)
async def follow_user(
    follow_data: FollowCreate,
    current_user: dict = Depends(get_current_active_user),
    follow_service: FollowService = Depends(get_follow_service),
):
    """
    Follow another user.
    """

    try:
        follow = await follow_service.follow_user(
            follower_id=current_user["_id"],
            follow_data=follow_data,
        )

        return FollowResponse(**follow)

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.delete("/{following_id}")
async def unfollow_user(
    following_id: str,
    current_user: dict = Depends(get_current_active_user),
    follow_service: FollowService = Depends(get_follow_service),
):
    """
    Unfollow a user.
    """

    success = await follow_service.unfollow_user(
        follower_id=current_user["_id"],
        following_id=following_id,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Follow relationship not found",
        )

    return {
        "message": "Unfollowed successfully",
    }