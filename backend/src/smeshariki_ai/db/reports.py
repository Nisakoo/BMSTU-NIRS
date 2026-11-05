from uuid import UUID

from asyncpg import PostgresError
from sqlalchemy import func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from smeshariki_ai.admin import (
    AdminStatsUnavailableError,
    MessageReport,
    ReportNotFoundError,
    ReportStatus,
    ReportStore,
)
from smeshariki_ai.db.tables import message_reports
from smeshariki_ai.dialogs import ReportReason

_FAILURES = (SQLAlchemyError, PostgresError, OSError, TimeoutError)


class PostgresReportStore(ReportStore):
    """Reports on answers; the author's id stays in the table and out of the result."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def list_reports(
        self, status: ReportStatus | None, limit: int
    ) -> tuple[MessageReport, ...]:
        statement = (
            select(
                message_reports.c.id,
                message_reports.c.reason,
                message_reports.c.comment,
                message_reports.c.request_text,
                message_reports.c.answer_text,
                message_reports.c.status,
                message_reports.c.created_at,
                message_reports.c.resolved_at,
                message_reports.c.message_id.is_(None).label("dialog_deleted"),
            )
            .order_by(message_reports.c.created_at.desc(), message_reports.c.id.desc())
            .limit(limit)
        )
        if status is not None:
            statement = statement.where(message_reports.c.status == status.value)
        try:
            async with self._engine.connect() as connection:
                rows = (await connection.execute(statement)).all()
        except _FAILURES as error:
            raise AdminStatsUnavailableError from error
        return tuple(
            MessageReport(
                id=row.id,
                reason=ReportReason(row.reason),
                comment=row.comment,
                request_text=row.request_text,
                answer_text=row.answer_text,
                status=ReportStatus(row.status),
                created_at=row.created_at,
                resolved_at=row.resolved_at,
                dialog_deleted=row.dialog_deleted,
            )
            for row in rows
        )

    async def set_status(
        self, report_id: int, status: ReportStatus, admin_id: UUID
    ) -> None:
        reopened = status is ReportStatus.NEW
        statement = (
            update(message_reports)
            .where(message_reports.c.id == report_id)
            .values(
                status=status.value,
                resolved_at=None if reopened else func.now(),
                resolved_by=None if reopened else admin_id,
                # A report reviewed again is news to the user again.
                **({"seen_at": None} if reopened else {}),
            )
        )
        try:
            async with self._engine.begin() as connection:
                result = await connection.execute(statement)
        except _FAILURES as error:
            raise AdminStatsUnavailableError from error
        if result.rowcount == 0:
            raise ReportNotFoundError(report_id)
