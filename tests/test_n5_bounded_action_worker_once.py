import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from ashare_v3.runtime.bounded_worker_control import BoundedResult, SingletonLockHeld

import run_n5_bounded_action_worker_once as n5_worker


TRADE_DATE = "20260617"
SOURCE_TRIGGER_RUN_ID = "trigger-run-001"
METRIC_RUN_ID = "metric-run-001"
ACTION_RUN_ID = "action-run-001"
CONSUMER_NAME = "n5-pr4-consumer"


class FakeChildResult:
    def __init__(self, result=BoundedResult.PASS, returncode=0, timed_out=False):
        self.result = result
        self.returncode = returncode
        self.timed_out = timed_out
        self.stdout_tail = ""
        self.stderr_tail = ""


@contextmanager
def null_lock(_path):
    yield


def conflicting_lock(_path):
    raise SingletonLockHeld(_path)


def candidate(event_id="evt-1", outbox_id=1, partition_key="stock:SH:600000"):
    return {
        "outbox_id": outbox_id,
        "event_id": event_id,
        "event_type": "TriggerMatched",
        "event_schema_version": "v1",
        "trade_date": TRADE_DATE,
        "asset_kind": "stock",
        "identity_key": "stock:SH:600000",
        "event_time": "2026-06-17T10:00:00+08:00",
        "source_layer": "N4_trigger",
        "source_run_id": SOURCE_TRIGGER_RUN_ID,
        "dedup_key": f"dedup-{event_id}",
        "partition_key": partition_key,
        "status": "pending",
        "payload_json": {
            "trade_date": TRADE_DATE,
            "trigger_state_id": 11,
            "trigger_match_id": 22,
            "source_trigger_match_id": 22,
            "asset_kind": "stock",
            "identity_key": "stock:SH:600000",
            "direction": "buy",
            "signal_type": "B_BUY",
            "condition_key": "BUY_HINT",
        },
    }


def candidate_without_payload_trade_date():
    row = candidate()
    row["payload_json"] = dict(row["payload_json"])
    row["payload_json"].pop("trade_date", None)
    return row


def candidate_with_metric_ref(event_id="evt-1", outbox_id=1, metric_id=101):
    row = candidate(event_id=event_id, outbox_id=outbox_id)
    row["payload_json"] = dict(row["payload_json"])
    row["payload_json"]["source_action_confirmation_metric_id"] = metric_id
    row["payload_json"]["source_projection_run_id"] = METRIC_RUN_ID
    return row


def candidate_with_trigger_ids(event_id, outbox_id, *, trigger_state_id, trigger_match_id):
    row = candidate(event_id=event_id, outbox_id=outbox_id)
    row["payload_json"] = dict(row["payload_json"])
    row["payload_json"]["trigger_state_id"] = trigger_state_id
    row["payload_json"]["trigger_match_id"] = trigger_match_id
    row["payload_json"]["source_trigger_match_id"] = trigger_match_id
    return row


def joined_trigger_state(for_trade_date=TRADE_DATE, current_status="matched", last_trigger_match_id=22):
    return {
        "trigger_state_id": 11,
        "run_id": SOURCE_TRIGGER_RUN_ID,
        "for_trade_date": for_trade_date,
        "current_status": current_status,
        "last_trigger_match_id": last_trigger_match_id,
    }


def joined_trigger_match(for_trade_date=TRADE_DATE):
    return {
        "trigger_match_id": 22,
        "trigger_state_id": 11,
        "run_id": SOURCE_TRIGGER_RUN_ID,
        "for_trade_date": for_trade_date,
    }


class FakeTriggerProofCursor:
    def __init__(self, *, state_row=None, match_row=None):
        self.state_row = state_row
        self.match_row = match_row
        self.result = None
        self.queries = []

    def execute(self, sql, params):
        self.queries.append((sql, params))
        if "FROM common_trigger_state" in sql:
            self.result = self.state_row
        elif "FROM common_trigger_match" in sql:
            self.result = self.match_row
        else:
            raise AssertionError(f"unexpected query: {sql}")

    def fetchone(self):
        return self.result


class FakeTriggerStateCursor:
    def __init__(self, state_by_id):
        self.state_by_id = {str(key): value for key, value in state_by_id.items()}
        self.result = None
        self.queries = []

    def execute(self, sql, params):
        self.queries.append((sql, params))
        if "FROM common_trigger_state" not in sql:
            raise AssertionError(f"unexpected query: {sql}")
        self.result = self.state_by_id.get(str((params or [""])[0]))

    def fetchone(self):
        return self.result


def metric_preflight_row(metric_id=101, projection_run_id=METRIC_RUN_ID):
    return {
        "action_confirmation_metric_id": metric_id,
        "projection_run_id": projection_run_id,
        "for_trade_date": TRADE_DATE,
        "identity_key": "stock:SH:600000",
        "direction": "buy",
        "signal_type": "B_BUY",
        "condition_key": "BUY_HINT",
        "metric_time": "2026-06-17T10:00:00+08:00",
        "all_periods_pass": True,
    }


