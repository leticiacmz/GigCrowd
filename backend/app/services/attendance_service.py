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
                0
            ),

            "maybe": summary.get(
                "maybe",
                0
            ),

            "user_status": user_status,
        }