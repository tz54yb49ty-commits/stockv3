from __future__ import annotations

from collections.abc import Mapping

import pytest

from ashare_v3.action.windows_n5_episode import (
    DAILY_SOURCE_RULE_POLICY_VERSION,
    SUPPORTED_SOURCE_RULE_POLICY_VERSIONS,
    WindowsN5EpisodePlanner,
)
from ashare_v3.action.windows_n5_restore import (
    N4_INBOX_RESTORE_SELECT,
    N5_OUTBOX_RESTORE_SELECT,
    WindowsN5EpisodeReadOnlyRepository,
    build_windows_n5_episode_restore_bundle,
)
from tests.test_windows_n5_episode import (
    SOURCE_CONDITION_RUN_ID,
    TRADE_DATE,
    _matched,
    _metric,
    _state_changed,
)


ASSET_KINDS = ("stock", "index", "board")
ACTION_RUN_IDS = {
    kind: f"windows_n5_closed_minute_{TRADE_DATE}_{kind}"
    for kind in ASSET_KINDS
}
CONSUMER_NAME = "windows_n5_state_v1"


def _history(
    asset_kind: str,
    outcome: str,
    *,
    rule_policy_version: str | None = None,
):
    planner = WindowsN5EpisodePlanner(
        asset_kind=asset_kind,
        action_run_id=ACTION_RUN_IDS[asset_kind],
    )
    matched = _matched(
        asset_kind=asset_kind,
        **(
            {"rule_policy_version": rule_policy_version}
            if rule_policy_version is not None
            else {}
        ),
    )
    eligible = planner.consume_trigger_event(matched).events[0]
    if outcome == "eligible":
        return (matched,), (eligible,)
    if outcome == "executed":
        executed = planner.consume_metric(
            _metric(asset_kind=asset_kind)
        ).events[0]
        return (matched,), (eligible, executed)
    changed = _state_changed(matched, trigger_live=False)
    skipped = planner.consume_trigger_event(changed).events[0]
    return (matched, changed), (eligible, skipped)


def _bundle():
    n4_events = []
    n5_events = []
    for asset_kind, outcome in (
        ("stock", "eligible"),
        ("index", "executed"),
        ("board", "skipped"),
    ):
        n4, n5 = _history(asset_kind, outcome)
        n4_events.extend(n4)
        n5_events.extend(n5)
    return build_windows_n5_episode_restore_bundle(
        n4_inbox_events=tuple(reversed(n4_events)),
        n5_outbox_events=tuple(reversed(n5_events)),
        source_condition_run_id=SOURCE_CONDITION_RUN_ID,
        for_trade_date=TRADE_DATE,
        consumer_name=CONSUMER_NAME,
        action_run_ids=ACTION_RUN_IDS,
    )


def test_bundle_restores_three_channel_episode_states_without_reemission() -> None:
    bundle = _bundle()
    planners = bundle.restore_planners(ACTION_RUN_IDS)

    stock = planners["stock"].read()
    assert len(stock.active) == 1
    assert next(iter(stock.active.values())).action_state == "eligible"
    assert next(iter(stock.active.values())).eligible_event_id is not None

    index = planners["index"].read()
    assert index.active == {}
    assert index.runtime_states == {}
    assert index.closed_episode_watermark_count == 1

    board = planners["board"].read()
    assert board.active == {}
    assert board.closed_episode_watermark_count == 1

    assert dict(bundle.n4_inbox_event_counts) == {
        "stock": 1,
        "index": 1,
        "board": 2,
    }
    assert dict(bundle.n5_outbox_event_counts) == {
        "stock": 1,
        "index": 2,
        "board": 2,
    }

    stock_matched = bundle.events["stock"][0]
    assert planners["stock"].consume_trigger_event(stock_matched).events == ()


def test_bundle_restores_daily_v2_without_reemission() -> None:
    n4_events, n5_events = _history(
        "stock",
        "eligible",
        rule_policy_version=DAILY_SOURCE_RULE_POLICY_VERSION,
    )
    bundle = build_windows_n5_episode_restore_bundle(
        n4_inbox_events=n4_events,
        n5_outbox_events=n5_events,
        source_condition_run_id=SOURCE_CONDITION_RUN_ID,
        for_trade_date=TRADE_DATE,
        consumer_name=CONSUMER_NAME,
        action_run_ids=ACTION_RUN_IDS,
    )

    planner = bundle.restore_planners(ACTION_RUN_IDS)["stock"]
    episode = next(iter(planner.read().active.values()))
    assert episode.key.condition_key == "BUY:D_STATE_V2"
    assert planner.consume_trigger_event(n4_events[0]).events == ()


