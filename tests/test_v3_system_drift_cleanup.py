import inspect
import unittest
from pathlib import Path

import run_v3_realtime_engine_once as realtime_engine
import run_v3_20260615_full_universe_replay_once as full_universe_replay
from ashare_v3.action import dry_run as action_dry_run
from ashare_v3.action import execute as action_execute
from ashare_v3.condition import schema_migration_readiness
from ashare_v3.market import b_buy_s_sell_replay_compare
from ashare_v3.market import v3_full_day_replay_plan
from ashare_v3.trigger import projection_matcher


REPO_ROOT = Path(__file__).resolve().parents[1]


class V3SystemDriftCleanupTest(unittest.TestCase):
    def test_full_universe_replay_script_is_plan_only_and_has_no_downstream_execute_imports(self) -> None:
        source = Path(full_universe_replay.__file__).read_text(encoding="utf-8")

        self.assertTrue(full_universe_replay.RUNTIME_CONTROL_PLAN_ONLY)
        self.assertEqual(full_universe_replay.ORCHESTRATION_MODE, "runtime_control_plan_only")
        self.assertFalse(full_universe_replay.CROSS_LAYER_EXECUTION_ALLOWED)
        self.assertNotIn("from ashare_v3.action.execute import", source)
        self.assertNotIn("from ashare_v3.user.projection_execute import", source)
        self.assertNotIn("from run_v3_20260612_n4_full_day_trigger_replay_once import", source)
        self.assertNotIn("run_action_consumer_once(", source)
        self.assertNotIn("run_projection_shadow_execute(", source)
        self.assertNotIn("execute_replay(", source)

    def test_realtime_engine_is_registered_as_runtime_control_orchestrator_only(self) -> None:
        self.assertTrue(realtime_engine.RUNTIME_CONTROL_ORCHESTRATOR)
        self.assertEqual(realtime_engine.ORCHESTRATOR_BOUNDARY, "runtime_control_only")
        self.assertEqual(
            realtime_engine.ORCHESTRATOR_ALLOWED_CHILD_STAGES,
            ("N3_REALTIME_VIRTUAL_METRIC", "N4_TRIGGER", "N5_ACTION", "N6_USER_PROJECTION"),
        )

    def test_projection_matcher_keeps_legacy_30m_signals_trace_only(self) -> None:
        self.assertEqual(
            projection_matcher.LEGACY_TRACE_ONLY_SIGNAL_TYPES,
            ("B_BUY_30M_VOL", "S_SELL_30M_SHRINK"),
        )
        self.assertNotIn("B_BUY_30M_VOL", projection_matcher.PROJECTION_SIGNAL_TYPES)
        self.assertNotIn("S_SELL_30M_SHRINK", projection_matcher.PROJECTION_SIGNAL_TYPES)
        self.assertIsNone(
            projection_matcher.projection_signal_type_for_context(
                {"direction": "buy", "condition_key": "BUY:D", "allowed_signal_types": ["B_BUY_30M_VOL"]}
            )
        )
        self.assertFalse(projection_matcher.projection_matches_signal("B_BUY_30M_VOL", "up_volume_expanding"))
        self.assertFalse(projection_matcher.projection_matches_signal("S_SELL_30M_SHRINK", "down_volume_shrinking"))

    def test_condition_schema_readiness_uses_only_canonical_n2_signal_literals(self) -> None:
        self.assertEqual(
            schema_migration_readiness.CANONICAL_N2_SIGNAL_LITERALS,
            ("BUY", "SELL", "BUY:FULL", "SELL:FULL", "BUY_HINT", "SELL_HINT"),
        )
        report = schema_migration_readiness.build_condition_schema_migration_readiness_report_from_sql(
            _minimal_condition_schema_sql(schema_migration_readiness.CANONICAL_N2_SIGNAL_LITERALS)
        )
        gate = next(item for item in report.quality_gates if item.gate_name == "condition_schema_standard_signal_whitelist")
        self.assertEqual(gate.status, "passed")
        self.assertNotIn("B_BUY_30M_VOL", gate.expected_value)
        self.assertNotIn("S_SELL_30M_SHRINK", gate.expected_value)

    def test_target_machine_compare_requires_explicit_path_and_confirmation(self) -> None:
        self.assertIsNone(b_buy_s_sell_replay_compare.TARGET_DB_PATH)
        self.assertFalse(hasattr(b_buy_s_sell_replay_compare, "DEFAULT_TARGET_DB_PATH"))
        with self.assertRaises(b_buy_s_sell_replay_compare.OldSystemReadConfirmationRequired):
            b_buy_s_sell_replay_compare.load_target_actions(None, trade_date="20260612")
        with self.assertRaises(b_buy_s_sell_replay_compare.OldSystemReadConfirmationRequired):
            b_buy_s_sell_replay_compare.load_target_actions(
                "/tmp/monitor.db",
                trade_date="20260612",
                old_system_read_confirmed=False,
            )

    def test_n5_execution_accepts_only_trigger_matched(self) -> None:
        self.assertEqual(action_execute.N5_CONSUMPTION_ONLY_SMOKE_ALLOWED_EVENT_TYPES, ("TriggerMatched",))
        self.assertIsNone(
            action_dry_run.infer_canonical_action_event_type(
                source_trigger_event_type="TriggerStateChanged",
                candidate_kind="state_gate",
                action_state="expired",
            )
        )
        self.assertEqual(
            action_dry_run.infer_canonical_action_event_type(
                source_trigger_event_type="TriggerMatched",
                candidate_kind="confirmation",
                action_state="executed",
            ),
            "ActionExecuted",
        )

    def test_n3_full_day_plan_has_no_downstream_run_id_generation(self) -> None:
        self.assertFalse(hasattr(v3_full_day_replay_plan, "N4_FULL_DAY_REPLAY_RUN_ID"))
        self.assertFalse(hasattr(v3_full_day_replay_plan, "N5_FULL_DAY_REPLAY_RUN_ID"))
        self.assertFalse(hasattr(v3_full_day_replay_plan, "N5_FULL_DAY_REPLAY_CONSUMER_NAME"))
        source = inspect.getsource(v3_full_day_replay_plan)
        self.assertNotIn("v3_n4_trigger_replay_", source)
        self.assertNotIn("v3_n5_action_replay_", source)


def _minimal_condition_schema_sql(signals: tuple[str, ...]) -> str:
    table_sql = "\n".join(f"CREATE TABLE {table_name} (id BIGINT);" for table_name in schema_migration_readiness.REQUIRED_SCHEMA_TABLES)
    index_sql = "\n".join(f"CREATE INDEX idx_test_{i} ON {table_name}(id);" for i, table_name in enumerate(schema_migration_readiness.REQUIRED_SCHEMA_TABLES))
    signal_values = ", ".join(f"'{signal}'" for signal in signals)
    return f"""
BEGIN;
{table_sql}
ALTER TABLE stock_condition_pool ADD COLUMN allowed_signal_types TEXT[] CHECK (allowed_signal_types <@ ARRAY[{signal_values}]);
ALTER TABLE index_minute_target_scope ADD COLUMN source_trade_date TEXT;
ALTER TABLE board_minute_target_scope ADD COLUMN previous_day_minute_date TEXT;
{index_sql}
-- total_mv >= market_value_threshold
-- source_trade_date = prev_trade_date
-- previous_day_minute_date = prev_trade_date
COMMIT;
"""


if __name__ == "__main__":
    unittest.main()
