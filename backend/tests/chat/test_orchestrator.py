import json
from uuid import UUID

import pytest

from app.chat.orchestrator import TURN_FAILED_TEXT, run_turn


async def reply(tokens: list[str]):
    for token in tokens:
        yield token


def parse(events: list[str]) -> list[dict | str]:
    parsed: list[dict | str] = []
    for event in events:
        assert event.startswith("data: ") and event.endswith("\n\n"), event
        payload = event.removeprefix("data: ").removesuffix("\n\n")
        parsed.append(payload if payload == "[DONE]" else json.loads(payload))
    return parsed


async def collect(**kwargs) -> list[dict | str]:
    return parse([event async for event in run_turn(**kwargs)])


@pytest.mark.anyio
async def test_streams_text_then_persists_then_finishes():
    saved: list[tuple[UUID, str]] = []
    order: list[str] = []

    async def persist(assistant_id: UUID, answer: str) -> None:
        order.append("persist")
        saved.append((assistant_id, answer))

    events = []
    async for event in run_turn(question="q", generate=lambda _: reply(["Hello ", "world"]), persist=persist):
        payload = parse([event])[0]
        order.append(payload if isinstance(payload, str) else payload["type"])
        events.append(payload)

    assert order == [
        "start",
        "start-step",
        "text-start",
        "text-delta",
        "text-delta",
        "text-end",
        "persist",
        "finish-step",
        "finish",
        "[DONE]",
    ]
    message_id = events[0]["messageId"]
    assert saved == [(UUID(message_id), "Hello world")]
    assert [e["delta"] for e in events if e != "[DONE]" and e["type"] == "text-delta"] == ["Hello ", "world"]
    assert events[-2] == {"type": "finish", "finishReason": "stop"}


@pytest.mark.anyio
async def test_failed_save_sends_error_and_never_finish():
    async def persist(assistant_id: UUID, answer: str) -> None:
        raise RuntimeError("db down")

    events = await collect(question="q", generate=lambda _: reply(["partial"]), persist=persist)
    types = [e if isinstance(e, str) else e["type"] for e in events]

    assert "finish" not in types
    assert events[-2] == {"type": "error", "errorText": TURN_FAILED_TEXT}
    assert events[-1] == "[DONE]"


@pytest.mark.anyio
async def test_failed_generation_saves_nothing():
    saved = []

    async def failing(_: str):
        yield "partial "
        raise RuntimeError("model crashed")

    async def persist(assistant_id: UUID, answer: str) -> None:
        saved.append(answer)

    events = await collect(question="q", generate=failing, persist=persist)

    assert saved == []
    assert events[-2]["type"] == "error"
