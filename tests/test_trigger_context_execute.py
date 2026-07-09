import unittest
import inspect
import sys
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from ashare_v3.trigger.context_execute import (
    N3_GUARD_TABLES,
    N4_FORBIDDEN_WRITE_TABLES,
    attach_market_subscription_trace_to_rows,
    build_post_execute_checks,
    build_execute_quality_items,
    build_trigger_context_rollback_sql,
    build_trigger_context_run_id,
    canonical_context_allowed_signal_types,
    fetch_context_summary,
    insert_trigger_run,
)
from ashare_v3.trigger.context_preflight import build_context_materialization_run_id
from ashare_v3.trigger.schema_review import REQUIRED_TRIGGER_TABLES
from run_trigger_context_snapshot_execute import (
    TriggerContextExecuteBlocked,
    assert_context_execute_confirmed,
    build_arg_parser,
    main as trigger_context_execute_main,
)


class TriggerContextExecuteTest(unittest.TestCase):
    def test_context_execute_runner_help_exposes_manual_confirmation_flags(self) -> None:
        help_text = build_arg_parser().format_help()

        self.assertIn("--execute", help_text)
        self.assertIn("--user-confirmed", help_text)
        self.assertIn("--allow-existing-context-for-trade-date", help_text)

    def test_context_execute_runner_blocks_without_execute_before_db_write(self) -> None:
        with self.assertRaises(TriggerContextExecuteBlocked) as ctx:
            assert_context_execute_confirmed(execute=False, user_confirmed=True)

        self.assertIn("--execute", str(ctx.exception))

    def test_context_execute_runner_blocks_without_user_confirmed_before_db_write(self) -> None:
        with self.assertRaises(TriggerContextExecuteBlocked) as ctx:
            assert_context_execute_confirmed(execute=True, user_confirmed=False)

        self.assertIn("--user-confirmed", str(ctx.exception))

    @patch("run_trigger_context_snapshot_execute.run_trigger_context_snapshot_execute")
    def test_context_execute_runner_does_not_call_writer_when_execute_flag_missing(self, writer) -> None:
        exit_code = trigger_context_execute_main(
            [
                "--condition-run-id",
                "condition_layer_test",
                "--for-trade-date",
                "20260608",
                "--json-report-path",
                "docs/test_context_guard.json",
                "--markdown-report-path",
                "docs/test_context_guard.md",
                "--rollback-sql-path",
                "sql/test_context_guard_rollback.sql",
                "--user-confirmed",
            ]
        )

        self.assertEqual(exit_code, 2)
        writer.assert_not_called()

    @patch("run_trigger_context_snapshot_execute.run_trigger_context_snapshot_execute")
    def test_context_execute_runner_does_not_call_writer_when_user_confirmed_flag_missing(self, writer) -> None:
        exit_code = trigger_context_execute_main(
            [
                "--condition-run-id",
                "condition_layer_test",
                "--for-trade-date",
                "20260608",
                "--json-report-path",
                "docs/test_context_guard.json",
                "--markdown-report-path",
                "docs/test_context_guard.md",
                "--rollback-sql-path",
                "sql/test_context_guard_rollback.sql",
                "--execute",
            ]
        )

        self.assertEqual(exit_code, 2)
        writer.assert_not_called()

    @patch("run_trigger_context_snapshot_execute.run_trigger_context_snapshot_execute")
    def test_context_execute_runner_preserves_existing_arguments_when_confirmed(self, writer) -> None:
        writer.return_value = {
            "stage": "N4-3",
            "layer_role": "N4_trigger",
            "run_id": "trigger_context_snapshot_test",
            "source_condition_run_id": "condition_layer_test",
            "for_trade_date": "20260608",
            "rollback_sql_path": "sql/test_context_guard_rollback.sql",
            "quality": {"p0_count": 0, "p1_count": 0, "p2_count": 0},
            "post_context_summary": {
                "row_count": 0,
                "row_count_by_asset_kind": {},
                "direction_distribution": {},
                "buy_hint_row_count": 0,
                "sell_hint_row_count": 0,
            },
        }

        exit_code = trigger_context_execute_main(
            [
                "--condition-run-id",
                "condition_layer_test",
                "--for-trade-date",
                "20260608",
                "--json-report-path",
                "docs/test_context_guard.json",
                "--markdown-report-path",
                "docs/test_context_guard.md",
                "--rollback-sql-path",
                "sql/test_context_guard_rollback.sql",
                "--execute",
                "--user-confirmed",
            ]
        )

        self.assertEqual(exit_code, 0)
        writer.assert_called_once()
        _, kwargs = writer.call_args
        self.assertEqual(kwargs["condition_run_id"], "condition_layer_test")
        self.assertEqual(kwargs["for_trade_date"], "20260608")
        self.assertEqual(kwargs["json_report_path"], "docs/test_context_guard.json")
        self.assertEqual(kwargs["markdown_report_path"], "docs/test_context_guard.md")
        self.assertEqual(kwargs["rollback_sql_path"], "sql/test_context_guard_rollback.sql")
        self.assertFalse(kwargs["allow_existing_context_for_trade_date"])

    @patch("run_trigger_context_snapshot_execute.run_trigger_context_snapshot_execute")
    def test_context_execute_runner_passes_explicit_existing_context_override(self, writer) -> None:
        writer.return_value = {
            "stage": "N4-3",
            "layer_role": "N4_trigger",
            "run_id": "trigger_context_snapshot_test_v4",
            "source_condition_run_id": "condition_layer_test_v4",
            "for_trade_date": "20260616",
            "rollback_sql_path": "sql/test_context_guard_rollback.sql",
            "quality": {"p0_count": 0, "p1_count": 0, "p2_count": 0},
            "post_context_summary": {
                "row_count": 0,
                "row_count_by_asset_kind": {},
                "direction_distribution": {},
                "buy_hint_row_count": 0,
                "sell_hint_row_count": 0,
            },
        }

        exit_code = trigger_context_execute_main(
            [
                "--condition-run-id",
                "condition_layer_test_v4",
                "--for-trade-date",
                "20260616",
                "--json-report-path",
                "docs/test_context_guard.json",
                "--markdown-report-path",
                "docs/test_context_guard.md",
                "--rollback-sql-path",
                "sql/test_context_guard_rollback.sql",
                "--allow-existing-context-for-trade-date",
                "--execute",
                "--user-confirmed",
            ]
        )

        self.assertEqual(exit_code, 0)
        _, kwargs = writer.call_args
        self.assertTrue(kwargs["allow_existing_context_for_trade_date"])

    def test_canonical_context_allowed_signal_types_maps_n2_buy_to_atomic_context_candidate(self) -> None:
        self.assertEqual(
            canonical_context_allowed_signal_types(["BUY"], direction="buy", condition_key="BUY:Y,D"),
            ["B_BUY"],
        )
        self.assertEqual(
            canonical_context_allowed_signal_types(["BUY:FULL"], direction="buy", condition_key="BUY:FULL"),
            ["B_BUY"],
        )

    def test_canonical_context_allowed_signal_types_maps_n2_sell_to_atomic_context_candidate(self) -> None:
        self.assertEqual(
            canonical_context_allowed_signal_types(["SELL"], direction="sell", condition_key="SELL:Y"),
            ["S_SELL"],
        )
        self.assertEqual(
            canonical_context_allowed_signal_types(["SELL:FULL"], direction="sell", condition_key="SELL:FULL"),
            ["S_SELL"],
        )

    def test_canonical_context_allowed_signal_types_normalizes_deprecated_30m_labels_to_runtime_direction(self) -> None:
        self.assertEqual(
            canonical_context_allowed_signal_types(["B_BUY_30M_VOL"], direction="buy", condition_key="BUY:D"),
            ["B_BUY"],
        )
        self.assertEqual(
            canonical_context_allowed_signal_types(["S_SELL_30M_SHRINK"], direction="sell", condition_key="SELL:D"),
            ["S_SELL"],
        )

    def test_canonical_context_allowed_signal_types_preserves_hint_candidates(self) -> None:
        self.assertEqual(
            canonical_context_allowed_signal_types(["BUY_HINT"], direction="buy", condition_key="BUY_HINT"),
            ["BUY_HINT"],
        )
        self.assertEqual(
            canonical_context_allowed_signal_types(["SELL_HINT"], direction="sell", condition_key="SELL_HINT"),
            ["SELL_HINT"],
        )

    def test_run_id_is_deterministic_for_atomic_condition_context(self) -> None:
        run_id = build_trigger_context_run_id(
            {
                "for_trade_date": "20260626",
                "source_condition_run_id": "condition_layer_20260625_source_20260625_for_20260626_v1",
            }
        )

        self.assertEqual(
            run_id,
            "trigger_context_snapshot_20260626_condition_layer_20260625_source_20260625_for_20260626_v1__atomic_rule_v1",
        )

    def test_preflight_and_execute_context_run_id_builders_match_atomic_contract(self) -> None:
        active_run = {
            "for_trade_date": "20260626",
            "run_id": "condition_layer_20260625_source_20260625_for_20260626_v1",
        }
        preflight = {
            "for_trade_date": "20260626",
            "source_condition_run_id": "condition_layer_20260625_source_20260625_for_20260626_v1",
        }

        self.assertEqual(build_context_materialization_run_id(active_run), build_trigger_context_run_id(preflight))

    def test_trigger_run_raw_json_registers_atomic_rule_spec_and_boundaries(self) -> None:
        class RecordingCursor:
            def __init__(self) -> None:
                self.params = None

            def execute(self, _sql, params) -> None:
                self.params = params

        cur = RecordingCursor()
        insert_trigger_run(
            cur,
            run_id="trigger_context_snapshot_20260626_condition_layer_20260625_source_20260625_for_20260626_v1__atomic_rule_v1",
            preflight={
                "source_condition_run_id": "condition_layer_20260625_source_20260625_for_20260626_v1",
                "for_trade_date": "20260626",
                "source_trade_date": "20260625",
                "prev_trade_date": "20260625",
                "candidate_context_row_count": 2165,
            },
            severity_counts={"P0": 0, "P1": 0, "P2": 0},
            context_row_count=2165,
        )

        raw_json = cur.params["raw_json"].obj
        self.assertEqual(raw_json["rule_spec_path"], "docs/N4_TRIGGER_RULE_SPEC_ATOMIC_REVISED.md")
        self.assertEqual(raw_json["rule_spec_version"], "atomic_rule_v1")
        self.assertEqual(raw_json["context_contract_version"], "n4_trigger_context_snapshot.atomic_rule_v1")
        self.assertFalse(raw_json["writes_outbox"])
        self.assertFalse(raw_json["downstream_layers_touched"])
        self.assertFalse(raw_json["worker_started"])
        self.assertFalse(raw_json["boundary"]["event_outbox_written"])
        self.assertFalse(raw_json["boundary"]["trigger_state_written"])
        self.assertFalse(raw_json["boundary"]["trigger_match_written"])

    def test_rollback_sql_only_deletes_n4_context_rows(self) -> None:
        rollback = build_trigger_context_rollback_sql("trigger_context_snapshot_test")

        self.assertIn("DELETE FROM common_trigger_quality_item", rollback)
        self.assertIn("DELETE FROM stock_trigger_context_snapshot", rollback)
        self.assertIn("DELETE FROM common_trigger_run", rollback)
        self.assertIn("common_event_inbox", rollback)
        self.assertIn("common_event_consumer_checkpoint", rollback)
        self.assertIn("common_action_run", rollback)
        self.assertIn("common_action_event", rollback)
        self.assertIn("user_projection_run", rollback)
        self.assertIn("user_signal_projection", rollback)
        self.assertIn("user_signal_card", rollback)
        self.assertIn("user_notification_queue", rollback)
        self.assertIn("user_sim_order", rollback)
        self.assertIn("user_sim_position", rollback)
        self.assertIn("user_sim_trade", rollback)
        self.assertIn("allow_n4_context_rollback_run_id", rollback)
        self.assertLess(
            rollback.lower().find("raise exception"),
            rollback.lower().find("delete from"),
        )
        self.assertIn("WHERE (source_layer = 'N4_trigger' AND source_run_id = v_run_id)", rollback)
        self.assertIn("status IN ('delivered', 'delivering')", rollback)
        self.assertLess(
            rollback.find("status IN ('delivered', 'delivering')"),
            rollback.find("DELETE FROM"),
        )
        self.assertNotIn("DELETE FROM common_event_outbox", rollback)
        self.assertNotIn("DELETE FROM common_condition_run", rollback)

    def test_fetch_context_summary_selects_source_trade_date_for_required_period_post_check(self) -> None:
        source = inspect.getsource(fetch_context_summary)

        self.assertIn("source_trade_date", source)

    def test_post_checks_pass_for_expected_context_write_only(self) -> None:
        preflight = sample_preflight()
        before = sample_snapshot()
        after = sample_snapshot()
        after["row_counts"]["common_trigger_run"]["row_count"] = 1
        after["row_counts"]["common_trigger_quality_item"]["row_count"] = 5
        after["row_counts"]["stock_trigger_context_snapshot"]["row_count"] = 2
        after["row_counts"]["index_trigger_context_snapshot"]["row_count"] = 1
        inserted = {
            "common_trigger_run": 1,
            "common_trigger_quality_item": 5,
            "stock_trigger_context_snapshot": 2,
            "index_trigger_context_snapshot": 1,
            "board_trigger_context_snapshot": 0,
            "common_trigger_state": 0,
            "common_trigger_match": 0,
            "common_event_outbox": 0,
            "context_snapshot_total": 3,
        }
        summary = {
            "row_count": 3,
            "row_count_by_asset_kind": {"stock": 2, "index": 1, "board": 0},
            "direction_distribution": {"buy": 2, "sell": 1},
            "condition_key_counts": {"BUY_HINT": 1, "SELL_HINT": 1, "BUY:Y,Q,M,W,D": 1},
            "buy_hint_row_count": 1,
            "sell_hint_row_count": 1,
            "source_condition_run_ids": ["condition_layer_20260522_to_20260525_test_execute"],
            "trigger_run": {
                "run_id": "trigger_context_snapshot_test",
                "status": "passed",
                "trigger_state_row_count": 0,
                "trigger_match_row_count": 0,
                "trigger_event_outbox_count": 0,
            },
        }

        checks = build_post_execute_checks(
            preflight=preflight,
            before_snapshot=before,
            after_snapshot=after,
            inserted_counts=inserted,
            post_context_summary=summary,
            run_id="trigger_context_snapshot_test",
            condition_run_id="condition_layer_20260522_to_20260525_test_execute",
        )

        self.assertTrue(all(checks.values()), checks)

    def test_post_checks_accept_buy_hint_only_when_counts_match_preflight(self) -> None:
        preflight = {
            **sample_preflight(),
            "direction_distribution": {"buy": 3},
            "condition_key_counts": {"BUY_HINT": 2, "BUY:Y,Q,M,W,D": 1},
            "buy_hint_row_count": 2,
            "sell_hint_row_count": 0,
        }
        before = sample_snapshot()
        after = sample_snapshot()
        after["row_counts"]["common_trigger_run"]["row_count"] = 1
        after["row_counts"]["common_trigger_quality_item"]["row_count"] = 5
        after["row_counts"]["stock_trigger_context_snapshot"]["row_count"] = 2
        after["row_counts"]["index_trigger_context_snapshot"]["row_count"] = 1
        inserted = sample_inserted_counts()
        summary = {
            "row_count": 3,
            "row_count_by_asset_kind": {"stock": 2, "index": 1, "board": 0},
            "direction_distribution": {"buy": 3},
            "condition_key_counts": {"BUY_HINT": 2, "BUY:Y,Q,M,W,D": 1},
            "buy_hint_row_count": 2,
            "sell_hint_row_count": 0,
            "source_condition_run_ids": ["condition_layer_20260522_to_20260525_test_execute"],
            "trigger_run": sample_trigger_run(),
        }

        checks = build_post_execute_checks(
            preflight=preflight,
            before_snapshot=before,
            after_snapshot=after,
            inserted_counts=inserted,
            post_context_summary=summary,
            run_id="trigger_context_snapshot_test",
            condition_run_id="condition_layer_20260522_to_20260525_test_execute",
        )

        self.assertTrue(checks["buy_hint_and_sell_hint_present"], checks)

    def test_post_checks_accept_sell_hint_only_when_counts_match_preflight(self) -> None:
        preflight = {
            **sample_preflight(),
            "direction_distribution": {"sell": 3},
            "condition_key_counts": {"SELL_HINT": 2, "SELL:Y,Q,M,W,D": 1},
            "buy_hint_row_count": 0,
            "sell_hint_row_count": 2,
        }
        before = sample_snapshot()
        after = sample_snapshot()
        after["row_counts"]["common_trigger_run"]["row_count"] = 1
        after["row_counts"]["common_trigger_quality_item"]["row_count"] = 5
        after["row_counts"]["stock_trigger_context_snapshot"]["row_count"] = 2
        after["row_counts"]["index_trigger_context_snapshot"]["row_count"] = 1
        inserted = sample_inserted_counts()
        summary = {
            "row_count": 3,
            "row_count_by_asset_kind": {"stock": 2, "index": 1, "board": 0},
            "direction_distribution": {"sell": 3},
            "condition_key_counts": {"SELL_HINT": 2, "SELL:Y,Q,M,W,D": 1},
            "buy_hint_row_count": 0,
            "sell_hint_row_count": 2,
            "source_condition_run_ids": ["condition_layer_20260522_to_20260525_test_execute"],
            "trigger_run": sample_trigger_run(),
        }

        checks = build_post_execute_checks(
            preflight=preflight,
            before_snapshot=before,
            after_snapshot=after,
            inserted_counts=inserted,
            post_context_summary=summary,
            run_id="trigger_context_snapshot_test",
            condition_run_id="condition_layer_20260522_to_20260525_test_execute",
        )

        self.assertTrue(checks["buy_hint_and_sell_hint_present"], checks)

    def test_post_checks_fail_when_hint_counts_do_not_match_preflight(self) -> None:
        preflight = sample_preflight()
        before = sample_snapshot()
        after = sample_snapshot()
        after["row_counts"]["common_trigger_run"]["row_count"] = 1
        after["row_counts"]["common_trigger_quality_item"]["row_count"] = 5
        after["row_counts"]["stock_trigger_context_snapshot"]["row_count"] = 2
        after["row_counts"]["index_trigger_context_snapshot"]["row_count"] = 1
        inserted = sample_inserted_counts()
        summary = {
            "row_count": 3,
            "row_count_by_asset_kind": {"stock": 2, "index": 1, "board": 0},
            "direction_distribution": {"buy": 2, "sell": 1},
            "condition_key_counts": {"BUY_HINT": 1, "SELL_HINT": 1, "BUY:Y,Q,M,W,D": 1},
            "buy_hint_row_count": 1,
            "sell_hint_row_count": 0,
            "source_condition_run_ids": ["condition_layer_20260522_to_20260525_test_execute"],
            "trigger_run": sample_trigger_run(),
        }

        checks = build_post_execute_checks(
            preflight=preflight,
            before_snapshot=before,
            after_snapshot=after,
            inserted_counts=inserted,
            post_context_summary=summary,
            run_id="trigger_context_snapshot_test",
            condition_run_id="condition_layer_20260522_to_20260525_test_execute",
        )

        self.assertFalse(checks["buy_hint_and_sell_hint_present"])

    def test_post_checks_fail_when_outbox_changes(self) -> None:
        preflight = sample_preflight()
        before = sample_snapshot()
        after = sample_snapshot()
        after["row_counts"]["common_trigger_run"]["row_count"] = 1
        after["row_counts"]["common_trigger_quality_item"]["row_count"] = 5
        after["row_counts"]["stock_trigger_context_snapshot"]["row_count"] = 2
        after["row_counts"]["index_trigger_context_snapshot"]["row_count"] = 1
        after["row_counts"]["common_event_outbox"]["row_count"] = 1
        inserted = {
            "common_trigger_run": 1,
            "common_trigger_quality_item": 5,
            "stock_trigger_context_snapshot": 2,
            "index_trigger_context_snapshot": 1,
            "board_trigger_context_snapshot": 0,
            "common_trigger_state": 0,
            "common_trigger_match": 0,
            "common_event_outbox": 0,
            "context_snapshot_total": 3,
        }
        summary = {
            "row_count": 3,
            "row_count_by_asset_kind": {"stock": 2, "index": 1, "board": 0},
            "direction_distribution": {"buy": 2, "sell": 1},
            "condition_key_counts": {"BUY_HINT": 1, "SELL_HINT": 1, "BUY:Y,Q,M,W,D": 1},
            "buy_hint_row_count": 1,
            "sell_hint_row_count": 1,
            "source_condition_run_ids": ["condition_layer_20260522_to_20260525_test_execute"],
            "trigger_run": {
                "run_id": "trigger_context_snapshot_test",
                "status": "passed",
                "trigger_state_row_count": 0,
                "trigger_match_row_count": 0,
                "trigger_event_outbox_count": 0,
            },
        }

        checks = build_post_execute_checks(
            preflight=preflight,
            before_snapshot=before,
            after_snapshot=after,
            inserted_counts=inserted,
            post_context_summary=summary,
            run_id="trigger_context_snapshot_test",
            condition_run_id="condition_layer_20260522_to_20260525_test_execute",
        )

        self.assertFalse(checks["trigger_state_match_outbox_unchanged"])
        self.assertFalse(checks["n3_facts_and_outbox_unchanged"])

    def test_market_subscription_trace_attaches_realtime_subscription_to_context_rows(self) -> None:
        rows, summary = attach_market_subscription_trace_to_rows(
            context_rows=[
                {
                    "asset_kind": "stock",
                    "identity_key": "stock:SH:600000",
                    "direction": "buy",
                    "condition_key": "BUY:D",
                }
            ],
            subscriptions=[
                {
                    "subscription_id": 2,
                    "asset_kind": "stock",
                    "identity_key": "stock:SH:600000",
                    "required_data_kind": "minute_bar_1m",
                },
                {
                    "subscription_id": 1,
                    "asset_kind": "stock",
                    "identity_key": "stock:SH:600000",
                    "required_data_kind": "realtime_daily_snapshot",
                },
            ],
            market_data_run_id="market_data_subscription_test",
        )

        self.assertEqual(rows[0]["source_market_subscription_id"], 1)
        self.assertEqual(summary["traced_context_row_count"], 1)
        self.assertEqual(summary["untraced_context_row_count"], 0)

    def test_execute_quality_requires_market_data_run_lineage_when_provided(self) -> None:
        items = build_execute_quality_items(
            preflight={
                **sample_preflight(),
                "candidate_context_row_count": 1,
                "source_condition_run_id": "condition_layer_new",
                "quality": {"items": []},
            },
            context_rows=[{"source_market_subscription_id": 1}],
            expected_condition_run_id="condition_layer_new",
            market_data_run_id="market_data_subscription_new",
            market_data_run_summary={
                "run_id": "market_data_subscription_new",
                "status": "passed",
                "source_condition_run_id": "condition_layer_new",
            },
            market_trace_summary={"untraced_context_row_count": 0},
        )

        failed = [item for item in items if item["status"] == "failed"]
        self.assertEqual(failed, [])

    def test_execute_quality_accepts_distinct_snapshot_and_subscription_runs(self) -> None:
        items = build_execute_quality_items(
            preflight={
                **sample_preflight(),
                "candidate_context_row_count": 1,
                "source_condition_run_id": "condition_layer_new",
                "quality": {"items": []},
            },
            context_rows=[{"source_market_subscription_id": 1}],
            expected_condition_run_id="condition_layer_new",
            market_data_run_id="realtime_snapshot_new",
            market_data_run_summary={
                "run_id": "realtime_snapshot_new",
                "status": "passed",
                "source_condition_run_id": "condition_layer_new",
            },
            market_subscription_run_id="market_data_subscription_new",
            market_subscription_run_summary={
                "run_id": "market_data_subscription_new",
                "status": "passed",
                "source_condition_run_id": "condition_layer_new",
            },
            market_trace_summary={"untraced_context_row_count": 0},
        )

        failed = [item for item in items if item["status"] == "failed"]
        self.assertEqual(failed, [])


