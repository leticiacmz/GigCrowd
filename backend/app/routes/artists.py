from fastapi import APIRouter

from app.services.artist_search_service import ArtistSearchService
from app.services.artist_import_service import ArtistImportService
from app.services.provider_manager import ProviderManager
from app.schemas.artist_import import ArtistImportRequest
from app.repositories.artist_repository import ArtistRepository
from app.repositories.event_repository import EventRepository
from app.repositories.venue_repository import VenueRepository
from app.services.event_import_service import EventImportService
from app.services.event_service import EventService
from app.providers.registry import registry
from app.schemas.event_response import EventResponse
from app.config import settings
from app.services.artist_synchronization_service import ArtistSynchronizationService
from motor.motor_asyncio import AsyncIOMotorClient


router = APIRouter(
    prefix="/artists",
    tags=["Artists"],
)

client = AsyncIOMotorClient(settings.MONGODB_URL)

db = client[settings.DATABASE_NAME]

provider_manager = ProviderManager()

artist_repository = ArtistRepository(db)

artist_search_service = ArtistSearchService(
    provider_manager=provider_manager,
    artist_repository=artist_repository,
)

artist_import_service = ArtistImportService(
    provider_manager=provider_manager,
    artist_repository=artist_repository,
)

event_repository = EventRepository(db)

venue_repository = VenueRepository(db)

event_import_service = EventImportService(
    provider_manager=provider_manager,
    event_repository=event_repository,
    venue_repository=venue_repository,
)

event_repository = EventRepository(db)

event_service = EventService(
    event_repository=event_repository,
    venue_repository=venue_repository,
)
artist_synchronization_service = (
    ArtistSynchronizationService(
        artist_import_service=artist_import_service,
        event_import_service=event_import_service,
    )
)

# ----------------------------------------------------
# Routes
# ----------------------------------------------------

@router.get("/search")
async def search_artist(q: str):
    return await artist_search_service.search_artist(q)


@router.post("/import")
async def import_artist(
    data: ArtistImportRequest,
):
    return await (
        artist_synchronization_service
        .synchronize_artist(data)
    )

@router.get(
    "/{artist_slug}/events",
    response_model=list[EventResponse],
)
async def get_artist_events(
    artist_slug: str,
):

    return await event_service.get_artist_events(
        artist_slug
    )