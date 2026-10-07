from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings
from app.services.artist_search_service import ArtistSearchService
from app.services.artist_import_service import ArtistImportService
from app.services.provider_manager import ProviderManager
from app.services.recommendation_service import RecommendationService
from app.schemas.artist_import import ArtistImportRequest

from app.repositories.artist_repository import ArtistRepository
from app.repositories.event_repository import EventRepository
from app.repositories.venue_repository import VenueRepository

from app.services.event_import_service import EventImportService
from app.services.event_enrichment_service import (
    EventEnrichmentService,
)
from app.services.event_service import EventService

from app.services.artist_service import ArtistService

from app.services.synchronization_service import (
    SynchronizationService,
)

from app.schemas.event_response import EventResponse

from app.schemas.artist_profile_response import (
    ArtistProfileResponse,
)

from app.schemas.artist_list_response import (
    ArtistListResponse,
)

from app.mappers.artist_response_mapper import ArtistResponseMapper

from app.database.connection import get_database

from app.repositories.artist_follow_repository import (
    ArtistFollowRepository,
)

from app.services.artist_follow_service import (
    ArtistFollowService,
)

from app.schemas.artist_follow_response import (
    ArtistFollowResponse,
)

from app.auth.dependencies import (
    get_current_active_user,
)

from app.core.logger import get_logger

logger = get_logger("artist_routes")


router = APIRouter(
    prefix="/artists",
    tags=["Artists"],
)



client = AsyncIOMotorClient(
    settings.MONGODB_URL
)

db = client[
    settings.DATABASE_NAME
]

# ----------------------------------------------------
# Repositories
# ----------------------------------------------------

artist_repository = ArtistRepository(
    db
)


event_repository = EventRepository(
    db
)


venue_repository = VenueRepository(
    db
)


artist_follow_repository = ArtistFollowRepository(
    db
)



# ----------------------------------------------------
# Providers
# ----------------------------------------------------

provider_manager = ProviderManager()



# ----------------------------------------------------
# Services
# ----------------------------------------------------

artist_search_service = ArtistSearchService(
    provider_manager=provider_manager,
    artist_repository=artist_repository,
)



artist_import_service = ArtistImportService(
    provider_manager=provider_manager,
    artist_repository=artist_repository,
)



# Enrichment is one service shared by the import path and the scheduler, so a
# date recovered during an import and one recovered by a scheduled run travel
# through identical logic. It is built here, next to the repositories that own
# the data, and handed to the importer.
event_enrichment_service = (
    EventEnrichmentService(event_repository)
    if settings.ENRICH_ON_IMPORT_ENABLED
    else None
)


event_import_service = EventImportService(
    provider_manager=provider_manager,
    event_repository=event_repository,
    venue_repository=venue_repository,
    artist_repository=artist_repository,
    enrichment_service=event_enrichment_service,
)



synchronization_service = SynchronizationService(
    artist_repository=artist_repository,
    event_import_service=event_import_service,
)


artist_service = ArtistService(
    artist_repository=artist_repository,
    event_repository=event_repository,
    artist_follow_repository=artist_follow_repository,
)


recommendation_service = RecommendationService()


event_service = EventService(
    event_repository=event_repository,
    venue_repository=venue_repository,
    artist_repository=artist_repository,
)



artist_follow_service = ArtistFollowService(
    repository=artist_follow_repository,
    artist_repository=artist_repository,
)



# ----------------------------------------------------
# Routes
# ----------------------------------------------------


@router.get("/search")
async def search_artist(
    q: str,
):

    return await artist_search_service.search_artist(
        q
    )



@router.post("/import")
async def import_artist(
    data: ArtistImportRequest,
):

    # Selecting an artist from search is a request to bring that artist here,
    # and "here" is the artist *and* their shows. This route used to stop after
    # writing the artist row, which left the catalogue holding an artist with an
    # empty page: the person searched, chose the right act, and nothing appeared.
    #
    # The missing step was never "wrong", it was absent, and its absence was
    # invisible - the response said `is_imported: true`, which reads as success.
    # So the synchronization runs here, explicitly, as part of the import, and
    # the outcome travels back in the response.
    #
    # This is the only place a gigography fetch is triggered by a reader's
    # action. `GET /artists/{slug}` remains read-only, and the scheduler remains
    # the long-term safety net for artists nobody has selected yet.
    try:

        if data.provider == "spotify":

            result = (
                await artist_import_service
                .import_from_spotify(
                    spotify_artist_id=(
                        data.provider_artist_id
                    )
                )
            )

        else:

            result = (
                await artist_import_service
                .import_artist(data)
            )

    except NotImplementedError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )

    except ValueError as error:

        # Unresolvable / mismatched identity is a controlled
        # client error, never a silent fallback to another artist.
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )

    artist = result["artist"]

    sync = await _synchronize_artist(
        artist,
    )

    # Built as the artist profile response this route has always returned, plus
    # the one fact it now also knows. Returning a different shape here would
    # break every caller reading `external_ids` for no reason.
    response = ArtistResponseMapper.to_response(
        artist
    )

    response.sync = sync

    return response


