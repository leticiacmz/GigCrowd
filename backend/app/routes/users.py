from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from app.auth.dependencies import (
    get_current_active_user,
)

from app.database.connection import (
    get_database,
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

from app.repositories.show_log_repository import (
    ShowLogRepository,
)

from app.schemas.user_stats import (
    UserStatsResponse,
)

router = APIRouter(
    prefix="/users",
    tags=["users"],
)


def get_profile_service():

    db = get_database()

    return UserProfileService(
        user_repository=UserRepository(db),
    )


def get_user_stats_service():

    db = get_database()

    return UserStatsService(
        user_repository=UserRepository(db),
        show_log_repository=ShowLogRepository(db),
        db=db,
    )


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