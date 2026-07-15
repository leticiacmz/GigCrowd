from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database.connection import db

from app.routes import (
    artists,
    auth,
    users,
    events,
    posts,
    feed,
    follows,
    show_logs,
    spotify_auth,
)

from app.providers.registry import registry
from app.providers.spotify.provider import SpotifyProvider
from app.providers.bandsintown.provider import BandsintownProvider



# =====================================================
# Lifespan
# =====================================================

@asynccontextmanager
async def lifespan(app: FastAPI):

    # Startup

    await db.connect()

    print("🚀 GigCrowd API started")


    yield


    # Shutdown

    await db.disconnect()

    print("🛑 GigCrowd API stopped")



# =====================================================
# Application
# =====================================================

app = FastAPI(
    title="GigCrowd",
    lifespan=lifespan,
)



# =====================================================
# CORS
# =====================================================

app.add_middleware(
    CORSMiddleware,

    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],

    allow_credentials=True,

    allow_methods=["*"],

    allow_headers=["*"],
)



# =====================================================
# Providers
# =====================================================

registry.register(
    "spotify",
    SpotifyProvider(),
)


registry.register(
    "bandsintown",
    BandsintownProvider(),
)



# =====================================================
# Routers
# =====================================================

app.include_router(auth.router)

app.include_router(users.router)

app.include_router(artists.router)

app.include_router(events.router)

app.include_router(posts.router)

app.include_router(feed.router)

app.include_router(follows.router)

app.include_router(show_logs.router)

app.include_router(spotify_auth.router)



# =====================================================
# Health Check
# =====================================================

@app.get("/")
async def health():

    return {
        "status": "ok",
        "service": "GigCrowd API",
    }