from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_n3_c1_n3t_action_confirmation_fastlane_once import (  # noqa: E402
    _fixed_current_amount_from_context_row,
    _metric_context_artifact_needs_rolling_window_rebuild,
)


def minute_row(physical_label: str, raw_label: str, amount: float) -> dict[str, object]:
    return {
        "physical_c1_label": physical_label,
        "raw_source_label": raw_label,
        "amount": amount,
        "fake_or_synthetic_row": False,
    }


def metric_payload(
    rows: list[dict[str, object]],
    *,
    current_5m_amount: float,
    current_5m_elapsed_amount: float | None = None,
    current_30m_amount: float | None = None,
) -> dict[str, object]:
    metric_values = {
        "current_5m_amount": current_5m_amount,
        "current_5m_elapsed_amount": (
            current_5m_amount
            if current_5m_elapsed_amount is None
            else current_5m_elapsed_amount
        ),
    }
    if current_30m_amount is not None:
        metric_values["current_30m_closed_elapsed_amount"] = current_30m_amount
    return {
        "artifact_type": "n3_c1_scoped_closed_1m_artifact_v1",
        "for_trade_date": "20260720",
        "metric_context_rows": [
            {
                "closed_minute_rows": rows,
                "metric_values": metric_values,
            }
        ],
    }


class N3C1N3TFastlaneFixedPeriodTest(unittest.TestCase):
    def test_postclose_raw_1130_and_1300_share_physical_1300_without_hiding_afternoon_bucket(self) -> None:
        rows = [
            minute_row("13:00", "11:30", 100.0),
            *[
                minute_row(f"13:0{minute}", f"13:0{minute}", float(minute + 1))
                for minute in range(5)
            ],
        ]

        self.assertEqual(
            _fixed_current_amount_from_context_row(
                {"closed_minute_rows": rows},
                for_trade_date="20260720",
                size=5,
            ),
            15.0,
        )
        self.assertTrue(
            _metric_context_artifact_needs_rolling_window_rebuild(
                metric_payload(rows, current_5m_amount=100.0)
            )
        )

    def test_partial_fixed_5m_bucket_detects_stale_rolling_amount_at_0952(self) -> None:
        rows = [
            minute_row(f"09:{minute:02d}", f"09:{minute:02d}", float(minute))
            for minute in range(31, 53)
        ]

        self.assertEqual(
            _fixed_current_amount_from_context_row(
                {"closed_minute_rows": rows},
                for_trade_date="20260720",
                size=5,
            ),
            103.0,
        )
        self.assertEqual(
            _fixed_current_amount_from_context_row(
                {"closed_minute_rows": rows},
                for_trade_date="20260720",
                size=30,
            ),
            913.0,
        )
        self.assertFalse(
            _metric_context_artifact_needs_rolling_window_rebuild(
                metric_payload(
                    rows,
                    current_5m_amount=250.0,
                    current_5m_elapsed_amount=103.0,
                    current_30m_amount=913.0,
                )
            )
        )
        self.assertTrue(
            _metric_context_artifact_needs_rolling_window_rebuild(
                metric_payload(rows, current_5m_amount=sum(range(48, 53)))
            )
        )
        self.assertTrue(
            _metric_context_artifact_needs_rolling_window_rebuild(
                metric_payload(
                    rows,
                    current_5m_amount=103.0,
                    current_30m_amount=900.0,
                )
            )
        )


if __name__ == "__main__":
    unittest.main()
