from app.domain.venue import Venue


class VenueDocumentMapper:

    @staticmethod
    def to_domain(
        document: dict,
    ) -> Venue:

        return Venue(

            id=str(document["_id"]),

            provider=document["provider"],

            provider_venue_id=document.get(
                "provider_venue_id",
            ),

            name=document["name"],

            slug=document["slug"],

            city=document["city"],

            country=document["country"],

            latitude=document.get(
                "latitude",
            ),

            longitude=document.get(
                "longitude",
            ),
        )