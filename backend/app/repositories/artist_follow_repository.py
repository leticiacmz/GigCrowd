from datetime import datetime, timezone
from bson import ObjectId

from app.repositories.base import BaseRepository
from app.utils.ids import id_matches


class ArtistFollowRepository(BaseRepository):

    def __init__(self, db):

        super().__init__(
            db,
            "artist_follows",
        )

    async def create_follow(
        self,
        user_id: str,
        artist_slug: str,
    ):

        # Convert user_id to ObjectId if it's a string
        try:
            user_id = ObjectId(user_id)
        except:
            pass  # Already an ObjectId or invalid

        document = {

            "user_id": user_id,

            "artist_slug": artist_slug,

            "created_at": datetime.now(
                timezone.utc
            ),

        }

        result = await self.insert_one(
            document
        )

        # Update artist followers count
        await self.db.artists.update_one(
            {"slug": artist_slug},
            {"$inc": {"followers_count": 1}}
        )

        # Update user followed artists count
        await self.db.users.update_one(
            {"_id": user_id},
            {"$inc": {"followed_artists_count": 1}}
        )

        return result

    async def delete_follow(
        self,
        user_id: str,
        artist_slug: str,
    ):

        # Convert user_id to ObjectId if it's a string
        try:
            user_id = ObjectId(user_id)
        except:
            pass  # Already an ObjectId or invalid

        result = await self.collection.delete_one(
            {
                "user_id": user_id,
                "artist_slug": artist_slug,
            }
        )

        # Update artist followers count if a document was deleted
        if result.deleted_count > 0:
            await self.db.artists.update_one(
                {"slug": artist_slug},
                {"$inc": {"followers_count": -1}}
            )

            # Update user followed artists count
            await self.db.users.update_one(
                {"_id": user_id},
                {"$inc": {"followed_artists_count": -1}}
            )

        return result

    async def exists(
        self,
        user_id: str,
        artist_slug: str,
    ):

        # Convert user_id to ObjectId if it's a string
        try:
            user_id = ObjectId(user_id)
        except:
            pass  # Already an ObjectId or invalid

        document = await self.find_one(
            {
                "user_id": user_id,
                "artist_slug": artist_slug,
            }
        )

        return document is not None

    async def count_followers(
        self,
        artist_slug: str,
    ) -> int:
        """
        Count only GigCrowd users following the artist.

        This collection is the sole source of truth for
        artist followers inside GigCrowd.
        """

        return await self.collection.count_documents(
            {
                "artist_slug": artist_slug,
            }
        )

    async def get_following_artists(
        self,
        user_id: str,
        limit: int = 50,
        skip: int = 0,
    ):
        """Get list of artists that a user follows.

        Matched through `id_matches`, not by converting the id: historic rows
        disagree about how to store one, and a lookup that only knows one form
        makes a real follow silently disappear from the feed and from every
        list built on it.
        """

        cursor = self.collection.find(
            id_matches(
                "user_id",
                user_id,
            )
        ).skip(skip).limit(limit)

        return await cursor.to_list(length=limit)