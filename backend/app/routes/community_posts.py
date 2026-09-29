from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorClient

from app.schemas.community_post import CommunityPostCreate, CommunityPostResponse
from app.repositories.community_post_repository import CommunityPostRepository
from app.repositories.user_repository import UserRepository
from app.repositories.artist_repository import ArtistRepository
from app.auth.dependencies import get_current_active_user
from app.database.connection import get_database
from app.routes.feed import get_feed_activity_service
from app.services.feed_activity_service import FeedActivityService
from app.core.logger import get_logger


logger = get_logger("community_posts_routes")

router = APIRouter(prefix="/community", tags=["community"])


def get_community_post_service():
    db = get_database()
    return CommunityPostRepository(db)


@router.post("/posts", response_model=CommunityPostResponse)
async def create_community_post(
    post: CommunityPostCreate,
    current_user: dict = Depends(get_current_active_user),
    post_repo: CommunityPostRepository = Depends(get_community_post_service),
    feed_activity_service: FeedActivityService = Depends(get_feed_activity_service),
):
    """Create a new community post for an artist"""
    
    # Verify artist exists
    artist_repo = ArtistRepository(get_database())
    artist = await artist_repo.get_by_slug(post.artist_slug)
    if not artist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artist not found"
        )
    
    # Create post
    result = await post_repo.create_post(
        artist_slug=post.artist_slug,
        user_id=current_user["_id"],
        content=post.content,
        image_url=post.image_url
    )
    
    await feed_activity_service.record_community_post(
        actor_id=current_user["_id"],
        post_id=str(result["_id"]),
        artist_slug=result["artist_slug"],
        content=result["content"],
    )

    logger.info(f"User {current_user['username']} created community post for {post.artist_slug}")
    
    return CommunityPostResponse(
        id=str(result["_id"]),
        artist_slug=result["artist_slug"],
        user_id=str(result["user_id"]),
        content=result["content"],
        image_url=result.get("image_url"),
        likes_count=result["likes_count"],
        comments_count=result["comments_count"],
        created_at=result["created_at"],
        updated_at=result.get("updated_at"),
        username=current_user.get("username"),
        user_avatar_url=current_user.get("avatar_url")
    )


@router.get("/posts/{artist_slug}", response_model=list[CommunityPostResponse])
async def get_artist_community_posts(
    artist_slug: str,
    current_user: dict = Depends(get_current_active_user),
    post_repo: CommunityPostRepository = Depends(get_community_post_service),
    user_repo: UserRepository = Depends(get_database),
    limit: int = 50,
    skip: int = 0,
):
    """Get community posts for a specific artist"""
    
    posts = await post_repo.get_posts_by_artist(artist_slug, limit=limit, skip=skip)
    
    # Enrich with user info
    enriched_posts = []
    for post in posts:
        user = await user_repo.get_by_id(str(post["user_id"]))
        enriched_posts.append(CommunityPostResponse(
            id=str(post["_id"]),
            artist_slug=post["artist_slug"],
            user_id=str(post["user_id"]),
            content=post["content"],
            image_url=post.get("image_url"),
            likes_count=post["likes_count"],
            comments_count=post["comments_count"],
            created_at=post["created_at"],
            updated_at=post.get("updated_at"),
            username=user.get("username") if user else None,
            user_avatar_url=user.get("avatar_url") if user else None
        ))
    
    return enriched_posts


@router.get("/posts", response_model=list[CommunityPostResponse])
async def get_user_community_posts(
    current_user: dict = Depends(get_current_active_user),
    post_repo: CommunityPostRepository = Depends(get_community_post_service),
    user_repo: UserRepository = Depends(get_database),
    limit: int = 50,
    skip: int = 0,
):
    """Get community posts by the current user"""
    
    posts = await post_repo.get_posts_by_user(current_user["_id"], limit=limit, skip=skip)
    
    # Enrich with user info
    enriched_posts = []
    for post in posts:
        user = await user_repo.get_by_id(str(post["user_id"]))
        enriched_posts.append(CommunityPostResponse(
            id=str(post["_id"]),
            artist_slug=post["artist_slug"],
            user_id=str(post["user_id"]),
            content=post["content"],
            image_url=post.get("image_url"),
            likes_count=post["likes_count"],
            comments_count=post["comments_count"],
            created_at=post["created_at"],
            updated_at=post.get("updated_at"),
            username=user.get("username") if user else None,
            user_avatar_url=user.get("avatar_url") if user else None
        ))
    
    return enriched_posts


@router.delete("/posts/{post_id}")
async def delete_community_post(
    post_id: str,
    current_user: dict = Depends(get_current_active_user),
    post_repo: CommunityPostRepository = Depends(get_community_post_service),
):
    """Delete a community post (only by author)"""
    
    success = await post_repo.delete_post(post_id, current_user["_id"])
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found or unauthorized"
        )
    
    logger.info(f"User {current_user['username']} deleted community post {post_id}")
    
    return {"success": True, "message": "Post deleted"}