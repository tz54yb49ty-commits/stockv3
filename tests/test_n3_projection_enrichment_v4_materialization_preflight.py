import json
import re
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from ashare_v3.market.projection_enrichment_v4_materialization_execute import (
    ALLOWED_WRITE_TABLES,
    ATTACH_EXISTING_PROJECTION_RUN_MODE,
    DEFAULT_MATERIALIZATION_MODE,
    EXECUTE_COMMAND,
    count_payload_rows,
    db_allowed_signal_types,
    execute_preflight,
    run,
    row_insert_params,
    validate_payload,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_JSON = ROOT / "docs" / "N3_projection_enrichment_v4_20260603_materialization_contract.json"
PREFLIGHT_JSON = ROOT / "docs" / "N3_projection_enrichment_v4_20260603_materialization_preflight.json"
PAYLOAD_JSON = ROOT / "docs" / "N3_projection_enrichment_v4_20260603_row_payload.json"
ROLLBACK_SQL = ROOT / "sql" / "N3_projection_enrichment_v4_20260603_materialization_rollback.sql"
SCRIPT_PATH = ROOT / "scripts" / "run_n3_projection_enrichment_v4_materialization_execute.py"


class N3ProjectionEnrichmentV4MaterializationPreflightTest(unittest.TestCase):
    def test_contract_records_schema_ready_and_allowed_write_scope_only(self) -> None:
        contract = json.loads(CONTRACT_JSON.read_text(encoding="utf-8"))

        self.assertEqual(contract["result"], "CONTRACT_READY")
        self.assertFalse(contract["db_materialization_plan"]["schema_migration_required"])
        self.assertEqual(
            contract["future_execute_allowed_write_tables"],
            [
                "common_market_data_run",
                "common_market_data_quality_item",
                "stock_projection_enrichment_v4_metric",
                "index_projection_enrichment_v4_metric",
                "board_projection_enrichment_v4_metric",
            ],
        )
        for forbidden in (
            "common_event_outbox",
            "common_event_inbox",
            "common_event_consumer_checkpoint",
            "N4/N5/N6",
            "worker",
        ):
            self.assertIn(forbidden, contract["forbidden_writes"])

    def test_preflight_refreshes_schema_and_baseline_after_034_migration(self) -> None:
        preflight = json.loads(PREFLIGHT_JSON.read_text(encoding="utf-8"))
        payload = json.loads(PAYLOAD_JSON.read_text(encoding="utf-8"))

        self.assertEqual(preflight["target_run_id"], payload["target_run_id"])
        self.assertEqual(preflight["result"], "PREFLIGHT_PASS")
        self.assertEqual(preflight["data_preflight_result"], "PREFLIGHT_PASS")
        self.assertEqual(preflight["row_count"], 5222)
        self.assertEqual(preflight["complete_lineage_rows"], 5218)
        self.assertEqual(preflight["bj_quality_visible_rows"], 4)
        self.assertEqual(preflight["baseline_summary"]["total_scoped_rows"], 0)
        self.assertEqual(preflight["baseline_summary"]["outbox_inbox_checkpoint_refs"], {"outbox": 0, "inbox": 0, "checkpoint": 0})
        self.assertEqual(preflight["data_quality"], {"P0": 0, "P1": 1, "P2": 0})
        self.assertEqual(preflight["quality"], {"P0": 0, "P1": 1, "P2": 0})
        self.assertEqual(preflight["blockers"], [])
        self.assertTrue(preflight["execute_runner_readiness"]["runner_exists"])
        self.assertEqual(preflight["execute_runner_readiness"]["runner_path"], "scripts/run_n3_projection_enrichment_v4_materialization_execute.py")

        for asset_kind in ("stock", "index", "board"):
            status = preflight["schema_status"][asset_kind]
            self.assertTrue(status["row_level_table_exists"])
            self.assertEqual(status["row_count"], 0)

    def test_rollback_hard_fails_before_delete_and_covers_downstream_refs(self) -> None:
        sql = ROLLBACK_SQL.read_text(encoding="utf-8")
        executable_sql = "\n".join(
            line for line in sql.splitlines() if not line.lstrip().startswith("--")
        ).lower()
        first_delete = re.search(r"\bdelete\s+from\b", executable_sql)

        self.assertIsNotNone(first_delete, "rollback SQL must contain scoped DELETE statements")
        self.assertIn("raise exception", executable_sql)
        self.assertLess(executable_sql.index("raise exception"), first_delete.start())

        for token in (
            "common_event_outbox",
            "common_event_inbox",
            "common_event_consumer_checkpoint",
            "common_trigger_%",
            "common_action_%",
            "user_projection",
            "user_signal",
            "notification",
            "downstream_layers_touched",
            "worker_started",
        ):
            with self.subTest(token=token):
                self.assertIn(token, sql)

        delete_targets = re.findall(r"\bdelete\s+from\s+([a-zA-Z0-9_]+)", executable_sql)
        self.assertEqual(
            delete_targets,
            [
                "stock_projection_enrichment_v4_metric",
                "index_projection_enrichment_v4_metric",
                "board_projection_enrichment_v4_metric",
                "common_market_data_quality_item",
                "common_market_data_run",
            ],
        )
        for forbidden in (
            "delete from common_event_outbox",
            "delete from common_event_inbox",
            "delete from common_event_consumer_checkpoint",
            "update common_event_outbox",
            "update common_event_inbox",
            "update common_event_consumer_checkpoint",
            "delete from common_trigger_",
            "delete from common_action_",
            "delete from user_projection",
            "delete from user_signal",
            "delete from user_notification",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, executable_sql)

    def test_execute_runner_exists_and_command_is_solidified(self) -> None:
        contract = json.loads(CONTRACT_JSON.read_text(encoding="utf-8"))

        self.assertTrue(SCRIPT_PATH.exists())
        self.assertEqual(contract["execute_command"]["candidate"], EXECUTE_COMMAND)
        self.assertTrue(contract["execute_command"]["solidified"])
        self.assertEqual(ALLOWED_WRITE_TABLES, contract["future_execute_allowed_write_tables"])
        for legacy_table in (
            "stock_action_confirmation_projection_metric",
            "index_action_confirmation_projection_metric",
            "board_action_confirmation_projection_metric",
            "stock_realtime_projection_metric",
            "index_realtime_projection_metric",
            "board_realtime_projection_metric",
        ):
            self.assertNotIn(legacy_table, ALLOWED_WRITE_TABLES)

    def test_missing_execute_or_user_confirmation_blocks_before_database(self) -> None:
        args = _args(execute=False, user_confirmed=True)
        report = run(args, connect=lambda *_args, **_kwargs: self.fail("database must not be opened"))
        self.assertEqual(report["execute_result"], "BLOCKED")
        self.assertIn("missing_execute_flag", report["blocked_reasons"])
        self.assertTrue(report["blocked_before_database_write"])

        args = _args(execute=True, user_confirmed=False)
        report = run(args, connect=lambda *_args, **_kwargs: self.fail("database must not be opened"))
        self.assertEqual(report["execute_result"], "BLOCKED")
        self.assertIn("missing_user_confirmed_flag", report["blocked_reasons"])
        self.assertTrue(report["blocked_before_database_write"])

    def test_payload_counts_and_bj_quality_visible_rows_are_preserved(self) -> None:
        payload = json.loads(PAYLOAD_JSON.read_text(encoding="utf-8"))
        validation = validate_payload(payload)

        self.assertEqual(count_payload_rows(payload["rows"]), {"stock": 4164, "index": 168, "board": 890, "total": 5222})
        self.assertTrue(validation["valid"])
        self.assertEqual(validation["row_count"], 5222)
        self.assertEqual(validation["complete_lineage_rows"], 5218)
        self.assertEqual(validation["bj_quality_visible_rows"], 4)
        self.assertEqual(validation["bj_quality_visible_rows_by_identity"], {"index:BJ:899050": 2, "index:BJ:899601": 2})

    def test_db_allowed_signal_types_are_canonicalized_without_losing_payload_trace(self) -> None:
        self.assertEqual(db_allowed_signal_types({"allowed_signal_types": ["B_BUY", "B_BUY_30M_VOL"]}), ["BUY"])
        self.assertEqual(db_allowed_signal_types({"allowed_signal_types": ["S_SELL", "S_SELL_30M_SHRINK"]}), ["SELL"])
        self.assertEqual(db_allowed_signal_types({"allowed_signal_types": ["BUY_HINT"]}), ["BUY_HINT"])
        self.assertEqual(db_allowed_signal_types({"allowed_signal_types": ["SELL_HINT"]}), ["SELL_HINT"])

    def test_20260617_exact_bj_daily_only_payload_validates_from_declared_expectations(self) -> None:
        payload = _bj_20260617_payload()

        validation = validate_payload(payload)

        self.assertTrue(validation["valid"], validation["blocked_reasons"])
        self.assertEqual(validation["target_run_id"], ACTION_METRIC_RUN_ID_20260617)
        self.assertEqual(validation["materialization_mode"], "attach_to_existing_projection_run")
        self.assertEqual(validation["row_count"], 4)
        self.assertEqual(validation["complete_lineage_rows"], 0)
        self.assertEqual(validation["bj_quality_visible_rows_by_identity"], {"index:BJ:899050": 2, "index:BJ:899601": 2})

    def test_20260617_missing_bj_quality_visible_row_blocks(self) -> None:
        payload = _bj_20260617_payload()
        payload["rows"] = payload["rows"][:-1]

        validation = validate_payload(payload)

        self.assertFalse(validation["valid"])
        self.assertIn("payload_expected_rows_mismatch", validation["blocked_reasons"])
        self.assertIn("payload_bj_quality_visible_row_key_mismatch", validation["blocked_reasons"])

    def test_20260617_malformed_bj_quality_visible_proof_blocks(self) -> None:
        cases = {
            "quality_visible_false": {"quality_visible": False},
            "metric_ready_true": {"metric_ready": True},
            "metric_quality_not_missing": {"metric_quality_status": "passed"},
            "freshness_not_quality_visible": {"source_freshness_status": "fresh_complete_lineage"},
        }
        for name, patch in cases.items():
            with self.subTest(name=name):
                payload = _bj_20260617_payload()
                payload["rows"][0].update(patch)

                validation = validate_payload(payload)

                self.assertFalse(validation["valid"])
                self.assertIn("payload_bj_quality_visible_proof_malformed", validation["blocked_reasons"])

    def test_row_insert_params_preserves_explicit_source_subscription_run_id(self) -> None:
        row = _bj_20260617_payload()["rows"][0]

        params = row_insert_params(row)

        self.assertEqual(params["source_snapshot_run_id"], TODAY_MINUTE_RUN_ID_20260617)
        self.assertEqual(params["source_subscription_run_id"], SUBSCRIPTION_RUN_ID_20260617)

    def test_attach_existing_run_mode_without_execute_blocks_before_database(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            payload_path = Path(tmpdir) / "payload.json"
            contract_path = Path(tmpdir) / "contract.json"
            payload_path.write_text(json.dumps(_bj_20260617_payload()), encoding="utf-8")
            contract_path.write_text(
                json.dumps(
                    {
                        "target_run_id": ACTION_METRIC_RUN_ID_20260617,
                        "expected_rows": 4,
                        "materialization_mode": "attach_to_existing_projection_run",
                        "future_execute_allowed_write_tables": ALLOWED_WRITE_TABLES,
                        "forbidden_writes": [
                            "common_event_outbox",
                            "common_event_inbox",
                            "common_event_consumer_checkpoint",
                            "N4/N5/N6",
                            "worker",
                        ],
                    }
                ),
                encoding="utf-8",
            )
            args = _args(execute=False, user_confirmed=True)
            args.payload_path = str(payload_path)
            args.contract_path = str(contract_path)

            report = run(args, connect=lambda *_args, **_kwargs: self.fail("database must not be opened"))

        self.assertEqual(report["execute_result"], "BLOCKED")
        self.assertIn("missing_execute_flag", report["blocked_reasons"])
        self.assertFalse(report["writes_performed"])
        self.assertTrue(report["blocked_before_database_write"])

    def test_attach_preflight_allows_payload_only_event_refs_with_explicit_opt_in(self) -> None:
        preflight = _execute_preflight_with_refs(
            _event_refs(payload_only_outbox_refs=7, payload_only_inbox_refs=3),
            allow_payload_only=True,
        )

        self.assertEqual(preflight["blocked_reasons"], [])
        self.assertEqual(preflight["event_refs"]["payload_only_outbox_refs"], 7)
        self.assertEqual(preflight["event_refs"]["payload_only_inbox_refs"], 3)
        self.assertIn("payload_only_event_refs_allowed_by_contract", preflight["warnings"])

    def test_attach_preflight_blocks_payload_only_event_refs_without_opt_in(self) -> None:
        preflight = _execute_preflight_with_refs(
            _event_refs(payload_only_outbox_refs=7, payload_only_inbox_refs=3),
            allow_payload_only=False,
        )

        self.assertIn("payload_only_event_refs_require_contract_opt_in", preflight["blocked_reasons"])
        self.assertEqual(preflight["warnings"], [])

    def test_attach_preflight_blocks_direct_outbox_source_run_id_ref(self) -> None:
        preflight = _execute_preflight_with_refs(
            _event_refs(direct_outbox_source_run_id_refs=1, payload_only_outbox_refs=7),
            allow_payload_only=True,
        )

        self.assertIn("direct_outbox_source_run_id_refs_nonzero", preflight["blocked_reasons"])

    def test_attach_preflight_blocks_direct_inbox_source_run_id_ref(self) -> None:
        preflight = _execute_preflight_with_refs(
            _event_refs(direct_inbox_source_run_id_refs=1, payload_only_inbox_refs=3),
            allow_payload_only=True,
        )

        self.assertIn("direct_inbox_source_run_id_refs_nonzero", preflight["blocked_reasons"])

    def test_attach_preflight_blocks_checkpoint_ref(self) -> None:
        preflight = _execute_preflight_with_refs(
            _event_refs(checkpoint_refs=1),
            allow_payload_only=True,
        )

        self.assertIn("checkpoint_event_refs_nonzero", preflight["blocked_reasons"])

    def test_attach_preflight_blocks_projection_enrichment_baseline_nonzero(self) -> None:
        preflight = _execute_preflight_with_refs(
            _event_refs(),
            allow_payload_only=True,
            projection_enrichment_rows=1,
        )

        self.assertIn("scoped_projection_enrichment_v4_baseline_nonzero", preflight["blocked_reasons"])

    def test_default_materialization_still_blocks_payload_only_event_refs(self) -> None:
        preflight = _execute_preflight_with_refs(
            _event_refs(payload_only_outbox_refs=1),
            materialization_mode=DEFAULT_MATERIALIZATION_MODE,
            allow_payload_only=True,
        )

        self.assertIn("scoped_event_infra_refs_nonzero", preflight["blocked_reasons"])
        self.assertNotIn("payload_only_event_refs_allowed_by_contract", preflight["warnings"])


def _args(*, execute: bool, user_confirmed: bool) -> Namespace:
    return Namespace(
        dsn="postgresql://should-not-connect",
        payload_path=str(PAYLOAD_JSON),
        contract_path=str(CONTRACT_JSON),
        execute=execute,
        user_confirmed=user_confirmed,
        operator="unit-test",
        confirmation_note="",
        report_path="docs/_unit_test_should_not_write_report.json",
    )


def _execute_preflight_with_refs(
    event_refs: dict[str, int],
    *,
    materialization_mode: str = ATTACH_EXISTING_PROJECTION_RUN_MODE,
    allow_payload_only: bool = False,
    projection_enrichment_rows: int = 0,
) -> dict[str, object]:
    contract = {
        "allow_attach_with_payload_only_event_refs": allow_payload_only,
        "source_inputs": {},
    }
    validation = {
        "target_run_id": ACTION_METRIC_RUN_ID_20260617,
        "materialization_mode": materialization_mode,
    }
    common_run_rows = 1 if materialization_mode == ATTACH_EXISTING_PROJECTION_RUN_MODE else 0
    conn = _PreflightConn(
        {
            "common_market_data_run": common_run_rows,
            "common_market_data_quality_item": 0,
            "stock_projection_enrichment_v4_metric": 0,
            "index_projection_enrichment_v4_metric": projection_enrichment_rows,
            "board_projection_enrichment_v4_metric": 0,
        }
    )
    module_path = "ashare_v3.market.projection_enrichment_v4_materialization_execute"
    from unittest.mock import patch

    with patch(f"{module_path}.fetch_source_status", return_value={"source_condition": "passed"}), patch(
        f"{module_path}.count_event_refs", return_value=event_refs
    ):
        return execute_preflight(conn, contract, validation)


def _event_refs(
    *,
    direct_outbox_source_run_id_refs: int = 0,
    direct_inbox_source_run_id_refs: int = 0,
    payload_only_outbox_refs: int = 0,
    payload_only_inbox_refs: int = 0,
    checkpoint_refs: int = 0,
) -> dict[str, int]:
    return {
        "direct_outbox_source_run_id_refs": direct_outbox_source_run_id_refs,
        "direct_inbox_source_run_id_refs": direct_inbox_source_run_id_refs,
        "payload_only_outbox_refs": payload_only_outbox_refs,
        "payload_only_inbox_refs": payload_only_inbox_refs,
        "checkpoint_refs": checkpoint_refs,
    }


class _PreflightConn:
    def __init__(self, table_counts: dict[str, int]) -> None:
        self.table_counts = table_counts

    def cursor(self) -> "_PreflightCursor":
        return _PreflightCursor(self.table_counts)


class _PreflightCursor:
    def __init__(self, table_counts: dict[str, int]) -> None:
        self.table_counts = table_counts
        self._count = 0

    def __enter__(self) -> "_PreflightCursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, sql: str, _params: object = None) -> None:
        for table_name, count in self.table_counts.items():
            if table_name in sql:
                self._count = count
                return
        self._count = 0

    def fetchone(self) -> dict[str, int]:
        return {"count": self._count}


ACTION_METRIC_RUN_ID_20260617 = (
    "action_confirmation_projection_metric_20260617_full_day__"
    "market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1"
)
TRIGGER_CONTEXT_RUN_ID_20260617 = (
    "trigger_context_snapshot_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1"
)
CONDITION_RUN_ID_20260617 = "condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1"
SUBSCRIPTION_RUN_ID_20260617 = (
    "market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1"
)
TODAY_MINUTE_RUN_ID_20260617 = (
    "today_minute_bar_1m_20260617_full_day__"
    "market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1"
)
PREVIOUS_DAY_MINUTE_RUN_ID_20260617 = (
    "previous_day_minute_preload_20260616_for_20260617__"
    "market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1"
)
EXPECTED_BJ_20260617_ROW_KEYS = [
    "index:BJ:899050|buy|BUY:M,W",
    "index:BJ:899050|sell|SELL:M,W,D",
    "index:BJ:899601|buy|BUY:W",
    "index:BJ:899601|sell|SELL:M,W,D",
]


def _bj_20260617_payload() -> dict[str, object]:
    rows = [
        _bj_20260617_row("index:BJ:899050", "899050", "北证50", "buy", "BUY:M,W", 1001),
        _bj_20260617_row("index:BJ:899050", "899050", "北证50", "sell", "SELL:M,W,D", 1002),
        _bj_20260617_row("index:BJ:899601", "899601", "北证中小", "buy", "BUY:W", 1003),
        _bj_20260617_row("index:BJ:899601", "899601", "北证中小", "sell", "SELL:M,W,D", 1004),
    ]
    return {
        "artifact_type": "N3_projection_enrichment_v4_row_level_payload",
        "target_run_id": ACTION_METRIC_RUN_ID_20260617,
        "materialization_mode": "attach_to_existing_projection_run",
        "expected_rows": 4,
        "expected_complete_lineage_rows": 0,
        "expected_bj_quality_visible_rows_by_identity": {"index:BJ:899050": 2, "index:BJ:899601": 2},
        "expected_bj_quality_visible_row_keys": EXPECTED_BJ_20260617_ROW_KEYS,
        "expected_source_trigger_context_run_id": TRIGGER_CONTEXT_RUN_ID_20260617,
        "spec_version": "n3.projection_enrichment_v4.row_level.v1",
        "policy_hash": "unit-test-policy-hash",
        "rows": rows,
    }


def _bj_20260617_row(
    identity_key: str,
    code: str,
    name: str,
    direction: str,
    condition_key: str,
    source_trigger_context_id: int,
) -> dict[str, object]:
    return {
        "target_run_id": ACTION_METRIC_RUN_ID_20260617,
        "spec_version": "n3.projection_enrichment_v4.row_level.v1",
        "policy_hash": "unit-test-policy-hash",
        "source_condition_run_id": CONDITION_RUN_ID_20260617,
        "source_subscription_run_id": SUBSCRIPTION_RUN_ID_20260617,
        "source_snapshot_run_id": TODAY_MINUTE_RUN_ID_20260617,
        "source_minute_run_id": None,
        "source_previous_day_minute_run_id": PREVIOUS_DAY_MINUTE_RUN_ID_20260617,
        "source_trigger_context_run_id": TRIGGER_CONTEXT_RUN_ID_20260617,
        "source_trigger_context_id": source_trigger_context_id,
        "asset_kind": "index",
        "identity_key": identity_key,
        "exchange": "BJ",
        "code": code,
        "display_code": code,
        "name": name,
        "direction": direction,
        "condition_key": condition_key,
        "allowed_signal_types": ["BUY"] if direction == "buy" else ["SELL"],
        "current_price_or_close": 1000,
        "current_amount_metric": None,
        "current_metric_time": None,
        "current_metric_quality_status": "missing",
        "metric_quality_status": "missing",
        "projection_period": "30m",
        "projection_30m_flag": None,
        "projection_30m_type": "unknown",
        "current_30m_virtual_amount": None,
        "reference_30m_amount": None,
        "reference_30m_entity_high": None,
        "reference_30m_entity_low": None,
        "trigger_amount_chain_pass": {
            "ready": False,
            "_trace": {"source_condition_run_id": CONDITION_RUN_ID_20260617, "source_trigger_context_id": source_trigger_context_id},
        },
        "projection_lineage_json": {"source_snapshot_id": None},
        "source_freshness_status": "source_minute_missing_quality_visible",
        "metric_ready": False,
        "quality_visible": {
            "status": "missing",
            "severity": "P1",
            "reason": "BJ source minute missing quality-visible; no silent fallback",
            "today_minute_bar_count": 0,
            "previous_day_minute_bar_count": 0,
        },
    }


if __name__ == "__main__":
    unittest.main()
