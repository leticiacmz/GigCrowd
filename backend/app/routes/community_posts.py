from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorClient

from app.schemas.community_post import CommunityPostCreate, CommunityPostResponse
from app.schemas.comment import CommentCreate, CommentUpdate, CommentResponse
from app.repositories.community_post_repository import CommunityPostRepository
from app.repositories.comment_repository import CommentRepository
from app.repositories.user_repository import UserRepository
from app.repositories.artist_repository import ArtistRepository
from app.auth.dependencies import get_current_active_user
from app.database.connection import get_database
from app.core.logger import get_logger
from bson import ObjectId
import bleach


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
    limit: int = 50,
    skip: int = 0,
):
    """Get community posts for a specific artist"""

    posts = await post_repo.get_posts_by_artist(artist_slug, limit=limit, skip=skip)

    # Enrich with user info
    user_repo = UserRepository(get_database())
    enriched_posts = []
    for post in posts:
        user = await user_repo.get_by_id(str(post["user_id"]))

        # Check if current user liked this post
        liked_by_user = await post_repo.get_like_status(post["_id"], current_user["_id"])

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
            user_avatar_url=user.get("avatar_url") if user else None,
            liked_by_user=liked_by_user,
        ))

    return enriched_posts


@router.get("/posts", response_model=list[CommunityPostResponse])
async def get_user_community_posts(
    current_user: dict = Depends(get_current_active_user),
    post_repo: CommunityPostRepository = Depends(get_community_post_service),
    limit: int = 50,
    skip: int = 0,
):
    """Get community posts by the current user"""

    posts = await post_repo.get_posts_by_user(current_user["_id"], limit=limit, skip=skip)

    # Enrich with user info
    user_repo = UserRepository(get_database())
    enriched_posts = []
    for post in posts:
        user = await user_repo.get_by_id(str(post["user_id"]))

        # Check if current user liked this post
        liked_by_user = await post_repo.get_like_status(post["_id"], current_user["_id"])

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
            user_avatar_url=user.get("avatar_url") if user else None,
            liked_by_user=liked_by_user,
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


@router.post("/posts/{post_id}/like")
async def like_community_post(
    post_id: str,
    current_user: dict = Depends(get_current_active_user),
    post_repo: CommunityPostRepository = Depends(get_community_post_service),
):
    """Like a community post"""

    # Verify post exists
    post = await post_repo.get_post_by_id(post_id)
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found"
        )

    success = await post_repo.like_post(post_id, current_user["_id"])

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Already liked this post"
        )

    logger.info(f"User {current_user['username']} liked community post {post_id}")

    return {"success": True, "message": "Post liked"}


@router.delete("/posts/{post_id}/like")
async def unlike_community_post(
    post_id: str,
    current_user: dict = Depends(get_current_active_user),
    post_repo: CommunityPostRepository = Depends(get_community_post_service),
):
    """Unlike a community post"""

    # Verify post exists
    post = await post_repo.get_post_by_id(post_id)
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found"
        )

    success = await post_repo.unlike_post(post_id, current_user["_id"])

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Post not liked"
        )

    logger.info(f"User {current_user['username']} unliked community post {post_id}")

    return {"success": True, "message": "Post unliked"}


# =====================================================
# Comments
# =====================================================

ALLOWED_COMMENT_TAGS = ["b", "i", "em", "strong", "p", "br"]
ALLOWED_COMMENT_ATTRIBUTES: dict = {}


def get_comment_service():
    db = get_database()
    return CommentRepository(db)


async def _enrich_comment(comment: dict, user_repo: UserRepository) -> CommentResponse:
    """Enrich a comment with user info"""
    user = await user_repo.get_by_id(str(comment["user_id"]))
    return CommentResponse(
        id=str(comment["_id"]),
        post_id=str(comment["post_id"]),
        user_id=str(comment["user_id"]),
        content=comment["content"],
        parent_comment_id=str(comment["parent_comment_id"]) if comment.get("parent_comment_id") else None,
        created_at=comment["created_at"],
        updated_at=comment.get("updated_at"),
        username=user.get("username") if user else None,
        user_avatar_url=user.get("avatar_url") if user else None,
    )


