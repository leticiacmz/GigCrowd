from fastapi import FastAPI

from app.routes import artists

from app.providers.registry import registry
from app.providers.spotify.provider import SpotifyProvider
from app.providers.bandsintown import BandsintownProvider
from app.providers.spotify.auth import spotify_auth


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

@app.get("/test/token")
async def test_token():
    token = await spotify_auth.get_access_token()

    return {
        "token": token[:20]
    }