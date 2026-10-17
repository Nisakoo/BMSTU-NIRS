import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from smeshariki_ai.dialogs import DRAFT_TTL, DialogDrafts

OWNER_ID = UUID(int=1)
START = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def drafts(clock: Clock) -> DialogDrafts:
    return DialogDrafts(clock=clock)


def test_ttl_is_thirty_minutes() -> None:
    assert DRAFT_TTL == timedelta(minutes=30)


def test_create_returns_unique_uuid4_with_owner(drafts: DialogDrafts) -> None:
    first = drafts.create(OWNER_ID)
    second = drafts.create(UUID(int=2))

    assert first.version == 4
    assert first != second
    assert drafts.owner(first) == OWNER_ID
    assert drafts.owner(second) == UUID(int=2)
    assert drafts.owner(UUID(int=99)) is None


def test_idle_draft_expires_after_ttl(drafts: DialogDrafts, clock: Clock) -> None:
    dialog_id = drafts.create(OWNER_ID)

    clock.advance(DRAFT_TTL - timedelta(seconds=1))
    assert drafts.owner(dialog_id) == OWNER_ID
    clock.advance(timedelta(seconds=1))
    assert drafts.owner(dialog_id) is None


def test_active_subscription_prevents_expiry(
    drafts: DialogDrafts, clock: Clock
) -> None:
    dialog_id = drafts.create(OWNER_ID)
    drafts.attach(dialog_id)

    clock.advance(DRAFT_TTL * 3)
    assert drafts.owner(dialog_id) == OWNER_ID

    drafts.detach(dialog_id)
    clock.advance(DRAFT_TTL - timedelta(seconds=1))
    assert drafts.owner(dialog_id) == OWNER_ID
    clock.advance(timedelta(seconds=1))
    assert drafts.owner(dialog_id) is None


def test_active_run_prevents_expiry(drafts: DialogDrafts, clock: Clock) -> None:
    dialog_id = drafts.create(OWNER_ID)
    drafts.run_started(dialog_id)

    clock.advance(DRAFT_TTL * 2)
    assert drafts.owner(dialog_id) == OWNER_ID

    drafts.run_finished(dialog_id)
    clock.advance(DRAFT_TTL)
    assert drafts.owner(dialog_id) is None


def test_reconnect_within_ttl_keeps_draft(drafts: DialogDrafts, clock: Clock) -> None:
    dialog_id = drafts.create(OWNER_ID)
    drafts.attach(dialog_id)
    drafts.detach(dialog_id)

    clock.advance(timedelta(minutes=29))
    drafts.attach(dialog_id)

    clock.advance(timedelta(minutes=29))
    assert drafts.owner(dialog_id) == OWNER_ID


def test_counters_do_not_go_negative(drafts: DialogDrafts) -> None:
    dialog_id = drafts.create(OWNER_ID)

    drafts.detach(dialog_id)
    drafts.run_finished(dialog_id)
    drafts.attach(dialog_id)

    assert drafts.owner(dialog_id) == OWNER_ID


def test_discard_removes_draft_and_tolerates_unknown(drafts: DialogDrafts) -> None:
    dialog_id = drafts.create(OWNER_ID)

    drafts.discard(dialog_id)
    drafts.discard(dialog_id)
    drafts.attach(dialog_id)
    drafts.run_started(dialog_id)

    assert drafts.owner(dialog_id) is None


def test_create_sweeps_expired_drafts_and_logs_without_owner(
    drafts: DialogDrafts, clock: Clock, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="smeshariki_ai.dialogs.drafts")
    stale = drafts.create(OWNER_ID)
    clock.advance(DRAFT_TTL)

    drafts.create(OWNER_ID)

    assert drafts.owner(stale) is None
    (record,) = caplog.records
    assert record.getMessage() == f"dialog.draft.expired dialog_id={stale}"
