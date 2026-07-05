import inspect
import unittest
from datetime import datetime, timezone

from ashare_v3.action.provisional_action_executed_dry_run import (
    ACTION_EXECUTED_PLAN,
    NOT_EXECUTED_RULE_FAILED,
    PENDING_NO_CLOSED_METRIC,
    SKIPPED_INVALID_PAYLOAD,
    build_provisional_action_executed_dry_run_report,
)
from ashare_v3.action.provisional_action_executed import (
    N5P_ACTIONEXECUTED_ALLOWED_WRITE_TABLES,
    N5P_ACTIONEXECUTED_FORBIDDEN_WRITE_TABLES,
    N5PActionExecutedBlocked,
    build_provisional_actionexecuted_once_report,
    build_provisional_actionexecuted_rollback_sql,
    build_n5p_actionexecuted_run_id,
    build_provisional_action_executed_write_plan,
    execute_provisional_action_executed_transaction,
    parse_n5p_actionexecuted_run_id,
)
from scripts.run_n5_provisional_actionexecuted_once import build_parser
from tests.test_provisional_action_executed_dry_run import (
    CONFIRMATION_METRIC_RUN_ID,
    CONFIRMATION_PROJECTION_RUN_ID,
    ELIGIBLE_ACTION_RUN_ID,
    FOR_TRADE_DATE,
    SOURCE_TRIGGER_RUN_ID,
    confirmation_metric_row,
    confirmation_projection_row,
    eligible_row,
    hint_eligible_row,
)


ACTION_RUN_ID = build_n5p_actionexecuted_run_id(for_trade_date=FOR_TRADE_DATE, until_hhmm="1024")
N5_CONFIRMATION_METRIC_V2_KIND = "n5_action_confirmation_metric_v2"


def empty_target_counts() -> dict[str, int]:
    return {
        "common_action_run": 0,
        "common_action_quality_item": 0,
        "stock_action_fact": 0,
        "index_action_fact": 0,
        "board_action_fact": 0,
        "common_action_event": 0,
        "common_event_outbox": 0,
        "common_event_inbox": 0,
        "common_event_consumer_checkpoint": 0,
    }


def action_executed_plans(*, rows=None, metrics=None):
    report = build_provisional_action_executed_dry_run_report(
        actioneligible_rows=rows or [eligible_row(1)],
        confirmation_metric_rows=metrics or [confirmation_metric_row(1)],
        for_trade_date=FOR_TRADE_DATE,
        confirmation_metric_run_id=CONFIRMATION_METRIC_RUN_ID,
        latest_closed_minute="2026-06-24T10:24:00+08:00",
    )
    return report["action_executed_plans"]


def as_n5_v2_action_executed_plans(plans):
    output = []
    for plan in plans:
        payload = dict(plan["payload"])
        payload["source_metric_kind"] = N5_CONFIRMATION_METRIC_V2_KIND
        trace = dict(payload.get("trace") or {})
        source_payload = dict(trace.get("source_actioneligible_payload") or {})
        source_payload["source_metric_kind"] = N5_CONFIRMATION_METRIC_V2_KIND
        trace["source_actioneligible_payload"] = source_payload
        payload["trace"] = trace
        output.append({**plan, "payload": payload})
    return output


def n5_v2_action_executed_plans(*, rows=None, metrics=None):
    return as_n5_v2_action_executed_plans(action_executed_plans(rows=rows, metrics=metrics))


def live_action_executed_plans():
    row = eligible_row(1)
    payload = row["payload_json"]
    if not isinstance(payload, dict):
        raise AssertionError("test helper expected dict payload")
    payload["source_mode"] = "live_current_1m"
    payload["c1_dependency"] = False
    report = build_provisional_action_executed_dry_run_report(
        actioneligible_rows=[row],
        confirmation_metric_rows=[confirmation_metric_row(1, is_closed_1m=False)],
        for_trade_date=FOR_TRADE_DATE,
        confirmation_metric_run_id=CONFIRMATION_METRIC_RUN_ID,
    )
    return as_n5_v2_action_executed_plans(report["action_executed_plans"])


