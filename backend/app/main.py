from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings

from app.providers.registry import registry
from app.providers.spotify import SpotifyProvider
from app.providers.bandsintown import BandsintownProvider

from app.repositories.artist_repository import ArtistRepository
from app.services.discovery_service import DiscoveryService

app = FastAPI(title="GigCrowd")

client = AsyncIOMotorClient(settings.MONGODB_URL)
db = client[settings.DATABASE_NAME]

artist_repo = ArtistRepository(db)
discovery_service = DiscoveryService(artist_repo)

registry.register("spotify", SpotifyProvider())
registry.register("bandsintown", BandsintownProvider())


@app.get("/")
def health():
    return {"status": "ok"}


# TEST SEARCH
@app.get("/test/search")
async def test_search(q: str):
    return await discovery_service.search_artist("spotify", q)


# TEST IMPORT
@app.post("/test/import")
async def test_import(data: dict):
    return await discovery_service.get_or_create_artist(data)