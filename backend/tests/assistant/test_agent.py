"""The agent loop with a scripted model: no network, but the real tools, registry, and citation contract."""

import json
import re
from datetime import date
from uuid import UUID, uuid4

import pytest
from pydantic_ai.messages import ModelMessage, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from app.assistant.agent import build_agent
from app.assistant.answer import AnswerDone, stream_answer
from app.assistant.deps import AgentDeps
from app.database.documents import CorpusCompany
from app.retrieval.models import SearchFilters, SourcePassage

AWS_PASSAGE = SourcePassage(
    chunk_id=uuid4(),
    document_id=uuid4(),
    chunk_index=40,
    ticker="AMZN",
    company_name="AMAZON.COM, INC.",
    filing_type="10-K",
    fiscal_year=2025,
    filing_date=date(2026, 2, 6),
    source_url="https://www.sec.gov/x",
    page_number=29,
    page_label="27",
    section="Item 7. MD&A",
    subsection="Results of Operations",
    content="AWS | Operating income | $45,606",
)


class FakeCorpus:
    def __init__(self) -> None:
        self.searches: list[tuple[str, SearchFilters]] = []
        self.ranges: list[tuple[UUID, int, int]] = []

    async def search(self, query: str, filters: SearchFilters) -> list[SourcePassage]:
        self.searches.append((query, filters))
        return [AWS_PASSAGE]

    async def chunks_in_range(self, document_id: UUID, first: int, last: int) -> list[SourcePassage]:
        self.ranges.append((document_id, first, last))
        return [AWS_PASSAGE]

    def deps(self) -> AgentDeps:
        corpus = [CorpusCompany("AMZN", "AMAZON.COM, INC.", (2024, 2025))]
        return AgentDeps(search=self.search, chunks_in_range=self.chunks_in_range, corpus=corpus)


def tool_returns(messages: list[ModelMessage]) -> list[str]:
    return [part.content for message in messages for part in message.parts if isinstance(part, ToolReturnPart)]


def scripted_model(tool: str, args: dict, answer_template: str) -> FunctionModel:
    """First call: request one tool. Second call: answer, citing the first handle the tool returned."""

    async def stream(messages: list[ModelMessage], info: AgentInfo):
        returns = tool_returns(messages)
        if not returns:
            yield {0: DeltaToolCall(name=tool, json_args=json.dumps(args), tool_call_id="call-1")}
            return
        handle = re.search(r"\[(P\d+)\]", returns[-1]).group(1)
        for piece in answer_template.format(handle=handle).split("|"):
            yield piece

    return FunctionModel(stream_function=stream)


async def run(model: FunctionModel, deps: AgentDeps) -> tuple[str, AnswerDone]:
    streamed, done = [], None
    async for item in stream_answer(build_agent(model), "What was AWS operating income in 2025?", [], deps):
        if isinstance(item, AnswerDone):
            done = item
        else:
            streamed.append(item)
    return "".join(streamed), done


@pytest.mark.anyio
async def test_search_answer_and_citation_resolve_to_the_passage_the_tool_returned():
    corpus = FakeCorpus()
    model = scripted_model(
        "search_filings",
        {"query": "AWS operating income", "tickers": ["amzn"], "fiscal_years": [2025]},
        "AWS operating income was $45,606 million |[{handle}].",
    )

    streamed, done = await run(model, corpus.deps())

    assert corpus.searches == [("AWS operating income", SearchFilters(tickers=("AMZN",), fiscal_years=(2025,)))]
    assert streamed == done.answer.text == "AWS operating income was $45,606 million [P1]."
    assert [(c.handle, c.passage) for c in done.answer.citations] == [("P1", AWS_PASSAGE)]
    assert done.answer.unknown_handles == []
    assert done.usage["requests"] == 2
    assert done.usage["tool_calls"] == 1
    assert done.usage["passages_shown"] == 1


