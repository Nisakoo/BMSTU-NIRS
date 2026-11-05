from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from uuid import UUID

from smeshariki_ai.admin.models import MessageReport, ReportStatus, UserStatsSnapshot


class AdminStatsStore(ABC):
    @abstractmethod
    async def user_stats(
        self,
        since: datetime,
        limit: int,
        *,
        bucket: timedelta = timedelta(days=1),
        buckets: int = 7,
    ) -> UserStatsSnapshot:
        """Count users and stories for the window starting at ``since``.

        ``activity`` holds the stories created in each of ``buckets`` buckets
        of length ``bucket``, oldest first.

        ``recent_users`` holds at most ``limit`` users ordered by their latest
        activity, falling back to the registration time, newest first. Raises
        ``AdminStatsUnavailableError`` when the backing storage fails.
        """


class ReportStore(ABC):
    @abstractmethod
    async def list_reports(
        self, status: ReportStatus | None, limit: int
    ) -> tuple[MessageReport, ...]:
        """Return at most ``limit`` reports, newest first; ``None`` means any status.

        Raises ``AdminStatsUnavailableError`` when the backing storage fails.
        """

    @abstractmethod
    async def set_status(
        self, report_id: int, status: ReportStatus, admin_id: UUID
    ) -> None:
        """Move a report to ``status``; closing records who and when, ``new`` clears it.

        Raises ``ReportNotFoundError`` for an unknown report.
        """
