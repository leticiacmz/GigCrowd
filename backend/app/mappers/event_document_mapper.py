from app.domain.event import Event


class EventDocumentMapper:

    @staticmethod
    def _read_location(
        value,
    ):
        """Read a stored location without failing on an older shape.

        Location is a structured field, but some early documents stored it as a
        plain string - "Central Park, NY". Passing that through raised a
        validation error, which surfaced as a 500 on the event page and a
        "not found" message to the reader, for a row that was perfectly readable.

        A bare string is kept as the place's name rather than discarded, so the
        information survives and the page renders. Anything that is neither a
        mapping nor a string is reported as no location rather than guessed at.
        """

        if value is None:
            return None

        if isinstance(
            value,
            dict,
        ):
            return value or None

        if isinstance(
            value,
            str,
        ):
            text = value.strip()

            return {"name": text} if text else None

        return None

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

            date_status=(
                document.get(
                    "date_status"
                )
                or (
                    "source"
                    if (
                        document.get("starts_at")
                        or document.get("ends_at")
                    )
                    else "unavailable"
                )
            ),

            # ====================================================
            # LOCATION
            # ====================================================

            location=EventDocumentMapper._read_location(
                document.get(
                    "location"
                )
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