import json
from datetime import date
from uuid import UUID, uuid4

import pytest

from app.assistant.answer import AnswerDone
from app.assistant.citations import Citation, CitedAnswer
from app.chat.orchestrator import TURN_FAILED_TEXT, run_turn
from app.retrieval.models import SourcePassage


def passage() -> SourcePassage:
    return SourcePassage(
        chunk_id=uuid4(),
        document_id=uuid4(),
        chunk_index=12,
        ticker="AMZN",
        company_name="AMAZON.COM, INC.",
        filing_type="10-K",
        fiscal_year=2025,
        filing_date=date(2026, 2, 6),
        source_url="https://www.sec.gov/Archives/edgar/data/1018724/x.htm",
        page_number=29,
        page_label="27",
        section="Item 7. MD&A",
        subsection="Results of Operations",
        content="AWS | Operating income | $45,606",
    )


def parse(event: str) -> dict | str:
    assert event.startswith("data: ") and event.endswith("\n\n"), event
    payload = event.removeprefix("data: ").removesuffix("\n\n")
    return payload if payload == "[DONE]" else json.loads(payload)


def answer_with(*items):
    async def generate(_question: str):
        for item in items:
            if isinstance(item, Exception):
                raise item
            yield item

    return generate


@pytest.mark.anyio
async def test_streams_text_then_citations_then_persists_then_finishes():
    cited = passage()
    done = AnswerDone(
        answer=CitedAnswer(
            text="AWS earned $45,606 million [P1].", citations=[Citation("P1", cited)], unknown_handles=[]
        ),
        usage={"requests": 2},
    )
    order: list[str] = []
    saved: list[tuple[UUID, AnswerDone]] = []

    async def persist(assistant_id: UUID, result: AnswerDone) -> None:
        order.append("persist")
        saved.append((assistant_id, result))

    events = []
    generate = answer_with("AWS earned $45,606 million ", "[P1].", done)
    async for raw in run_turn(question="q", generate=generate, persist=persist):
        event = parse(raw)
        events.append(event)
        order.append(event if isinstance(event, str) else event["type"])

    assert order == [
        "start",
        "start-step",
        "text-start",
        "text-delta",
        "text-delta",
        "text-end",
        "data-citations",
        "persist",
        "finish-step",
        "finish",
        "[DONE]",
    ]
    message_id = UUID(events[0]["messageId"])
    assert saved == [(message_id, done)]
    citations = next(e for e in events if e != "[DONE]" and e["type"] == "data-citations")
    assert citations["id"] == f"{message_id}-citations"
    assert citations["data"][0] | {"chunkId": None} == {
        "handle": "P1",
        "chunkId": None,
        "ticker": "AMZN",
        "companyName": "AMAZON.COM, INC.",
        "filingType": "10-K",
        "fiscalYear": 2025,
        "filingDate": "2026-02-06",
        "pageNumber": 29,
        "pageLabel": "27",
        "section": "Item 7. MD&A",
        "subsection": "Results of Operations",
        "sourceUrl": "https://www.sec.gov/Archives/edgar/data/1018724/x.htm",
        "excerpt": "AWS | Operating income | $45,606",
    }


@pytest.mark.anyio
async def test_answer_without_citations_sends_no_citations_part():
    done = AnswerDone(answer=CitedAnswer(text="Not in the filings.", citations=[], unknown_handles=[]), usage={})

    async def persist(_id: UUID, _done: AnswerDone) -> None:
        return None

    generate = answer_with("Not in the filings.", done)
    events = [parse(raw) async for raw in run_turn(question="q", generate=generate, persist=persist)]
    types = [e if isinstance(e, str) else e["type"] for e in events]
    assert "data-citations" not in types
    assert "finish" in types


@pytest.mark.anyio
async def test_failed_save_sends_error_and_never_finish():
    done = AnswerDone(answer=CitedAnswer(text="partial", citations=[], unknown_handles=[]), usage={})

    async def persist(_id: UUID, _done: AnswerDone) -> None:
        raise RuntimeError("db down")

    events = [
        parse(raw) async for raw in run_turn(question="q", generate=answer_with("partial", done), persist=persist)
    ]
    types = [e if isinstance(e, str) else e["type"] for e in events]

    assert "finish" not in types
    assert events[-2] == {"type": "error", "errorText": TURN_FAILED_TEXT}
    assert events[-1] == "[DONE]"


@pytest.mark.anyio
async def test_failed_generation_saves_nothing():
    saved = []

    async def persist(_id: UUID, done: AnswerDone) -> None:
        saved.append(done)

    generate = answer_with("partial ", RuntimeError("model provider down"))
    events = [parse(raw) async for raw in run_turn(question="q", generate=generate, persist=persist)]

    assert saved == []
    assert events[-2]["type"] == "error"


@pytest.mark.anyio
async def test_generator_that_never_finishes_its_answer_is_an_error():
    async def persist(_id: UUID, _done: AnswerDone) -> None:
        raise AssertionError("must not persist")

    events = [parse(raw) async for raw in run_turn(question="q", generate=answer_with("text only"), persist=persist)]
    assert events[-2]["type"] == "error"
