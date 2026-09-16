from pathlib import Path

from pydantic_ai import Agent, RunContext
from pydantic_ai.models import Model
from pydantic_ai.usage import UsageLimits

from app.assistant.deps import AgentDeps
from app.retrieval.models import SearchFilters, SourcePassage

INSTRUCTIONS = Path(__file__).with_name("instructions.md").read_text(encoding="utf-8")

PASSAGES_PER_SEARCH = 6
MAX_NEIGHBORS = 2
# A turn that needs more than this is looping, not researching. Each request is one model call.
USAGE_LIMITS = UsageLimits(request_limit=8, tool_calls_limit=12)


def format_passage(handle: str, passage: SourcePassage) -> str:
    page = f"page {passage.page_label}" if passage.page_label else f"page {passage.page_number} of the document"
    location = passage.section + (f" > {passage.subsection}" if passage.subsection else "")
    return (
        f"[{handle}] {passage.company_name} ({passage.ticker}) Form {passage.filing_type}, "
        f"fiscal year {passage.fiscal_year}, {page}, {location}\n{passage.content}"
    )


def build_agent(model: Model) -> Agent[AgentDeps, str]:
    agent = Agent(model, deps_type=AgentDeps, output_type=str, instructions=INSTRUCTIONS)

    @agent.instructions
    def corpus_contents(ctx: RunContext[AgentDeps]) -> str:
        lines = [
            f"- {company.ticker}: {company.company_name}, fiscal years {', '.join(map(str, company.fiscal_years))}"
            for company in ctx.deps.corpus
        ]
        return "The corpus holds Form 10-K filings for these companies only:\n" + "\n".join(lines)

    @agent.tool
    async def search_filings(
        ctx: RunContext[AgentDeps],
        query: str,
        tickers: list[str] | None = None,
        fiscal_years: list[int] | None = None,
    ) -> str:
        """Search the 10-K filings and return the most relevant passages, each with a handle to cite.

        Args:
            query: What to look for, in plain words. Include the metric, segment, or topic.
            tickers: Limit the search to these tickers, for example ["AMZN"]. Pass it whenever a company is implied.
            fiscal_years: Limit the search to these fiscal years, for example [2024, 2025]. Pass it whenever a
                year is implied.
        """
        filters = SearchFilters(
            tickers=tuple(ticker.upper() for ticker in tickers or ()), fiscal_years=tuple(fiscal_years or ())
        )
        passages = await ctx.deps.search(query, filters)
        if not passages:
            return "No passages matched. Try different words, or check the tickers and fiscal years in the corpus."
        return "\n\n".join(format_passage(ctx.deps.passages.register(p), p) for p in passages)

    @agent.tool
    async def read_surrounding_chunks(ctx: RunContext[AgentDeps], handle: str, before: int = 1, after: int = 1) -> str:
        """Return the passages just before and after a passage in the same filing, for a table or sentence cut
        at a passage edge.

        Args:
            handle: A handle that a search in this turn returned, for example "P3".
            before: How many passages before it to return (0 to 2).
            after: How many passages after it to return (0 to 2).
        """
        passage = ctx.deps.passages.get(handle)
        if passage is None:
            return f"Unknown handle {handle}. Use a handle that a search in this turn returned."
        before = max(0, min(before, MAX_NEIGHBORS))
        after = max(0, min(after, MAX_NEIGHBORS))
        neighbors = await ctx.deps.chunks_in_range(
            passage.document_id, passage.chunk_index - before, passage.chunk_index + after
        )
        return "\n\n".join(format_passage(ctx.deps.passages.register(p), p) for p in neighbors)

    return agent
