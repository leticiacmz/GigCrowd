from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings

from app.providers.registry import registry
from app.providers.spotify import SpotifyProvider
from app.providers.bandsintown import BandsintownProvider

from app.repositories.artist_repository import ArtistRepository

from app.services.provider_manager import ProviderManager
from app.services.discovery_service import DiscoveryService

app = FastAPI(title="GigCrowd")


# -------------------------------------------------------------------
# Database
# -------------------------------------------------------------------

client = AsyncIOMotorClient(settings.MONGODB_URL)
db = client[settings.DATABASE_NAME]


# -------------------------------------------------------------------
# Providers
# -------------------------------------------------------------------

registry.register("spotify", SpotifyProvider())
registry.register("bandsintown", BandsintownProvider())

provider_manager = ProviderManager()


# -------------------------------------------------------------------
# Repositories
# -------------------------------------------------------------------

artist_repository = ArtistRepository(db)


# -------------------------------------------------------------------
# Services
# -------------------------------------------------------------------

discovery_service = DiscoveryService(
    artist_repository=artist_repository,
    provider_manager=provider_manager,
)


# -------------------------------------------------------------------
# Health Check
# -------------------------------------------------------------------

@app.get("/")
def health():
    return {"status": "ok"}


# -------------------------------------------------------------------
# Test Routes
# -------------------------------------------------------------------

@app.get("/test/search")
async def test_search(q: str):
    return await discovery_service.search_artist(
        "spotify",
        q,
    )


@app.post("/test/import")
async def test_import(data: dict):
    return await discovery_service.get_or_create_artist(data)