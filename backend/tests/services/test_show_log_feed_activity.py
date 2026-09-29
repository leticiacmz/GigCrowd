from datetime import datetime, timedelta, UTC

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.domain.event import Event
from app.models.show_log import AttendanceStatus, ShowLogCreate
from app.services.show_log_service import ShowLogService


def build_service(existing_log=None):

    show_log_repository = MagicMock()
    show_log_repository.collection = AsyncMock()
    show_log_repository.collection.find_one.return_value = existing_log
    show_log_repository.count_by_status = AsyncMock(return_value=0)
    show_log_repository.delete_by_user_and_event = AsyncMock(return_value=True)

    event_repository = AsyncMock()
    event_repository.get_by_id.return_value = Event(
        id="event-1",
        venue_slug="venue",
        title="Radiohead at Madison Square Garden",
        starts_at=datetime.now(UTC) - timedelta(days=1),
    )

    feed_activity_service = AsyncMock()

    service = ShowLogService(
        show_log_repository,
        event_repository,
        feed_activity_service=feed_activity_service,
    )

    return service, show_log_repository, feed_activity_service


@pytest.mark.asyncio
async def test_create_show_log_records_attendance_activity():

    service, show_log_repository, feed_activity_service = build_service()

    show_log_repository.collection.insert_one.return_value = MagicMock(
        inserted_id="log-1"
    )

    await service.create_show_log(
        "user-1",
        ShowLogCreate(event_id="event-1", status=AttendanceStatus.WENT),
    )

    feed_activity_service.record_event_attendance.assert_awaited_once_with(
        actor_id="user-1",
        event_id="event-1",
        status="went",
        event_title="Radiohead at Madison Square Garden",
    )


@pytest.mark.asyncio
async def test_delete_show_log_removes_attendance_activity():

    service, _, feed_activity_service = build_service()

    await service.delete_show_log("user-1", "event-1")

    feed_activity_service.remove_event_attendance.assert_awaited_once_with(
        actor_id="user-1",
        event_id="event-1",
    )


@pytest.mark.asyncio
async def test_update_review_records_review_activity():

    now = datetime.now(UTC)

    existing_log = {
        "_id": "log-1",
        "user_id": "user-1",
        "event_id": "event-1",
        "status": AttendanceStatus.WENT.value,
        "created_at": now,
        "updated_at": now,
    }

    service, show_log_repository, feed_activity_service = build_service(
        existing_log
    )

    show_log_repository.collection.find_one_and_update.return_value = {
        **existing_log,
        "rating": 5,
        "review": "Unforgettable",
    }

    await service.update_review("user-1", "event-1", 5, "Unforgettable")

    feed_activity_service.record_review.assert_awaited_once_with(
        actor_id="user-1",
        review_id="log-1",
        event_id="event-1",
        rating=5,
    )


@pytest.mark.asyncio
async def test_delete_review_removes_review_activity():

    now = datetime.now(UTC)

    existing_log = {
        "_id": "log-1",
        "user_id": "user-1",
        "event_id": "event-1",
        "status": AttendanceStatus.WENT.value,
        "created_at": now,
        "updated_at": now,
    }

    service, show_log_repository, feed_activity_service = build_service(
        existing_log
    )

    show_log_repository.collection.find_one_and_update.return_value = existing_log

    await service.delete_review("user-1", "event-1")

    feed_activity_service.remove_review.assert_awaited_once_with(
        actor_id="user-1",
        review_id="log-1",
    )


@pytest.mark.asyncio
async def test_show_log_service_works_without_feed_service():

    show_log_repository = MagicMock()
    show_log_repository.collection = AsyncMock()
    show_log_repository.collection.find_one.return_value = None
    show_log_repository.collection.insert_one.return_value = MagicMock(
        inserted_id="log-1"
    )
    show_log_repository.count_by_status = AsyncMock(return_value=0)

    event_repository = AsyncMock()
    event_repository.get_by_id.return_value = Event(
        id="event-1",
        venue_slug="venue",
        title="Radiohead",
        starts_at=datetime.now(UTC) + timedelta(days=10),
    )

    service = ShowLogService(show_log_repository, event_repository)

    log = await service.create_show_log(
        "user-1",
        ShowLogCreate(event_id="event-1", status=AttendanceStatus.GOING),
    )

    assert log.status == AttendanceStatus.GOING
