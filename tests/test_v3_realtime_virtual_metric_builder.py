import unittest

from ashare_v3.market.realtime_virtual_metric import (
    REALTIME_VIRTUAL_METRIC_FIELD_ALIASES,
    REALTIME_VIRTUAL_METRIC_DB_COLUMNS,
    build_previous_day_cumulative_amount_rows,
    build_realtime_virtual_metric,
    build_previous_day_cumulative_summary_rows,
    canonicalize_realtime_virtual_metric_fields,
)


def bar(code, dt, open_, close, amount):
    high = max(open_, close)
    low = min(open_, close)
    return {
        "code": code,
        "datetime": dt,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "amount": amount,
    }


def canonical_trade_minute_labels(trade_date: str) -> list[str]:
    labels: list[str] = []
    for hour, minute_start, minute_end in (
        (9, 31, 59),
        (10, 0, 59),
        (11, 0, 29),
        (13, 0, 59),
        (14, 0, 59),
        (15, 0, 0),
    ):
        for minute in range(minute_start, minute_end + 1):
            labels.append(f"{trade_date} {hour:02d}:{minute:02d}")
    return labels


def canonical_previous_day_rows(code: str, trade_date: str = "2026-06-11", amount: float = 10.0) -> list[dict]:
    return [bar(code, label, 100.0, 101.0, amount) for label in canonical_trade_minute_labels(trade_date)]


def previous_day_rows_with_midday_bridge_1130(
    code: str, trade_date: str = "2026-06-11", amount: float = 10.0
) -> list[dict]:
    rows: list[dict] = []
    for label in canonical_trade_minute_labels(trade_date):
        raw_label = f"{trade_date} 11:30" if label.endswith(" 13:00") else label
        rows.append(bar(code, raw_label, 100.0, 101.0, amount))
    return rows


