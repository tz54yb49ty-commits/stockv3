import json
import unittest

from ashare_v3.trigger.local_trigger_dry_run import (
    build_local_trigger_dry_run_report,
    build_local_trigger_plans,
    ordinary_amount_baseline,
    summarize_local_trigger_plans,
)


CONTEXT_RUN_ID = "trigger_context_snapshot_20260528_condition_layer_20260527_source_20260527_v1"
SNAPSHOT_RUN_ID = "realtime_snapshot_20260528_retry1_market_data_subscription_20260528_condition_layer_20260527_source_20260527_v1"


class LocalTriggerDryRunTests(unittest.TestCase):
    def test_snapshot_ready_ordinary_buy_sell_emit_matched_plans(self) -> None:
        plans = build_local_trigger_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            snapshot_run_id=SNAPSHOT_RUN_ID,
            context_rows=[
                context_row("stock:SH:600000", "buy", "BUY:D", ["B_BUY", "B_BUY_30M_VOL"]),
                context_row("stock:SH:600001", "sell", "SELL:D", ["S_SELL", "S_SELL_30M_SHRINK"]),
            ],
            snapshot_rows=[
                snapshot_row("stock", "stock:SH:600000", open_price="10.00", close="10.50", amount="1000"),
                snapshot_row("stock", "stock:SH:600001", open_price="10.50", close="10.00", amount="50"),
            ],
        )

        summary = summarize_local_trigger_plans(plans)

        self.assertEqual(summary["matched_plan_count"], 2)
        self.assertEqual(summary["pending_plan_count"], 2)
        self.assertEqual(summary["matched_by_signal_type"], {"B_BUY": 1, "S_SELL": 1})
        self.assertEqual(
            summary["pending_by_signal_type"],
            {"B_BUY": 1, "S_SELL": 1},
        )
        self.assertEqual(summary["pending_by_trigger_mark_candidate"], {"30m_shrink": 1, "30m_volume": 1})
        self.assertEqual(
            summary["pending_by_legacy_signal_type"],
            {"B_BUY_30M_VOL": 1, "S_SELL_30M_SHRINK": 1},
        )
        self.assertEqual(
            summary["planned_output_event_types"],
            {"TriggerMatched": 2, "TriggerPendingMarketData": 2, "TriggerStateChanged": 4},
        )
        self.assertEqual(summary["state_change_plan_count"], 4)
        self.assertEqual(summary["deprecated_runtime_signal_type_count"], 0)
        self.assertEqual(summary["pending_market_data_trigger_live_false_count"], 2)
        self.assertTrue(all("trigger_mark_candidate" in plan for plan in plans))
        self.assertTrue(all("action_mark" not in plan for plan in plans))
        self.assertTrue(all(plan["previous_status"] == "inactive" for plan in plans))

    def test_down_snapshot_does_not_emit_buy_trigger_matched(self) -> None:
        plans = build_local_trigger_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            snapshot_run_id=SNAPSHOT_RUN_ID,
            context_rows=[
                context_row("stock:SH:600000", "buy", "BUY:D", ["B_BUY", "B_BUY_30M_VOL"]),
            ],
            snapshot_rows=[
                snapshot_row("stock", "stock:SH:600000", open_price="10.50", close="10.00", amount="1000"),
            ],
        )

        summary = summarize_local_trigger_plans(plans)

        self.assertEqual(summary["matched_plan_count"], 0)
        self.assertEqual(summary["pending_plan_count"], 2)
        self.assertEqual(summary["deprecated_runtime_signal_type_count"], 0)
        ordinary_pending = [
            plan
            for plan in plans
            if plan["legacy_signal_type"] == "B_BUY" and plan["output_event_type"] == "TriggerPendingMarketData"
        ]
        self.assertEqual(len(ordinary_pending), 1)
        self.assertEqual(ordinary_pending[0]["pending_reason"], "ordinary_snapshot_trigger_condition_not_met")
        self.assertEqual(ordinary_pending[0]["signal_type"], "B_BUY")

    def test_up_snapshot_does_not_emit_sell_trigger_matched(self) -> None:
        plans = build_local_trigger_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            snapshot_run_id=SNAPSHOT_RUN_ID,
            context_rows=[
                context_row("stock:SH:600001", "sell", "SELL:D", ["S_SELL", "S_SELL_30M_SHRINK"]),
            ],
            snapshot_rows=[
                snapshot_row("stock", "stock:SH:600001", open_price="10.00", close="10.50", amount="50"),
            ],
        )

        summary = summarize_local_trigger_plans(plans)

        self.assertEqual(summary["matched_plan_count"], 0)
        self.assertEqual(summary["pending_plan_count"], 2)
        self.assertEqual(summary["deprecated_runtime_signal_type_count"], 0)
        ordinary_pending = [
            plan
            for plan in plans
            if plan["legacy_signal_type"] == "S_SELL" and plan["output_event_type"] == "TriggerPendingMarketData"
        ]
        self.assertEqual(len(ordinary_pending), 1)
        self.assertEqual(ordinary_pending[0]["pending_reason"], "ordinary_snapshot_trigger_condition_not_met")
        self.assertEqual(ordinary_pending[0]["signal_type"], "S_SELL")

    def test_missing_period_baseline_does_not_emit_trigger_matched(self) -> None:
        plans = build_local_trigger_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            snapshot_run_id=SNAPSHOT_RUN_ID,
            context_rows=[
                context_row(
                    "stock:SH:600000",
                    "buy",
                    "BUY:D",
                    ["B_BUY", "B_BUY_30M_VOL"],
                    period_baseline={},
                ),
            ],
            snapshot_rows=[
                snapshot_row("stock", "stock:SH:600000", open_price="10.00", close="10.50", amount="1000"),
            ],
        )

        summary = summarize_local_trigger_plans(plans)

        self.assertEqual(summary["matched_plan_count"], 0)
        self.assertEqual(summary["deprecated_runtime_signal_type_count"], 0)
        ordinary_pending = [
            plan
            for plan in plans
            if plan["legacy_signal_type"] == "B_BUY" and plan["output_event_type"] == "TriggerPendingMarketData"
        ]
        self.assertEqual(len(ordinary_pending), 1)
        self.assertEqual(ordinary_pending[0]["pending_reason"], "period_trigger_baseline_missing")
        self.assertEqual(ordinary_pending[0]["signal_type"], "B_BUY")

    def test_ordinary_buy_uses_repaired_trigger_amount_baseline(self) -> None:
        period_baseline = period_trigger_baseline_json()
        period_baseline["periods"]["D"]["previous_amount"] = "100"
        period_baseline["periods"]["D"]["previous_avg_amount"] = "100"
        period_baseline["periods"]["D"]["trigger_previous_entity_high"] = "9.66"
        period_baseline["periods"]["D"]["trigger_previous_amount_baseline"] = "200"

        plans = build_local_trigger_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            snapshot_run_id=SNAPSHOT_RUN_ID,
            context_rows=[
                context_row(
                    "stock:SZ:002399",
                    "buy",
                    "BUY:D",
                    ["B_BUY"],
                    period_baseline=period_baseline,
                ),
            ],
            snapshot_rows=[
                snapshot_row("stock", "stock:SZ:002399", open_price="9.40", close="9.70", amount="150"),
            ],
        )

        summary = summarize_local_trigger_plans(plans)

        self.assertEqual(summary["matched_plan_count"], 0)
        ordinary_pending = [
            plan
            for plan in plans
            if plan["legacy_signal_type"] == "B_BUY" and plan["output_event_type"] == "TriggerPendingMarketData"
        ]
        self.assertEqual(len(ordinary_pending), 1)
        self.assertEqual(ordinary_pending[0]["pending_reason"], "ordinary_snapshot_trigger_condition_not_met")
        self.assertIn("trigger_previous_amount_baseline", ordinary_pending[0]["dry_run_reason"])

    def test_ordinary_buy_and_sell_use_repaired_trigger_entity_bounds(self) -> None:
        buy_baseline = period_trigger_baseline_json()
        buy_baseline["periods"]["D"]["trigger_previous_entity_high"] = "9.66"
        buy_baseline["periods"]["D"]["trigger_previous_entity_low"] = "9.45"
        sell_baseline = period_trigger_baseline_json()
        sell_baseline["periods"]["D"]["trigger_previous_entity_high"] = "4088.88"
        sell_baseline["periods"]["D"]["trigger_previous_entity_low"] = "4072.55"

        plans = build_local_trigger_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            snapshot_run_id=SNAPSHOT_RUN_ID,
            context_rows=[
                context_row(
                    "stock:SZ:002399",
                    "buy",
                    "BUY:D",
                    ["B_BUY"],
                    period_baseline=buy_baseline,
                ),
                context_row(
                    "index:SZ:399006",
                    "sell",
                    "SELL:D",
                    ["S_SELL"],
                    asset_kind="index",
                    period_baseline=sell_baseline,
                ),
            ],
            snapshot_rows=[
                snapshot_row("stock", "stock:SZ:002399", open_price="9.40", close="9.60", amount="1000000"),
                snapshot_row("index", "index:SZ:399006", open_price="4080", close="4075", amount="1"),
            ],
        )

        summary = summarize_local_trigger_plans(plans)

        self.assertEqual(summary["matched_plan_count"], 0)
        self.assertEqual(summary["pending_plan_count"], 2)
        reasons = {plan["identity_key"]: plan["dry_run_reason"] for plan in plans}
        self.assertIn("trigger_previous_entity_high", reasons["stock:SZ:002399"])
        self.assertIn("trigger_previous_entity_low", reasons["index:SZ:399006"])

    def test_ordinary_amount_baseline_falls_back_when_trigger_baseline_missing(self) -> None:
        self.assertEqual(
            ordinary_amount_baseline({"previous_amount": "100", "previous_avg_amount": "90", "amount_metric": "amount"}),
            100,
        )

    def test_hint_and_30m_signals_are_pending_without_projection(self) -> None:
        plans = build_local_trigger_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            snapshot_run_id=SNAPSHOT_RUN_ID,
            context_rows=[
                context_row("stock:SH:600000", "buy", "BUY_HINT", ["BUY_HINT"]),
                context_row("stock:SH:600001", "sell", "SELL_HINT", ["SELL_HINT"]),
            ],
            snapshot_rows=[
                snapshot_row("stock", "stock:SH:600000"),
                snapshot_row("stock", "stock:SH:600001"),
            ],
        )

        summary = summarize_local_trigger_plans(plans)

        self.assertEqual(summary["matched_plan_count"], 0)
        self.assertEqual(summary["pending_plan_count"], 2)
        self.assertEqual(summary["pending_by_signal_type"], {"B_BUY": 1, "S_SELL": 1})
        self.assertEqual(summary["pending_by_legacy_signal_type"], {"BUY_HINT": 1, "SELL_HINT": 1})
        self.assertEqual(summary["buy_hint_condition_key_trace_count"], 1)
        self.assertEqual(summary["sell_hint_condition_key_trace_count"], 1)
        self.assertEqual(summary["deprecated_runtime_signal_type_count"], 0)
        self.assertEqual({plan["output_event_type"] for plan in plans}, {"TriggerPendingMarketData"})
        self.assertTrue(all(plan["pending_reason"] == "projection_fact_not_available_in_local_snapshot_dry_run" for plan in plans))
        self.assertTrue(all(plan["condition_key"] in {"BUY_HINT", "SELL_HINT"} for plan in plans))
        self.assertTrue(all(plan["signal_type"] in {"B_BUY", "S_SELL"} for plan in plans))

    def test_local_dry_run_report_includes_independent_state_change_plans(self) -> None:
        report = build_local_trigger_dry_run_report(
            trigger_context_run_id=CONTEXT_RUN_ID,
            snapshot_run_id=SNAPSHOT_RUN_ID,
            trigger_run={"run_id": CONTEXT_RUN_ID, "status": "passed", "for_trade_date": "20260528"},
            snapshot_run={"run_id": SNAPSHOT_RUN_ID, "status": "passed", "p0_count": 0, "p1_count": 0, "p2_count": 0},
            context_rows=[
                context_row("stock:SH:600000", "buy", "BUY:D", ["B_BUY", "B_BUY_30M_VOL"]),
            ],
            snapshot_rows=[snapshot_row("stock", "stock:SH:600000")],
            before_row_counts=guard_counts(),
            after_row_counts=guard_counts(),
            scoped_event_refs=scoped_refs(),
        )

        self.assertEqual(report["summary"]["state_change_plan_count"], report["candidate_count"])
        self.assertEqual(report["summary"]["planned_output_event_types"]["TriggerStateChanged"], report["candidate_count"])
        self.assertEqual(len(report["sample_state_change_plans"]), report["candidate_count"])
        state_plan = report["sample_state_change_plans"][0]
        self.assertEqual(state_plan["output_event_type"], "TriggerStateChanged")
        self.assertEqual(state_plan["previous_status"], "inactive")
        self.assertIn(state_plan["state_change_reason"], {"activated", "status_changed"})

    def test_report_has_no_db_write_or_event_consumption_side_effects(self) -> None:
        report = build_local_trigger_dry_run_report(
            trigger_context_run_id=CONTEXT_RUN_ID,
            snapshot_run_id=SNAPSHOT_RUN_ID,
            trigger_run={"run_id": CONTEXT_RUN_ID, "status": "passed", "for_trade_date": "20260528"},
            snapshot_run={"run_id": SNAPSHOT_RUN_ID, "status": "passed", "p0_count": 0, "p1_count": 1, "p2_count": 0},
            context_rows=[
                context_row("stock:SH:600000", "buy", "BUY:D", ["B_BUY", "B_BUY_30M_VOL"]),
            ],
            snapshot_rows=[snapshot_row("stock", "stock:SH:600000")],
            before_row_counts=guard_counts(),
            after_row_counts=guard_counts(),
            scoped_event_refs=scoped_refs(),
        )

        self.assertEqual(report["result"], "DRY_RUN_PASS")
        self.assertEqual(report["quality"]["p0_count"], 0, report["quality"]["items"])
        self.assertGreaterEqual(report["quality"]["p1_count"], 1)
        self.assertFalse(report["side_effects"]["writes_performed"])
        self.assertFalse(report["side_effects"]["common_event_outbox_consumed"])
        self.assertFalse(report["side_effects"]["common_event_inbox_written"])
        self.assertFalse(report["side_effects"]["checkpoint_written"])
        self.assertFalse(report["side_effects"]["trigger_match_written"])
        self.assertFalse(report["side_effects"]["trigger_state_written"])
        self.assertFalse(report["side_effects"]["event_outbox_written"])
        self.assertFalse(report["side_effects"]["worker_started"])
        self.assertNotIn("/Volumes/MacRaid", json.dumps(report, ensure_ascii=False))

    def test_allowlisted_upstream_n3_outbox_does_not_block_live2_dry_run(self) -> None:
        report = build_local_trigger_dry_run_report(
            trigger_context_run_id=CONTEXT_RUN_ID,
            snapshot_run_id=SNAPSHOT_RUN_ID,
            trigger_run={"run_id": CONTEXT_RUN_ID, "status": "passed", "for_trade_date": "20260529"},
            snapshot_run={"run_id": SNAPSHOT_RUN_ID, "status": "passed", "p0_count": 0, "p1_count": 0, "p2_count": 0},
            context_rows=[
                context_row("stock:SH:600000", "buy", "BUY:D", ["B_BUY", "B_BUY_30M_VOL"]),
            ],
            snapshot_rows=[snapshot_row("stock", "stock:SH:600000")],
            before_row_counts=guard_counts(),
            after_row_counts=guard_counts(),
            scoped_event_refs=live2_scoped_refs(upstream_allowed=2157),
        )

        self.assertEqual(report["result"], "DRY_RUN_PASS", report["quality"]["items"])
        self.assertEqual(report["upstream_input_refs"]["upstream_input_outbox_allowed"], 2157)
        self.assertEqual(report["target_output_refs"]["target_output_outbox_refs"], 0)
        gate_codes = {item["gate_code"]: item["status"] for item in report["quality"]["items"]}
        self.assertEqual(gate_codes["n4_local_dry_run_upstream_input_refs_compatible"], "passed")
        self.assertEqual(gate_codes["n4_local_dry_run_target_refs_zero"], "passed")

    def test_consumed_or_non_allowlisted_upstream_input_blocks_live2_dry_run(self) -> None:
        report = build_local_trigger_dry_run_report(
            trigger_context_run_id=CONTEXT_RUN_ID,
            snapshot_run_id=SNAPSHOT_RUN_ID,
            trigger_run={"run_id": CONTEXT_RUN_ID, "status": "passed", "for_trade_date": "20260529"},
            snapshot_run={"run_id": SNAPSHOT_RUN_ID, "status": "passed", "p0_count": 0, "p1_count": 0, "p2_count": 0},
            context_rows=[
                context_row("stock:SH:600000", "buy", "BUY:D", ["B_BUY", "B_BUY_30M_VOL"]),
            ],
            snapshot_rows=[snapshot_row("stock", "stock:SH:600000")],
            before_row_counts=guard_counts(),
            after_row_counts=guard_counts(),
            scoped_event_refs=live2_scoped_refs(upstream_allowed=2157, upstream_inbox=1),
        )

        self.assertEqual(report["result"], "DRY_RUN_BLOCKED")
        gate_codes = {item["gate_code"]: item["status"] for item in report["quality"]["items"]}
        self.assertEqual(gate_codes["n4_local_dry_run_upstream_input_refs_compatible"], "failed")


