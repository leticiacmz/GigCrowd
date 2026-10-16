"""Festivals addressed by their series.

`GET /festivals/series/{series_id}` is the canonical address of a festival:
the identity of the whole series, not the festival behind one concrete date.
The date-keyed view stays where it was, at `GET /events/{id}/festival`,
because that is the festival a reader is standing on. Both call the same
service method chain and return the same `FestivalResponse`, so the same
festival reads the same whichever address reached it.
"""
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query

from app.config import settings
from app.database.connection import get_database
from app.repositories.artist_repository import ArtistRepository
from app.repositories.event_repository import EventRepository
from app.services.festival_service import FestivalService
from app.services.lineup_enrichment_service import (
    STATE_PENDING,
    service_for_database,
)


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


@router.post("/lineup/{event_id}/retry")
async def retry_lineup_enrichment(
    event_id: str,
    db=Depends(get_database),
):
    """Ask for one festival edition's own page to be read again.

    The only trigger that is neither an import nor a clock: a person looking
    at an edition that says `failed`, `partial`, `pending` for too long, or
    an empty lineup they know better about presses the button, and the same
    background pass runs again (`LineupEnrichmentService`). The response
    never waits for the page read - it reports the state the edition is left
    in, and the page sees progress on its next read.

    Answered without starting anything when the feature is off (409), when
    the edition does not exist (404), or when it is not a festival edition
    (400): a concert's lineup is its one artist, already associated, and has
    nothing to enrich. A retry while a worker is freshly mid-read changes
    nothing and says so, rather than stealing the claim.
    """

    if not settings.LINEUP_ENRICHMENT_ENABLED:
        raise HTTPException(
            status_code=409,
            detail=(
                "Lineup enrichment is disabled on this server."
            ),
        )

    try:
        identifier = ObjectId(event_id)
    except Exception:
        raise HTTPException(
            status_code=404,
            detail="No festival edition with that id.",
        )

    document = await db.events.find_one(
        {"_id": identifier},
        {"event_type": 1, "lineup_state": 1},
    )

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="No festival edition with that id.",
        )

    event_type = document.get("event_type") or ""

    if "festival" not in event_type.casefold():
        raise HTTPException(
            status_code=400,
            detail=(
                "Only a festival edition has a lineup to enrich."
            ),
        )

    service = service_for_database(db)

    if service is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Lineup enrichment is disabled on this server."
            ),
        )

    state = await service.enqueue(identifier, force=True)

    if state == STATE_PENDING:
        # Fire-and-forget: the person asking is not held hostage to a page
        # read. Any second request while this one is queued or running
        # finds the same claim and does no second read.
        service.schedule([str(identifier)])

    return {
        "event_id": str(identifier),
        "lineup_state": state or "unknown",
    }
