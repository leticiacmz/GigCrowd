from app.database.connection import get_database


async def create_indexes():
    """Create MongoDB indexes for better query performance"""
    db = await get_database()
    
    # Users indexes
    await db.users.create_index("email", unique=True)
    await db.users.create_index("username", unique=True)
    await db.users.create_index("created_at")
    
    # Events indexes
    await db.events.create_index([("artist_id", 1), ("date", 1)])
    await db.events.create_index("venue_id")
    await db.events.create_index("date")
    await db.events.create_index("location")
    
    # Artists indexes
    await db.artists.create_index("name", unique=True)
    await db.artists.create_index("spotify_id")
    
    # Follows indexes
    await db.follows.create_index([("follower_id", 1), ("following_id", 1)], unique=True)
    await db.follows.create_index("follower_id")
    await db.follows.create_index("following_id")
    
    # Show logs indexes
    await db.show_logs.create_index([("user_id", 1), ("event_id", 1)], unique=True)
    await db.show_logs.create_index("user_id")
    await db.show_logs.create_index("event_id")
    await db.show_logs.create_index("status")
    await db.show_logs.create_index("date")
    
    # Posts indexes
    await db.posts.create_index("user_id")
    await db.posts.create_index("event_id")
    await db.posts.create_index("created_at")
    
    # Comments indexes
    await db.comments.create_index("post_id")
    await db.comments.create_index("user_id")
    
    # Likes indexes
    await db.likes.create_index([("user_id", 1), ("target_id", 1), ("target_type", 1)], unique=True)
    await db.likes.create_index("target_id")
    
    # Activities indexes
    await db.activities.create_index("user_id")
    await db.activities.create_index("created_at")
    await db.activities.create_index([("user_id", 1), ("created_at", -1)])
    
    print("Database indexes created successfully")
