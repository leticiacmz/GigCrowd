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

from app.models.activity import (
    ActivityType,
    NotificationType,
)

from app.repositories.artist_repository import (
    ArtistRepository,
)

from app.repositories.follow_repository import (
    FollowRepository,
)

from app.repositories.user_repository import (
    UserRepository,
)

from app.services.activity_service import (
    ActivityService,
)

from app.services.follow_service import (
    FollowService,
)

from bson import ObjectId


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


async def _get_followed_user(
    username: str,
) -> dict | None:

    return await UserRepository(
        get_database()
    ).get_by_username(
        username
    )


async def _record_follow(
    follower: dict,
    followed: dict,
) -> None:
    """
    Turn a user follow into feed activity and a notification.

    Both are best effort: neither may fail the follow request itself.
    ActivityService.notify already skips self-notifications.
    """
    await ActivityService.record(
        follower["_id"],
        ActivityType.FOLLOW,
        target_id=str(ObjectId(followed["_id"])),
        target_type="user",
        metadata={
            "username": followed.get("username"),
            "avatar_url": followed.get("avatar_url"),
        },
    )

    await ActivityService.notify(
        recipient_id=str(followed["_id"]),
        actor_id=follower["_id"],
        notification_type=NotificationType.FOLLOW,
        related_entity_type="user",
        related_entity_id=str(followed["_id"]),
        context={"username": follower.get("username")},
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

        await _record_follow(

            current_user,

            await _get_followed_user(username),

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