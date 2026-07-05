import inspect
import unittest
from datetime import datetime, timezone

from ashare_v3.action.provisional_action_eligible import (
    PROVISIONAL_ACTIONELIGIBLE_ALLOWED_WRITE_TABLES,
    PROVISIONAL_ACTIONELIGIBLE_FORBIDDEN_WRITE_TABLES,
    ProvisionalActionEligibleBlocked,
    build_provisional_actioneligible_plan,
)


SOURCE_TRIGGER_RUN_ID = "trigger_provisional_b2_20260624_until_1352__realtime_projection_metric_20260624_until_1352"
ORDINARY_SOURCE_TRIGGER_RUN_ID = (
    "trigger_provisional_ordinary_20260624_until_1352__realtime_action_confirmation_metric_20260624_until_1352"
)
ACTION_RUN_ID = "action_provisional_eligible_20260624_until_1352_v1"
SOURCE_CONDITION_RUN_ID = "condition_layer_20260623_source_20260623_for_20260624_v1"
PROJECTION_RUN_ID = (
    "realtime_projection_metric_20260624_until_1352__realtime_daily_snapshot_20260624_until_1352__"
    "market_data_subscription_20260624_condition_layer_20260623_source_20260623_for_20260624_v1"
)


def trigger_run(status: str = "passed") -> dict[str, object]:
    return {
        "run_id": SOURCE_TRIGGER_RUN_ID,
        "status": status,
        "source_condition_run_id": SOURCE_CONDITION_RUN_ID,
        "for_trade_date": "20260624",
    }


def empty_target_counts() -> dict[str, int]:
    return {
        "common_action_run": 0,
        "common_action_quality_item": 0,
        "stock_action_fact": 0,
        "index_action_fact": 0,
        "board_action_fact": 0,
        "common_action_event": 0,
        "common_event_outbox": 0,
        "common_event_inbox": 0,
        "common_event_consumer_checkpoint": 0,
    }


def outbox_row(
    index: int,
    *,
    asset_kind: str = "stock",
    identity_key: str | None = None,
    signal_type: str = "B_BUY",
    condition_key: str = "BUY_HINT",
    event_type: str = "TriggerMatched",
    provisional: bool = True,
) -> dict[str, object]:
    resolved_identity = identity_key or f"{asset_kind}:TEST:{index:06d}"
    direction = "buy" if signal_type == "B_BUY" else "sell"
    trigger_mark_candidate = "30m_volume" if signal_type == "B_BUY" else "30m_shrink"
    projection_30m_type = "volume_up" if signal_type == "B_BUY" else "shrink_down"
    return {
        "outbox_id": index,
        "event_id": f"evt_n4_provisional_{index}",
        "event_type": event_type,
        "event_schema_version": "v1",
        "trade_date": "20260624",
        "asset_kind": asset_kind,
        "identity_key": resolved_identity,
        "event_time": datetime(2026, 6, 24, 13, 52, tzinfo=timezone.utc),
        "source_layer": "N4_trigger",
        "source_run_id": SOURCE_TRIGGER_RUN_ID,
        "dedup_key": f"n4-dedup-{index}",
        "partition_key": resolved_identity,
        "status": "pending",
        "payload_json": {
            "run_id": SOURCE_TRIGGER_RUN_ID,
            "provisional": provisional,
            "source_event_id": f"B2:{PROJECTION_RUN_ID}:{1000 + index}",
            "identity_key": resolved_identity,
            "asset_kind": asset_kind,
            "direction": direction,
            "condition_key": condition_key,
            "original_condition_key": condition_key,
            "signal_type": signal_type,
            "trigger_mark_candidate": trigger_mark_candidate,
            "trigger_period": "30m",
            "trigger_bucket": f"projection:{1000 + index}",
            "match_basis": "intraday_projection",
            "data_quality_status": "passed",
            "projection_run_id": PROJECTION_RUN_ID,
            "source_projection_run_id": PROJECTION_RUN_ID,
            "projection_id": 1000 + index,
            "projection_30m_flag": True,
            "projection_30m_type": projection_30m_type,
            "trigger_price": "10.00",
            "trigger_time": "2026-06-24T13:52:00+08:00",
            "trigger_live": True,
            "current_status": "matched",
            "trigger_state_id": 300000 + index,
            "trigger_match_id": 400000 + index,
            "source_condition_run_id": SOURCE_CONDITION_RUN_ID,
            "period_trigger_baseline_trace": {"source": "provisional_b2"},
        },
    }


