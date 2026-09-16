from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser
from app.database.models import ChatMessage, ChatThread, MessageCitation, Profile

TITLE_MAX_CHARS = 80


async def ensure_profile(session: AsyncSession, user: CurrentUser) -> None:
    # Profiles are created lazily on first write instead of by a trigger on auth.users,
    # so the email here always matches the verified token.
    statement = insert(Profile).values(id=user.id, email=user.email)
    await session.execute(statement.on_conflict_do_update(index_elements=[Profile.id], set_={"email": user.email}))


async def list_threads(session: AsyncSession, user_id: UUID) -> list[ChatThread]:
    result = await session.scalars(
        select(ChatThread).where(ChatThread.user_id == user_id).order_by(ChatThread.updated_at.desc())
    )
    return list(result)


async def create_thread(session: AsyncSession, user: CurrentUser) -> ChatThread:
    await ensure_profile(session, user)
    thread = ChatThread(user_id=user.id)
    session.add(thread)
    await session.commit()
    await session.refresh(thread)
    return thread


async def get_thread(session: AsyncSession, thread_id: UUID) -> ChatThread | None:
    return await session.get(ChatThread, thread_id)


async def list_messages(session: AsyncSession, thread_id: UUID) -> list[ChatMessage]:
    result = await session.scalars(
        select(ChatMessage).where(ChatMessage.thread_id == thread_id).order_by(ChatMessage.position)
    )
    return list(result)


async def append_turn(
    session: AsyncSession,
    *,
    thread_id: UUID,
    user_parts: list[dict],
    user_text: str,
    assistant_id: UUID,
    assistant_parts: list[dict],
    cited_chunk_ids: list[UUID],
    usage: dict | None,
) -> None:
    # Row lock serialises two turns on the same thread, so positions never collide.
    thread = await session.scalar(select(ChatThread).where(ChatThread.id == thread_id).with_for_update())
    if thread is None:
        raise LookupError(f"thread {thread_id} disappeared mid-turn")

    last_position = await session.scalar(
        select(func.coalesce(func.max(ChatMessage.position), -1)).where(ChatMessage.thread_id == thread_id)
    )
    session.add_all(
        [
            ChatMessage(thread_id=thread_id, position=last_position + 1, role="user", parts=user_parts),
            ChatMessage(
                id=assistant_id,
                thread_id=thread_id,
                position=last_position + 2,
                role="assistant",
                parts=assistant_parts,
                usage=usage,
            ),
        ]
    )
    await session.flush()  # the citation rows reference the assistant message
    session.add_all(
        MessageCitation(message_id=assistant_id, chunk_id=chunk_id, citation_index=index)
        for index, chunk_id in enumerate(cited_chunk_ids, start=1)
    )
    if thread.title is None:
        thread.title = user_text[:TITLE_MAX_CHARS]
    thread.updated_at = func.now()
    await session.commit()
