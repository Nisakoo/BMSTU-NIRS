"""Administrator-only HTTP routes; see docs/admin.md."""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, Request

from smeshariki_ai.admin import (
    AdminStatsService,
    AdminStatsUnavailableError,
    StatsPeriod,
    UserStats,
)
from smeshariki_ai.api.auth import current_admin, unavailable

# The role check runs before query validation, so guests get 401 and users 403.
router = APIRouter(prefix="/api/v1/admin", dependencies=[Depends(current_admin)])


def install_admin(app: FastAPI, admin_stats: AdminStatsService | None) -> None:
    app.state.admin_stats = admin_stats
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
            }
            for entry in stats.recent_users
        ],
        "feedback": {
            "answers_total": stats.feedback.answers_total,
            "rated_answers": stats.feedback.rated_answers,
            "counts": list(stats.feedback.counts),
        },
    }


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