def context_row(
    identity_key: str,
    direction: str,
    condition_key: str,
    allowed_signal_types: list[str],
    *,
    asset_kind: str = "stock",
    period_baseline: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "trigger_context_id": stable_int(identity_key + condition_key),
        "run_id": CONTEXT_RUN_ID,
        "source_condition_run_id": "condition_layer_20260527_source_20260527_v1",
        "source_condition_pool_id": stable_int(identity_key + "pool"),
        "source_condition_basis_id": stable_int(identity_key + "basis"),
        "source_minute_target_scope_id": stable_int(identity_key + "scope"),
        "source_market_subscription_id": stable_int(identity_key + "subscription"),
        "for_trade_date": "20260528",
        "source_trade_date": "20260527",
        "prev_trade_date": "20260527",
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "direction": direction,
        "condition_key": condition_key,
        "condition_periods": ["D"] if ":" in condition_key else [],
        "allowed_signal_types": allowed_signal_types,
        "is_hint_scope": condition_key in {"BUY_HINT", "SELL_HINT"},
        "context_hash": f"context-{identity_key}-{condition_key}",
        "quality_status": "passed",
        "period_trigger_baseline_json": (
            period_trigger_baseline_json() if period_baseline is None else period_baseline
        ),
    }


def snapshot_row(
    asset_kind: str,
    identity_key: str,
    *,
    quality_status: str = "passed",
    open_price: str = "10.00",
    close: str = "10.50",
    current_price: str | None = None,
    amount: str = "1000000",
) -> dict[str, object]:
    return {
        "snapshot_id": stable_int(identity_key + "snapshot"),
        "snapshot_run_id": SNAPSHOT_RUN_ID,
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "for_trade_date": "20260528",
        "trade_date": "20260528",
        "snapshot_time": "2026-05-28T09:30:00+08:00",
        "quality_status": quality_status,
        "current_price": current_price or close,
        "open": open_price,
        "close": close,
        "amount": amount,
        "source_adapter": "test",
        "raw_json": {},
    }


