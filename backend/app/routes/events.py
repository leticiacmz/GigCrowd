from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query


from app.schemas.event_search import (
    EventSearchGenresResponse,
    EventSearchResponse,
)

from app.services.event_service import EventService

from app.repositories.show_log_repository import ShowLogRepository
from app.services.attendance_service import AttendanceService
from app.repositories.event_repository import EventRepository
from app.repositories.venue_repository import VenueRepository
from app.repositories.artist_repository import ArtistRepository

from app.auth.dependencies import get_current_active_user
from app.database.connection import get_database




router = APIRouter(
    prefix="/events",
    tags=["events"],
)





def get_event_service() -> EventService:


    db = get_database()


    event_repository = EventRepository(
        db
    )


    venue_repository = VenueRepository(
        db
    )


    artist_repository = ArtistRepository(
        db
    )


    return EventService(

        event_repository,

        venue_repository,

        artist_repository,

    )


def get_attendance_service():

    db = get_database()

    return AttendanceService(
        ShowLogRepository(db)
    )



@router.get(
    "",
    response_model=EventSearchResponse,
)
async def search_events(

    q: Optional[str] = Query(
        None,
        max_length=200,
        description="Free text, matched against the title and the artists.",
    ),

    genre: Optional[str] = Query(
        None,
        max_length=80,
        description=(
            "A genre as spelled in the genres list. Matched against "
            "persisted artist metadata, never inferred from a title."
        ),
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

    include_past: bool = Query(
        False,
        description="Include events that have already happened.",
    ),

    db=Depends(get_database),

):
    """Search the events catalogue.

    Declared before `/{event_id}` so "search" is never read as an event id.

    Text and genre are composed inside one query rather than by the client
    filtering a page it has already fetched. That is what keeps `total` honest
    and keeps "next page" from jumping: both describe the same result set,
    whichever combination produced it.
    """

    from app.services.event_search_service import (
        EventSearchService,
    )

    service = EventSearchService(
        EventRepository(db),
        VenueRepository(db),
        ArtistRepository(db),
    )

    return await service.search(
        q=q,
        genre=genre,
        limit=limit,
        before=before,
        before_id=before_id,
        include_past=include_past,
    )


@router.get(
    "/genres",
    response_model=EventSearchGenresResponse,
)
async def list_event_genres(

    db=Depends(get_database),

):
    """The genres the catalogue can be filtered by.

    Sourced from artist metadata only. A genre is never read out of an event
    title, so "Rock in Rio" contributes nothing here - which is the point: the
    filter offers real genres and nothing else.
    """

    from app.services.event_search_service import (
        EventSearchService,
    )

    service = EventSearchService(
        EventRepository(db),
        VenueRepository(db),
        ArtistRepository(db),
    )

    return {"genres": await service.genres()}


@router.get(
    "/artist/{artist_slug}"
)
async def get_artist_events(

    artist_slug: str,

    event_service: EventService = Depends(
        get_event_service
    ),

):

    return await event_service.get_artist_events(
        artist_slug
    )







@router.get(
    "/{event_id}"
)
async def get_event(

    event_id: str,

    event_service: EventService = Depends(
        get_event_service
    ),

):


    event = await event_service.get_event(
        event_id
    )


    if not event:

        raise HTTPException(
            status_code=404,
            detail="Event not found",
        )


    return event

@router.get(
    "/{event_id}/festival"
)
async def get_event_festival(

    event_id: str,

    db=Depends(get_database),

):

    """The festival behind this event: identity, every date, and the lineup.

    One request by design. A festival page that fetched each edition, and then
    each artist in the lineup, would issue a request per row and stall on
    exactly the pages that have the most to show.
    """

    from app.services.festival_service import (
        FestivalService,
    )

    festival = await FestivalService(
        EventRepository(db),
        artist_repository=ArtistRepository(db),
    ).get_festival(event_id)

    if not festival:

        raise HTTPException(
            status_code=404,
            detail=(
                "This event does not belong to a festival"
            ),
        )

    return festival


@router.get(
    "/{event_id}/attendance"
)
async def get_event_attendance(

    event_id: str,

    current_user: dict = Depends(
        get_current_active_user
    ),

    attendance_service: AttendanceService = Depends(
        get_attendance_service
    ),

):

    return await attendance_service.get_event_attendance(
        event_id,
        current_user["_id"]
    )