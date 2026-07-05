import unittest

from ashare_v3.market.closed_signal_enrichment_execute import (
    ALLOWED_WRITE_TABLES,
    FORBIDDEN_WRITE_TABLES,
    ClosedSignalEnrichmentExecuteError,
    build_c2b_execute_quality_items,
    build_c2b_rollback_sql,
    ensure_c2b_execute_contract,
    ensure_clean_c2b_target,
    summarize_enrichment_rows,
    validate_rows_against_dry_run,
)


C2B_RUN_ID = (
    "closed_signal_enrichment_20260525__closed_minute_30m_replay_20260525_until_1500__"
    "market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute"
)
C2_RUN_ID = (
    "closed_minute_30m_replay_20260525_until_1500__"
    "market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute"
)
CONDITION_RUN_ID = "condition_layer_20260522_to_20260525_20260525102249_execute"
SUBSCRIPTION_RUN_ID = "market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute"
A1_RUN_ID = (
    "previous_day_minute_preload_20260522_for_20260525__"
    "market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute"
)


class ClosedSignalEnrichmentExecuteTests(unittest.TestCase):
    def test_execute_requires_double_confirmation(self) -> None:
        with self.assertRaisesRegex(ClosedSignalEnrichmentExecuteError, "--execute"):
            ensure_c2b_execute_contract(
                sample_contract(),
                sample_preflight(),
                sample_dry_run(),
                execute=False,
                user_confirmed=True,
                c2b_run_id=C2B_RUN_ID,
                for_trade_date="20260525",
            )

        with self.assertRaisesRegex(ClosedSignalEnrichmentExecuteError, "--user-confirmed"):
            ensure_c2b_execute_contract(
                sample_contract(),
                sample_preflight(),
                sample_dry_run(),
                execute=True,
                user_confirmed=False,
                c2b_run_id=C2B_RUN_ID,
                for_trade_date="20260525",
            )

    def test_contract_and_preflight_must_be_ready(self) -> None:
        contract = sample_contract()
        contract["runner_readiness"] = "missing"

        with self.assertRaisesRegex(ClosedSignalEnrichmentExecuteError, "runner readiness"):
            ensure_c2b_execute_contract(
                contract,
                sample_preflight(),
                sample_dry_run(),
                execute=True,
                user_confirmed=True,
                c2b_run_id=C2B_RUN_ID,
                for_trade_date="20260525",
            )

        preflight = sample_preflight()
        preflight["result"] = "PREFLIGHT_BLOCKED"
        with self.assertRaisesRegex(ClosedSignalEnrichmentExecuteError, "preflight"):
            ensure_c2b_execute_contract(
                sample_contract(),
                preflight,
                sample_dry_run(),
                execute=True,
                user_confirmed=True,
                c2b_run_id=C2B_RUN_ID,
                for_trade_date="20260525",
            )

    def test_baseline_nonzero_blocks(self) -> None:
        target = sample_clean_target()
        target["enrichment_rows_for_c2b_run"]["stock"] = 1
        with self.assertRaisesRegex(ClosedSignalEnrichmentExecuteError, "enrichment"):
            ensure_clean_c2b_target(target, C2B_RUN_ID)

        target = sample_clean_target()
        target["outbox_rows_for_c2b_run"] = 1
        with self.assertRaisesRegex(ClosedSignalEnrichmentExecuteError, "outbox"):
            ensure_clean_c2b_target(target, C2B_RUN_ID)

        target = sample_clean_target()
        target["checkpoint_rows_for_c2b_run"] = 1
        with self.assertRaisesRegex(ClosedSignalEnrichmentExecuteError, "checkpoint"):
            ensure_clean_c2b_target(target, C2B_RUN_ID)

    def test_rows_must_match_dry_run_distribution(self) -> None:
        rows = [
            {"asset_kind": "stock", "closed_signal_status": "up_volume_expanding", "closed_signal_quality_status": "passed"},
            {"asset_kind": "stock", "closed_signal_status": "unknown", "closed_signal_quality_status": "missing"},
            {"asset_kind": "index", "closed_signal_status": "flat", "closed_signal_quality_status": "passed"},
        ]
        dry_run = sample_dry_run(
            current_summary_rows={"stock": 2, "index": 1, "board": 0, "total": 3},
            signal_distribution={"up_volume_expanding": 1, "unknown": 1, "flat": 1},
            computable_rows=2,
            unknown_rows=1,
        )

        summary = summarize_enrichment_rows(rows)
        validate_rows_against_dry_run(summary, dry_run)

        bad_dry_run = sample_dry_run(
            current_summary_rows={"stock": 2, "index": 1, "board": 0, "total": 3},
            signal_distribution={"up_volume_expanding": 2, "unknown": 1},
            computable_rows=2,
            unknown_rows=1,
        )
        with self.assertRaisesRegex(ClosedSignalEnrichmentExecuteError, "signal distribution"):
            validate_rows_against_dry_run(summary, bad_dry_run)

    def test_quality_keeps_unknown_as_p1_not_p0(self) -> None:
        rows = [
            {
                "asset_kind": "stock",
                "closed_signal_status": "up_volume_expanding",
                "closed_signal_quality_status": "passed",
                "closed_signal_basis_json": {"baseline_status": "passed"},
            },
            {
                "asset_kind": "stock",
                "closed_signal_status": "unknown",
                "closed_signal_quality_status": "missing",
                "closed_signal_basis_json": {"baseline_status": "missing"},
            },
        ]
        items = build_c2b_execute_quality_items(
            contract=sample_contract(expected_total=2),
            row_summary=summarize_enrichment_rows(rows),
            target_audit=sample_clean_target(),
        )

        p0 = [item for item in items if item["severity"] == "P0" and item["status"] in {"failed", "warning"}]
        p1 = [item for item in items if item["severity"] == "P1" and item["status"] == "warning"]
        self.assertEqual(p0, [])
        self.assertEqual(len(p1), 3)
        self.assertTrue(all((item["details"] or {}).get("metric_scope") == "closed_signal_enrichment" for item in items))

    def test_allowed_write_scope_has_no_outbox_or_downstream(self) -> None:
        self.assertEqual(
            ALLOWED_WRITE_TABLES,
            (
                "common_market_data_run",
                "common_market_data_quality_item",
                "stock_closed_30m_signal_enrichment",
                "index_closed_30m_signal_enrichment",
                "board_closed_30m_signal_enrichment",
            ),
        )
        self.assertIn("common_event_outbox", FORBIDDEN_WRITE_TABLES)
        self.assertIn("common_event_inbox", FORBIDDEN_WRITE_TABLES)
        self.assertIn("common_event_consumer_checkpoint", FORBIDDEN_WRITE_TABLES)
        self.assertIn("N4/N5/N6", FORBIDDEN_WRITE_TABLES)
        self.assertIn("worker", FORBIDDEN_WRITE_TABLES)

    def test_rollback_sql_scope(self) -> None:
        sql = build_c2b_rollback_sql(C2B_RUN_ID)

        self.assertIn("common_event_outbox", sql)
        self.assertIn("common_event_inbox", sql)
        self.assertIn("common_event_consumer_checkpoint", sql)
        self.assertIn("DELETE FROM stock_closed_30m_signal_enrichment", sql)
        self.assertIn("DELETE FROM index_closed_30m_signal_enrichment", sql)
        self.assertIn("DELETE FROM board_closed_30m_signal_enrichment", sql)
        self.assertIn("DELETE FROM common_market_data_quality_item", sql)
        self.assertIn("DELETE FROM common_market_data_run", sql)
        self.assertNotIn("DELETE FROM stock_closed_30m_summary", sql)
        self.assertNotIn("DELETE FROM stock_minute_bar_1m", sql)


