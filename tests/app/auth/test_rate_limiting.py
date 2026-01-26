import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
from unittest.mock import patch, MagicMock

from app.auth.routes import router
from shorui_core.infrastructure.rate_limiter import limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware


@pytest.fixture
def app():
    """Create a test app with rate limiting enabled."""
    app = FastAPI()
    # Use a fresh limiter with memory storage for testing
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    test_limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")
    app.state.limiter = test_limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    
    # We also need to patch the global limiter used by decorators
    # Since decorators are already applied, we can't easily change them.
    # However, slowapi stores the limiter in app.state.limiter and uses it.
    # BUT the decorator adds the limit to the route.
    
    app.include_router(router)
    return app


@pytest.mark.asyncio
async def test_login_rate_limit(app):
    """Test that login endpoint is rate limited."""
    # Mock services
    with patch("app.auth.routes.get_user_service") as mock_user_service_factory, \
         patch("app.auth.routes.get_jwt_service") as mock_jwt_service_factory:
        
        # Configure mocks
        mock_user_service = mock_user_service_factory.return_value
        mock_user_service.authenticate.return_value = {
            "user_id": "test-user",
            "email": "test@example.com",
            "tenant_id": "test-tenant",
            "role": "user",
        }
        
        mock_jwt_service = mock_jwt_service_factory.return_value
        mock_jwt_service.create_access_token.return_value = "access.token.jwt"
        mock_jwt_service.create_refresh_token.return_value = "refresh.token.jwt"

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Send 5 requests
            for i in range(5):
                response = await client.post(
                    "/auth/login",
                    json={"email": "test@example.com", "password": "password"},
                )
                assert response.status_code == 200, f"Request {i+1} failed: {response.text}"

            # Send 6th request (should be BLOCKED if rate limited, but allowed in baseline)
            response = await client.post(
                "/auth/login",
                json={"email": "test@example.com", "password": "password"},
            )
            if response.status_code == 422:
                 print(f"FAILED with 422: {response.text}")
                 
            # In baseline (no limits), this should be 200.
            # When limits applied, this should be 429.
            assert response.status_code == 429
