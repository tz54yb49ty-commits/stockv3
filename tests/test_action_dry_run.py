import unittest

from ashare_v3.action.dry_run import (
    build_action_tracking_state_plan,
    build_action_candidates_from_outbox_rows,
    derive_final_action_mark_from_n5_metric,
    validate_blocked_reason,
    summarize_action_candidates,
    summarize_action_tracking_state_plan,
)
from ashare_v3.action.preflight import build_action_preflight_report_from_rows
from ashare_v3.action.consumer_dry_run import DEFAULT_N5_1_CONSUMER_NAME
from ashare_v3.action.run_once_dry_run import (
    build_action_consumer_run_once_dry_run_report_from_rows,
    build_action_write_plan,
    summarize_action_write_plan,
)

_DEFAULT = object()


class ActionDryRunTest(unittest.TestCase):
    def test_opaque_action_confirmation_payload_is_trace_only_not_proof(self) -> None:
        candidates = build_action_candidates_from_outbox_rows(
            [
                sample_outbox_row(
                    signal_type="B_BUY",
                    condition_key="BUY_HINT",
                    original_condition_key="BUY_HINT",
                    trigger_mark_candidate="30m_volume",
                    projection_30m_type="volume_up",
                    action_confirmation={
                        "120m": "passed",
                        "30m": "passed",
                        "5m": "passed",
                        "1m": "passed",
                    },
                    minute_context={"is_closed": True, "minute_label": "14:10"},
                )
            ]
        )

        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate["candidate_kind"], "action_confirmation")
        self.assertEqual(candidate["source_trigger_event_type"], "TriggerMatched")
        self.assertTrue(candidate["starts_action_confirmation"])
        self.assertEqual(candidate["signal_type"], "B_BUY")
        self.assertEqual(candidate["condition_key"], "BUY_HINT")
        self.assertEqual(candidate["original_condition_key"], "BUY_HINT")
        self.assertEqual(candidate["trigger_mark_candidate"], "30m_volume")
        self.assertEqual(candidate["action_mark_candidate"], "normal")
        self.assertIsNone(candidate["final_action_mark"])
        self.assertEqual(candidate["action_state"], "blocked")
        self.assertEqual(candidate["confirmation_status"], "failed")
        self.assertEqual(candidate["minute_boundary_status"], "closed")
        self.assertEqual(candidate["confirmation_source"], "n3_action_confirmation_metric_missing")
        self.assertEqual(candidate["blocked_reason"], "metric_missing")
        self.assertEqual(candidate["action_event_type"], "ActionBlocked")
        self.assertEqual(candidate["planned_output_event_type"], "ActionBlocked")
        self.assertEqual(candidate["trace_json"]["condition_key"], "BUY_HINT")
        self.assertEqual(candidate["trace_json"]["original_condition_key"], "BUY_HINT")
        self.assertNotIn("action_confirmation", candidate["trace_json"])
        self.assertEqual(candidate["trace_json"]["opaque_action_confirmation_trace_only"]["120m"], "passed")
        self.assertFalse(candidate["would_write_db"])

    def test_trigger_matched_uses_n3_metric_fact_to_execute_or_block(self) -> None:
        rows = [
            sample_outbox_row(
                event_id="evt_sell_metric",
                signal_type="S_SELL",
                direction="sell",
                condition_key="SELL:Y,Q,M",
                trigger_mark_candidate="30m_shrink",
                projection_30m_type="shrink_down",
                source_action_confirmation_metric_id=6,
                asset_kind="index",
                identity_key="index:SH:000682",
            ),
            sample_outbox_row(
                event_id="evt_buy_metric",
                signal_type="B_BUY",
                direction="buy",
                condition_key="BUY_HINT",
                trigger_mark_candidate="30m_volume",
                projection_30m_type="volume_up",
                source_action_confirmation_metric_id=647,
                asset_kind="stock",
                identity_key="stock:SZ:300382",
            ),
        ]
        rows[0]["payload_json"].update(
            {
                "trigger_period": "M",
                "triggered_periods": ["M"],
                "all_trigger_periods": ["M"],
                "primary_trigger_period": "M",
                "trigger_kind": "trigger",
            }
        )

        candidates = build_action_candidates_from_outbox_rows(
            rows,
            action_confirmation_metric_facts={
                ("index", "6"): metric_fact(
                    asset_kind="index",
                    action_confirmation_metric_id=6,
                    identity_key="index:SH:000682",
                    signal_type="S_SELL",
                    sell_pass=True,
                ),
                ("stock", "647"): metric_fact(
                    asset_kind="stock",
                    action_confirmation_metric_id=647,
                    identity_key="stock:SZ:300382",
                    signal_type="B_BUY",
                    buy_pass=False,
                    buy_120m_price_pass=False,
                ),
            },
        )

        by_id = {candidate["source_trigger_event_id"]: candidate for candidate in candidates}
        self.assertEqual(by_id["evt_sell_metric"]["confirmation_source"], "n3_action_confirmation_metric")
        self.assertEqual(by_id["evt_sell_metric"]["confirmation_status"], "passed")
        self.assertEqual(by_id["evt_sell_metric"]["action_state"], "executed")
        self.assertEqual(by_id["evt_sell_metric"]["planned_output_event_type"], "ActionExecuted")
        self.assertEqual(by_id["evt_sell_metric"]["final_action_mark"], "30m_shrink")
        self.assertEqual(by_id["evt_sell_metric"]["source_action_confirmation_metric_id"], "6")
        self.assertTrue(by_id["evt_sell_metric"]["trace_json"]["action_confirmation_metric"]["all_period_confirmation_pass"])

        self.assertEqual(by_id["evt_buy_metric"]["confirmation_source"], "n3_action_confirmation_metric")
        self.assertEqual(by_id["evt_buy_metric"]["confirmation_status"], "failed")
        self.assertEqual(by_id["evt_buy_metric"]["action_state"], "blocked")
        self.assertEqual(by_id["evt_buy_metric"]["planned_output_event_type"], "ActionBlocked")
        self.assertIsNone(by_id["evt_buy_metric"]["final_action_mark"])
        self.assertEqual(by_id["evt_buy_metric"]["blocked_reason"], "price_confirmation_failed")
        self.assertFalse(by_id["evt_buy_metric"]["trace_json"]["action_confirmation_metric"]["all_period_confirmation_pass"])

    def test_live_trigger_window_executes_on_later_confirming_metric(self) -> None:
        row = sample_outbox_row(
            event_id="evt_live_window_000300",
            trigger_match_id=436642,
            asset_kind="index",
            identity_key="index:SH:000300",
            signal_type="B_BUY",
            direction="buy",
            condition_key="BUY:M",
            source_action_confirmation_metric_id=338338,
        )
        row["event_time"] = "2026-06-22T13:56:00+08:00"
        row["payload_json"].update(
            {
                "trigger_time": "2026-06-22T13:56:00+08:00",
                "current_status": "matched",
                "trigger_live": True,
            }
        )
        first_metric = metric_fact(
            asset_kind="index",
            action_confirmation_metric_id=338338,
            identity_key="index:SH:000300",
            buy_pass=False,
        )
        first_metric.update({"metric_time": "2026-06-22T13:56:00+08:00", "metric_minute_label": "13:56"})
        later_metric = metric_fact(
            asset_kind="index",
            action_confirmation_metric_id=338346,
            identity_key="index:SH:000300",
            buy_pass=True,
        )
        later_metric.update({"metric_time": "2026-06-22T14:04:00+08:00", "metric_minute_label": "14:04"})

        candidates = build_action_candidates_from_outbox_rows(
            [row],
            action_confirmation_metric_facts={
                ("index", "338338"): first_metric,
                ("index", "338346"): later_metric,
            },
            action_confirmation_metric_facts_by_identity={
                ("index", "index:SH:000300"): [first_metric, later_metric],
            },
        )

        candidate = candidates[0]
        self.assertEqual(candidate["planned_output_event_type"], "ActionExecuted")
        self.assertEqual(candidate["action_state"], "executed")
        self.assertEqual(candidate["confirmation_status"], "passed")
        self.assertEqual(candidate["source_action_confirmation_metric_id"], "338346")
        self.assertEqual(candidate["trace_json"]["live_window_confirmation"]["trigger_metric_time"], "2026-06-22T13:56:00+08:00")
        self.assertEqual(candidate["trace_json"]["live_window_confirmation"]["executed_metric_time"], "2026-06-22T14:04:00+08:00")
        self.assertTrue(candidate["trace_json"]["live_window_confirmation"]["executed_from_window"])

    def test_live_trigger_window_generates_action_for_each_passing_metric(self) -> None:
        row = sample_outbox_row(
            event_id="evt_live_window_000300_multi",
            trigger_match_id=436642,
            asset_kind="index",
            identity_key="index:SH:000300",
            signal_type="B_BUY",
            direction="buy",
            condition_key="BUY:M",
            source_action_confirmation_metric_id=338338,
        )
        row["event_time"] = "2026-06-22T13:56:00+08:00"
        row["payload_json"].update(
            {
                "trigger_time": "2026-06-22T13:56:00+08:00",
                "current_status": "matched",
                "trigger_live": True,
            }
        )
        first_metric = metric_fact(
            asset_kind="index",
            action_confirmation_metric_id=338338,
            identity_key="index:SH:000300",
            buy_pass=False,
        )
        first_metric.update({"metric_time": "2026-06-22T13:56:00+08:00", "metric_minute_label": "13:56"})
        passing_specs = [
            (338343, "2026-06-22T14:01:00+08:00", "14:01"),
            (338345, "2026-06-22T14:03:00+08:00", "14:03"),
            (338346, "2026-06-22T14:04:00+08:00", "14:04"),
            (338351, "2026-06-22T14:09:00+08:00", "14:09"),
            (338352, "2026-06-22T14:10:00+08:00", "14:10"),
        ]
        passing_metrics = []
        for metric_id, metric_time, minute_label in passing_specs:
            metric = metric_fact(
                asset_kind="index",
                action_confirmation_metric_id=metric_id,
                identity_key="index:SH:000300",
                buy_pass=True,
            )
            metric.update({"metric_time": metric_time, "metric_minute_label": minute_label})
            passing_metrics.append(metric)

        candidates = build_action_candidates_from_outbox_rows(
            [row],
            action_confirmation_metric_facts={("index", "338338"): first_metric},
            action_confirmation_metric_facts_by_identity={
                ("index", "index:SH:000300"): [first_metric, *passing_metrics],
            },
        )

        self.assertEqual([candidate["planned_output_event_type"] for candidate in candidates], ["ActionExecuted"] * 5)
        self.assertEqual(
            [candidate["source_action_confirmation_metric_id"] for candidate in candidates],
            ["338343", "338345", "338346", "338351", "338352"],
        )
        self.assertEqual(len({candidate["action_key"] for candidate in candidates}), 5)
        self.assertEqual(len({candidate["dedup_key"] for candidate in candidates}), 5)
        for candidate, (metric_id, metric_time, _minute_label) in zip(candidates, passing_specs):
            live_trace = candidate["trace_json"]["live_window_confirmation"]
            self.assertTrue(live_trace["live_window_confirmation"])
            self.assertTrue(live_trace["executed_from_window"])
            self.assertTrue(live_trace["multi_action_window"])
            self.assertEqual(live_trace["selected_metric_id"], str(metric_id))
            self.assertEqual(live_trace["executed_metric_time"], metric_time)
            self.assertEqual(
                live_trace["action_grain"],
                "source_trigger_event_id+action_type+selected_metric_id",
            )
        write_plan = build_action_write_plan(candidates)
        self.assertEqual([row["plan_status"] for row in write_plan], ["planned_action_fact"] * 5)
        self.assertEqual(len({row["action_key"] for row in write_plan}), 5)

    def test_live_trigger_window_scans_only_bounded_identity_metric_cache(self) -> None:
        row = sample_outbox_row(
            event_id="evt_live_window_bounded",
            trigger_match_id=436644,
            asset_kind="index",
            identity_key="index:SH:000300",
            signal_type="B_BUY",
            direction="buy",
            condition_key="BUY:M",
            source_action_confirmation_metric_id=338338,
        )
        row["event_time"] = "2026-06-22T13:56:00+08:00"
        row["payload_json"].update(
            {
                "trigger_time": "2026-06-22T13:56:00+08:00",
                "current_status": "matched",
                "trigger_live": True,
            }
        )
        first_metric = metric_fact(
            asset_kind="index",
            action_confirmation_metric_id=338338,
            identity_key="index:SH:000300",
            buy_pass=False,
        )
        first_metric.update({"metric_time": "2026-06-22T13:56:00+08:00", "metric_minute_label": "13:56"})
        later_metric = metric_fact(
            asset_kind="index",
            action_confirmation_metric_id=338343,
            identity_key="index:SH:000300",
            buy_pass=True,
        )
        later_metric.update({"metric_time": "2026-06-22T14:01:00+08:00", "metric_minute_label": "14:01"})
        unrelated_metric = metric_fact(
            asset_kind="index",
            action_confirmation_metric_id=999999,
            identity_key="index:SH:000905",
            buy_pass=True,
        )
        unrelated_metric.update({"metric_time": "2026-06-22T14:01:00+08:00", "metric_minute_label": "14:01"})

        candidates = build_action_candidates_from_outbox_rows(
            [row],
            action_confirmation_metric_facts={("index", "338338"): first_metric},
            action_confirmation_metric_facts_by_identity={
                ("index", "index:SH:000300"): [first_metric, later_metric],
                ("index", "index:SH:000905"): [unrelated_metric],
            },
        )

        candidate = candidates[0]
        self.assertEqual(candidate["planned_output_event_type"], "ActionExecuted")
        self.assertEqual(candidate["source_action_confirmation_metric_id"], "338343")
        self.assertEqual(candidate["trace_json"]["live_window_confirmation"]["executed_metric_time"], "2026-06-22T14:01:00+08:00")

    def test_live_trigger_window_requires_identity_metric_cache_to_scan_later_metrics(self) -> None:
        row = sample_outbox_row(
            event_id="evt_live_window_missing_identity_cache",
            trigger_match_id=436645,
            asset_kind="index",
            identity_key="index:SH:000300",
            signal_type="B_BUY",
            direction="buy",
            condition_key="BUY:M",
            source_action_confirmation_metric_id=338338,
        )
        row["event_time"] = "2026-06-22T13:56:00+08:00"
        row["payload_json"].update(
            {
                "trigger_time": "2026-06-22T13:56:00+08:00",
                "current_status": "matched",
                "trigger_live": True,
            }
        )
        first_metric = metric_fact(
            asset_kind="index",
            action_confirmation_metric_id=338338,
            identity_key="index:SH:000300",
            buy_pass=False,
        )
        first_metric.update({"metric_time": "2026-06-22T13:56:00+08:00", "metric_minute_label": "13:56"})
        later_metric = metric_fact(
            asset_kind="index",
            action_confirmation_metric_id=338343,
            identity_key="index:SH:000300",
            buy_pass=True,
        )
        later_metric.update({"metric_time": "2026-06-22T14:01:00+08:00", "metric_minute_label": "14:01"})

        candidates = build_action_candidates_from_outbox_rows(
            [row],
            action_confirmation_metric_facts={
                ("index", "338338"): first_metric,
                ("index", "338343"): later_metric,
            },
        )

        candidate = candidates[0]
        self.assertEqual(candidate["planned_output_event_type"], "ActionEligible")
        self.assertEqual(candidate["confirmation_status"], "pending")
        self.assertEqual(candidate["source_action_confirmation_metric_id"], "338338")
        live_trace = candidate["trace_json"]["live_window_confirmation"]
        self.assertTrue(live_trace["identity_metric_cache_required"])
        self.assertEqual(live_trace["pending_reason"], "live_window_identity_metric_cache_missing")

    def test_live_trigger_window_stays_eligible_when_no_later_metric_passes(self) -> None:
        row = sample_outbox_row(
            event_id="evt_live_window_pending",
            trigger_match_id=436643,
            asset_kind="index",
            identity_key="index:SH:000300",
            signal_type="B_BUY",
            direction="buy",
            condition_key="BUY:M",
            source_action_confirmation_metric_id=338338,
        )
        row["event_time"] = "2026-06-22T13:56:00+08:00"
        row["payload_json"].update(
            {
                "trigger_time": "2026-06-22T13:56:00+08:00",
                "current_status": "matched",
                "trigger_live": True,
            }
        )
        first_metric = metric_fact(
            asset_kind="index",
            action_confirmation_metric_id=338338,
            identity_key="index:SH:000300",
            buy_pass=False,
        )
        first_metric.update({"metric_time": "2026-06-22T13:56:00+08:00", "metric_minute_label": "13:56"})

        candidates = build_action_candidates_from_outbox_rows(
            [row],
            action_confirmation_metric_facts={("index", "338338"): first_metric},
            action_confirmation_metric_facts_by_identity={
                ("index", "index:SH:000300"): [first_metric],
            },
        )
        tracking_plan = build_action_tracking_state_plan(candidates)

        candidate = candidates[0]
        self.assertEqual(candidate["planned_output_event_type"], "ActionEligible")
        self.assertEqual(candidate["action_state"], "eligible")
        self.assertEqual(candidate["confirmation_status"], "pending")
        self.assertIsNone(candidate["blocked_reason"])
        self.assertEqual(candidate["last_checked_minute_label"], "13:56")
        self.assertEqual(
            candidate["trace_json"]["live_window_confirmation"]["tracking_window_end_policy"],
            "implicit_for_trade_date_close",
        )
        self.assertEqual(tracking_plan[0]["operation"], "create_tracking_unfinished")
        self.assertEqual(tracking_plan[0]["tracking_state"]["tracking_status"], "tracking")

    def test_non_live_trigger_keeps_one_shot_terminal_behavior(self) -> None:
        row = sample_outbox_row(
            event_id="evt_non_live_no_window",
            trigger_live=False,
            source_action_confirmation_metric_id=338338,
        )
        first_metric = metric_fact(action_confirmation_metric_id=338338, buy_pass=False)

        candidates = build_action_candidates_from_outbox_rows(
            [row],
            action_confirmation_metric_facts={("stock", "338338"): first_metric},
        )

        candidate = candidates[0]
        self.assertEqual(candidate["planned_output_event_type"], "ActionSkipped")
        self.assertEqual(candidate["action_state"], "expired")
        self.assertNotIn("live_window_confirmation", candidate["trace_json"])

    def test_trigger_price_can_derive_from_joined_n3_metric_current_price(self) -> None:
        rows = [
            sample_outbox_row(
                event_id="evt_metric_price",
                signal_type="B_BUY",
                direction="buy",
                condition_key="BUY:Y,D",
                source_action_confirmation_metric_id=702,
            )
        ]

        candidates = build_action_candidates_from_outbox_rows(
            rows,
            action_confirmation_metric_facts={
                ("stock", "702"): numeric_metric_fact(
                    signal_type="B_BUY",
                    current_price="12.34",
                )
            },
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["trigger_price"], "12.34")
        self.assertEqual(
            candidates[0]["trace_json"]["trigger_price_source"],
            "n3_action_confirmation_metric.current_price",
        )

    def test_final_action_mark_uses_n5_metric_not_n4_trigger_candidate(self) -> None:
        candidate = build_action_candidates_from_outbox_rows(
            [
                sample_outbox_row(
                    event_id="evt_n4_candidate_ignored",
                    signal_type="B_BUY",
                    direction="buy",
                    condition_key="BUY_HINT",
                    trigger_mark_candidate="30m_volume",
                    source_action_confirmation_metric_id=710,
                )
            ],
            action_confirmation_metric_facts={
                ("stock", "710"): numeric_metric_fact(
                    signal_type="B_BUY",
                    current_30m_virtual_amount="100",
                    previous_day_same_window_amount="200",
                )
            },
        )[0]

        self.assertEqual(candidate["confirmation_status"], "passed")
        self.assertEqual(candidate["action_state"], "executed")
        self.assertEqual(candidate["trigger_mark_candidate"], "30m_volume")
        self.assertEqual(candidate["action_mark_candidate"], "normal")
        self.assertEqual(candidate["final_action_mark"], "normal")
        self.assertEqual(candidate["trace_json"]["n4_trigger_mark_candidate"], "30m_volume")
        self.assertEqual(candidate["trace_json"]["action_mark_source"], "n5_action_confirmation_metric")
        self.assertEqual(candidate["trace_json"]["action_mark_basis"], "previous_day_same_window_amount")

    def test_final_action_mark_can_be_30m_volume_without_n4_trigger_candidate(self) -> None:
        candidate = build_action_candidates_from_outbox_rows(
            [
                sample_outbox_row(
                    event_id="evt_n5_metric_volume",
                    signal_type="B_BUY",
                    direction="buy",
                    condition_key="BUY:D",
                    trigger_mark_candidate="normal",
                    source_action_confirmation_metric_id=711,
                )
            ],
            action_confirmation_metric_facts={
                ("stock", "711"): numeric_metric_fact(
                    signal_type="B_BUY",
                    current_30m_virtual_amount="300",
                    previous_day_same_window_amount="100",
                )
            },
        )[0]

        self.assertEqual(candidate["confirmation_status"], "passed")
        self.assertEqual(candidate["action_mark_candidate"], "30m_volume")
        self.assertEqual(candidate["final_action_mark"], "30m_volume")
        self.assertEqual(candidate["trace_json"]["action_mark_reason"], "n5_buy_30m_volume_confirmed")

    def test_missing_previous_day_same_window_amount_downgrades_action_mark_only(self) -> None:
        candidate = build_action_candidates_from_outbox_rows(
            [
                sample_outbox_row(
                    event_id="evt_prev_day_same_window_missing",
                    signal_type="B_BUY",
                    direction="buy",
                    condition_key="BUY_HINT",
                    trigger_mark_candidate="30m_volume",
                    source_action_confirmation_metric_id=712,
                )
            ],
            action_confirmation_metric_facts={
                ("stock", "712"): numeric_metric_fact(
                    signal_type="B_BUY",
                    current_30m_virtual_amount="300",
                    previous_day_same_window_amount=None,
                )
            },
        )[0]

        self.assertEqual(candidate["confirmation_status"], "passed")
        self.assertEqual(candidate["action_state"], "executed")
        self.assertEqual(candidate["action_mark_candidate"], "normal")
        self.assertEqual(candidate["final_action_mark"], "normal")
        self.assertEqual(candidate["trace_json"]["action_mark_reason"], "previous_day_same_window_amount_missing")

    def test_sell_final_action_mark_uses_n5_same_window_shrink_metric(self) -> None:
        metric = numeric_metric_fact(
            signal_type="S_SELL",
            direction="sell",
            current_30m_virtual_amount="80",
            previous_day_same_window_amount="100",
        )

        self.assertEqual(derive_final_action_mark_from_n5_metric("S_SELL", metric), "30m_shrink")

    def test_numeric_metric_fields_drive_buy_confirmation_subconditions(self) -> None:
        base = numeric_metric_fact(signal_type="B_BUY")
        cases = {
            "previous_120m_body_high": ("previous_120m_body_high", "10.01", "price_confirmation_failed"),
            "previous_5m_body_high": ("previous_5m_body_high", "10.01", "price_confirmation_failed"),
            "previous_5m_full_amount": ("previous_5m_full_amount", "1001", "amount_confirmation_failed"),
            "previous_1m_body_high": ("previous_1m_body_high", "10.01", "price_confirmation_failed"),
            "previous_1m_amount": ("previous_1m_amount", "1001", "amount_confirmation_failed"),
        }
        for case_name, (field, failing_value, blocked_reason) in cases.items():
            with self.subTest(case_name=case_name):
                metric = {**base, field: failing_value}
                candidate = build_action_candidates_from_outbox_rows(
                    [
                        sample_outbox_row(
                            event_id=f"evt_buy_{case_name}",
                            signal_type="B_BUY",
                            direction="buy",
                            condition_key="BUY:D",
                            source_action_confirmation_metric_id=700,
                        )
                    ],
                    action_confirmation_metric_facts={("stock", "700"): metric},
                )[0]

                self.assertEqual(candidate["planned_output_event_type"], "ActionBlocked")
                self.assertEqual(candidate["action_state"], "blocked")
                self.assertEqual(candidate["confirmation_status"], "failed")
                self.assertEqual(candidate["blocked_reason"], blocked_reason)
                self.assertIsNone(candidate["final_action_mark"])

    def test_numeric_metric_fields_drive_sell_confirmation_subconditions(self) -> None:
        base = numeric_metric_fact(signal_type="S_SELL", direction="sell")
        cases = {
            "previous_120m_body_low": ("previous_120m_body_low", "9.99", "price_confirmation_failed"),
            "previous_5m_body_low": ("previous_5m_body_low", "9.99", "price_confirmation_failed"),
            "previous_5m_full_amount": ("previous_5m_full_amount", "999", "amount_confirmation_failed"),
            "previous_1m_body_low": ("previous_1m_body_low", "9.99", "price_confirmation_failed"),
            "previous_1m_amount": ("previous_1m_amount", "999", "amount_confirmation_failed"),
        }
        for case_name, (field, failing_value, blocked_reason) in cases.items():
            with self.subTest(case_name=case_name):
                metric = {**base, field: failing_value}
                candidate = build_action_candidates_from_outbox_rows(
                    [
                        sample_outbox_row(
                            event_id=f"evt_sell_{case_name}",
                            signal_type="S_SELL",
                            direction="sell",
                            condition_key="SELL:D",
                            source_action_confirmation_metric_id=701,
                        )
                    ],
                    action_confirmation_metric_facts={("stock", "701"): metric},
                )[0]

                self.assertEqual(candidate["planned_output_event_type"], "ActionBlocked")
                self.assertEqual(candidate["action_state"], "blocked")
                self.assertEqual(candidate["confirmation_status"], "failed")
                self.assertEqual(candidate["blocked_reason"], blocked_reason)
                self.assertIsNone(candidate["final_action_mark"])

    def test_all_numeric_metric_subconditions_pass_to_action_executed(self) -> None:
        for signal_type, direction, mark in (
            ("B_BUY", "buy", "30m_volume"),
            ("S_SELL", "sell", "30m_shrink"),
        ):
            with self.subTest(signal_type=signal_type):
                candidate = build_action_candidates_from_outbox_rows(
                    [
                        sample_outbox_row(
                            event_id=f"evt_{signal_type}_numeric_pass",
                            signal_type=signal_type,
                            direction=direction,
                            condition_key="BUY_HINT" if direction == "buy" else "SELL_HINT",
                            original_condition_key="BUY_HINT" if direction == "buy" else "SELL_HINT",
                            trigger_mark_candidate=mark,
                            source_action_confirmation_metric_id=702,
                        )
                    ],
                    action_confirmation_metric_facts={
                        ("stock", "702"): numeric_metric_fact(signal_type=signal_type, direction=direction)
                    },
                )[0]

                self.assertEqual(candidate["planned_output_event_type"], "ActionExecuted")
                self.assertEqual(candidate["action_state"], "executed")
                self.assertEqual(candidate["confirmation_status"], "passed")
                self.assertIsNone(candidate.get("blocked_reason"))
                self.assertEqual(candidate["final_action_mark"], mark)

    def test_30m_price_confirmation_only_affects_action_mark_not_action_execution(self) -> None:
        cases = (
            ("B_BUY", "buy", {"previous_30m_body_high": "10.01"}),
            ("S_SELL", "sell", {"previous_30m_body_low": "9.99"}),
        )
        for signal_type, direction, overrides in cases:
            with self.subTest(signal_type=signal_type):
                metric = {**numeric_metric_fact(signal_type=signal_type, direction=direction), **overrides}
                candidate = build_action_candidates_from_outbox_rows(
                    [
                        sample_outbox_row(
                            event_id=f"evt_{signal_type}_30m_price_mark_only",
                            signal_type=signal_type,
                            direction=direction,
                            condition_key="BUY:D" if direction == "buy" else "SELL:D",
                            source_action_confirmation_metric_id=702,
                        )
                    ],
                    action_confirmation_metric_facts={("stock", "702"): metric},
                )[0]

                self.assertEqual(candidate["planned_output_event_type"], "ActionExecuted")
                self.assertEqual(candidate["action_state"], "executed")
                self.assertEqual(candidate["confirmation_status"], "passed")
                self.assertEqual(candidate["final_action_mark"], "normal")
                self.assertEqual(candidate["action_mark_reason"], f"{direction}_30m_price_not_confirmed")

    def test_hint_and_ordinary_trigger_matched_share_unified_metric_confirmation_path(self) -> None:
        rows = [
            sample_outbox_row(
                event_id="evt_buy_hint_pass",
                signal_type="B_BUY",
                direction="buy",
                condition_key="BUY_HINT",
                original_condition_key="BUY_HINT",
                trigger_mark_candidate="30m_volume",
                source_action_confirmation_metric_id=801,
            ),
            sample_outbox_row(
                event_id="evt_buy_ordinary_pass",
                signal_type="B_BUY",
                direction="buy",
                condition_key="BUY:D",
                original_condition_key="BUY:D",
                trigger_mark_candidate="normal",
                source_action_confirmation_metric_id=802,
            ),
        ]
        candidates = build_action_candidates_from_outbox_rows(
            rows,
            action_confirmation_metric_facts={
                ("stock", "801"): numeric_metric_fact(signal_type="B_BUY"),
                ("stock", "802"): numeric_metric_fact(
                    signal_type="B_BUY",
                    current_30m_virtual_amount="100",
                    previous_day_same_window_amount="200",
                ),
            },
        )

        by_id = {candidate["source_trigger_event_id"]: candidate for candidate in candidates}
        for event_id in ("evt_buy_hint_pass", "evt_buy_ordinary_pass"):
            with self.subTest(event_id=event_id):
                self.assertEqual(by_id[event_id]["confirmation_source"], "n3_action_confirmation_metric")
                self.assertEqual(by_id[event_id]["confirmation_status"], "passed")
                self.assertEqual(by_id[event_id]["action_state"], "executed")
                self.assertEqual(by_id[event_id]["planned_output_event_type"], "ActionExecuted")
        self.assertEqual(by_id["evt_buy_hint_pass"]["final_action_mark"], "30m_volume")
        self.assertEqual(by_id["evt_buy_ordinary_pass"]["final_action_mark"], "normal")

    def test_metric_time_mismatch_blocks_trigger_row_confirmation(self) -> None:
        row = sample_outbox_row(
            event_id="evt_metric_time_mismatch",
            signal_type="B_BUY",
            direction="buy",
            condition_key="BUY:D",
            source_action_confirmation_metric_id=803,
        )
        row["trade_date"] = "20260608"
        row["event_time"] = "2026-06-08T09:44:00+08:00"
        row["payload_json"]["trade_date"] = "20260608"
        row["payload_json"]["trigger_time"] = "2026-06-08T09:44:00+08:00"
        metric = numeric_metric_fact(signal_type="B_BUY")
        metric.update(
            {
                "action_confirmation_metric_id": 803,
                "metric_time": "2026-06-08T15:00:00+08:00",
                "metric_minute_label": "15:00",
            }
        )

        candidate = build_action_candidates_from_outbox_rows(
            [row],
            action_confirmation_metric_facts={("stock", "803"): metric},
        )[0]

        self.assertEqual(candidate["confirmation_source"], "n3_action_confirmation_metric")
        self.assertEqual(candidate["action_confirmation_metric_status"], "time_mismatch")
        self.assertEqual(candidate["confirmation_status"], "failed")
        self.assertEqual(candidate["action_state"], "blocked")
        self.assertEqual(candidate["planned_output_event_type"], "ActionBlocked")
        self.assertEqual(candidate["blocked_reason"], "lineage_mismatch")
        self.assertIsNone(candidate["final_action_mark"])

    def test_metric_time_aligned_accepts_trigger_row_confirmation(self) -> None:
        row = sample_outbox_row(
            event_id="evt_metric_time_aligned",
            signal_type="B_BUY",
            direction="buy",
            condition_key="BUY:D",
            source_action_confirmation_metric_id=804,
        )
        row["trade_date"] = "20260608"
        row["event_time"] = "2026-06-08T09:44:00+08:00"
        row["payload_json"]["trade_date"] = "20260608"
        row["payload_json"]["trigger_time"] = "2026-06-08T09:44:00+08:00"
        metric = numeric_metric_fact(signal_type="B_BUY")
        metric.update(
            {
                "action_confirmation_metric_id": 804,
                "metric_time": "2026-06-08T09:44:00+08:00",
                "metric_minute_label": "09:44",
            }
        )

        candidate = build_action_candidates_from_outbox_rows(
            [row],
            action_confirmation_metric_facts={("stock", "804"): metric},
        )[0]

        self.assertEqual(candidate["action_confirmation_metric_status"], "ready")
        self.assertEqual(candidate["confirmation_status"], "passed")
        self.assertEqual(candidate["action_state"], "executed")
        self.assertEqual(candidate["planned_output_event_type"], "ActionExecuted")

    def test_first_period_amount_default_pass_does_not_default_price_pass(self) -> None:
        metric = numeric_metric_fact(
            signal_type="B_BUY",
            current_1m_amount="1",
            previous_1m_amount="100000",
            current_5m_virtual_amount="1",
            previous_5m_full_amount="100000",
        )
        metric.update(
            {
                "is_first_1m_of_day": True,
                "is_first_5m_of_day": True,
                "first_1m_amount_default_pass": True,
                "first_5m_amount_default_pass": True,
                "previous_1m_body_high": "10.01",
            }
        )

        candidate = build_action_candidates_from_outbox_rows(
            [
                sample_outbox_row(
                    event_id="evt_first_period_price_fail",
                    signal_type="B_BUY",
                    condition_key="BUY:D",
                    source_action_confirmation_metric_id=703,
                )
            ],
            action_confirmation_metric_facts={("stock", "703"): metric},
        )[0]

        selected = candidate["trace_json"]["action_confirmation_metric"]["selected_flags"]
        self.assertTrue(selected["buy_1m_amount_pass"])
        self.assertTrue(selected["buy_5m_amount_pass"])
        self.assertFalse(selected["buy_1m_price_pass"])
        self.assertEqual(candidate["blocked_reason"], "price_confirmation_failed")
        self.assertEqual(candidate["planned_output_event_type"], "ActionBlocked")

    def test_missing_previous_session_reference_blocks_without_default_pass(self) -> None:
        metric = numeric_metric_fact(signal_type="B_BUY")
        metric.update(
            {
                "is_first_120m_of_day": True,
                "previous_120m_period_source": "not_available",
                "previous_120m_body_high": None,
            }
        )

        candidate = build_action_candidates_from_outbox_rows(
            [
                sample_outbox_row(
                    event_id="evt_missing_previous_reference",
                    signal_type="B_BUY",
                    condition_key="BUY:D",
                    source_action_confirmation_metric_id=704,
                )
            ],
            action_confirmation_metric_facts={("stock", "704"): metric},
        )[0]

        self.assertEqual(candidate["blocked_reason"], "missing_previous_session_reference")
        self.assertEqual(candidate["planned_output_event_type"], "ActionBlocked")
        self.assertIsNone(candidate["final_action_mark"])

    def test_metric_missing_maps_to_action_blocked_reason(self) -> None:
        candidate = build_action_candidates_from_outbox_rows(
            [
                sample_outbox_row(
                    event_id="evt_metric_missing",
                    signal_type="B_BUY",
                    condition_key="BUY:D",
                    source_action_confirmation_metric_id=705,
                )
            ],
            action_confirmation_metric_facts={},
        )[0]

        self.assertEqual(candidate["planned_output_event_type"], "ActionBlocked")
        self.assertEqual(candidate["blocked_reason"], "metric_missing")

    def test_blocked_reason_validator_rejects_user_layer_reasons(self) -> None:
        for allowed in (
            "metric_missing",
            "metric_quality_failed",
            "trigger_not_live",
            "lineage_mismatch",
            "missing_previous_session_reference",
            "price_confirmation_failed",
            "amount_confirmation_failed",
            "duplicate_action_fact",
            "unsupported_signal_type",
            "metric_policy_invalid",
        ):
            self.assertEqual(validate_blocked_reason(allowed), allowed)

        for forbidden in (
            "no_position",
            "insufficient_cash",
            "t_plus_one_locked",
            "already_sold",
            "position_limit",
            "blacklist",
        ):
            with self.subTest(forbidden=forbidden):
                with self.assertRaises(ValueError):
                    validate_blocked_reason(forbidden)

    def test_metric_action_write_plan_merges_same_minute_multi_condition_grain(self) -> None:
        rows = [
            sample_outbox_row(
                event_id="evt_buy_hint",
                condition_key="BUY_HINT",
                original_condition_key="BUY_HINT",
                trigger_match_id=101,
                source_action_confirmation_metric_id=647,
                identity_key="stock:SZ:300382",
                trigger_mark_candidate="30m_volume",
            ),
            sample_outbox_row(
                event_id="evt_buy_periods",
                condition_key="BUY:Y,W,D",
                original_condition_key="BUY:Y,W,D",
                trigger_match_id=102,
                source_action_confirmation_metric_id=647,
                identity_key="stock:SZ:300382",
                trigger_mark_candidate="30m_volume",
            ),
        ]
        candidates = build_action_candidates_from_outbox_rows(
            rows,
            action_confirmation_metric_facts={
                ("stock", "647"): metric_fact(
                    action_confirmation_metric_id=647,
                    identity_key="stock:SZ:300382",
                    buy_pass=False,
                    buy_120m_price_pass=False,
                )
            },
        )
        plan = build_action_write_plan(candidates)
        summary = summarize_action_write_plan(plan)

        self.assertEqual(summary["planned_action_fact_count"], 1)
        self.assertEqual(summary["skipped_count"], 1)
        self.assertEqual(summary["skip_reasons"], {"duplicate_action_confirmation_grain": 1})
        planned = [row for row in plan if row["plan_status"] == "planned_action_fact"][0]
        self.assertEqual(planned["trace_json"]["condition_provenance"]["condition_keys"], ["BUY_HINT", "BUY:Y,W,D"])
        self.assertEqual(len(planned["trace_json"]["condition_provenance"]["source_trigger_event_ids"]), 2)

    def test_non_calibrated_metric_policy_blocks_action_confirmation(self) -> None:
        candidate = build_action_candidates_from_outbox_rows(
            [
                sample_outbox_row(
                    event_id="evt_metric_policy_invalid",
                    signal_type="B_BUY",
                    condition_key="BUY:D",
                    source_action_confirmation_metric_id=713,
                )
            ],
            action_confirmation_metric_facts={
                ("stock", "713"): numeric_metric_fact(
                    signal_type="B_BUY",
                    virtual_amount_policy_version="linear_elapsed_ratio_legacy",
                )
            },
        )[0]

        self.assertEqual(candidate["planned_output_event_type"], "ActionBlocked")
        self.assertEqual(candidate["blocked_reason"], "metric_policy_invalid")
        self.assertEqual(candidate["trace_json"]["action_confirmation_metric"]["metric_policy_status"], "invalid")

    def test_action_confirmation_grain_uses_v1_recommended_key_without_action_run_or_source_event(self) -> None:
        candidates = build_action_candidates_from_outbox_rows(
            [
                sample_outbox_row(
                    event_id="evt_v1_grain_a",
                    trigger_match_id=201,
                    signal_type="B_BUY",
                    condition_key="BUY:D",
                    original_condition_key="BUY:D",
                    trigger_mark_candidate="normal",
                    source_action_confirmation_metric_id=706,
                ),
                sample_outbox_row(
                    event_id="evt_v1_grain_b",
                    trigger_match_id=202,
                    signal_type="B_BUY",
                    condition_key="BUY:D",
                    original_condition_key="BUY:D",
                    trigger_mark_candidate="normal",
                    source_action_confirmation_metric_id=707,
                ),
            ],
            action_run_id="action_run_a",
            action_confirmation_metric_facts={
                ("stock", "706"): numeric_metric_fact(signal_type="B_BUY"),
                ("stock", "707"): numeric_metric_fact(signal_type="B_BUY"),
            },
        )

        keys = {candidate["action_confirmation_grain_key"] for candidate in candidates}
        self.assertEqual(len(keys), 1)
        key = keys.pop()
        self.assertIn("trade_date|20260525", key)
        self.assertIn("identity_key|stock:SH:600000", key)
        self.assertIn("signal_type|B_BUY", key)
        self.assertIn("trigger_kind|trigger", key)
        self.assertIn("original_condition_key|BUY:D", key)
        self.assertIn("primary_trigger_period|D", key)
        self.assertIn("trigger_mark_candidate|normal", key)
        self.assertIn("trigger_time|2026-05-25T02:30:00+00:00", key)
        self.assertNotIn("action_run_a", key)
        self.assertNotIn("evt_v1_grain_a", key)
        self.assertNotIn("evt_v1_grain_b", key)

    def test_buy_hint_and_sell_hint_are_trace_only_not_hint_events(self) -> None:
        rows = [
                sample_outbox_row(
                    event_id="evt_buy_hint",
                    signal_type="B_BUY",
                    condition_key="BUY_HINT",
                    original_condition_key="BUY_HINT",
                    direction="buy",
                    trigger_mark_candidate="30m_volume",
                    action_confirmation_mode="deferred",
                ),
                sample_outbox_row(
                    event_id="evt_sell_hint",
                    signal_type="S_SELL",
                    condition_key="SELL_HINT",
                    original_condition_key="SELL_HINT",
                    direction="sell",
                    trigger_mark_candidate="30m_shrink",
                    action_confirmation_mode="deferred",
                ),
        ]
        candidates = build_action_candidates_from_outbox_rows(rows)
        summary = summarize_action_candidates(candidates)

        self.assertEqual(summary["buy_hint_trace_count"], 1)
        self.assertEqual(summary["sell_hint_trace_count"], 1)
        self.assertEqual({candidate["signal_type"] for candidate in candidates}, {"B_BUY", "S_SELL"})
        self.assertEqual({candidate["planned_output_event_type"] for candidate in candidates}, {"ActionEligible"})
        self.assertEqual(summary["deprecated_hint_event_plan_count"], 0)

    def test_buy_hint_30m_candidate_keeps_primary_trigger_period_null(self) -> None:
        row = sample_outbox_row(
            event_id="evt_buy_hint_30m",
            signal_type="B_BUY",
            condition_key="BUY_HINT",
            original_condition_key="BUY_HINT",
            direction="buy",
            trigger_mark_candidate="30m_volume",
        )
        row["payload_json"].update(
            {
                "trigger_kind": "hint",
                "trigger_period": "30m",
                "triggered_periods": [],
                "all_trigger_periods": [],
                "primary_trigger_period": None,
                "n5_entry_allowed": True,
            }
        )

        candidate = build_action_candidates_from_outbox_rows([row])[0]

        self.assertEqual(candidate["trigger_kind"], "hint")
        self.assertEqual(candidate["trigger_period"], "30m")
        self.assertIsNone(candidate["primary_trigger_period"])
        self.assertIn("primary_trigger_period|null", candidate["action_confirmation_grain_key"])

    def test_sell_hint_30m_candidate_keeps_primary_trigger_period_null(self) -> None:
        row = sample_outbox_row(
            event_id="evt_sell_hint_30m",
            signal_type="S_SELL",
            condition_key="SELL_HINT",
            original_condition_key="SELL_HINT",
            direction="sell",
            trigger_mark_candidate="30m_shrink",
        )
        row["payload_json"].update(
            {
                "trigger_kind": "hint",
                "trigger_period": "30m",
                "triggered_periods": [],
                "all_trigger_periods": [],
                "primary_trigger_period": None,
                "n5_entry_allowed": True,
            }
        )

        candidate = build_action_candidates_from_outbox_rows([row])[0]

        self.assertEqual(candidate["trigger_kind"], "hint")
        self.assertEqual(candidate["trigger_period"], "30m")
        self.assertIsNone(candidate["primary_trigger_period"])
        self.assertIn("primary_trigger_period|null", candidate["action_confirmation_grain_key"])

    def test_run_once_action_write_plan_keeps_hint_30m_primary_trigger_period_null(self) -> None:
        row = sample_outbox_row(
            event_id="evt_write_plan_buy_hint_30m",
            signal_type="B_BUY",
            condition_key="BUY_HINT",
            original_condition_key="BUY_HINT",
            direction="buy",
            trigger_mark_candidate="30m_volume",
        )
        row["payload_json"].update(
            {
                "trigger_kind": "hint",
                "trigger_period": "30m",
                "triggered_periods": [],
                "all_trigger_periods": [],
                "primary_trigger_period": None,
                "n5_entry_allowed": True,
            }
        )

        candidates = build_action_candidates_from_outbox_rows([row])
        action_write_plan = build_action_write_plan(candidates)

        self.assertEqual(action_write_plan[0]["trigger_kind"], "hint")
        self.assertEqual(action_write_plan[0]["trigger_period"], "30m")
        self.assertIsNone(action_write_plan[0]["primary_trigger_period"])

    def test_deprecated_runtime_signal_type_is_blocked(self) -> None:
        rows = [
            sample_outbox_row(
                event_id="evt_buy_hint_bad_signal",
                signal_type="BUY_HINT",
                condition_key="BUY_HINT",
                original_condition_key="BUY_HINT",
            ),
            sample_outbox_row(
                event_id="evt_sell_30m_bad_signal",
                signal_type="S_SELL_30M_SHRINK",
                condition_key="SELL_HINT",
                original_condition_key="SELL_HINT",
                direction="sell",
            ),
        ]
        candidates = build_action_candidates_from_outbox_rows(rows)
        summary = summarize_action_candidates(candidates)

        self.assertEqual(summary["deprecated_runtime_signal_type_count"], 2)
        self.assertEqual({candidate["action_state"] for candidate in candidates}, {"blocked"})
        self.assertEqual({candidate["confirmation_status"] for candidate in candidates}, {"failed"})
        self.assertEqual({candidate["final_action_mark"] for candidate in candidates}, {None})
        self.assertEqual({candidate["action_event_type"] for candidate in candidates}, {"ActionBlocked"})

    def test_trigger_pending_market_data_and_state_changed_do_not_create_confirmation(self) -> None:
        rows = [
            sample_outbox_row(
                event_id="evt_pending",
                event_type="TriggerPendingMarketData",
                signal_type="B_BUY",
                condition_key="BUY_HINT",
                data_quality_status="missing",
            ),
            sample_outbox_row(
                event_id="evt_live_true",
                event_type="TriggerStateChanged",
                signal_type="B_BUY",
                condition_key="BUY:D",
                trigger_live=True,
            ),
            sample_outbox_row(
                event_id="evt_live_false",
                event_type="TriggerStateChanged",
                signal_type="B_BUY",
                condition_key="BUY:D",
                trigger_live=False,
            ),
        ]
        candidates = build_action_candidates_from_outbox_rows(rows)
        by_id = {candidate["source_trigger_event_id"]: candidate for candidate in candidates}

        self.assertFalse(by_id["evt_pending"]["starts_action_confirmation"])
        self.assertEqual(by_id["evt_pending"]["candidate_kind"], "quality_plan")
        self.assertIsNone(by_id["evt_pending"]["action_event_type"])
        self.assertFalse(by_id["evt_live_true"]["starts_action_confirmation"])
        self.assertEqual(by_id["evt_live_true"]["candidate_kind"], "state_gate")
        self.assertIsNone(by_id["evt_live_true"]["action_event_type"])
        self.assertFalse(by_id["evt_live_false"]["starts_action_confirmation"])
        self.assertEqual(by_id["evt_live_false"]["candidate_kind"], "state_gate")
        self.assertEqual(by_id["evt_live_false"]["action_state"], "expired")
        self.assertEqual(by_id["evt_live_false"]["confirmation_status"], "expired")
        self.assertIsNone(by_id["evt_live_false"]["action_event_type"])

    def test_trigger_matched_creates_tracking_state_key_with_trade_date(self) -> None:
        candidates = build_action_candidates_from_outbox_rows(
            [
                sample_outbox_row(
                    event_id="evt_tracking",
                    signal_type="B_BUY",
                    condition_key="BUY:D",
                    action_confirmation_mode="deferred",
                )
            ],
            action_run_id="action_run_tracking",
        )
        tracking_plan = build_action_tracking_state_plan(candidates)

        self.assertEqual(tracking_plan[0]["operation"], "create_tracking_unfinished")
        self.assertTrue(tracking_plan[0]["would_create_tracking_state"])
        self.assertIn("trade_date|20260525", tracking_plan[0]["state_key"])
        self.assertIn("asset_kind|stock", tracking_plan[0]["state_key"])
        self.assertIn("condition_key|BUY:D", tracking_plan[0]["state_key"])
        self.assertEqual(tracking_plan[0]["tracking_state"]["tracking_status"], "tracking")

    def test_duplicate_trigger_matched_state_key_updates_tracking_state(self) -> None:
        rows = [
            sample_outbox_row(
                event_id="evt_tracking_first",
                trigger_match_id=501,
                signal_type="B_BUY",
                condition_key="BUY:D",
                action_confirmation_mode="deferred",
            ),
            sample_outbox_row(
                event_id="evt_tracking_second",
                trigger_match_id=502,
                signal_type="B_BUY",
                condition_key="BUY:D",
                action_confirmation_mode="deferred",
            ),
        ]
        candidates = build_action_candidates_from_outbox_rows(rows, action_run_id="action_run_tracking")
        tracking_plan = build_action_tracking_state_plan(candidates)
        action_write_plan = build_action_write_plan(candidates, action_tracking_state_plan=tracking_plan)
        summary = summarize_action_tracking_state_plan(tracking_plan)
        write_summary = summarize_action_write_plan(action_write_plan)

        self.assertEqual([row["operation"] for row in tracking_plan], [
            "create_tracking_unfinished",
            "update_tracking_from_matched_unfinished",
        ])
        self.assertEqual(summary["matched_tracking_create_count"], 1)
        self.assertEqual(summary["matched_tracking_update_count"], 1)
        self.assertEqual(write_summary["would_create_action_tracking_state_count"], 1)
        self.assertEqual(write_summary["would_update_action_tracking_state_count"], 1)
        self.assertEqual(tracking_plan[0]["state_key"], tracking_plan[1]["state_key"])
        self.assertIn("trade_date|20260525", tracking_plan[1]["state_key"])

    def test_duplicate_trigger_matched_does_not_downgrade_executed_tracking_state(self) -> None:
        rows = [
            sample_outbox_row(
                event_id="evt_tracking_executed",
                trigger_match_id=601,
                signal_type="B_BUY",
                condition_key="BUY_HINT",
                source_action_confirmation_metric_id=601,
            ),
            sample_outbox_row(
                event_id="evt_tracking_blocked",
                trigger_match_id=602,
                signal_type="B_BUY",
                condition_key="BUY_HINT",
                source_action_confirmation_metric_id=602,
            ),
        ]
        candidates = build_action_candidates_from_outbox_rows(
            rows,
            action_run_id="action_run_tracking",
            action_confirmation_metric_facts={
                ("stock", "601"): metric_fact(action_confirmation_metric_id=601, buy_pass=True),
                ("stock", "602"): metric_fact(action_confirmation_metric_id=602, buy_pass=False),
            },
        )
        tracking_plan = build_action_tracking_state_plan(candidates)

        self.assertEqual(candidates[0]["action_state"], "executed")
        self.assertEqual(candidates[1]["action_state"], "blocked")
        self.assertEqual(tracking_plan[1]["operation"], "update_tracking_from_matched_terminal")
        self.assertEqual(tracking_plan[1]["tracking_state"]["action_state"], "executed")
        self.assertEqual(tracking_plan[1]["tracking_state"]["confirmation_status"], "passed")
        self.assertEqual(tracking_plan[1]["tracking_state"]["planned_output_event_type"], "ActionExecuted")

    def test_state_changed_false_expires_prior_unfinished_tracking_and_plans_action_skipped(self) -> None:
        rows = [
            sample_outbox_row(
                event_id="evt_matched_deferred",
                signal_type="B_BUY",
                condition_key="BUY:D",
                action_confirmation_mode="deferred",
            ),
            sample_outbox_row(
                event_id="evt_state_false",
                event_type="TriggerStateChanged",
                signal_type="B_BUY",
                condition_key="BUY:D",
                trigger_live=False,
            ),
        ]
        candidates = build_action_candidates_from_outbox_rows(rows, action_run_id="action_run_tracking")
        tracking_plan = build_action_tracking_state_plan(candidates)
        action_write_plan = build_action_write_plan(candidates, action_tracking_state_plan=tracking_plan)
        state_gate_plan = {row["source_trigger_event_id"]: row for row in action_write_plan}["evt_state_false"]

        self.assertEqual(tracking_plan[1]["operation"], "expire_unfinished_tracking")
        self.assertEqual(tracking_plan[1]["match_strategy"], "source_trigger_state_id")
        self.assertEqual(tracking_plan[1]["planned_output_event_type"], "ActionSkipped")
        self.assertEqual(tracking_plan[1]["expired_reason"], "trigger_live_false")
        self.assertEqual(state_gate_plan["plan_status"], "state_gate_expire")
        self.assertEqual(state_gate_plan["planned_output_event_type"], "ActionSkipped")
        self.assertFalse(state_gate_plan["would_insert_action_fact"])
        self.assertTrue(state_gate_plan["would_update_existing_action_fact"])
        self.assertTrue(state_gate_plan["would_expire_action_tracking_state"])
        self.assertTrue(state_gate_plan["would_insert_common_action_event"])
        self.assertTrue(state_gate_plan["would_insert_common_event_outbox"])

    def test_state_changed_false_without_prior_tracking_is_trace_only(self) -> None:
        candidates = build_action_candidates_from_outbox_rows(
            [
                sample_outbox_row(
                    event_id="evt_state_false_only",
                    event_type="TriggerStateChanged",
                    signal_type="B_BUY",
                    condition_key="BUY:D",
                    trigger_live=False,
                )
            ],
            action_run_id="action_run_tracking",
        )
        tracking_plan = build_action_tracking_state_plan(candidates)
        action_write_plan = build_action_write_plan(candidates, action_tracking_state_plan=tracking_plan)

        self.assertEqual(tracking_plan[0]["operation"], "state_gate_trace_only_no_prior_tracking")
        self.assertFalse(tracking_plan[0]["would_create_tracking_state"])
        self.assertFalse(tracking_plan[0]["would_update_tracking_state"])
        self.assertEqual(action_write_plan[0]["plan_status"], "state_gate_only")
        self.assertFalse(action_write_plan[0]["would_insert_action_fact"])
        self.assertFalse(action_write_plan[0]["would_insert_common_action_event"])

    def test_state_changed_false_does_not_reverse_terminal_action(self) -> None:
        rows = [
            sample_outbox_row(
                event_id="evt_matched_terminal",
                signal_type="B_BUY",
                condition_key="BUY:D",
            ),
            sample_outbox_row(
                event_id="evt_state_false_terminal",
                event_type="TriggerStateChanged",
                signal_type="B_BUY",
                condition_key="BUY:D",
                trigger_live=False,
            ),
        ]
        candidates = build_action_candidates_from_outbox_rows(rows, action_run_id="action_run_tracking")
        tracking_plan = build_action_tracking_state_plan(candidates)
        action_write_plan = build_action_write_plan(candidates, action_tracking_state_plan=tracking_plan)
        state_gate_plan = {row["source_trigger_event_id"]: row for row in action_write_plan}["evt_state_false_terminal"]

        self.assertEqual(candidates[0]["action_state"], "blocked")
        self.assertEqual(tracking_plan[1]["operation"], "state_gate_terminal_noop")
        self.assertEqual(tracking_plan[1]["terminal_action_state"], "blocked")
        self.assertEqual(state_gate_plan["plan_status"], "state_gate_only")
        self.assertIsNone(state_gate_plan["planned_output_event_type"])
        self.assertFalse(state_gate_plan["would_update_existing_action_fact"])

    def test_duplicate_state_changed_event_id_is_idempotent(self) -> None:
        rows = [
            sample_outbox_row(
                event_id="evt_matched_deferred",
                signal_type="B_BUY",
                condition_key="BUY:D",
                action_confirmation_mode="deferred",
            ),
            sample_outbox_row(
                event_id="evt_state_duplicate",
                event_type="TriggerStateChanged",
                signal_type="B_BUY",
                condition_key="BUY:D",
                trigger_live=False,
            ),
            sample_outbox_row(
                event_id="evt_state_duplicate",
                event_type="TriggerStateChanged",
                signal_type="B_BUY",
                condition_key="BUY:D",
                trigger_live=False,
            ),
        ]
        candidates = build_action_candidates_from_outbox_rows(rows, action_run_id="action_run_tracking")
        tracking_plan = build_action_tracking_state_plan(candidates)
        action_write_plan = build_action_write_plan(candidates, action_tracking_state_plan=tracking_plan)
        summary = summarize_action_tracking_state_plan(tracking_plan)

        self.assertEqual(summary["tracking_expire_count"], 1)
        self.assertEqual(summary["duplicate_n4_event_id_noop_count"], 1)
        self.assertEqual(
            [row["plan_status"] for row in action_write_plan if row["source_trigger_event_id"] == "evt_state_duplicate"],
            ["state_gate_expire", "state_gate_only"],
        )

    def test_period_trigger_baseline_trace_is_carried_in_source_market_trace(self) -> None:
        candidates = build_action_candidates_from_outbox_rows(
            [
                sample_outbox_row(
                    event_id="evt_trace",
                    signal_type="B_BUY",
                    condition_key="BUY:D",
                    source_event_type="MarketSnapshotUpdated",
                    period_trigger_baseline_trace={"present": True, "baseline_version": "N2-R4-period-trigger-baseline-v1"},
                )
            ]
        )

        self.assertEqual(
            candidates[0]["source_market_trace"]["period_trigger_baseline_trace"]["baseline_version"],
            "N2-R4-period-trigger-baseline-v1",
        )

    def test_final_action_mark_is_null_when_confirmation_is_pending(self) -> None:
        candidates = build_action_candidates_from_outbox_rows(
            [
                sample_outbox_row(
                    event_id="evt_pending_confirmation",
                    signal_type="B_BUY",
                    condition_key="BUY:D",
                    trigger_mark_candidate="normal",
                    action_confirmation_mode="deferred",
                )
            ]
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["action_state"], "eligible")
        self.assertEqual(candidates[0]["confirmation_status"], "pending")
        self.assertIsNone(candidates[0]["final_action_mark"])
        self.assertEqual(candidates[0]["trace_json"]["candidate_action_mark"], "normal")
        self.assertEqual(candidates[0]["action_event_type"], "ActionEligible")

    def test_n5_dry_run_does_not_write_user_voice_sim_or_checkpoint(self) -> None:
        before = {
            "common_event_inbox": {"exists": True, "row_count": 0, "status": "present"},
            "common_event_consumer_checkpoint": {"exists": True, "row_count": 0, "status": "present"},
        }
        report = build_action_preflight_report_from_rows(
            trigger_run_id="trigger_run",
            action_run_id="action_run",
            trigger_run={"run_id": "trigger_run", "for_trade_date": "20260525"},
            outbox_rows=[
                sample_outbox_row(event_id="evt_buy_hint", signal_type="B_BUY", condition_key="BUY_HINT"),
                sample_outbox_row(
                    event_id="evt_sell_hint",
                    signal_type="S_SELL",
                    condition_key="SELL_HINT",
                    direction="sell",
                ),
                sample_outbox_row(
                    event_id="evt_pending",
                    event_type="TriggerPendingMarketData",
                    source_event_type="MarketDataDelayed",
                    data_quality_status="delayed",
                ),
            ],
            before_row_counts=before,
            after_row_counts=before,
        )

        self.assertFalse(report["side_effects"]["common_event_inbox_updated"])
        self.assertFalse(report["side_effects"]["consumer_checkpoint_updated"])
        self.assertFalse(report["side_effects"]["user_layer_touched"])
        self.assertFalse(report["side_effects"]["voice_touched"])
        self.assertFalse(report["side_effects"]["sim_touched"])
        self.assertFalse(report["side_effects"]["real_trade_touched"])

    def test_unclosed_minute_k_does_not_confirm_action(self) -> None:
        candidates = build_action_candidates_from_outbox_rows(
            [
                sample_outbox_row(
                    event_id="evt_unclosed",
                    signal_type="B_BUY",
                    condition_key="BUY_HINT",
                    source_event_type="MinuteBarOpen",
                    minute_context={"is_closed": False},
                )
            ]
        )
        summary = summarize_action_candidates(candidates)

        self.assertEqual(candidates[0]["minute_boundary_status"], "unclosed")
        self.assertEqual(candidates[0]["action_state"], "blocked")
        self.assertEqual(candidates[0]["confirmation_status"], "failed")
        self.assertEqual(candidates[0]["planned_output_event_type"], "ActionBlocked")
        self.assertEqual(summary["unclosed_minute_generates_action_executed_count"], 0)

    def test_default_consumer_name_contract_passes(self) -> None:
        report = build_action_consumer_report(
            consumer_name=DEFAULT_N5_1_CONSUMER_NAME,
            baseline_report={},
        )

        self.assertEqual(quality_status(report, "n5_5_consumer_name_contract"), "passed")

    def test_declared_dedicated_metric_reprocess_consumer_name_contract_passes(self) -> None:
        dedicated_consumer = "n5_action_consumer_v1_until_0952_metric_aware_reprocess"
        source_run_id = "trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry"
        report = build_action_consumer_report(
            consumer_name=dedicated_consumer,
            trigger_run_id=source_run_id,
            baseline_report=metric_reprocess_baseline(
                source_run_id=source_run_id,
                dedicated_consumer_name=dedicated_consumer,
            ),
        )

        self.assertEqual(quality_status(report, "n5_5_consumer_name_contract"), "passed")
        self.assertEqual(report["consumer_guard"]["strategy"], "dedicated_reprocess")
        self.assertTrue(report["consumer_guard"]["passed"])

    def test_arbitrary_consumer_name_contract_blocks_without_baseline_declaration(self) -> None:
        report = build_action_consumer_report(
            consumer_name="n5_action_consumer_v1_surprise_replay",
            baseline_report={},
        )

        self.assertEqual(quality_status(report, "n5_5_consumer_name_contract"), "failed")
        self.assertFalse(report["consumer_guard"]["passed"])
        self.assertIn("baseline_dedicated_consumer_not_declared", report["consumer_guard"]["blockers"])

    def test_dedicated_metric_reprocess_consumer_blocks_when_live_refs_exist(self) -> None:
        dedicated_consumer = "n5_action_consumer_v1_until_0952_metric_aware_reprocess"
        source_run_id = "trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry"
        report = build_action_consumer_report(
            consumer_name=dedicated_consumer,
            trigger_run_id=source_run_id,
            baseline_report=metric_reprocess_baseline(
                source_run_id=source_run_id,
                dedicated_consumer_name=dedicated_consumer,
            ),
            existing_inbox_keys={"evt_trigger": {"existing"}},
            existing_checkpoints={"stock:SH:600000": {"checkpoint_event_id": "evt_later"}},
        )

        self.assertEqual(quality_status(report, "n5_5_consumer_name_contract"), "failed")
        self.assertFalse(report["consumer_guard"]["passed"])
        self.assertIn("dedicated_consumer_inbox_or_checkpoint_not_empty", report["consumer_guard"]["blockers"])


