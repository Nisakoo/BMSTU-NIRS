import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from smeshariki_ai.admin.models import (
    ActivityPoint,
    MessageReport,
    RecentUser,
    RecentUserStats,
    ReportStatus,
    StatsPeriod,
    UserStats,
    UserStatus,
)
from smeshariki_ai.admin.stores import AdminStatsStore, ReportStore
from smeshariki_ai.observability import log_event

logger = logging.getLogger(__name__)

RECENT_USERS_LIMIT = 5
REPORTS_LIMIT = 50


class AdminStatsService:
    """User statistics for the admin panel; transport and storage independent."""

    def __init__(
        self,
        store: AdminStatsStore,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._clock = clock or (lambda: datetime.now(UTC))

    async def user_stats(self, period: StatsPeriod) -> UserStats:
        since = self._clock() - timedelta(days=period.days)
        bucket = timedelta(days=period.days / period.buckets)
        snapshot = await self._store.user_stats(
            since, RECENT_USERS_LIMIT, bucket=bucket, buckets=period.buckets
        )
        log_event(logger, logging.INFO, "admin.stats.served")
        return UserStats(
            period=period,
            users_total=snapshot.users_total,
            new_users=snapshot.new_users,
            active_users=snapshot.active_users,
            recent_users=tuple(
                RecentUserStats(user, _status(user, since))
                for user in snapshot.recent_users
            ),
            feedback=snapshot.feedback,
            reports_new=snapshot.reports_new,
            dialogs=snapshot.dialogs,
            messages=snapshot.messages,
            activity=tuple(
                ActivityPoint(start=since + bucket * index, dialogs=count)
                for index, count in enumerate(snapshot.activity)
            ),
        )


class AdminReportsService:
    """Reports on assistant answers for the admin panel; texts are never logged."""

    def __init__(self, store: ReportStore) -> None:
        self._store = store

    async def list_reports(
        self, status: ReportStatus | None
    ) -> tuple[MessageReport, ...]:
        return await self._store.list_reports(status, REPORTS_LIMIT)

    async def set_status(
        self, report_id: int, status: ReportStatus, admin_id: UUID
    ) -> None:
        await self._store.set_status(report_id, status, admin_id)
        log_event(
            logger,
            logging.INFO,
            "admin.report.status_changed",
            report_id=report_id,
            status=status.value,
        )


def _status(user: RecentUser, since: datetime) -> UserStatus:
    if user.registered_at >= since:
        return UserStatus.NEW
    if user.last_active_at is not None and user.last_active_at >= since:
        return UserStatus.ACTIVE
    return UserStatus.INACTIVE
