from app.database.connection import get_database
from app.models.follow import FollowCreate


class FollowService:
    """Service for managing user follow relationships"""

    @staticmethod
    async def follow_user(follower_id: str, follow_data: FollowCreate):
        db = get_database()

        # check self-follow
        if follower_id == follow_data.following_id:
            raise ValueError("Cannot follow yourself")

        # check existing follow
        existing = await db.follows.find_one({
            "follower_id": follower_id,
            "following_id": follow_data.following_id
        })

        if existing:
            raise ValueError("Already following this user")

        # create follow document (NO MODEL INSTANCING)
        follow_doc = {
            "follower_id": follower_id,
            "following_id": follow_data.following_id,
            "created_at": None  # opcional, pode remover ou setar datetime.utcnow()
        }

        result = await db.follows.insert_one(follow_doc)

        # update counters
        await db.users.update_one(
            {"_id": follower_id},
            {"$inc": {"following_count": 1}}
        )

        await db.users.update_one(
            {"_id": follow_data.following_id},
            {"$inc": {"followers_count": 1}}
        )

        follow_doc["_id"] = str(result.inserted_id)
        return follow_doc

    @staticmethod
    async def unfollow_user(follower_id: str, following_id: str) -> bool:
        db = get_database()

        result = await db.follows.delete_one({
            "follower_id": follower_id,
            "following_id": following_id
        })

        if result.deleted_count == 0:
            return False

        await db.users.update_one(
            {"_id": follower_id},
            {"$inc": {"following_count": -1}}
        )

        await db.users.update_one(
            {"_id": following_id},
            {"$inc": {"followers_count": -1}}
        )

        return True

    @staticmethod
    async def get_following(user_id: str, skip: int = 0, limit: int = 20):
        db = get_database()

        follows = await db.follows.find(
            {"follower_id": user_id}
        ).skip(skip).limit(limit).to_list(length=limit)

        following_ids = [f["following_id"] for f in follows]

        if not following_ids:
            return []

        return await db.users.find(
            {"_id": {"$in": following_ids}}
        ).to_list(length=limit)

    @staticmethod
    async def get_followers(user_id: str, skip: int = 0, limit: int = 20):
        db = get_database()

        follows = await db.follows.find(
            {"following_id": user_id}
        ).skip(skip).limit(limit).to_list(length=limit)

        follower_ids = [f["follower_id"] for f in follows]

        if not follower_ids:
            return []

        return await db.users.find(
            {"_id": {"$in": follower_ids}}
        ).to_list(length=limit)

    @staticmethod
    async def is_following(follower_id: str, following_id: str) -> bool:
        db = get_database()

        follow = await db.follows.find_one({
            "follower_id": follower_id,
            "following_id": following_id
        })

        return follow is not None