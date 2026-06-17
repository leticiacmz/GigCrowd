from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from app.models.post import PostCreate, PostResponse, PostUpdate
from app.services.post_service import PostService
from app.auth.dependencies import get_current_active_user
from typing import List
import os
import io
from PIL import Image
from app.config import settings
import cloudinary
import cloudinary.uploader

# Configure Cloudinary if credentials are provided
if settings.CLOUDINARY_CLOUD_NAME:
    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET
    )

router = APIRouter(prefix="/posts", tags=["posts"])


@router.post("", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
async def create_post(
    post_data: PostCreate,
    current_user: dict = Depends(get_current_active_user)
):
    """Create a new post"""
    post = await PostService.create_post(current_user["_id"], post_data)
    
    # Create activity
    from app.services.activity_service import ActivityService
    from app.models.activity import ActivityCreate, ActivityType
    await ActivityService.create_activity(
        user_id=current_user["_id"],
        activity_data=ActivityCreate(
            activity_type=ActivityType.CREATE_POST,
            target_id=post.id,
            target_type="post"
        )
    )
    
    return PostResponse(**post.model_dump())


@router.get("", response_model=List[PostResponse])
async def get_posts(
    skip: int = 0,
    limit: int = 50,
    user_id: str = None,
    event_id: str = None
):
    """Get posts with optional filters"""
    posts = await PostService.get_posts(skip, limit, user_id, event_id)
    return [PostResponse(**post.model_dump()) for post in posts]


@router.get("/{post_id}", response_model=PostResponse)
async def get_post(post_id: str):
    """Get post by ID"""
    post = await PostService.get_post_by_id(post_id)
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found"
        )
    return PostResponse(**post.model_dump())


@router.put("/{post_id}", response_model=PostResponse)
async def update_post(
    post_id: str,
    post_data: PostUpdate,
    current_user: dict = Depends(get_current_active_user)
):
    """Update post"""
    try:
        post = await PostService.update_post(post_id, current_user["_id"], post_data)
        return PostResponse(**post.model_dump())
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{post_id}")
async def delete_post(
    post_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """Delete post"""
    success = await PostService.delete_post(post_id, current_user["_id"])
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found or not authorized"
        )
    return {"message": "Post deleted successfully"}


@router.post("/upload")
async def upload_media(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_active_user)
):
    """Upload image file only (no videos) with compression and Cloudinary"""
    
    # Validate file type (images only)
    file_extension = file.filename.split(".")[-1].lower()
    allowed_extensions = ["jpg", "jpeg", "png", "gif", "webp"]
    
    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only images are allowed. Supported formats: {', '.join(allowed_extensions)}"
        )
    
    # Read file
    content = await file.read()
    file_size = len(content)
    
    # Validate file size
    max_size = settings.MAX_IMAGE_SIZE_MB * 1024 * 1024  # Convert MB to bytes
    if file_size > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Image size exceeds maximum allowed size of {settings.MAX_IMAGE_SIZE_MB}MB"
        )
    
    # Compress image using PIL
    try:
        image = Image.open(io.BytesIO(content))
        
        # Convert to RGB if necessary (for JPEG)
        if image.mode in ("RGBA", "P"):
            image = image.convert("RGB")
        
        # Resize if too large (max 1920x1080)
        max_width, max_height = 1920, 1080
        if image.width > max_width or image.height > max_height:
            image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
        
        # Compress and save to bytes
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=85, optimize=True)
        compressed_content = output.getvalue()
        
        # If Cloudinary is configured, upload there
        if settings.CLOUDINARY_CLOUD_NAME:
            upload_result = cloudinary.uploader.upload(
                io.BytesIO(compressed_content),
                folder="gigcrowd/posts",
                transformation=[
                    {"width": 1920, "height": 1080, "crop": "limit"},
                    {"quality": "auto"}
                ]
            )
            file_url = upload_result["secure_url"]
            media_type = "image"
        else:
            # Fallback to local storage
            upload_dir = settings.UPLOAD_DIR
            os.makedirs(upload_dir, exist_ok=True)
            
            import uuid
            filename = f"{uuid.uuid4()}.jpg"
            file_path = os.path.join(upload_dir, filename)
            
            with open(file_path, "wb") as f:
                f.write(compressed_content)
            
            file_url = f"/uploads/{filename}"
            media_type = "image"
        
        return {
            "file_url": file_url,
            "media_type": media_type,
            "original_size": file_size,
            "compressed_size": len(compressed_content)
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing image: {str(e)}"
        )
