import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_JSON = ROOT / "docs/V3_REALTIME_VIRTUAL_METRIC_SCHEMA_CONTRACT.json"
CONTRACT_MD = ROOT / "docs/V3_REALTIME_VIRTUAL_METRIC_SCHEMA_CONTRACT.md"
DRY_RUN_JSON = ROOT / "docs/V3_REALTIME_VIRTUAL_METRIC_SCHEMA_DRY_RUN.json"
PREFLIGHT_JSON = ROOT / "docs/V3_REALTIME_VIRTUAL_METRIC_SCHEMA_PREFLIGHT.json"
DRY_RUN_MD = ROOT / "docs/V3_REALTIME_VIRTUAL_METRIC_SCHEMA_DRY_RUN.md"
PREFLIGHT_MD = ROOT / "docs/V3_REALTIME_VIRTUAL_METRIC_SCHEMA_PREFLIGHT.md"
SCHEMA_SQL = ROOT / "sql/039_v3_realtime_virtual_metric_schema_draft.sql"
ROLLBACK_SQL = ROOT / "sql/039_v3_realtime_virtual_metric_schema_rollback_draft.sql"


class V3RealtimeVirtualMetricSchemaContractTest(unittest.TestCase):
    def test_contract_json_freezes_n3_metric_ownership_and_physical_tables(self) -> None:
        contract = json.loads(CONTRACT_JSON.read_text())

        self.assertEqual(contract["result"], "CONTRACT_PASS")
        self.assertEqual(contract["layer_owner"], "N3_market_data")
        self.assertFalse(contract["side_effects"]["database_written"])
        self.assertFalse(contract["side_effects"]["worker_started"])
        self.assertFalse(contract["side_effects"]["n6_entered"])
        self.assertEqual(
            contract["physical_tables"],
            [
                "stock_action_confirmation_projection_metric",
                "index_action_confirmation_projection_metric",
                "board_action_confirmation_projection_metric",
            ],
        )
        self.assertTrue(contract["n3_metric_ownership"]["n3_is_unique_metric_source"])
        self.assertTrue(contract["n3_metric_ownership"]["n4_must_not_read_raw_minute_rows"])
        self.assertTrue(contract["n3_metric_ownership"]["n5_must_not_pull_market_data"])

    def test_contract_covers_realtime_periods_and_session_policies(self) -> None:
        contract = json.loads(CONTRACT_JSON.read_text())

        self.assertEqual(contract["periods"], ["1m", "5m", "30m", "120m", "D", "W", "M", "Q", "Y"])
        self.assertEqual(
            contract["session_policies"]["auction_0920_0930"],
            "mootdx_0931_label_as_auction_realtime_virtual_1m",
        )
        self.assertEqual(
            contract["session_policies"]["midday_bridge"],
            "13:00_label_equivalent_to_missing_11:30_for_13:01_previous_1m",
        )
        self.assertEqual(
            contract["session_policies"]["minute_bar_closed_fastlane"],
            "MinuteBarClosed_not_fast_lane_blocker",
        )

    def test_contract_fields_cover_n4_and_n5_required_metrics(self) -> None:
        contract = json.loads(CONTRACT_JSON.read_text())
        fields = set(contract["field_registry"]["columns"])
        required = {
            "source_time",
            "observed_at",
            "snapshot_id",
            "event_id",
            "quality_status",
            "session_kind",
            "period_source",
            "is_closed_1m",
            "is_auction_virtual",
            "midday_bridge_policy",
            "deterministic_pass_flags",
            "current_30m_virtual_amount",
            "previous_day_same_window_amount",
            "previous_30m_full_amount",
            "current_120m_virtual_amount",
            "previous_120m_full_amount",
            "current_d_virtual_amount",
            "previous_d_amount",
            "current_w_virtual_amount",
            "previous_w_amount",
            "current_m_virtual_amount",
            "previous_m_amount",
            "current_q_virtual_amount",
            "previous_q_amount",
            "current_y_virtual_amount",
            "previous_y_amount",
            "current_30m_body_high",
            "current_30m_body_low",
            "previous_30m_body_high",
            "previous_30m_body_low",
            "current_d_body_high",
            "current_d_body_low",
            "previous_d_body_high",
            "previous_d_body_low",
            "trace_json",
        }

        self.assertEqual(sorted(required - fields), [])
        self.assertNotIn("current_D_virtual_amount", fields)
        self.assertNotIn("previous_Y_amount", fields)
        aliases = contract["field_registry"]["display_alias_to_db_column"]
        self.assertEqual(aliases["current_D_virtual_amount"], "current_d_virtual_amount")
        self.assertEqual(aliases["previous_Y_amount"], "previous_y_amount")

    def test_schema_sql_is_additive_physical_and_non_destructive(self) -> None:
        sql = SCHEMA_SQL.read_text()

        for asset_kind in ("stock", "index", "board"):
            table = f"{asset_kind}_action_confirmation_projection_metric"
            self.assertIn(f"ALTER TABLE {table}", sql)
            self.assertIn("ADD COLUMN IF NOT EXISTS source_time TIMESTAMPTZ", sql)
            self.assertIn("ADD COLUMN IF NOT EXISTS snapshot_id BIGINT", sql)
            self.assertIn("ADD COLUMN IF NOT EXISTS event_id TEXT", sql)
            self.assertIn("ADD COLUMN IF NOT EXISTS quality_status TEXT", sql)
            self.assertIn("ADD COLUMN IF NOT EXISTS deterministic_pass_flags JSONB", sql)
            self.assertIn("ADD COLUMN IF NOT EXISTS current_y_virtual_amount NUMERIC", sql)
            self.assertIn("ADD COLUMN IF NOT EXISTS trace_json JSONB", sql)

        self.assertNotRegex(sql, r"\bcurrent_[DWMQY]_")
        self.assertNotRegex(sql, r"\bprevious_[DWMQY]_")
        self.assertIsNone(re.search(r"\b(INSERT|UPDATE|DELETE|TRUNCATE|DROP)\b", sql, flags=re.IGNORECASE))
        self.assertNotIn("common_event_outbox", sql)
        self.assertNotIn("common_event_inbox", sql)
        self.assertNotIn("common_event_consumer_checkpoint", sql)
        self.assertNotIn("trigger_", sql)
        self.assertNotIn("action_event", sql)
        self.assertNotIn("user_", sql)
        self.assertNotIn("voice_", sql)
        self.assertNotIn("sim_", sql)
        self.assertNotIn("real_trade", sql)

    def test_rollback_draft_hard_fails_before_any_destructive_statement(self) -> None:
        rollback = ROLLBACK_SQL.read_text()
        first_raise = rollback.index("RAISE EXCEPTION")
        destructive_positions = [
            pos
            for token in ("DROP", "DELETE", "UPDATE", "ALTER TABLE")
            if (pos := rollback.find(token)) >= 0
        ]

        self.assertLess(first_raise, min(destructive_positions))
        self.assertIn("v3 realtime virtual metric schema rollback blocked by default", rollback)
        self.assertIn("stock_action_confirmation_projection_metric", rollback)
        self.assertIn("index_action_confirmation_projection_metric", rollback)
        self.assertIn("board_action_confirmation_projection_metric", rollback)
        self.assertIn("downstream_refs", rollback)
        self.assertNotRegex(rollback, r"\bcurrent_[DWMQY]_")
        self.assertNotRegex(rollback, r"\bprevious_[DWMQY]_")
        self.assertNotIn("CASCADE", rollback.upper())
        self.assertNotIn("TRUNCATE", rollback.upper())

    def test_markdown_mentions_no_n4_n5_business_rule_change(self) -> None:
        md = CONTRACT_MD.read_text()

        self.assertIn("不改 N4/N5 当前业务规则", md)
        self.assertIn("N4 可以消费 N3 标准化、可追溯 realtime virtual metric", md)
        self.assertIn("N5 不拉行情、不拼 raw 分钟", md)
        self.assertIn("ActionExecuted 不代表下单、sim、语音、N6 展示或真实交易", md)

    def test_dry_run_and_preflight_artifacts_exist_and_are_side_effect_free(self) -> None:
        dry_run = json.loads(DRY_RUN_JSON.read_text())
        preflight = json.loads(PREFLIGHT_JSON.read_text())
        dry_md = DRY_RUN_MD.read_text()
        preflight_md = PREFLIGHT_MD.read_text()

        self.assertEqual(dry_run["result"], "DRY_RUN_PASS")
        self.assertEqual(preflight["result"], "PREFLIGHT_PASS")
        for artifact in (dry_run, preflight):
            self.assertFalse(artifact["side_effects"]["database_written"])
            self.assertFalse(artifact["side_effects"]["migration_executed"])
            self.assertFalse(artifact["side_effects"]["n6_entered"])
            self.assertIn("sql/039_v3_realtime_virtual_metric_schema_draft.sql", artifact["paths"].values())
        self.assertIn("DRY_RUN_PASS", dry_md)
        self.assertIn("PREFLIGHT_PASS", preflight_md)


if __name__ == "__main__":
    unittest.main()