def hint_action_executed_plans():
    report = build_provisional_action_executed_dry_run_report(
        actioneligible_rows=[hint_eligible_row(1, condition_key="BUY_HINT", signal_type="B_BUY")],
        confirmation_metric_rows=[
            confirmation_metric_row(1, condition_key="BUY:D", signal_type="B_BUY")
        ],
        confirmation_projection_rows=[confirmation_projection_row(1, condition_key="BUY_HINT")],
        for_trade_date=FOR_TRADE_DATE,
        confirmation_metric_run_id=CONFIRMATION_METRIC_RUN_ID,
        latest_closed_minute="2026-06-24T10:24:00+08:00",
    )
    return as_n5_v2_action_executed_plans(report["action_executed_plans"])


def hint_rows(count: int):
    return [hint_eligible_row(index, condition_key="BUY_HINT", signal_type="B_BUY") for index in range(1, count + 1)]


def hint_projection_rows(count: int):
    return [confirmation_projection_row(index, condition_key="BUY_HINT") for index in range(1, count + 1)]


def hint_confirmation_metric_rows(count: int):
    return [
        confirmation_metric_row(index, condition_key="BUY:D", signal_type="B_BUY")
        for index in range(1, count + 1)
    ]


def build_plan(plans=None, *, target_counts=None):
    return build_provisional_action_executed_write_plan(
        action_run_id=ACTION_RUN_ID,
        for_trade_date=FOR_TRADE_DATE,
        dry_run_plans=plans if plans is not None else n5_v2_action_executed_plans(),
        target_counts=target_counts or empty_target_counts(),
    )


class FakeCursor:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.params: list[object] = []
        self._next_fact_id = 1000

    def execute(self, sql, params=None):
        self.statements.append(str(sql))
        self.params.append(params)

    def fetchone(self):
        self._next_fact_id += 1
        return (self._next_fact_id,)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeConnection:
    def __init__(self) -> None:
        self.cursor_obj = FakeCursor()
        self.committed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True


