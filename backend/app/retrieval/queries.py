import re

from pgvector.sqlalchemy import Vector
from sqlalchemy import Integer, Text, bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.retrieval.models import SearchFilters, SourcePassage

PASSAGE_COLUMNS = """
    c.id as chunk_id, c.document_id, c.chunk_index, d.ticker, d.company_name, d.filing_type, d.fiscal_year,
    d.filing_date, d.source_url, c.page as page_number, c.metadata->>'page_label' as page_label, c.section,
    c.metadata->>'subsection' as subsection, c.content
"""
FROM_AND_FILTERS = """
    from document_chunks c
    join source_documents d on d.id = c.document_id
    where (cardinality(:tickers) = 0 or d.ticker = any(:tickers))
      and (cardinality(:fiscal_years) = 0 or d.fiscal_year = any(:fiscal_years))
"""
FILTER_PARAMS = (bindparam("tickers", type_=ARRAY(Text)), bindparam("fiscal_years", type_=ARRAY(Integer)))

SEMANTIC_SQL = text(
    f"select {PASSAGE_COLUMNS} {FROM_AND_FILTERS} order by c.embedding <=> :embedding limit :limit"
).bindparams(*FILTER_PARAMS, bindparam("embedding", type_=Vector(settings.embedding_dimensions)))

# ts_rank with normalization 1 (divide by 1 + log of document length). Measured on
# evals/retrieval_questions.json against ts_rank_cd without normalization: keyword MRR 0.36 -> 0.57 and
# hybrid MRR 0.55 -> 0.69, because long chunks no longer win just by containing more question words.
KEYWORD_SQL = text(
    f"""
    select {PASSAGE_COLUMNS} {FROM_AND_FILTERS}
      and c.search_vector @@ to_tsquery('english', :tsquery)
    order by ts_rank(c.search_vector, to_tsquery('english', :tsquery), 1) desc, c.id
    limit :limit
    """
).bindparams(*FILTER_PARAMS)

# Enough to rank a filtered subset correctly: without iterative scans, an HNSW index returns its
# ef_search nearest rows first and the ticker/year filter is applied after, so a filtered search
# can come back short. pgvector 0.8+.
HNSW_SETTINGS = ("set local hnsw.iterative_scan = strict_order", "set local hnsw.ef_search = 100")

WORD = re.compile(r"[A-Za-z0-9]+")


def keyword_tsquery(question: str) -> str:
    """OR the question's words together; to_tsquery stems them and drops stopwords.

    Words are reduced to letters and digits first, so nothing from the question can be parsed as
    tsquery syntax. OR rather than AND: a natural-language question rarely has every word in one
    passage (AND found an answer for 2 of 20 eval questions), and ts_rank still ranks passages that
    match more words higher.
    """
    words = dict.fromkeys(word.lower() for word in WORD.findall(question))
    return " | ".join(words)


def _params(filters: SearchFilters, limit: int) -> dict:
    return {"tickers": list(filters.tickers), "fiscal_years": list(filters.fiscal_years), "limit": limit}


async def semantic_search(
    session: AsyncSession, embedding: list[float], filters: SearchFilters, limit: int
) -> list[SourcePassage]:
    for statement in HNSW_SETTINGS:
        await session.execute(text(statement))
    result = await session.execute(SEMANTIC_SQL, {**_params(filters, limit), "embedding": embedding})
    return [SourcePassage(**row._mapping, semantic_rank=rank) for rank, row in enumerate(result, start=1)]


async def keyword_search(
    session: AsyncSession, question: str, filters: SearchFilters, limit: int
) -> list[SourcePassage]:
    tsquery = keyword_tsquery(question)
    if not tsquery:
        return []
    result = await session.execute(KEYWORD_SQL, {**_params(filters, limit), "tsquery": tsquery})
    return [SourcePassage(**row._mapping, keyword_rank=rank) for rank, row in enumerate(result, start=1)]
