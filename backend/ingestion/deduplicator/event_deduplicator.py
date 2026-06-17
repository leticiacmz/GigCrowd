from typing import List, Dict, Set
from datetime import datetime, timedelta


class EventDeduplicator:
    """Deduplicates events based on various criteria"""
    
    @staticmethod
    def deduplicate(events: List[Dict]) -> List[Dict]:
        """
        Deduplicate a list of events
        
        Deduplication criteria:
        - Same artist + same venue + same date (within tolerance)
        - Same external_id from same source
        - High similarity in title + venue + date
        """
        if not events:
            return []
        
        # Group events by deduplication key
        groups = {}
        seen_external_ids: Set[tuple] = set()
        
        for event in events:
            # Check by external_id
            external_id = event.get("external_id")
            source = event.get("source")
            
            if external_id and source:
                key = (source, external_id)
                if key in seen_external_ids:
                    continue  # Skip duplicate
                seen_external_ids.add(key)
            
            # Create deduplication key
            dedup_key = EventDeduplicator._create_dedup_key(event)
            
            if dedup_key not in groups:
                groups[dedup_key] = []
            
            groups[dedup_key].append(event)
        
        # Select best event from each group
        deduplicated = []
        for key, group_events in groups.items():
            best_event = EventDeduplicator._select_best_event(group_events)
            deduplicated.append(best_event)
        
        return deduplicated
    
    @staticmethod
    def _create_dedup_key(event: Dict) -> str:
        """Create a deduplication key for an event"""
        artist_name = event.get("artist_name", "").lower().strip()
        venue_name = event.get("venue_name", "").lower().strip()
        date = event.get("date")
        
        if isinstance(date, datetime):
            date_str = date.strftime("%Y-%m-%d")
        else:
            date_str = str(date)
        
        return f"{artist_name}|{venue_name}|{date_str}"
    
    @staticmethod
    def _select_best_event(events: List[Dict]) -> Dict:
        """Select the best event from a group of duplicates"""
        if len(events) == 1:
            return events[0]
        
        # Priority: most complete data, most recent source, preferred source
        source_priority = {
            "setlistfm": 3,
            "songkick": 2,
            "bandsintown": 1
        }
        
        def score_event(event: Dict):
            score = 0
            
            # Count non-empty fields
            fields = ["title", "venue_name", "location", "description", "image_url", "ticket_url"]
            for field in fields:
                if event.get(field):
                    score += 1
            
            # Source priority
            source = event.get("source", "")
            score += source_priority.get(source, 0)
            
            return score
        
        return max(events, key=score_event)
    
    @staticmethod
    def find_similar_events(event: Dict, existing_events: List[Dict], threshold: float = 0.7) -> List[Dict]:
        """
        Find events similar to the given event in existing events
        Uses simple similarity scoring
        """
        similar = []
        
        for existing in existing_events:
            similarity = EventDeduplicator._calculate_similarity(event, existing)
            if similarity >= threshold:
                similar.append((existing, similarity))
        
        # Sort by similarity
        similar.sort(key=lambda x: x[1], reverse=True)
        
        return [item[0] for item in similar]
    
    @staticmethod
    def _calculate_similarity(event1: Dict, event2: Dict) -> float:
        """Calculate similarity score between two events (0-1)"""
        score = 0.0
        factors = 0
        
        # Artist name similarity
        artist1 = event1.get("artist_name", "").lower()
        artist2 = event2.get("artist_name", "").lower()
        if artist1 and artist2:
            factors += 1
            if artist1 == artist2:
                score += 1.0
            elif artist1 in artist2 or artist2 in artist1:
                score += 0.7
        
        # Venue name similarity
        venue1 = event1.get("venue_name", "").lower()
        venue2 = event2.get("venue_name", "").lower()
        if venue1 and venue2:
            factors += 1
            if venue1 == venue2:
                score += 1.0
            elif venue1 in venue2 or venue2 in venue1:
                score += 0.6
        
        # Date similarity
        date1 = event1.get("date")
        date2 = event2.get("date")
        if date1 and date2 and isinstance(date1, datetime) and isinstance(date2, datetime):
            factors += 1
            diff = abs((date1 - date2).days)
            if diff == 0:
                score += 1.0
            elif diff <= 1:
                score += 0.8
            elif diff <= 7:
                score += 0.5
        
        # Location similarity
        loc1 = event1.get("location", "").lower()
        loc2 = event2.get("location", "").lower()
        if loc1 and loc2:
            factors += 1
            if loc1 == loc2:
                score += 1.0
            elif loc1 in loc2 or loc2 in loc1:
                score += 0.6
        
        return score / factors if factors > 0 else 0.0
