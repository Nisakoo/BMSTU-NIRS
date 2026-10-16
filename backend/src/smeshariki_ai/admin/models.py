from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from smeshariki_ai.auth import Role


class AdminStatsUnavailableError(Exception):
    """The statistics storage failed; the caller must not show partial data."""


class StatsPeriod(StrEnum):
    DAYS_7 = "7"
    DAYS_30 = "30"
    DAYS_90 = "90"

    @property
    def days(self) -> int:
        return int(self.value)


class UserStatus(StrEnum):
    NEW = "new"
    ACTIVE = "active"
    INACTIVE = "inactive"


@dataclass(frozen=True, slots=True)
class RecentUser:
    id: UUID
    login: str
    role: Role
    registered_at: datetime
    # Creation time of the latest refresh session: a login or a session renewal.
    last_active_at: datetime | None


@dataclass(frozen=True, slots=True)
class UserStatsSnapshot:
    """Raw figures for one window, as counted by the storage."""

    users_total: int
    new_users: int
    active_users: int
    recent_users: tuple[RecentUser, ...]


@dataclass(frozen=True, slots=True)
class RecentUserStats:
    user: RecentUser
    status: UserStatus


@dataclass(frozen=True, slots=True)
class UserStats:
    period: StatsPeriod
    users_total: int
    new_users: int
    active_users: int
    recent_users: tuple[RecentUserStats, ...]
