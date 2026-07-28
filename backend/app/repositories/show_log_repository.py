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