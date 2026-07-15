from fastapi import FastAPI

from app.routes import artists

from app.providers.registry import registry
from app.providers.spotify.provider import SpotifyProvider
from app.providers.bandsintown.provider import BandsintownProvider
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="GigCrowd")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
