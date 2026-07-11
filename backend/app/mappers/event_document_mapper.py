from app.domain.event import Event


class EventDocumentMapper:

    @staticmethod
    def to_domain(
        document: dict,
    ) -> Event:

        return Event(

            id=str(document["_id"]),

            provider=document["provider"],

            provider_event_id=document["provider_event_id"],

            artist_ids=document.get(
                "artist_ids",
                [],
            ),

            venue_id=document.get(
                "venue_id",
            ),

            title=document["title"],

            description=document.get(
                "description",
            ),

            starts_at=document["starts_at"],

            url=document.get(
                "url",
            ),

            image=document.get(
                "image",
            ),

            status=document.get(
                "status",
                "scheduled",
            ),

            last_synced_at=document.get(
                "last_synced_at",
            ),
        )