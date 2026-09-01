from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from types import MappingProxyType, SimpleNamespace

import pytest

from ashare_v3.runtime_control import windows_n3_n4_n5_diagnostics
from ashare_v3.runtime_control.windows_n3_n4_n5_diagnostics import (
    WindowsN3N4N5DiagnosticWriter,
)
from ashare_v3.runtime_control.windows_n3_n4_n5_memory import (
    WindowsN3N4N5FinalizeResult,
)


ASSET_KINDS = ("stock", "index", "board")


@dataclass(frozen=True)
class _Key:
    identity_key: str
    direction: str
    episode_entry_event_id: str


@dataclass(frozen=True)
class _RuntimeState:
    identity_key: str
    direction: str
    metric_ready: bool
    metric_quality_status: str
    metric_error_summary: str
    metric_expected_minute_index: int
    metric_observed_minute_index: int
    metric_minute_label: str
    confirmation_checks: MappingProxyType
    confirmation_pending_reason: str


class _Summary:
    def __init__(self, minute_index: int = 7) -> None:
        self.completed_minute_index = minute_index
        self.action_metric_pending_reason_counts = {
            kind: {"expected_closed_minute_missing": 1}
            for kind in ASSET_KINDS
        }
        self.database_write_counts = {kind: 0 for kind in ASSET_KINDS}
        self.event_persistence_counts = {kind: 0 for kind in ASSET_KINDS}

    def as_dict(self):
        return {
            "completed_minute_index": self.completed_minute_index,
            "action_metric_pending_reason_counts": (
                self.action_metric_pending_reason_counts
            ),
            "database_write_counts": self.database_write_counts,
            "event_persistence_counts": self.event_persistence_counts,
            "session_finalized": True,
        }


def _episode_snapshot(kind: str, *, active: bool = True):
    key = _Key(
        identity_key=f"{kind}:SH:fixture",
        direction="buy",
        episode_entry_event_id=f"entry-{kind}",
    )
    state = _RuntimeState(
        identity_key=key.identity_key,
        direction="buy",
        metric_ready=False,
        metric_quality_status="pending",
        metric_error_summary=(
            "postgresql://ashare:secret@127.0.0.1/db "
            "password=hidden\ntrace"
        ),
        metric_expected_minute_index=7,
        metric_observed_minute_index=6,
        metric_minute_label="09:37",
        confirmation_checks=MappingProxyType(
            {
                "120m_price": None,
                "30m_price": None,
                "5m_price": None,
                "5m_amount": None,
                "1m_price": None,
                "1m_amount": None,
            }
        ),
        confirmation_pending_reason="expected_closed_minute_missing",
    )
    return SimpleNamespace(
        version=7,
        active=MappingProxyType({key: object()} if active else {}),
        runtime_states=MappingProxyType({key: state} if active else {}),
    )


def _bridge_snapshot():
    return SimpleNamespace(
        generated_at=datetime(2026, 9, 2, 9, 37, tzinfo=timezone.utc),
        n4_states={
            kind: SimpleNamespace(source_n4_version=7)
            for kind in ASSET_KINDS
        },
        n5_episodes={
            kind: _episode_snapshot(kind)
            for kind in ASSET_KINDS
        },
        action_confirmation={
            kind: {
                "status": "pending",
                "active_pending_count": 1,
                "requested_count": 1,
                "ready_count": 0,
                "pending_count": 1,
                "errors": (),
            }
            for kind in ASSET_KINDS
        },
        diagnostic={
            "status": "ready",
            "write_error_count": 0,
            "errors": (),
        },
    )


def test_confirmation_latest_is_atomic_once_per_closed_minute(tmp_path) -> None:
    writer = WindowsN3N4N5DiagnosticWriter(
        for_trade_date="20260902",
        started_at=datetime(2026, 9, 2, 9, 15, tzinfo=timezone.utc),
        root=tmp_path,
        process_id=1234,
    )
    snapshot = _bridge_snapshot()
    summary = _Summary(7)

    assert writer.write_confirmation_latest(snapshot, summary) is True
    assert writer.write_confirmation_latest(snapshot, summary) is False

    target = writer.run_directory / "confirmation-latest.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    stock = payload["channels"]["stock"]
    assert stock["action_confirmation"]["pending_reason_counts"] == {
        "expected_closed_minute_missing": 1,
    }
    assert stock["active_episodes"][0]["metric_ready"] is False
    assert "secret" not in target.read_text(encoding="utf-8")
    assert "hidden" not in target.read_text(encoding="utf-8")
    assert "<redacted>" in target.read_text(encoding="utf-8")
    assert [
        path
        for path in writer.run_directory.iterdir()
        if path.name.endswith(".tmp")
    ] == []

    summary.completed_minute_index = 8
    assert writer.write_confirmation_latest(snapshot, summary) is True
    assert json.loads(target.read_text(encoding="utf-8"))[
        "completed_minute_index"
    ] == 8


def test_failed_confirmation_write_is_not_retried_same_minute(
    tmp_path,
    monkeypatch,
) -> None:
    writer = WindowsN3N4N5DiagnosticWriter(
        for_trade_date="20260902",
        started_at=datetime(2026, 9, 2, 9, 15, tzinfo=timezone.utc),
        root=tmp_path,
        process_id=2468,
    )
    attempts = []

    def fail_write(path, payload):
        attempts.append((path, payload))
        raise OSError("fixture diagnostic write failure")

    monkeypatch.setattr(
        windows_n3_n4_n5_diagnostics,
        "_atomic_replace_json",
        fail_write,
    )

    with pytest.raises(OSError, match="fixture diagnostic write failure"):
        writer.write_confirmation_latest(_bridge_snapshot(), _Summary(7))

    assert writer.write_confirmation_latest(
        _bridge_snapshot(),
        _Summary(7),
    ) is False
    assert len(attempts) == 1
    assert list(writer.run_directory.iterdir()) == []


def test_session_final_is_no_replace_and_sha_bound(tmp_path) -> None:
    writer = WindowsN3N4N5DiagnosticWriter(
        for_trade_date="20260902",
        started_at=datetime(2026, 9, 2, 9, 15, tzinfo=timezone.utc),
        root=tmp_path,
        process_id=5678,
    )
    pre = {kind: _episode_snapshot(kind) for kind in ASSET_KINDS}
    post = {
        kind: _episode_snapshot(kind, active=False)
        for kind in ASSET_KINDS
    }
    events = {
        kind: (
            SimpleNamespace(
                event_type="ActionSkipped",
                payload_json={"skipped_reason": "window_expired"},
            ),
        )
        for kind in ASSET_KINDS
    }
    finalization = WindowsN3N4N5FinalizeResult(
        observed_at=datetime(2026, 9, 2, 15, 0, 1, tzinfo=timezone.utc),
        pre_finalize_snapshots=pre,
        post_finalize_snapshots=post,
        action_events=events,
    )

    target = writer.write_session_final(finalization, _Summary(240))

    encoded = target.read_bytes()
    sidecar = (writer.run_directory / "session-final.sha256").read_text(
        encoding="ascii"
    )
    assert sidecar == (
        hashlib.sha256(encoded).hexdigest()
        + "  session-final.json\n"
    )
    payload = json.loads(encoded)
    for kind in ASSET_KINDS:
        assert payload["channels"][kind][
            "pre_finalize_active_count"
        ] == 1
        assert payload["channels"][kind][
            "window_expired_event_count"
        ] == 1
        assert payload["channels"][kind][
            "post_finalize_active_count"
        ] == 0
    with pytest.raises(FileExistsError):
        writer.write_session_final(finalization, _Summary(240))
