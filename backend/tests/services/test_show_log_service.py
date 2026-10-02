"""Show logs, reviews and the events nobody could date.

The crash this file is named after: logging attendance for one of the many
imported events that carries neither `starts_at` nor `ends_at` raised
`AttributeError: 'NoneType' object has no attribute 'tzinfo'` and surfaced as a
500. The tests below pin the fix from both directions - no crash, and a
deliberate 400 - and cover the review rules that sit on top of attendance.
"""
from datetime import UTC, datetime, timedelta

import pytest
from bson import ObjectId

from app.domain.event_schedule import (
    EVENT_DATE_UNAVAILABLE,
    EventDateUnavailable,
)
from app.models.show_log import (
    AttendanceStatus,
    ShowLogCreate,
    ShowLogUpdate,
)
from app.repositories.event_repository import EventRepository
from app.repositories.show_log_repository import ShowLogRepository
from app.services.show_log_service import ShowLogService
from tests.support.fake_mongo import FakeDatabase


NOW = datetime.now(UTC)


def an_event(**fields) -> dict:
    """An event as it is actually stored: keyed by an `ObjectId`."""

    document = {
        "title": "Some Concert",
        "artist_slug": "some-artist",
        "artist_slugs": [],
        "venue_slug": "some-venue",
        "event_type": "Concert",
        "going_count": 0,
        "maybe_count": 0,
        "went_count": 0,
    }

    document.update(fields)

    document.setdefault(
        "_id",
        ObjectId("6a0000000000000000000001"),
    )

    return document


@pytest.fixture
def a_past_concert():

    return an_event(
        starts_at=NOW - timedelta(days=30),
    )


@pytest.fixture
def an_undated_event():
    """An event imported without any usable date.

    This shape is real: hundreds of rows in the events collection have neither
    `starts_at` nor `ends_at`.
    """

    return an_event(
        starts_at=None,
        ends_at=None,
    )


@pytest.fixture
def service():
    """A service over an in-memory database, plus the documents it holds."""

    db = FakeDatabase()

    service = ShowLogService(
        ShowLogRepository(db),
        EventRepository(db),
    )

    service.db = db

    return service


async def add_event(
    db,
    event: dict,
):

    """Store an event and return it with the string id a show log references."""

    await db.events.insert_one(event)

    event["id"] = str(event["_id"])

    return event


async def add_log(
    db,
    user_id: str = "user-1",
    event_id: str = "6a0000000000000000000001",
    **fields,
):

    document = {
        "_id": f"log-{user_id}-{event_id}",
        "user_id": user_id,
        "event_id": event_id,
        "status": AttendanceStatus.WENT.value,
        "date": NOW - timedelta(days=30),
        "created_at": NOW - timedelta(days=30),
        "updated_at": NOW - timedelta(days=30),
    }

    document.update(fields)

    await db.show_logs.insert_one(document)

    return document


