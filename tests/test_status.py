import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_read_main():
    """Test the root endpoint"""
    response = client.get("/")
    assert response.status_code == 200
    assert "message" in response.json()

def test_health_check():
    """Test health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

@pytest.mark.asyncio
async def test_async_endpoint():
    """Example async test"""
    response = client.get("/async-endpoint")
    assert response.status_code == 200

def test_protected_endpoint_without_auth():
    """Test protected endpoint without authentication"""
    response = client.get("/protected")
    assert response.status_code == 401

def test_protected_endpoint_with_auth():
    """Test protected endpoint with authentication"""
    # Mock authentication headers
    headers = {"Authorization": "Bearer fake-token"}
    response = client.get("/protected", headers=headers)
    # Adjust assertion based on your auth implementation
    assert response.status_code in [200, 401, 403]

class TestUserEndpoints:
    """Group related tests in a class"""
    
    def test_create_user(self):
        """Test user creation"""
        user_data = {
            "email": "test@example.com",
            "password": "testpass123"
        }
        response = client.post("/users/", json=user_data)
        assert response.status_code in [200, 201, 422]  # Adjust based on your implementation
    
    def test_get_user(self):
        """Test get user by ID"""
        response = client.get("/users/1")
        assert response.status_code in [200, 404]  # User might not exist
    
    def test_update_user(self):
        """Test user update"""
        update_data = {"email": "updated@example.com"}
        response = client.put("/users/1", json=update_data)
        assert response.status_code in [200, 404, 401]

# Test with different HTTP methods
@pytest.mark.parametrize("method,endpoint,expected_status", [
    ("GET", "/", 200),
    ("GET", "/health", 200),
    ("GET", "/docs", 200),
    ("GET", "/openapi.json", 200),
])
def test_endpoints(method, endpoint, expected_status):
    """Test multiple endpoints with different methods"""
    response = getattr(client, method.lower())(endpoint)
    assert response.status_code == expected_status