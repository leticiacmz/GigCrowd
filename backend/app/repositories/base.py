from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase


class BaseRepository:

    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        collection: str,
    ):

        self.collection = db[collection]

    async def insert_one(
        self,
        data: dict[str, Any],
    ):

        return await self.collection.insert_one(data)

    async def find_one(
        self,
        query: dict[str, Any],
    ) -> dict | None:

        return await self.collection.find_one(query)

    async def find_many(
        self,
        query: dict[str, Any],
    ) -> list[dict]:

        cursor = self.collection.find(query)

        return await cursor.to_list(
            length=100
        )