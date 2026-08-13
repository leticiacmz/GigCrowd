from app.domain.venue import Venue


class VenueDocumentMapper:

    @staticmethod
    def to_domain(
        document: dict,
    ) -> Venue:

        return Venue(

            id=str(document["_id"]),

            external_ids=document.get(
                "external_ids",
                {},
            ),

            name=document["name"],

            normalized_name=document.get(
                "normalized_name",
                ""
            ),

            slug=document["slug"],

            city=document["city"],

            country=document["country"],

            region=document.get("region"),

            latitude=document.get(
                "latitude",
            ),

            longitude=document.get(
                "longitude",
            ),

            street_address=document.get("street_address"),

            postal_code=document.get("postal_code"),
        )