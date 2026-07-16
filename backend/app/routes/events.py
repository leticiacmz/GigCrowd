from fastapi import APIRouter, Depends


from app.services.event_service import EventService


from app.repositories.event_repository import EventRepository
from app.repositories.venue_repository import VenueRepository
from app.repositories.artist_repository import ArtistRepository


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