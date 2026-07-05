import unittest
import json
from pathlib import Path

from ashare_v3.market.closed_30m_replay_execute import (
    ALLOWED_WRITE_TABLES,
    C2_QUALITY_LAYER_SCOPE,
    C2_REPLAY_COMPARE_KEY,
    C2_REPLAY_DIFF_REQUIRED_FIELDS,
    C2_REPLAY_TOLERANCE,
    CLOSED_30M_METRIC_SCOPE,
    FORBIDDEN_WRITE_TABLES,
    Closed30mReplayExecuteError,
    MootdxClosed30mReplayAdapter,
    build_c2_quality_items,
    build_c2_business_rollback_sql,
    build_closed_30m_summary_records,
    build_closed_30m_rollback_scope,
    build_replay_delta_records,
    ensure_clean_c2_target,
    ensure_c2_execute_contract,
    summarize_execute_rows,
)


C2_RUN_ID = (
    "closed_minute_30m_replay_20260525_until_1500__"
    "market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute"
)
SUBSCRIPTION_RUN_ID = "market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute"
CONDITION_RUN_ID = "condition_layer_20260522_to_20260525_20260525102249_execute"
TODAY_MINUTE_RUN_ID = f"today_minute_bar_1m_20260525_until_1411__{SUBSCRIPTION_RUN_ID}"


