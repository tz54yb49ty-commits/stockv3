import argparse
import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ashare_v3.trigger.rule_v4_execute import V4TriggerExecuteBlocked
from run_n4_20260605_v4_corrected_execute_once import (
    assert_artifacts_ready,
    assert_corrected_execute_confirmed,
    build_arg_parser,
    build_corrected_write_plan_from_report,
    run_execute,
)


def _plan(identity_key: str = "stock:SH:600000") -> dict:
    return {
        "output_event_type": "TriggerMatched",
        "plan_id": f"plan:{identity_key}",
        "source_event_id": f"source:{identity_key}",
        "source_event_type": "MarketSnapshotUpdated",
        "source_snapshot_run_id": "snapshot_run",
        "asset_kind": "stock",
        "identity_key": identity_key,
        "direction": "buy",
        "signal_type": "B_BUY",
        "condition_key": "BUY:Y,Q,M,W,D",
        "original_condition_key": "BUY:Y,Q,M,W,D",
        "trigger_price": "10.00",
        "trigger_time": "2026-06-05T11:06:00+08:00",
        "source_confirmed_time": "2026-06-05T11:06:00+08:00",
        "trigger_kind": "trigger",
        "triggered_periods": ["D"],
        "all_trigger_periods": ["D"],
        "primary_trigger_period": "D",
        "n5_entry_allowed": True,
        "trigger_live": True,
        "current_status": "matched",
        "data_quality_status": "passed",
        "match_basis": "realtime_snapshot",
        "trigger_mark_candidate": "normal",
        "projection_30m_flag": False,
        "projection_30m_type": "none",
        "trigger_period": "D",
        "trigger_bucket": "trading_day",
        "snapshot_trace": {
            "snapshot_id": 1,
            "snapshot_time": "2026-06-05T11:06:00+08:00",
            "current_price": "10.00",
            "quality_status": "passed",
        },
    }


def _dry_run(
    plans: list[dict],
    *,
    candidate_count: int | None = None,
    compliant_count: int | None = None,
    blocked_count: int = 297,
) -> dict:
    candidate = len(plans) if candidate_count is None else candidate_count
    compliant = len(plans) if compliant_count is None else compliant_count
    return {
        "result": "DRY_RUN_PASS",
        "execute_run_id": "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
        "trigger_context_run_id": "trigger_context_snapshot_20260605_condition_layer_20260604_source_20260604_v1",
        "snapshot_run_id": "realtime_snapshot_20260605_live2_market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1",
        "projection_run_id": "projection_run",
        "candidate_plans_before_strict_guard": candidate,
        "persisted_plans_after_strict_guard": compliant,
        "compliant_count": compliant,
        "blocked_count": blocked_count,
        "blocked_counts_by_reason": {
            "missing trigger_price": 275,
            "missing triggered_periods": 275,
            "FULL forbidden": 29 if blocked_count == 297 else 23,
            "invalid N5 entry": 0,
        },
        "n5_entry_eligibility_proof": {"invalid_n5_entry_count": 0},
        "compliant_trigger_matched_sample": plans,
        "quality": {"p0_count": 0, "p1_count": 1, "p2_count": 0},
    }


def _contract(
    planned: int,
    *,
    candidate_count: int | None = None,
    blocked_count: int = 297,
) -> dict:
    candidate = planned if candidate_count is None else candidate_count
    return {
        "result": "CONTRACT_PASS",
        "execute_run_id": "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
        "trigger_context_run_id": "trigger_context_snapshot_20260605_condition_layer_20260604_source_20260604_v1",
        "snapshot_run_id": "realtime_snapshot_20260605_live2_market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1",
        "corrected_dry_run_baseline": {
            "candidate_plans_before_strict_guard": candidate,
            "persisted_plans_after_strict_guard": planned,
            "blocked_count": blocked_count,
            "invalid_n5_entry_count": 0,
        },
        "planned_writes": {
            "common_trigger_run": 1,
            "common_trigger_quality_item": 4,
            "common_trigger_state": planned,
            "common_trigger_match": planned,
            "common_event_outbox": planned,
            "TriggerMatched": planned,
            "TriggerPendingMarketData": 0,
            "TriggerStateChanged": 0,
        },
        "blocked_candidates": {
            "total": blocked_count,
            "by_reason": {
                "missing trigger_price": 275,
                "missing triggered_periods": 275,
                "FULL forbidden": 29 if blocked_count == 297 else 23,
                "invalid N5 entry": 0,
            },
        },
    }


def _preflight(
    planned: int,
    *,
    candidate_count: int | None = None,
    blocked_count: int = 297,
) -> dict:
    data = _contract(planned, candidate_count=candidate_count, blocked_count=blocked_count)
    data.update(
        {
            "result": "PREFLIGHT_PASS",
            "quality": {"p0_count": 0, "p1_count": 1, "p2_count": 0},
            "runner_readiness": {"ready": True},
            "baseline_refs": {
                "common_trigger_run": 0,
                "common_trigger_quality_item": 0,
                "common_trigger_state": 0,
                "common_trigger_match": 0,
                "common_event_outbox": 0,
                "common_event_inbox": 0,
                "common_event_consumer_checkpoint": 0,
                "n5_refs": 0,
                "n6_refs": 0,
            },
        }
    )
    return data


