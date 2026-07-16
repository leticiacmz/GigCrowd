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