async def _synchronize_artist(artist, *, claimed: bool = False):
    """Run the existing synchronization flow for an artist that needs it.

    `force=True` because both callers have already decided this fetch is wanted.
    The TTL guard exists to stop a *scheduler* re-fetching an artist that was
    read recently; applying it to a person who imported an artist or opened their
    page for the first time would mean an explicit request silently did nothing.

    Reuses `SynchronizationService` unchanged - no second synchronization path,
    and nothing here decides *how* to import, only that this fetch is asked for.

    `claimed` says the caller has already taken the initialization claim, and so
    is responsible for releasing it if the fetch could not be started. A caller
    that has not claimed does not release: it has nothing to release, and
    clearing another caller's claim would be worse than doing nothing.

    Never raises. A provider failure must not undo a successful artist write: the
    artist is real and persisted at this point, and a person can try again.
    Turning a partial success into an error response would leave the caller unable
    to tell "not imported" from "imported but the shows did not come".
    """

    from app.schemas.artist_response import ArtistSyncOutcome

    if synchronization_service is None:

        if claimed:
            await artist_repository.release_initialization_claim(
                artist.id
            )

        return ArtistSyncOutcome(
            attempted=False,
            succeeded=False,
            reason="synchronization is not configured",
        )

    try:

        outcome = await synchronization_service.synchronize_artist(
            artist,
            force=True,
        )

    except Exception as exc:

        logger.warning(
            f"[ARTIST INIT] '{artist.name}' could not be "
            f"synchronized: {exc}"
        )

        # `synchronize_artist` records `sync_status = "error"` before it
        # re-raises, which is what clears the claim: the artist is left in a
        # state a person - not the scheduler - can retry.
        return ArtistSyncOutcome(
            attempted=True,
            succeeded=False,
            reason=f"{type(exc).__name__}: {exc}"[:200],
        )

    if not outcome.get("synced"):

        return ArtistSyncOutcome(
            attempted=True,
            succeeded=False,
            reason=str(outcome.get("reason") or "not synchronized"),
        )

    import_result = outcome.get("result") or {}

    return ArtistSyncOutcome(
        attempted=True,
        succeeded=True,
        events_received=int(import_result.get("events_received") or 0),
        events_created=int(import_result.get("events_created") or 0),
        events_existing=int(import_result.get("events_existing") or 0),
    )


async def _initialize_pending_artist(artist):
    """First open of an artist that only exists as a lineup record.

    A festival announced this act, the identity was checked against their own
    Songkick page, and a minimal record was written so the name in the lineup
    would be pressable. That record knows who they are and nothing about when
    they play.

    This is where the rest is learned, and it happens once - the first person to
    open the page. Every later open is a plain read.

    The claim is what makes "once" true rather than merely likely. Two people
    opening a cold artist at the same moment is an ordinary thing for a catalogue
    to see; without a compare-and-set, both would decide nobody had claimed it
    and both would spend a full gigography scrape to produce the same rows. The
    loser of the race does nothing at all and reads the artist as it stands.

    The TTL is not consulted, and neither is the scheduler. Being new is the whole
    reason this is allowed to fetch.
    """

    from app.schemas.artist_response import ArtistSyncOutcome

    claimed = await artist_repository.claim_initialization(
        artist.id
    )

    if not claimed:

        # Somebody else is fetching, or already has. Either way this request has
        # nothing to do, and saying so is better than queueing behind a four
        # minute scrape to return the same page.
        logger.info(
            f"[ARTIST INIT] {artist.slug} is already being "
            f"initialized; serving the stored record"
        )

        return ArtistSyncOutcome(
            attempted=False,
            succeeded=False,
            reason="already being initialized",
        )

    logger.info(
        f"[ARTIST INIT] first open of '{artist.name}'; "
        f"fetching their gigography"
    )

    return await _synchronize_artist(artist, claimed=True)