def test_bundle_deduplicates_replayed_inbox_and_outbox_events() -> None:
    n4_events, n5_events = _history("stock", "eligible")
    bundle = build_windows_n5_episode_restore_bundle(
        n4_inbox_events=(*n4_events, *n4_events),
        n5_outbox_events=(*n5_events, *n5_events),
        source_condition_run_id=SOURCE_CONDITION_RUN_ID,
        for_trade_date=TRADE_DATE,
        consumer_name=CONSUMER_NAME,
        action_run_ids=ACTION_RUN_IDS,
    )

    assert len(bundle.events["stock"]) == 2
    assert bundle.n4_inbox_event_counts["stock"] == 1
    assert bundle.n5_outbox_event_counts["stock"] == 1


def test_bundle_rejects_wrong_lineage_and_action_run() -> None:
    n4_events, n5_events = _history("stock", "eligible")
    wrong_payload = dict(n4_events[0].payload_json)
    wrong_payload["source_condition_run_id"] = "different_lineage"
    wrong_n4 = n4_events[0].__class__(
        **{
            **n4_events[0].as_record(),
            "payload_json": wrong_payload,
        }
    )
    with pytest.raises(ValueError, match="outside N2 lineage"):
        build_windows_n5_episode_restore_bundle(
            n4_inbox_events=(wrong_n4,),
            n5_outbox_events=(),
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            for_trade_date=TRADE_DATE,
            consumer_name=CONSUMER_NAME,
            action_run_ids=ACTION_RUN_IDS,
        )

    wrong_runs = {**ACTION_RUN_IDS, "stock": "different_action_run"}
    with pytest.raises(ValueError, match="outside action_run_id"):
        build_windows_n5_episode_restore_bundle(
            n4_inbox_events=n4_events,
            n5_outbox_events=n5_events,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            for_trade_date=TRADE_DATE,
            consumer_name=CONSUMER_NAME,
            action_run_ids=wrong_runs,
        )


class _FakeCursor:
    def __init__(self, n4_rows, n5_rows) -> None:
        self.n4_rows = n4_rows
        self.n5_rows = n5_rows
        self.executions = []
        self.current_rows = ()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params) -> None:
        self.executions.append((sql, tuple(params)))
        self.current_rows = (
            self.n4_rows if sql == N4_INBOX_RESTORE_SELECT else self.n5_rows
        )

    def fetchall(self):
        return self.current_rows


class _FakeConnection:
    def __init__(self, n4_rows, n5_rows) -> None:
        self.cursor_value = _FakeCursor(n4_rows, n5_rows)
        self.read_only = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def cursor(self):
        return self.cursor_value


def _inbox_row(event, inbox_id: int) -> Mapping[str, object]:
    return {
        "inbox_id": inbox_id,
        "raw_json": {
            "source_outbox_id": inbox_id,
            "source_event": event.as_record(),
        },
    }


def _outbox_row(event, outbox_id: int) -> Mapping[str, object]:
    return {"outbox_id": outbox_id, **event.as_record()}


def test_repository_reads_inbox_and_outbox_in_one_read_only_session() -> None:
    n4_events, n5_events = _history("stock", "eligible")
    connection = _FakeConnection(
        [_inbox_row(n4_events[0], 11)],
        [_outbox_row(n5_events[0], 22)],
    )
    connect_calls = []

    def connect(dsn, **kwargs):
        connect_calls.append((dsn, kwargs))
        return connection

    repository = WindowsN5EpisodeReadOnlyRepository(
        "postgresql://fixture",
        consumer_name=CONSUMER_NAME,
        connect=connect,
    )
    bundle = repository.load(
        source_condition_run_id=SOURCE_CONDITION_RUN_ID,
        for_trade_date=TRADE_DATE,
        action_run_ids=ACTION_RUN_IDS,
    )

    assert connection.read_only is True
    assert len(connection.cursor_value.executions) == 2
    assert connect_calls == [("postgresql://fixture", {})]
    n4_params = connection.cursor_value.executions[0][1]
    assert n4_params[-1] == list(SUPPORTED_SOURCE_RULE_POLICY_VERSIONS)
    assert len(bundle.events["stock"]) == 2
    for sql, _params in connection.cursor_value.executions:
        assert sql.lstrip().upper().startswith("SELECT ")
        assert not any(
            token in sql.upper()
            for token in (
                "INSERT ",
                "UPDATE ",
                "DELETE ",
                "ALTER ",
                "CREATE ",
            )
        )


def test_restore_rejects_n5_event_without_trigger_matched_entry() -> None:
    _n4_events, n5_events = _history("stock", "eligible")
    planner = WindowsN5EpisodePlanner(
        asset_kind="stock",
        action_run_id=ACTION_RUN_IDS["stock"],
    )

    with pytest.raises(ValueError, match="requires TriggerMatched"):
        planner.restore_from_outbox(n5_events)
