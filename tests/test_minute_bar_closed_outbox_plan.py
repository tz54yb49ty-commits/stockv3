import json
import unittest
from datetime import datetime, timezone

from ashare_v3.market.minute_bar_closed_outbox_plan import (
    ALLOWED_FUTURE_EXECUTE_WRITE_TABLES,
    build_c3_run_id,
    build_minute_bar_closed_candidate,
    build_minute_bar_closed_dry_run_report,
    build_trace_enrichment_context,
    build_write_scope_contract,
)


C2_RUN_ID = (
    "closed_minute_30m_replay_20260525_until_1500__"
    "market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute"
)
CONDITION_RUN_ID = "condition_layer_20260522_to_20260525_20260525102249_execute"
SUBSCRIPTION_RUN_ID = "market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute"
TODAY_MINUTE_RUN_ID = (
    "today_minute_bar_1m_20260525_until_1411__"
    "market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute"
)


def summary_row(
    *,
    asset_kind: str = "stock",
    identity_key: str = "stock:SH:600000",
    summary_id: int = 73,
    bucket_id: str = "0931_1000",
    closed_status: str = "closed",
    code: str = "600000",
    exchange: str = "SH",
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
        "asset_kind": asset_kind,
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
        "source_minute_bar_ids": [101, 102],
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
        "raw_json": {
            "subscription_id": subscription_id,
            "resolved_minute_trace": [
                {
                    "source_kind": "C1",
                    "run_id": TODAY_MINUTE_RUN_ID,
                    "bar_id": 101,
                    "identity_key": identity_key,
                    "trade_date": "20260525",
                    "bar_time": "2026-05-25T09:31:00+08:00",
                }
            ],
        },
    }


def enrichment_context() -> dict[str, object]:
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
                "pull_plan_id": 22,
                "run_id": SUBSCRIPTION_RUN_ID,
                "asset_kind": "stock",
                "required_data_kind": "minute_bar_1m",
                "data_trade_date": "20260525",
                "adapter_name": "mootdx.std.bars.frequency8",
            }
        ],
    )


