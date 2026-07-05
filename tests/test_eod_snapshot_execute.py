import unittest

from ashare_v3.market.eod_snapshot_execute import (
    ALLOWED_WRITE_TABLES,
    FORBIDDEN_WRITE_TABLES,
    EodSnapshotExecuteError,
    build_eod_execute_quality_items,
    build_eod_rollback_sql,
    build_eod_snapshot_rows,
    build_reconciliation_items,
    ensure_clean_eod_target,
    ensure_eod_execute_contract,
    ensure_official_daily_available,
    summarize_eod_snapshot_rows,
)


EOD_RUN_ID = (
    "eod_snapshot_refresh_20260525__"
    "market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute"
)
CONDITION_RUN_ID = "condition_layer_20260522_to_20260525_20260525102249_execute"
SUBSCRIPTION_RUN_ID = (
    "market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute"
)
B1_RUN_ID = (
    "realtime_daily_snapshot_20260525__"
    "market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute"
)
C2_RUN_ID = (
    "closed_minute_30m_replay_20260525_until_1500__"
    "market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute"
)
C2B_RUN_ID = (
    "closed_signal_enrichment_20260525__closed_minute_30m_replay_20260525_until_1500__"
    "market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute"
)
C3_RUN_ID = (
    "minute_bar_closed_outbox_20260525__closed_minute_30m_replay_20260525_until_1500__"
    "market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute"
)
N4_AUDIT_RUN_ID = "trigger_replay_from_c3_minute_bar_closed_20260525__c3_2ebd245a603b"


