import json

import httpx
import pytest

from app import embeddings
from app.config import settings
from app.embeddings import EmbeddingError, embed_query, embed_texts, estimate_tokens


@pytest.fixture(autouse=True)
def embedding_settings(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_base_url", "https://openrouter.test/api/v1/")
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-or-test")
    monkeypatch.setattr(settings, "embedding_model", "baai/bge-m3")
    monkeypatch.setattr(settings, "embedding_dimensions", 3)
    monkeypatch.setattr(settings, "embedding_max_input_tokens", 8000)
    monkeypatch.setattr(settings, "embedding_query_instruction", "")
    monkeypatch.setattr(embeddings.asyncio, "sleep", _no_sleep)


async def _no_sleep(_seconds: float) -> None:
    return None


def client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def ok(*vectors: list[float]) -> httpx.Response:
    # Out of order on purpose: results are matched to inputs by index, not position.
    data = [{"index": i, "embedding": v} for i, v in enumerate(vectors)]
    return httpx.Response(200, json={"data": list(reversed(data))})


@pytest.mark.anyio
async def test_posts_openai_compatible_request_and_orders_by_index():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return ok([0.1, 0.2, 0.3], [0.4, 0.5, 0.6])

    async with client(handler) as http:
        vectors = await embed_texts(http, ["a", "b"])

    assert vectors == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    assert seen["url"] == "https://openrouter.test/api/v1/embeddings"
    assert seen["auth"] == "Bearer sk-or-test"
    assert seen["body"] == {"model": "baai/bge-m3", "input": ["a", "b"], "encoding_format": "float"}


@pytest.mark.anyio
async def test_over_long_input_is_refused_before_any_request(monkeypatch):
    monkeypatch.setattr(settings, "embedding_max_input_tokens", 10)
    requests = []
    async with client(lambda request: requests.append(request) or ok([1.0, 0.0, 0.0])) as http:
        with pytest.raises(EmbeddingError, match="exceeds EMBEDDING_MAX_INPUT_TOKENS"):
            await embed_texts(http, ["x" * 100])
    assert requests == []


@pytest.mark.anyio
async def test_rate_limit_is_retried_then_succeeds():
    responses = iter([httpx.Response(429), httpx.Response(503), ok([1.0, 0.0, 0.0])])
    async with client(lambda _: next(responses)) as http:
        assert await embed_texts(http, ["a"]) == [[1.0, 0.0, 0.0]]


@pytest.mark.anyio
async def test_client_errors_are_not_retried():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(401, json={"error": {"message": "No auth credentials found"}})

    async with client(handler) as http:
        with pytest.raises(EmbeddingError, match="401"):
            await embed_texts(http, ["a"])
    assert len(calls) == 1


@pytest.mark.anyio
async def test_error_inside_a_200_response_is_raised():
    body = {"error": {"message": "upstream provider unavailable"}}
    async with client(lambda _: httpx.Response(200, json=body)) as http:
        with pytest.raises(EmbeddingError, match="upstream provider unavailable"):
            await embed_texts(http, ["a"])


@pytest.mark.anyio
async def test_wrong_dimensions_fail_before_anything_is_stored():
    async with client(lambda _: ok([0.1, 0.2])) as http:
        with pytest.raises(EmbeddingError, match="returned 2 dimensions"):
            await embed_texts(http, ["a"])


@pytest.mark.anyio
async def test_missing_embeddings_fail():
    async with client(lambda _: ok([0.1, 0.2, 0.3])) as http:
        with pytest.raises(EmbeddingError, match="Asked for 2"):
            await embed_texts(http, ["a", "b"])


@pytest.mark.anyio
async def test_query_gets_instruction_prefix_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "embedding_query_instruction", "Retrieve filing passages")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["input"] = json.loads(request.content)["input"]
        return ok([1.0, 0.0, 0.0])

    async with client(handler) as http:
        assert await embed_query(http, "What is AWS margin?") == [1.0, 0.0, 0.0]
    assert seen["input"] == ["Instruct: Retrieve filing passages\nQuery:What is AWS margin?"]


def test_query_without_instruction_is_unchanged():
    assert embeddings.query_text("plain question") == "plain question"


def test_token_estimate_rounds_up():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abc") == 2
