from typing import Dict, Any, List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase


class BaseRepository:
    def __init__(self, db: AsyncIOMotorDatabase, collection: str):
        self.collection = db[collection]

    async def insert_one(self, data: Dict[str, Any]):
        return await self.collection.insert_one(data)

    async def find_one(self, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return await self.collection.find_one(query)

    async def find_many(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        cursor = self.collection.find(query)
        return await cursor.to_list(length=100)