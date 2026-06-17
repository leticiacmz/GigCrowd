from fastapi import APIRouter, Depends, HTTPException, status, Query
from app.models.artist import ArtistCreate, ArtistResponse, ArtistUpdate
from app.services.artist_service import ArtistService
from typing import List

router = APIRouter(prefix="/artists", tags=["artists"])


@router.post("", response_model=ArtistResponse, status_code=status.HTTP_201_CREATED)
async def create_artist(artist_data: ArtistCreate):
    """Create a new artist"""
    try:
        artist = await ArtistService.create_artist(artist_data)
        return ArtistResponse(**artist.model_dump())
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("", response_model=List[ArtistResponse])
async def get_artists(skip: int = 0, limit: int = 50):
    """Get all artists"""
    artists = await ArtistService.get_artists(skip, limit)
    return [ArtistResponse(**artist.model_dump()) for artist in artists]


@router.get("/search", response_model=List[ArtistResponse])
async def search_artists(q: str = Query(..., min_length=1), skip: int = 0, limit: int = 50):
    """Search artists by name"""
    artists = await ArtistService.search_artists(q, skip, limit)
    return [ArtistResponse(**artist.model_dump()) for artist in artists]


@router.get("/{artist_id}", response_model=ArtistResponse)
async def get_artist(artist_id: str):
    """Get artist by ID"""
    artist = await ArtistService.get_artist_by_id(artist_id)
    if not artist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artist not found"
        )
    return ArtistResponse(**artist.model_dump())


@router.put("/{artist_id}", response_model=ArtistResponse)
async def update_artist(artist_id: str, artist_data: ArtistUpdate):
    """Update artist"""
    artist = await ArtistService.update_artist(artist_id, artist_data)
    if not artist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artist not found"
        )
    return ArtistResponse(**artist.model_dump())
