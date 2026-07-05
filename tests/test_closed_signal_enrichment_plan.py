import json
import unittest

from ashare_v3.market.closed_signal_enrichment_plan import (
    bucket_id_for_label,
    build_baseline_buckets,
    build_closed_signal_dry_run_report,
    build_write_scope_contract,
    calculate_enrichment_candidate,
)


class ClosedSignalEnrichmentPlanTests(unittest.TestCase):
    def test_bucket_rule_maps_8_closed_30m_windows(self) -> None:
        self.assertEqual(bucket_id_for_label("09:31"), "0931_1000")
        self.assertEqual(bucket_id_for_label("10:00"), "0931_1000")
        self.assertEqual(bucket_id_for_label("10:01"), "1001_1030")
        self.assertEqual(bucket_id_for_label("11:30"), "1101_1130")
        self.assertEqual(bucket_id_for_label("13:01"), "1301_1330")
        self.assertEqual(bucket_id_for_label("15:00"), "1431_1500")
        self.assertIsNone(bucket_id_for_label("11:31"))

    def test_baseline_bucket_amount_uses_previous_day_same_bucket(self) -> None:
        rows = [
            {"identity_key": "stock:SH:600000", "bar_time_label": "09:31", "amount": "10", "open": "1", "close": "2", "bar_id": 1},
            {"identity_key": "stock:SH:600000", "bar_time_label": "10:00", "amount": "20", "open": "2", "close": "3", "bar_id": 2},
            {"identity_key": "stock:SH:600000", "bar_time_label": "10:01", "amount": "40", "open": "3", "close": "4", "bar_id": 3},
        ]

        baseline = build_baseline_buckets(rows)

        first_bucket = baseline[("stock:SH:600000", "0931_1000")]
        second_bucket = baseline[("stock:SH:600000", "1001_1030")]
        self.assertEqual(str(first_bucket["baseline_window_amount"]), "30")
        self.assertEqual(first_bucket["baseline_minute_count"], 2)
        self.assertEqual(first_bucket["baseline_minute_bar_ids"], [1, 2])
        self.assertEqual(str(first_bucket["baseline_window_open"]), "1")
        self.assertEqual(str(first_bucket["baseline_window_close"]), "3")
        self.assertEqual(str(second_bucket["baseline_window_amount"]), "40")

    def test_calculates_price_direction_amount_ratio_and_signal(self) -> None:
        summary = {
            "summary_id": 10,
            "run_id": "c2",
            "source_condition_run_id": "condition",
            "source_subscription_run_id": "subscription",
            "for_trade_date": "20260525",
            "trade_date": "20260525",
            "asset_kind": "stock",
            "identity_key": "stock:SH:600000",
            "exchange": "SH",
            "code": "600000",
            "bucket_id": "0931_1000",
            "bucket_start": "2026-05-25T09:31:00+08:00",
            "bucket_end": "2026-05-25T10:00:00+08:00",
            "open": "100",
            "close": "101",
            "amount": "130",
            "closed_status": "closed",
            "quality_status": "passed",
        }
        baseline = {
            "baseline_window_amount": "100",
            "baseline_minute_count": 30,
            "baseline_minute_bar_ids": list(range(1, 31)),
        }

        candidate = calculate_enrichment_candidate(
            summary,
            baseline,
            c2b_run_id="c2b",
            source_previous_day_minute_run_id="a1",
            previous_day_minute_date="20260522",
        )

        self.assertEqual(candidate["closed_price_direction_status"], "up")
        self.assertEqual(candidate["closed_signal_status"], "up_volume_expanding")
        self.assertEqual(candidate["closed_market_shape_status"], "up_volume_expanding")
        self.assertEqual(candidate["closed_signal_quality_status"], "passed")
        self.assertEqual(str(candidate["closed_amount_ratio"]), "1.3")
        self.assertIn("baseline_minute_bar_ids", candidate["baseline_trace_json"])

    def test_flat_price_maps_to_flat_even_when_amount_expands(self) -> None:
        summary = {
            "summary_id": 11,
            "run_id": "c2",
            "source_condition_run_id": "condition",
            "source_subscription_run_id": "subscription",
            "for_trade_date": "20260525",
            "trade_date": "20260525",
            "asset_kind": "index",
            "identity_key": "index:SH:000001",
            "exchange": "SH",
            "code": "000001",
            "bucket_id": "0931_1000",
            "bucket_start": "2026-05-25T09:31:00+08:00",
            "bucket_end": "2026-05-25T10:00:00+08:00",
            "open": "100",
            "close": "100.05",
            "amount": "200",
            "closed_status": "closed",
            "quality_status": "passed",
        }
        candidate = calculate_enrichment_candidate(
            summary,
            {"baseline_window_amount": "100", "baseline_minute_count": 30, "baseline_minute_bar_ids": []},
            c2b_run_id="c2b",
            source_previous_day_minute_run_id="a1",
            previous_day_minute_date="20260522",
        )

        self.assertEqual(candidate["closed_price_direction_status"], "flat")
        self.assertEqual(candidate["closed_signal_status"], "flat")

    def test_missing_current_summary_becomes_unknown_without_fabricating_signal(self) -> None:
        summary = {
            "summary_id": 12,
            "run_id": "c2",
            "source_condition_run_id": "condition",
            "source_subscription_run_id": "subscription",
            "for_trade_date": "20260525",
            "trade_date": "20260525",
            "asset_kind": "stock",
            "identity_key": "stock:BJ:920045",
            "exchange": "BJ",
            "code": "920045",
            "bucket_id": "0931_1000",
            "bucket_start": "2026-05-25T09:31:00+08:00",
            "bucket_end": "2026-05-25T10:00:00+08:00",
            "open": None,
            "close": None,
            "amount": None,
            "closed_status": "missing",
            "quality_status": "missing",
        }

        candidate = calculate_enrichment_candidate(
            summary,
            None,
            c2b_run_id="c2b",
            source_previous_day_minute_run_id="a1",
            previous_day_minute_date="20260522",
        )

        self.assertEqual(candidate["closed_signal_status"], "unknown")
        self.assertEqual(candidate["closed_market_shape_status"], "unknown")
        self.assertEqual(candidate["closed_signal_quality_status"], "missing")
        self.assertIsNone(candidate["closed_amount_ratio"])

    def test_baseline_missing_becomes_warning_unknown(self) -> None:
        summary = {
            "summary_id": 13,
            "run_id": "c2",
            "source_condition_run_id": "condition",
            "source_subscription_run_id": "subscription",
            "for_trade_date": "20260525",
            "trade_date": "20260525",
            "asset_kind": "board",
            "identity_key": "board:TDX:881001",
            "exchange": "TDX",
            "code": "881001",
            "bucket_id": "0931_1000",
            "bucket_start": "2026-05-25T09:31:00+08:00",
            "bucket_end": "2026-05-25T10:00:00+08:00",
            "open": "100",
            "close": "99",
            "amount": "100",
            "closed_status": "closed",
            "quality_status": "passed",
        }

        candidate = calculate_enrichment_candidate(
            summary,
            None,
            c2b_run_id="c2b",
            source_previous_day_minute_run_id="a1",
            previous_day_minute_date="20260522",
        )

        self.assertEqual(candidate["closed_price_direction_status"], "down")
        self.assertEqual(candidate["closed_signal_status"], "unknown")
        self.assertEqual(candidate["closed_signal_quality_status"], "warning")

    def test_write_scope_is_no_outbox_no_downstream(self) -> None:
        scope = build_write_scope_contract()

        self.assertFalse(scope["writes_outbox"])
        self.assertIn("common_market_data_run", scope["allowed_future_execute_write_tables"])
        self.assertIn("stock_closed_30m_signal_enrichment", scope["allowed_future_execute_write_tables"])
        self.assertIn("common_event_outbox", scope["forbidden_write_tables"])
        self.assertIn("common_event_inbox", scope["forbidden_write_tables"])
        self.assertIn("common_event_consumer_checkpoint", scope["forbidden_write_tables"])
        self.assertIn("N4/N5/N6", scope["forbidden_write_tables"])

    def test_report_json_valid_and_read_only(self) -> None:
        report = build_closed_signal_dry_run_report(
            c2b_run_id="c2b",
            c2_run_id="c2",
            source_condition_run_id="condition",
            source_subscription_run_id="subscription",
            source_previous_day_minute_run_id="a1",
            for_trade_date="20260525",
            previous_day_minute_date="20260522",
            expected_rows={"stock": 1, "index": 0, "board": 0, "total": 1},
            candidates_by_asset={
                "stock": [
                    {
                        "asset_kind": "stock",
                        "closed_signal_status": "up_volume_expanding",
                        "closed_price_direction_status": "up",
                        "closed_signal_quality_status": "passed",
                    }
                ],
                "index": [],
                "board": [],
            },
            target_audit={
                "run_exists": False,
                "enrichment_rows_for_c2b_run": {"stock": 0, "index": 0, "board": 0},
                "quality_rows_for_c2b_run": 0,
                "outbox_rows_for_c2b_run": 0,
                "inbox_rows_for_c2b_run": 0,
                "checkpoint_rows_for_c2b_run": 0,
            },
            n4_replay_source={"closed_signal_status_missing": 35952, "c3_event_missing": 18},
        )

        json.dumps(report, ensure_ascii=False)
        self.assertEqual(report["result"], "DRY_RUN_PASS")
        self.assertFalse(report["blocked"])
        self.assertFalse(report["side_effects"]["writes_performed"])
        self.assertFalse(report["side_effects"]["event_outbox_written"])
        self.assertEqual(report["n4_replay_unblock_estimate"]["closed_signal_status_missing_after_c2b"], 0)
        self.assertEqual(report["quality"]["p0_count"], 0)


if __name__ == "__main__":
    unittest.main()
