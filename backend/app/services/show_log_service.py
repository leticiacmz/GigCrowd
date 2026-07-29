from datetime import UTC, datetime
from typing import Optional

from app.models.show_log import (
    AttendanceStatus,
    ShowLogCreate,
    ShowLogInDB,
    ShowLogUpdate,
)
from app.repositories.event_repository import EventRepository
from app.repositories.show_log_repository import ShowLogRepository


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

        if "_id" in document:
            document["_id"] = str(
                document["_id"]
            )

        return document

    async def create_show_log(
        self,
        user_id: str,
        show_log_data: ShowLogCreate,
    ) -> ShowLogInDB:

        event = await self.event_repository.get_by_id(
            show_log_data.event_id
        )

        if not event:
            raise ValueError(
                "Event not found"
            )

        now = datetime.now(UTC)

        event_date = event.starts_at

        if event_date.tzinfo is None:
            event_date = event_date.replace(
                tzinfo=UTC
            )

        if (
            show_log_data.status == AttendanceStatus.WENT
            and event_date > now
        ):
            raise ValueError(
                "You cannot mark an upcoming event as attended."
            )

        existing_log = await self.show_log_repository.collection.find_one(
            {
                "user_id": user_id,
                "event_id": show_log_data.event_id,
            }
        )

        if existing_log:

            update_data = show_log_data.model_dump(
                exclude_unset=True
            )

            update_data["updated_at"] = now

            await self.show_log_repository.collection.update_one(
                {
                    "_id": existing_log["_id"],
                },
                {
                    "$set": update_data,
                },
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

        show_log["user_id"] = user_id
        show_log["date"] = event.starts_at
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

        log = await self.show_log_repository.collection.find_one(
            {
                "user_id": user_id,
                "event_id": event_id,
            }
        )

        if not log:
            return None

        return ShowLogInDB(
            **self._normalize_id(log)
        )


    async def update_show_log(
        self,
        user_id: str,
        event_id: str,
        show_log_data: ShowLogUpdate,
    ) -> Optional[ShowLogInDB]:

        existing_log = await self.show_log_repository.collection.find_one(
            {
                "user_id": user_id,
                "event_id": event_id,
            }
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

        if (
            show_log_data.status == AttendanceStatus.WENT
        ):

            event = await self.event_repository.get_by_id(
                event_id
            )

            if event:

                event_date = event.starts_at

                if event_date.tzinfo is None:

                    event_date = event_date.replace(
                        tzinfo=UTC
                    )

                if event_date > datetime.now(UTC):

                    raise ValueError(
                        "Cannot mark an upcoming event as attended."
                    )

        update_data["updated_at"] = datetime.now(UTC)

        updated = await self.show_log_repository.collection.find_one_and_update(
            {
                "_id": existing_log["_id"],
            },
            {
                "$set": update_data,
            },
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
    ) -> ShowLogInDB:

        log = await self.show_log_repository.collection.find_one(
            {
                "user_id": user_id,
                "event_id": event_id,
            }
        )

        if not log:

            raise ValueError(
                "Show log not found"
            )

        if log["status"] != AttendanceStatus.WENT.value:

            raise ValueError(
                "Reviews can only be created for attended events."
            )

        update_data = {
            "rating": rating,
            "review": review,
            "updated_at": datetime.now(UTC),
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

        log = await self.show_log_repository.collection.find_one(
            {
                "user_id": user_id,
                "event_id": event_id,
            }
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
                    "rating": "",
                    "review": "",
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