
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings


class Database:
    client: Optional[AsyncIOMotorClient] = None
    database = None

    async def connect(self):
        """Connect to MongoDB and verify the connection."""
        self.client = AsyncIOMotorClient(
            settings.MONGODB_URL,
            tz_aware=True,
            serverSelectionTimeoutMS=10000,
        )

        self.database = self.client[settings.DATABASE_NAME]

        try:
            # Verify connectivity and authentication during startup.
            await self.client.admin.command("ping")
            print("MongoDB connection established successfully.")

        except Exception:
            # Do not log the connection URI or credentials.
            self.client.close()
            self.client = None
            self.database = None
            print("MongoDB connection failed. Check the database configuration.")
            raise

    async def disconnect(self):
        """Disconnect from MongoDB."""
        if self.client:
            self.client.close()
            self.client = None
            self.database = None
            print("Disconnected from MongoDB.")

    def get_database(self):
        """Get database instance."""
        return self.database

    def get_collection(self, name: str):
        """Get a specific collection."""
        if self.database is None:
            raise RuntimeError("Database is not connected.")

        return self.database[name]


db = Database()


def get_database():
    """Dependency to get database instance."""
    return db.get_database()