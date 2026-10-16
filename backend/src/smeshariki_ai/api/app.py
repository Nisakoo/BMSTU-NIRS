import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from importlib.resources import files
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import ValidationError

from smeshariki_ai.admin import AdminStatsService
from smeshariki_ai.agent import UserRequest
from smeshariki_ai.api.admin import install_admin
from smeshariki_ai.api.auth import current_user, install_auth, install_auth_errors
from smeshariki_ai.api.schemas import StartDialogResponse, SubmitMessageRequest
from smeshariki_ai.application import (
    AgentService,
    AgentServiceUnavailableError,
    DialogEvent,
    DialogEventType,
)
from smeshariki_ai.auth import AuthService
from smeshariki_ai.dialogs import DialogNotFoundError
from smeshariki_ai.observability import RequestLogMiddleware

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
    async def start_dialog(response: Response) -> StartDialogResponse:
        try:
            dialog_id = await agent_service.start_dialog()
        except AgentServiceUnavailableError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Agent service is unavailable.",
            ) from error

        response.headers["Location"] = f"/api/v1/dialogs/{dialog_id}"
        return StartDialogResponse(dialog_id=dialog_id)

    @router.post(
        "/dialogs/{dialog_id}/messages",
        status_code=status.HTTP_202_ACCEPTED,
        response_class=Response,
    )
    async def submit_message(
        dialog_id: UUID,
        request: Request,
    ) -> Response:
        body = await _read_submit_request(request)
        try:
            await agent_service.submit(
                dialog_id,
                UserRequest(content=body.request),
            )
        except DialogNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dialog not found.",
            ) from error
        except AgentServiceUnavailableError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Agent service is unavailable.",
            ) from error

        return Response(status_code=status.HTTP_202_ACCEPTED)

    @router.get("/dialogs/{dialog_id}/events")
    async def stream_dialog_events(dialog_id: UUID) -> StreamingResponse:
        try:
            subscription = await agent_service.subscribe(dialog_id)
        except DialogNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dialog not found.",
            ) from error
        except AgentServiceUnavailableError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Agent service is unavailable.",
            ) from error

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
    install_admin(app, admin_stats)
    return app


async def _read_submit_request(request: Request) -> SubmitMessageRequest:
    # Parsed here rather than by FastAPI, which rejects malformed JSON before
    # running the authentication dependency.
    try:
        return SubmitMessageRequest.model_validate_json(await request.body())
    except ValidationError as error:
        raise RequestValidationError(
            [
                {**detail, "loc": ("body", *detail["loc"])}
                for detail in error.errors(include_url=False, include_context=False)
            ]
        ) from error


def _format_dialog_event(event: DialogEvent) -> str:
    if event.type is DialogEventType.MESSAGE_DELTA:
        assert event.delta is not None
        data: dict[str, str] = {"delta": event.delta}
    elif event.type is DialogEventType.MESSAGE_ERROR:
        assert event.code is not None
        assert event.message is not None
        data = {"code": event.code, "message": event.message}
    else:
        data = {}
    return _format_sse(event.type.value, data)


def _format_sse(event: str, data: dict[str, str]) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"
