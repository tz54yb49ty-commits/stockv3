from __future__ import annotations

from datetime import datetime

import pytest

from ashare_v3.runtime_control.windows_n4_outbox_restore import (
    OUTBOX_RESTORE_SELECT,
    WindowsN4OutboxReadOnlyRepository,
    build_windows_n4_outbox_restore_bundle,
)
from ashare_v3.trigger.event_factory import build_n4_trigger_event
from ashare_v3.trigger.windows_n4_state_transition import (
    RULE_POLICY_VERSION,
)


SOURCE_RUN_ID = "condition_layer_20260826_to_20260827_fixture"
TRADE_DATE = "20260827"


def _time(label: str) -> datetime:
    return datetime.fromisoformat(f"2026-08-27T{label}+08:00")


def _matched_event(
    asset_kind: str,
    identity_key: str,
    code: str,
    *,
    version: int,
):
    run_id = f"prior_n4_{asset_kind}_{version}"
    payload = {
        "rule_policy_version": RULE_POLICY_VERSION,
        "source_condition_run_id": SOURCE_RUN_ID,
        "source_trade_date": "20260826",
        "for_trade_date": TRADE_DATE,
        "code": code,
        "name": f"{asset_kind}-{code}",
        "n4_state_version": version,
        "source_n3_version": version,
        "source_transitions": {"D": "low_volume_down"},
        "source_amounts": {"W": "100"},
        "comparison_amounts": {"W": "100"},
        "realtime_transitions": {
            "D": "volume_up",
            "30m": "none",
        },
        "realtime_virtual_amounts": {"W": "110"},
        "current_price": "10",
        "cumulative_amount": "100000000",
        "provider": "fixture",
        "live_status": "available",
        "fresh": True,
        "effective_time": _time("09:35:05").isoformat(),
        "data_quality_status": "ready",
        "rule_flags": {
            "A": True,
            "B": False,
            "C": False,
            "D30": False,
        },
        "activation_sources": ["D"],
        "formal_triggered_periods": ["D"],
        "triggered_periods": ["D"],
        "all_trigger_periods": ["D"],
        "primary_trigger_period": "D",
        "projection_30m_flag": False,
        "projection_30m_type": "none",
        "trigger_live": True,
        "current_status": "matched",
        "episode_number": 1,
        "episode_entry_event_id": "pending",
    }
    arguments = {
        "event_type": "TriggerMatched",
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "trade_date": TRADE_DATE,
        "event_time": _time("09:35:05"),
        "trigger_run_id": run_id,
        "source_event_id": f"n4-memory:{identity_key}:{version}",
        "direction": "buy",
        "signal_type": "B_BUY",
        "condition_key": "BUY:STATE_V1",
        "trigger_mark_candidate": "normal",
        "trigger_period": "D",
        "trigger_bucket": "episode:1",
        "match_basis": f"{RULE_POLICY_VERSION}:D",
        "data_quality_status": "ready",
        "created_at": _time("09:35:05"),
    }
    first = build_n4_trigger_event(payload=payload, **arguments)
    payload["episode_entry_event_id"] = first.event_id
    return build_n4_trigger_event(payload=payload, **arguments)


class _FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.executions = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params):
        self.executions.append((sql, params))

    def fetchall(self):
        return self.rows


class _FakeConnection:
    def __init__(self, rows):
        self.cursor_value = _FakeCursor(rows)
        self.read_only = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def cursor(self):
        return self.cursor_value


def test_bundle_groups_three_channels_and_freezes_last_versions() -> None:
    events = (
        _matched_event(
            "stock",
            "stock:SZ:000001",
            "000001",
            version=7,
        ),
        _matched_event(
            "index",
            "index:SH:000001",
            "000001",
            version=4,
        ),
        _matched_event(
            "board",
            "board:SH:881333",
            "881333",
            version=9,
        ),
    )
    bundle = build_windows_n4_outbox_restore_bundle(
        (*events, events[0]),
        source_condition_run_id=SOURCE_RUN_ID,
        for_trade_date=TRADE_DATE,
    )
    assert {
        kind: len(bundle.events[kind])
        for kind in ("stock", "index", "board")
    } == {"stock": 1, "index": 1, "board": 1}
    assert dict(bundle.last_versions) == {
        "stock": 7,
        "index": 4,
        "board": 9,
    }

    empty = build_windows_n4_outbox_restore_bundle(
        (),
        source_condition_run_id=SOURCE_RUN_ID,
        for_trade_date=TRADE_DATE,
    )
    assert dict(empty.last_versions) == {
        "stock": 0,
        "index": 0,
        "board": 0,
    }


def test_bundle_rejects_wrong_lineage() -> None:
    event = _matched_event(
        "stock",
        "stock:SZ:000001",
        "000001",
        version=7,
    )
    with pytest.raises(ValueError, match="outside"):
        build_windows_n4_outbox_restore_bundle(
            (event,),
            source_condition_run_id="different-lineage",
            for_trade_date=TRADE_DATE,
        )


def test_repository_executes_one_read_only_select() -> None:
    event = _matched_event(
        "stock",
        "stock:SZ:000001",
        "000001",
        version=7,
    )
    row = {"outbox_id": 1, **event.as_record()}
    connection = _FakeConnection([row])
    connect_calls = []

    def connect(dsn, **kwargs):
        connect_calls.append((dsn, kwargs))
        return connection

    repository = WindowsN4OutboxReadOnlyRepository(
        "postgresql://fixture",
        connect=connect,
    )
    bundle = repository.load(
        source_condition_run_id=SOURCE_RUN_ID,
        for_trade_date=TRADE_DATE,
    )

    assert connection.read_only is True
    assert len(connection.cursor_value.executions) == 1
    sql, params = connection.cursor_value.executions[0]
    assert sql == OUTBOX_RESTORE_SELECT
    assert sql.lstrip().upper().startswith("SELECT ")
    assert not any(
        token in sql.upper()
        for token in ("INSERT ", "UPDATE ", "DELETE ", "ALTER ", "CREATE ")
    )
    assert params[0] == TRADE_DATE
    assert params[3] == SOURCE_RUN_ID
    assert dict(bundle.last_versions) == {
        "stock": 7,
        "index": 0,
        "board": 0,
    }
    assert connect_calls[0][0] == "postgresql://fixture"
