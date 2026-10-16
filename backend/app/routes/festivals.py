"""Festivals addressed by their series.

`GET /festivals/series/{series_id}` is the canonical address of a festival:
the identity of the whole series, not the festival behind one concrete date.
The date-keyed view stays where it was, at `GET /events/{id}/festival`,
because that is the festival a reader is standing on. Both call the same
service method chain and return the same `FestivalResponse`, so the same
festival reads the same whichever address reached it.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database.connection import get_database
from app.repositories.artist_repository import ArtistRepository
from app.repositories.event_repository import EventRepository
from app.services.festival_service import FestivalService


router = APIRouter(
    prefix="/festivals",
    tags=["festivals"],
)


@router.get("/series/{series_id}")
async def get_festival_series(
    series_id: str,
    edition: Optional[str] = Query(
        None,
        description=(
            "The event id of the edition whose lineup the page "
            "opens on. Ignored when it is not an edition of "
            "this series."
        ),
    ),
    db=Depends(get_database),
):
    """The festival a series id names: identity, every date, one lineup.

    Asked with no record in hand, so the page costs one request instead of
    one per edition and one per artist - the same assembly the date-keyed
    endpoint uses, reached by the festival's own id rather than by one of
    its dates' ids.
    """

    festival = await FestivalService(
        EventRepository(db),
        artist_repository=ArtistRepository(db),
    ).get_series(
        series_id,
        edition_event_id=edition,
    )

    if not festival:

        raise HTTPException(
            status_code=404,
            detail="Festival series not found",
        )

    return festival
