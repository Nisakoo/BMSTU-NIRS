import logging
from datetime import UTC, datetime
from uuid import UUID

import pytest

from smeshariki_ai.admin import (
    AdminReportsService,
    MessageReport,
    ReportNotFoundError,
    ReportStatus,
    ReportStore,
)
from smeshariki_ai.dialogs import ReportReason

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
ADMIN = UUID(int=7)

REPORT = MessageReport(
    id=1,
    reason=ReportReason.SCARY,
    comment="секретный комментарий",
    request_text="секретный вопрос",
    answer_text="секретный ответ",
    status=ReportStatus.NEW,
    created_at=NOW,
    resolved_at=None,
    dialog_deleted=False,
)


class RecordingStore(ReportStore):
    def __init__(self) -> None:
        self.listed: list[tuple[ReportStatus | None, int]] = []
        self.changed: list[tuple[int, ReportStatus, UUID]] = []

    async def list_reports(
        self, status: ReportStatus | None, limit: int
    ) -> tuple[MessageReport, ...]:
        self.listed.append((status, limit))
        return (REPORT,)

    async def set_status(
        self, report_id: int, status: ReportStatus, admin_id: UUID
    ) -> None:
        if report_id != REPORT.id:
            raise ReportNotFoundError(report_id)
        self.changed.append((report_id, status, admin_id))


@pytest.mark.asyncio
async def test_reports_are_listed_by_status_up_to_fifty() -> None:
    store = RecordingStore()
    service = AdminReportsService(store)

    assert await service.list_reports(ReportStatus.NEW) == (REPORT,)
    assert await service.list_reports(None) == (REPORT,)
    assert store.listed == [(ReportStatus.NEW, 50), (None, 50)]


@pytest.mark.asyncio
async def test_status_change_is_logged_without_texts(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="smeshariki_ai.admin.service")
    store = RecordingStore()
    service = AdminReportsService(store)

    await service.set_status(1, ReportStatus.RESOLVED, ADMIN)
    with pytest.raises(ReportNotFoundError):
        await service.set_status(2, ReportStatus.DISMISSED, ADMIN)

    assert store.changed == [(1, ReportStatus.RESOLVED, ADMIN)]
    [record] = [
        record
        for record in caplog.records
        if record.getMessage().startswith("admin.report.status_changed")
    ]
    assert (record.log_fields["report_id"], record.log_fields["status"]) == (
        1,
        "resolved",
    )
    assert "секретн" not in caplog.text
