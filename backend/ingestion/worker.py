import asyncio
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from app.database.connection import get_database
from app.services.artist_service import ArtistService
from app.services.event_service import EventService
from ingestion.sources.setlistfm_source import SetlistFmSource
from ingestion.sources.songkick_source import SongkickSource
from ingestion.normalizers.event_normalizer import EventNormalizer
from ingestion.deduplicator.event_deduplicator import EventDeduplicator
from app.config import settings


class IngestionWorker:
    """Worker for ingesting event data from various sources"""
    
    def __init__(self):
        self.sources = []
        self._initialize_sources()
    
    def _initialize_sources(self):
        """Initialize available data sources"""
        if settings.SETLISTFM_API_KEY:
            self.sources.append(SetlistFmSource(api_key=settings.SETLISTFM_API_KEY))
        
        # Add Songkick if API key is available
        # if settings.SONGKICK_API_KEY:
        #     self.sources.append(SongkickSource(api_key=settings.SONGKICK_API_KEY))
    
    async def ingest_events_for_artist(self, artist_name: str, days_ahead: int = 90) -> Dict:
        """
        Ingest events for a specific artist from all available sources
        
        Args:
            artist_name: Name of the artist
            days_ahead: Number of days ahead to fetch events for
        
        Returns:
            Summary of ingestion results
        """
        date_from = datetime.utcnow()
        date_to = date_from + timedelta(days=days_ahead)
        
        all_raw_events = []
        source_results = {}
        
        # Fetch events from all sources
        for source in self.sources:
            try:
                raw_events = await source.fetch_events(artist_name, date_from, date_to)
                all_raw_events.extend(raw_events)
                source_results[source.get_source_name()] = len(raw_events)
            except Exception as e:
                print(f"Error fetching from {source.get_source_name()}: {e}")
                source_results[source.get_source_name()] = 0
        
        if not all_raw_events:
            return {
                "artist": artist_name,
                "total_events": 0,
                "events_added": 0,
                "events_updated": 0,
                "source_results": source_results
            }
        
        # Normalize events
        normalized_events = []
        for event in all_raw_events:
            source = event.get("source", "unknown")
            normalized = EventNormalizer.normalize(event, source)
            normalized_events.append(normalized)
        
        # Deduplicate events
        deduplicated_events = EventDeduplicator.deduplicate(normalized_events)
        
        # Get or create artist
        artist = await ArtistService.get_artist_by_name(artist_name)
        if not artist:
            from app.models.artist import ArtistCreate
            artist_data = ArtistCreate(name=artist_name)
            artist = await ArtistService.create_artist(artist_data)
        
        # Save events to database
        events_added = 0
        events_updated = 0
        
        db = await get_database()
        
        for event in deduplicated_events:
            # Check if event already exists
            existing = await db.events.find_one({
                "external_id": event.get("external_id"),
                "source": event.get("source")
            })
            
            event_dict = {
                "title": event.get("title"),
                "artist_id": artist.id,
                "venue_name": event.get("venue_name"),
                "date": event.get("date"),
                "location": event.get("location"),
                "latitude": event.get("latitude"),
                "longitude": event.get("longitude"),
                "description": event.get("description"),
                "image_url": event.get("image_url"),
                "ticket_url": event.get("ticket_url"),
                "price_min": event.get("price_min"),
                "price_max": event.get("price_max"),
                "source": event.get("source"),
                "external_id": event.get("external_id")
            }
            
            if existing:
                # Update existing event
                await db.events.update_one(
                    {"_id": existing["_id"]},
                    {"$set": event_dict}
                )
                events_updated += 1
            else:
                # Create new event
                event_dict["created_at"] = datetime.utcnow()
                event_dict["updated_at"] = datetime.utcnow()
                await db.events.insert_one(event_dict)
                events_added += 1
        
        return {
            "artist": artist_name,
            "artist_id": artist.id,
            "total_events": len(all_raw_events),
            "deduplicated_events": len(deduplicated_events),
            "events_added": events_added,
            "events_updated": events_updated,
            "source_results": source_results
        }
    
    async def batch_ingest_artists(self, artist_names: List[str], days_ahead: int = 90) -> List[Dict]:
        """Batch ingest events for multiple artists"""
        results = []
        
        for artist_name in artist_names:
            result = await self.ingest_events_for_artist(artist_name, days_ahead)
            results.append(result)
            
            # Small delay between artists to avoid rate limiting
            await asyncio.sleep(1)
        
        return results
    
    async def run_scheduled_ingestion(self, interval_hours: int = 24):
        """Run ingestion on a schedule (for background worker)"""
        while True:
            print(f"Starting scheduled ingestion at {datetime.utcnow()}")
            
            # Get list of artists to ingest (could be from database or config)
            # For now, we'll use a hardcoded list
            popular_artists = [
                "Taylor Swift",
                "The Beatles",
                "Radiohead",
                "Coldplay",
                "Beyoncé"
            ]
            
            results = await self.batch_ingest_artists(popular_artists)
            
            total_added = sum(r["events_added"] for r in results)
            total_updated = sum(r["events_updated"] for r in results)
            
            print(f"Ingestion complete. Added: {total_added}, Updated: {total_updated}")
            
            # Wait for next interval
            await asyncio.sleep(interval_hours * 3600)


async def main():
    """Main entry point for running ingestion"""
    worker = IngestionWorker()
    
    # Example: Ingest events for a specific artist
    result = await worker.ingest_events_for_artist("Radiohead")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
