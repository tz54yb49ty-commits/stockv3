from __future__ import annotations

import subprocess
import sys
import unittest
from unittest.mock import patch

from ashare_v3.trigger.action_confirmation_metric_execute import (
    ActionConfirmationMetricExecuteError,
    assert_action_confirmation_metric_execute_confirmed,
    build_action_confirmation_metric_execute_event_envelope,
    execute_action_confirmation_metric_transaction,
    insert_action_confirmation_metric_trigger_run,
    write_action_confirmation_metric_outcomes_with_cursor,
)
from ashare_v3.trigger.action_confirmation_metric_matcher import (
    DEFAULT_EXECUTE_RUN_ID,
    build_action_confirmation_metric_business_execute_contract,
    build_action_confirmation_metric_dry_run_report,
    build_action_confirmation_metric_execute_final_preflight,
    build_action_confirmation_metric_preflight_report,
)


class TriggerActionConfirmationMetricExecuteTest(unittest.TestCase):
    def test_missing_execute_confirmation_blocks_before_writes(self) -> None:
        with self.assertRaises(ActionConfirmationMetricExecuteError):
            assert_action_confirmation_metric_execute_confirmed(execute=False, user_confirmed=True)
        with self.assertRaises(ActionConfirmationMetricExecuteError):
            assert_action_confirmation_metric_execute_confirmed(execute=True, user_confirmed=False)

    def test_execute_event_envelope_contains_metric_trace(self) -> None:
        envelope = build_action_confirmation_metric_execute_event_envelope(
            execute_run_id=DEFAULT_EXECUTE_RUN_ID,
            trigger_context_run=trigger_context_run(),
            plan=metric_plan(),
            trigger_state_id=101,
            trigger_match_id=202,
            output_event_id="evt_metric_outcome",
            dedup_key="dedup-metric-outcome",
        )

        self.assertEqual(envelope.event_type, "TriggerMatched")
        payload = envelope.payload_json
        self.assertEqual(payload["source_action_confirmation_metric_id"], 1001)
        self.assertEqual(payload["source_projection_run_id"], "projection_run")
        self.assertEqual(payload["projection_schema_version"], "n3.action_confirmation_metric.v1")
        self.assertEqual(payload["metric_trace"]["current_price"], 10.5)
        self.assertEqual(payload["trigger_price"], 10.5)
        self.assertEqual(payload["trigger_price_source"], "n3_action_confirmation_metric.current_price")
        self.assertEqual(payload["triggered_periods"], ["D"])
        self.assertEqual(payload["all_trigger_periods"], ["D"])
        self.assertEqual(payload["primary_trigger_period"], "D")
        self.assertEqual(
            payload["triggered_period_details"],
            [
                {
                    "period": "D",
                    "entity_pass": True,
                    "amount_pass": True,
                    "status": "triggered",
                }
            ],
        )
        self.assertEqual(payload["formal_trigger_period_proof_status"], "passed")
        self.assertFalse(payload["n4_boundary"]["n3_outbox_consumed"])
        self.assertFalse(payload["n4_boundary"]["worker_started"])
        self.assertNotIn("action_mark", payload)

    def test_write_outcomes_drops_pending_and_writes_lifecycle_events_only(self) -> None:
        cur = RecordingCursor()
        counts = write_action_confirmation_metric_outcomes_with_cursor(
            cur,
            execute_run_id=DEFAULT_EXECUTE_RUN_ID,
            trigger_context_run=trigger_context_run(),
            plans=[
                metric_plan(),
                {
                    **metric_plan(),
                    "plan_id": "pending",
                    "output_event_type": "TriggerPendingMarketData",
                    "writes_common_trigger_match": False,
                    "is_n5_action_entry": False,
                    "n5_entry_allowed": False,
                    "trigger_live": False,
                    "current_status": "pending_market_data",
                    "source_event_id": "snapshot-event-pending",
                },
                {
                    **metric_plan(),
                    "plan_id": "state-changed",
                    "output_event_type": "TriggerStateChanged",
                    "writes_common_trigger_match": False,
                    "is_n5_action_entry": False,
                    "n5_entry_allowed": False,
                    "trigger_live": False,
                    "previous_trigger_live": True,
                    "current_status": "inactive",
                    "previous_status": "matched",
                    "state_change_reason": "deactivated",
                    "source_event_id": "snapshot-event-state-changed",
                    "source_outcome_event_type": None,
                    "source_outcome_event_id": None,
                },
            ],
        )

        self.assertEqual(counts["common_trigger_state"], 1)
        self.assertEqual(counts["common_trigger_match"], 1)
        self.assertEqual(counts["common_event_outbox"], 2)
        self.assertEqual(counts["TriggerMatched"], 1)
        self.assertEqual(counts["TriggerPendingMarketData"], 0)
        self.assertEqual(counts["TriggerStateChanged"], 1)
        all_sql = "\n".join(cur.sql_log)
        match_params = next(
            params
            for sql, params in cur.execute_log
            if "INSERT INTO common_trigger_match" in sql and isinstance(params, dict)
        )
        self.assertEqual(match_params["trigger_price"], 10.5)
        self.assertEqual(match_params["raw_json"].obj["trigger_price"], 10.5)
        self.assertEqual(
            match_params["raw_json"].obj["canonical_plan"]["trigger_price_source"],
            "n3_action_confirmation_metric.current_price",
        )
        self.assertIn("common_trigger_state", all_sql)
        self.assertIn("common_trigger_match", all_sql)
        self.assertIn("common_event_outbox", all_sql)
        self.assertEqual(all_sql.count("INSERT INTO common_trigger_match"), 1)
        self.assertNotIn("common_event_inbox", all_sql)
        self.assertNotIn("common_event_consumer_checkpoint", all_sql)
        self.assertNotIn("stock_action_confirmation_projection_metric", all_sql)

    def test_runner_cli_blocks_missing_user_confirmed_before_writes(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "scripts/run_trigger_action_confirmation_metric_once.py",
                "--execute",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("BLOCKED", result.stdout)
        self.assertIn("missing --user-confirmed", result.stdout)

    def test_trigger_run_insert_uses_final_preflight_p1_warning(self) -> None:
        report = sample_report_with_p1()
        dry_run_preflight = build_action_confirmation_metric_preflight_report(report)
        contract = build_action_confirmation_metric_business_execute_contract(
            report,
            dry_run_preflight,
            business_execute_runner_ready=True,
            business_execute_runner="scripts/run_trigger_action_confirmation_metric_once.py",
        )
        final_preflight = build_action_confirmation_metric_execute_final_preflight(
            report,
            dry_run_preflight,
            contract,
            baseline_summary=clean_baseline(),
            rollback_sql_exists=True,
        )
        cur = RecordingCursor()
        insert_action_confirmation_metric_trigger_run(
            cur,
            execute_run_id=DEFAULT_EXECUTE_RUN_ID,
            trigger_context_run=trigger_context_run(),
            projection_run={"projection_run_id": "projection_run"},
            plan_count=2,
            quality_items=final_preflight["quality_items"],
        )

        self.assertEqual(final_preflight["quality"]["p0_count"], 0)
        self.assertEqual(final_preflight["quality"]["p1_count"], 1)
        self.assertEqual(final_preflight["quality"]["p2_count"], 0)
        self.assertEqual(cur.last_params["p0_count"], 0)
        self.assertEqual(cur.last_params["p1_count"], 1)
        self.assertEqual(cur.last_params["p2_count"], 0)

    def test_execute_transaction_updates_run_counts_with_matching_parameters(self) -> None:
        conn = RecordingConnection()

        with patch(
            "ashare_v3.trigger.action_confirmation_metric_execute.audited_n4_trigger_connect",
            return_value=conn,
        ):
            counts = execute_action_confirmation_metric_transaction(
                dsn="postgresql://example",
                execute_run_id=DEFAULT_EXECUTE_RUN_ID,
                trigger_context_run=trigger_context_run(),
                projection_run={"projection_run_id": "projection_run"},
                plan_count=0,
                plans=[],
                quality_items=[],
            )

        self.assertEqual(counts["common_trigger_state"], 0)
        update_params = next(
            params
            for sql, params in conn.cursor_obj.execute_log
            if "UPDATE common_trigger_run" in sql and "trigger_event_outbox_count" in sql
        )
        self.assertEqual(
            update_params,
            (0, 0, 0, DEFAULT_EXECUTE_RUN_ID),
        )
        self.assertEqual(conn.commit_count, 1)


def trigger_context_run() -> dict[str, object]:
    return {
        "run_id": "trigger_context_run",
        "source_condition_run_id": "condition_run",
        "source_trade_date": "20260601",
        "prev_trade_date": "20260601",
        "for_trade_date": "20260602",
        "context_snapshot_row_count": 2,
    }


def metric_plan() -> dict[str, object]:
    return {
        "plan_id": "matched",
        "output_event_type": "TriggerMatched",
        "source_event_id": "snapshot-event-1",
        "source_event_type": "MarketSnapshotUpdated",
        "source_action_confirmation_metric_id": 1001,
        "source_projection_run_id": "projection_run",
        "projection_schema_version": "n3.action_confirmation_metric.v1",
        "source_snapshot_run_id": "snapshot_run",
        "source_snapshot_event_id": "snapshot-event-1",
        "source_today_minute_run_id": "today_minute_run",
        "source_previous_day_minute_run_id": "previous_day_minute_run",
        "asset_kind": "stock",
        "identity_key": "stock:SH:600000",
        "direction": "buy",
        "signal_type": "B_BUY",
        "trigger_mark_candidate": "30m_volume",
        "condition_key": "BUY_HINT",
        "original_condition_key": "BUY_HINT",
        "legacy_signal_type": "BUY_HINT",
        "match_basis": "n3_action_confirmation_metric",
        "trigger_price": 10.5,
        "trigger_price_source": "n3_action_confirmation_metric.current_price",
        "trigger_period": "30m",
        "trigger_bucket": "11:05",
        "trigger_live": True,
        "previous_trigger_live": False,
        "current_status": "matched",
        "previous_status": "inactive",
        "primary_trigger_period": "D",
        "previous_primary_trigger_period": None,
        "triggered_periods": ["D"],
        "triggered_period_details": [
            {
                "period": "D",
                "entity_pass": True,
                "amount_pass": True,
                "status": "triggered",
            }
        ],
        "formal_trigger_period_proof_status": "passed",
        "all_trigger_periods": ["D"],
        "previous_all_trigger_periods": [],
        "projection_30m_flag": True,
        "projection_30m_type": "volume_up",
        "previous_projection_30m_flag": False,
        "previous_projection_30m_type": "none",
        "previous_trigger_mark_candidate": None,
        "state_change_reason": "activated",
        "data_quality_status": "passed",
        "metric_quality_status": "passed",
        "metric_ready": True,
        "context_snapshot_id": 11,
        "source_condition_run_id": "condition_run",
        "source_condition_pool_id": 12,
        "source_condition_basis_id": 13,
        "source_minute_target_scope_id": 14,
        "source_market_subscription_id": 15,
        "context_hash": "context-hash",
        "metric_trace": {
            "current_price": 10.5,
            "source_fact_ids": {"snapshot_id": 1},
        },
        "period_trigger_baseline_trace": {},
    }


def sample_report_with_p1() -> dict[str, object]:
    return build_action_confirmation_metric_dry_run_report(
        trigger_context_run_id="trigger_context_run",
        projection_run_id="projection_run",
        source_condition_run_id="condition_run",
        source_subscription_run_id="subscription_run",
        source_snapshot_run_id="snapshot_run",
        for_trade_date="20260602",
        trigger_run={"run_id": "trigger_context_run", "status": "passed"},
        context_rows=[
            {
                "trigger_context_id": 11,
                "run_id": "trigger_context_run",
                "source_condition_run_id": "condition_run",
                "source_condition_pool_id": 12,
                "source_condition_basis_id": 13,
                "source_minute_target_scope_id": 14,
                "source_market_subscription_id": 15,
                "for_trade_date": "20260602",
                "source_trade_date": "20260601",
                "prev_trade_date": "20260601",
                "asset_kind": "stock",
                "identity_key": "stock:SH:600000",
                "direction": "buy",
                "condition_key": "BUY_HINT",
                "allowed_signal_types": ["BUY_HINT"],
                "context_hash": "context-hash",
                "quality_status": "passed",
                "period_trigger_baseline_json": {},
            }
        ],
        metric_rows=[metric_row_for_report("stock:SH:600001")],
        before_row_counts=guard_counts(),
        after_row_counts=guard_counts(),
    )


def metric_row_for_report(identity_key: str) -> dict[str, object]:
    return {
        "action_confirmation_metric_id": 3001,
        "projection_run_id": "projection_run",
        "projection_schema_version": "n3.action_confirmation_metric.v1",
        "source_condition_run_id": "condition_run",
        "source_subscription_run_id": "subscription_run",
        "source_snapshot_run_id": "snapshot_run",
        "source_snapshot_event_id": f"evt-{identity_key}",
        "source_today_minute_run_id": "today_run",
        "source_previous_day_minute_run_id": "previous_run",
        "for_trade_date": "20260602",
        "trade_date": "20260602",
        "asset_kind": "stock",
        "identity_key": identity_key,
        "metric_time": "2026-06-02T11:05:00+08:00",
        "metric_minute_label": "11:05",
        "current_price": 10.5,
        "buy_30m_price_pass": False,
        "buy_5m_amount_pass": False,
        "sell_30m_price_pass": False,
        "sell_5m_amount_pass": False,
        "metric_quality_status": "passed",
        "metric_ready": True,
        "raw_json": {},
    }


def clean_baseline() -> dict[str, int]:
    return {
        "execute_run_common_trigger_run": 0,
        "execute_run_quality": 0,
        "execute_run_state": 0,
        "execute_run_match": 0,
        "execute_run_outbox": 0,
        "execute_run_outbox_delivered_or_delivering": 0,
        "execute_run_inbox": 0,
        "execute_run_checkpoint_refs": 0,
        "downstream_inbox_for_execute_run": 0,
        "downstream_checkpoint_refs": 0,
        "n5_action_run_refs": 0,
    }


def guard_counts() -> dict[str, dict[str, object]]:
    return {
        "common_event_inbox": {"exists": True, "row_count": 1, "status": "present"},
        "common_event_consumer_checkpoint": {"exists": True, "row_count": 2, "status": "present"},
        "common_trigger_state": {"exists": True, "row_count": 3, "status": "present"},
        "common_trigger_match": {"exists": True, "row_count": 4, "status": "present"},
        "common_event_outbox": {"exists": True, "row_count": 5, "status": "present"},
    }


class RecordingCursor:
    def __init__(self) -> None:
        self.sql_log: list[str] = []
        self.execute_log: list[tuple[str, object]] = []
        self.last_sql = ""
        self.last_params: object = None
        self._next_row: dict[str, object] = {}

    def execute(self, sql: str, params: object = None) -> None:
        self.sql_log.append(sql)
        self.execute_log.append((sql, params))
        self.last_sql = sql
        self.last_params = params
        if "RETURNING trigger_state_id" in sql:
            self._next_row = {"trigger_state_id": 101}
        elif "RETURNING trigger_match_id" in sql:
            self._next_row = {"trigger_match_id": 202}
        elif "RETURNING event_id" in sql:
            self._next_row = {"event_id": "evt_recorded"}
        else:
            self._next_row = {"row_count": 0, "exists": False}

    def fetchone(self) -> dict[str, object]:
        return self._next_row

    def __enter__(self) -> "RecordingCursor":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class RecordingConnection:
    def __init__(self) -> None:
        self.cursor_obj = RecordingCursor()
        self.commit_count = 0

    def cursor(self) -> RecordingCursor:
        return self.cursor_obj

    def commit(self) -> None:
        self.commit_count += 1

    def __enter__(self) -> "RecordingConnection":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


if __name__ == "__main__":
    unittest.main()
