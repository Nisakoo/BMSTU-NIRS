import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.resources import files
from uuid import UUID

from fastapi import APIRouter, FastAPI, HTTPException, Response, status
from fastapi.responses import HTMLResponse, StreamingResponse

from smeshariki_ai.agent import UserRequest
from smeshariki_ai.api.schemas import StartDialogResponse, SubmitMessageRequest
from smeshariki_ai.application import (
    AgentService,
    AgentServiceUnavailableError,
    DialogEvent,
    DialogEventType,
)
from smeshariki_ai.dialogs import DialogNotFoundError

AGENT_TEST_HTML = (
    files("smeshariki_ai.api").joinpath("agent_test.html").read_text(encoding="utf-8")
)


def create_app(
    agent_service: AgentService,
    *,
    heartbeat_seconds: float = 15.0,
) -> FastAPI:
    if heartbeat_seconds <= 0:
        raise ValueError("heartbeat_seconds must be positive")

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await agent_service.shutdown()

    app = FastAPI(title="smeshariki-ai", lifespan=lifespan)
    app.state.agent_service = agent_service

    @app.get("/agent_test", response_class=HTMLResponse, include_in_schema=False)
    async def agent_test() -> HTMLResponse:
        return HTMLResponse(AGENT_TEST_HTML)

    router = APIRouter(prefix="/api/v1")

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
        body: SubmitMessageRequest,
    ) -> Response:
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
    return app


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
