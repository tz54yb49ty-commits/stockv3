import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ashare_v3.market.action_confirmation_metric_materialization_execute import (
    ALLOWED_WRITE_TABLES,
    BOARD_LINEAGE_METRIC_V2_RUN_ID_20260605,
    BOARD_LINEAGE_SAMPLE_IDENTITIES_20260605,
    COVERAGE_REPAIR_RUN_ID_20260605,
    DEFAULT_BOARD_LINEAGE_METRIC_V2_CONTRACT_PATH_20260605,
    DEFAULT_BOARD_LINEAGE_METRIC_V2_DRY_RUN_PATH_20260605,
    DEFAULT_BOARD_LINEAGE_METRIC_V2_PAYLOAD_PATH_20260605,
    DEFAULT_BOARD_LINEAGE_METRIC_V2_PREFLIGHT_PATH_20260605,
    DEFAULT_BOARD_LINEAGE_METRIC_V2_ROLLBACK_SQL_PATH_20260605,
    DEFAULT_REPAIRED_CONTEXT_CONTRACT_PATH_20260605,
    DEFAULT_REPAIRED_CONTEXT_PAYLOAD_PATH_20260605,
    DEFAULT_REPAIRED_CONTEXT_PREFLIGHT_PATH_20260605,
    FORBIDDEN_WRITE_TABLES,
    EXPECTED_ROW_COUNTS,
    MATERIALIZATION_TABLES,
    TARGET_RUN_ID,
    build_20260605_board_lineage_metric_v2_contract,
    build_20260605_board_lineage_metric_v2_dry_run_report,
    build_20260605_coverage_repair_contract,
    build_20260605_coverage_repair_dry_run_report,
    build_board_lineage_metric_v2_rollback_sql,
    classify_20260605_metric_trace_eligibility,
    build_20260605_repaired_context_contract,
    validate_contract,
    validate_execute_flags,
    validate_payload,
)
from ashare_v3.market.action_confirmation_projection_execute import insert_action_confirmation_metric_rows


ROOT = Path(__file__).resolve().parents[1]
ROLLBACK_SQL = ROOT / "sql/N3_action_confirmation_metric_20260603_materialization_rollback.sql"
ROLLBACK_SQL_20260605 = ROOT / "sql/N3_action_confirmation_metric_20260605_materialization_rollback.sql"
ROLLBACK_SQL_REPAIRED_20260605 = (
    ROOT / "sql/N3_repaired_context_action_confirmation_metric_20260605_materialization_rollback.sql"
)
REPAIRED_N6_GUARD_TABLES = [
    "user_card_projection",
    "user_signal_projection",
    "user_signal_card",
    "user_notification_queue",
    "user_sim_order",
    "user_sim_trade",
    "user_sim_position",
    "n6_virtual_account",
    "n6_virtual_order",
    "n6_virtual_trade",
    "n6_virtual_position",
    "n6_virtual_position_event",
    "n6_virtual_pnl_snapshot",
]


def _projection_row(
    *,
    projection_status: str,
    projection_quality_status: str = "blocked",
    trace_status: str = "blocked",
    missing_reason: list[str] | None = None,
) -> dict:
    return {
        "projection_id": 42,
        "projection_run_id": "realtime_projection_metric_20260605_live2_compat__realtime_snapshot_20260605_live2_market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1",
        "projection_status": projection_status,
        "projection_quality_status": projection_quality_status,
        "trace_status": trace_status,
        "projection_signal_status": "up_volume_expanding",
        "source_fact_ids": {"missing_reason": missing_reason or ["completion_ratio_below_min_ready"]},
    }


