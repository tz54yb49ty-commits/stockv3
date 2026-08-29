from __future__ import annotations

from dataclasses import replace
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
        self.rows: dict[str, tuple[int, tuple[object, ...]]] = {}
        self.dedup_event_ids: dict[tuple[str, ...], str] = {}
        self.next_outbox_id = 1
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self._returned: list[tuple[object, ...]] = []

    def execute(self, query, params) -> None:
        sql = " ".join(str(query).split())
        values = tuple(params)
        self.calls.append((sql, values))
        self._returned = []
        if "INSERT INTO common_event_outbox" in sql:
            assert "ON CONFLICT DO NOTHING" in sql
            event_id = str(values[0])
            dedup_key = str(values[9])
            dedup_identity = (
                str(values[7]),
                str(values[1]),
                str(values[8]),
                dedup_key,
                str(values[2]),
            )
            if (
                event_id in self.event_ids
                or dedup_identity in self.dedup_event_ids
            ):
                return
            outbox_id = self.next_outbox_id
            self.next_outbox_id += 1
            self.event_ids.add(event_id)
            self.dedup_keys.add(dedup_key)
            self.rows[event_id] = (outbox_id, values)
            self.dedup_event_ids[dedup_identity] = event_id
            self._returned = [(outbox_id, *values)]
            return
        assert "FROM common_event_outbox" in sql
        event_id, layer, event_type, run_id, dedup_key, schema = values
        dedup_identity = tuple(
            str(value)
            for value in (
                layer,
                event_type,
                run_id,
                dedup_key,
                schema,
            )
        )
        matching_event_ids = {str(event_id)} & set(self.rows)
        dedup_event_id = self.dedup_event_ids.get(dedup_identity)
        if dedup_event_id is not None:
            matching_event_ids.add(dedup_event_id)
        self._returned = [
            (self.rows[key][0], *self.rows[key][1])
            for key in sorted(
                matching_event_ids,
                key=lambda item: self.rows[item][0],
            )[:2]
        ]

    def fetchone(self):
        return self._returned[0] if self._returned else None

    def fetchall(self):
        return list(self._returned)


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
    assert first.outbox_rows[0].outbox_id == 1
    assert first.outbox_rows[0].event == plan.output_events[0]
    assert replay.database_write_count == 0
    assert replay.outbox_rows == first.outbox_rows
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


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("dedup_key", "windows-n4-conflicting-dedup"),
        ("event_id", "windows-n4-conflicting-event-id"),
    ),
)
def test_idempotent_conflict_must_resolve_the_exact_planned_event(
    field: str,
    value: str,
) -> None:
    planner = WindowsN4StateTransitionPlanner(
        asset_kind="stock",
        trigger_run_id="windows_n4_delivery_stock",
    )
    plan = plan_windows_n4_delivery(planner, _runtime_snapshot("stock"))
    cursor = _FakeCursor()
    persist_windows_n4_delivery(
        cursor,
        plan=plan,
        json_adapter=lambda payload: payload,
    )
    conflicting_event = replace(plan.output_events[0], **{field: value})
    conflicting_plan = replace(
        plan,
        output_events=(conflicting_event,),
    )

    with pytest.raises(
        RuntimeError,
        match="authoritative N4 outbox row does not match planned event",
    ):
        persist_windows_n4_delivery(
            cursor,
            plan=conflicting_plan,
            json_adapter=lambda payload: payload,
        )


def test_delivery_module_never_connects_commits_or_enters_other_layers() -> None:
    source = Path(
        "src/ashare_v3/trigger/windows_n4_delivery.py"
    ).read_text(encoding="utf-8").lower()

    for forbidden in (
        "psycopg.connect",
        ".commit(",
        "eltdx",
        "n5_action",
        "ashare_v3.action",
        "n6_user",
        "register-scheduledtask",
    ):
        assert forbidden not in source
