"""
Artist-scoped community routes.

All community operations are explicitly tied to an artist.
There is no global community concept.
"""
from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.community_post import CommunityPostCreate, CommunityPostResponse
from app.schemas.comment import CommentCreate, CommentUpdate, CommentResponse
from app.repositories.community_post_repository import CommunityPostRepository
from app.repositories.comment_repository import CommentRepository
from app.repositories.user_repository import UserRepository
from app.repositories.artist_repository import ArtistRepository
from app.repositories.artist_follow_repository import ArtistFollowRepository
from app.services.community_service import CommunityService
from app.auth.dependencies import get_current_active_user, get_optional_user
from app.database.connection import get_database
from app.core.logger import get_logger
import bleach


logger = get_logger("artist_community_routes")

router = APIRouter(
    prefix="/artists/{artist_slug}/community",
    tags=["artist-community"],
)


def get_community_post_repo():
    db = get_database()
    return CommunityPostRepository(db)


def get_comment_repo():
    db = get_database()
    return CommentRepository(db)


def get_community_service():
    db = get_database()
    return CommunityService(
        artist_follow_repository=ArtistFollowRepository(db),
        artist_repository=ArtistRepository(db),
    )


# =====================================================
# Posts
# =====================================================

@router.get("/posts", response_model=list[CommunityPostResponse])
async def get_community_posts(
    artist_slug: str,
    current_user: dict = Depends(get_optional_user),
    post_repo: CommunityPostRepository = Depends(get_community_post_repo),
    limit: int = 50,
    skip: int = 0,
):
    """Get community posts for a specific artist (public)"""

    posts = await post_repo.get_posts_by_artist(artist_slug, limit=limit, skip=skip)

    user_repo = UserRepository(get_database())
    enriched_posts = []
    for post in posts:
        user = await user_repo.get_by_id(str(post["user_id"]))

        liked_by_user = False
        if current_user:
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


@router.post("/posts", response_model=CommunityPostResponse)
async def create_community_post(
    artist_slug: str,
    post: CommunityPostCreate,
    current_user: dict = Depends(get_current_active_user),
    post_repo: CommunityPostRepository = Depends(get_community_post_repo),
    community_service: CommunityService = Depends(get_community_service),
):
    """Create a new community post for an artist (requires follow)"""

    # Verify artist exists
    await community_service.verify_artist_exists(artist_slug)

    # Verify user follows the artist
    await community_service.require_follow_for_write(current_user["_id"], artist_slug)

    # Create post
    result = await post_repo.create_post(
        artist_slug=artist_slug,
        user_id=current_user["_id"],
        content=post.content,
        image_url=post.image_url
    )

    logger.info(f"User {current_user['username']} created community post for {artist_slug}")

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


@router.post("/posts/{post_id}/like")
async def like_community_post(
    artist_slug: str,
    post_id: str,
    current_user: dict = Depends(get_current_active_user),
    post_repo: CommunityPostRepository = Depends(get_community_post_repo),
    community_service: CommunityService = Depends(get_community_service),
):
    """Like a community post (requires follow)"""

    # Verify post belongs to artist
    await community_service.verify_post_belongs_to_artist(post_id, artist_slug, post_repo)

    # Verify user follows the artist
    await community_service.require_follow_for_write(current_user["_id"], artist_slug)

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
    artist_slug: str,
    post_id: str,
    current_user: dict = Depends(get_current_active_user),
    post_repo: CommunityPostRepository = Depends(get_community_post_repo),
    community_service: CommunityService = Depends(get_community_service),
):
    """Unlike a community post (requires follow)"""

    # Verify post belongs to artist
    await community_service.verify_post_belongs_to_artist(post_id, artist_slug, post_repo)

    # Verify user follows the artist
    await community_service.require_follow_for_write(current_user["_id"], artist_slug)

    success = await post_repo.unlike_post(post_id, current_user["_id"])

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Post not liked"
        )

    logger.info(f"User {current_user['username']} unliked community post {post_id}")

    return {"success": True, "message": "Post unliked"}


@router.delete("/posts/{post_id}")
async def delete_community_post(
    artist_slug: str,
    post_id: str,
    current_user: dict = Depends(get_current_active_user),
    post_repo: CommunityPostRepository = Depends(get_community_post_repo),
    community_service: CommunityService = Depends(get_community_service),
):
    """Delete a community post (only by author)"""

    # Verify post belongs to artist
    await community_service.verify_post_belongs_to_artist(post_id, artist_slug, post_repo)

    success = await post_repo.delete_post(post_id, current_user["_id"])

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found or unauthorized"
        )

    logger.info(f"User {current_user['username']} deleted community post {post_id}")

    return {"success": True, "message": "Post deleted"}


