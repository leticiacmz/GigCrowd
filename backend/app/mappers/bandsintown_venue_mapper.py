from app.domain.venue import Venue
from app.utils.slug import generate_slug
from app.utils.text import normalize_text


class BandsintownVenueMapper:

    @staticmethod
    def to_domain(
        payload: dict,
    ) -> Venue:

        return Venue(

            name=payload["name"],

            normalized_name=normalize_text(
                payload["name"]
            ),

            slug=generate_slug(
                payload["name"]
            ),

            city=payload["city"],

            country=payload["country"],

            region=payload.get(
                "region"
            ),

            latitude=float(payload["latitude"])
            if payload.get("latitude")
            else None,

            longitude=float(payload["longitude"])
            if payload.get("longitude")
            else None,

            street_address=payload.get(
                "street_address"
            ),

            postal_code=payload.get(
                "postal_code"
            ),
        )