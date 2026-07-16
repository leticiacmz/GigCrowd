from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import get_current_active_user
from app.schemas.user_stats import UserStatsResponse
from app.services.user_stats_service import UserStatsService

from app.database.connection import get_database

from app.repositories.user_repository import UserRepository
from app.repositories.show_log_repository import ShowLogRepository


router = APIRouter(
    prefix="/users",
    tags=["users"]
)



def get_user_stats_service():

    db = get_database()

    return UserStatsService(

        user_repository=UserRepository(db),

        show_log_repository=ShowLogRepository(db),

        db=db
    )



@router.get(
    "/me/stats",
    response_model=UserStatsResponse
)
async def get_user_stats(

    current_user: dict = Depends(
        get_current_active_user
    ),

    service: UserStatsService = Depends(
        get_user_stats_service
    )

):

    stats = await service.get_user_stats(
        current_user["_id"]
    )


    if not stats:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )


    return stats