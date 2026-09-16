from uuid import UUID

from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.ui.vercel_ai.request_types import TextUIPart, UIMessage

from app.assistant.citations import CitedAnswer, strip_citation_markers
from app.database.models import ChatMessage

MAX_USER_MESSAGE_CHARS = 4000
# Enough for follow-ups like "and in 2023?" without sending a long thread to the model on every turn.
MAX_HISTORY_MESSAGES = 10
CITATIONS_PART_TYPE = "data-citations"


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


def citation_data(answer: CitedAnswer) -> list[dict]:
    """The citations as the browser receives them: everything needed to show and verify each source."""
    return [
        {
            "handle": citation.handle,
            "chunkId": str(citation.passage.chunk_id),
            "ticker": citation.passage.ticker,
            "companyName": citation.passage.company_name,
            "filingType": citation.passage.filing_type,
            "fiscalYear": citation.passage.fiscal_year,
            "filingDate": citation.passage.filing_date.isoformat(),
            "pageNumber": citation.passage.page_number,
            "pageLabel": citation.passage.page_label,
            "section": citation.passage.section,
            "subsection": citation.passage.subsection,
            "sourceUrl": citation.passage.source_url,
            "excerpt": citation.passage.content,
        }
        for citation in answer.citations
    ]


def citations_part_id(assistant_id: UUID) -> str:
    return f"{assistant_id}-citations"


def assistant_parts(assistant_id: UUID, answer: CitedAnswer) -> list[dict]:
    parts = text_parts(answer.text)
    if answer.citations:
        parts.append(
            {"type": CITATIONS_PART_TYPE, "id": citations_part_id(assistant_id), "data": citation_data(answer)}
        )
    return parts


def message_text(parts: list[dict]) -> str:
    return "".join(part["text"] for part in parts if part.get("type") == "text")


def to_model_history(rows: list[ChatMessage]) -> list[ModelMessage]:
    history: list[ModelMessage] = []
    for row in rows[-MAX_HISTORY_MESSAGES:]:
        text = message_text(row.parts)
        if row.role == "user":
            history.append(ModelRequest(parts=[UserPromptPart(content=text)]))
        else:
            history.append(ModelResponse(parts=[TextPart(content=strip_citation_markers(text))]))
    return history


def to_ui_message(row: ChatMessage) -> UIMessage:
    return UIMessage(id=str(row.id), role=row.role, parts=row.parts)
