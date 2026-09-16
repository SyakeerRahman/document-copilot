"""Retrieval eval: does search put a passage that answers the question near the top?

    uv run python -m evals.retrieval             # verify the answer key, then measure every mode
    uv run python -m evals.retrieval --misses    # also list what hybrid search missed
    uv run python -m evals.retrieval --modes keyword   # no embedding calls

Each question names the one filing it is about and one or more acceptable passages, written as
substrings that must all appear in a chunk. Answers were located by searching chunk text directly,
never by running the retriever being measured. The key is checked against the database before
anything is measured, so a stale or loose key fails loudly instead of skewing the numbers.
"""

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.session import create_engine, create_sessionmaker
from app.retrieval.models import SearchFilters, SourcePassage
from app.retrieval.retriever import SearchMode, search_filings

QUESTIONS_PATH = Path(__file__).with_name("retrieval_questions.json")
TOP_K = 10
# More matching chunks than this means the substrings no longer pin down an answer.
MAX_MATCHES_PER_ALTERNATIVE = 6

MODES: tuple[SearchMode, ...] = ("semantic", "keyword", "hybrid")
SCOPES = ("ticker+year", "ticker", "all filings")


@dataclass(frozen=True)
class Question:
    id: str
    question: str
    ticker: str
    fiscal_year: int
    expect_any: list[list[str]]

    def is_answer(self, passage: SourcePassage) -> bool:
        if passage.ticker != self.ticker or passage.fiscal_year != self.fiscal_year:
            return False
        content = passage.content.lower()
        return any(all(part.lower() in content for part in alternative) for alternative in self.expect_any)

    def filters(self, scope: str) -> SearchFilters:
        if scope == "ticker+year":
            return SearchFilters(tickers=(self.ticker,), fiscal_years=(self.fiscal_year,))
        if scope == "ticker":
            return SearchFilters(tickers=(self.ticker,))
        return SearchFilters()


def load_questions() -> list[Question]:
    return [Question(**item) for item in json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))]


async def verify_answer_key(session: AsyncSession, questions: list[Question]) -> list[str]:
    problems = []
    for q in questions:
        for alternative in q.expect_any:
            conditions = " and ".join(f"c.content ilike :p{i}" for i in range(len(alternative)))
            params = {f"p{i}": f"%{part}%" for i, part in enumerate(alternative)}
            count = await session.scalar(
                text(
                    "select count(*) from document_chunks c join source_documents d on d.id = c.document_id "
                    f"where d.ticker = :ticker and d.fiscal_year = :year and {conditions}"
                ),
                {**params, "ticker": q.ticker, "year": q.fiscal_year},
            )
            if count == 0:
                problems.append(f"{q.id}: no chunk contains {alternative}")
            elif count > MAX_MATCHES_PER_ALTERNATIVE:
                problems.append(f"{q.id}: {count} chunks contain {alternative}; make it more specific")
    return problems


def hit_rate(ranks: list[int | None], k: int) -> float:
    return sum(1 for rank in ranks if rank is not None and rank <= k) / len(ranks)


def first_hit_rank(question: Question, passages: list[SourcePassage]) -> int | None:
    return next((rank for rank, p in enumerate(passages, start=1) if question.is_answer(p)), None)


async def run(show_misses: bool, modes: tuple[SearchMode, ...]) -> int:
    questions = load_questions()
    engine = create_engine()
    sessionmaker = create_sessionmaker(engine)
    try:
        async with sessionmaker() as session:
            problems = await verify_answer_key(session, questions)
        if problems:
            print("Answer key does not match the database:", *problems, sep="\n  ")
            return 1
        if set(modes) & {"semantic", "hybrid"}:
            async with sessionmaker() as session:
                stored = set(
                    await session.scalars(text("select distinct metadata->>'embedding_model' from source_documents"))
                )
            if stored != {settings.embedding_model}:
                # A question embedded by one model compared with passages embedded by another returns
                # confident nonsense, not an error.
                print(f"Stored vectors come from {sorted(stored)}, but EMBEDDING_MODEL is {settings.embedding_model}.")
                print("Re-run `uv run python -m ingest` first, or use --modes keyword.")
                return 1

        print(f"{len(questions)} questions, embedding model {settings.embedding_model}, top {TOP_K}\n")
        print(f"{'scope':12} {'mode':9} {'hit@1':>6} {'hit@3':>6} {'hit@10':>7} {'MRR':>6}")
        misses: list[str] = []
        async with httpx.AsyncClient() as http:
            for scope in SCOPES:
                for mode in modes:
                    ranks = []
                    for q in questions:
                        async with sessionmaker() as session:
                            passages = await search_filings(
                                session, http, q.question, q.filters(scope), limit=TOP_K, mode=mode
                            )
                        rank = first_hit_rank(q, passages)
                        ranks.append(rank)
                        if rank is None and scope == "ticker+year" and mode == "hybrid":
                            top = passages[0] if passages else None
                            where = f"p.{top.page_label} {top.section[:40]} > {top.subsection}" if top else "nothing"
                            misses.append(f"  {q.id}: top result was {where}")
                    mrr = sum(1 / r for r in ranks if r is not None) / len(ranks)
                    hits = " ".join(f"{hit_rate(ranks, k):6.2f}" for k in (1, 3))
                    print(f"{scope:12} {mode:9} {hits} {hit_rate(ranks, 10):7.2f} {mrr:6.2f}")
                print()
        if show_misses:
            print("Hybrid misses with ticker+year filters:", *(misses or ["  none"]), sep="\n")
    finally:
        await engine.dispose()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m evals.retrieval")
    parser.add_argument("--misses", action="store_true", help="list hybrid misses with ticker+year filters")
    parser.add_argument("--modes", nargs="+", choices=MODES, default=list(MODES), help="search modes to measure")
    args = parser.parse_args()
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    sys.exit(asyncio.run(run(args.misses, tuple(args.modes)), loop_factory=loop_factory))


if __name__ == "__main__":
    main()
