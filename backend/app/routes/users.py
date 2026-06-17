from fastapi import APIRouter, Depends, HTTPException, status
from app.models.user import UserResponse, UserUpdate
from app.services.user_service import UserService
from app.auth.dependencies import get_current_active_user
from typing import List

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(current_user: dict = Depends(get_current_active_user)):
    """Get current user profile"""
    return UserResponse(**current_user)


@router.put("/me", response_model=UserResponse)
async def update_current_user_profile(
    user_data: UserUpdate,
    current_user: dict = Depends(get_current_active_user)
):
    """Update current user profile"""
    user = await UserService.update_user(current_user["_id"], user_data)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return UserResponse(**user.model_dump())


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: str):
    """Get user by ID"""
    user = await UserService.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return UserResponse(**user.model_dump())


@router.get("/{user_id}/followers", response_model=List[dict])
async def get_user_followers(user_id: str, skip: int = 0, limit: int = 50):
    """Get user's followers"""
    followers = await UserService.get_user_by_id(user_id)
    if not followers:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    from app.services.follow_service import FollowService
    followers_list = await FollowService.get_followers(user_id, skip, limit)
    return followers_list


@router.get("/{user_id}/following", response_model=List[dict])
async def get_user_following(user_id: str, skip: int = 0, limit: int = 50):
    """Get users that a user is following"""
    user = await UserService.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    from app.services.follow_service import FollowService
    following_list = await FollowService.get_following(user_id, skip, limit)
    return following_list
