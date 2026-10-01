"""
Tests for ArtistFollowRepository to verify the db attribute fix.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.repositories.artist_follow_repository import ArtistFollowRepository


@pytest.fixture
def mock_db():
    """Create a mock database with async collection methods."""
    db = MagicMock()
    db.artists = MagicMock()
    db.users = MagicMock()
    db.artist_follows = MagicMock()
    return db


@pytest.fixture
def repository(mock_db):
    """Create an ArtistFollowRepository instance."""
    return ArtistFollowRepository(mock_db)


class TestArtistFollowRepositoryInit:
    """Test that the repository is properly initialized with db attribute."""

    def test_repository_has_db_attribute(self, repository, mock_db):
        """Verify that the repository has a db attribute after initialization."""
        assert hasattr(repository, 'db')
        assert repository.db is mock_db

    def test_repository_has_collection_attribute(self, repository):
        """Verify that the repository has a collection attribute."""
        assert hasattr(repository, 'collection')


class TestArtistFollowRepositoryMethods:
    """Test that repository methods work correctly with the db attribute."""

    @pytest.mark.asyncio
    async def test_create_follow_updates_artist_count(self, repository, mock_db):
        """Test that create_follow updates the artist followers count."""
        # Setup
        mock_db.artists.update_one = AsyncMock()
        mock_db.users.update_one = AsyncMock()
        mock_collection = MagicMock()
        mock_collection.insert_one = AsyncMock(return_value=MagicMock(inserted_id="test_id"))
        repository.collection = mock_collection

        # Execute
        await repository.create_follow("user123", "artist-slug")

        # Verify
        mock_db.artists.update_one.assert_called_once_with(
            {"slug": "artist-slug"},
            {"$inc": {"followers_count": 1}}
        )
        mock_db.users.update_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_follow_updates_artist_count(self, repository, mock_db):
        """Test that delete_follow updates the artist followers count."""
        # Setup
        mock_db.artists.update_one = AsyncMock()
        mock_db.users.update_one = AsyncMock()
        mock_collection = MagicMock()
        mock_collection.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))
        repository.collection = mock_collection

        # Execute
        await repository.delete_follow("user123", "artist-slug")

        # Verify
        mock_db.artists.update_one.assert_called_once_with(
            {"slug": "artist-slug"},
            {"$inc": {"followers_count": -1}}
        )
        mock_db.users.update_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_follow_no_update_when_not_found(self, repository, mock_db):
        """Test that delete_follow doesn't update counts when follow doesn't exist."""
        # Setup
        mock_db.artists.update_one = AsyncMock()
        mock_db.users.update_one = AsyncMock()
        mock_collection = MagicMock()
        mock_collection.delete_one = AsyncMock(return_value=MagicMock(deleted_count=0))
        repository.collection = mock_collection

        # Execute
        await repository.delete_follow("user123", "artist-slug")

        # Verify
        mock_db.artists.update_one.assert_not_called()
        mock_db.users.update_one.assert_not_called()


class TestFeedActivityRepositoryInit:
    """Test that FeedActivityRepository works with the db attribute fix."""

    def test_repository_has_db_attribute(self, mock_db):
        """Verify that FeedActivityRepository has a db attribute."""
        from app.repositories.feed_activity_repository import FeedActivityRepository
        repo = FeedActivityRepository(mock_db)
        assert hasattr(repo, 'db')
        assert repo.db is mock_db


class TestCommunityPostRepositoryInit:
    """Test that CommunityPostRepository works with the db attribute fix."""

    def test_repository_has_db_attribute(self, mock_db):
        """Verify that CommunityPostRepository has a db attribute."""
        from app.repositories.community_post_repository import CommunityPostRepository
        repo = CommunityPostRepository(mock_db)
        assert hasattr(repo, 'db')
        assert repo.db is mock_db


class TestCommentRepositoryInit:
    """Test that CommentRepository works with the db attribute fix."""

    def test_repository_has_db_attribute(self, mock_db):
        """Verify that CommentRepository has a db attribute."""
        from app.repositories.comment_repository import CommentRepository
        repo = CommentRepository(mock_db)
        assert hasattr(repo, 'db')
        assert repo.db is mock_db