def _row(asset_kind: str, index: int, *, projection_run_id: str = TARGET_RUN_ID) -> dict:
    exchange = {"stock": "SH", "index": "SH", "board": "TDX"}[asset_kind]
    prefix = {"stock": "600", "index": "000", "board": "880"}[asset_kind]
    code = f"{prefix}{index:03d}"[-6:]
    identity_key = f"{asset_kind}:{exchange}:{code}"
    return {
        "projection_run_id": projection_run_id,
        "projection_schema_version": "n3.action_confirmation_metric.v1",
        "source_condition_run_id": "condition_layer_20260602_source_20260602_v1",
        "source_subscription_run_id": "market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1",
        "source_snapshot_run_id": "realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1",
        "source_snapshot_id": index + 1,
        "source_snapshot_event_id": None,
        "source_today_minute_run_id": "today_minute_bar_1m_20260603_until_1500__market_data_subscription_20260603_full_context_expansion_condition_layer_20260602_source_20260602_v1",
        "source_previous_day_minute_run_id": "previous_day_minute_preload_20260602_for_20260603_full_context_expansion__market_data_subscription_20260603_full_context_expansion_condition_layer_20260602_source_20260602_v1",
        "for_trade_date": "20260603",
        "trade_date": "20260603",
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "exchange": exchange,
        "code": code,
        "display_code": code,
        "name": identity_key,
        "metric_time": "2026-06-03T15:00:00+08:00",
        "metric_minute_label": "15:00",
        "current_price": "10.00",
        "current_price_source": "realtime_daily_snapshot",
        "current_price_time": "2026-06-03T15:00:00+08:00",
        "previous_120m_body_high": "10.00",
        "previous_120m_body_low": "9.00",
        "previous_30m_body_high": "10.00",
        "previous_30m_body_low": "9.00",
        "previous_5m_body_high": "10.00",
        "previous_5m_body_low": "9.00",
        "previous_1m_body_high": "10.00",
        "previous_1m_body_low": "9.00",
        "current_1m_amount": "1000",
        "previous_1m_amount": "900",
        "current_5m_virtual_amount": "5000",
        "previous_5m_full_amount": "4500",
        "is_first_1m_of_day": False,
        "is_first_5m_of_day": False,
        "is_first_30m_of_day": False,
        "is_first_120m_of_day": False,
        "first_1m_amount_default_pass": False,
        "first_5m_amount_default_pass": False,
        "previous_1m_period_source": "same_trade_date_previous_period",
        "previous_5m_period_source": "same_trade_date_previous_period",
        "previous_30m_period_source": "same_trade_date_previous_period",
        "previous_120m_period_source": "same_trade_date_previous_period",
        "boundary_policy_version": "n3.action_confirmation_boundary.v1",
        "buy_120m_price_pass": True,
        "buy_30m_price_pass": True,
        "buy_5m_price_pass": True,
        "buy_5m_amount_pass": True,
        "buy_1m_price_pass": True,
        "buy_1m_amount_pass": True,
        "sell_120m_price_pass": False,
        "sell_30m_price_pass": False,
        "sell_5m_price_pass": False,
        "sell_5m_amount_pass": False,
        "sell_1m_price_pass": False,
        "sell_1m_amount_pass": False,
        "metric_quality_status": "passed",
        "metric_ready": True,
        "source_fact_ids": {"source_snapshot_id": index + 1},
        "source_minute_refs": [{"bar_id": index + 1, "bar_time": "2026-06-03T15:00:00+08:00"}],
        "previous_day_minute_refs": [],
        "calculation_config_hash": "n3.action_confirmation_projection_metric.v1",
        "raw_json": {
            "n4_trigger_matched_events": [
                {
                    "signal_type": "B_BUY",
                    "condition_key": "BUY:W,D",
                    "output_event_id": f"evt_{asset_kind}_{index}",
                }
            ],
            "bj_excluded": True,
            "full_excluded": True,
        },
    }


def _payload(
    *,
    projection_run_id: str = TARGET_RUN_ID,
    expected_rows: dict[str, int] | None = None,
    coverage: dict[str, int] | None = None,
) -> dict:
    counts = expected_rows or EXPECTED_ROW_COUNTS
    rows = []
    for asset_kind, count in counts.items():
        if asset_kind == "total":
            continue
        rows.extend(_row(asset_kind, index, projection_run_id=projection_run_id) for index in range(count))
    return {
        "artifact_type": "N3_action_confirmation_metric_materialization_payload",
        "projection_run_id": projection_run_id,
        "target_run_id": projection_run_id,
        "projection_schema_version": "n3.action_confirmation_metric.v1",
        "expected_rows": counts,
        "metric_ready_expected": counts["total"],
        "n4_matched_coverage": coverage or {"covered": 863, "expected": 863, "missing": 0},
        "bj_full_scope_decision": {
            "bj_identity_rows": 0,
            "full_signal_type_rows": 0,
            "full_condition_key_rows": 0,
        },
        "rows": rows,
    }


