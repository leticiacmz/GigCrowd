from fastapi import APIRouter, Depends, HTTPException, status
from typing import List

from app.models.show_log import (
    ShowLogResponse,
    ShowLogCreate,
    ShowLogUpdate,
    AttendanceStatus,
)

from app.services.show_log_service import ShowLogService

from app.repositories.show_log_repository import ShowLogRepository
from app.repositories.event_repository import EventRepository

from app.database.connection import get_database

from app.auth.dependencies import get_current_active_user



router = APIRouter(
    prefix="/show-logs",
    tags=["show-logs"],
)





def get_show_log_service() -> ShowLogService:

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
    response_model=List[ShowLogResponse]
)
async def get_my_show_logs(

    skip: int = 0,

    limit: int = 50,

    status: AttendanceStatus | None = None,

    current_user: dict = Depends(
        get_current_active_user
    ),

):


    show_log_service = get_show_log_service()


    show_logs = await show_log_service.get_user_show_logs(
        current_user["_id"],
        skip,
        limit,
        status,
    )


    return [

        ShowLogResponse(
            **log.model_dump()
        )

        for log in show_logs

    ]









@router.get(
    "/my/history",
    response_model=List[ShowLogResponse]
)
async def get_my_concert_history(

    skip: int = 0,

    limit: int = 50,

    current_user: dict = Depends(
        get_current_active_user
    ),

):


    show_log_service = get_show_log_service()


    show_logs = await show_log_service.get_user_concert_history(
        current_user["_id"],
        skip,
        limit,
    )


    return [

        ShowLogResponse(
            **log.model_dump()
        )

        for log in show_logs

    ]









@router.get(
    "/{event_id}",
    response_model=ShowLogResponse
)
async def get_show_log(

    event_id: str,

    current_user: dict = Depends(
        get_current_active_user
    ),

):


    show_log_service = get_show_log_service()


    show_log = await show_log_service.get_show_log(
        current_user["_id"],
        event_id,
    )


    if not show_log:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Show log not found",
        )


    return ShowLogResponse(
        **show_log.model_dump()
    )









@router.post(
    "",
    response_model=ShowLogResponse
)
async def create_show_log(

    show_log_data: ShowLogCreate,

    current_user: dict = Depends(
        get_current_active_user
    ),

):


    show_log_service = get_show_log_service()


    show_log = await show_log_service.create_show_log(
        current_user["_id"],
        show_log_data,
    )


    return ShowLogResponse(
        **show_log.model_dump()
    )









@router.put(
    "/{event_id}",
    response_model=ShowLogResponse
)
async def update_show_log(

    event_id: str,

    show_log_data: ShowLogUpdate,

    current_user: dict = Depends(
        get_current_active_user
    ),

):


    show_log_service = get_show_log_service()


    show_log = await show_log_service.update_show_log(
        current_user["_id"],
        event_id,
        show_log_data,
    )


    if not show_log:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Show log not found",
        )


    return ShowLogResponse(
        **show_log.model_dump()
    )