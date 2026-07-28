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

            going_count=document.get(
                "going_count",
                0,
            ),

            maybe_count=document.get(
                "maybe_count",
                0,
            ),

            went_count=document.get(
                "went_count",
                0,
            ),
        )