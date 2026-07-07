import unittest
from datetime import datetime

from ashare_v3.market.minute_label_normalization import (
    ASHARE_CN_1M_CANONICAL_POLICY,
    MOOTDX_INTRADAY_1130_TO_PHYSICAL_1129_POLICY,
    MOOTDX_INTRADAY_1300_TO_1130_POLICY,
    MinuteLabelNormalizationError,
    ashare_c1_minute_close_time,
    canonical_ashare_1m_labels,
    next_ashare_c1_trading_minute_label,
    normalize_c1_physical_intraday_1m_labels,
    normalize_mootdx_intraday_1m_labels,
    normalize_ashare_c1_target_minute_label,
    previous_ashare_c1_trading_minute_label,
    validate_ashare_c1_minute_label,
)

def row(label: str, *, identity_key: str = "stock:SH:600000") -> dict[str, object]:
    return {
        "identity_key": identity_key,
        "bar_time": datetime.fromisoformat(label).replace(tzinfo=None),
        "open": 10,
        "close": 11,
        "amount": 100,
        "raw_payload": {},
    }


class MinuteLabelNormalizationTest(unittest.TestCase):
    def test_legacy_mootdx_raw_1300_bridge_remains_trace_only_compatibility(self) -> None:
        rows = normalize_mootdx_intraday_1m_labels(
            [row("2026-06-26T11:29:00"), row("2026-06-26T13:00:00"), row("2026-06-26T13:01:00")],
            trade_date="20260626",
            intraday_trade_date="20260626",
            source_adapter="mootdx",
        )

        self.assertEqual([item["bar_time"].strftime("%H:%M") for item in rows], ["11:29", "11:30", "13:01"])
        trace = rows[1]["raw_payload"]
        self.assertEqual(trace["raw_bar_time"], "2026-06-26T13:00:00+08:00")
        self.assertEqual(trace["source_bar_time"], "2026-06-26T13:00:00+08:00")
        self.assertEqual(trace["canonical_bar_time"], "2026-06-26T11:30:00+08:00")
        self.assertEqual(trace["time_label_normalization"], MOOTDX_INTRADAY_1300_TO_1130_POLICY)
        self.assertEqual(trace["canonical_minute_policy"], ASHARE_CN_1M_CANONICAL_POLICY)

    def test_c1_physical_current_day_maps_raw_1300_to_morning_close_and_1301_to_afternoon_open(self) -> None:
        rows = normalize_c1_physical_intraday_1m_labels(
            [row("2026-06-26T11:29:00"), row("2026-06-26T13:00:00"), row("2026-06-26T13:01:00")],
            trade_date="20260626",
            intraday_trade_date="20260626",
            source_adapter="mootdx",
        )

        self.assertEqual([item["bar_time"].strftime("%H:%M") for item in rows], ["11:28", "11:29", "13:00"])
        self.assertEqual(rows[1]["raw_source_label"], "13:00")
        self.assertEqual(rows[1]["physical_c1_label"], "11:29")
        self.assertEqual(rows[2]["raw_source_label"], "13:01")
        self.assertEqual(rows[2]["physical_c1_label"], "13:00")

    def test_c1_physical_current_day_raw_1130_maps_to_physical_1129_with_trace(self) -> None:
        rows = normalize_c1_physical_intraday_1m_labels(
            [row("2026-06-26T11:30:00")],
            trade_date="20260626",
            intraday_trade_date="20260626",
            source_adapter="mootdx",
        )

        self.assertEqual(rows[0]["bar_time"].strftime("%H:%M"), "11:29")
        self.assertEqual(rows[0]["raw_source_label"], "11:30")
        self.assertEqual(rows[0]["physical_c1_label"], "11:29")
        self.assertEqual(rows[0]["raw_payload"]["raw_source_label"], "11:30")
        self.assertEqual(rows[0]["raw_payload"]["physical_c1_label"], "11:29")
        self.assertEqual(
            rows[0]["raw_payload"]["time_label_normalization"],
            MOOTDX_INTRADAY_1130_TO_PHYSICAL_1129_POLICY,
        )
        self.assertNotEqual(
            rows[0]["raw_payload"]["time_label_normalization"],
            MOOTDX_INTRADAY_1300_TO_1130_POLICY,
        )

    def test_c1_physical_current_day_dedupes_raw_1130_and_1300_as_same_physical_1129(self) -> None:
        rows = normalize_c1_physical_intraday_1m_labels(
            [
                row("2026-06-26T11:29:00"),
                row("2026-06-26T11:30:00"),
                row("2026-06-26T13:00:00"),
            ],
            trade_date="20260626",
            intraday_trade_date="20260626",
            source_adapter="mootdx",
        )

        self.assertEqual([item["bar_time"].strftime("%H:%M") for item in rows], ["11:28", "11:29"])
        self.assertEqual(rows[0]["raw_source_label"], "11:29")
        self.assertEqual(rows[0]["physical_c1_label"], "11:28")
        self.assertEqual(rows[1]["raw_source_label"], "11:30")
        self.assertEqual(rows[1]["physical_c1_label"], "11:29")
        self.assertEqual(
            rows[1]["raw_payload"]["time_label_normalization"],
            MOOTDX_INTRADAY_1130_TO_PHYSICAL_1129_POLICY,
        )

    def test_historical_mootdx_1130_is_not_rewritten(self) -> None:
        rows = normalize_mootdx_intraday_1m_labels(
            [row("2026-06-25T11:30:00")],
            trade_date="20260625",
            intraday_trade_date="20260626",
            source_adapter="mootdx",
        )

        self.assertEqual(rows[0]["bar_time"].strftime("%H:%M"), "11:30")
        self.assertNotIn("time_label_normalization", rows[0]["raw_payload"])

    def test_raw_1130_and_1300_same_identity_fail_closed(self) -> None:
        with self.assertRaisesRegex(MinuteLabelNormalizationError, "duplicate-source anomaly"):
            normalize_mootdx_intraday_1m_labels(
                [row("2026-06-26T11:30:00"), row("2026-06-26T13:00:00")],
                trade_date="20260626",
                intraday_trade_date="20260626",
                source_adapter="mootdx",
            )

    def test_c1_valid_minute_labels_are_start_labels_and_skip_lunch_boundary(self) -> None:
        labels = canonical_ashare_1m_labels("20260626")

        self.assertEqual(len(labels), 240)
        self.assertEqual(labels[0], "09:30")
        self.assertEqual(labels[119], "11:29")
        self.assertEqual(labels[120], "13:00")
        self.assertEqual(labels[-1], "14:59")
        self.assertNotIn("11:30", labels)
        self.assertIn("13:00", labels)

    def test_c1_lunch_break_labels_are_not_interchangeable(self) -> None:
        self.assertEqual(
            ashare_c1_minute_close_time("20260626", "11:29").strftime("%H:%M"),
            "11:30",
        )
        self.assertEqual(
            ashare_c1_minute_close_time("20260626", "13:00").strftime("%H:%M"),
            "13:01",
        )
        self.assertEqual(previous_ashare_c1_trading_minute_label("13:00"), "11:29")
        self.assertEqual(next_ashare_c1_trading_minute_label("11:29"), "13:00")
        self.assertNotEqual("13:00", "11:30")

    def test_1130_is_session_boundary_not_physical_c1_bar_label(self) -> None:
        with self.assertRaisesRegex(MinuteLabelNormalizationError, "BLOCKED_C1_MINUTE_LABEL_NOT_TRADABLE"):
            validate_ashare_c1_minute_label("11:30")

        fail_closed = normalize_ashare_c1_target_minute_label("11:30")
        self.assertEqual(fail_closed["status"], "blocked")
        self.assertEqual(fail_closed["reason"], "BLOCKED_C1_MINUTE_LABEL_NOT_TRADABLE")

        normalized = normalize_ashare_c1_target_minute_label("11:30", policy="latest_closed_tradable")
        self.assertEqual(normalized["status"], "normalized")
        self.assertEqual(normalized["normalized_minute_label"], "11:29")
        self.assertEqual(normalized["reason"], "session_close_boundary_latest_closed_tradable")


if __name__ == "__main__":
    unittest.main()