def ordinary_outbox_row(
    index: int,
    *,
    condition_key: str,
    signal_type: str,
    trigger_type: str,
    is_closed_1m: bool = False,
) -> dict[str, object]:
    asset_kind = "stock"
    identity_key = f"stock:SH:{600000 + index:06d}"
    direction = "buy" if signal_type == "B_BUY" else "sell"
    selected_metric_id = 900000 + index
    return {
        "outbox_id": 100 + index,
        "event_id": f"evt_n4p_ordinary_{index}",
        "event_type": "TriggerMatched",
        "event_schema_version": "v1",
        "trade_date": "20260624",
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "event_time": datetime(2026, 6, 24, 13, 52, tzinfo=timezone.utc),
        "source_layer": "N4_trigger",
        "source_run_id": ORDINARY_SOURCE_TRIGGER_RUN_ID,
        "dedup_key": f"n4p-ordinary-dedup-{index}",
        "partition_key": identity_key,
        "status": "pending",
        "payload_json": {
            "run_id": ORDINARY_SOURCE_TRIGGER_RUN_ID,
            "provisional": True,
            "source_event_id": f"N3P:realtime_action_confirmation_metric_20260624_until_1352__asset_all:{selected_metric_id}",
            "source_event_type": "N3PRealtimeActionMetric",
            "identity_key": identity_key,
            "asset_kind": asset_kind,
            "display_name": identity_key,
            "direction": direction,
            "condition_key": condition_key,
            "original_condition_key": condition_key,
            "signal_type": signal_type,
            "trigger_type": trigger_type,
            "trigger_mark_candidate": "normal",
            "trigger_period": "13:52",
            "trigger_bucket": "n3p:2026-06-24T13:52:00+08:00",
            "match_basis": "n3p_realtime_action_confirmation_metric",
            "data_quality_status": "passed",
            "source_metric_kind": "realtime_action_confirmation_metric",
            "source_metric_run_id": "realtime_action_confirmation_metric_20260624_until_1352__asset_all",
            "selected_metric_id": selected_metric_id,
            "selected_metric_time": "2026-06-24T13:52:00+08:00",
            "metric_role": "trigger_proof",
            "proof_owner": "N3",
            "proof_consumer": "N4",
            "not_n5_final_proof": True,
            "source_trigger_proof_kind": "n3p_formal_amount_chain",
            "source_trigger_proof_run_id": "realtime_action_confirmation_metric_20260624_until_1352__asset_all",
            "source_trigger_proof_metric_id": selected_metric_id,
            "source_trigger_proof_time": "2026-06-24T13:52:00+08:00",
            "metric_time_label": "2026-06-24 13:52",
            "metric_minute_label": "13:52",
            "is_closed_1m": is_closed_1m,
            "trigger_live": True,
            "current_status": "matched",
            "trigger_context_run_id": "trigger_context_snapshot_20260624_condition_layer_20260623_source_20260623_for_20260624_v1",
            "trigger_state_id": 500000 + index,
            "trigger_match_id": 600000 + index,
            "source_condition_run_id": SOURCE_CONDITION_RUN_ID,
            "candidate_trigger_identity_key": f"candidate-key-{index}",
            "rule_eval_result": {"output_event_type": "TriggerMatched"},
            "rule_proof": {"rule_reused": "rule_v4_matcher"},
            "trace": {"source": "n4p_ordinary_test"},
        },
    }


