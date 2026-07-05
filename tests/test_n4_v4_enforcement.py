import unittest
import json
from datetime import datetime
from pathlib import Path

from ashare_v3.trigger.v4_enforcement import (
    V4EnforcementBlocked,
    assert_v4_trigger_matched_plan,
)
from ashare_v3.trigger.standard_trigger_execute import build_execute_event_envelope


def _valid_plan() -> dict:
    return {
        "output_event_type": "TriggerMatched",
        "source_event_id": "evt_n3_source",
        "source_event_type": "MarketSnapshotUpdated",
        "signal_type": "B_BUY",
        "runtime_signal_type": "B_BUY",
        "condition_signal_type": "BUY",
        "condition_key": "BUY:D",
        "original_condition_key": "BUY:D",
        "direction": "buy",
        "asset_kind": "stock",
        "identity_key": "stock:SH:600000",
        "trigger_price": "10.50",
        "trigger_kind": "trigger",
        "trigger_time": "2026-06-05T14:30:00+08:00",
        "event_time": "2026-06-05T14:30:00+08:00",
        "trigger_period": "D",
        "trigger_bucket": "trading_day",
        "requested_periods": ["D"],
        "triggered_periods": ["D"],
        "all_trigger_periods": ["D"],
        "primary_trigger_period": "D",
        "triggered_period_details": [
            {
                "period": "D",
                "classification": "triggered",
                "trigger_price": "10.50",
                "baseline_source": "trigger_baseline",
            }
        ],
        "n5_entry_allowed": True,
        "trigger_live": True,
        "current_status": "matched",
        "data_quality_status": "passed",
        "match_basis": "realtime_snapshot",
        "price_source": "n3_realtime_snapshot",
        "baseline_source": "trigger_baseline",
        "trigger_mark_candidate": "normal",
        "projection_30m_required": False,
        "projection_30m_flag": False,
        "projection_30m_type": "none",
        "projection_period": None,
        "projection_30m_volume_up_flag": False,
        "projection_30m_shrink_down_flag": False,
        "snapshot_trace": {
            "snapshot_run_id": "snapshot_run",
            "snapshot_id": 1,
            "snapshot_time": "2026-06-05T14:30:00+08:00",
            "source_confirmed_time": "2026-06-05T14:30:00+08:00",
            "current_price": "10.50",
            "quality_status": "passed",
        },
    }


def _valid_hint_plan(condition_key: str = "BUY_HINT") -> dict:
    direction = "buy" if condition_key == "BUY_HINT" else "sell"
    signal_type = "B_BUY" if direction == "buy" else "S_SELL"
    trigger_mark_candidate = "30m_volume" if direction == "buy" else "30m_shrink"
    projection_30m_type = "volume_up" if direction == "buy" else "shrink_down"
    return {
        **_valid_plan(),
        "signal_type": signal_type,
        "runtime_signal_type": signal_type,
        "condition_signal_type": condition_key,
        "condition_key": condition_key,
        "original_condition_key": condition_key,
        "direction": direction,
        "trigger_kind": "hint",
        "trigger_period": "30m",
        "requested_periods": [],
        "triggered_periods": [],
        "all_trigger_periods": [],
        "primary_trigger_period": None,
        "triggered_period_details": [],
        "match_basis": "intraday_projection",
        "price_source": "n3_realtime_projection",
        "trigger_mark_candidate": trigger_mark_candidate,
        "projection_period": "30m",
        "projection_30m_required": True,
        "projection_30m_flag": True,
        "projection_30m_type": projection_30m_type,
        "projection_30m_volume_up_flag": direction == "buy",
        "projection_30m_shrink_down_flag": direction == "sell",
        "snapshot_trace": {},
        "projection_trace": {
            "projection_id": 101,
            "trigger_price": "10.50",
            "trigger_time": "2026-06-05T14:30:00+08:00",
            "source_confirmed_time": "2026-06-05T14:30:00+08:00",
            "closed_label_used": "2026-06-05T14:30:00+08:00",
            "quality_status": "passed",
        },
    }


