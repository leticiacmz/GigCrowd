from datetime import datetime

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


    async def get_user_logs(
        self,
        user_id: str,
    ):

        cursor = self.collection.find(
            id_matches(
                "user_id",
                user_id,
            )
        )

        return await cursor.to_list(
            length=None,
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