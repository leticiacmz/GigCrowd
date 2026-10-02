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

from app.models.activity import (
    ActivityType,
)

from app.services.activity_service import (
    ActivityService,
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


async def _record_show_log_activity(
    current_user: dict,
    show_log_data,
    log,
) -> None:
    """Add a show log to the caller's unified timeline.

    A log that carries a review is a review; one without is attendance. Both
    are recorded against the show log document so the feed can resolve the
    event behind them.
    """
    review = (getattr(log, "review", None) or "").strip()

    if review:
        activity_type = ActivityType.CREATE_REVIEW
    else:
        activity_type = ActivityType.ATTEND_EVENT

    await ActivityService.record(
        current_user["_id"],
        activity_type,
        target_id=str(log.id),
        target_type="show_log",
        metadata={
            "rating": getattr(log, "rating", None),
            "status": getattr(log, "status", None),
            "review": review or None,
        },
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
    # Validate pagination parameters
    skip = max(0, min(skip, 10000))
    limit = max(1, min(limit, 100))

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

    try:
        log = await service.create_show_log(
            current_user["_id"],
            show_log_data,
        )

    # The service rejects impossible show logs (unknown event, or "went" on
    # an event that has not happened yet). Those are client errors, not
    # server faults, so they must not surface as a 500.
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    await _record_show_log_activity(
        current_user,
        show_log_data,
        log,
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