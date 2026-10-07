from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status as http_status,
)
from typing import Literal, Optional

from app.auth.dependencies import (
    get_current_active_user,
)

from app.database.connection import (
    get_database,
)

from app.repositories.follow_repository import (
    FollowRepository,
)

from app.repositories.user_repository import (
    UserRepository,
)

from app.services.user_profile_service import (
    UserProfileService,
)

from app.services.user_stats_service import (
    UserStatsService,
)

from app.services.user_concert_service import (
    SHOW_STATUS,
    UserConcertService,
    resolve_show_status,
)

from app.repositories.show_log_repository import (
    ShowLogRepository,
)

from app.repositories.event_repository import (
    EventRepository,
)

from app.schemas.user_concert import (
    ProfileArtistsResponse,
    ProfileArtistsSeenResponse,
    ProfileEventsPageResponse,
    ProfileEventsResponse,
    ProfileFestivalsResponse,
    ProfileShowCalendarResponse,
    ProfileShowYearResponse,
    ProfileReviewsResponse,
)

from app.schemas.user_stats import (
    UserStatsResponse,
)

from app.schemas.user_update import UserUpdateRequest

router = APIRouter(
    prefix="/users",
    tags=["users"],
)


def get_profile_service():

    db = get_database()

    return UserProfileService(
        user_repository=UserRepository(db),
        follow_repository=FollowRepository(db),
    )


def get_user_stats_service():

    db = get_database()

    return UserStatsService(
        user_repository=UserRepository(db),
        show_log_repository=ShowLogRepository(db),
        follow_repository=FollowRepository(db),
        db=db,
    )


def get_user_concert_service():

    db = get_database()

    return UserConcertService(
        user_repository=UserRepository(db),
        show_log_repository=ShowLogRepository(db),
        db=db,
        # "Artists I have seen" resolves the whole attendance history to
        # events, which is what lets a festival lineup contribute.
        event_repository=EventRepository(db),
    )


async def _require_profile(
    service: UserProfileService,
    username: str,
) -> dict:

    """Resolve a profile or fail with a 404.

    Every list below is about a person, so a missing person is a 404 rather
    than an empty list that would read as "this user has done nothing".
    """

    profile = await service.get_profile(
        username
    )

    if not profile:

        raise HTTPException(

            status_code=http_status.HTTP_404_NOT_FOUND,

            detail="User not found",

        )

    return profile


@router.get("/me")
async def get_me(

    current_user: dict = Depends(
        get_current_active_user
    ),

):

    return current_user


@router.get(
    "/profile/{username}",
)
async def get_profile(

    username: str,

    service: UserProfileService = Depends(
        get_profile_service
    ),

):

    profile = await service.get_profile(
        username
    )

    if not profile:

        raise HTTPException(

            status_code=http_status.HTTP_404_NOT_FOUND,

            detail="User not found",
        )

    return profile


@router.get(
    "/profile/{username}/stats",
    response_model=UserStatsResponse,
)
async def get_public_user_stats(

    username: str,

    stats_service: UserStatsService = Depends(
        get_user_stats_service
    ),

    profile_service: UserProfileService = Depends(
        get_profile_service
    ),

):

    profile = await profile_service.get_profile(
        username
    )

    if not profile:

        raise HTTPException(

            status_code=http_status.HTTP_404_NOT_FOUND,

            detail="User not found",
        )

    return await stats_service.get_user_stats(
        username
    )


@router.get(
    "/profile/{username}/reviews",
    response_model=ProfileReviewsResponse,
)
async def get_profile_reviews(

    username: str,

    limit: int = 12,

    service: UserConcertService = Depends(
        get_user_concert_service
    ),

    profile_service: UserProfileService = Depends(
        get_profile_service
    ),

):

    """The reviews a user wrote about the shows they attended.

    Public, because a review is already published to the timeline of everyone
    who follows the artist.
    """

    await _require_profile(profile_service, username)

    result = await service.get_reviews(
        username,
        limit=max(1, min(limit, 50)),
    )

    return ProfileReviewsResponse(**result)


