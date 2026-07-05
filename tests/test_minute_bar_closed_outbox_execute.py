import unittest
import json
from datetime import datetime, timezone
from pathlib import Path

from ashare_v3.market.minute_bar_closed_outbox_execute import (
    ALLOWED_WRITE_TABLES,
    FORBIDDEN_WRITE_TABLES,
    C3_QUALITY_LAYER_SCOPE,
    C3_METRIC_SCOPE,
    MinuteBarClosedOutboxExecuteError,
    build_c3_execute_quality_items,
    build_c3_rollback_sql,
    build_events_for_execute,
    ensure_c3_execute_contract,
    ensure_clean_c3_target,
    summarize_c3_events,
)
from ashare_v3.market.minute_bar_closed_outbox_plan import (
    build_c3_run_id,
    build_trace_enrichment_context,
)


C2_RUN_ID = (
    "closed_minute_30m_replay_20260525_until_1500__"
    "market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute"
)
C3_RUN_ID = build_c3_run_id(c2_run_id=C2_RUN_ID, for_trade_date="20260525")
SUBSCRIPTION_RUN_ID = "market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute"
CONDITION_RUN_ID = "condition_layer_20260522_to_20260525_20260525102249_execute"
TODAY_MINUTE_RUN_ID = f"today_minute_bar_1m_20260525_until_1411__{SUBSCRIPTION_RUN_ID}"


