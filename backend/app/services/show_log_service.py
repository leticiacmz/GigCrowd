from app.database.connection import get_database
from app.models.show_log import ShowLogCreate, ShowLogInDB, ShowLogUpdate, AttendanceStatus
from app.services.event_service import EventService
from datetime import datetime, UTC
from typing import Optional, List


class ShowLogService:
    @staticmethod
    async def create_show_log(user_id: str, show_log_data: ShowLogCreate) -> ShowLogInDB:
        """Create or update a show log"""
        db = await get_database()
        
        # Check if event exists
        event = await EventService.get_event_by_id(show_log_data.event_id)
        if not event:
            raise ValueError("Event not found")
        
        # Check if show log already exists
        existing_log = await db.show_logs.find_one({
            "user_id": user_id,
            "event_id": show_log_data.event_id
        })
        
        if existing_log:
            # Update existing log
            old_status = existing_log["status"]
            update_dict = show_log_data.model_dump(exclude_unset=True)
            update_dict["updated_at"] = datetime.now(UTC)
            
            await db.show_logs.update_one(
                {"_id": existing_log["_id"]},
                {"$set": update_dict}
            )
            
            # Update event counts
            await EventService.update_attendance_counts(show_log_data.event_id, old_status, increment=False)
            await EventService.update_attendance_counts(show_log_data.event_id, show_log_data.status, increment=True)
            
            updated_log = await db.show_logs.find_one({"_id": existing_log["_id"]})
            return ShowLogInDB(**updated_log)
        
        # Create new show log
        show_log_dict = show_log_data.model_dump()
        show_log_dict["user_id"] = user_id
        show_log_dict["date"] = event.date
        show_log_dict["created_at"] = datetime.now(UTC)
        show_log_dict["updated_at"] = datetime.now(UTC)
        
        result = await db.show_logs.insert_one(show_log_dict)
        show_log_dict["_id"] = str(result.inserted_id)
        
        # Update event counts
        await EventService.increment_attendees_count(show_log_data.event_id)
        await EventService.update_attendance_counts(show_log_data.event_id, show_log_data.status, increment=True)
        
        return ShowLogInDB(**show_log_dict)
    
    @staticmethod
    async def get_show_log(user_id: str, event_id: str) -> Optional[ShowLogInDB]:
        """Get a show log for a user and event"""
        db = await get_database()
        show_log = await db.show_logs.find_one({
            "user_id": user_id,
            "event_id": event_id
        })
        if show_log:
            return ShowLogInDB(**show_log)
        return None
    
    @staticmethod
    async def get_user_show_logs(
        user_id: str,
        skip: int = 0,
        limit: int = 50,
        status: Optional[AttendanceStatus] = None
    ) -> List[ShowLogInDB]:
        """Get all show logs for a user"""
        db = await get_database()
        
        query = {"user_id": user_id}
        if status:
            query["status"] = status
        
        cursor = db.show_logs.find(query).sort("date", -1).skip(skip).limit(limit)
        show_logs = await cursor.to_list(length=limit)
        
        return [ShowLogInDB(**log) for log in show_logs]
    
    @staticmethod
    async def get_event_show_logs(event_id: str, skip: int = 0, limit: int = 50) -> List[ShowLogInDB]:
        """Get all show logs for an event"""
        db = await get_database()
        cursor = db.show_logs.find({"event_id": event_id}).sort("created_at", -1).skip(skip).limit(limit)
        show_logs = await cursor.to_list(length=limit)
        
        return [ShowLogInDB(**log) for log in show_logs]
    
    @staticmethod
    async def get_user_concert_history(user_id: str, skip: int = 0, limit: int = 50) -> List[ShowLogInDB]:
        """Get user's concert history (went events)"""
        return await ShowLogService.get_user_show_logs(
            user_id=user_id,
            skip=skip,
            limit=limit,
            status=AttendanceStatus.WENT
        )
