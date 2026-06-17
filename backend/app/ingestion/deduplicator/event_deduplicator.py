from typing import Dict, Any, Optional
from datetime import datetime


class EventDeduplicator:
    """Deduplicates events based on external IDs and other attributes"""
    
    def __init__(self, db):
        self.db = db
    
    async def find_duplicate(self, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Check if an event already exists in the database.
        
        Args:
            event: Event data to check for duplicates
            
        Returns:
            Existing event if found, None otherwise
        """
        # Check by external_id first
        if event.get("external_id"):
            existing = await self.db.events.find_one({
                "external_id": event["external_id"]
            })
            if existing:
                return existing
        
        # Check by combination of artist, venue, and date
        existing = await self.db.events.find_one({
            "artist_id": event.get("artist_id"),
            "venue_name": event.get("venue_name"),
            "date": event.get("date")
        })
        
        if existing:
            return existing
        
        return None
    
    async def deduplicate_events(self, events: list) -> list:
        """
        Remove duplicate events from a list.
        
        Args:
            events: List of events to deduplicate
            
        Returns:
            Deduplicated list of events
        """
        seen = set()
        deduplicated = []
        
        for event in events:
            # Create a unique key based on artist, venue, and date
            key = (
                event.get("artist_id", ""),
                event.get("venue_name", ""),
                event.get("date", "")
            )
            
            if key not in seen:
                seen.add(key)
                deduplicated.append(event)
        
        return deduplicated
