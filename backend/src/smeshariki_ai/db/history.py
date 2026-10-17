from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime
from uuid import UUID

from asyncpg import PostgresError
from sqlalchemy import (
    DateTime,
    Uuid,
    delete,
    func,
    insert,
    literal,
    select,
    tuple_,
    update,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from smeshariki_ai.agent import Message, MessageRole
from smeshariki_ai.db.tables import dialogs, messages
from smeshariki_ai.dialogs import (
    DialogCursor,
    DialogNotFoundError,
    DialogSummary,
    DialogTranscript,
    HistoryStore,
    HistoryUnavailableError,
    StoredMessage,
)


@contextmanager
def _unavailable_on_failure() -> Iterator[None]:
    try:
        yield
    except (SQLAlchemyError, PostgresError, OSError, TimeoutError) as error:
        # The cause is chained, but its text (SQL, parameters) is never logged.
        raise HistoryUnavailableError from error


class PostgresHistoryStore(HistoryStore):
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def create(
        self,
        dialog_id: UUID,
        owner_id: UUID,
        title: str | None,
        messages_: Sequence[Message],
        now: datetime,
    ) -> None:
        with _unavailable_on_failure():
            async with self._engine.begin() as connection:
                await connection.execute(
                    insert(dialogs).values(
                        id=dialog_id,
                        user_id=owner_id,
                        title=title,
                        created_at=now,
                        updated_at=now,
                    )
                )
                await _insert_messages(connection, dialog_id, messages_, 0, now)

    async def owner(self, dialog_id: UUID) -> UUID:
        statement = select(dialogs.c.user_id).where(dialogs.c.id == dialog_id)
        with _unavailable_on_failure():
            async with self._engine.connect() as connection:
                owner_id = (await connection.execute(statement)).scalar_one_or_none()
        if owner_id is None:
            raise DialogNotFoundError(dialog_id)
        return owner_id

    async def get(self, dialog_id: UUID) -> tuple[Message, ...]:
        transcript = await self.read(dialog_id)
        return tuple(
            Message(role=message.role, content=message.content)
            for message in transcript.messages
        )

    async def read(self, dialog_id: UUID) -> DialogTranscript:
        dialog = select(dialogs.c.title).where(dialogs.c.id == dialog_id)
        stored = (
            select(messages.c.role, messages.c.content, messages.c.created_at)
            .where(messages.c.dialog_id == dialog_id)
            .order_by(messages.c.position)
        )
        with _unavailable_on_failure():
            async with self._engine.connect() as connection:
                row = (await connection.execute(dialog)).first()
                if row is None:
                    raise DialogNotFoundError(dialog_id)
                rows = (await connection.execute(stored)).all()
        return DialogTranscript(
            title=row.title,
            messages=tuple(
                StoredMessage(
                    role=MessageRole(item.role),
                    content=item.content,
                    created_at=item.created_at,
                )
                for item in rows
            ),
        )

    async def append(
        self,
        dialog_id: UUID,
        messages_: Sequence[Message],
        now: datetime,
    ) -> None:
        lock = select(dialogs.c.id).where(dialogs.c.id == dialog_id).with_for_update()
        next_position = select(func.coalesce(func.max(messages.c.position), -1) + 1)
        next_position = next_position.where(messages.c.dialog_id == dialog_id)
        touch = update(dialogs).where(dialogs.c.id == dialog_id).values(updated_at=now)
        with _unavailable_on_failure():
            async with self._engine.begin() as connection:
                # The row lock serializes concurrent appends to one dialog.
                if (await connection.execute(lock)).first() is None:
                    raise DialogNotFoundError(dialog_id)
                position = (await connection.execute(next_position)).scalar_one()
                await _insert_messages(connection, dialog_id, messages_, position, now)
                await connection.execute(touch)

    async def list(
        self,
        owner_id: UUID,
        limit: int,
        after: DialogCursor | None,
    ) -> tuple[DialogSummary, ...]:
        statement = select(
            dialogs.c.id,
            dialogs.c.title,
            dialogs.c.created_at,
            dialogs.c.updated_at,
        ).where(dialogs.c.user_id == owner_id)
        if after is not None:
            statement = statement.where(
                tuple_(dialogs.c.updated_at, dialogs.c.id)
                < tuple_(
                    literal(after.updated_at, DateTime(timezone=True)),
                    literal(after.dialog_id, Uuid),
                )
            )
        statement = statement.order_by(
            dialogs.c.updated_at.desc(), dialogs.c.id.desc()
        ).limit(limit)
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

    async def delete(self, dialog_id: UUID) -> None:
        statement = (
            delete(dialogs).where(dialogs.c.id == dialog_id).returning(dialogs.c.id)
        )
        with _unavailable_on_failure():
            async with self._engine.begin() as connection:
                deleted = (await connection.execute(statement)).first()
        if deleted is None:
            raise DialogNotFoundError(dialog_id)


async def _insert_messages(
    connection: AsyncConnection,
    dialog_id: UUID,
    items: Sequence[Message],
    first_position: int,
    now: datetime,
) -> None:
    if not items:
        return
    await connection.execute(
        insert(messages),
        [
            {
                "dialog_id": dialog_id,
                "position": first_position + offset,
                "role": item.role.value,
                "content": item.content,
                "created_at": now,
            }
            for offset, item in enumerate(items)
        ],
    )
