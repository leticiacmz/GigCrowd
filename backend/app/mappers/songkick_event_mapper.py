from datetime import datetime
from typing import Any

from app.domain.event import Event
from app.domain.event_schedule import (
    parse_source_datetime,
    valid_interval_end,
)
from app.domain.lineup import LineupEntry
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

        # A date-only end parses to midnight of its own calendar day, which
        # sits before a start time on that same day. The two are read together
        # here, which is the one place an interval can be judged, so an end
        # that does not reach the start is never stored - see
        # `valid_interval_end`. A later calendar day is kept as stated, so a
        # multi-day festival range survives intact.
        ends_at = valid_interval_end(
            starts_at,
            ends_at,
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
        # LINEUP
        # ========================================================
        #
        # Performers are kept as structured entries with their Songkick
        # identity. They are not folded into the event's artist list: that
        # list is the GigCrowd artists this show belongs to, while the lineup
        # is who Songkick announces for it, most of whom are not imported yet.

        lineup = SongkickEventMapper._parse_lineup(
            songkick_event_data.get("lineup")
            or songkick_event_data.get(
                "performers"
            )
        )

        # ========================================================
        # DATE PROVENANCE
        # ========================================================

        date_status = (
            songkick_event_data.get(
                "date_status"
            )
        )

        if not date_status:
            # A date is a claim about the source, and only a real source read
            # makes one. An artist's gigography lists festival dates carrying no
            # date at all, because the listing does not state one - yet each of
            # those rows has a page of its own that does.
            #
            # Calling that `unavailable` asserted something this listing cannot
            # know, and the enrichment selector took it at face value, so fifty
            # festival dates whose dates were sitting on Songkick the whole time
            # were never re-read. An undated listing therefore leaves the status
            # unset: the date is unknown, which is not the same as the source
            # having none, and unknown is exactly what enrichment retries.
            date_status = (
                "source"
                if (starts_at or ends_at)
                else None
            )

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

            lineup=lineup,

            date_status=date_status,

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

        # Date parsing has one definition, owned by the module that defines
        # what an event's schedule means. Reading a provider's ISO string here
        # is the same operation `as_utc` performs on a stored date.
        return parse_source_datetime(value)

    # ============================================================
    # LINEUP
    # ============================================================

    @staticmethod
    def _parse_lineup(
        entries: Any,
    ) -> list[LineupEntry]:
        """Read a lineup, keeping only what the source actually stated.

        An entry without a name is dropped: there is nothing to show. An entry
        without a Songkick id is kept, because the artist is still real, but it
        carries no identifier and so cannot be matched to a GigCrowd artist
        yet. Nothing is invented to fill either gap.
        """

        if not isinstance(
            entries,
            list,
        ):
            return []

        from app.domain.lineup import (
            dedupe_lineup,
            LineupEntry,
        )

        parsed: list[LineupEntry] = []

        for entry in entries:

            if not isinstance(
                entry,
                dict,
            ):
                continue

            name = entry.get("name")

            if not name:
                continue

            genres = entry.get(
                "genres"
            )

            if isinstance(
                genres,
                str,
            ):
                genres = [genres]

            if not isinstance(
                genres,
                list,
            ):
                genres = []

            parsed.append(
                LineupEntry(
                    name=str(name).strip(),
                    songkick_id=(
                        str(
                            entry["songkick_id"],
                        )
                        if entry.get(
                            "songkick_id"
                        )
                        else None
                    ),
                    url=entry.get("url"),
                    slug=entry.get("slug"),
                    image=entry.get("image"),
                    genres=[
                        str(genre)
                        for genre in genres
                        if genre
                    ],
                    order=len(parsed),
                )
            )

        return dedupe_lineup(parsed)

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