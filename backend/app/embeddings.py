import asyncio
import math

import httpx

from app.config import settings

EMBED_TIMEOUT_SECONDS = 120
RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 4
# Pessimistic on purpose: figure-heavy filing text measured ~2.8 characters per token.
CHARS_PER_TOKEN = 2.8


class EmbeddingError(RuntimeError):
    pass


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN)


async def embed_texts(http: httpx.AsyncClient, texts: list[str]) -> list[list[float]]:
    # Refuse over-long input before sending. A provider that silently truncates would leave the end
    # of a passage unsearchable, with no error anywhere.
    for text in texts:
        if estimate_tokens(text) > settings.embedding_max_input_tokens:
            raise EmbeddingError(
                f"Input of ~{estimate_tokens(text)} tokens exceeds EMBEDDING_MAX_INPUT_TOKENS "
                f"({settings.embedding_max_input_tokens}): {text[:80]!r}"
            )

    body = await _post_with_retries(
        http, {"model": settings.embedding_model, "input": texts, "encoding_format": "float"}
    )
    if "error" in body:
        # OpenRouter can report upstream provider failures inside a 200 response.
        raise EmbeddingError(f"OpenRouter embedding error: {body['error']}")

    data = sorted(body["data"], key=lambda item: item["index"])
    vectors: list[list[float]] = [item["embedding"] for item in data]
    if len(vectors) != len(texts):
        raise EmbeddingError(f"Asked for {len(texts)} embeddings, got {len(vectors)}")
    for vector in vectors:
        if len(vector) != settings.embedding_dimensions:
            raise EmbeddingError(
                f"{settings.embedding_model} returned {len(vector)} dimensions; "
                f"EMBEDDING_DIMENSIONS is {settings.embedding_dimensions}"
            )
    return vectors


async def _post_with_retries(http: httpx.AsyncClient, payload: dict) -> dict:
    url = f"{settings.openrouter_base_url.rstrip('/')}/embeddings"
    headers = {"Authorization": f"Bearer {settings.openrouter_api_key}"}
    for attempt in range(1, MAX_ATTEMPTS + 1):
        response = await http.post(url, json=payload, headers=headers, timeout=EMBED_TIMEOUT_SECONDS)
        if response.status_code == 200:
            return response.json()
        if response.status_code not in RETRY_STATUSES or attempt == MAX_ATTEMPTS:
            raise EmbeddingError(f"OpenRouter embeddings returned {response.status_code}: {response.text[:300]}")
        await asyncio.sleep(2**attempt)
    raise AssertionError("unreachable")


def query_text(question: str) -> str:
    if not settings.embedding_query_instruction:
        return question
    # Qwen3-Embedding's documented query format. Passages are embedded without it.
    return f"Instruct: {settings.embedding_query_instruction}\nQuery:{question}"


async def embed_query(http: httpx.AsyncClient, question: str) -> list[float]:
    return (await embed_texts(http, [query_text(question)]))[0]
