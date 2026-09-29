from datetime import datetime, UTC

import pytest
from unittest.mock import AsyncMock

from app.domain.feed_activity import ActivityObjectType, ActivityType
from app.services.feed_activity_service import FeedActivityService


def build_service():

    repository = AsyncMock()
    follow_repository = AsyncMock()
    user_repository = AsyncMock()

    service = FeedActivityService(
        repository=repository,
        follow_repository=follow_repository,
        user_repository=user_repository,
    )

    return service, repository, follow_repository, user_repository


@pytest.mark.asyncio
async def test_record_user_follow_stores_generic_activity():

    service, repository, _, _ = build_service()

    await service.record_user_follow(
        actor_id="actor-1",
        followed_user_id="user-2",
        username="leticia",
    )

    activity = repository.create.call_args.args[0]

    assert activity.actor_id == "actor-1"
    assert activity.activity_type == ActivityType.USER_FOLLOWED_USER
    assert activity.object_type == ActivityObjectType.USER
    assert activity.object_id == "user-2"
    assert activity.payload == {"username": "leticia"}


@pytest.mark.asyncio
async def test_record_artist_follow_stores_artist_slug_as_object():

    service, repository, _, _ = build_service()

    await service.record_artist_follow(
        actor_id="actor-1",
        artist_slug="radiohead",
        artist_name="Radiohead",
    )

    activity = repository.create.call_args.args[0]

    assert activity.activity_type == ActivityType.USER_FOLLOWED_ARTIST
    assert activity.object_type == ActivityObjectType.ARTIST
    assert activity.object_id == "radiohead"
    assert activity.payload == {"artist_name": "Radiohead"}


@pytest.mark.asyncio
async def test_record_community_post_references_parent_artist():

    service, repository, _, _ = build_service()

    await service.record_community_post(
        actor_id="actor-1",
        post_id="post-1",
        artist_slug="radiohead",
        content="Amazing show last night",
    )

    activity = repository.create.call_args.args[0]

    assert activity.activity_type == ActivityType.COMMUNITY_POST_CREATED
    assert activity.object_type == ActivityObjectType.COMMUNITY_POST
    assert activity.object_id == "post-1"
    assert activity.target_type == ActivityObjectType.ARTIST
    assert activity.target_id == "radiohead"
    assert activity.payload["preview"] == "Amazing show last night"


@pytest.mark.asyncio
async def test_get_user_feed_includes_self_and_followed_actors():

    service, repository, follow_repository, user_repository = build_service()

    follow_repository.get_following_ids.return_value = ["actor-2", "actor-3"]
    repository.get_feed_for_actors.return_value = []
    repository.count_for_actors.return_value = 0
    user_repository.get_by_ids.return_value = []

    await service.get_user_feed("actor-1", limit=10, skip=0)

    actor_ids = repository.get_feed_for_actors.call_args.args[0]

    assert actor_ids == ["actor-1", "actor-2", "actor-3"]


@pytest.mark.asyncio
async def test_get_user_feed_returns_enriched_paginated_items():

    service, repository, follow_repository, user_repository = build_service()

    created_at = datetime.now(UTC)

    follow_repository.get_following_ids.return_value = ["actor-2"]

    repository.get_feed_for_actors.return_value = [
        {
            "_id": "activity-1",
            "actor_id": "actor-2",
            "activity_type": "community_post_created",
            "object_type": "community_post",
            "object_id": "post-1",
            "target_type": "artist",
            "target_id": "radiohead",
            "payload": {"artist_slug": "radiohead"},
            "created_at": created_at,
        }
    ]

    repository.count_for_actors.return_value = 5

    user_repository.get_by_ids.return_value = [
        {
            "_id": "actor-2",
            "username": "leticia",
            "avatar_url": "https://example.com/a.png",
        }
    ]

    page = await service.get_user_feed("actor-1", limit=1, skip=0)

    assert page.total == 5
    assert page.has_more is True
    assert page.next_skip == 1

    item = page.items[0]

    assert item.id == "activity-1"
    assert item.actor.username == "leticia"
    assert item.activity_type == ActivityType.COMMUNITY_POST_CREATED
    assert item.target_id == "radiohead"
    assert item.created_at == created_at


@pytest.mark.asyncio
async def test_get_user_feed_last_page_has_no_next_skip():

    service, repository, follow_repository, user_repository = build_service()

    follow_repository.get_following_ids.return_value = []
    repository.get_feed_for_actors.return_value = []
    repository.count_for_actors.return_value = 0
    user_repository.get_by_ids.return_value = []

    page = await service.get_user_feed("actor-1", limit=20, skip=0)

    assert page.items == []
    assert page.has_more is False
    assert page.next_skip is None
