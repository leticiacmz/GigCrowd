import asyncio
import logging
from motor.motor_asyncio import AsyncIOMotorClient

from backend.app.config import settings


# =========================================================
# LOGGING
# =========================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("init_db")


# =========================================================
# FULL RESET (remove collections antigas)
# =========================================================
async def reset_database(db):
    logger.info("Dropping all collections...")

    collections = await db.list_collection_names()

    for col in collections:
        await db.drop_collection(col)
        logger.info(f"Dropped collection: {col}")

    logger.info("Database reset complete.")


# =========================================================
# INIT INDEXES
# =========================================================
async def create_indexes(db):
    logger.info("Creating indexes...")

    # ---------------- USERS ----------------
    await db.users.create_index("email", unique=True)
    await db.users.create_index("username", unique=True)

    # ---------------- PROFILES (embedded in user, but safe index if used later)
    # (ignored for now)

    # ---------------- POSTS ----------------
    await db.posts.create_index("user_id")
    await db.posts.create_index("event_id")
    await db.posts.create_index([("created_at", -1)])

    # ---------------- COMMENTS ----------------
    await db.comments.create_index("post_id")
    await db.comments.create_index("user_id")
    await db.comments.create_index([("created_at", -1)])

    # ---------------- LIKES ----------------
    await db.likes.create_index(
        [("target_id", 1), ("user_id", 1)],
        unique=True
    )

    # ---------------- FOLLOWS ----------------
    await db.follows.create_index(
        [("follower_id", 1), ("following_id", 1)],
        unique=True
    )

    # ---------------- ACTIVITY FEED ----------------
    await db.activity.create_index("user_id")
    await db.activity.create_index([("created_at", -1)])

    # ---------------- EVENTS ----------------
    await db.events.create_index("artist_id")
    await db.events.create_index("venue_id")
    await db.events.create_index([("date", -1)])

    # ---------------- ARTISTS ----------------
    await db.artists.create_index("normalized_name", unique=True)

    # ---------------- VENUES ----------------
    await db.venues.create_index(
        [("name", 1), ("city", 1), ("country", 1)],
        unique=True
    )

    # ---------------- SHOW LOGS (attendance) ----------------
    await db.show_logs.create_index(
        [("user_id", 1), ("event_id", 1)],
        unique=True
    )

    logger.info("Indexes created successfully.")


# =========================================================
# MAIN INIT
# =========================================================
async def init_db():
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.DATABASE_NAME]

    logger.info("Starting database initialization...")

    await reset_database(db)
    await create_indexes(db)

    logger.info("Database is ready.")


if __name__ == "__main__":
    asyncio.run(init_db())