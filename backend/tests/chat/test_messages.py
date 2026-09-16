from uuid import uuid4

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse
from pydantic_ai.ui.vercel_ai.request_types import UIMessage

from app.chat.messages import (
    MAX_HISTORY_MESSAGES,
    MAX_USER_MESSAGE_CHARS,
    InvalidUserMessage,
    extract_user_text,
    text_parts,
    to_model_history,
    to_ui_message,
)
from app.database.models import ChatMessage


def message(role: str, *parts: dict) -> UIMessage:
    return UIMessage.model_validate({"id": "m1", "role": role, "parts": list(parts)})


def test_joins_and_trims_text_parts():
    msg = message("user", {"type": "text", "text": "  What changed "}, {"type": "text", "text": "in 2024?  "})
    assert extract_user_text(msg) == "What changed \nin 2024?"


@pytest.mark.parametrize(
    ("msg", "reason"),
    [
        (message("assistant", {"type": "text", "text": "hi"}), "Only user messages"),
        (message("user", {"type": "text", "text": "   "}), "no text"),
        (message("user", {"type": "text", "text": "x" * (MAX_USER_MESSAGE_CHARS + 1)}), "longer than"),
    ],
)
def test_rejects_invalid_user_messages(msg, reason):
    with pytest.raises(InvalidUserMessage, match=reason):
        extract_user_text(msg)


def test_stored_parts_round_trip_as_ui_message():
    parts = text_parts("hello")
    assert parts == [{"type": "text", "text": "hello"}]
    assert message("assistant", *parts).parts[0].text == "hello"


def test_stored_citations_part_loads_back_as_a_data_part():
    row = ChatMessage(
        id=uuid4(),
        role="assistant",
        parts=[{"type": "text", "text": "a [P1]"}, {"type": "data-citations", "id": "x", "data": [{"handle": "P1"}]}],
    )
    ui = to_ui_message(row)
    assert ui.parts[1].type == "data-citations"
    assert ui.parts[1].data == [{"handle": "P1"}]


def test_history_keeps_roles_strips_old_handles_and_ignores_citation_parts():
    rows = [
        ChatMessage(role="user", parts=text_parts("AWS income in 2025?")),
        ChatMessage(
            role="assistant",
            parts=[*text_parts("It was $45,606 million [P2]."), {"type": "data-citations", "id": "c", "data": []}],
        ),
    ]
    history = to_model_history(rows)

    assert isinstance(history[0], ModelRequest)
    assert history[0].parts[0].content == "AWS income in 2025?"
    assert isinstance(history[1], ModelResponse)
    assert history[1].parts[0].content == "It was $45,606 million."


def test_history_is_capped_to_the_most_recent_messages():
    rows = [ChatMessage(role="user", parts=text_parts(f"q{i}")) for i in range(MAX_HISTORY_MESSAGES + 5)]
    history = to_model_history(rows)
    assert len(history) == MAX_HISTORY_MESSAGES
    assert history[0].parts[0].content == "q5"


def test_unverified_turn_is_left_out_of_history_but_the_question_stays():
    from app.assistant.citations import CitedAnswer
    from app.chat.messages import assistant_parts

    assistant_id = uuid4()
    notice_parts = assistant_parts(
        assistant_id, CitedAnswer(text="I could not verify...", citations=[], unknown_handles=[]), grounded=False
    )
    assert notice_parts[1] == {"type": "data-unverified", "id": f"{assistant_id}-unverified", "data": {}}

    rows = [
        ChatMessage(role="user", parts=text_parts("What was AWS margin?")),
        ChatMessage(role="assistant", parts=notice_parts),
        ChatMessage(role="user", parts=text_parts("What was AWS operating income in 2025?")),
    ]
    history = to_model_history(rows)
    assert [type(m).__name__ for m in history] == ["ModelRequest", "ModelRequest"]
