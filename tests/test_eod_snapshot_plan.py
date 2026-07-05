import json
import unittest

from ashare_v3.market.eod_snapshot_plan import (
    build_eod_dry_run_report,
    build_eod_execute_preflight_report,
    build_write_scope_contract,
)


EOD_RUN_ID = (
    "eod_snapshot_refresh_20260525__"
    "market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute"
)


class EodSnapshotPlanTests(unittest.TestCase):
    def test_missing_official_daily_is_warning_and_blocks_execute_gate(self) -> None:
        report = build_eod_dry_run_report(
            eod_run_id=EOD_RUN_ID,
            for_trade_date="20260525",
            lineage_allowlist={"source_subscription_run_id": "subscription"},
            expected_eod_snapshot_rows={"stock": 2, "index": 1, "board": 1, "total": 4},
            source_summary={
                "source_runs": {"passed": True, "missing_or_not_passed": []},
                "b1_snapshot_rows": {"stock": 2, "index": 1, "board": 1, "total": 4},
                "c2_summary_rows": {"total": 32, "closed": 30, "missing": 2},
                "c2b_enrichment_rows": {"total": 32, "computable": 30, "unknown": 2},
                "c3_outbox": {"pending": 30, "delivered": 0, "delivering": 0, "total": 30},
                "n4_replay_audit": {"total": 10, "missing": 1, "not_ready": 0},
            },
            official_daily_status={
                "available": False,
                "missing_code": "missing_official_daily_fact",
                "missing_fact_count": 4,
                "coverage": {"stock": 0, "index": 0, "board": 0, "total": 0},
            },
            target_audit={
                "schema_tables_exist": True,
                "eod_run_exists": False,
                "target_rows_for_eod_run": {"stock": 0, "index": 0, "board": 0, "total": 0},
                "reconciliation_rows_for_eod_run": {"stock": 0, "index": 0, "board": 0, "total": 0},
                "quality_rows_for_eod_run": 0,
                "outbox_rows_for_eod_run": 0,
                "inbox_rows_for_eod_run": 0,
                "checkpoint_rows_for_eod_run": 0,
            },
        )

        self.assertEqual(report["result"], "DRY_RUN_PASS")
        self.assertFalse(report["blocked"])
        self.assertFalse(report["execute_final_gate_allowed"])
        self.assertEqual(report["execute_blocker"], "missing_official_daily_fact")
        self.assertEqual(report["quality"]["p0_count"], 0)
        self.assertGreaterEqual(report["quality"]["p1_count"], 1)
        self.assertFalse(report["side_effects"]["writes_database"])
        self.assertFalse(report["side_effects"]["consumes_c3_outbox"])
        json.dumps(report, ensure_ascii=False)

    def test_eod_scoped_existing_rows_are_p0_blocker(self) -> None:
        report = build_eod_dry_run_report(
            eod_run_id=EOD_RUN_ID,
            for_trade_date="20260525",
            lineage_allowlist={},
            expected_eod_snapshot_rows={"stock": 2, "index": 0, "board": 0, "total": 2},
            source_summary={
                "source_runs": {"passed": True, "missing_or_not_passed": []},
                "b1_snapshot_rows": {"stock": 1, "index": 0, "board": 0, "total": 1},
            },
            official_daily_status={"available": True, "missing_fact_count": 0, "coverage": {"total": 2}},
            target_audit={
                "schema_tables_exist": True,
                "eod_run_exists": True,
                "target_rows_for_eod_run": {"stock": 1, "index": 0, "board": 0, "total": 1},
                "reconciliation_rows_for_eod_run": {"stock": 0, "index": 0, "board": 0, "total": 0},
                "quality_rows_for_eod_run": 0,
                "outbox_rows_for_eod_run": 0,
                "inbox_rows_for_eod_run": 0,
                "checkpoint_rows_for_eod_run": 0,
            },
        )

        self.assertEqual(report["result"], "DRY_RUN_BLOCKED")
        self.assertTrue(report["blocked"])
        self.assertGreaterEqual(report["quality"]["p0_count"], 1)
        self.assertIn("eod_run_id_already_exists", report["blockers"])
        self.assertIn("target_rows_not_zero", report["blockers"])

    def test_write_scope_contract_forbids_events_and_downstream(self) -> None:
        scope = build_write_scope_contract()

        self.assertFalse(scope["writes_outbox"])
        self.assertFalse(scope["consumes_c3_outbox"])
        self.assertIn("common_market_data_run", scope["allowed_future_execute_write_tables"])
        self.assertIn("stock_eod_snapshot", scope["allowed_future_execute_write_tables"])
        self.assertIn("common_event_outbox", scope["forbidden_write_tables"])
        self.assertIn("common_event_inbox", scope["forbidden_write_tables"])
        self.assertIn("common_event_consumer_checkpoint", scope["forbidden_write_tables"])
        self.assertIn("N4/N5/N6", scope["forbidden_write_tables"])

    def test_preflight_blocks_when_dry_run_has_missing_official_daily(self) -> None:
        dry_run = build_eod_dry_run_report(
            eod_run_id=EOD_RUN_ID,
            for_trade_date="20260525",
            lineage_allowlist={},
            expected_eod_snapshot_rows={"stock": 1, "index": 0, "board": 0, "total": 1},
            source_summary={
                "source_runs": {"passed": True, "missing_or_not_passed": []},
                "b1_snapshot_rows": {"stock": 1, "index": 0, "board": 0, "total": 1},
            },
            official_daily_status={
                "available": False,
                "missing_code": "missing_official_daily_fact",
                "missing_fact_count": 1,
                "coverage": {"total": 0},
            },
            target_audit={
                "schema_tables_exist": True,
                "eod_run_exists": False,
                "target_rows_for_eod_run": {"stock": 0, "index": 0, "board": 0, "total": 0},
                "reconciliation_rows_for_eod_run": {"stock": 0, "index": 0, "board": 0, "total": 0},
                "quality_rows_for_eod_run": 0,
                "outbox_rows_for_eod_run": 0,
                "inbox_rows_for_eod_run": 0,
                "checkpoint_rows_for_eod_run": 0,
            },
        )

        preflight = build_eod_execute_preflight_report(dry_run)

        self.assertEqual(preflight["result"], "PREFLIGHT_BLOCKED")
        self.assertFalse(preflight["execute_final_gate_allowed"])
        self.assertIn("missing_official_daily_fact", preflight["blockers"])
        self.assertFalse(preflight["side_effects"]["writes_database"])


if __name__ == "__main__":
    unittest.main()
