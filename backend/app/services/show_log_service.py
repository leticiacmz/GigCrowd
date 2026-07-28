from app.repositories.event_repository import EventRepository
from app.repositories.show_log_repository import ShowLogRepository

from app.models.show_log import (
    ShowLogCreate,
    ShowLogUpdate,
    ShowLogInDB,
    AttendanceStatus,
)

from datetime import datetime, UTC
from typing import Optional, List



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
        show_log_data: ShowLogCreate
    ) -> ShowLogInDB:


        event = await self.event_repository.get_by_id(
            show_log_data.event_id
        )


        if not event:
            raise ValueError(
                "Event not found"
            )


        existing_log = await self.show_log_repository.collection.find_one(
            {
                "user_id": user_id,
                "event_id": show_log_data.event_id,
            }
        )


        now = datetime.now(UTC)


        if existing_log:


            update_data = show_log_data.model_dump(
                exclude_unset=True
            )

            update_data["updated_at"] = now


            await self.show_log_repository.collection.update_one(
                {
                    "_id": existing_log["_id"]
                },
                {
                    "$set": update_data
                }
            )


            updated = await self.show_log_repository.collection.find_one(
                {
                    "_id": existing_log["_id"]
                }
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


        update_data = show_log_data.model_dump(
            exclude_unset=True
        )


        if not update_data:
            return await self.get_show_log(
                user_id,
                event_id
            )


        update_data["updated_at"] = datetime.now(UTC)



        updated = await self.show_log_repository.collection.find_one_and_update(
            {
                "user_id": user_id,
                "event_id": event_id,
            },
            {
                "$set": update_data
            },
            return_document=True
        )


        if not updated:
            return None


        return ShowLogInDB(
            **self._normalize_id(updated)
        )