class EodSnapshotExecuteTests(unittest.TestCase):
    def test_execute_requires_double_confirmation(self) -> None:
        with self.assertRaisesRegex(EodSnapshotExecuteError, "--execute"):
            ensure_eod_execute_contract(
                sample_contract(),
                sample_preflight(),
                execute=False,
                user_confirmed=True,
                eod_run_id=EOD_RUN_ID,
                for_trade_date="20260525",
            )

        with self.assertRaisesRegex(EodSnapshotExecuteError, "--user-confirmed"):
            ensure_eod_execute_contract(
                sample_contract(),
                sample_preflight(),
                execute=True,
                user_confirmed=False,
                eod_run_id=EOD_RUN_ID,
                for_trade_date="20260525",
            )

    def test_preflight_and_runner_must_be_ready(self) -> None:
        contract = sample_contract()
        contract["runner_readiness"] = "missing"
        with self.assertRaisesRegex(EodSnapshotExecuteError, "runner readiness"):
            ensure_eod_execute_contract(
                contract,
                sample_preflight(),
                execute=True,
                user_confirmed=True,
                eod_run_id=EOD_RUN_ID,
                for_trade_date="20260525",
            )

        preflight = sample_preflight()
        preflight["result"] = "PREFLIGHT_BLOCKED"
        with self.assertRaisesRegex(EodSnapshotExecuteError, "preflight"):
            ensure_eod_execute_contract(
                sample_contract(),
                preflight,
                execute=True,
                user_confirmed=True,
                eod_run_id=EOD_RUN_ID,
                for_trade_date="20260525",
            )

    def test_baseline_nonzero_blocks(self) -> None:
        target = sample_clean_target()
        target["target_rows_for_eod_run"]["stock"] = 1
        with self.assertRaisesRegex(EodSnapshotExecuteError, "EOD target"):
            ensure_clean_eod_target(target, EOD_RUN_ID)

        target = sample_clean_target()
        target["outbox_rows_for_eod_run"] = 1
        with self.assertRaisesRegex(EodSnapshotExecuteError, "outbox"):
            ensure_clean_eod_target(target, EOD_RUN_ID)

        target = sample_clean_target()
        target["checkpoint_rows_for_eod_run"] = 1
        with self.assertRaisesRegex(EodSnapshotExecuteError, "checkpoint"):
            ensure_clean_eod_target(target, EOD_RUN_ID)

    def test_official_daily_missing_blocks(self) -> None:
        status = sample_official_daily_status()
        status["missing_fact_count"] = 1
        status["available"] = False

        with self.assertRaisesRegex(EodSnapshotExecuteError, "official daily"):
            ensure_official_daily_available(status)

    def test_c3_delivered_or_delivering_blocks(self) -> None:
        preflight = sample_preflight()
        preflight["source_summary"]["c3_outbox"]["delivered"] = 1

        with self.assertRaisesRegex(EodSnapshotExecuteError, "C3 outbox"):
            ensure_eod_execute_contract(
                sample_contract(),
                preflight,
                execute=True,
                user_confirmed=True,
                eod_run_id=EOD_RUN_ID,
                for_trade_date="20260525",
            )

    def test_builds_official_confirmed_snapshot_rows(self) -> None:
        rows = build_eod_snapshot_rows(
            contract=sample_contract(expected_rows={"stock": 1, "index": 0, "board": 0, "total": 1}),
            snapshot_rows={"stock": [sample_b1_snapshot_row()], "index": [], "board": []},
            official_rows={"stock": [sample_official_daily_row()], "index": [], "board": []},
        )

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["asset_kind"], "stock")
        self.assertEqual(row["identity_key"], "stock:SH:600000")
        self.assertEqual(row["open"], "10.20")
        self.assertEqual(row["close"], "10.88")
        self.assertEqual(row["official_close_price"], "10.88")
        self.assertEqual(row["eod_source_status"], "official_confirmed")
        self.assertEqual(row["settlement_quality_status"], "passed")
        self.assertFalse(row["stale_candidate"])

    def test_snapshot_rows_must_match_contract_counts(self) -> None:
        rows = [sample_eod_snapshot_row("stock")]
        summary = summarize_eod_snapshot_rows(rows)
        self.assertEqual(summary["rows_by_asset"], {"stock": 1, "index": 0, "board": 0})
        self.assertEqual(summary["total_rows"], 1)

        quality = build_eod_execute_quality_items(
            contract=sample_contract(expected_rows={"stock": 1, "index": 0, "board": 0, "total": 1}),
            row_summary=summary,
            official_daily_status=sample_official_daily_status(coverage={"stock": 1, "index": 0, "board": 0, "total": 1}),
            target_audit=sample_clean_target(),
            source_summary=sample_source_summary(),
        )
        self.assertFalse([item for item in quality if item["severity"] == "P0" and item["status"] == "failed"])

        bad_quality = build_eod_execute_quality_items(
            contract=sample_contract(expected_rows={"stock": 2, "index": 0, "board": 0, "total": 2}),
            row_summary=summary,
            official_daily_status=sample_official_daily_status(coverage={"stock": 1, "index": 0, "board": 0, "total": 1}),
            target_audit=sample_clean_target(),
            source_summary=sample_source_summary(),
        )
        self.assertTrue([item for item in bad_quality if item["severity"] == "P0" and item["status"] == "failed"])

    def test_quality_p1_does_not_block(self) -> None:
        items = build_eod_execute_quality_items(
            contract=sample_contract(expected_rows={"stock": 1, "index": 0, "board": 0, "total": 1}),
            row_summary={"rows_by_asset": {"stock": 1, "index": 0, "board": 0}, "total_rows": 1, "stale_candidate_count": 0},
            official_daily_status=sample_official_daily_status(coverage={"stock": 1, "index": 0, "board": 0, "total": 1}),
            target_audit=sample_clean_target(),
            source_summary=sample_source_summary(c2_missing=72, n4_missing=18),
        )

        p0_failed = [item for item in items if item["severity"] == "P0" and item["status"] in {"failed", "warning"}]
        p1_warning = [item for item in items if item["severity"] == "P1" and item["status"] == "warning"]
        self.assertEqual(p0_failed, [])
        self.assertEqual(len(p1_warning), 2)
        self.assertTrue(all((item["details"] or {}).get("metric_scope") == "eod_snapshot_refresh" for item in items))

    def test_reconciliation_items_keep_stale_as_eod_only(self) -> None:
        snapshot = sample_eod_snapshot_row("stock")
        rows = build_reconciliation_items(
            contract=sample_contract(),
            snapshot_rows=[snapshot],
            source_summary=sample_source_summary(c2_missing=72, n4_missing=18),
        )

        diff_types = {row["diff_type"] for row in rows}
        self.assertIn("official_daily_confirmed", diff_types)
        self.assertIn("c2_closed_summary_missing", diff_types)
        self.assertIn("n4_replay_audit_missing", diff_types)
        self.assertTrue(all(row["eod_run_id"] == EOD_RUN_ID for row in rows))
        self.assertTrue(all(row["source_layer"] in {"N1_ingestion", "N3_market_data", "N4_trigger"} for row in rows))

    def test_allowed_write_scope_has_no_outbox_or_downstream(self) -> None:
        self.assertEqual(
            ALLOWED_WRITE_TABLES,
            (
                "common_market_data_run",
                "common_market_data_quality_item",
                "stock_eod_snapshot",
                "index_eod_snapshot",
                "board_eod_snapshot",
                "stock_eod_reconciliation_item",
                "index_eod_reconciliation_item",
                "board_eod_reconciliation_item",
            ),
        )
        self.assertIn("common_event_outbox", FORBIDDEN_WRITE_TABLES)
        self.assertIn("common_event_inbox", FORBIDDEN_WRITE_TABLES)
        self.assertIn("common_event_consumer_checkpoint", FORBIDDEN_WRITE_TABLES)
        self.assertIn("N4/N5/N6", FORBIDDEN_WRITE_TABLES)
        self.assertIn("worker", FORBIDDEN_WRITE_TABLES)

    def test_rollback_sql_scope(self) -> None:
        sql = build_eod_rollback_sql(EOD_RUN_ID)

        self.assertIn("common_event_outbox", sql)
        self.assertIn("common_event_inbox", sql)
        self.assertIn("common_event_consumer_checkpoint", sql)
        self.assertIn("DELETE FROM stock_eod_reconciliation_item", sql)
        self.assertIn("DELETE FROM index_eod_reconciliation_item", sql)
        self.assertIn("DELETE FROM board_eod_reconciliation_item", sql)
        self.assertIn("DELETE FROM stock_eod_snapshot", sql)
        self.assertIn("DELETE FROM index_eod_snapshot", sql)
        self.assertIn("DELETE FROM board_eod_snapshot", sql)
        self.assertIn("DELETE FROM common_market_data_quality_item", sql)
        self.assertIn("DELETE FROM common_market_data_run", sql)
        self.assertNotIn("DELETE FROM stock_realtime_daily_snapshot", sql)
        self.assertNotIn("DELETE FROM stock_closed_30m_summary", sql)
        self.assertNotIn("DELETE FROM stock_minute_bar_1m", sql)


