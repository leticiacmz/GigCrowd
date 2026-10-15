from fastapi import HTTPException

from app.repositories.show_log_repository import ShowLogRepository


class AttendanceService:


    def __init__(
        self,
        show_log_repository: ShowLogRepository,
    ):

        self.show_log_repository = show_log_repository


    async def get_event_attendance(
        self,
        event_id: str,
        user_id: str | None = None,
    ):

        summary = await self.show_log_repository.get_attendance_summary(
            event_id
        )

        user_status = None

        if user_id:

            user_status = await self.show_log_repository.get_user_status(
                user_id,
                event_id,
            )

        return {
            "going": summary.get(
                "going",
                0,
            ),

            "maybe": summary.get(
                "maybe",
                0,
            ),

            "went": summary.get(
                "went",
                0,
            ),

            "user_status": user_status,
        }


    async def update_review(
        self,
        event_id: str,
        user_id: str,
        rating: int | None,
        review: str | None,
    ):

        show_log = await self.show_log_repository.get_by_user_and_event(
            user_id,
            event_id,
        )

        if not show_log:

            raise HTTPException(
                status_code=404,
                detail="Attendance not found.",
            )

        if show_log["status"] != "went":

            raise HTTPException(
                status_code=400,
                detail="Only users who attended the event can leave a review.",
            )

        # The same rule every other door into a review holds to: a rating or
        # some words, never neither - this endpoint takes no photo, so an
        # empty submission here is exactly an empty review.
        if rating is None and not (review or "").strip():

            raise HTTPException(
                status_code=400,
                detail=(
                    "A review needs a rating or some words - "
                    "a photo on its own is not one."
                ),
            )

        if rating is not None and (rating < 1 or rating > 5):

            raise HTTPException(
                status_code=400,
                detail="Rating must be between 1 and 5.",
            )

        return await self.show_log_repository.update_review(
            user_id=user_id,
            event_id=event_id,
            rating=rating,
            review=review,
        )