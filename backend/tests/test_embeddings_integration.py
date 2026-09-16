import httpx
import pytest

from app.config import settings
from app.embeddings import embed_query, embed_texts

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


async def test_configured_model_matches_configured_dimensions():
    # Needs a real OPENROUTER_API_KEY in backend/.env. Costs a fraction of a cent.
    async with httpx.AsyncClient() as http:
        vector = await embed_query(http, "How did AWS operating income change?")
    assert len(vector) == settings.embedding_dimensions


async def test_similar_passages_are_closer_than_unrelated_ones():
    async with httpx.AsyncClient() as http:
        question, related, unrelated = await embed_texts(
            http,
            [
                "How much revenue did AWS generate?",
                "AWS segment net sales increased 19% compared with the prior year.",
                "The company's headquarters is located in Seattle, Washington.",
            ],
        )

    def cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b, strict=True))
        return dot / (sum(x * x for x in a) ** 0.5 * sum(y * y for y in b) ** 0.5)

    assert cosine(question, related) > cosine(question, unrelated)
