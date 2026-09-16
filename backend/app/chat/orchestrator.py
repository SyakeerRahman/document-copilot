from collections.abc import AsyncIterator, Awaitable, Callable
from uuid import UUID, uuid4

import structlog
from pydantic_ai.ui.vercel_ai.response_types import (
    DataChunk,
    ErrorChunk,
    FinishChunk,
    FinishStepChunk,
    StartChunk,
    StartStepChunk,
    TextDeltaChunk,
    TextEndChunk,
    TextStartChunk,
)

from app.assistant.answer import AnswerDone
from app.chat.messages import CITATIONS_PART_TYPE, citation_data, citations_part_id
from app.chat.streaming import DONE, encode

logger = structlog.get_logger()

AnswerGenerator = Callable[[str], AsyncIterator[str | AnswerDone]]
PersistTurn = Callable[[UUID, AnswerDone], Awaitable[None]]

TURN_FAILED_TEXT = "The answer could not be completed and nothing was saved. Try again."


async def run_turn(*, question: str, generate: AnswerGenerator, persist: PersistTurn) -> AsyncIterator[str]:
    """Stream one assistant turn and save it.

    Text streams as the model writes it. Citations follow as one data part once the answer is complete.
    `finish` is only sent after the turn is saved, so the client never shows a completed answer that is
    missing from history. A client disconnect cancels the generator and saves nothing.
    """
    assistant_id = uuid4()
    text_id = f"{assistant_id}-text"

    yield encode(StartChunk(message_id=str(assistant_id)))
    yield encode(StartStepChunk())
    yield encode(TextStartChunk(id=text_id))

    done: AnswerDone | None = None
    try:
        async for item in generate(question):
            if isinstance(item, AnswerDone):
                done = item
            else:
                yield encode(TextDeltaChunk(id=text_id, delta=item))
        if done is None:
            raise RuntimeError("the answer generator ended without a final answer")
        yield encode(TextEndChunk(id=text_id))
        if done.answer.citations:
            yield encode(
                DataChunk(type=CITATIONS_PART_TYPE, id=citations_part_id(assistant_id), data=citation_data(done.answer))
            )
        await persist(assistant_id, done)
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