@router.get(
    "/profile/{username}/events",
    response_model=ProfileEventsResponse,
)
async def get_profile_events(

    username: str,

    limit: int = 12,

    skip: int = 0,

    status: Optional[Literal["went", "attended", "i-went",
                             "going", "want-to-go", "maybe", "all"]] = None,

    service: UserConcertService = Depends(
        get_user_concert_service
    ),

    profile_service: UserProfileService = Depends(
        get_profile_service
    ),

):

    """The shows a user logged, in one of the three states a show can be in.

    `status` picks the state: the shows they attended, the ones they want to go
    to, or the ones they are undecided about. Every response carries the count
    for all three, so the breakdown on a profile is drawn from the same rows as
    the list behind it.

    An omitted `status` keeps the behaviour this endpoint has always had and
    returns the attended shows; `all` returns every logged show.

    Public, because what someone has already seen or already plans to see is
    exactly what a concert profile is for.
    """

    await _require_profile(profile_service, username)

    if status is None:

        selected = SHOW_STATUS

    else:

        try:
            selected = resolve_show_status(status)

        except ValueError as exc:

            raise HTTPException(
                status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            )

    result = await service.get_events(
        username,
        limit=max(1, min(limit, 50)),
        skip=max(0, skip),
        status=selected,
    )

    return ProfileEventsResponse(**result)


@router.get(
    "/profile/{username}/events/page",
    response_model=ProfileEventsPageResponse,
)
async def get_profile_events_page(

    username: str,

    before: Optional[str] = None,

    before_id: Optional[str] = None,

    limit: int = 40,

    status: Optional[Literal["went", "attended", "i-went",
                             "going", "want-to-go", "maybe", "all"]] = None,

    service: UserConcertService = Depends(
        get_user_concert_service
    ),

    profile_service: UserProfileService = Depends(
        get_profile_service
    ),

):

    """One page of the scrollable show history, addressed by cursor.

    The same rows and the same states as `/profile/{username}/events`, paged by
    cursor instead of by position, so the diary can be scrolled to the past without
    every page re-reading the pages before it.

    `before` and `before_id` are opaque: a client passes back whatever
    `next_cursor` it was last given, and never has to interpret it.
    """

    await _require_profile(profile_service, username)

    selected = SHOW_STATUS

    if status is not None:

        try:
            selected = resolve_show_status(status)

        except ValueError as exc:

            raise HTTPException(
                status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            )

    try:

        result = await service.get_events_page(
            username,
            status=selected,
            before_date=before,
            before_id=before_id,
            limit=max(1, min(limit, 50)),
        )

    except ValueError as exc:

        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    if result is None:

        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Profile not found.",
        )

    return ProfileEventsPageResponse(**result)


@router.get(
    "/profile/{username}/shows/calendar",
    response_model=ProfileShowCalendarResponse,
)
async def get_profile_show_calendar(

    username: str,

    year: int = Query(
        ..., ge=1900, le=2999,
        description="Calendar year to read.",
    ),

    month: int = Query(
        ..., ge=1, le=12,
        description="Calendar month to read, 1-12.",
    ),

    service: UserConcertService = Depends(
        get_user_concert_service
    ),

    profile_service: UserProfileService = Depends(
        get_profile_service
    ),

):

    """The days in one month on which this user says they went to a show.

    Only `went` marks a day. A `going` or `maybe` log records an intention, and
    being on a festival bill records that an act was announced - neither means
    anybody stood in the room, so neither may mark a day on a calendar of shows
    attended.

    Bounded to the requested month, so the caller pays for one month of history
    rather than all of it.
    """

    await _require_profile(profile_service, username)

    try:

        result = await service.get_attended_calendar(
            username,
            year=year,
            month=month,
        )

    except ValueError as exc:

        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    if result is None:

        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Profile not found.",
        )

    return ProfileShowCalendarResponse(**result)


@router.get(
    "/profile/{username}/shows/years",
    response_model=ProfileShowYearResponse,
)
async def get_profile_show_years(

    username: str,

    service: UserConcertService = Depends(
        get_user_concert_service
    ),

    profile_service: UserProfileService = Depends(
        get_profile_service
    ),

):
    """The years this user says they went to a show, newest first.

    Read-only and aggregated in the database. It exists so the profile calendar
    can offer the years a reader actually has shows in, instead of making
    somebody click from this year back to 2021 one month at a time to reach the
    night they had in mind.
    """

    await _require_profile(profile_service, username)

    try:

        result = await service.get_attended_years(
            username,
        )

    except ValueError as exc:

        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    if result is None:

        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Profile not found.",
        )

    return ProfileShowYearResponse(**result)


