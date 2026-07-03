from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database.connection import db

from app.jobs.scheduler import create_scheduler

from app.routes import (
    auth,
    users,
    follows,
    artists,
    events,
    posts,
    feed,
    show_logs,
    spotify_auth,
)

# Cria UMA única instância do scheduler
scheduler = create_scheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""

    # Startup
    await db.connect()
    scheduler.start()

    yield

    # Shutdown
    scheduler.shutdown()
    await db.disconnect()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(follows.router)
app.include_router(artists.router)
app.include_router(events.router)
app.include_router(posts.router)
app.include_router(feed.router)
app.include_router(show_logs.router)
app.include_router(spotify_auth.router)


@app.get("/")
async def root():
    return {
        "message": "Welcome to GigCrowd API",
        "version": settings.APP_VERSION,
        "status": "healthy",
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "scheduler": scheduler.get_job_status(),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
    )