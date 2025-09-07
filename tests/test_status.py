import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_read_main():
    response = client.get("/")
    assert response.status_code == 200
    assert "message" in response.json()

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

@pytest.mark.asyncio
async def test_async_endpoint():
    response = client.get("/async-endpoint")
    assert response.status_code == 200

def test_protected_endpoint_without_auth():
    response = client.get("/protected")
    assert response.status_code == 401

def test_protected_endpoint_with_auth():
    headers = {"Authorization": "Bearer fake-token"}
    response = client.get("/protected", headers=headers)
    assert response.status_code in [200, 401, 403]

class TestUserEndpoints:
    
    def test_create_user(self):
        user_data = {
            "email": "test@example.com",
            "password": "testpass123"
        }
        response = client.post("/users/", json=user_data)
        assert response.status_code in [200, 201, 422]
    
    def test_get_user(self):
        response = client.get("/users/1")
        assert response.status_code in [200, 404]
    
    def test_update_user(self):
        update_data = {"email": "updated@example.com"}
        response = client.put("/users/1", json=update_data)
        assert response.status_code in [200, 404, 401]

@pytest.mark.parametrize("method,endpoint,expected_status", [
    ("GET", "/", 200),
    ("GET", "/health", 200),
    ("GET", "/docs", 200),
    ("GET", "/openapi.json", 200),
])
def test_endpoints(method, endpoint, expected_status):
    response = getattr(client, method.lower())(endpoint)
    assert response.status_code == expected_status