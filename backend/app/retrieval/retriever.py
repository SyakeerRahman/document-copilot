from dataclasses import replace
from typing import Literal
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.embeddings import embed_query
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.models import SearchFilters, SourcePassage
from app.retrieval.queries import keyword_search, semantic_search

SearchMode = Literal["hybrid", "semantic", "keyword"]

# Each method contributes this many candidates to fusion. Fusion can only reorder what the two
# lists found, so this bounds recall, not the number of passages returned.
CANDIDATES_PER_METHOD = 30
DEFAULT_LIMIT = 8
NO_FILTERS = SearchFilters()


async def search_filings(
    session: AsyncSession,
    http: httpx.AsyncClient,
    question: str,
    filters: SearchFilters = NO_FILTERS,
    *,
    limit: int = DEFAULT_LIMIT,
    mode: SearchMode = "hybrid",
) -> list[SourcePassage]:
    semantic: list[SourcePassage] = []
    keyword: list[SourcePassage] = []
    if mode in ("hybrid", "semantic"):
        embedding = await embed_query(http, question)
        semantic = await semantic_search(session, embedding, filters, CANDIDATES_PER_METHOD)
    if mode in ("hybrid", "keyword"):
        keyword = await keyword_search(session, question, filters, CANDIDATES_PER_METHOD)

    passages: dict[UUID, SourcePassage] = {}
    for passage in semantic:
        passages[passage.chunk_id] = passage
    for passage in keyword:
        existing = passages.get(passage.chunk_id)
        passages[passage.chunk_id] = (
            replace(existing, keyword_rank=passage.keyword_rank) if existing is not None else passage
        )

    fused = reciprocal_rank_fusion([p.chunk_id for p in semantic], [p.chunk_id for p in keyword])
    return [replace(passages[chunk_id], score=score) for chunk_id, score in fused[:limit]]
