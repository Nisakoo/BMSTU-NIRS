from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from smeshariki_ai.agent import Message, MessageRole
from smeshariki_ai.dialogs import (
    DialogNotFoundError,
    InMemoryHistoryStore,
    MessageNotFoundError,
    dialog_title,
)

OWNER = UUID(int=1)
STRANGER = UUID(int=2)
START = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


class StepClock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


def pair(question: str, answer: str = "answer") -> tuple[Message, Message]:
    return (
        Message(role=MessageRole.USER, content=question),
        Message(role=MessageRole.ASSISTANT, content=answer),
    )


@pytest.mark.asyncio
async def test_create_returns_unique_uuid4_with_empty_history() -> None:
    store = InMemoryHistoryStore()

    first_dialog_id = await store.create(OWNER)
    second_dialog_id = await store.create(OWNER)

    assert isinstance(first_dialog_id, UUID)
    assert first_dialog_id.version == 4
    assert second_dialog_id.version == 4
    assert first_dialog_id != second_dialog_id
    assert await store.get(OWNER, first_dialog_id) == ()
    assert await store.get(OWNER, second_dialog_id) == ()


@pytest.mark.asyncio
async def test_append_is_atomic_ordered_and_isolated_between_dialogs() -> None:
    store = InMemoryHistoryStore()
    first_dialog_id = await store.create(OWNER)
    second_dialog_id = await store.create(OWNER)
    messages = pair("question")

    await store.append(first_dialog_id, messages)

    assert await store.get(OWNER, first_dialog_id) == messages
    assert await store.get(OWNER, second_dialog_id) == ()


@pytest.mark.asyncio
async def test_get_returns_an_immutable_snapshot() -> None:
    store = InMemoryHistoryStore()
    dialog_id = await store.create(OWNER)
    first_message = Message(role=MessageRole.USER, content="first")
    await store.append(dialog_id, (first_message,))

    snapshot = await store.get(OWNER, dialog_id)
    await store.append(
        dialog_id,
        (Message(role=MessageRole.ASSISTANT, content="second"),),
    )

    assert snapshot == (first_message,)
    assert await store.get(OWNER, dialog_id) != snapshot


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["get", "append", "transcript"])
async def test_unknown_dialog_raises_domain_error(operation: str) -> None:
    store = InMemoryHistoryStore()
    missing_dialog_id = uuid4()

    with pytest.raises(DialogNotFoundError) as caught:
        if operation == "get":
            await store.get(OWNER, missing_dialog_id)
        elif operation == "append":
            await store.append(missing_dialog_id, ())
        else:
            await store.transcript(OWNER, missing_dialog_id)

    assert caught.value.dialog_id == missing_dialog_id


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["get", "transcript"])
async def test_foreign_dialog_looks_like_a_missing_one(operation: str) -> None:
    store = InMemoryHistoryStore()
    dialog_id = await store.create(OWNER)
    await store.append(dialog_id, pair("secret"))

    with pytest.raises(DialogNotFoundError) as caught:
        if operation == "get":
            await store.get(STRANGER, dialog_id)
        else:
            await store.transcript(STRANGER, dialog_id)

    assert caught.value.dialog_id == dialog_id
    assert await store.list_dialogs(STRANGER, limit=50) == ()


@pytest.mark.asyncio
async def test_first_user_message_sets_the_title_once() -> None:
    store = InMemoryHistoryStore()
    dialog_id = await store.create(OWNER)

    assert (await store.transcript(OWNER, dialog_id)).title is None
    await store.append(dialog_id, pair("  Крош и\n\tЁжик   строят ракету "))
    await store.append(dialog_id, pair("Другая тема"))

    transcript = await store.transcript(OWNER, dialog_id)
    assert transcript.dialog_id == dialog_id
    assert transcript.title == "Крош и Ёжик строят ракету"
    assert [(item.role, item.content) for item in transcript.messages] == [
        (MessageRole.USER, "  Крош и\n\tЁжик   строят ракету "),
        (MessageRole.ASSISTANT, "answer"),
        (MessageRole.USER, "Другая тема"),
        (MessageRole.ASSISTANT, "answer"),
    ]


