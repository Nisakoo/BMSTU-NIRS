import asyncio
from collections.abc import AsyncIterator, Sequence
from uuid import UUID, uuid4

import httpx
import pytest
from api_auth_support import (
    AUTH_COOKIES,
    OTHER_COOKIES,
    TEST_USER,
    static_auth_service,
)

from smeshariki_ai.agent import (
    AgentResponse,
    AgentStreamEvent,
    Message,
    MessageRole,
    UserRequest,
)
from smeshariki_ai.api import create_app
from smeshariki_ai.application import AgentService, InMemoryDialogEventBroker
from smeshariki_ai.dialogs import (
    DialogStoreUnavailableError,
    InMemoryHistoryStore,
)

NOT_FOUND = {"detail": "Message not found."}


class SilentAgent:
    async def run(
        self, history: Sequence[Message], request: UserRequest
    ) -> AsyncIterator[AgentStreamEvent]:
        yield AgentResponse(content="")


class UnavailableFeedbackStore(InMemoryHistoryStore):
    async def set_feedback(
        self,
        owner_id: UUID,
        dialog_id: UUID,
        message_id: int,
        score: int,
    ) -> None:
        raise DialogStoreUnavailableError

    async def clear_feedback(
        self, owner_id: UUID, dialog_id: UUID, message_id: int
    ) -> None:
        raise DialogStoreUnavailableError


async def prepared(
    store: InMemoryHistoryStore,
) -> tuple[AgentService, UUID, int, int]:
    service = AgentService(SilentAgent(), store, InMemoryDialogEventBroker())
    dialog_id = await service.start_dialog(TEST_USER.id)
    question_id, answer_id = await store.append(
        dialog_id,
        (
            Message(role=MessageRole.USER, content="Крош"),
            Message(role=MessageRole.ASSISTANT, content="Однажды…"),
        ),
    )
    return service, dialog_id, question_id, answer_id


def client(
    service: AgentService, cookies: dict[str, str] | None = None
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(
            app=create_app(service, auth_service=static_auth_service())
        ),
        base_url="http://test",
        cookies=AUTH_COOKIES if cookies is None else cookies,
    )


def url(dialog_id: object, message_id: object) -> str:
    return f"/api/v1/dialogs/{dialog_id}/messages/{message_id}/feedback"


async def feedback_of(http: httpx.AsyncClient, dialog_id: UUID) -> list[object]:
    body = (await http.get(f"/api/v1/dialogs/{dialog_id}/messages")).json()
    return [item["feedback"] for item in body["messages"]]


@pytest.mark.asyncio
async def test_feedback_is_set_changed_and_cleared() -> None:
    service, dialog_id, _, answer_id = await prepared(InMemoryHistoryStore())

    async with client(service) as http:
        best = await http.put(url(dialog_id, answer_id), json={"score": 5})
        after_best = await feedback_of(http, dialog_id)
        worst = await http.put(url(dialog_id, answer_id), json={"score": 1})
        after_worst = await feedback_of(http, dialog_id)
        cleared = await http.delete(url(dialog_id, answer_id))
        cleared_again = await http.delete(url(dialog_id, answer_id))
        after_clear = await feedback_of(http, dialog_id)

    for response in (best, worst, cleared, cleared_again):
        assert response.status_code == 204
        assert response.content == b""
    assert after_best == [None, 5]
    assert after_worst == [None, 1]
    assert after_clear == [None, None]
    await service.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["question", "missing", "other-dialog", "stranger"])
async def test_only_own_answers_can_be_rated(case: str) -> None:
    store = InMemoryHistoryStore()
    service, dialog_id, question_id, answer_id = await prepared(store)
    other_dialog = await service.start_dialog(TEST_USER.id)
    target, message_id, cookies = {
        "question": (dialog_id, question_id, None),
        "missing": (dialog_id, 999, None),
        "other-dialog": (other_dialog, answer_id, None),
        "stranger": (dialog_id, answer_id, OTHER_COOKIES),
    }[case]

    async with client(service, cookies) as http:
        put = await http.put(url(target, message_id), json={"score": 4})
        delete = await http.delete(url(target, message_id))
    async with client(service) as http:
        stored = await feedback_of(http, dialog_id)

    assert (put.status_code, put.json()) == (404, NOT_FOUND)
    assert (delete.status_code, delete.json()) == (404, NOT_FOUND)
    assert stored == [None, None]
    await service.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message_id", "body"),
    [
        ("abc", {"score": 3}),
        ("{answer}", {"score": 0}),
        ("{answer}", {"score": 6}),
        ("{answer}", {"score": 2.5}),
        ("{answer}", {"score": True}),
        ("{answer}", {"score": "5"}),
        ("{answer}", {"score": None}),
        ("{answer}", {"value": "like"}),
        ("{answer}", {}),
        ("{answer}", {"score": 3, "extra": 1}),
    ],
)
async def test_invalid_feedback_returns_422(message_id: str, body: object) -> None:
    service, dialog_id, _, answer_id = await prepared(InMemoryHistoryStore())

    async with client(service) as http:
        response = await http.put(
            url(dialog_id, message_id.format(answer=answer_id)), json=body
        )

    assert response.status_code == 422
    await service.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["PUT", "DELETE"])
async def test_guest_gets_401_before_validation(method: str) -> None:
    service, _, _, _ = await prepared(InMemoryHistoryStore())

    async with client(service, {}) as http:
        response = await http.request(
            method, url("not-a-uuid", "abc"), json={"score": 0}
        )

    assert (response.status_code, response.json()) == (401, {"error": "unauthorized"})
    await service.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["PUT", "DELETE"])
async def test_unavailable_store_returns_503(method: str) -> None:
    service, dialog_id, _, answer_id = await prepared(UnavailableFeedbackStore())

    async with client(service) as http:
        response = await http.request(
            method, url(dialog_id, answer_id), json={"score": 4}
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "Agent service is unavailable."}
    await service.shutdown()


@pytest.mark.asyncio
async def test_feedback_on_missing_dialog_is_404() -> None:
    service, _, _, answer_id = await prepared(InMemoryHistoryStore())

    async with client(service) as http:
        response = await http.put(url(uuid4(), answer_id), json={"score": 4})

    assert (response.status_code, response.json()) == (404, NOT_FOUND)
    await asyncio.sleep(0)
    await service.shutdown()