@router.post("/comments", response_model=CommentResponse)
async def create_comment(
    comment_data: CommentCreate,
    current_user: dict = Depends(get_current_active_user),
    comment_repo: CommentRepository = Depends(get_comment_service),
):
    """Create a comment or reply on a community post"""

    # Verify post exists
    post_repo = CommunityPostRepository(get_database())
    post = await post_repo.get_post_by_id(comment_data.post_id)
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found"
        )

    # If this is a reply, verify parent comment exists
    if comment_data.parent_comment_id:
        parent = await comment_repo.get_comment_by_id(comment_data.parent_comment_id)
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Parent comment not found"
            )
        # Verify parent comment belongs to the same post
        if str(parent["post_id"]) != comment_data.post_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Parent comment does not belong to this post"
            )

    # Sanitize content
    cleaned_content = bleach.clean(
        comment_data.content,
        tags=ALLOWED_COMMENT_TAGS,
        attributes=ALLOWED_COMMENT_ATTRIBUTES,
        strip=True,
    )

    result = await comment_repo.create_comment(
        post_id=comment_data.post_id,
        user_id=current_user["_id"],
        content=cleaned_content,
        parent_comment_id=comment_data.parent_comment_id,
    )

    user_repo = UserRepository(get_database())
    response = await _enrich_comment(result, user_repo)

    logger.info(f"User {current_user['username']} created comment on post {comment_data.post_id}")

    return response


@router.get("/posts/{post_id}/comments", response_model=list[CommentResponse])
async def get_post_comments(
    post_id: str,
    current_user: dict = Depends(get_current_active_user),
    comment_repo: CommentRepository = Depends(get_comment_service),
    limit: int = 50,
    skip: int = 0,
):
    """Get top-level comments for a post"""

    # Validate pagination
    limit = max(1, min(limit, 100))
    skip = max(0, min(skip, 10000))

    # Verify post exists
    post_repo = CommunityPostRepository(get_database())
    post = await post_repo.get_post_by_id(post_id)
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found"
        )

    comments = await comment_repo.get_comments_by_post(post_id, limit=limit, skip=skip)

    user_repo = UserRepository(get_database())
    enriched = []
    for comment in comments:
        enriched_comment = await _enrich_comment(comment, user_repo)

        # Get replies for each comment
        replies = await comment_repo.get_replies(str(comment["_id"]))
        enriched_replies = []
        for reply in replies:
            enriched_reply = await _enrich_comment(reply, user_repo)
            enriched_replies.append(enriched_reply)

        enriched_comment.replies = enriched_replies
        enriched_comment.replies_count = len(enriched_replies)
        enriched.append(enriched_comment)

    return enriched


@router.get("/comments/{comment_id}/replies", response_model=list[CommentResponse])
async def get_comment_replies(
    comment_id: str,
    current_user: dict = Depends(get_current_active_user),
    comment_repo: CommentRepository = Depends(get_comment_service),
    limit: int = 50,
    skip: int = 0,
):
    """Get replies for a specific comment"""

    # Validate pagination
    limit = max(1, min(limit, 100))
    skip = max(0, min(skip, 10000))

    # Verify comment exists
    comment = await comment_repo.get_comment_by_id(comment_id)
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found"
        )

    replies = await comment_repo.get_replies(comment_id, limit=limit, skip=skip)

    user_repo = UserRepository(get_database())
    enriched = []
    for reply in replies:
        enriched_reply = await _enrich_comment(reply, user_repo)
        enriched.append(enriched_reply)

    return enriched


@router.put("/comments/{comment_id}", response_model=CommentResponse)
async def update_comment(
    comment_id: str,
    comment_data: CommentUpdate,
    current_user: dict = Depends(get_current_active_user),
    comment_repo: CommentRepository = Depends(get_comment_service),
):
    """Update a comment (only by author)"""

    # Verify comment exists
    comment = await comment_repo.get_comment_by_id(comment_id)
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found"
        )

    # Check ownership
    if str(comment["user_id"]) != current_user["_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to edit this comment"
        )

    # Sanitize content
    cleaned_content = bleach.clean(
        comment_data.content,
        tags=ALLOWED_COMMENT_TAGS,
        attributes=ALLOWED_COMMENT_ATTRIBUTES,
        strip=True,
    )

    updated = await comment_repo.update_comment(
        comment_id,
        current_user["_id"],
        cleaned_content,
    )

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update comment"
        )

    user_repo = UserRepository(get_database())
    response = await _enrich_comment(updated, user_repo)

    logger.info(f"User {current_user['username']} updated comment {comment_id}")

    return response


@router.delete("/comments/{comment_id}")
async def delete_comment(
    comment_id: str,
    current_user: dict = Depends(get_current_active_user),
    comment_repo: CommentRepository = Depends(get_comment_service),
):
    """Delete a comment (only by author)"""

    # Verify comment exists
    comment = await comment_repo.get_comment_by_id(comment_id)
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found"
        )

    # Check ownership
    if str(comment["user_id"]) != current_user["_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this comment"
        )

    success = await comment_repo.delete_comment(comment_id, current_user["_id"])

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete comment"
        )

    logger.info(f"User {current_user['username']} deleted comment {comment_id}")

    return {"success": True, "message": "Comment deleted"}