class TestUndatedEventsDoNotCrash:

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "status",
        [
            AttendanceStatus.WENT,
            AttendanceStatus.GOING,
            AttendanceStatus.MAYBE,
        ],
    )
    async def test_every_status_reports_the_missing_date(
        self,
        service,
        an_undated_event,
        status,
    ):

        # This is the regression. Any status used to reach `event.starts_at`
        # and dereference `.tzinfo` on `None`.
        await add_event(service.db, an_undated_event)

        with pytest.raises(EventDateUnavailable) as raised:

            await service.create_show_log(
                "user-1",
                ShowLogCreate(
                    event_id=an_undated_event["id"],
                    status=status,
                ),
            )

        assert str(raised.value) == EVENT_DATE_UNAVAILABLE

    @pytest.mark.asyncio
    async def test_a_stored_date_is_never_null(
        self,
        service,
        an_undated_event,
    ):

        # A log must never be written with a null date, so the failed write
        # leaves no row behind for the profile to read.
        await add_event(service.db, an_undated_event)

        with pytest.raises(EventDateUnavailable):

            await service.create_show_log(
                "user-1",
                ShowLogCreate(
                    event_id=an_undated_event["id"],
                    status=AttendanceStatus.GOING,
                ),
            )

        assert await service.db.show_logs.count_documents({}) == 0

    @pytest.mark.asyncio
    async def test_the_error_is_a_value_error_so_the_route_answers_400(
        self,
        service,
        an_undated_event,
    ):

        # `routes/show_logs.py` already maps `ValueError` onto a 400; subclassing
        # it is what keeps an undated event a deliberate 400 rather than a 500.
        await add_event(service.db, an_undated_event)

        with pytest.raises(ValueError):

            await service.create_show_log(
                "user-1",
                ShowLogCreate(
                    event_id=an_undated_event["id"],
                    status=AttendanceStatus.WENT,
                ),
            )

    @pytest.mark.asyncio
    async def test_an_update_cannot_move_a_log_onto_an_undated_event(
        self,
        service,
        an_undated_event,
        a_past_concert,
    ):

        await add_event(service.db, an_undated_event)
        await add_event(service.db, a_past_concert)

        await add_log(
            service.db,
            event_id=a_past_concert["id"],
            status=AttendanceStatus.GOING.value,
        )

        with pytest.raises(EventDateUnavailable):

            await service.update_show_log(
                "user-1",
                an_undated_event["id"],
                ShowLogUpdate(status=AttendanceStatus.GOING),
            )


class TestCreateShowLog:

    @pytest.mark.asyncio
    async def test_a_past_concert_is_logged_with_its_own_date(
        self,
        service,
        a_past_concert,
    ):

        await add_event(service.db, a_past_concert)

        log = await service.create_show_log(
            "user-1",
            ShowLogCreate(
                event_id=a_past_concert["id"],
                status=AttendanceStatus.WENT,
            ),
        )

        assert log.date == a_past_concert["starts_at"]
        assert log.status == AttendanceStatus.WENT
        assert log.user_id == "user-1"

    @pytest.mark.asyncio
    async def test_an_upcoming_concert_cannot_be_marked_attended(
        self,
        service,
    ):

        event = an_event(
            starts_at=NOW + timedelta(days=30),
        )

        await add_event(service.db, event)

        with pytest.raises(ValueError) as raised:

            await service.create_show_log(
                "user-1",
                ShowLogCreate(
                    event_id=event["id"],
                    status=AttendanceStatus.WENT,
                ),
            )

        assert "upcoming" in str(raised.value)

    @pytest.mark.asyncio
    async def test_an_upcoming_concert_can_still_be_marked_going(
        self,
        service,
    ):

        event = an_event(
            starts_at=NOW + timedelta(days=30),
        )

        await add_event(service.db, event)

        log = await service.create_show_log(
            "user-1",
            ShowLogCreate(
                event_id=event["id"],
                status=AttendanceStatus.GOING,
            ),
        )

        assert log.status == AttendanceStatus.GOING

    @pytest.mark.asyncio
    async def test_a_running_festival_cannot_be_marked_attended(
        self,
        service,
    ):

        # The end date is what makes it "not over yet", so a festival in its
        # final day is still not something you can say you attended today.
        event = an_event(
            event_type="FestivalInstance",
            starts_at=NOW - timedelta(days=1),
            ends_at=NOW + timedelta(days=1),
        )

        await add_event(service.db, event)

        with pytest.raises(ValueError):

            await service.create_show_log(
                "user-1",
                ShowLogCreate(
                    event_id=event["id"],
                    status=AttendanceStatus.WENT,
                ),
            )

    @pytest.mark.asyncio
    async def test_an_unknown_event_is_rejected(
        self,
        service,
    ):

        with pytest.raises(ValueError) as raised:

            await service.create_show_log(
                "user-1",
                ShowLogCreate(
                    event_id="6a0000000000000000000099",
                    status=AttendanceStatus.GOING,
                ),
            )

        assert "not found" in str(raised.value)

    @pytest.mark.asyncio
    async def test_logging_twice_updates_the_same_row(
        self,
        service,
        a_past_concert,
    ):

        await add_event(service.db, a_past_concert)

        await service.create_show_log(
            "user-1",
            ShowLogCreate(
                event_id=a_past_concert["id"],
                status=AttendanceStatus.WENT,
            ),
        )

        await service.create_show_log(
            "user-1",
            ShowLogCreate(
                event_id=a_past_concert["id"],
                status=AttendanceStatus.MAYBE,
            ),
        )

        assert await service.db.show_logs.count_documents({}) == 1

    @pytest.mark.asyncio
    async def test_the_event_attendance_counters_are_refreshed(
        self,
        service,
        a_past_concert,
    ):

        await add_event(service.db, a_past_concert)

        await service.create_show_log(
            "user-1",
            ShowLogCreate(
                event_id=a_past_concert["id"],
                status=AttendanceStatus.WENT,
            ),
        )

        stored = await service.db.events.find_one(
            {"_id": ObjectId(a_past_concert["id"])}
        )

        assert stored["went_count"] == 1
        assert stored["going_count"] == 0
        assert stored["maybe_count"] == 0

    @pytest.mark.asyncio
    async def test_intent_alone_stores_no_review(
        self,
        service,
    ):
        """A review is only ever written for a show someone attended.

        The seed data and any client that posts a review alongside an intent
        used to store one on a `going` row, where the review endpoints would
        never read it and the profile counted a review nobody wrote.
        """
        event = an_event(
            starts_at=NOW + timedelta(days=30),
        )

        await add_event(service.db, event)

        log = await service.create_show_log(
            "user-1",
            ShowLogCreate(
                event_id=event["id"],
                status=AttendanceStatus.GOING,
                rating=5,
                review="Worth every second",
            ),
        )

        assert log.rating is None
        assert log.review is None

        stored = await service.db.show_logs.find_one({"user_id": "user-1"})

        assert stored is not None
        assert "review" not in stored
        assert "rating" not in stored


