from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from app.models.follow import FollowCreate
from app.services.follow_service import FollowService

from app.repositories.follow_repository import FollowRepository
from app.repositories.user_repository import UserRepository

from app.database.connection import get_database

from app.auth.dependencies import get_current_active_user


router = APIRouter(
    prefix="/follows",
    tags=["follows"]
)



def get_follow_service():

    db = get_database()

    return FollowService(

        follow_repository=FollowRepository(
            db
        ),

        user_repository=UserRepository(
            db
        )

    )



@router.post("")
async def follow_user(

    follow_data: FollowCreate,

    current_user: dict = Depends(
        get_current_active_user
    ),

    service: FollowService = Depends(
        get_follow_service
    )

):

    try:

        follow = await service.follow_user(

            follower_id=current_user["_id"],

            follow_data=follow_data

        )


        return follow


    except ValueError as error:

        raise HTTPException(

            status_code=status.HTTP_400_BAD_REQUEST,

            detail=str(error)

        )



@router.delete("/{following_id}")
async def unfollow_user(

    following_id: str,

    current_user: dict = Depends(
        get_current_active_user
    ),

    service: FollowService = Depends(
        get_follow_service
    )

):

    result = await service.unfollow_user(

        follower_id=current_user["_id"],

        following_id=following_id

    )


    if not result:

        raise HTTPException(

            status_code=status.HTTP_404_NOT_FOUND,

            detail="Follow relationship not found"

        )


    return {
        "message": "Unfollowed successfully"
    }



@router.get("/{user_id}/followers")
async def get_followers(

    user_id: str,

    skip: int = 0,

    limit: int = 20,

    service: FollowService = Depends(
        get_follow_service
    )

):

    return await service.get_followers(

        user_id=user_id,

        skip=skip,

        limit=limit

    )



@router.get("/{user_id}/following")
async def get_following(

    user_id: str,

    skip: int = 0,

    limit: int = 20,

    service: FollowService = Depends(
        get_follow_service
    )

):

    return await service.get_following(

        user_id=user_id,

        skip=skip,

        limit=limit

    )