@pytest.mark.asyncio
async def test_list_skips_empty_dialogs_and_orders_by_last_update() -> None:
    clock = StepClock()
    store = InMemoryHistoryStore(clock=clock)
    older = await store.create(OWNER)
    newer = await store.create(OWNER)
    await store.create(OWNER)
    await store.append(older, pair("first"))
    await store.append(newer, pair("second"))
    await store.append(older, pair("third"))

    dialogs = await store.list_dialogs(OWNER, limit=50)

    assert [summary.dialog_id for summary in dialogs] == [older, newer]
    assert [summary.title for summary in dialogs] == ["first", "second"]
    assert dialogs[0].updated_at > dialogs[1].updated_at
    assert dialogs[0].created_at < dialogs[1].created_at


@pytest.mark.asyncio
async def test_list_returns_at_most_limit_dialogs() -> None:
    store = InMemoryHistoryStore(clock=StepClock())
    for index in range(3):
        await store.append(await store.create(OWNER), pair(f"story {index}"))

    dialogs = await store.list_dialogs(OWNER, limit=2)

    assert [summary.title for summary in dialogs] == ["story 2", "story 1"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Крош", "Крош"),
        ("  a \n\t b  ", "a b"),
        ("x" * 60, "x" * 60),
        ("x" * 61, "x" * 60 + "…"),
        ("слово " * 20, ("слово " * 10).strip() + "…"),
    ],
)
def test_dialog_title_collapses_whitespace_and_truncates(
    text: str, expected: str
) -> None:
    assert dialog_title(text) == expected


@pytest.mark.asyncio
async def test_append_returns_increasing_message_ids() -> None:
    store = InMemoryHistoryStore()
    first = await store.create(OWNER)
    second = await store.create(OWNER)

    first_ids = await store.append(first, pair("a"))
    second_ids = await store.append(second, pair("b"))

    assert len(first_ids) == 2 and len(second_ids) == 2
    assert list(first_ids + second_ids) == sorted(set(first_ids + second_ids))
    transcript = await store.transcript(OWNER, first)
    assert [item.id for item in transcript.messages] == list(first_ids)
    assert [item.feedback for item in transcript.messages] == [None, None]


@pytest.mark.asyncio
async def test_feedback_is_set_changed_and_cleared() -> None:
    store = InMemoryHistoryStore()
    dialog_id = await store.create(OWNER)
    _, answer_id = await store.append(dialog_id, pair("q"))

    await store.set_feedback(OWNER, dialog_id, answer_id, 5)
    assert (await store.transcript(OWNER, dialog_id)).messages[1].feedback == 5
    await store.set_feedback(OWNER, dialog_id, answer_id, 1)
    assert (await store.transcript(OWNER, dialog_id)).messages[1].feedback == 1
    await store.clear_feedback(OWNER, dialog_id, answer_id)
    await store.clear_feedback(OWNER, dialog_id, answer_id)
    assert (await store.transcript(OWNER, dialog_id)).messages[1].feedback is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case", ["user-message", "stranger", "other-dialog", "missing", "missing-dialog"]
)
async def test_feedback_targets_only_own_assistant_answers(case: str) -> None:
    store = InMemoryHistoryStore()
    dialog_id = await store.create(OWNER)
    other_id = await store.create(OWNER)
    question_id, answer_id = await store.append(dialog_id, pair("q"))
    _, other_answer = await store.append(other_id, pair("other"))
    owner, target_dialog, message_id = {
        "user-message": (OWNER, dialog_id, question_id),
        "stranger": (STRANGER, dialog_id, answer_id),
        "other-dialog": (OWNER, dialog_id, other_answer),
        "missing": (OWNER, dialog_id, 10_000),
        "missing-dialog": (OWNER, uuid4(), answer_id),
    }[case]

    for operation in ("set", "clear"):
        with pytest.raises(MessageNotFoundError):
            if operation == "set":
                await store.set_feedback(owner, target_dialog, message_id, 4)
            else:
                await store.clear_feedback(owner, target_dialog, message_id)

    assert [
        item.feedback for item in (await store.transcript(OWNER, dialog_id)).messages
    ] == [None, None]
