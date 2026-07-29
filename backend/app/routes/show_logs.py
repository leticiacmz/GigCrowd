from typing import List

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

from app.models.show_log import (
    AttendanceStatus,
    ShowLogCreate,
    ShowLogResponse,
    ShowLogUpdate,
)

from app.repositories.event_repository import (
    EventRepository,
)

from app.repositories.show_log_repository import (
    ShowLogRepository,
)


from app.services.show_log_service import (
    ShowLogService,
)


router = APIRouter(
    prefix="/show-logs",
    tags=["show-logs"],
)


def get_show_log_service():

    db = get_database()

    show_log_repository = ShowLogRepository(
        db
    )

    event_repository = EventRepository(
        db
    )

    return ShowLogService(
        show_log_repository,
        event_repository,
    )


@router.get(
    "/my",
    response_model=List[ShowLogResponse],
)
async def get_my_show_logs(

    skip: int = 0,

    limit: int = 50,

    status: AttendanceStatus | None = None,

    current_user: dict = Depends(
        get_current_active_user
    ),

):

    service = get_show_log_service()

    logs = await service.get_user_show_logs(
        current_user["_id"],
        skip,
        limit,
        status,
    )

    return [
        ShowLogResponse(
            **log.model_dump()
        )
        for log in logs
    ]


@router.get(
    "/my/history",
    response_model=List[ShowLogResponse],
)
async def get_my_concert_history(

    skip: int = 0,

    limit: int = 50,

    current_user: dict = Depends(
        get_current_active_user
    ),

):

    service = get_show_log_service()

    logs = await service.get_user_concert_history(
        current_user["_id"],
        skip,
        limit,
    )

    return [
        ShowLogResponse(
            **log.model_dump()
        )
        for log in logs
    ]


@router.get(
    "/{event_id}",
    response_model=ShowLogResponse,
)
async def get_show_log(

    event_id: str,

    current_user: dict = Depends(
        get_current_active_user
    ),

):

    service = get_show_log_service()

    log = await service.get_show_log(
        current_user["_id"],
        event_id,
    )

    if not log:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Show log not found",
        )

    return ShowLogResponse(
        **log.model_dump()
    )


@router.post(
    "",
    response_model=ShowLogResponse,
)
async def create_show_log(

    show_log_data: ShowLogCreate,

    current_user: dict = Depends(
        get_current_active_user
    ),

):

    service = get_show_log_service()

    log = await service.create_show_log(
        current_user["_id"],
        show_log_data,
    )

    return ShowLogResponse(
        **log.model_dump()
    )


@router.put(
    "/{event_id}",
    response_model=ShowLogResponse,
)
async def update_show_log(

    event_id: str,

    show_log_data: ShowLogUpdate,

    current_user: dict = Depends(
        get_current_active_user
    ),

):

    service = get_show_log_service()

    log = await service.update_show_log(
        current_user["_id"],
        event_id,
        show_log_data,
    )

    if not log:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Show log not found",
        )

    return ShowLogResponse(
        **log.model_dump()
    )

@router.delete(
    "/{event_id}",
)
async def delete_show_log(

    event_id: str,

    current_user: dict = Depends(
        get_current_active_user
    ),

):

    service = get_show_log_service()

    deleted = await service.delete_show_log(
        current_user["_id"],
        event_id,
    )

    if not deleted:

        raise HTTPException(
            status_code=404,
            detail="Show log not found",
        )

    return {
        "message": "Show log deleted",
    }


@router.get(
    "/{event_id}/review",
    response_model=ShowLogResponse,
)
async def get_review(

    event_id: str,

    current_user: dict = Depends(
        get_current_active_user
    ),

):

    service = get_show_log_service()

    log = await service.get_show_log(
        current_user["_id"],
        event_id,
    )

    if not log:

        raise HTTPException(
            status_code=404,
            detail="Show log not found",
        )

    return ShowLogResponse(
        **log.model_dump()
    )


@router.put(
    "/{event_id}/review",
    response_model=ShowLogResponse,
)
async def update_review(

    event_id: str,

    current_user: dict = Depends(
        get_current_active_user
    ),

):

    service = get_show_log_service()

    log = await service.update_review(
        user_id=current_user["_id"],
        event_id=event_id,
        rating=review_data.rating,
        review=review_data.review,
    )

    return ShowLogResponse(
        **log.model_dump()
    )


@router.delete(
    "/{event_id}/review",
    response_model=ShowLogResponse,
)
async def delete_review(

    event_id: str,

    current_user: dict = Depends(
        get_current_active_user
    ),

):

    service = get_show_log_service()

    log = await service.delete_review(
        user_id=current_user["_id"],
        event_id=event_id,
    )

    return ShowLogResponse(
        **log.model_dump()
    )
    
@router.delete(
    "/{event_id}/review",
    response_model=ShowLogResponse
)
async def delete_review(

    event_id: str,

    current_user: dict = Depends(
        get_current_active_user
    ),

):

    service = get_show_log_service()


    show_log = await service.delete_review(
        current_user["_id"],
        event_id,
    )


    return ShowLogResponse(
        **show_log.model_dump()
    )