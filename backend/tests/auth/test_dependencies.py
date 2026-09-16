from uuid import UUID

import httpx
import pytest

from app.auth.dependencies import AuthUnavailable, InvalidToken, verify_access_token
from app.config import settings

USER_ID = "7d3f1c2e-8a4b-4c5d-9e6f-0a1b2c3d4e5f"


def client_returning(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.anyio
async def test_valid_token_returns_user_and_forwards_credentials():
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers["authorization"]
        seen["apikey"] = request.headers["apikey"]
        return httpx.Response(200, json={"id": USER_ID, "email": "analyst@driftwood.test"})

    async with client_returning(handler) as http:
        user = await verify_access_token(http, "token-123")

    assert user.id == UUID(USER_ID)
    assert user.email == "analyst@driftwood.test"
    assert seen == {
        "url": f"{settings.supabase_url}/auth/v1/user",
        "authorization": "Bearer token-123",
        "apikey": settings.supabase_anon_key,
    }


@pytest.mark.anyio
@pytest.mark.parametrize("status_code", [400, 401, 403])
async def test_rejected_token_is_invalid(status_code):
    async with client_returning(lambda _: httpx.Response(status_code, json={"msg": "bad_jwt"})) as http:
        with pytest.raises(InvalidToken):
            await verify_access_token(http, "expired")


@pytest.mark.anyio
async def test_supabase_server_error_is_unavailable_not_invalid():
    async with client_returning(lambda _: httpx.Response(500)) as http:
        with pytest.raises(AuthUnavailable):
            await verify_access_token(http, "token")


@pytest.mark.anyio
async def test_network_failure_is_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    async with client_returning(handler) as http:
        with pytest.raises(AuthUnavailable):
            await verify_access_token(http, "token")
