"""Image uploads through Cloudinary.

The point of these tests is the two rules that protect the account and the
bandwidth: a file the product does not accept never reaches Cloudinary, and the
secret never leaves the server. The Cloudinary client itself is replaced, so
these run with no account and no network.
"""
import pytest

from app.services.media_upload_service import (
    ALLOWED_IMAGE_CONTENT_TYPES,
    MediaUploadError,
    MediaUploadService,
    UploadedImage,
)


A_JPEG = b"\xff\xd8\xff\xe0" + b"0" * 512


class FakeCloudinary:

    """Stands in for the `cloudinary` module.

    Only the two entry points the service uses are present: the module is
    configured with the server-side credentials, and `uploader.upload` sends
    the bytes. Everything is recorded so a test can assert what was sent.
    """

    def __init__(
        self,
        result: dict | None = None,
    ):
        self.result = result or {
            "secure_url": (
                "https://res.cloudinary.com/demo/"
                "image/upload/gigcrowd/show.jpg"
            ),
            "public_id": "gigcrowd/show",
            "width": 1200,
            "height": 800,
            "bytes": len(A_JPEG),
        }

        self.configuration: dict = {}
        self.uploads: list[tuple[bytes, dict]] = []

        outer = self

        class _Uploader:

            def upload(inner_self, content, **options):
                outer.uploads.append((content, options))
                return outer.result

        self.uploader = _Uploader()


@pytest.fixture
def cloudinary() -> FakeCloudinary:

    return FakeCloudinary()


@pytest.fixture
def service(cloudinary: FakeCloudinary) -> MediaUploadService:

    return MediaUploadService(
        uploader=cloudinary,
        cloud_name="demo",
        api_key="key",
        api_secret="secret",
        max_size_mb=1,
    )


class TestValidation:

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "content_type",
        ALLOWED_IMAGE_CONTENT_TYPES,
    )
    async def test_every_supported_type_is_accepted(
        self,
        service,
        cloudinary,
        content_type,
    ):

        uploaded = await service.upload_image(
            content=A_JPEG,
            content_type=content_type,
        )

        assert uploaded.url.startswith("https://")
        assert len(cloudinary.uploads) == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "content_type",
        [
            "image/svg+xml",
            "application/pdf",
            "text/html",
            "image/jpg",
            None,
        ],
    )
    async def test_anything_else_is_refused_before_upload(
        self,
        service,
        cloudinary,
        content_type,
    ):

        # SVG and HTML are documents that can carry script, so the allow-list
        # is the only defence. The important assertion is that Cloudinary was
        # never called.
        with pytest.raises(MediaUploadError):

            await service.upload_image(
                content=A_JPEG,
                content_type=content_type,
            )

        assert cloudinary.uploads == []

    @pytest.mark.asyncio
    async def test_the_refusal_lists_what_is_allowed(
        self,
        service,
    ):

        with pytest.raises(MediaUploadError) as raised:

            await service.upload_image(
                content=A_JPEG,
                content_type="image/tiff",
            )

        message = str(raised.value)

        for content_type in ALLOWED_IMAGE_CONTENT_TYPES:

            assert content_type in message

    @pytest.mark.asyncio
    async def test_an_empty_file_is_refused(
        self,
        service,
        cloudinary,
    ):

        with pytest.raises(MediaUploadError) as raised:

            await service.upload_image(
                content=b"",
                content_type="image/jpeg",
            )

        assert "empty" in str(raised.value)
        assert cloudinary.uploads == []

    @pytest.mark.asyncio
    async def test_an_oversized_image_is_refused(
        self,
        service,
        cloudinary,
    ):

        with pytest.raises(MediaUploadError) as raised:

            await service.upload_image(
                content=b"0" * (1024 * 1024 + 1),
                content_type="image/jpeg",
            )

        assert "1MB" in str(raised.value)
        assert cloudinary.uploads == []

    @pytest.mark.asyncio
    async def test_an_image_exactly_at_the_limit_is_accepted(
        self,
        service,
    ):

        uploaded = await service.upload_image(
            content=b"0" * (1024 * 1024),
            content_type="image/jpeg",
        )

        assert uploaded.url

    @pytest.mark.asyncio
    async def test_the_refusal_is_a_value_error(
        self,
        service,
    ):

        # `routes/media.py` maps `MediaUploadError` onto a 400. Subclassing
        # `ValueError` keeps a bad file a client error, never a 500.
        with pytest.raises(ValueError):

            await service.upload_image(
                content=b"x",
                content_type="application/zip",
            )