class N420260605V4CorrectedExecuteRunnerTests(unittest.TestCase):
    def test_missing_execute_flag_blocks_before_db_write(self) -> None:
        with self.assertRaises(V4TriggerExecuteBlocked) as ctx:
            assert_corrected_execute_confirmed(execute=False, user_confirmed=True)

        self.assertIn("--execute", str(ctx.exception))

    def test_missing_user_confirmed_flag_blocks_before_db_write(self) -> None:
        with self.assertRaises(V4TriggerExecuteBlocked) as ctx:
            assert_corrected_execute_confirmed(execute=True, user_confirmed=False)

        self.assertIn("--user-confirmed", str(ctx.exception))

    def test_cli_accepts_required_corrected_execute_arguments(self) -> None:
        args = build_arg_parser().parse_args(
            [
                "--execute-run-id",
                "run",
                "--dry-run-json-path",
                "dry.json",
                "--contract-path",
                "contract.json",
                "--preflight-path",
                "preflight.json",
                "--rollback-sql-path",
                "rollback.sql",
            ]
        )

        self.assertEqual(args.execute_run_id, "run")
        self.assertEqual(args.dry_run_json_path, "dry.json")
        self.assertEqual(args.preflight_path, "preflight.json")

    def test_runner_source_does_not_use_old_outbox_consuming_projection_route(self) -> None:
        source = Path("scripts/run_n4_20260605_v4_corrected_execute_once.py").read_text()

        self.assertNotIn("projection_matcher_execute", source)
        self.assertNotIn("run_projection_matcher_once", source)

    def test_artifact_guard_requires_matching_counts_and_preflight_pass(self) -> None:
        args = argparse.Namespace(
            execute_run_id="trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
        )

        assert_artifacts_ready(dry_run=_dry_run([_plan()]), contract=_contract(1), preflight=_preflight(1), args=args)
        with self.assertRaises(V4TriggerExecuteBlocked):
            assert_artifacts_ready(dry_run=_dry_run([_plan()]), contract=_contract(2), preflight=_preflight(2), args=args)

    def test_artifact_guard_accepts_old_297_count_when_contract_matches(self) -> None:
        args = argparse.Namespace(
            execute_run_id="trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
        )

        assert_artifacts_ready(
            dry_run=_dry_run([], candidate_count=1537, compliant_count=1240, blocked_count=297),
            contract=_contract(1240, candidate_count=1537, blocked_count=297),
            preflight=_preflight(1240, candidate_count=1537, blocked_count=297),
            args=args,
        )

    def test_artifact_guard_accepts_repaired_291_count_when_contract_matches(self) -> None:
        args = argparse.Namespace(
            execute_run_id="trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
        )

        assert_artifacts_ready(
            dry_run=_dry_run([], candidate_count=896, compliant_count=605, blocked_count=291),
            contract=_contract(605, candidate_count=896, blocked_count=291),
            preflight=_preflight(605, candidate_count=896, blocked_count=291),
            args=args,
        )

    def test_actual_old_297_artifacts_pass_contract_driven_guard(self) -> None:
        args = argparse.Namespace(
            execute_run_id="trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
        )

        assert_artifacts_ready(
            dry_run=json.loads(Path("docs/N4_20260605_V4_CORRECTED_DRY_RUN.json").read_text()),
            contract=json.loads(Path("docs/N4_20260605_V4_CORRECTED_EXECUTE_CONTRACT.json").read_text()),
            preflight=json.loads(Path("docs/N4_20260605_V4_CORRECTED_EXECUTE_PREFLIGHT.json").read_text()),
            args=args,
        )

    def test_actual_repaired_291_artifacts_pass_contract_driven_guard(self) -> None:
        args = argparse.Namespace(
            execute_run_id="trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
        )

        assert_artifacts_ready(
            dry_run=json.loads(Path("docs/N4_20260605_V4_REPAIRED_CONTEXT_CORRECTED_DRY_RUN.json").read_text()),
            contract=json.loads(Path("docs/N4_20260605_V4_REPAIRED_CONTEXT_CORRECTED_EXECUTE_CONTRACT.json").read_text()),
            preflight=json.loads(Path("docs/N4_20260605_V4_REPAIRED_CONTEXT_CORRECTED_EXECUTE_PREFLIGHT.json").read_text()),
            args=args,
        )

    def test_artifact_guard_blocks_when_blocked_count_differs_from_contract(self) -> None:
        args = argparse.Namespace(
            execute_run_id="trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
        )

        with self.assertRaises(V4TriggerExecuteBlocked) as ctx:
            assert_artifacts_ready(
                dry_run=_dry_run([], candidate_count=896, compliant_count=605, blocked_count=291),
                contract=_contract(605, candidate_count=896, blocked_count=297),
                preflight=_preflight(605, candidate_count=896, blocked_count=297),
                args=args,
            )

        self.assertIn("blocked_count", str(ctx.exception))

    def test_artifact_guard_blocks_when_preflight_blocked_count_differs_from_contract(self) -> None:
        args = argparse.Namespace(
            execute_run_id="trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
        )

        with self.assertRaises(V4TriggerExecuteBlocked) as ctx:
            assert_artifacts_ready(
                dry_run=_dry_run([], candidate_count=896, compliant_count=605, blocked_count=291),
                contract=_contract(605, candidate_count=896, blocked_count=291),
                preflight=_preflight(605, candidate_count=896, blocked_count=292),
                args=args,
            )

        self.assertIn("blocked_count", str(ctx.exception))

    def test_artifact_guard_blocks_when_candidate_count_differs_from_contract(self) -> None:
        args = argparse.Namespace(
            execute_run_id="trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
        )

        with self.assertRaises(V4TriggerExecuteBlocked) as ctx:
            assert_artifacts_ready(
                dry_run=_dry_run([], candidate_count=897, compliant_count=605, blocked_count=291),
                contract=_contract(605, candidate_count=896, blocked_count=291),
                preflight=_preflight(605, candidate_count=896, blocked_count=291),
                args=args,
            )

        self.assertIn("candidate", str(ctx.exception))

    def test_write_plan_contains_only_v4_compliant_trigger_matched(self) -> None:
        plans = [_plan("stock:SH:600000"), _plan("stock:SH:600004")]
        write_plan = build_corrected_write_plan_from_report(
            _dry_run(plans),
            execute_run_id="trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
        )

        self.assertEqual(write_plan["write_counts"]["TriggerMatched"], 2)
        self.assertEqual(write_plan["write_counts"]["TriggerPendingMarketData"], 0)
        self.assertEqual(write_plan["write_counts"]["TriggerStateChanged"], 0)
        self.assertEqual(write_plan["invalid_n5_entry_count"], 0)

    @patch("run_n4_20260605_v4_corrected_execute_once.execute_v4_matched_only_transaction")
    @patch("run_n4_20260605_v4_corrected_execute_once.capture_post_review_refs")
    @patch("run_n4_20260605_v4_corrected_execute_once.fetch_snapshot_rows")
    @patch("run_n4_20260605_v4_corrected_execute_once.fetch_context_rows")
    @patch("run_n4_20260605_v4_corrected_execute_once.recompute_corrected_dry_run_report")
    @patch("run_n4_20260605_v4_corrected_execute_once.capture_execute_guard_refs")
    @patch("run_n4_20260605_v4_corrected_execute_once.load_json")
    def test_run_execute_writes_only_corrected_scope_with_mocked_db_writer(
        self,
        load_json: Mock,
        capture_refs: Mock,
        recompute: Mock,
        fetch_context: Mock,
        fetch_snapshot: Mock,
        capture_post_refs: Mock,
        execute_tx: Mock,
    ) -> None:
        dry_run = _dry_run([_plan()])
        load_json.side_effect = [dry_run, _contract(1), _preflight(1)]
        capture_refs.return_value = {
            "common_trigger_run": 0,
            "common_trigger_quality_item": 0,
            "common_trigger_state": 0,
            "common_trigger_match": 0,
            "common_event_outbox": 0,
            "common_event_outbox_delivered_or_delivering": 0,
            "common_event_inbox": 0,
            "common_event_consumer_checkpoint": 0,
            "n5_refs": 0,
            "n6_refs": 0,
        }
        recompute.return_value = dry_run
        fetch_context.return_value = ({"run_id": "ctx", "source_condition_run_id": "condition", "for_trade_date": "20260605"}, [])
        fetch_snapshot.return_value = ({"run_id": "snapshot"}, [])
        capture_post_refs.return_value = {
            "outbox_pending": 1,
            "outbox_delivered": 0,
            "outbox_delivering": 0,
            "inbox_refs": 0,
            "checkpoint_refs": 0,
            "n5_refs": 0,
            "n6_refs": 0,
        }
        execute_tx.return_value = {
            "common_trigger_run": 1,
            "common_trigger_quality_item": 4,
            "common_trigger_state": 1,
            "common_trigger_match": 1,
            "common_event_outbox": 1,
            "TriggerMatched": 1,
            "TriggerPendingMarketData": 0,
            "TriggerStateChanged": 0,
        }

        report = run_execute(
            argparse.Namespace(
                dsn="dsn",
                execute_run_id="trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
                dry_run_json_path="dry.json",
                contract_path="contract.json",
                preflight_path="preflight.json",
                rollback_sql_path="rollback.sql",
            )
        )

        self.assertEqual(report["result"], "EXECUTE_PASS")
        self.assertEqual(report["actual_rows"]["TriggerMatched"], 1)
        self.assertEqual(report["post_review_checks"]["strict_required_field_compliance"], "1/1")
        self.assertFalse(report["boundary_proof"]["common_event_inbox_written"])
        self.assertFalse(report["boundary_proof"]["checkpoint_written"])
        self.assertFalse(report["boundary_proof"]["n5_n6_entered"])
        execute_tx.assert_called_once()


if __name__ == "__main__":
    unittest.main()
