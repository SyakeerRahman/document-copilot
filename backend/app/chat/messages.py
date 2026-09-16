from pydantic_ai.ui.vercel_ai.request_types import TextUIPart, UIMessage

from app.database.models import ChatMessage

MAX_USER_MESSAGE_CHARS = 4000


class InvalidUserMessage(ValueError):
    pass


def extract_user_text(message: UIMessage) -> str:
    if message.role != "user":
        raise InvalidUserMessage("Only user messages can be submitted")
    text = "\n".join(part.text for part in message.parts if isinstance(part, TextUIPart)).strip()
    if not text:
        raise InvalidUserMessage("Message has no text")
    if len(text) > MAX_USER_MESSAGE_CHARS:
        raise InvalidUserMessage(f"Message is longer than {MAX_USER_MESSAGE_CHARS} characters")
    return text


def text_parts(text: str) -> list[dict]:
    # Stored in the AI SDK wire shape so history loads back into useChat unchanged.
    return [TextUIPart(text=text).model_dump(mode="json", by_alias=True, exclude_none=True)]


def to_ui_message(row: ChatMessage) -> UIMessage:
    return UIMessage(id=str(row.id), role=row.role, parts=row.parts)
