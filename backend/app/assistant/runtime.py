from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.assistant.deps import AgentDeps
from app.database import documents
from app.retrieval import queries
from app.retrieval.models import SearchFilters, SourcePassage
from app.retrieval.retriever import search_filings


async def database_deps(sessionmaker: async_sessionmaker[AsyncSession], http: httpx.AsyncClient) -> AgentDeps:
    """Agent dependencies backed by Postgres and OpenRouter, for the API, the eval, and integration tests.

    Each tool call opens its own short session: the model may call tools in parallel, and a request-scoped
    session is not guaranteed to outlive a streamed response.
    """

    async def search(query: str, filters: SearchFilters) -> list[SourcePassage]:
        async with sessionmaker() as session:
            return await search_filings(session, http, query, filters)

    async def chunks_in_range(document_id: UUID, first_index: int, last_index: int) -> list[SourcePassage]:
        async with sessionmaker() as session:
            return await queries.chunks_in_range(session, document_id, first_index, last_index)

    async with sessionmaker() as session:
        corpus = await documents.corpus_overview(session)
    return AgentDeps(search=search, chunks_in_range=chunks_in_range, corpus=corpus)
