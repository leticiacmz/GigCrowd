#!/usr/bin/env python3
"""
Development seed script to create two test users with social data.
This script is for LOCAL DEVELOPMENT ONLY - should never run in production.
"""

import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.connection import db as database, get_database
from app.services.user_service import UserService
from app.models.user import UserCreate
from app.auth.security import get_password_hash
from bson import ObjectId
from datetime import datetime, UTC

# Development user credentials
DEV_USERS = [
    {
        "email": "alice@gigcrowd.dev",
        "username": "crowd_alice",
        "password": "devpass123",
        "full_name": "Alice Crowd"
    },
    {
        "email": "bob@gigcrowd.dev",
        "username": "crowd_bob",
        "password": "devpass123",
        "full_name": "Bob Crowd"
    }
]

# Some artist slugs to follow (assuming they exist in DB)
ARTIST_SLUGS_TO_FOLLOW = [
    "metallica",
    "taylor-swift",
    "the-beatles",
    "pink-floyd",
    "radiohead"
]

async def seed_dev_users():
    """Create two development users with social connections."""
    print("Seeding development users...")
    
    # Initialize database
    await database.connect()
    db = get_database()
    
    users_created = []
    
    for user_data in DEV_USERS:
        # Check if user already exists
        existing = await db.users.find_one({"email": user_data["email"]})
        if existing:
            print(f"  User {user_data['username']} already exists, skipping creation")
            users_created.append(existing)
            continue
        
        # Create user
        hashed_password = get_password_hash(user_data["password"])
        user_dict = {
            "email": user_data["email"],
            "username": user_data["username"],
            "full_name": user_data["full_name"],
            "hashed_password": hashed_password,
            "role": "user",
            "is_active": True,
            "followers_count": 0,
            "following_count": 0,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
        
        result = await db.users.insert_one(user_dict)
        user_dict["_id"] = str(result.inserted_id)
        users_created.append(user_dict)
        print(f"  Created user: {user_data['username']} ({user_data['email']})")
    
    alice = users_created[0]
    bob = users_created[1]
    
    # Make them follow each other
    print("  Creating follow relationships...")
    
    # Alice follows Bob
    await db.follows.update_one(
        {"follower_id": alice["_id"], "following_id": bob["_id"]},
        {"$set": {
            "follower_id": alice["_id"],
            "following_id": bob["_id"],
            "created_at": datetime.now(UTC)
        }},
        upsert=True
    )
    await db.users.update_one({"_id": ObjectId(alice["_id"])}, {"$inc": {"following_count": 1}})
    await db.users.update_one({"_id": ObjectId(bob["_id"])}, {"$inc": {"followers_count": 1}})
    
    # Bob follows Alice
    await db.follows.update_one(
        {"follower_id": bob["_id"], "following_id": alice["_id"]},
        {"$set": {
            "follower_id": bob["_id"],
            "following_id": alice["_id"],
            "created_at": datetime.now(UTC)
        }},
        upsert=True
    )
    await db.users.update_one({"_id": ObjectId(bob["_id"])}, {"$inc": {"following_count": 1}})
    await db.users.update_one({"_id": ObjectId(alice["_id"])}, {"$inc": {"followers_count": 1}})
    
    print("  Users now follow each other")
    
    # Follow some artists
    print("  Creating artist follows...")
    for artist_slug in ARTIST_SLUGS_TO_FOLLOW:
        # Check if artist exists
        artist = await db.artists.find_one({"slug": artist_slug})
        if artist:
            for user in [alice, bob]:
                await db.artist_follows.update_one(
                    {"user_id": user["_id"], "artist_slug": artist_slug},
                    {"$set": {
                        "user_id": user["_id"],
                        "artist_slug": artist_slug,
                        "created_at": datetime.now(UTC)
                    }},
                    upsert=True
                )
    print("  Artist follows created")
    
    # Create community posts
    print("  Creating community posts...")
    for artist_slug in ARTIST_SLUGS_TO_FOLLOW[:3]:  # First 3 artists
        artist = await db.artists.find_one({"slug": artist_slug})
        if artist:
            # Alice posts
            await db.posts.insert_one({
                "artist_slug": artist_slug,
                "user_id": alice["_id"],
                "content": f"Just saw {artist.get('name', artist_slug)} live! What an incredible show!",
                "likes_count": 0,
                "comments_count": 0,
                "created_at": datetime.now(UTC),
                "username": alice["username"],
                "user_avatar_url": alice.get("avatar_url"),
                "liked_by_user": False
            })
            
            # Bob posts
            await db.posts.insert_one({
                "artist_slug": artist_slug,
                "user_id": bob["_id"],
                "content": f"{artist.get('name', artist_slug)} is my favorite band. Can't wait for the next tour!",
                "likes_count": 0,
                "comments_count": 0,
                "created_at": datetime.now(UTC),
                "username": bob["username"],
                "user_avatar_url": bob.get("avatar_url"),
                "liked_by_user": False
            })
    
    print("  Community posts created")
    
    # Create likes (cross-like each other's posts)
    print("  Creating likes...")
    posts = await db.posts.find({"user_id": {"$in": [alice["_id"], bob["_id"]]}}).to_list(10)
    for i, post in enumerate(posts):
        # Alternate likes
        if i % 2 == 0:
            liker_id = alice["_id"] if post["user_id"] == bob["_id"] else bob["_id"]
            await db.post_likes.update_one(
                {"post_id": post["_id"], "user_id": liker_id},
                {"$set": {"post_id": post["_id"], "user_id": liker_id, "created_at": datetime.now(UTC)}},
                upsert=True
            )
            await db.posts.update_one({"_id": post["_id"]}, {"$inc": {"likes_count": 1}})
    
    print("  Likes created")
    
    # Create comments
    print("  Creating comments...")
    for post in posts[:2]:
        commenter_id = bob["_id"] if post["user_id"] == alice["_id"] else alice["_id"]
        commenter_name = bob["username"] if post["user_id"] == alice["_id"] else alice["username"]
        await db.comments.insert_one({
            "post_id": post["_id"],
            "user_id": commenter_id,
            "content": "Totally agree! Best concert ever!",
            "parent_comment_id": None,
            "replies": [],
            "replies_count": 0,
            "created_at": datetime.now(UTC),
            "username": commenter_name,
            "user_avatar_url": None
        })
        await db.posts.update_one({"_id": post["_id"]}, {"$inc": {"comments_count": 1}})
    
    print("  Comments created")
    
    # Create some event attendance
    print("  Creating event attendance...")
    events = await db.events.find().limit(3).to_list(3)
    for event in events:
        for user in [alice, bob]:
            await db.show_logs.update_one(
                {"user_id": user["_id"], "event_id": str(event["_id"])},
                {"$set": {
                    "user_id": user["_id"],
                    "event_id": str(event["_id"]),
                    "status": "went",
                    "rating": 5 if user["username"] == "crowd_alice" else 4,
                    "review": f"Amazing show! {event.get('title', 'The event')} was incredible!",
                    "created_at": datetime.now(UTC),
                    "updated_at": datetime.now(UTC)
                }},
                upsert=True
            )
    
    print("  Event attendance and reviews created")
    
    # Create notifications
    print("  Creating notifications...")
    for user in [alice, bob]:
        other = bob if user["username"] == "crowd_alice" else alice
        await db.notifications.insert_many([
            {
                "user_id": user["_id"],
                "type": "new_follower",
                "actor_id": other["_id"],
                "actor_username": other["username"],
                "read": False,
                "created_at": datetime.now(UTC)
            },
            {
                "user_id": user["_id"],
                "type": "new_like",
                "actor_id": other["_id"],
                "actor_username": other["username"],
                "read": False,
                "created_at": datetime.now(UTC)
            },
            {
                "user_id": user["_id"],
                "type": "new_comment",
                "actor_id": other["_id"],
                "actor_username": other["username"],
                "read": False,
                "created_at": datetime.now(UTC)
            }
        ])
    
    print("  Notifications created")
    
    print("\nDevelopment users seeded successfully!")
    print("\nDevelopment Login Credentials:")
    print("=" * 50)
    print("User A (Alice):")
    print("  Email:    alice@gigcrowd.dev")
    print("  Username: crowd_alice")
    print("  Password: devpass123")
    print("")
    print("User B (Bob):")
    print("  Email:    bob@gigcrowd.dev")
    print("  Username: crowd_bob")
    print("  Password: devpass123")
    print("=" * 50)
    print("\nIMPORTANT: These are DEVELOPMENT ONLY credentials.")
    print("   Never use these in production!")
    
    return True

if __name__ == "__main__":
    try:
        asyncio.run(seed_dev_users())
    except Exception as e:
        print(f"Error seeding users: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)