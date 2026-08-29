from __future__ import annotations

from pathlib import Path
from types import MappingProxyType

import pytest

from ashare_v3.trigger.windows_n4_delivery import (
    persist_windows_n4_delivery,
    plan_windows_n4_delivery,
)
from ashare_v3.trigger.windows_n4_memory import (
    BoardRuntimeState,
    IndexRuntimeState,
    RuntimeStateSnapshot,
    StockRuntimeState,
)
from ashare_v3.trigger.windows_n4_state_transition import (
    WindowsN4StateTransitionPlanner,
)
from tests.test_windows_n4_state_transition import (
    SOURCE_RUN_ID,
    _state,
    _time,
)


STATE_TYPES = {
    "stock": StockRuntimeState,
    "index": IndexRuntimeState,
    "board": BoardRuntimeState,
}
IDENTITIES = {
    "stock": ("stock:SZ:000001", "SZ", "000001"),
    "index": ("index:SH:000001", "SH", "000001"),
    "board": ("board:SH:881001", "SH", "881001"),
}


class _FakeCursor:
    def __init__(self) -> None:
        self.event_ids: set[str] = set()
        self.dedup_keys: set[str] = set()
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self._returned = None

    def execute(self, query, params) -> None:
        sql = " ".join(str(query).split())
        values = tuple(params)
        self.calls.append((sql, values))
        self._returned = None
        assert "INSERT INTO common_event_outbox" in sql
        assert "ON CONFLICT DO NOTHING" in sql
        event_id = str(values[0])
        dedup_key = str(values[9])
        if event_id in self.event_ids or dedup_key in self.dedup_keys:
            return
        self.event_ids.add(event_id)
        self.dedup_keys.add(dedup_key)
        self._returned = (event_id,)

    def fetchone(self):
        return self._returned


def _runtime_snapshot(
    asset_kind: str,
    *,
    version: int = 1,
    live_30m: str = "none",
) -> RuntimeStateSnapshot:
    identity_key, exchange, code = IDENTITIES[asset_kind]
    stock = _state(
        version=version,
        observed_at=_time("09:35"),
        source_d="low_volume_down",
        live_d="volume_up",
        source_w="10",
        live_w="11",
        live_30m=live_30m,
    )
    values = {
        field: getattr(stock, field)
        for field in stock.__dataclass_fields__
    }
    values.update(
        asset_kind=asset_kind,
        identity_key=identity_key,
        exchange=exchange,
        code=code,
        name=f"{asset_kind}-{code}",
    )
    state = STATE_TYPES[asset_kind](**values)
    return RuntimeStateSnapshot(
        source_condition_run_id=SOURCE_RUN_ID,
        source_trade_date="20260826",
        for_trade_date="20260827",
        version=version,
        source_n3_version=version,
        generated_at=_time("09:35"),
        channel_status="ready",
        states=MappingProxyType({identity_key: state}),
    )


@pytest.mark.parametrize("asset_kind", ("stock", "index", "board"))
def test_candidate_persists_idempotently_before_postcommit_adoption(
    asset_kind: str,
) -> None:
    planner = WindowsN4StateTransitionPlanner(
        asset_kind=asset_kind,
        trigger_run_id=f"windows_n4_delivery_{asset_kind}",
    )
    plan = plan_windows_n4_delivery(
        planner,
        _runtime_snapshot(asset_kind),
    )

    with pytest.raises(RuntimeError, match="no N4 snapshot"):
        planner.read()
    assert [event.event_type for event in plan.output_events] == [
        "TriggerMatched"
    ]

    cursor = _FakeCursor()
    first = persist_windows_n4_delivery(
        cursor,
        plan=plan,
        json_adapter=lambda value: value,
    )
    replay = persist_windows_n4_delivery(
        cursor,
        plan=plan,
        json_adapter=lambda value: value,
    )

    assert first.outbox_insert_count == 1
    assert first.database_write_count == 1
    assert replay.database_write_count == 0
    with pytest.raises(RuntimeError, match="no N4 snapshot"):
        planner.read()

    planner = plan.candidate_planner
    assert planner.read() == plan.snapshot
    assert planner.read().asset_kind == asset_kind
    assert planner.read().source_n4_version == 1

    changed_plan = plan_windows_n4_delivery(
        planner,
        _runtime_snapshot(
            asset_kind,
            version=2,
            live_30m="volume_up",
        ),
    )
    assert [event.event_type for event in changed_plan.output_events] == [
        "TriggerStateChanged"
    ]
    changed = persist_windows_n4_delivery(
        cursor,
        plan=changed_plan,
        json_adapter=lambda value: value,
    )
    assert changed.outbox_insert_count == 1
    planner = changed_plan.candidate_planner
    assert planner.read().source_n4_version == 2


def test_failed_persistence_discards_candidate_and_retry_is_stable() -> None:
    planner = WindowsN4StateTransitionPlanner(
        asset_kind="stock",
        trigger_run_id="windows_n4_delivery_stock",
    )
    snapshot = _runtime_snapshot("stock")
    first_plan = plan_windows_n4_delivery(planner, snapshot)

    class _FailingCursor:
        def execute(self, _query, _params) -> None:
            raise RuntimeError("fixture transaction failure")

    with pytest.raises(RuntimeError, match="fixture transaction failure"):
        persist_windows_n4_delivery(
            _FailingCursor(),
            plan=first_plan,
            json_adapter=lambda value: value,
        )

    with pytest.raises(RuntimeError, match="no N4 snapshot"):
        planner.read()
    retry_plan = plan_windows_n4_delivery(planner, snapshot)
    assert [
        (event.event_id, event.dedup_key)
        for event in retry_plan.output_events
    ] == [
        (event.event_id, event.dedup_key)
        for event in first_plan.output_events
    ]

    result = persist_windows_n4_delivery(
        _FakeCursor(),
        plan=retry_plan,
        json_adapter=lambda value: value,
    )
    assert result.outbox_insert_count == 1
    planner = retry_plan.candidate_planner
    assert planner.read().source_n4_version == 1


def test_delivery_module_never_connects_commits_or_enters_other_layers() -> None:
    source = Path(
        "src/ashare_v3/trigger/windows_n4_delivery.py"
    ).read_text(encoding="utf-8").lower()

    for forbidden in (
        "psycopg.connect",
        ".commit(",
        "eltdx",
        "n5_action",
        "n6_user",
        "register-scheduledtask",
    ):
        assert forbidden not in source
