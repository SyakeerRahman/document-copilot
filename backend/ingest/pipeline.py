import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.database import documents
from app.database.models import SourceDocument
from app.embeddings import embed_texts, estimate_tokens
from ingest.chunking import Chunk, Document, build_document
from ingest.filing_html import Filing, parse_filing

EMBED_BATCH_SIZE = 32


@dataclass(frozen=True)
class ManifestEntry:
    ticker: str
    cik: str
    form: str
    filing_date: str
    report_date: str
    accession_number: str
    primary_document: str
    source_url: str
    local_path: str


@dataclass
class PreparedFiling:
    entry: ManifestEntry
    filing: Filing
    company_name: str
    fiscal_year: int
    document: Document


def prepare(entry: ManifestEntry, downloads_dir: Path) -> PreparedFiling:
    # Strict UTF-8: a mis-decoded filing would store and cite garbled text without complaint.
    html = (downloads_dir / entry.local_path).read_text(encoding="utf-8")
    filing = parse_filing(html)
    company_name = filing.registrant_name or entry.ticker
    fiscal_year = filing.fiscal_year or int(entry.report_date[:4])
    title = f"{company_name} Form {entry.form} for fiscal year {fiscal_year}"
    return PreparedFiling(entry, filing, company_name, fiscal_year, build_document(filing, title))


def embedding_input(prepared: PreparedFiling, chunk: Chunk) -> str:
    # The chunk alone often lacks its subject ("Total net sales | $416,161"), so the embedded text
    # names the company, year, and section. The stored chunk content stays verbatim.
    location = chunk.section + (f" > {chunk.subsection}" if chunk.subsection else "")
    return (
        f"{prepared.company_name} {prepared.entry.form}, fiscal year {prepared.fiscal_year}. {location}.\n\n"
        f"{chunk.content}"
    )


def chunk_row(prepared: PreparedFiling, chunk: Chunk, embedding: list[float]) -> dict:
    entry = prepared.entry
    return {
        "chunk_index": chunk.index,
        "section": chunk.section,
        "page": chunk.page_number,
        "content": chunk.content,
        "token_count": estimate_tokens(chunk.content),
        "embedding": embedding,
        "metadata_": {
            "ticker": entry.ticker,
            "company_name": prepared.company_name,
            "filing_type": entry.form,
            "filing_date": entry.filing_date,
            "fiscal_year": prepared.fiscal_year,
            "accession_number": entry.accession_number,
            "page_number": chunk.page_number,
            "page_label": chunk.page_label,
            "section": chunk.section,
            "subsection": chunk.subsection,
            "char_start": chunk.char_start,
            "char_end": chunk.char_end,
            "embedding_model": settings.embedding_model,
        },
    }


def document_row(prepared: PreparedFiling) -> SourceDocument:
    entry = prepared.entry
    return SourceDocument(
        accession_number=entry.accession_number,
        ticker=entry.ticker,
        company_name=prepared.company_name,
        filing_type=entry.form,
        filing_date=date.fromisoformat(entry.filing_date),
        fiscal_year=prepared.fiscal_year,
        source_url=entry.source_url,
        content_markdown=prepared.document.markdown,
        metadata_={
            "cik": entry.cik,
            "report_date": entry.report_date,
            "primary_document": entry.primary_document,
            "page_count": len(prepared.filing.pages),
            "chunk_count": len(prepared.document.chunks),
            "embedding_model": settings.embedding_model,
        },
    )


async def embed_chunks(http: httpx.AsyncClient, prepared: PreparedFiling) -> list[list[float]]:
    texts = [embedding_input(prepared, chunk) for chunk in prepared.document.chunks]
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        vectors.extend(await embed_texts(http, texts[start : start + EMBED_BATCH_SIZE]))
    return vectors


class IngestError(RuntimeError):
    pass


async def check_embedding_column(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        column = await documents.embedding_column_dimensions(session)
    if column != settings.embedding_dimensions:
        raise IngestError(
            f"document_chunks.embedding is vector({column}) but EMBEDDING_DIMENSIONS is "
            f"{settings.embedding_dimensions}. Run `uv run alembic upgrade head` or fix the setting."
        )


async def ingest_filing(
    http: httpx.AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    prepared: PreparedFiling,
    *,
    replace: bool,
) -> str:
    """Embed and store one filing in a single transaction. Returns a one-line outcome."""
    accession = prepared.entry.accession_number
    async with sessionmaker() as session:
        existing = await documents.find_document(session, accession)
    existing_id, existing_model = existing if existing else (None, None)
    # Vectors from another model are not comparable with this one, so a stale filing is always re-embedded.
    stale = existing_id is not None and existing_model != settings.embedding_model
    if existing_id and not (replace or stale):
        return "skipped (already ingested with this model; use --replace to re-ingest)"

    started = time.perf_counter()
    vectors = await embed_chunks(http, prepared)
    embedded_seconds = time.perf_counter() - started

    rows = [chunk_row(prepared, chunk, vector) for chunk, vector in zip(prepared.document.chunks, vectors, strict=True)]
    async with sessionmaker() as session:
        try:
            async with session.begin():
                if existing_id:
                    await documents.delete_document(session, existing_id)
                await documents.insert_document(session, document_row(prepared), rows)
        except IntegrityError as exc:
            raise IngestError(
                f"{accession}: cannot replace, saved answers cite its chunks ({exc.orig.__class__.__name__})"
            ) from exc

    verb = (
        f"replaced ({existing_model} -> {settings.embedding_model})"
        if stale
        else "replaced"
        if existing_id
        else "stored"
    )
    return f"{verb} {len(rows)} chunks (embedding {embedded_seconds:.1f}s)"
