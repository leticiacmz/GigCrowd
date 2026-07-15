from datetime import datetime, timezone

from app.repositories.base import BaseRepository



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


        document = {

            "user_id": user_id,

            "artist_slug": artist_slug,

            "created_at": datetime.now(
                timezone.utc
            ),

        }


        return await self.insert_one(
            document
        )




    async def delete_follow(
        self,
        user_id: str,
        artist_slug: str,
    ):


        return await self.collection.delete_one(
            {
                "user_id": user_id,

                "artist_slug": artist_slug,
            }
        )





    async def exists(
        self,
        user_id: str,
        artist_slug: str,
    ):


        document = await self.find_one(
            {
                "user_id": user_id,

                "artist_slug": artist_slug,
            }
        )


        return document is not None