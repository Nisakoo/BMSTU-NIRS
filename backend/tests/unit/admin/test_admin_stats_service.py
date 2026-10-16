from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from smeshariki_ai.admin import (
    AdminStatsService,
    AdminStatsStore,
    RecentUser,
    StatsPeriod,
    UserStatsSnapshot,
    UserStatus,
)
from smeshariki_ai.auth import Role

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)


class RecordingStore(AdminStatsStore):
    def __init__(self, snapshot: UserStatsSnapshot) -> None:
        self.snapshot = snapshot
        self.calls: list[tuple[datetime, int]] = []

    async def user_stats(self, since: datetime, limit: int) -> UserStatsSnapshot:
        self.calls.append((since, limit))
        return self.snapshot


def recent(
    number: int,
    *,
    registered_days_ago: float,
    active_days_ago: float | None,
) -> RecentUser:
    return RecentUser(
        id=UUID(int=number),
        login=f"user{number}",
        role=Role.USER,
        registered_at=NOW - timedelta(days=registered_days_ago),
        last_active_at=None
        if active_days_ago is None
        else NOW - timedelta(days=active_days_ago),
    )


def make_service(
    snapshot: UserStatsSnapshot,
) -> tuple[AdminStatsService, RecordingStore]:
    store = RecordingStore(snapshot)
    return AdminStatsService(store, clock=lambda: NOW), store


@pytest.mark.parametrize(
    ("period", "days"),
    [(StatsPeriod.DAYS_7, 7), (StatsPeriod.DAYS_30, 30), (StatsPeriod.DAYS_90, 90)],
)
async def test_window_starts_period_days_before_now(
    period: StatsPeriod, days: int
) -> None:
    service, store = make_service(UserStatsSnapshot(0, 0, 0, ()))

    stats = await service.user_stats(period)

    assert store.calls == [(NOW - timedelta(days=days), 5)]
    assert stats.period is period


async def test_counts_are_passed_through_and_statuses_follow_the_window() -> None:
    snapshot = UserStatsSnapshot(
        users_total=40,
        new_users=2,
        active_users=7,
        recent_users=(
            recent(1, registered_days_ago=1, active_days_ago=0.5),
            recent(2, registered_days_ago=100, active_days_ago=3),
            recent(3, registered_days_ago=100, active_days_ago=8),
            recent(4, registered_days_ago=6, active_days_ago=None),
            recent(5, registered_days_ago=200, active_days_ago=None),
        ),
    )
    service, _ = make_service(snapshot)

    stats = await service.user_stats(StatsPeriod.DAYS_7)

    assert (stats.users_total, stats.new_users, stats.active_users) == (40, 2, 7)
    assert [entry.user.login for entry in stats.recent_users] == [
        "user1",
        "user2",
        "user3",
        "user4",
        "user5",
    ]
    assert [entry.status for entry in stats.recent_users] == [
        UserStatus.NEW,
        UserStatus.ACTIVE,
        UserStatus.INACTIVE,
        UserStatus.NEW,
        UserStatus.INACTIVE,
    ]


async def test_longer_period_turns_older_activity_into_active() -> None:
    snapshot = UserStatsSnapshot(
        1, 0, 1, (recent(3, registered_days_ago=100, active_days_ago=8),)
    )
    service, _ = make_service(snapshot)

    stats = await service.user_stats(StatsPeriod.DAYS_30)

    assert stats.recent_users[0].status is UserStatus.ACTIVE