def sample_contract(expected_rows: dict[str, int] | None = None) -> dict[str, object]:
    return {
        "stage": "N3-EOD-snapshot-refresh-execute-contract",
        "layer_role": "N3_market_data",
        "result": "DESIGN_PASS",
        "execute_authorized": False,
        "runner_exists": True,
        "runner_readiness": "ready",
        "eod_execute_allowed_now": False,
        "eod_run_id": EOD_RUN_ID,
        "for_trade_date": "20260525",
        "writes_outbox": False,
        "consumes_c3_outbox": False,
        "lineage": sample_lineage(),
        "run_metadata": {
            "source_trade_date": "20260525",
            "prev_trade_date": "20260525",
            "market_data_pulled": False,
            "market_data_fact_written": True,
            "downstream_layers_touched": False,
            "worker_started": False,
        },
        "expected_eod_snapshot_rows": expected_rows
        or {"stock": 2052, "index": 9, "board": 127, "total": 2188},
    }


def sample_preflight() -> dict[str, object]:
    return {
        "stage": "N3-EOD-snapshot-refresh-execute-preflight",
        "layer_role": "N3_market_data",
        "result": "PREFLIGHT_PASS",
        "runner_exists": True,
        "runner_readiness": "ready",
        "execute_final_gate_allowed": True,
        "eod_run_id": EOD_RUN_ID,
        "for_trade_date": "20260525",
        "target_audit": sample_clean_target(),
        "official_daily_status": sample_official_daily_status(),
        "source_summary": sample_source_summary(),
        "write_scope": {"writes_outbox": False, "consumes_c3_outbox": False},
    }


def sample_lineage() -> dict[str, str | None]:
    return {
        "source_condition_run_id": CONDITION_RUN_ID,
        "source_subscription_run_id": SUBSCRIPTION_RUN_ID,
        "source_b1_snapshot_run_id": B1_RUN_ID,
        "source_c2_run_id": C2_RUN_ID,
        "source_c2b_run_id": C2B_RUN_ID,
        "source_c3_run_id": C3_RUN_ID,
        "source_n4_replay_audit_run_id": N4_AUDIT_RUN_ID,
        "official_daily_run_id": "official_daily_ingest_20260525_v1",
    }


