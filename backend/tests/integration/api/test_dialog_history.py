import asyncio
import logging
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from api_auth_support import (
    ADMIN_COOKIES,
    AUTH_COOKIES,
    OTHER_COOKIES,
    TEST_USER,
    static_auth_service,
)

from smeshariki_ai.agent import (
    AgentResponse,
    AgentStreamEvent,
    AgentTextDelta,
    Message,
    MessageRole,
    UserRequest,
)
from smeshariki_ai.api import create_app
from smeshariki_ai.application import AgentService, InMemoryDialogEventBroker
from smeshariki_ai.dialogs import HistoryUnavailableError, InMemoryHistoryStore

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
PAIR = (
    Message(role=MessageRole.USER, content="private question"),
    Message(role=MessageRole.ASSISTANT, content="private answer"),
)


class GatedAgent:
    """Answers "answer" once released; every call waits for ``release``."""

    def __init__(self, *, open_gate: bool = True) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        if open_gate:
            self.release.set()
        self.calls: list[tuple[tuple[Message, ...], UserRequest]] = []

    async def run(
        self,
        history: Sequence[Message],
        request: UserRequest,
    ) -> AsyncIterator[AgentStreamEvent]:
        self.calls.append((tuple(history), request))
        self.started.set()
        await self.release.wait()
        yield AgentTextDelta(content="answer")
        yield AgentResponse(content="answer")


