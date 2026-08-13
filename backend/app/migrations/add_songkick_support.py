"""
Migration script to add Songkick support to existing schema.
Run this before deploying Phase 1.
"""
async def migrate_to_songkick_support(db):
    """
    Add new fields and indexes for Songkick support.
    """
    # Add indexes
    await db.events.create_index("artist_slugs")
    await db.events.create_index("external_ids.songkick", sparse=True)
    await db.artists.create_index("external_ids.songkick", sparse=True)
    await db.venues.create_index("external_ids.songkick", sparse=True)
    
    # Migrate existing events to have artist_slugs
    await db.events.update_many(
        {"artist_slugs": {"$exists": False}},
        {
            "$set": {
                "artist_slugs": ["$artist_slug"],
                "event_type": "Concert"
            }
        }
    )
    
    print("Migration to Songkick support completed")
