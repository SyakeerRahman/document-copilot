"""The real agent: CHAT_MODEL through OpenRouter, real hybrid search over the ingested corpus.

Needs local Supabase, the ingested corpus, and a real OPENROUTER_API_KEY. Costs a fraction of a cent.
"""

import httpx
import pytest

from app.assistant.agent import build_agent
from app.assistant.answer import AnswerDone, run_answer
from app.assistant.model import build_chat_model
from app.assistant.runtime import database_deps
from app.config import settings
from app.database.session import create_engine, create_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


async def test_answer_cites_only_retrieved_passages_from_the_right_filing():
    engine = create_engine()
    sessionmaker = create_sessionmaker(engine)
    try:
        async with httpx.AsyncClient() as http:
            deps = await database_deps(sessionmaker, http)
            agent = build_agent(build_chat_model(settings))

            done = None
            async for item in run_answer(
                agent, "How much did Apple's Services net sales grow in fiscal 2025?", [], deps
            ):
                if isinstance(item, AnswerDone):
                    done = item
    finally:
        await engine.dispose()

    assert done is not None
    assert done.answer.citations, done.answer.text
    assert done.answer.unknown_handles == []
    assert ("AAPL", 2025) in {(c.passage.ticker, c.passage.fiscal_year) for c in done.answer.citations}
    assert done.grounded, done.rejected_drafts