class V3RealtimeVirtualMetricBuilderTest(unittest.TestCase):
    def test_previous_day_cumulative_summary_builds_240_canonical_rows(self) -> None:
        rows = canonical_previous_day_rows("000001", amount=10.0)

        summary = build_previous_day_cumulative_summary_rows(
            rows,
            asset_kind="index",
            identity_key="index:SH:000001",
            source_previous_day_minute_run_id="a1_run",
        )

        self.assertEqual(len(summary), 240)
        row_0955 = next(row for row in summary if row["canonical_minute_label"] == "2026-06-11 09:55")
        self.assertEqual(row_0955["previous_day_elapsed_amount"], 250.0)
        self.assertEqual(row_0955["previous_day_full_amount"], 2400.0)
        self.assertEqual(row_0955["elapsed_count"], 25)
        self.assertEqual(row_0955["full_count"], 240)
        self.assertEqual(row_0955["source_previous_day_minute_run_id"], "a1_run")
        self.assertEqual(row_0955["raw_first_label"], "2026-06-11 09:31")
        self.assertEqual(row_0955["raw_last_label"], "2026-06-11 15:00")

    def test_previous_day_cumulative_summary_normalizes_midday_bridge_1130_to_1300(self) -> None:
        rows = previous_day_rows_with_midday_bridge_1130("000001", amount=10.0)

        summary = build_previous_day_cumulative_summary_rows(rows, asset_kind="index", identity_key="index:SH:000001")

        labels = [row["canonical_minute_label"] for row in summary]
        row_1300 = next(row for row in summary if row["canonical_minute_label"] == "2026-06-11 13:00")
        self.assertIn("2026-06-11 13:00", labels)
        self.assertNotIn("2026-06-11 11:30", labels)
        self.assertEqual(row_1300["raw_label"], "2026-06-11 11:30")
        self.assertEqual(row_1300["normalization_policy"], "previous_day_midday_bridge_1130_to_1300_v1")

    def test_previous_day_cumulative_summary_blocks_midday_duplicate(self) -> None:
        rows = [
            *canonical_previous_day_rows("000001", amount=10.0),
            bar("000001", "2026-06-11 11:30", 100.0, 101.0, 10.0),
        ]

        with self.assertRaisesRegex(ValueError, "previous_day_midday_bridge_duplicate"):
            build_previous_day_cumulative_summary_rows(rows, asset_kind="index", identity_key="index:SH:000001")

    def test_previous_day_cumulative_summary_blocks_incomplete_full_window(self) -> None:
        rows = canonical_previous_day_rows("000001", amount=10.0)[:-1]

        with self.assertRaisesRegex(ValueError, "previous_day_cumulative_full_window_incomplete"):
            build_previous_day_cumulative_summary_rows(rows, asset_kind="index", identity_key="index:SH:000001")

    def test_previous_day_cumulative_amount_rows_are_physical_asset_separated_and_unit_normalized(self) -> None:
        result = build_previous_day_cumulative_amount_rows(
            {
                "stock": [
                    {
                        **row,
                        "asset_kind": "stock",
                        "identity_key": "stock:SH:600000",
                        "exchange": "SH",
                    }
                    for row in canonical_previous_day_rows("600000", trade_date="2026-06-26", amount=10.0)
                ],
                "index": [
                    {
                        **row,
                        "asset_kind": "index",
                        "identity_key": "index:SH:000001",
                        "exchange": "SH",
                    }
                    for row in canonical_previous_day_rows("000001", trade_date="2026-06-26", amount=10.0)
                ],
                "board": [
                    {
                        **row,
                        "asset_kind": "board",
                        "identity_key": "board:TDX:881001",
                        "exchange": "TDX",
                    }
                    for row in canonical_previous_day_rows("881001", trade_date="2026-06-26", amount=10.0)
                ],
            },
            source_previous_day_minute_run_id="a1_run",
            for_trade_date="20260629",
            source_trade_date="20260626",
        )

        self.assertEqual(result["quality_summary"]["status"], "passed")
        self.assertEqual(result["quality_summary"]["row_count_by_asset"], {"stock": 240, "index": 240, "board": 240})
        stock_0955 = next(
            row
            for row in result["rows_by_asset"]["stock"]
            if row["canonical_minute_label"] == "2026-06-26 09:55"
        )
        index_0955 = next(
            row
            for row in result["rows_by_asset"]["index"]
            if row["canonical_minute_label"] == "2026-06-26 09:55"
        )
        self.assertEqual(stock_0955["source_amount_unit"], "thousand_yuan")
        self.assertEqual(stock_0955["canonical_amount_unit"], "yuan")
        self.assertEqual(stock_0955["unit_conversion_factor"], 1000.0)
        self.assertEqual(stock_0955["cumulative_amount_yuan"], 250000.0)
        self.assertEqual(stock_0955["full_day_amount_yuan"], 2400000.0)
        self.assertEqual(stock_0955["previous_day_elapsed_amount"], 250000.0)
        self.assertEqual(stock_0955["previous_day_full_amount"], 2400000.0)
        self.assertEqual(index_0955["source_amount_unit"], "yuan")
        self.assertEqual(index_0955["unit_conversion_factor"], 1.0)
        self.assertEqual(index_0955["cumulative_amount_yuan"], 250.0)
        self.assertEqual(index_0955["full_day_amount_yuan"], 2400.0)
        self.assertEqual(stock_0955["source_previous_day_minute_run_id"], "a1_run")
        self.assertEqual(stock_0955["for_trade_date"], "20260629")
        self.assertEqual(stock_0955["source_trade_date"], "20260626")
        self.assertIn("a1_run", stock_0955["cumulative_id"])
        self.assertEqual(stock_0955["raw_json"]["source_amount_unit"], "thousand_yuan")
        self.assertEqual(stock_0955["trace_json"]["physical_table_asset_kind"], "stock")

    def test_previous_day_cumulative_amount_rows_normalize_midday_bridge_without_fake_1130(self) -> None:
        result = build_previous_day_cumulative_amount_rows(
            {
                "board": [
                    {
                        **row,
                        "asset_kind": "board",
                        "identity_key": "board:TDX:881001",
                        "exchange": "TDX",
                    }
                    for row in previous_day_rows_with_midday_bridge_1130("881001", trade_date="2026-06-26", amount=10.0)
                ]
            },
            source_previous_day_minute_run_id="a1_run",
            for_trade_date="20260629",
            source_trade_date="20260626",
        )

        labels = [row["canonical_minute_label"] for row in result["rows_by_asset"]["board"]]
        row_1300 = next(row for row in result["rows_by_asset"]["board"] if row["canonical_minute_label"].endswith("13:00"))
        self.assertEqual(result["quality_summary"]["status"], "passed")
        self.assertIn("2026-06-26 13:00", labels)
        self.assertNotIn("2026-06-26 11:30", labels)
        self.assertEqual(row_1300["raw_bar_time"], "2026-06-26 11:30")
        self.assertEqual(row_1300["canonical_bar_time"], "2026-06-26 13:00")
        self.assertEqual(row_1300["normalization_policy"], "previous_day_midday_bridge_1130_to_1300_v1")
        self.assertEqual(row_1300["trace_json"]["normalization_policy"], "previous_day_midday_bridge_1130_to_1300_v1")

    def test_previous_day_cumulative_amount_rows_fail_closed_on_bad_source_shape(self) -> None:
        rows_with_duplicate = [
            *canonical_previous_day_rows("881001", trade_date="2026-06-26", amount=10.0),
            bar("881001", "2026-06-26 11:30", 100.0, 101.0, 10.0),
        ]
        duplicate = build_previous_day_cumulative_amount_rows(
            {
                "board": [
                    {
                        **row,
                        "asset_kind": "board",
                        "identity_key": "board:TDX:881001",
                    }
                    for row in rows_with_duplicate
                ]
            },
            source_previous_day_minute_run_id="a1_run",
            for_trade_date="20260629",
            source_trade_date="20260626",
        )
        mixed = build_previous_day_cumulative_amount_rows(
            {
                "stock": [
                    {
                        **row,
                        "asset_kind": "index",
                        "identity_key": "index:SH:000001",
                    }
                    for row in canonical_previous_day_rows("000001", trade_date="2026-06-26", amount=10.0)
                ]
            },
            source_previous_day_minute_run_id="a1_run",
            for_trade_date="20260629",
            source_trade_date="20260626",
        )

        self.assertEqual(duplicate["quality_summary"]["status"], "failed")
        self.assertTrue(any("previous_day_midday_bridge_duplicate" in error["reason"] for error in duplicate["errors"]))
        self.assertEqual(duplicate["rows_by_asset"]["board"], [])
        self.assertEqual(mixed["quality_summary"]["status"], "failed")
        self.assertTrue(any(error["reason"] == "mixed_physical_table_source_leakage" for error in mixed["errors"]))

    def test_auction_0931_label_can_enter_realtime_metric_before_0931_close(self) -> None:
        rows = [
            bar("000001", "2026-06-11 09:31", 8.0, 8.1, 10.0),
            bar("000001", "2026-06-11 09:32", 8.1, 8.2, 10.0),
            bar("000001", "2026-06-11 09:33", 8.2, 8.3, 10.0),
            bar("000001", "2026-06-11 09:34", 8.3, 8.4, 10.0),
            bar("000001", "2026-06-11 09:35", 8.4, 8.5, 10.0),
            bar("000001", "2026-06-11 14:56", 9.0, 10.0, 10.0),
            bar("000001", "2026-06-11 14:57", 10.0, 11.0, 10.0),
            bar("000001", "2026-06-11 14:58", 11.0, 12.0, 10.0),
            bar("000001", "2026-06-11 14:59", 12.0, 13.0, 10.0),
            bar("000001", "2026-06-11 15:00", 13.0, 14.0, 10.0),
            bar("000001", "2026-06-12 09:31", 14.0, 15.0, 20.0),
        ]

        metric = build_realtime_virtual_metric(
            rows,
            code="000001",
            minute_label="2026-06-12 09:31",
            observed_at="2026-06-12 09:25:03",
        )

        self.assertTrue(metric["metric_ready"], metric)
        self.assertEqual(metric["session_kind"], "auction")
        self.assertTrue(metric["is_auction_virtual"])
        self.assertFalse(metric["is_closed_1m"])
        self.assertEqual(metric["metric_time_label"], "2026-06-12 09:31")
        self.assertEqual(metric["previous_1m_period_source"], "previous_trade_date_last_period")
        self.assertGreater(len(metric["previous_day_minute_refs"]), 0)
        self.assertIn("2026-06-11 15:00", metric["previous_day_minute_refs"])
        self.assertEqual(metric["raw_json"]["auction_policy"], "mootdx_0931_label_as_auction_realtime_virtual_1m")
        self.assertIn("B_BUY", metric["deterministic_pass_flags"])
        self.assertIn("S_SELL", metric["deterministic_pass_flags"])
        self.assertEqual(metric["quality_status"], "passed")

    def test_midday_1301_compares_previous_1m_to_1300_label(self) -> None:
        rows = [
            bar("881001", "2026-04-22 13:00", 9.0, 10.0, 100.0),
            bar("881001", "2026-04-22 13:01", 10.0, 11.0, 200.0),
            bar("881001", "2026-04-22 13:02", 11.0, 12.0, 300.0),
            bar("881001", "2026-04-22 13:03", 12.0, 13.0, 400.0),
            bar("881001", "2026-04-22 13:04", 13.0, 14.0, 500.0),
            bar("881001", "2026-04-23 11:26", 10.0, 11.0, 10.0),
            bar("881001", "2026-04-23 11:27", 11.0, 12.0, 20.0),
            bar("881001", "2026-04-23 11:28", 12.0, 13.0, 30.0),
            bar("881001", "2026-04-23 11:29", 13.0, 14.0, 40.0),
            bar("881001", "2026-04-23 13:00", 14.0, 15.0, 50.0),
            bar("881001", "2026-04-23 13:01", 16.0, 17.0, 60.0),
        ]

        metric = build_realtime_virtual_metric(
            rows,
            code="881001",
            minute_label="2026-04-23 13:01",
            observed_at="2026-04-23 13:01:08",
        )

        self.assertTrue(metric["metric_ready"], metric)
        self.assertEqual(metric["previous_1m_body_high"], 15.0)
        self.assertEqual(metric["previous_1m_body_low"], 14.0)
        self.assertEqual(metric["previous_1m_amount"], 50.0)
        self.assertIsNone(metric["midday_bridge_policy"])
        self.assertEqual(metric["raw_json"]["canonical_minute_policy"], "ashare_cn_1m_v1")
        self.assertNotIn("13:00_label_equivalent_to_missing_11:30_bar", str(metric))
        self.assertEqual(metric["previous_5m_full_amount"], 150.0)
        self.assertEqual(metric["current_5m_virtual_amount"], 60.0 / 200.0 * 1400.0)

    def test_higher_period_virtual_amounts_use_supplied_n2_period_context(self) -> None:
        rows = [
            bar("000001", "2026-06-11 09:31", 8.0, 8.1, 100.0),
            bar("000001", "2026-06-11 09:32", 8.1, 8.2, 200.0),
            bar("000001", "2026-06-11 09:33", 8.2, 8.3, 300.0),
            bar("000001", "2026-06-11 14:56", 9.0, 10.0, 10.0),
            bar("000001", "2026-06-11 14:57", 10.0, 11.0, 10.0),
            bar("000001", "2026-06-11 14:58", 11.0, 12.0, 10.0),
            bar("000001", "2026-06-11 14:59", 12.0, 13.0, 10.0),
            bar("000001", "2026-06-11 15:00", 13.0, 14.0, 10.0),
            bar("000001", "2026-06-12 09:31", 10.0, 11.0, 20.0),
            bar("000001", "2026-06-12 09:32", 11.0, 12.0, 30.0),
            bar("000001", "2026-06-12 09:33", 12.0, 13.0, 40.0),
        ]
        higher_context = {
            "D": {"current_open": 10.0, "previous_open": 8.0, "previous_close": 12.0, "previous_amount": 1000.0, "elapsed_units": 3, "total_units": 240},
            "W": {"current_open": 9.0, "previous_open": 7.0, "previous_close": 8.0, "previous_amount": 5000.0, "elapsed_units": 1, "total_units": 5},
            "M": {"current_open": 8.0, "previous_open": 6.0, "previous_close": 7.0, "previous_amount": 20000.0, "elapsed_units": 1, "total_units": 20},
            "Q": {"current_open": 7.0, "previous_open": 5.0, "previous_close": 6.0, "previous_amount": 60000.0, "elapsed_units": 1, "total_units": 60},
            "Y": {"current_open": 6.0, "previous_open": 4.0, "previous_close": 5.0, "previous_amount": 240000.0, "elapsed_units": 1, "total_units": 240},
        }

        metric = build_realtime_virtual_metric(
            rows,
            code="000001",
            minute_label="2026-06-12 09:33",
            higher_period_context=higher_context,
        )

        self.assertTrue(metric["metric_ready"], metric)
        self.assertEqual(metric["current_d_body_high"], 13.0)
        self.assertEqual(metric["current_d_body_low"], 10.0)
        self.assertEqual(metric["previous_d_body_high"], 12.0)
        self.assertEqual(metric["previous_d_body_low"], 8.0)
        self.assertAlmostEqual(metric["current_d_virtual_amount"], 90.0 / 3.0 * 240.0)
        self.assertEqual(metric["previous_d_amount"], 1000.0)
        self.assertAlmostEqual(metric["current_w_virtual_amount"], 90.0 / 1.0 * 5.0)
        self.assertAlmostEqual(metric["current_y_virtual_amount"], 90.0 / 1.0 * 240.0)
        self.assertEqual(metric["period_source"]["D"], "n2_period_context_plus_intraday_1m")
        self.assertEqual(metric["period_source"]["Y"], "n2_period_context_plus_intraday_1m")
        self.assertNotIn("current_D_body_high", metric)
        self.assertNotIn("current_Y_virtual_amount", metric)

    def test_previous_day_same_window_amount_uses_previous_trade_date_same_30m_segment(self) -> None:
        rows = [
            bar("000001", "2026-06-11 09:31", 9.0, 9.1, 100.0),
            bar("000001", "2026-06-11 09:32", 9.1, 9.2, 200.0),
            bar("000001", "2026-06-11 09:33", 9.2, 9.3, 300.0),
            bar("000001", "2026-06-12 09:31", 10.0, 10.1, 10.0),
            bar("000001", "2026-06-12 09:32", 10.1, 10.2, 20.0),
            bar("000001", "2026-06-12 09:33", 10.2, 10.3, 30.0),
        ]

        metric = build_realtime_virtual_metric(
            rows,
            code="000001",
            minute_label="2026-06-12 09:33",
        )

        self.assertEqual(metric["current_30m_virtual_amount"], 60.0)
        self.assertEqual(metric["previous_day_same_window_amount"], 600.0)
        self.assertEqual(metric["virtual_amount_policy_version"], "previous_day_same_window_elapsed_ratio_v1")
        self.assertEqual(
            metric["trace_json"]["virtual_amount_policy"]["periods"]["30m"]["previous_day_same_elapsed_amount"],
            600.0,
        )
        self.assertIn("2026-06-11 09:31", metric["previous_day_minute_refs"])
        self.assertIn("previous_day_same_window_amount", REALTIME_VIRTUAL_METRIC_DB_COLUMNS)

    def test_5m_and_30m_virtual_amounts_use_previous_day_same_elapsed_ratio(self) -> None:
        rows = [
            bar("000001", "2026-06-11 09:31", 9.0, 9.1, 100.0),
            bar("000001", "2026-06-11 09:32", 9.1, 9.2, 200.0),
            bar("000001", "2026-06-11 09:33", 9.2, 9.3, 300.0),
            bar("000001", "2026-06-12 09:31", 10.0, 10.1, 10.0),
            bar("000001", "2026-06-12 09:32", 10.1, 10.2, 20.0),
        ]

        metric = build_realtime_virtual_metric(
            rows,
            code="000001",
            minute_label="2026-06-12 09:32",
        )

        expected = 30.0 / 300.0 * 600.0
        self.assertEqual(metric["current_5m_virtual_amount"], expected)
        self.assertEqual(metric["current_30m_virtual_amount"], expected)
        self.assertNotEqual(metric["current_30m_virtual_amount"], 30.0 / 2.0 * 30.0)
        self.assertEqual(
            metric["raw_json"]["virtual_amount_policy_version"],
            "previous_day_same_window_elapsed_ratio_v1",
        )

    def test_virtual_amount_policy_proof_contains_required_trace_fields(self) -> None:
        rows = [
            bar("000001", "2026-06-11 09:31", 9.0, 9.1, 100.0),
            bar("000001", "2026-06-11 09:32", 9.1, 9.2, 200.0),
            bar("000001", "2026-06-11 09:33", 9.2, 9.3, 300.0),
            bar("000001", "2026-06-12 09:31", 10.0, 10.1, 10.0),
            bar("000001", "2026-06-12 09:32", 10.1, 10.2, 20.0),
        ]

        metric = build_realtime_virtual_metric(
            rows,
            code="000001",
            minute_label="2026-06-12 09:32",
        )

        for period in ("5m", "30m"):
            proof = metric["trace_json"]["virtual_amount_policy"]["periods"][period]
            self.assertEqual(proof["metric_policy"], "previous_day_same_window_elapsed_ratio_v1")
            self.assertEqual(proof["current_period_amount_source_kind"], "N3_standard_period_metric")
            self.assertEqual(proof["amount_unit"], "yuan")
            self.assertEqual(proof["current_elapsed_amount"], 30.0)
            self.assertEqual(proof["previous_day_same_elapsed_amount"], 300.0)
            self.assertEqual(proof["previous_day_same_full_amount"], 600.0)
        self.assertEqual(metric["previous_day_same_5m_full_amount"], 600.0)
        self.assertEqual(metric["previous_day_same_30m_full_amount"], 600.0)

    def test_5m_and_30m_virtual_amount_fail_closed_when_same_elapsed_missing(self) -> None:
        rows = [
            bar("000001", "2026-06-11 09:31", 9.0, 9.1, 100.0),
            bar("000001", "2026-06-12 09:31", 10.0, 10.1, 10.0),
            bar("000001", "2026-06-12 09:32", 10.1, 10.2, 20.0),
        ]

        metric = build_realtime_virtual_metric(
            rows,
            code="000001",
            minute_label="2026-06-12 09:32",
        )

        self.assertFalse(metric["metric_ready"], metric)
        self.assertIsNone(metric["current_5m_virtual_amount"])
        self.assertIsNone(metric["current_30m_virtual_amount"])
        self.assertIn(
            "current_5m_virtual_amount_calibration_failed:previous_day_same_elapsed_window_incomplete",
            metric["blocked_reasons"],
        )
        self.assertIn(
            "current_30m_virtual_amount_calibration_failed:previous_day_same_elapsed_window_incomplete",
            metric["blocked_reasons"],
        )

    def test_formal_amount_chain_metrics_use_today_virtual_and_period_averages(self) -> None:
        rows = [
            bar("000001", "2026-06-11 09:31", 8.0, 8.1, 100.0),
            bar("000001", "2026-06-11 09:32", 8.1, 8.2, 200.0),
            bar("000001", "2026-06-11 09:33", 8.2, 8.3, 300.0),
            bar("000001", "2026-06-11 09:34", 8.3, 8.4, 400.0),
            bar("000001", "2026-06-11 09:35", 8.4, 8.5, 500.0),
            bar("000001", "2026-06-12 09:31", 10.0, 11.0, 10.0),
            bar("000001", "2026-06-12 09:32", 11.0, 12.0, 20.0),
            bar("000001", "2026-06-12 09:33", 12.0, 13.0, 30.0),
        ]
        higher_context = {
            "D": {"current_open": 10.0, "previous_open": 8.0, "previous_close": 12.0, "previous_amount": 1500.0, "elapsed_units": 3, "total_units": 240},
            "W": {
                "current_open": 9.0,
                "previous_open": 7.0,
                "previous_close": 8.0,
                "previous_amount": 2500.0,
                "current_amount_seed": 300.0,
                "current_trade_days_seed": 2,
                "elapsed_units": 2,
                "total_units": 5,
            },
            "M": {
                "current_open": 8.0,
                "previous_open": 6.0,
                "previous_close": 7.0,
                "previous_amount": 8000.0,
                "current_amount_seed": 900.0,
                "current_trade_days_seed": 3,
                "elapsed_units": 3,
                "total_units": 20,
            },
            "Q": {
                "current_open": 7.0,
                "previous_open": 5.0,
                "previous_close": 6.0,
                "previous_amount": 18000.0,
                "current_amount_seed": 1800.0,
                "current_trade_days_seed": 4,
                "elapsed_units": 4,
                "total_units": 60,
            },
            "Y": {
                "current_open": 6.0,
                "previous_open": 4.0,
                "previous_close": 5.0,
                "previous_amount": 48000.0,
                "current_amount_seed": 3000.0,
                "current_trade_days_seed": 5,
                "elapsed_units": 5,
                "total_units": 240,
            },
        }

        metric = build_realtime_virtual_metric(
            rows,
            code="000001",
            minute_label="2026-06-12 09:33",
            higher_period_context=higher_context,
        )

        self.assertTrue(metric["metric_ready"], metric)
        self.assertEqual(metric["today_virt_amount"], 150.0)
        self.assertEqual(metric["weekly_avg_with_today"], (300.0 * 2.0 * 1000.0 + 150.0) / 3.0)
        self.assertEqual(metric["monthly_avg_with_today"], (900.0 * 3.0 * 1000.0 + 150.0) / 4.0)
        self.assertEqual(metric["quarterly_avg_with_today"], (1800.0 * 4.0 * 1000.0 + 150.0) / 5.0)
        self.assertEqual(metric["yearly_avg_with_today"], (3000.0 * 5.0 * 1000.0 + 150.0) / 6.0)
        self.assertEqual(metric["prev_weekly_avg"], 500.0 * 1000.0)
        self.assertEqual(metric["prev_monthly_avg"], 400.0 * 1000.0)
        self.assertEqual(metric["prev_quarterly_avg"], 300.0 * 1000.0)
        self.assertEqual(metric["prev_yearly_avg"], 200.0 * 1000.0)
        proof = metric["trace_json"]["formal_period_amount_proof"]
        self.assertEqual(proof["source_kind"], "N3_standard_period_metric")
        self.assertEqual(proof["amount_unit"], "yuan")
        self.assertEqual(proof["source_amount_unit"], "thousand_yuan")
        self.assertEqual(proof["unit_conversion_policy"], "formal_amount_chain_thousand_yuan_to_yuan_v1")
        self.assertEqual(proof["amount_chain_metrics"]["today_virt_amount"], 150.0)
        self.assertEqual(metric["trace_json"]["formal_amount_chain_metrics"]["prev_weekly_avg"], 500.0 * 1000.0)
        self.assertEqual(proof["periods"]["W"]["current_amount_total_seed_yuan"], 300.0 * 2.0 * 1000.0)
        self.assertEqual(proof["periods"]["W"]["today_virt_amount_yuan"], 150.0)
        self.assertEqual(proof["periods"]["W"]["with_today_units"], 3.0)
        self.assertEqual(proof["periods"]["W"]["previous_avg_amount_yuan"], 500.0 * 1000.0)

    def test_formal_amount_chain_metrics_fail_closed_without_seed_days(self) -> None:
        rows = [
            bar("000001", "2026-06-11 09:31", 8.0, 8.1, 100.0),
            bar("000001", "2026-06-11 09:32", 8.1, 8.2, 200.0),
            bar("000001", "2026-06-11 09:33", 8.2, 8.3, 300.0),
            bar("000001", "2026-06-12 09:31", 10.0, 11.0, 10.0),
            bar("000001", "2026-06-12 09:32", 11.0, 12.0, 20.0),
            bar("000001", "2026-06-12 09:33", 12.0, 13.0, 30.0),
        ]
        higher_context = {
            "W": {
                "current_open": 9.0,
                "previous_open": 7.0,
                "previous_close": 8.0,
                "previous_amount": 2500.0,
                "current_amount_seed": 300.0,
                "total_units": 5,
            },
        }

        metric = build_realtime_virtual_metric(
            rows,
            code="000001",
            minute_label="2026-06-12 09:33",
            higher_period_context=higher_context,
        )

        self.assertIsNone(metric["weekly_avg_with_today"])
        proof = metric["trace_json"]["formal_period_amount_proof"]
        self.assertEqual(proof["periods"]["W"]["avg_status"], "failed")
        self.assertEqual(proof["periods"]["W"]["avg_blocked_reason"], "missing_current_trade_days_seed")

    def test_field_alias_registry_maps_display_names_to_lowercase_db_columns(self) -> None:
        self.assertEqual(REALTIME_VIRTUAL_METRIC_FIELD_ALIASES["current_D_body_high"], "current_d_body_high")
        self.assertEqual(REALTIME_VIRTUAL_METRIC_FIELD_ALIASES["previous_Y_amount"], "previous_y_amount")
        self.assertIn("current_d_body_high", REALTIME_VIRTUAL_METRIC_DB_COLUMNS)
        self.assertIn("previous_y_amount", REALTIME_VIRTUAL_METRIC_DB_COLUMNS)
        self.assertNotIn("current_D_body_high", REALTIME_VIRTUAL_METRIC_DB_COLUMNS)

    def test_canonicalize_realtime_virtual_metric_fields_accepts_display_aliases(self) -> None:
        row = {
            "current_D_body_high": 13.0,
            "previous_Y_amount": 240000.0,
            "current_30m_virtual_amount": 1200.0,
            "previous_day_same_window_amount": 900.0,
        }

        canonical = canonicalize_realtime_virtual_metric_fields(row)

        self.assertEqual(canonical["current_d_body_high"], 13.0)
        self.assertEqual(canonical["previous_y_amount"], 240000.0)
        self.assertEqual(canonical["current_30m_virtual_amount"], 1200.0)
        self.assertEqual(canonical["previous_day_same_window_amount"], 900.0)
        self.assertNotIn("current_D_body_high", canonical)
        self.assertNotIn("previous_Y_amount", canonical)


if __name__ == "__main__":
    unittest.main()