def _valid_full_plan(condition_key: str = "BUY:FULL") -> dict:
    direction = "buy" if condition_key == "BUY:FULL" else "sell"
    signal_type = "B_BUY" if direction == "buy" else "S_SELL"
    return {
        **_valid_plan(),
        "signal_type": signal_type,
        "runtime_signal_type": signal_type,
        "condition_signal_type": condition_key,
        "condition_key": condition_key,
        "original_condition_key": condition_key,
        "direction": direction,
        "trigger_kind": "trigger",
        "trigger_period": "D",
        "requested_periods": ["D"],
        "triggered_periods": ["D"],
        "all_trigger_periods": ["D"],
        "primary_trigger_period": "D",
        "triggered_period_details": [
            {
                "period": "D",
                "classification": "triggered",
                "trigger_price": "10.50",
                "baseline_source": "trigger_baseline",
            }
        ],
        "trigger_mark_candidate": "normal",
        "projection_30m_required": False,
        "projection_30m_flag": False,
        "projection_30m_type": "none",
        "projection_period": None,
        "projection_30m_volume_up_flag": False,
        "projection_30m_shrink_down_flag": False,
    }


class N4V4EnforcementTests(unittest.TestCase):
    def test_valid_trigger_matched_plan_passes(self) -> None:
        assert_v4_trigger_matched_plan(
            _valid_plan(),
            created_at=datetime.fromisoformat("2026-06-05T14:31:00+08:00"),
        )

    def test_missing_trigger_price_blocks(self) -> None:
        plan = _valid_plan()
        plan.pop("trigger_price")

        with self.assertRaisesRegex(V4EnforcementBlocked, "trigger_price"):
            assert_v4_trigger_matched_plan(
                plan,
                created_at=datetime.fromisoformat("2026-06-05T14:31:00+08:00"),
            )

    def test_missing_event_time_blocks(self) -> None:
        plan = _valid_plan()
        plan.pop("event_time")

        with self.assertRaisesRegex(V4EnforcementBlocked, "missing_event_time"):
            assert_v4_trigger_matched_plan(
                plan,
                created_at=datetime.fromisoformat("2026-06-05T14:31:00+08:00"),
            )

    def test_future_event_time_blocks(self) -> None:
        plan = _valid_plan()
        plan["trigger_time"] = "2026-06-05T15:00:00+08:00"
        plan["event_time"] = "2026-06-05T15:00:00+08:00"
        plan["snapshot_trace"]["snapshot_time"] = "2026-06-05T15:00:00+08:00"
        plan["snapshot_trace"]["source_confirmed_time"] = "2026-06-05T15:00:00+08:00"

        with self.assertRaisesRegex(V4EnforcementBlocked, "event_time_after_created_at"):
            assert_v4_trigger_matched_plan(
                plan,
                created_at=datetime.fromisoformat("2026-06-05T14:31:00+08:00"),
            )

    def test_price_must_have_reviewed_snapshot_source(self) -> None:
        plan = _valid_plan()
        plan["snapshot_trace"].pop("current_price")

        with self.assertRaisesRegex(V4EnforcementBlocked, "trigger_price_source_missing"):
            assert_v4_trigger_matched_plan(
                plan,
                created_at=datetime.fromisoformat("2026-06-05T14:31:00+08:00"),
            )

    def test_trigger_time_after_source_confirmed_time_blocks(self) -> None:
        plan = _valid_plan()
        plan["trigger_time"] = "2026-06-05T14:45:00+08:00"
        plan["snapshot_trace"]["snapshot_time"] = "2026-06-05T14:45:00+08:00"
        plan["snapshot_trace"]["source_confirmed_time"] = "2026-06-05T14:30:00+08:00"

        with self.assertRaisesRegex(V4EnforcementBlocked, "trigger_time_after_source_confirmed_time"):
            assert_v4_trigger_matched_plan(
                plan,
                created_at=datetime.fromisoformat("2026-06-05T14:50:00+08:00"),
            )

    def test_projection_time_after_approved_closed_label_blocks(self) -> None:
        plan = _valid_plan()
        plan.update(
            {
                "match_basis": "intraday_projection",
                "trigger_mark_candidate": "30m_volume",
                "projection_30m_type": "volume_up",
                "trigger_time": "2026-06-05T10:45:00+08:00",
                "projection_trace": {
                    "approved_projection_closed_label_used": "2026-06-05T10:30:00+08:00",
                    "source_confirmed_time": "2026-06-05T10:45:00+08:00",
                },
            }
        )

        with self.assertRaisesRegex(V4EnforcementBlocked, "projection_trigger_time_after_closed_label"):
            assert_v4_trigger_matched_plan(
                plan,
                created_at=datetime.fromisoformat("2026-06-05T10:50:00+08:00"),
            )

    def test_buy_full_d_trigger_matched_payload_passes(self) -> None:
        assert_v4_trigger_matched_plan(
            _valid_full_plan("BUY:FULL"),
            created_at=datetime.fromisoformat("2026-06-05T14:31:00+08:00"),
        )

    def test_sell_full_d_trigger_matched_payload_passes(self) -> None:
        assert_v4_trigger_matched_plan(
            _valid_full_plan("SELL:FULL"),
            created_at=datetime.fromisoformat("2026-06-05T14:31:00+08:00"),
        )

    def test_full_condition_keys_must_match_n2_context(self) -> None:
        plan = _valid_full_plan("BUY:FULL")
        plan["original_condition_key"] = "BUY:D"

        with self.assertRaisesRegex(V4EnforcementBlocked, "full_condition_key_mismatch"):
            assert_v4_trigger_matched_plan(
                plan,
                created_at=datetime.fromisoformat("2026-06-05T14:31:00+08:00"),
            )

    def test_full_trigger_period_must_be_d(self) -> None:
        plan = _valid_full_plan("BUY:FULL")
        plan["trigger_period"] = "30m"

        with self.assertRaisesRegex(V4EnforcementBlocked, "full_trigger_period_must_be_D"):
            assert_v4_trigger_matched_plan(
                plan,
                created_at=datetime.fromisoformat("2026-06-05T14:31:00+08:00"),
            )

    def test_full_formal_period_fields_must_be_exactly_d(self) -> None:
        for field in ("primary_trigger_period", "triggered_periods", "all_trigger_periods"):
            with self.subTest(field=field):
                plan = _valid_full_plan("SELL:FULL")
                plan[field] = "30m" if field == "primary_trigger_period" else ["D", "30m"]

                with self.assertRaisesRegex(V4EnforcementBlocked, "full_.*must_be_D"):
                    assert_v4_trigger_matched_plan(
                        plan,
                        created_at=datetime.fromisoformat("2026-06-05T14:31:00+08:00"),
                    )

    def test_full_trigger_kind_must_not_be_hint(self) -> None:
        plan = _valid_full_plan("BUY:FULL")
        plan["trigger_kind"] = "hint"

        with self.assertRaisesRegex(V4EnforcementBlocked, "full_trigger_kind_must_be_trigger"):
            assert_v4_trigger_matched_plan(
                plan,
                created_at=datetime.fromisoformat("2026-06-05T14:31:00+08:00"),
            )

    def test_full_trigger_mark_candidate_must_be_normal(self) -> None:
        plan = _valid_full_plan("SELL:FULL")
        plan["trigger_mark_candidate"] = "30m_shrink"

        with self.assertRaisesRegex(V4EnforcementBlocked, "full_trigger_mark_candidate_must_be_normal"):
            assert_v4_trigger_matched_plan(
                plan,
                created_at=datetime.fromisoformat("2026-06-05T14:31:00+08:00"),
            )

    def test_hint_cannot_be_runtime_signal_type(self) -> None:
        plan = _valid_plan()
        plan["signal_type"] = "BUY_HINT"
        plan["runtime_signal_type"] = "BUY_HINT"
        plan["condition_key"] = "BUY_HINT"
        plan["original_condition_key"] = "BUY_HINT"
        plan["condition_signal_type"] = "BUY_HINT"
        plan["trigger_kind"] = "hint"
        plan["trigger_mark_candidate"] = "30m_volume"
        plan["projection_30m_type"] = "volume_up"

        with self.assertRaisesRegex(V4EnforcementBlocked, "invalid_runtime_signal_type"):
            assert_v4_trigger_matched_plan(
                plan,
                created_at=datetime.fromisoformat("2026-06-05T14:31:00+08:00"),
            )

    def test_n5_entry_contract_blocks_non_live_match(self) -> None:
        plan = _valid_plan()
        plan["trigger_live"] = False

        with self.assertRaisesRegex(V4EnforcementBlocked, "invalid_n5_entry_contract"):
            assert_v4_trigger_matched_plan(
                plan,
                created_at=datetime.fromisoformat("2026-06-05T14:31:00+08:00"),
            )

    def test_ordinary_trigger_kind_blocks_trigger_period_30m(self) -> None:
        plan = _valid_plan()
        plan["trigger_period"] = "30m"

        with self.assertRaisesRegex(V4EnforcementBlocked, "invalid_trigger_period_30m"):
            assert_v4_trigger_matched_plan(
                plan,
                created_at=datetime.fromisoformat("2026-06-05T14:31:00+08:00"),
            )

    def test_30m_must_not_be_primary_or_triggered_period_for_trigger_matched(self) -> None:
        for field in ("primary_trigger_period", "triggered_periods", "all_trigger_periods"):
            with self.subTest(field=field):
                plan = _valid_plan()
                plan[field] = "30m" if field == "primary_trigger_period" else ["D", "30m"]

                with self.assertRaisesRegex(V4EnforcementBlocked, "invalid_.*30m"):
                    assert_v4_trigger_matched_plan(
                        plan,
                        created_at=datetime.fromisoformat("2026-06-05T14:31:00+08:00"),
                    )

    def test_buy_hint_allows_trigger_period_30m_with_empty_formal_periods(self) -> None:
        assert_v4_trigger_matched_plan(
            _valid_hint_plan("BUY_HINT"),
            created_at=datetime.fromisoformat("2026-06-05T14:31:00+08:00"),
        )

    def test_sell_hint_allows_trigger_period_30m_with_empty_formal_periods(self) -> None:
        assert_v4_trigger_matched_plan(
            _valid_hint_plan("SELL_HINT"),
            created_at=datetime.fromisoformat("2026-06-05T14:31:00+08:00"),
        )

    def test_hint_missing_trigger_price_blocks(self) -> None:
        plan = _valid_hint_plan("BUY_HINT")
        plan.pop("trigger_price")

        with self.assertRaisesRegex(V4EnforcementBlocked, "trigger_price"):
            assert_v4_trigger_matched_plan(
                plan,
                created_at=datetime.fromisoformat("2026-06-05T14:31:00+08:00"),
            )

    def test_hint_n5_entry_allowed_false_or_missing_blocks(self) -> None:
        for value in (False, None):
            with self.subTest(value=value):
                plan = _valid_hint_plan("BUY_HINT")
                if value is None:
                    plan.pop("n5_entry_allowed")
                else:
                    plan["n5_entry_allowed"] = value

                with self.assertRaisesRegex(V4EnforcementBlocked, "n5_entry_allowed|invalid_n5_entry_contract"):
                    assert_v4_trigger_matched_plan(
                        plan,
                        created_at=datetime.fromisoformat("2026-06-05T14:31:00+08:00"),
                    )

    def test_hint_blocks_30m_in_formal_period_sets(self) -> None:
        for field in ("primary_trigger_period", "triggered_periods", "all_trigger_periods"):
            with self.subTest(field=field):
                plan = _valid_hint_plan("SELL_HINT")
                plan[field] = "30m" if field == "primary_trigger_period" else ["30m"]

                with self.assertRaisesRegex(V4EnforcementBlocked, "invalid_.*30m"):
                    assert_v4_trigger_matched_plan(
                        plan,
                        created_at=datetime.fromisoformat("2026-06-05T14:31:00+08:00"),
                    )

    def test_projection_period_30m_is_allowed_when_formal_periods_remain_daily(self) -> None:
        plan = _valid_plan()
        plan.update(
            {
                "match_basis": "intraday_projection",
                "trigger_mark_candidate": "30m_volume",
                "projection_period": "30m",
                "projection_30m_flag": True,
                "projection_30m_type": "volume_up",
                "projection_30m_volume_up_flag": True,
                "projection_30m_shrink_down_flag": False,
                "projection_trace": {
                    "projection_id": 101,
                    "trigger_price": "10.50",
                    "trigger_time": "2026-06-05T14:30:00+08:00",
                    "source_confirmed_time": "2026-06-05T14:30:00+08:00",
                    "closed_label_used": "2026-06-05T14:30:00+08:00",
                    "quality_status": "passed",
                },
            }
        )

        assert_v4_trigger_matched_plan(
            plan,
            created_at=datetime.fromisoformat("2026-06-05T14:31:00+08:00"),
        )

    def test_missing_condition_signal_type_blocks(self) -> None:
        plan = _valid_plan()
        plan.pop("condition_signal_type")

        with self.assertRaisesRegex(V4EnforcementBlocked, "condition_signal_type"):
            assert_v4_trigger_matched_plan(
                plan,
                created_at=datetime.fromisoformat("2026-06-05T14:31:00+08:00"),
            )

    def test_condition_signal_type_must_match_condition_key_family(self) -> None:
        plan = _valid_plan()
        plan["condition_signal_type"] = "SELL"

        with self.assertRaisesRegex(V4EnforcementBlocked, "condition_signal_type"):
            assert_v4_trigger_matched_plan(
                plan,
                created_at=datetime.fromisoformat("2026-06-05T14:31:00+08:00"),
            )

    def test_runtime_signal_type_must_equal_signal_type(self) -> None:
        plan = _valid_plan()
        plan["runtime_signal_type"] = "S_SELL"

        with self.assertRaisesRegex(V4EnforcementBlocked, "runtime_signal_type_mismatch"):
            assert_v4_trigger_matched_plan(
                plan,
                created_at=datetime.fromisoformat("2026-06-05T14:31:00+08:00"),
            )

    def test_formal_matched_requires_triggered_period_details(self) -> None:
        plan = _valid_plan()
        plan["triggered_period_details"] = []

        with self.assertRaisesRegex(V4EnforcementBlocked, "blank_triggered_period_details"):
            assert_v4_trigger_matched_plan(
                plan,
                created_at=datetime.fromisoformat("2026-06-05T14:31:00+08:00"),
            )

    def test_hint_requires_empty_triggered_period_details(self) -> None:
        plan = _valid_hint_plan("BUY_HINT")
        plan["triggered_period_details"] = [{"period": "30m"}]

        with self.assertRaisesRegex(V4EnforcementBlocked, "hint_triggered_period_details_must_be_empty"):
            assert_v4_trigger_matched_plan(
                plan,
                created_at=datetime.fromisoformat("2026-06-05T14:31:00+08:00"),
            )

    def test_projection_30m_flags_must_match_projection_type(self) -> None:
        plan = _valid_hint_plan("SELL_HINT")
        plan["projection_30m_volume_up_flag"] = True

        with self.assertRaisesRegex(V4EnforcementBlocked, "projection_30m_flags"):
            assert_v4_trigger_matched_plan(
                plan,
                created_at=datetime.fromisoformat("2026-06-05T14:31:00+08:00"),
            )

    def test_n4_payload_must_not_emit_action_mark(self) -> None:
        plan = _valid_plan()
        plan["action_mark"] = "normal"

        with self.assertRaisesRegex(V4EnforcementBlocked, "action_mark_forbidden"):
            assert_v4_trigger_matched_plan(
                plan,
                created_at=datetime.fromisoformat("2026-06-05T14:31:00+08:00"),
            )

    def test_execute_event_payload_contains_v4_required_fields_and_uses_trigger_time(self) -> None:
        plan = _valid_plan()
        plan["snapshot_trace"]["snapshot_time"] = "2026-06-05T15:00:00+08:00"

        envelope = build_execute_event_envelope(
            execute_run_id="run",
            trigger_context_run={"run_id": "ctx", "for_trade_date": "20260605"},
            plan=plan,
            trigger_state_id=1,
            trigger_match_id=2,
            output_event_id="evt",
            dedup_key="dedup",
        )

        self.assertEqual(envelope.event_time, datetime.fromisoformat("2026-06-05T14:30:00+08:00"))
        for key in (
            "trigger_price",
            "trigger_kind",
            "triggered_periods",
            "all_trigger_periods",
            "primary_trigger_period",
            "n5_entry_allowed",
            "trigger_live",
            "current_status",
            "data_quality_status",
            "match_basis",
        ):
            self.assertIn(key, envelope.payload_json)
        self.assertEqual(envelope.payload_json["trigger_price"], "10.50")

    def test_enforcement_contract_artifacts_freeze_p0_guards_and_block_execute(self) -> None:
        contract = json.loads(Path("docs/N4_TRIGGER_RULE_V4_ENFORCEMENT_CONTRACT.json").read_text())
        preflight = json.loads(Path("docs/N4_TRIGGER_RULE_V4_ENFORCEMENT_PREFLIGHT.json").read_text())

        guard_codes = {guard["code"] for guard in contract["p0_guards"]}
        self.assertEqual(
            guard_codes,
            {
                "N4-V4-P0-001",
                "N4-V4-P0-002",
                "N4-V4-P0-003",
                "N4-V4-P0-004",
                "N4-V4-P0-005",
                "N4-V4-P0-006",
                "N4-V4-P0-007",
            },
        )
        self.assertEqual(contract["result"], "CONTRACT_PASS")
        self.assertEqual(preflight["result"], "PREFLIGHT_BLOCKED")
        self.assertFalse(preflight["execute_authorized"])


if __name__ == "__main__":
    unittest.main()
