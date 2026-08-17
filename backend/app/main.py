import asyncio
import sys
import os
from contextlib import asynccontextmanager

# =====================================================
# Windows Event Loop Policy for Playwright
# =====================================================
# Playwright requires subprocess support on Windows.
# The default SelectorEventLoop doesn't support subprocesses,
# so we use ProactorEventLoopPolicy on Windows.
# This must be set at module level before any async operations.
if sys.platform == "win32":
    os.environ["PYTHONUNBUFFERED"] = "1"
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception as e:
        # If policy is already set, that's fine
        pass

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
    user_stats
)
from app.config import settings

from app.providers.registry import registry
from app.providers.spotify.provider import SpotifyProvider
from app.providers.bandsintown.provider import BandsintownProvider
from app.providers.songkick.provider import SongkickProvider



# =====================================================
# Lifespan
# =====================================================

@asynccontextmanager
async def lifespan(app: FastAPI):

    # Startup

    await db.connect()

    print("GigCrowd API started")


    yield


    # Shutdown

    await db.disconnect()

    print("GigCrowd API stopped")



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

    allow_origins=settings.CORS_ORIGINS,

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

registry.register(
    "songkick",
    SongkickProvider(),
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

app.include_router(user_stats.router)

# =====================================================
# Health Check
# =====================================================

@app.get("/")
async def health():

    return {
        "status": "ok",
        "service": "GigCrowd API",
    }