def sample_outbox_row(
    *,
    event_id: str = "evt_trigger",
    event_type: str = "TriggerMatched",
    trigger_match_id: int = 100,
    signal_type: str = "B_BUY",
    condition_key: str = "BUY_HINT",
    original_condition_key: str | None = None,
    direction: str = "buy",
    source_event_type: str = "MinuteBarClosed",
    data_quality_status: str = "passed",
    minute_context: dict[str, object] | None = None,
    asset_kind: str = "stock",
    identity_key: str | None = None,
    trigger_live: bool | None = True,
    trigger_mark_candidate: str = "normal",
    projection_30m_type: str = "none",
    action_confirmation: dict[str, str] | None = None,
    source_action_confirmation_metric_id: int | None = None,
    action_confirmation_mode: str | None = None,
    period_trigger_baseline_trace: dict[str, object] | None = None,
    projection_trace: dict[str, object] | None = None,
    source_run_id: str = "trigger_run",
) -> dict[str, object]:
    identity = identity_key or ("stock:SH:600000" if direction == "buy" else "stock:SH:600001")
    payload = {
        "run_id": source_run_id,
        "source_event_id": f"source_{event_id}",
        "source_event_type": source_event_type,
        "source_condition_run_id": "condition_run",
        "source_market_data_run_id": "market_run",
        "trigger_match_id": trigger_match_id,
        "trigger_state_id": 200,
        "identity_key": identity,
        "asset_kind": asset_kind,
        "direction": direction,
        "signal_type": signal_type,
        "condition_key": condition_key,
        "original_condition_key": original_condition_key or condition_key,
        "trigger_mark_candidate": trigger_mark_candidate,
        "projection_30m_flag": projection_30m_type != "none",
        "projection_30m_type": projection_30m_type,
        "trigger_live": trigger_live,
        "trigger_period": "30m" if trigger_mark_candidate in {"30m_volume", "30m_shrink"} else "D",
        "trigger_bucket": "30m_1000_1030",
        "data_quality_status": data_quality_status,
        "synthetic_sample_event": True,
    }
    if minute_context is not None:
        payload["minute_context"] = minute_context
    if action_confirmation is not None:
        payload["action_confirmation"] = action_confirmation
    if source_action_confirmation_metric_id is not None:
        payload["source_action_confirmation_metric_id"] = source_action_confirmation_metric_id
        payload["source_projection_run_id"] = "action_confirmation_projection_metric_test"
    if action_confirmation_mode is not None:
        payload["action_confirmation_mode"] = action_confirmation_mode
    if period_trigger_baseline_trace is not None:
        payload["period_trigger_baseline_trace"] = period_trigger_baseline_trace
    if projection_trace is not None:
        payload["projection_trace"] = projection_trace
    return {
        "outbox_id": 1,
        "event_id": event_id,
        "event_type": event_type,
        "event_schema_version": "v1",
        "trade_date": "20260525",
        "asset_kind": payload["asset_kind"],
        "identity_key": payload["identity_key"],
        "event_time": "2026-05-25T02:30:00+00:00",
        "source_layer": "N4_trigger",
        "source_run_id": source_run_id,
        "dedup_key": f"dedup_{event_id}",
        "partition_key": payload["identity_key"],
        "payload_json": payload,
        "status": "pending",
    }


