from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient

from app.providers.registry import registry
from app.providers.spotify import SpotifyProvider
from app.providers.bandsintown import BandsintownProvider

from app.repositories.artist_repository import ArtistRepository
from app.core.config import settings

app = FastAPI()


# DB CONNECTION
client = AsyncIOMotorClient(settings.MONGODB_URL)
db = client[settings.DATABASE_NAME]


# PROVIDERS
registry.register("spotify", SpotifyProvider())
registry.register("bandsintown", BandsintownProvider())


# (por enquanto só pra teste manual)
artist_repo = ArtistRepository(db)


@app.get("/")
def health():
    return {"status": "ok"}