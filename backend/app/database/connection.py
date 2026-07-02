from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings
from typing import Optional


class Database:
    client: Optional[AsyncIOMotorClient] = None
    database = None

    async def connect(self):
        """Connect to MongoDB"""
        self.client = AsyncIOMotorClient(settings.MONGODB_URL)
        self.database = self.client[settings.DATABASE_NAME]
        print(f"Connected to MongoDB at {settings.MONGODB_URL}")

    async def disconnect(self):
        """Disconnect from MongoDB"""
        if self.client:
            self.client.close()
            print("Disconnected from MongoDB")

    def get_database(self):
        """Get database instance"""
        return self.database

    def get_collection(self, name: str):
        """Get a specific collection"""
        return self.database[name]


db = Database()


def get_database():
    """Dependency to get database instance"""
    return db.get_database()
