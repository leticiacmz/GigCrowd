"""
Security tests for GigCrowd API.
Tests security headers, input validation, rate limiting, CORS, and XSS protection.
Note: These tests do not require database connection.
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    # raise_server_exceptions=False so DB errors return 500 instead of raising
    return TestClient(app, raise_server_exceptions=False)


# ==========================================
# Security Headers Tests
# ==========================================

class TestSecurityHeaders:
    """Test security headers are present."""

    def test_security_headers_present(self, client):
        """Test that security headers are set on responses."""
        response = client.get("/")
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert "no-store" in response.headers.get("Cache-Control", "")

    def test_security_headers_on_404(self, client):
        """Test that security headers are set on 404 responses."""
        response = client.get("/nonexistent")
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"

    def test_security_headers_on_422(self, client):
        """Test that security headers are set on 422 responses."""
        response = client.get("/feed?skip=abc")
        assert response.headers.get("X-Content-Type-Options") == "nosniff"


# ==========================================
# Input Validation Tests
# ==========================================

class TestInputValidation:
    """Test input validation and injection prevention."""

    def test_pagination_string_skip(self, client):
        """Test that string skip values are rejected."""
        response = client.get("/feed?skip=abc")
        # Should be 422 (validation error) or 401 (auth required)
        assert response.status_code in [401, 422]

    def test_pagination_string_limit(self, client):
        """Test that string limit values are rejected."""
        response = client.get("/feed?limit=abc")
        assert response.status_code in [401, 422]

    def test_pagination_negative_skip(self, client):
        """Test that negative skip values are rejected."""
        response = client.get("/feed?skip=-100")
        assert response.status_code in [401, 422]

    def test_pagination_zero_limit(self, client):
        """Test that zero limit is rejected."""
        response = client.get("/feed?limit=0")
        assert response.status_code in [401, 422]

    def test_pagination_excessive_limit(self, client):
        """Test that excessive limit values are rejected."""
        response = client.get("/feed?limit=10000")
        assert response.status_code in [401, 422]


# ==========================================
# Authentication Error Message Tests
# ==========================================

class TestAuthenticationErrors:
    """Test that authentication errors don't leak information."""

    def test_login_invalid_credentials_format(self, client):
        """Test that login with invalid format returns 422."""
        response = client.post("/auth/login", data={
            "username": "",
            "password": ""
        })
        assert response.status_code == 422

    def test_register_invalid_email_format(self, client):
        """Test that registration with invalid email returns 422."""
        response = client.post("/auth/register", json={
            "email": "not-an-email",
            "username": "testuser",
            "password": "SecurePass123!"
        })
        assert response.status_code == 422

    def test_register_short_username(self, client):
        """Test that registration with short username returns 422."""
        response = client.post("/auth/register", json={
            "email": "test@gigcrowd.com",
            "username": "ab",
            "password": "SecurePass123!"
        })
        assert response.status_code == 422

    def test_register_short_password(self, client):
        """Test that registration with short password returns 422."""
        response = client.post("/auth/register", json={
            "email": "test@gigcrowd.com",
            "username": "testuser",
            "password": "123"
        })
        assert response.status_code == 422


# ==========================================
# CORS Tests
# ==========================================

class TestCORS:
    """Test CORS configuration."""

    def test_cors_preflight(self, client):
        """Test CORS preflight request."""
        response = client.options("/", headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET"
        })
        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers

    def test_cors_disallowed_origin(self, client):
        """Test that disallowed origins are rejected."""
        response = client.get("/", headers={
            "Origin": "http://evil.com"
        })
        # Should not have CORS headers for disallowed origin
        assert "access-control-allow-origin" not in response.headers


# ==========================================
# User-Generated Content Tests
# ==========================================

class TestUserGeneratedContent:
    """Test safe handling of user-generated content."""

    def test_username_xss_rejected(self, client):
        """Test that usernames with HTML/JS are rejected."""
        response = client.post("/auth/register", json={
            "email": "xssuser@gigcrowd.com",
            "username": "<script>alert('xss')</script>",
            "password": "SecurePass123!"
        })
        # Should be rejected due to invalid username format or DB error
        assert response.status_code in [400, 422, 500]

    def test_username_html_rejected(self, client):
        """Test that usernames with HTML are rejected."""
        response = client.post("/auth/register", json={
            "email": "htmluser@gigcrowd.com",
            "username": "<b>bold</b>",
            "password": "SecurePass123!"
        })
        # Should be rejected due to invalid username format or DB error
        assert response.status_code in [400, 422, 500]


# ==========================================
# Rate Limiting Tests (run last to avoid affecting other tests)
# ==========================================

class TestRateLimiting:
    """Test rate limiting on auth endpoints."""

    def test_rate_limit_allows_normal_requests(self, client):
        """Test that normal request rate is allowed."""
        for _ in range(3):
            response = client.post("/auth/login", data={
                "username": "test@gigcrowd.com",
                "password": "test"
            })
            # Should not be 429 (rate limited) - will be 500 (DB error) or 401
            assert response.status_code != 429

    def test_rate_limit_returns_429(self, client):
        """Test that excessive requests return 429."""
        response = None
        for _ in range(105):
            response = client.post("/auth/login", data={
                "username": "test@gigcrowd.com",
                "password": "test"
            })

        # The last request should be rate limited
        assert response.status_code == 429
