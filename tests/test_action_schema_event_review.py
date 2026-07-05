import unittest
from pathlib import Path

from ashare_v3.action.schema_event_review import (
    DEFAULT_N5_2_SCHEMA_PATH,
    PROJECT_ROOT,
    REQUIRED_N5_SCHEMA_TABLES,
    REQUIRED_PAYLOAD_KEYS,
    build_n5_schema_event_contract_review,
    scan_forbidden_text,
)


class ActionSchemaEventReviewTest(unittest.TestCase):
    def test_current_n5_schema_event_contract_review_is_canonical(self) -> None:
        schema_text = (PROJECT_ROOT / DEFAULT_N5_2_SCHEMA_PATH).read_text(encoding="utf-8")
        report = build_n5_schema_event_contract_review(schema_text=schema_text, scan_files=[])

        self.assertTrue(report["passed"])
        self.assertEqual(report["quality"]["p0_count"], 0)
        self.assertEqual(report["schema_review"]["missing_tables"], [])
        self.assertEqual(report["schema_review"]["missing_required_literals"], [])
        self.assertEqual(
            set(report["schema_review"]["physical_action_fact_tables"]),
            {"stock_action_fact", "index_action_fact", "board_action_fact"},
        )
        for legacy in (
            "TriggerCleared",
            "ActionEvent",
            "HintEvent",
            "RiskEvent",
            "PositionEvent",
            "B_BUY_30M_VOL",
            "S_SELL_30M_SHRINK",
            "'BUY_HINT'",
            "'SELL_HINT'",
        ):
            self.assertNotIn(legacy, schema_text)
        for canonical in (
            "TriggerMatched",
            "TriggerPendingMarketData",
            "TriggerStateChanged",
            "ActionEligible",
            "ActionBlocked",
            "ActionExecuted",
            "ActionSkipped",
        ):
            self.assertIn(canonical, schema_text)

    def test_review_declares_required_tables_and_payload_keys(self) -> None:
        schema_text = (PROJECT_ROOT / DEFAULT_N5_2_SCHEMA_PATH).read_text(encoding="utf-8")
        report = build_n5_schema_event_contract_review(schema_text=schema_text, scan_files=[])

        self.assertEqual(tuple(report["schema_review"]["required_tables"]), REQUIRED_N5_SCHEMA_TABLES)
        for key in REQUIRED_PAYLOAD_KEYS:
            self.assertIn(key, report["event_contract"]["payload_required_keys"])
        self.assertIn("source_trigger_match_id", report["event_contract"]["payload_required_keys"])
        self.assertIn("source_market_trace", report["event_contract"]["payload_required_keys"])

    def test_forbidden_user_voice_sim_and_trade_patterns_are_detected(self) -> None:
        text = """
        CREATE TABLE user_card_projection (id bigint);
        INSERT INTO common_event_inbox VALUES (1);
        event_type = "UserActionEvent";
        place_order();
        """
        findings = scan_forbidden_text("sample", text)

        self.assertGreaterEqual(len(findings), 4)


if __name__ == "__main__":
    unittest.main()