class TestReviewFollowsAttendance:

    @pytest.mark.asyncio
    async def test_a_review_is_written_with_a_photo(
        self,
        service,
        a_past_concert,
    ):

        await add_event(service.db, a_past_concert)

        await add_log(service.db, event_id=a_past_concert["id"])

        log = await service.update_review(
            user_id="user-1",
            event_id=a_past_concert["id"],
            rating=5,
            review="  Best set of the year.  ",
            photo_url="https://res.cloudinary.com/demo/image/upload/x.jpg",
            photo_public_id="gigcrowd/x",
        )

        assert log.rating == 5
        assert log.review == "Best set of the year."
        assert log.photo_url.endswith("x.jpg")
        assert log.photo_public_id == "gigcrowd/x"
        assert log.reviewed_at is not None

    @pytest.mark.asyncio
    async def test_a_review_needs_attendance(
        self,
        service,
        a_past_concert,
    ):

        # A rating for a show you did not attend would be a review of nothing.
        await add_event(service.db, a_past_concert)

        await add_log(
            service.db,
            event_id=a_past_concert["id"],
            status=AttendanceStatus.GOING.value,
        )

        with pytest.raises(ValueError) as raised:

            await service.update_review(
                user_id="user-1",
                event_id=a_past_concert["id"],
                rating=4,
                review="Great",
            )

        assert "attended" in str(raised.value)

    @pytest.mark.asyncio
    async def test_a_review_needs_an_existing_log(
        self,
        service,
        a_past_concert,
    ):

        await add_event(service.db, a_past_concert)

        with pytest.raises(ValueError) as raised:

            await service.update_review(
                user_id="user-1",
                event_id=a_past_concert["id"],
                rating=4,
                review="Great",
            )

        assert "not found" in str(raised.value)

    @pytest.mark.asyncio
    async def test_withdrawing_attendance_removes_the_review(
        self,
        service,
        a_past_concert,
    ):

        # The review only makes sense while the attendance stands, so it is
        # removed rather than left attached to a show you no longer claim.
        await add_event(service.db, a_past_concert)

        await add_log(
            service.db,
            event_id=a_past_concert["id"],
            rating=5,
            review="Amazing",
            photo_url="https://example.test/p.jpg",
            photo_public_id="p",
            reviewed_at=NOW,
        )

        log = await service.update_show_log(
            "user-1",
            a_past_concert["id"],
            ShowLogUpdate(status=AttendanceStatus.MAYBE),
        )

        stored = await service.db.show_logs.find_one(
            {"_id": log.id}
        )

        for field in (
            "rating",
            "review",
            "photo_url",
            "photo_public_id",
            "reviewed_at",
        ):
            assert field not in stored

    @pytest.mark.asyncio
    async def test_keeping_attendance_keeps_the_review(
        self,
        service,
        a_past_concert,
    ):

        await add_event(service.db, a_past_concert)

        await add_log(
            service.db,
            event_id=a_past_concert["id"],
            rating=4,
            review="Good",
            reviewed_at=NOW,
        )

        await service.update_show_log(
            "user-1",
            a_past_concert["id"],
            ShowLogUpdate(status=AttendanceStatus.WENT),
        )

        stored = await service.db.show_logs.find_one(
            {"_id": f"log-user-1-{a_past_concert['id']}"}
        )

        assert stored["rating"] == 4
        assert stored["review"] == "Good"

    @pytest.mark.asyncio
    async def test_a_review_can_be_deleted_but_the_attendance_stays(
        self,
        service,
        a_past_concert,
    ):

        await add_event(service.db, a_past_concert)

        await add_log(
            service.db,
            event_id=a_past_concert["id"],
            rating=3,
            review="Fine",
            reviewed_at=NOW,
        )

        log = await service.delete_review(
            "user-1",
            a_past_concert["id"],
        )

        assert log.status == AttendanceStatus.WENT
        assert not log.rating
        assert not log.review

    @pytest.mark.asyncio
    async def test_deleting_an_attendance_twice_reports_nothing_deleted(
        self,
        service,
        a_past_concert,
    ):

        await add_event(service.db, a_past_concert)

        await service.create_show_log(
            "user-1",
            ShowLogCreate(
                event_id=a_past_concert["id"],
                status=AttendanceStatus.WENT,
            ),
        )

        assert await service.delete_show_log(
            "user-1", a_past_concert["id"],
        )
        assert not await service.delete_show_log(
            "user-1", a_past_concert["id"],
        )


