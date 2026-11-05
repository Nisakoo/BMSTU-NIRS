import asyncio
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Sequence
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime
from importlib.resources import files
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    FastAPI,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, ValidationError

from smeshariki_ai.admin import AdminReportsService, AdminStatsService
from smeshariki_ai.agent import UserRequest
from smeshariki_ai.api.admin import install_admin
from smeshariki_ai.api.auth import (
    ACCESS_COOKIE,
    current_user,
    install_auth,
    install_auth_errors,
)
from smeshariki_ai.api.schemas import (
    DbIdPath,
    DialogListResponse,
    DialogMessageResponse,
    DialogMessagesResponse,
    DialogSummaryResponse,
    FeedbackRequest,
    ReportNewsItem,
    ReportNewsResponse,
    ReportNewsSeenRequest,
    ReportRequest,
    ReportResponse,
    StartDialogResponse,
    SubmitMessageRequest,
)
from smeshariki_ai.api.security import ForbiddenOriginMiddleware, has_json_body
from smeshariki_ai.application import (
    AgentService,
    AgentServiceUnavailableError,
    DialogEvent,
    DialogEventType,
)
from smeshariki_ai.auth import (
    AuthService,
    AuthUnavailableError,
    UnauthorizedError,
    User,
)
from smeshariki_ai.dialogs import (
    DialogNotFoundError,
    DialogStoreUnavailableError,
    MessageNotFoundError,
    ReportExistsError,
)
from smeshariki_ai.observability import RequestLogMiddleware, log_event

logger = logging.getLogger(__name__)

CurrentUser = Annotated[User, Depends(current_user)]

AGENT_TEST_HTML = (
    files("smeshariki_ai.api").joinpath("agent_test.html").read_text(encoding="utf-8")
)