def sample_clean_target() -> dict[str, object]:
    return {
        "schema_tables_exist": True,
        "eod_run_exists": False,
        "target_rows_for_eod_run": {"stock": 0, "index": 0, "board": 0, "total": 0},
        "reconciliation_rows_for_eod_run": {"stock": 0, "index": 0, "board": 0, "total": 0},
        "quality_rows_for_eod_run": 0,
        "outbox_rows_for_eod_run": 0,
        "inbox_rows_for_eod_run": 0,
        "checkpoint_rows_for_eod_run": 0,
    }


def sample_official_daily_status(coverage: dict[str, int] | None = None) -> dict[str, object]:
    coverage = coverage or {"stock": 2052, "index": 9, "board": 127, "total": 2188}
    return {
        "available": True,
        "missing_fact_count": 0,
        "missing_by_asset": {"stock": 0, "index": 0, "board": 0, "total": 0},
        "coverage": coverage,
        "expected": coverage,
        "source_versions_for_trade_date": {
            "stock": ["stock_daily_20260525_v1"],
            "index": ["index_daily_20260525_v1"],
            "board": ["board_daily_20260525_v1"],
        },
    }


def sample_source_summary(c2_missing: int = 0, n4_missing: int = 0) -> dict[str, object]:
    return {
        "source_runs": {"passed": True, "missing_or_not_passed": []},
        "c2_summary_rows": {"missing": c2_missing},
        "n4_replay_audit": {"missing": n4_missing},
        "c3_outbox": {"pending": 17432, "total": 17432, "delivered": 0, "delivering": 0},
    }


def sample_b1_snapshot_row() -> dict[str, object]:
    return {
        "snapshot_id": 101,
        "run_id": B1_RUN_ID,
        "subscription_id": 501,
        "source_condition_run_id": CONDITION_RUN_ID,
        "trade_date": "20260525",
        "asset_kind": "stock",
        "identity_key": "stock:SH:600000",
        "exchange": "SH",
        "code": "600000",
        "display_code": "600000.SH",
        "name": "浦发银行",
        "open": "10.00",
        "high": "10.90",
        "low": "9.95",
        "close": "10.80",
        "current_price": "10.80",
        "volume": "1000",
        "amount": "10800",
        "source_adapter": "mootdx",
        "source_version": "runtime_snapshot",
        "quality_status": "passed",
    }


def sample_official_daily_row() -> dict[str, object]:
    return {
        "trade_date": "20260525",
        "asset_kind": "stock",
        "identity_key": "stock:SH:600000",
        "exchange": "SH",
        "code": "600000",
        "display_code": "600000.SH",
        "name": "浦发银行",
        "open": "10.20",
        "high": "10.95",
        "low": "10.10",
        "close": "10.88",
        "volume": "1200",
        "amount": "13056",
        "source_version": "stock_daily_20260525_v1",
        "source_batch_id": "official_daily_ingest_20260525_v1",
    }


def sample_eod_snapshot_row(asset_kind: str) -> dict[str, object]:
    return {
        "eod_run_id": EOD_RUN_ID,
        "source_condition_run_id": CONDITION_RUN_ID,
        "source_subscription_run_id": SUBSCRIPTION_RUN_ID,
        "source_b1_snapshot_run_id": B1_RUN_ID,
        "source_c2_run_id": C2_RUN_ID,
        "source_c2b_run_id": C2B_RUN_ID,
        "source_c3_run_id": C3_RUN_ID,
        "source_n4_replay_audit_run_id": N4_AUDIT_RUN_ID,
        "official_daily_run_id": "official_daily_ingest_20260525_v1",
        "trade_date": "20260525",
        "asset_kind": asset_kind,
        "identity_key": f"{asset_kind}:SH:600000",
        "exchange": "SH",
        "code": "600000",
        "display_code": "600000.SH",
        "name": "sample",
        "open": "10.20",
        "high": "10.95",
        "low": "10.10",
        "close": "10.88",
        "volume": "1200",
        "amount": "13056",
        "official_close_price": "10.88",
        "official_volume": "1200",
        "official_amount": "13056",
        "eod_source_status": "official_confirmed",
        "settlement_quality_status": "passed",
        "stale_candidate": False,
        "raw_json": {},
    }


if __name__ == "__main__":
    unittest.main()
