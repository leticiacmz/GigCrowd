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
        asyncio.set_event_loop_policy(
            asyncio.WindowsProactorEventLoopPolicy()
        )
    except Exception:
        # If policy is already set, that's fine.
        pass


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


# The single background scheduler. Built from settings, so whether it does
# anything at all is a configuration decision rather than a code one.
scheduler = create_scheduler()


# =====================================================
# Lifespan
# =====================================================

@asynccontextmanager
async def lifespan(app: FastAPI):

    # Startup

    await db.connect()

    # Indexes are declared in one place and created here, so a fresh database
    # is usable immediately and a wiped one does not silently lose them.
    #
    # `ensure_indexes` contains its own failures: an index it cannot create is
    # reported rather than raised, because a missing index is a slow query, not
    # a reason to refuse to serve.
    index_report = await ensure_indexes(db.get_database())

    failed = [
        f"{collection}.{name}"
        for collection, names in index_report.items()
        for name in names
        if "FAILED" in name
    ]

    if failed:
        print(f"GigCrowd API started with index problems: {failed}")

    print("GigCrowd API started")

    # Started after the database is connected, because the first pass plans
    # against it. Disabled by default: this only does work when
    # ENRICHMENT_SCHEDULER_ENABLED says so.
    scheduler.start()

    try:
        yield
    finally:
        # Shutdown. In a `finally` so a failure during startup or a request
        # cannot leave a background thread making outbound requests after the
        # application has decided to stop.
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

    # Keep the explicitly configured origins from the environment.
    allow_origins=settings.CORS_ORIGINS,

    # Allow local network development without hardcoding
    # the machine's current IP address or the dev server's port.
    #
    # Examples:
    # http://localhost:3000
    # http://127.0.0.1:3000
    # http://localhost:3100
    # http://192.168.15.8:3000
    # http://192.168.15.13:3000
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

    # Prevent MIME type sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"

    # Prevent clickjacking
    response.headers["X-Frame-Options"] = "DENY"

    # XSS protection
    response.headers["X-XSS-Protection"] = "1; mode=block"

    # Referrer policy
    response.headers["Referrer-Policy"] = (
        "strict-origin-when-cross-origin"
    )

    # Content Security Policy
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'"
    )

    # Cache control for authenticated responses
    response.headers["Cache-Control"] = (
        "no-store, no-cache, must-revalidate, max-age=0"
    )
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    return response


# =====================================================
# Rate Limiting Middleware
# =====================================================

# Simple in-memory rate limiter (per IP)
_rate_limit_store: dict[str, list[float]] = {}

RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX_REQUESTS = 100  # max requests per window


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

    # Only rate limit auth endpoints
    if request.url.path.startswith("/auth/"):
        import time

        now = time.time()

        if client_ip not in _rate_limit_store:
            _rate_limit_store[client_ip] = []

        # Remove old entries
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
        # Scheduling facts only: no credentials, no source URLs and no page
        # content. Useful for confirming that enrichment is on in production and
        # off everywhere else.
        "scheduler": scheduler.get_status(),
    }


@app.get("/")
async def root():
    return {
        "status": "ok",
        "service": "GigCrowd API",
    }
