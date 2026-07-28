from app.repositories.base import BaseRepository


class ShowLogRepository(BaseRepository):


    def __init__(self, db):

        super().__init__(
            db,
            "show_logs"
        )


    async def get_user_logs(
        self,
        user_id: str
    ):

        cursor = self.collection.find(
            {
                "user_id": user_id
            }
        )


        return await cursor.to_list(
            length=None
        )

    async def get_by_user_and_event(
        self,
        user_id: str,
        event_id: str,
    ):

        return await self.collection.find_one(
            {
                "user_id": user_id,
                "event_id": event_id,
            }
        )
    
    async def delete_by_user_and_event(
    self,
    user_id: str,
        event_id: str,
    ):

        result = await self.collection.delete_one(
            {
                "user_id": user_id,
                "event_id": event_id,
            }
        )

        return result.deleted_count > 0
    
    async def count_by_status(
        self,
        event_id: str,
        status: str,
    ):

        return await self.collection.count_documents(
            {
                "event_id": event_id,
                "status": status,
            }
        )
    
    async def get_user_status(
        self,
        user_id: str,
        event_id: str,
        ):

        log = await self.collection.find_one(
            {
                "user_id": user_id,
                "event_id": event_id,
            }
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
                "$match": {
                    "event_id": event_id
                }
            },
            {
                "$group": {
                    "_id": "$status",
                    "count": {
                        "$sum": 1
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