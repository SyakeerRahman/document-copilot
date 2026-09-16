from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic_ai.ui.vercel_ai.request_types import UIMessage

from app.api.models import ApiModel
from app.api.threads import get_owned_thread
from app.assistant.stub import stub_reply
from app.auth.dependencies import CurrentUserDep
from app.chat.messages import InvalidUserMessage, extract_user_text, text_parts
from app.chat.orchestrator import run_turn
from app.chat.streaming import STREAM_HEADERS, STREAM_MEDIA_TYPE
from app.database import chats
from app.database.session import SessionDep

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatStreamRequest(ApiModel):
    thread_id: UUID
    # Only the new message. History is loaded from the database, never trusted from the client,
    # so a client cannot put words or citations in the assistant's mouth.
    message: UIMessage


@router.post("/stream")
async def stream_chat(
    body: ChatStreamRequest, user: CurrentUserDep, session: SessionDep, request: Request
) -> StreamingResponse:
    await get_owned_thread(session, body.thread_id, user)
    try:
        question = extract_user_text(body.message)
    except InvalidUserMessage as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    sessionmaker = request.app.state.sessionmaker

    async def persist(assistant_id: UUID, answer: str) -> None:
        # A fresh session: the request-scoped one is not guaranteed to outlive the response body.
        async with sessionmaker() as turn_session:
            await chats.append_turn(
                turn_session,
                thread_id=body.thread_id,
                user_parts=text_parts(question),
                user_text=question,
                assistant_id=assistant_id,
                assistant_parts=text_parts(answer),
            )

    return StreamingResponse(
        run_turn(question=question, generate=stub_reply, persist=persist),
        media_type=STREAM_MEDIA_TYPE,
        headers=STREAM_HEADERS,
    )