def create_app(
    agent_service: AgentService,
    *,
    heartbeat_seconds: float = 15.0,
    auth_service: AuthService | None = None,
    auth_cookie_secure: bool = False,
    admin_stats: AdminStatsService | None = None,
    admin_reports: AdminReportsService | None = None,
    on_shutdown: Sequence[Callable[[], Awaitable[None]]] = (),
) -> FastAPI:
    if heartbeat_seconds <= 0:
        raise ValueError("heartbeat_seconds must be positive")

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        try:
            await agent_service.shutdown()
        finally:
            for close in on_shutdown:
                await close()

    app = FastAPI(title="smeshariki-ai", lifespan=lifespan)
    # Added first, so it runs inside the request log and its 403 is logged.
    app.add_middleware(ForbiddenOriginMiddleware)
    app.add_middleware(RequestLogMiddleware)
    app.state.agent_service = agent_service
    install_auth_errors(app)

    @app.get("/agent_test", response_class=HTMLResponse, include_in_schema=False)
    async def agent_test() -> HTMLResponse:
        return HTMLResponse(AGENT_TEST_HTML)

    # Authentication runs before path and body validation, so guests get 401.
    router = APIRouter(prefix="/api/v1", dependencies=[Depends(current_user)])

    @router.post(
        "/dialogs",
        status_code=status.HTTP_201_CREATED,
        response_model=StartDialogResponse,
    )
    async def start_dialog(
        user: CurrentUser, response: Response
    ) -> StartDialogResponse:
        with _dialog_errors():
            dialog_id = await agent_service.start_dialog(user.id)

        response.headers["Location"] = f"/api/v1/dialogs/{dialog_id}"
        return StartDialogResponse(dialog_id=dialog_id)

    @router.get("/dialogs", response_model=DialogListResponse)
    async def list_dialogs(user: CurrentUser) -> DialogListResponse:
        with _dialog_errors():
            dialogs = await agent_service.list_dialogs(user.id)
        return DialogListResponse(
            dialogs=[
                DialogSummaryResponse(
                    dialog_id=item.dialog_id,
                    title=item.title,
                    created_at=_utc(item.created_at),
                    updated_at=_utc(item.updated_at),
                )
                for item in dialogs
            ]
        )

    @router.delete(
        "/dialogs/{dialog_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        response_class=Response,
    )
    async def delete_dialog(user: CurrentUser, dialog_id: UUID) -> Response:
        with _dialog_errors():
            await agent_service.delete_dialog(user.id, dialog_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.get(
        "/dialogs/{dialog_id}/messages",
        response_model=DialogMessagesResponse,
    )
    async def dialog_messages(
        user: CurrentUser, dialog_id: UUID
    ) -> DialogMessagesResponse:
        with _dialog_errors():
            transcript = await agent_service.transcript(user.id, dialog_id)
        return DialogMessagesResponse(
            dialog_id=transcript.dialog_id,
            title=transcript.title,
            messages=[
                DialogMessageResponse(
                    id=item.id,
                    role=item.role.value,
                    content=item.content,
                    created_at=_utc(item.created_at),
                    feedback=item.feedback,
                    reported=item.reported,
                    report=item.report,
                )
                for item in transcript.messages
            ],
        )

    @router.post(
        "/dialogs/{dialog_id}/messages",
        status_code=status.HTTP_202_ACCEPTED,
        response_class=Response,
    )
    async def submit_message(
        user: CurrentUser,
        dialog_id: UUID,
        request: Request,
    ) -> Response:
        body = await _read_body(request, SubmitMessageRequest)
        with _dialog_errors():
            await agent_service.submit(
                user.id,
                dialog_id,
                UserRequest(content=body.request, reading_minutes=body.reading_minutes),
            )

        return Response(status_code=status.HTTP_202_ACCEPTED)

    @router.put(
        "/dialogs/{dialog_id}/messages/{message_id}/feedback",
        status_code=status.HTTP_204_NO_CONTENT,
        response_class=Response,
    )
    async def set_feedback(
        user: CurrentUser, dialog_id: UUID, message_id: DbIdPath, request: Request
    ) -> Response:
        body = await _read_body(request, FeedbackRequest)
        with _dialog_errors():
            await agent_service.set_feedback(user.id, dialog_id, message_id, body.score)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.delete(
        "/dialogs/{dialog_id}/messages/{message_id}/feedback",
        status_code=status.HTTP_204_NO_CONTENT,
        response_class=Response,
    )
    async def clear_feedback(
        user: CurrentUser, dialog_id: UUID, message_id: DbIdPath
    ) -> Response:
        with _dialog_errors():
            await agent_service.clear_feedback(user.id, dialog_id, message_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.post(
        "/dialogs/{dialog_id}/messages/{message_id}/report",
        status_code=status.HTTP_201_CREATED,
        response_model=ReportResponse,
    )
    async def report_message(
        user: CurrentUser, dialog_id: UUID, message_id: DbIdPath, request: Request
    ) -> ReportResponse:
        body = await _read_body(request, ReportRequest)
        with _dialog_errors():
            try:
                report_id = await agent_service.report(
                    user.id, dialog_id, message_id, body.reason, body.comment
                )
            except ReportExistsError as error:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Already reported.",
                ) from error
        return ReportResponse(report_id=report_id)

    @router.get("/reports/news", response_model=ReportNewsResponse)
    async def report_news(user: CurrentUser) -> ReportNewsResponse:
        with _dialog_errors():
            news = await agent_service.report_news(user.id)
        return ReportNewsResponse(
            news=[
                ReportNewsItem(
                    report_id=item.report_id,
                    dialog_id=item.dialog_id,
                    dialog_title=item.dialog_title,
                )
                for item in news
            ]
        )

    @router.post(
        "/reports/news/seen",
        status_code=status.HTTP_204_NO_CONTENT,
        response_class=Response,
    )
    async def mark_report_news_seen(user: CurrentUser, request: Request) -> Response:
        body = await _read_body(request, ReportNewsSeenRequest)
        with _dialog_errors():
            await agent_service.mark_report_news_seen(user.id, body.report_ids)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.get("/dialogs/{dialog_id}/events")
    async def stream_dialog_events(
        user: CurrentUser,
        dialog_id: UUID,
        request: Request,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> StreamingResponse:
        with _dialog_errors():
            subscription = await agent_service.subscribe(user.id, dialog_id)

        async def generate_events() -> AsyncIterator[str]:
            try:
                yield _format_sse(
                    "ready",
                    {"dialog_id": str(dialog_id)},
                )
                while True:
                    try:
                        event = await asyncio.wait_for(
                            subscription.receive(),
                            timeout=heartbeat_seconds,
                        )
                    except TimeoutError:
                        # The router dependency guarantees the service and token.
                        if not await _session_is_active(
                            request.app.state.auth_service,
                            access_token or "",
                            dialog_id,
                        ):
                            return
                        yield ": keep-alive\n\n"
                        continue

                    if event is None:
                        return
                    yield _format_dialog_event(event)
            finally:
                await agent_service.unsubscribe(subscription)

        return StreamingResponse(
            generate_events(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    app.include_router(router)
    if auth_service is not None:
        install_auth(app, auth_service, cookie_secure=auth_cookie_secure)
    install_admin(app, admin_stats, admin_reports)
    return app


@contextmanager
def _dialog_errors() -> Iterator[None]:
    # A foreign dialog is reported exactly like a missing one.
    try:
        yield
    except MessageNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found.",
        ) from error
    except DialogNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dialog not found.",
        ) from error
    except (AgentServiceUnavailableError, DialogStoreUnavailableError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent service is unavailable.",
        ) from error


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


async def _session_is_active(
    auth_service: AuthService, access_token: str, dialog_id: UUID
) -> bool:
    """Re-check the session of an open stream; ``exp`` is deliberately ignored."""

    try:
        await auth_service.verify_session(access_token)
    except UnauthorizedError:
        outcome = "revoked"
    except AuthUnavailableError:
        outcome = "unavailable"
    else:
        return True
    log_event(
        logger,
        logging.INFO,
        "dialog.subscription.revoked",
        dialog_id=str(dialog_id),
        outcome=outcome,
    )
    return False


async def _read_body[Body: BaseModel](request: Request, model: type[Body]) -> Body:
    # Parsed here rather than by FastAPI, which rejects malformed JSON before
    # running the authentication dependency.
    if not has_json_body(request):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported media type.",
        )
    try:
        return model.model_validate_json(await request.body())
    except ValidationError as error:
        raise RequestValidationError(
            [
                {**detail, "loc": ("body", *detail["loc"])}
                for detail in error.errors(include_url=False, include_context=False)
            ]
        ) from error


def _format_dialog_event(event: DialogEvent) -> str:
    data: dict[str, str | int]
    if event.type is DialogEventType.MESSAGE_DELTA:
        assert event.delta is not None
        data = {"delta": event.delta}
    elif event.type is DialogEventType.MESSAGE_ERROR:
        assert event.code is not None
        assert event.message is not None
        data = {"code": event.code, "message": event.message}
    elif event.type is DialogEventType.MESSAGE_END and event.message_id is not None:
        data = {"message_id": event.message_id}
    else:
        data = {}
    return _format_sse(event.type.value, data)


def _format_sse(event: str, data: dict[str, str | int]) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"
