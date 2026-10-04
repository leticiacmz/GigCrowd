from datetime import datetime, UTC

from app.repositories.base import BaseRepository
from app.mappers.event_document_mapper import EventDocumentMapper
from app.domain.event import Event
from bson import ObjectId


class EventRepository(BaseRepository):

    def __init__(self, db):
        super().__init__(
            db,
            "events",
        )

    # ============================================================
    # GET BY ID
    # ============================================================

    async def get_by_id(
        self,
        event_id: str,
    ):

        document = await self.find_one(
            {
                "_id": ObjectId(
                    event_id
                )
            }
        )

        if not document:
            return None

        return EventDocumentMapper.to_domain(
            document
        )

    # ============================================================
    # GET BY EXTERNAL ID
    # ============================================================

    async def get_by_external_id(
        self,
        provider: str,
        external_id: str,
    ):

        document = await self.find_one(
            {
                f"external_ids.{provider}": external_id
            }
        )

        if not document:
            return None

        return EventDocumentMapper.to_domain(
            document
        )

    # ============================================================
    # GET RAW DOCUMENT BY ID
    # ============================================================

    async def get_document_by_id(
        self,
        event_id: str,
    ):

        """The stored document, for callers that read provider metadata.

        Reporting a festival means reading fields the domain `Event` does not
        model - the raw Songkick URL, the provider's own series id - so that
        answer is built from the document rather than by inventing the missing
        fields on the domain object.
        """

        if not ObjectId.is_valid(event_id):
            return None

        return await self.find_one(
            {
                "_id": ObjectId(event_id)
            }
        )

    # ============================================================
    # UPCOMING FILTER
    # ============================================================

    @staticmethod
    def _upcoming_filter(
        artist_slug: str,
    ) -> dict:

        now = datetime.now(UTC)

        return {
            "$and": [
                {
                    "$or": [
                        {
                            "artist_slug": artist_slug
                        },
                        {
                            "artist_slugs": artist_slug
                        },
                    ]
                },
                {
                    "$or": [
                        {
                            "ends_at": {
                                "$gte": now
                            }
                        },
                        {
                            "$and": [
                                {
                                    "$or": [
                                        {
                                            "ends_at": {
                                                "$exists": False
                                            }
                                        },
                                        {
                                            "ends_at": None
                                        },
                                    ]
                                },
                                {
                                    "starts_at": {
                                        "$gte": now
                                    }
                                },
                            ]
                        },
                    ]
                },
            ]
        }

    # ============================================================
    # GET UPCOMING EVENTS
    # ============================================================

    async def get_by_artist_slug(
        self,
        artist_slug: str,
    ):

        cursor = (
            self.collection
            .find(
                self._upcoming_filter(
                    artist_slug
                )
            )
            .sort(
                "starts_at",
                1,
            )
        )

        documents = await cursor.to_list(
            length=6
        )

        return [
            EventDocumentMapper.to_domain(
                document
            )
            for document in documents
        ]

    # ============================================================
    # INSERT
    # ============================================================

    async def insert_event(
        self,
        event: Event,
    ):

        await self.insert_one(
            event.model_dump(
                exclude={"id"}
            )
        )

    # ============================================================
    # COUNTS
    # ============================================================

    async def count_by_artist_slug(
        self,
        artist_slug: str,
    ):

        return await self.collection.count_documents(
            {
                "$or": [
                    {
                        "artist_slug": artist_slug
                    },
                    {
                        "artist_slugs": artist_slug
                    },
                ]
            }
        )

    async def count_upcoming_by_artist_slug(
        self,
        artist_slug: str,
    ):

        return await self.collection.count_documents(
            self._upcoming_filter(
                artist_slug
            )
        )

    # ============================================================
    # ATTENDANCE
    # ============================================================

    async def update_attendance_counts(
        self,
        event_id: str,
        going_count: int,
        maybe_count: int,
        went_count: int,
    ):

        await self.collection.update_one(
            {
                "_id": ObjectId(
                    event_id
                )
            },
            {
                "$set": {
                    "going_count": going_count,
                    "maybe_count": maybe_count,
                    "went_count": went_count,
                }
            },
        )

    # ============================================================
    # UPCOMING BY ARTIST
    # ============================================================

    async def get_upcoming_by_artist_slug(
        self,
        artist_slug: str,
        limit: int = 6,
    ):

        cursor = (
            self.collection
            .find(
                self._upcoming_filter(
                    artist_slug
                )
            )
            .sort(
                "starts_at",
                1,
            )
            .limit(limit)
        )

        documents = await cursor.to_list(
            length=limit
        )

        return [
            EventDocumentMapper.to_domain(
                document
            )
            for document in documents
        ]

    # ============================================================
    # ALL EVENTS
    # ============================================================

    async def get_all_by_artist_slug(
        self,
        artist_slug: str,
    ):

        cursor = (
            self.collection
            .find(
                {
                    "$or": [
                        {
                            "artist_slug": artist_slug
                        },
                        {
                            "artist_slugs": artist_slug
                        },
                    ]
                }
            )
            .sort(
                "starts_at",
                -1,
            )
        )

        documents = await cursor.to_list(
            length=1000
        )

        return [
            EventDocumentMapper.to_domain(
                document
            )
            for document in documents
        ]

    # ============================================================
    # LEGACY BANDsINTOWN UPDATE
    # ============================================================

    async def update_event(
        self,
        event: Event,
    ):

        bandsintown_id = event.external_ids.get(
            "bandsintown"
        )

        if not bandsintown_id:
            raise ValueError(
                "Event does not have a Bandsintown external ID."
            )

        await self.collection.update_one(
            {
                "external_ids.bandsintown": bandsintown_id
            },
            {
                "$set": event.model_dump(
                    exclude={"id"}
                )
            },
        )

    # ============================================================
    # LEGACY BANDsINTOWN UPSERT
    # ============================================================

    async def upsert_event(
        self,
        event: Event,
    ) -> bool:

        bandsintown_id = event.external_ids.get(
            "bandsintown"
        )

        if not bandsintown_id:
            raise ValueError(
                "Event does not have a Bandsintown external ID."
            )

        existing = await self.get_by_external_id(
            "bandsintown",
            bandsintown_id,
        )

        if existing:

            await self.update_event(
                event
            )

            return False

        await self.insert_event(
            event
        )

        return True

    # ============================================================
    # ARTIST SLUGS
    # ============================================================

    async def get_by_artist_slugs(
        self,
        artist_slugs: list[str],
    ):

        now = datetime.now(UTC)

        cursor = (
            self.collection
            .find(
                {
                    "artist_slugs": {
                        "$in": artist_slugs
                    },
                    "$or": [
                        {
                            "ends_at": {
                                "$gte": now
                            }
                        },
                        {
                            "$and": [
                                {
                                    "$or": [
                                        {
                                            "ends_at": {
                                                "$exists": False
                                            }
                                        },
                                        {
                                            "ends_at": None
                                        },
                                    ]
                                },
                                {
                                    "starts_at": {
                                        "$gte": now
                                    }
                                },
                            ]
                        },
                    ],
                }
            )
            .sort(
                "starts_at",
                1,
            )
        )

        documents = await cursor.to_list(
            length=6
        )

        return [
            EventDocumentMapper.to_domain(
                document
            )
            for document in documents
        ]

    # ============================================================
    # PROVIDER UPSERT
    # ============================================================

    async def upsert_event_by_provider(
        self,
        event: Event,
        provider: str,
    ) -> bool:

        provider_external_id = event.external_ids.get(
            provider
        )

        if not provider_external_id:

            raise ValueError(
                f"No {provider} external ID in event"
            )

        existing = await self.get_by_external_id(
            provider,
            provider_external_id,
        )

        if existing:

            await self.update_event_by_provider(
                event,
                provider,
            )

            return False

        await self.insert_event(
            event
        )

        return True

    # ============================================================
    # PROVIDER UPDATE
    # ============================================================

    async def update_event_by_provider(
        self,
        event: Event,
        provider: str,
    ):

        await self.collection.update_one(
            {
                f"external_ids.{provider}": (
                    event.external_ids[provider]
                )
            },
            {
                "$set": event.model_dump(
                    exclude={"id"}
                )
            },
        )