class MinuteBarClosedOutboxExecuteTests(unittest.TestCase):
    def test_execute_requires_double_confirmation(self) -> None:
        with self.assertRaisesRegex(MinuteBarClosedOutboxExecuteError, "--execute"):
            ensure_c3_execute_contract(
                sample_contract(),
                sample_preflight(),
                sample_dry_run(),
                execute=False,
                user_confirmed=True,
                c3_run_id=C3_RUN_ID,
                for_trade_date="20260525",
            )

        with self.assertRaisesRegex(MinuteBarClosedOutboxExecuteError, "--user-confirmed"):
            ensure_c3_execute_contract(
                sample_contract(),
                sample_preflight(),
                sample_dry_run(),
                execute=True,
                user_confirmed=False,
                c3_run_id=C3_RUN_ID,
                for_trade_date="20260525",
            )

    def test_contract_authorization_false_means_waiting_for_cli_confirmation_not_runner_missing(self) -> None:
        contract = sample_contract()
        self.assertFalse(contract["c3_execute_authorized"])
        self.assertTrue(contract["runner_exists"])
        self.assertEqual(contract["runner_readiness"], "ready")

        ensure_c3_execute_contract(
            contract,
            sample_preflight(),
            sample_dry_run(),
            execute=True,
            user_confirmed=True,
            c3_run_id=C3_RUN_ID,
            for_trade_date="20260525",
        )

    def test_contract_validation_rejects_common_market_data_run_date_mismatch_before_db_write(self) -> None:
        contract = sample_contract()
        contract["dates"] = {
            "for_trade_date": "20260525",
            "source_trade_date": "20260525",
            "prev_trade_date": "20260522",
        }

        with self.assertRaisesRegex(MinuteBarClosedOutboxExecuteError, "prev_trade_date must equal for_trade_date"):
            ensure_c3_execute_contract(
                contract,
                sample_preflight(),
                sample_dry_run(),
                execute=True,
                user_confirmed=True,
                c3_run_id=C3_RUN_ID,
                for_trade_date="20260525",
            )

    def test_real_contract_run_metadata_uses_for_trade_date_and_keeps_previous_day_trace(self) -> None:
        contract = json.loads(Path("docs/N3_C3_minute_bar_closed_execute_contract.json").read_text())

        dates = contract["dates"]
        self.assertEqual(dates["source_trade_date"], dates["for_trade_date"])
        self.assertEqual(dates["prev_trade_date"], dates["for_trade_date"])

        previous_day = contract["previous_day_provenance"]
        self.assertEqual(previous_day["previous_day_minute_date"], "20260522")
        self.assertIn("source_today_minute_run_ids", previous_day)
        self.assertIn("c2_run_id", previous_day)

    def test_baseline_nonzero_blocks(self) -> None:
        target = sample_clean_target()
        target["outbox_rows_for_c3_run"] = 1

        with self.assertRaisesRegex(MinuteBarClosedOutboxExecuteError, "outbox"):
            ensure_clean_c3_target(target, C3_RUN_ID)

        target = sample_clean_target()
        target["checkpoint_rows_for_c3_run"] = 1
        with self.assertRaisesRegex(MinuteBarClosedOutboxExecuteError, "checkpoint"):
            ensure_clean_c3_target(target, C3_RUN_ID)

    def test_only_closed_generates_outbox_events_and_missing_is_excluded(self) -> None:
        events, blockers, excluded = build_events_for_execute(
            summary_rows_by_asset={
                "stock": [
                    summary_row(summary_id=1),
                    summary_row(
                        summary_id=2,
                        identity_key="stock:BJ:920001",
                        exchange="BJ",
                        code="920001",
                        closed_status="missing",
                        subscription_id=12,
                    ),
                ],
                "index": [],
                "board": [],
            },
            enrichment_context=sample_enrichment_context(),
            c3_run_id=C3_RUN_ID,
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(blockers, [])
        self.assertEqual(excluded["missing"], 1)
        self.assertEqual(events[0].event_type, "MinuteBarClosed")
        self.assertEqual(events[0].event_schema_version, "v2")
        self.assertEqual(events[0].payload_json["closed_30m_summary_id"], 1)
        self.assertNotIn("minute_bar_id", events[0].payload_json)

    def test_payload_v2_and_dedup_are_unique(self) -> None:
        events, blockers, excluded = build_events_for_execute(
            summary_rows_by_asset={
                "stock": [summary_row(summary_id=1), summary_row(summary_id=2, bucket_id="1001_1030")],
                "index": [],
                "board": [],
            },
            enrichment_context=sample_enrichment_context(),
            c3_run_id=C3_RUN_ID,
        )

        summary = summarize_c3_events(events, blockers, excluded)

        self.assertEqual(summary["event_count_by_type"], {"MinuteBarClosed": 2})
        self.assertEqual(summary["duplicate_candidate_count"], 0)
        self.assertEqual(summary["payload_blocker_count"], 0)
        self.assertTrue(all(event.payload_json["source_minute_refs"] for event in events))

    def test_duplicate_dedup_is_detected(self) -> None:
        events, blockers, excluded = build_events_for_execute(
            summary_rows_by_asset={"stock": [summary_row(summary_id=1), summary_row(summary_id=1)], "index": [], "board": []},
            enrichment_context=sample_enrichment_context(),
            c3_run_id=C3_RUN_ID,
        )

        summary = summarize_c3_events(events, blockers, excluded)

        self.assertEqual(summary["duplicate_candidate_count"], 1)

    def test_quality_items_keep_p1_missing_warning_and_existing_quality_schema(self) -> None:
        events, blockers, excluded = build_events_for_execute(
            summary_rows_by_asset={"stock": [summary_row()], "index": [], "board": []},
            enrichment_context=sample_enrichment_context(),
            c3_run_id=C3_RUN_ID,
        )
        excluded["missing"] = 72
        excluded["total"] = 72

        items = build_c3_execute_quality_items(
            contract=sample_contract(expected_total=1),
            event_summary=summarize_c3_events(events, blockers, excluded),
            target_audit=sample_clean_target(),
        )

        domains = {item["data_domain"] for item in items}
        self.assertLessEqual(domains, {"common", "stock", "index", "board"})
        for item in items:
            self.assertEqual(item["layer_scope"], C3_QUALITY_LAYER_SCOPE)
            self.assertEqual((item["details"] or {}).get("metric_scope"), C3_METRIC_SCOPE)
            self.assertEqual((item["details"] or {}).get("c3_run_id"), C3_RUN_ID)
            self.assertEqual((item["details"] or {}).get("previous_day_provenance", {}).get("previous_day_minute_date"), "20260522")
        warnings = [item for item in items if item["severity"] == "P1" and item["status"] == "warning"]
        self.assertEqual(len(warnings), 1)

    def test_rollback_sql_has_outbox_inbox_checkpoint_guards(self) -> None:
        sql = build_c3_rollback_sql(C3_RUN_ID)

        self.assertIn("delivering', 'delivered", sql)
        self.assertIn("common_event_inbox", sql)
        self.assertIn("common_event_consumer_checkpoint", sql)
        self.assertIn(f"DELETE FROM common_event_outbox WHERE source_run_id = '{C3_RUN_ID}'", sql)
        self.assertIn(f"DELETE FROM common_market_data_quality_item WHERE run_id = '{C3_RUN_ID}'", sql)
        self.assertIn(f"DELETE FROM common_market_data_run WHERE run_id = '{C3_RUN_ID}'", sql)
        self.assertNotIn("stock_closed_30m_summary", sql)
        self.assertNotIn("stock_minute_bar_1m", sql)

    def test_write_scope_is_outbox_only_no_inbox_downstream_or_worker(self) -> None:
        self.assertEqual(
            ALLOWED_WRITE_TABLES,
            (
                "common_market_data_run",
                "common_market_data_quality_item",
                "common_event_outbox",
            ),
        )
        self.assertIn("common_event_inbox", FORBIDDEN_WRITE_TABLES)
        self.assertIn("common_event_consumer_checkpoint", FORBIDDEN_WRITE_TABLES)
        self.assertIn("N4/N5/N6", FORBIDDEN_WRITE_TABLES)
        self.assertIn("worker", FORBIDDEN_WRITE_TABLES)


def sample_contract(expected_total: int = 17432) -> dict[str, object]:
    return {
        "stage": "N3-C3-MinuteBarClosed-outbox-execute-contract",
        "layer_role": "N3_market_data",
        "execution_mode": "minute_bar_closed_outbox_run_once_execute",
        "c3_run_id": C3_RUN_ID,
        "c2_run_id": C2_RUN_ID,
        "c3_execute_authorized": False,
        "runner_exists": True,
        "runner_readiness": "ready",
        "writes_outbox": True,
        "consumes_outbox": False,
        "source_runs": {
            "source_condition_run_id": CONDITION_RUN_ID,
            "source_subscription_run_id": SUBSCRIPTION_RUN_ID,
            "c2_run_id": C2_RUN_ID,
        },
        "dates": {
            "for_trade_date": "20260525",
            "source_trade_date": "20260525",
            "prev_trade_date": "20260525",
        },
        "previous_day_provenance": {
            "previous_day_minute_date": "20260522",
            "source_previous_day_minute_run_id": (
                "previous_day_minute_preload_20260522_for_20260525__"
                "market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute"
            ),
            "source_today_minute_run_ids": [TODAY_MINUTE_RUN_ID, C2_RUN_ID],
            "c2_run_id": C2_RUN_ID,
        },
        "expected_outbox_rows": {
            "MinuteBarClosed": expected_total,
            "total": expected_total,
            "stock": expected_total,
            "index": 0,
            "board": 0,
        },
        "expected_excluded_summary_count": {
            "missing": 72,
            "partial": 0,
            "failed": 0,
            "total": 72,
        },
    }


def sample_preflight(result: str = "PREFLIGHT_PASS") -> dict[str, object]:
    return {
        "stage": "N3-C3-MinuteBarClosed-outbox-execute-preflight",
        "layer_role": "N3_market_data",
        "result": result,
        "c3_run_id": C3_RUN_ID,
        "runner_readiness": "ready",
        "target_audit": sample_clean_target(),
        "contract_summary": {"writes_outbox": True, "consumes_outbox": False},
    }


def sample_dry_run() -> dict[str, object]:
    return {
        "result": "DRY_RUN_PASS",
        "c3_run_id": C3_RUN_ID,
        "c2_run_id": C2_RUN_ID,
        "for_trade_date": "20260525",
        "candidate_summary": {
            "candidate_count_by_asset": {"stock": 17432, "index": 0, "board": 0, "total": 17432},
            "excluded_by_status": {"missing": 72, "partial": 0, "failed": 0, "total": 72},
        },
        "payload_validation_summary": {"validated_count": 17432, "blocked_count": 0},
        "duplicate_summary": {"duplicate_candidate_count": 0},
        "quality": {"p0_count": 0, "p1_count": 1, "p2_count": 0},
    }


def sample_clean_target() -> dict[str, object]:
    return {
        "run_exists": False,
        "quality_rows_for_c3_run": 0,
        "outbox_rows_for_c3_run": 0,
        "inbox_rows_for_c3_run": 0,
        "checkpoint_rows_for_c3_run": 0,
    }


def sample_enrichment_context() -> dict[str, object]:
    return build_trace_enrichment_context(
        subscription_rows=[
            {
                "subscription_id": 11,
                "run_id": SUBSCRIPTION_RUN_ID,
                "asset_kind": "stock",
                "identity_key": "stock:SH:600000",
                "required_data_kind": "minute_bar_1m",
                "data_trade_date": "20260525",
            },
            {
                "subscription_id": 12,
                "run_id": SUBSCRIPTION_RUN_ID,
                "asset_kind": "stock",
                "identity_key": "stock:BJ:920001",
                "required_data_kind": "minute_bar_1m",
                "data_trade_date": "20260525",
            },
        ],
        pull_plan_rows=[
            {
                "pull_plan_id": 34,
                "run_id": SUBSCRIPTION_RUN_ID,
                "asset_kind": "stock",
                "required_data_kind": "minute_bar_1m",
                "data_trade_date": "20260525",
                "adapter_name": "mootdx.std.bars.frequency8",
            }
        ],
    )


def summary_row(
    *,
    summary_id: int = 1,
    identity_key: str = "stock:SH:600000",
    exchange: str = "SH",
    code: str = "600000",
    bucket_id: str = "0931_1000",
    closed_status: str = "closed",
    subscription_id: int = 11,
) -> dict[str, object]:
    return {
        "summary_id": summary_id,
        "run_id": C2_RUN_ID,
        "source_condition_run_id": CONDITION_RUN_ID,
        "source_subscription_run_id": SUBSCRIPTION_RUN_ID,
        "source_today_minute_run_ids": [TODAY_MINUTE_RUN_ID],
        "for_trade_date": "20260525",
        "trade_date": "20260525",
        "asset_kind": "stock",
        "identity_key": identity_key,
        "exchange": exchange,
        "code": code,
        "display_code": code,
        "name": "sample",
        "bucket_id": bucket_id,
        "bucket_start": datetime(2026, 5, 25, 1, 31, tzinfo=timezone.utc),
        "bucket_end": datetime(2026, 5, 25, 2, 0, tzinfo=timezone.utc),
        "closed_status": closed_status,
        "quality_status": "passed" if closed_status == "closed" else "missing",
        "source_minute_bar_ids": [101],
        "replay_diff_json": {
            "source_minute_refs": [
                {
                    "source_kind": "C1",
                    "run_id": TODAY_MINUTE_RUN_ID,
                    "bar_id": 101,
                    "identity_key": identity_key,
                    "trade_date": "20260525",
                    "bar_time": "2026-05-25T09:31:00+08:00",
                }
            ]
        },
        "raw_json": {"subscription_id": subscription_id},
    }


if __name__ == "__main__":
    unittest.main()
