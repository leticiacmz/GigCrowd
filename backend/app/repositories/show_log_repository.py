from datetime import UTC, datetime
from typing import Optional

from app.repositories.base import BaseRepository
from app.utils.ids import id_matches, ids_match


class ShowLogRepository(BaseRepository):


    def __init__(self, db):

        super().__init__(
            db,
            "show_logs",
        )


    @staticmethod
    def _pair_query(
        user_id: str,
        event_id: str,
    ) -> dict:
        """Match one user's log for one event.

        Both identifiers are matched in either storage form so an existing log
        is always found, updated and deleted.
        """

        return {
            **id_matches("user_id", user_id),
            **id_matches("event_id", event_id),
        }


    def pair_query(
        self,
        user_id: str,
        event_id: str,
    ) -> dict:
        """The query for one user's log of one event.

        Exposed so the service can reach an existing log in the same way the
        repository does, instead of restating the matching rule.
        """

        return self._pair_query(
            user_id,
            event_id,
        )


    async def get_user_logs(
        self,
        user_id: str,
        status=None,
        skip: int = 0,
        limit: Optional[int] = 50,
    ):
        """One user's show logs, most recent first.

        A single log exists per event, so filtering by status returns each
        event in exactly one state. The logs are ordered by the event date the
        log records, which is the field that answers "when was this show?".
        """

        query = id_matches("user_id", user_id)

        if status is not None:

            query["status"] = (
                status.value
                if hasattr(status, "value")
                else status
            )

        cursor = (
            self.collection
            .find(query)
            .sort("date", -1)
            .skip(max(0, skip))
        )

        if limit is not None:

            cursor = cursor.limit(limit)

        return await cursor.to_list(
            length=None,
        )


    @staticmethod
    def _review_query(
        user_id: str,
    ) -> dict:
        """Match the logs of one user that carry a review.

        A review needs more than a rating: text or a photo is what makes it
        worth showing, so a bare star rating is not counted as one.
        """

        return {
            **id_matches("user_id", user_id),
            # `$exists` is part of the clause on purpose: in MongoDB `$nin`
            # also matches a document where the field is absent, which would
            # make every bare star rating count as a review.
            "$or": [
                {
                    "review": {
                        "$exists": True,
                        "$nin": [None, ""],
                    }
                },
                {
                    "photo_url": {
                        "$exists": True,
                        "$nin": [None, ""],
                    }
                },
            ],
        }


    async def get_user_reviews(
        self,
        user_id: str,
        skip: int = 0,
        limit: Optional[int] = 50,
    ):
        """The logs that carry a review, most recently reviewed first."""

        cursor = (
            self.collection
            .find(
                self._review_query(user_id),
            )
            .sort("reviewed_at", -1)
            .skip(max(0, skip))
        )

        if limit is not None:

            cursor = cursor.limit(limit)

        return await cursor.to_list(
            length=None,
        )


    async def count_user_reviews(
        self,
        user_id: str,
    ) -> int:

        return await self.collection.count_documents(
            self._review_query(user_id),
        )


    async def get_by_user_and_event(
        self,
        user_id: str,
        event_id: str,
    ):

        return await self.collection.find_one(
            self._pair_query(
                user_id,
                event_id,
            )
        )


    async def delete_by_user_and_event(
        self,
        user_id: str,
        event_id: str,
    ):

        result = await self.collection.delete_one(
            self._pair_query(
                user_id,
                event_id,
            )
        )

        return result.deleted_count > 0


    async def count_by_status(
        self,
        event_id: str,
        status: str,
    ):

        return await self.collection.count_documents(
            {
                **ids_match("event_id", [event_id]),
                "status": status,
            }
        )


    async def count_user_logs(
        self,
        user_id: str,
        status=None,
    ) -> int:
        """How many logs a user holds, optionally in one status.

        Counted from the collection rather than from the length of a page, so
        the number a profile shows always matches the full list behind it.
        """

        query = id_matches("user_id", user_id)

        if status is not None:

            query["status"] = (
                status.value
                if hasattr(status, "value")
                else status
            )

        return await self.collection.count_documents(
            query
        )


    async def get_user_status(
        self,
        user_id: str,
        event_id: str,
    ):

        log = await self.collection.find_one(
            self._pair_query(
                user_id,
                event_id,
            )
        )

        if not log:
            return None

        return log["status"]


    async def get_attendance_summary(
        self,
        event_id: str,
    ):

        pipeline = [
            {
                "$match": ids_match(
                    "event_id",
                    [event_id],
                )
            },
            {
                "$group": {
                    "_id": "$status",
                    "count": {
                        "$sum": 1,
                    }
                }
            }
        ]

        cursor = self.collection.aggregate(
            pipeline
        )

        result = {}

        async for item in cursor:
            result[item["_id"]] = item["count"]

        return result


    async def update_review(
        self,
        user_id: str,
        event_id: str,
        rating: int,
        review: str | None,
    ):

        await self.collection.update_one(
            self._pair_query(
                user_id,
                event_id,
            ),
            {
                "$set": {
                    "rating": rating,
                    "review": review,
                    "reviewed_at": datetime.utcnow(),
                }
            },
        )

        return await self.get_by_user_and_event(
            user_id,
            event_id,
        )


    async def delete_review(
        self,
        user_id: str,
        event_id: str,
    ):

        await self.collection.update_one(
            self._pair_query(
                user_id,
                event_id,
            ),
            {
                "$unset": {
                    "rating": "",
                    "review": "",
                    "reviewed_at": "",
                }
            },
        )

        return await self.get_by_user_and_event(
            user_id,
            event_id,
        )