def sample_contract(expected_total: int = 17504) -> dict[str, object]:
    return {
        "stage": "N3-C2B-closed-signal-enrichment-execute-contract",
        "layer_role": "N3_market_data",
        "result": "DESIGN_PASS",
        "execute_authorized": False,
        "runner_exists": True,
        "runner_readiness": "ready",
        "c2b_execute_allowed_now": False,
        "c2b_run_id": C2B_RUN_ID,
        "for_trade_date": "20260525",
        "writes_outbox": False,
        "consumes_c3_outbox": False,
        "lineage": {
            "source_condition_run_id": CONDITION_RUN_ID,
            "source_subscription_run_id": SUBSCRIPTION_RUN_ID,
            "c2_run_id": C2_RUN_ID,
            "source_previous_day_minute_run_id": A1_RUN_ID,
            "previous_day_minute_date": "20260522",
        },
        "run_metadata": {
            "source_trade_date": "20260522",
            "prev_trade_date": "20260522",
            "market_data_pulled": False,
            "market_data_fact_written": True,
            "downstream_layers_touched": False,
            "worker_started": False,
        },
        "expected_enrichment_rows": {"stock": expected_total, "index": 0, "board": 0, "total": expected_total},
    }


def sample_preflight() -> dict[str, object]:
    return {
        "stage": "N3-C2B-closed-signal-enrichment-execute-preflight",
        "layer_role": "N3_market_data",
        "result": "PREFLIGHT_PASS",
        "runner_readiness": "ready",
        "c2b_run_id": C2B_RUN_ID,
        "baseline_guard": sample_clean_target(),
    }


def sample_dry_run(
    *,
    current_summary_rows: dict[str, int] | None = None,
    signal_distribution: dict[str, int] | None = None,
    computable_rows: int = 17432,
    unknown_rows: int = 72,
) -> dict[str, object]:
    return {
        "stage": "N3-C2B",
        "result": "DRY_RUN_PASS",
        "c2b_run_id": C2B_RUN_ID,
        "for_trade_date": "20260525",
        "current_summary_rows": current_summary_rows or {"stock": 16416, "index": 72, "board": 1016, "total": 17504},
        "signal_distribution": signal_distribution
        or {
            "up_volume_expanding": 2800,
            "up_volume_flat": 2494,
            "up_volume_shrinking": 2260,
            "down_volume_expanding": 2806,
            "down_volume_flat": 2408,
            "down_volume_shrinking": 2011,
            "flat": 2653,
            "unknown": 72,
        },
        "computable_rows": computable_rows,
        "unknown_rows": unknown_rows,
        "quality": {"p0_count": 0, "p1_count": 3, "p2_count": 0},
        "n4_replay_unblock_estimate": {
            "closed_signal_status_missing_before_c2b": 35952,
            "closed_signal_status_missing_after_c2b": 0,
            "c3_event_missing_remains": 18,
        },
    }


def sample_clean_target() -> dict[str, object]:
    return {
        "run_exists": False,
        "enrichment_rows_for_c2b_run": {"stock": 0, "index": 0, "board": 0},
        "quality_rows_for_c2b_run": 0,
        "outbox_rows_for_c2b_run": 0,
        "inbox_rows_for_c2b_run": 0,
        "checkpoint_rows_for_c2b_run": 0,
    }


if __name__ == "__main__":
    unittest.main()