@pytest.mark.anyio
async def test_citing_a_handle_no_tool_returned_is_reported_as_unknown():
    corpus = FakeCorpus()
    model = scripted_model("search_filings", {"query": "AWS"}, "AWS earned $1 [{handle}] and 99% margin [P9].")

    _, done = await run(model, corpus.deps())

    assert [c.handle for c in done.answer.citations] == ["P1"]
    assert done.answer.unknown_handles == ["P9"]


@pytest.mark.anyio
async def test_tool_result_shows_the_model_where_each_passage_comes_from():
    corpus = FakeCorpus()
    shown: list[str] = []

    async def stream(messages: list[ModelMessage], info: AgentInfo):
        returns = tool_returns(messages)
        if not returns:
            yield {0: DeltaToolCall(name="search_filings", json_args='{"query": "AWS"}', tool_call_id="c1")}
            return
        shown.extend(returns)
        yield "done"

    await run(FunctionModel(stream_function=stream), corpus.deps())

    expected = (
        "[P1] AMAZON.COM, INC. (AMZN) Form 10-K, fiscal year 2025, page 27, "
        "Item 7. MD&A > Results of Operations\nAWS | Operating income | $45,606"
    )
    assert shown == [expected]


@pytest.mark.anyio
async def test_surrounding_chunks_clamp_the_range_and_reject_unknown_handles():
    corpus = FakeCorpus()
    deps = corpus.deps()
    deps.passages.register(AWS_PASSAGE)
    outputs: list[str] = []

    async def stream(messages: list[ModelMessage], info: AgentInfo):
        returns = tool_returns(messages)
        if not returns:
            yield {
                0: DeltaToolCall(
                    name="read_surrounding_chunks",
                    json_args='{"handle": "P1", "before": 9, "after": 1}',
                    tool_call_id="a",
                ),
                1: DeltaToolCall(name="read_surrounding_chunks", json_args='{"handle": "P42"}', tool_call_id="b"),
            }
            return
        outputs.extend(returns)
        yield "done"

    await run(FunctionModel(stream_function=stream), deps)

    assert corpus.ranges == [(AWS_PASSAGE.document_id, 38, 41)]
    assert "Unknown handle P42" in outputs[1]


def test_instructions_include_the_product_contract():
    agent = build_agent(FunctionModel(stream_function=lambda *_: None))
    instructions = " ".join(str(i) for i in agent._instructions)
    for rule in ("Cite only handles that a tool returned", "investment advice", "not contain enough evidence"):
        assert rule in instructions


@pytest.mark.anyio
async def test_text_written_before_a_tool_call_never_reaches_the_answer_stream():
    corpus = FakeCorpus()

    async def stream(messages: list[ModelMessage], info: AgentInfo):
        if not tool_returns(messages):
            yield "Let me search the filings first. "
            yield {1: DeltaToolCall(name="search_filings", json_args='{"query": "AWS"}', tool_call_id="c1")}
            return
        yield "AWS earned $45,606 million [P1]."

    streamed, done = await run(FunctionModel(stream_function=stream), corpus.deps())

    assert streamed == done.answer.text == "AWS earned $45,606 million [P1]."


@pytest.mark.anyio
async def test_long_answer_streams_in_pieces_after_the_holdback():
    corpus = FakeCorpus()
    sentence = "AWS operating income grew because sales grew [P1]. "

    async def stream(messages: list[ModelMessage], info: AgentInfo):
        if not tool_returns(messages):
            yield {0: DeltaToolCall(name="search_filings", json_args='{"query": "AWS"}', tool_call_id="c1")}
            return
        for _ in range(20):
            yield sentence

    pieces: list[str] = []
    async for item in stream_answer(build_agent(FunctionModel(stream_function=stream)), "q", [], corpus.deps()):
        if not isinstance(item, AnswerDone):
            pieces.append(item)

    assert "".join(pieces) == sentence * 20
    assert len(pieces) > 10  # held back once, then one piece per model delta
    assert len(pieces[0]) >= 300
