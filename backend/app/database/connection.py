from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings
from typing import Optional


class Database:
    client: Optional[AsyncIOMotorClient] = None
    database = None

    async def connect(self):
        """Connect to MongoDB

        `tz_aware=True` makes a datetime read back exactly as it was written.

        BSON has no timezone, so by default MongoDB hands back naive datetimes
        and a document written with an aware value never compares equal to
        itself afterwards. That silently breaks anything which has to be
        idempotent - a seed that rewrites the same rows on every run, or an
        "update only what changed" comparison.
        """
        self.client = AsyncIOMotorClient(
            settings.MONGODB_URL,
            tz_aware=True,
        )
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