@router.get(
    "/profile/{username}/festivals",
    response_model=ProfileFestivalsResponse,
)
async def get_profile_festivals(

    username: str,

    service: UserConcertService = Depends(
        get_user_concert_service
    ),

    profile_service: UserProfileService = Depends(
        get_profile_service
    ),

):

    """The festivals a user has been to, one row per festival.

    Editions of the same festival collapse into one row, so the count is the
    number of festivals and not the number of tickets.
    """

    await _require_profile(profile_service, username)

    result = await service.get_festivals(
        username
    )

    return ProfileFestivalsResponse(**result)


@router.get(
    "/profile/{username}/artists",
    response_model=ProfileArtistsResponse,
)
async def get_profile_artists(

    username: str,

    limit: int = 12,

    service: UserConcertService = Depends(
        get_user_concert_service
    ),

    profile_service: UserProfileService = Depends(
        get_profile_service
    ),

):

    """The artists a user follows, which are the communities they belong to."""

    await _require_profile(profile_service, username)

    result = await service.get_artists(
        username,
        limit=max(1, min(limit, 50)),
    )

    return ProfileArtistsResponse(**result)


@router.get(
    "/profile/{username}/artists-seen",
    response_model=ProfileArtistsSeenResponse,
)
async def get_profile_artists_seen(

    username: str,

    limit: int = 12,

    skip: int = 0,

    service: UserConcertService = Depends(
        get_user_concert_service
    ),

    profile_service: UserProfileService = Depends(
        get_profile_service
    ),

):

    """The artists this user has actually seen, and how often.

    Attendance is the only source: a `went` show log, the event's own artist
    reference for a concert, and the event's lineup for a festival date. An
    artist the user merely follows does not appear unless they have been to a
    show, and only the lineup of the concrete event they attended counts - not
    every edition of the festival it belongs to.

    Public, because what someone has seen is what a concert profile is for.
    """

    await _require_profile(profile_service, username)

    result = await service.get_artists_seen(
        username,
        limit=max(1, min(limit, 200)),
        skip=max(0, skip),
    )

    return ProfileArtistsSeenResponse(**result)


@router.get(
    "/profile/{username}/connections",
)
async def get_connections(

    username: str,

    direction: Literal["followers", "following"] = "followers",

    limit: int = 50,

    service: UserProfileService = Depends(
        get_profile_service
    ),

):

    """
    List the people a user follows, or the people who follow them.

    Public, because a profile's social graph is public, and used by the
    profile page to render clickable usernames.
    """

    limit = max(1, min(limit, 100))

    profile = await service.get_profile(
        username
    )

    if not profile:

        raise HTTPException(

            status_code=http_status.HTTP_404_NOT_FOUND,

            detail="User not found",

        )


    connections = await service.get_connections(

        username=username,

        direction=direction,

        limit=limit,

    )


    return {

        "username": profile["username"],

        "direction": direction,

        "users": connections,

    }


@router.get(
    "/me/stats",
    response_model=UserStatsResponse,
)
async def get_my_stats(

    current_user: dict = Depends(
        get_current_active_user
    ),

    stats_service: UserStatsService = Depends(
        get_user_stats_service
    ),

):

    stats = await stats_service.get_user_stats(
        current_user["_id"]
    )

    if not stats:

        raise HTTPException(

            status_code=http_status.HTTP_404_NOT_FOUND,

            detail="User not found",
        )

    return stats

@router.put("/me")
async def update_me(

    user_data: UserUpdateRequest,

    current_user: dict = Depends(
        get_current_active_user
    ),

    service: UserProfileService = Depends(
        get_profile_service
    ),

):

    updated_user = await service.update_profile(
        current_user["_id"],
        user_data.model_dump(
            exclude_none=True
        ),
    )


    return {
        "message": "Profile updated successfully",
        "user": updated_user,
    }
