from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from typing import Literal

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
    UserConcertService,
)

from app.repositories.show_log_repository import (
    ShowLogRepository,
)

from app.schemas.user_concert import (
    ProfileArtistsResponse,
    ProfileEventsResponse,
    ProfileFestivalsResponse,
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

            status_code=status.HTTP_404_NOT_FOUND,

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

            status_code=status.HTTP_404_NOT_FOUND,

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

            status_code=status.HTTP_404_NOT_FOUND,

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

    service: UserConcertService = Depends(
        get_user_concert_service
    ),

    profile_service: UserProfileService = Depends(
        get_profile_service
    ),

):

    """The shows a user says they attended, most recent first."""

    await _require_profile(profile_service, username)

    result = await service.get_events(
        username,
        limit=max(1, min(limit, 50)),
    )

    return ProfileEventsResponse(**result)


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

            status_code=status.HTTP_404_NOT_FOUND,

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

            status_code=status.HTTP_404_NOT_FOUND,

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
