"""The festival behind a concrete event.

A festival page needs three things at once: which festival this is, every date
GigCrowd holds for it, and who is playing. Assembling them here means the page
costs one request instead of one per edition and one per artist, and it keeps
the two levels of the data from being confused.

Identity and edition are answered separately and never mixed:

- The identity is the series, matched on the Songkick series id alone. Name is
  carried for display and is never used to decide that two events are the same
  festival, because festivals share names across cities and years.
- An edition is one imported event. It exists because the catalogue holds it,
  and it keeps its own dates, venue and lineup. Nothing here fabricates an
  edition that was never imported.

The lineup shown is the selected edition's own. A festival's lineup differs per
date, so borrowing one date's performers for the whole series would state
something untrue.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from app.core.logger import get_logger
from app.domain.event_schedule import (
    event_date,
    event_reference_date,
)
from app.domain.festival import festival_identity
from app.domain.event_provenance import (
    trusted_listing_filter,
)
from app.mappers.event_document_mapper import (
    EventDocumentMapper,
)
from app.mappers.event_response_mapper import (
    EventResponseMapper,
)
from app.repositories.event_repository import EventRepository
from app.schemas.festival_response import (
    FestivalEventResponse,
    FestivalIdentityResponse,
    FestivalResponse,
)
from app.services.lineup_artist_resolver import LineupArtistResolver

logger = get_logger("festival")

# Undated editions sort below dated ones rather than crashing the comparison. A
# festival whose date could not be read is still listed; it is just not claimed
# to be the nearest date.
_EPOCH = datetime.min.replace(tzinfo=UTC)


class FestivalService:
    """Assemble a festival page from stored events."""

    def __init__(
        self,
        event_repository,
        artist_repository=None,
    ):
        self.event_repository = event_repository
        self.artist_repository = artist_repository

        # The one implementation of "does this lineup entry have a GigCrowd
        # page". Shared with the resolution report so a festival page and an
        # operational report can never disagree.
        self.resolver = LineupArtistResolver(artist_repository)

    async def _venues(
        self,
        slugs: list[Optional[str]],
    ) -> dict[str, dict]:
        """The venues of every edition, keyed by slug, in one query.

        An event stores only a venue slug, so the place each date is held has to
        be read from the venues collection. Doing it for all editions at once is
        what keeps the page to a fixed number of reads rather than one per date.
        """

        wanted = {
            slug for slug in slugs if slug
        }

        if not wanted:
            return {}

        documents = await (
            self.event_repository.db.venues.find(
                {"slug": {"$in": sorted(wanted)}}
            ).to_list(length=None)
        )

        return {
            document["slug"]: document
            for document in documents
            if document.get("slug")
        }

    async def _artist_slugs(
        self,
        entries: list[dict],
    ) -> dict[str, str]:
        """Map each Songkick artist id to the GigCrowd page that exists for it.

        A festival announces many more artists than GigCrowd has imported, and a
        name is not enough to link on: two different artists can share a name,
        and a wrong link is worse than no link. So the match is on the Songkick
        artist id - the one identifier both systems agree on - and an artist with
        no imported page is simply absent from the result. That absence is what
        the client renders as a plain name.

        The whole lineup is resolved in one query, by the shared resolver that
        also produces the resolution report, so the page and the report can
        never disagree about which entries are linkable.
        """

        ids = [
            entry["songkick_id"]
            for entry in entries
            if entry.get("songkick_id")
        ]

        if not ids or self.artist_repository is None:
            return {}

        return await self.resolver.resolve(ids)

    async def get_festival(
        self,
        event_id: str,
    ) -> Optional[FestivalResponse]:
        """The festival this event belongs to, or `None` if it is not one.

        Returns `None` for an event that is not a festival date at all, which
        the route turns into a 404. An undated festival is still a festival: it
        is returned with whatever editions exist, because refusing to show a
        festival page for an event whose date could not be read would hide the
        very records that most need to be visible.
        """

        document = await self.event_repository.get_document_by_id(
            event_id
        )

        if document is None:
            return None

        identity = festival_identity(document)

        if not identity:
            return None

        series_id = identity["series_id"]

        editions = await self._editions_for(
            series_id,
            # The record the reader arrived from. It is part of the query rather
            # than assumed to match, because the list applies the provenance
            # rule and this page has to render for whichever record was opened.
            document["_id"],
        )

        # The event the reader arrived from is always among the editions: it
        # is returned by id, because its identity - read from its stored block
        # or from its own address when no block was written - is what named the
        # series in the first place. Finding it by id rather than assuming it
        # is first keeps the selection correct without depending on sort order.
        selected = next(
            document
            for document in editions
            if str(document["_id"]) == str(event_id)
        )

        # The span runs from when the first date begins to when the last one finishes.
        #
        # Both ends matter and they come from different fields. The opening is
        # the earliest *start*: `event_reference_date` returns the later of start
        # and end so that "has this happened?" is answered by the end of a
        # multi-day festival, which would report the festival as opening on its
        # last night. The closing is the latest *finish*, because a festival that
        # finishes after midnight is not over when its last night starts.
        opening = [
            moment
            for moment in (
                event_date(document)
                for document in editions
            )
            if moment is not None
        ]

        closing = [
            moment
            for moment in (
                event_reference_date(document)
                for document in editions
            )
            if moment is not None
        ]

        # Most recent first: a festival page is read to answer "when can I still
        # get to this". An edition whose date could not be read sorts last rather
        # than inheriting a date from another edition, which would place it on a
        # night it was never stated to happen on.
        editions.sort(
            key=lambda document: (
                event_date(document) or _EPOCH
            ),
            reverse=True,
        )

        name = (
            identity.get("name")
            or selected.get("title")
        )

        # Every edition's lineup is read first, then all of them are resolved
        # together. Resolving per edition would query the artists collection
        # once per date, so a festival with ten dates would cost ten round trips
        # to render one page - and a thirty-act lineup on each would be worse.
        raw_lineups = [
            [
                _lineup_response(entry)
                for entry in EventDocumentMapper.to_domain(
                    document
                ).lineup
            ]
            for document in editions
        ]

        slugs = await self._artist_slugs(
            [
                entry
                for lineup in raw_lineups
                for entry in lineup
            ]
        )

        def attach(lineup: list[dict]) -> list[dict]:
            return [
                {**entry, "artist_slug": _slug_of(entry, slugs)}
                for entry in lineup
            ]

        venues = await self._venues(
            [
                document.get("venue_slug")
                for document in editions
            ]
        )

        selected_index = next(
            (
                index
                for index, candidate in enumerate(editions)
                if str(candidate["_id"]) == str(selected["_id"])
            ),
            0,
        )

        resolved_lineups = [
            attach(lineup)
            for lineup in raw_lineups
        ]

        return FestivalResponse(
            identity=FestivalIdentityResponse(
                series_id=series_id,
                name=name,
                url=identity.get("url"),
                official_url=identity.get(
                    "official_url"
                ),
                image_url=(
                    identity.get("image_url")
                    or _image_of(selected)
                ),
                edition=identity.get("edition"),
                tracking_count=identity.get(
                    "tracking_count"
                ),
                editions_count=len(editions),
                first_date=(
                    min(opening)
                    if opening
                    else None
                ),
                last_date=(
                    max(closing)
                    if closing
                    else None
                ),
            ),
            editions=[
                FestivalEventResponse(
                    event=EventResponseMapper.from_domain(
                        EventDocumentMapper.to_domain(
                            document
                        ),
                        venues.get(
                            document.get("venue_slug")
                        ),
                    ),
                    lineup=resolved_lineups[index],
                )
                for index, document in enumerate(editions)
            ],
            selected_event_id=str(selected["_id"]),
            lineup=resolved_lineups[selected_index],
        )

    async def _editions_for(
        self,
        series_id: str,
        arrived_at,
    ) -> list[dict]:
        """Every stored date of one festival series.

        One indexed read, not one per edition.

        Editions are found by the stored series id, which is what identifies the
        festival. An event whose series id was never recorded is not listed as
        another date of the series: that field is written from the series
        segment of the event's own Songkick URL, so a second, fuzzier way of
        guessing the same thing would only risk grouping events that are not
        the same festival. The record the reader arrived on is the one
        exception, and it is matched by id below.

        The provenance clause is the same one every other listing of future
        events applies. An edition list reaches into the future, and a fixture
        edition dated next year would otherwise sit here looking exactly like an
        announcement. Past editions are kept, because a festival's history is
        part of what the page is for.

        `arrived_at` is the record the reader came from, and it is always
        returned. The whole page - its span, its edition count, and the lineup
        beside the reader's own date - is read from this one list, so a record
        that is filtered out of discovery must not also disappear from the page
        somebody is already standing on. That record was reached deliberately;
        what the clause stops is the rest of the future being sold as announced.
        """

        documents = await (
            self.event_repository.collection.find(
                {
                    "$or": [
                        # The record the reader arrived from, matched by id.
                        # Its identity may have been read from its own address
                        # while no festival block was ever written beside it,
                        # so the series field alone would drop the very record
                        # the page is standing on.
                        {
                            "_id": arrived_at,
                        },
                        {
                            "$and": [
                                {
                                    "festival.series_id": str(series_id),
                                },
                                trusted_listing_filter(
                                    EventRepository._still_ahead_dates_filter()
                                ),
                            ]
                        },
                    ]
                }
            ).to_list(length=None)
        )

        return documents


def _slug_of(
    entry: dict,
    slugs: dict[str, str],
) -> Optional[str]:
    """The GigCrowd page for a lineup entry, when one exists.

    `slugs` is keyed by the bare numeric id the entry carries. An entry whose id
    resolved to nothing - because no artist is imported for it, or because more
    than one claims it - returns `None`, and the client shows the name as plain
    text rather than a link that would go somewhere unverified.
    """

    songkick_id = entry.get("songkick_id")

    if not songkick_id:
        return None

    return slugs.get(str(songkick_id).strip())


def _lineup_response(entry) -> dict:
    return {
        "name": entry.name,
        "songkick_id": entry.songkick_id,
        "slug": entry.slug,
        "url": entry.url,
        "image": entry.image,
        "genres": entry.genres,
        "order": entry.order,
    }


def _image_of(document: dict) -> Optional[str]:
    """The event's own image, used as a last resort for the header."""

    return (
        document.get("songkick_image")
        or document.get("image_url")
    )