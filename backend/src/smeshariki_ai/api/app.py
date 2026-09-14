from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import APIRouter, FastAPI, HTTPException, Response, status

from smeshariki_ai.agent import UserRequest
from smeshariki_ai.api.schemas import StartDialogResponse, SubmitMessageRequest
from smeshariki_ai.application import AgentService, AgentServiceUnavailableError
from smeshariki_ai.dialogs import DialogNotFoundError


def create_app(agent_service: AgentService) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await agent_service.shutdown()

    app = FastAPI(title="smeshariki-ai", lifespan=lifespan)
    app.state.agent_service = agent_service
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

    app.include_router(router)
    return app
