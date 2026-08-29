from __future__ import annotations

from pathlib import Path

import pytest

from ashare_v3.trigger.windows_n4_state_transition import (
    WindowsN4StateTransitionPlanner,
)
from ashare_v3.trigger.windows_n4_transaction import (
    WindowsN4TransactionCoordinator,
)
from tests.test_windows_n4_delivery import _FakeCursor, _runtime_snapshot


class _CursorContext:
    def __init__(self, cursor: _FakeCursor) -> None:
        self.cursor = cursor

    def __enter__(self) -> _FakeCursor:
        return self.cursor

    def __exit__(self, _exc_type, _exc, _traceback) -> bool:
        return False


class _TransactionContext:
    def __init__(self, connection: "_FakeConnection") -> None:
        self.connection = connection
        self._before = None

    def __enter__(self) -> "_TransactionContext":
        cursor = self.connection.fake_cursor
        self.connection.begin_count += 1
        self._before = (
            set(cursor.event_ids),
            set(cursor.dedup_keys),
            dict(cursor.rows),
            dict(cursor.dedup_event_ids),
            cursor.next_outbox_id,
        )
        return self

    def __exit__(self, exc_type, _exc, _traceback) -> bool:
        if exc_type is not None or self.connection.fail_commit:
            assert self._before is not None
            cursor = self.connection.fake_cursor
            (
                cursor.event_ids,
                cursor.dedup_keys,
                cursor.rows,
                cursor.dedup_event_ids,
                cursor.next_outbox_id,
            ) = self._before
            self.connection.rollback_count += 1
            if exc_type is None:
                raise RuntimeError("fixture commit failure")
            return False
        self.connection.commit_count += 1
        return False


class _FakeConnection:
    def __init__(self, *, fail_commit: bool = False) -> None:
        self.fake_cursor = _FakeCursor()
        self.fail_commit = fail_commit
        self.begin_count = 0
        self.commit_count = 0
        self.rollback_count = 0

    def transaction(self) -> _TransactionContext:
        return _TransactionContext(self)

    def cursor(self) -> _CursorContext:
        return _CursorContext(self.fake_cursor)


def _planner(asset_kind: str) -> WindowsN4StateTransitionPlanner:
    return WindowsN4StateTransitionPlanner(
        asset_kind=asset_kind,
        trigger_run_id=f"windows_n4_transaction_{asset_kind}",
    )


def _coordinator() -> WindowsN4TransactionCoordinator:
    return WindowsN4TransactionCoordinator(
        json_adapter=lambda value: value,
    )


@pytest.mark.parametrize("asset_kind", ("stock", "index", "board"))
def test_commit_exposes_authoritative_row_and_candidate_for_each_channel(
    asset_kind: str,
) -> None:
    planner = _planner(asset_kind)
    connection = _FakeConnection()

    committed = _coordinator().deliver(
        connection,
        planner=planner,
        runtime_snapshot=_runtime_snapshot(asset_kind),
    )

    with pytest.raises(RuntimeError, match="no N4 snapshot"):
        planner.read()
    assert committed.planner.read() == committed.snapshot
    assert committed.outbox_rows[0].outbox_id == 1
    assert committed.outbox_rows[0].event == committed.output_events[0]
    assert committed.persistence.outbox_insert_count == 1
    assert connection.begin_count == 1
    assert connection.commit_count == 1
    assert connection.rollback_count == 0

    replay = _coordinator().deliver(
        connection,
        planner=planner,
        runtime_snapshot=_runtime_snapshot(asset_kind),
    )
    assert replay.persistence.outbox_insert_count == 0
    assert replay.outbox_rows == committed.outbox_rows


@pytest.mark.parametrize("asset_kind", ("stock", "index", "board"))
def test_commit_failure_keeps_original_and_retry_identity_stable(
    asset_kind: str,
) -> None:
    planner = _planner(asset_kind)
    snapshot = _runtime_snapshot(asset_kind)
    failed_connection = _FakeConnection(fail_commit=True)

    with pytest.raises(RuntimeError, match="fixture commit failure"):
        _coordinator().deliver(
            failed_connection,
            planner=planner,
            runtime_snapshot=snapshot,
        )

    with pytest.raises(RuntimeError, match="no N4 snapshot"):
        planner.read()
    assert failed_connection.fake_cursor.rows == {}
    assert failed_connection.commit_count == 0
    assert failed_connection.rollback_count == 1
    failed_insert = failed_connection.fake_cursor.calls[0][1]

    retry_connection = _FakeConnection()
    committed = _coordinator().deliver(
        retry_connection,
        planner=planner,
        runtime_snapshot=snapshot,
    )
    retry_insert = retry_connection.fake_cursor.calls[0][1]

    assert failed_insert[0] == retry_insert[0]
    assert failed_insert[9] == retry_insert[9]
    assert committed.output_events[0].event_id == retry_insert[0]
    assert committed.outbox_rows[0].outbox_id == 1


def test_transaction_module_has_no_cross_layer_or_external_runtime_boundary() -> None:
    source = Path(
        "src/ashare_v3/trigger/windows_n4_transaction.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "psycopg.connect",
        ".commit(",
        "eltdx",
        "ashare_v3.action",
        "ashare_v3.user",
        "Register-ScheduledTask",
    ):
        assert forbidden not in source
