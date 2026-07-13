from fastapi import FastAPI

from app.routes import artists

from app.providers.registry import registry
from app.providers.spotify.provider import SpotifyProvider
from app.providers.bandsintown.provider import BandsintownProvider

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
