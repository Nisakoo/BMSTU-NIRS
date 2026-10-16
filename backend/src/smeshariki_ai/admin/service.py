import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from smeshariki_ai.admin.models import (
    RecentUser,
    RecentUserStats,
    StatsPeriod,
    UserStats,
    UserStatus,
)
from smeshariki_ai.admin.stores import AdminStatsStore
from smeshariki_ai.observability import log_event

logger = logging.getLogger(__name__)

RECENT_USERS_LIMIT = 5


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
        snapshot = await self._store.user_stats(since, RECENT_USERS_LIMIT)
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
        )


def _status(user: RecentUser, since: datetime) -> UserStatus:
    if user.registered_at >= since:
        return UserStatus.NEW
    if user.last_active_at is not None and user.last_active_at >= since:
        return UserStatus.ACTIVE
    return UserStatus.INACTIVE
