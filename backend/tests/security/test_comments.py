"""
Tests for community post comments and replies.
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        # Register and login first user
        c.post("/auth/register", json={
            "email": "commentuser@gigcrowd.com",
            "username": "commentuser",
            "password": "TestPass123!",
        })
        resp = c.post("/auth/login", data={
            "username": "commentuser@gigcrowd.com",
            "password": "TestPass123!",
        })
        token = resp.json()["access_token"]
        c.headers["Authorization"] = f"Bearer {token}"

        # Register and login second user
        c.post("/auth/register", json={
            "email": "otheruser@gigcrowd.com",
            "username": "otheruser",
            "password": "TestPass123!",
        })
        resp2 = c.post("/auth/login", data={
            "username": "otheruser@gigcrowd.com",
            "password": "TestPass123!",
        })
        second_token = resp2.json()["access_token"]

        # Store both tokens for use in tests
        c._first_token = token
        c._second_token = second_token

        yield c


@pytest.fixture(scope="module")
def community_post(client):
    """Create a community post for testing."""
    # Get an artist
    resp = client.get("/artists")
    artists = resp.json()
    if not artists:
        pytest.skip("No artists available")
    artist_slug = artists[0]["slug"]

    resp = client.post("/community/posts", json={
        "artist_slug": artist_slug,
        "content": "Test post for comments",
    })
    return resp.json()


def test_create_comment(client, community_post):
    """Test creating a comment on a post."""
    resp = client.post("/community/comments", json={
        "post_id": community_post["id"],
        "content": "This is a test comment",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["content"] == "This is a test comment"
    assert data["post_id"] == community_post["id"]
    assert data["username"] == "commentuser"


def test_list_comments(client, community_post):
    """Test listing comments for a post."""
    # Create a comment first
    client.post("/community/comments", json={
        "post_id": community_post["id"],
        "content": "Test comment",
    })

    resp = client.get(f"/community/posts/{community_post['id']}/comments")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["content"] == "Test comment"


def test_create_reply(client, community_post):
    """Test creating a reply to a comment."""
    # Create parent comment
    resp = client.post("/community/comments", json={
        "post_id": community_post["id"],
        "content": "Parent comment",
    })
    parent_id = resp.json()["id"]

    # Create reply
    resp = client.post("/community/comments", json={
        "post_id": community_post["id"],
        "content": "This is a reply",
        "parent_comment_id": parent_id,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["content"] == "This is a reply"
    assert data["parent_comment_id"] == parent_id


def test_invalid_parent_comment(client, community_post):
    """Test creating a reply with invalid parent comment ID."""
    resp = client.post("/community/comments", json={
        "post_id": community_post["id"],
        "content": "Reply to non-existent",
        "parent_comment_id": "nonexistent-id",
    })
    assert resp.status_code == 404


def test_edit_own_comment(client, community_post):
    """Test editing own comment."""
    # Create comment
    resp = client.post("/community/comments", json={
        "post_id": community_post["id"],
        "content": "Original content",
    })
    comment_id = resp.json()["id"]

    # Edit comment
    resp = client.put(f"/community/comments/{comment_id}", json={
        "content": "Updated content",
    })
    assert resp.status_code == 200
    assert resp.json()["content"] == "Updated content"


def test_reject_edit_others_comment(client, community_post):
    """Test that users cannot edit others' comments."""
    # Create comment as first user
    resp = client.post("/community/comments", json={
        "post_id": community_post["id"],
        "content": "My comment",
    })
    comment_id = resp.json()["id"]

    # Switch to second user
    old_token = client.headers["Authorization"]
    client.headers["Authorization"] = f"Bearer {client._second_token}"

    # Try to edit as second user
    resp = client.put(f"/community/comments/{comment_id}", json={
        "content": "Hacked!",
    })
    assert resp.status_code == 403

    # Switch back to first user
    client.headers["Authorization"] = old_token


def test_delete_own_comment(client, community_post):
    """Test deleting own comment."""
    # Create comment
    resp = client.post("/community/comments", json={
        "post_id": community_post["id"],
        "content": "To be deleted",
    })
    comment_id = resp.json()["id"]

    # Delete comment
    resp = client.delete(f"/community/comments/{comment_id}")
    assert resp.status_code == 200


def test_reject_delete_others_comment(client, community_post):
    """Test that users cannot delete others' comments."""
    # Create comment as first user
    resp = client.post("/community/comments", json={
        "post_id": community_post["id"],
        "content": "My comment",
    })
    comment_id = resp.json()["id"]

    # Switch to second user
    old_token = client.headers["Authorization"]
    client.headers["Authorization"] = f"Bearer {client._second_token}"

    # Try to delete as second user
    resp = client.delete(f"/community/comments/{comment_id}")
    assert resp.status_code == 403

    # Switch back to first user
    client.headers["Authorization"] = old_token


def test_pagination(client, community_post):
    """Test comment pagination."""
    # Create multiple comments
    for i in range(5):
        client.post("/community/comments", json={
            "post_id": community_post["id"],
            "content": f"Comment {i}",
        })

    # Test limit
    resp = client.get(f"/community/posts/{community_post['id']}/comments?limit=2")
    assert resp.status_code == 200
    assert len(resp.json()) <= 2

    # Test skip
    resp = client.get(f"/community/posts/{community_post['id']}/comments?skip=2&limit=2")
    assert resp.status_code == 200


def test_xss_sanitization(client, community_post):
    """Test that XSS attempts are sanitized in comments."""
    resp = client.post("/community/comments", json={
        "post_id": community_post["id"],
        "content": "<script>alert('xss')</script>Hello",
    })
    assert resp.status_code == 200
    # Script tags should be stripped
    assert "<script>" not in resp.json()["content"]


def test_unauthenticated_create_comment(community_post):
    """Test that unauthenticated users cannot create comments."""
    with TestClient(app) as c:
        resp = c.post("/community/comments", json={
            "post_id": community_post["id"],
            "content": "Anonymous comment",
        })
        assert resp.status_code == 401