def period_trigger_baseline_json() -> dict[str, object]:
    return {
        "baseline_version": "N2-R4-period-trigger-baseline-v1",
        "baseline_source": "condition_basis",
        "periods": {
            period: {
                "baseline_ready": True,
                "period_key_current": f"current-{period}",
                "period_key_previous": f"previous-{period}",
                "current_open_seed": "11",
                "current_close_seed": "11",
                "current_amount_seed": "10",
                "current_trade_days_seed": 1,
                "previous_open": "10",
                "previous_close": "12",
                "previous_entity_high": "12",
                "previous_entity_low": "10",
                "previous_amount": "100",
                "previous_avg_amount": "100",
                "trigger_previous_entity_high": "10.2",
                "trigger_previous_entity_low": "10.2",
                "trigger_previous_amount_baseline": "100",
                "baseline_source_trade_date": "20260527",
                "amount_metric": "amount",
                "current_window_start": "20260528",
                "current_window_end": "20260528",
                "previous_window_start": "20260527",
                "previous_window_end": "20260527",
            }
            for period in ("Y", "Q", "M", "W", "D")
        },
    }


def guard_counts() -> dict[str, dict[str, object]]:
    return {
        table_name: {"exists": True, "row_count": 0, "status": "present"}
        for table_name in (
            "common_event_outbox",
            "common_event_inbox",
            "common_event_consumer_checkpoint",
            "common_trigger_state",
            "common_trigger_match",
        )
    }


def scoped_refs() -> dict[str, int]:
    return {
        "common_event_outbox": 0,
        "common_event_inbox": 0,
        "common_event_consumer_checkpoint": 0,
        "common_trigger_match": 0,
        "common_trigger_state": 0,
    }


def live2_scoped_refs(
    *,
    upstream_allowed: int = 0,
    upstream_disallowed: int = 0,
    upstream_inbox: int = 0,
    upstream_checkpoint: int = 0,
    target_outbox: int = 0,
) -> dict[str, int]:
    return {
        "upstream_input_outbox_allowed": upstream_allowed,
        "upstream_input_outbox_disallowed": upstream_disallowed,
        "upstream_input_inbox_refs": upstream_inbox,
        "upstream_input_checkpoint_refs": upstream_checkpoint,
        "target_output_outbox_refs": target_outbox,
        "target_inbox_refs": 0,
        "target_checkpoint_refs": 0,
        "target_trigger_match_refs": 0,
        "target_trigger_state_refs": 0,
    }


def stable_int(value: str) -> int:
    return int.from_bytes(value.encode("utf-8")[:6].ljust(6, b"0"), "big") % 1000000 + 1


if __name__ == "__main__":
    unittest.main()
