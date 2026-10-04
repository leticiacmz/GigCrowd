from fastapi import APIRouter, Depends, HTTPException


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