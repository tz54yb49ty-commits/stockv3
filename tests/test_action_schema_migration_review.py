import unittest

from ashare_v3.action.schema_migration_review import (
    ALLOWED_N5_TABLES,
    DEFAULT_N5_3_SCHEMA_PATH,
    PROJECT_ROOT,
    build_n5_action_schema_migration_review,
)


class ActionSchemaMigrationReviewTest(unittest.TestCase):
    def test_current_action_schema_migration_review_reports_canonical_payload_divergence(self) -> None:
        schema_text = (PROJECT_ROOT / DEFAULT_N5_3_SCHEMA_PATH).read_text(encoding="utf-8")
        report = build_n5_action_schema_migration_review(schema_text=schema_text)

        self.assertFalse(report["passed"])
        self.assertEqual(report["quality"]["p0_count"], 1)
        self.assertEqual(report["migration_review"]["created_tables"], list(ALLOWED_N5_TABLES))
        self.assertTrue(report["migration_review"]["additive_only"])
        self.assertEqual(report["migration_review"]["unsafe_statements"], [])
        self.assertEqual(report["migration_review"]["index_target_violations"], [])
        for literal in (
            "source_trigger_state_id",
            "original_condition_key",
            "action_state",
            "confirmation_status",
            "action_policy",
            "trace_json",
            "ActionEligible",
            "ActionBlocked",
            "ActionExecuted",
            "ActionSkipped",
        ):
            self.assertIn(literal, report["migration_review"]["payload_contract_missing"])
        self.assertFalse(report["side_effects"]["migration_executed"])

    def test_destructive_or_business_write_sql_is_rejected(self) -> None:
        schema_text = """
        BEGIN;
        CREATE TABLE common_action_run (run_id TEXT PRIMARY KEY);
        INSERT INTO common_action_run (run_id) VALUES ('x');
        DROP TABLE common_action_run;
        COMMIT;
        """
        report = build_n5_action_schema_migration_review(schema_text=schema_text)

        self.assertFalse(report["passed"])
        self.assertGreater(report["quality"]["p0_count"], 0)
        self.assertFalse(report["migration_review"]["additive_only"])
        self.assertTrue(report["migration_review"]["unsafe_statements"])
        self.assertTrue(report["migration_review"]["business_data_write_statements"])

    def test_n6_tables_and_trade_execution_fields_are_rejected(self) -> None:
        schema_text = """
        BEGIN;
        CREATE TABLE user_card_projection (projection_id BIGINT);
        CREATE TABLE stock_action_fact (
          action_fact_id BIGINT,
          broker_account TEXT,
          source_trigger_event_id TEXT,
          source_trigger_match_id BIGINT,
          source_condition_run_id TEXT,
          source_market_trace JSONB,
          action_key TEXT,
          dedup_key TEXT,
          signal_type TEXT,
          direction TEXT,
          asset_kind TEXT,
          identity_key TEXT,
          event_schema_version TEXT
        );
        COMMIT;
        """
        report = build_n5_action_schema_migration_review(schema_text=schema_text)

        self.assertFalse(report["passed"])
        self.assertIn("user_card_projection", report["migration_review"]["n6_table_violations"])
        self.assertIn("stock_action_fact.broker_account", report["migration_review"]["true_trade_field_violations"])

    def test_buy_sell_hint_contract_must_not_force_hint_only(self) -> None:
        schema_text = """
        CREATE TABLE stock_action_fact (
          signal_type TEXT CHECK (signal_type IN ('B_BUY_30M_VOL', 'B_BUY', 'S_SELL_30M_SHRINK', 'S_SELL', 'BUY_HINT', 'SELL_HINT')),
          direction TEXT,
          lane TEXT CHECK (signal_type <> 'BUY_HINT' OR lane = 'hint'),
          CHECK (signal_type NOT IN ('B_BUY_30M_VOL', 'B_BUY', 'BUY_HINT') OR direction = 'buy'),
          CHECK (signal_type NOT IN ('S_SELL_30M_SHRINK', 'S_SELL', 'SELL_HINT') OR direction = 'sell')
        );
        """
        report = build_n5_action_schema_migration_review(schema_text=schema_text)

        self.assertFalse(report["migration_review"]["buy_sell_hint_contract"]["passed"])
        self.assertTrue(report["migration_review"]["buy_sell_hint_contract"]["forced_hint_only"])

    def test_rollback_preview_is_generated_but_not_executed(self) -> None:
        schema_text = (PROJECT_ROOT / DEFAULT_N5_3_SCHEMA_PATH).read_text(encoding="utf-8")
        report = build_n5_action_schema_migration_review(schema_text=schema_text)

        rollback = report["rollback_preview"]
        self.assertTrue(rollback["generated"])
        self.assertFalse(rollback["executed"])
        self.assertIn("DROP TABLE IF EXISTS common_position_event CASCADE;", rollback["sql"])


if __name__ == "__main__":
    unittest.main()
