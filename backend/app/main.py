
import asyncio
import sys
import os
from contextlib import asynccontextmanager

# =====================================================
# Windows Event Loop Policy for Playwright
# =====================================================

if sys.platform == "win32":
   
    asyncio.set_event_loop_policy(
        asyncio.WindowsProactorEventLoopPolicy()
        )

os.environ["PYTHONUNBUFFERED"] = "1"

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.database.connection import db
from app.database.indexes import ensure_indexes

from app.routes import (
    artists,
    auth,
    users,
    events,
    search,
    posts,
    feed,
    follows,
    show_logs,
    spotify_auth,
    artist_community,
    notifications,
    media,
)

from app.config import settings

from app.providers.registry import registry
from app.providers.spotify.provider import SpotifyProvider
from app.providers.songkick.provider import SongkickProvider

from app.jobs.scheduler import create_scheduler


# =====================================================
# Scheduler
# =====================================================

# The scheduler is configured through application settings.
scheduler = create_scheduler()


# =====================================================
# Lifespan
# =====================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await db.connect()

    # Create the indexes required by the application.
    index_report = await ensure_indexes(db.get_database())

    failed = [
        f"{collection}.{name}"
        for collection, names in index_report.items()
        for name in names
        if "FAILED" in name
    ]

    if failed:
        print(
            f"GigCrowd API started with index problems: {failed}"
        )

    print("GigCrowd API started")

    # Start background jobs after the database connection is ready.
    scheduler.start()

    try:
        yield
    finally:
        # Stop background jobs before disconnecting from the database.
        scheduler.shutdown()
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
    allow_origin_regex=(
        r"^https?://"
        r"(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+)"
        r":\d+$"
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =====================================================
# Security Headers Middleware
# =====================================================

@app.middleware("http")
async def security_headers_middleware(
    request: Request,
    call_next,
):
    response = await call_next(request)

    # Prevent MIME type sniffing.
    response.headers["X-Content-Type-Options"] = "nosniff"

    # Prevent clickjacking.
    response.headers["X-Frame-Options"] = "DENY"

    # Legacy browser XSS protection header.
    response.headers["X-XSS-Protection"] = "1; mode=block"

    # Control how much referrer information is sent.
    response.headers["Referrer-Policy"] = (
        "strict-origin-when-cross-origin"
    )

    # Content Security Policy.
    if request.url.path in {"/docs", "/redoc"}:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "base-uri 'self'; "
            "object-src 'none'; "
            "frame-ancestors 'none'; "
            "style-src 'self' 'unsafe-inline' "
            "https://cdn.jsdelivr.net "
            "https://fonts.googleapis.com; "
            "style-src-elem 'self' 'unsafe-inline' "
            "https://cdn.jsdelivr.net "
            "https://fonts.googleapis.com; "
            "script-src 'self' 'unsafe-inline' "
            "https://cdn.jsdelivr.net; "
            "img-src 'self' data: "
            "https://fastapi.tiangolo.com; "
            "font-src 'self' data: "
            "https://fonts.gstatic.com; "
            "connect-src 'self'"
        )
    else:
        # Use a restrictive policy for the rest of the application.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "base-uri 'self'; "
            "object-src 'none'; "
            "frame-ancestors 'none'"
        )

    # Prevent caching of responses, including authenticated responses.
    response.headers["Cache-Control"] = (
        "no-store, no-cache, must-revalidate, max-age=0"
    )
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    return response


# =====================================================
# Rate Limiting Middleware
# =====================================================

# Simple in-memory rate limiter, tracked per client IP.
_rate_limit_store: dict[str, list[float]] = {}

RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX_REQUESTS = 100


@app.middleware("http")
async def rate_limit_middleware(
    request: Request,
    call_next,
):
    client_ip = (
        request.client.host
        if request.client
        else "unknown"
    )

    # Apply rate limiting only to authentication endpoints.
    if request.url.path.startswith("/auth/"):
        import time

        now = time.time()

        if client_ip not in _rate_limit_store:
            _rate_limit_store[client_ip] = []

        # Remove timestamps outside the current time window.
        _rate_limit_store[client_ip] = [
            timestamp
            for timestamp in _rate_limit_store[client_ip]
            if now - timestamp < RATE_LIMIT_WINDOW
        ]

        if (
            len(_rate_limit_store[client_ip])
            >= RATE_LIMIT_MAX_REQUESTS
        ):
            return JSONResponse(
                status_code=429,
                content={
                    "detail": (
                        "Too many requests. "
                        "Please try again later."
                    )
                },
            )

        _rate_limit_store[client_ip].append(now)

    return await call_next(request)


# =====================================================
# Providers
# =====================================================

registry.register(
    "spotify",
    SpotifyProvider(),
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
app.include_router(search.router)
app.include_router(posts.router)
app.include_router(media.router)
app.include_router(feed.router)
app.include_router(follows.router)
app.include_router(show_logs.router)
app.include_router(spotify_auth.router)
app.include_router(artist_community.router)
app.include_router(notifications.router)


# =====================================================
# Health Check
# =====================================================

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "GigCrowd API",
        "scheduler": scheduler.get_status(),
    }


@app.get("/")
async def root():
    return {
        "status": "ok",
        "service": "GigCrowd API",
    }