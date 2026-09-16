"""Search against the ingested corpus. Needs local Supabase, ingestion done with the current
EMBEDDING_MODEL, and a real OPENROUTER_API_KEY (hybrid and semantic modes embed the question)."""

import httpx
import pytest

from app.database.session import create_engine, create_sessionmaker
from app.retrieval.models import SearchFilters
from app.retrieval.retriever import NO_FILTERS, search_filings

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


@pytest.fixture
async def search():
    engine = create_engine()
    sessionmaker = create_sessionmaker(engine)
    async with httpx.AsyncClient() as http:

        async def run(question: str, filters: SearchFilters = NO_FILTERS, **kwargs):
            async with sessionmaker() as session:
                return await search_filings(session, http, question, filters, **kwargs)

        yield run
    await engine.dispose()


@pytest.mark.parametrize("mode", ["hybrid", "semantic", "keyword"])
async def test_filters_restrict_results_to_that_company_and_year(search, mode):
    passages = await search(
        "net sales by category", SearchFilters(tickers=("AAPL",), fiscal_years=(2024,)), limit=10, mode=mode
    )
    assert passages
    assert {(p.ticker, p.fiscal_year) for p in passages} == {("AAPL", 2024)}


async def test_hybrid_results_are_fused_ranked_and_citable(search):
    passages = await search("AWS operating income by segment", SearchFilters(tickers=("AMZN",)), limit=8)

    assert len(passages) == 8
    assert [p.score for p in passages] == sorted((p.score for p in passages), reverse=True)
    assert all(p.semantic_rank is not None or p.keyword_rank is not None for p in passages)
    assert any(p.semantic_rank is not None and p.keyword_rank is not None for p in passages)
    assert all(p.page_number >= 1 and p.section and p.source_url.startswith("https://www.sec.gov/") for p in passages)


async def test_tsquery_syntax_in_a_question_cannot_break_keyword_search(search):
    passages = await search("revenue' & !(china | :* taiwan)) <-> ", mode="keyword", limit=5)
    assert passages


async def test_question_with_no_searchable_words_returns_nothing_from_keyword_search(search):
    assert await search("?!", mode="keyword") == []
