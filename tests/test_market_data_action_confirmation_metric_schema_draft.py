import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_SQL = ROOT / "sql/032_n3_action_confirmation_metric_schema.sql"
SCHEMA_ROLLBACK_SQL = ROOT / "sql/032_n3_action_confirmation_metric_schema_rollback.sql"
BUSINESS_ROLLBACK_SQL = ROOT / "sql/N3_action_confirmation_projection_metric_business_rollback.sql"
READINESS_JSON = ROOT / "docs/N3_action_confirmation_projection_facts_schema_readiness.json"
PREFLIGHT_JSON = ROOT / "docs/N3_action_confirmation_projection_facts_preflight_draft.json"
TESTS_JSON = ROOT / "docs/N3_action_confirmation_projection_facts_tests_draft.json"
PREFLIGHT_MD = ROOT / "docs/N3_ACTION_CONFIRMATION_PROJECTION_FACTS_PREFLIGHT_DRAFT.md"


class MarketDataActionConfirmationMetricSchemaDraftTest(unittest.TestCase):
    def test_schema_declares_three_physical_metric_tables(self) -> None:
        sql = SCHEMA_SQL.read_text()

        for asset_kind in ("stock", "index", "board"):
            table = f"{asset_kind}_action_confirmation_projection_metric"
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", sql)
            self.assertIn(f"CHECK (asset_kind = '{asset_kind}')", sql)
            self.assertIn(f"CHECK (identity_key LIKE '{asset_kind}:%')", sql)

        self.assertNotIn("common_action_confirmation_projection_metric", sql)

    def test_schema_covers_canonical_metric_fields(self) -> None:
        sql = SCHEMA_SQL.read_text()
        required_fields = {
            "current_price",
            "current_price_source",
            "current_price_time",
            "previous_120m_body_high",
            "previous_120m_body_low",
            "previous_30m_body_high",
            "previous_30m_body_low",
            "previous_5m_body_high",
            "previous_5m_body_low",
            "previous_1m_body_high",
            "previous_1m_body_low",
            "current_1m_amount",
            "previous_1m_amount",
            "current_5m_virtual_amount",
            "previous_5m_full_amount",
            "is_first_1m_of_day",
            "is_first_5m_of_day",
            "is_first_30m_of_day",
            "is_first_120m_of_day",
            "first_1m_amount_default_pass",
            "first_5m_amount_default_pass",
            "previous_1m_period_source",
            "previous_5m_period_source",
            "previous_30m_period_source",
            "previous_120m_period_source",
            "boundary_policy_version",
            "source_fact_ids",
            "source_minute_refs",
            "previous_day_minute_refs",
            "projection_run_id",
            "projection_schema_version",
            "source_snapshot_event_id",
            "metric_quality_status",
            "metric_ready",
        }

        missing = sorted(field for field in required_fields if field not in sql)

        self.assertEqual(missing, [])

    def test_metric_ready_requires_trace_refs_at_database_layer(self) -> None:
        sql = SCHEMA_SQL.read_text()

        self.assertIn("jsonb_typeof(source_fact_ids) = 'object'", sql)
        self.assertIn("source_fact_ids <> '{}'::JSONB", sql)
        self.assertIn("jsonb_typeof(source_minute_refs) = 'array'", sql)
        self.assertIn("jsonb_array_length(source_minute_refs) > 0", sql)
        self.assertIn("previous_trade_date_last_period", sql)
        self.assertIn("jsonb_typeof(previous_day_minute_refs) = 'array'", sql)
        self.assertIn("jsonb_array_length(previous_day_minute_refs) > 0", sql)

    def test_schema_is_additive_and_does_not_touch_events_or_downstream(self) -> None:
        sql = SCHEMA_SQL.read_text()

        self.assertIn("CREATE TABLE IF NOT EXISTS", sql)
        self.assertIn("CREATE INDEX IF NOT EXISTS", sql)
        self.assertIsNone(re.search(r"\b(ALTER|INSERT|UPDATE|DELETE|TRUNCATE|DROP)\b", sql, flags=re.IGNORECASE))
        self.assertNotIn("common_event_outbox", sql)
        self.assertNotIn("common_event_inbox", sql)
        self.assertNotIn("common_event_consumer_checkpoint", sql)
        self.assertNotIn("trigger_", sql)
        self.assertNotIn("action_fact", sql)
        self.assertNotIn("user_", sql)
        self.assertNotIn("voice_", sql)
        self.assertNotIn("sim_", sql)
        self.assertNotIn("position_", sql)

    def test_rollback_guards_are_scoped_and_hard_fail(self) -> None:
        schema_rollback = SCHEMA_ROLLBACK_SQL.read_text()
        business_rollback = BUSINESS_ROLLBACK_SQL.read_text()

        self.assertIn("DO $$", schema_rollback)
        self.assertIn("RAISE EXCEPTION", schema_rollback)
        self.assertIn("action_confirmation metric schema rollback blocked", schema_rollback)
        self.assertIn("stock_count", schema_rollback)
        self.assertIn("index_count", schema_rollback)
        self.assertIn("board_count", schema_rollback)
        self.assertIn("DROP TABLE IF EXISTS board_action_confirmation_projection_metric", schema_rollback)

        self.assertIn("\\set projection_run_id", business_rollback)
        self.assertIn("set_config('app.projection_run_id'", business_rollback)
        self.assertIn("DO $$", business_rollback)
        self.assertIn("RAISE EXCEPTION", business_rollback)
        self.assertIn("action_confirmation metric business rollback blocked", business_rollback)
        self.assertIn("outbox_refs", business_rollback)
        self.assertIn("inbox_refs", business_rollback)
        self.assertIn("checkpoint_refs", business_rollback)
        self.assertIn("WHERE projection_run_id = :'projection_run_id'", business_rollback)
        self.assertNotIn("DELETE FROM stock_realtime_daily_snapshot", business_rollback)
        self.assertNotIn("DELETE FROM common_event_outbox", business_rollback)
        self.assertNotIn("DELETE FROM trigger_", business_rollback)
        self.assertNotIn("DELETE FROM action_", business_rollback)

    def test_json_artifacts_are_valid_and_boundary_is_n3_owned(self) -> None:
        readiness = json.loads(READINESS_JSON.read_text())
        preflight = json.loads(PREFLIGHT_JSON.read_text())
        tests = json.loads(TESTS_JSON.read_text())
        preflight_md = PREFLIGHT_MD.read_text()

        self.assertEqual(readiness["result"], "DRAFT_PASS")
        self.assertTrue(readiness["schema_decision"]["physical_separation"])
        self.assertEqual(
            readiness["metric_ready_trace_refs_strategy"]["mode"],
            "db_hard_guard_plus_preflight_p0",
        )
        self.assertEqual(readiness["quality"]["p0_count"], 0)
        self.assertEqual(
            preflight["metric_ready_trace_refs_strategy"]["mode"],
            "db_hard_guard_plus_preflight_p0",
        )
        self.assertIn("common_event_outbox", preflight["forbidden_writes_future_execute"])
        self.assertIn("n3_action_confirmation_no_n4_n5_n6_writes", preflight["p0_gate_codes"])
        self.assertTrue(tests["coverage"]["rollback_hard_fail_guard"])
        self.assertTrue(tests["coverage"]["metric_ready_trace_db_hard_guard"])
        self.assertTrue(tests["coverage"]["n4_n5_no_recomputation_boundary"])
        self.assertIn("N4 must not read raw minute rows", preflight_md)
        self.assertIn("N5 must not trust opaque", preflight_md)


if __name__ == "__main__":
    unittest.main()
