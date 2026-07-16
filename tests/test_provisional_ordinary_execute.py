import copy
import inspect
import unittest
from unittest.mock import patch

from ashare_v3.trigger.provisional_ordinary_execute import (
    N4P_ORDINARY_ALLOWED_WRITE_TABLES,
    N4P_ORDINARY_FORBIDDEN_WRITE_TABLES,
    N4POrdinaryExecuteBlocked,
    build_n4p_ordinary_trigger_run_id,
    build_ordinary_rollback_sql,
    build_provisional_ordinary_execute_plan,
    fetch_previous_ordinary_trigger_states,
    parse_n4p_ordinary_trigger_run_id,
    run_provisional_ordinary_once,
    select_previous_ordinary_trigger_states,
)
from ashare_v3.trigger.provisional_ordinary_matcher import build_provisional_ordinary_matcher_plans
from tests.test_provisional_ordinary_matcher import (
    N3P_RUN_ID,
    PRODUCTION_20260714_1322_FALSE_POSITIVE_CASES,
    PRODUCTION_20260714_1322_METRIC_RUN_ID,
    PRODUCTION_20260714_SOURCE_CONDITION_RUN_ID,
    SAME_DAY_CONTEXT_RUN_ID,
    formal_period_amount_proof_factory,
    n3p_metric_row,
    production_20260714_1322_negative_evidence_fixture,
    same_day_fail_closed_mutations,
)
from tests.test_trigger_projection_matcher import CONTEXT_RUN_ID, context_row


TRIGGER_RUN_ID = build_n4p_ordinary_trigger_run_id(for_trade_date="20260624", until_hhmm="1352")
SOURCE_CONDITION_RUN_ID = "condition_layer_20260623_source_20260623_for_20260624_v1"


def empty_target_counts() -> dict[str, int]:
    return {
        "common_trigger_run": 0,
        "common_trigger_state": 0,
        "common_trigger_match": 0,
        "common_event_outbox": 0,
        "common_event_inbox": 0,
        "checkpoint_refs": 0,
    }


def ordinary_plans(
    contexts: list[dict[str, object]],
    metrics: list[dict[str, object]],
    *,
    trigger_context_run_id: str = CONTEXT_RUN_ID,
) -> list[dict[str, object]]:
    return build_provisional_ordinary_matcher_plans(
        trigger_context_run_id=trigger_context_run_id,
        source_metric_run_id=N3P_RUN_ID,
        context_rows=contexts,
        metric_rows=metrics,
    )


def build_plan(
    plans: list[dict[str, object]],
    *,
    context_snapshot_row_count: int | None = None,
    target_counts: dict[str, int] | None = None,
    previous_trigger_states: list[dict[str, object]] | None = None,
    trigger_context_run_id: str = CONTEXT_RUN_ID,
    source_metric_run_id: str = N3P_RUN_ID,
    for_trade_date: str = "20260624",
    source_condition_run_id: str = SOURCE_CONDITION_RUN_ID,
    trigger_run_id: str = TRIGGER_RUN_ID,
) -> dict[str, object]:
    return build_provisional_ordinary_execute_plan(
        trigger_run_id=trigger_run_id,
        trigger_context_run={
            "run_id": trigger_context_run_id,
            "status": "passed",
            "for_trade_date": for_trade_date,
        },
        source_metric_run={"run_id": source_metric_run_id, "status": "passed"},
        trigger_context_run_id=trigger_context_run_id,
        source_metric_run_id=source_metric_run_id,
        for_trade_date=for_trade_date,
        source_condition_run_id=source_condition_run_id,
        dry_run_plans=plans,
        context_snapshot_row_count=context_snapshot_row_count if context_snapshot_row_count is not None else len(plans),
        target_counts=target_counts or empty_target_counts(),
        previous_trigger_states=previous_trigger_states or [],
    )


def previous_state_for_payload(payload: dict[str, object]) -> dict[str, object]:
    return {
        "run_id": "previous_ordinary_run",
        "source_condition_run_id": SOURCE_CONDITION_RUN_ID,
        "for_trade_date": "20260624",
        "asset_kind": payload["asset_kind"],
        "identity_key": payload["identity_key"],
        "direction": payload["direction"],
        "signal_type": payload["signal_type"],
        "condition_key": payload["condition_key"],
        "trigger_period": payload["trigger_period"],
        "current_status": "matched",
        "match_count": 1,
        "dedup_key": "previous-ordinary-key",
        "raw_json": {
            "trigger_type": payload["trigger_type"],
            "trigger_mark_candidate": payload["trigger_mark_candidate"],
            "primary_trigger_period": payload["primary_trigger_period"],
            "all_trigger_periods": payload["all_trigger_periods"],
            "trigger_price": payload["trigger_price"],
            "projection_30m_flag": False,
            "projection_30m_type": "none",
        },
    }


def with_production_contract_sources(plan: dict[str, object]) -> dict[str, object]:
    triggered_periods = list(plan.get("triggered_periods") or [])
    all_trigger_periods = list(plan.get("all_trigger_periods") or triggered_periods)
    primary_trigger_period = plan.get("primary_trigger_period")
    period_escalation_trace: dict[str, object] = {}
    plan.update(
        {
            "triggered_periods": triggered_periods,
            "all_trigger_periods": all_trigger_periods,
            "primary_trigger_period": primary_trigger_period,
            "prerequisite_periods": [],
            "period_escalation_trace": period_escalation_trace,
            "ordinary_period_escalation_policy_version": None,
            "ordinary_period_escalation_policy_hash": None,
            "rule_proof": {
                "rule_reused": "ashare_v3.trigger.rule_v4_matcher.evaluate_v4_plan",
                "trigger_rule_spec_version": "N4_TRIGGER_RULE_SPEC_v4",
                "trigger_rule_policy_hash": "fixture_non_same_day",
                "selected_metric": {},
                "period_evaluation_details": [],
                "triggered_period_details": [],
                "period_escalation_trace": period_escalation_trace,
                "ordinary_period_escalation_policy_version": None,
                "ordinary_period_escalation_policy_hash": None,
            },
            "rule_eval_result": {
                "trigger_rule_spec_version": "N4_TRIGGER_RULE_SPEC_v4",
                "trigger_rule_policy_hash": "fixture_non_same_day",
                "outcome_classification": (
                    "matched" if plan.get("output_event_type") == "TriggerMatched" else "no_op"
                ),
                "output_event_type": plan.get("output_event_type"),
                "trigger_live": plan.get("trigger_live"),
                "triggered_periods": triggered_periods,
                "all_trigger_periods": all_trigger_periods,
                "primary_trigger_period": primary_trigger_period,
                "prerequisite_periods": [],
                "period_escalation_trace": period_escalation_trace,
                "ordinary_period_escalation_policy_version": None,
                "ordinary_period_escalation_policy_hash": None,
                "pending_reasons": [],
                "quality_reasons": [],
                "blocked_reason": None,
            },
        }
    )
    return plan


def state_changed_candidate(
    *,
    condition_key: str = "BUY:Y,M,D",
    identity_key: str = "stock:SH:600100",
) -> dict[str, object]:
    return with_production_contract_sources({
        "plan_status": "no_op",
        "output_event_type": None,
        "asset_kind": "stock",
        "identity_key": identity_key,
        "direction": "buy",
        "signal_type": "B_BUY",
        "condition_key": condition_key,
        "trigger_type": "BUY",
        "source_metric_kind": "realtime_action_confirmation_metric",
        "source_metric_run_id": N3P_RUN_ID,
        "selected_metric_id": f"metric:{identity_key}",
        "selected_metric_time": "2026-06-24T11:29:00+08:00",
        "metric_minute_label": "11:29",
        "metric_ready": True,
        "trigger_live": False,
        "current_status": "inactive",
        "trigger_mark_candidate": "normal",
        "projection_30m_flag": False,
        "projection_30m_type": "none",
        "candidate_trigger_identity_key": f"candidate:{identity_key}:{condition_key}",
    })


def matched_lifecycle_candidate(
    *,
    condition_key: str = "BUY:M",
    trigger_type: str = "BUY",
    identity_key: str = "stock:SH:603061",
    trigger_price: object = 417.0,
    triggered_periods: list[str] | None = None,
    trigger_live: object | None = True,
) -> dict[str, object]:
    result = {
        "plan_status": "matched",
        "output_event_type": "TriggerMatched",
        "asset_kind": "stock",
        "identity_key": identity_key,
        "direction": "buy",
        "signal_type": "B_BUY",
        "condition_key": condition_key,
        "trigger_type": trigger_type,
        "source_metric_kind": "realtime_action_confirmation_metric",
        "source_metric_run_id": N3P_RUN_ID,
        "selected_metric_id": f"metric:{identity_key}",
        "selected_metric_time": "2026-06-24T14:47:00+08:00",
        "metric_minute_label": "14:47",
        "metric_ready": True,
        "current_status": "matched",
        "trigger_mark_candidate": "normal",
        "projection_30m_flag": False,
        "projection_30m_type": "none",
        "trigger_period": "M",
        "triggered_periods": triggered_periods or ["M"],
        "all_trigger_periods": triggered_periods or ["M"],
        "primary_trigger_period": "M",
        "trigger_price": trigger_price,
        "candidate_trigger_identity_key": f"candidate:{identity_key}:{condition_key}",
    }
    if trigger_live is not None:
        result["trigger_live"] = trigger_live
    return with_production_contract_sources(result)


def previous_matched_state(
    candidate: dict[str, object],
    *,
    trigger_period: str | None,
) -> dict[str, object]:
    raw_json: dict[str, object] = {
        "trigger_type": candidate["trigger_type"],
        "trigger_mark_candidate": "normal",
        "projection_30m_flag": False,
        "projection_30m_type": "none",
    }
    if trigger_period:
        raw_json.update(
            {
                "primary_trigger_period": trigger_period,
                "triggered_periods": [trigger_period],
                "all_trigger_periods": [trigger_period],
            }
        )
    return {
        "run_id": "previous_ordinary_run",
        "source_condition_run_id": SOURCE_CONDITION_RUN_ID,
        "for_trade_date": "20260624",
        "asset_kind": candidate["asset_kind"],
        "identity_key": candidate["identity_key"],
        "direction": candidate["direction"],
        "signal_type": candidate["signal_type"],
        "condition_key": candidate["condition_key"],
        "trigger_period": trigger_period or "",
        "current_status": "matched",
        "match_count": 1,
        "dedup_key": f"previous:{candidate['identity_key']}:{candidate['condition_key']}",
        "raw_json": raw_json,
    }


def previous_matched_lifecycle_state(
    candidate: dict[str, object],
    *,
    trigger_type: str = "BUY",
    trigger_price: object = 417.0,
    triggered_periods: list[str] | None = None,
    trigger_mark_candidate: str = "normal",
) -> dict[str, object]:
    periods = triggered_periods or ["M"]
    return {
        "run_id": "previous_ordinary_run",
        "source_condition_run_id": SOURCE_CONDITION_RUN_ID,
        "for_trade_date": "20260624",
        "asset_kind": candidate["asset_kind"],
        "identity_key": candidate["identity_key"],
        "direction": candidate["direction"],
        "signal_type": candidate["signal_type"],
        "condition_key": candidate["condition_key"],
        "trigger_period": "M",
        "current_status": "matched",
        "match_count": 1,
        "dedup_key": f"previous:{candidate['identity_key']}:{candidate['condition_key']}",
        "raw_json": {
            "trigger_type": trigger_type,
            "trigger_mark_candidate": trigger_mark_candidate,
            "projection_30m_flag": False,
            "projection_30m_type": "none",
            "trigger_period": "M",
            "primary_trigger_period": "M",
            "triggered_periods": periods,
            "all_trigger_periods": periods,
            "trigger_price": trigger_price,
        },
    }


