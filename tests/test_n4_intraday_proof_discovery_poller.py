import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.run_n4_provisional_ordinary_execute_once import build_arg_parser as build_ordinary_arg_parser


EXPECTED_PYTHON = "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3"
FOR_TRADE_DATE = "20260701"
SOURCE_TRADE_DATE = "20260630"
SOURCE_CONDITION_RUN_ID = "condition_layer_20260630_source_20260630_for_20260701_v1"
CONTEXT_RUN_ID = "trigger_context_snapshot_20260701_condition_layer_20260630_source_20260630_for_20260701_v1__atomic_rule_v1"
SUBSCRIPTION_RUN_ID = "market_data_subscription_20260701_condition_layer_20260630_source_20260630_for_20260701_v1"

ORDINARY_0946_SOURCE = (
    "realtime_action_confirmation_metric_20260701_until_0946__asset_all__"
    "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__"
    f"{SUBSCRIPTION_RUN_ID}"
)
ORDINARY_1412_SOURCE = (
    "realtime_action_confirmation_metric_20260701_until_1412__asset_all__"
    "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__"
    f"{SUBSCRIPTION_RUN_ID}"
)
ORDINARY_1429_SOURCE = (
    "realtime_action_confirmation_metric_20260701_until_1429__asset_all__"
    "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__"
    f"{SUBSCRIPTION_RUN_ID}"
)
ORDINARY_1453_SOURCE = (
    "realtime_action_confirmation_metric_20260701_until_1453__asset_all__"
    "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__"
    f"{SUBSCRIPTION_RUN_ID}"
)
ORDINARY_1453_SOURCE_V2 = (
    "realtime_action_confirmation_metric_20260701_until_1453__asset_all__"
    "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__"
    "market_data_subscription_20260701_condition_layer_20260630_source_20260630_for_20260701_v2"
)
ORDINARY_1500_SOURCE = (
    "realtime_action_confirmation_metric_20260701_until_1500__asset_all__"
    "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__"
    f"{SUBSCRIPTION_RUN_ID}"
)
HINT_1044_SOURCE = (
    "realtime_hint_projection_metric_20260701_until_1044__asset_index_board__"
    f"index_board_1m_hint_projection_v1_midday_bridge_v1__{SUBSCRIPTION_RUN_ID}"
)
HINT_1429_SOURCE = (
    "realtime_hint_projection_metric_20260701_until_1429__asset_index_board__"
    f"index_board_1m_hint_projection_v1_midday_bridge_v1__{SUBSCRIPTION_RUN_ID}"
)
HINT_1454_SOURCE = (
    "realtime_hint_projection_metric_20260701_until_1454__asset_index_board__"
    f"index_board_1m_hint_projection_v1_midday_bridge_v1__{SUBSCRIPTION_RUN_ID}"
)

ORDINARY_0946_TARGET = (
    "trigger_provisional_ordinary_20260701_until_0946__realtime_action_confirmation_metric_20260701_until_0946"
    "__asset_all__b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1"
    "__atomic_rule_v1_period_rollover_guard_v1"
)
ORDINARY_1412_TARGET = (
    "trigger_provisional_ordinary_20260701_until_1412__realtime_action_confirmation_metric_20260701_until_1412"
    "__asset_all__b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1"
    "__atomic_rule_v1_period_rollover_guard_v1"
)
ORDINARY_1429_TARGET = (
    "trigger_provisional_ordinary_20260701_until_1429__realtime_action_confirmation_metric_20260701_until_1429"
    "__asset_all__b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1"
    "__atomic_rule_v1_period_rollover_guard_v1"
)
ORDINARY_1453_TARGET = (
    "trigger_provisional_ordinary_20260701_until_1453__realtime_action_confirmation_metric_20260701_until_1453"
    "__asset_all__b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1"
    "__atomic_rule_v1_period_rollover_guard_v1"
)
ORDINARY_1500_TARGET = (
    "trigger_provisional_ordinary_20260701_until_1500__realtime_action_confirmation_metric_20260701_until_1500"
    "__asset_all__b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1"
    "__atomic_rule_v1_period_rollover_guard_v1"
)
HINT_1044_TARGET = (
    "trigger_provisional_b2_20260701_until_1044__realtime_hint_projection_metric_20260701_until_1044"
    "__asset_index_board__index_board_1m_hint_projection_v1_midday_bridge_v1__atomic_rule_v1"
)
HINT_1429_TARGET = (
    "trigger_provisional_b2_20260701_until_1429__realtime_hint_projection_metric_20260701_until_1429"
    "__asset_index_board__index_board_1m_hint_projection_v1_midday_bridge_v1__atomic_rule_v1"
)
HINT_1454_TARGET = (
    "trigger_provisional_b2_20260701_until_1454__realtime_hint_projection_metric_20260701_until_1454"
    "__asset_index_board__index_board_1m_hint_projection_v1_midday_bridge_v1__atomic_rule_v1"
)


def write_lineage_config(path: Path, *, enabled: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "enabled": enabled,
                "for_trade_date": "20260702",
                "source_trade_date": "20260701",
                "n2_run_id": "condition_layer_20260701_source_20260701_for_20260702_v1",
                "subscription_run_id": "market_data_subscription_20260702_condition_layer_20260701_source_20260701_for_20260702_v1",
                "a1_preload_run_id": (
                    "previous_day_minute_preload_20260701_for_20260702__"
                    "market_data_subscription_20260702_condition_layer_20260701_source_20260701_for_20260702_v1"
                ),
                "n4_context_run_id": "trigger_context_snapshot_20260702_condition_layer_20260701_source_20260701_for_20260702_v1__atomic_rule_v1",
                "updated_by": "test",
                "updated_at": "2026-07-01T18:00:00+08:00",
                "source_status_path": "docs/post_close_fastlane/20260702/00_status.json",
                "source_oneshot_report_path": "docs/post_close_fastlane/20260702/01_oneshot_execute_report.json",
            }
        ),
        encoding="utf-8",
    )
    docs_root = path.parent
    if docs_root.name == "runtime":
        docs_root = docs_root.parent
    fastlane_root = docs_root / "post_close_fastlane"
    status_dir = fastlane_root / "20260702"
    status_dir.mkdir(parents=True, exist_ok=True)
    (status_dir / "00_status.json").write_text(
        json.dumps(
            {
                "result": "EXECUTE_PASS",
                "for_trade_date": "20260702",
                "source_trade_date": "20260701",
            }
        ),
        encoding="utf-8",
    )
    latest = fastlane_root / "latest"
    if latest.exists() or latest.is_symlink():
        latest.unlink()
    latest.symlink_to("20260702")


def write_latest_status(docs_root: Path, *, for_trade_date: str, result: str, failed_step_id: str | None = None) -> None:
    fastlane_root = docs_root / "post_close_fastlane"
    status_dir = fastlane_root / for_trade_date
    status_dir.mkdir(parents=True, exist_ok=True)
    (status_dir / "00_status.json").write_text(
        json.dumps(
            {
                "result": result,
                "failed_step_id": failed_step_id,
                "for_trade_date": for_trade_date,
                "source_trade_date": "20260701",
            }
        ),
        encoding="utf-8",
    )
    latest = fastlane_root / "latest"
    if latest.exists() or latest.is_symlink():
        latest.unlink()
    latest.symlink_to(for_trade_date)


def ordinary_candidate(run_id: str, *, row_count: int = 10, role: str = "trigger_proof") -> dict[str, object]:
    return {
        "run_id": run_id,
        "status": "passed",
        "proof_family": "ordinary",
        "metric_role": role,
        "proof_owner": "N3",
        "proof_consumer": "N4",
        "not_n5_final_proof": True,
        "row_count": row_count,
        "stock_row_count": row_count,
        "index_row_count": 0,
        "board_row_count": 0,
    }


def ordinary_candidate_with_expected_counts(run_id: str) -> dict[str, object]:
    candidate = ordinary_candidate(run_id)
    candidate.update({"expected_state_count": 2, "expected_match_count": 2, "expected_outbox_count": 2})
    return candidate


def hint_candidate(run_id: str, *, row_count: int = 6, stock_rows: int = 0) -> dict[str, object]:
    return {
        "run_id": run_id,
        "status": "passed",
        "proof_family": "hint",
        "metric_role": "hint_trigger_proof",
        "proof_owner": "N3",
        "proof_consumer": "N4",
        "not_n5_final_proof": True,
        "row_count": row_count,
        "stock_row_count": stock_rows,
        "index_row_count": 0,
        "board_row_count": row_count,
    }


def passed_target(
    run_id: str,
    *,
    source_run_id: str,
    previous_trigger_run_id: str = "",
    state_count: int = 1,
    match_count: int = 1,
    outbox_count: int = 1,
    run_state_count: int | None = None,
    run_match_count: int | None = None,
    run_outbox_count: int | None = None,
    downstream_ref_count: int = 0,
) -> dict[str, object]:
    return {
        "run_id": run_id,
        "status": "passed",
        "source_run_id": source_run_id,
        "previous_trigger_run_id": previous_trigger_run_id,
        "state_count": state_count,
        "match_count": match_count,
        "outbox_count": outbox_count,
        "run_state_count": state_count if run_state_count is None else run_state_count,
        "run_match_count": match_count if run_match_count is None else run_match_count,
        "run_outbox_count": outbox_count if run_outbox_count is None else run_outbox_count,
        "outbox_delivered_delivering": 0,
        "downstream_ref_count": downstream_ref_count,
    }


