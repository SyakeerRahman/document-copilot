from dataclasses import dataclass
from datetime import date
from uuid import UUID


@dataclass(frozen=True)
class SearchFilters:
    # Empty means "any". The agent fills these when the question names a company or a year.
    tickers: tuple[str, ...] = ()
    fiscal_years: tuple[int, ...] = ()


@dataclass
class SourcePassage:
    chunk_id: UUID
    document_id: UUID
    chunk_index: int
    ticker: str
    company_name: str
    filing_type: str
    fiscal_year: int
    filing_date: date
    source_url: str
    page_number: int
    page_label: str | None
    section: str
    subsection: str | None
    content: str
    # 1-based position in each ranked list, None when that method did not return the passage.
    semantic_rank: int | None = None
    keyword_rank: int | None = None
    score: float = 0.0
