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

from app.repositories.follow_repository import (
    FollowRepository,
)

from app.repositories.user_repository import (
    UserRepository,
)

from app.services.follow_service import (
    FollowService,
)


router = APIRouter(
    prefix="/follows",
    tags=["follows"],
)



def get_follow_service():

    db = get_database()

    return FollowService(

        follow_repository=FollowRepository(
            db
        ),

        user_repository=UserRepository(
            db
        ),

    )



@router.post(
    "/{username}",
)
async def follow_user(

    username: str,

    current_user: dict = Depends(
        get_current_active_user
    ),

    service: FollowService = Depends(
        get_follow_service
    ),

):

    try:

        follow = await service.follow_user(

            follower_id=current_user["_id"],

            username=username,

        )


        return {

            "message":
                "User followed successfully",

            "follow":
                follow,

        }


    except ValueError as error:

        raise HTTPException(

            status_code=status.HTTP_400_BAD_REQUEST,

            detail=str(error),

        )



@router.delete(
    "/{username}",
)
async def unfollow_user(

    username: str,

    current_user: dict = Depends(
        get_current_active_user
    ),

    service: FollowService = Depends(
        get_follow_service
    ),

):

    try:

        deleted = await service.unfollow_user(

            follower_id=current_user["_id"],

            username=username,

        )


        if not deleted:

            raise HTTPException(

                status_code=status.HTTP_400_BAD_REQUEST,

                detail="Follow relationship not found",

            )


        return {

            "message":
                "User unfollowed successfully"

        }


    except ValueError as error:

        raise HTTPException(

            status_code=status.HTTP_400_BAD_REQUEST,

            detail=str(error),

        )



@router.get(
    "/{username}/status",
)
async def follow_status(

    username: str,

    current_user: dict = Depends(
        get_current_active_user
    ),

    service: FollowService = Depends(
        get_follow_service
    ),

):

    user = await UserRepository(
        get_database()
    ).get_by_username(
        username
    )


    if not user:

        raise HTTPException(

            status_code=status.HTTP_404_NOT_FOUND,

            detail="User not found",

        )


    following = await service.follow_repository.exists(

        follower_id=current_user["_id"],

        following_id=str(
            user["_id"]
        ),

    )


    return {

        "following":
            following

    }