class ProvisionalOrdinaryExecuteTest(unittest.TestCase):
    def test_20260714_1322_negative_evidence_cases_reach_match_and_outbox(self) -> None:
        contexts: list[dict[str, object]] = []
        metrics: list[dict[str, object]] = []
        expected_by_identity: dict[str, tuple[list[str], list[str], list[str]]] = {}
        for (
            asset_kind,
            identity_key,
            direction,
            condition_key,
            formal_periods,
            negative_statuses,
            expected_triggered,
            expected_all,
            expected_prerequisites,
        ) in PRODUCTION_20260714_1322_FALSE_POSITIVE_CASES:
            context, metric = production_20260714_1322_negative_evidence_fixture(
                asset_kind=asset_kind,
                identity_key=identity_key,
                direction=direction,
                condition_key=condition_key,
                formal_periods=formal_periods,
                negative_statuses=negative_statuses,
            )
            contexts.append(context)
            metrics.append(metric)
            expected_by_identity[identity_key] = (
                expected_triggered,
                expected_all,
                expected_prerequisites,
            )

        plans = build_provisional_ordinary_matcher_plans(
            trigger_context_run_id=SAME_DAY_CONTEXT_RUN_ID,
            source_metric_run_id=PRODUCTION_20260714_1322_METRIC_RUN_ID,
            context_rows=contexts,
            metric_rows=metrics,
        )
        production_trigger_run_id = build_n4p_ordinary_trigger_run_id(
            for_trade_date="20260714",
            until_hhmm="1322",
            source_metric_run_id=PRODUCTION_20260714_1322_METRIC_RUN_ID,
            rule_suffix="atomic_rule_v1",
        )
        execute_plan = build_plan(
            plans,
            context_snapshot_row_count=len(plans),
            trigger_context_run_id=SAME_DAY_CONTEXT_RUN_ID,
            source_metric_run_id=PRODUCTION_20260714_1322_METRIC_RUN_ID,
            for_trade_date="20260714",
            source_condition_run_id=PRODUCTION_20260714_SOURCE_CONDITION_RUN_ID,
            trigger_run_id=production_trigger_run_id,
        )

        self.assertEqual(len(plans), 13)
        self.assertEqual(execute_plan["matched_count"], 13)
        self.assertEqual(len(execute_plan["writes"]["common_trigger_match"]), 13)
        self.assertEqual(len(execute_plan["writes"]["common_event_outbox"]), 13)
        matches = {
            row["identity_key"]: row["raw_json"]
            for row in execute_plan["writes"]["common_trigger_match"]
        }
        outboxes = {
            row["payload_json"]["identity_key"]: row["payload_json"]
            for row in execute_plan["writes"]["common_event_outbox"]
        }
        for identity_key, (expected_triggered, expected_all, expected_prerequisites) in expected_by_identity.items():
            with self.subTest(identity_key=identity_key):
                for output in (matches[identity_key], outboxes[identity_key]):
                    self.assertEqual(output["triggered_periods"], expected_triggered)
                    self.assertEqual(output["all_trigger_periods"], expected_all)
                    self.assertEqual(output["primary_trigger_period"], expected_triggered[0])
                    self.assertEqual(output["prerequisite_periods"], expected_prerequisites)
                    self.assertEqual(
                        output["ordinary_period_escalation_policy_version"],
                        "N4-ordinary-period-escalation-v2",
                    )
                self.assertEqual(outboxes[identity_key]["event_type"], "TriggerMatched")
                self.assertTrue(outboxes[identity_key]["n5_entry_allowed"])

    def test_20260715_stock_600480_sell_q_contract_reaches_match_and_outbox(self) -> None:
        context, metric = production_20260714_1322_negative_evidence_fixture(
            asset_kind="stock",
            identity_key="stock:SH:600480",
            direction="sell",
            condition_key="SELL:Y,Q,M",
            formal_periods=("Q", "M"),
            negative_statuses={"Y": "not_ready"},
        )
        plans = build_provisional_ordinary_matcher_plans(
            trigger_context_run_id=SAME_DAY_CONTEXT_RUN_ID,
            source_metric_run_id=PRODUCTION_20260714_1322_METRIC_RUN_ID,
            context_rows=[context],
            metric_rows=[metric],
        )
        trigger_run_id = build_n4p_ordinary_trigger_run_id(
            for_trade_date="20260714",
            until_hhmm="1322",
            source_metric_run_id=PRODUCTION_20260714_1322_METRIC_RUN_ID,
            rule_suffix="atomic_rule_v1",
        )
        execute_plan = build_plan(
            plans,
            trigger_context_run_id=SAME_DAY_CONTEXT_RUN_ID,
            source_metric_run_id=PRODUCTION_20260714_1322_METRIC_RUN_ID,
            for_trade_date="20260714",
            source_condition_run_id=PRODUCTION_20260714_SOURCE_CONDITION_RUN_ID,
            trigger_run_id=trigger_run_id,
        )

        self.assertEqual(execute_plan["matched_count"], 1)
        match = execute_plan["writes"]["common_trigger_match"][0]["raw_json"]
        outbox = execute_plan["writes"]["common_event_outbox"][0]["payload_json"]
        for output in (match, outbox):
            self.assertEqual(output["triggered_periods"], ["Q"])
            self.assertEqual(output["all_trigger_periods"], ["Q", "M"])
            self.assertEqual(output["primary_trigger_period"], "Q")
            self.assertEqual(output["prerequisite_periods"], ["M"])
        self.assertEqual(outbox["event_type"], "TriggerMatched")
        self.assertTrue(outbox["n5_entry_allowed"])

    def test_20260715_1017_mixed_context_contract_reaches_match_raw_json_and_outbox(self) -> None:
        cases = (
            (
                "stock:SH:688321",
                "BUY:Y,Q,W",
                ("Y", "Q", "W"),
                ["Y", "W"],
                ["Y", "Q", "W"],
                "Y",
                ["Q", "D"],
                True,
            ),
            (
                "stock:SH:688336",
                "BUY:Q,M,W",
                ("Q", "M"),
                ["Q"],
                ["Q", "M"],
                "Q",
                ["M"],
                False,
            ),
        )
        for (
            identity_key,
            condition_key,
            formal_periods,
            expected_triggered,
            expected_all,
            expected_primary,
            expected_prerequisites,
            w_triggered,
        ) in cases:
            with self.subTest(identity_key=identity_key):
                context, metric = production_20260714_1322_negative_evidence_fixture(
                    asset_kind="stock",
                    identity_key=identity_key,
                    direction="buy",
                    condition_key=condition_key,
                    formal_periods=formal_periods,
                    negative_statuses={},
                )
                plans = build_provisional_ordinary_matcher_plans(
                    trigger_context_run_id=SAME_DAY_CONTEXT_RUN_ID,
                    source_metric_run_id=PRODUCTION_20260714_1322_METRIC_RUN_ID,
                    context_rows=[context],
                    metric_rows=[metric],
                )
                trigger_run_id = build_n4p_ordinary_trigger_run_id(
                    for_trade_date="20260714",
                    until_hhmm="1322",
                    source_metric_run_id=PRODUCTION_20260714_1322_METRIC_RUN_ID,
                    rule_suffix="atomic_rule_v1",
                )
                execute_plan = build_plan(
                    plans,
                    trigger_context_run_id=SAME_DAY_CONTEXT_RUN_ID,
                    source_metric_run_id=PRODUCTION_20260714_1322_METRIC_RUN_ID,
                    for_trade_date="20260714",
                    source_condition_run_id=PRODUCTION_20260714_SOURCE_CONDITION_RUN_ID,
                    trigger_run_id=trigger_run_id,
                )

                self.assertEqual(execute_plan["matched_count"], 1)
                match = execute_plan["writes"]["common_trigger_match"][0]["raw_json"]
                outbox = execute_plan["writes"]["common_event_outbox"][0]["payload_json"]
                for output in (match, outbox):
                    self.assertEqual(output["triggered_periods"], expected_triggered)
                    self.assertEqual(output["all_trigger_periods"], expected_all)
                    self.assertEqual(output["primary_trigger_period"], expected_primary)
                    self.assertEqual(output["prerequisite_periods"], expected_prerequisites)
                    traces = output["period_escalation_trace"]["periods"]
                    self.assertEqual(
                        output["period_escalation_trace"]["context_hash"],
                        traces["W"]["context_hash"],
                    )
                    self.assertEqual("W" in output["triggered_periods"], w_triggered)
                self.assertEqual(outbox["event_type"], "TriggerMatched")
                self.assertTrue(outbox["n5_entry_allowed"])

    def test_same_day_v2_matrix_reaches_lifecycle_match_raw_json_and_outbox_without_field_loss(self) -> None:
        assets = (
            ("stock", "stock:SH:600000"),
            ("index", "index:SH:000300"),
            ("board", "board:TDX:881001"),
        )
        period_chains = (
            (("W", "D"), ["W"], ["W", "D"], ["D"]),
            (("M", "W"), ["M"], ["M", "W"], ["W"]),
            (("Q", "M"), ["Q"], ["Q", "M"], ["M"]),
            (("Y", "Q"), ["Y"], ["Y", "Q"], ["Q"]),
            (("M", "W", "D"), ["M"], ["M", "W"], ["W"]),
            (("Y", "Q", "M", "W", "D"), ["Y"], ["Y", "Q"], ["Q"]),
            (("Y", "Q", "W", "D"), ["Y", "W"], ["Y", "Q", "W", "D"], ["Q", "D"]),
        )
        prerequisite_by_target = {"W": "D", "M": "W", "Q": "M", "Y": "Q"}

        for asset_kind, identity_key in assets:
            for direction in ("buy", "sell"):
                for formal_periods, expected_triggered, expected_all, expected_prerequisites in period_chains:
                    with self.subTest(
                        asset_kind=asset_kind,
                        direction=direction,
                        formal_periods=formal_periods,
                    ):
                        prefix = "BUY" if direction == "buy" else "SELL"
                        context = context_row(
                            identity_key,
                            direction,
                            f"{prefix}:{','.join(formal_periods)}",
                            [prefix],
                            asset_kind=asset_kind,
                            run_id=SAME_DAY_CONTEXT_RUN_ID,
                        )
                        amount_value = 150000.0 if asset_kind == "stock" and direction == "buy" else (
                            50.0 if asset_kind == "stock" else (150.0 if direction == "buy" else 50.0)
                        )
                        metric = n3p_metric_row(
                            asset_kind,
                            identity_key,
                            direction=direction,
                            formal_period_amount_proof=formal_period_amount_proof_factory(
                                periods=formal_periods,
                                amount_unit="yuan",
                                source_kind="N3_standard_period_metric",
                                amount_pass=True,
                                amount_value=amount_value,
                            ),
                        )
                        plans = ordinary_plans(
                            [context],
                            [metric],
                            trigger_context_run_id=SAME_DAY_CONTEXT_RUN_ID,
                        )

                        execute_plan = build_plan(
                            plans,
                            trigger_context_run_id=SAME_DAY_CONTEXT_RUN_ID,
                        )
                        repeat_plan = build_plan(
                            plans,
                            trigger_context_run_id=SAME_DAY_CONTEXT_RUN_ID,
                        )
                        match = execute_plan["writes"]["common_trigger_match"][0]
                        outbox = execute_plan["writes"]["common_event_outbox"][0]
                        payload = outbox["payload_json"]
                        raw_json = match["raw_json"]

                        for output in (raw_json, payload):
                            self.assertEqual(output["triggered_periods"], expected_triggered)
                            self.assertEqual(output["all_trigger_periods"], expected_all)
                            self.assertEqual(output["primary_trigger_period"], expected_triggered[0])
                            self.assertEqual(output["prerequisite_periods"], expected_prerequisites)
                            self.assertEqual(
                                output["ordinary_period_escalation_policy_version"],
                                "N4-ordinary-period-escalation-v2",
                            )
                            self.assertEqual(
                                output["ordinary_period_escalation_policy_hash"],
                                plans[0]["ordinary_period_escalation_policy_hash"],
                            )
                            expected_trace_targets = {
                                candidate
                                for candidate, required_period in prerequisite_by_target.items()
                                if candidate in formal_periods and required_period in formal_periods
                            }
                            self.assertEqual(
                                {
                                    period
                                    for period, trace in output["period_escalation_trace"]["periods"].items()
                                    if trace.get("evidence_source") == "current_same_day_formal_pass"
                                },
                                expected_trace_targets,
                            )
                        self.assertEqual(payload["event_type"], "TriggerMatched")
                        self.assertTrue(payload["n5_entry_allowed"])
                        self.assertEqual(execute_plan["matched_count"], 1)
                        self.assertEqual(
                            outbox["event_id"],
                            repeat_plan["writes"]["common_event_outbox"][0]["event_id"],
                        )
                        self.assertEqual(
                            outbox["dedup_key"],
                            repeat_plan["writes"]["common_event_outbox"][0]["dedup_key"],
                        )

    def test_20260714_same_day_v2_output_contract_fail_closed_cases(self) -> None:
        context = context_row(
            "stock:SH:600000",
            "buy",
            "BUY:W,D",
            ["BUY"],
            run_id=SAME_DAY_CONTEXT_RUN_ID,
        )
        metric = n3p_metric_row(
            "stock",
            "stock:SH:600000",
            direction="buy",
            formal_period_amount_proof=formal_period_amount_proof_factory(
                periods=("W", "D"),
                amount_unit="yuan",
                source_kind="N3_standard_period_metric",
                amount_pass=True,
                amount_value=150000.0,
            ),
        )
        valid = ordinary_plans(
            [context],
            [metric],
            trigger_context_run_id=SAME_DAY_CONTEXT_RUN_ID,
        )[0]
        invalid_plans: list[dict[str, object]] = []
        for field in (
            "all_trigger_periods",
            "primary_trigger_period",
            "prerequisite_periods",
            "period_escalation_trace",
            "ordinary_period_escalation_policy_version",
            "ordinary_period_escalation_policy_hash",
        ):
            invalid = copy.deepcopy(valid)
            invalid.pop(field)
            invalid_plans.append(invalid)
        wrong_order = copy.deepcopy(valid)
        wrong_order["all_trigger_periods"] = ["D", "W"]
        invalid_plans.append(wrong_order)
        wrong_prerequisite = copy.deepcopy(valid)
        wrong_prerequisite["prerequisite_periods"] = ["M"]
        invalid_plans.append(wrong_prerequisite)
        wrong_direction = copy.deepcopy(valid)
        wrong_direction["direction"] = "sell"
        invalid_plans.append(wrong_direction)
        condition_key_only = copy.deepcopy(valid)
        condition_key_only.pop("direction")
        condition_key_only.pop("signal_type")
        invalid_plans.append(condition_key_only)
        missing_formal_pair = copy.deepcopy(valid)
        missing_formal_pair["period_escalation_trace"]["periods"]["W"]["current_formal_pass_periods"] = ["W"]
        invalid_plans.append(missing_formal_pair)

        multi_context = context_row(
            "stock:SH:600000",
            "buy",
            "BUY:M,W,D",
            ["BUY"],
            run_id=SAME_DAY_CONTEXT_RUN_ID,
        )
        multi_metric = n3p_metric_row(
            "stock",
            "stock:SH:600000",
            direction="buy",
            formal_period_amount_proof=formal_period_amount_proof_factory(
                periods=("M", "W", "D"),
                amount_unit="yuan",
                source_kind="N3_standard_period_metric",
                amount_pass=True,
                amount_value=150000.0,
            ),
        )
        multi_valid = ordinary_plans(
            [multi_context],
            [multi_metric],
            trigger_context_run_id=SAME_DAY_CONTEXT_RUN_ID,
        )[0]
        disjoint_context = context_row(
            "stock:SH:600000",
            "buy",
            "BUY:Y,Q,W,D",
            ["BUY"],
            run_id=SAME_DAY_CONTEXT_RUN_ID,
        )
        disjoint_metric = n3p_metric_row(
            "stock",
            "stock:SH:600000",
            direction="buy",
            formal_period_amount_proof=formal_period_amount_proof_factory(
                periods=("Y", "Q", "W", "D"),
                amount_unit="yuan",
                source_kind="N3_standard_period_metric",
                amount_pass=True,
                amount_value=150000.0,
            ),
        )
        disjoint_valid = ordinary_plans(
            [disjoint_context],
            [disjoint_metric],
            trigger_context_run_id=SAME_DAY_CONTEXT_RUN_ID,
        )[0]
        invalid_plans.extend(same_day_fail_closed_mutations(multi_valid, disjoint_valid))

        for invalid in invalid_plans:
            with self.subTest(invalid=invalid):
                with self.assertRaises(N4POrdinaryExecuteBlocked):
                    build_plan(
                        [invalid],
                        trigger_context_run_id=SAME_DAY_CONTEXT_RUN_ID,
                    )

    def test_run_id_builder_and_parser_fail_closed_for_invalid_values(self) -> None:
        run_id = build_n4p_ordinary_trigger_run_id(for_trade_date="20260624", until_hhmm="1352")

        parsed = parse_n4p_ordinary_trigger_run_id(run_id)

        self.assertEqual(
            run_id,
            "trigger_provisional_ordinary_20260624_until_1352"
            "__realtime_action_confirmation_metric_20260624_until_1352__asset_all",
        )
        self.assertEqual(parsed["for_trade_date"], "20260624")
        self.assertEqual(parsed["until_hhmm"], "1352")
        self.assertEqual(parsed["asset_scope"], "asset_all")
        self.assertEqual(parsed["mode"], "provisional_ordinary")
        self.assertEqual(parsed["source_metric_kind"], "realtime_action_confirmation_metric")

        legacy = parse_n4p_ordinary_trigger_run_id(
            "trigger_provisional_ordinary_20260624_until_1352"
            "__realtime_action_confirmation_metric_20260624_until_1352"
        )
        self.assertEqual(legacy["asset_scope"], "legacy")
        with self.assertRaises(N4POrdinaryExecuteBlocked):
            parse_n4p_ordinary_trigger_run_id("trigger_provisional_b2_20260624_until_1352")
        with self.assertRaises(N4POrdinaryExecuteBlocked):
            parse_n4p_ordinary_trigger_run_id(
                "trigger_provisional_ordinary_20260624_until_1352"
                "__realtime_action_confirmation_metric_20260624_until_1352__asset_foo"
            )
        with self.assertRaises(N4POrdinaryExecuteBlocked):
            parse_n4p_ordinary_trigger_run_id(
                "trigger_provisional_ordinary_20260624_until_1352"
                "__realtime_action_confirmation_metric_20260625_until_1352__asset_all"
            )
        with self.assertRaises(N4POrdinaryExecuteBlocked):
            build_n4p_ordinary_trigger_run_id(for_trade_date="2026-06-24", until_hhmm="1352")

    def test_atomic_run_id_builder_and_parser_preserve_legacy_compatibility(self) -> None:
        run_id = build_n4p_ordinary_trigger_run_id(
            for_trade_date="20260625",
            until_hhmm="1129",
            asset_scope="asset_all",
            rule_suffix="atomic_rule_v1",
        )

        parsed = parse_n4p_ordinary_trigger_run_id(run_id)
        legacy = parse_n4p_ordinary_trigger_run_id(
            "trigger_provisional_ordinary_20260625_until_1129"
            "__realtime_action_confirmation_metric_20260625_until_1129__asset_all"
        )

        self.assertEqual(
            run_id,
            "trigger_provisional_ordinary_20260625_until_1129"
            "__realtime_action_confirmation_metric_20260625_until_1129"
            "__asset_all__atomic_rule_v1",
        )
        self.assertEqual(parsed["for_trade_date"], "20260625")
        self.assertEqual(parsed["until_hhmm"], "1129")
        self.assertEqual(parsed["asset_scope"], "asset_all")
        self.assertEqual(parsed["rule_suffix"], "atomic_rule_v1")
        self.assertEqual(legacy["asset_scope"], "asset_all")
        self.assertEqual(legacy["rule_suffix"], "")

    def test_amount_chain_v2_run_id_builder_and_parser_preserve_source_variant(self) -> None:
        run_id = build_n4p_ordinary_trigger_run_id(
            for_trade_date="20260626",
            until_hhmm="1447",
            asset_scope="asset_all",
            source_variant="live_current_1m_amount_chain_v2",
            rule_suffix="atomic_rule_v1",
        )
        derived_run_id = build_n4p_ordinary_trigger_run_id(
            for_trade_date="20260626",
            until_hhmm="1447",
            asset_scope="asset_all",
            source_metric_run_id=(
                "realtime_action_confirmation_metric_20260626_until_1447"
                "__asset_all__live_current_1m_amount_chain_v2"
                "__market_data_subscription_20260626_condition_layer_20260625_source_20260625_for_20260626_v1"
            ),
            rule_suffix="atomic_rule_v1",
        )

        parsed = parse_n4p_ordinary_trigger_run_id(run_id)

        self.assertEqual(
            run_id,
            "trigger_provisional_ordinary_20260626_until_1447"
            "__realtime_action_confirmation_metric_20260626_until_1447"
            "__asset_all__live_current_1m_amount_chain_v2__atomic_rule_v1",
        )
        self.assertEqual(derived_run_id, run_id)
        self.assertEqual(parsed["for_trade_date"], "20260626")
        self.assertEqual(parsed["until_hhmm"], "1447")
        self.assertEqual(parsed["source_metric_prefix"], "realtime_action_confirmation_metric")
        self.assertEqual(parsed["source_metric_date"], "20260626")
        self.assertEqual(parsed["source_metric_until_hhmm"], "1447")
        self.assertEqual(parsed["asset_scope"], "asset_all")
        self.assertEqual(parsed["source_variant"], "live_current_1m_amount_chain_v2")
        self.assertEqual(parsed["rule_suffix"], "atomic_rule_v1")

    def test_lifecycle_v2_run_id_builder_and_parser_preserve_source_variant(self) -> None:
        run_id = build_n4p_ordinary_trigger_run_id(
            for_trade_date="20260626",
            until_hhmm="1447",
            asset_scope="asset_all",
            source_variant="live_current_1m_amount_chain_v2_lifecycle_v2",
            rule_suffix="atomic_rule_v1",
        )
        derived_run_id = build_n4p_ordinary_trigger_run_id(
            for_trade_date="20260626",
            until_hhmm="1447",
            asset_scope="asset_all",
            source_metric_run_id=(
                "realtime_action_confirmation_metric_20260626_until_1447"
                "__asset_all__live_current_1m_amount_chain_v2_lifecycle_v2"
                "__market_data_subscription_20260626_condition_layer_20260625_source_20260625_for_20260626_v1"
            ),
            rule_suffix="atomic_rule_v1",
        )

        parsed = parse_n4p_ordinary_trigger_run_id(run_id)

        self.assertEqual(
            run_id,
            "trigger_provisional_ordinary_20260626_until_1447"
            "__realtime_action_confirmation_metric_20260626_until_1447"
            "__asset_all__live_current_1m_amount_chain_v2_lifecycle_v2__atomic_rule_v1",
        )
        self.assertEqual(derived_run_id, run_id)
        self.assertEqual(parsed["source_variant"], "live_current_1m_amount_chain_v2_lifecycle_v2")
        self.assertEqual(parsed["rule_suffix"], "atomic_rule_v1")

    def test_corrected_replay_run_id_builder_parser_and_rollback_preserve_source_variant(self) -> None:
        run_id = build_n4p_ordinary_trigger_run_id(
            for_trade_date="20260626",
            until_hhmm="1447",
            asset_scope="asset_all",
            source_variant="live_current_1m_amount_chain_v2_corrected_replay",
            rule_suffix="atomic_rule_v1",
        )
        derived_run_id = build_n4p_ordinary_trigger_run_id(
            for_trade_date="20260626",
            until_hhmm="1447",
            asset_scope="asset_all",
            source_metric_run_id=(
                "realtime_action_confirmation_metric_20260626_until_1447"
                "__asset_all__live_current_1m_amount_chain_v2_corrected_replay"
                "__market_data_subscription_20260626_condition_layer_20260625_source_20260625_for_20260626_v1"
            ),
            rule_suffix="atomic_rule_v1",
        )

        parsed = parse_n4p_ordinary_trigger_run_id(run_id)
        rollback_sql = build_ordinary_rollback_sql(run_id)

        self.assertEqual(
            run_id,
            "trigger_provisional_ordinary_20260626_until_1447"
            "__realtime_action_confirmation_metric_20260626_until_1447"
            "__asset_all__live_current_1m_amount_chain_v2_corrected_replay__atomic_rule_v1",
        )
        self.assertEqual(derived_run_id, run_id)
        self.assertEqual(parsed["source_variant"], "live_current_1m_amount_chain_v2_corrected_replay")
        self.assertEqual(parsed["rule_suffix"], "atomic_rule_v1")
        self.assertIn(run_id, rollback_sql)
        self.assertIn("common_event_inbox", rollback_sql)
        self.assertIn("common_event_consumer_checkpoint", rollback_sql)
        self.assertIn("common_action_run", rollback_sql)
        self.assertIn("user_projection_run", rollback_sql)
        self.assertIn("sim_projection", rollback_sql)
        self.assertIn("n6_virtual_order", rollback_sql)
        self.assertNotIn("DELETE FROM common_action", rollback_sql)
        self.assertNotIn("DELETE FROM user_", rollback_sql)
        self.assertNotIn("DELETE FROM sim_", rollback_sql)
        self.assertNotIn("DELETE FROM n6_", rollback_sql)

    def test_unified_payload_run_id_builder_parser_and_rollback_preserve_source_variant(self) -> None:
        run_id = build_n4p_ordinary_trigger_run_id(
            for_trade_date="20260626",
            until_hhmm="1447",
            asset_scope="asset_all",
            source_variant="live_current_1m_amount_chain_v2_unified_payload_v1",
            rule_suffix="atomic_rule_v1",
        )

        parsed = parse_n4p_ordinary_trigger_run_id(run_id)
        rollback_sql = build_ordinary_rollback_sql(run_id)

        self.assertEqual(
            run_id,
            "trigger_provisional_ordinary_20260626_until_1447"
            "__realtime_action_confirmation_metric_20260626_until_1447"
            "__asset_all__live_current_1m_amount_chain_v2_unified_payload_v1__atomic_rule_v1",
        )
        self.assertEqual(parsed["for_trade_date"], "20260626")
        self.assertEqual(parsed["until_hhmm"], "1447")
        self.assertEqual(parsed["asset_scope"], "asset_all")
        self.assertEqual(parsed["source_variant"], "live_current_1m_amount_chain_v2_unified_payload_v1")
        self.assertEqual(parsed["rule_suffix"], "atomic_rule_v1")
        self.assertIn(run_id, rollback_sql)
        self.assertIn("common_event_inbox", rollback_sql)
        self.assertIn("common_event_consumer_checkpoint", rollback_sql)
        self.assertIn("common_action_run", rollback_sql)
        self.assertIn("user_projection_run", rollback_sql)
        self.assertIn("sim_projection", rollback_sql)
        self.assertIn("n6_virtual_order", rollback_sql)
        self.assertNotIn("DELETE FROM common_action", rollback_sql)
        self.assertNotIn("DELETE FROM user_", rollback_sql)
        self.assertNotIn("DELETE FROM sim_", rollback_sql)
        self.assertNotIn("DELETE FROM n6_", rollback_sql)

    def test_asset_unit_fix_run_id_builder_parser_and_rollback_preserve_source_variant(self) -> None:
        source_variant = "live_current_1m_amount_chain_v2_asset_unit_fix_v1"
        source_metric_run_id = (
            "realtime_action_confirmation_metric_20260626_until_1447"
            "__asset_all__live_current_1m_amount_chain_v2_asset_unit_fix_v1"
            "__market_data_subscription_20260626_condition_layer_20260625_source_20260625_for_20260626_v1"
        )
        run_id = build_n4p_ordinary_trigger_run_id(
            for_trade_date="20260626",
            until_hhmm="1447",
            asset_scope="asset_all",
            source_variant=source_variant,
            rule_suffix="atomic_rule_v1",
        )
        derived_run_id = build_n4p_ordinary_trigger_run_id(
            for_trade_date="20260626",
            until_hhmm="1447",
            asset_scope="asset_all",
            source_metric_run_id=source_metric_run_id,
            rule_suffix="atomic_rule_v1",
        )

        parsed = parse_n4p_ordinary_trigger_run_id(run_id)
        rollback_sql = build_ordinary_rollback_sql(run_id)

        self.assertEqual(
            run_id,
            "trigger_provisional_ordinary_20260626_until_1447"
            "__realtime_action_confirmation_metric_20260626_until_1447"
            "__asset_all__live_current_1m_amount_chain_v2_asset_unit_fix_v1__atomic_rule_v1",
        )
        self.assertEqual(derived_run_id, run_id)
        self.assertEqual(parsed["source_variant"], source_variant)
        self.assertEqual(parsed["rule_suffix"], "atomic_rule_v1")
        self.assertIn(run_id, rollback_sql)
        self.assertIn("common_event_inbox", rollback_sql)
        self.assertIn("common_event_consumer_checkpoint", rollback_sql)
        self.assertIn("common_action_run", rollback_sql)
        self.assertIn("user_projection_run", rollback_sql)
        self.assertIn("sim_projection", rollback_sql)
        self.assertIn("n6_virtual_order", rollback_sql)
        self.assertNotIn("DELETE FROM common_action", rollback_sql)
        self.assertNotIn("DELETE FROM user_", rollback_sql)
        self.assertNotIn("DELETE FROM sim_", rollback_sql)
        self.assertNotIn("DELETE FROM n6_", rollback_sql)

    def test_b1_source_returned_asset_unit_fix_run_id_builder_parser_and_rollback_preserve_source_variant(self) -> None:
        source_variant = "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1"
        source_metric_run_id = (
            "realtime_action_confirmation_metric_20260629_until_1455"
            "__asset_all__b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1"
            "__market_data_subscription_20260629_condition_layer_20260626_source_20260626_for_20260629_v1"
        )
        expected_run_id = (
            "trigger_provisional_ordinary_20260629_until_1455"
            "__realtime_action_confirmation_metric_20260629_until_1455"
            "__asset_all__b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1__atomic_rule_v1"
        )

        run_id = build_n4p_ordinary_trigger_run_id(
            for_trade_date="20260629",
            until_hhmm="1455",
            asset_scope="asset_all",
            source_variant=source_variant,
            rule_suffix="atomic_rule_v1",
        )
        derived_run_id = build_n4p_ordinary_trigger_run_id(
            for_trade_date="20260629",
            until_hhmm="1455",
            asset_scope="asset_all",
            source_metric_run_id=source_metric_run_id,
            rule_suffix="atomic_rule_v1",
        )
        parsed = parse_n4p_ordinary_trigger_run_id(expected_run_id)
        rollback_sql = build_ordinary_rollback_sql(expected_run_id)

        self.assertEqual(run_id, expected_run_id)
        self.assertEqual(derived_run_id, expected_run_id)
        self.assertEqual(parsed["source_variant"], source_variant)
        self.assertEqual(parsed["rule_suffix"], "atomic_rule_v1")
        self.assertIn(expected_run_id, rollback_sql)
        self.assertIn("common_event_inbox", rollback_sql)
        self.assertIn("common_event_consumer_checkpoint", rollback_sql)
        self.assertIn("common_action_run", rollback_sql)
        self.assertIn("user_projection_run", rollback_sql)

    def test_current_period_avg_supersession_run_id_builder_parser_and_rollback_preserve_source_variant(self) -> None:
        source_variant = "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1"
        source_metric_run_id = (
            "realtime_action_confirmation_metric_20260629_until_1455"
            "__asset_all__b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1"
            "__market_data_subscription_20260629_condition_layer_20260626_source_20260626_for_20260629_v1"
        )
        expected_run_id = (
            "trigger_provisional_ordinary_20260629_until_1455"
            "__realtime_action_confirmation_metric_20260629_until_1455"
            "__asset_all__b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1"
            "__atomic_rule_v1"
        )

        run_id = build_n4p_ordinary_trigger_run_id(
            for_trade_date="20260629",
            until_hhmm="1455",
            asset_scope="asset_all",
            source_variant=source_variant,
            rule_suffix="atomic_rule_v1",
        )
        derived_run_id = build_n4p_ordinary_trigger_run_id(
            for_trade_date="20260629",
            until_hhmm="1455",
            asset_scope="asset_all",
            source_metric_run_id=source_metric_run_id,
            rule_suffix="atomic_rule_v1",
        )
        parsed = parse_n4p_ordinary_trigger_run_id(expected_run_id)
        rollback_sql = build_ordinary_rollback_sql(expected_run_id)

        self.assertEqual(run_id, expected_run_id)
        self.assertEqual(derived_run_id, expected_run_id)
        self.assertEqual(parsed["source_variant"], source_variant)
        self.assertEqual(parsed["rule_suffix"], "atomic_rule_v1")
        self.assertIn(expected_run_id, rollback_sql)
        self.assertIn("common_event_inbox", rollback_sql)
        self.assertIn("common_event_consumer_checkpoint", rollback_sql)
        self.assertIn("common_action_run", rollback_sql)
        self.assertIn("user_projection_run", rollback_sql)

    def test_period_rollover_guard_run_id_uses_n4_only_suffix_without_rewriting_n3p_source(self) -> None:
        source_variant = "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1"
        n4_rule_suffix = "period_rollover_guard_v1"
        source_metric_run_id = (
            "realtime_action_confirmation_metric_20260629_until_1455"
            "__asset_all__b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1"
            "__market_data_subscription_20260629_condition_layer_20260626_source_20260626_for_20260629_v1"
        )
        expected_run_id = (
            "trigger_provisional_ordinary_20260629_until_1455"
            "__realtime_action_confirmation_metric_20260629_until_1455"
            "__asset_all__b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1"
            "__atomic_rule_v1_period_rollover_guard_v1"
        )

        run_id = build_n4p_ordinary_trigger_run_id(
            for_trade_date="20260629",
            until_hhmm="1455",
            asset_scope="asset_all",
            source_variant=source_variant,
            rule_suffix="atomic_rule_v1",
            n4_rule_suffix=n4_rule_suffix,
        )
        derived_run_id = build_n4p_ordinary_trigger_run_id(
            for_trade_date="20260629",
            until_hhmm="1455",
            asset_scope="asset_all",
            source_metric_run_id=source_metric_run_id,
            rule_suffix="atomic_rule_v1",
            n4_rule_suffix=n4_rule_suffix,
        )
        parsed = parse_n4p_ordinary_trigger_run_id(expected_run_id)
        rollback_sql = build_ordinary_rollback_sql(expected_run_id)

        self.assertEqual(run_id, expected_run_id)
        self.assertEqual(derived_run_id, expected_run_id)
        self.assertEqual(parsed["source_variant"], source_variant)
        self.assertEqual(parsed["rule_suffix"], "atomic_rule_v1_period_rollover_guard_v1")
        self.assertEqual(parsed["atomic_rule_suffix"], "atomic_rule_v1")
        self.assertEqual(parsed["n4_rule_suffix"], n4_rule_suffix)
        self.assertIn(expected_run_id, rollback_sql)
        self.assertIn("common_event_inbox", rollback_sql)
        self.assertIn("common_event_consumer_checkpoint", rollback_sql)
        self.assertIn("common_action_run", rollback_sql)
        self.assertIn("user_projection_run", rollback_sql)

    def test_atomic_run_id_parser_fails_closed_for_invalid_suffix_pollution(self) -> None:
        with self.assertRaises(N4POrdinaryExecuteBlocked):
            parse_n4p_ordinary_trigger_run_id(
                "trigger_provisional_ordinary_20260625_until_1129"
                "__realtime_action_confirmation_metric_20260625_until_1129"
                "__asset_all__atomic_rule"
            )
        with self.assertRaises(N4POrdinaryExecuteBlocked):
            parse_n4p_ordinary_trigger_run_id(
                "trigger_provisional_ordinary_20260625_until_1129"
                "__realtime_action_confirmation_metric_20260625_until_1129"
                "__asset_all__atomic_rule_v1__extra"
            )
        with self.assertRaises(N4POrdinaryExecuteBlocked):
            build_n4p_ordinary_trigger_run_id(
                for_trade_date="20260625",
                until_hhmm="1129",
                asset_scope="asset_all",
                rule_suffix="atomic_rule_bad",
            )

    def test_amount_chain_v2_run_id_parser_fails_closed_for_unsafe_variants(self) -> None:
        with self.assertRaises(N4POrdinaryExecuteBlocked):
            parse_n4p_ordinary_trigger_run_id(
                "trigger_provisional_ordinary_20260626_until_1447"
                "__realtime_action_confirmation_metric_20260626_until_1447"
                "__asset_all__live_current_1m_amount_chain_v3__atomic_rule_v1"
            )
        with self.assertRaises(N4POrdinaryExecuteBlocked):
            parse_n4p_ordinary_trigger_run_id(
                "trigger_provisional_ordinary_20260626_until_1447"
                "__realtime_projection_metric_20260626_until_1447"
                "__asset_all__live_current_1m_amount_chain_v2__atomic_rule_v1"
            )
        with self.assertRaises(N4POrdinaryExecuteBlocked):
            parse_n4p_ordinary_trigger_run_id(
                "trigger_provisional_ordinary_20260626_until_1447"
                "__realtime_action_confirmation_metric_20260626_until_1447"
                "__asset_all__live_current_1m_amount_chain_v2"
            )
        with self.assertRaises(N4POrdinaryExecuteBlocked):
            parse_n4p_ordinary_trigger_run_id(
                "trigger_provisional_ordinary_20260626_until_1447"
                "__realtime_action_confirmation_metric_20260626_until_1447"
                "__live_current_1m_amount_chain_v2__atomic_rule_v1"
            )
        with self.assertRaises(N4POrdinaryExecuteBlocked):
            parse_n4p_ordinary_trigger_run_id(
                "trigger_provisional_ordinary_20260626_until_1447"
                "__realtime_action_confirmation_metric_20260626_until_1447"
                "__asset_all__live_current_1m_amount_chain_v2__atomic_rule_v2"
            )
        with self.assertRaises(N4POrdinaryExecuteBlocked):
            parse_n4p_ordinary_trigger_run_id(
                "trigger_provisional_ordinary_20260626_until_1447"
                "__realtime_action_confirmation_metric_20260626_until_1447"
                "__asset_all__live_current_1m_amount_chain_v2_unified_payload_v1"
            )
        with self.assertRaises(N4POrdinaryExecuteBlocked):
            parse_n4p_ordinary_trigger_run_id(
                "trigger_provisional_ordinary_20260626_until_1447"
                "__realtime_action_confirmation_metric_20260626_until_1447"
                "__asset_all__live_current_1m_amount_chain_v2_unified_payload_v2__atomic_rule_v1"
            )
        with self.assertRaises(N4POrdinaryExecuteBlocked):
            parse_n4p_ordinary_trigger_run_id(
                "trigger_provisional_ordinary_20260626_until_1447"
                "__realtime_action_confirmation_metric_20260626_until_1447"
                "__asset_all__live_current_1m_amount_chain_v2_asset_unit_fix_v2__atomic_rule_v1"
            )
        with self.assertRaises(N4POrdinaryExecuteBlocked):
            parse_n4p_ordinary_trigger_run_id(
                "trigger_provisional_ordinary_20260629_until_1455"
                "__realtime_action_confirmation_metric_20260629_until_1455"
                "__asset_all__b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v2__atomic_rule_v1"
            )
        with self.assertRaises(N4POrdinaryExecuteBlocked):
            parse_n4p_ordinary_trigger_run_id(
                "trigger_provisional_ordinary_20260629_until_1455"
                "__realtime_action_confirmation_metric_20260629_until_1455"
                "__asset_all__b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v2"
                "__atomic_rule_v1"
            )
        with self.assertRaises(N4POrdinaryExecuteBlocked):
            parse_n4p_ordinary_trigger_run_id(
                "trigger_provisional_ordinary_20260629_until_1455"
                "__realtime_action_confirmation_metric_20260629_until_1455"
                "__asset_all__b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v2_current_period_avg_v1"
                "__atomic_rule_v1"
            )
        with self.assertRaises(N4POrdinaryExecuteBlocked):
            parse_n4p_ordinary_trigger_run_id(
                "trigger_provisional_ordinary_20260629_until_1455"
                "__realtime_action_confirmation_metric_20260629_until_1455"
                "__asset_all__b1_source_returned_snapshot_amount_chain_v3_asset_unit_fix_v1_current_period_avg_v1"
                "__atomic_rule_v1"
            )
        with self.assertRaises(N4POrdinaryExecuteBlocked):
            parse_n4p_ordinary_trigger_run_id(
                "trigger_provisional_ordinary_20260629_until_1455"
                "__realtime_action_confirmation_metric_20260629_until_1455"
                "__asset_all__b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1"
                "__atomic_rule_v1_period_rollover_guard_v2"
            )
        with self.assertRaises(N4POrdinaryExecuteBlocked):
            parse_n4p_ordinary_trigger_run_id(
                "trigger_provisional_ordinary_20260629_until_1455"
                "__realtime_action_confirmation_metric_20260629_until_1455"
                "__asset_all__b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1_period_rollover_guard_v1"
                "__atomic_rule_v1"
            )
        with self.assertRaises(N4POrdinaryExecuteBlocked):
            build_n4p_ordinary_trigger_run_id(
                for_trade_date="20260629",
                until_hhmm="1455",
                asset_scope="asset_all",
                source_metric_run_id=(
                    "realtime_action_confirmation_metric_20260629_until_1455"
                    "__asset_all__b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1_period_rollover_guard_v1"
                    "__market_data_subscription_20260629_condition_layer_20260626_source_20260626_for_20260629_v1"
                ),
                rule_suffix="atomic_rule_v1",
            )
        with self.assertRaises(N4POrdinaryExecuteBlocked):
            parse_n4p_ordinary_trigger_run_id(
                "trigger_provisional_ordinary_20260626_until_1447"
                "__realtime_action_confirmation_metric_20260626_until_1447"
                "__asset_all__live_current_1m_amount_chain_v2_asset_unit_fix_v1"
            )
        with self.assertRaises(N4POrdinaryExecuteBlocked):
            parse_n4p_ordinary_trigger_run_id(
                "trigger_provisional_ordinary_20260626_until_1447"
                "__realtime_action_confirmation_metric_20260625_until_1447"
                "__asset_all__live_current_1m_amount_chain_v2__atomic_rule_v1"
            )
        with self.assertRaises(N4POrdinaryExecuteBlocked):
            build_n4p_ordinary_trigger_run_id(
                for_trade_date="20260626",
                until_hhmm="1447",
                asset_scope="asset_all",
                source_variant="live_current_1m_amount_chain_v3",
                rule_suffix="atomic_rule_v1",
            )
        with self.assertRaises(N4POrdinaryExecuteBlocked):
            build_n4p_ordinary_trigger_run_id(
                for_trade_date="20260626",
                until_hhmm="1447",
                asset_scope="asset_all",
                source_variant="live_current_1m_amount_chain_v2_unified_payload_v2",
                rule_suffix="atomic_rule_v1",
            )
        with self.assertRaises(N4POrdinaryExecuteBlocked):
            build_n4p_ordinary_trigger_run_id(
                for_trade_date="20260626",
                until_hhmm="1447",
                asset_scope="asset_all",
                source_variant="live_current_1m_amount_chain_v2_asset_unit_fix_v2",
                rule_suffix="atomic_rule_v1",
            )
        with self.assertRaises(N4POrdinaryExecuteBlocked):
            build_n4p_ordinary_trigger_run_id(
                for_trade_date="20260626",
                until_hhmm="1447",
                asset_scope="asset_all",
                source_metric_run_id="realtime_projection_metric_20260626_until_1447__asset_all",
                rule_suffix="atomic_rule_v1",
            )

    def test_clean_target_writes_run_state_match_outbox_only_for_ordinary_matches(self) -> None:
        plans = ordinary_plans(
            [
                context_row("stock:SH:600000", "buy", "BUY:D", ["BUY"]),
                context_row("stock:SH:600001", "sell", "SELL:D", ["SELL"]),
                context_row("stock:SH:600002", "buy", "BUY:FULL", ["BUY:FULL"]),
                context_row("stock:SH:600003", "sell", "SELL:FULL", ["SELL:FULL"]),
            ],
            [
                n3p_metric_row("stock", "stock:SH:600000", direction="buy"),
                n3p_metric_row("stock", "stock:SH:600001", direction="sell"),
                n3p_metric_row("stock", "stock:SH:600002", direction="buy"),
                n3p_metric_row("stock", "stock:SH:600003", direction="sell"),
            ],
        )

        execute_plan = build_plan(plans, context_snapshot_row_count=4)
        writes = execute_plan["writes"]

        self.assertEqual(execute_plan["status"], "passed")
        self.assertEqual(execute_plan["matched_count"], 4)
        self.assertEqual(len(writes["common_trigger_run"]), 1)
        self.assertEqual(writes["common_trigger_run"][0]["context_snapshot_row_count"], 4)
        self.assertIsInstance(writes["common_trigger_run"][0]["context_snapshot_row_count"], int)
        self.assertEqual(len(writes["common_trigger_quality_item"]), 1)
        self.assertEqual(len(writes["common_trigger_state"]), 4)
        self.assertEqual(len(writes["common_trigger_match"]), 4)
        self.assertEqual(len(writes["common_event_outbox"]), 4)
        self.assertEqual({row["source_event_type"] for row in writes["common_trigger_match"]}, {"MarketSnapshotUpdated"})
        self.assertEqual(set(writes), N4P_ORDINARY_ALLOWED_WRITE_TABLES)
        for table_name in N4P_ORDINARY_FORBIDDEN_WRITE_TABLES:
            self.assertEqual(execute_plan["forbidden_write_counts"][table_name], 0)
        self.assertEqual({row["event_type"] for row in writes["common_event_outbox"]}, {"TriggerMatched"})
        self.assertNotIn("TriggerPendingMarketData", {row["event_type"] for row in writes["common_event_outbox"]})
        self.assertNotIn("TriggerStateChanged", {row["event_type"] for row in writes["common_event_outbox"]})

    def test_run_report_includes_ordinary_matcher_phase_timing_evidence(self) -> None:
        dry_run_plan = matched_lifecycle_candidate()

        with (
            patch(
                "ashare_v3.trigger.provisional_ordinary_execute.fetch_ordinary_trigger_context_rows",
                return_value=(
                    [context_row("stock:SH:600000", "buy", "BUY:D", ["BUY"])],
                    {"run_id": CONTEXT_RUN_ID, "status": "passed", "for_trade_date": "20260624"},
                ),
            ),
            patch(
                "ashare_v3.trigger.provisional_ordinary_execute.fetch_ordinary_source_metric_rows",
                return_value=([n3p_metric_row("stock", "stock:SH:600000", direction="buy")], {"run_id": N3P_RUN_ID, "status": "passed"}),
            ),
            patch(
                "ashare_v3.trigger.provisional_ordinary_execute.build_provisional_ordinary_matcher_plans",
                return_value=[dry_run_plan],
            ),
            patch(
                "ashare_v3.trigger.provisional_ordinary_execute.fetch_target_counts",
                return_value=empty_target_counts(),
            ),
            patch(
                "ashare_v3.trigger.provisional_ordinary_execute.fetch_previous_ordinary_trigger_states",
                return_value=[],
            ),
        ):
            report = run_provisional_ordinary_once(
                dsn="postgresql://example.invalid/db",
                trigger_context_run_id=CONTEXT_RUN_ID,
                source_metric_run_id=N3P_RUN_ID,
                trigger_run_id=TRIGGER_RUN_ID,
                for_trade_date="20260624",
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                execute=False,
                user_confirmed=False,
            )

        timings = report["phase_timing_ms"]
        expected_phases = {
            "fetch_context_ms",
            "fetch_metric_ms",
            "build_matcher_plans_ms",
            "fetch_target_counts_ms",
            "fetch_previous_states_ms",
            "build_execute_plan_ms",
            "execute_transaction_ms",
            "write_artifacts_ms",
            "total_ms",
        }
        self.assertEqual(set(timings), expected_phases)
        for phase in expected_phases:
            self.assertIsInstance(timings[phase], float)
            self.assertGreaterEqual(timings[phase], 0.0)
        self.assertEqual(timings["execute_transaction_ms"], 0.0)

    def test_matched_unchanged_lifecycle_writes_no_duplicate_ordinary_trigger_matched(self) -> None:
        plans = ordinary_plans(
            [context_row("stock:SH:600000", "buy", "BUY:D", ["BUY"])],
            [n3p_metric_row("stock", "stock:SH:600000", direction="buy")],
        )
        initial = build_plan(plans)
        previous = previous_state_for_payload(initial["writes"]["common_event_outbox"][0]["payload_json"])

        execute_plan = build_plan(plans, previous_trigger_states=[previous])

        self.assertEqual(execute_plan["matched_count"], 0)
        self.assertEqual(execute_plan["state_changed_count"], 0)
        self.assertEqual(execute_plan["writes"]["common_trigger_state"], [])
        self.assertEqual(execute_plan["writes"]["common_trigger_match"], [])
        self.assertEqual(execute_plan["writes"]["common_event_outbox"], [])

    def test_matched_changed_lifecycle_writes_state_changed_without_ordinary_match(self) -> None:
        plans = ordinary_plans(
            [context_row("stock:SH:600000", "buy", "BUY:D", ["BUY"])],
            [n3p_metric_row("stock", "stock:SH:600000", direction="buy")],
        )
        initial = build_plan(plans)
        previous = previous_state_for_payload(initial["writes"]["common_event_outbox"][0]["payload_json"])
        previous["raw_json"]["trigger_mark_candidate"] = "legacy_mark"

        execute_plan = build_plan(plans, previous_trigger_states=[previous])

        self.assertEqual(execute_plan["matched_count"], 0)
        self.assertEqual(execute_plan["state_changed_count"], 1)
        self.assertEqual(len(execute_plan["writes"]["common_trigger_state"]), 1)
        self.assertEqual(execute_plan["writes"]["common_trigger_match"], [])
        self.assertEqual({row["event_type"] for row in execute_plan["writes"]["common_event_outbox"]}, {"TriggerStateChanged"})
        payload = execute_plan["writes"]["common_event_outbox"][0]["payload_json"]
        self.assertEqual(payload["current_status"], "matched")
        self.assertTrue(payload["trigger_live"])
        self.assertFalse(payload["n4_boundary"]["enters_n5"])

    def test_live_buy_full_is_cleared_when_current_ready_metric_no_longer_matches(self) -> None:
        current = matched_lifecycle_candidate(
            condition_key="BUY:FULL",
            trigger_type="BUY:FULL",
            identity_key="stock:SZ:000938",
            trigger_price=34.67,
        )
        current.update(
            {
                "signal_type": "B_BUY",
                "plan_status": "no_op",
                "output_event_type": None,
                "current_status": "no_op",
                "trigger_live": False,
                "projection_status": "ready",
                "projection_quality_status": "passed",
                "trace_status": "passed",
                "rule_eval_result": {
                    **current["rule_eval_result"],
                    "outcome_classification": "no_op",
                    "output_event_type": None,
                    "pending_reasons": [],
                    "quality_reasons": [],
                    "blocked_reason": None,
                },
            }
        )
        previous = previous_matched_lifecycle_state(current, trigger_type="BUY:FULL", trigger_price=34.67)
        previous["signal_type"] = "B_BUY"

        execute_plan = build_plan([current], previous_trigger_states=[previous])

        self.assertEqual(execute_plan["matched_count"], 0)
        self.assertEqual(execute_plan["state_changed_count"], 1)
        self.assertEqual(execute_plan["writes"]["common_trigger_match"], [])
        self.assertEqual(len(execute_plan["writes"]["common_trigger_state"]), 1)
        self.assertEqual(execute_plan["writes"]["common_trigger_state"][0]["current_status"], "inactive")
        self.assertEqual({row["event_type"] for row in execute_plan["writes"]["common_event_outbox"]}, {"TriggerStateChanged"})
        payload = execute_plan["writes"]["common_event_outbox"][0]["payload_json"]
        self.assertEqual(payload["current_status"], "inactive")
        self.assertFalse(payload["trigger_live"])
        self.assertFalse(payload["n4_boundary"]["enters_n5"])

    def test_live_state_is_kept_when_current_metric_is_not_ready(self) -> None:
        current = matched_lifecycle_candidate(condition_key="BUY:FULL", trigger_type="BUY:FULL")
        current.update(
            {
                "plan_status": "no_op",
                "output_event_type": "TriggerPendingMarketData",
                "current_status": "pending_market_data",
                "trigger_live": False,
                "projection_status": "pending",
                "projection_quality_status": "pending",
                "trace_status": "pending",
                "metric_ready": False,
                "rule_eval_result": {
                    **current["rule_eval_result"],
                    "outcome_classification": "pending",
                    "output_event_type": "TriggerPendingMarketData",
                    "pending_reasons": ["missing_projection"],
                    "quality_reasons": [],
                    "blocked_reason": None,
                },
            }
        )
        previous = previous_matched_lifecycle_state(current, trigger_type="BUY:FULL")

        execute_plan = build_plan([current], previous_trigger_states=[previous])

        self.assertEqual(execute_plan["matched_count"], 0)
        self.assertEqual(execute_plan["state_changed_count"], 0)
        self.assertEqual(execute_plan["writes"]["common_trigger_state"], [])
        self.assertEqual(execute_plan["writes"]["common_trigger_match"], [])
        self.assertEqual(execute_plan["writes"]["common_event_outbox"], [])

    def test_matched_changed_with_missing_live_defaults_to_live_true(self) -> None:
        current = matched_lifecycle_candidate(trigger_live=False)
        previous = previous_matched_lifecycle_state(current, trigger_mark_candidate="legacy_mark")

        execute_plan = build_plan([current], previous_trigger_states=[previous])
        payload = execute_plan["writes"]["common_event_outbox"][0]["payload_json"]

        self.assertEqual(execute_plan["matched_count"], 0)
        self.assertEqual(execute_plan["state_changed_count"], 1)
        self.assertEqual(execute_plan["writes"]["common_trigger_match"], [])
        self.assertEqual(payload["event_type"], "TriggerStateChanged")
        self.assertEqual(payload["current_status"], "matched")
        self.assertTrue(payload["trigger_live"])
        self.assertFalse(payload["n4_boundary"]["enters_n5"])

    def test_603061_equivalent_buy_m_replay_is_noop(self) -> None:
        current = matched_lifecycle_candidate(trigger_type="BUY:M", trigger_live=False)
        previous = previous_matched_lifecycle_state(current, trigger_type="BUY")

        execute_plan = build_plan([current], previous_trigger_states=[previous])

        self.assertEqual(execute_plan["matched_count"], 0)
        self.assertEqual(execute_plan["state_changed_count"], 0)
        self.assertEqual(execute_plan["writes"]["common_trigger_state"], [])
        self.assertEqual(execute_plan["writes"]["common_trigger_match"], [])
        self.assertEqual(execute_plan["writes"]["common_event_outbox"], [])

    def test_603061_equivalent_buy_m_replay_uses_pre_lifecycle_trigger_price_enrichment(self) -> None:
        current = matched_lifecycle_candidate(trigger_type="BUY:M", trigger_price=None, trigger_live=False)
        current["rule_proof"]["period_evaluation_details"] = [
            {"period": "M", "current_price_or_close": 417.0},
        ]
        previous = previous_matched_lifecycle_state(current, trigger_type="BUY", trigger_price=417.0)

        execute_plan = build_plan([current], previous_trigger_states=[previous])

        self.assertEqual(execute_plan["matched_count"], 0)
        self.assertEqual(execute_plan["state_changed_count"], 0)
        self.assertEqual(execute_plan["writes"]["common_trigger_state"], [])
        self.assertEqual(execute_plan["writes"]["common_trigger_match"], [])
        self.assertEqual(execute_plan["writes"]["common_event_outbox"], [])

    def test_trigger_price_only_material_change_does_not_emit_state_changed(self) -> None:
        current = matched_lifecycle_candidate(trigger_type="BUY", trigger_price=None, trigger_live=False)
        current["rule_proof"]["period_evaluation_details"] = [
            {"period": "M", "current_price_or_close": 418.0},
        ]
        previous = previous_matched_lifecycle_state(current, trigger_type="BUY", trigger_price=417.0)

        execute_plan = build_plan([current], previous_trigger_states=[previous])

        self.assertEqual(execute_plan["matched_count"], 0)
        self.assertEqual(execute_plan["state_changed_count"], 0)
        self.assertEqual(execute_plan["writes"]["common_trigger_state"], [])
        self.assertEqual(execute_plan["writes"]["common_trigger_match"], [])
        self.assertEqual(execute_plan["writes"]["common_event_outbox"], [])

    def test_trigger_period_material_change_still_emits_state_changed(self) -> None:
        current = matched_lifecycle_candidate(trigger_type="BUY", trigger_price=418.0, trigger_live=False)
        current["trigger_period"] = "D"
        current["primary_trigger_period"] = "D"
        current["triggered_periods"] = ["D"]
        current["all_trigger_periods"] = ["D"]
        previous = previous_matched_lifecycle_state(current, trigger_type="BUY", trigger_price=418.0)

        execute_plan = build_plan([current], previous_trigger_states=[previous])
        payload = execute_plan["writes"]["common_event_outbox"][0]["payload_json"]

        self.assertEqual(execute_plan["matched_count"], 0)
        self.assertEqual(execute_plan["state_changed_count"], 1)
        self.assertEqual(payload["event_type"], "TriggerStateChanged")
        self.assertEqual(payload["current_status"], "matched")
        self.assertTrue(payload["trigger_live"])

    def test_previous_baseline_explicit_run_id_selects_only_that_target(self) -> None:
        current = matched_lifecycle_candidate()
        flawed = previous_matched_lifecycle_state(current, trigger_price=417.0)
        flawed["run_id"] = "flawed_v2_target"
        old = previous_matched_lifecycle_state(current, trigger_price=300.0)
        old["run_id"] = "old_default_target"

        selected = select_previous_ordinary_trigger_states(
            [old, flawed],
            previous_trigger_run_id="flawed_v2_target",
        )

        self.assertEqual(selected, [flawed])

    def test_previous_baseline_explicit_run_id_wins_over_no_previous_mode(self) -> None:
        current = matched_lifecycle_candidate()
        flawed = previous_matched_lifecycle_state(current, trigger_price=417.0)
        flawed["run_id"] = "flawed_v2_target"
        old = previous_matched_lifecycle_state(current, trigger_price=300.0)
        old["run_id"] = "old_default_target"

        selected = select_previous_ordinary_trigger_states(
            [old, flawed],
            previous_trigger_run_id="flawed_v2_target",
            baseline_mode="no_previous_baseline",
        )

        self.assertEqual(selected, [flawed])

    def test_previous_baseline_explicit_run_id_uses_latest_state_snapshot_through_target(self) -> None:
        current = matched_lifecycle_candidate(condition_key="BUY:Q,M,W", identity_key="stock:SZ:300139")
        old_matched = previous_matched_lifecycle_state(current, trigger_price=44.14)
        old_matched["run_id"] = build_n4p_ordinary_trigger_run_id(
            for_trade_date="20260624",
            until_hhmm="1022",
            asset_scope="asset_all",
        )
        unrelated_previous_target = previous_matched_lifecycle_state(
            matched_lifecycle_candidate(condition_key="BUY:M", identity_key="stock:SH:600000"),
            trigger_price=12.34,
        )
        unrelated_previous_target["run_id"] = build_n4p_ordinary_trigger_run_id(
            for_trade_date="20260624",
            until_hhmm="1026",
            asset_scope="asset_all",
        )
        future = previous_matched_lifecycle_state(current, trigger_price=44.79)
        future["run_id"] = build_n4p_ordinary_trigger_run_id(
            for_trade_date="20260624",
            until_hhmm="1030",
            asset_scope="asset_all",
        )

        selected = select_previous_ordinary_trigger_states(
            [old_matched, unrelated_previous_target, future],
            previous_trigger_run_id=unrelated_previous_target["run_id"],
        )
        execute_plan = build_plan([current], previous_trigger_states=selected)

        self.assertIn(old_matched, selected)
        self.assertNotIn(future, selected)
        self.assertEqual(execute_plan["matched_count"], 0)
        self.assertEqual(execute_plan["state_changed_count"], 0)
        self.assertEqual(execute_plan["writes"]["common_event_outbox"], [])

    def test_previous_baseline_fetch_uses_db_side_latest_snapshot_query_with_cutoff(self) -> None:
        class RecordingCursor:
            def __init__(self, snapshot_rows: list[dict[str, object]], exact_rows: list[dict[str, object]]) -> None:
                self.snapshot_rows = snapshot_rows
                self.exact_rows = exact_rows
                self.executions: list[tuple[str, tuple[object, ...]]] = []

            def __enter__(self) -> "RecordingCursor":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def execute(self, sql: str, params: tuple[object, ...]) -> None:
                self.executions.append((sql, params))

            def fetchall(self) -> list[dict[str, object]]:
                sql = self.executions[-1][0]
                if "ranked_previous_states" in sql:
                    return self.snapshot_rows
                return self.exact_rows

        class RecordingConnection:
            def __init__(self, cursor: RecordingCursor) -> None:
                self._cursor = cursor

            def __enter__(self) -> "RecordingConnection":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def cursor(self) -> RecordingCursor:
                return self._cursor

        current = matched_lifecycle_candidate(condition_key="BUY:Q,M,W", identity_key="stock:SZ:300139")
        old_matched = previous_matched_lifecycle_state(current, trigger_price=44.14)
        old_matched["run_id"] = build_n4p_ordinary_trigger_run_id(
            for_trade_date="20260624",
            until_hhmm="1022",
            asset_scope="asset_all",
        )
        unrelated_previous_target = previous_matched_lifecycle_state(
            matched_lifecycle_candidate(condition_key="BUY:M", identity_key="stock:SH:600000"),
            trigger_price=12.34,
        )
        unrelated_previous_target["run_id"] = build_n4p_ordinary_trigger_run_id(
            for_trade_date="20260624",
            until_hhmm="1026",
            asset_scope="asset_all",
        )
        future = previous_matched_lifecycle_state(current, trigger_price=44.79)
        future["run_id"] = build_n4p_ordinary_trigger_run_id(
            for_trade_date="20260624",
            until_hhmm="1030",
            asset_scope="asset_all",
        )
        cursor = RecordingCursor(snapshot_rows=[old_matched, unrelated_previous_target], exact_rows=[])

        with patch(
            "ashare_v3.trigger.provisional_ordinary_execute.audited_n4_readonly_plan_connect",
            return_value=RecordingConnection(cursor),
        ):
            selected = fetch_previous_ordinary_trigger_states(
                "postgresql://example.invalid/db",
                trigger_run_id=TRIGGER_RUN_ID,
                for_trade_date="20260624",
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                previous_trigger_run_id=unrelated_previous_target["run_id"],
            )

        sql, params = cursor.executions[0]
        normalized_sql = " ".join(sql.split()).lower()
        self.assertIn("ranked_previous_states", normalized_sql)
        self.assertIn("row_number() over", normalized_sql)
        self.assertIn("lifecycle_trigger_type", normalized_sql)
        self.assertIn("<= %s", normalized_sql)
        self.assertIn("like 'buy:%%'", normalized_sql)
        self.assertIn("like 'sell:%%'", normalized_sql)
        self.assertNotIn("like 'buy:%'", normalized_sql)
        self.assertNotIn("like 'sell:%'", normalized_sql)
        self.assertIn("1026", params)
        self.assertIn(old_matched, selected)
        self.assertIn(unrelated_previous_target, selected)
        self.assertNotIn(future, selected)

    def test_previous_baseline_fetch_falls_back_to_exact_rows_when_snapshot_unavailable(self) -> None:
        class RecordingCursor:
            def __init__(self, exact_rows: list[dict[str, object]]) -> None:
                self.exact_rows = exact_rows
                self.executions: list[tuple[str, tuple[object, ...]]] = []

            def __enter__(self) -> "RecordingCursor":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def execute(self, sql: str, params: tuple[object, ...]) -> None:
                self.executions.append((sql, params))

            def fetchall(self) -> list[dict[str, object]]:
                return self.exact_rows

        class RecordingConnection:
            def __init__(self, cursor: RecordingCursor) -> None:
                self._cursor = cursor

            def __enter__(self) -> "RecordingConnection":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def cursor(self) -> RecordingCursor:
                return self._cursor

        current = matched_lifecycle_candidate()
        flawed = previous_matched_lifecycle_state(current, trigger_price=417.0)
        flawed["run_id"] = "flawed_v2_target"
        cursor = RecordingCursor(exact_rows=[flawed])

        with patch(
            "ashare_v3.trigger.provisional_ordinary_execute.audited_n4_readonly_plan_connect",
            return_value=RecordingConnection(cursor),
        ):
            selected = fetch_previous_ordinary_trigger_states(
                "postgresql://example.invalid/db",
                trigger_run_id=TRIGGER_RUN_ID,
                for_trade_date="20260624",
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                previous_trigger_run_id="flawed_v2_target",
            )

        self.assertEqual(selected, [flawed])
        self.assertNotIn("ranked_previous_states", cursor.executions[0][0])

    def test_previous_baseline_latest_state_snapshot_uses_latest_state_per_lifecycle_key(self) -> None:
        current = matched_lifecycle_candidate(condition_key="BUY:Q,M,W", identity_key="stock:SZ:300139")
        old_matched = previous_matched_lifecycle_state(current, trigger_price=44.14)
        old_matched["run_id"] = build_n4p_ordinary_trigger_run_id(
            for_trade_date="20260624",
            until_hhmm="1022",
            asset_scope="asset_all",
        )
        latest_inactive = previous_matched_lifecycle_state(current, trigger_price=44.20)
        latest_inactive["run_id"] = build_n4p_ordinary_trigger_run_id(
            for_trade_date="20260624",
            until_hhmm="1026",
            asset_scope="asset_all",
        )
        latest_inactive["current_status"] = "inactive"
        latest_inactive["raw_json"]["current_status"] = "inactive"
        latest_inactive["raw_json"]["trigger_live"] = False

        selected = select_previous_ordinary_trigger_states(
            [old_matched, latest_inactive],
            previous_trigger_run_id=latest_inactive["run_id"],
        )
        execute_plan = build_plan([current], previous_trigger_states=selected)

        self.assertNotIn(old_matched, selected)
        self.assertIn(latest_inactive, selected)
        self.assertEqual(execute_plan["matched_count"], 1)
        self.assertEqual(execute_plan["writes"]["common_event_outbox"][0]["payload_json"]["event_type"], "TriggerMatched")

    def test_previous_baseline_ambiguous_without_explicit_run_id_fails_closed(self) -> None:
        current = matched_lifecycle_candidate()
        flawed = previous_matched_lifecycle_state(current)
        flawed["run_id"] = "flawed_v2_target"
        old = previous_matched_lifecycle_state(current)
        old["run_id"] = "old_default_target"

        with self.assertRaises(N4POrdinaryExecuteBlocked) as raised:
            select_previous_ordinary_trigger_states([old, flawed])

        self.assertIn("ambiguous previous ordinary trigger baseline", str(raised.exception))

    def test_previous_baseline_no_previous_mode_allows_empty_baseline(self) -> None:
        current = matched_lifecycle_candidate()
        flawed = previous_matched_lifecycle_state(current)
        flawed["run_id"] = "flawed_v2_target"
        old = previous_matched_lifecycle_state(current)
        old["run_id"] = "old_default_target"

        selected = select_previous_ordinary_trigger_states(
            [old, flawed],
            baseline_mode="no_previous_baseline",
        )

        self.assertEqual(selected, [])

    def test_previous_baseline_unknown_mode_fails_closed(self) -> None:
        with self.assertRaises(N4POrdinaryExecuteBlocked) as raised:
            select_previous_ordinary_trigger_states([], baseline_mode="latest")

        self.assertIn("unsupported previous baseline mode", str(raised.exception))

    def test_asset_unit_fix_no_previous_baseline_plan_generates_initial_matches(self) -> None:
        trigger_run_id = build_n4p_ordinary_trigger_run_id(
            for_trade_date="20260626",
            until_hhmm="1447",
            asset_scope="asset_all",
            source_variant="live_current_1m_amount_chain_v2_asset_unit_fix_v1",
            rule_suffix="atomic_rule_v1",
        )
        plans = [
            matched_lifecycle_candidate(identity_key=f"stock:SH:{600000 + index:06d}")
            for index in range(406)
        ]

        execute_plan = build_provisional_ordinary_execute_plan(
            trigger_run_id=trigger_run_id,
            trigger_context_run={"run_id": CONTEXT_RUN_ID, "status": "passed", "for_trade_date": "20260626"},
            source_metric_run={"run_id": N3P_RUN_ID, "status": "passed"},
            trigger_context_run_id=CONTEXT_RUN_ID,
            source_metric_run_id=N3P_RUN_ID,
            for_trade_date="20260626",
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            dry_run_plans=plans,
            context_snapshot_row_count=len(plans),
            target_counts=empty_target_counts(),
            previous_trigger_states=select_previous_ordinary_trigger_states(
                [previous_matched_lifecycle_state(plans[0])],
                baseline_mode="no_previous_baseline",
            ),
        )

        self.assertEqual(execute_plan["matched_count"], 406)
        self.assertEqual(execute_plan["state_changed_count"], 0)
        self.assertEqual(execute_plan["write_counts"]["common_trigger_run"], 1)
        self.assertEqual(execute_plan["write_counts"]["common_trigger_quality_item"], 1)
        self.assertEqual(execute_plan["write_counts"]["common_trigger_state"], 406)
        self.assertEqual(execute_plan["write_counts"]["common_trigger_match"], 406)
        self.assertEqual(execute_plan["write_counts"]["common_event_outbox"], 406)

    def test_matched_to_inactive_lifecycle_writes_state_changed_without_ordinary_match(self) -> None:
        matched_plans = ordinary_plans(
            [context_row("stock:SH:600000", "buy", "BUY:D", ["BUY"])],
            [n3p_metric_row("stock", "stock:SH:600000", direction="buy")],
        )
        previous = previous_state_for_payload(build_plan(matched_plans)["writes"]["common_event_outbox"][0]["payload_json"])
        inactive_plans = ordinary_plans(
            [context_row("stock:SH:600000", "buy", "BUY:D", ["BUY"])],
            [n3p_metric_row("stock", "stock:SH:600000", direction="sell")],
        )

        execute_plan = build_plan(inactive_plans, previous_trigger_states=[previous])

        self.assertEqual(execute_plan["matched_count"], 0)
        self.assertEqual(execute_plan["state_changed_count"], 1)
        self.assertEqual(execute_plan["writes"]["common_trigger_state"][0]["current_status"], "inactive")
        self.assertEqual(execute_plan["writes"]["common_trigger_match"], [])
        payload = execute_plan["writes"]["common_event_outbox"][0]["payload_json"]
        self.assertEqual(payload["event_type"], "TriggerStateChanged")
        self.assertFalse(payload["trigger_live"])
        self.assertEqual(payload["current_status"], "inactive")
        self.assertEqual(payload["state_change_reason"], "matched_to_inactive")


    def test_inactive_state_changed_preserves_previous_valid_period_not_minute_label(self) -> None:
        current = state_changed_candidate(condition_key="BUY:Y,M,D")
        previous = previous_matched_state(current, trigger_period="W")

        execute_plan = build_plan([current], previous_trigger_states=[previous])
        state = execute_plan["writes"]["common_trigger_state"][0]
        payload = execute_plan["writes"]["common_event_outbox"][0]["payload_json"]

        self.assertEqual(execute_plan["state_changed_count"], 1)
        self.assertEqual(execute_plan["writes"]["common_trigger_match"], [])
        self.assertEqual(state["current_status"], "inactive")
        self.assertEqual(state["trigger_period"], "W")
        self.assertNotEqual(state["trigger_period"], "11:29")
        self.assertEqual(payload["trigger_period"], "W")
        self.assertFalse(payload["n4_boundary"]["enters_n5"])
        self.assertFalse(execute_plan["event_model"]["enters_n5"])
        self.assertFalse(execute_plan["event_model"]["writes_inbox_or_checkpoint"])
        self.assertFalse(execute_plan["side_effect_guard"]["worker_started"])

    def test_state_changed_period_falls_back_to_condition_key_highest_priority_period(self) -> None:
        current = state_changed_candidate(condition_key="BUY:Y,M,D", identity_key="stock:SH:600101")
        previous = previous_matched_state(current, trigger_period=None)

        execute_plan = build_plan([current], previous_trigger_states=[previous])
        state = execute_plan["writes"]["common_trigger_state"][0]
        payload = execute_plan["writes"]["common_event_outbox"][0]["payload_json"]

        self.assertEqual(state["trigger_period"], "Y")
        self.assertEqual(payload["trigger_period"], "Y")
        self.assertNotEqual(state["trigger_period"], "11:29")

    def test_state_changed_period_fails_closed_without_any_valid_period(self) -> None:
        current = state_changed_candidate(condition_key="BUY", identity_key="stock:SH:600102")
        previous = previous_matched_state(current, trigger_period=None)

        with self.assertRaises(N4POrdinaryExecuteBlocked) as raised:
            build_plan([current], previous_trigger_states=[previous])

        self.assertIn("valid trigger_period", str(raised.exception))

    def test_dirty_target_fails_closed_before_insert_planning(self) -> None:
        plans = ordinary_plans(
            [context_row("stock:SH:600000", "buy", "BUY:D", ["BUY"])],
            [n3p_metric_row("stock", "stock:SH:600000", direction="buy")],
        )

        with self.assertRaises(N4POrdinaryExecuteBlocked) as raised:
            build_plan(plans, target_counts={**empty_target_counts(), "common_trigger_state": 1})

        self.assertIn("BLOCKED_TARGET_NOT_EMPTY", str(raised.exception))

    def test_atomic_run_id_keeps_duplicate_guard_fail_closed(self) -> None:
        plans = ordinary_plans(
            [context_row("stock:SH:600000", "buy", "BUY:D", ["BUY"])],
            [n3p_metric_row("stock", "stock:SH:600000", direction="buy")],
        )

        with self.assertRaises(N4POrdinaryExecuteBlocked) as raised:
            build_provisional_ordinary_execute_plan(
                trigger_run_id=build_n4p_ordinary_trigger_run_id(
                    for_trade_date="20260624",
                    until_hhmm="1352",
                    asset_scope="asset_all",
                    rule_suffix="atomic_rule_v1",
                ),
                trigger_context_run={"run_id": CONTEXT_RUN_ID, "status": "passed", "for_trade_date": "20260624"},
                source_metric_run={"run_id": N3P_RUN_ID, "status": "passed"},
                trigger_context_run_id=CONTEXT_RUN_ID,
                source_metric_run_id=N3P_RUN_ID,
                for_trade_date="20260624",
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                dry_run_plans=plans,
                context_snapshot_row_count=len(plans),
                target_counts={**empty_target_counts(), "common_trigger_run": 1},
                previous_trigger_states=[],
            )

        self.assertIn("BLOCKED_TARGET_NOT_EMPTY", str(raised.exception))

    def test_payload_preserves_n3p_metric_fields_and_unclosed_minute(self) -> None:
        plans = ordinary_plans(
            [context_row("stock:SH:600000", "buy", "BUY:D", ["BUY"])],
            [
                n3p_metric_row(
                    "stock",
                    "stock:SH:600000",
                    direction="buy",
                    is_closed_1m=False,
                    source_mode="live_current_1m",
                    c1_dependency=False,
                )
            ],
        )

        execute_plan = build_plan(plans)
        match = execute_plan["writes"]["common_trigger_match"][0]
        payload = execute_plan["writes"]["common_event_outbox"][0]["payload_json"]

        self.assertEqual(payload["event_type"], "TriggerMatched")
        self.assertTrue(payload["provisional"])
        self.assertEqual(payload["metric_role"], "trigger_proof")
        self.assertEqual(payload["proof_owner"], "N3")
        self.assertEqual(payload["proof_consumer"], "N4")
        self.assertTrue(payload["not_n5_final_proof"])
        self.assertEqual(payload["source_trigger_proof_kind"], "n3p_formal_amount_chain")
        self.assertEqual(payload["source_trigger_proof_run_id"], N3P_RUN_ID)
        self.assertEqual(payload["source_trigger_proof_metric_id"], plans[0]["selected_metric_id"])
        self.assertEqual(payload["source_trigger_proof_time"], "2026-06-24T13:52:00+08:00")
        self.assertEqual(payload["source_metric_kind"], "realtime_action_confirmation_metric")
        self.assertEqual(payload["source_metric_run_id"], N3P_RUN_ID)
        self.assertEqual(payload["source_n3p_live_target_run_id"], N3P_RUN_ID)
        self.assertEqual(payload["selected_metric_id"], plans[0]["selected_metric_id"])
        self.assertEqual(payload["source_metric_event_type"], "N3PRealtimeActionMetric")
        self.assertEqual(payload["selected_metric_time"], "2026-06-24T13:52:00+08:00")
        self.assertEqual(payload["metric_time_label"], "2026-06-24 13:52")
        self.assertEqual(payload["metric_minute_label"], "13:52")
        self.assertFalse(payload["is_closed_1m"])
        self.assertEqual(payload["source_mode"], "live_current_1m")
        self.assertFalse(payload["c1_dependency"])
        self.assertTrue(payload["n4_boundary"]["enters_n5"])
        self.assertTrue(payload["n5_entry_allowed"])
        self.assertTrue(execute_plan["event_model"]["enters_n5"])
        self.assertTrue(execute_plan["writes"]["common_trigger_quality_item"][0]["details"]["enters_n5"])
        self.assertEqual(payload["condition_key"], "BUY:D")
        self.assertEqual(payload["original_condition_key"], "BUY:D")
        self.assertEqual(payload["signal_type"], "B_BUY")
        self.assertEqual(payload["trigger_type"], "BUY")
        self.assertEqual(payload["trigger_mark_candidate"], "normal")
        self.assertEqual(payload["trigger_period"], "D")
        self.assertEqual(payload["triggered_periods"], ["D"])
        self.assertEqual(payload["trigger_price"], 10.5)
        self.assertEqual(payload["rule_eval_result"]["output_event_type"], "TriggerMatched")
        self.assertIn("rule_reused", payload["rule_proof"])
        self.assertEqual(payload["candidate_trigger_identity_key"], plans[0]["candidate_trigger_identity_key"])
        self.assertEqual(match["source_event_type"], "MarketSnapshotUpdated")
        self.assertIn(f"N3P:{N3P_RUN_ID}:{plans[0]['selected_metric_id']}", match["source_event_id"])
        self.assertEqual(match["trigger_period"], "D")
        self.assertEqual(match["trigger_price"], 10.5)
        self.assertEqual(match["raw_json"]["source_metric_event_type"], "N3PRealtimeActionMetric")
        self.assertEqual(match["raw_json"]["metric_role"], "trigger_proof")
        self.assertEqual(match["raw_json"]["source_trigger_proof_kind"], "n3p_formal_amount_chain")
        self.assertTrue(match["raw_json"]["not_n5_final_proof"])
        self.assertEqual(match["raw_json"]["source_n3p_live_target_run_id"], N3P_RUN_ID)
        self.assertEqual(match["raw_json"]["source_mode"], "live_current_1m")
        self.assertFalse(match["raw_json"]["c1_dependency"])
        self.assertEqual(match["raw_json"]["condition_key"], "BUY:D")
        self.assertEqual(match["raw_json"]["original_condition_key"], "BUY:D")
        self.assertTrue(match["raw_json"]["n5_entry_allowed"])
        self.assertEqual(match["raw_json"]["candidate_trigger_identity_key"], plans[0]["candidate_trigger_identity_key"])
        self.assertEqual(match["raw_json"]["trigger_period"], "D")
        self.assertEqual(match["raw_json"]["triggered_periods"], ["D"])
        self.assertEqual(match["raw_json"]["trigger_price"], 10.5)

    def test_legacy_multi_period_plan_is_rejected_at_production_boundary(self) -> None:
        plans = ordinary_plans(
            [context_row("stock:SH:600000", "buy", "BUY:Y,Q,M,W,D", ["BUY"])],
            [
                n3p_metric_row(
                    "stock",
                    "stock:SH:600000",
                    direction="buy",
                    formal_period_amount_proof=formal_period_amount_proof_factory(
                        periods=("Y", "Q", "M", "W", "D"),
                        amount_unit="yuan",
                        source_kind="N3_standard_period_metric",
                        amount_pass=True,
                        amount_value=150000.0,
                    ),
                )
            ],
        )

        with self.assertRaises(N4POrdinaryExecuteBlocked) as raised:
            build_plan(plans)

        self.assertIn("top_level_trace_legacy_replay_conflicting", str(raised.exception))

    def test_multi_period_trigger_contract_uses_highest_priority_period_and_price(self) -> None:
        plans = ordinary_plans(
            [context_row("stock:SH:600000", "buy", "BUY:Y,Q,M,W,D", ["BUY"])],
            [
                n3p_metric_row(
                    "stock",
                    "stock:SH:600000",
                    direction="buy",
                    formal_period_amount_proof=formal_period_amount_proof_factory(
                        periods=("Y", "Q", "M", "W", "D"),
                        amount_unit="yuan",
                        source_kind="N3_standard_period_metric",
                        amount_pass=True,
                    ),
                )
            ],
        )

        with self.assertRaises(N4POrdinaryExecuteBlocked) as raised:
            build_plan(plans)
        self.assertIn("top_level_trace_legacy_replay_conflicting", str(raised.exception))

    def test_hint_plans_are_rejected_by_ordinary_execute(self) -> None:
        hint_plan = {
            "output_event_type": "TriggerMatched",
            "condition_key": "BUY_HINT",
            "trigger_type": "BUY_HINT",
            "asset_kind": "stock",
            "identity_key": "stock:SH:600000",
            "signal_type": "B_BUY",
            "candidate_trigger_identity_key": "bad",
        }

        with self.assertRaises(N4POrdinaryExecuteBlocked) as raised:
            build_plan([hint_plan])

        self.assertIn("ordinary execute received hint condition", str(raised.exception))

    def test_duplicate_candidate_identity_is_deduped_before_write_planning(self) -> None:
        plans = ordinary_plans(
            [context_row("stock:SH:600000", "buy", "BUY:D", ["BUY"])],
            [n3p_metric_row("stock", "stock:SH:600000", direction="buy")],
        )

        execute_plan = build_plan([plans[0], dict(plans[0])])

        self.assertEqual(execute_plan["candidate_count"], 2)
        self.assertEqual(execute_plan["matched_count"], 1)
        self.assertEqual(len(execute_plan["writes"]["common_event_outbox"]), 1)
        outbox = execute_plan["writes"]["common_event_outbox"][0]
        self.assertIn(str(plans[0]["selected_metric_id"]), outbox["dedup_key"])
        self.assertIn(plans[0]["candidate_trigger_identity_key"], outbox["payload_json"]["candidate_trigger_identity_key"])

    def test_side_effect_guard_and_static_forbidden_route_checks(self) -> None:
        import ashare_v3.trigger.provisional_ordinary_execute as ordinary_execute

        module_source = inspect.getsource(ordinary_execute)
        plans = ordinary_plans(
            [context_row("stock:SH:600000", "buy", "BUY:D", ["BUY"])],
            [n3p_metric_row("stock", "stock:SH:600000", direction="buy")],
        )
        execute_plan = build_plan(plans)

        self.assertTrue(execute_plan["side_effect_guard"]["db_written"])
        self.assertFalse(execute_plan["side_effect_guard"]["inbox_written"])
        self.assertFalse(execute_plan["side_effect_guard"]["checkpoint_written"])
        self.assertFalse(execute_plan["side_effect_guard"]["n5_executed"])
        self.assertFalse(execute_plan["side_effect_guard"]["n6_written"])
        self.assertFalse(execute_plan["side_effect_guard"]["sim_trade_virtual_written"])
        self.assertNotIn("projection_matcher_execute", module_source)
        self.assertEqual(ordinary_execute.ORDINARY_STATE_CHANGED_EVENT_TYPE, "TriggerStateChanged")
        self.assertNotIn("INSERT INTO common_event_inbox", module_source)
        self.assertNotIn("INSERT INTO common_event_consumer_checkpoint", module_source)

    def test_rollback_sql_has_full_downstream_guards_and_scoped_deletes(self) -> None:
        sql = build_ordinary_rollback_sql(TRIGGER_RUN_ID)
        first_delete = sql.index("DELETE FROM")
        guard_prefix = sql[:first_delete]

        for table_name in (
            "common_event_outbox",
            "common_event_inbox",
            "common_event_consumer_checkpoint",
            "common_action_run",
            "common_action_event",
            "stock_action_fact",
            "index_action_fact",
            "board_action_fact",
            "user_projection_run",
            "user_signal_projection",
            "user_signal_card",
            "user_notification_queue",
            "sim_projection",
            "n6_virtual_account",
        ):
            self.assertIn(table_name, guard_prefix)
        self.assertIn("RAISE EXCEPTION", guard_prefix)
        self.assertIn("source_run_id = $1", guard_prefix)
        self.assertIn("delivered", guard_prefix)
        self.assertIn("delivering", guard_prefix)
        self.assertIn("rollback blocked: scoped outbox already delivered/delivering", guard_prefix)

        for table_name in (
            "common_action_run",
            "common_action_event",
            "stock_action_fact",
            "index_action_fact",
            "board_action_fact",
            "user_projection_run",
            "user_signal_projection",
            "user_signal_card",
            "user_notification_queue",
            "sim_projection",
            "n6_virtual_account",
        ):
            self.assertNotIn(f"DELETE FROM {table_name}", sql)
        self.assertIn("DELETE FROM common_event_outbox", sql)
        self.assertIn("source_run_id = v_run_id", sql)
        self.assertIn("DELETE FROM common_trigger_match WHERE run_id = v_run_id", sql)
        self.assertIn("DELETE FROM common_trigger_state WHERE run_id = v_run_id", sql)
        self.assertIn("DELETE FROM common_trigger_quality_item WHERE run_id = v_run_id", sql)
        self.assertIn("DELETE FROM common_trigger_run WHERE run_id = v_run_id", sql)

    def test_rollback_sql_can_be_built_for_amount_chain_v2_target(self) -> None:
        run_id = (
            "trigger_provisional_ordinary_20260626_until_1447"
            "__realtime_action_confirmation_metric_20260626_until_1447"
            "__asset_all__live_current_1m_amount_chain_v2__atomic_rule_v1"
        )

        sql = build_ordinary_rollback_sql(run_id)

        self.assertIn(run_id, sql)
        self.assertIn("DELETE FROM common_event_outbox", sql)
        self.assertNotIn("DELETE FROM common_action", sql)


if __name__ == "__main__":
    unittest.main()
