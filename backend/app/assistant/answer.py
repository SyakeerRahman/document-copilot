from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass

import structlog
from pydantic_ai import Agent, AgentRunResultEvent
from pydantic_ai.messages import (
    FunctionToolResultEvent,
    ModelMessage,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ToolCallPart,
)

from app.assistant.agent import USAGE_LIMITS
from app.assistant.citations import CitedAnswer, extract_citations
from app.assistant.deps import AgentDeps

logger = structlog.get_logger()

# Text a model writes before a tool call ("Let me search...") is short. Holding back this much of each model
# response before streaming it keeps that preamble out of the answer at the cost of a brief first-word delay.
# PydanticAI's FinalResultEvent cannot decide this: it fires when text starts, even if a tool call follows.
HOLDBACK_CHARS = 300


@dataclass(frozen=True)
class AnswerDone:
    answer: CitedAnswer
    usage: dict


async def stream_answer(
    agent: Agent[AgentDeps, str], question: str, history: Sequence[ModelMessage], deps: AgentDeps
) -> AsyncIterator[str | AnswerDone]:
    """Yield the answer text as the model writes it, then one AnswerDone with the citations resolved.

    The answer and its citations come from the run's final output. Streamed text matches it unless a model
    writes more than HOLDBACK_CHARS before a tool call; that case is logged.
    """
    streamed: list[str] = []
    pending: list[str] = []  # text of the current model response not yet sent
    live = False  # the current response has passed the holdback and streams directly
    result = None

    async with agent.run_stream_events(
        question, deps=deps, message_history=list(history), usage_limits=USAGE_LIMITS
    ) as events:
        async for event in events:
            delta = _text_delta(event)
            if delta:
                if live:
                    streamed.append(delta)
                    yield delta
                    continue
                pending.append(delta)
                if sum(map(len, pending)) >= HOLDBACK_CHARS:
                    live = True
                    released = "".join(pending)
                    pending.clear()
                    streamed.append(released)
                    yield released
            elif isinstance(event, PartStartEvent) and isinstance(event.part, ToolCallPart):
                if pending:
                    logger.info("discarded_text_before_tool_call", chars=sum(map(len, pending)))
                    pending.clear()
            elif isinstance(event, FunctionToolResultEvent):
                live = False  # the next model response gets its own holdback
            elif isinstance(event, AgentRunResultEvent):
                result = event.result

    if result is None:
        raise RuntimeError("agent run ended without a result")
    if pending:
        tail = "".join(pending)
        streamed.append(tail)
        yield tail
    if "".join(streamed) != result.output:
        logger.warning("streamed_text_differs_from_output", streamed_chars=len("".join(streamed)))

    usage = result.usage
    yield AnswerDone(
        answer=extract_citations(result.output, deps.passages),
        usage={
            "model": agent.model.model_name if agent.model else None,
            "requests": usage.requests,
            "tool_calls": usage.tool_calls,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "passages_shown": len(deps.passages),
        },
    )


def _text_delta(event: object) -> str | None:
    if isinstance(event, PartStartEvent) and isinstance(event.part, TextPart):
        return event.part.content or None
    if isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
        return event.delta.content_delta or None
    return None
