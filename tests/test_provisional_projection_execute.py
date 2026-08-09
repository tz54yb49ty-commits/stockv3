from copy import deepcopy
import inspect
import json
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

from ashare_v3.trigger.provisional_projection_execute import (
    PROVISIONAL_ALLOWED_WRITE_TABLES,
    PROVISIONAL_FORBIDDEN_WRITE_TABLES,
    ProvisionalProjectionExecuteBlocked,
    build_provisional_rollback_sql,
    build_provisional_projection_execute_plan,
    fetch_projection_rows,
    insert_provisional_trigger_state,
    normalize_provisional_projection_row,
    run_provisional_projection_once,
    to_jsonable,
)
from tests.test_trigger_projection_matcher import (
    CONTEXT_RUN_ID,
    PROJECTION_RUN_ID,
    context_row,
    context_row_with_condition_projection,
    hint_1m_projection_row,
    projection_row,
)


TRIGGER_RUN_ID = "trigger_provisional_b2_20260525_until_1415_v1"
UNIFIED_TRIGGER_RUN_ID = (
    "trigger_provisional_b2_20260626_until_1447"
    "__realtime_projection_metric_20260626_until_1447"
    "__live_current_1m_unified_payload_v1__atomic_rule_v1"
)
HINT_V2_SOURCE_RUN_ID = (
    "realtime_hint_projection_metric_20260629_until_1500__asset_index_board__"
    "index_board_1m_hint_projection_v1__"
    "market_data_subscription_20260629_condition_layer_20260626_source_20260626_for_20260629_v1"
)
HINT_V2_TRIGGER_RUN_ID = (
    "trigger_provisional_b2_20260629_until_1500__realtime_hint_projection_metric_20260629_until_1500__"
    "asset_index_board__index_board_1m_hint_projection_v1__atomic_rule_v1"
)
HINT_V2_MIDDAY_BRIDGE_SOURCE_RUN_ID = (
    "realtime_hint_projection_metric_20260630_until_1300__asset_index_board__"
    "index_board_1m_hint_projection_v1_midday_bridge_v1__"
    "market_data_subscription_20260630_condition_layer_20260629_source_20260629_for_20260630_v1"
)
HINT_V2_MIDDAY_BRIDGE_TRIGGER_RUN_ID = (
    "trigger_provisional_b2_20260630_until_1300__realtime_hint_projection_metric_20260630_until_1300__"
    "asset_index_board__index_board_1m_hint_projection_v1_midday_bridge_v1__atomic_rule_v1"
)
ORDINARY_TRIGGER_RUN_ID = (
    "trigger_provisional_ordinary_20260701_until_0946__realtime_action_confirmation_metric_20260701_until_0946"
    "__asset_all__b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1"
    "__atomic_rule_v1_period_rollover_guard_v1"
)
SOURCE_CONDITION_RUN_ID = "condition_layer_20260522_to_20260525_20260525102249_execute"
CANONICAL_STATE_FIELDS = (
    "trigger_live",
    "trigger_mark_candidate",
    "primary_trigger_period",
    "all_trigger_periods",
    "projection_30m_flag",
    "projection_30m_type",
)


def assert_canonical_state_columns(test_case: unittest.TestCase, state: dict[str, object]) -> None:
    raw_json = state["raw_json"]
    for field in CANONICAL_STATE_FIELDS:
        test_case.assertIn(field, state)
        test_case.assertEqual(state[field], raw_json[field])


def empty_target_counts() -> dict[str, int]:
    return {
        "common_trigger_run": 0,
        "common_trigger_state": 0,
        "common_trigger_match": 0,
        "common_event_outbox": 0,
    }