class TestUserLists:

    @pytest.mark.asyncio
    async def test_history_only_contains_attended_shows(
        self,
        service,
    ):

        went = an_event(
            _id="6a0000000000000000000001",
            starts_at=NOW - timedelta(days=10),
        )

        maybe = an_event(
            _id="6a0000000000000000000002",
            starts_at=NOW + timedelta(days=10),
        )

        await add_event(service.db, went)
        await add_event(service.db, maybe)

        await add_log(service.db, event_id=went["id"])
        await add_log(
            service.db,
            event_id=maybe["id"],
            status=AttendanceStatus.MAYBE.value,
        )

        history = await service.get_user_concert_history(
            "user-1"
        )

        assert [log.event_id for log in history] == [
            went["id"],
        ]

    @pytest.mark.asyncio
    async def test_lists_are_newest_first(
        self,
        service,
    ):

        older = an_event(
            _id="6a0000000000000000000001",
            starts_at=NOW - timedelta(days=100),
        )

        newer = an_event(
            _id="6a0000000000000000000002",
            starts_at=NOW - timedelta(days=5),
        )

        await add_event(service.db, older)
        await add_event(service.db, newer)

        await add_log(
            service.db,
            event_id=older["id"],
            date=older["starts_at"],
        )
        await add_log(
            service.db,
            event_id=newer["id"],
            date=newer["starts_at"],
        )

        logs = await service.get_user_show_logs("user-1")

        assert [log.event_id for log in logs] == [
            newer["id"],
            older["id"],
        ]

    @pytest.mark.asyncio
    async def test_a_status_filter_returns_each_event_in_one_state(
        self,
        service,
    ):

        # The profile counts and the lists behind them must not double count,
        # which they cannot if every event lives in exactly one state.
        went = an_event(
            _id="6a0000000000000000000001",
            starts_at=NOW - timedelta(days=10),
        )

        going = an_event(
            _id="6a0000000000000000000002",
            starts_at=NOW + timedelta(days=10),
        )

        await add_event(service.db, went)
        await add_event(service.db, going)

        await add_log(service.db, event_id=went["id"])
        await add_log(
            service.db,
            event_id=going["id"],
            status=AttendanceStatus.GOING.value,
        )

        attended = await service.get_user_show_logs(
            "user-1",
            status=AttendanceStatus.WENT,
        )

        planned = await service.get_user_show_logs(
            "user-1",
            status=AttendanceStatus.GOING,
        )

        assert [log.event_id for log in attended] == [went["id"]]
        assert [log.event_id for log in planned] == [going["id"]]

    @pytest.mark.asyncio
    async def test_reviews_are_only_the_logs_that_carry_one(
        self,
        service,
    ):

        # A bare star rating is a score, not something to put on a profile, so
        # it is not counted as a review.
        reviewed = an_event(
            _id="6a0000000000000000000001",
            starts_at=NOW - timedelta(days=10),
        )

        rated = an_event(
            _id="6a0000000000000000000002",
            starts_at=NOW - timedelta(days=20),
        )

        photographed = an_event(
            _id="6a0000000000000000000003",
            starts_at=NOW - timedelta(days=30),
        )

        for event in (reviewed, rated, photographed):
            await add_event(service.db, event)

        await add_log(
            service.db,
            event_id=reviewed["id"],
            review="Wonderful",
            reviewed_at=NOW - timedelta(days=1),
        )
        await add_log(
            service.db,
            event_id=rated["id"],
            rating=4,
            reviewed_at=NOW,
        )
        await add_log(
            service.db,
            event_id=photographed["id"],
            rating=5,
            photo_url="https://example.test/p.jpg",
            reviewed_at=NOW - timedelta(days=2),
        )

        reviews = await service.get_user_reviews("user-1")

        assert [review.event_id for review in reviews] == [
            reviewed["id"],
            photographed["id"],
        ]

    @pytest.mark.asyncio
    async def test_a_review_count_matches_the_full_list_not_the_page(
        self,
        service,
    ):

        for index in range(5):

            event = an_event(
                _id=f"6a00000000000000000000{index + 10:02d}",
                starts_at=NOW - timedelta(days=index + 1),
            )

            await add_event(service.db, event)

            await add_log(
                service.db,
                event_id=event["id"],
                review=f"Show {index}",
                reviewed_at=NOW - timedelta(days=index),
            )

        reviews = await service.get_user_reviews(
            "user-1",
            limit=2,
        )

        assert len(reviews) == 2
        assert await service.show_log_repository.count_user_reviews(
            "user-1",
        ) == 5

    @pytest.mark.asyncio
    async def test_a_log_stored_with_a_null_date_is_still_listed(
        self,
        service,
    ):

        # Legacy rows predate the schedule rules. They must not break the
        # profile, so they are returned rather than skipped.
        event = an_event(
            _id="6a0000000000000000000001",
        )

        await add_event(service.db, event)

        await add_log(
            service.db,
            event_id=event["id"],
            date=None,
        )

        logs = await service.get_user_show_logs("user-1")

        assert len(logs) == 1
        assert logs[0].date is None