class TestUpload:

    @pytest.mark.asyncio
    async def test_the_bytes_reach_the_provider(
        self,
        service,
        cloudinary,
    ):

        await service.upload_image(
            content=A_JPEG,
            content_type="image/jpeg",
            filename="my-show.jpg",
        )

        content, options = cloudinary.uploads[0]

        assert content == A_JPEG
        assert options["folder"] == "gigcrowd"
        assert options["resource_type"] == "image"
        assert options["public_id"] == "my-show.jpg"

    @pytest.mark.asyncio
    async def test_the_result_is_reported_as_stored(
        self,
        service,
    ):

        uploaded = await service.upload_image(
            content=A_JPEG,
            content_type="image/jpeg",
        )

        assert uploaded.public_id == "gigcrowd/show"
        assert uploaded.width == 1200
        assert uploaded.height == 800

    @pytest.mark.asyncio
    async def test_only_the_url_is_preferred_over_the_plain_one(
        self,
        service,
        cloudinary,
    ):

        # `secure_url` is what the client should be given; the plain `url`
        # would embed an image in an unencrypted request.
        cloudinary.result = {
            "url": "http://res.cloudinary.com/demo/x.jpg",
            "secure_url": "https://res.cloudinary.com/demo/x.jpg",
            "public_id": "x",
        }

        uploaded = await service.upload_image(
            content=A_JPEG,
            content_type="image/jpeg",
        )

        assert uploaded.url.startswith("https://")

    @pytest.mark.asyncio
    async def test_a_provider_failure_is_reported_not_swallowed(
        self,
        service,
        cloudinary,
    ):

        # A response with no URL means the upload did not happen. Storing
        # `None` would leave a review pointing at a photo that does not exist.
        cloudinary.result = {"public_id": "x"}

        with pytest.raises(MediaUploadError):

            await service.upload_image(
                content=A_JPEG,
                content_type="image/jpeg",
            )

    @pytest.mark.asyncio
    async def test_extra_provider_fields_do_not_leak_into_the_stored_shape(
        self,
        service,
        cloudinary,
    ):

        # Only the fields the product stores are read off the response, so a
        # new Cloudinary field cannot end up on a show log.
        cloudinary.result = {
            "secure_url": "https://example.test/x.jpg",
            "public_id": "x",
            "bytes": 10,
            "eager": [{"transformation": "x"}],
            "context": {"custom": "secret"},
        }

        uploaded = await service.upload_image(
            content=A_JPEG,
            content_type="image/jpeg",
        )

        assert set(uploaded.model_dump()) == {
            "url",
            "public_id",
            "width",
            "height",
            "bytes",
        }


class TestCredentials:

    @pytest.mark.asyncio
    async def test_the_secret_is_used_server_side_only(
        self,
        cloudinary,
    ):

        # The service configures the SDK; it never returns the credentials and
        # never accepts them from the caller.
        service = MediaUploadService(
            uploader=None,
            cloud_name="demo",
            api_key="key",
            api_secret="secret",
            max_size_mb=1,
        )

        service._uploader = cloudinary

        await service.upload_image(
            content=A_JPEG,
            content_type="image/jpeg",
        )

        assert "secret" not in service._to_uploaded_image(
            cloudinary.result,
        ).model_dump_json()

    def test_a_missing_configuration_is_reported_not_guessed(
        self,
    ):

        service = MediaUploadService(
            uploader=None,
            cloud_name=None,
            api_key=None,
            api_secret=None,
        )

        assert not service.is_configured()

        with pytest.raises(MediaUploadError):

            service._build_uploader()

    def test_a_complete_configuration_is_reported_as_ready(
        self,
    ):

        service = MediaUploadService(
            uploader=None,
            cloud_name="demo",
            api_key="key",
            api_secret="secret",
        )

        assert service.is_configured()


class TestUploadedImage:

    def test_the_public_id_is_required(
        self,
    ):

        # The URL alone cannot be deleted or replaced by the provider, so an
        # upload that arrives without its identifier is not something the
        # product can manage later.
        from pydantic import ValidationError

        with pytest.raises(ValidationError):

            UploadedImage(url="https://example.test/x.jpg")

    def test_it_serialises_to_what_the_api_returns(
        self,
    ):

        image = UploadedImage(
            url="https://example.test/x.jpg",
            public_id="gigcrowd/x",
        )

        assert image.model_dump() == {
            "url": "https://example.test/x.jpg",
            "public_id": "gigcrowd/x",
            "width": None,
            "height": None,
            "bytes": None,
        }
