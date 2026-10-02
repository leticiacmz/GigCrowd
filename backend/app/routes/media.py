"""Image upload endpoint.

One endpoint for every image the product accepts, so the validation, the
Cloudinary credentials and the response shape live in one place. The client
never sees the Cloudinary secret: it posts the file here and receives a public
URL.
"""
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)

from app.auth.dependencies import (
    get_current_active_user,
)

from app.services.media_upload_service import (
    MediaUploadError,
    MediaUploadService,
    UploadedImage,
)


router = APIRouter(
    prefix="/media",
    tags=["media"],
)


def get_media_upload_service() -> MediaUploadService:
    """The upload service, wired to the server-side Cloudinary credentials."""

    return MediaUploadService()


@router.post(
    "/images",
    response_model=UploadedImage,
    status_code=status.HTTP_201_CREATED,
)
async def upload_image(
    image: UploadFile = File(...),
    current_user: dict = Depends(
        get_current_active_user
    ),
):

    service = get_media_upload_service()

    content = await image.read()

    # `MediaUploadError` is a `ValueError`, so an empty file, an unsupported
    # type, an oversized image and a broken configuration are all reported to
    # the caller as a deliberate 400 instead of a 500.
    try:

        uploaded = await service.upload_image(
            content=content,
            content_type=image.content_type,
            filename=image.filename,
        )

    except MediaUploadError as exc:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    return uploaded
