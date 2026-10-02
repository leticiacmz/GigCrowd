"""Image uploads.

Photos attached to a review go to Cloudinary. The Cloudinary secret only ever
lives on the server: the browser posts the file to this service, which
validates it and uploads it with the server-side credentials, and only the
resulting public URL is stored on the show log.

There is exactly one upload implementation, so a review photo and a post image
are stored the same way and share the same validation.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.config import settings


# The formats the product accepts. Animated formats are included on purpose:
# a gig photo set is not a design deliverable, and re-encoding someone's photo
# is worse than storing it as sent.
ALLOWED_IMAGE_CONTENT_TYPES = (
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
)

# Cloudinary's own resource type. Every upload here is a still image.
IMAGE_RESOURCE_TYPE = "image"

# Folder in the Cloudinary account, so review photos stay grouped and can be
# found (or purged) without scanning the whole account.
MEDIA_FOLDER = "gigcrowd"


class UploadedImage(BaseModel):
    """What a stored upload looks like.

    `public_id` is Cloudinary's handle on the asset. It is kept because it is
    the only identifier Cloudinary accepts for replacing or deleting the
    image; the URL alone cannot be deleted reliably.
    """

    url: str = Field(
        description="Public URL of the stored image",
    )

    public_id: str = Field(
        description=(
            "Provider-side identifier, kept so the image "
            "can be replaced or removed later"
        ),
    )

    width: Optional[int] = None

    height: Optional[int] = None

    bytes: Optional[int] = None


class MediaUploadError(ValueError):
    """The upload cannot be accepted as sent.

    Subclasses `ValueError` so a caller that already maps validation failures
    onto a 400 does not have to learn a second exception type.
    """


class MediaUploadService:
    """Uploads an image and reports where it ended up."""

    def __init__(
        self,
        uploader=None,
        cloud_name: Optional[str] = settings.CLOUDINARY_CLOUD_NAME,
        api_key: Optional[str] = settings.CLOUDINARY_API_KEY,
        api_secret: Optional[str] = settings.CLOUDINARY_API_SECRET,
        max_size_mb: Optional[int] = None,
        allowed_content_types: tuple[str, ...] = ALLOWED_IMAGE_CONTENT_TYPES,
        folder: str = MEDIA_FOLDER,
    ):
        """
        `uploader` is anything exposing an `upload(content, **options)` call
        that answers with the provider's result mapping. It is injected so a
        test can upload without a network or an account, and it defaults to
        the configured Cloudinary client.

        The credentials default to the server's own configuration; passing
        `None` explicitly means "not configured", which is how a
        misconfigured deployment reports itself instead of half-working.
        """

        self.cloud_name = cloud_name

        self.api_key = api_key

        self.api_secret = api_secret

        self.max_size_bytes = int(
            max_size_mb
            if max_size_mb is not None
            else settings.MAX_IMAGE_SIZE_MB
        ) * 1024 * 1024

        self.allowed_content_types = allowed_content_types

        self.folder = folder

        self._uploader = uploader

    # ============================================================
    # CONFIGURATION
    # ============================================================

    def is_configured(self) -> bool:
        """Whether an upload can actually be performed.

        Reported instead of guessed, so a misconfigured deployment fails with
        a clear message rather than an SDK error.
        """

        return bool(
            self.cloud_name and self.api_key and self.api_secret
        )

    @property
    def uploader(self):
        """The Cloudinary client, built on first use.

        Imported lazily so a process that never uploads an image (the tests,
        for instance) does not need the SDK to be installed or configured.
        """

        if self._uploader is None:
            self._uploader = self._build_uploader()

        return self._uploader

    def _build_uploader(self):
        """Configure the SDK with the server-side credentials."""

        if not self.is_configured():
            raise MediaUploadError(
                "Image uploads are not configured on this server."
            )

        import cloudinary

        cloudinary.config(
            cloud_name=self.cloud_name,
            api_key=self.api_key,
            api_secret=self.api_secret,
            secure=True,
        )

        return cloudinary

    # ============================================================
    # VALIDATION
    # ============================================================

    def validate(
        self,
        content: bytes,
        content_type: Optional[str],
        filename: Optional[str] = None,
    ) -> None:
        """Reject an upload that must not reach Cloudinary.

        Checked before the bytes are sent anywhere, so an oversized or
        unsupported file costs nothing.
        """

        if not content:
            raise MediaUploadError(
                "The uploaded file is empty."
            )

        if content_type not in self.allowed_content_types:

            allowed = ", ".join(
                self.allowed_content_types
            )

            raise MediaUploadError(
                "Unsupported image type. "
                f"Allowed types: {allowed}."
            )

        if len(content) > self.max_size_bytes:

            megabytes = self.max_size_bytes // (
                1024 * 1024
            )

            raise MediaUploadError(
                f"Image is too large. The maximum size is "
                f"{megabytes}MB."
            )

    # ============================================================
    # UPLOAD
    # ============================================================

    async def upload_image(
        self,
        content: bytes,
        content_type: Optional[str],
        filename: Optional[str] = None,
        folder: Optional[str] = None,
    ) -> UploadedImage:
        """Store an image and return where it landed."""

        self.validate(
            content,
            content_type,
            filename,
        )

        options = {
            "folder": folder or self.folder,
            "resource_type": IMAGE_RESOURCE_TYPE,
        }

        if filename:
            options["public_id"] = filename

        result = await self._run_upload(
            content,
            options,
        )

        return self._to_uploaded_image(result)

    async def _run_upload(
        self,
        content: bytes,
        options: dict,
    ):
        """Send the bytes to Cloudinary.

        The SDK call is synchronous and does its own networking, so it runs in
        a worker thread to keep the event loop free.
        """

        import asyncio

        return await asyncio.to_thread(
            self.uploader.uploader.upload,
            content,
            **options,
        )

    @staticmethod
    def _to_uploaded_image(result) -> UploadedImage:
        """Read the documented fields out of an upload result.

        Cloudinary answers with a mapping; only the fields the product stores
        are read, so extra fields in the response cannot leak into a show log.
        """

        url = result.get("secure_url") or result.get("url")

        if not url:
            raise MediaUploadError(
                "The image could not be stored."
            )

        return UploadedImage(
            url=url,
            public_id=result.get("public_id") or "",
            width=result.get("width"),
            height=result.get("height"),
            bytes=result.get("bytes"),
        )
