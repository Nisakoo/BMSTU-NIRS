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
    ReportReason,
)

NOT_FOUND = {"detail": "Message not found."}


class SilentAgent:
    async def run(
        self, history: Sequence[Message], request: UserRequest
    ) -> AsyncIterator[AgentStreamEvent]:
        yield AgentResponse(content="")


class UnavailableReportStore(InMemoryHistoryStore):
    async def report(
        self,
        owner_id: UUID,
        dialog_id: UUID,
        message_id: int,
        reason: ReportReason,
        comment: str | None,
    ) -> int:
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
    return f"/api/v1/dialogs/{dialog_id}/messages/{message_id}/report"


async def reported_of(http: httpx.AsyncClient, dialog_id: UUID) -> list[object]:
    body = (await http.get(f"/api/v1/dialogs/{dialog_id}/messages")).json()
    return [item["reported"] for item in body["messages"]]


@pytest.mark.asyncio
async def test_report_is_created_once_and_marks_the_answer() -> None:
    store = InMemoryHistoryStore()
    service, dialog_id, _, answer_id = await prepared(store)

    async with client(service) as http:
        before = await reported_of(http, dialog_id)
        created = await http.post(
            url(dialog_id, answer_id),
            json={"reason": "scary", "comment": "  Страшно стало  "},
        )
        again = await http.post(url(dialog_id, answer_id), json={"reason": "rude"})
        after = await reported_of(http, dialog_id)

    assert before == [False, False]
    assert created.status_code == 201
    [report] = store.reports()
    assert created.json() == {"report_id": report.id}
    assert (report.reason, report.comment) == (ReportReason.SCARY, "Страшно стало")
    assert (again.status_code, again.json()) == (409, {"detail": "Already reported."})
    assert after == [False, True]
    await service.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("comment", [None, "", "   "])
async def test_missing_or_blank_comment_is_stored_as_none(
    comment: str | None,
) -> None:
    store = InMemoryHistoryStore()
    service, dialog_id, _, answer_id = await prepared(store)
    body: dict[str, object] = {"reason": "wrong"}
    if comment is not None:
        body["comment"] = comment

    async with client(service) as http:
        response = await http.post(url(dialog_id, answer_id), json=body)

    assert response.status_code == 201
    assert store.reports()[0].comment is None
    await service.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("comment", [None, "", "   "])
async def test_other_reason_needs_a_comment(comment: str | None) -> None:
    store = InMemoryHistoryStore()
    service, dialog_id, _, answer_id = await prepared(store)
    body: dict[str, object] = {"reason": "other"}
    if comment is not None:
        body["comment"] = comment

    async with client(service) as http:
        refused = await http.post(url(dialog_id, answer_id), json=body)
        accepted = await http.post(
            url(dialog_id, answer_id), json={"reason": "other", "comment": " Скучно "}
        )

    assert refused.status_code == 422
    assert accepted.status_code == 201
    [report] = store.reports()
    assert (report.reason, report.comment) == (ReportReason.OTHER, "Скучно")
    await service.shutdown()


@pytest.mark.asyncio
async def test_comment_of_500_characters_is_accepted() -> None:
    store = InMemoryHistoryStore()
    service, dialog_id, _, answer_id = await prepared(store)

    async with client(service) as http:
        response = await http.post(
            url(dialog_id, answer_id), json={"reason": "wrong", "comment": "я" * 500}
        )

    assert response.status_code == 201
    assert store.reports()[0].comment == "я" * 500
    await service.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["question", "missing", "other-dialog", "stranger"])
async def test_only_own_answers_can_be_reported(case: str) -> None:
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
        response = await http.post(url(target, message_id), json={"reason": "rude"})

    assert (response.status_code, response.json()) == (404, NOT_FOUND)
    assert store.reports() == ()
    await service.shutdown()


@pytest.mark.asyncio
async def test_report_on_missing_dialog_is_404() -> None:
    service, _, _, answer_id = await prepared(InMemoryHistoryStore())

    async with client(service) as http:
        response = await http.post(url(uuid4(), answer_id), json={"reason": "rude"})

    assert (response.status_code, response.json()) == (404, NOT_FOUND)
    await service.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message_id", "body"),
    [
        ("abc", {"reason": "rude"}),
        ("0", {"reason": "rude"}),
        (str(2**63), {"reason": "rude"}),
        ("{answer}", {"reason": "boring"}),
        ("{answer}", {"reason": None}),
        ("{answer}", {}),
        ("{answer}", {"reason": "rude", "comment": "я" * 501}),
        ("{answer}", {"reason": "rude", "comment": 5}),
        ("{answer}", {"reason": "rude", "extra": 1}),
    ],
)
async def test_invalid_report_returns_422(message_id: str, body: object) -> None:
    store = InMemoryHistoryStore()
    service, dialog_id, _, answer_id = await prepared(store)

    async with client(service) as http:
        response = await http.post(
            url(dialog_id, message_id.format(answer=answer_id)), json=body
        )

    assert response.status_code == 422
    assert store.reports() == ()
    await service.shutdown()


@pytest.mark.asyncio
async def test_guest_gets_401_before_validation() -> None:
    service, _, _, _ = await prepared(InMemoryHistoryStore())

    async with client(service, {}) as http:
        response = await http.post(url("not-a-uuid", "abc"), json={"reason": "x"})

    assert (response.status_code, response.json()) == (401, {"error": "unauthorized"})
    await service.shutdown()


@pytest.mark.asyncio
async def test_unavailable_store_returns_503() -> None:
    service, dialog_id, _, answer_id = await prepared(UnavailableReportStore())

    async with client(service) as http:
        response = await http.post(url(dialog_id, answer_id), json={"reason": "rude"})

    assert response.status_code == 503
    assert response.json() == {"detail": "Agent service is unavailable."}
    await service.shutdown()
