from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from smeshariki_ai.auth import Role
from smeshariki_ai.dialogs import ReportReason


class AdminStatsUnavailableError(Exception):
    """The statistics storage failed; the caller must not show partial data."""


class StatsPeriod(StrEnum):
    DAYS_7 = "7"
    DAYS_30 = "30"
    DAYS_90 = "90"

    @property
    def days(self) -> int:
        return int(self.value)

    @property
    def buckets(self) -> int:
        """Columns of the activity chart: buckets of 1, 3 or 10 days."""

        return {"7": 7, "30": 10, "90": 9}[self.value]


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
    # Stories of the user, all time: dialogs with at least one message.
    dialogs: int = 0


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
    # Reports waiting for review, whatever the window.
    reports_new: int = 0
    # Stories created and messages sent in the window; empty dialogs do not count.
    dialogs: int = 0
    messages: int = 0
    # Stories created in each equal bucket of the window, oldest first.
    activity: tuple[int, ...] = ()


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
    reports_new: int = 0
    dialogs: int = 0
    messages: int = 0
    activity: tuple["ActivityPoint", ...] = ()


@dataclass(frozen=True, slots=True)
class ActivityPoint:
    """Stories created in the bucket of the window that starts at ``start``."""

    start: datetime
    dialogs: int


class ReportStatus(StrEnum):
    NEW = "new"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class ReportNotFoundError(Exception):
    def __init__(self, report_id: int) -> None:
        self.report_id = report_id
        super().__init__(f"Report not found: {report_id}")


@dataclass(frozen=True, slots=True)
class MessageReport:
    """A report as the administrator sees it: texts, but not its author."""

    id: int
    reason: ReportReason
    comment: str | None
    request_text: str | None
    answer_text: str
    status: ReportStatus
    created_at: datetime
    resolved_at: datetime | None
    # The user deleted the dialog; the copied texts remain.
    dialog_deleted: bool
