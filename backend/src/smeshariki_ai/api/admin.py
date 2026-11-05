"""Administrator-only HTTP routes; see docs/admin.md."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any

from fastapi import APIRouter, Depends, FastAPI, Request, Response, status
from pydantic import BaseModel, ConfigDict

from smeshariki_ai.admin import (
    AdminReportsService,
    AdminStatsService,
    AdminStatsUnavailableError,
    MessageReport,
    ReportNotFoundError,
    ReportStatus,
    StatsPeriod,
    UserStats,
)
from smeshariki_ai.api.auth import AuthHTTPError, current_admin, unavailable
from smeshariki_ai.api.schemas import DbIdPath
from smeshariki_ai.auth import User

# The role check runs before query validation, so guests get 401 and users 403.
router = APIRouter(prefix="/api/v1/admin", dependencies=[Depends(current_admin)])


class ReportFilter(StrEnum):
    NEW = "new"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"
    ALL = "all"


class ReportStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ReportStatus


def install_admin(
    app: FastAPI,
    admin_stats: AdminStatsService | None,
    admin_reports: AdminReportsService | None = None,
) -> None:
    app.state.admin_stats = admin_stats
    app.state.admin_reports = admin_reports
    app.include_router(router)


@router.get("/stats")
async def user_stats(request: Request, period: StatsPeriod) -> dict[str, Any]:
    service: AdminStatsService | None = request.app.state.admin_stats
    if service is None:
        raise unavailable()
    try:
        stats = await service.user_stats(period)
    except AdminStatsUnavailableError as error:
        raise unavailable() from error
    return _stats_body(stats)


@router.get("/reports")
async def list_reports(
    request: Request, status: ReportFilter = ReportFilter.NEW
) -> dict[str, Any]:
    service = _reports_service(request)
    try:
        reports = await service.list_reports(
            None if status is ReportFilter.ALL else ReportStatus(status.value)
        )
    except AdminStatsUnavailableError as error:
        raise unavailable() from error
    return {"reports": [_report_body(report) for report in reports]}


@router.patch(
    "/reports/{report_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def set_report_status(
    request: Request,
    report_id: DbIdPath,
    body: ReportStatusRequest,
    admin: Annotated[User, Depends(current_admin)],
) -> Response:
    service = _reports_service(request)
    try:
        await service.set_status(report_id, body.status, admin.id)
    except ReportNotFoundError as error:
        raise AuthHTTPError(status.HTTP_404_NOT_FOUND, "not_found") from error
    except AdminStatsUnavailableError as error:
        raise unavailable() from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _reports_service(request: Request) -> AdminReportsService:
    service: AdminReportsService | None = request.app.state.admin_reports
    if service is None:
        raise unavailable()
    return service


def _report_body(report: MessageReport) -> dict[str, Any]:
    return {
        "id": report.id,
        "reason": report.reason.value,
        "comment": report.comment,
        "request_text": report.request_text,
        "answer_text": report.answer_text,
        "status": report.status.value,
        "created_at": _timestamp(report.created_at),
        "resolved_at": None
        if report.resolved_at is None
        else _timestamp(report.resolved_at),
        "dialog_deleted": report.dialog_deleted,
    }


def _stats_body(stats: UserStats) -> dict[str, Any]:
    return {
        "period": stats.period.value,
        "users_total": stats.users_total,
        "active_users": stats.active_users,
        "new_users": stats.new_users,
        "recent_users": [
            {
                "id": str(entry.user.id),
                "login": entry.user.login,
                "role": entry.user.role.value,
                "registered_at": _timestamp(entry.user.registered_at),
                "last_active_at": None
                if entry.user.last_active_at is None
                else _timestamp(entry.user.last_active_at),
                "status": entry.status.value,
                "dialogs": entry.user.dialogs,
            }
            for entry in stats.recent_users
        ],
        "feedback": {
            "answers_total": stats.feedback.answers_total,
            "rated_answers": stats.feedback.rated_answers,
            "counts": list(stats.feedback.counts),
        },
        "reports_new": stats.reports_new,
        "dialogs": stats.dialogs,
        "messages": stats.messages,
        "activity": [
            {"start": _timestamp(point.start), "dialogs": point.dialogs}
            for point in stats.activity
        ],
    }


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