class ProvisionalActionExecutedWriteTest(unittest.TestCase):
    def test_run_id_builder_and_parser_fail_closed_for_invalid_values(self) -> None:
        run_id = build_n5p_actionexecuted_run_id(for_trade_date="20260624", until_hhmm="1024")

        parsed = parse_n5p_actionexecuted_run_id(run_id)

        self.assertEqual(parsed["for_trade_date"], "20260624")
        self.assertEqual(parsed["until_hhmm"], "1024")
        self.assertEqual(parsed["mode"], "provisional_executed")
        self.assertEqual(parsed["confirmation_mode"], "intraday_closed_minute")
        with self.assertRaises(N5PActionExecutedBlocked):
            parse_n5p_actionexecuted_run_id("action_provisional_eligible_20260624_until_1024")
        with self.assertRaises(N5PActionExecutedBlocked):
            build_n5p_actionexecuted_run_id(for_trade_date="2026-06-24", until_hhmm="1024")

    def test_clean_target_writes_actionexecuted_run_quality_fact_event_outbox(self) -> None:
        plan = build_plan()
        writes = plan["writes"]
        payload = writes["common_event_outbox"][0]["payload_json"]
        fact = writes["stock_action_fact"][0]

        self.assertEqual(plan["status"], "passed")
        self.assertEqual(plan["action_executed_count"], 1)
        self.assertEqual(plan["event_counts"], {"ActionExecuted": 1})
        self.assertEqual(set(writes), N5P_ACTIONEXECUTED_ALLOWED_WRITE_TABLES)
        self.assertEqual(len(writes["common_action_run"]), 1)
        self.assertEqual(len(writes["common_action_quality_item"]), 1)
        self.assertEqual(len(writes["stock_action_fact"]), 1)
        self.assertEqual(len(writes["common_action_event"]), 1)
        self.assertEqual(len(writes["common_event_outbox"]), 1)
        self.assertEqual(payload["event_type"], "ActionExecuted")
        self.assertTrue(payload["provisional"])
        self.assertEqual(payload["action_confirmation_mode"], "intraday_closed_minute")
        self.assertEqual(payload["action_state"], "executed")
        self.assertEqual(payload["confirmation_status"], "passed")
        self.assertEqual(payload["source_trigger_run_id"], SOURCE_TRIGGER_RUN_ID)
        self.assertEqual(payload["confirmation_metric_run_id"], CONFIRMATION_METRIC_RUN_ID)
        self.assertEqual(payload["action_mark"], "30m_volume")
        self.assertEqual(fact["action_state"], "executed")
        self.assertEqual(fact["confirmation_status"], "passed")
        self.assertEqual(fact["decision_status"], "executed")
        self.assertEqual(fact["action_type"], "buy_candidate")
        self.assertEqual(fact["raw_json"]["plan"]["decision_status"], "executed")
        self.assertEqual(fact["action_mark"], "30m_volume")
        self.assertTrue(fact["closed_minute_required"])
        self.assertTrue(fact["closed_minute_verified"])
        self.assertEqual(fact["last_checked_minute_label"], "10:23")
        self.assertEqual(fact["source_payload_json"]["selected_metric_id"], 900001)
        self.assertEqual(fact["source_payload_json"]["confirmation_metric_id"], 950001)
        for table_name in N5P_ACTIONEXECUTED_FORBIDDEN_WRITE_TABLES:
            self.assertEqual(plan["forbidden_write_counts"][table_name], 0)

    def test_hint_actionexecuted_plan_uses_n5_v2_confirmation_metric_proof(self) -> None:
        plan = build_plan(hint_action_executed_plans())
        writes = plan["writes"]
        payload = writes["common_event_outbox"][0]["payload_json"]
        event = writes["common_action_event"][0]
        fact = writes["stock_action_fact"][0]

        self.assertEqual(plan["event_counts"], {"ActionExecuted": 1})
        self.assertEqual(payload["event_type"], "ActionExecuted")
        self.assertEqual(payload["source_metric_kind"], N5_CONFIRMATION_METRIC_V2_KIND)
        self.assertEqual(payload["source_metric_run_id"], CONFIRMATION_METRIC_RUN_ID)
        self.assertEqual(payload["confirmation_metric_run_id"], CONFIRMATION_METRIC_RUN_ID)
        self.assertEqual(payload["confirmation_metric_id"], 950001)
        self.assertNotIn("source_fact_kind", payload)
        self.assertNotIn("confirmation_projection_run_id", payload)
        self.assertEqual(payload["action_mark"], "30m_volume")
        self.assertEqual(event["event_type"], "ActionExecuted")
        self.assertNotEqual(event["payload_json"].get("decision_status"), "confirmed")
        self.assertEqual(fact["action_state"], "executed")
        self.assertEqual(fact["decision_status"], "executed")
        self.assertEqual(fact["action_type"], "buy_candidate")
        self.assertEqual(payload["action_type"], "buy")
        self.assertEqual(fact["raw_json"]["plan"]["decision_status"], "executed")
        self.assertEqual(fact["source_payload_json"]["source_metric_kind"], N5_CONFIRMATION_METRIC_V2_KIND)
        self.assertEqual(fact["source_payload_json"]["confirmation_metric_id"], 950001)
        self.assertEqual(
            fact["trace_json"]["trace"]["source_actioneligible_payload"]["projection_id"],
            880001,
        )

    def test_realtime_or_unclosed_actionexecuted_payload_is_rejected_by_writer(self) -> None:
        plans = n5_v2_action_executed_plans()
        realtime_payload = dict(plans[0]["payload"])
        realtime_payload["action_confirmation_mode"] = "intraday_realtime_metric"
        realtime_payload["is_closed_1m"] = False
        realtime_plan = {**plans[0], "payload": realtime_payload}

        with self.assertRaises(N5PActionExecutedBlocked) as raised:
            build_plan([realtime_plan])

        self.assertIn("closed N3P confirmation metric", str(raised.exception))

    def test_n3p_trigger_proof_is_rejected_as_actionexecuted_final_proof(self) -> None:
        plans = action_executed_plans()
        trigger_proof_payload = dict(plans[0]["payload"])
        trigger_proof_payload.update(
            {
                "metric_role": "trigger_proof",
                "proof_owner": "N3",
                "proof_consumer": "N4",
                "not_n5_final_proof": True,
                "source_trigger_proof_kind": "n3p_formal_amount_chain",
            }
        )
        trigger_proof_plan = {**plans[0], "payload": trigger_proof_payload}

        with self.assertRaises(N5PActionExecutedBlocked) as raised:
            build_plan([trigger_proof_plan])

        self.assertIn("BLOCKED_N3P_NOT_ACTION_CONFIRMATION_PROOF", str(raised.exception))

    def test_b2_projection_proof_is_rejected_as_actionexecuted_final_proof(self) -> None:
        plans = action_executed_plans()
        projection_proof_payload = dict(plans[0]["payload"])
        projection_proof_payload.update(
            {
                "source_fact_kind": "realtime_projection_metric",
                "metric_role": "projection_trigger_proof",
                "proof_owner": "N3",
                "proof_consumer": "N4",
                "proof_kind": "n3_b2_30m_projection",
                "not_n5_final_proof": True,
            }
        )
        projection_proof_plan = {**plans[0], "payload": projection_proof_payload}

        with self.assertRaises(N5PActionExecutedBlocked) as raised:
            build_plan([projection_proof_plan])

        self.assertIn("B2 projection", str(raised.exception))

    def test_dirty_target_fails_closed_before_write_planning(self) -> None:
        for table_name in empty_target_counts():
            with self.subTest(table_name=table_name):
                with self.assertRaises(N5PActionExecutedBlocked) as raised:
                    build_plan(target_counts={**empty_target_counts(), table_name: 1})
                self.assertIn("BLOCKED_TARGET_NOT_EMPTY", str(raised.exception))

    def test_only_actionexecuted_decisions_write_rows(self) -> None:
        skipped = [
            {"decision": PENDING_NO_CLOSED_METRIC, "payload": {"event_type": "ActionExecuted"}},
            {"decision": NOT_EXECUTED_RULE_FAILED, "payload": {"event_type": "ActionExecuted"}},
            {"decision": SKIPPED_INVALID_PAYLOAD, "payload": {"event_type": "ActionExecuted"}},
        ]

        plan = build_plan(skipped)

        self.assertEqual(plan["action_executed_count"], 0)
        self.assertEqual(plan["skipped_decision_counts"][PENDING_NO_CLOSED_METRIC], 1)
        self.assertEqual(plan["writes"]["common_action_event"], [])
        self.assertEqual(plan["writes"]["common_event_outbox"], [])

    def test_duplicate_actionexecuted_plan_is_not_written_twice(self) -> None:
        plans = n5_v2_action_executed_plans()

        plan = build_plan([plans[0], dict(plans[0])])

        self.assertEqual(plan["input_plan_count"], 2)
        self.assertEqual(plan["action_executed_count"], 1)
        self.assertEqual(plan["skipped_decision_counts"]["SKIPPED_DUPLICATE_ACTION_EXECUTED"], 1)
        self.assertIn("confirmation_metric_id", plan["writes"]["common_event_outbox"][0]["dedup_key"])

    def test_fake_transaction_inserts_only_allowed_tables(self) -> None:
        plan = build_plan()
        connection = FakeConnection()

        counts = execute_provisional_action_executed_transaction(connection=connection, execute_plan=plan)
        sql_text = "\n".join(connection.cursor_obj.statements)

        self.assertTrue(connection.committed)
        self.assertEqual(counts["common_action_run"], 1)
        self.assertEqual(counts["common_action_quality_item"], 1)
        self.assertEqual(counts["stock_action_fact"], 1)
        self.assertEqual(counts["common_action_event"], 1)
        self.assertEqual(counts["common_event_outbox"], 1)
        self.assertIn("INSERT INTO common_action_run", sql_text)
        self.assertIn("INSERT INTO stock_action_fact", sql_text)
        self.assertIn("INSERT INTO common_action_event", sql_text)
        self.assertIn("INSERT INTO common_event_outbox", sql_text)
        self.assertNotIn("INSERT INTO common_event_inbox", sql_text)
        self.assertNotIn("INSERT INTO common_event_consumer_checkpoint", sql_text)
        self.assertNotIn("tracking_state", sql_text)

    def test_side_effect_guard_and_static_forbidden_route_checks(self) -> None:
        import ashare_v3.action.provisional_action_executed as module

        plan = build_plan()
        module_source = inspect.getsource(module)

        self.assertTrue(plan["side_effect_guard"]["action_run_written"])
        self.assertTrue(plan["side_effect_guard"]["action_fact_written"])
        self.assertTrue(plan["side_effect_guard"]["action_event_written"])
        self.assertTrue(plan["side_effect_guard"]["outbox_written"])
        self.assertFalse(plan["side_effect_guard"]["inbox_written"])
        self.assertFalse(plan["side_effect_guard"]["checkpoint_written"])
        self.assertFalse(plan["side_effect_guard"]["tracking_written"])
        self.assertFalse(plan["side_effect_guard"]["n6_written"])
        self.assertFalse(plan["side_effect_guard"]["sim_trade_virtual_written"])
        self.assertFalse(plan["side_effect_guard"]["worker_started"])
        self.assertFalse(plan["side_effect_guard"]["auto_trade_triggered"])
        self.assertNotIn("execute_action_transaction", module_source)
        self.assertNotIn("INSERT INTO common_event_inbox", module_source)
        self.assertNotIn("INSERT INTO common_event_consumer_checkpoint", module_source)
        self.assertNotIn("common_action_tracking_state", module_source)
        self.assertNotIn("user_signal_projection", module_source)
        self.assertNotIn("virtual_order", module_source)
        self.assertNotIn("trade_order", module_source)

    def test_runner_cli_parser_exposes_actionexecuted_contract_args(self) -> None:
        args = build_parser().parse_args(
            [
                "--dsn",
                "postgresql://example",
                "--source-eligible-action-run-id",
                ELIGIBLE_ACTION_RUN_ID,
                "--action-run-id",
                ACTION_RUN_ID,
                "--for-trade-date",
                FOR_TRADE_DATE,
                "--latest-closed-minute-label",
                "2026-06-24T10:24:00+08:00",
                "--json-report-path",
                "tmp/report.json",
                "--markdown-report-path",
                "tmp/report.md",
                "--rollback-sql-path",
                "tmp/rollback.sql",
                "--json",
            ]
        )

        self.assertEqual(args.source_eligible_action_run_id, ELIGIBLE_ACTION_RUN_ID)
        self.assertEqual(args.action_run_id, ACTION_RUN_ID)
        self.assertEqual(args.latest_closed_minute_label, "2026-06-24T10:24:00+08:00")
        self.assertFalse(args.execute)
        self.assertFalse(args.user_confirmed)

    def test_runner_report_blocks_n3p_actionexecuted_plans(self) -> None:
        n3p_row = eligible_row(1)
        payload = n3p_row["payload_json"]
        if not isinstance(payload, dict):
            raise AssertionError("test helper expected dict payload")
        payload.update(
            {
                "source_metric_kind": "realtime_action_confirmation_metric",
                "metric_role": "trigger_proof",
                "not_n5_final_proof": True,
                "source_trigger_proof_kind": "n3p_formal_amount_chain",
            }
        )

        report = build_provisional_actionexecuted_once_report(
            source_eligible_action_run={"run_id": ELIGIBLE_ACTION_RUN_ID, "status": "passed"},
            source_eligible_action_run_id=ELIGIBLE_ACTION_RUN_ID,
            action_run_id=ACTION_RUN_ID,
            for_trade_date=FOR_TRADE_DATE,
            latest_closed_minute_label="2026-06-24T10:24:00+08:00",
            source_actioneligible_rows=[n3p_row],
            confirmation_metric_rows=[confirmation_metric_row(1)],
            confirmation_projection_rows=[],
            target_counts=empty_target_counts(),
            execute=False,
            user_confirmed=False,
            rollback_sql_path="tmp/rollback.sql",
        )

        self.assertEqual(report["dry_run_counts"]["BLOCKED_N3P_NOT_ACTION_CONFIRMATION_PROOF"], 1)
        self.assertEqual(report["action_executed_plan_count"], 0)
        self.assertEqual(report["write_plan_counts"]["common_action_event"], 0)
        self.assertEqual(report["write_plan_counts"]["common_event_outbox"], 0)

    def test_runner_execute_requires_user_confirmation(self) -> None:
        with self.assertRaises(N5PActionExecutedBlocked) as raised:
            build_provisional_actionexecuted_once_report(
                source_eligible_action_run={"run_id": ELIGIBLE_ACTION_RUN_ID, "status": "passed"},
                source_eligible_action_run_id=ELIGIBLE_ACTION_RUN_ID,
                action_run_id=ACTION_RUN_ID,
                for_trade_date=FOR_TRADE_DATE,
                latest_closed_minute_label="2026-06-24T10:24:00+08:00",
                source_actioneligible_rows=hint_rows(3),
                confirmation_metric_rows=hint_confirmation_metric_rows(3),
                confirmation_projection_rows=hint_projection_rows(3),
                target_counts=empty_target_counts(),
                execute=True,
                user_confirmed=False,
            )

        self.assertIn("--user-confirmed", str(raised.exception))

    def test_runner_target_dirty_blocks_before_write_plan(self) -> None:
        with self.assertRaises(N5PActionExecutedBlocked) as raised:
            build_provisional_actionexecuted_once_report(
                source_eligible_action_run={"run_id": ELIGIBLE_ACTION_RUN_ID, "status": "passed"},
                source_eligible_action_run_id=ELIGIBLE_ACTION_RUN_ID,
                action_run_id=ACTION_RUN_ID,
                for_trade_date=FOR_TRADE_DATE,
                latest_closed_minute_label="2026-06-24T10:24:00+08:00",
                source_actioneligible_rows=hint_rows(3),
                confirmation_metric_rows=hint_confirmation_metric_rows(3),
                confirmation_projection_rows=hint_projection_rows(3),
                target_counts={**empty_target_counts(), "common_action_run": 1},
                execute=False,
                user_confirmed=False,
            )

        self.assertIn("BLOCKED_TARGET_NOT_EMPTY", str(raised.exception))

    def test_actionexecuted_rollback_sql_is_exact_run_scoped(self) -> None:
        rollback_sql = build_provisional_actionexecuted_rollback_sql(ACTION_RUN_ID)

        self.assertIn(ACTION_RUN_ID, rollback_sql)
        self.assertIn("source_run_id = v_run_id", rollback_sql)
        self.assertIn("WHERE run_id = v_run_id", rollback_sql)
        self.assertNotIn("TRUNCATE", rollback_sql.upper())
        self.assertNotIn("DROP", rollback_sql.upper())
        self.assertNotIn("CASCADE", rollback_sql.upper())


if __name__ == "__main__":
    unittest.main()
