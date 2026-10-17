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
class FeedbackStats:
    """Ratings of assistant answers created in the window.

    ``counts[i]`` is the number of answers rated ``i + 1`` out of 5.
    """

    answers_total: int
    rated_answers: int
    counts: tuple[int, ...]


NO_FEEDBACK = FeedbackStats(answers_total=0, rated_answers=0, counts=(0,) * 5)


@dataclass(frozen=True, slots=True)
class UserStatsSnapshot:
    """Raw figures for one window, as counted by the storage."""

    users_total: int
    new_users: int
    active_users: int
    recent_users: tuple[RecentUser, ...]
    feedback: FeedbackStats = NO_FEEDBACK


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
    feedback: FeedbackStats = NO_FEEDBACK
