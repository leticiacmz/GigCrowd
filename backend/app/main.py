from fastapi import FastAPI

from app.routes import artists

from app.providers.registry import registry
from app.providers.spotify.provider import SpotifyProvider
from app.providers.bandsintown.provider import BandsintownProvider
from app.providers.spotify.auth import spotify_auth
from app.providers.bandsintown.client import BandsintownClient

app = FastAPI(title="GigCrowd")


# ----------------------------------------------------
# Providers
# ----------------------------------------------------

registry.register("spotify", SpotifyProvider())
registry.register("bandsintown", BandsintownProvider())


# ----------------------------------------------------
# Routers
# ----------------------------------------------------

app.include_router(artists.router)


# ----------------------------------------------------
# Health
# ----------------------------------------------------

@app.get("/")
def health():
    return {
        "status": "ok",
    }

@app.get("/test/bandsintown")
async def test_bandsintown():

    client = BandsintownClient()

    return await client.get_artist_events(
        "Coldplay"
    )