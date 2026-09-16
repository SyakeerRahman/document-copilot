from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic_ai.ui.vercel_ai.request_types import UIMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.models import ApiModel
from app.auth.dependencies import CurrentUser, CurrentUserDep
from app.chat.messages import to_ui_message
from app.database import chats
from app.database.models import ChatThread
from app.database.session import SessionDep

router = APIRouter(prefix="/threads", tags=["threads"])


class ThreadOut(ApiModel):
    id: UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


async def get_owned_thread(session: AsyncSession, thread_id: UUID, user: CurrentUser) -> ChatThread:
    thread = await chats.get_thread(session, thread_id)
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    if thread.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Thread belongs to another user")
    return thread


@router.get("")
async def list_threads(user: CurrentUserDep, session: SessionDep) -> list[ThreadOut]:
    return [ThreadOut.model_validate(thread) for thread in await chats.list_threads(session, user.id)]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_thread(user: CurrentUserDep, session: SessionDep) -> ThreadOut:
    return ThreadOut.model_validate(await chats.create_thread(session, user))


@router.get("/{thread_id}")
async def get_thread(thread_id: UUID, user: CurrentUserDep, session: SessionDep) -> ThreadOut:
    return ThreadOut.model_validate(await get_owned_thread(session, thread_id, user))


# exclude_none: the AI SDK validates optional fields as absent-or-valid, so `"state": null` is rejected.
@router.get("/{thread_id}/messages", response_model_exclude_none=True)
async def list_messages(thread_id: UUID, user: CurrentUserDep, session: SessionDep) -> list[UIMessage]:
    await get_owned_thread(session, thread_id, user)
    return [to_ui_message(row) for row in await chats.list_messages(session, thread_id)]
