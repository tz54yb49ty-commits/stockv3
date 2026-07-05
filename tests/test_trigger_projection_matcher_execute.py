import inspect
import json
import tempfile
import unittest

import ashare_v3.trigger.projection_matcher_execute as projection_matcher_execute
from ashare_v3.trigger.projection_matcher_execute import (
    CURRENT_V4_CORRECTED_FORBIDDEN_EXECUTE_RUN_IDS,
    DEFAULT_CONSUMER_NAME,
    DEFAULT_EXECUTE_RUN_ID,
    DEFAULT_SNAPSHOT_RUN_ID,
    LEGACY_PROJECTION_MATCHER_ROUTE_METADATA,
    ProjectionMatcherExecuteError,
    assert_execute_confirmed,
    assert_legacy_projection_route_allowed,
    build_checkpoint_write_plan,
    build_execute_contract,
    build_preflight_quality_items,
    build_output_dedup_key,
    build_output_event_envelope,
    build_projection_matcher_execute_plan,
    build_projection_matcher_rollback_sql,
    load_dry_run_alignment,
    run_projection_matcher_execute_preflight,
    to_jsonable,
)


CONTEXT_RUN_ID = "trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525102249_execute"
PROJECTION_RUN_ID = (
    "realtime_projection_metric_20260525__realtime_daily_snapshot_20260525__"
    "market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute"
)
SYNTHETIC_DENYLIST = (
    "trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524014029_execute",
    "trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525003855_execute",
)


