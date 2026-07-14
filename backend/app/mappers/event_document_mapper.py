from app.domain.event import Event


class EventDocumentMapper:

    @staticmethod
    def to_domain(
        document: dict,
    ) -> Event:

        return Event(

            id=str(document["_id"]),

            external_ids=document.get(
                "external_ids",
                {},
            ),

            artist_slug=document["artist_slug"],

            venue_slug=document["venue_slug"],

            title=document["title"],

            starts_at=document.get(
                "starts_at"
            ),

            sold_out=document.get(
                "sold_out",
                False,
            ),

            free=document.get(
                "free",
                False,
            ),

            ticket_url=document.get(
                "ticket_url"
            ),
        )