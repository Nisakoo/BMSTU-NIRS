from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from smeshariki_ai.agent import Message, MessageRole
from smeshariki_ai.dialogs import (
    DialogCursor,
    DialogNotFoundError,
    HistoryStore,
    InMemoryHistoryStore,
)

OWNER_ID = UUID(int=1)
OTHER_ID = UUID(int=2)
NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
PAIR = (
    Message(role=MessageRole.USER, content="question"),
    Message(role=MessageRole.ASSISTANT, content="answer"),
)


async def create_dialog(
    store: HistoryStore,
    owner_id: UUID = OWNER_ID,
    *,
    now: datetime = NOW,
    title: str | None = "title",
    dialog_id: UUID | None = None,
) -> UUID:
    dialog_id = dialog_id or uuid4()
    await store.create(dialog_id, owner_id, title, PAIR, now)
    return dialog_id


async def test_create_stores_owner_title_and_first_messages() -> None:
    store = InMemoryHistoryStore()

    dialog_id = await create_dialog(store, title="First question")

    assert await store.owner(dialog_id) == OWNER_ID
    assert await store.get(dialog_id) == PAIR
    transcript = await store.read(dialog_id)
    assert transcript.title == "First question"
    assert [(m.role, m.content, m.created_at) for m in transcript.messages] == [
        (MessageRole.USER, "question", NOW),
        (MessageRole.ASSISTANT, "answer", NOW),
    ]


async def test_create_with_existing_id_is_rejected() -> None:
    store = InMemoryHistoryStore()
    dialog_id = await create_dialog(store)

    with pytest.raises(ValueError):
        await create_dialog(store, dialog_id=dialog_id)

    assert await store.get(dialog_id) == PAIR


async def test_append_keeps_order_and_moves_updated_at_only() -> None:
    store = InMemoryHistoryStore()
    dialog_id = await create_dialog(store)
    later = NOW + timedelta(minutes=5)
    second = (
        Message(role=MessageRole.USER, content="next"),
        Message(role=MessageRole.ASSISTANT, content="next answer"),
    )

    await store.append(dialog_id, second, later)

    assert await store.get(dialog_id) == (*PAIR, *second)
    transcript = await store.read(dialog_id)
    assert [m.created_at for m in transcript.messages] == [NOW, NOW, later, later]
    (summary,) = await store.list(OWNER_ID, 10, None)
    assert (summary.created_at, summary.updated_at) == (NOW, later)
    assert transcript.title == "title"


async def test_get_returns_an_immutable_snapshot() -> None:
    store = InMemoryHistoryStore()
    dialog_id = await create_dialog(store)

    snapshot = await store.get(dialog_id)
    await store.append(dialog_id, PAIR, NOW)

    assert snapshot == PAIR
    assert await store.get(dialog_id) != snapshot


@pytest.mark.parametrize("operation", ["owner", "get", "read", "append", "delete"])
async def test_unknown_dialog_raises_domain_error(operation: str) -> None:
    store = InMemoryHistoryStore()
    missing_dialog_id = uuid4()

    with pytest.raises(DialogNotFoundError) as caught:
        if operation == "append":
            await store.append(missing_dialog_id, PAIR, NOW)
        else:
            await getattr(store, operation)(missing_dialog_id)

    assert caught.value.dialog_id == missing_dialog_id


async def test_list_returns_only_owner_dialogs_newest_activity_first() -> None:
    store = InMemoryHistoryStore()
    oldest = await create_dialog(store, now=NOW)
    newest = await create_dialog(store, now=NOW + timedelta(hours=2))
    middle = await create_dialog(store, now=NOW + timedelta(hours=1))
    await create_dialog(store, OTHER_ID, now=NOW + timedelta(hours=3))

    page = await store.list(OWNER_ID, 10, None)

    assert [item.dialog_id for item in page] == [newest, middle, oldest]


async def test_list_orders_equal_activity_by_dialog_id_descending() -> None:
    store = InMemoryHistoryStore()
    ids = [UUID(int=value) for value in (5, 9, 7)]
    for dialog_id in ids:
        await create_dialog(store, dialog_id=dialog_id)

    page = await store.list(OWNER_ID, 10, None)

    assert [item.dialog_id for item in page] == [UUID(int=9), UUID(int=7), UUID(int=5)]


async def test_list_follows_cursor_without_repeats_or_gaps() -> None:
    store = InMemoryHistoryStore()
    for index in range(7):
        await create_dialog(
            store, now=NOW + timedelta(minutes=index // 2), title=str(index)
        )

    seen: list[UUID] = []
    after: DialogCursor | None = None
    while True:
        page = await store.list(OWNER_ID, 3, after)
        if not page:
            break
        seen.extend(item.dialog_id for item in page)
        after = DialogCursor(
            updated_at=page[-1].updated_at, dialog_id=page[-1].dialog_id
        )

    assert len(seen) == len(set(seen)) == 7
    full = await store.list(OWNER_ID, 50, None)
    assert seen == [item.dialog_id for item in full]


async def test_delete_removes_dialog_from_every_view() -> None:
    store = InMemoryHistoryStore()
    dialog_id = await create_dialog(store)
    kept = await create_dialog(store)

    await store.delete(dialog_id)

    assert [item.dialog_id for item in await store.list(OWNER_ID, 10, None)] == [kept]
    with pytest.raises(DialogNotFoundError):
        await store.get(dialog_id)
    with pytest.raises(DialogNotFoundError):
        await store.delete(dialog_id)