def build_action_consumer_report(
    *,
    consumer_name: str,
    trigger_run_id: str = "trigger_run",
    baseline_report: dict[str, object] | None = None,
    existing_inbox_keys: dict[str, set[str]] | None = None,
    existing_checkpoints: dict[str, dict[str, object]] | None = None,
) -> dict[str, object]:
    return build_action_consumer_run_once_dry_run_report_from_rows(
        trigger_run_id=trigger_run_id,
        action_run_id="action_run",
        consumer_name=consumer_name,
        trigger_run={"run_id": trigger_run_id, "for_trade_date": "20260525"},
        outbox_rows=[sample_outbox_row(event_id="evt_trigger", source_run_id=trigger_run_id)],
        existing_inbox_keys=existing_inbox_keys or {},
        existing_checkpoints=existing_checkpoints or {},
        before_row_counts=empty_guard_counts(),
        after_row_counts=empty_guard_counts(),
        baseline_report=baseline_report,
        baseline_report_path="baseline.json",
        expected_read_event_count=1,
    )


def metric_reprocess_baseline(
    *,
    source_run_id: str,
    dedicated_consumer_name: str,
    metric_run_id: str = "action_confirmation_metric_20260608_until_0952",
) -> dict[str, object]:
    return {
        "source_trigger_run_id": source_run_id,
        "metric_run_id": metric_run_id,
        "consumer_strategy": {
            "uses_dedicated_consumer": True,
            "dedicated_consumer_name": dedicated_consumer_name,
        },
    }


