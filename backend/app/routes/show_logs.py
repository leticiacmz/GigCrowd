from fastapi import APIRouter, Depends, HTTPException, status
from app.models.show_log import ShowLogResponse, AttendanceStatus
from app.services.show_log_service import ShowLogService
from app.auth.dependencies import get_current_active_user
from typing import List

router = APIRouter(prefix="/show-logs", tags=["show-logs"])


@router.get("/my", response_model=List[ShowLogResponse])
async def get_my_show_logs(
    skip: int = 0,
    limit: int = 50,
    status: AttendanceStatus = None,
    current_user: dict = Depends(get_current_active_user)
):
    """Get current user's show logs"""
    show_logs = await ShowLogService.get_user_show_logs(current_user["_id"], skip, limit, status)
    return [ShowLogResponse(**log.model_dump()) for log in show_logs]


@router.get("/my/history", response_model=List[ShowLogResponse])
async def get_my_concert_history(
    skip: int = 0,
    limit: int = 50,
    current_user: dict = Depends(get_current_active_user)
):
    """Get current user's concert history (attended events)"""
    show_logs = await ShowLogService.get_user_concert_history(current_user["_id"], skip, limit)
    return [ShowLogResponse(**log.model_dump()) for log in show_logs]


@router.get("/{event_id}", response_model=ShowLogResponse)
async def get_show_log(
    event_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """Get current user's show log for a specific event"""
    show_log = await ShowLogService.get_show_log(current_user["_id"], event_id)
    if not show_log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Show log not found"
        )
    return ShowLogResponse(**show_log.model_dump())