@router.get(
    "",
    response_model=list[ArtistListResponse],
)
async def get_artists(
    limit: int = 20,
    skip: int = 0,
):

    return await artist_service.get_artists(
        limit=limit,
        skip=skip,
    )





@router.get(
    "/{artist_slug}",
    response_model=ArtistProfileResponse,
)
async def get_artist(
    artist_slug: str,
):
    """One artist's page.

    Reads, with exactly one exception: a page for an artist that has never been
    initialized is also the moment that artist is initialized.

    The exception is narrow and it is the point. A festival announced this act and
    a minimal, identity-checked record exists so their name in the lineup is
    pressable - but nobody has fetched their gigography. Somebody opens the page
    expecting to see a discography, and the honest way to deliver one is to fetch
    it rather than to render an empty page and an apology.

    Everything else is a read. An initialized artist - including one whose
    synchronization previously failed - is never re-fetched here, because a page
    view that scrapes a provider is what made this application's artist pages
    slow, expensive and impossible to reason about: the catalogue depended on who
    happened to look, one request could spend an unbounded number of calls, and
    opening a page wrote rows nobody asked it to write.

    So the distinction is the artist's state, and it is checked before anything is
    fetched rather than after:

        pending / errored  -> may initialize, exactly once, under a claim
        initialized        -> read-only, every time
    """

    from app.domain.artist_state import may_initialize

    artist = await artist_repository.get_by_slug(
        artist_slug
    )

    if artist is None:

        raise HTTPException(
            status_code=404,
            detail="Artist not found",
        )

    sync = None

    # A failed attempt is retried on a cooldown rather than on every view, so a
    # permanently broken identity cannot turn page loads into a stream of failed
    # provider requests. A pending artist has never been asked and is never cooled
    # down - delaying its first fetch would only hand the reader an empty page.
    if may_initialize(
        artist,
        retry_cooldown=timedelta(
            hours=settings.ARTIST_SYNC_TTL_HOURS
        ),
    ):

        sync = await _initialize_pending_artist(
            artist
        )

        # Re-read, so the response describes what the fetch actually stored
        # rather than the record as it was a minute ago. The freshly imported
        # events are the entire reason the reader came.
        artist = await artist_repository.get_by_slug(
            artist_slug
        )

    profile = await artist_service.get_artist_profile(
        artist_slug
    )

    if sync is not None:

        profile.sync = sync

    return profile





@router.get(
    "/{artist_slug}/events",
    response_model=list[EventResponse],
)
async def get_artist_events(
    artist_slug: str,
):

    return await event_service.get_artist_events(
        artist_slug
    )





@router.get(
    "/{artist_slug}/events/all",
)
async def get_all_artist_events(
    artist_slug: str,
):

    return await event_service.get_all_artist_events(
        artist_slug
    )





# ----------------------------------------------------
# Follow
# ----------------------------------------------------


@router.post(
    "/{artist_slug}/follow",
    response_model=ArtistFollowResponse,
)
async def follow_artist(
    artist_slug: str,
    current_user: dict = Depends(
        get_current_active_user
    ),
):

    return await artist_follow_service.follow(
        user_id=current_user["_id"],
        artist_slug=artist_slug,
    )





@router.delete(
    "/{artist_slug}/follow",
    response_model=ArtistFollowResponse,
)
async def unfollow_artist(
    artist_slug: str,
    current_user: dict = Depends(
        get_current_active_user
    ),
):

    return await artist_follow_service.unfollow(
        user_id=current_user["_id"],
        artist_slug=artist_slug,
    )





@router.get(
    "/{artist_slug}/follow",
    response_model=ArtistFollowResponse,
)
async def get_follow_status(
    artist_slug: str,
    current_user: dict = Depends(
        get_current_active_user
    ),
):

    return await artist_follow_service.status(
        user_id=current_user["_id"],
        artist_slug=artist_slug,
    )


@router.get(
    "/{artist_slug}/related",
)
async def get_related_artists(
    artist_slug: str,
):
    """
    Get related artists using Spotify for discovery.
    
    Phase 4: This uses Spotify for discovery/recommendation only.
    Does not create canonical artists.
    """
    artist = await artist_repository.get_by_slug(artist_slug)
    
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    
    # Use RecommendationService to get related artists from Spotify
    related = await recommendation_service.get_related_artists(artist.name)
    
    return {
        "artist": artist.name,
        "related_artists": related,
        "source": "spotify_discovery"
    }