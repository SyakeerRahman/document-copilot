"""End to end against the local Supabase stack: real sign-up, real token check, real database, real agent.

Needs `supabase start`, the ingested corpus, and a real OPENROUTER_API_KEY. Runs the agent for two turns,
which costs a fraction of a cent and takes about 30 seconds.
"""

import json
from uuid import uuid4

import httpx
import psycopg
import pytest

from app.config import settings
from app.main import app

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

AGENT_TIMEOUT_SECONDS = 120


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


def ask(thread_id: str, text: str) -> dict:
    return {
        "threadId": thread_id,
        "message": {"id": uuid4().hex, "role": "user", "parts": [{"type": "text", "text": text}]},
    }


def stream_payloads(response: httpx.Response) -> list[str]:
    return [line.removeprefix("data: ") for line in response.text.split("\n\n") if line]


async def citation_rows(message_id: str) -> list[tuple[int, str, int]]:
    async with await psycopg.AsyncConnection.connect(settings.database_url) as conn:
        cursor = await conn.execute(
            "select mc.citation_index, d.ticker, d.fiscal_year from message_citations mc "
            "join document_chunks c on c.id = mc.chunk_id join source_documents d on d.id = c.document_id "
            "where mc.message_id = %s order by mc.citation_index",
            (message_id,),
        )
        return await cursor.fetchall()


async def test_a_user_can_chat_and_only_they_can_read_it(api, users):
    token_a, token_b = users

    assert (await api.get("/threads")).status_code == 401
    assert (await api.get("/threads", headers=auth("not-a-jwt"))).status_code == 401
    assert (await api.get("/corpus")).status_code == 401

    corpus = (await api.get("/corpus", headers=auth(token_a))).json()
    assert {c["ticker"] for c in corpus} == {"AAPL", "AMZN", "GOOGL", "MSFT", "NVDA"}
    assert next(c for c in corpus if c["ticker"] == "AMZN") == {
        "ticker": "AMZN",
        "companyName": "AMAZON.COM, INC.",
        "fiscalYears": [2021, 2022, 2023, 2024, 2025],
    }

    created = await api.post("/threads", headers=auth(token_a))
    assert created.status_code == 201
    thread_id = created.json()["id"]

    question = "What was AWS operating income in fiscal 2025?"
    body = ask(thread_id, question)
    stream = await api.post("/chat/stream", headers=auth(token_a), json=body, timeout=AGENT_TIMEOUT_SECONDS)
    assert stream.status_code == 200
    assert stream.headers["x-vercel-ai-ui-message-stream"] == "v1"
    payloads = stream_payloads(stream)
    assert payloads[-1] == "[DONE]"
    assert json.loads(payloads[-2])["type"] == "finish"
    assert "data-citations" in [json.loads(p)["type"] for p in payloads[:-1]]

    messages = (await api.get(f"/threads/{thread_id}/messages", headers=auth(token_a))).json()
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[0]["parts"] == [{"type": "text", "text": question}]
    answer_id = json.loads(payloads[0])["messageId"]
    assert messages[1]["id"] == answer_id
    text_part, citations_part = messages[1]["parts"]
    assert "[P" in text_part["text"]
    assert citations_part["type"] == "data-citations"
    assert {(c["ticker"], c["fiscalYear"]) for c in citations_part["data"]} == {("AMZN", 2025)}
    # The saved citation rows match the part the browser received, in order.
    rows = await citation_rows(answer_id)
    assert [index for index, _, _ in rows] == list(range(1, len(citations_part["data"]) + 1))

    # A follow-up that only makes sense with the history: the agent must carry the company into the new year.
    follow_up = await api.post(
        "/chat/stream", headers=auth(token_a), json=ask(thread_id, "And in fiscal 2024?"), timeout=AGENT_TIMEOUT_SECONDS
    )
    follow_id = json.loads(stream_payloads(follow_up)[0])["messageId"]
    assert ("AMZN", 2024) in {(ticker, year) for _, ticker, year in await citation_rows(follow_id)}

    threads_a = (await api.get("/threads", headers=auth(token_a))).json()
    assert [(t["id"], t["title"]) for t in threads_a] == [(thread_id, question)]

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
