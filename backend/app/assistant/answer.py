from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field

import structlog
from pydantic_ai import Agent, AgentRunResultEvent
from pydantic_ai.exceptions import UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.messages import FunctionToolCallEvent, ModelMessage

from app.assistant.agent import USAGE_LIMITS
from app.assistant.citations import CitedAnswer, extract_citations
from app.assistant.deps import AgentDeps

logger = structlog.get_logger()

UNVERIFIED_NOTICE = (
    "I could not verify an answer against the filings, so I am not showing one. "
    "Try a narrower question, for example about one company and one fiscal year."
)


@dataclass(frozen=True)
class AnswerStatus:
    """Progress while the answer is not ready. The browser shows it; it is never saved."""

    text: str


@dataclass(frozen=True)
class AnswerDone:
    answer: CitedAnswer
    usage: dict
    grounded: bool = True
    # Violations of each draft the grounding check rejected, including drafts the model later fixed.
    rejected_drafts: list[list[str]] = field(default_factory=list)


async def run_answer(
    agent: Agent[AgentDeps, str], question: str, history: Sequence[ModelMessage], deps: AgentDeps
) -> AsyncIterator[AnswerStatus | AnswerDone]:
    """Run the agent to a grounded answer, reporting progress on the way.

    No answer text is released before the grounding check passes: the output validator on the agent checks
    every draft, sends violations back to the model, and fails the run after OUTPUT_RETRIES rejected drafts.
    A failed run yields the unverified notice instead of the draft.
    """
    model_name = agent.model.model_name if agent.model else None
    yield AnswerStatus("Reading the question")
    result = None
    try:
        async with agent.run_stream_events(
            question, deps=deps, message_history=list(history), usage_limits=USAGE_LIMITS
        ) as events:
            async for event in events:
                if isinstance(event, FunctionToolCallEvent):
                    yield AnswerStatus(describe_tool_call(event.part.tool_name, event.part.args_as_dict()))
                elif isinstance(event, AgentRunResultEvent):
                    result = event.result
    except (UnexpectedModelBehavior, UsageLimitExceeded) as exc:
        if not deps.grounding_failures:
            raise  # a real failure, not a rejected answer
        logger.warning(
            "answer_failed_grounding", rejected_drafts=len(deps.grounding_failures), error=type(exc).__name__
        )
        yield AnswerDone(
            answer=CitedAnswer(text=UNVERIFIED_NOTICE, citations=[], unknown_handles=[]),
            usage={"model": model_name, "grounding": grounding_usage(deps, grounded=False)},
            grounded=False,
            rejected_drafts=deps.grounding_failures,
        )
        return

    if result is None:
        raise RuntimeError("agent run ended without a result")
    usage = result.usage
    yield AnswerDone(
        answer=extract_citations(result.output, deps.passages),
        usage={
            "model": model_name,
            "requests": usage.requests,
            "tool_calls": usage.tool_calls,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "passages_shown": len(deps.passages),
            "grounding": grounding_usage(deps, grounded=True),
        },
        rejected_drafts=deps.grounding_failures,
    )


def grounding_usage(deps: AgentDeps, *, grounded: bool) -> dict:
    return {
        "grounded": grounded,
        "rejected_drafts": len(deps.grounding_failures),
        "violations": deps.grounding_failures,
    }


def describe_tool_call(tool_name: str, args: dict) -> str:
    if tool_name == "search_filings":
        scope = " ".join(
            part
            for part in (
                ", ".join(ticker.upper() for ticker in args.get("tickers") or []),
                ("fiscal " + ", ".join(map(str, args["fiscal_years"]))) if args.get("fiscal_years") else "",
            )
            if part
        )
        query = args.get("query", "")
        return f"Searching {scope}: {query}" if scope else f"Searching all filings: {query}"
    if tool_name == "read_surrounding_chunks":
        return "Reading the surrounding passages"
    return "Working"
