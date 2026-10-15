"""The rule that decides what a review is, held from every door.

An opinion is a rating or some words. Both are optional one at a time - a
bare star rating and a written paragraph are each complete - but together
they are never optional: a photo alone is evidence rather than an opinion,
an empty submission says nothing, and a text of only spaces says nothing
too. Three doors write reviews (a log created with attendance, a review
written on its own, an edit of one already written) and one service takes
them directly; each is pinned here with the same scenarios. Reading is
pinned as the deliberately broader rule so rows recorded under the older
scheme keep counting as what they already are.
"""
from datetime import UTC, datetime, timedelta

import pytest
from bson import ObjectId
from pydantic import ValidationError

from app.domain.show_log import (
    log_carries_review,
    stored_rating,
)
from app.models.show_log import (
    AttendanceStatus,
    ReviewUpsert,
    ShowLogCreate,
    ShowLogUpdate,
)
from app.repositories.event_repository import EventRepository
from app.repositories.show_log_repository import ShowLogRepository
from app.services.show_log_service import ShowLogService
from tests.support.fake_mongo import FakeDatabase


NOW = datetime.now(UTC)

EVENT_ID = "6a0000000000000000000001"

USER_ID = "user-1"

PHOTO = "https://example.test/p.jpg"

NEEDS_AN_OPINION = "rating or some words"


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


async def seed_a_went_show(db):
    """An event thirty days past with the attended log already on it."""

    await db.events.insert_one(
        {
            "_id": ObjectId(EVENT_ID),
            "title": "Some Concert",
            "artist_slug": "some-artist",
            "artist_slugs": [],
            "venue_slug": "some-venue",
            "event_type": "Concert",
            "starts_at": NOW - timedelta(days=30),
            "ends_at": NOW - timedelta(days=30),
            "going_count": 0,
            "maybe_count": 0,
            "went_count": 1,
        }
    )

    await db.show_logs.insert_one(
        {
            "_id": f"log-{USER_ID}-{EVENT_ID}",
            "user_id": USER_ID,
            "event_id": EVENT_ID,
            "status": AttendanceStatus.WENT.value,
            "date": NOW - timedelta(days=30),
            "created_at": NOW - timedelta(days=30),
            "updated_at": NOW - timedelta(days=30),
        }
    )


def a_went_log(**fields) -> dict:
    """The body of a log created with attendance and an opinion."""

    return {
        "event_id": EVENT_ID,
        "status": AttendanceStatus.WENT,
        **fields,
    }


class TestTheReviewItselfNeedsAnOpinion:
    """`ReviewUpsert` - the door the review dialog writes through."""

    def test_a_rating_alone_is_an_opinion(self):

        body = ReviewUpsert(rating=4)

        assert body.rating == 4
        assert body.review is None

    def test_a_text_alone_is_an_opinion(self):

        body = ReviewUpsert(review="Loud, tight, worth the trip")

        assert body.rating is None
        assert body.review == "Loud, tight, worth the trip"

    @pytest.mark.parametrize(
        "fields",
        [
            {"rating": 5, "review": "Encore!"},
            {"review": "Encore!", "photo_url": PHOTO},
            {"rating": 3, "photo_url": PHOTO},
            {"rating": 3, "review": "Encore!", "photo_url": PHOTO},
        ],
    )
    def test_an_opinion_with_detail_is_accepted(self, fields):

        # Constructing the body without raising is the acceptance; each
        # shape is a review the product promises to keep.
        ReviewUpsert(**fields)

    def test_a_photo_alone_is_refused(self):

        with pytest.raises(ValidationError, match=NEEDS_AN_OPINION):

            ReviewUpsert(photo_url=PHOTO)

    def test_an_empty_submission_is_refused(self):

        with pytest.raises(ValidationError, match=NEEDS_AN_OPINION):

            ReviewUpsert()

    @pytest.mark.parametrize("text", ["   ", "\t", "\n"])
    def test_a_text_that_says_nothing_is_refused(self, text):

        with pytest.raises(ValidationError, match=NEEDS_AN_OPINION):

            ReviewUpsert(review=text)

        with pytest.raises(ValidationError, match=NEEDS_AN_OPINION):

            ReviewUpsert(
                review=text,
                photo_url=PHOTO,
            )

    @pytest.mark.parametrize("rating", [0, -1, 6])
    def test_a_rating_outside_the_stars_is_refused(self, rating):

        with pytest.raises(ValidationError):

            ReviewUpsert(rating=rating)


class TestAReviewWrittenWithAttendance:
    """`ShowLogCreate` - attendance and an opinion in one call."""

    def test_a_rating_alone_is_accepted(self):

        body = ShowLogCreate(**a_went_log(rating=4))

        assert body.rating == 4
        assert body.review is None

    def test_a_text_alone_leaves_the_rating_absent(self):

        body = ShowLogCreate(
            **a_went_log(review="Worth every minute")
        )

        assert body.rating is None
        assert body.review == "Worth every minute"

    def test_a_photo_alone_is_refused(self):

        with pytest.raises(ValidationError, match=NEEDS_AN_OPINION):

            ShowLogCreate(
                **a_went_log(photo_url=PHOTO)
            )

    def test_a_text_that_says_nothing_is_refused(self):

        with pytest.raises(ValidationError, match=NEEDS_AN_OPINION):

            ShowLogCreate(
                **a_went_log(review="   ")
            )

    def test_attendance_with_nothing_to_say_is_accepted(self):

        # Marking "I went" without writing anything is the common case and
        # never was an attempt at a review; the body holds no opinion and
        # the rule has nothing to judge.
        body = ShowLogCreate(**a_went_log())

        assert body.rating is None
        assert body.review is None

    def test_content_on_an_unattended_status_is_not_judged(self):

        # A `going` log drops the review fields on the way in, so the rule
        # only judges a log that will actually carry the review.
        body = ShowLogCreate(
            event_id=EVENT_ID,
            status=AttendanceStatus.GOING,
            rating=5,
            review="Cannot wait",
        )

        assert body.rating == 5


