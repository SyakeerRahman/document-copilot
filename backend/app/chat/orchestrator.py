from collections.abc import AsyncIterator, Awaitable, Callable
from uuid import UUID, uuid4

import structlog
from pydantic_ai.ui.vercel_ai.response_types import (
    ErrorChunk,
    FinishChunk,
    FinishStepChunk,
    StartChunk,
    StartStepChunk,
    TextDeltaChunk,
    TextEndChunk,
    TextStartChunk,
)

from app.chat.streaming import DONE, encode

logger = structlog.get_logger()

ReplyGenerator = Callable[[str], AsyncIterator[str]]
PersistTurn = Callable[[UUID, str], Awaitable[None]]

TURN_FAILED_TEXT = "The answer could not be completed and nothing was saved. Try again."


async def run_turn(*, question: str, generate: ReplyGenerator, persist: PersistTurn) -> AsyncIterator[str]:
    """Stream one assistant turn and save it.

    `finish` is only sent after the turn is saved, so the client never shows a completed answer
    that is missing from history. A client disconnect cancels the generator and saves nothing.
    """
    assistant_id = uuid4()
    text_id = f"{assistant_id}-text"

    yield encode(StartChunk(message_id=str(assistant_id)))
    yield encode(StartStepChunk())
    yield encode(TextStartChunk(id=text_id))

    answer: list[str] = []
    try:
        async for delta in generate(question):
            answer.append(delta)
            yield encode(TextDeltaChunk(id=text_id, delta=delta))
        yield encode(TextEndChunk(id=text_id))
        await persist(assistant_id, "".join(answer))
    except Exception:
        # Headers are already sent, so an HTTP status is no longer possible; the protocol's
        # error chunk is the only way to tell the client.
        logger.exception("chat_turn_failed", assistant_message_id=str(assistant_id))
        yield encode(ErrorChunk(error_text=TURN_FAILED_TEXT))
        yield DONE
        return

    yield encode(FinishStepChunk())
    yield encode(FinishChunk(finish_reason="stop"))
    yield DONE
