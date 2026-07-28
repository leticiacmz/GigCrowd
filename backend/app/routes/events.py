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