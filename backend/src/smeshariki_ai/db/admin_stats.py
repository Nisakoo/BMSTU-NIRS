from datetime import datetime

from asyncpg import PostgresError
from sqlalchemy import distinct, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from smeshariki_ai.admin import (
    AdminStatsStore,
    AdminStatsUnavailableError,
    RecentUser,
    UserStatsSnapshot,
)
from smeshariki_ai.auth import Role
from smeshariki_ai.db.tables import refresh_sessions, users


class PostgresAdminStatsStore(AdminStatsStore):
    """Counts users and their activity; a refresh session marks one activity."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def user_stats(self, since: datetime, limit: int) -> UserStatsSnapshot:
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
        recent = (
            select(
                users.c.id,
                users.c.login,
                users.c.role,
                users.c.created_at,
                last_activity.c.last_active_at,
            )
            .outerjoin(last_activity, last_activity.c.user_id == users.c.id)
            .order_by(
                func.coalesce(
                    last_activity.c.last_active_at, users.c.created_at
                ).desc(),
                users.c.id,
            )
            .limit(limit)
        )
        try:
            async with self._engine.connect() as connection:
                users_total, new_users, active_users = (
                    await connection.execute(counts)
                ).one()
                rows = (await connection.execute(recent)).all()
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
                )
                for row in rows
            ),
        )
