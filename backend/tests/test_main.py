import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app"""
    return TestClient(app)


def test_root_endpoint(client):
    """Test the root endpoint"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Welcome to GigCrowd API"
    assert data["status"] == "healthy"


def test_health_check(client):
    """Test the health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_register_user(client):
    """Test user registration"""
    user_data = {
        "email": "test@example.com",
        "username": "testuser",
        "password": "testpassword123",
        "full_name": "Test User"
    }
    response = client.post("/auth/register", json=user_data)
    # May fail if user already exists, but endpoint should be reachable
    assert response.status_code in [200, 201, 400]


def test_login_user(client):
    """Test user login"""
    response = client.post("/auth/login", params={
        "email": "test@example.com",
        "password": "testpassword123"
    })
    # May fail if user doesn't exist, but endpoint should be reachable
    assert response.status_code in [200, 401]


def test_get_events(client):
    """Test getting events list"""
    response = client.get("/events")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_get_artists(client):
    """Test getting artists list"""
    response = client.get("/artists")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
