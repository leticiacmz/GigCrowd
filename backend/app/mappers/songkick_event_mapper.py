from datetime import datetime
from typing import Any

from app.domain.event import Event
from app.domain.venue import Venue


class SongkickEventMapper:

    @staticmethod
    def to_domain(
        songkick_event_data: dict,
        artist_slugs: list[str],
    ) -> tuple[Event, Venue]:

        if not isinstance(
            songkick_event_data,
            dict,
        ):

            raise ValueError(
                "Invalid Songkick event payload."
            )

        # ========================================================
        # EVENT ID
        # ========================================================

        event_id = (
            songkick_event_data.get(
                "songkick_id"
            )
            or songkick_event_data.get(
                "id"
            )
        )

        if not event_id:

            raise ValueError(
                "Songkick event does not have "
                "a valid ID."
            )

        # ========================================================
        # EVENT TITLE
        # ========================================================

        title = (
            songkick_event_data.get(
                "name"
            )
        )

        if not title:

            raise ValueError(
                f"Songkick event {event_id} "
                "does not have a valid name."
            )

        # ========================================================
        # DATES
        # ========================================================

        starts_at = (
            SongkickEventMapper
            ._parse_datetime(
                songkick_event_data.get(
                    "start_date"
                )
                or songkick_event_data.get("date")  # Support both formats
            )
        )

        ends_at = (
            SongkickEventMapper
            ._parse_datetime(
                songkick_event_data.get(
                    "end_date"
                )
            )
        )

        # ========================================================
        # VENUE
        # ========================================================

        venue = (
            SongkickEventMapper
            ._create_venue(
                songkick_event_data
            )
        )

        # ========================================================
        # EVENT TYPE
        # ========================================================

        raw_event_type = (
            songkick_event_data.get(
                "event_type"
            )
        )

        if raw_event_type == "festival" or raw_event_type == "FestivalInstance":

            event_type = "FestivalInstance"

        elif songkick_event_data.get(
            "is_live_stream"
        ):

            event_type = "Livestream"

        else:

            event_type = "Concert"

        # ========================================================
        # EXTERNAL IDS
        # ========================================================

        external_ids = {
            "songkick": str(
                event_id
            )
        }

        # ========================================================
        # FESTIVAL
        # ========================================================

        festival = (
            songkick_event_data.get(
                "festival"
            )
        )

        if not isinstance(
            festival,
            dict,
        ):

            festival = None

        # ========================================================
        # LOCATION
        # ========================================================

        location = (
            songkick_event_data.get(
                "location"
            )
        )

        if not isinstance(
            location,
            dict,
        ):

            location = None

        # ========================================================
        # SOURCE
        # ========================================================

        source = (
            songkick_event_data.get(
                "source"
            )
        )

        if not isinstance(
            source,
            dict,
        ):

            source = {
                "provider": "songkick",
                "external_id": str(
                    event_id
                ),
            }

            event_url = songkick_event_data.get(
                "url"
            )

            if event_url:

                source["url"] = event_url

        # ========================================================
        # EVENT
        # ========================================================

        event = Event(

            external_ids=external_ids,

            artist_slugs=artist_slugs,

            artist_slug=(
                artist_slugs[0]
                if artist_slugs
                else ""
            ),

            venue_slug=venue.slug,

            title=title,

            starts_at=starts_at,

            ends_at=ends_at,

            event_type=event_type,

            festival=festival,

            location=location,

            source=source,

            sold_out=False,

            free=False,

            ticket_url=(
                SongkickEventMapper
                ._extract_ticket_url(
                    songkick_event_data
                )
            ),

            going_count=0,

            maybe_count=0,

            went_count=0,
        )

        return event, venue

    # ============================================================
    # DATETIME
    # ============================================================

    @staticmethod
    def _parse_datetime(
        value: Any,
    ) -> datetime | None:

        if not value:

            return None

        if isinstance(
            value,
            datetime,
        ):

            return value

        if not isinstance(
            value,
            str,
        ):

            return None

        try:

            normalized = (
                value.strip()
            )

            normalized = (
                normalized.replace(
                    "Z",
                    "+00:00",
                )
            )

            return datetime.fromisoformat(
                normalized
            )

        except (
            ValueError,
            TypeError,
        ):

            return None

    # ============================================================
    # VENUE
    # ============================================================

    @staticmethod
    def _create_venue(
        songkick_event_data: dict,
    ) -> Venue:

        from app.utils.slug import (
            generate_slug,
        )

        from app.utils.text import (
            normalize_text,
        )

        location = (
            songkick_event_data.get(
                "venue"
            )
        )

        if not isinstance(
            location,
            dict,
        ):
            # Try simple format with venue_name, city_name, country_name at top level
            location = {
                "name": songkick_event_data.get("venue_name"),
                "address": {
                    "addressLocality": songkick_event_data.get("city_name"),
                    "addressCountry": songkick_event_data.get("country_name"),
                },
                "url": None
            }

        if not isinstance(
            location,
            dict,
        ):

            location = {}

        venue_name = (
            location.get(
                "name"
            )
            or "Unknown Venue"
        )

        address = (
            location.get(
                "address"
            )
        )

        street_address = None

        postal_code = None

        city = ""

        country = ""

        region = None

        if isinstance(
            address,
            dict,
        ):

            street_address = (
                address.get(
                    "streetAddress"
                )
                or address.get(
                    "street"
                )
            )

            postal_code = (
                address.get(
                    "postalCode"
                )
            )

            city = (
                address.get(
                    "addressLocality"
                )
                or address.get(
                    "city"
                )
                or ""
            )

            country_value = (
                address.get(
                    "addressCountry"
                )
                or address.get(
                    "country"
                )
                or ""
            )

            if isinstance(
                country_value,
                dict,
            ):

                country = (
                    country_value.get(
                        "name"
                    )
                    or country_value.get(
                        "code"
                    )
                    or ""
                )

            else:

                country = str(
                    country_value
                )

            region = (
                address.get(
                    "addressRegion"
                )
                or address.get(
                    "region"
                )
            )

        elif isinstance(
            address,
            str,
        ):

            street_address = address

        venue_url = (
            location.get(
                "url"
            )
        )

        venue_external_id = (
            SongkickEventMapper
            ._extract_venue_id(
                venue_url
            )
        )

        # Also try to get venue_id from top level
        if not venue_external_id:
            venue_external_id = songkick_event_data.get("venue_id")

        external_ids = {}

        if venue_external_id:

            external_ids[
                "songkick"
            ] = str(venue_external_id)

        slug = generate_slug(
            venue_name
        )

        return Venue(

            external_ids=external_ids,

            name=venue_name,

            normalized_name=normalize_text(
                venue_name
            ),

            slug=slug,

            city=city,

            country=country,

            region=region,

            latitude=None,

            longitude=None,

            street_address=street_address,

            postal_code=postal_code,
        )

    # ============================================================
    # TICKETS
    # ============================================================

    @staticmethod
    def _extract_ticket_url(
        event_data: dict,
    ) -> str | None:

        offers = event_data.get(
            "offers"
        )

        if not offers:

            return None

        if isinstance(
            offers,
            dict,
        ):

            offers = [
                offers
            ]

        if not isinstance(
            offers,
            list,
        ):

            return None

        for offer in offers:

            if not isinstance(
                offer,
                dict,
            ):

                continue

            url = offer.get(
                "url"
            )

            if url:

                return str(
                    url
                )

        return None

    # ============================================================
    # VENUE ID
    # ============================================================

    @staticmethod
    def _extract_venue_id(
        venue_url: str | None,
    ) -> str | None:

        if not venue_url:

            return None

        import re

        match = re.search(
            r"/venues/(\d+)",
            venue_url,
        )

        if match:

            return match.group(1)

        return None