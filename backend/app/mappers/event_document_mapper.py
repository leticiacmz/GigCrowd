from app.domain.event import Event


class EventDocumentMapper:

    @staticmethod
    def to_domain(
        document: dict,
    ) -> Event:

        # ========================================================
        # ARTISTS
        # ========================================================

        # Backward compatibility:
        # migrate artist_slug to artist_slugs if not present.
        artist_slugs = document.get(
            "artist_slugs"
        )

        if artist_slugs is None:

            artist_slug = document.get(
                "artist_slug",
                "",
            )

            artist_slugs = (
                [artist_slug]
                if artist_slug
                else []
            )

        else:

            artist_slug = document.get(
                "artist_slug",
                artist_slugs[0]
                if artist_slugs
                else "",
            )

        # ========================================================
        # EVENT
        # ========================================================

        return Event(

            id=str(
                document["_id"]
            ),

            external_ids=document.get(
                "external_ids",
                {},
            ),

            artist_slugs=artist_slugs,

            artist_slug=artist_slug,

            venue_slug=document.get(
                "venue_slug",
                "",
            ),

            title=document.get(
                "title",
                "",
            ),

            starts_at=document.get(
                "starts_at"
            ),

            ends_at=document.get(
                "ends_at"
            ),

            event_type=document.get(
                "event_type",
                "Concert",
            ),

            # ====================================================
            # FESTIVAL
            # ====================================================

            festival=document.get(
                "festival"
            ),

            # ====================================================
            # LINEUP
            # ====================================================

            lineup=document.get(
                "lineup",
                [],
            ),

            # ====================================================
            # DATE PROVENANCE
            # ====================================================

            date_status=document.get(
                "date_status"
            ),

            # ====================================================
            # LOCATION
            # ====================================================

            location=document.get(
                "location"
            ),

            # ====================================================
            # SOURCE
            # ====================================================

            source=document.get(
                "source"
            ),

            # ====================================================
            # STATUS
            # ====================================================

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

            # ====================================================
            # ATTENDANCE
            # ====================================================

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