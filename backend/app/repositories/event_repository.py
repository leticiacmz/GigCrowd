from app.repositories.base import BaseRepository
from app.mappers.event_document_mapper import EventDocumentMapper

from bson import ObjectId





class EventRepository(BaseRepository):


    def __init__(
        self,
        db
    ):

        super().__init__(
            db,
            "events"
        )





    async def get_by_id(
        self,
        event_id: str,
    ):


        document = await self.find_one(
            {
                "_id": ObjectId(event_id)
            }
        )


        if not document:

            return None



        return EventDocumentMapper.to_domain(
            document
        )






    async def get_by_external_id(
        self,
        provider: str,
        external_id: str,
    ):

        return await self.find_one(
            {
                f"external_ids.{provider}": external_id,
            }
        )






    async def get_by_artist_slug(
        self,
        artist_slug: str,
    ):

        cursor = (
            self.collection
            .find(
                {
                    "artist_slug": artist_slug,
                }
            )
            .sort(
                "starts_at",
                -1,
            )
        )


        documents = await cursor.to_list(
            length=1000,
        )


        return [

            EventDocumentMapper.to_domain(
                document
            )

            for document in documents

        ]