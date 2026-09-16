from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import delete, insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import DocumentChunk, SourceDocument


async def embedding_column_dimensions(session: AsyncSession) -> int:
    # pgvector stores the declared dimensions as the column's type modifier.
    return await session.scalar(
        text(
            "select atttypmod from pg_attribute where attrelid = 'document_chunks'::regclass and attname = 'embedding'"
        )
    )


async def find_document(session: AsyncSession, accession_number: str) -> tuple[UUID, str | None] | None:
    """Return the stored document's id and the embedding model its chunks were embedded with."""
    row = (
        await session.execute(
            select(SourceDocument.id, SourceDocument.metadata_["embedding_model"].astext).where(
                SourceDocument.accession_number == accession_number
            )
        )
    ).first()
    return (row[0], row[1]) if row else None


async def delete_document(session: AsyncSession, document_id: UUID) -> None:
    # Chunks cascade. A chunk cited by a saved answer is protected by ON DELETE RESTRICT, so replacing
    # a document that analysts have already cited fails instead of breaking their citations.
    await session.execute(delete(SourceDocument).where(SourceDocument.id == document_id))


async def insert_document(session: AsyncSession, document: SourceDocument, chunks: list[dict]) -> None:
    session.add(document)
    await session.flush()
    await session.execute(insert(DocumentChunk), [{**chunk, "document_id": document.id} for chunk in chunks])


@dataclass(frozen=True)
class CorpusCompany:
    ticker: str
    company_name: str
    fiscal_years: tuple[int, ...]


async def corpus_overview(session: AsyncSession) -> list[CorpusCompany]:
    """What the corpus holds, so the agent knows which tickers and fiscal years a search can filter on."""
    rows = await session.execute(
        select(SourceDocument.ticker, SourceDocument.company_name, SourceDocument.fiscal_year).order_by(
            SourceDocument.ticker, SourceDocument.fiscal_year
        )
    )
    companies: dict[str, CorpusCompany] = {}
    for ticker, company_name, fiscal_year in rows:
        existing = companies.get(ticker)
        years = (*existing.fiscal_years, fiscal_year) if existing else (fiscal_year,)
        companies[ticker] = CorpusCompany(ticker, company_name, years)
    return list(companies.values())
