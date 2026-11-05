from datetime import datetime, timedelta

from asyncpg import PostgresError
from sqlalchemy import DateTime, bindparam, distinct, exists, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from smeshariki_ai.admin import (
    AdminStatsStore,
    AdminStatsUnavailableError,
    FeedbackStats,
    RecentUser,
    UserStatsSnapshot,
)
from smeshariki_ai.agent import MessageRole
from smeshariki_ai.auth import Role
from smeshariki_ai.db.tables import (
    dialogs,
    message_feedback,
    message_reports,
    messages,
    refresh_sessions,
    users,
)
from smeshariki_ai.dialogs import MAX_SCORE, MIN_SCORE

SCORES = range(MIN_SCORE, MAX_SCORE + 1)


class PostgresAdminStatsStore(AdminStatsStore):
    """Counts users and their activity; a refresh session marks one activity."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def user_stats(
        self,
        since: datetime,
        limit: int,
        *,
        bucket: timedelta = timedelta(days=1),
        buckets: int = 7,
    ) -> UserStatsSnapshot:
        counts = select(
            select(func.count()).select_from(users).scalar_subquery(),
            select(func.count())
            .select_from(users)
            .where(users.c.created_at >= since)
            .scalar_subquery(),
            select(func.count(distinct(refresh_sessions.c.user_id)))
            .where(refresh_sessions.c.created_at >= since)
            .scalar_subquery(),
        )
        last_activity = (
            select(
                refresh_sessions.c.user_id,
                func.max(refresh_sessions.c.created_at).label("last_active_at"),
            )
            .group_by(refresh_sessions.c.user_id)
            .subquery()
        )
        # A story is a dialog with a message; opening the chat creates empty ones.
        story = exists().where(messages.c.dialog_id == dialogs.c.id)
        stories_of_user = (
            select(dialogs.c.user_id, func.count().label("dialogs"))
            .where(story)
            .group_by(dialogs.c.user_id)
            .subquery()
        )
        recent = (
            select(
                users.c.id,
                users.c.login,
                users.c.role,
                users.c.created_at,
                last_activity.c.last_active_at,
                func.coalesce(stories_of_user.c.dialogs, 0).label("dialogs"),
            )
            .outerjoin(last_activity, last_activity.c.user_id == users.c.id)
            .outerjoin(stories_of_user, stories_of_user.c.user_id == users.c.id)
            .order_by(
                func.coalesce(
                    last_activity.c.last_active_at, users.c.created_at
                ).desc(),
                users.c.id,
            )
            .limit(limit)
        )
        # Ratings count against answers created in the window.
        answers_in_window = (
            messages.c.role == MessageRole.ASSISTANT.value,
            messages.c.created_at >= since,
        )
        feedback = select(
            select(func.count())
            .select_from(messages)
            .where(*answers_in_window)
            .scalar_subquery(),
            select(
                func.count(),
                *(
                    func.count().filter(message_feedback.c.score == score)
                    for score in SCORES
                ),
            )
            .select_from(
                message_feedback.join(
                    messages, messages.c.id == message_feedback.c.message_id
                )
            )
            .where(*answers_in_window)
            .subquery(),
        )
        start = bindparam("since", since, type_=DateTime(timezone=True))
        stories = select(
            select(func.count())
            .select_from(dialogs)
            .where(story, dialogs.c.created_at >= start)
            .scalar_subquery(),
            select(func.count())
            .select_from(messages)
            .where(messages.c.created_at >= start)
            .scalar_subquery(),
        )
        position = func.least(
            func.floor(
                func.extract("epoch", dialogs.c.created_at - start)
                / bucket.total_seconds()
            ),
            buckets - 1,
        ).label("position")
        activity = (
            select(position, func.count())
            .where(story, dialogs.c.created_at >= start)
            .group_by(position)
        )
        reports_new = (
            select(func.count())
            .select_from(message_reports)
            .where(message_reports.c.status == "new")
        )
        try:
            async with self._engine.connect() as connection:
                users_total, new_users, active_users = (
                    await connection.execute(counts)
                ).one()
                waiting = await connection.scalar(reports_new)
                story_count, message_count = (await connection.execute(stories)).one()
                per_bucket = {
                    int(index): count
                    for index, count in await connection.execute(activity)
                }
                rows = (await connection.execute(recent)).all()
                answers_total, rated, *counts = (
                    await connection.execute(feedback)
                ).one()
        except (SQLAlchemyError, PostgresError, OSError, TimeoutError) as error:
            raise AdminStatsUnavailableError from error

        return UserStatsSnapshot(
            users_total=users_total,
            new_users=new_users,
            active_users=active_users,
            recent_users=tuple(
                RecentUser(
                    id=row.id,
                    login=row.login,
                    role=Role(row.role),
                    registered_at=row.created_at,
                    last_active_at=row.last_active_at,
                    dialogs=row.dialogs,
                )
                for row in rows
            ),
            feedback=FeedbackStats(
                answers_total=answers_total,
                rated_answers=rated,
                counts=tuple(counts),
            ),
            reports_new=waiting,
            dialogs=story_count,
            messages=message_count,
            activity=tuple(per_bucket.get(index, 0) for index in range(buckets)),
        )
