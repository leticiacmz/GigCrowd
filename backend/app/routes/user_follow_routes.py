from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorClient

from app.models.user import UserResponse
from app.repositories.user_follow_repository import UserFollowRepository
from app.repositories.user_repository import UserRepository
from app.core.auth import get_current_user
from app.core.logger import get_logger


logger = get_logger("user_follow_routes")

router = APIRouter()


@router.post("/follow/{username}", response_model=dict)
async def follow_user(
    username: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorClient = Depends(get_db),
):
    """
    Follow a user by username
    """
    user_repo = UserRepository(db)
    follow_repo = UserFollowRepository(db)

    # Get the user to follow
    target_user = await user_repo.get_by_username(username)
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Prevent self-following
    if target_user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot follow yourself"
        )

    # Check if already following
    already_following = await follow_repo.exists(
        current_user.id,
        target_user.id
    )

    if already_following:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Already following this user"
        )

    # Create follow relationship
    await follow_repo.create_follow(
        current_user.id,
        target_user.id
    )

    # Update user counts
    await user_repo.update_following_count(current_user.id, 1)
    await user_repo.update_followers_count(target_user.id, 1)

    logger.info(f"User {current_user.username} followed {username}")

    return {
        "success": True,
        "message": f"Now following {username}"
    }


@router.delete("/follow/{username}", response_model=dict)
async def unfollow_user(
    username: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorClient = Depends(get_db),
):
    """
    Unfollow a user by username
    """
    user_repo = UserRepository(db)
    follow_repo = UserFollowRepository(db)

    # Get the user to unfollow
    target_user = await user_repo.get_by_username(username)
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Check if following
    is_following = await follow_repo.exists(
        current_user.id,
        target_user.id
    )

    if not is_following:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Not following this user"
        )

    # Remove follow relationship
    await follow_repo.delete_follow(
        current_user.id,
        target_user.id
    )

    # Update user counts
    await user_repo.update_following_count(current_user.id, -1)
    await user_repo.update_followers_count(target_user.id, -1)

    logger.info(f"User {current_user.username} unfollowed {username}")

    return {
        "success": True,
        "message": f"Unfollowed {username}"
    }


@router.get("/followers", response_model=list[UserResponse])
async def get_followers(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorClient = Depends(get_db),
    limit: int = 50,
    skip: int = 0,
):
    """
    Get list of users who follow the current user
    """
    follow_repo = UserFollowRepository(db)
    user_repo = UserRepository(db)

    follow_relationships = await follow_repo.get_followers(
        current_user.id,
        limit=limit,
        skip=skip
    )

    # Get full user objects
    follower_ids = [rel["follower_id"] for rel in follow_relationships]
    followers = []
    for user_id in follower_ids:
        user = await user_repo.get_by_id(user_id)
        if user:
            followers.append(user)

    return followers


@router.get("/following", response_model=list[UserResponse])
async def get_following(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorClient = Depends(get_db),
    limit: int = 50,
    skip: int = 0,
):
    """
    Get list of users the current user follows
    """
    follow_repo = UserFollowRepository(db)
    user_repo = UserRepository(db)

    follow_relationships = await follow_repo.get_following(
        current_user.id,
        limit=limit,
        skip=skip
    )

    # Get full user objects
    following_ids = [rel["following_id"] for rel in follow_relationships]
    following = []
    for user_id in following_ids:
        user = await user_repo.get_by_id(user_id)
        if user:
            following.append(user)

    return following


@router.get("/follow/{username}/status", response_model=dict)
async def check_follow_status(
    username: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorClient = Depends(get_db),
):
    """
    Check if current user follows the specified user
    """
    user_repo = UserRepository(db)
    follow_repo = UserFollowRepository(db)

    target_user = await user_repo.get_by_username(username)
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    is_following = await follow_repo.exists(
        current_user.id,
        target_user.id
    )

    return {
        "is_following": is_following,
        "username": username
    }