def empty_guard_counts() -> dict[str, dict[str, object]]:
    return {
        "common_event_inbox": {"exists": True, "row_count": 0},
        "common_event_consumer_checkpoint": {"exists": True, "row_count": 0},
        "stock_action_fact": {"exists": True, "row_count": 0},
        "index_action_fact": {"exists": True, "row_count": 0},
        "board_action_fact": {"exists": True, "row_count": 0},
        "common_action_event": {"exists": True, "row_count": 0},
        "common_position_state": {"exists": True, "row_count": 0},
        "common_position_event": {"exists": True, "row_count": 0},
    }


def quality_status(report: dict[str, object], gate_code: str) -> str:
    for item in report["quality"]["items"]:
        if item["gate_code"] == gate_code:
            return item["status"]
    raise AssertionError(f"missing quality item {gate_code}")


def metric_fact(
    *,
    asset_kind: str = "stock",
    action_confirmation_metric_id: int = 647,
    identity_key: str = "stock:SZ:300382",
    signal_type: str = "B_BUY",
    buy_pass: bool = True,
    sell_pass: bool = True,
    buy_120m_price_pass: bool | None = None,
) -> dict[str, object]:
    buy_120m = buy_pass if buy_120m_price_pass is None else buy_120m_price_pass
    if signal_type == "S_SELL":
        current_30m_virtual_amount = "800"
        previous_day_same_window_amount = "1000"
    else:
        current_30m_virtual_amount = "1200"
        previous_day_same_window_amount = "1000"
    return {
        "asset_kind": asset_kind,
        "action_confirmation_metric_id": action_confirmation_metric_id,
        "projection_run_id": "action_confirmation_projection_metric_test",
        "identity_key": identity_key,
        "metric_ready": True,
        "metric_quality_status": "passed",
        "metric_minute_label": "11:05",
        "buy_120m_price_pass": buy_120m,
        "buy_30m_price_pass": buy_pass,
        "buy_5m_price_pass": buy_pass,
        "buy_5m_amount_pass": buy_pass,
        "buy_1m_price_pass": buy_pass,
        "buy_1m_amount_pass": buy_pass,
        "sell_120m_price_pass": sell_pass,
        "sell_30m_price_pass": sell_pass,
        "sell_5m_price_pass": sell_pass,
        "sell_5m_amount_pass": sell_pass,
        "sell_1m_price_pass": sell_pass,
        "sell_1m_amount_pass": sell_pass,
        "current_30m_virtual_amount": current_30m_virtual_amount,
        "previous_day_same_window_amount": previous_day_same_window_amount,
        "previous_30m_full_amount": previous_day_same_window_amount,
        "virtual_amount_policy_version": "previous_day_same_window_elapsed_ratio_v1",
        "projection_schema_version": "n3.action_confirmation_metric.v1",
        "source_fact_ids": {"source_snapshot_id": 1},
    }


