import json
import sqlite3
import tempfile
import unittest

from ashare_v3.market.b_buy_s_sell_replay_compare import (
    build_metric_for_minute,
    build_replay_report,
    evaluate_b_buy_s_sell,
    load_target_actions,
    OldSystemReadConfirmationRequired,
)
from ashare_v3.events.models import N5_RUNTIME_SIGNAL_TYPES


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


class V3BBuySSellReplayCompareTest(unittest.TestCase):
    def test_metric_builder_computes_previous_bodies_and_virtual_amounts(self):
        rows = [
            bar("000001", "2026-06-11 14:31", 8.0, 9.0, 10.0),
            bar("000001", "2026-06-11 14:32", 9.0, 10.0, 10.0),
            bar("000001", "2026-06-11 14:33", 10.0, 11.0, 10.0),
            bar("000001", "2026-06-11 14:34", 11.0, 12.0, 10.0),
            bar("000001", "2026-06-11 14:35", 12.0, 13.0, 20.0),
            bar("000001", "2026-06-12 09:31", 10.0, 11.0, 20.0),
            bar("000001", "2026-06-12 09:32", 11.0, 12.0, 20.0),
            bar("000001", "2026-06-12 09:33", 12.0, 14.0, 30.0),
        ]

        metric = build_metric_for_minute(rows, code="000001", minute_label="2026-06-12 09:33")

        self.assertTrue(metric["metric_ready"], metric)
        self.assertEqual(metric["current_price"], 14.0)
        self.assertEqual(metric["previous_1m_body_high"], 12.0)
        self.assertEqual(metric["previous_1m_body_low"], 11.0)
        self.assertEqual(metric["previous_5m_body_high"], 13.0)
        self.assertEqual(metric["previous_5m_body_low"], 8.0)
        self.assertEqual(metric["previous_30m_period_source"], "previous_trade_date_last_period")
        self.assertEqual(metric["previous_120m_period_source"], "previous_trade_date_last_period")
        self.assertAlmostEqual(metric["current_5m_virtual_amount"], 70.0 / 3.0 * 5.0)
        self.assertEqual(metric["previous_5m_full_amount"], 60.0)

    def test_midday_1300_label_is_1130_equivalent_for_1301_metric_context(self):
        rows = [
            bar("881001", "2026-04-23 11:26", 10.0, 11.0, 10.0),
            bar("881001", "2026-04-23 11:27", 11.0, 12.0, 20.0),
            bar("881001", "2026-04-23 11:28", 12.0, 13.0, 30.0),
            bar("881001", "2026-04-23 11:29", 13.0, 14.0, 40.0),
            bar("881001", "2026-04-23 13:00", 14.0, 15.0, 50.0),
            bar("881001", "2026-04-23 13:01", 16.0, 17.0, 60.0),
        ]

        metric = build_metric_for_minute(rows, code="881001", minute_label="2026-04-23 13:01")

        self.assertTrue(metric["metric_ready"], metric)
        self.assertEqual(metric["previous_1m_body_high"], 15.0)
        self.assertEqual(metric["previous_1m_body_low"], 14.0)
        self.assertEqual(metric["previous_1m_amount"], 50.0)
        self.assertEqual(metric["previous_5m_full_amount"], 150.0)
        self.assertEqual(metric["current_5m_virtual_amount"], 300.0)
        self.assertEqual(metric["previous_5m_period_source"], "same_trade_date_previous_period")
        self.assertEqual(
            metric["raw_json"]["midday_bridge_policy"],
            "13:00_label_equivalent_to_missing_11:30_bar",
        )

    def test_canonical_b_buy_and_s_sell_rules_are_evaluated_without_changing_n4_n5_types(self):
        buy_metric = {
            "metric_ready": True,
            "current_price": 14.0,
            "previous_120m_body_high": 10.0,
            "previous_30m_body_high": 11.0,
            "previous_5m_body_high": 12.0,
            "previous_1m_body_high": 13.0,
            "previous_120m_body_low": 8.0,
            "previous_30m_body_low": 8.0,
            "previous_5m_body_low": 8.0,
            "previous_1m_body_low": 8.0,
            "current_5m_virtual_amount": 200.0,
            "previous_5m_full_amount": 100.0,
            "current_1m_amount": 30.0,
            "previous_1m_amount": 20.0,
            "is_first_1m_of_day": False,
            "is_first_5m_of_day": False,
        }
        sell_metric = dict(buy_metric)
        sell_metric.update(
            {
                "current_price": 7.0,
                "current_5m_virtual_amount": 50.0,
                "current_1m_amount": 10.0,
            }
        )

        self.assertTrue(evaluate_b_buy_s_sell("B_BUY", buy_metric)["passed"])
        self.assertTrue(evaluate_b_buy_s_sell("S_SELL", sell_metric)["passed"])
        self.assertFalse(evaluate_b_buy_s_sell("BUY_HINT", buy_metric)["passed"])
        self.assertFalse(evaluate_b_buy_s_sell("S_SELL", buy_metric)["passed"])
        self.assertEqual(tuple(N5_RUNTIME_SIGNAL_TYPES), ("B_BUY", "S_SELL"))

    def test_target_machine_golden_counts_require_explicit_read_confirmation(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as handle:
            with sqlite3.connect(handle.name) as conn:
                conn.execute(
                    """
                    CREATE TABLE action_fact_cache (
                      signal_id INTEGER,
                      signal_date TEXT,
                      signal_time TEXT,
                      signal_type TEXT,
                      code TEXT,
                      name TEXT,
                      monitor_type TEXT,
                      asset_kind TEXT,
                      quote_kind TEXT,
                      current_price REAL,
                      price REAL,
                      virt_amount REAL,
                      today_amount REAL,
                      yesterday_amount REAL,
                      condition_key TEXT,
                      trigger_period TEXT
                    )
                    """
                )
                conn.executemany(
                    """
                    INSERT INTO action_fact_cache (
                      signal_id, signal_date, signal_time, signal_type, code, name,
                      monitor_type, asset_kind, quote_kind, current_price, price,
                      virt_amount, today_amount, yesterday_amount, condition_key, trigger_period
                    ) VALUES (?, '20260612', '09:31', ?, ?, 'sample', 'stock', 'stock', 'stock', 1, 1, 1, 1, 1, 'BUY:D', 'D')
                    """,
                    [(idx + 1, "B_BUY", f"{idx:06d}") for idx in range(76)]
                    + [(idx + 77, "S_SELL", f"{idx + 1000:06d}") for idx in range(24)],
                )
                conn.commit()

            with self.assertRaises(OldSystemReadConfirmationRequired):
                load_target_actions(handle.name, trade_date="20260612")

            rows = load_target_actions(
                handle.name,
                trade_date="20260612",
                old_system_read_confirmed=True,
            )
        counts = {}
        for row in rows:
            counts[row["signal_type"]] = counts.get(row["signal_type"], 0) + 1

        self.assertEqual(counts, {"B_BUY": 76, "S_SELL": 24})

    def test_replay_report_is_json_serializable_and_keeps_forbidden_scope_false(self):
        rows = [
            bar("000001", "2026-06-11 14:31", 8.0, 9.0, 10.0),
            bar("000001", "2026-06-11 14:32", 9.0, 10.0, 10.0),
            bar("000001", "2026-06-11 14:33", 10.0, 11.0, 10.0),
            bar("000001", "2026-06-11 14:34", 11.0, 12.0, 10.0),
            bar("000001", "2026-06-11 14:35", 12.0, 13.0, 20.0),
            bar("000001", "2026-06-12 09:31", 10.0, 11.0, 20.0),
            bar("000001", "2026-06-12 09:32", 11.0, 12.0, 20.0),
            bar("000001", "2026-06-12 09:33", 12.0, 14.0, 30.0),
        ]
        actions = [
            {
                "signal_id": 1,
                "signal_date": "20260612",
                "signal_time": "09:33",
                "signal_type": "B_BUY",
                "code": "000001",
                "name": "sample",
                "monitor_type": "stock",
                "asset_kind": "stock",
                "price": 14.2,
                "current_price": 13.5,
            }
        ]

        report = build_replay_report(actions=actions, minute_rows_by_code={"000001": rows}, trade_date="20260612")

        json.dumps(report, ensure_ascii=False)
        self.assertEqual(report["target_golden_counts"], {"B_BUY": 1})
        self.assertEqual(report["v3_replay_counts"], {"B_BUY": 1})
        self.assertEqual(report["diff_summary"]["missing_in_v3"], 0)
        self.assertEqual(report["diagnostics"]["target_action_price_replay_counts"], {"B_BUY": 1})
        self.assertEqual(report["diagnostics"]["target_legacy_board_amount_compat_replay_counts"], {"B_BUY": 1})
        self.assertEqual(report["diagnostics"]["action_price_differs_from_minute_close"], 1)
        self.assertFalse(report["side_effects"]["database_written"])
        self.assertFalse(report["side_effects"]["worker_started"])
        self.assertFalse(report["side_effects"]["n6_entered"])


if __name__ == "__main__":
    unittest.main()
