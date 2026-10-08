"""The single search box.

Two existing services, one answer:

* the events catalogue (`EventSearchService`) - text and genre over the rows
  GigCrowd already holds, including shows that have already happened, because
  a *search* is a lookup ("did we have that Mada?") rather than the browse
  list on `/events`, which answers a different question ("what is on") and
  keeps its upcoming-only behaviour;
* artist discovery (`ArtistSearchService`) - one Songkick lookup, the same one
  `/artists/search` makes, annotated with what GigCrowd has already imported.

Both are asked, neither is asked twice, and no import or synchronization is
triggered by asking: selecting a result is a separate action, as it always
was. The artist half is asked only for the first page, so paging through
events does not repeat a remote lookup.

What is deliberately absent: venues. Songkick's search payload does contain a
`venues` section, but no GigCrowd client method, service or page has ever
consumed it, so exposing it here would be the start of a venue-search feature
rather than a search box. A venue query is answered with the catalogue rows
that mention the venue (their titles carry it) and nothing is pretended.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.core.logger import get_logger
from app.database.connection import get_database
from app.repositories.artist_repository import ArtistRepository
from app.repositories.event_repository import EventRepository
from app.repositories.venue_repository import VenueRepository
from app.schemas.unified_search import UnifiedSearchResponse
from app.services.artist_search_service import ArtistSearchService
from app.services.event_search_service import EventSearchService
from app.services.provider_manager import ProviderManager


logger = get_logger("unified_search")

router = APIRouter(
    prefix="/search",
    tags=["search"],
)


def get_event_search_service(
    db=Depends(get_database),
) -> EventSearchService:
    """The catalogue search, built from the request's database."""

    return EventSearchService(
        EventRepository(db),
        VenueRepository(db),
        ArtistRepository(db),
    )


def get_artist_search_service(
    db=Depends(get_database),
) -> ArtistSearchService:
    """Artist discovery, built from the request's database."""

    return ArtistSearchService(
        ProviderManager(),
        ArtistRepository(db),
    )


@router.get(
    "",
    response_model=UnifiedSearchResponse,
)
async def unified_search(

    q: str = Query(
        ...,
        min_length=1,
        max_length=200,
        description=(
            "Free text. Matched against event titles and artist names "
            "for events, and sent to Songkick for artist discovery."
        ),
    ),

    genre: Optional[str] = Query(
        None,
        max_length=80,
        description="A genre as spelled in the genres list.",
    ),

    limit: int = Query(20, ge=1, le=50),

    before: Optional[str] = Query(
        None,
        description="Opaque cursor date, from a previous next_cursor.",
    ),

    before_id: Optional[str] = Query(
        None,
        description="Opaque cursor id, from a previous next_cursor.",
    ),

    event_search: EventSearchService = Depends(
        get_event_search_service
    ),

    artist_search: ArtistSearchService = Depends(
        get_artist_search_service
    ),

):
    """Answer one general query in both of the ways this app can.

    The reader never names a source, so the response names the results: the
    `artists` array holds acts, the `events` array holds shows, and a show
    carrying a `festival` block is a festival edition. Nothing is imported,
    followed or synchronized by asking.
    """

    events = await event_search.search(
        q=q,
        genre=genre,
        limit=limit,
        before=before,
        before_id=before_id,
        # A search looks across the catalogue, not only at what is ahead.
        # `/events` stays upcoming-only because it is the "what is on" list;
        # asking for "Espaço Unimed" or "Mada" and being told "nothing" when
        # the rows exist would be the box lying about what it can see.
        include_past=True,
    )

    artists: list = []
    artists_unavailable = False

    # Only the first page asks: paging through events must not repeat a
    # remote lookup the reader already has the answer to.
    if not before:
        try:
            artists = await artist_search.search_artist(q)
        except Exception as exc:
            # Songkick being down is not "no artist by that name". The event
            # half still answers, and the flag lets the page say so instead
            # of rendering an empty artist list as a fact.
            logger.warning(
                f"Unified search could not reach artist discovery: {exc}"
            )
            artists = []
            artists_unavailable = True

    return UnifiedSearchResponse(
        query=q,
        artists=artists,
        artists_unavailable=artists_unavailable,
        events=events.get("events") or [],
        total=events.get("total") or 0,
        next_cursor=events.get("next_cursor"),
        genre=events.get("genre"),
    )