class UnavailableStore(InMemoryHistoryStore):
    async def create(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        raise HistoryUnavailableError

    async def owner(self, dialog_id: UUID) -> UUID:
        raise HistoryUnavailableError

    async def read(self, dialog_id: UUID):  # type: ignore[no-untyped-def]
        raise HistoryUnavailableError

    async def list(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise HistoryUnavailableError


def make_service(
    agent: GatedAgent | None = None, store: InMemoryHistoryStore | None = None
) -> AgentService:
    return AgentService(
        agent or GatedAgent(),  # type: ignore[arg-type]
        store or InMemoryHistoryStore(),
        InMemoryDialogEventBroker(),
    )


def make_client(
    service: AgentService, *, cookies: dict[str, str] | None = None
) -> httpx.AsyncClient:
    app = create_app(service, auth_service=static_auth_service())
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=AUTH_COOKIES if cookies is None else cookies,
    )


async def answer(client: httpx.AsyncClient, dialog_id: str, text: str) -> None:
    """Send a request and wait until the dialog reports the answer."""

    events = asyncio.create_task(client.get(f"/api/v1/dialogs/{dialog_id}/events"))
    await asyncio.sleep(0)
    posted = await client.post(
        f"/api/v1/dialogs/{dialog_id}/messages", json={"request": text}
    )
    assert posted.status_code == 202
    for _ in range(200):
        transcript = (await client.get(f"/api/v1/dialogs/{dialog_id}/messages")).json()
        if any(m["content"] == "answer" for m in transcript["messages"]):
            break
        await asyncio.sleep(0.005)
    events.cancel()


async def seed(store: InMemoryHistoryStore, count: int, owner_id: UUID) -> list[UUID]:
    ids = []
    for index in range(count):
        dialog_id = uuid4()
        await store.create(
            dialog_id,
            owner_id,
            f"dialog {index}",
            PAIR,
            NOW + timedelta(minutes=index),
        )
        ids.append(dialog_id)
    return ids


async def test_draft_is_hidden_until_the_first_answer_then_listed() -> None:
    service = make_service()
    async with make_client(service) as client:
        created = await client.post("/api/v1/dialogs")
        dialog_id = created.json()["dialog_id"]

        assert (await client.get("/api/v1/dialogs")).json() == {
            "items": [],
            "next_cursor": None,
        }
        draft = await client.get(f"/api/v1/dialogs/{dialog_id}/messages")
        assert draft.status_code == 200
        assert draft.json() == {"dialog_id": dialog_id, "title": None, "messages": []}

        await answer(client, dialog_id, "  Hello,\n  Krosh  ")

        listed = (await client.get("/api/v1/dialogs")).json()
        (item,) = listed["items"]
        assert set(item) == {"dialog_id", "title", "created_at", "updated_at"}
        assert (item["dialog_id"], item["title"]) == (dialog_id, "Hello, Krosh")
        assert item["created_at"].endswith("Z")
        assert item["updated_at"].endswith("Z")
        assert listed["next_cursor"] is None
        transcript = (await client.get(f"/api/v1/dialogs/{dialog_id}/messages")).json()
        assert transcript["title"] == "Hello, Krosh"
        assert [(m["role"], m["content"]) for m in transcript["messages"]] == [
            ("user", "Hello,\n  Krosh"),
            ("assistant", "answer"),
        ]
        assert all(m["created_at"].endswith("Z") for m in transcript["messages"])
    await service.shutdown()


async def test_list_pages_with_cursor_without_repeats() -> None:
    store = InMemoryHistoryStore()
    service = make_service(store=store)
    ids = await seed(store, 25, TEST_USER.id)
    await seed(store, 4, UUID(int=2))
    async with make_client(service) as client:
        for _ in range(3):
            await client.post("/api/v1/dialogs")
        first = (await client.get("/api/v1/dialogs?limit=20")).json()
        second = (
            await client.get(
                "/api/v1/dialogs", params={"limit": 20, "cursor": first["next_cursor"]}
            )
        ).json()
        default_page = (await client.get("/api/v1/dialogs")).json()

    assert [i["dialog_id"] for i in first["items"]] == [str(i) for i in ids[::-1][:20]]
    assert first["next_cursor"]
    assert [i["dialog_id"] for i in second["items"]] == [str(i) for i in ids[::-1][20:]]
    assert second["next_cursor"] is None
    assert default_page["items"] == first["items"]
    await service.shutdown()


@pytest.mark.parametrize(
    ("query", "location"),
    [
        ("limit=0", "limit"),
        ("limit=51", "limit"),
        ("limit=many", "limit"),
        ("cursor=not-a-cursor", "cursor"),
        ("cursor=e30", "cursor"),
        ("cursor=bm90LWpzb24", "cursor"),
    ],
)
async def test_invalid_limit_or_cursor_is_rejected_with_422(
    query: str, location: str
) -> None:
    service = make_service()
    async with make_client(service) as client:
        response = await client.get(f"/api/v1/dialogs?{query}")

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", location]
    await service.shutdown()


async def test_new_routes_require_authentication_before_validation() -> None:
    service = make_service()
    async with make_client(service, cookies={}) as client:
        responses = [
            await client.get("/api/v1/dialogs?limit=0"),
            await client.get(f"/api/v1/dialogs/{uuid4()}/messages"),
            await client.get("/api/v1/dialogs/not-a-uuid/messages"),
            await client.delete(f"/api/v1/dialogs/{uuid4()}"),
            await client.delete("/api/v1/dialogs/not-a-uuid"),
        ]

    assert [response.status_code for response in responses] == [401] * 5
    await service.shutdown()


async def test_invalid_dialog_id_is_rejected_with_422() -> None:
    service = make_service()
    async with make_client(service) as client:
        read = await client.get("/api/v1/dialogs/not-a-uuid/messages")
        delete = await client.delete("/api/v1/dialogs/not-a-uuid")

    assert (read.status_code, delete.status_code) == (422, 422)
    await service.shutdown()


@pytest.mark.parametrize("cookies", [OTHER_COOKIES, ADMIN_COOKIES])
async def test_foreign_draft_and_saved_dialog_look_missing(
    cookies: dict[str, str], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="smeshariki_ai.application.agent_service")
    store = InMemoryHistoryStore()
    service = make_service(store=store)
    (saved_id,) = await seed(store, 1, TEST_USER.id)
    async with make_client(service) as owner:
        draft_id = (await owner.post("/api/v1/dialogs")).json()["dialog_id"]
    async with make_client(service, cookies=cookies) as client:
        responses = []
        for dialog_id in (draft_id, str(saved_id), str(uuid4())):
            responses.append(await client.get(f"/api/v1/dialogs/{dialog_id}/messages"))
            responses.append(await client.delete(f"/api/v1/dialogs/{dialog_id}"))
        listed = await client.get("/api/v1/dialogs")

    for response in responses:
        assert response.status_code == 404
        assert response.json() == {"detail": "Dialog not found."}
    assert listed.json()["items"] == []
    assert len(await store.list(TEST_USER.id, 10, None)) == 1
    denied = [r for r in caplog.records if r.getMessage().startswith("dialog.access")]
    assert len(denied) == 4
    await service.shutdown()


async def test_delete_removes_saved_dialog_and_draft() -> None:
    store = InMemoryHistoryStore()
    service = make_service(store=store)
    (saved_id,) = await seed(store, 1, TEST_USER.id)
    async with make_client(service) as client:
        draft_id = (await client.post("/api/v1/dialogs")).json()["dialog_id"]

        for dialog_id in (str(saved_id), draft_id):
            deleted = await client.delete(f"/api/v1/dialogs/{dialog_id}")
            assert (deleted.status_code, deleted.content) == (204, b"")
            assert (
                await client.get(f"/api/v1/dialogs/{dialog_id}/messages")
            ).status_code == 404
            assert (
                await client.post(
                    f"/api/v1/dialogs/{dialog_id}/messages", json={"request": "x"}
                )
            ).status_code == 404
            assert (
                await client.get(f"/api/v1/dialogs/{dialog_id}/events")
            ).status_code == 404
            assert (
                await client.delete(f"/api/v1/dialogs/{dialog_id}")
            ).status_code == 404

        assert (await client.get("/api/v1/dialogs")).json()["items"] == []
    await service.shutdown()


async def test_delete_during_answer_ends_stream_after_message_error() -> None:
    agent = GatedAgent(open_gate=False)
    store = InMemoryHistoryStore()
    service = make_service(agent, store)
    async with make_client(service) as client:
        dialog_id = (await client.post("/api/v1/dialogs")).json()["dialog_id"]
        stream = asyncio.create_task(client.get(f"/api/v1/dialogs/{dialog_id}/events"))
        await asyncio.sleep(0.01)
        await client.post(
            f"/api/v1/dialogs/{dialog_id}/messages", json={"request": "private"}
        )
        await client.post(
            f"/api/v1/dialogs/{dialog_id}/messages", json={"request": "queued"}
        )
        await asyncio.wait_for(agent.started.wait(), timeout=1)

        deleted = await client.delete(f"/api/v1/dialogs/{dialog_id}")
        response = await asyncio.wait_for(stream, timeout=2)

    assert deleted.status_code == 204
    assert "event: message_error" in response.text
    assert "event: message_end" not in response.text
    assert len(agent.calls) == 1
    assert await store.list(TEST_USER.id, 10, None) == ()
    await service.shutdown()


async def test_cross_site_delete_is_forbidden_and_changes_nothing() -> None:
    store = InMemoryHistoryStore()
    service = make_service(store=store)
    (saved_id,) = await seed(store, 1, TEST_USER.id)
    async with make_client(service) as client:
        for site in ("cross-site", "same-site"):
            response = await client.delete(
                f"/api/v1/dialogs/{saved_id}", headers={"Sec-Fetch-Site": site}
            )
            assert response.status_code == 403
        same_origin = await client.delete(
            f"/api/v1/dialogs/{saved_id}", headers={"Sec-Fetch-Site": "same-origin"}
        )

    assert same_origin.status_code == 204
    await service.shutdown()


async def test_unavailable_storage_gives_503_but_drafts_keep_working(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="smeshariki_ai.api.app")
    service = make_service(store=UnavailableStore())
    missing = uuid4()
    async with make_client(service) as client:
        created = await client.post("/api/v1/dialogs")
        dialog_id = created.json()["dialog_id"]
        events = asyncio.create_task(client.get(f"/api/v1/dialogs/{dialog_id}/events"))
        await asyncio.sleep(0.01)
        accepted = await client.post(
            f"/api/v1/dialogs/{dialog_id}/messages", json={"request": "private"}
        )
        draft = await client.get(f"/api/v1/dialogs/{dialog_id}/messages")
        await asyncio.sleep(0.05)
        unavailable = [
            await client.get("/api/v1/dialogs"),
            await client.get(f"/api/v1/dialogs/{missing}/messages"),
            await client.post(
                f"/api/v1/dialogs/{missing}/messages", json={"request": "x"}
            ),
            await client.get(f"/api/v1/dialogs/{missing}/events"),
            await client.delete(f"/api/v1/dialogs/{missing}"),
        ]
        still_draft = await client.get(f"/api/v1/dialogs/{dialog_id}/messages")
        events.cancel()

    assert (created.status_code, accepted.status_code) == (201, 202)
    assert draft.json()["messages"] == []
    assert still_draft.json() == {"dialog_id": dialog_id, "title": None, "messages": []}
    for response in unavailable:
        assert response.status_code == 503
        assert response.json() == {"detail": "Dialog storage is unavailable."}
    failures = [
        r for r in caplog.records if r.getMessage().startswith("dialog.storage.")
    ]
    assert len(failures) == len(unavailable)
    assert {r.error_type for r in failures} == {"HistoryUnavailableError"}
    await service.shutdown()


async def test_failed_first_save_sends_message_error_to_subscriber() -> None:
    service = make_service(store=UnavailableStore())
    async with make_client(service) as client:
        dialog_id = (await client.post("/api/v1/dialogs")).json()["dialog_id"]
        events = asyncio.create_task(client.get(f"/api/v1/dialogs/{dialog_id}/events"))
        await asyncio.sleep(0.01)
        await client.post(
            f"/api/v1/dialogs/{dialog_id}/messages", json={"request": "private"}
        )
        await asyncio.sleep(0.05)
        await client.delete(f"/api/v1/dialogs/{dialog_id}")
        response = await asyncio.wait_for(events, timeout=2)

    assert "event: message_error" in response.text
    assert "event: message_end" not in response.text
    await service.shutdown()


async def test_logs_never_contain_titles_texts_or_cursors(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="smeshariki_ai")
    store = InMemoryHistoryStore()
    service = make_service(store=store)
    ids = await seed(store, 3, TEST_USER.id)
    async with make_client(service) as client:
        page = (await client.get("/api/v1/dialogs?limit=2")).json()
        await client.get("/api/v1/dialogs", params={"cursor": page["next_cursor"]})
        await client.get("/api/v1/dialogs?cursor=private-garbage")
        await client.get(f"/api/v1/dialogs/{ids[0]}/messages")
        await client.delete(f"/api/v1/dialogs/{ids[0]}")

    assert "dialog 0" not in caplog.text
    assert "private" not in caplog.text
    assert page["next_cursor"] not in caplog.text
    deleted = next(
        r for r in caplog.records if r.getMessage().startswith("dialog.deleted ")
    )
    assert (deleted.dialog_id, deleted.user_id, deleted.draft) == (
        str(ids[0]),
        str(TEST_USER.id),
        False,
    )
    await service.shutdown()
