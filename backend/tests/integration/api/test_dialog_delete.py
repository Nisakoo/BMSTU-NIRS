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
from smeshariki_ai.dialogs import DialogStoreUnavailableError, InMemoryHistoryStore

NOT_FOUND = {"detail": "Dialog not found."}


class SilentAgent:
    async def run(
        self, history: Sequence[Message], request: UserRequest
    ) -> AsyncIterator[AgentStreamEvent]:
        yield AgentResponse(content="")


class UnavailableDeleteStore(InMemoryHistoryStore):
    async def delete(self, owner_id: UUID, dialog_id: UUID) -> None:
        raise DialogStoreUnavailableError


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


async def saved_dialog(
    store: InMemoryHistoryStore,
) -> tuple[AgentService, UUID, int]:
    service = AgentService(SilentAgent(), store, InMemoryDialogEventBroker())
    dialog_id = await service.start_dialog(TEST_USER.id)
    _, answer_id = await store.append(
        dialog_id,
        (
            Message(role=MessageRole.USER, content="Крош"),
            Message(role=MessageRole.ASSISTANT, content="Однажды…"),
        ),
    )
    return service, dialog_id, answer_id


@pytest.mark.asyncio
async def test_deleted_dialog_is_gone_from_every_route() -> None:
    store = InMemoryHistoryStore()
    service, dialog_id, answer_id = await saved_dialog(store)
    kept = await service.start_dialog(TEST_USER.id)
    await store.append(
        kept,
        (
            Message(role=MessageRole.USER, content="Пирог"),
            Message(role=MessageRole.ASSISTANT, content="…"),
        ),
    )

    async with client(service) as http:
        deleted = await http.delete(f"/api/v1/dialogs/{dialog_id}")
        listed = await http.get("/api/v1/dialogs")
        after = [
            await http.get(f"/api/v1/dialogs/{dialog_id}/messages"),
            await http.post(
                f"/api/v1/dialogs/{dialog_id}/messages", json={"request": "hi"}
            ),
            await http.get(f"/api/v1/dialogs/{dialog_id}/events"),
            await http.delete(f"/api/v1/dialogs/{dialog_id}"),
        ]
        rating = await http.put(
            f"/api/v1/dialogs/{dialog_id}/messages/{answer_id}/feedback",
            json={"score": 5},
        )

    assert (deleted.status_code, deleted.content) == (204, b"")
    assert [item["dialog_id"] for item in listed.json()["dialogs"]] == [str(kept)]
    for response in after:
        assert (response.status_code, response.json()) == (404, NOT_FOUND)
    assert rating.status_code == 404
    await service.shutdown()


@pytest.mark.asyncio
async def test_foreign_or_missing_dialog_is_not_found_and_kept() -> None:
    store = InMemoryHistoryStore()
    service, dialog_id, _ = await saved_dialog(store)

    async with client(service, OTHER_COOKIES) as stranger:
        foreign = await stranger.delete(f"/api/v1/dialogs/{dialog_id}")
        missing = await stranger.delete(f"/api/v1/dialogs/{uuid4()}")

    assert (foreign.status_code, foreign.json()) == (404, NOT_FOUND)
    assert (missing.status_code, missing.json()) == (404, NOT_FOUND)
    assert len(await store.get(TEST_USER.id, dialog_id)) == 2
    await service.shutdown()


@pytest.mark.asyncio
async def test_bad_id_is_422_and_guest_gets_401_first() -> None:
    service, dialog_id, _ = await saved_dialog(InMemoryHistoryStore())

    async with client(service) as http:
        bad = await http.delete("/api/v1/dialogs/not-a-uuid")
    async with client(service, {}) as guest:
        guest_bad = await guest.delete("/api/v1/dialogs/not-a-uuid")
        guest_real = await guest.delete(f"/api/v1/dialogs/{dialog_id}")

    assert bad.status_code == 422
    for response in (guest_bad, guest_real):
        assert (response.status_code, response.json()) == (
            401,
            {"error": "unauthorized"},
        )
    await service.shutdown()


@pytest.mark.asyncio
async def test_unavailable_store_returns_503() -> None:
    service, dialog_id, _ = await saved_dialog(UnavailableDeleteStore())

    async with client(service) as http:
        response = await http.delete(f"/api/v1/dialogs/{dialog_id}")

    assert response.status_code == 503
    assert response.json() == {"detail": "Agent service is unavailable."}
    await service.shutdown()
