"""Attendance and reviews for events.

A show log is one user's record for one event: whether they are going, maybe,
or went. A review is extra content on a log whose attendance is `went`, and it
is stripped again the moment the attendance is withdrawn, so a review can never
outlive the show that justifies it.

Every rule about "has this event happened?" resolves through
`app.domain.event_schedule`, because imported events are inconsistent about
dates and some carry none at all.
"""
from datetime import UTC, datetime
from typing import Optional

from app.domain.event_schedule import (
    is_past,
    require_event_date,
)
from app.models.show_log import (
    AttendanceStatus,
    ShowLogCreate,
    ShowLogInDB,
    ShowLogUpdate,
)
from app.repositories.event_repository import EventRepository
from app.repositories.show_log_repository import ShowLogRepository


# Fields that only make sense on a log that records attendance. They are
# removed whenever a log is moved out of the "went" state, so a review can
# never survive the attendance that justifies it.
REVIEW_FIELDS = (
    "rating",
    "review",
    "photo_url",
    "photo_public_id",
    "reviewed_at",
)


class ShowLogService:

    def __init__(
        self,
        show_log_repository: ShowLogRepository,
        event_repository: EventRepository,
    ):

        self.show_log_repository = show_log_repository
        self.event_repository = event_repository

    @staticmethod
    def _normalize_id(document: dict):
        """Stored ids come back in whatever form they were written."""

        if "_id" in document:
            document["_id"] = str(
                document["_id"]
            )

        return document

    @staticmethod
    def _assert_attended_event_is_past(event):
        """Guard the one rule about "I went": the show has to have happened.

        `is_past` reads the event's own dates, and an event without any date
        is never past, so the same call also rejects an undated event instead
        of reaching for a date that does not exist.
        """

        if not is_past(event):
            raise ValueError(
                "You cannot mark an upcoming event as attended."
            )

    @staticmethod
    def _review_unset(
        status: Optional[AttendanceStatus],
    ) -> dict:
        """The `$unset` half of an update, empty while attendance is `went`.

        The fields are removed rather than blanked so a withdrawn review
        leaves nothing behind for the profile to read.
        """

        if status == AttendanceStatus.WENT:
            return {}

        return {
            field: ""
            for field in REVIEW_FIELDS
        }

    async def _assert_event_can_be_logged(
        self,
        event_id: str,
        status: AttendanceStatus,
    ):
        """Resolve an event for a log about to be written.

        Raises `ValueError` (a 400 at the route) when the event does not
        exist, carries no date, or is still in the future and cannot be marked
        as attended.
        """

        event = await self.event_repository.get_by_id(
            event_id
        )

        if not event:
            raise ValueError(
                "Event not found"
            )

        # Required for every status: a log must never store a null date,
        # because "going" is meaningless on an event nobody can place in time.
        # An undated event raises `EventDateUnavailable` here instead of the
        # `None.tzinfo` crash this used to produce further down.
        require_event_date(event)

        if status == AttendanceStatus.WENT:
            self._assert_attended_event_is_past(event)

        return event

    async def create_show_log(
        self,
        user_id: str,
        show_log_data: ShowLogCreate,
    ) -> ShowLogInDB:

        event = await self._assert_event_can_be_logged(
            show_log_data.event_id,
            show_log_data.status,
        )

        now = datetime.now(UTC)

        event_moment = require_event_date(event)

        existing_log = await self.show_log_repository.collection.find_one(
            self.show_log_repository.pair_query(
                user_id,
                show_log_data.event_id,
            )
        )

        if existing_log:

            update_data = show_log_data.model_dump(
                exclude_unset=True
            )

            update_data["updated_at"] = now

            update = {
                "$set": update_data,
            }

            unset = self._review_unset(
                show_log_data.status
            )

            if unset:
                update["$unset"] = unset

            await self.show_log_repository.collection.update_one(
                {
                    "_id": existing_log["_id"],
                },
                update,
            )

            updated = await self.show_log_repository.collection.find_one(
                {
                    "_id": existing_log["_id"],
                }
            )

            await self._refresh_event_counts(
                show_log_data.event_id
            )

            return ShowLogInDB(
                **self._normalize_id(updated)
            )

        show_log = show_log_data.model_dump()

        # A log created without attendance carries no review, so the review is
        # never born on a row that could not justify it. The same fields are
        # unset again the moment attendance is withdrawn.
        for field in self._review_unset(
            show_log_data.status
        ):
            show_log.pop(field, None)

        show_log["user_id"] = user_id
        show_log["date"] = event_moment
        show_log["created_at"] = now
        show_log["updated_at"] = now

        result = await self.show_log_repository.collection.insert_one(
            show_log
        )

        show_log["_id"] = str(
            result.inserted_id
        )

        await self._refresh_event_counts(
            show_log_data.event_id
        )

        return ShowLogInDB(
            **self._normalize_id(show_log)
        )

    async def get_show_log(
        self,
        user_id: str,
        event_id: str,
    ) -> Optional[ShowLogInDB]:

        log = await self.show_log_repository.get_by_user_and_event(
            user_id,
            event_id,
        )

        if not log:
            return None

        return ShowLogInDB(
            **self._normalize_id(log)
        )

    async def get_user_show_logs(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 50,
        status: AttendanceStatus | None = None,
    ) -> list[ShowLogInDB]:
        """One user's show logs, most recent first.

        A single log exists per event, so the status filter returns each event
        in exactly one state and the lists behind the profile counts cannot
        overlap.
        """

        logs = await self.show_log_repository.get_user_logs(
            user_id,
            status=status,
            skip=skip,
            limit=limit,
        )

        return [
            ShowLogInDB(
                **self._normalize_id(log)
            )
            for log in logs
        ]

    async def get_user_concert_history(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ShowLogInDB]:
        """The shows a user says they attended, most recent first."""

        logs = await self.show_log_repository.get_user_logs(
            user_id,
            status=AttendanceStatus.WENT,
            skip=skip,
            limit=limit,
        )

        return [
            ShowLogInDB(
                **self._normalize_id(log)
            )
            for log in logs
        ]

    async def get_user_reviews(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ShowLogInDB]:
        """A user's reviews, most recently written first."""

        logs = await self.show_log_repository.get_user_reviews(
            user_id,
            skip=skip,
            limit=limit,
        )

        return [
            ShowLogInDB(
                **self._normalize_id(log)
            )
            for log in logs
        ]

    async def update_show_log(
        self,
        user_id: str,
        event_id: str,
        show_log_data: ShowLogUpdate,
    ) -> Optional[ShowLogInDB]:

        existing_log = await self.show_log_repository.get_by_user_and_event(
            user_id,
            event_id,
        )

        if not existing_log:
            return None

        update_data = show_log_data.model_dump(
            exclude_unset=True
        )

        if not update_data:

            return ShowLogInDB(
                **self._normalize_id(existing_log)
            )

        if show_log_data.status is not None:

            await self._assert_event_can_be_logged(
                event_id,
                show_log_data.status,
            )

        update_data["updated_at"] = datetime.now(UTC)

        update = {
            "$set": update_data,
        }

        unset = self._review_unset(
            show_log_data.status
        )

        if unset:
            update["$unset"] = unset

        updated = await self.show_log_repository.collection.find_one_and_update(
            {
                "_id": existing_log["_id"],
            },
            update,
            return_document=True,
        )

        await self._refresh_event_counts(
            event_id
        )

        return ShowLogInDB(
            **self._normalize_id(updated)
        )

    async def delete_show_log(
        self,
        user_id: str,
        event_id: str,
    ) -> bool:

        deleted = await self.show_log_repository.delete_by_user_and_event(
            user_id,
            event_id,
        )

        if deleted:

            await self._refresh_event_counts(
                event_id
            )

        return deleted

    async def update_review(
        self,
        user_id: str,
        event_id: str,
        rating: int,
        review: str | None,
        photo_url: str | None = None,
        photo_public_id: str | None = None,
    ) -> ShowLogInDB:

        log = await self.show_log_repository.get_by_user_and_event(
            user_id,
            event_id,
        )

        if not log:

            raise ValueError(
                "Show log not found"
            )

        if log["status"] != AttendanceStatus.WENT.value:

            raise ValueError(
                "Reviews can only be created for attended events."
            )

        now = datetime.now(UTC)

        update_data = {
            "rating": rating,
            "review": (review or "").strip() or None,
            "photo_url": photo_url,
            "photo_public_id": photo_public_id,
            "reviewed_at": now,
            "updated_at": now,
        }

        updated = await self.show_log_repository.collection.find_one_and_update(
            {
                "_id": log["_id"],
            },
            {
                "$set": update_data,
            },
            return_document=True,
        )

        return ShowLogInDB(
            **self._normalize_id(updated)
        )

    async def delete_review(
        self,
        user_id: str,
        event_id: str,
    ) -> ShowLogInDB:

        log = await self.show_log_repository.get_by_user_and_event(
            user_id,
            event_id,
        )

        if not log:

            raise ValueError(
                "Show log not found"
            )

        updated = await self.show_log_repository.collection.find_one_and_update(
            {
                "_id": log["_id"],
            },
            {
                "$unset": {
                    field: ""
                    for field in REVIEW_FIELDS
                },
                "$set": {
                    "updated_at": datetime.now(UTC),
                },
            },
            return_document=True,
        )

        return ShowLogInDB(
            **self._normalize_id(updated)
        )

    async def _refresh_event_counts(
        self,
        event_id: str,
    ):

        going = await self.show_log_repository.count_by_status(
            event_id,
            AttendanceStatus.GOING.value,
        )

        maybe = await self.show_log_repository.count_by_status(
            event_id,
            AttendanceStatus.MAYBE.value,
        )

        went = await self.show_log_repository.count_by_status(
            event_id,
            AttendanceStatus.WENT.value,
        )

        await self.event_repository.update_attendance_counts(
            event_id,
            going,
            maybe,
            went,
        )