def sample_preflight() -> dict[str, object]:
    return {
        "candidate_context_row_count": 3,
        "condition_row_count_by_asset_kind": {"stock": 2, "index": 1, "board": 0},
        "direction_distribution": {"buy": 2, "sell": 1},
        "condition_key_counts": {"BUY_HINT": 1, "SELL_HINT": 1, "BUY:Y,Q,M,W,D": 1},
        "buy_hint_row_count": 1,
        "sell_hint_row_count": 1,
    }


def sample_inserted_counts() -> dict[str, int]:
    return {
        "common_trigger_run": 1,
        "common_trigger_quality_item": 5,
        "stock_trigger_context_snapshot": 2,
        "index_trigger_context_snapshot": 1,
        "board_trigger_context_snapshot": 0,
        "common_trigger_state": 0,
        "common_trigger_match": 0,
        "common_event_outbox": 0,
        "context_snapshot_total": 3,
    }


def sample_trigger_run() -> dict[str, object]:
    return {
        "run_id": "trigger_context_snapshot_test",
        "status": "passed",
        "trigger_state_row_count": 0,
        "trigger_match_row_count": 0,
        "trigger_event_outbox_count": 0,
    }


def sample_snapshot() -> dict[str, object]:
    row_counts = {
        table_name: {"exists": True, "row_count": 0, "status": "present"}
        for table_name in set(REQUIRED_TRIGGER_TABLES + N4_FORBIDDEN_WRITE_TABLES + N3_GUARD_TABLES)
    }
    row_counts["common_condition_run"] = {"exists": True, "row_count": 1, "status": "present"}
    return {
        "row_counts": row_counts,
        "condition_run_snapshot": {
            "run_id": "condition_layer_20260522_to_20260525_test_execute",
            "status": "passed",
        },
    }


if __name__ == "__main__":
    unittest.main()