class MinuteBarClosedOutboxPlanTests(unittest.TestCase):
    def test_closed_only_generates_candidates_and_missing_is_excluded(self) -> None:
        report = build_minute_bar_closed_dry_run_report(
            c2_run_id=C2_RUN_ID,
            c3_run_id=build_c3_run_id(c2_run_id=C2_RUN_ID, for_trade_date="20260525"),
            source_condition_run_id=CONDITION_RUN_ID,
            source_subscription_run_id=SUBSCRIPTION_RUN_ID,
            for_trade_date="20260525",
            summary_rows_by_asset={
                "stock": [
                    summary_row(summary_id=1),
                    summary_row(
                        summary_id=2,
                        identity_key="stock:BJ:920001",
                        code="920001",
                        exchange="BJ",
                        subscription_id=12,
                        closed_status="missing",
                    ),
                ],
                "index": [],
                "board": [],
            },
            enrichment_context=enrichment_context(),
            target_audit={
                "run_exists": False,
                "quality_rows_for_c3_run": 0,
                "outbox_rows_for_c3_run": 0,
                "inbox_rows_for_c3_run": 0,
                "checkpoint_rows_for_c3_run": 0,
            },
            expected_counts={"stock": 1, "index": 0, "board": 0, "total": 1},
            expected_excluded={"missing": 1, "partial": 0, "failed": 0, "total": 1},
        )

        self.assertEqual(report["result"], "DRY_RUN_PASS")
        self.assertEqual(report["candidate_summary"]["candidate_count_by_asset"]["stock"], 1)
        self.assertEqual(report["candidate_summary"]["excluded_by_status"]["missing"], 1)
        self.assertEqual(report["candidate_summary"]["bj_920xxx_excluded_summary_rows"], 1)
        self.assertFalse(report["side_effects"]["event_outbox_written"])

    def test_payload_v2_validates_without_minute_bar_id(self) -> None:
        candidate = build_minute_bar_closed_candidate(
            summary=summary_row(),
            enrichment_context=enrichment_context(),
            c3_run_id=build_c3_run_id(c2_run_id=C2_RUN_ID, for_trade_date="20260525"),
        )

        self.assertIsNone(candidate.blocker)
        self.assertEqual(candidate.event.event_schema_version, "v2")
        self.assertEqual(candidate.event.event_type, "MinuteBarClosed")
        self.assertNotIn("minute_bar_id", candidate.event.payload_json)
        self.assertEqual(candidate.event.payload_json["closed_30m_summary_id"], 73)
        self.assertEqual(candidate.event.payload_json["pull_plan_id"], 22)
        self.assertTrue(candidate.event.payload_json["source_minute_refs"])

    def test_pull_plan_id_missing_blocks_candidate(self) -> None:
        context = build_trace_enrichment_context(
            subscription_rows=[
                {
                    "subscription_id": 11,
                    "run_id": SUBSCRIPTION_RUN_ID,
                    "asset_kind": "stock",
                    "identity_key": "stock:SH:600000",
                    "required_data_kind": "minute_bar_1m",
                    "data_trade_date": "20260525",
                }
            ],
            pull_plan_rows=[],
        )

        candidate = build_minute_bar_closed_candidate(
            summary=summary_row(),
            enrichment_context=context,
            c3_run_id=build_c3_run_id(c2_run_id=C2_RUN_ID, for_trade_date="20260525"),
        )

        self.assertIsNone(candidate.event)
        self.assertEqual(candidate.blocker["blocker_code"], "missing_pull_plan_id")

    def test_dedup_v2_is_stable_and_duplicate_candidates_are_detected(self) -> None:
        report = build_minute_bar_closed_dry_run_report(
            c2_run_id=C2_RUN_ID,
            c3_run_id=build_c3_run_id(c2_run_id=C2_RUN_ID, for_trade_date="20260525"),
            source_condition_run_id=CONDITION_RUN_ID,
            source_subscription_run_id=SUBSCRIPTION_RUN_ID,
            for_trade_date="20260525",
            summary_rows_by_asset={
                "stock": [summary_row(summary_id=1), summary_row(summary_id=1)],
                "index": [],
                "board": [],
            },
            enrichment_context=enrichment_context(),
            target_audit={
                "run_exists": False,
                "quality_rows_for_c3_run": 0,
                "outbox_rows_for_c3_run": 0,
                "inbox_rows_for_c3_run": 0,
                "checkpoint_rows_for_c3_run": 0,
            },
            expected_counts={"stock": 2, "index": 0, "board": 0, "total": 2},
            expected_excluded={"missing": 0, "partial": 0, "failed": 0, "total": 0},
        )

        self.assertEqual(report["duplicate_summary"]["duplicate_candidate_count"], 1)
        self.assertEqual(report["quality"]["p0_count"], 1)
        self.assertEqual(report["result"], "DRY_RUN_BLOCKED")

    def test_write_scope_is_future_outbox_only_and_no_downstream(self) -> None:
        scope = build_write_scope_contract()

        self.assertTrue(scope["future_execute_writes_outbox"])
        self.assertFalse(scope["dry_run_writes_outbox"])
        self.assertEqual(scope["allowed_future_execute_write_tables"], ALLOWED_FUTURE_EXECUTE_WRITE_TABLES)
        self.assertIn("common_event_outbox", scope["allowed_future_execute_write_tables"])
        self.assertIn("common_event_inbox", scope["forbidden_write_tables"])
        self.assertIn("common_event_consumer_checkpoint", scope["forbidden_write_tables"])
        self.assertIn("N4/N5/N6", scope["forbidden_write_tables"])

    def test_report_json_valid_and_read_only(self) -> None:
        report = build_minute_bar_closed_dry_run_report(
            c2_run_id=C2_RUN_ID,
            c3_run_id=build_c3_run_id(c2_run_id=C2_RUN_ID, for_trade_date="20260525"),
            source_condition_run_id=CONDITION_RUN_ID,
            source_subscription_run_id=SUBSCRIPTION_RUN_ID,
            for_trade_date="20260525",
            summary_rows_by_asset={"stock": [summary_row()], "index": [], "board": []},
            enrichment_context=enrichment_context(),
            target_audit={
                "run_exists": False,
                "quality_rows_for_c3_run": 0,
                "outbox_rows_for_c3_run": 0,
                "inbox_rows_for_c3_run": 0,
                "checkpoint_rows_for_c3_run": 0,
            },
            expected_counts={"stock": 1, "index": 0, "board": 0, "total": 1},
            expected_excluded={"missing": 0, "partial": 0, "failed": 0, "total": 0},
        )

        json.dumps(report, ensure_ascii=False, default=str)
        self.assertFalse(report["side_effects"]["writes_performed"])
        self.assertFalse(report["side_effects"]["event_outbox_written"])
        self.assertFalse(report["side_effects"]["downstream_layers_touched"])
        self.assertFalse(report["side_effects"]["worker_started"])


if __name__ == "__main__":
    unittest.main()
