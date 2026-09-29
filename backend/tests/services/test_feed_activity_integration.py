import pytest
from unittest.mock import AsyncMock

from app.services.artist_follow_service import ArtistFollowService
from app.services.follow_service import FollowService


@pytest.mark.asyncio
async def test_follow_user_records_feed_activity():

    follow_repository = AsyncMock()
    follow_repository.exists.return_value = False

    user_repository = AsyncMock()
    user_repository.get_by_username.return_value = {"_id": "user-2"}

    feed_activity_service = AsyncMock()

    service = FollowService(
        follow_repository=follow_repository,
        user_repository=user_repository,
        feed_activity_service=feed_activity_service,
    )

    await service.follow_user("user-1", "leticia")

    feed_activity_service.record_user_follow.assert_awaited_once_with(
        actor_id="user-1",
        followed_user_id="user-2",
        username="leticia",
    )


@pytest.mark.asyncio
async def test_unfollow_user_removes_feed_activity():

    follow_repository = AsyncMock()
    follow_repository.delete.return_value = True

    user_repository = AsyncMock()
    user_repository.get_by_username.return_value = {"_id": "user-2"}

    feed_activity_service = AsyncMock()

    service = FollowService(
        follow_repository=follow_repository,
        user_repository=user_repository,
        feed_activity_service=feed_activity_service,
    )

    await service.unfollow_user("user-1", "leticia")

    feed_activity_service.remove_user_follow.assert_awaited_once_with(
        actor_id="user-1",
        followed_user_id="user-2",
    )


@pytest.mark.asyncio
async def test_follow_user_without_feed_service_still_works():

    follow_repository = AsyncMock()
    follow_repository.exists.return_value = False

    user_repository = AsyncMock()
    user_repository.get_by_username.return_value = {"_id": "user-2"}

    service = FollowService(
        follow_repository=follow_repository,
        user_repository=user_repository,
    )

    await service.follow_user("user-1", "leticia")

    follow_repository.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_follow_artist_records_feed_activity():

    repository = AsyncMock()
    repository.exists.return_value = False

    artist_repository = AsyncMock()
    artist_repository.get_by_slug.return_value = {
        "slug": "radiohead",
        "name": "Radiohead",
    }

    feed_activity_service = AsyncMock()

    service = ArtistFollowService(
        repository=repository,
        artist_repository=artist_repository,
        feed_activity_service=feed_activity_service,
    )

    await service.follow("user-1", "radiohead")

    feed_activity_service.record_artist_follow.assert_awaited_once_with(
        actor_id="user-1",
        artist_slug="radiohead",
        artist_name="Radiohead",
    )


@pytest.mark.asyncio
async def test_follow_artist_twice_does_not_duplicate_activity():

    repository = AsyncMock()
    repository.exists.return_value = True

    artist_repository = AsyncMock()
    artist_repository.get_by_slug.return_value = {"slug": "radiohead"}

    feed_activity_service = AsyncMock()

    service = ArtistFollowService(
        repository=repository,
        artist_repository=artist_repository,
        feed_activity_service=feed_activity_service,
    )

    await service.follow("user-1", "radiohead")

    feed_activity_service.record_artist_follow.assert_not_awaited()


@pytest.mark.asyncio
async def test_unfollow_artist_removes_feed_activity():

    repository = AsyncMock()

    artist_repository = AsyncMock()

    feed_activity_service = AsyncMock()

    service = ArtistFollowService(
        repository=repository,
        artist_repository=artist_repository,
        feed_activity_service=feed_activity_service,
    )

    await service.unfollow("user-1", "radiohead")

    feed_activity_service.remove_artist_follow.assert_awaited_once_with(
        actor_id="user-1",
        artist_slug="radiohead",
    )