def build_plan(
    context_rows: list[dict[str, object]],
    projection_rows: list[dict[str, object]],
    *,
    trigger_run_id: str = TRIGGER_RUN_ID,
    for_trade_date: str = "20260525",
    target_counts: dict[str, int] | None = None,
    previous_trigger_states: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return build_provisional_projection_execute_plan(
        trigger_run_id=trigger_run_id,
        trigger_context_run={"run_id": CONTEXT_RUN_ID, "status": "passed"},
        projection_run={"run_id": PROJECTION_RUN_ID, "status": "passed"},
        trigger_context_run_id=CONTEXT_RUN_ID,
        projection_run_id=PROJECTION_RUN_ID,
        for_trade_date=for_trade_date,
        source_condition_run_id=SOURCE_CONDITION_RUN_ID,
        source_projection_run_id=PROJECTION_RUN_ID,
        context_rows=context_rows,
        projection_rows=projection_rows,
        target_counts=target_counts or empty_target_counts(),
        previous_trigger_states=previous_trigger_states or [],
    )


def previous_state_for_payload(payload: dict[str, object]) -> dict[str, object]:
    return {
        "run_id": "previous_hint_run",
        "source_condition_run_id": SOURCE_CONDITION_RUN_ID,
        "for_trade_date": "20260525",
        "asset_kind": payload["asset_kind"],
        "identity_key": payload["identity_key"],
        "direction": payload["direction"],
        "signal_type": payload["signal_type"],
        "condition_key": payload["condition_key"],
        "trigger_period": "30m",
        "current_status": "matched",
        "match_count": 1,
        "dedup_key": "previous-key",
        "raw_json": {
            "trigger_type": payload["trigger_type"],
            "projection_30m_flag": payload["projection_30m_flag"],
            "projection_30m_type": payload["projection_30m_type"],
            "trigger_mark_candidate": payload["trigger_mark_candidate"],
            "trigger_period": payload["trigger_period"],
            "triggered_periods": payload["triggered_periods"],
            "primary_trigger_period": payload["primary_trigger_period"],
            "all_trigger_periods": payload["all_trigger_periods"],
            "trigger_price": payload["trigger_price"],
        },
    }


def minimal_projection_execute_plan(previous_count: int = 0) -> dict[str, object]:
    return {
        "summary": {"candidate_count": 0, "matched_count": 0},
        "write_counts": {
            "common_trigger_run": 1,
            "common_trigger_quality_item": 1,
            "common_trigger_state": previous_count,
            "common_trigger_match": 0,
            "common_event_outbox": 0,
        },
        "event_model": {
            "enters_n5": False,
            "writes_inbox_or_checkpoint": False,
        },
        "forbidden_write_counts": {table_name: 0 for table_name in PROVISIONAL_FORBIDDEN_WRITE_TABLES},
    }


class ProjectionRunOncePatch:
    def __init__(self, module, **replacements) -> None:
        self.module = module
        self.replacements = replacements
        self.originals: dict[str, object] = {}

    def __enter__(self):
        for name, replacement in self.replacements.items():
            self.originals[name] = getattr(self.module, name)
            setattr(self.module, name, replacement)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        for name, original in self.originals.items():
            setattr(self.module, name, original)
        return None


class ProvisionalProjectionExecuteTest(unittest.TestCase):
    def test_condition_projection_context_passthrough_preserves_hint_lifecycle_and_dedup(self) -> None:
        context = context_row_with_condition_projection(
            "index:SH:000016",
            "buy",
            "BUY_HINT",
            ["BUY_HINT"],
            asset_kind="index",
        )
        projection = projection_row("index", "index:SH:000016", "ready", "up_volume_expanding")
        initial = build_plan([context], [projection])
        outbox = initial["writes"]["common_event_outbox"][0]
        payload = outbox["payload_json"]
        expected_context = context["period_trigger_baseline_json"]["condition_projection_context"]

        self.assertEqual(outbox["event_type"], "TriggerMatched")
        self.assertEqual(outbox["event_schema_version"], "v1")
        self.assertEqual(payload["condition_projection_context"], expected_context)
        self.assertEqual(payload["condition_projection_context_status"], "ready")
        self.assertEqual(payload["condition_projection_context_trace"]["validation_reasons"], [])
        self.assertTrue(payload["n5_entry_allowed"])
        self.assertEqual(
            initial["writes"]["common_trigger_match"][0]["raw_json"]["condition_projection_context"],
            expected_context,
        )

        legacy = build_plan(
            [context_row("index:SH:000016", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="index")],
            [projection],
        )["writes"]["common_event_outbox"][0]
        self.assertEqual(outbox["dedup_key"], legacy["dedup_key"])
        self.assertEqual(outbox["event_id"], legacy["event_id"])

        previous = previous_state_for_payload(payload)
        previous["raw_json"]["projection_30m_type"] = "shrink_down"
        previous["raw_json"]["trigger_mark_candidate"] = "30m_shrink"
        changed = build_plan([context], [projection], previous_trigger_states=[previous])
        changed_payload = changed["writes"]["common_event_outbox"][0]["payload_json"]
        self.assertEqual(changed_payload["event_type"], "TriggerStateChanged")
        self.assertTrue(changed_payload["trigger_live"])
        self.assertFalse(changed_payload["n5_entry_allowed"])
        self.assertEqual(changed_payload["condition_projection_context"], expected_context)

        invalid_context = deepcopy(context)
        invalid_context["period_trigger_baseline_json"]["condition_projection_context"]["fields"]["close"] = "10.6"
        invalid_initial = build_plan([invalid_context], [projection])
        invalid_payload = invalid_initial["writes"]["common_event_outbox"][0]["payload_json"]
        self.assertEqual(invalid_payload["event_type"], "TriggerMatched")
        self.assertEqual(invalid_payload["condition_projection_context_status"], "not_ready")
        self.assertEqual(
            invalid_initial["writes"]["common_event_outbox"][0]["event_id"],
            outbox["event_id"],
        )
        unchanged = build_plan(
            [invalid_context],
            [projection],
            previous_trigger_states=[previous_state_for_payload(payload)],
        )
        self.assertEqual(unchanged["writes"]["common_event_outbox"], [])

    def test_hint_run_once_without_baseline_policy_fails_before_using_same_day_states(self) -> None:
        import ashare_v3.trigger.provisional_projection_execute as projection_execute

        def fake_build_plan(**kwargs):
            self.assertEqual(kwargs["previous_trigger_states"], [{"run_id": ORDINARY_TRIGGER_RUN_ID}])
            return minimal_projection_execute_plan(previous_count=1)

        with ProjectionRunOncePatch(
            projection_execute,
            fetch_trigger_context_rows=lambda *args, **kwargs: ([], {"run_id": CONTEXT_RUN_ID, "status": "passed"}),
            fetch_projection_rows=lambda *args, **kwargs: ([], {"run_id": HINT_V2_SOURCE_RUN_ID, "status": "passed"}),
            fetch_target_counts=lambda *args, **kwargs: empty_target_counts(),
            fetch_previous_trigger_states=lambda *args, **kwargs: [{"run_id": ORDINARY_TRIGGER_RUN_ID}],
            build_provisional_projection_execute_plan=fake_build_plan,
        ):
            with self.assertRaises(ProvisionalProjectionExecuteBlocked) as raised:
                run_provisional_projection_once(
                    dsn="postgresql://unit-test",
                    trigger_context_run_id=CONTEXT_RUN_ID,
                    projection_run_id=HINT_V2_SOURCE_RUN_ID,
                    source_projection_run_id=HINT_V2_SOURCE_RUN_ID,
                    trigger_run_id=HINT_V2_TRIGGER_RUN_ID,
                    for_trade_date="20260629",
                    source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                    execute=False,
                    user_confirmed=False,
                )

        self.assertIn("BLOCKED_PREVIOUS_BASELINE_POLICY_UNSAFE", str(raised.exception))

    def test_hint_run_once_no_previous_baseline_skips_unscoped_previous_fetch(self) -> None:
        import ashare_v3.trigger.provisional_projection_execute as projection_execute

        def forbidden_fetch_previous(*args, **kwargs):
            raise AssertionError("unscoped previous state fetch must not run")

        def fake_build_plan(**kwargs):
            self.assertEqual(kwargs["previous_trigger_states"], [])
            return minimal_projection_execute_plan()

        with ProjectionRunOncePatch(
            projection_execute,
            fetch_trigger_context_rows=lambda *args, **kwargs: ([], {"run_id": CONTEXT_RUN_ID, "status": "passed"}),
            fetch_projection_rows=lambda *args, **kwargs: ([], {"run_id": HINT_V2_SOURCE_RUN_ID, "status": "passed"}),
            fetch_target_counts=lambda *args, **kwargs: empty_target_counts(),
            fetch_previous_trigger_states=forbidden_fetch_previous,
            build_provisional_projection_execute_plan=fake_build_plan,
        ):
            report = run_provisional_projection_once(
                dsn="postgresql://unit-test",
                trigger_context_run_id=CONTEXT_RUN_ID,
                projection_run_id=HINT_V2_SOURCE_RUN_ID,
                source_projection_run_id=HINT_V2_SOURCE_RUN_ID,
                trigger_run_id=HINT_V2_TRIGGER_RUN_ID,
                for_trade_date="20260629",
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                execute=False,
                user_confirmed=False,
                no_previous_baseline=True,
            )

        self.assertEqual(report["baseline_mode"], "no_previous_baseline")
        self.assertIsNone(report["previous_trigger_run_id"])
        self.assertEqual(report["previous_state_count"], 0)
        self.assertEqual(report["previous_baseline_family"], "none")
        self.assertTrue(report["previous_baseline_policy_safe"])

    def test_hint_run_once_rejects_ordinary_previous_baseline_run_id(self) -> None:
        with self.assertRaises(ProvisionalProjectionExecuteBlocked) as raised:
            run_provisional_projection_once(
                dsn="postgresql://unit-test",
                trigger_context_run_id=CONTEXT_RUN_ID,
                projection_run_id=HINT_V2_SOURCE_RUN_ID,
                source_projection_run_id=HINT_V2_SOURCE_RUN_ID,
                trigger_run_id=HINT_V2_TRIGGER_RUN_ID,
                for_trade_date="20260629",
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                execute=False,
                user_confirmed=False,
                previous_trigger_run_id=ORDINARY_TRIGGER_RUN_ID,
            )

        self.assertIn("previous HINT baseline", str(raised.exception))

    def test_hint_run_once_uses_exact_previous_hint_baseline_only(self) -> None:
        import ashare_v3.trigger.provisional_projection_execute as projection_execute

        def fake_fetch_exact_previous(*args, **kwargs):
            self.assertEqual(kwargs["previous_trigger_run_id"], HINT_V2_TRIGGER_RUN_ID)
            return [{"run_id": HINT_V2_TRIGGER_RUN_ID}]

        def fake_build_plan(**kwargs):
            self.assertEqual(kwargs["previous_trigger_states"], [{"run_id": HINT_V2_TRIGGER_RUN_ID}])
            return minimal_projection_execute_plan(previous_count=1)

        with ProjectionRunOncePatch(
            projection_execute,
            fetch_trigger_context_rows=lambda *args, **kwargs: ([], {"run_id": CONTEXT_RUN_ID, "status": "passed"}),
            fetch_projection_rows=lambda *args, **kwargs: ([], {"run_id": HINT_V2_SOURCE_RUN_ID, "status": "passed"}),
            fetch_target_counts=lambda *args, **kwargs: empty_target_counts(),
            fetch_exact_previous_hint_trigger_states=fake_fetch_exact_previous,
            build_provisional_projection_execute_plan=fake_build_plan,
        ):
            report = run_provisional_projection_once(
                dsn="postgresql://unit-test",
                trigger_context_run_id=CONTEXT_RUN_ID,
                projection_run_id=HINT_V2_SOURCE_RUN_ID,
                source_projection_run_id=HINT_V2_SOURCE_RUN_ID,
                trigger_run_id=HINT_V2_MIDDAY_BRIDGE_TRIGGER_RUN_ID,
                for_trade_date="20260630",
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                execute=False,
                user_confirmed=False,
                previous_trigger_run_id=HINT_V2_TRIGGER_RUN_ID,
            )

        self.assertEqual(report["baseline_mode"], "exact_hint_previous_baseline")
        self.assertEqual(report["previous_trigger_run_id"], HINT_V2_TRIGGER_RUN_ID)
        self.assertEqual(report["previous_state_count"], 1)
        self.assertEqual(report["previous_baseline_family"], "hint_projection")
        self.assertTrue(report["previous_baseline_policy_safe"])

    def test_hint_previous_baseline_carries_forward_prior_live_state(self) -> None:
        import ashare_v3.trigger.provisional_projection_execute as projection_execute

        current_context = [
            context_row("board:TDX:881395", "sell", "SELL_HINT", ["SELL_HINT"], asset_kind="board")
        ]
        current_projection = [
            hint_1m_projection_row("board", "board:TDX:881395", "shrink_down")
        ]
        initial = build_plan(
            current_context,
            current_projection,
            trigger_run_id=(
                "trigger_provisional_b2_20260702_until_1012__"
                "realtime_hint_projection_metric_20260702_until_1012__asset_index_board__"
                "index_board_1m_hint_projection_v1__atomic_rule_v1"
            ),
            for_trade_date="20260702",
        )
        carried_state = previous_state_for_payload(initial["writes"]["common_event_outbox"][0]["payload_json"])
        carried_state["run_id"] = (
            "trigger_provisional_b2_20260702_until_1012__"
            "realtime_hint_projection_metric_20260702_until_1012__asset_index_board__"
            "index_board_1m_hint_projection_v1__atomic_rule_v1"
        )
        carried_state["for_trade_date"] = "20260702"
        exact_delta_state = {
            **carried_state,
            "run_id": (
                "trigger_provisional_b2_20260702_until_1103__"
                "realtime_hint_projection_metric_20260702_until_1103__asset_index_board__"
                "index_board_1m_hint_projection_v1__atomic_rule_v1"
            ),
            "identity_key": "board:TDX:OTHER",
        }

        class FakeCursor:
            def __init__(self) -> None:
                self._last_params: tuple[object, ...] | None = None

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

            def execute(self, sql: str, params: object = None) -> None:
                self._last_params = tuple(params or ())

            def fetchone(self):
                return {
                    "run_id": exact_delta_state["run_id"],
                    "status": "passed",
                    "for_trade_date": "20260702",
                    "source_condition_run_id": SOURCE_CONDITION_RUN_ID,
                }

            def fetchall(self):
                if self._last_params == (exact_delta_state["run_id"],):
                    return [exact_delta_state]
                return [carried_state, exact_delta_state]

        class FakeConnection:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

            def cursor(self):
                return FakeCursor()

        with ProjectionRunOncePatch(
            projection_execute,
            audited_n4_readonly_plan_connect=lambda *args, **kwargs: FakeConnection(),
        ):
            previous_states = projection_execute.fetch_exact_previous_hint_trigger_states(
                "postgresql://unit-test",
                previous_trigger_run_id=str(exact_delta_state["run_id"]),
                for_trade_date="20260702",
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            )

        plan = build_plan(
            current_context,
            current_projection,
            trigger_run_id=(
                "trigger_provisional_b2_20260702_until_1109__"
                "realtime_hint_projection_metric_20260702_until_1109__asset_index_board__"
                "index_board_1m_hint_projection_v1__atomic_rule_v1"
            ),
            for_trade_date="20260702",
            previous_trigger_states=previous_states,
        )

        self.assertEqual(plan["matched_count"], 0)
        self.assertEqual(plan["state_changed_count"], 0)
        self.assertEqual(plan["writes"]["common_trigger_state"], [])
        self.assertEqual(plan["writes"]["common_trigger_match"], [])
        self.assertEqual(plan["writes"]["common_event_outbox"], [])

    def test_hint_runner_cli_accepts_explicit_previous_baseline_policy_flags(self) -> None:
        from scripts.run_n4_provisional_projection_execute_once import build_arg_parser

        base_args = [
            "--dsn",
            "postgresql://unit-test",
            "--trigger-context-run-id",
            CONTEXT_RUN_ID,
            "--projection-run-id",
            HINT_V2_SOURCE_RUN_ID,
            "--source-projection-run-id",
            HINT_V2_SOURCE_RUN_ID,
            "--trigger-run-id",
            HINT_V2_TRIGGER_RUN_ID,
            "--for-trade-date",
            "20260629",
            "--source-condition-run-id",
            SOURCE_CONDITION_RUN_ID,
        ]

        no_previous = build_arg_parser().parse_args([*base_args, "--no-previous-baseline"])
        exact_previous = build_arg_parser().parse_args(
            [*base_args, "--previous-trigger-run-id", HINT_V2_TRIGGER_RUN_ID]
        )

        self.assertTrue(no_previous.no_previous_baseline)
        self.assertIsNone(no_previous.previous_trigger_run_id)
        self.assertFalse(exact_previous.no_previous_baseline)
        self.assertEqual(exact_previous.previous_trigger_run_id, HINT_V2_TRIGGER_RUN_ID)

    def test_fetch_projection_rows_uses_hint_tables_for_hint_v2_source_run(self) -> None:
        import ashare_v3.trigger.provisional_projection_execute as projection_execute

        class FakeCursor:
            def __init__(self) -> None:
                self.sqls: list[str] = []
                self._fetchone_queue = [
                    {"run_id": HINT_V2_SOURCE_RUN_ID, "status": "passed"},
                ]
                self._fetchall_queue = [
                    [
                        {
                            "projection_id": 101,
                            "projection_run_id": HINT_V2_SOURCE_RUN_ID,
                            "metric_minute_label": "2026-06-29 15:00",
                            "asset_kind": "index",
                            "identity_key": "index:SH:000001",
                            "condition_key": "BUY_HINT",
                            "proof_kind": "index_board_1m_hint_projection_v1",
                            "source_mode": "index_board_frequency8_1m",
                            "metric_role": "hint_trigger_proof",
                            "proof_owner": "N3",
                            "proof_consumer": "N4",
                            "not_n5_final_proof": True,
                            "current_window_start": "14:31",
                            "current_window_end": "15:00",
                            "current_30m_price": "1",
                            "current_30m_virtual_amount": "100",
                            "reference_30m_amount": "120",
                            "reference_30m_entity_high": "2",
                            "reference_30m_entity_low": "0.5",
                            "projection_30m_type": "none",
                            "projection_30m_flag": False,
                            "metric_ready": True,
                        }
                    ],
                    [
                        {
                            "projection_id": 202,
                            "projection_run_id": HINT_V2_SOURCE_RUN_ID,
                            "metric_minute_label": "2026-06-29 15:00",
                            "asset_kind": "board",
                            "identity_key": "board:TDX:881289",
                            "condition_key": "SELL_HINT",
                            "proof_kind": "index_board_1m_hint_projection_v1",
                            "source_mode": "index_board_frequency8_1m",
                            "metric_role": "hint_trigger_proof",
                            "proof_owner": "N3",
                            "proof_consumer": "N4",
                            "not_n5_final_proof": True,
                            "current_window_start": "14:31",
                            "current_window_end": "15:00",
                            "current_30m_price": "1",
                            "current_30m_virtual_amount": "150",
                            "reference_30m_amount": "120",
                            "reference_30m_entity_high": "2",
                            "reference_30m_entity_low": "0.5",
                            "projection_30m_type": "volume_up",
                            "projection_30m_flag": True,
                            "metric_ready": True,
                        }
                    ],
                ]

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

            def execute(self, sql: str, params: object = None) -> None:
                self.sqls.append(sql)

            def fetchone(self):
                return self._fetchone_queue.pop(0)

            def fetchall(self):
                return self._fetchall_queue.pop(0)

        class FakeConnection:
            def __init__(self, cursor: FakeCursor) -> None:
                self._cursor = cursor

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

            def cursor(self) -> FakeCursor:
                return self._cursor

        fake_cursor = FakeCursor()
        original_connect = projection_execute.audited_n4_readonly_plan_connect
        projection_execute.audited_n4_readonly_plan_connect = lambda *args, **kwargs: FakeConnection(fake_cursor)
        try:
            rows, run = fetch_projection_rows("fake-dsn", HINT_V2_SOURCE_RUN_ID)
        finally:
            projection_execute.audited_n4_readonly_plan_connect = original_connect

        executed_sql = "\n".join(fake_cursor.sqls)
        self.assertEqual(run["run_id"], HINT_V2_SOURCE_RUN_ID)
        self.assertEqual([row["identity_key"] for row in rows], ["index:SH:000001", "board:TDX:881289"])
        self.assertEqual([row["projection_signal_status"] for row in rows], ["flat", "up_volume_expanding"])
        self.assertEqual(rows[0]["source_fact_ids"]["source_hint_projection_metric_id"], 101)
        self.assertIn("index_realtime_hint_projection_metric", executed_sql)
        self.assertIn("board_realtime_hint_projection_metric", executed_sql)
        self.assertNotIn("stock_realtime_projection_metric", executed_sql)
        self.assertNotIn("index_realtime_projection_metric", executed_sql)
        self.assertNotIn("board_realtime_projection_metric", executed_sql)

    def test_unified_payload_run_id_builder_parser_and_rollback_preserve_source_variant(self) -> None:
        import ashare_v3.trigger.provisional_projection_execute as projection_execute

        parse_run_id = getattr(projection_execute, "parse_provisional_projection_trigger_run_id", None)
        build_run_id = getattr(projection_execute, "build_provisional_projection_trigger_run_id", None)
        self.assertIsNotNone(parse_run_id)
        self.assertIsNotNone(build_run_id)

        built = build_run_id(
            for_trade_date="20260626",
            until_hhmm="1447",
            source_variant="live_current_1m_unified_payload_v1",
            rule_suffix="atomic_rule_v1",
        )
        parsed = parse_run_id(UNIFIED_TRIGGER_RUN_ID)
        legacy = parse_run_id(TRIGGER_RUN_ID)
        historical_default = parse_run_id(
            "trigger_provisional_b2_20260625_until_1129"
            "__realtime_projection_metric_20260625_until_1129"
        )
        historical_atomic = parse_run_id(
            "trigger_provisional_b2_20260626_until_1447"
            "__realtime_projection_metric_20260626_until_1447"
            "__live_current_1m__atomic_rule_v1"
        )
        rollback_sql = build_provisional_rollback_sql(UNIFIED_TRIGGER_RUN_ID)

        self.assertEqual(built, UNIFIED_TRIGGER_RUN_ID)
        self.assertEqual(parsed["for_trade_date"], "20260626")
        self.assertEqual(parsed["until_hhmm"], "1447")
        self.assertEqual(parsed["source_variant"], "live_current_1m_unified_payload_v1")
        self.assertEqual(parsed["rule_suffix"], "atomic_rule_v1")
        self.assertEqual(legacy["source_variant"], "legacy_v1")
        self.assertEqual(historical_default["source_variant"], "default")
        self.assertEqual(historical_atomic["source_variant"], "live_current_1m")
        self.assertIn(UNIFIED_TRIGGER_RUN_ID, rollback_sql)

    def test_hint_v2_run_id_builder_parser_and_rollback_preserve_source_lineage(self) -> None:
        import ashare_v3.trigger.provisional_projection_execute as projection_execute

        parse_run_id = getattr(projection_execute, "parse_provisional_projection_trigger_run_id", None)
        build_run_id = getattr(projection_execute, "build_provisional_projection_trigger_run_id", None)
        self.assertIsNotNone(parse_run_id)
        self.assertIsNotNone(build_run_id)

        built = build_run_id(
            for_trade_date="20260629",
            until_hhmm="1500",
            source_metric_run_id=HINT_V2_SOURCE_RUN_ID,
            rule_suffix="atomic_rule_v1",
        )
        parsed = parse_run_id(HINT_V2_TRIGGER_RUN_ID)
        rollback_sql = build_provisional_rollback_sql(HINT_V2_TRIGGER_RUN_ID)
        first_delete = rollback_sql.index("DELETE FROM")
        guard_prefix = rollback_sql[:first_delete]

        self.assertEqual(built, HINT_V2_TRIGGER_RUN_ID)
        self.assertEqual(parsed["for_trade_date"], "20260629")
        self.assertEqual(parsed["until_hhmm"], "1500")
        self.assertEqual(parsed["source_metric_kind"], "realtime_hint_projection_metric")
        self.assertEqual(parsed["asset_scope"], "asset_index_board")
        self.assertEqual(parsed["proof_kind"], "index_board_1m_hint_projection_v1")
        self.assertEqual(parsed["rule_suffix"], "atomic_rule_v1")
        self.assertEqual(parsed["mode"], "provisional_hint_v2")
        self.assertIn(HINT_V2_TRIGGER_RUN_ID, rollback_sql)
        self.assertIn("status IN ('delivered', 'delivering')", guard_prefix)
        self.assertIn("source_layer = 'N4_trigger'", guard_prefix)
        self.assertIn("source_run_id = v_run_id", guard_prefix)

    def test_hint_v2_midday_bridge_run_id_builder_parser_and_rollback_preserve_source_suffix(self) -> None:
        import ashare_v3.trigger.provisional_projection_execute as projection_execute

        parse_run_id = getattr(projection_execute, "parse_provisional_projection_trigger_run_id", None)
        build_run_id = getattr(projection_execute, "build_provisional_projection_trigger_run_id", None)
        self.assertIsNotNone(parse_run_id)
        self.assertIsNotNone(build_run_id)

        built = build_run_id(
            for_trade_date="20260630",
            until_hhmm="1300",
            source_metric_run_id=HINT_V2_MIDDAY_BRIDGE_SOURCE_RUN_ID,
            rule_suffix="atomic_rule_v1",
        )
        parsed = parse_run_id(HINT_V2_MIDDAY_BRIDGE_TRIGGER_RUN_ID)
        rollback_sql = build_provisional_rollback_sql(HINT_V2_MIDDAY_BRIDGE_TRIGGER_RUN_ID)
        first_delete = rollback_sql.index("DELETE FROM")
        guard_prefix = rollback_sql[:first_delete]

        self.assertEqual(built, HINT_V2_MIDDAY_BRIDGE_TRIGGER_RUN_ID)
        self.assertEqual(parsed["for_trade_date"], "20260630")
        self.assertEqual(parsed["until_hhmm"], "1300")
        self.assertEqual(parsed["source_metric_kind"], "realtime_hint_projection_metric")
        self.assertEqual(parsed["asset_scope"], "asset_index_board")
        self.assertEqual(parsed["source_variant"], "index_board_1m_hint_projection_v1_midday_bridge_v1")
        self.assertEqual(parsed["proof_kind"], "index_board_1m_hint_projection_v1_midday_bridge_v1")
        self.assertEqual(parsed["rule_suffix"], "atomic_rule_v1")
        self.assertEqual(parsed["mode"], "provisional_hint_v2")
        self.assertIn(HINT_V2_MIDDAY_BRIDGE_TRIGGER_RUN_ID, rollback_sql)
        self.assertIn("status IN ('delivered', 'delivering')", guard_prefix)
        self.assertIn("common_event_inbox", guard_prefix)
        self.assertIn("common_event_consumer_checkpoint", guard_prefix)
        self.assertIn("common_action_run", guard_prefix)
        self.assertNotIn("DELETE FROM common_action", rollback_sql)

    def test_unified_payload_run_id_is_accepted_by_execute_plan(self) -> None:
        plan = build_plan(
            [context_row("index:SH:000016", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="index")],
            [projection_row("index", "index:SH:000016", "ready", "up_volume_expanding")],
            trigger_run_id=UNIFIED_TRIGGER_RUN_ID,
            for_trade_date="20260626",
        )

        self.assertEqual(plan["matched_count"], 1)
        self.assertEqual(len(plan["writes"]["common_event_outbox"]), 1)

    def test_hint_run_id_rejects_unsafe_suffix_missing_atomic_and_ordinary_prefix(self) -> None:
        import ashare_v3.trigger.provisional_projection_execute as projection_execute

        parse_run_id = getattr(projection_execute, "parse_provisional_projection_trigger_run_id", None)
        self.assertIsNotNone(parse_run_id)
        bad_suffix = (
            "trigger_provisional_b2_20260626_until_1447"
            "__realtime_projection_metric_20260626_until_1447"
            "__live_current_1m_unified_payload_v2__atomic_rule_v1"
        )
        missing_atomic = (
            "trigger_provisional_b2_20260626_until_1447"
            "__realtime_projection_metric_20260626_until_1447"
            "__live_current_1m_unified_payload_v1"
        )
        ordinary_prefix = (
            "trigger_provisional_ordinary_20260626_until_1447"
            "__realtime_projection_metric_20260626_until_1447"
            "__live_current_1m_unified_payload_v1__atomic_rule_v1"
        )

        for run_id in (bad_suffix, missing_atomic, ordinary_prefix):
            with self.subTest(run_id=run_id):
                with self.assertRaises(ProvisionalProjectionExecuteBlocked):
                    parse_run_id(run_id)

        with self.assertRaises(ProvisionalProjectionExecuteBlocked):
            build_plan(
                [context_row("index:SH:000016", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="index")],
                [projection_row("index", "index:SH:000016", "ready", "up_volume_expanding")],
                trigger_run_id=bad_suffix,
            )

    def test_hint_v2_run_id_rejects_unsafe_scope_suffix_prefix_and_missing_atomic(self) -> None:
        import ashare_v3.trigger.provisional_projection_execute as projection_execute

        parse_run_id = getattr(projection_execute, "parse_provisional_projection_trigger_run_id", None)
        self.assertIsNotNone(parse_run_id)
        bad_run_ids = (
            HINT_V2_TRIGGER_RUN_ID.replace("asset_index_board", "asset_all"),
            HINT_V2_TRIGGER_RUN_ID.replace("asset_index_board", "asset_stock"),
            HINT_V2_TRIGGER_RUN_ID.replace("index_board_1m_hint_projection_v1", "index_board_1m_hint_projection_v2"),
            HINT_V2_TRIGGER_RUN_ID.removesuffix("__atomic_rule_v1"),
            HINT_V2_TRIGGER_RUN_ID.replace("trigger_provisional_b2_", "trigger_provisional_ordinary_", 1),
            HINT_V2_MIDDAY_BRIDGE_TRIGGER_RUN_ID.replace("midday_bridge_v1", "midday_bridge_v2"),
            HINT_V2_MIDDAY_BRIDGE_TRIGGER_RUN_ID.replace("asset_index_board", "asset_all"),
            HINT_V2_MIDDAY_BRIDGE_TRIGGER_RUN_ID.replace("asset_index_board", "asset_stock"),
            HINT_V2_MIDDAY_BRIDGE_TRIGGER_RUN_ID.removesuffix("__atomic_rule_v1"),
            HINT_V2_MIDDAY_BRIDGE_TRIGGER_RUN_ID.replace("trigger_provisional_b2_", "trigger_provisional_ordinary_", 1),
        )

        for run_id in bad_run_ids:
            with self.subTest(run_id=run_id):
                with self.assertRaises(ProvisionalProjectionExecuteBlocked):
                    parse_run_id(run_id)

    def test_hint_v2_execute_plan_uses_iso_proof_time_not_hhmm_label(self) -> None:
        trigger_run_id = (
            "trigger_provisional_b2_20260630_until_1107__realtime_hint_projection_metric_20260630_until_1107__"
            "asset_index_board__index_board_1m_hint_projection_v1__atomic_rule_v1"
        )
        projection = hint_1m_projection_row("board", "board:TDX:BK001", "volume_up")
        proof_time = "2026-06-30T11:07:00+08:00"
        projection["metric_minute_label"] = "1107"
        projection["raw_json"] = {
            **dict(projection["raw_json"]),
            "proof": {
                "source_projection_proof_time": proof_time,
                "proof_input_time": proof_time,
                "proof_input_minute_label": "1107",
            },
        }

        plan = build_plan(
            [context_row("board:TDX:BK001", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="board")],
            [projection],
            trigger_run_id=trigger_run_id,
            for_trade_date="20260630",
        )

        self.assertEqual(plan["matched_count"], 1)
        outbox = plan["writes"]["common_event_outbox"][0]
        payload = outbox["payload_json"]
        match = plan["writes"]["common_trigger_match"][0]
        self.assertEqual(outbox["event_time"].isoformat(), proof_time)
        self.assertEqual(payload["trigger_time"], proof_time)
        self.assertEqual(match["trigger_time"].isoformat(), proof_time)
        self.assertEqual(payload["source_projection_proof_time"], proof_time)
        self.assertEqual(payload["projection_trace"]["metric_minute_label"], "1107")
        self.assertEqual(payload["projection_trace"]["trigger_time"], proof_time)

    def test_hint_v2_state_changed_uses_iso_proof_time_not_build_time(self) -> None:
        trigger_run_id = (
            "trigger_provisional_b2_20260630_until_1300__realtime_hint_projection_metric_20260630_until_1300__"
            "asset_index_board__index_board_1m_hint_projection_v1__atomic_rule_v1"
        )
        initial = build_plan(
            [context_row("board:TDX:BK001", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="board")],
            [hint_1m_projection_row("board", "board:TDX:BK001", "volume_up")],
            trigger_run_id=trigger_run_id,
            for_trade_date="20260630",
        )
        previous = previous_state_for_payload(initial["writes"]["common_event_outbox"][0]["payload_json"])
        previous["for_trade_date"] = "20260630"
        previous["raw_json"]["projection_30m_type"] = "shrink_down"
        previous["raw_json"]["trigger_mark_candidate"] = "30m_shrink"
        proof_time = "2026-06-30T13:00:00+08:00"
        projection = hint_1m_projection_row("board", "board:TDX:BK001", "volume_up")
        projection["metric_minute_label"] = "1300"
        projection["raw_json"] = {
            **dict(projection["raw_json"]),
            "proof": {
                "source_projection_proof_time": proof_time,
                "proof_input_time": proof_time,
                "proof_input_minute_label": "1300",
            },
        }

        plan = build_plan(
            [context_row("board:TDX:BK001", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="board")],
            [projection],
            trigger_run_id=trigger_run_id,
            for_trade_date="20260630",
            previous_trigger_states=[previous],
        )

        self.assertEqual(plan["matched_count"], 0)
        self.assertEqual(plan["state_changed_count"], 1)
        outbox = plan["writes"]["common_event_outbox"][0]
        payload = outbox["payload_json"]
        state = plan["writes"]["common_trigger_state"][0]
        self.assertEqual(outbox["event_type"], "TriggerStateChanged")
        self.assertEqual(outbox["event_time"].isoformat(), proof_time)
        self.assertEqual(payload["trigger_time"], proof_time)
        self.assertEqual(state["last_matched_at"].isoformat(), proof_time)
        self.assertEqual(payload["source_projection_proof_time"], proof_time)
        self.assertEqual(payload["projection_trace"]["metric_minute_label"], "1300")
        self.assertEqual(payload["projection_trace"]["trigger_time"], proof_time)

    def test_hint_v2_missing_iso_proof_time_emits_no_state_changed_from_previous_baseline(self) -> None:
        previous = previous_state_for_payload(
            build_plan(
                [context_row("board:TDX:BK001", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="board")],
                [hint_1m_projection_row("board", "board:TDX:BK001", "volume_up")],
                trigger_run_id=HINT_V2_TRIGGER_RUN_ID,
                for_trade_date="20260629",
            )["writes"]["common_event_outbox"][0]["payload_json"]
        )
        previous["for_trade_date"] = "20260629"
        projection = hint_1m_projection_row("board", "board:TDX:BK001", "volume_up")
        projection["metric_minute_label"] = "1300"
        projection["raw_json"] = {
            **dict(projection["raw_json"]),
            "proof": {
                "source_projection_proof_time": None,
                "proof_input_time": None,
                "proof_input_minute_label": "1300",
            },
        }

        plan = build_plan(
            [context_row("board:TDX:BK001", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="board")],
            [projection],
            trigger_run_id=HINT_V2_TRIGGER_RUN_ID,
            for_trade_date="20260629",
            previous_trigger_states=[previous],
        )

        self.assertEqual(plan["matched_count"], 0)
        self.assertEqual(plan["state_changed_count"], 0)
        self.assertEqual(plan["writes"]["common_trigger_state"], [])
        self.assertEqual(plan["writes"]["common_trigger_match"], [])
        self.assertEqual(plan["writes"]["common_event_outbox"], [])

    def test_hint_v2_matched_to_inactive_state_changed_uses_iso_proof_time(self) -> None:
        trigger_run_id = (
            "trigger_provisional_b2_20260630_until_1300__realtime_hint_projection_metric_20260630_until_1300__"
            "asset_index_board__index_board_1m_hint_projection_v1__atomic_rule_v1"
        )
        previous = previous_state_for_payload(
            build_plan(
                [context_row("board:TDX:BK001", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="board")],
                [hint_1m_projection_row("board", "board:TDX:BK001", "volume_up")],
                trigger_run_id=trigger_run_id,
                for_trade_date="20260630",
            )["writes"]["common_event_outbox"][0]["payload_json"]
        )
        previous["for_trade_date"] = "20260630"
        proof_time = "2026-06-30T13:00:00+08:00"
        projection = hint_1m_projection_row("board", "board:TDX:BK001", "none")
        projection["metric_minute_label"] = "1300"
        projection["raw_json"] = {
            **dict(projection["raw_json"]),
            "proof": {
                "source_projection_proof_time": proof_time,
                "proof_input_time": proof_time,
                "proof_input_minute_label": "1300",
            },
        }

        plan = build_plan(
            [context_row("board:TDX:BK001", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="board")],
            [projection],
            trigger_run_id=trigger_run_id,
            for_trade_date="20260630",
            previous_trigger_states=[previous],
        )

        self.assertEqual(plan["matched_count"], 0)
        self.assertEqual(plan["state_changed_count"], 1)
        outbox = plan["writes"]["common_event_outbox"][0]
        payload = outbox["payload_json"]
        state = plan["writes"]["common_trigger_state"][0]
        self.assertEqual(outbox["event_type"], "TriggerStateChanged")
        self.assertEqual(payload["current_status"], "inactive")
        self.assertEqual(outbox["event_time"].isoformat(), proof_time)
        self.assertEqual(payload["trigger_time"], proof_time)
        self.assertEqual(state["cleared_at"].isoformat(), proof_time)
        self.assertEqual(payload["source_projection_proof_time"], proof_time)
        self.assertEqual(payload["projection_trace"]["metric_minute_label"], "1300")
        self.assertEqual(payload["projection_trace"]["trigger_time"], proof_time)

    def test_matched_plans_build_trigger_run_state_match_and_outbox_only(self) -> None:
        plan = build_plan(
            [
                context_row("index:SH:000016", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="index"),
                context_row("board:TDX:BK001", "sell", "SELL_HINT", ["SELL_HINT"], asset_kind="board"),
            ],
            [
                projection_row("index", "index:SH:000016", "ready", "up_volume_expanding"),
                projection_row("board", "board:TDX:BK001", "ready", "down_volume_shrinking"),
            ],
        )

        writes = plan["writes"]

        self.assertEqual(plan["status"], "passed")
        self.assertEqual(plan["matched_count"], 2)
        self.assertEqual(len(writes["common_trigger_run"]), 1)
        self.assertEqual(len(writes["common_trigger_state"]), 2)
        self.assertEqual(len(writes["common_trigger_match"]), 2)
        self.assertEqual(len(writes["common_event_outbox"]), 2)
        self.assertEqual(set(writes), PROVISIONAL_ALLOWED_WRITE_TABLES)
        for table_name in PROVISIONAL_FORBIDDEN_WRITE_TABLES:
            self.assertEqual(plan["forbidden_write_counts"][table_name], 0)
        self.assertEqual({row["event_type"] for row in writes["common_event_outbox"]}, {"TriggerMatched"})
        payload_by_condition = {
            row["payload_json"]["condition_key"]: row["payload_json"]
            for row in writes["common_event_outbox"]
        }
        self.assertEqual(payload_by_condition["BUY_HINT"]["original_condition_key"], "BUY_HINT")
        self.assertEqual(payload_by_condition["BUY_HINT"]["signal_type"], "B_BUY")
        self.assertEqual(payload_by_condition["BUY_HINT"]["trigger_type"], "BUY")
        self.assertTrue(payload_by_condition["BUY_HINT"]["n5_entry_allowed"])
        self.assertEqual(payload_by_condition["SELL_HINT"]["original_condition_key"], "SELL_HINT")
        self.assertEqual(payload_by_condition["SELL_HINT"]["signal_type"], "S_SELL")
        self.assertEqual(payload_by_condition["SELL_HINT"]["trigger_type"], "SELL")
        self.assertTrue(payload_by_condition["SELL_HINT"]["n5_entry_allowed"])
        for state in writes["common_trigger_state"]:
            assert_canonical_state_columns(self, state)

    def test_no_matched_plans_passes_without_state_match_or_outbox(self) -> None:
        plan = build_plan(
            [context_row("index:SH:000016", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="index")],
            [projection_row("index", "index:SH:000016", "ready", "flat")],
        )

        writes = plan["writes"]

        self.assertEqual(plan["status"], "passed")
        self.assertEqual(plan["matched_count"], 0)
        self.assertEqual(plan["noop_count"], 1)
        self.assertEqual(len(writes["common_trigger_run"]), 1)
        self.assertEqual(writes["common_trigger_state"], [])
        self.assertEqual(writes["common_trigger_match"], [])
        self.assertEqual(writes["common_event_outbox"], [])

    def test_unknown_hint_projection_writes_pending_market_data_without_n5_entry(self) -> None:
        plan = build_plan(
            [context_row("index:SH:000016", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="index")],
            [projection_row("index", "index:SH:000016", "ready", "unknown")],
        )

        writes = plan["writes"]

        self.assertEqual(plan["matched_count"], 0)
        self.assertEqual(len(writes["common_trigger_state"]), 1)
        self.assertEqual(writes["common_trigger_match"], [])
        self.assertEqual({row["event_type"] for row in writes["common_event_outbox"]}, {"TriggerPendingMarketData"})
        payload = writes["common_event_outbox"][0]["payload_json"]
        self.assertEqual(payload["current_status"], "pending_market_data")
        self.assertFalse(payload["trigger_live"])
        self.assertEqual(payload["projection_30m_type"], "unknown")
        self.assertFalse(payload["projection_30m_flag"])
        self.assertFalse(payload["n4_boundary"]["enters_n5"])
        self.assertFalse(payload["n5_entry_allowed"])
        assert_canonical_state_columns(self, writes["common_trigger_state"][0])

    def test_matched_unchanged_lifecycle_writes_no_duplicate_trigger_matched(self) -> None:
        initial = build_plan(
            [context_row("index:SH:000016", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="index")],
            [projection_row("index", "index:SH:000016", "ready", "up_volume_expanding")],
        )
        payload = initial["writes"]["common_event_outbox"][0]["payload_json"]

        plan = build_plan(
            [context_row("index:SH:000016", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="index")],
            [projection_row("index", "index:SH:000016", "ready", "up_volume_expanding")],
            previous_trigger_states=[previous_state_for_payload(payload)],
        )

        self.assertEqual(plan["matched_count"], 0)
        self.assertEqual(plan["state_changed_count"], 0)
        self.assertEqual(plan["writes"]["common_trigger_state"], [])
        self.assertEqual(plan["writes"]["common_trigger_match"], [])
        self.assertEqual(plan["writes"]["common_event_outbox"], [])

    def test_matched_changed_lifecycle_writes_state_changed_without_match(self) -> None:
        initial = build_plan(
            [context_row("index:SH:000016", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="index")],
            [projection_row("index", "index:SH:000016", "ready", "up_volume_expanding")],
        )
        previous = previous_state_for_payload(initial["writes"]["common_event_outbox"][0]["payload_json"])
        previous["raw_json"]["projection_30m_type"] = "shrink_down"
        previous["raw_json"]["trigger_mark_candidate"] = "30m_shrink"

        plan = build_plan(
            [context_row("index:SH:000016", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="index")],
            [projection_row("index", "index:SH:000016", "ready", "up_volume_expanding")],
            previous_trigger_states=[previous],
        )

        self.assertEqual(plan["matched_count"], 0)
        self.assertEqual(plan["state_changed_count"], 1)
        self.assertEqual(len(plan["writes"]["common_trigger_state"]), 1)
        self.assertEqual(plan["writes"]["common_trigger_match"], [])
        self.assertEqual({row["event_type"] for row in plan["writes"]["common_event_outbox"]}, {"TriggerStateChanged"})
        payload = plan["writes"]["common_event_outbox"][0]["payload_json"]
        self.assertEqual(payload["current_status"], "matched")
        self.assertTrue(payload["trigger_live"])
        self.assertFalse(payload["n4_boundary"]["enters_n5"])
        self.assertFalse(payload["n5_entry_allowed"])
        assert_canonical_state_columns(self, plan["writes"]["common_trigger_state"][0])

    def test_matched_to_inactive_lifecycle_writes_state_changed_without_match(self) -> None:
        previous = previous_state_for_payload(
            build_plan(
                [context_row("index:SH:000016", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="index")],
                [projection_row("index", "index:SH:000016", "ready", "up_volume_expanding")],
            )["writes"]["common_event_outbox"][0]["payload_json"]
        )

        plan = build_plan(
            [context_row("index:SH:000016", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="index")],
            [projection_row("index", "index:SH:000016", "ready", "flat")],
            previous_trigger_states=[previous],
        )

        self.assertEqual(plan["matched_count"], 0)
        self.assertEqual(plan["state_changed_count"], 1)
        self.assertEqual(plan["writes"]["common_trigger_state"][0]["current_status"], "inactive")
        self.assertEqual(plan["writes"]["common_trigger_match"], [])
        payload = plan["writes"]["common_event_outbox"][0]["payload_json"]
        self.assertEqual(payload["event_type"], "TriggerStateChanged")
        self.assertFalse(payload["trigger_live"])
        self.assertEqual(payload["current_status"], "inactive")
        self.assertEqual(payload["state_change_reason"], "deactivated")
        self.assertEqual(
            plan["writes"]["common_trigger_state"][0]["raw_json"]["lifecycle_output_reason"],
            "matched_to_inactive",
        )
        self.assertFalse(payload["n5_entry_allowed"])
        assert_canonical_state_columns(self, plan["writes"]["common_trigger_state"][0])

    def test_opposite_hint_projection_writes_canonical_inactive_state(self) -> None:
        cases = (
            ("buy", "BUY_HINT", "volume_up", "shrink_down", "30m_volume"),
            ("sell", "SELL_HINT", "shrink_down", "volume_up", "30m_shrink"),
        )
        for direction, condition_key, previous_type, current_type, previous_mark in cases:
            with self.subTest(condition_key=condition_key):
                identity_key = f"board:TDX:{'BK001' if direction == 'buy' else 'BK002'}"
                context = context_row(
                    identity_key,
                    direction,
                    condition_key,
                    [condition_key],
                    asset_kind="board",
                )
                initial = build_plan(
                    [context],
                    [hint_1m_projection_row("board", identity_key, previous_type)],
                )
                previous = previous_state_for_payload(
                    initial["writes"]["common_event_outbox"][0]["payload_json"]
                )

                plan = build_plan(
                    [context],
                    [hint_1m_projection_row("board", identity_key, current_type)],
                    previous_trigger_states=[previous],
                )

                self.assertEqual(plan["state_changed_count"], 1)
                self.assertEqual(plan["matched_count"], 0)
                self.assertEqual(len(plan["writes"]["common_trigger_state"]), 1)
                self.assertEqual(plan["writes"]["common_trigger_match"], [])
                self.assertEqual(len(plan["writes"]["common_event_outbox"]), 1)
                self.assertEqual(
                    {row["event_type"] for row in plan["writes"]["common_event_outbox"]},
                    {"TriggerStateChanged"},
                )
                state = plan["writes"]["common_trigger_state"][0]
                payload = plan["writes"]["common_event_outbox"][0]["payload_json"]
                self.assertEqual(payload["current_status"], "inactive")
                self.assertFalse(payload["trigger_live"])
                self.assertEqual(payload["trigger_mark_candidate"], "normal")
                self.assertFalse(payload["projection_30m_flag"])
                self.assertEqual(payload["projection_30m_type"], "none")
                self.assertEqual(payload["previous_projection_30m_type"], previous_type)
                self.assertEqual(payload["previous_trigger_mark_candidate"], previous_mark)
                self.assertFalse(payload["n5_entry_allowed"])
                self.assertNotIn("ActionEligible", {row["event_type"] for row in plan["writes"]["common_event_outbox"]})
                assert_canonical_state_columns(self, state)

    def test_hint_state_insert_includes_all_canonical_typed_columns(self) -> None:
        class Cursor:
            def execute(self, sql: str, params: dict[str, object]) -> None:
                self.sql = sql
                self.params = params

            def fetchone(self) -> tuple[int]:
                return (1,)

        state = build_plan(
            [context_row("index:SH:000016", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="index")],
            [projection_row("index", "index:SH:000016", "ready", "up_volume_expanding")],
        )["writes"]["common_trigger_state"][0]
        cursor = Cursor()

        self.assertEqual(insert_provisional_trigger_state(cursor, state), 1)
        for field in CANONICAL_STATE_FIELDS:
            self.assertIn(field, cursor.sql)
            self.assertIn(field, cursor.params)

    def test_duplicate_target_run_blocks_without_upsert_or_overwrite(self) -> None:
        with self.assertRaises(ProvisionalProjectionExecuteBlocked) as raised:
            build_plan(
                [context_row("index:SH:000016", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="index")],
                [projection_row("index", "index:SH:000016", "ready", "up_volume_expanding")],
                target_counts={**empty_target_counts(), "common_trigger_run": 1},
            )

        self.assertIn("target exists", str(raised.exception))

    def test_source_event_id_dedup_key_and_payload_keep_projection_grain(self) -> None:
        projection = projection_row("index", "index:SH:000016", "ready", "up_volume_expanding")
        live_source_run_id = "live_current_1m_source_20260525_until_1415__market_data_subscription"
        projection["source_mode"] = "live_current_1m"
        projection["source_live_minute_run_id"] = live_source_run_id
        projection["c1_dependency"] = False
        projection_id = str(projection["projection_id"])
        plan = build_plan(
            [context_row("index:SH:000016", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="index")],
            [projection],
        )

        match = plan["writes"]["common_trigger_match"][0]
        outbox = plan["writes"]["common_event_outbox"][0]
        payload = outbox["payload_json"]

        self.assertEqual(match["source_event_id"], f"B2:{PROJECTION_RUN_ID}:{projection_id}")
        self.assertIn(projection_id, match["dedup_key"])
        self.assertIn(PROJECTION_RUN_ID, match["dedup_key"])
        self.assertIn("30m_volume", match["dedup_key"])
        self.assertEqual(payload["provisional"], True)
        self.assertEqual(payload["projection_run_id"], PROJECTION_RUN_ID)
        self.assertEqual(payload["source_b2_live_target_run_id"], PROJECTION_RUN_ID)
        self.assertEqual(payload["projection_id"], projection["projection_id"])
        self.assertEqual(payload["source_projection_proof_run_id"], PROJECTION_RUN_ID)
        self.assertEqual(payload["source_projection_proof_metric_id"], projection["projection_id"])
        self.assertEqual(payload["source_projection_proof_time"], "2026-05-25T14:15:00+08:00")
        self.assertTrue(payload["not_n5_final_proof"])
        self.assertEqual(payload["condition_key"], "BUY_HINT")
        self.assertEqual(payload["original_condition_key"], "BUY_HINT")
        self.assertEqual(payload["signal_type"], "B_BUY")
        self.assertEqual(payload["trigger_type"], "BUY")
        self.assertNotIn(payload["trigger_type"], {"BUY_HINT", "SELL_HINT"})
        self.assertEqual(payload["projection_30m_flag"], True)
        self.assertEqual(payload["projection_30m_type"], "volume_up")
        self.assertEqual(payload["trigger_mark_candidate"], "30m_volume")
        self.assertEqual(payload["trigger_period"], "30m")
        self.assertEqual(payload["triggered_periods"], ["30m"])
        self.assertEqual(payload["trigger_price"], match["trigger_price"])
        self.assertEqual(payload["source_mode"], "live_current_1m")
        self.assertEqual(payload["source_live_minute_run_id"], live_source_run_id)
        self.assertFalse(payload["c1_dependency"])
        self.assertTrue(payload["n4_boundary"]["enters_n5"])
        self.assertTrue(payload["n5_entry_allowed"])
        self.assertTrue(plan["event_model"]["enters_n5"])
        self.assertTrue(plan["writes"]["common_trigger_quality_item"][0]["details"]["enters_n5"])
        self.assertEqual(payload["source_condition_run_id"], SOURCE_CONDITION_RUN_ID)
        self.assertEqual(payload["trigger_context_run_id"], CONTEXT_RUN_ID)
        self.assertEqual(match["raw_json"]["source_b2_live_target_run_id"], PROJECTION_RUN_ID)
        self.assertEqual(match["raw_json"]["source_projection_proof_run_id"], PROJECTION_RUN_ID)
        self.assertEqual(match["raw_json"]["source_projection_proof_metric_id"], projection["projection_id"])
        self.assertEqual(match["raw_json"]["source_projection_proof_time"], "2026-05-25T14:15:00+08:00")
        self.assertTrue(match["raw_json"]["not_n5_final_proof"])
        self.assertEqual(match["raw_json"]["projection_trace"]["proof_kind"], "n3_b2_30m_projection")
        self.assertEqual(match["raw_json"]["condition_key"], "BUY_HINT")
        self.assertEqual(match["raw_json"]["original_condition_key"], "BUY_HINT")
        self.assertEqual(match["raw_json"]["signal_type"], "B_BUY")
        self.assertEqual(match["raw_json"]["trigger_type"], "BUY")
        self.assertTrue(match["raw_json"]["n5_entry_allowed"])
        self.assertEqual(match["raw_json"]["trigger_period"], "30m")
        self.assertEqual(match["raw_json"]["triggered_periods"], ["30m"])
        self.assertEqual(match["raw_json"]["trigger_price"], match["trigger_price"])
        self.assertEqual(match["raw_json"]["source_mode"], "live_current_1m")
        self.assertEqual(match["raw_json"]["source_live_minute_run_id"], live_source_run_id)
        self.assertFalse(match["raw_json"]["c1_dependency"])

    def test_alias_amount_source_trace_is_preserved_in_payload_and_raw_json(self) -> None:
        projection = projection_row("index", "index:SH:000016", "ready", "unknown")
        projection["source_mode"] = "live_current_1m"
        projection["c1_dependency"] = False
        projection["projected_30m_amount"] = "220"
        projection["previous_day_same_window_amount"] = "100"

        plan = build_plan(
            [context_row("index:SH:000016", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="index")],
            [projection],
        )

        self.assertEqual(plan["matched_count"], 1)
        payload = plan["writes"]["common_event_outbox"][0]["payload_json"]
        match = plan["writes"]["common_trigger_match"][0]
        self.assertEqual(payload["event_type"], "TriggerMatched")
        self.assertEqual(payload["condition_key"], "BUY_HINT")
        self.assertEqual(payload["original_condition_key"], "BUY_HINT")
        self.assertEqual(payload["signal_type"], "B_BUY")
        self.assertEqual(payload["trigger_type"], "BUY")
        self.assertTrue(payload["n4_boundary"]["enters_n5"])
        self.assertTrue(payload["n5_entry_allowed"])
        self.assertFalse(payload["n4_boundary"]["writes_inbox_or_checkpoint"])
        self.assertFalse(payload["n4_boundary"]["source_outbox_consumed"])
        self.assertFalse(payload["n4_boundary"]["downstream_layers_touched"])
        self.assertFalse(payload["n4_boundary"]["worker_started"])
        self.assertEqual(payload["source_b2_live_target_run_id"], PROJECTION_RUN_ID)
        self.assertEqual(payload["source_projection_run_id"], PROJECTION_RUN_ID)
        self.assertEqual(payload["source_mode"], "live_current_1m")
        self.assertFalse(payload["c1_dependency"])
        self.assertEqual(match["raw_json"]["trigger_type"], "BUY")
        self.assertEqual(match["raw_json"]["original_condition_key"], "BUY_HINT")
        self.assertTrue(match["raw_json"]["n5_entry_allowed"])
        self.assertEqual(
            payload["projection_trace"]["projection_30m_amount_source"],
            "projected_30m_amount",
        )
        self.assertEqual(
            payload["projection_trace"]["projection_30m_reference_source"],
            "previous_day_same_window_amount",
        )
        self.assertEqual(
            payload["projection_trace"]["projection_amount_alias_policy"],
            "b2_live_current_legacy_amount_alias_v1",
        )
        self.assertEqual(
            match["raw_json"]["projection_trace"]["projection_30m_amount_source"],
            "projected_30m_amount",
        )
        self.assertEqual(
            match["raw_json"]["projection_trace"]["projection_30m_reference_source"],
            "previous_day_same_window_amount",
        )

    def test_jsonable_normalizes_decimal_datetime_date_and_nested_values(self) -> None:
        converted = to_jsonable(
            {
                "price": Decimal("10.123456"),
                "event_time": datetime(2026, 6, 24, 13, 52, tzinfo=timezone.utc),
                "trade_date": date(2026, 6, 24),
                "nested": [{"amount": Decimal("123.45")}],
            }
        )

        json.dumps(converted)
        self.assertEqual(converted["price"], "10.123456")
        self.assertEqual(converted["event_time"], "2026-06-24T13:52:00+00:00")
        self.assertEqual(converted["trade_date"], "2026-06-24")
        self.assertEqual(converted["nested"][0]["amount"], "123.45")

    def test_execute_plan_json_payloads_are_serializable_with_db_numeric_types(self) -> None:
        projection = projection_row("index", "index:SH:000016", "ready", "up_volume_expanding")
        projection["trigger_price"] = Decimal("10.123456")
        projection["projection_trace"] = {
            "snapshot_time": datetime(2026, 6, 24, 13, 52, tzinfo=timezone.utc),
            "trade_date": date(2026, 6, 24),
            "nested": [{"amount": Decimal("123.45")}],
        }
        plan = build_plan(
            [context_row("index:SH:000016", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="index")],
            [projection],
        )

        writes = plan["writes"]
        payloads = [
            writes["common_trigger_state"][0]["raw_json"],
            writes["common_trigger_match"][0]["raw_json"],
            writes["common_event_outbox"][0]["payload_json"],
        ]

        for payload in payloads:
            json.dumps(payload)
        self.assertEqual({row["event_type"] for row in writes["common_event_outbox"]}, {"TriggerMatched"})

    def test_asset_specific_projection_identity_columns_normalize_to_identity_key(self) -> None:
        rows = [
            normalize_provisional_projection_row(
                "stock",
                {"stock_identity_key": "stock:SH:600000", "projection_id": 1, "projection_run_id": PROJECTION_RUN_ID},
            ),
            normalize_provisional_projection_row(
                "index",
                {"index_identity_key": "index:SH:000300", "projection_id": 2, "projection_run_id": PROJECTION_RUN_ID},
            ),
            normalize_provisional_projection_row(
                "board",
                {"board_identity_key": "board:TDX:881001", "projection_id": 3, "projection_run_id": PROJECTION_RUN_ID},
            ),
        ]

        self.assertEqual([row["asset_kind"] for row in rows], ["stock", "index", "board"])
        self.assertEqual(
            [row["identity_key"] for row in rows],
            ["stock:SH:600000", "index:SH:000300", "board:TDX:881001"],
        )

    def test_missing_projection_identity_alias_stays_projection_missing_until_normalized(self) -> None:
        raw_projection = projection_row("index", "index:SH:000016", "ready", "up_volume_expanding")
        raw_projection["index_identity_key"] = raw_projection.pop("identity_key")

        missing_alias_plan = build_plan(
            [context_row("index:SH:000016", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="index")],
            [raw_projection],
        )
        normalized_plan = build_plan(
            [context_row("index:SH:000016", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="index")],
            [normalize_provisional_projection_row("index", raw_projection)],
        )

        self.assertEqual(missing_alias_plan["matched_count"], 0)
        self.assertEqual(missing_alias_plan["summary"]["noop_by_projection_signal_status"], {"missing": 1})
        self.assertEqual(normalized_plan["matched_count"], 1)
        self.assertEqual(normalized_plan["summary"]["output_event_types"], {"TriggerMatched": 1})

    def test_execute_module_keeps_state_changed_boundary_and_does_not_use_legacy_route(self) -> None:
        import ashare_v3.trigger.provisional_projection_execute as provisional_projection_execute

        module_source = inspect.getsource(provisional_projection_execute)

        self.assertEqual(provisional_projection_execute.PROVISIONAL_PENDING_EVENT_TYPE, "TriggerPendingMarketData")
        self.assertEqual(provisional_projection_execute.PROVISIONAL_STATE_CHANGED_EVENT_TYPE, "TriggerStateChanged")
        self.assertNotIn("projection_matcher_execute", module_source)
        self.assertNotIn("INSERT INTO common_event_inbox", module_source)
        self.assertNotIn("INSERT INTO common_event_consumer_checkpoint", module_source)

    def test_rollback_sql_has_full_downstream_guards_and_scoped_deletes(self) -> None:
        sql = build_provisional_rollback_sql(TRIGGER_RUN_ID)
        first_delete = sql.index("DELETE FROM")
        guard_prefix = sql[:first_delete]

        for table_name in (
            "common_event_outbox",
            "common_event_inbox",
            "common_event_consumer_checkpoint",
            "common_action_run",
            "common_action_event",
            "stock_action_fact",
            "index_action_fact",
            "board_action_fact",
            "user_projection_run",
            "user_signal_projection",
            "user_signal_card",
            "user_notification_queue",
            "sim_projection",
            "n6_virtual_account",
        ):
            self.assertIn(table_name, guard_prefix)
        self.assertIn("status IN ('delivered', 'delivering')", guard_prefix)
        self.assertIn("source_layer = 'N4_trigger'", guard_prefix)
        self.assertIn("source_run_id = v_run_id", guard_prefix)
        self.assertIn("RAISE EXCEPTION", guard_prefix)

        for table_name in (
            "common_action_run",
            "common_action_event",
            "stock_action_fact",
            "index_action_fact",
            "board_action_fact",
            "user_projection_run",
            "user_signal_projection",
            "user_signal_card",
            "user_notification_queue",
            "sim_projection",
            "n6_virtual_account",
        ):
            self.assertNotIn(f"DELETE FROM {table_name}", sql)
        self.assertIn("DELETE FROM common_event_outbox", sql)
        self.assertIn("source_run_id = v_run_id", sql)
        self.assertIn("DELETE FROM common_trigger_match WHERE run_id = v_run_id", sql)
        self.assertIn("DELETE FROM common_trigger_state WHERE run_id = v_run_id", sql)
        self.assertIn("DELETE FROM common_trigger_quality_item WHERE run_id = v_run_id", sql)
        self.assertIn("DELETE FROM common_trigger_run WHERE run_id = v_run_id", sql)


if __name__ == "__main__":
    unittest.main()