# =====================================================
# Comments
# =====================================================

ALLOWED_COMMENT_TAGS = ["b", "i", "em", "strong", "p", "br"]
ALLOWED_COMMENT_ATTRIBUTES: dict = {}


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


@router.get("/posts/{post_id}/comments", response_model=list[CommentResponse])
async def get_post_comments(
    artist_slug: str,
    post_id: str,
    current_user: dict = Depends(get_optional_user),
    comment_repo: CommentRepository = Depends(get_comment_repo),
    post_repo: CommunityPostRepository = Depends(get_community_post_repo),
    limit: int = 50,
    skip: int = 0,
):
    """Get top-level comments for a post (public)"""

    limit = max(1, min(limit, 100))
    skip = max(0, min(skip, 10000))

    # Verify post exists and belongs to artist
    post = await post_repo.get_post_by_id(post_id)
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found"
        )
    if post.get("artist_slug") != artist_slug:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found in this artist's community"
        )

    comments = await comment_repo.get_comments_by_post(post_id, limit=limit, skip=skip)

    user_repo = UserRepository(get_database())
    enriched = []
    for comment in comments:
        enriched_comment = await _enrich_comment(comment, user_repo)

        replies = await comment_repo.get_replies(str(comment["_id"]))
        enriched_replies = []
        for reply in replies:
            enriched_reply = await _enrich_comment(reply, user_repo)
            enriched_replies.append(enriched_reply)

        enriched_comment.replies = enriched_replies
        enriched_comment.replies_count = len(enriched_replies)
        enriched.append(enriched_comment)

    return enriched


@router.post("/comments", response_model=CommentResponse)
async def create_comment(
    artist_slug: str,
    comment_data: CommentCreate,
    current_user: dict = Depends(get_current_active_user),
    comment_repo: CommentRepository = Depends(get_comment_repo),
    post_repo: CommunityPostRepository = Depends(get_community_post_repo),
    community_service: CommunityService = Depends(get_community_service),
):
    """Create a comment or reply on a community post (requires follow)"""

    # Verify post exists and belongs to artist
    post = await post_repo.get_post_by_id(comment_data.post_id)
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found"
        )
    if post.get("artist_slug") != artist_slug:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found in this artist's community"
        )

    # Verify user follows the artist
    await community_service.require_follow_for_write(current_user["_id"], artist_slug)

    # If this is a reply, verify parent comment exists
    if comment_data.parent_comment_id:
        parent = await comment_repo.get_comment_by_id(comment_data.parent_comment_id)
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Parent comment not found"
            )
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


@router.get("/comments/{comment_id}/replies", response_model=list[CommentResponse])
async def get_comment_replies(
    artist_slug: str,
    comment_id: str,
    current_user: dict = Depends(get_optional_user),
    comment_repo: CommentRepository = Depends(get_comment_repo),
    limit: int = 50,
    skip: int = 0,
):
    """Get replies for a specific comment (public)"""

    limit = max(1, min(limit, 100))
    skip = max(0, min(skip, 10000))

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
    artist_slug: str,
    comment_id: str,
    comment_data: CommentUpdate,
    current_user: dict = Depends(get_current_active_user),
    comment_repo: CommentRepository = Depends(get_comment_repo),
    community_service: CommunityService = Depends(get_community_service),
):
    """Update a comment (only by author)"""

    comment = await comment_repo.get_comment_by_id(comment_id)
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found"
        )

    if str(comment["user_id"]) != current_user["_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to edit this comment"
        )

    # Verify user follows the artist
    await community_service.require_follow_for_write(current_user["_id"], artist_slug)

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
    artist_slug: str,
    comment_id: str,
    current_user: dict = Depends(get_current_active_user),
    comment_repo: CommentRepository = Depends(get_comment_repo),
    community_service: CommunityService = Depends(get_community_service),
):
    """Delete a comment (only by author)"""

    comment = await comment_repo.get_comment_by_id(comment_id)
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found"
        )

    if str(comment["user_id"]) != current_user["_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this comment"
        )

    # Verify user follows the artist
    await community_service.require_follow_for_write(current_user["_id"], artist_slug)

    success = await comment_repo.delete_comment(comment_id, current_user["_id"])

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete comment"
        )

    logger.info(f"User {current_user['username']} deleted comment {comment_id}")

    return {"success": True, "message": "Comment deleted"}