class Closed30mReplayExecuteTest(unittest.TestCase):
    def test_execute_requires_double_confirmation(self) -> None:
        with self.assertRaisesRegex(Closed30mReplayExecuteError, "--execute"):
            ensure_c2_execute_contract(
                sample_dry_run_plan(),
                sample_execute_contract(),
                sample_dry_run_report(),
                execute=False,
                user_confirmed=True,
                c2_run_id=C2_RUN_ID,
                for_trade_date="20260525",
            )

        with self.assertRaisesRegex(Closed30mReplayExecuteError, "--user-confirmed"):
            ensure_c2_execute_contract(
                sample_dry_run_plan(),
                sample_execute_contract(),
                sample_dry_run_report(),
                execute=True,
                user_confirmed=False,
                c2_run_id=C2_RUN_ID,
                for_trade_date="20260525",
            )

    def test_contract_and_report_mismatch_blocks(self) -> None:
        report = sample_dry_run_report()
        report["c2_run_id"] = "wrong"

        with self.assertRaisesRegex(Closed30mReplayExecuteError, "c2_run_id"):
            ensure_c2_execute_contract(
                sample_dry_run_plan(),
                sample_execute_contract(),
                report,
                execute=True,
                user_confirmed=True,
                c2_run_id=C2_RUN_ID,
                for_trade_date="20260525",
            )

    def test_dry_run_must_pass_and_outbox_must_be_false(self) -> None:
        report = sample_dry_run_report()
        report["result"] = "DRY_RUN_BLOCKED"
        with self.assertRaisesRegex(Closed30mReplayExecuteError, "dry-run"):
            ensure_c2_execute_contract(
                sample_dry_run_plan(),
                sample_execute_contract(),
                report,
                execute=True,
                user_confirmed=True,
                c2_run_id=C2_RUN_ID,
                for_trade_date="20260525",
            )

        contract = sample_execute_contract()
        contract["writes_outbox"] = True
        with self.assertRaisesRegex(Closed30mReplayExecuteError, "writes_outbox=false"):
            ensure_c2_execute_contract(
                sample_dry_run_plan(),
                contract,
                sample_dry_run_report(),
                execute=True,
                user_confirmed=True,
                c2_run_id=C2_RUN_ID,
                for_trade_date="20260525",
            )

    def test_expected_summary_rows_are_read_from_closed_summary_contract(self) -> None:
        contract = sample_execute_contract()
        contract.pop("expected_summary_rows", None)
        contract["closed_30m_summary_contract"]["expected_summary_rows"]["total"] = 17000

        with self.assertRaisesRegex(Closed30mReplayExecuteError, "expected summary rows"):
            ensure_c2_execute_contract(
                sample_dry_run_plan(),
                contract,
                sample_dry_run_report(),
                execute=True,
                user_confirmed=True,
                c2_run_id=C2_RUN_ID,
                for_trade_date="20260525",
            )

    def test_existing_c2_target_blocks(self) -> None:
        audit = sample_clean_target()
        audit["run_exists"] = True
        with self.assertRaisesRegex(Closed30mReplayExecuteError, "already exists"):
            ensure_clean_c2_target(audit, C2_RUN_ID)

        audit = sample_clean_target()
        audit["outbox_rows_for_c2_run"] = 1
        with self.assertRaisesRegex(Closed30mReplayExecuteError, "outbox"):
            ensure_clean_c2_target(audit, C2_RUN_ID)

        audit = sample_clean_target()
        audit["checkpoint_rows_for_c2_run"] = 1
        with self.assertRaisesRegex(Closed30mReplayExecuteError, "checkpoint"):
            ensure_clean_c2_target(audit, C2_RUN_ID)

    def test_adapter_routing_keeps_stock_index_board_separate(self) -> None:
        client = FakeMootdxClient()
        adapter = MootdxClosed30mReplayAdapter(client=client, offset=512)

        adapter.fetch_full_day_minute_bars(sample_subscription("stock", "stock:SH:600000", "SH", "600000"), "20260525")
        adapter.fetch_full_day_minute_bars(sample_subscription("index", "index:SH:000905", "SH", "000905"), "20260525")
        adapter.fetch_full_day_minute_bars(sample_subscription("board", "board:TDX:881001", "TDX", "881001"), "20260525")

        self.assertEqual(
            client.calls,
            [
                ("bars", "600000", 8, 512),
                ("index_bars", "000905", 8, 512),
                ("index_bars", "881001", 8, 512),
            ],
        )

    def test_delta_rows_only_include_missing_or_changed_rows(self) -> None:
        subscription = sample_subscription("stock", "stock:SH:600000", "SH", "600000")
        baseline_rows = [
            minute_row("09:31", close="10.10", amount="100", run_id=TODAY_MINUTE_RUN_ID, bar_id=1),
            minute_row("09:32", close="10.20", amount="200", run_id=TODAY_MINUTE_RUN_ID, bar_id=2),
        ]
        replay_rows = [
            minute_row("09:31", close="10.10", amount="100", run_id="replay"),
            minute_row("09:32", close="10.25", amount="250", run_id="replay"),
            minute_row("09:33", close="10.30", amount="300", run_id="replay"),
        ]

        deltas = build_replay_delta_records(
            c2_run_id=C2_RUN_ID,
            source_condition_run_id=CONDITION_RUN_ID,
            for_trade_date="20260525",
            subscription=subscription,
            baseline_rows=baseline_rows,
            replay_rows=replay_rows,
            expected_labels=["09:31", "09:32", "09:33"],
            source_adapter="mootdx.std.bars",
            source_version="tdx_replay",
        )

        self.assertEqual([row["minute_label"] for row in deltas], ["09:32", "09:33"])
        self.assertEqual([row["raw_json"]["delta_kind"] for row in deltas], ["replay_diff", "baseline_missing"])
        self.assertTrue(all(row["run_id"] == C2_RUN_ID for row in deltas))
        self.assertTrue(all(row["is_previous_day_preload"] is False for row in deltas))
        self.assertFalse(any("event_id" in row for row in deltas))
        for row in deltas:
            replay_diff = row["raw_json"]["replay_diff_json"]
            self.assertLessEqual(set(C2_REPLAY_DIFF_REQUIRED_FIELDS), set(replay_diff))
            self.assertEqual(replay_diff["c2_run_id"], C2_RUN_ID)
            self.assertEqual(replay_diff["replay_source_adapter"], "mootdx.std.bars")
            self.assertEqual(replay_diff["compare_key"], C2_REPLAY_COMPARE_KEY)
            self.assertEqual(replay_diff["tolerance"], C2_REPLAY_TOLERANCE)
            self.assertEqual(replay_diff["c2_delta_bar_id"], None)
            self.assertEqual(replay_diff["source_error"], None)
            self.assertEqual(replay_diff["source_trade_date"], "20260525")
            self.assertTrue(replay_diff["source_bar_time"])
            self.assertTrue(replay_diff["replay_row_hash"])
            self.assertIn("diff_fields", replay_diff)

    def test_bj_missing_does_not_fabricate_minute_rows_but_writes_missing_summary(self) -> None:
        subscription = sample_subscription("stock", "stock:BJ:920045", "BJ", "920045")

        deltas = build_replay_delta_records(
            c2_run_id=C2_RUN_ID,
            source_condition_run_id=CONDITION_RUN_ID,
            for_trade_date="20260525",
            subscription=subscription,
            baseline_rows=[],
            replay_rows=[],
            expected_labels=["09:31", "09:32"],
            source_adapter="mootdx.std.bars",
            source_version="tdx_replay",
        )
        summaries = build_closed_30m_summary_records(
            c2_run_id=C2_RUN_ID,
            source_condition_run_id=CONDITION_RUN_ID,
            source_subscription_run_id=SUBSCRIPTION_RUN_ID,
            source_today_minute_run_ids=[TODAY_MINUTE_RUN_ID],
            for_trade_date="20260525",
            subscription=subscription,
            baseline_rows=[],
            delta_rows=[],
        )

        self.assertEqual(deltas, [])
        self.assertEqual(len(summaries), 8)
        self.assertTrue(all(row["closed_status"] == "missing" for row in summaries))
        self.assertTrue(all(row["actual_minute_count"] == 0 for row in summaries))
        self.assertTrue(all(row["missing_minute_count"] == 30 for row in summaries))

    def test_summary_rows_use_eight_buckets_and_expected_counts(self) -> None:
        subscription = sample_subscription("index", "index:SH:000905", "SH", "000905")
        full_bucket_labels = [*[f"09:{minute:02d}" for minute in range(31, 60)], "10:00"]
        full_bucket_rows = [minute_row(label, close=label, amount="1") for label in full_bucket_labels]
        partial_bucket_rows = [minute_row(f"10:{minute:02d}", close=str(minute), amount=str(minute)) for minute in range(1, 12)]

        summaries = build_closed_30m_summary_records(
            c2_run_id=C2_RUN_ID,
            source_condition_run_id=CONDITION_RUN_ID,
            source_subscription_run_id=SUBSCRIPTION_RUN_ID,
            source_today_minute_run_ids=[TODAY_MINUTE_RUN_ID],
            for_trade_date="20260525",
            subscription=subscription,
            baseline_rows=full_bucket_rows + partial_bucket_rows,
            delta_rows=[],
        )

        self.assertEqual(len(summaries), 8)
        by_bucket = {row["bucket_id"]: row for row in summaries}
        self.assertEqual(by_bucket["0931_1000"]["closed_status"], "closed")
        self.assertEqual(by_bucket["0931_1000"]["actual_minute_count"], 30)
        self.assertEqual(by_bucket["1001_1030"]["closed_status"], "partial")
        self.assertEqual(by_bucket["1001_1030"]["actual_minute_count"], 11)
        self.assertEqual(by_bucket["1431_1500"]["closed_status"], "missing")

    def test_summary_trace_covers_c1_ids_and_c2_delta_keys(self) -> None:
        subscription = sample_subscription("stock", "stock:SH:600000", "SH", "600000")
        baseline_rows = [minute_row("09:31", close="10.10", amount="100", run_id=TODAY_MINUTE_RUN_ID, bar_id=101)]
        delta_rows = build_replay_delta_records(
            c2_run_id=C2_RUN_ID,
            source_condition_run_id=CONDITION_RUN_ID,
            for_trade_date="20260525",
            subscription=subscription,
            baseline_rows=[],
            replay_rows=[minute_row("09:32", close="10.20", amount="200", run_id="replay")],
            expected_labels=["09:32"],
            source_adapter="mootdx.std.bars",
            source_version="tdx_replay",
        )

        summaries = build_closed_30m_summary_records(
            c2_run_id=C2_RUN_ID,
            source_condition_run_id=CONDITION_RUN_ID,
            source_subscription_run_id=SUBSCRIPTION_RUN_ID,
            source_today_minute_run_ids=[TODAY_MINUTE_RUN_ID],
            for_trade_date="20260525",
            subscription=subscription,
            baseline_rows=baseline_rows,
            delta_rows=delta_rows,
        )

        first_bucket = {row["bucket_id"]: row for row in summaries}["0931_1000"]
        self.assertEqual(first_bucket["source_minute_bar_ids"], [101])
        trace = first_bucket["raw_json"]["resolved_minute_trace"]
        c1_refs = [item for item in trace if item["source_kind"] == "C1_baseline"]
        c2_refs = [item for item in trace if item["source_kind"] == "C2_delta"]
        self.assertEqual(c1_refs[0]["bar_id"], 101)
        self.assertEqual(c2_refs[0]["run_id"], C2_RUN_ID)
        self.assertEqual(c2_refs[0]["identity_key"], "stock:SH:600000")
        self.assertEqual(c2_refs[0]["trade_date"], "20260525")
        self.assertEqual(c2_refs[0]["minute_label"], "09:32")
        self.assertTrue(c2_refs[0]["c2_delta_key"])
        self.assertIn("source_minute_refs", first_bucket["replay_diff_json"])

    def test_quality_items_use_existing_contract_values(self) -> None:
        items = build_c2_quality_items(
            c2_run_id=C2_RUN_ID,
            source_condition_run_id=CONDITION_RUN_ID,
            row_summary={
                "minute_delta_rows": {"stock": 10, "index": 1, "board": 2, "total": 13},
                "summary_rows": {"stock": 16, "index": 8, "board": 8, "total": 32},
                "summary_status": {"closed": 8, "partial": 8, "missing": 16, "failed": 0},
                "bj_920xxx_missing": 9,
                "replay_diff_rows": 2,
            },
        )

        self.assertTrue(items)
        self.assertEqual({item["layer_scope"] for item in items}, {C2_QUALITY_LAYER_SCOPE})
        self.assertLessEqual({item["data_domain"] for item in items}, {"common", "stock", "index", "board"})
        self.assertTrue(all((item["details"] or {}).get("metric_scope") == CLOSED_30M_METRIC_SCOPE for item in items))

    def test_write_scope_and_rollback_do_not_touch_downstream_or_outbox(self) -> None:
        self.assertFalse(set(ALLOWED_WRITE_TABLES) & set(FORBIDDEN_WRITE_TABLES))
        self.assertIn("common_event_outbox", FORBIDDEN_WRITE_TABLES)
        self.assertIn("stock_closed_30m_summary", ALLOWED_WRITE_TABLES)
        self.assertIn("stock_minute_bar_1m", ALLOWED_WRITE_TABLES)

        scope = build_closed_30m_rollback_scope(C2_RUN_ID)
        self.assertIn("stock_closed_30m_summary", scope["delete_tables"])
        self.assertIn("stock_minute_bar_1m", scope["delete_tables"])
        self.assertNotIn("common_event_outbox", scope["delete_tables"])
        self.assertNotIn("stock_realtime_projection_metric", scope["delete_tables"])
        self.assertIn("common_event_consumer_checkpoint", scope["precheck_no_rows"])
        self.assertTrue(scope["preserves_c1_b1_b2_n4_n5"])

    def test_generated_rollback_sql_keeps_checkpoint_guard(self) -> None:
        sql = build_c2_business_rollback_sql(C2_RUN_ID)

        self.assertIn("common_event_outbox", sql)
        self.assertIn("common_event_inbox", sql)
        self.assertIn("common_event_consumer_checkpoint", sql)
        self.assertIn("checkpoint_payload::TEXT LIKE", sql)
        self.assertIn("Refusing C2 rollback", sql)
        self.assertIn(C2_RUN_ID, sql)

    def test_contract_documents_runner_readiness_and_authorization_boundary(self) -> None:
        contract = json.loads(Path("docs/N3_C2_closed_30m_execute_contract.json").read_text())

        self.assertTrue(contract["runner_exists"])
        self.assertEqual(contract["runner_readiness"], "ready")
        self.assertFalse(contract["execute_authorized"])
        self.assertFalse(contract["c2_execute_allowed_now"])
        self.assertEqual(contract["c2_execute_allowed_reason"], "awaiting_final_gate_user_confirmation")
        self.assertIn("closed_30m_summary_contract", contract)
        self.assertEqual(contract["closed_30m_summary_contract"]["expected_summary_rows"]["total"], 17504)

    def test_execute_summary_enforces_writes_outbox_false_and_no_worker(self) -> None:
        summary = summarize_execute_rows(
            c2_run_id=C2_RUN_ID,
            minute_delta_rows={"stock": 10, "index": 1, "board": 2},
            summary_rows={"stock": 16, "index": 8, "board": 8},
            summary_status={"closed": 8, "partial": 8, "missing": 16, "failed": 0},
            quality_rows=4,
            outbox_rows_for_c2_run=0,
        )

        self.assertEqual(summary["minute_delta_rows"]["total"], 13)
        self.assertEqual(summary["summary_rows"]["total"], 32)
        self.assertFalse(summary["side_effects"]["writes_outbox"])
        self.assertFalse(summary["side_effects"]["starts_worker"])
        self.assertEqual(summary["outbox_rows_for_c2_run"], 0)


class FakeMootdxClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int, int]] = []

    def bars(self, *, symbol: str, frequency: int, start: int, offset: int) -> list[dict[str, object]]:
        del start
        self.calls.append(("bars", symbol, frequency, offset))
        return []

    def index_bars(self, *, symbol: str, frequency: int, start: int, offset: int) -> list[dict[str, object]]:
        del start
        self.calls.append(("index_bars", symbol, frequency, offset))
        return []


def sample_subscription(asset_kind: str, identity_key: str, exchange: str, code: str) -> dict[str, object]:
    return {
        "subscription_id": 11,
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "exchange": exchange,
        "code": code,
        "display_code": code,
        "name": f"{asset_kind}-{code}",
        "source_scope_ids": [101],
        "source_condition_pool_ids": [201],
    }


def minute_row(
    label: str,
    *,
    open_: str = "10",
    high: str = "11",
    low: str = "9",
    close: str = "10",
    volume: str = "1000",
    amount: str = "100",
    run_id: str = TODAY_MINUTE_RUN_ID,
    bar_id: int | None = None,
) -> dict[str, object]:
    return {
        "bar_id": bar_id,
        "run_id": run_id,
        "trade_date": "20260525",
        "bar_time": f"2026-05-25 {label}:00+08:00",
        "minute_label": label,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "amount": amount,
        "quality_status": "passed",
        "raw_json": {},
    }