def build_plan(rows: list[dict[str, object]], *, target_counts: dict[str, int] | None = None) -> dict[str, object]:
    return build_provisional_actioneligible_plan(
        source_trigger_run=trigger_run(),
        source_trigger_run_id=SOURCE_TRIGGER_RUN_ID,
        action_run_id=ACTION_RUN_ID,
        for_trade_date="20260624",
        consumer_name="n5_provisional_actioneligible_test",
        outbox_rows=rows,
        target_counts=target_counts or empty_target_counts(),
    )


def build_mixed_source_plan(
    rows: list[dict[str, object]],
    *,
    target_counts: dict[str, int] | None = None,
    allowed_source_trigger_run_ids: set[str] | None = None,
) -> dict[str, object]:
    return build_provisional_actioneligible_plan(
        source_trigger_run=trigger_run(),
        source_trigger_run_id=SOURCE_TRIGGER_RUN_ID,
        action_run_id=ACTION_RUN_ID,
        for_trade_date="20260624",
        consumer_name="n5_provisional_actioneligible_test",
        outbox_rows=rows,
        target_counts=target_counts or empty_target_counts(),
        allowed_source_trigger_run_ids=allowed_source_trigger_run_ids,
    )


class ProvisionalActionEligibleTest(unittest.TestCase):
    def test_ordinary_buy_sell_and_full_trigger_matched_rows_produce_actioneligible_only(self) -> None:
        rows = [
            ordinary_outbox_row(1, condition_key="BUY:D", signal_type="B_BUY", trigger_type="BUY"),
            ordinary_outbox_row(2, condition_key="SELL:D", signal_type="S_SELL", trigger_type="SELL"),
            ordinary_outbox_row(3, condition_key="BUY:FULL", signal_type="B_BUY", trigger_type="BUY:FULL"),
            ordinary_outbox_row(4, condition_key="SELL:FULL", signal_type="S_SELL", trigger_type="SELL:FULL"),
        ]

        plan = build_plan(rows)
        payloads = [row["payload_json"] for row in plan["writes"]["common_event_outbox"]]

        self.assertEqual(plan["eligible_count"], 4)
        self.assertEqual(plan["event_counts"], {"ActionEligible": 4})
        self.assertEqual({payload["event_type"] for payload in payloads}, {"ActionEligible"})
        self.assertEqual({payload["action_state"] for payload in payloads}, {"eligible"})
        self.assertNotIn("ActionExecuted", plan["event_counts"])
        self.assertNotIn("ActionBlocked", plan["event_counts"])
        self.assertNotIn("ActionSkipped", plan["event_counts"])
        self.assertEqual([payload["action_type"] for payload in payloads], ["buy", "sell", "buy", "sell"])

    def test_ordinary_payload_preserves_n3p_fields_and_unclosed_minute(self) -> None:
        plan = build_plan(
            [
                ordinary_outbox_row(
                    1,
                    condition_key="BUY:D",
                    signal_type="B_BUY",
                    trigger_type="BUY",
                    is_closed_1m=False,
                )
            ]
        )
        payload = plan["writes"]["common_event_outbox"][0]["payload_json"]
        trace = payload["trace_json"]

        self.assertTrue(payload["provisional"])
        self.assertTrue(payload["eligibility_only"])
        self.assertEqual(payload["action_confirmation_mode"], "eligibility_only")
        self.assertEqual(payload["source_metric_kind"], "realtime_action_confirmation_metric")
        self.assertEqual(payload["source_metric_run_id"], "realtime_action_confirmation_metric_20260624_until_1352__asset_all")
        self.assertEqual(payload["selected_metric_id"], 900001)
        self.assertEqual(payload["selected_metric_time"], "2026-06-24T13:52:00+08:00")
        self.assertEqual(payload["metric_role"], "trigger_proof")
        self.assertEqual(payload["proof_owner"], "N3")
        self.assertEqual(payload["proof_consumer"], "N4")
        self.assertTrue(payload["not_n5_final_proof"])
        self.assertEqual(payload["source_trigger_proof_kind"], "n3p_formal_amount_chain")
        self.assertEqual(payload["source_trigger_proof_metric_id"], 900001)
        self.assertEqual(payload["metric_time_label"], "2026-06-24 13:52")
        self.assertEqual(payload["metric_minute_label"], "13:52")
        self.assertFalse(payload["is_closed_1m"])
        self.assertEqual(payload["trigger_type"], "BUY")
        self.assertEqual(payload["trigger_kind"], "trigger")
        self.assertEqual(payload["trigger_period"], "D")
        self.assertEqual(payload["triggered_periods"], ["D"])
        self.assertEqual(payload["all_trigger_periods"], ["D"])
        self.assertEqual(payload["primary_trigger_period"], "D")
        self.assertEqual(payload["candidate_trigger_identity_key"], "candidate-key-1")
        self.assertEqual(payload["rule_proof"], {"rule_reused": "rule_v4_matcher"})
        self.assertEqual(trace["source_fact_kind"], "realtime_action_confirmation_metric")
        self.assertEqual(trace["metric_role"], "trigger_proof")
        self.assertTrue(trace["not_n5_final_proof"])
        self.assertFalse(trace["closed_minute_proof"]["is_closed_1m"])

    def test_ordinary_payload_has_stable_canonical_action_identity_key(self) -> None:
        plan = build_plan(
            [ordinary_outbox_row(1, condition_key="BUY:D", signal_type="B_BUY", trigger_type="BUY")]
        )
        fact = plan["writes"]["stock_action_fact"][0]
        payload = plan["writes"]["common_event_outbox"][0]["payload_json"]
        canonical_key = payload["canonical_action_identity_key"]

        self.assertEqual(canonical_key, fact["trace_json"]["canonical_action_identity_key"])
        self.assertIn("20260624", canonical_key)
        self.assertIn("stock", canonical_key)
        self.assertIn("stock:SH:600001", canonical_key)
        self.assertIn("B_BUY", canonical_key)
        self.assertIn("BUY:D", canonical_key)
        self.assertIn("buy", canonical_key)
        self.assertIn("2026-06-24T13:52:00+08:00", canonical_key)
        self.assertIn("none", canonical_key)

    def test_eighteen_provisional_trigger_matched_rows_produce_only_actioneligible(self) -> None:
        rows = [outbox_row(i) for i in range(1, 18)]
        rows.append(
            outbox_row(
                18,
                asset_kind="board",
                identity_key="board:TDX:881001",
                signal_type="S_SELL",
                condition_key="SELL_HINT",
            )
        )

        plan = build_plan(rows)
        writes = plan["writes"]

        self.assertEqual(plan["status"], "passed")
        self.assertEqual(plan["candidate_count"], 18)
        self.assertEqual(plan["eligible_count"], 18)
        self.assertEqual(plan["event_counts"], {"ActionEligible": 18})
        self.assertEqual(len(writes["common_action_run"]), 1)
        self.assertEqual(len(writes["common_action_event"]), 18)
        self.assertEqual(len(writes["common_event_outbox"]), 18)
        self.assertEqual(len(writes["stock_action_fact"]), 17)
        self.assertEqual(len(writes["board_action_fact"]), 1)
        self.assertEqual(len(writes["index_action_fact"]), 0)
        self.assertEqual({row["event_type"] for row in writes["common_event_outbox"]}, {"ActionEligible"})
        self.assertEqual({row["payload_json"]["action_state"] for row in writes["common_event_outbox"]}, {"eligible"})
        self.assertNotIn("ActionExecuted", plan["event_counts"])
        self.assertEqual(set(writes), PROVISIONAL_ACTIONELIGIBLE_ALLOWED_WRITE_TABLES)
        for table_name in PROVISIONAL_ACTIONELIGIBLE_FORBIDDEN_WRITE_TABLES:
            self.assertEqual(plan["forbidden_write_counts"][table_name], 0)

    def test_formal_metric_missing_does_not_block_provisional_eligible(self) -> None:
        plan = build_plan([outbox_row(1)])
        payload = plan["writes"]["common_event_outbox"][0]["payload_json"]

        self.assertEqual(payload["event_type"], "ActionEligible")
        self.assertEqual(payload["action_confirmation_mode"], "eligibility_only")
        self.assertIsNone(payload["source_action_confirmation_metric_id"])
        self.assertEqual(payload["confirmation_status"], "pending")

    def test_invalid_or_non_trigger_rows_are_noop_not_executed_or_blocked(self) -> None:
        plan = build_plan(
            [
                outbox_row(1, provisional=False),
                outbox_row(2, event_type="TriggerStateChanged"),
            ]
        )

        self.assertEqual(plan["eligible_count"], 0)
        self.assertEqual(plan["noop_count"], 2)
        self.assertEqual(plan["event_counts"], {})
        self.assertEqual(plan["writes"]["common_action_event"], [])
        self.assertEqual(plan["writes"]["common_event_outbox"], [])
        self.assertIn("not_provisional", plan["noop_reason_counts"])
        self.assertIn("unsupported_event_type", plan["noop_reason_counts"])

    def test_buy_and_sell_hint_map_to_business_action_type_in_payload(self) -> None:
        plan = build_plan(
            [
                outbox_row(1, signal_type="B_BUY", condition_key="BUY_HINT"),
                outbox_row(2, asset_kind="board", signal_type="S_SELL", condition_key="SELL_HINT"),
            ]
        )

        payloads = [row["payload_json"] for row in plan["writes"]["common_event_outbox"]]
        self.assertEqual(payloads[0]["action_type"], "buy")
        self.assertEqual(payloads[0]["fact_action_type"], "buy_candidate")
        self.assertEqual(payloads[1]["action_type"], "sell")
        self.assertEqual(payloads[1]["fact_action_type"], "sell_candidate")

    def test_hint_payload_sets_trigger_type_for_actionexecuted_confirmation(self) -> None:
        plan = build_plan(
            [
                outbox_row(1, signal_type="B_BUY", condition_key="BUY_HINT"),
                outbox_row(2, asset_kind="board", signal_type="S_SELL", condition_key="SELL_HINT"),
            ]
        )

        payloads = [row["payload_json"] for row in plan["writes"]["common_event_outbox"]]
        self.assertEqual(payloads[0]["trigger_type"], "BUY_HINT")
        self.assertEqual(payloads[1]["trigger_type"], "SELL_HINT")

    def test_mixed_ordinary_and_hint_candidates_preserve_per_candidate_source_trigger_run_id(self) -> None:
        plan = build_mixed_source_plan(
            [
                ordinary_outbox_row(1, condition_key="BUY:D", signal_type="B_BUY", trigger_type="BUY"),
                outbox_row(2, signal_type="B_BUY", condition_key="BUY_HINT"),
            ],
            allowed_source_trigger_run_ids={ORDINARY_SOURCE_TRIGGER_RUN_ID, SOURCE_TRIGGER_RUN_ID},
        )

        stock_facts = plan["writes"]["stock_action_fact"]
        self.assertEqual(stock_facts[0]["source_trigger_run_id"], ORDINARY_SOURCE_TRIGGER_RUN_ID)
        self.assertEqual(stock_facts[0]["source_payload_json"]["source_trigger_run_id"], ORDINARY_SOURCE_TRIGGER_RUN_ID)
        self.assertEqual(stock_facts[1]["source_trigger_run_id"], SOURCE_TRIGGER_RUN_ID)
        self.assertEqual(stock_facts[1]["source_payload_json"]["source_trigger_run_id"], SOURCE_TRIGGER_RUN_ID)
        self.assertEqual(stock_facts[1]["condition_key"], "BUY_HINT")
        self.assertEqual(stock_facts[1]["signal_type"], "B_BUY")

        payloads = [row["payload_json"] for row in plan["writes"]["common_event_outbox"]]
        self.assertEqual(payloads[0]["source_trigger_run_id"], ORDINARY_SOURCE_TRIGGER_RUN_ID)
        self.assertEqual(payloads[1]["source_trigger_run_id"], SOURCE_TRIGGER_RUN_ID)

    def test_missing_candidate_source_trigger_run_id_blocks_fail_closed(self) -> None:
        row = outbox_row(1)
        row["source_run_id"] = ""
        row["payload_json"]["run_id"] = ""

        with self.assertRaises(ProvisionalActionEligibleBlocked) as raised:
            build_mixed_source_plan([row], allowed_source_trigger_run_ids={SOURCE_TRIGGER_RUN_ID})

        self.assertIn("missing_candidate_source_trigger_run_id", str(raised.exception))

    def test_candidate_source_trigger_run_id_outside_allowed_set_blocks(self) -> None:
        with self.assertRaises(ProvisionalActionEligibleBlocked) as raised:
            build_mixed_source_plan(
                [ordinary_outbox_row(1, condition_key="BUY:D", signal_type="B_BUY", trigger_type="BUY")],
                allowed_source_trigger_run_ids={SOURCE_TRIGGER_RUN_ID},
            )

        self.assertIn("candidate_source_trigger_run_id_not_allowed", str(raised.exception))

    def test_action_key_and_dedup_key_include_projection_grain(self) -> None:
        plan = build_plan([outbox_row(7)])
        fact = plan["writes"]["stock_action_fact"][0]

        self.assertIn(ACTION_RUN_ID, fact["action_key"])
        self.assertIn("evt_n4_provisional_7", fact["action_key"])
        self.assertIn(PROJECTION_RUN_ID, fact["action_key"])
        self.assertIn("1007", fact["action_key"])
        self.assertIn("buy", fact["action_key"])
        self.assertIn(fact["action_key"], fact["dedup_key"])

    def test_target_exists_blocks_without_upsert_or_overwrite(self) -> None:
        with self.assertRaises(ProvisionalActionEligibleBlocked) as raised:
            build_plan([outbox_row(1)], target_counts={**empty_target_counts(), "common_action_run": 1})

        self.assertIn("target exists", str(raised.exception))

    def test_inbox_and_checkpoint_target_refs_block_and_are_not_hardcoded(self) -> None:
        for dirty_table in ("common_event_inbox", "common_event_consumer_checkpoint"):
            with self.subTest(dirty_table=dirty_table):
                with self.assertRaises(ProvisionalActionEligibleBlocked) as raised:
                    build_plan([outbox_row(1)], target_counts={**empty_target_counts(), dirty_table: 1})
                self.assertIn("BLOCKED_TARGET_NOT_EMPTY", str(raised.exception))

        import ashare_v3.action.provisional_action_eligible as provisional_action_eligible

        module_source = inspect.getsource(provisional_action_eligible)
        self.assertIn("FROM common_event_inbox", module_source)
        self.assertIn("FROM common_event_consumer_checkpoint", module_source)
        self.assertNotIn('counts["common_event_inbox"] = 0', module_source)
        self.assertNotIn('counts["common_event_consumer_checkpoint"] = 0', module_source)

    def test_module_does_not_use_formal_metric_join_inbox_checkpoint_or_downstream_paths(self) -> None:
        import ashare_v3.action.provisional_action_eligible as provisional_action_eligible

        module_source = inspect.getsource(provisional_action_eligible)

        self.assertNotIn("ActionExecuted", module_source)
        self.assertNotIn("ActionBlocked", module_source)
        self.assertNotIn("ActionSkipped", module_source)
        self.assertNotIn("resolve_action_confirmation_metrics_for_execute", module_source)
        self.assertNotIn("INSERT INTO common_event_inbox", module_source)
        self.assertNotIn("INSERT INTO common_event_consumer_checkpoint", module_source)
        self.assertNotIn("user_projection", module_source)
        self.assertNotIn("sim_projection", module_source)
        self.assertNotIn("real_trade_order", module_source)


if __name__ == "__main__":
    unittest.main()
