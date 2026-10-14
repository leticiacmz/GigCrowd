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

            # `dict.get` with a default returns None when the key is *present*
            # holding None, which is exactly what a festival date looks like:
            # it has a lineup but no headline performer. Falling back to the
            # first of the bill keeps a concert's own value and gives a festival
            # the empty string, which is already this mapper's "no single
            # artist" answer.
            artist_slug = (
                document.get("artist_slug")
                or (
                    artist_slugs[0]
                    if artist_slugs
                    else ""
                )
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

            # Read as stored. The only inference left here is the one that
            # cannot be wrong: a document that carries a date but no status is
            # a row imported before `date_status` existed, and its date did come
            # from a source.
            #
            # A document with neither reports `None` rather than
            # "unavailable". Asserting `unavailable` for a row nobody has read
            # is precisely the claim the storage model refuses to make - it
            # collapses "not checked" and "checked and there was no date" into
            # one value, which is the distinction the client needs. The two are
            # told apart by `date_source_checked_at`, carried alongside.
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
                    else None
                )
            ),

            date_source_checked_at=document.get(
                "date_source_checked_at"
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
            # PRESENTATION
            # ====================================================

            description=document.get(
                "description"
            ),

            # `songkick_image` is how an earlier writer stored the photograph
            # before the field had a name of its own. Both are read so a row
            # imported either way renders the same picture; new writes use
            # `image_url`.
            image_url=document.get(
                "image_url"
            )
            or document.get(
                "songkick_image"
            ),

            event_status=document.get(
                "event_status"
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