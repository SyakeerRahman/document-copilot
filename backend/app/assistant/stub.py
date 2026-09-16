import asyncio
import re
from collections.abc import AsyncIterator

# Placeholder until the grounded PydanticAI agent lands (architecture step 11). It streams word
# by word so the browser, streaming, and persistence path is exercised for real before any model.
WORD_DELAY_SECONDS = 0.03


async def stub_reply(question: str) -> AsyncIterator[str]:
    text = (
        "This is a placeholder reply. The assistant is not connected to the filings yet, "
        f'so it cannot answer: "{question}"'
    )
    for token in re.findall(r"\S+\s*", text):
        await asyncio.sleep(WORD_DELAY_SECONDS)
        yield token