class MetricPreflightCursor:
    def __init__(self, metric_rows=None, *, allow_full_join=False):
        self.metric_rows = list(metric_rows or [])
        self.allow_full_join = allow_full_join
        self.result = []
        self.calls = []
        self.full_metric_run_fetches = 0

    def execute(self, sql, params=None):
        lowered = " ".join(str(sql).lower().split())
        self.calls.append((sql, params))
        is_direct_lookup = "action_confirmation_metric_id = any" in lowered
        is_full_metric_run_fetch = "projection_run_id = any" in lowered and not is_direct_lookup
        if is_full_metric_run_fetch:
            self.full_metric_run_fetches += 1
            if not self.allow_full_join:
                raise AssertionError("fast path must not fetch the full metric run")
            run_ids = {str(item) for item in (params or ([],))[0]}
            self.result = [row for row in self.metric_rows if str(row.get("projection_run_id") or "") in run_ids]
            return
        if is_direct_lookup:
            metric_ids = {str(item) for item in (params or ([],))[0]}
            run_ids = None
            if params is not None and len(params) > 1:
                run_ids = {str(item) for item in params[1]}
            self.result = [
                row
                for row in self.metric_rows
                if str(row.get("action_confirmation_metric_id") or "") in metric_ids
                and (run_ids is None or str(row.get("projection_run_id") or "") in run_ids)
            ]
            return
        raise AssertionError(f"unexpected query: {sql}")

    def fetchall(self):
        return list(self.result)


def preflight_result(**overrides):
    rows = overrides.pop("candidate_rows", [candidate()])
    event_counts = overrides.pop(
        "action_event_counts",
        {"ActionExecuted": 1, "ActionBlocked": 0, "ActionSkipped": 0, "ActionEligible": 0},
    )
    result = {
        "candidate_rows": rows,
        "candidate_total": len(rows),
        "candidate_event_ids": [str(row["event_id"]) for row in rows],
        "candidate_partitions": sorted({str(row["partition_key"]) for row in rows}),
        "source_query_filter": {},
        "consumer_scope": {"fresh": True, "existing_inbox_count": 0, "existing_checkpoint_count": 0},
        "trade_date_proof": {
            "passed": True,
            "proof": "joined_trigger_rows",
            "trigger_match_for_trade_date": TRADE_DATE,
            "trigger_state_for_trade_date": TRADE_DATE,
            "joined_proof_count": len(rows),
            "joined_proof_sample": [
                {
                    "event_id": str(row["event_id"]),
                    "trigger_match_for_trade_date": TRADE_DATE,
                    "trigger_state_for_trade_date": TRADE_DATE,
                }
                for row in rows
            ],
        },
        "metric_preflight": {
            "passed": True,
            "metric_run_id": METRIC_RUN_ID,
            "n4_trigger_matched_rows": len(rows),
            "joined_n4_rows": len(rows),
            "missing_n4_rows": 0,
            "duplicate_join_key_count": 0,
        },
        "stale_trigger_preflight": {"passed": True, "checked_count": len(rows), "trigger_state_for_trade_date": TRADE_DATE},
        "action_event_counts": event_counts,
        "action_eligible_zero": {"passed": int(event_counts.get("ActionEligible") or 0) == 0, "count": int(event_counts.get("ActionEligible") or 0)},
    }
    result.update(overrides)
    return result


def committed_post_check(action_eligible=0):
    return {
        "state": "committed",
        "action_event_counts": {
            "ActionExecuted": 1,
            "ActionBlocked": 0,
            "ActionSkipped": 0,
            "ActionEligible": action_eligible,
        },
        "downstream_refs": {},
    }


def rolled_back_post_check(_context=None, _preflight=None):
    return {"state": "rolled_back", "action_event_counts": n5_worker.zero_action_event_counts(), "downstream_refs": {}}


def unresolved_post_check(_context=None, _preflight=None):
    return {"state": "unresolved", "action_event_counts": n5_worker.zero_action_event_counts(), "downstream_refs": {}}


class N5BoundedActionWorkerOnceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.docs_root = self.root / "docs"
        self.sql_root = self.root / "sql"
        self.status_json = self.root / "status.json"
        self.manifest_json = self.root / "manifest.json"
        self.rollback_sql = self.root / "rollback.sql"
        self.child_calls = []

    def tearDown(self):
        self.tmp.cleanup()

    def base_argv(self, *extra):
        return [
            "--for-trade-date",
            TRADE_DATE,
            "--source-trigger-run-id",
            SOURCE_TRIGGER_RUN_ID,
            "--source-metric-run-id",
            METRIC_RUN_ID,
            "--projection-run-id",
            METRIC_RUN_ID,
            "--action-run-id",
            ACTION_RUN_ID,
            "--consumer-name",
            CONSUMER_NAME,
            "--source-event-type",
            "TriggerMatched",
            "--dsn",
            "postgresql://unit-test",
            "--status-json",
            str(self.status_json),
            "--manifest-json",
            str(self.manifest_json),
            "--rollback-sql-path",
            str(self.rollback_sql),
            "--docs-root",
            str(self.docs_root),
            "--sql-root",
            str(self.sql_root),
            "--python-executable",
            "/usr/bin/python3",
            *extra,
        ]

    def preflight_provider(self, _context):
        return preflight_result()

    def passing_child(self, command, timeout_seconds):
        self.child_calls.append((command, timeout_seconds))
        report_path = Path(command[command.index("--json-report-path") + 1])
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(
                {
                    "action_run_id": ACTION_RUN_ID,
                    "smoke_run_id": ACTION_RUN_ID,
                    "action_event_counts": {
                        "ActionExecuted": 1,
                        "ActionBlocked": 0,
                        "ActionSkipped": 0,
                        "ActionEligible": 0,
                    },
                }
            ),
            encoding="utf-8",
        )
        return FakeChildResult()

    def run_worker(self, argv=None, **overrides):
        kwargs = {
            "argv": argv if argv is not None else self.base_argv(),
            "repo_root": self.root,
            "preflight_provider": self.preflight_provider,
            "command_runner": self.passing_child,
            "post_check_provider": lambda _context, _preflight: committed_post_check(),
            "lock_acquirer": null_lock,
        }
        kwargs.update(overrides)
        return n5_worker.run_n5_bounded_action_worker_once(**kwargs)

    def context(self, *extra):
        args = n5_worker.build_arg_parser().parse_args(self.base_argv("--execute", "--user-confirmed", *extra))
        lineage = n5_worker.build_explicit_lineage(args)
        return n5_worker.build_n5_bounded_context(lineage, args, repo_root=self.root)

    def test_live_window_plan_summary_counts_multi_action_metrics(self):
        row = candidate_with_metric_ref(event_id="evt-live-window", outbox_id=1, metric_id=338338)
        row["asset_kind"] = "index"
        row["identity_key"] = "index:SH:000300"
        row["event_time"] = "2026-06-22T13:56:00+08:00"
        row["payload_json"].update(
            {
                "trade_date": "20260622",
                "asset_kind": "index",
                "identity_key": "index:SH:000300",
                "condition_key": "BUY:M",
                "trigger_time": "2026-06-22T13:56:00+08:00",
                "current_status": "matched",
                "trigger_live": True,
                "trigger_period": "M",
                "triggered_periods": ["M"],
                "all_trigger_periods": ["M"],
                "primary_trigger_period": "M",
            }
        )

        def metric(metric_id, metric_time, minute_label, *, buy_pass):
            return {
                "asset_kind": "index",
                "action_confirmation_metric_id": metric_id,
                "projection_run_id": METRIC_RUN_ID,
                "identity_key": "index:SH:000300",
                "metric_ready": True,
                "metric_quality_status": "passed",
                "metric_time": metric_time,
                "metric_minute_label": minute_label,
                "buy_120m_price_pass": buy_pass,
                "buy_30m_price_pass": buy_pass,
                "buy_5m_price_pass": buy_pass,
                "buy_5m_amount_pass": buy_pass,
                "buy_1m_price_pass": buy_pass,
                "buy_1m_amount_pass": buy_pass,
                "current_30m_virtual_amount": "1200",
                "previous_day_same_window_amount": "1000",
                "previous_30m_full_amount": "1000",
                "virtual_amount_policy_version": "previous_day_same_window_elapsed_ratio_v1",
                "source_fact_ids": {"source_snapshot_id": 1},
            }

        first_metric = metric(338338, "2026-06-22T13:56:00+08:00", "13:56", buy_pass=False)
        pass_1401 = metric(338343, "2026-06-22T14:01:00+08:00", "14:01", buy_pass=True)
        pass_1404 = metric(338346, "2026-06-22T14:04:00+08:00", "14:04", buy_pass=True)

        counts, live_summary = n5_worker._build_action_plan_summaries(
            self.context("--current-only-trigger-matched"),
            [row],
            {("index", "338338"): first_metric},
            {("index", "index:SH:000300"): [first_metric, pass_1401, pass_1404]},
        )

        self.assertEqual(counts["ActionExecuted"], 2)
        self.assertEqual(live_summary["executed_from_window"], 2)
        self.assertEqual(live_summary["executed_metric_count"], 2)
        self.assertEqual(live_summary["multi_action_trigger_count"], 1)
        self.assertEqual(live_summary["max_actions_per_trigger"], 2)

    def test_current_only_filter_selects_current_rows_and_records_excluded_stale(self):
        rows = [
            candidate_with_trigger_ids("evt-current", 1, trigger_state_id=11, trigger_match_id=22),
            candidate_with_trigger_ids("evt-inactive", 2, trigger_state_id=12, trigger_match_id=23),
            candidate_with_trigger_ids("evt-old-match", 3, trigger_state_id=13, trigger_match_id=24),
        ]
        cursor = FakeTriggerStateCursor(
            {
                11: joined_trigger_state(current_status="matched", last_trigger_match_id=22),
                12: dict(joined_trigger_state(current_status="inactive", last_trigger_match_id=23), trigger_state_id=12),
                13: dict(joined_trigger_state(current_status="matched", last_trigger_match_id=999), trigger_state_id=13),
            }
        )

        selected, summary = n5_worker._filter_current_trigger_matched_rows(cursor, self.context("--current-only-trigger-matched"), rows)

        self.assertEqual([row["event_id"] for row in selected], ["evt-current"])
        self.assertTrue(summary["passed"])
        self.assertEqual(summary["source_candidate_count"], 3)
        self.assertEqual(summary["selected_current_count"], 1)
        self.assertEqual(summary["excluded_stale_count"], 2)
        self.assertEqual(summary["stale_reason_counts"]["current_status_not_matched"], 1)
        self.assertEqual(summary["stale_reason_counts"]["last_trigger_match_id_mismatch"], 1)

    def test_current_only_filter_blocks_when_no_current_rows(self):
        rows = [candidate_with_trigger_ids("evt-inactive", 1, trigger_state_id=12, trigger_match_id=23)]
        cursor = FakeTriggerStateCursor(
            {12: dict(joined_trigger_state(current_status="inactive", last_trigger_match_id=23), trigger_state_id=12)}
        )

        selected, summary = n5_worker._filter_current_trigger_matched_rows(cursor, self.context("--current-only-trigger-matched"), rows)

        self.assertEqual(selected, [])
        self.assertFalse(summary["passed"])
        self.assertEqual(summary["reason"], "current_only_no_current_trigger_matched")
        reason = n5_worker.preflight_block_reason(
            preflight_result(
                candidate_rows=[],
                current_only_trigger_matched_filter=summary,
                trade_date_proof={"passed": True},
                metric_preflight={"passed": True},
                stale_trigger_preflight={"passed": True},
                action_event_counts=n5_worker.zero_action_event_counts(),
            ),
            max_events=10,
        )
        self.assertEqual(reason, "current_only_no_current_trigger_matched")

    def test_metric_preflight_uses_direct_payload_metric_id_fast_path(self):
        rows = [
            candidate_with_metric_ref(event_id="evt-fast-1", outbox_id=1, metric_id=101),
            candidate_with_metric_ref(event_id="evt-fast-2", outbox_id=2, metric_id=101),
        ]
        cursor = MetricPreflightCursor([metric_preflight_row(metric_id=101)])

        summary, enriched_rows, metric_facts, _metric_facts_by_identity = n5_worker._verify_metric_preflight(cursor, self.context(), rows)

        self.assertTrue(summary["passed"])
        self.assertEqual(summary["join_policy"], "direct_payload_metric_id")
        self.assertTrue(summary["full_metric_run_join_skipped"])
        self.assertEqual(summary["n4_trigger_matched_rows"], 2)
        self.assertEqual(summary["joined_n4_rows"], 2)
        self.assertEqual(summary["missing_n4_rows"], 0)
        self.assertEqual(summary["direct_metric_fact_rows"], 1)
        self.assertEqual(len(enriched_rows), 2)
        self.assertEqual(len(metric_facts), 1)
        self.assertEqual(cursor.full_metric_run_fetches, 0)

    def test_metric_preflight_missing_direct_metric_fact_blocks_without_full_join(self):
        rows = [candidate_with_metric_ref(event_id="evt-missing", outbox_id=1, metric_id=404)]
        cursor = MetricPreflightCursor([])

        summary, enriched_rows, metric_facts, _metric_facts_by_identity = n5_worker._verify_metric_preflight(cursor, self.context(), rows)

        self.assertFalse(summary["passed"])
        self.assertEqual(summary["join_policy"], "direct_payload_metric_id")
        self.assertTrue(summary["full_metric_run_join_skipped"])
        self.assertEqual(summary["n4_trigger_matched_rows"], 1)
        self.assertEqual(summary["joined_n4_rows"], 0)
        self.assertEqual(summary["missing_n4_rows"], 1)
        self.assertEqual(len(enriched_rows), 1)
        self.assertEqual(metric_facts, {})
        self.assertEqual(cursor.full_metric_run_fetches, 0)

    def test_metric_preflight_projection_run_id_mismatch_blocks_without_full_join(self):
        rows = [candidate_with_metric_ref(event_id="evt-mismatch", outbox_id=1, metric_id=101)]
        cursor = MetricPreflightCursor([metric_preflight_row(metric_id=101, projection_run_id="other-metric-run")])

        summary, _enriched_rows, metric_facts, _metric_facts_by_identity = n5_worker._verify_metric_preflight(cursor, self.context(), rows)

        self.assertFalse(summary["passed"])
        self.assertEqual(summary["missing_n4_rows"], 1)
        self.assertEqual(metric_facts, {})
        self.assertEqual(cursor.full_metric_run_fetches, 0)

    def test_metric_preflight_payload_missing_metric_id_keeps_full_join_fallback(self):
        rows = [candidate(event_id="evt-no-ref", outbox_id=1)]
        cursor = MetricPreflightCursor([], allow_full_join=True)

        summary, _enriched_rows, _metric_facts, _metric_facts_by_identity = n5_worker._verify_metric_preflight(cursor, self.context(), rows)

        self.assertFalse(summary["passed"])
        self.assertGreater(cursor.full_metric_run_fetches, 0)

    def test_plan_only_does_not_execute_action_child(self):
        result = self.run_worker()

        self.assertEqual(result["result"], BoundedResult.NOOP)
        self.assertEqual(result["stop_reason"], "plan_only")
        self.assertFalse(result["child_invoked"])
        self.assertEqual(self.child_calls, [])

    def test_plan_only_does_not_acquire_global_lock(self):
        def fail_if_called(_path):
            raise AssertionError("plan-only must not acquire global lock")

        result = self.run_worker(lock_acquirer=fail_if_called)

        self.assertEqual(result["result"], BoundedResult.NOOP)
        self.assertEqual(result["stop_reason"], "plan_only")
        self.assertFalse(result["child_invoked"])
        self.assertEqual(self.child_calls, [])

    def test_execute_requires_user_confirmed(self):
        result = self.run_worker(argv=self.base_argv("--execute"))

        self.assertEqual(result["result"], BoundedResult.BLOCKED)
        self.assertEqual(result["stop_reason"], "execute_requires_user_confirmed")
        self.assertFalse(result["child_invoked"])

    def test_missing_lineage_blocks_before_child(self):
        argv = self.base_argv("--execute", "--user-confirmed")
        idx = argv.index("--action-run-id")
        del argv[idx : idx + 2]

        result = self.run_worker(argv=argv)

        self.assertEqual(result["result"], BoundedResult.BLOCKED)
        self.assertIn("action_run_id", result["stop_reason"])
        self.assertFalse(result["child_invoked"])

    def test_non_trigger_matched_blocks_before_child(self):
        argv = self.base_argv("--execute", "--user-confirmed")
        argv[argv.index("--source-event-type") + 1] = "TriggerStateChanged"

        result = self.run_worker(argv=argv)

        self.assertEqual(result["result"], BoundedResult.BLOCKED)
        self.assertIn("source_event_type", result["stop_reason"])
        self.assertFalse(result["child_invoked"])

    def test_source_metric_run_id_must_equal_projection_run_id(self):
        argv = self.base_argv("--execute", "--user-confirmed")
        argv[argv.index("--projection-run-id") + 1] = "metric-run-002"

        result = self.run_worker(argv=argv)

        self.assertEqual(result["result"], BoundedResult.BLOCKED)
        self.assertIn("source_metric_run_id", result["stop_reason"])
        self.assertFalse(result["child_invoked"])

    def test_singleton_conflict_is_noop(self):
        result = self.run_worker(argv=self.base_argv("--execute", "--user-confirmed"), lock_acquirer=conflicting_lock)

        self.assertEqual(result["result"], BoundedResult.NOOP)
        self.assertEqual(result["stop_reason"], "singleton_lock_held")
        self.assertFalse(result["child_invoked"])

    def test_stop_file_before_child_is_noop(self):
        stop_file = self.root / "stop"
        stop_file.write_text("stop\n", encoding="utf-8")

        result = self.run_worker(argv=self.base_argv("--execute", "--user-confirmed", "--stop-file", str(stop_file)))

        self.assertEqual(result["result"], BoundedResult.NOOP)
        self.assertEqual(result["stop_reason"], "stop_file_present")
        self.assertFalse(result["child_invoked"])

    def test_deadline_before_child_blocks(self):
        result = self.run_worker(argv=self.base_argv("--execute", "--user-confirmed", "--max-runtime-seconds", "0"))

        self.assertEqual(result["result"], BoundedResult.BLOCKED)
        self.assertEqual(result["stop_reason"], "deadline_before_child")
        self.assertFalse(result["child_invoked"])

    def test_max_events_overflow_blocks_before_child(self):
        result = self.run_worker(
            argv=self.base_argv("--execute", "--user-confirmed", "--max-events", "1"),
            preflight_provider=lambda _context: preflight_result(candidate_rows=[candidate("evt-1", 1), candidate("evt-2", 2)]),
        )

        self.assertEqual(result["result"], BoundedResult.BLOCKED)
        self.assertEqual(result["stop_reason"], "candidate_total_exceeds_max_events")
        self.assertEqual(result["candidate_total"], 2)
        self.assertFalse(result["child_invoked"])

    def test_child_query_filters_equal_count_query_filters(self):
        seen_filters = []

        def provider(context):
            seen_filters.append(n5_worker.build_source_query_filter(context))
            return preflight_result()

        result = self.run_worker(
            argv=self.base_argv("--execute", "--user-confirmed", "--max-events", "10"),
            preflight_provider=provider,
        )

        self.assertEqual(result["result"], BoundedResult.PASS)
        self.assertEqual(
            seen_filters[0],
            {
                "source_layer": "N4_trigger",
                "source_trigger_run_id": SOURCE_TRIGGER_RUN_ID,
                "event_type": "TriggerMatched",
                "status": "pending",
                "consumer_name": CONSUMER_NAME,
                "for_trade_date": TRADE_DATE,
                "uses_limit": False,
                "current_only_trigger_matched": False,
            },
        )
        command = self.child_calls[0][0]
        self.assertIn("--source-trigger-run-id", command)
        self.assertEqual(command[command.index("--source-trigger-run-id") + 1], SOURCE_TRIGGER_RUN_ID)
        self.assertEqual(command[command.index("--source-event-type") + 1], "TriggerMatched")
        self.assertEqual(command[command.index("--consumer-name") + 1], CONSUMER_NAME)
        self.assertEqual(command[command.index("--max-events") + 1], "10")
        self.assertEqual(command[command.index("--heartbeat-interval-seconds") + 1], "10")
        self.assertNotIn("--current-only-trigger-matched", command)

    def test_current_only_child_command_passes_explicit_filter_flag(self):
        result = self.run_worker(
            argv=self.base_argv("--execute", "--user-confirmed", "--max-runtime-seconds", "600.0", "--current-only-trigger-matched"),
            preflight_provider=lambda _context: preflight_result(
                current_only_trigger_matched_filter={
                    "enabled": True,
                    "passed": True,
                    "source_candidate_count": 2,
                    "selected_current_count": 1,
                    "excluded_stale_count": 1,
                    "filter_applied_before_action_plan": True,
                }
            ),
        )

        command = self.child_calls[0][0]
        self.assertIn("--current-only-trigger-matched", command)
        self.assertEqual(command[command.index("--max-runtime-seconds") + 1], "600")
        self.assertEqual(command[command.index("--heartbeat-interval-seconds") + 1], "10")
        self.assertEqual(result["current_only_trigger_matched_filter"]["excluded_stale_count"], 1)

    def test_child_command_forwards_custom_heartbeat_interval(self):
        self.run_worker(argv=self.base_argv("--execute", "--user-confirmed", "--heartbeat-interval-seconds", "7"))

        command = self.child_calls[0][0]
        self.assertEqual(command[command.index("--heartbeat-interval-seconds") + 1], "7")

    def test_trade_date_mismatch_blocks(self):
        result = self.run_worker(
            argv=self.base_argv("--execute", "--user-confirmed"),
            preflight_provider=lambda _context: preflight_result(trade_date_proof={"passed": False, "reason": "trade_date_mismatch"}),
        )

        self.assertEqual(result["result"], BoundedResult.BLOCKED)
        self.assertEqual(result["stop_reason"], "trade_date_proof_failed")
        self.assertFalse(result["child_invoked"])

    def test_missing_trade_date_proof_blocks(self):
        result = self.run_worker(
            argv=self.base_argv("--execute", "--user-confirmed"),
            preflight_provider=lambda _context: preflight_result(trade_date_proof={"passed": False, "reason": "missing_trade_date_proof"}),
        )

        self.assertEqual(result["result"], BoundedResult.BLOCKED)
        self.assertEqual(result["stop_reason"], "trade_date_proof_failed")
        self.assertFalse(result["child_invoked"])

    def test_preflight_passed_trade_date_without_joined_fields_blocks(self):
        result = self.run_worker(
            argv=self.base_argv("--execute", "--user-confirmed"),
            preflight_provider=lambda _context: preflight_result(trade_date_proof={"passed": True}),
        )

        self.assertEqual(result["result"], BoundedResult.BLOCKED)
        self.assertEqual(result["stop_reason"], "trade_date_proof_failed")
        self.assertFalse(result["child_invoked"])

    def test_payload_missing_trade_date_without_joined_proof_blocks(self):
        cursor = FakeTriggerProofCursor()
        proof = n5_worker._verify_trade_date_proof(cursor, self.context(), [candidate_without_payload_trade_date()])

        self.assertFalse(proof["passed"])
        self.assertEqual(proof["missing_proof_count"], 2)

    def test_payload_missing_trade_date_with_joined_match_and_state_trade_dates_passes(self):
        cursor = FakeTriggerProofCursor(state_row=joined_trigger_state(), match_row=joined_trigger_match())
        proof = n5_worker._verify_trade_date_proof(cursor, self.context(), [candidate_without_payload_trade_date()])

        self.assertTrue(proof["passed"])
        self.assertEqual(proof["joined_proof_count"], 1)
        self.assertEqual(proof["joined_proof_sample"][0]["trigger_match_for_trade_date"], TRADE_DATE)
        self.assertEqual(proof["joined_proof_sample"][0]["trigger_state_for_trade_date"], TRADE_DATE)

    def test_joined_trigger_match_trade_date_mismatch_blocks(self):
        cursor = FakeTriggerProofCursor(state_row=joined_trigger_state(), match_row=joined_trigger_match("20260618"))
        proof = n5_worker._verify_trade_date_proof(cursor, self.context(), [candidate_without_payload_trade_date()])

        self.assertFalse(proof["passed"])
        self.assertEqual(proof["mismatch_count"], 1)
        self.assertEqual(proof["mismatches_sample"][0]["source"], "trigger_match")

    def test_joined_trigger_state_trade_date_mismatch_blocks(self):
        cursor = FakeTriggerProofCursor(state_row=joined_trigger_state("20260618"), match_row=joined_trigger_match())
        proof = n5_worker._verify_trade_date_proof(cursor, self.context(), [candidate_without_payload_trade_date()])

        self.assertFalse(proof["passed"])
        self.assertEqual(proof["mismatch_count"], 1)
        self.assertEqual(proof["mismatches_sample"][0]["source"], "trigger_state")

    def test_payload_trade_date_mismatch_blocks_in_default_proof(self):
        row = candidate()
        row["payload_json"] = dict(row["payload_json"], trade_date="20260618")
        cursor = FakeTriggerProofCursor(state_row=joined_trigger_state(), match_row=joined_trigger_match())
        proof = n5_worker._verify_trade_date_proof(cursor, self.context(), [row])

        self.assertFalse(proof["passed"])
        self.assertEqual(proof["mismatches_sample"][0]["source"], "payload")

    def test_outbox_trade_date_mismatch_blocks_in_default_proof(self):
        row = candidate()
        row["trade_date"] = "20260618"
        cursor = FakeTriggerProofCursor(state_row=joined_trigger_state(), match_row=joined_trigger_match())
        proof = n5_worker._verify_trade_date_proof(cursor, self.context(), [row])

        self.assertFalse(proof["passed"])
        self.assertEqual(proof["mismatches_sample"][0]["source"], "outbox")

    def test_metric_missing_blocks_before_child(self):
        result = self.run_worker(
            argv=self.base_argv("--execute", "--user-confirmed"),
            preflight_provider=lambda _context: preflight_result(metric_preflight={"passed": False, "missing_n4_rows": 1}),
        )

        self.assertEqual(result["result"], BoundedResult.BLOCKED)
        self.assertEqual(result["stop_reason"], "metric_preflight_failed")
        self.assertFalse(result["child_invoked"])

    def test_planning_deadline_blocks_with_status_and_manifest_artifacts(self):
        result = self.run_worker(
            argv=self.base_argv("--execute", "--user-confirmed"),
            preflight_provider=lambda _context: preflight_result(
                planning_deadline={"passed": False, "reason": "planning_deadline_exceeded"},
                metric_preflight={"passed": False, "reason": "planning_deadline_exceeded"},
            ),
        )

        self.assertEqual(result["result"], BoundedResult.BLOCKED)
        self.assertEqual(result["stop_reason"], "planning_deadline_exceeded")
        self.assertFalse(result["child_invoked"])
        self.assertTrue(self.status_json.exists())
        self.assertTrue(self.manifest_json.exists())
        status = json.loads(self.status_json.read_text(encoding="utf-8"))
        self.assertEqual(status["stop_reason"], "planning_deadline_exceeded")

    def test_stale_trigger_blocks_before_child(self):
        result = self.run_worker(
            argv=self.base_argv("--execute", "--user-confirmed"),
            preflight_provider=lambda _context: preflight_result(stale_trigger_preflight={"passed": False, "stale_count": 1}),
        )

        self.assertEqual(result["result"], BoundedResult.BLOCKED)
        self.assertEqual(result["stop_reason"], "stale_trigger_preflight_failed")
        self.assertFalse(result["child_invoked"])

    def test_action_eligible_preflight_is_allowed_for_live_window_tracking(self):
        result = self.run_worker(
            argv=self.base_argv("--execute", "--user-confirmed"),
            preflight_provider=lambda _context: preflight_result(
                action_event_counts={"ActionExecuted": 0, "ActionBlocked": 0, "ActionSkipped": 0, "ActionEligible": 1}
            ),
        )

        self.assertEqual(result["result"], BoundedResult.PASS)
        self.assertTrue(result["child_invoked"])
        self.assertEqual(result["action_event_counts"]["ActionEligible"], 1)
        self.assertEqual(result["live_window_action_summary"]["opened_tracking"], 1)
        self.assertEqual(result["live_window_action_summary"]["still_pending"], 1)

    def test_action_eligible_post_child_is_allowed_for_live_window_tracking(self):
        def child(command, timeout_seconds):
            self.passing_child(command, timeout_seconds)
            report_path = Path(command[command.index("--json-report-path") + 1])
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            payload["action_event_counts"]["ActionEligible"] = 1
            report_path.write_text(json.dumps(payload), encoding="utf-8")
            return FakeChildResult()

        result = self.run_worker(
            argv=self.base_argv("--execute", "--user-confirmed"),
            command_runner=child,
            post_check_provider=lambda _context, _preflight: committed_post_check(action_eligible=1),
        )

        self.assertEqual(result["result"], BoundedResult.PASS)
        self.assertEqual(result["action_event_counts"]["ActionEligible"], 1)

    def test_no_action_eligible_allows_pass(self):
        result = self.run_worker(argv=self.base_argv("--execute", "--user-confirmed"))

        self.assertEqual(result["result"], BoundedResult.PASS)
        self.assertTrue(result["child_invoked"])
        self.assertEqual(result["action_event_counts"]["ActionEligible"], 0)
        self.assertFalse(result["downstream_consumption_allowed"])

    def test_child_timeout_returns_unknown_after_timeout(self):
        result = self.run_worker(
            argv=self.base_argv("--execute", "--user-confirmed"),
            command_runner=lambda _command, _timeout: FakeChildResult(BoundedResult.UNKNOWN_AFTER_TIMEOUT, returncode=None, timed_out=True),
            post_check_provider=lambda _context, _preflight: unresolved_post_check(),
        )

        self.assertEqual(result["result"], BoundedResult.UNKNOWN_AFTER_TIMEOUT)
        self.assertEqual(result["stop_reason"], "child_timeout")
        self.assertTrue(result["requires_post_check"])

    def test_child_exit_one_with_rolled_back_post_check_is_crashed(self):
        result = self.run_worker(
            argv=self.base_argv("--execute", "--user-confirmed"),
            command_runner=lambda _command, _timeout: FakeChildResult(BoundedResult.CRASHED, returncode=1),
            post_check_provider=lambda _context, _preflight: rolled_back_post_check(),
        )

        self.assertEqual(result["result"], BoundedResult.CRASHED)
        self.assertEqual(result["stop_reason"], "child_exit_nonzero")

    def test_unresolved_post_check_is_commit_unknown(self):
        result = self.run_worker(
            argv=self.base_argv("--execute", "--user-confirmed"),
            command_runner=lambda _command, _timeout: FakeChildResult(BoundedResult.CRASHED, returncode=1),
            post_check_provider=lambda _context, _preflight: unresolved_post_check(),
        )

        self.assertEqual(result["result"], BoundedResult.COMMIT_UNKNOWN)
        self.assertTrue(result["requires_post_check"])

    def test_tracking_state_rollback_is_included(self):
        result = self.run_worker(argv=self.base_argv("--execute", "--user-confirmed"))

        self.assertEqual(result["result"], BoundedResult.PASS)
        sql = self.rollback_sql.read_text(encoding="utf-8")
        self.assertIn("common_action_tracking_state", sql)
        self.assertIn("source_trigger_run_id <> :'source_trigger_run_id'", sql)
        self.assertTrue(result["tracking_state_rollback_coverage"]["included"])

    def test_downstream_refs_block_rollback(self):
        sql = n5_worker.build_wrapper_rollback_sql(
            action_run_id=ACTION_RUN_ID,
            source_trigger_run_id=SOURCE_TRIGGER_RUN_ID,
            consumer_name=CONSUMER_NAME,
            candidate_event_ids=["evt-1"],
        )

        self.assertIn("scoped N5 outbox has downstream inbox refs", sql)
        self.assertIn("scoped N5 outbox has downstream checkpoint refs", sql)
        self.assertIn("N5 rollback blocked: downstream table", sql)
        self.assertIn("common_position_state", sql)
        self.assertIn("order", sql)
        self.assertNotIn("DELETE FROM common_trigger_state", sql)
        self.assertNotIn("DELETE FROM user_", sql)

    def test_external_side_effects_are_zero(self):
        result = self.run_worker(argv=self.base_argv("--execute", "--user-confirmed"))

        self.assertEqual(
            result["external_side_effects"],
            {
                "db_write": False,
                "worker_started": False,
                "n6_writes": 0,
                "real_trade_api_calls": 0,
                "sim_writes": 0,
                "voice_writes": 0,
                "mobile_writes": 0,
                "position_writes": 0,
                "order_writes": 0,
            },
        )

    def test_downstream_consumption_is_false(self):
        result = self.run_worker(argv=self.base_argv("--execute", "--user-confirmed"))

        self.assertFalse(result["downstream_consumption_allowed"])

    def test_old_entrypoint_bypass_warning_is_documented(self):
        doc = Path("docs/V3_PHASE1_N5_BOUNDED_ACTION_WORKER_CONTRACT.md")
        self.assertTrue(doc.exists())
        text = doc.read_text(encoding="utf-8")
        self.assertIn("scripts/run_action_consumer_once.py", text)
        self.assertIn("bypass", text.lower())
        self.assertIn("old N5 entries from running in parallel", text)
        self.assertIn("PR-4 is wrapper-only", text)
        self.assertIn("adds no SQL migration", text)
        self.assertIn("does not modify execute.py", text)


if __name__ == "__main__":
    unittest.main()
