from uuid import UUID, uuid4

import pytest

from smeshariki_ai.agent import Message, MessageRole
from smeshariki_ai.dialogs import DialogNotFoundError, InMemoryHistoryStore


@pytest.mark.asyncio
async def test_create_returns_unique_uuid4_with_empty_history() -> None:
    store = InMemoryHistoryStore()

    first_dialog_id = await store.create()
    second_dialog_id = await store.create()

    assert isinstance(first_dialog_id, UUID)
    assert first_dialog_id.version == 4
    assert second_dialog_id.version == 4
    assert first_dialog_id != second_dialog_id
    assert await store.get(first_dialog_id) == ()
    assert await store.get(second_dialog_id) == ()


@pytest.mark.asyncio
async def test_append_is_atomic_ordered_and_isolated_between_dialogs() -> None:
    store = InMemoryHistoryStore()
    first_dialog_id = await store.create()
    second_dialog_id = await store.create()
    messages = (
        Message(role=MessageRole.USER, content="question"),
        Message(role=MessageRole.ASSISTANT, content="answer"),
    )

    await store.append(first_dialog_id, messages)

    assert await store.get(first_dialog_id) == messages
    assert await store.get(second_dialog_id) == ()


@pytest.mark.asyncio
async def test_get_returns_an_immutable_snapshot() -> None:
    store = InMemoryHistoryStore()
    dialog_id = await store.create()
    first_message = Message(role=MessageRole.USER, content="first")
    await store.append(dialog_id, (first_message,))

    snapshot = await store.get(dialog_id)
    await store.append(
        dialog_id,
        (Message(role=MessageRole.ASSISTANT, content="second"),),
    )

    assert snapshot == (first_message,)
    assert await store.get(dialog_id) != snapshot


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["get", "append"])
async def test_unknown_dialog_raises_domain_error(operation: str) -> None:
    store = InMemoryHistoryStore()
    missing_dialog_id = uuid4()

    with pytest.raises(DialogNotFoundError) as caught:
        if operation == "get":
            await store.get(missing_dialog_id)
        else:
            await store.append(missing_dialog_id, ())

    assert caught.value.dialog_id == missing_dialog_id
