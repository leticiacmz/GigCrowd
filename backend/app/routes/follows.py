from fastapi import APIRouter, Depends, HTTPException, status
from app.models.follow import FollowCreate, FollowResponse
from app.services.follow_service import FollowService
from app.auth.dependencies import get_current_active_user

router = APIRouter(prefix="/follows", tags=["follows"])


@router.post("", response_model=FollowResponse, status_code=status.HTTP_201_CREATED)
async def follow_user(
    follow_data: FollowCreate,
    current_user: dict = Depends(get_current_active_user)
):
    """Follow a user"""
    try:
        follow = await FollowService.follow_user(current_user["_id"], follow_data)
        return FollowResponse(**follow.model_dump())
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{following_id}")
async def unfollow_user(
    following_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """Unfollow a user"""
    success = await FollowService.unfollow_user(current_user["_id"], following_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Follow relationship not found"
        )
    return {"message": "Unfollowed successfully"}
