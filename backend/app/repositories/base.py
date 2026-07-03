from typing import Generic, TypeVar, Dict, Any, List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

T = TypeVar("T")


class BaseRepository(Generic[T]):
    def __init__(self, db: AsyncIOMotorDatabase, collection_name: str):
        self.collection = db[collection_name]

    async def insert_one(self, data: Dict[str, Any]):
        return await self.collection.insert_one(data)

    async def find_one(self, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return await self.collection.find_one(query)

    async def find_many(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        cursor = self.collection.find(query)
        return await cursor.to_list(length=100)

    async def update_one(self, query: Dict[str, Any], update: Dict[str, Any]):
        return await self.collection.update_one(query, {"$set": update})