def _contract(
    *,
    projection_run_id: str,
    expected_rows: dict[str, int],
    n4_covered: int,
    rollback_sql_path: str = "sql/N3_action_confirmation_metric_20260605_materialization_rollback.sql",
) -> dict:
    return {
        "projection_run_id": projection_run_id,
        "expected_rows": expected_rows,
        "metric_ready_expected": expected_rows["total"],
        "expected_n4_matched_coverage": {"covered": n4_covered, "expected": n4_covered, "missing": 0},
        "allowed_write_tables": list(ALLOWED_WRITE_TABLES),
        "requested_target_aliases": [
            "stock_action_confirmation_metric",
            "index_action_confirmation_metric",
            "board_action_confirmation_metric",
        ],
        "forbidden_write_tables": list(FORBIDDEN_WRITE_TABLES),
        "writes_outbox": False,
        "rollback": {"rollback_sql_path": rollback_sql_path},
    }


class N3ActionConfirmationMetricMaterializationExecuteTest(unittest.TestCase):
    def test_missing_execute_is_blocked(self) -> None:
        gate = validate_execute_flags(execute=False, user_confirmed=True)

        self.assertEqual(gate["gate_result"], "BLOCKED")
        self.assertIn("missing_execute_flag", gate["blocked_reasons"])

    def test_missing_user_confirmed_is_blocked(self) -> None:
        gate = validate_execute_flags(execute=True, user_confirmed=False)

        self.assertEqual(gate["gate_result"], "BLOCKED")
        self.assertIn("missing_user_confirmed_flag", gate["blocked_reasons"])

    def test_allowed_write_scope_only(self) -> None:
        self.assertEqual(
            ALLOWED_WRITE_TABLES,
            [
                "common_market_data_run",
                "common_market_data_quality_item",
                "stock_action_confirmation_projection_metric",
                "index_action_confirmation_projection_metric",
                "board_action_confirmation_projection_metric",
            ],
        )

    def test_optional_realtime_virtual_metric_writer_columns_use_lowercase_db_names(self) -> None:
        class FakeCursor:
            def __init__(self) -> None:
                self.sql = ""
                self.payload = []

            def executemany(self, sql: str, payload: list[tuple]) -> None:
                self.sql = sql
                self.payload = payload

        row = _row("stock", 1)
        row.update(
            {
                "current_D_body_high": "13.0",
                "previous_Y_amount": "240000.0",
                "current_30m_virtual_amount": "3000.0",
                "previous_day_same_window_amount": "2000.0",
                "period_source": {"D": "n2_period_context_plus_intraday_1m"},
                "trace_json": {"source": "unit_test"},
            }
        )
        cursor = FakeCursor()

        insert_action_confirmation_metric_rows(
            cursor,
            table="stock_action_confirmation_projection_metric",
            rows=[row],
        )

        self.assertIn("current_d_body_high", cursor.sql)
        self.assertIn("previous_y_amount", cursor.sql)
        self.assertIn("current_30m_virtual_amount", cursor.sql)
        self.assertIn("previous_day_same_window_amount", cursor.sql)
        self.assertIn("period_source", cursor.sql)
        self.assertIn("trace_json", cursor.sql)
        self.assertNotIn("current_D_body_high", cursor.sql)
        self.assertNotIn("previous_Y_amount", cursor.sql)
        self.assertEqual(len(cursor.payload), 1)
        self.assertEqual(
            MATERIALIZATION_TABLES,
            {
                "stock": "stock_action_confirmation_projection_metric",
                "index": "index_action_confirmation_projection_metric",
                "board": "board_action_confirmation_projection_metric",
            },
        )
        self.assertIn("common_event_outbox", FORBIDDEN_WRITE_TABLES)
        self.assertIn("N4/N5/N6 tables", FORBIDDEN_WRITE_TABLES)
        self.assertIn("stock_projection_enrichment_v4_metric", FORBIDDEN_WRITE_TABLES)

    def test_payload_row_count_and_scope_validation(self) -> None:
        result = validate_payload(_payload())

        self.assertTrue(result["valid"], result["blocked_reasons"])
        self.assertEqual(result["row_counts"], EXPECTED_ROW_COUNTS)
        self.assertEqual(result["metric_ready"], 822)
        self.assertEqual(result["bj_identity_rows"], 0)
        self.assertEqual(result["full_signal_type_rows"], 0)
        self.assertEqual(result["full_condition_key_rows"], 0)

    def test_bj_rows_are_rejected(self) -> None:
        payload = _payload()
        payload["rows"][0]["identity_key"] = "stock:BJ:920001"

        result = validate_payload(payload)

        self.assertFalse(result["valid"])
        self.assertIn("bj_rows_must_be_excluded", result["blocked_reasons"])

    def test_full_rows_are_rejected(self) -> None:
        payload = _payload()
        payload["rows"][0]["raw_json"]["n4_trigger_matched_events"][0]["condition_key"] = "BUY:FULL"

        result = validate_payload(payload)

        self.assertFalse(result["valid"])
        self.assertIn("full_rows_must_be_excluded", result["blocked_reasons"])

    def test_rollback_sql_has_hard_fail_before_delete(self) -> None:
        sql = ROLLBACK_SQL.read_text(encoding="utf-8")
        first_raise = sql.index("RAISE EXCEPTION")
        first_delete = sql.index("DELETE FROM")

        self.assertLess(first_raise, first_delete)
        self.assertIn("common_event_outbox", sql)
        self.assertIn("common_event_inbox", sql)
        self.assertIn("common_event_consumer_checkpoint", sql)
        self.assertIn("common_trigger_match", sql)
        self.assertIn("common_action_event", sql)

    def test_payload_artifact_validation_when_present(self) -> None:
        path = ROOT / "docs/N3_action_confirmation_metric_20260603_materialization_payload.json"
        if not path.exists():
            self.skipTest("payload artifact is generated by implementation gate")
        result = validate_payload(json.loads(path.read_text(encoding="utf-8")))

        self.assertTrue(result["valid"], result["blocked_reasons"])
        self.assertEqual(result["row_counts"], EXPECTED_ROW_COUNTS)

    def test_20260605_payload_is_validated_against_contract_not_20260603_constants(self) -> None:
        projection_run_id = (
            "action_confirmation_projection_metric_20260605__"
            "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
        )
        expected_rows = {"stock": 595, "index": 0, "board": 0, "total": 595}
        payload = _payload(
            projection_run_id=projection_run_id,
            expected_rows=expected_rows,
            coverage={"covered": 1240, "expected": 1240, "missing": 0, "distinct_metric_rows": 595},
        )
        contract = _contract(projection_run_id=projection_run_id, expected_rows=expected_rows, n4_covered=1240)

        validation = validate_payload(
            payload,
            target_run_id=projection_run_id,
            expected_row_counts=expected_rows,
            expected_metric_ready=595,
            expected_n4_matched=1240,
        )
        contract_blockers = validate_contract(contract, validation)

        self.assertTrue(validation["valid"], validation["blocked_reasons"])
        self.assertEqual(contract_blockers, [])

    def test_20260605_repaired_context_contract_uses_605_scope(self) -> None:
        projection_run_id = (
            "action_confirmation_projection_metric_20260605__"
            "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
        )
        expected_rows = {"stock": 316, "index": 0, "board": 0, "total": 316}
        payload = _payload(
            projection_run_id=projection_run_id,
            expected_rows=expected_rows,
            coverage={
                "covered": 605,
                "expected": 605,
                "missing": 0,
                "distinct_metric_rows": 316,
                "ready_backed": 316,
                "pending_market_data": 289,
            },
        )
        payload["ready_backed_policy"] = {
            "policy": "materialize_metric",
            "counts": {"stock": 316, "index": 0, "board": 0, "total": 316},
        }
        payload["not_ready_policy"] = {
            "policy": "pending_market_data",
            "counts": {"stock": 256, "index": 0, "board": 33, "total": 289},
        }

        contract = build_20260605_repaired_context_contract(payload)
        validation = validate_payload(
            payload,
            target_run_id=contract["projection_run_id"],
            expected_row_counts=contract["expected_rows"],
            expected_metric_ready=contract["metric_ready_expected"],
            expected_n4_matched=contract["expected_n4_matched_coverage"]["expected"],
        )

        self.assertTrue(validation["valid"], validation["blocked_reasons"])
        self.assertEqual(contract["expected_n4_matched_coverage"]["expected"], 605)
        self.assertEqual(contract["expected_rows"], expected_rows)
        self.assertEqual(contract["ready_backed_policy"]["counts"]["total"], 316)
        self.assertEqual(contract["not_ready_policy"]["counts"]["total"], 289)
        self.assertNotIn("1240", json.dumps(contract, sort_keys=True))
        self.assertNotIn("595", json.dumps(contract["expected_rows"], sort_keys=True))

    def test_repaired_context_contract_has_runner_parameterization_paths(self) -> None:
        projection_run_id = (
            "action_confirmation_projection_metric_20260605__"
            "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
        )
        expected_rows = {"stock": 316, "index": 0, "board": 0, "total": 316}
        payload = _payload(
            projection_run_id=projection_run_id,
            expected_rows=expected_rows,
            coverage={"covered": 605, "expected": 605, "missing": 0, "distinct_metric_rows": 316},
        )
        contract = build_20260605_repaired_context_contract(payload)

        self.assertIn("--payload-path docs/N3_20260605_repaired_context_action_confirmation_metric_payload.json", contract["execute_command"])
        self.assertIn("--contract-path docs/N3_20260605_REPAIRED_CONTEXT_ACTION_CONFIRMATION_METRIC_CONTRACT.json", contract["execute_command"])
        self.assertIn("--execute --user-confirmed", contract["execute_command"])
        self.assertEqual(contract["runner_readiness"], "ready_contract_driven")

    def test_20260605_coverage_repair_policy_accepts_not_ready_when_trace_complete(self) -> None:
        metric_row = _row("stock", 690, projection_run_id=COVERAGE_REPAIR_RUN_ID_20260605)
        projection_row = _projection_row(projection_status="not_ready")

        decision = classify_20260605_metric_trace_eligibility(
            metric_row=metric_row,
            projection_row=projection_row,
            original_metric_identities={"stock:SH:600001"},
        )

        self.assertTrue(decision["eligible"], decision)
        self.assertEqual(decision["eligibility_source"], "metric_trace_complete")
        self.assertEqual(decision["original_projection_status"], "not_ready")
        self.assertEqual(decision["excluded_reason"], None)

    def test_20260605_coverage_repair_policy_keeps_lineage_missing_excluded(self) -> None:
        projection_row = _projection_row(
            projection_status="not_ready",
            missing_reason=["missing_today_minute_elapsed", "missing_current_lineage_previous_day_window"],
        )

        decision = classify_20260605_metric_trace_eligibility(
            metric_row=None,
            projection_row=projection_row,
            original_metric_identities=set(),
        )

        self.assertFalse(decision["eligible"], decision)
        self.assertEqual(decision["excluded_reason"], "lineage_missing")

    def test_20260605_coverage_repair_dry_run_is_additive_not_overwrite(self) -> None:
        expected_rows = {"stock": 256, "index": 0, "board": 5, "total": 261}
        payload = _payload(
            projection_run_id=COVERAGE_REPAIR_RUN_ID_20260605,
            expected_rows=expected_rows,
            coverage={"covered": 605, "expected": 605, "missing": 0},
        )
        payload["repair_summary"] = {
            "original_metric_rows": 316,
            "n4_matched_universe": 605,
            "repair_additive_rows": expected_rows,
            "repaired_total_coverage": {"stock": 572, "index": 0, "board": 5, "total": 577},
            "remaining_excluded": {"stock": 0, "index": 0, "board": 28, "total": 28},
            "remaining_excluded_reason": "board_lineage_missing",
            "duplicate_vs_original_metric": 0,
            "duplicate_inside_repair_payload": 0,
        }
        contract = build_20260605_coverage_repair_contract(payload)
        dry_run = build_20260605_coverage_repair_dry_run_report(
            payload=payload,
            contract=contract,
            preflight={"result": "PREFLIGHT_PASS", "quality": {"P0": 0, "P1": 2, "P2": 0}},
        )

        self.assertEqual(contract["projection_run_id"], COVERAGE_REPAIR_RUN_ID_20260605)
        self.assertEqual(contract["coverage_policy"]["eligibility_source"], "metric_trace_complete")
        self.assertEqual(dry_run["result"], "DRY_RUN_PASS")
        self.assertEqual(dry_run["dry_run_proof"]["repair_additive_rows"]["total"], 261)
        self.assertEqual(dry_run["dry_run_proof"]["remaining_excluded_reason"], "board_lineage_missing")

    def test_20260605_board_lineage_metric_v2_dry_run_closes_remaining_28(self) -> None:
        expected_rows = {"stock": 0, "index": 0, "board": 28, "total": 28}
        payload = _payload(
            projection_run_id=BOARD_LINEAGE_METRIC_V2_RUN_ID_20260605,
            expected_rows=expected_rows,
            coverage={
                "covered": 605,
                "expected": 605,
                "missing": 0,
                "existing_coverage": 577,
                "final_coverage_after_metric_v2": 605,
                "remaining_excluded": 0,
            },
        )
        payload["artifact_subtype"] = "board_lineage_metric_v2"
        payload["repair_summary"] = {
            "existing_coverage": 577,
            "original_metric_rows": {"stock": 316, "index": 0, "board": 0, "total": 316},
            "additive_v1_metric_rows": {"stock": 256, "index": 0, "board": 5, "total": 261},
            "board_metric_v2_additive": expected_rows,
            "expected_coverage": 605,
            "final_coverage_after_metric_v2": 605,
            "remaining_excluded": {"stock": 0, "index": 0, "board": 0, "total": 0},
            "remaining_excluded_reason": None,
            "duplicate_vs_original_metric": 0,
            "duplicate_vs_additive_v1": 0,
            "duplicate_inside_metric_v2_payload": 0,
        }
        payload["sample_proof"] = {
            identity: {
                "materialized_in_metric_v2": True,
                "metric_trace_complete": True,
                "db_check_pass": True,
            }
            for identity in BOARD_LINEAGE_SAMPLE_IDENTITIES_20260605
        }
        contract = build_20260605_board_lineage_metric_v2_contract(payload)
        dry_run = build_20260605_board_lineage_metric_v2_dry_run_report(
            payload=payload,
            contract=contract,
            preflight={"result": "PREFLIGHT_PASS", "quality": {"P0": 0, "P1": 1, "P2": 0}},
        )

        self.assertEqual(contract["projection_run_id"], BOARD_LINEAGE_METRIC_V2_RUN_ID_20260605)
        self.assertEqual(contract["rollback"]["delete_scope"], [
            "board_action_confirmation_projection_metric",
            "common_market_data_quality_item",
            "common_market_data_run",
        ])
        self.assertEqual(dry_run["result"], "DRY_RUN_PASS")
        self.assertEqual(dry_run["coverage_proof"]["existing_coverage"], 577)
        self.assertEqual(dry_run["coverage_proof"]["board_metric_v2_additive"], 28)
        self.assertEqual(dry_run["coverage_proof"]["final_coverage_after_metric_v2"], 605)
        self.assertEqual(dry_run["coverage_proof"]["remaining_excluded"]["total"], 0)

    def test_board_lineage_metric_v2_rollback_deletes_only_board_metric_rows(self) -> None:
        sql = build_board_lineage_metric_v2_rollback_sql()
        upper = sql.upper()
        first_raise = upper.find("RAISE EXCEPTION")
        first_delete = upper.find("DELETE FROM")

        self.assertNotEqual(first_raise, -1)
        self.assertLess(first_raise, first_delete)
        self.assertIn("DELETE FROM board_action_confirmation_projection_metric", sql)
        self.assertIn("DELETE FROM common_market_data_quality_item", sql)
        self.assertIn("DELETE FROM common_market_data_run", sql)
        self.assertNotIn("DELETE FROM stock_action_confirmation_projection_metric", sql)
        self.assertNotIn("DELETE FROM index_action_confirmation_projection_metric", sql)
        self.assertNotIn("DELETE FROM board_minute_bar_1m", sql)
        self.assertNotIn("DELETE FROM common_market_data_subscription", sql)
        self.assertNotIn("DELETE FROM common_event_outbox", sql)
        self.assertNotIn("DELETE FROM common_event_inbox", sql)
        self.assertNotIn("DELETE FROM common_event_consumer_checkpoint", sql)
        for token in ("CASCADE", "DROP ", "TRUNCATE"):
            self.assertNotIn(token, upper)

    def test_20260605_repaired_context_artifacts_are_contract_driven_when_present(self) -> None:
        payload_path = ROOT / DEFAULT_REPAIRED_CONTEXT_PAYLOAD_PATH_20260605
        contract_path = ROOT / DEFAULT_REPAIRED_CONTEXT_CONTRACT_PATH_20260605
        preflight_path = ROOT / DEFAULT_REPAIRED_CONTEXT_PREFLIGHT_PATH_20260605
        if not payload_path.exists() or not contract_path.exists() or not preflight_path.exists():
            self.skipTest("repaired-context 20260605 artifacts are generated by the refresh gate")

        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
        validation = validate_payload(
            payload,
            target_run_id=contract["projection_run_id"],
            expected_row_counts=contract["expected_rows"],
            expected_metric_ready=contract["metric_ready_expected"],
            expected_n4_matched=contract["expected_n4_matched_coverage"]["expected"],
        )

        self.assertEqual(payload["n4_matched_coverage"]["expected"], 605)
        self.assertEqual(contract["expected_n4_matched_coverage"]["expected"], 605)
        self.assertEqual(contract["not_ready_policy"]["policy"], "pending_market_data")
        self.assertEqual(preflight["result"], "PREFLIGHT_PASS")
        self.assertEqual(preflight["quality"]["P0"], 0)
        self.assertTrue(validation["valid"], validation["blocked_reasons"])
        self.assertNotIn("1240", json.dumps(contract, sort_keys=True))

    def test_20260605_board_lineage_metric_v2_artifacts_are_contract_driven_when_present(self) -> None:
        payload_path = ROOT / DEFAULT_BOARD_LINEAGE_METRIC_V2_PAYLOAD_PATH_20260605
        contract_path = ROOT / DEFAULT_BOARD_LINEAGE_METRIC_V2_CONTRACT_PATH_20260605
        preflight_path = ROOT / DEFAULT_BOARD_LINEAGE_METRIC_V2_PREFLIGHT_PATH_20260605
        dry_run_path = ROOT / DEFAULT_BOARD_LINEAGE_METRIC_V2_DRY_RUN_PATH_20260605
        if not payload_path.exists() or not contract_path.exists() or not preflight_path.exists() or not dry_run_path.exists():
            self.skipTest("board-lineage metric_v2 artifacts are generated by the contract gate")

        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
        dry_run = json.loads(dry_run_path.read_text(encoding="utf-8"))
        validation = validate_payload(
            payload,
            target_run_id=contract["projection_run_id"],
            expected_row_counts=contract["expected_rows"],
            expected_metric_ready=contract["metric_ready_expected"],
            expected_n4_matched=contract["expected_n4_matched_coverage"]["expected"],
        )

        self.assertEqual(contract["expected_rows"], {"stock": 0, "index": 0, "board": 28, "total": 28})
        self.assertEqual(preflight["result"], "PREFLIGHT_PASS")
        self.assertEqual(preflight["quality"]["P0"], 0)
        self.assertEqual(dry_run["result"], "DRY_RUN_PASS")
        self.assertEqual(dry_run["coverage_proof"]["existing_coverage"], 577)
        self.assertEqual(dry_run["coverage_proof"]["final_coverage_after_metric_v2"], 605)
        self.assertEqual(dry_run["coverage_proof"]["remaining_excluded"]["total"], 0)
        for identity in BOARD_LINEAGE_SAMPLE_IDENTITIES_20260605:
            self.assertTrue(dry_run["sample_proof"][identity]["materialized_in_metric_v2"])
        self.assertTrue(validation["valid"], validation["blocked_reasons"])

    def test_20260605_artifacts_are_contract_driven_when_present(self) -> None:
        payload_path = ROOT / "docs/N3_20260605_action_confirmation_metric_payload.json"
        contract_path = ROOT / "docs/N3_20260605_ACTION_CONFIRMATION_METRIC_CONTRACT.json"
        preflight_path = ROOT / "docs/N3_20260605_ACTION_CONFIRMATION_METRIC_PREFLIGHT.json"
        if not payload_path.exists() or not contract_path.exists() or not preflight_path.exists():
            self.skipTest("20260605 artifacts are generated by the readiness gate")

        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
        expected_rows = {"stock": 595, "index": 0, "board": 0, "total": 595}
        validation = validate_payload(
            payload,
            target_run_id=contract["projection_run_id"],
            expected_row_counts=expected_rows,
            expected_metric_ready=595,
            expected_n4_matched=1240,
        )

        self.assertEqual(contract["expected_rows"], expected_rows)
        self.assertEqual(contract["not_ready_policy"]["policy"], "pending_market_data")
        self.assertEqual(contract["not_ready_policy"]["counts"], {"stock": 584, "index": 1, "board": 60, "total": 645})
        self.assertEqual(preflight["result"], "PREFLIGHT_PASS")
        self.assertEqual(preflight["quality"]["P0"], 0)
        self.assertTrue(validation["valid"], validation["blocked_reasons"])

    def test_20260605_rollback_sql_has_hard_fail_before_delete_when_present(self) -> None:
        if not ROLLBACK_SQL_20260605.exists():
            self.skipTest("20260605 rollback is generated by the readiness gate")
        sql = ROLLBACK_SQL_20260605.read_text(encoding="utf-8")
        first_raise = sql.index("RAISE EXCEPTION")
        first_delete = sql.index("DELETE FROM")

        self.assertLess(first_raise, first_delete)
        self.assertIn("common_event_outbox", sql)
        self.assertIn("common_event_inbox", sql)
        self.assertIn("common_event_consumer_checkpoint", sql)
        self.assertIn("common_trigger_match", sql)
        self.assertIn("common_action_event", sql)
        self.assertIn("downstream_layers_touched", sql)
        self.assertIn("worker_started", sql)

    def test_20260605_repaired_context_rollback_sql_has_hard_fail_before_delete_when_present(self) -> None:
        if not ROLLBACK_SQL_REPAIRED_20260605.exists():
            self.skipTest("repaired-context 20260605 rollback is generated by the refresh gate")
        sql = ROLLBACK_SQL_REPAIRED_20260605.read_text(encoding="utf-8")
        first_raise = sql.index("RAISE EXCEPTION")
        first_delete = sql.index("DELETE FROM")

        self.assertLess(first_raise, first_delete)
        self.assertIn("common_event_outbox", sql)
        self.assertIn("common_event_inbox", sql)
        self.assertIn("common_event_consumer_checkpoint", sql)
        self.assertIn("common_trigger_match", sql)
        self.assertIn("common_action_event", sql)
        self.assertIn("downstream_layers_touched", sql)
        self.assertIn("worker_started", sql)

    def test_20260605_repaired_context_rollback_guards_n6_user_sim_virtual_refs_when_present(self) -> None:
        if not ROLLBACK_SQL_REPAIRED_20260605.exists():
            self.skipTest("repaired-context 20260605 rollback is generated by the refresh gate")
        sql = ROLLBACK_SQL_REPAIRED_20260605.read_text(encoding="utf-8")
        first_raise = sql.index("RAISE EXCEPTION")
        first_delete = sql.index("DELETE FROM")

        self.assertLess(first_raise, first_delete)
        for table_name in REPAIRED_N6_GUARD_TABLES:
            self.assertIn(table_name, sql)
            self.assertIn(f"to_regclass('public.{table_name}')", sql)
        forbidden_tokens = [" CASCADE", "DROP TABLE", "TRUNCATE"]
        for token in forbidden_tokens:
            self.assertNotIn(token, sql.upper())
        self.assertIn("DELETE FROM stock_action_confirmation_projection_metric", sql)
        self.assertIn("DELETE FROM index_action_confirmation_projection_metric", sql)
        self.assertIn("DELETE FROM board_action_confirmation_projection_metric", sql)
        self.assertNotIn("DELETE FROM common_event_outbox", sql)
        self.assertNotIn("DELETE FROM common_event_inbox", sql)
        self.assertNotIn("DELETE FROM common_event_consumer_checkpoint", sql)


if __name__ == "__main__":
    unittest.main()
