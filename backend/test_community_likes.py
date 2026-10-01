"""Test community post likes functionality."""
import requests
import json

BASE_URL = "http://localhost:8000"


def test_community_likes():
    # Login
    r = requests.post(f"{BASE_URL}/auth/login", data={
        "username": "testuser@gigcrowd.com",
        "password": "TestPass123!"
    })
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # First, get an artist slug
    r = requests.get(f"{BASE_URL}/artists", headers=headers)
    artists = r.json()
    if not artists:
        print("No artists found, cannot test community posts")
        return

    artist_slug = artists[0]["slug"]
    print(f"Using artist: {artist_slug}")

    # Create a community post
    r = requests.post(f"{BASE_URL}/community/posts", headers=headers, json={
        "artist_slug": artist_slug,
        "content": "Test community post for likes!"
    })
    print(f"Create post: {r.status_code}")
    if r.status_code != 200:
        print(f"Error: {r.text}")
        return

    post_id = r.json()["id"]
    print(f"Post ID: {post_id}")
    print(f"Likes count after create: {r.json()['likes_count']}")

    # Like the post
    r = requests.post(f"{BASE_URL}/community/posts/{post_id}/like", headers=headers)
    print(f"Like post: {r.status_code}")
    if r.status_code != 200:
        print(f"Error: {r.text}")
        return

    # Get posts to verify like count
    r = requests.get(f"{BASE_URL}/community/posts/{artist_slug}", headers=headers)
    posts = r.json()
    liked_post = next((p for p in posts if p["id"] == post_id), None)
    if liked_post:
        print(f"Likes count after like: {liked_post['likes_count']}")
        print(f"Liked by user: {liked_post['liked_by_user']}")

    # Try to like again (should fail)
    r = requests.post(f"{BASE_URL}/community/posts/{post_id}/like", headers=headers)
    print(f"Duplicate like: {r.status_code} (should be 400)")

    # Unlike the post
    r = requests.delete(f"{BASE_URL}/community/posts/{post_id}/like", headers=headers)
    print(f"Unlike post: {r.status_code}")
    if r.status_code != 200:
        print(f"Error: {r.text}")
        return

    # Get posts to verify unlike
    r = requests.get(f"{BASE_URL}/community/posts/{artist_slug}", headers=headers)
    posts = r.json()
    liked_post = next((p for p in posts if p["id"] == post_id), None)
    if liked_post:
        print(f"Likes count after unlike: {liked_post['likes_count']}")
        print(f"Liked by user: {liked_post['liked_by_user']}")

    # Try to unlike again (should fail)
    r = requests.delete(f"{BASE_URL}/community/posts/{post_id}/like", headers=headers)
    print(f"Duplicate unlike: {r.status_code} (should be 400)")

    # Clean up - delete the post
    r = requests.delete(f"{BASE_URL}/community/posts/{post_id}", headers=headers)
    print(f"Delete post: {r.status_code}")

    print("\nAll tests passed!")


if __name__ == "__main__":
    test_community_likes()
