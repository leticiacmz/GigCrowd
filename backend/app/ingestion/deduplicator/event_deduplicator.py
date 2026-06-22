from typing import List, Dict, Any
from datetime import datetime


class EventDeduplicator:
    """Deduplicate events from multiple sources"""
    
    @staticmethod
    def deduplicate_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate events based on title, artist, venue, and date"""
        seen = set()
        unique_events = []
        
        for event in events:
            # Create a unique key based on event properties
            key = (
                event.get("title", ""),
                event.get("artist_name", ""),
                event.get("venue_name", ""),
                event.get("date", "")
            )
            
            if key not in seen:
                seen.add(key)
                unique_events.append(event)
        
        return unique_events
    
    @staticmethod
    def merge_duplicate_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Merge duplicate events, keeping the most complete data"""
        event_map = {}
        
        for event in events:
            key = (
                event.get("title", ""),
                event.get("artist_name", ""),
                event.get("venue_name", ""),
                event.get("date", "")
            )
            
            if key not in event_map:
                event_map[key] = event
            else:
                # Merge with existing event, preferring non-null values
                existing = event_map[key]
                for field, value in event.items():
                    if value is not None and existing.get(field) is None:
                        existing[field] = value
        
        return list(event_map.values())