class N4IntradayProofDiscoveryPollerTest(unittest.TestCase):
    def test_discovery_poller_uses_enabled_lineage_config_over_stale_cli_lineage(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import build_proof_discovery_plan

        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "current_intraday_worker_lineage.json"
            write_lineage_config(config_path)

            report = build_proof_discovery_plan(
                for_trade_date=FOR_TRADE_DATE,
                source_trade_date=SOURCE_TRADE_DATE,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                trigger_context_run_id=CONTEXT_RUN_ID,
                lineage_config_path=str(config_path),
                ordinary_candidates=[],
                hint_candidates=[],
                existing_targets=[],
            )

        self.assertEqual(report["result"], "PLAN_ONLY_PASS")
        self.assertTrue(report["lineage_config_used"])
        self.assertEqual(report["effective_for_trade_date"], "20260702")
        self.assertEqual(report["effective_source_trade_date"], "20260701")
        self.assertEqual(report["for_trade_date"], "20260702")
        self.assertEqual(report["source_condition_run_id"], "condition_layer_20260701_source_20260701_for_20260702_v1")
        self.assertEqual(
            report["trigger_context_run_id"],
            "trigger_context_snapshot_20260702_condition_layer_20260701_source_20260701_for_20260702_v1__atomic_rule_v1",
        )

    def test_discovery_poller_blocks_missing_lineage_config_without_stale_fallback(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import ProofDiscoveryBlocked, build_proof_discovery_plan

        with self.assertRaises(ProofDiscoveryBlocked):
            build_proof_discovery_plan(
                for_trade_date=FOR_TRADE_DATE,
                source_trade_date=SOURCE_TRADE_DATE,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                trigger_context_run_id=CONTEXT_RUN_ID,
                lineage_config_path="/tmp/missing-current-intraday-worker-lineage.json",
                ordinary_candidates=[],
                hint_candidates=[],
                existing_targets=[],
            )

    def test_discovery_poller_blocks_stale_lineage_when_latest_attempt_is_newer_and_blocked(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import ProofDiscoveryBlocked, build_proof_discovery_plan

        with tempfile.TemporaryDirectory() as tmp:
            docs_root = Path(tmp) / "docs"
            config_path = docs_root / "runtime" / "current_intraday_worker_lineage.json"
            write_lineage_config(config_path)
            write_latest_status(
                docs_root,
                for_trade_date="20260703",
                result="PARTIAL_BLOCKED",
                failed_step_id="worker_launchd_guard",
            )

            with self.assertRaises(ProofDiscoveryBlocked) as ctx:
                build_proof_discovery_plan(
                    for_trade_date=FOR_TRADE_DATE,
                    source_trade_date=SOURCE_TRADE_DATE,
                    source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                    trigger_context_run_id=CONTEXT_RUN_ID,
                    lineage_config_path=str(config_path),
                    ordinary_candidates=[],
                    hint_candidates=[],
                    existing_targets=[],
                )

        message = str(ctx.exception)
        self.assertIn("BLOCKED_INTRADAY_WORKER_LINEAGE_CONFIG", message)
        self.assertIn("BLOCKED_STALE_INTRADAY_WORKER_LINEAGE", message)
        self.assertIn("active_for_trade_date=20260702", message)
        self.assertIn("latest_attempted_for_trade_date=20260703", message)
        self.assertIn("latest_result=PARTIAL_BLOCKED", message)
        self.assertIn("latest_failed_step_id=worker_launchd_guard", message)

    def test_db_discovery_uses_parameterized_like_patterns(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import discover_proofs_from_db

        fake = FakePsycopgModule([])
        with patch.dict(
            sys.modules,
            {
                "psycopg": fake,
                "psycopg.rows": SimpleNamespace(dict_row="dict_row"),
            },
        ):
            discover_proofs_from_db(
                dsn="postgresql://unit-test",
                for_trade_date=FOR_TRADE_DATE,
                source_trade_date=SOURCE_TRADE_DATE,
            )

        market_sql, market_params = fake.cursor.executed[0]
        existing_sql, existing_params = fake.cursor.executed[-1]
        self.assertIn("run_id LIKE %s", market_sql)
        self.assertIn("OR run_id LIKE %s", market_sql)
        self.assertNotIn("run_id LIKE 'realtime_action_confirmation_metric_%", market_sql)
        self.assertNotIn("run_id LIKE 'realtime_hint_projection_metric_%", market_sql)
        self.assertIn("realtime_action_confirmation_metric_%current_period_avg_v1%", market_params)
        self.assertIn("realtime_hint_projection_metric_%index_board_1m_hint_projection_v1_midday_bridge_v1%", market_params)
        self.assertIn("run_id LIKE %s", existing_sql)
        self.assertNotIn("run_id LIKE 'trigger_provisional_ordinary_%", existing_sql)
        self.assertIn("trigger_provisional_ordinary_%", existing_params)
        self.assertIn("trigger_provisional_b2_%", existing_params)

    def test_db_discovery_returns_ordinary_and_hint_candidates_with_mocked_db(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import discover_proofs_from_db

        fake = FakePsycopgModule(
            [
                {
                    "run_id": ORDINARY_1453_SOURCE,
                    "status": "passed",
                    "for_trade_date": FOR_TRADE_DATE,
                    "source_trade_date": SOURCE_TRADE_DATE,
                    "source_condition_run_id": SOURCE_CONDITION_RUN_ID,
                },
                {
                    "run_id": HINT_1454_SOURCE,
                    "status": "passed",
                    "for_trade_date": FOR_TRADE_DATE,
                    "source_trade_date": SOURCE_TRADE_DATE,
                    "source_condition_run_id": SOURCE_CONDITION_RUN_ID,
                },
            ]
        )
        with patch.dict(
            sys.modules,
            {
                "psycopg": fake,
                "psycopg.rows": SimpleNamespace(dict_row="dict_row"),
            },
        ):
            discovered = discover_proofs_from_db(
                dsn="postgresql://unit-test",
                for_trade_date=FOR_TRADE_DATE,
                source_trade_date=SOURCE_TRADE_DATE,
            )

        self.assertEqual(discovered["ordinary_candidates"][0]["run_id"], ORDINARY_1453_SOURCE)
        self.assertEqual(discovered["ordinary_candidates"][0]["proof_family"], "ordinary")
        self.assertEqual(discovered["ordinary_candidates"][0]["row_count"], 10)
        self.assertEqual(discovered["hint_candidates"][0]["run_id"], HINT_1454_SOURCE)
        self.assertEqual(discovered["hint_candidates"][0]["proof_family"], "hint")
        self.assertEqual(discovered["hint_candidates"][0]["row_count"], 6)
        self.assertEqual(discovered["existing_targets"], [])

    def test_db_discovery_realtime_latest_only_contract_counts_only_latest_per_family(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import discover_proofs_from_db

        def ordinary_source(hhmm: str) -> dict[str, object]:
            return {
                "run_id": (
                    f"realtime_action_confirmation_metric_{FOR_TRADE_DATE}_until_{hhmm}__asset_all__"
                    "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__"
                    f"{SUBSCRIPTION_RUN_ID}"
                ),
                "status": "passed",
                "for_trade_date": FOR_TRADE_DATE,
                "source_trade_date": SOURCE_TRADE_DATE,
                "source_condition_run_id": SOURCE_CONDITION_RUN_ID,
            }

        def hint_source(hhmm: str) -> dict[str, object]:
            return {
                "run_id": (
                    f"realtime_hint_projection_metric_{FOR_TRADE_DATE}_until_{hhmm}__asset_index_board__"
                    f"index_board_1m_hint_projection_v1_midday_bridge_v1__{SUBSCRIPTION_RUN_ID}"
                ),
                "status": "passed",
                "for_trade_date": FOR_TRADE_DATE,
                "source_trade_date": SOURCE_TRADE_DATE,
                "source_condition_run_id": SOURCE_CONDITION_RUN_ID,
            }

        fake = FakePsycopgModule(
            [ordinary_source(f"{900 + i:04d}") for i in range(100)]
            + [hint_source(f"{900 + i:04d}") for i in range(100)]
        )
        with patch.dict(
            sys.modules,
            {
                "psycopg": fake,
                "psycopg.rows": SimpleNamespace(dict_row="dict_row"),
            },
        ):
            discovered = discover_proofs_from_db(
                dsn="postgresql://unit-test",
                for_trade_date=FOR_TRADE_DATE,
                source_trade_date=SOURCE_TRADE_DATE,
                selection_mode="realtime_latest_only",
            )

        self.assertEqual(len(discovered["ordinary_candidates"]), 100)
        self.assertEqual(len(discovered["hint_candidates"]), 100)
        self.assertEqual(discovered["ordinary_candidates"][0]["row_count"], 10)
        self.assertEqual(discovered["hint_candidates"][0]["row_count"], 6)
        self.assertTrue(discovered["ordinary_candidates"][1]["contract_validation_deferred"])
        self.assertTrue(discovered["hint_candidates"][1]["contract_validation_deferred"])
        self.assertLessEqual(fake.cursor.count_queries("FROM stock_action_confirmation_projection_metric"), 1)
        self.assertLessEqual(fake.cursor.count_queries("FROM index_action_confirmation_projection_metric"), 1)
        self.assertLessEqual(fake.cursor.count_queries("FROM board_action_confirmation_projection_metric"), 1)
        self.assertLessEqual(fake.cursor.count_queries("FROM index_realtime_hint_projection_metric"), 1)
        self.assertLessEqual(fake.cursor.count_queries("FROM board_realtime_hint_projection_metric"), 1)

    def test_hint_realtime_fast_path_discovers_only_latest_hint_candidate(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import discover_proofs_from_db

        def ordinary_source(hhmm: str) -> dict[str, object]:
            return {
                "run_id": (
                    f"realtime_action_confirmation_metric_{FOR_TRADE_DATE}_until_{hhmm}__asset_all__"
                    "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__"
                    f"{SUBSCRIPTION_RUN_ID}"
                ),
                "status": "passed",
                "for_trade_date": FOR_TRADE_DATE,
                "source_trade_date": SOURCE_TRADE_DATE,
                "source_condition_run_id": SOURCE_CONDITION_RUN_ID,
            }

        def hint_source(hhmm: str) -> dict[str, object]:
            return {
                "run_id": (
                    f"realtime_hint_projection_metric_{FOR_TRADE_DATE}_until_{hhmm}__asset_index_board__"
                    f"index_board_1m_hint_projection_v1_midday_bridge_v1__{SUBSCRIPTION_RUN_ID}"
                ),
                "status": "passed",
                "for_trade_date": FOR_TRADE_DATE,
                "source_trade_date": SOURCE_TRADE_DATE,
                "source_condition_run_id": SOURCE_CONDITION_RUN_ID,
            }

        fake = FakePsycopgModule(
            [ordinary_source(f"{900 + i:04d}") for i in range(20)]
            + [hint_source(f"{900 + i:04d}") for i in range(20)]
        )
        with patch.dict(
            sys.modules,
            {
                "psycopg": fake,
                "psycopg.rows": SimpleNamespace(dict_row="dict_row"),
            },
        ):
            discovered = discover_proofs_from_db(
                dsn="postgresql://unit-test",
                for_trade_date=FOR_TRADE_DATE,
                source_trade_date=SOURCE_TRADE_DATE,
                selection_mode="realtime_latest_only",
                mode="hint",
            )

        self.assertEqual(discovered["ordinary_candidates"], [])
        self.assertEqual(len(discovered["hint_candidates"]), 1)
        self.assertEqual(discovered["hint_candidates"][0]["run_id"], hint_source("0919")["run_id"])
        self.assertEqual(discovered["hint_candidates"][0]["row_count"], 6)
        self.assertLessEqual(fake.cursor.count_queries("FROM index_realtime_hint_projection_metric"), 1)
        self.assertLessEqual(fake.cursor.count_queries("FROM board_realtime_hint_projection_metric"), 1)
        self.assertEqual(fake.cursor.count_queries("FROM stock_action_confirmation_projection_metric"), 0)
        self.assertEqual(fake.cursor.count_queries("FROM common_trigger_run r"), 2)

    def test_hint_realtime_fast_path_noops_when_exact_target_exists(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import append_poll_history, run_proof_discovery_poll

        fake = FakePsycopgModule(
            [
                {
                    "run_id": HINT_1454_SOURCE,
                    "status": "passed",
                    "for_trade_date": FOR_TRADE_DATE,
                    "source_trade_date": SOURCE_TRADE_DATE,
                    "source_condition_run_id": SOURCE_CONDITION_RUN_ID,
                }
            ],
            target_rows=[
                {
                    "run_id": HINT_1454_TARGET,
                    "status": "passed",
                    "source_projection_run_id": HINT_1454_SOURCE,
                    "trigger_state_row_count": 6,
                    "trigger_match_row_count": 6,
                    "trigger_event_outbox_count": 6,
                    "raw_json": {"previous_trigger_run_id": HINT_1044_TARGET},
                },
                {
                    "run_id": HINT_1044_TARGET,
                    "status": "passed",
                    "source_projection_run_id": HINT_1044_SOURCE,
                    "trigger_state_row_count": 3,
                    "trigger_match_row_count": 3,
                    "trigger_event_outbox_count": 3,
                    "raw_json": {"previous_trigger_run_id": ""},
                },
            ],
        )
        with patch.dict(
            sys.modules,
            {
                "psycopg": fake,
                "psycopg.rows": SimpleNamespace(dict_row="dict_row"),
            },
        ):
            exit_code, report = run_proof_discovery_poll(
                dsn="postgresql://unit-test",
                for_trade_date=FOR_TRADE_DATE,
                source_trade_date=SOURCE_TRADE_DATE,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                trigger_context_run_id=CONTEXT_RUN_ID,
                mode="hint",
                selection_mode="realtime_latest_only",
                execute=True,
                user_confirmed=True,
                command_runner=lambda argv: self.fail("exact target should noop before child execution"),
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["result"], "noop")
        self.assertEqual(report["selected"]["hint"], None)
        self.assertEqual(report["discovery_policy"], "hint_realtime_latest_fast_path_v1")
        self.assertEqual(report["skipped_candidates"][0]["reason"], "already_passed_exact_target")
        self.assertEqual(report["skipped_candidates"][0]["source_run_id"], HINT_1454_SOURCE)
        self.assertEqual(report["child_execution"]["executed_child_command_count"], 0)
        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "hint_history.jsonl"
            append_poll_history(report, history_path=history_path)
            record = json.loads(history_path.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(record["discovery_policy"], "hint_realtime_latest_fast_path_v1")
        self.assertEqual(record["existing_target_skip"][0]["source_run_id"], HINT_1454_SOURCE)

    def test_ordinary_realtime_fast_path_discovers_only_latest_ordinary_candidate(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import discover_proofs_from_db

        def ordinary_source(hhmm: str) -> dict[str, object]:
            return {
                "run_id": (
                    f"realtime_action_confirmation_metric_{FOR_TRADE_DATE}_until_{hhmm}__asset_all__"
                    "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__"
                    f"{SUBSCRIPTION_RUN_ID}"
                ),
                "status": "passed",
                "for_trade_date": FOR_TRADE_DATE,
                "source_trade_date": SOURCE_TRADE_DATE,
                "source_condition_run_id": SOURCE_CONDITION_RUN_ID,
            }

        def hint_source(hhmm: str) -> dict[str, object]:
            return {
                "run_id": (
                    f"realtime_hint_projection_metric_{FOR_TRADE_DATE}_until_{hhmm}__asset_index_board__"
                    f"index_board_1m_hint_projection_v1_midday_bridge_v1__{SUBSCRIPTION_RUN_ID}"
                ),
                "status": "passed",
                "for_trade_date": FOR_TRADE_DATE,
                "source_trade_date": SOURCE_TRADE_DATE,
                "source_condition_run_id": SOURCE_CONDITION_RUN_ID,
            }

        fake = FakePsycopgModule(
            [ordinary_source(f"{900 + i:04d}") for i in range(20)]
            + [hint_source(f"{900 + i:04d}") for i in range(20)]
        )
        with patch.dict(
            sys.modules,
            {
                "psycopg": fake,
                "psycopg.rows": SimpleNamespace(dict_row="dict_row"),
            },
        ):
            discovered = discover_proofs_from_db(
                dsn="postgresql://unit-test",
                for_trade_date=FOR_TRADE_DATE,
                source_trade_date=SOURCE_TRADE_DATE,
                selection_mode="realtime_latest_only",
                mode="ordinary",
            )

        self.assertEqual(len(discovered["ordinary_candidates"]), 1)
        self.assertEqual(discovered["ordinary_candidates"][0]["run_id"], ordinary_source("0919")["run_id"])
        self.assertEqual(discovered["ordinary_candidates"][0]["row_count"], 10)
        self.assertEqual(discovered["hint_candidates"], [])
        self.assertEqual(discovered["discovery_policy"], "ordinary_realtime_latest_fast_path_v1")
        self.assertLessEqual(fake.cursor.count_queries("FROM stock_action_confirmation_projection_metric"), 1)
        self.assertLessEqual(fake.cursor.count_queries("FROM index_action_confirmation_projection_metric"), 1)
        self.assertLessEqual(fake.cursor.count_queries("FROM board_action_confirmation_projection_metric"), 1)
        self.assertEqual(fake.cursor.count_queries("FROM index_realtime_hint_projection_metric"), 0)
        self.assertEqual(fake.cursor.count_queries("FROM board_realtime_hint_projection_metric"), 0)
        self.assertEqual(fake.cursor.count_queries("FROM common_trigger_run r"), 2)

    def test_ordinary_realtime_fast_path_noops_when_exact_target_exists(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import append_poll_history, run_proof_discovery_poll

        fake = FakePsycopgModule(
            [
                {
                    "run_id": ORDINARY_1453_SOURCE,
                    "status": "passed",
                    "for_trade_date": FOR_TRADE_DATE,
                    "source_trade_date": SOURCE_TRADE_DATE,
                    "source_condition_run_id": SOURCE_CONDITION_RUN_ID,
                }
            ],
            target_rows=[
                {
                    "run_id": ORDINARY_1453_TARGET,
                    "status": "passed",
                    "source_market_data_run_id": ORDINARY_1453_SOURCE,
                    "trigger_state_row_count": 10,
                    "trigger_match_row_count": 4,
                    "trigger_event_outbox_count": 4,
                    "raw_json": {"previous_trigger_run_id": ORDINARY_0946_TARGET},
                },
                {
                    "run_id": ORDINARY_0946_TARGET,
                    "status": "passed",
                    "source_market_data_run_id": ORDINARY_0946_SOURCE,
                    "trigger_state_row_count": 5,
                    "trigger_match_row_count": 2,
                    "trigger_event_outbox_count": 2,
                    "raw_json": {"previous_trigger_run_id": ""},
                },
            ],
        )
        with patch.dict(
            sys.modules,
            {
                "psycopg": fake,
                "psycopg.rows": SimpleNamespace(dict_row="dict_row"),
            },
        ):
            exit_code, report = run_proof_discovery_poll(
                dsn="postgresql://unit-test",
                for_trade_date=FOR_TRADE_DATE,
                source_trade_date=SOURCE_TRADE_DATE,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                trigger_context_run_id=CONTEXT_RUN_ID,
                mode="ordinary",
                selection_mode="realtime_latest_only",
                execute=True,
                user_confirmed=True,
                command_runner=lambda argv: self.fail("exact target should noop before child execution"),
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["result"], "noop")
        self.assertEqual(report["selected"]["ordinary"], None)
        self.assertEqual(report["discovery_policy"], "ordinary_realtime_latest_fast_path_v1")
        self.assertEqual(report["skipped_candidates"][0]["reason"], "already_passed_exact_target")
        self.assertEqual(report["skipped_candidates"][0]["source_run_id"], ORDINARY_1453_SOURCE)
        self.assertEqual(report["child_execution"]["executed_child_command_count"], 0)
        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "ordinary_history.jsonl"
            append_poll_history(report, history_path=history_path)
            record = json.loads(history_path.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(record["discovery_policy"], "ordinary_realtime_latest_fast_path_v1")
        self.assertEqual(record["existing_target_skip"][0]["source_run_id"], ORDINARY_1453_SOURCE)

    def test_existing_target_audit_batches_downstream_ref_queries(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import _db_existing_targets

        fake = ExistingTargetAuditFakeCursor(target_count=100)

        targets = _db_existing_targets(fake, for_trade_date=FOR_TRADE_DATE)

        self.assertEqual(len(targets), 100)
        self.assertLessEqual(fake.count_queries("FROM common_trigger_state"), 3)
        self.assertLessEqual(fake.count_queries("FROM common_trigger_match"), 3)
        self.assertLessEqual(fake.count_queries("FROM common_event_outbox"), 4)
        self.assertLessEqual(fake.count_queries("FROM common_event_inbox"), 3)
        self.assertLessEqual(fake.count_queries("FROM common_event_consumer_checkpoint"), 3)

    def test_existing_target_audit_preserves_batched_downstream_ref_counts(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import _db_existing_targets

        run_id = "trigger_provisional_ordinary_20260701_until_0000__source"
        fake = ExistingTargetAuditFakeCursor(
            target_count=1,
            inbox_refs={run_id: 3},
            checkpoint_refs={run_id: 4},
            optional_refs={
                "common_action_run": {run_id: 5},
                "user_card_projection": {run_id: 6},
                "n6_virtual_order": {run_id: 7},
            },
        )

        target = _db_existing_targets(fake, for_trade_date=FOR_TRADE_DATE)[0]

        self.assertEqual(target["state_count"], 0)
        self.assertEqual(target["match_count"], 1)
        self.assertEqual(target["outbox_count"], 2)
        self.assertEqual(target["outbox_delivered_delivering"], 0)
        self.assertEqual(target["downstream_ref_count"], 25)

    def test_ordinary_wrapper_accepts_explicit_baseline_flags(self) -> None:
        args = build_ordinary_arg_parser().parse_args(
            [
                "--trigger-context-run-id",
                CONTEXT_RUN_ID,
                "--source-metric-run-id",
                ORDINARY_1453_SOURCE,
                "--trigger-run-id",
                ORDINARY_1453_TARGET,
                "--for-trade-date",
                FOR_TRADE_DATE,
                "--source-condition-run-id",
                SOURCE_CONDITION_RUN_ID,
                "--previous-trigger-run-id",
                ORDINARY_0946_TARGET,
                "--baseline-mode",
                "latest",
            ]
        )

        self.assertEqual(args.previous_trigger_run_id, ORDINARY_0946_TARGET)
        self.assertEqual(args.baseline_mode, "latest")

    def test_plan_selects_next_unprocessed_ordinary_and_hint_with_exact_baselines(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import build_proof_discovery_plan

        plan = build_proof_discovery_plan(
            for_trade_date=FOR_TRADE_DATE,
            source_trade_date=SOURCE_TRADE_DATE,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            trigger_context_run_id=CONTEXT_RUN_ID,
            mode="both",
            ordinary_candidates=[ordinary_candidate(ORDINARY_0946_SOURCE), ordinary_candidate(ORDINARY_1453_SOURCE)],
            hint_candidates=[hint_candidate(HINT_1044_SOURCE), hint_candidate(HINT_1454_SOURCE)],
            existing_targets=[
                passed_target(ORDINARY_0946_TARGET, source_run_id=ORDINARY_0946_SOURCE),
                passed_target(HINT_1044_TARGET, source_run_id=HINT_1044_SOURCE),
            ],
            python_executable=sys.executable,
        )

        self.assertEqual(plan["result"], "PLAN_ONLY_PASS")
        self.assertEqual(plan["selected"]["ordinary"]["source_run_id"], ORDINARY_1453_SOURCE)
        self.assertEqual(plan["selected"]["ordinary"]["target_run_id"], ORDINARY_1453_TARGET)
        self.assertEqual(plan["selected"]["ordinary"]["previous_trigger_run_id"], ORDINARY_0946_TARGET)
        self.assertEqual(plan["selected"]["hint"]["source_run_id"], HINT_1454_SOURCE)
        self.assertEqual(plan["selected"]["hint"]["target_run_id"], HINT_1454_TARGET)
        self.assertEqual(plan["selected"]["hint"]["previous_trigger_run_id"], HINT_1044_TARGET)
        self.assertIn("--previous-trigger-run-id", plan["selected"]["ordinary"]["child_argv_plan_only"])
        self.assertIn("--previous-trigger-run-id", plan["selected"]["hint"]["child_argv_plan_only"])
        self.assertNotIn("--execute", plan["selected"]["ordinary"]["child_argv_plan_only"])
        self.assertNotIn("--execute", plan["selected"]["hint"]["child_argv_plan_only"])
        self.assertIn("--execute", plan["selected"]["ordinary"]["child_argv_for_execute"])
        self.assertIn("--execute", plan["selected"]["hint"]["child_argv_for_execute"])

    def test_default_child_python_executable_is_absolute_python_311(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import build_proof_discovery_plan

        plan = build_proof_discovery_plan(
            for_trade_date=FOR_TRADE_DATE,
            source_trade_date=SOURCE_TRADE_DATE,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            trigger_context_run_id=CONTEXT_RUN_ID,
            mode="both",
            ordinary_candidates=[ordinary_candidate(ORDINARY_1453_SOURCE)],
            hint_candidates=[hint_candidate(HINT_1454_SOURCE)],
            existing_targets=[],
        )

        for family in ("ordinary", "hint"):
            self.assertEqual(plan["selected"][family]["child_argv_plan_only"][0], EXPECTED_PYTHON)
            self.assertEqual(plan["selected"][family]["child_argv_for_execute"][0], EXPECTED_PYTHON)
            self.assertNotEqual(plan["selected"][family]["child_argv_for_execute"][0], "python3")

    def test_realtime_latest_only_selects_latest_unprocessed_candidates_and_marks_older_manual_backlog(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import build_proof_discovery_plan

        plan = build_proof_discovery_plan(
            for_trade_date=FOR_TRADE_DATE,
            source_trade_date=SOURCE_TRADE_DATE,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            trigger_context_run_id=CONTEXT_RUN_ID,
            mode="both",
            ordinary_candidates=[
                ordinary_candidate(ORDINARY_0946_SOURCE),
                ordinary_candidate(ORDINARY_1412_SOURCE),
                ordinary_candidate(ORDINARY_1453_SOURCE),
            ],
            hint_candidates=[
                hint_candidate(HINT_1044_SOURCE),
                hint_candidate(HINT_1429_SOURCE),
                hint_candidate(HINT_1454_SOURCE),
            ],
            existing_targets=[
                passed_target(ORDINARY_0946_TARGET, source_run_id=ORDINARY_0946_SOURCE),
                passed_target(HINT_1044_TARGET, source_run_id=HINT_1044_SOURCE),
            ],
            python_executable=sys.executable,
        )

        self.assertEqual(plan["selection_mode"], "realtime_latest_only")
        self.assertEqual(plan["selection_policy"], "latest_unprocessed_only")
        self.assertEqual(plan["selected"]["ordinary"]["source_run_id"], ORDINARY_1453_SOURCE)
        self.assertEqual(plan["selected"]["ordinary"]["target_run_id"], ORDINARY_1453_TARGET)
        self.assertEqual(plan["selected"]["ordinary"]["previous_trigger_run_id"], ORDINARY_0946_TARGET)
        self.assertEqual(plan["selected"]["hint"]["source_run_id"], HINT_1454_SOURCE)
        self.assertEqual(plan["selected"]["hint"]["target_run_id"], HINT_1454_TARGET)
        self.assertEqual(plan["selected"]["hint"]["previous_trigger_run_id"], HINT_1044_TARGET)
        self.assertIn(ORDINARY_1453_TARGET, plan["selected"]["ordinary"]["child_argv_plan_only"])
        self.assertIn(HINT_1454_TARGET, plan["selected"]["hint"]["child_argv_plan_only"])
        skipped = {(item["family"], item["source_run_id"]): item["reason"] for item in plan["skipped_candidates"]}
        self.assertEqual(skipped[("ordinary", ORDINARY_0946_SOURCE)], "already_passed_exact_target")
        self.assertEqual(skipped[("hint", HINT_1044_SOURCE)], "already_passed_exact_target")
        self.assertEqual(skipped[("ordinary", ORDINARY_1412_SOURCE)], "backlog_requires_manual_catchup")
        self.assertEqual(skipped[("hint", HINT_1429_SOURCE)], "backlog_requires_manual_catchup")
        self.assertTrue(plan["backlog_requires_manual_catchup"])
        self.assertEqual(plan["backlog_candidate_count"], 2)
        self.assertIn(ORDINARY_1412_SOURCE, plan["backlog_candidate_run_ids"])
        self.assertIn(HINT_1429_SOURCE, plan["backlog_candidate_run_ids"])

    def test_realtime_latest_only_skips_older_exact_target_with_downstream_refs_without_blocking_latest(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import build_proof_discovery_plan

        plan = build_proof_discovery_plan(
            for_trade_date=FOR_TRADE_DATE,
            source_trade_date=SOURCE_TRADE_DATE,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            trigger_context_run_id=CONTEXT_RUN_ID,
            mode="ordinary",
            ordinary_candidates=[
                ordinary_candidate(ORDINARY_0946_SOURCE),
                ordinary_candidate(ORDINARY_1429_SOURCE),
                ordinary_candidate(ORDINARY_1453_SOURCE),
            ],
            hint_candidates=[],
            existing_targets=[
                passed_target(ORDINARY_0946_TARGET, source_run_id=ORDINARY_0946_SOURCE),
                passed_target(
                    ORDINARY_1429_TARGET,
                    source_run_id=ORDINARY_1429_SOURCE,
                    previous_trigger_run_id=ORDINARY_0946_TARGET,
                    downstream_ref_count=90,
                ),
            ],
            python_executable=sys.executable,
        )

        self.assertEqual(plan["selection_mode"], "realtime_latest_only")
        self.assertEqual(plan["selected"]["ordinary"]["source_run_id"], ORDINARY_1453_SOURCE)
        skipped = {(item["family"], item["source_run_id"]): item for item in plan["skipped_candidates"]}
        self.assertEqual(
            skipped[("ordinary", ORDINARY_1429_SOURCE)]["reason"],
            "already_passed_exact_backlog_target_with_downstream_refs",
        )
        self.assertEqual(skipped[("ordinary", ORDINARY_1429_SOURCE)]["downstream_ref_policy"], "ignored_for_realtime_backlog")

    def test_realtime_latest_only_blocks_older_exact_target_source_mismatch(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import ProofDiscoveryBlocked, build_proof_discovery_plan

        with self.assertRaises(ProofDiscoveryBlocked) as raised:
            build_proof_discovery_plan(
                for_trade_date=FOR_TRADE_DATE,
                source_trade_date=SOURCE_TRADE_DATE,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                trigger_context_run_id=CONTEXT_RUN_ID,
                mode="ordinary",
                ordinary_candidates=[
                    ordinary_candidate(ORDINARY_1429_SOURCE),
                    ordinary_candidate(ORDINARY_1453_SOURCE),
                ],
                hint_candidates=[],
                existing_targets=[
                    passed_target(
                        ORDINARY_1429_TARGET,
                        source_run_id=ORDINARY_1412_SOURCE,
                        downstream_ref_count=90,
                    ),
                ],
                python_executable=sys.executable,
            )

        self.assertIn("source mismatch", str(raised.exception))

    def test_realtime_latest_only_latest_candidate_contract_invalid_blocks_fail_closed(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import ProofDiscoveryBlocked, build_proof_discovery_plan

        with self.assertRaises(ProofDiscoveryBlocked) as raised:
            build_proof_discovery_plan(
                for_trade_date=FOR_TRADE_DATE,
                source_trade_date=SOURCE_TRADE_DATE,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                trigger_context_run_id=CONTEXT_RUN_ID,
                mode="ordinary",
                ordinary_candidates=[
                    ordinary_candidate(ORDINARY_1429_SOURCE),
                    ordinary_candidate(ORDINARY_1453_SOURCE, role="unexpected_role"),
                ],
                hint_candidates=[],
                existing_targets=[],
                python_executable=sys.executable,
            )

        self.assertIn("latest ordinary candidate contract invalid", str(raised.exception))

    def test_realtime_latest_only_does_not_select_older_backlog_after_latest_target_exists(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import build_proof_discovery_plan

        plan = build_proof_discovery_plan(
            for_trade_date=FOR_TRADE_DATE,
            source_trade_date=SOURCE_TRADE_DATE,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            trigger_context_run_id=CONTEXT_RUN_ID,
            mode="both",
            ordinary_candidates=[
                ordinary_candidate(ORDINARY_1412_SOURCE),
                ordinary_candidate(ORDINARY_1429_SOURCE),
                ordinary_candidate(ORDINARY_1500_SOURCE),
            ],
            hint_candidates=[
                hint_candidate(HINT_1429_SOURCE),
                hint_candidate(HINT_1454_SOURCE),
            ],
            existing_targets=[
                passed_target(ORDINARY_0946_TARGET, source_run_id=ORDINARY_0946_SOURCE),
                passed_target(ORDINARY_1500_TARGET, source_run_id=ORDINARY_1500_SOURCE),
                passed_target(HINT_1044_TARGET, source_run_id=HINT_1044_SOURCE),
                passed_target(HINT_1454_TARGET, source_run_id=HINT_1454_SOURCE),
            ],
            python_executable=sys.executable,
        )

        self.assertIsNone(plan["selected"]["ordinary"])
        self.assertIsNone(plan["selected"]["hint"])
        self.assertTrue(plan["backlog_requires_manual_catchup"])
        self.assertEqual(plan["backlog_candidate_count"], 3)
        self.assertEqual(
            set(plan["backlog_candidate_run_ids"]),
            {ORDINARY_1412_SOURCE, ORDINARY_1429_SOURCE, HINT_1429_SOURCE},
        )
        skipped = {(item["family"], item["source_run_id"]): item["reason"] for item in plan["skipped_candidates"]}
        self.assertEqual(skipped[("ordinary", ORDINARY_1412_SOURCE)], "backlog_requires_manual_catchup")
        self.assertEqual(skipped[("ordinary", ORDINARY_1429_SOURCE)], "backlog_requires_manual_catchup")
        self.assertEqual(skipped[("hint", HINT_1429_SOURCE)], "backlog_requires_manual_catchup")
        self.assertEqual(skipped[("ordinary", ORDINARY_1500_SOURCE)], "already_passed_exact_target")
        self.assertEqual(skipped[("hint", HINT_1454_SOURCE)], "already_passed_exact_target")

    def test_realtime_latest_only_skips_latest_exact_target_with_downstream_refs_as_noop(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import build_proof_discovery_plan

        plan = build_proof_discovery_plan(
            for_trade_date=FOR_TRADE_DATE,
            source_trade_date=SOURCE_TRADE_DATE,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            trigger_context_run_id=CONTEXT_RUN_ID,
            mode="ordinary",
            ordinary_candidates=[
                ordinary_candidate(ORDINARY_1429_SOURCE),
                ordinary_candidate(ORDINARY_1500_SOURCE),
            ],
            hint_candidates=[],
            existing_targets=[
                passed_target(ORDINARY_0946_TARGET, source_run_id=ORDINARY_0946_SOURCE),
                passed_target(
                    ORDINARY_1500_TARGET,
                    source_run_id=ORDINARY_1500_SOURCE,
                    previous_trigger_run_id=ORDINARY_0946_TARGET,
                    downstream_ref_count=8,
                ),
            ],
            python_executable=sys.executable,
        )

        self.assertIsNone(plan["selected"]["ordinary"])
        skipped = {(item["family"], item["source_run_id"]): item for item in plan["skipped_candidates"]}
        self.assertEqual(
            skipped[("ordinary", ORDINARY_1500_SOURCE)]["reason"],
            "already_passed_exact_target_with_downstream_refs",
        )
        self.assertEqual(skipped[("ordinary", ORDINARY_1500_SOURCE)]["downstream_ref_count"], "8")
        self.assertEqual(skipped[("ordinary", ORDINARY_1500_SOURCE)]["downstream_ref_policy"], "ignored_for_realtime_latest")

    def test_explicit_catchup_mode_can_select_latest_unprocessed_backlog(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import build_proof_discovery_plan

        plan = build_proof_discovery_plan(
            selection_mode="catchup_latest_unprocessed",
            for_trade_date=FOR_TRADE_DATE,
            source_trade_date=SOURCE_TRADE_DATE,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            trigger_context_run_id=CONTEXT_RUN_ID,
            mode="ordinary",
            ordinary_candidates=[
                ordinary_candidate(ORDINARY_1412_SOURCE),
                ordinary_candidate(ORDINARY_1429_SOURCE),
                ordinary_candidate(ORDINARY_1500_SOURCE),
            ],
            hint_candidates=[],
            existing_targets=[
                passed_target(ORDINARY_0946_TARGET, source_run_id=ORDINARY_0946_SOURCE),
                passed_target(ORDINARY_1500_TARGET, source_run_id=ORDINARY_1500_SOURCE),
            ],
            python_executable=sys.executable,
        )

        self.assertEqual(plan["selection_mode"], "catchup_latest_unprocessed")
        self.assertEqual(plan["selected"]["ordinary"]["source_run_id"], ORDINARY_1429_SOURCE)
        skipped = {(item["family"], item["source_run_id"]): item["reason"] for item in plan["skipped_candidates"]}
        self.assertEqual(skipped[("ordinary", ORDINARY_1412_SOURCE)], "backlog_older_than_selected_latest")
        self.assertEqual(skipped[("ordinary", ORDINARY_1500_SOURCE)], "already_passed_exact_target")

    def test_explicit_catchup_mode_blocks_exact_target_with_downstream_refs(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import ProofDiscoveryBlocked, build_proof_discovery_plan

        with self.assertRaises(ProofDiscoveryBlocked) as raised:
            build_proof_discovery_plan(
                selection_mode="catchup_latest_unprocessed",
                for_trade_date=FOR_TRADE_DATE,
                source_trade_date=SOURCE_TRADE_DATE,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                trigger_context_run_id=CONTEXT_RUN_ID,
                mode="ordinary",
                ordinary_candidates=[
                    ordinary_candidate(ORDINARY_1412_SOURCE),
                    ordinary_candidate(ORDINARY_1429_SOURCE),
                    ordinary_candidate(ORDINARY_1500_SOURCE),
                ],
                hint_candidates=[],
                existing_targets=[
                    passed_target(
                        ORDINARY_1429_TARGET,
                        source_run_id=ORDINARY_1429_SOURCE,
                        downstream_ref_count=1,
                    ),
                ],
                python_executable=sys.executable,
            )

        self.assertIn("downstream refs", str(raised.exception))

    def test_latest_selection_uses_run_id_descending_as_tie_breaker(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import build_proof_discovery_plan

        plan = build_proof_discovery_plan(
            for_trade_date=FOR_TRADE_DATE,
            source_trade_date=SOURCE_TRADE_DATE,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            trigger_context_run_id=CONTEXT_RUN_ID,
            mode="ordinary",
            ordinary_candidates=[ordinary_candidate(ORDINARY_1453_SOURCE), ordinary_candidate(ORDINARY_1453_SOURCE_V2)],
            hint_candidates=[],
            existing_targets=[],
            python_executable=sys.executable,
        )

        self.assertEqual(plan["selected"]["ordinary"]["source_run_id"], ORDINARY_1453_SOURCE_V2)
        skipped = {(item["family"], item["source_run_id"]): item["reason"] for item in plan["skipped_candidates"]}
        self.assertEqual(skipped[("ordinary", ORDINARY_1453_SOURCE)], "backlog_requires_manual_catchup")

    def test_first_same_day_candidates_use_no_previous_baseline_modes(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import build_proof_discovery_plan

        plan = build_proof_discovery_plan(
            for_trade_date=FOR_TRADE_DATE,
            source_trade_date=SOURCE_TRADE_DATE,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            trigger_context_run_id=CONTEXT_RUN_ID,
            mode="both",
            ordinary_candidates=[ordinary_candidate(ORDINARY_0946_SOURCE)],
            hint_candidates=[hint_candidate(HINT_1044_SOURCE)],
            existing_targets=[],
            python_executable=sys.executable,
        )

        ordinary_argv = plan["selected"]["ordinary"]["child_argv_plan_only"]
        hint_argv = plan["selected"]["hint"]["child_argv_plan_only"]
        self.assertIn("--baseline-mode", ordinary_argv)
        self.assertIn("no_previous_baseline", ordinary_argv)
        self.assertIn("--no-previous-baseline", hint_argv)
        self.assertEqual(plan["selected"]["ordinary"]["previous_trigger_run_id"], "")
        self.assertEqual(plan["selected"]["hint"]["previous_trigger_run_id"], "")

    def test_source_selection_filters_contract_scope_and_family(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import ProofDiscoveryBlocked, build_proof_discovery_plan

        with self.assertRaises(ProofDiscoveryBlocked) as raised:
            build_proof_discovery_plan(
                for_trade_date=FOR_TRADE_DATE,
                source_trade_date=SOURCE_TRADE_DATE,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                trigger_context_run_id=CONTEXT_RUN_ID,
                mode="both",
                ordinary_candidates=[
                    ordinary_candidate(ORDINARY_1453_SOURCE, role="not_trigger_proof"),
                    hint_candidate(HINT_1454_SOURCE),
                ],
                hint_candidates=[
                    hint_candidate(HINT_1454_SOURCE, stock_rows=1),
                    ordinary_candidate(ORDINARY_1453_SOURCE),
                ],
                existing_targets=[],
                python_executable=sys.executable,
            )

        self.assertIn("latest ordinary candidate contract invalid", str(raised.exception))

    def test_dirty_existing_target_blocks_instead_of_overwriting(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import ProofDiscoveryBlocked, build_proof_discovery_plan

        with self.assertRaises(ProofDiscoveryBlocked) as raised:
            build_proof_discovery_plan(
                for_trade_date=FOR_TRADE_DATE,
                source_trade_date=SOURCE_TRADE_DATE,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                trigger_context_run_id=CONTEXT_RUN_ID,
                mode="ordinary",
                ordinary_candidates=[ordinary_candidate(ORDINARY_1453_SOURCE)],
                hint_candidates=[],
                existing_targets=[
                    {
                        "run_id": ORDINARY_1453_TARGET,
                        "status": "failed",
                        "source_run_id": ORDINARY_1453_SOURCE,
                        "previous_trigger_run_id": "",
                        "outbox_delivered_delivering": 0,
                    }
                ],
                python_executable=sys.executable,
            )

        self.assertIn("dirty existing N4 target", str(raised.exception))

    def test_delivered_outbox_existing_target_blocks_overwrite_path(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import ProofDiscoveryBlocked, build_proof_discovery_plan

        with self.assertRaises(ProofDiscoveryBlocked) as raised:
            build_proof_discovery_plan(
                for_trade_date=FOR_TRADE_DATE,
                source_trade_date=SOURCE_TRADE_DATE,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                trigger_context_run_id=CONTEXT_RUN_ID,
                mode="ordinary",
                ordinary_candidates=[ordinary_candidate(ORDINARY_1453_SOURCE)],
                hint_candidates=[],
                existing_targets=[
                    {
                        "run_id": ORDINARY_1453_TARGET,
                        "status": "passed",
                        "source_run_id": ORDINARY_1453_SOURCE,
                        "previous_trigger_run_id": "",
                        "state_count": 1,
                        "match_count": 1,
                        "outbox_count": 1,
                        "outbox_delivered_delivering": 1,
                    }
                ],
                python_executable=sys.executable,
            )

        self.assertIn("delivered/delivering outbox refs", str(raised.exception))

    def test_idempotent_existing_target_requires_matching_counts_when_available(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import ProofDiscoveryBlocked, build_proof_discovery_plan

        with self.assertRaises(ProofDiscoveryBlocked) as raised:
            build_proof_discovery_plan(
                for_trade_date=FOR_TRADE_DATE,
                source_trade_date=SOURCE_TRADE_DATE,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                trigger_context_run_id=CONTEXT_RUN_ID,
                mode="ordinary",
                ordinary_candidates=[ordinary_candidate_with_expected_counts(ORDINARY_1453_SOURCE)],
                hint_candidates=[],
                existing_targets=[
                    passed_target(ORDINARY_1453_TARGET, source_run_id=ORDINARY_1453_SOURCE),
                ],
                python_executable=sys.executable,
            )

        self.assertIn("count mismatch", str(raised.exception))

    def test_existing_target_missing_legacy_baseline_metadata_can_skip_when_source_and_counts_match(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import build_proof_discovery_plan

        candidate = ordinary_candidate(ORDINARY_1453_SOURCE)
        candidate.update({"expected_state_count": 486, "expected_match_count": 225, "expected_outbox_count": 486})

        plan = build_proof_discovery_plan(
            for_trade_date=FOR_TRADE_DATE,
            source_trade_date=SOURCE_TRADE_DATE,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            trigger_context_run_id=CONTEXT_RUN_ID,
            mode="ordinary",
            ordinary_candidates=[ordinary_candidate(ORDINARY_0946_SOURCE), candidate],
            hint_candidates=[],
            existing_targets=[
                passed_target(ORDINARY_0946_TARGET, source_run_id=ORDINARY_0946_SOURCE),
                passed_target(
                    ORDINARY_1453_TARGET,
                    source_run_id=ORDINARY_1453_SOURCE,
                    previous_trigger_run_id="",
                    state_count=486,
                    match_count=225,
                    outbox_count=486,
                ),
            ],
            python_executable=sys.executable,
        )

        self.assertIsNone(plan["selected"]["ordinary"])
        skipped_by_source = {item["source_run_id"]: item for item in plan["skipped_candidates"]}
        skipped_1453 = skipped_by_source[ORDINARY_1453_SOURCE]
        self.assertEqual(skipped_1453["reason"], "already_passed_exact_target")
        self.assertEqual(skipped_1453["baseline_policy"], "baseline_metadata_compat_pass")
        self.assertEqual(
            skipped_1453["baseline_policy_compat_reason"],
            "missing_or_legacy_baseline_metadata_with_verified_exact_source_and_counts",
        )

    def test_existing_target_baseline_compat_still_blocks_wrong_source(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import ProofDiscoveryBlocked, build_proof_discovery_plan

        with self.assertRaises(ProofDiscoveryBlocked) as raised:
            build_proof_discovery_plan(
                for_trade_date=FOR_TRADE_DATE,
                source_trade_date=SOURCE_TRADE_DATE,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                trigger_context_run_id=CONTEXT_RUN_ID,
                mode="ordinary",
                ordinary_candidates=[ordinary_candidate(ORDINARY_0946_SOURCE), ordinary_candidate(ORDINARY_1453_SOURCE)],
                hint_candidates=[],
                existing_targets=[
                    passed_target(ORDINARY_0946_TARGET, source_run_id=ORDINARY_0946_SOURCE),
                    passed_target(
                        ORDINARY_1453_TARGET,
                        source_run_id=ORDINARY_1412_SOURCE,
                        previous_trigger_run_id="",
                    ),
                ],
                python_executable=sys.executable,
            )

        self.assertIn("source mismatch", str(raised.exception))

    def test_existing_target_baseline_compat_requires_internal_run_count_consistency(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import ProofDiscoveryBlocked, build_proof_discovery_plan

        with self.assertRaises(ProofDiscoveryBlocked) as raised:
            build_proof_discovery_plan(
                for_trade_date=FOR_TRADE_DATE,
                source_trade_date=SOURCE_TRADE_DATE,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                trigger_context_run_id=CONTEXT_RUN_ID,
                mode="ordinary",
                ordinary_candidates=[ordinary_candidate(ORDINARY_0946_SOURCE), ordinary_candidate(ORDINARY_1453_SOURCE)],
                hint_candidates=[],
                existing_targets=[
                    passed_target(ORDINARY_0946_TARGET, source_run_id=ORDINARY_0946_SOURCE),
                    passed_target(
                        ORDINARY_1453_TARGET,
                        source_run_id=ORDINARY_1453_SOURCE,
                        previous_trigger_run_id="",
                        state_count=486,
                        match_count=225,
                        outbox_count=486,
                        run_state_count=487,
                    ),
                ],
                python_executable=sys.executable,
            )

        self.assertIn("run count mismatch", str(raised.exception))

    def test_existing_target_baseline_compat_allows_realtime_latest_downstream_refs_noop(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import build_proof_discovery_plan

        plan = build_proof_discovery_plan(
            for_trade_date=FOR_TRADE_DATE,
            source_trade_date=SOURCE_TRADE_DATE,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            trigger_context_run_id=CONTEXT_RUN_ID,
            mode="ordinary",
            ordinary_candidates=[ordinary_candidate(ORDINARY_0946_SOURCE), ordinary_candidate(ORDINARY_1453_SOURCE)],
            hint_candidates=[],
            existing_targets=[
                passed_target(ORDINARY_0946_TARGET, source_run_id=ORDINARY_0946_SOURCE),
                passed_target(
                    ORDINARY_1453_TARGET,
                    source_run_id=ORDINARY_1453_SOURCE,
                    previous_trigger_run_id="",
                    downstream_ref_count=1,
                ),
            ],
            python_executable=sys.executable,
        )

        self.assertIsNone(plan["selected"]["ordinary"])
        skipped = {(item["family"], item["source_run_id"]): item for item in plan["skipped_candidates"]}
        self.assertEqual(
            skipped[("ordinary", ORDINARY_1453_SOURCE)]["reason"],
            "already_passed_exact_target_with_downstream_refs",
        )
        self.assertEqual(skipped[("ordinary", ORDINARY_1453_SOURCE)]["downstream_ref_policy"], "ignored_for_realtime_latest")

    def test_previous_baseline_selection_is_family_scoped(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import build_proof_discovery_plan

        plan = build_proof_discovery_plan(
            for_trade_date=FOR_TRADE_DATE,
            source_trade_date=SOURCE_TRADE_DATE,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            trigger_context_run_id=CONTEXT_RUN_ID,
            mode="both",
            ordinary_candidates=[ordinary_candidate(ORDINARY_1453_SOURCE)],
            hint_candidates=[hint_candidate(HINT_1454_SOURCE)],
            existing_targets=[
                passed_target(HINT_1044_TARGET, source_run_id=HINT_1044_SOURCE),
                passed_target(ORDINARY_0946_TARGET, source_run_id=ORDINARY_0946_SOURCE),
            ],
            python_executable=sys.executable,
        )

        self.assertEqual(plan["selected"]["ordinary"]["previous_trigger_run_id"], ORDINARY_0946_TARGET)
        self.assertEqual(plan["selected"]["hint"]["previous_trigger_run_id"], HINT_1044_TARGET)

    def test_plan_only_runner_executes_zero_children(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import run_proof_discovery_poll

        calls: list[list[str]] = []

        exit_code, report = run_proof_discovery_poll(
            for_trade_date=FOR_TRADE_DATE,
            source_trade_date=SOURCE_TRADE_DATE,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            trigger_context_run_id=CONTEXT_RUN_ID,
            mode="both",
            ordinary_candidates=[ordinary_candidate(ORDINARY_1453_SOURCE)],
            hint_candidates=[hint_candidate(HINT_1454_SOURCE)],
            existing_targets=[],
            python_executable=sys.executable,
            command_runner=lambda argv: calls.append(list(argv)),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["result"], "PLAN_ONLY_PASS")
        self.assertEqual(report["child_execution"]["executed_child_command_count"], 0)
        self.assertEqual(calls, [])
        self.assertFalse(report["side_effects"]["child_executed"])

    def test_execute_requires_user_confirmation_and_execute_flag_pair(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import run_proof_discovery_poll

        execute_only_code, execute_only_report = run_proof_discovery_poll(
            for_trade_date=FOR_TRADE_DATE,
            source_trade_date=SOURCE_TRADE_DATE,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            trigger_context_run_id=CONTEXT_RUN_ID,
            mode="ordinary",
            ordinary_candidates=[ordinary_candidate(ORDINARY_1453_SOURCE)],
            hint_candidates=[],
            existing_targets=[],
            execute=True,
            user_confirmed=False,
            python_executable=sys.executable,
            command_runner=lambda argv: self.fail("child runner must not be called"),
        )
        confirmed_only_code, confirmed_only_report = run_proof_discovery_poll(
            for_trade_date=FOR_TRADE_DATE,
            source_trade_date=SOURCE_TRADE_DATE,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            trigger_context_run_id=CONTEXT_RUN_ID,
            mode="ordinary",
            ordinary_candidates=[ordinary_candidate(ORDINARY_1453_SOURCE)],
            hint_candidates=[],
            existing_targets=[],
            execute=False,
            user_confirmed=True,
            python_executable=sys.executable,
            command_runner=lambda argv: self.fail("child runner must not be called"),
        )

        self.assertNotEqual(execute_only_code, 0)
        self.assertEqual(execute_only_report["result"], "blocked")
        self.assertIn("requires --user-confirmed", execute_only_report["error"])
        self.assertFalse(execute_only_report["side_effects"]["child_executed"])
        self.assertNotEqual(confirmed_only_code, 0)
        self.assertEqual(confirmed_only_report["result"], "blocked")
        self.assertIn("requires --execute", confirmed_only_report["error"])
        self.assertFalse(confirmed_only_report["side_effects"]["child_executed"])

    def test_execute_calls_hint_then_ordinary_children_in_order(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import run_proof_discovery_poll

        calls: list[list[str]] = []
        dsn = "postgresql://ashare_v3_user:secret@127.0.0.1:5432/ashare_v3"

        def runner(argv: list[str]) -> SimpleNamespace:
            calls.append(list(argv))
            return SimpleNamespace(returncode=0, stdout="ok", stderr="")

        exit_code, report = run_proof_discovery_poll(
            for_trade_date=FOR_TRADE_DATE,
            source_trade_date=SOURCE_TRADE_DATE,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            trigger_context_run_id=CONTEXT_RUN_ID,
            mode="both",
            ordinary_candidates=[ordinary_candidate(ORDINARY_0946_SOURCE), ordinary_candidate(ORDINARY_1453_SOURCE)],
            hint_candidates=[hint_candidate(HINT_1044_SOURCE), hint_candidate(HINT_1454_SOURCE)],
            existing_targets=[
                passed_target(ORDINARY_0946_TARGET, source_run_id=ORDINARY_0946_SOURCE),
                passed_target(HINT_1044_TARGET, source_run_id=HINT_1044_SOURCE),
            ],
            execute=True,
            user_confirmed=True,
            dsn=dsn,
            python_executable=sys.executable,
            command_runner=runner,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["result"], "passed")
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["selected_child_order_policy"], "hint_first_realtime_latency_v1")
        self.assertEqual(report["selected_child_order"], ["hint", "ordinary"])
        self.assertEqual(report["child_execution"]["executed_child_command_count"], 2)
        self.assertEqual(report["child_execution"]["selected_child_order_policy"], "hint_first_realtime_latency_v1")
        self.assertEqual(report["child_execution"]["selected_child_order"], ["hint", "ordinary"])
        self.assertEqual([child["family"] for child in report["child_execution"]["children"]], ["hint", "ordinary"])
        timing = report["timing"]
        self.assertGreaterEqual(timing["total_duration_ms"], 0)
        phase_names = [phase["phase_name"] for phase in timing["phases"]]
        self.assertIn("discovery", phase_names)
        self.assertIn("candidate_selection", phase_names)
        self.assertIn("hint_child_execution", phase_names)
        self.assertIn("ordinary_child_execution", phase_names)
        for child in report["child_execution"]["children"]:
            self.assertIn("child_started_at", child)
            self.assertIn("child_finished_at", child)
            self.assertGreaterEqual(child["child_duration_ms"], 0)
        self.assertIn("scripts/run_n4_provisional_projection_execute_once.py", calls[0])
        self.assertIn(HINT_1454_SOURCE, calls[0])
        self.assertIn(HINT_1044_TARGET, calls[0])
        self.assertIn("scripts/run_n4_provisional_ordinary_execute_once.py", calls[1])
        self.assertIn(ORDINARY_1453_SOURCE, calls[1])
        self.assertIn(ORDINARY_0946_TARGET, calls[1])
        self.assertIn("--dsn", calls[0])
        self.assertIn(dsn, calls[0])
        self.assertIn("--dsn", calls[1])
        self.assertIn(dsn, calls[1])
        self.assertTrue(report["side_effects"]["child_executed"])
        self.assertTrue(report["forbidden_operation_proof"]["child_executed"])
        report_blob = str(report)
        self.assertIn("postgresql://ashare_v3_user:***@127.0.0.1:5432/ashare_v3", report_blob)
        self.assertNotIn("secret", report_blob)

    def test_execute_uses_lineage_context_for_actual_child_argv(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import run_proof_discovery_poll

        source_run_id = (
            "realtime_action_confirmation_metric_20260702_until_0937__asset_all__"
            "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__"
            "market_data_subscription_20260702_condition_layer_20260701_source_20260701_for_20260702_v1"
        )
        expected_context_run_id = (
            "trigger_context_snapshot_20260702_condition_layer_20260701_source_20260701_for_20260702_v1__atomic_rule_v1"
        )
        calls: list[list[str]] = []

        with tempfile.TemporaryDirectory() as tmpdir:
            lineage_path = Path(tmpdir) / "current_intraday_worker_lineage.json"
            write_lineage_config(lineage_path)
            exit_code, report = run_proof_discovery_poll(
                for_trade_date="",
                source_trade_date="",
                source_condition_run_id="",
                trigger_context_run_id="",
                mode="ordinary",
                ordinary_candidates=[ordinary_candidate(source_run_id)],
                hint_candidates=[],
                existing_targets=[],
                execute=True,
                user_confirmed=True,
                python_executable=sys.executable,
                command_runner=lambda argv: calls.append(list(argv)) or {"returncode": 0, "stdout": "", "stderr": ""},
                lineage_config_path=str(lineage_path),
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["result"], "passed")
        self.assertEqual(report["trigger_context_run_id"], expected_context_run_id)
        self.assertEqual(calls[0][calls[0].index("--trigger-context-run-id") + 1], expected_context_run_id)
        self.assertEqual(
            report["child_execution"]["children"][0]["argv"][
                report["child_execution"]["children"][0]["argv"].index("--trigger-context-run-id") + 1
            ],
            expected_context_run_id,
        )

    def test_plan_only_redacts_dsn_in_child_argv_report(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import build_proof_discovery_plan

        dsn = "postgresql://ashare_v3_user:secret@127.0.0.1:5432/ashare_v3"

        plan = build_proof_discovery_plan(
            dsn=dsn,
            for_trade_date=FOR_TRADE_DATE,
            source_trade_date=SOURCE_TRADE_DATE,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            trigger_context_run_id=CONTEXT_RUN_ID,
            mode="both",
            ordinary_candidates=[ordinary_candidate(ORDINARY_1453_SOURCE)],
            hint_candidates=[hint_candidate(HINT_1454_SOURCE)],
            existing_targets=[],
            python_executable=sys.executable,
        )

        ordinary_argv = plan["selected"]["ordinary"]["child_argv_for_execute"]
        hint_argv = plan["selected"]["hint"]["child_argv_for_execute"]
        self.assertIn("--dsn", ordinary_argv)
        self.assertIn("--dsn", hint_argv)
        self.assertIn("postgresql://ashare_v3_user:***@127.0.0.1:5432/ashare_v3", ordinary_argv)
        self.assertIn("postgresql://ashare_v3_user:***@127.0.0.1:5432/ashare_v3", hint_argv)
        self.assertEqual(plan["dsn_redacted"], "postgresql://ashare_v3_user:***@127.0.0.1:5432/ashare_v3")
        self.assertNotIn("secret", str(plan))

    def test_execute_mode_scopes_to_requested_family(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import run_proof_discovery_poll

        ordinary_calls: list[list[str]] = []
        hint_calls: list[list[str]] = []

        ordinary_code, ordinary_report = run_proof_discovery_poll(
            for_trade_date=FOR_TRADE_DATE,
            source_trade_date=SOURCE_TRADE_DATE,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            trigger_context_run_id=CONTEXT_RUN_ID,
            mode="ordinary",
            ordinary_candidates=[ordinary_candidate(ORDINARY_1453_SOURCE)],
            hint_candidates=[hint_candidate(HINT_1454_SOURCE)],
            existing_targets=[],
            execute=True,
            user_confirmed=True,
            python_executable=sys.executable,
            command_runner=lambda argv: ordinary_calls.append(list(argv)) or {"returncode": 0, "stdout": "", "stderr": ""},
        )
        hint_code, hint_report = run_proof_discovery_poll(
            for_trade_date=FOR_TRADE_DATE,
            source_trade_date=SOURCE_TRADE_DATE,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            trigger_context_run_id=CONTEXT_RUN_ID,
            mode="hint",
            ordinary_candidates=[ordinary_candidate(ORDINARY_1453_SOURCE)],
            hint_candidates=[hint_candidate(HINT_1454_SOURCE)],
            existing_targets=[],
            execute=True,
            user_confirmed=True,
            python_executable=sys.executable,
            command_runner=lambda argv: hint_calls.append(list(argv)) or {"returncode": 0, "stdout": "", "stderr": ""},
        )

        self.assertEqual(ordinary_code, 0)
        self.assertEqual(ordinary_report["child_execution"]["executed_child_command_count"], 1)
        self.assertIn("scripts/run_n4_provisional_ordinary_execute_once.py", ordinary_calls[0])
        self.assertEqual(hint_code, 0)
        self.assertEqual(hint_report["child_execution"]["executed_child_command_count"], 1)
        self.assertIn("scripts/run_n4_provisional_projection_execute_once.py", hint_calls[0])

    def test_child_failure_stops_subsequent_child_and_returns_nonzero(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import run_proof_discovery_poll

        calls: list[list[str]] = []

        def runner(argv: list[str]) -> dict[str, object]:
            calls.append(list(argv))
            return {"returncode": 7, "stdout": "bad", "stderr": "failed"}

        exit_code, report = run_proof_discovery_poll(
            for_trade_date=FOR_TRADE_DATE,
            source_trade_date=SOURCE_TRADE_DATE,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            trigger_context_run_id=CONTEXT_RUN_ID,
            mode="both",
            ordinary_candidates=[ordinary_candidate(ORDINARY_1453_SOURCE)],
            hint_candidates=[hint_candidate(HINT_1454_SOURCE)],
            existing_targets=[],
            execute=True,
            user_confirmed=True,
            python_executable=sys.executable,
            command_runner=runner,
        )

        self.assertEqual(exit_code, 7)
        self.assertEqual(report["result"], "blocked")
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["selected_child_order_policy"], "hint_first_realtime_latency_v1")
        self.assertEqual(report["selected_child_order"], ["hint", "ordinary"])
        self.assertEqual(report["child_execution"]["executed_child_command_count"], 1)
        self.assertEqual(report["child_execution"]["selected_child_order_policy"], "hint_first_realtime_latency_v1")
        self.assertEqual(report["child_execution"]["selected_child_order"], ["hint", "ordinary"])
        self.assertEqual(report["child_execution"]["children"][0]["family"], "hint")
        self.assertTrue(report["child_execution"]["stopped_after_failure"])
        self.assertIn("timing", report)
        self.assertTrue(
            any(
                phase["phase_name"] == "hint_child_execution" and phase["status"] == "blocked"
                for phase in report["timing"]["phases"]
            )
        )
        self.assertEqual(len(calls), 1)
        self.assertIn("scripts/run_n4_provisional_projection_execute_once.py", calls[0])

    def test_execute_with_no_selected_candidates_is_noop(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import run_proof_discovery_poll

        exit_code, report = run_proof_discovery_poll(
            for_trade_date=FOR_TRADE_DATE,
            source_trade_date=SOURCE_TRADE_DATE,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            trigger_context_run_id=CONTEXT_RUN_ID,
            mode="both",
            ordinary_candidates=[],
            hint_candidates=[],
            existing_targets=[],
            execute=True,
            user_confirmed=True,
            python_executable=sys.executable,
            command_runner=lambda argv: self.fail("child runner must not be called"),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["result"], "noop")
        self.assertEqual(report["status"], "noop")
        self.assertEqual(report["child_execution"]["executed_child_command_count"], 0)
        timing = report["timing"]
        self.assertGreaterEqual(timing["total_duration_ms"], 0)
        phase_names = [phase["phase_name"] for phase in timing["phases"]]
        self.assertIn("discovery", phase_names)
        self.assertIn("candidate_selection", phase_names)
        self.assertIn("report_closeout", phase_names)
        self.assertFalse(report["side_effects"]["child_executed"])

    def test_hint_noop_appends_history_evidence(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import append_poll_history, run_proof_discovery_poll

        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "hint_history.jsonl"
            exit_code, report = run_proof_discovery_poll(
                for_trade_date=FOR_TRADE_DATE,
                source_trade_date=SOURCE_TRADE_DATE,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                trigger_context_run_id=CONTEXT_RUN_ID,
                mode="hint",
                ordinary_candidates=[],
                hint_candidates=[],
                existing_targets=[],
                execute=True,
                user_confirmed=True,
                python_executable=sys.executable,
                command_runner=lambda argv: self.fail("child runner must not be called"),
            )
            append_poll_history(report, report_path="tmp/N4_intraday_proof_discovery_poller_hint_launchd_report.json", history_path=history_path)

            self.assertEqual(exit_code, 0)
            records = [json.loads(line) for line in history_path.read_text().splitlines()]
            self.assertEqual(len(records), 1)
            record = records[0]
            self.assertEqual(record["mode"], "hint")
            self.assertEqual(record["result"], "noop")
            self.assertEqual(record["executed_child_command_count"], 0)
            self.assertEqual(record["no_candidate_reason"], "no_selected_candidate")
            self.assertEqual(record["report_path"], "tmp/N4_intraday_proof_discovery_poller_hint_launchd_report.json")
            self.assertIn("started_at", record)
            self.assertIn("finished_at", record)
            self.assertIn("duration_ms", record)

    def test_hint_selected_child_appends_history_with_run_id_and_child_result(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import append_poll_history, run_proof_discovery_poll

        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "hint_history.jsonl"
            exit_code, report = run_proof_discovery_poll(
                for_trade_date=FOR_TRADE_DATE,
                source_trade_date=SOURCE_TRADE_DATE,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                trigger_context_run_id=CONTEXT_RUN_ID,
                mode="hint",
                ordinary_candidates=[],
                hint_candidates=[hint_candidate(HINT_1454_SOURCE)],
                existing_targets=[],
                execute=True,
                user_confirmed=True,
                python_executable=sys.executable,
                command_runner=lambda argv: {"returncode": 0, "stdout": "ok", "stderr": ""},
            )
            append_poll_history(report, report_path="tmp/N4_intraday_proof_discovery_poller_hint_launchd_report.json", history_path=history_path)

            self.assertEqual(exit_code, 0)
            record = json.loads(history_path.read_text().splitlines()[0])
            self.assertEqual(record["mode"], "hint")
            self.assertEqual(record["selected_run_id"], HINT_1454_TARGET)
            self.assertEqual(record["selected_source_market_data_run_id"], HINT_1454_SOURCE)
            self.assertEqual(record["executed_child_command_count"], 1)
            self.assertEqual(record["children"][0]["family"], "hint")
            self.assertEqual(record["children"][0]["returncode"], 0)
            self.assertEqual(record["children"][0]["target_run_id"], HINT_1454_TARGET)

    def test_ordinary_history_path_is_separate_from_hint_history_path(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import poll_history_path_for_mode

        self.assertEqual(
            poll_history_path_for_mode("hint"),
            Path("tmp/N4_intraday_proof_discovery_poller_hint_history.jsonl"),
        )
        self.assertEqual(
            poll_history_path_for_mode("ordinary"),
            Path("tmp/N4_intraday_proof_discovery_poller_history.jsonl"),
        )

    def test_history_evidence_keeps_last_500_lines(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import append_poll_history, run_proof_discovery_poll

        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.jsonl"
            history_path.write_text("".join(json.dumps({"seq": i}) + "\n" for i in range(500)), encoding="utf-8")
            exit_code, report = run_proof_discovery_poll(
                for_trade_date=FOR_TRADE_DATE,
                source_trade_date=SOURCE_TRADE_DATE,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                trigger_context_run_id=CONTEXT_RUN_ID,
                mode="hint",
                ordinary_candidates=[],
                hint_candidates=[],
                existing_targets=[],
                execute=True,
                user_confirmed=True,
                python_executable=sys.executable,
                command_runner=lambda argv: self.fail("child runner must not be called"),
            )
            append_poll_history(report, history_path=history_path)

            self.assertEqual(exit_code, 0)
            records = [json.loads(line) for line in history_path.read_text().splitlines()]
            self.assertEqual(len(records), 500)
            self.assertEqual(records[0]["seq"], 1)
            self.assertEqual(records[-1]["mode"], "hint")

    def test_history_append_preserves_latest_report_payload(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import append_poll_history, run_proof_discovery_poll

        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.jsonl"
            exit_code, report = run_proof_discovery_poll(
                for_trade_date=FOR_TRADE_DATE,
                source_trade_date=SOURCE_TRADE_DATE,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                trigger_context_run_id=CONTEXT_RUN_ID,
                mode="hint",
                ordinary_candidates=[],
                hint_candidates=[],
                existing_targets=[],
                execute=True,
                user_confirmed=True,
                python_executable=sys.executable,
                command_runner=lambda argv: self.fail("child runner must not be called"),
            )
            before = json.dumps(report, sort_keys=True)
            append_poll_history(report, history_path=history_path)

            self.assertEqual(exit_code, 0)
            self.assertEqual(json.dumps(report, sort_keys=True), before)

    def test_forbidden_operations_are_absent_from_planned_child_argv(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import build_proof_discovery_plan

        plan = build_proof_discovery_plan(
            for_trade_date=FOR_TRADE_DATE,
            source_trade_date=SOURCE_TRADE_DATE,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            trigger_context_run_id=CONTEXT_RUN_ID,
            mode="both",
            ordinary_candidates=[ordinary_candidate(ORDINARY_1453_SOURCE)],
            hint_candidates=[hint_candidate(HINT_1454_SOURCE)],
            existing_targets=[],
            python_executable=sys.executable,
        )

        argv_blob = " ".join(
            " ".join(plan["selected"][family]["child_argv_for_execute"])
            for family in ("ordinary", "hint")
            if plan["selected"][family]
        ).lower()
        for token in ("n5", "n6", "consume", "checkpoint", "launchctl", "bootstrap", "rollback"):
            self.assertNotIn(token, argv_blob)
        self.assertEqual(
            plan["side_effects"],
            {
                "database_written": False,
                "child_executed": False,
                "outbox_consumed": False,
                "inbox_or_checkpoint_updated": False,
                "n5_n6_entered": False,
                "worker_or_launchd_touched": False,
                "rollback_executed": False,
                "schema_changed": False,
            },
        )

    def test_main_blocked_closeout_writes_report_and_stderr_without_name_error(self) -> None:
        from scripts.run_n4_intraday_proof_discovery_poll_once import main

        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "blocked_report.json"
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                exit_code = main(
                    [
                        "--for-trade-date",
                        FOR_TRADE_DATE,
                        "--source-trade-date",
                        SOURCE_TRADE_DATE,
                        "--source-condition-run-id",
                        SOURCE_CONDITION_RUN_ID,
                        "--trigger-context-run-id",
                        CONTEXT_RUN_ID,
                        "--json-report-path",
                        str(report_path),
                        "--user-confirmed",
                    ]
                )

            self.assertNotEqual(exit_code, 0)
            self.assertIn("BLOCKED:", stderr.getvalue())
            self.assertTrue(report_path.exists())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "blocked")
            self.assertEqual(report["result"], "blocked")
            self.assertEqual(report["child_execution"]["executed_child_command_count"], 0)
            self.assertFalse(report["side_effects"]["child_executed"])

    def test_ordinary_wrapper_passes_trigger_context_run_id_to_provider(self) -> None:
        from scripts.run_n4_provisional_ordinary_execute_once import main

        captured: dict[str, object] = {}

        def fake_run(**kwargs: object) -> dict[str, object]:
            captured.update(kwargs)
            return {"result": "PREFLIGHT_PASS", "trigger_run_id": ORDINARY_1453_TARGET}

        with patch("scripts.run_n4_provisional_ordinary_execute_once.run_provisional_ordinary_once", fake_run):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--trigger-context-run-id",
                        CONTEXT_RUN_ID,
                        "--source-metric-run-id",
                        ORDINARY_1453_SOURCE,
                        "--trigger-run-id",
                        ORDINARY_1453_TARGET,
                        "--for-trade-date",
                        FOR_TRADE_DATE,
                        "--source-condition-run-id",
                        SOURCE_CONDITION_RUN_ID,
                    ]
                )

        self.assertEqual(exit_code, 0)
        self.assertEqual(captured["trigger_context_run_id"], CONTEXT_RUN_ID)
        self.assertEqual(captured["source_metric_run_id"], ORDINARY_1453_SOURCE)
        self.assertEqual(captured["trigger_run_id"], ORDINARY_1453_TARGET)


class FakePsycopgModule:
    def __init__(self, market_runs: list[dict[str, object]], target_rows: list[dict[str, object]] | None = None) -> None:
        self.cursor = FakeCursor(market_runs, target_rows=target_rows)

    def connect(self, *args: object, **kwargs: object) -> "FakeConnection":
        return FakeConnection(self.cursor)


class FakeConnection:
    def __init__(self, cursor: "FakeCursor") -> None:
        self._cursor = cursor

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def execute(self, sql: str) -> None:
        self._cursor.connection_sql.append(sql)

    def cursor(self) -> "FakeCursor":
        return self._cursor


class FakeCursor:
    def __init__(self, market_runs: list[dict[str, object]], target_rows: list[dict[str, object]] | None = None) -> None:
        self.market_runs = market_runs
        self.target_rows = target_rows or []
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.connection_sql: list[str] = []
        self._fetchall: list[dict[str, object]] = []
        self._fetchone: dict[str, object] = {}

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> None:
        self.executed.append((sql, params))
        if "FROM common_market_data_run" in sql:
            rows = list(self.market_runs)
            if "run_id LIKE %s" in sql and "OR run_id LIKE %s" not in sql:
                like_value = str(params[2]) if len(params) > 2 else ""
                if like_value.startswith("realtime_hint_projection_metric_"):
                    rows = [row for row in rows if str(row.get("run_id") or "").startswith("realtime_hint_projection_metric_")]
                elif like_value.startswith("realtime_action_confirmation_metric_"):
                    rows = [row for row in rows if str(row.get("run_id") or "").startswith("realtime_action_confirmation_metric_")]
            if "ORDER BY run_id DESC" in sql:
                rows.sort(key=lambda row: str(row.get("run_id") or ""), reverse=True)
            if "LIMIT 1" in sql:
                rows = rows[:1]
            self._fetchall = rows
            return
        if "FROM stock_action_confirmation_projection_metric" in sql:
            self._fetchone = self._contract_counts(10)
            return
        if "FROM index_action_confirmation_projection_metric" in sql:
            self._fetchone = self._contract_counts(0)
            return
        if "FROM board_action_confirmation_projection_metric" in sql:
            self._fetchone = self._contract_counts(0)
            return
        if "FROM index_realtime_hint_projection_metric" in sql:
            self._fetchone = self._contract_counts(0)
            return
        if "FROM board_realtime_hint_projection_metric" in sql:
            self._fetchone = self._contract_counts(6)
            return
        if "FROM common_trigger_run" in sql:
            if "run_id = ANY" in sql:
                requested = set(params[0]) if params else set()
                self._fetchall = [{"j": row} for row in self.target_rows if row.get("run_id") in requested]
                return
            if "run_id < %s" in sql:
                before_run_id = str(params[2]) if len(params) > 2 else ""
                like_pattern = str(params[1]) if len(params) > 1 else ""
                prefix = "trigger_provisional_b2_"
                if like_pattern.startswith("trigger_provisional_ordinary_"):
                    prefix = "trigger_provisional_ordinary_"
                previous = [
                    row
                    for row in self.target_rows
                    if str(row.get("run_id") or "").startswith(f"{prefix}{FOR_TRADE_DATE}_until_")
                    and str(row.get("run_id") or "") < before_run_id
                ]
                previous.sort(key=lambda row: str(row.get("run_id") or ""), reverse=True)
                self._fetchone = {"j": previous[0]} if previous else {}
                return
            self._fetchall = [{"j": row} for row in self.target_rows]
            return
        if "FROM common_trigger_state" in sql and "GROUP BY" in sql:
            self._fetchall = [
                {"run_id": str(row["run_id"]), "count": int(row.get("trigger_state_row_count") or 0)}
                for row in self.target_rows
            ]
            return
        if "FROM common_trigger_match" in sql and "GROUP BY" in sql:
            self._fetchall = [
                {"run_id": str(row["run_id"]), "count": int(row.get("trigger_match_row_count") or 0)}
                for row in self.target_rows
            ]
            return
        if "FROM common_event_outbox" in sql and "GROUP BY" in sql:
            self._fetchall = [
                {
                    "source_run_id": str(row["run_id"]),
                    "outbox_count": int(row.get("trigger_event_outbox_count") or 0),
                    "outbox_delivered_delivering": 0,
                }
                for row in self.target_rows
            ]
            return
        if "FROM common_event_inbox" in sql and "GROUP BY" in sql:
            self._fetchall = []
            return
        if "FROM common_event_consumer_checkpoint" in sql and "GROUP BY" in sql:
            self._fetchall = []
            return
        if "SELECT to_regclass" in sql:
            self._fetchone = {"regclass": None}
            return
        self._fetchone = {"count": 0}

    def fetchall(self) -> list[dict[str, object]]:
        return self._fetchall

    def fetchone(self) -> dict[str, object]:
        return self._fetchone

    def count_queries(self, needle: str) -> int:
        return sum(1 for sql, _params in self.executed if needle in sql)

    @staticmethod
    def _contract_counts(row_count: int) -> dict[str, int]:
        return {
            "row_count": row_count,
            "metric_role": row_count,
            "proof_owner": row_count,
            "proof_consumer": row_count,
            "not_n5_final_proof": row_count,
        }


class ExistingTargetAuditFakeCursor:
    def __init__(
        self,
        *,
        target_count: int,
        inbox_refs: dict[str, int] | None = None,
        checkpoint_refs: dict[str, int] | None = None,
        optional_refs: dict[str, dict[str, int]] | None = None,
    ) -> None:
        self.target_count = target_count
        self.inbox_refs = inbox_refs or {}
        self.checkpoint_refs = checkpoint_refs or {}
        self.optional_refs = optional_refs or {}
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self._fetchall: list[dict[str, object]] = []
        self._fetchone: dict[str, object] = {}

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> None:
        self.executed.append((sql, params))
        if "FROM common_trigger_run r" in sql:
            self._fetchall = [
                {
                    "j": {
                        "run_id": f"trigger_provisional_ordinary_20260701_until_{i:04d}__source",
                        "status": "passed",
                        "source_market_data_run_id": f"source_{i}",
                        "trigger_state_row_count": i,
                        "trigger_match_row_count": i + 1,
                        "trigger_event_outbox_count": i + 2,
                        "raw_json": {"previous_trigger_run_id": f"previous_{i}"},
                    }
                }
                for i in range(self.target_count)
            ]
            return
        if "GROUP BY" in sql and "FROM common_trigger_state" in sql:
            self._fetchall = [
                {"run_id": f"trigger_provisional_ordinary_20260701_until_{i:04d}__source", "count": i}
                for i in range(self.target_count)
            ]
            return
        if "GROUP BY" in sql and "FROM common_trigger_match" in sql:
            self._fetchall = [
                {"run_id": f"trigger_provisional_ordinary_20260701_until_{i:04d}__source", "count": i + 1}
                for i in range(self.target_count)
            ]
            return
        if "GROUP BY" in sql and "FROM common_event_outbox" in sql:
            self._fetchall = [
                {
                    "source_run_id": f"trigger_provisional_ordinary_20260701_until_{i:04d}__source",
                    "outbox_count": i + 2,
                    "outbox_delivered_delivering": 0,
                }
                for i in range(self.target_count)
            ]
            return
        if "GROUP BY" in sql and "FROM common_event_inbox" in sql:
            self._fetchall = [
                {"source_run_id": run_id, "count": count}
                for run_id, count in self.inbox_refs.items()
            ]
            return
        if "GROUP BY" in sql and "FROM common_event_consumer_checkpoint" in sql:
            self._fetchall = [
                {"source_run_id": run_id, "count": count}
                for run_id, count in self.checkpoint_refs.items()
            ]
            return
        if "SELECT to_regclass" in sql:
            table_name = str(params[0]) if params else ""
            self._fetchone = {"regclass": table_name if table_name in self.optional_refs else None}
            return
        if "information_schema.columns" in sql:
            table_name = str(params[0]) if params else ""
            self._fetchone = {"has_column": table_name in self.optional_refs}
            return
        for table_name, refs in self.optional_refs.items():
            if f"FROM {table_name}" in sql and "source_trigger_run_id" in sql:
                self._fetchall = [
                    {"source_trigger_run_id": run_id, "count": count}
                    for run_id, count in refs.items()
                ]
                return
        self._fetchone = {"count": 0}

    def fetchall(self) -> list[dict[str, object]]:
        return self._fetchall

    def fetchone(self) -> dict[str, object]:
        return self._fetchone

    def count_queries(self, needle: str) -> int:
        return sum(1 for sql, _params in self.executed if needle in sql)


if __name__ == "__main__":
    unittest.main()
