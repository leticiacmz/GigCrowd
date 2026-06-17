import pytest
from app.database.connection import db


@pytest.fixture(autouse=True)
async def setup_database():
    """Setup database connection for tests"""
    # In production, you would use a test database
    # For now, we skip actual database setup
    yield
    # Cleanup if needed
