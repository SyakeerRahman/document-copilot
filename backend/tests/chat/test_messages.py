import pytest
from pydantic_ai.ui.vercel_ai.request_types import UIMessage

from app.chat.messages import MAX_USER_MESSAGE_CHARS, InvalidUserMessage, extract_user_text, text_parts


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