class TestAnEditFollowsTheSameRule:
    """`ShowLogUpdate` - the same opinion rule on the way back in."""

    def test_a_rating_alone_is_accepted(self):

        patch = ShowLogUpdate(rating=4)

        assert patch.rating == 4

    def test_a_text_alone_leaves_the_rating_absent(self):

        patch = ShowLogUpdate(review="Better than expected")

        assert patch.rating is None
        assert patch.review == "Better than expected"

    def test_a_photo_alone_is_refused(self):

        with pytest.raises(ValidationError, match=NEEDS_AN_OPINION):

            ShowLogUpdate(photo_url=PHOTO)

    def test_a_text_that_says_nothing_is_refused(self):

        with pytest.raises(ValidationError, match=NEEDS_AN_OPINION):

            ShowLogUpdate(review="   ")

    def test_a_patch_that_states_no_review_passes(self):

        # Attendance changes say nothing about the review half, and are
        # exactly what the attendance buttons send.
        patch = ShowLogUpdate(status=AttendanceStatus.GOING)

        assert patch.rating is None
        assert patch.review is None


class TestTheServiceHoldsTheRuleForDirectCallers:
    """`ShowLogService.update_review` - the door without the schema in front."""

    @pytest.mark.asyncio
    async def test_a_rating_alone_is_stored_as_itself(
        self,
        service,
    ):

        await seed_a_went_show(service.db)

        log = await service.update_review(
            USER_ID,
            EVENT_ID,
            rating=4,
            review=None,
        )

        assert log.rating == 4
        assert log.review is None
        assert log.reviewed_at is not None

    @pytest.mark.asyncio
    async def test_a_text_alone_is_stored_with_the_rating_absent(
        self,
        service,
    ):

        await seed_a_went_show(service.db)

        log = await service.update_review(
            USER_ID,
            EVENT_ID,
            rating=None,
            review="Worth every minute",
        )

        # Absence, not a zero: storage says the rating was never stated.
        assert log.rating is None
        assert log.review == "Worth every minute"

    @pytest.mark.asyncio
    async def test_a_photo_alone_is_an_error(self,
        service,
    ):

        await seed_a_went_show(service.db)

        with pytest.raises(ValueError, match=NEEDS_AN_OPINION):

            await service.update_review(
                USER_ID,
                EVENT_ID,
                rating=None,
                review=None,
                photo_url=PHOTO,
            )

    @pytest.mark.asyncio
    async def test_a_text_that_says_nothing_is_an_error(
        self,
        service,
    ):

        await seed_a_went_show(service.db)

        with pytest.raises(ValueError, match=NEEDS_AN_OPINION):

            await service.update_review(
                USER_ID,
                EVENT_ID,
                rating=None,
                review="   ",
            )


class TestReadingKeepsWhatWasAlreadyRecorded:
    """Reading is broader than writing, on purpose.

    The listing, the profile's review marker, the lifecycle prompt and the
    feed all ask one question of a stored log - does it carry an opinion -
    and all four must answer it the same way, keeping rows written under
    the older rule while refusing rows that say nothing at all.
    """

    @pytest.mark.asyncio
    async def test_a_rating_only_log_is_a_review(
        self,
        service,
    ):

        await seed_a_went_show(service.db)

        await service.show_log_repository.collection.update_one(
            {"_id": f"log-{USER_ID}-{EVENT_ID}"},
            {"$set": {"rating": 4}},
        )

        reviews = await service.get_user_reviews(USER_ID)

        assert len(reviews) == 1
        assert reviews[0].rating == 4
        assert log_carries_review(reviews[0].model_dump()) is True

    @pytest.mark.asyncio
    async def test_a_legacy_photo_only_log_is_still_a_review(
        self,
        service,
    ):

        await seed_a_went_show(service.db)

        await service.show_log_repository.collection.update_one(
            {"_id": f"log-{USER_ID}-{EVENT_ID}"},
            {"$set": {"photo_url": PHOTO}},
        )

        reviews = await service.get_user_reviews(USER_ID)

        assert len(reviews) == 1
        assert reviews[0].rating is None

    @pytest.mark.asyncio
    async def test_a_log_without_an_opinion_is_not_a_review(
        self,
        service,
    ):

        await seed_a_went_show(service.db)

        reviews = await service.get_user_reviews(USER_ID)

        assert reviews == []
        assert log_carries_review({"status": "went"}) is False

    @pytest.mark.parametrize(
        "log, expected",
        [
            ({"review": "Great night"}, True),
            ({"review": "   "}, False),
            ({"photo_url": PHOTO}, True),
            ({"rating": 5}, True),
            ({"rating": 0}, False),
            ({"rating": None}, False),
            ({"rating": ""}, False),
            ({"rating": True}, False),
            ({"status": "went"}, False),
        ],
    )
    def test_the_reading_rule_sees_opinions_and_nothing_else(
        self,
        log,
        expected,
    ):

        assert log_carries_review(log) is expected

    @pytest.mark.parametrize(
        "log, expected",
        [
            ({"rating": 5}, 5),
            ({}, None),
            ({"rating": None}, None),
            ({"rating": ""}, None),
            ({"rating": 0}, None),
            ({"rating": True}, None),
        ],
    )
    def test_a_rating_that_was_never_stated_reads_as_absence(
        self,
        log,
        expected,
    ):

        assert stored_rating(log) is expected
