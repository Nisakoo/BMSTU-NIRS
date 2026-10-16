from abc import ABC, abstractmethod
from datetime import datetime

from smeshariki_ai.admin.models import UserStatsSnapshot


class AdminStatsStore(ABC):
    @abstractmethod
    async def user_stats(self, since: datetime, limit: int) -> UserStatsSnapshot:
        """Count users for the window starting at ``since``.

        ``recent_users`` holds at most ``limit`` users ordered by their latest
        activity, falling back to the registration time, newest first. Raises
        ``AdminStatsUnavailableError`` when the backing storage fails.
        """
