from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic_ai.ui.vercel_ai.request_types import UIMessage

from app.api.models import ApiModel
from app.api.threads import get_owned_thread
from app.assistant.answer import AnswerDone, run_answer
from app.assistant.runtime import database_deps
from app.auth.dependencies import CurrentUserDep
from app.chat.messages import InvalidUserMessage, assistant_parts, extract_user_text, text_parts, to_model_history
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

    history = to_model_history(await chats.list_messages(session, body.thread_id))
    sessionmaker = request.app.state.sessionmaker
    deps = await database_deps(sessionmaker, request.app.state.http)

    def generate(question: str):
        return run_answer(request.app.state.agent, question, history, deps)

    async def persist(assistant_id: UUID, done: AnswerDone) -> None:
        async with sessionmaker() as turn_session:
            await chats.append_turn(
                turn_session,
                thread_id=body.thread_id,
                user_parts=text_parts(question),
                user_text=question,
                assistant_id=assistant_id,
                assistant_parts=assistant_parts(assistant_id, done.answer, grounded=done.grounded),
                cited_chunk_ids=[citation.passage.chunk_id for citation in done.answer.citations],
                usage=done.usage,
            )

    return StreamingResponse(
        run_turn(question=question, generate=generate, persist=persist),
        media_type=STREAM_MEDIA_TYPE,
        headers=STREAM_HEADERS,
    )
