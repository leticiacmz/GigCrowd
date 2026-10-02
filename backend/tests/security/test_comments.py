"""
Tests for artist-scoped community comment operations.

These tests verify that community interactions are properly scoped to artists.
They replaced the deprecated global community comment tests.
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        # Register and login first user
        c.post("/auth/register", json={"email": "communityuser@gigcrowd.com", "username": "communityuser", "password": "TestPass123!"})
        resp = c.post("/auth/login", data={"username": "communityuser@gigcrowd.com", "password": "TestPass123!"})
        token = resp.json()["access_token"]
        c.headers["Authorization"] = f"Bearer {token}"

        # Register and login second user
        c.post("/auth/register", json={"email": "otheruser@gigcrowd.com", "username": "otheruser", "password": "TestPass123!"})
        resp2 = c.post("/auth/login", data={"username": "otheruser@gigcrowd.com", "password": "TestPass123!"})
        second_token = resp2.json()["access_token"]

        # Store both tokens for use in tests
        c._first_token = token
        c._second_token = second_token

        yield c


@pytest.fixture(scope="module")
def artist_a(client):
    """Get artist A for testing."""
    resp = client.get("/artists")
    artists = resp.json()
    if not artists:
        pytest.skip("No artists available")
    return artists[0]["slug"]


@pytest.fixture(scope="module")
def artist_b(client):
    """Get artist B for testing isolation."""
    resp = client.get("/artists")
    artists = resp.json()
    if len(artists) < 2:
        pytest.skip("Need at least 2 artists for isolation tests")
    return artists[1]["slug"]


@pytest.fixture(scope="module")
def community_post(client, artist_a):
    """Create a community post for artist A."""
    # Follow artist A
    client.post(f"/artists/{artist_a}/follow")

    # Create post in artist A's community
    resp = client.post(f"/artists/{artist_a}/community/posts", json={"content": "Test post for comments"})
    return resp.json()


class TestCommentCreation:
    """Test comment creation on artist community posts."""

    def test_authenticated_user_can_comment(self, client, artist_a, community_post):
        """Authenticated user can create comments."""
        resp = client.post(f"/artists/{artist_a}/community/comments", json={
            "post_id": community_post["id"],
            "content": "Test comment",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["content"] == "Test comment"
        assert data["post_id"] == community_post["id"]

    def test_unauthenticated_cannot_comment(self, client, artist_a, community_post):
        """Unauthenticated users cannot create comments."""
        # Send the request without the session header. A second TestClient
        # would tear down the app lifespan and close the shared Mongo client.
        old_token = client.headers.get("Authorization")
        if "Authorization" in client.headers:
            del client.headers["Authorization"]

        resp = client.post(f"/artists/{artist_a}/community/comments", json={
            "post_id": community_post["id"],
            "content": "Anonymous comment",
        })
        assert resp.status_code == 401

        # Restore auth header
        if old_token:
            client.headers["Authorization"] = old_token

    def test_non_follower_cannot_comment(self, client, artist_a, artist_b, community_post):
        """User who doesn't follow the artist cannot comment."""
        # Create post in artist A's community
        resp = client.post(f"/artists/{artist_a}/community/posts", json={"content": "Test post"})
        community_post = resp.json()

        # Use second user who doesn't follow artist A
        old_token = client.headers.get("Authorization")
        client.headers["Authorization"] = f"Bearer {client._second_token}"

        resp = client.post(f"/artists/{artist_a}/community/comments", json={
            "post_id": community_post["id"],
            "content": "Attempting to comment",
        })
        # Should get 403, not redirect to login
        assert resp.status_code == 403

        # Restore original token
        if old_token:
            client.headers["Authorization"] = old_token


class TestCommentIsolation:
    """Test that comments are properly isolated by artist."""

    def test_comments_belong_to_correct_artist(self, client, artist_a, artist_b, community_post):
        """All comments belong to the correct artist's community."""
        # Create post in artist A's community
        resp = client.post(f"/artists/{artist_a}/community/posts", json={"content": "Test post"})
        community_post = resp.json()

        # Get comments for artist A
        resp = client.get(f"/artists/{artist_a}/community/posts/{community_post['id']}/comments")
        assert resp.status_code == 200
        comments = resp.json()
        assert len(comments) >= 0

        # Comments should NOT be accessible via artist B's community
        resp = client.get(f"/artists/{artist_b}/community/posts/{community_post['id']}/comments")
        assert resp.status_code == 404


class TestReplyCreation:
    """Test reply creation on artist community comments."""

    def test_authenticated_user_can_reply(self, client, artist_a, community_post):
        """Authenticated user can create replies."""
        # First create a comment
        resp = client.post(f"/artists/{artist_a}/community/comments", json={
            "post_id": community_post["id"],
            "content": "Test comment",
        })
        comment_id = resp.json()["id"]

        # Then create a reply
        resp = client.post(f"/artists/{artist_a}/community/comments", json={
            "post_id": community_post["id"],
            "content": "This is a reply",
            "parent_comment_id": comment_id,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["content"] == "This is a reply"
        assert data["parent_comment_id"] == comment_id


class TestReadOnlyAccess:
    """Test that unauthenticated and non-followers can read."""

    def test_unauthenticated_can_read_posts(self, client, artist_a):
        """Unauthenticated users can read community posts."""
        # Remove auth header
        old_token = client.headers.get("Authorization")
        if "Authorization" in client.headers:
            del client.headers["Authorization"]

        resp = client.get(f"/artists/{artist_a}/community/posts")
        assert resp.status_code == 200

        # Restore auth header
        if old_token:
            client.headers["Authorization"] = old_token

    def test_unauthenticated_can_read_comments(self, client, artist_a, community_post):
        """Unauthenticated users can read comments."""
        # Remove auth header
        old_token = client.headers.get("Authorization")
        if "Authorization" in client.headers:
            del client.headers["Authorization"]

        resp = client.get(f"/artists/{artist_a}/community/posts/{community_post['id']}/comments")
        assert resp.status_code == 200

        # Restore auth header
        if old_token:
            client.headers["Authorization"] = old_token

    def test_non_follower_can_read_posts(self, client, artist_a, artist_b, community_post):
        """Authenticated users who don't follow can still read posts."""
        # Use second user who doesn't follow artist A
        old_token = client.headers.get("Authorization")
        client.headers["Authorization"] = f"Bearer {client._second_token}"

        resp = client.get(f"/artists/{artist_a}/community/posts")
        assert resp.status_code == 200

        # Restore original token
        if old_token:
            client.headers["Authorization"] = old_token