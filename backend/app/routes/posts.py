from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from typing import List, Optional
from app.database.connection import get_database
from app.auth.dependencies import get_current_active_user
from datetime import datetime, UTC
import uuid

router = APIRouter(prefix="/posts", tags=["posts"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_post(
    content: str,
    image: Optional[UploadFile] = File(None),
    current_user: dict = Depends(get_current_active_user)
):
    """Create a new post"""
    db = get_database()
    
    post = {
        "_id": str(uuid.uuid4()),
        "user_id": current_user["_id"],
        "content": content,
        "image_url": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "likes_count": 0,
        "comments_count": 0
    }
    
    # Handle image upload if provided
    if image:
        # For now, just store the filename
        # In production, upload to Cloudinary or S3
        post["image_url"] = f"/uploads/{image.filename}"
    
    await db.posts.insert_one(post)
    post["id"] = post["_id"]
    del post["_id"]
    
    return post


@router.get("")
async def get_posts(
    skip: int = 0,
    limit: int = 50,
    user_id: Optional[str] = None
):
    """Get posts with optional filters"""
    db = get_database()
    
    query = {}
    if user_id:
        query["user_id"] = user_id
    
    posts = await db.posts.find(query).sort("created_at", -1).skip(skip).limit(limit).to_list(length=limit)
    
    # Convert ObjectId to string
    for post in posts:
        post["id"] = str(post["_id"])
        del post["_id"]
    
    return posts


@router.get("/{post_id}")
async def get_post(post_id: str):
    """Get post by ID"""
    db = get_database()
    
    post = await db.posts.find_one({"_id": post_id})
    
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found"
        )
    
    post["id"] = str(post["_id"])
    del post["_id"]
    
    return post


@router.delete("/{post_id}")
async def delete_post(
    post_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """Delete a post"""
    db = get_database()
    
    post = await db.posts.find_one({"_id": post_id})
    
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found"
        )
    
    # Check if user owns the post
    if post["user_id"] != current_user["_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this post"
        )
    
    await db.posts.delete_one({"_id": post_id})
    
    return {"message": "Post deleted successfully"}