class TriggerProjectionMatcherExecuteTest(unittest.TestCase):
    def test_legacy_route_exposes_deprecation_and_selection_fence_metadata(self) -> None:
        metadata = LEGACY_PROJECTION_MATCHER_ROUTE_METADATA

        self.assertTrue(metadata["deprecated"])
        self.assertEqual(metadata["route_name"], "legacy_outbox_consuming_projection_matcher_execute")
        self.assertEqual(metadata["source_module"], "src/ashare_v3/trigger/projection_matcher_execute.py")
        self.assertIn("trigger_execute_20260605_condition_layer_20260604_source_20260604_v1", metadata["forbidden_execute_run_ids"])
        self.assertFalse(metadata["allowed_for_current_v4_corrected_flow"])
        self.assertFalse(metadata["allowed_for_20260605_n4_execute_gate"])
        self.assertFalse(metadata["n5_entry_source_for_current_chain"])

    def test_legacy_route_blocks_20260605_corrected_execute_run_id_before_write(self) -> None:
        self.assertIn(
            "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
            CURRENT_V4_CORRECTED_FORBIDDEN_EXECUTE_RUN_IDS,
        )

        with self.assertRaisesRegex(ProjectionMatcherExecuteError, "deprecated legacy projection matcher route"):
            assert_legacy_projection_route_allowed(
                execute_run_id="trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
            )

    def test_legacy_route_preflight_blocks_20260605_corrected_execute_run_id_before_db_connect(self) -> None:
        with self.assertRaisesRegex(ProjectionMatcherExecuteError, "deprecated legacy projection matcher route"):
            run_projection_matcher_execute_preflight(
                dsn="postgresql://example.invalid/should_not_connect",
                execute_run_id="trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
                trigger_context_run_id=CONTEXT_RUN_ID,
                projection_run_id=PROJECTION_RUN_ID,
                snapshot_run_id=DEFAULT_SNAPSHOT_RUN_ID,
                json_report_path="/tmp/should_not_write.json",
                markdown_report_path="/tmp/should_not_write.md",
                rollback_sql_path="/tmp/should_not_write.sql",
            )

    def test_execute_requires_execute_flag(self) -> None:
        with self.assertRaises(ProjectionMatcherExecuteError):
            assert_execute_confirmed(
                execute=False,
                user_confirmed=True,
                execute_run_id=DEFAULT_EXECUTE_RUN_ID,
                trigger_context_run_id=CONTEXT_RUN_ID,
                projection_run_id=PROJECTION_RUN_ID,
                snapshot_run_id=DEFAULT_SNAPSHOT_RUN_ID,
            )

    def test_execute_requires_user_confirmation_flag(self) -> None:
        with self.assertRaises(ProjectionMatcherExecuteError):
            assert_execute_confirmed(
                execute=True,
                user_confirmed=False,
                execute_run_id=DEFAULT_EXECUTE_RUN_ID,
                trigger_context_run_id=CONTEXT_RUN_ID,
                projection_run_id=PROJECTION_RUN_ID,
                snapshot_run_id=DEFAULT_SNAPSHOT_RUN_ID,
            )

    def test_plan_consumes_only_current_snapshot_run_and_excludes_synthetic(self) -> None:
        report = build_projection_matcher_execute_plan(
            execute_run_id=DEFAULT_EXECUTE_RUN_ID,
            trigger_context_run_id=CONTEXT_RUN_ID,
            projection_run_id=PROJECTION_RUN_ID,
            snapshot_run_id=DEFAULT_SNAPSHOT_RUN_ID,
            trigger_run=trigger_run(),
            evaluations=[
                matched_eval("evt_current", "stock:SH:600000"),
                matched_eval("evt_old_snapshot", "stock:SH:600001"),
                matched_eval("evt_synthetic", "stock:SH:600002"),
            ],
            source_outbox_rows=[
                source_outbox_row("evt_current", "stock:SH:600000"),
                source_outbox_row("evt_old_snapshot", "stock:SH:600001", source_run_id="old_snapshot_run"),
                source_outbox_row("evt_synthetic", "stock:SH:600002", source_layer="N4_trigger", source_run_id=SYNTHETIC_DENYLIST[0]),
            ],
            existing_inbox_keys=empty_inbox_keys(),
            existing_checkpoints={},
            synthetic_denylist=SYNTHETIC_DENYLIST,
        )

        self.assertEqual(report["summary"]["accepted_source_event_count"], 1)
        self.assertEqual(report["summary"]["matched_output_count"], 1)
        self.assertEqual(report["summary"]["skipped_source_event_reasons"], {"non_current_snapshot_run": 1, "unsupported_source_layer": 1})
        self.assertTrue(report["summary"]["synthetic_denylist_enforced"])
        self.assertFalse(report["summary"]["current_context_is_denylisted"])

    def test_denylisted_context_run_is_blocked(self) -> None:
        with self.assertRaises(ProjectionMatcherExecuteError):
            build_projection_matcher_execute_plan(
                execute_run_id=DEFAULT_EXECUTE_RUN_ID,
                trigger_context_run_id=SYNTHETIC_DENYLIST[0],
                projection_run_id=PROJECTION_RUN_ID,
                snapshot_run_id=DEFAULT_SNAPSHOT_RUN_ID,
                trigger_run=trigger_run(run_id=SYNTHETIC_DENYLIST[0]),
                evaluations=[matched_eval("evt_current", "stock:SH:600000")],
                source_outbox_rows=[source_outbox_row("evt_current", "stock:SH:600000")],
                existing_inbox_keys=empty_inbox_keys(),
                existing_checkpoints={},
                synthetic_denylist=SYNTHETIC_DENYLIST,
            )

    def test_ready_projection_generates_trigger_matched_and_pending_stays_non_n5_entry(self) -> None:
        report = build_projection_matcher_execute_plan(
            execute_run_id=DEFAULT_EXECUTE_RUN_ID,
            trigger_context_run_id=CONTEXT_RUN_ID,
            projection_run_id=PROJECTION_RUN_ID,
            snapshot_run_id=DEFAULT_SNAPSHOT_RUN_ID,
            trigger_run=trigger_run(),
            evaluations=[
                matched_eval(
                    "evt_ready",
                    "stock:SH:600000",
                    signal_type="B_BUY",
                    action_mark="30m_volume",
                    legacy_signal_type="B_BUY_30M_VOL",
                    condition_key="BUY:D",
                ),
                pending_eval("evt_board", "board:TDX:881001", asset_kind="board"),
                pending_eval("evt_bj", "stock:BJ:920045", asset_kind="stock"),
            ],
            source_outbox_rows=[
                source_outbox_row("evt_ready", "stock:SH:600000"),
                source_outbox_row("evt_board", "board:TDX:881001", asset_kind="board"),
                source_outbox_row("evt_bj", "stock:BJ:920045"),
            ],
            existing_inbox_keys=empty_inbox_keys(),
            existing_checkpoints={},
            synthetic_denylist=SYNTHETIC_DENYLIST,
        )

        self.assertEqual(report["summary"]["matched_output_count"], 1)
        self.assertEqual(report["summary"]["pending_output_count"], 2)
        self.assertEqual(report["summary"]["board_not_ready_pending_count"], 1)
        self.assertEqual(report["summary"]["bj_920xxx_not_ready_pending_count"], 1)
        self.assertEqual(report["summary"]["board_bj_not_ready_matched_count"], 0)
        self.assertEqual(
            {row["output_event_type"] for row in report["trigger_output_plan"]},
            {"TriggerMatched", "TriggerPendingMarketData"},
        )
        pending_rows = [
            row for row in report["trigger_output_plan"]
            if row["output_event_type"] == "TriggerPendingMarketData"
        ]
        self.assertTrue(all(row["would_write_trigger_state"] for row in pending_rows))
        self.assertTrue(all(row["would_write_n4_outbox"] for row in pending_rows))
        self.assertFalse(any(row["would_write_trigger_match"] for row in pending_rows))
        self.assertTrue(all(row["trigger_live"] is False for row in pending_rows))
        self.assertTrue(all(row["current_status"] == "pending_market_data" for row in pending_rows))
        self.assertTrue(all(row["n5_entry_allowed"] is False for row in pending_rows))

    def test_ready_board_trigger_matched_does_not_trip_not_ready_guard(self) -> None:
        report = build_projection_matcher_execute_plan(
            execute_run_id=DEFAULT_EXECUTE_RUN_ID,
            trigger_context_run_id=CONTEXT_RUN_ID,
            projection_run_id=PROJECTION_RUN_ID,
            snapshot_run_id=DEFAULT_SNAPSHOT_RUN_ID,
            trigger_run=trigger_run(),
            evaluations=[
                matched_eval("evt_ready_board", "board:TDX:881001", asset_kind="board"),
                pending_eval("evt_pending_board", "board:TDX:881002", asset_kind="board"),
            ],
            source_outbox_rows=[
                source_outbox_row("evt_ready_board", "board:TDX:881001", asset_kind="board"),
                source_outbox_row("evt_pending_board", "board:TDX:881002", asset_kind="board"),
            ],
            existing_inbox_keys=empty_inbox_keys(),
            existing_checkpoints={},
            synthetic_denylist=SYNTHETIC_DENYLIST,
        )

        self.assertEqual(report["summary"]["matched_output_count"], 1)
        self.assertEqual(report["summary"]["pending_output_count"], 1)
        self.assertEqual(report["summary"]["board_not_ready_pending_count"], 1)
        self.assertEqual(report["summary"]["board_bj_not_ready_matched_count"], 0)

    def test_formal_snapshot_fallback_board_match_does_not_trip_not_ready_guard(self) -> None:
        evaluation = matched_eval(
            "evt_snapshot_board",
            "board:TDX:881001",
            asset_kind="board",
            action_mark="normal",
            legacy_signal_type="SELL",
            condition_key="SELL:D",
            direction="sell",
            signal_type="S_SELL",
        )
        evaluation.update(
            {
                "projection_status": "not_ready",
                "projection_quality_status": "blocked",
                "trace_status": "blocked",
                "projection_signal_status": "unknown",
                "trigger_mark_candidate": "normal",
                "projection_30m_flag": False,
                "projection_30m_type": "none",
                "n3_trace": {"formal_snapshot_fallback": True},
            }
        )
        report = build_projection_matcher_execute_plan(
            execute_run_id=DEFAULT_EXECUTE_RUN_ID,
            trigger_context_run_id=CONTEXT_RUN_ID,
            projection_run_id=PROJECTION_RUN_ID,
            snapshot_run_id=DEFAULT_SNAPSHOT_RUN_ID,
            trigger_run=trigger_run(),
            evaluations=[evaluation],
            source_outbox_rows=[source_outbox_row("evt_snapshot_board", "board:TDX:881001", asset_kind="board")],
            existing_inbox_keys=empty_inbox_keys(),
            existing_checkpoints={},
            synthetic_denylist=SYNTHETIC_DENYLIST,
        )

        self.assertEqual(report["summary"]["matched_output_count"], 1)
        self.assertEqual(report["summary"]["board_bj_not_ready_matched_count"], 0)
        self.assertEqual(report["summary"]["formal_snapshot_fallback_board_bj_matched_count"], 1)

    def test_execute_plan_uses_trigger_mark_candidate_without_n4_action_mark_output(self) -> None:
        evaluation = matched_eval(
            "evt_ready",
            "stock:SH:600000",
            signal_type="B_BUY",
            action_mark="30m_volume",
            legacy_signal_type="B_BUY_30M_VOL",
            condition_key="BUY:D",
        )
        evaluation.pop("action_mark")
        evaluation["trigger_mark_candidate"] = "30m_volume"

        report = build_projection_matcher_execute_plan(
            execute_run_id=DEFAULT_EXECUTE_RUN_ID,
            trigger_context_run_id=CONTEXT_RUN_ID,
            projection_run_id=PROJECTION_RUN_ID,
            snapshot_run_id=DEFAULT_SNAPSHOT_RUN_ID,
            trigger_run=trigger_run(),
            evaluations=[evaluation],
            source_outbox_rows=[source_outbox_row("evt_ready", "stock:SH:600000")],
            existing_inbox_keys=empty_inbox_keys(),
            existing_checkpoints={},
            synthetic_denylist=SYNTHETIC_DENYLIST,
        )

        self.assertEqual(report["summary"]["matched_output_count"], 1)
        self.assertEqual(report["summary"]["matched_by_trigger_mark_candidate"], {"30m_volume": 1})
        self.assertEqual(report["trigger_output_plan"][0]["trigger_mark_candidate"], "30m_volume")
        self.assertNotIn("action_mark", report["trigger_output_plan"][0])

    def test_breach_shape_trigger_period_30m_blocks_before_write_plan(self) -> None:
        evaluation = matched_eval(
            "evt_breach",
            "stock:SZ:301656",
            signal_type="B_BUY",
            action_mark="30m_volume",
            legacy_signal_type="B_BUY_30M_VOL",
            condition_key="BUY:Y,Q,M,W",
        )
        evaluation["trigger_period"] = "30m"
        evaluation["trigger_price"] = None
        evaluation.pop("trigger_kind", None)
        evaluation.pop("n5_entry_allowed", None)

        with self.assertRaisesRegex(ProjectionMatcherExecuteError, "v4 enforcement"):
            build_projection_matcher_execute_plan(
                execute_run_id=DEFAULT_EXECUTE_RUN_ID,
                trigger_context_run_id=CONTEXT_RUN_ID,
                projection_run_id=PROJECTION_RUN_ID,
                snapshot_run_id=DEFAULT_SNAPSHOT_RUN_ID,
                trigger_run=trigger_run(),
                evaluations=[evaluation],
                source_outbox_rows=[source_outbox_row("evt_breach", "stock:SZ:301656")],
                existing_inbox_keys=empty_inbox_keys(),
                existing_checkpoints={},
                synthetic_denylist=SYNTHETIC_DENYLIST,
            )

    def test_inbox_checkpoint_and_outbox_dedup_are_idempotent(self) -> None:
        duplicate = matched_eval("evt_duplicate", "stock:SH:600000")
        report = build_projection_matcher_execute_plan(
            execute_run_id=DEFAULT_EXECUTE_RUN_ID,
            trigger_context_run_id=CONTEXT_RUN_ID,
            projection_run_id=PROJECTION_RUN_ID,
            snapshot_run_id=DEFAULT_SNAPSHOT_RUN_ID,
            trigger_run=trigger_run(),
            evaluations=[
                matched_eval("evt_existing_inbox", "stock:SH:600001"),
                matched_eval("evt_checkpointed", "stock:SH:600002"),
                duplicate,
                dict(duplicate),
            ],
            source_outbox_rows=[
                source_outbox_row("evt_existing_inbox", "stock:SH:600001", outbox_id=10),
                source_outbox_row("evt_checkpointed", "stock:SH:600002", outbox_id=20),
                source_outbox_row("evt_duplicate", "stock:SH:600000", outbox_id=30),
            ],
            existing_inbox_keys={
                "event_ids": {"evt_existing_inbox"},
                "consumer_dedup_keys": set(),
                "output_dedup_keys": set(),
                "outbox_event_ids": set(),
            },
            existing_checkpoints={
                "stock:SH:600002": {"last_outbox_id": 25, "last_event_time": "2026-05-25T06:00:00+00:00"}
            },
            synthetic_denylist=SYNTHETIC_DENYLIST,
        )

        self.assertEqual(report["summary"]["matched_output_count"], 1)
        self.assertEqual(report["summary"]["output_dedup_skipped_count"], 1)
        self.assertEqual(report["summary"]["skipped_source_event_reasons"], {"at_or_before_existing_watermark": 1, "existing_inbox_event_id": 1})
        self.assertEqual(report["summary"]["inbox_write_plan_count"], 1)
        self.assertEqual(report["summary"]["checkpoint_write_plan_count"], 1)

    def test_checkpoint_only_moves_forward(self) -> None:
        event_plan = {
            "consumer_name": DEFAULT_CONSUMER_NAME,
            "partition_key": "stock:SH:600000",
            "source_layer": "N3_market_data",
            "event_id": "evt_new",
            "event_time": "2026-05-25T06:05:00+00:00",
            "source_outbox_id": 10,
        }

        blocked = build_checkpoint_write_plan(event_plan, {"last_outbox_id": 10})
        advanced = build_checkpoint_write_plan(event_plan, {"last_outbox_id": 9})

        self.assertFalse(blocked["would_insert_or_update_common_event_consumer_checkpoint"])
        self.assertEqual(blocked["skip_reason"], "checkpoint_not_advanced")
        self.assertTrue(advanced["would_insert_or_update_common_event_consumer_checkpoint"])

    def test_rollback_sql_is_scoped_to_n4_execute_run_and_does_not_touch_n3(self) -> None:
        rollback_sql = build_projection_matcher_rollback_sql(DEFAULT_EXECUTE_RUN_ID, DEFAULT_CONSUMER_NAME)

        self.assertIn("DELETE FROM common_event_outbox", rollback_sql)
        self.assertIn("DELETE FROM common_trigger_match", rollback_sql)
        self.assertIn("DELETE FROM common_trigger_state", rollback_sql)
        self.assertIn("DELETE FROM common_event_inbox", rollback_sql)
        self.assertIn("DELETE FROM common_event_consumer_checkpoint", rollback_sql)
        self.assertIn("DELETE FROM common_trigger_run", rollback_sql)
        self.assertLess(
            rollback_sql.lower().find("raise exception"),
            rollback_sql.lower().find("delete from"),
        )
        self.assertNotEqual(rollback_sql.lower().find("raise exception"), -1)
        self.assertNotIn("stock_realtime", rollback_sql)
        self.assertNotIn("index_realtime", rollback_sql)
        self.assertNotIn("board_realtime", rollback_sql)
        self.assertNotIn("common_market_data_run", rollback_sql)

    def test_contract_is_run_once_only_and_has_no_downstream_writes(self) -> None:
        contract = build_execute_contract()

        self.assertEqual(contract["execution_mode"], "run_once")
        self.assertTrue(contract["route_selection"]["deprecated"])
        self.assertFalse(contract["route_selection"]["allowed_for_current_v4_corrected_flow"])
        self.assertFalse(contract["route_selection"]["allowed_for_20260605_n4_execute_gate"])
        self.assertFalse(contract["route_selection"]["n5_entry_source_for_current_chain"])
        self.assertTrue(contract["requires_execute_flag"])
        self.assertTrue(contract["requires_user_confirmed_flag"])
        self.assertFalse(contract["side_effects"]["worker_started"])
        self.assertFalse(contract["side_effects"]["n5_n6_touched"])
        self.assertEqual(contract["planned_event_types"], ["TriggerMatched", "TriggerPendingMarketData"])
        self.assertNotIn("action_mark", contract["canonical_payload_fields"])
        self.assertIn("trigger_mark_candidate", contract["canonical_payload_fields"])
        self.assertEqual(contract["canonical_trigger_mark_candidates"], ["normal", "30m_volume", "30m_shrink"])
        self.assertEqual(contract["canonical_signal_types"], ["B_BUY", "S_SELL"])
        self.assertNotIn("TriggerSuppressed", contract["planned_event_types"])
        self.assertNotIn("TriggerNotReady", contract["planned_event_types"])

    def test_contract_uses_explicit_runtime_lineage_when_provided(self) -> None:
        contract = build_execute_contract(
            consumer_name="n4_projection_matcher_consumer_v1_until_1500_full_repair_retry",
            trigger_context_run_id="trigger_context_snapshot_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute",
            projection_run_id=(
                "realtime_projection_metric_20260608_until_1500__"
                "realtime_daily_snapshot_20260608__"
                "market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute"
            ),
            snapshot_run_id=(
                "realtime_daily_snapshot_20260608__"
                "market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute"
            ),
        )

        self.assertEqual(
            contract["consumer_name"],
            "n4_projection_matcher_consumer_v1_until_1500_full_repair_retry",
        )
        self.assertEqual(
            contract["trigger_context_run_id"],
            "trigger_context_snapshot_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute",
        )
        self.assertIn("20260608_until_1500", contract["projection_run_id"])
        self.assertIn("20260608", contract["input_filter"]["source_run_id"])
        active_lineage = {
            "consumer_name": contract["consumer_name"],
            "trigger_context_run_id": contract["trigger_context_run_id"],
            "projection_run_id": contract["projection_run_id"],
            "source_run_id": contract["input_filter"]["source_run_id"],
        }
        self.assertNotIn("20260525", json.dumps(active_lineage, ensure_ascii=False))

    def test_runner_does_not_import_market_adapters_or_raw_minute_reads(self) -> None:
        module_source = inspect.getsource(projection_matcher_execute)

        for forbidden in ("mootdx", "tushare", "MarketDataAdapter", "minute_bar_1m"):
            self.assertNotIn(forbidden, module_source)

    def test_execute_raw_json_payload_is_json_serializable(self) -> None:
        row = source_outbox_row("evt_serializable", "stock:SH:600000")
        row["event_time"] = projection_matcher_execute.parse_event_time("2026-05-25T06:01:00+00:00")
        report = build_projection_matcher_execute_plan(
            execute_run_id=DEFAULT_EXECUTE_RUN_ID,
            trigger_context_run_id=CONTEXT_RUN_ID,
            projection_run_id=PROJECTION_RUN_ID,
            snapshot_run_id=DEFAULT_SNAPSHOT_RUN_ID,
            trigger_run=trigger_run(),
            evaluations=[matched_eval("evt_serializable", "stock:SH:600000")],
            source_outbox_rows=[row],
            existing_inbox_keys=empty_inbox_keys(),
            existing_checkpoints={},
            synthetic_denylist=SYNTHETIC_DENYLIST,
        )

        json_ready = to_jsonable({"plan": report["trigger_output_plan"]})

        self.assertIsInstance(json_ready["plan"][0]["source_event_time"], str)
        projection_matcher_execute.json.dumps(json_ready)

    def test_preflight_counts_match_current_dry_run_alignment_not_stale_constants(self) -> None:
        execute_plan = {
            "summary": {
                "accepted_source_event_count": 3,
                "matched_output_count": 2,
                "pending_output_count": 1,
                "board_bj_not_ready_matched_count": 0,
                "planned_event_types": ["TriggerMatched", "TriggerPendingMarketData"],
                "n3_outbox_status_update_count": 0,
            }
        }

        items = build_preflight_quality_items(
            execute_plan=execute_plan,
            dry_run_alignment={
                "source": "docs/current_n4_dry_run.json",
                "result": "DRY_RUN_PASS",
                "p0_count": 0,
                "expected_matched_count": 2,
                "expected_pending_count": 1,
            },
            before_row_counts={},
            after_row_counts={},
        )

        by_code = {item["gate_code"]: item for item in items}
        self.assertEqual(by_code["n4_projection_execute_matched_count_matches_dry_run"]["status"], "passed")
        self.assertEqual(by_code["n4_projection_execute_matched_count_matches_dry_run"]["expected_value"], "2")
        self.assertEqual(by_code["n4_projection_execute_pending_count_matches_dry_run"]["status"], "passed")
        self.assertEqual(by_code["n4_projection_execute_pending_count_matches_dry_run"]["expected_value"], "1")

    def test_load_dry_run_alignment_accepts_reviewed_expected_counts_shape(self) -> None:
        dry_run = {
            "result": "DRY_RUN_PASS",
            "quality": {"p0_count": 0},
            "reviewed_expected_counts": {
                "TriggerMatched": 548,
                "TriggerPendingMarketData": 251,
            },
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8") as handle:
            json.dump(dry_run, handle)
            handle.flush()

            alignment = load_dry_run_alignment(handle.name)

        self.assertEqual(alignment["expected_matched_count"], 548)
        self.assertEqual(alignment["expected_pending_count"], 251)

    def test_preflight_allows_trigger_matched_only_when_pending_count_is_zero(self) -> None:
        execute_plan = {
            "summary": {
                "accepted_source_event_count": 2,
                "matched_output_count": 2,
                "pending_output_count": 0,
                "board_bj_not_ready_matched_count": 0,
                "planned_event_types": ["TriggerMatched"],
                "n3_outbox_status_update_count": 0,
            }
        }

        items = build_preflight_quality_items(
            execute_plan=execute_plan,
            dry_run_alignment={
                "source": "docs/current_n4_dry_run.json",
                "result": "DRY_RUN_PASS",
                "p0_count": 0,
                "expected_matched_count": 2,
                "expected_pending_count": 0,
            },
            before_row_counts={},
            after_row_counts={},
        )

        by_code = {item["gate_code"]: item for item in items}
        self.assertEqual(by_code["n4_projection_execute_only_allowed_output_events"]["status"], "passed")

    def test_output_event_envelope_carries_trigger_mark_candidate_contract_field(self) -> None:
        report = build_projection_matcher_execute_plan(
            execute_run_id=DEFAULT_EXECUTE_RUN_ID,
            trigger_context_run_id=CONTEXT_RUN_ID,
            projection_run_id=PROJECTION_RUN_ID,
            snapshot_run_id=DEFAULT_SNAPSHOT_RUN_ID,
            trigger_run=trigger_run(),
            evaluations=[
                matched_eval(
                    "evt_contract",
                    "stock:SH:600000",
                    signal_type="B_BUY",
                    action_mark="30m_volume",
                    legacy_signal_type="B_BUY_30M_VOL",
                    condition_key="BUY:D",
                )
            ],
            source_outbox_rows=[source_outbox_row("evt_contract", "stock:SH:600000")],
            existing_inbox_keys=empty_inbox_keys(),
            existing_checkpoints={},
            synthetic_denylist=SYNTHETIC_DENYLIST,
        )

        envelope = build_output_event_envelope(
            execute_run_id=DEFAULT_EXECUTE_RUN_ID,
            context_run={"for_trade_date": "20260525"},
            plan=report["trigger_output_plan"][0],
            event_time=projection_matcher_execute.parse_event_time("2026-05-25T06:01:00+00:00"),
            trigger_state_id=1,
            trigger_match_id=2,
        )

        self.assertEqual(envelope.payload_json["trigger_mark_candidate"], "30m_volume")
        self.assertEqual(envelope.payload_json["trigger_price"], "10.50")
        self.assertEqual(envelope.payload_json["trigger_kind"], "trigger")
        self.assertIs(envelope.payload_json["n5_entry_allowed"], True)
        self.assertEqual(envelope.payload_json["projection_period"], "30m")
        self.assertNotEqual(envelope.payload_json["trigger_period"], "30m")
        for key in (
            "runtime_signal_type",
            "condition_signal_type",
            "requested_periods",
            "triggered_period_details",
            "price_source",
            "baseline_source",
            "projection_30m_required",
            "projection_30m_volume_up_flag",
            "projection_30m_shrink_down_flag",
        ):
            self.assertIn(key, envelope.payload_json)
        self.assertEqual(envelope.payload_json["runtime_signal_type"], "B_BUY")
        self.assertEqual(envelope.payload_json["condition_signal_type"], "BUY")
        self.assertEqual(envelope.payload_json["requested_periods"], ["D"])
        self.assertTrue(envelope.payload_json["triggered_period_details"])
        self.assertFalse(envelope.payload_json["projection_30m_required"])
        self.assertNotIn("action_mark", envelope.payload_json)

    def test_hint_output_event_envelope_allows_trigger_period_30m_with_empty_formal_periods(self) -> None:
        report = build_projection_matcher_execute_plan(
            execute_run_id=DEFAULT_EXECUTE_RUN_ID,
            trigger_context_run_id=CONTEXT_RUN_ID,
            projection_run_id=PROJECTION_RUN_ID,
            snapshot_run_id=DEFAULT_SNAPSHOT_RUN_ID,
            trigger_run=trigger_run(),
            evaluations=[matched_eval("evt_hint", "stock:SH:600000", condition_key="BUY_HINT")],
            source_outbox_rows=[source_outbox_row("evt_hint", "stock:SH:600000")],
            existing_inbox_keys=empty_inbox_keys(),
            existing_checkpoints={},
            synthetic_denylist=SYNTHETIC_DENYLIST,
        )

        plan = report["trigger_output_plan"][0]
        envelope = build_output_event_envelope(
            execute_run_id=DEFAULT_EXECUTE_RUN_ID,
            context_run={"for_trade_date": "20260525"},
            plan=plan,
            event_time=projection_matcher_execute.parse_event_time("2026-05-25T06:01:00+00:00"),
            trigger_state_id=1,
            trigger_match_id=2,
        )

        self.assertEqual(plan["trigger_kind"], "hint")
        self.assertEqual(plan["trigger_period"], "30m")
        self.assertEqual(plan["event_time"], "2026-05-25T06:01:00+00:00")
        self.assertEqual(plan["event_time"], plan["source_event_time"])
        self.assertEqual(plan["triggered_periods"], [])
        self.assertEqual(plan["all_trigger_periods"], [])
        self.assertIsNone(plan["primary_trigger_period"])
        self.assertEqual(envelope.payload_json["trigger_period"], "30m")
        self.assertEqual(envelope.payload_json["event_time"], "2026-05-25T06:01:00+00:00")
        self.assertEqual(envelope.event_time, projection_matcher_execute.parse_event_time("2026-05-25T06:01:00+00:00"))
        self.assertEqual(envelope.payload_json["triggered_periods"], [])
        self.assertEqual(envelope.payload_json["all_trigger_periods"], [])
        self.assertIsNone(envelope.payload_json["primary_trigger_period"])
        self.assertEqual(envelope.payload_json["projection_period"], "30m")
        self.assertEqual(envelope.payload_json["projection_30m_type"], "volume_up")
        self.assertEqual(envelope.payload_json["trigger_mark_candidate"], "30m_volume")
        self.assertEqual(envelope.payload_json["runtime_signal_type"], "B_BUY")
        self.assertEqual(envelope.payload_json["condition_signal_type"], "BUY_HINT")
        self.assertEqual(envelope.payload_json["requested_periods"], [])
        self.assertEqual(envelope.payload_json["triggered_period_details"], [])
        self.assertTrue(envelope.payload_json["projection_30m_required"])
        self.assertTrue(envelope.payload_json["projection_30m_volume_up_flag"])
        self.assertFalse(envelope.payload_json["projection_30m_shrink_down_flag"])
        self.assertNotIn("action_mark", envelope.payload_json)

    def test_trigger_state_and_match_persist_trigger_mark_candidate_columns(self) -> None:
        plan = matched_eval(
            "evt_columns",
            "stock:SH:600000",
            signal_type="B_BUY",
            action_mark="30m_volume",
            legacy_signal_type="B_BUY_30M_VOL",
            condition_key="BUY:D",
        )
        plan["output_event_id"] = "evt_n4_columns"
        plan["output_dedup_key"] = "dedup_n4_columns"
        plan["trigger_mark_candidate"] = "30m_volume"
        cursor = RecordingCursor()

        projection_matcher_execute.upsert_trigger_state(
            cursor,
            execute_run_id=DEFAULT_EXECUTE_RUN_ID,
            context_run=trigger_run(),
            plan=plan,
            event_time=projection_matcher_execute.parse_event_time("2026-05-25T06:01:00+00:00"),
            current_status="matched",
        )

        self.assertIn("trigger_mark_candidate", cursor.sql)
        self.assertIn("projection_30m_flag", cursor.sql)
        self.assertIn("projection_30m_type", cursor.sql)
        self.assertIn("30m_volume", cursor.params)
        self.assertIn(True, cursor.params)
        self.assertIn("volume_up", cursor.params)
        state_raw_json = cursor.params[23].obj
        self.assertEqual(state_raw_json["runtime_signal_type"], "B_BUY")
        self.assertEqual(state_raw_json["condition_signal_type"], "BUY")
        self.assertEqual(state_raw_json["requested_periods"], ["D"])
        self.assertTrue(state_raw_json["triggered_period_details"])
        self.assertFalse(state_raw_json["projection_30m_required"])
        self.assertNotIn("action_mark", state_raw_json)
        self.assertEqual(cursor.sql.count("%s"), len(cursor.params))

        cursor = RecordingCursor({"trigger_match_id": 2})
        projection_matcher_execute.insert_trigger_match(
            cursor,
            execute_run_id=DEFAULT_EXECUTE_RUN_ID,
            context_run=trigger_run(),
            plan=plan,
            trigger_state_id=1,
            trigger_time=projection_matcher_execute.parse_event_time("2026-05-25T06:01:00+00:00"),
        )

        self.assertIn("trigger_mark_candidate", cursor.sql)
        self.assertIn("trigger_price", cursor.sql)
        self.assertIn("30m_volume", cursor.params)
        self.assertIn("10.50", cursor.params)
        match_raw_json = cursor.params[24].obj
        self.assertEqual(match_raw_json["runtime_signal_type"], "B_BUY")
        self.assertEqual(match_raw_json["condition_signal_type"], "BUY")
        self.assertEqual(match_raw_json["requested_periods"], ["D"])
        self.assertTrue(match_raw_json["triggered_period_details"])
        self.assertFalse(match_raw_json["projection_30m_required"])
        self.assertNotIn("action_mark", match_raw_json)
        self.assertEqual(cursor.sql.count("%s"), len(cursor.params))

    def test_pending_market_data_does_not_insert_common_trigger_match(self) -> None:
        cursor = RecordingCursor()
        counts = projection_matcher_execute.execute_trigger_output_rows(
            cursor,
            execute_run_id=DEFAULT_EXECUTE_RUN_ID,
            context_run=trigger_run(),
            rows=[pending_eval("evt_pending", "stock:SH:600000", asset_kind="stock")],
        )

        self.assertEqual(counts["common_trigger_state"], 1)
        self.assertEqual(counts["common_trigger_match"], 0)
        self.assertEqual(counts["common_event_outbox"], 1)
        self.assertFalse(any("INSERT INTO common_trigger_match" in sql for sql in cursor.sql_history))

    def test_pending_market_data_state_uses_projection_period_for_schema_compatibility(self) -> None:
        cursor = RecordingCursor()
        plan = pending_eval("evt_pending_period", "stock:SH:600000", asset_kind="stock")

        counts = projection_matcher_execute.execute_trigger_output_rows(
            cursor,
            execute_run_id=DEFAULT_EXECUTE_RUN_ID,
            context_run=trigger_run(),
            rows=[plan],
        )

        state_params = cursor.params_history[0]
        self.assertEqual(counts["common_trigger_state"], 1)
        self.assertEqual(counts["common_trigger_match"], 0)
        self.assertEqual(state_params[8], "30m")
        self.assertIs(state_params[17], False)
        self.assertIsNone(state_params[19])
        self.assertEqual(state_params[20].obj, [])
        self.assertFalse(any("INSERT INTO common_trigger_match" in sql for sql in cursor.sql_history))

        envelope = build_output_event_envelope(
            execute_run_id=DEFAULT_EXECUTE_RUN_ID,
            context_run={"for_trade_date": "20260525"},
            plan=plan,
            event_time=projection_matcher_execute.parse_event_time("2026-05-25T06:01:00+00:00"),
            trigger_state_id=1,
            trigger_match_id=None,
        )

        self.assertEqual(envelope.event_type, "TriggerPendingMarketData")
        self.assertEqual(envelope.payload_json["trigger_period"], "30m")
        self.assertEqual(envelope.payload_json["triggered_periods"], [])
        self.assertEqual(envelope.payload_json["all_trigger_periods"], [])
        self.assertIsNone(envelope.payload_json["primary_trigger_period"])
        self.assertFalse(envelope.payload_json["trigger_live"])
        self.assertFalse(envelope.payload_json["n5_entry_allowed"])
        self.assertEqual(envelope.payload_json["runtime_signal_type"], "B_BUY")
        self.assertEqual(envelope.payload_json["condition_signal_type"], "BUY")
        self.assertEqual(envelope.payload_json["requested_periods"], ["D"])
        self.assertEqual(envelope.payload_json["triggered_period_details"], [])
        self.assertFalse(envelope.payload_json["projection_30m_required"])


def trigger_run(run_id: str = CONTEXT_RUN_ID) -> dict[str, object]:
    return {
        "run_id": run_id,
        "source_condition_run_id": "condition_layer_20260522_to_20260525_20260525102249_execute",
        "source_market_data_run_id": "market_data_subscription_20260525_condition_layer_20260522_to_20260525102249_execute",
        "for_trade_date": "20260525",
        "source_trade_date": "20260522",
        "prev_trade_date": "20260522",
        "status": "passed",
        "context_snapshot_row_count": 4512,
    }


def matched_eval(
    event_id: str,
    identity_key: str,
    *,
    signal_type: str = "B_BUY",
    action_mark: str = "30m_volume",
    legacy_signal_type: str = "BUY_HINT",
    condition_key: str = "BUY_HINT",
    direction: str = "buy",
    asset_kind: str = "stock",
) -> dict[str, object]:
    return base_eval(
        event_id,
        identity_key,
        output_event_type="TriggerMatched",
        plan_status="matched",
        signal_type=signal_type,
        action_mark=action_mark,
        legacy_signal_type=legacy_signal_type,
        condition_key=condition_key,
        direction=direction,
        asset_kind=asset_kind,
        data_quality_status="passed",
        projection_status="ready",
        projection_quality_status="passed",
        trace_status="passed",
        projection_signal_status="up_volume_expanding" if direction == "buy" else "down_volume_shrinking",
    )


def pending_eval(event_id: str, identity_key: str, *, asset_kind: str) -> dict[str, object]:
    return base_eval(
        event_id,
        identity_key,
        output_event_type="TriggerPendingMarketData",
        plan_status="pending",
        signal_type="B_BUY",
        action_mark="30m_volume",
        legacy_signal_type="B_BUY_30M_VOL",
        condition_key="BUY:D",
        direction="buy",
        asset_kind=asset_kind,
        data_quality_status="missing",
        projection_status="not_ready",
        projection_quality_status="blocked",
        trace_status="blocked",
        projection_signal_status="unknown",
        not_ready_classification="warning" if identity_key.startswith("stock:BJ:920") else "blocked",
    )


def condition_signal_type_for_test(condition_key: str) -> str:
    if condition_key in {"BUY_HINT", "SELL_HINT", "BUY:FULL", "SELL:FULL"}:
        return condition_key
    if condition_key.startswith("SELL"):
        return "SELL"
    return "BUY"


def base_eval(
    event_id: str,
    identity_key: str,
    *,
    output_event_type: str,
    plan_status: str,
    signal_type: str,
    action_mark: str,
    legacy_signal_type: str,
    condition_key: str,
    direction: str,
    asset_kind: str,
    data_quality_status: str,
    projection_status: str,
    projection_quality_status: str,
    trace_status: str,
    projection_signal_status: str,
    not_ready_classification: str | None = None,
) -> dict[str, object]:
    return {
        "plan_id": f"plan_{event_id}_{identity_key}_{signal_type}_{condition_key}",
        "plan_status": plan_status,
        "output_event_type": output_event_type,
        "source_event_id": event_id,
        "source_event_type": "MarketSnapshotUpdated",
        "source_projection_id": 501,
        "output_event_id": f"evt_n4_{event_id}",
        "output_dedup_key": f"dedup_n4_{event_id}",
        "projection_run_id": PROJECTION_RUN_ID,
        "projection_window_id": "20260525_1400_1430",
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "direction": direction,
        "signal_type": signal_type,
        "runtime_signal_type": signal_type,
        "condition_signal_type": condition_signal_type_for_test(condition_key),
        "action_mark": action_mark,
        "condition_key": condition_key,
        "original_condition_key": condition_key,
        "legacy_signal_type": legacy_signal_type,
        "match_basis": "intraday_projection",
        "trigger_period": "30m" if output_event_type == "TriggerMatched" and condition_key in {"BUY_HINT", "SELL_HINT"}
        else "D" if output_event_type == "TriggerMatched"
        else None,
        "trigger_price": "10.50" if output_event_type == "TriggerMatched" else None,
        "trigger_kind": "hint" if condition_key in {"BUY_HINT", "SELL_HINT"} else "trigger",
        "trigger_live": output_event_type == "TriggerMatched",
        "current_status": "matched" if output_event_type == "TriggerMatched" else "pending_market_data",
        "n5_entry_allowed": output_event_type == "TriggerMatched",
        "requested_periods": []
        if condition_key in {"BUY_HINT", "SELL_HINT"}
        else ["D"],
        "triggered_periods": []
        if condition_key in {"BUY_HINT", "SELL_HINT"}
        else ["D"] if output_event_type == "TriggerMatched"
        else [],
        "all_trigger_periods": []
        if condition_key in {"BUY_HINT", "SELL_HINT"}
        else ["D"] if output_event_type == "TriggerMatched"
        else [],
        "primary_trigger_period": None
        if condition_key in {"BUY_HINT", "SELL_HINT"}
        else "D" if output_event_type == "TriggerMatched"
        else None,
        "triggered_period_details": []
        if condition_key in {"BUY_HINT", "SELL_HINT"} or output_event_type != "TriggerMatched"
        else [{"period": "D", "classification": "triggered", "trigger_price": "10.50"}],
        "projection_period": "30m",
        "projection_30m_required": condition_key in {"BUY_HINT", "SELL_HINT"},
        "projection_30m_flag": action_mark in {"30m_volume", "30m_shrink"},
        "projection_30m_type": "volume_up" if action_mark == "30m_volume" else "shrink_down" if action_mark == "30m_shrink" else "none",
        "projection_30m_volume_up_flag": action_mark == "30m_volume",
        "projection_30m_shrink_down_flag": action_mark == "30m_shrink",
        "price_source": "n3_realtime_projection",
        "baseline_source": "trigger_baseline",
        "trigger_bucket": "20260525_1400_1430",
        "data_quality_status": data_quality_status,
        "projection_status": projection_status,
        "projection_quality_status": projection_quality_status,
        "trace_status": trace_status,
        "projection_signal_status": projection_signal_status,
        "not_ready_classification": not_ready_classification,
        "context_snapshot_id": 1001,
        "source_condition_run_id": "condition_layer_20260522_to_20260525_20260525102249_execute",
        "source_condition_pool_id": 2001,
        "source_condition_basis_id": 3001,
        "source_minute_target_scope_id": 4001,
        "source_market_subscription_id": 5001,
        "context_hash": "context_hash",
        "projection_trace": {
            "projection_id": 501,
            "trigger_price": "10.50",
            "trigger_time": "2026-05-25T06:01:00+00:00",
            "source_confirmed_time": "2026-05-25T06:01:00+00:00",
            "closed_label_used": "2026-05-25T06:01:00+00:00",
            "quality_status": "passed",
            "source_snapshot_run_id": DEFAULT_SNAPSHOT_RUN_ID,
            "snapshot_event_id": event_id,
            "snapshot_id": 8001,
            "source_fact_ids": {"snapshot_event_id": event_id},
        },
        "period_trigger_baseline_trace": {"present": True, "baseline_version": "N2-R4-period-trigger-baseline-v1"},
    }


def source_outbox_row(
    event_id: str,
    identity_key: str,
    *,
    asset_kind: str = "stock",
    outbox_id: int = 1,
    source_layer: str = "N3_market_data",
    source_run_id: str = DEFAULT_SNAPSHOT_RUN_ID,
    event_type: str = "MarketSnapshotUpdated",
    status: str = "pending",
) -> dict[str, object]:
    return {
        "outbox_id": outbox_id,
        "event_id": event_id,
        "event_type": event_type,
        "event_schema_version": "v1",
        "trade_date": "20260525",
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "event_time": "2026-05-25T06:01:00+00:00",
        "source_layer": source_layer,
        "source_run_id": source_run_id,
        "dedup_key": f"n3_dedup_{event_id}",
        "partition_key": identity_key,
        "payload_json": {"run_id": source_run_id, "snapshot_id": 8001, "data_quality_status": "passed"},
        "status": status,
    }


def empty_inbox_keys() -> dict[str, set[str]]:
    return {
        "event_ids": set(),
        "consumer_dedup_keys": set(),
        "output_dedup_keys": set(),
        "outbox_event_ids": set(),
    }


class RecordingCursor:
    def __init__(self, fetched: dict[str, object] | None = None) -> None:
        self.sql = ""
        self.params: tuple[object, ...] = ()
        self.sql_history: list[str] = []
        self.params_history: list[tuple[object, ...]] = []
        self._fetched = fetched or {"trigger_state_id": 1}

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.sql = sql
        self.params = params
        self.sql_history.append(sql)
        self.params_history.append(params)

    def fetchone(self) -> dict[str, object]:
        if "RETURNING event_id" in self.sql:
            return {"event_id": "evt_pending_outbox"}
        if "RETURNING trigger_match_id" in self.sql:
            return {"trigger_match_id": 2}
        return self._fetched


if __name__ == "__main__":
    unittest.main()
