import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAN_MD = ROOT / "docs" / "V3_REALTIME_SIGNAL_ACTION_ENGINE_EXECUTABLE_PLAN.md"
PLAN_JSON = ROOT / "docs" / "V3_REALTIME_SIGNAL_ACTION_ENGINE_EXECUTABLE_PLAN.json"


class V3RealtimeSignalActionEnginePlanTest(unittest.TestCase):
    def test_plan_artifacts_freeze_user_confirmed_runtime_semantics(self):
        plan = json.loads(PLAN_JSON.read_text(encoding="utf-8"))
        md = PLAN_MD.read_text(encoding="utf-8")

        self.assertEqual(plan["result"], "PLAN_PASS")
        self.assertEqual(plan["runtime_cadence"]["first_version"], "launchd_run_once_start_interval_3_seconds")
        self.assertEqual(plan["runtime_cadence"]["long_running_worker"], "deferred")
        self.assertFalse(plan["side_effects"]["database_written"])
        self.assertFalse(plan["side_effects"]["scheduler_modified"])
        self.assertFalse(plan["side_effects"]["n6_voice_mobile_sim_trade_touched"])

        self.assertEqual(plan["n4_contract"]["canonical_events"], [
            "TriggerMatched",
            "TriggerPendingMarketData",
            "TriggerStateChanged",
        ])
        self.assertEqual(plan["n4_contract"]["runtime_signal_type"], ["B_BUY", "S_SELL"])
        self.assertEqual(
            plan["n4_contract"]["forming_metric_policy"],
            "may_consume_n3_standard_realtime_virtual_metric_not_raw_unclosed_k",
        )
        self.assertEqual(plan["n5_contract"]["action_entry_event"], "TriggerMatched")
        self.assertEqual(plan["n5_contract"]["canonical_events"], [
            "ActionEligible",
            "ActionBlocked",
            "ActionExecuted",
            "ActionSkipped",
        ])
        self.assertEqual(
            plan["n5_contract"]["action_executed_policy"],
            "trigger_time_virtual_120_30_5_snapshot_plus_closed_trigger_1m",
        )

        self.assertEqual(plan["n3_metric_contract"]["covered_periods"], [
            "1m",
            "5m",
            "30m",
            "120m",
            "D",
            "W",
            "M",
            "Q",
            "Y",
        ])
        required_fields = set(plan["n3_metric_contract"]["required_fields"])
        for field in {
            "metric_time_label",
            "source_time",
            "observed_at",
            "session_kind",
            "period_source",
            "is_closed_1m",
            "is_auction_virtual",
            "midday_bridge_policy",
            "source_minute_refs",
            "snapshot_id",
            "event_id",
            "quality_status",
            "trace_json",
        }:
            self.assertIn(field, required_fields)

        self.assertEqual(
            plan["session_policy"]["auction_0920_0930"],
            "mootdx_0931_label_kline_is_auction_realtime_virtual_1m",
        )
        self.assertEqual(
            plan["session_policy"]["midday_bridge"],
            "13:00_label_equivalent_to_missing_11:30_bar;13:01_compares_with_13:00",
        )
        self.assertIn("MinuteBarClosed 不作为 fast-lane blocker", md)
        self.assertIn("不改 N4/N5 当前业务规则", md)

    def test_legacy_conflict_is_superseded_without_changing_n4_n5_rules(self):
        plan = json.loads(PLAN_JSON.read_text(encoding="utf-8"))
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        runtime_spec = (ROOT / "docs" / "V3_TRIGGER_ACTION_RUNTIME_SPEC.md").read_text(encoding="utf-8")

        self.assertIn("n4_unclosed_raw_minute_boundary", plan["conflict_resolutions"])
        self.assertEqual(
            plan["conflict_resolutions"]["n4_unclosed_raw_minute_boundary"]["resolution"],
            "supersede_old_blanket_ban_with_n3_standard_virtual_metric_allowance",
        )
        self.assertIn("N4 不得直接读取 raw 未闭合分钟 K", agents)
        self.assertIn("允许消费 N3 标准化、可追溯 realtime virtual metric", agents)
        self.assertIn("V3_REALTIME_SIGNAL_ACTION_ENGINE_EXECUTABLE_PLAN", runtime_spec)
        self.assertIn("不改 N4/N5 当前业务规则", runtime_spec)


if __name__ == "__main__":
    unittest.main()
