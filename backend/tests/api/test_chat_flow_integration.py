"""End to end against the local Supabase stack: real sign-up, real token check, real database.

Needs `supabase start` and `uv run alembic upgrade head`. Uses the stub reply, so no model runs.
"""

import json
from uuid import uuid4

import httpx
import psycopg
import pytest

from app.config import settings
from app.main import app

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


async def sign_up(email: str) -> str:
    async with httpx.AsyncClient() as http:
        response = await http.post(
            f"{settings.supabase_url}/auth/v1/signup",
            headers={"apikey": settings.supabase_anon_key},
            json={"email": email, "password": "integration-password-1"},
        )
    response.raise_for_status()
    return response.json()["access_token"]


@pytest.fixture
async def users():
    run = uuid4().hex[:8]
    emails = [f"it-{run}-a@driftwood.test", f"it-{run}-b@driftwood.test"]
    tokens = [await sign_up(email) for email in emails]
    yield tokens
    async with await psycopg.AsyncConnection.connect(settings.database_url) as conn:
        await conn.execute("delete from auth.users where email = any(%s)", (emails,))
        await conn.commit()


@pytest.fixture
async def api():
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_a_user_can_chat_and_only_they_can_read_it(api, users):
    token_a, token_b = users

    assert (await api.get("/threads")).status_code == 401
    assert (await api.get("/threads", headers=auth("not-a-jwt"))).status_code == 401

    created = await api.post("/threads", headers=auth(token_a))
    assert created.status_code == 201
    thread_id = created.json()["id"]

    body = {
        "threadId": thread_id,
        "message": {"id": "client-1", "role": "user", "parts": [{"type": "text", "text": "What is AWS margin?"}]},
    }
    stream = await api.post("/chat/stream", headers=auth(token_a), json=body)
    assert stream.status_code == 200
    assert stream.headers["x-vercel-ai-ui-message-stream"] == "v1"
    payloads = [line.removeprefix("data: ") for line in stream.text.split("\n\n") if line]
    assert payloads[-1] == "[DONE]"
    assert json.loads(payloads[-2])["type"] == "finish"

    messages = (await api.get(f"/threads/{thread_id}/messages", headers=auth(token_a))).json()
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[0]["parts"] == [{"type": "text", "text": "What is AWS margin?"}]
    assert "placeholder reply" in messages[1]["parts"][0]["text"]
    assert messages[1]["id"] == json.loads(payloads[0])["messageId"]

    threads_a = (await api.get("/threads", headers=auth(token_a))).json()
    assert [(t["id"], t["title"]) for t in threads_a] == [(thread_id, "What is AWS margin?")]

    assert (await api.get("/threads", headers=auth(token_b))).json() == []
    assert (await api.get(f"/threads/{thread_id}/messages", headers=auth(token_b))).status_code == 403
    assert (await api.post("/chat/stream", headers=auth(token_b), json=body)).status_code == 403
    assert (await api.get(f"/threads/{uuid4()}", headers=auth(token_a))).status_code == 404


async def test_rejects_non_user_message(api, users):
    token_a, _ = users
    thread_id = (await api.post("/threads", headers=auth(token_a))).json()["id"]
    body = {
        "threadId": thread_id,
        "message": {"id": "x", "role": "assistant", "parts": [{"type": "text", "text": "I am the assistant"}]},
    }
    response = await api.post("/chat/stream", headers=auth(token_a), json=body)
    assert response.status_code == 422
