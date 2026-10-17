from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any
from uuid import UUID, uuid4

from asyncpg import PostgresError
from sqlalchemy import Row, delete, exists, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from smeshariki_ai.agent import Message, MessageRole
from smeshariki_ai.db.tables import dialogs, message_feedback, messages
from smeshariki_ai.dialogs import (
    DialogNotFoundError,
    DialogStoreUnavailableError,
    DialogSummary,
    DialogTranscript,
    HistoryStore,
    MessageNotFoundError,
    StoredMessage,
    dialog_title,
)


@contextmanager
def _unavailable_on_failure() -> Iterator[None]:
    try:
        yield
    except (SQLAlchemyError, PostgresError, OSError, TimeoutError) as error:
        raise DialogStoreUnavailableError from error


class PostgresHistoryStore(HistoryStore):
    """Dialogs and their user/assistant messages in PostgreSQL."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def create(self, owner_id: UUID) -> UUID:
        dialog_id = uuid4()
        with _unavailable_on_failure():
            async with self._engine.begin() as connection:
                await connection.execute(
                    insert(dialogs).values(id=dialog_id, user_id=owner_id)
                )
        return dialog_id

    async def get(self, owner_id: UUID, dialog_id: UUID) -> tuple[Message, ...]:
        with _unavailable_on_failure():
            async with self._engine.connect() as connection:
                await self._owned_title(connection, owner_id, dialog_id)
                rows = await self._messages(connection, dialog_id)
        return tuple(
            Message(role=MessageRole(row.role), content=row.content) for row in rows
        )

    async def append(
        self,
        dialog_id: UUID,
        messages_to_add: Sequence[Message],
    ) -> tuple[int, ...]:
        title = next(
            (
                dialog_title(item.content)
                for item in messages_to_add
                if item.role is MessageRole.USER
            ),
            None,
        )
        with _unavailable_on_failure():
            async with self._engine.begin() as connection:
                # The row lock serialises appends, so positions never collide.
                locked = await connection.execute(
                    select(dialogs.c.id)
                    .where(dialogs.c.id == dialog_id)
                    .with_for_update()
                )
                if locked.first() is None:
                    raise DialogNotFoundError(dialog_id)
                last_position = await connection.scalar(
                    select(func.coalesce(func.max(messages.c.position), -1)).where(
                        messages.c.dialog_id == dialog_id
                    )
                )
                ids: tuple[int, ...] = ()
                if messages_to_add:
                    inserted = await connection.execute(
                        insert(messages).returning(
                            messages.c.id, sort_by_parameter_order=True
                        ),
                        [
                            {
                                "dialog_id": dialog_id,
                                "position": last_position + offset,
                                "role": item.role.value,
                                "content": item.content,
                            }
                            for offset, item in enumerate(messages_to_add, start=1)
                        ],
                    )
                    ids = tuple(inserted.scalars().all())
                await connection.execute(
                    update(dialogs)
                    .where(dialogs.c.id == dialog_id)
                    .values(
                        updated_at=func.now(),
                        title=func.coalesce(dialogs.c.title, title),
                    )
                )
        return ids

    async def list_dialogs(
        self, owner_id: UUID, *, limit: int
    ) -> tuple[DialogSummary, ...]:
        statement = (
            select(
                dialogs.c.id,
                dialogs.c.title,
                dialogs.c.created_at,
                dialogs.c.updated_at,
            )
            .where(
                dialogs.c.user_id == owner_id,
                exists().where(messages.c.dialog_id == dialogs.c.id),
            )
            .order_by(dialogs.c.updated_at.desc(), dialogs.c.id)
            .limit(limit)
        )
        with _unavailable_on_failure():
            async with self._engine.connect() as connection:
                rows = (await connection.execute(statement)).all()
        return tuple(
            DialogSummary(
                dialog_id=row.id,
                title=row.title,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        )

    async def transcript(self, owner_id: UUID, dialog_id: UUID) -> DialogTranscript:
        with _unavailable_on_failure():
            async with self._engine.connect() as connection:
                title = await self._owned_title(connection, owner_id, dialog_id)
                rows = await self._messages(connection, dialog_id)
        return DialogTranscript(
            dialog_id=dialog_id,
            title=title,
            messages=tuple(
                StoredMessage(
                    id=row.id,
                    role=MessageRole(row.role),
                    content=row.content,
                    created_at=row.created_at,
                    feedback=row.feedback,
                )
                for row in rows
            ),
        )

    async def set_feedback(
        self,
        owner_id: UUID,
        dialog_id: UUID,
        message_id: int,
        score: int,
    ) -> None:
        statement = pg_insert(message_feedback).values(
            message_id=message_id, score=score
        )
        statement = statement.on_conflict_do_update(
            index_elements=[message_feedback.c.message_id],
            set_={"score": statement.excluded.score, "updated_at": func.now()},
        )
        with _unavailable_on_failure():
            async with self._engine.begin() as connection:
                await self._own_answer(connection, owner_id, dialog_id, message_id)
                await connection.execute(statement)

    async def clear_feedback(
        self, owner_id: UUID, dialog_id: UUID, message_id: int
    ) -> None:
        with _unavailable_on_failure():
            async with self._engine.begin() as connection:
                await self._own_answer(connection, owner_id, dialog_id, message_id)
                await connection.execute(
                    delete(message_feedback).where(
                        message_feedback.c.message_id == message_id
                    )
                )

    @staticmethod
    async def _own_answer(
        connection: AsyncConnection,
        owner_id: UUID,
        dialog_id: UUID,
        message_id: int,
    ) -> None:
        found = await connection.scalar(
            select(messages.c.id)
            .join(dialogs, dialogs.c.id == messages.c.dialog_id)
            .where(
                messages.c.id == message_id,
                messages.c.dialog_id == dialog_id,
                messages.c.role == MessageRole.ASSISTANT.value,
                dialogs.c.user_id == owner_id,
            )
        )
        if found is None:
            raise MessageNotFoundError(dialog_id, message_id)

    @staticmethod
    async def _owned_title(
        connection: AsyncConnection, owner_id: UUID, dialog_id: UUID
    ) -> str | None:
        row = (
            await connection.execute(
                select(dialogs.c.title).where(
                    dialogs.c.id == dialog_id, dialogs.c.user_id == owner_id
                )
            )
        ).first()
        if row is None:
            raise DialogNotFoundError(dialog_id)
        return row.title

    @staticmethod
    async def _messages(
        connection: AsyncConnection, dialog_id: UUID
    ) -> Sequence[Row[Any]]:
        result = await connection.execute(
            select(
                messages.c.id,
                messages.c.role,
                messages.c.content,
                messages.c.created_at,
                message_feedback.c.score.label("feedback"),
            )
            .outerjoin(message_feedback, message_feedback.c.message_id == messages.c.id)
            .where(messages.c.dialog_id == dialog_id)
            .order_by(messages.c.position)
        )
        return result.all()