def sample_dry_run_plan() -> dict[str, object]:
    return {
        "stage": "N3-C2-business-dry-run-plan",
        "layer_role": "N3_market_data",
        "c2_run_id": C2_RUN_ID,
        "for_trade_date": "20260525",
        "writes_outbox": False,
        "closed_30m_summary_plan": {"bucket_count": 8},
        "write_scope": {
            "allowed_write_tables": list(ALLOWED_WRITE_TABLES),
            "forbidden_write_tables": list(FORBIDDEN_WRITE_TABLES),
            "writes_outbox": False,
        },
    }


def sample_execute_contract() -> dict[str, object]:
    return {
        "stage": "N3-C2-business-execute-contract-design",
        "layer_role": "N3_market_data",
        "c2_run_id": C2_RUN_ID,
        "for_trade_date": "20260525",
        "writes_outbox": False,
        "starts_worker": False,
        "runner_exists": True,
        "runner_readiness": "ready",
        "execute_authorized": False,
        "c2_execute_allowed_now": False,
        "c2_execute_allowed_reason": "awaiting_final_gate_user_confirmation",
        "closed_30m_summary_contract": {"expected_summary_rows": {"total": 17504}},
        "allowed_writes": list(ALLOWED_WRITE_TABLES),
        "forbidden_writes": list(FORBIDDEN_WRITE_TABLES),
    }


def sample_dry_run_report() -> dict[str, object]:
    return {
        "stage": "N3-C2",
        "layer_role": "N3_market_data",
        "result": "DRY_RUN_PASS",
        "blocked": False,
        "c2_run_id": C2_RUN_ID,
        "for_trade_date": "20260525",
        "source_condition_run_id": CONDITION_RUN_ID,
        "source_subscription_run_id": SUBSCRIPTION_RUN_ID,
        "today_minute_run_id": TODAY_MINUTE_RUN_ID,
        "closed_30m_summary_plan": {"expected_summary_rows": {"total": 17504}},
        "target_audit": sample_clean_target(),
        "quality": {"p0_count": 0, "p1_count": 3, "p2_count": 0},
    }


def sample_clean_target() -> dict[str, object]:
    return {
        "run_exists": False,
        "minute_rows_for_c2_run": {"stock": 0, "index": 0, "board": 0},
        "summary_rows_for_c2_run": {"stock": 0, "index": 0, "board": 0},
        "quality_rows_for_c2_run": 0,
        "outbox_rows_for_c2_run": 0,
        "inbox_rows_for_c2_run": 0,
        "checkpoint_rows_for_c2_run": 0,
    }


if __name__ == "__main__":
    unittest.main()
