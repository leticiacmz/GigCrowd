from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings

from app.providers.registry import registry
from app.providers.spotify import SpotifyProvider
from app.providers.bandsintown import BandsintownProvider

from app.repositories.artist_repository import ArtistRepository

from app.services.provider_manager import ProviderManager
from app.services.artist_search_service import ArtistSearchService
from app.services.artist_import_service import ArtistImportService

app = FastAPI(title="GigCrowd")


# ----------------------------------------------------
# Database
# ----------------------------------------------------

client = AsyncIOMotorClient(settings.MONGODB_URL)
db = client[settings.DATABASE_NAME]


# ----------------------------------------------------
# Providers
# ----------------------------------------------------

registry.register("spotify", SpotifyProvider())
registry.register("bandsintown", BandsintownProvider())

provider_manager = ProviderManager()


# ----------------------------------------------------
# Repositories
# ----------------------------------------------------

artist_repository = ArtistRepository(db)


# ----------------------------------------------------
# Services
# ----------------------------------------------------

artist_search_service = ArtistSearchService(
    provider_manager=provider_manager,
)

artist_import_service = ArtistImportService(
    artist_repository=artist_repository,
)


# ----------------------------------------------------
# Health
# ----------------------------------------------------

@app.get("/")
def health():
    return {"status": "ok"}


# ----------------------------------------------------
# Test Routes
# ----------------------------------------------------

@app.get("/test/search")
async def test_search(q: str):
    return await artist_search_service.search_artist(q)


@app.post("/test/import")
async def test_import(data: dict):
    return await artist_import_service.import_artist(data)