def numeric_metric_fact(
    *,
    signal_type: str,
    direction: str = "buy",
    current_price: str = "10.00",
    current_1m_amount: str = "1000",
    previous_1m_amount: str = "900",
    current_5m_virtual_amount: str = "1000",
    previous_5m_full_amount: str = "900",
    current_30m_virtual_amount: object = _DEFAULT,
    previous_day_same_window_amount: object = _DEFAULT,
    virtual_amount_policy_version: str = "previous_day_same_window_elapsed_ratio_v1",
) -> dict[str, object]:
    if signal_type == "S_SELL" or direction == "sell":
        previous_high = "10.50"
        previous_low = "10.50"
        previous_1m_amount = previous_1m_amount if previous_1m_amount != "900" else "1100"
        previous_5m_full_amount = previous_5m_full_amount if previous_5m_full_amount != "900" else "1100"
        current_30m_virtual_amount = current_30m_virtual_amount if current_30m_virtual_amount is not _DEFAULT else "800"
        previous_day_same_window_amount = (
            previous_day_same_window_amount if previous_day_same_window_amount is not _DEFAULT else "1000"
        )
    else:
        previous_high = "9.50"
        previous_low = "9.50"
        current_30m_virtual_amount = current_30m_virtual_amount if current_30m_virtual_amount is not _DEFAULT else "1200"
        previous_day_same_window_amount = (
            previous_day_same_window_amount if previous_day_same_window_amount is not _DEFAULT else "1000"
        )
    return {
        "asset_kind": "stock",
        "action_confirmation_metric_id": 702,
        "projection_run_id": "action_confirmation_projection_metric_test",
        "identity_key": "stock:SH:600000",
        "metric_ready": True,
        "metric_quality_status": "passed",
        "metric_minute_label": "11:05",
        "current_price": current_price,
        "previous_120m_body_high": previous_high,
        "previous_120m_body_low": previous_low,
        "previous_30m_body_high": previous_high,
        "previous_30m_body_low": previous_low,
        "previous_5m_body_high": previous_high,
        "previous_5m_body_low": previous_low,
        "previous_1m_body_high": previous_high,
        "previous_1m_body_low": previous_low,
        "current_1m_amount": current_1m_amount,
        "previous_1m_amount": previous_1m_amount,
        "current_5m_virtual_amount": current_5m_virtual_amount,
        "previous_5m_full_amount": previous_5m_full_amount,
        "current_30m_virtual_amount": current_30m_virtual_amount,
        "previous_day_same_window_amount": previous_day_same_window_amount,
        "previous_30m_full_amount": previous_day_same_window_amount,
        "virtual_amount_policy_version": virtual_amount_policy_version,
        "previous_1m_period_source": "same_trade_date_previous_period",
        "previous_5m_period_source": "same_trade_date_previous_period",
        "previous_30m_period_source": "same_trade_date_previous_period",
        "previous_120m_period_source": "same_trade_date_previous_period",
        "is_first_1m_of_day": False,
        "is_first_5m_of_day": False,
        "is_first_30m_of_day": False,
        "is_first_120m_of_day": False,
        "first_1m_amount_default_pass": False,
        "first_5m_amount_default_pass": False,
        "projection_schema_version": "n3.action_confirmation_metric.v1",
        "source_fact_ids": {"source_snapshot_id": 1},
    }


if __name__ == "__main__":
    unittest.main()
