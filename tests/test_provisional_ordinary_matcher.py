import copy
import hashlib
import inspect
import json
import unittest

from ashare_v3.trigger import provisional_projection_matcher
from ashare_v3.trigger.provisional_ordinary_matcher import (
    adapt_n3p_metric_row_for_rule_v4,
    assert_same_day_period_escalation_output_contract,
    build_provisional_ordinary_matcher_dry_run_report,
    build_provisional_ordinary_matcher_plans,
    summarize_provisional_ordinary_matcher_plans,
)
from ashare_v3.trigger.provisional_trigger_lifecycle import build_lifecycle_output_plans
from ashare_v3.trigger.rule_v4_matcher import (
    LEGACY_PERIOD_ESCALATION_REPLAY_CONTEXT_RUN_IDS,
    ORDINARY_PERIOD_ESCALATION_POLICY_HASH,
    ORDINARY_PERIOD_ESCALATION_POLICY_VERSION,
    PERIOD_ESCALATION_CONTEXT_VERSION,
    PERIOD_ESCALATION_DIRECTION_TRANSITIONS,
    PERIOD_ESCALATION_REQUIREMENTS,
)
from tests.test_trigger_projection_matcher import (
    CONTEXT_RUN_ID,
    context_row,
    context_row_with_condition_projection,
    stable_int,
)


N3P_RUN_ID = (
    "realtime_action_confirmation_metric_20260624_until_1352__asset_all__"
    "market_data_subscription_20260624_condition_layer_20260623_source_20260623_for_20260624_v1"
)
SAME_DAY_CONTEXT_RUN_ID = (
    "trigger_context_snapshot_20260714_condition_layer_20260713_"
    "source_20260713_for_20260714_v1__atomic_rule_v1"
)
PRODUCTION_20260714_SOURCE_CONDITION_RUN_ID = (
    "condition_layer_20260713_source_20260713_for_20260714_v1"
)
PRODUCTION_20260714_1322_METRIC_RUN_ID = (
    "realtime_action_confirmation_metric_20260714_until_1322__asset_all__"
    "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__"
    "market_data_subscription_20260714_condition_layer_20260713_source_20260713_for_20260714_v1"
)
PRODUCTION_20260714_1322_FALSE_POSITIVE_CASES = (
    ("stock", "stock:SH:600018", "buy", "BUY:Y,Q,M", ("Q", "M"), {"Y": "not_ready"}, ["Q"], ["Q", "M"], ["M"]),
    ("stock", "stock:SH:600161", "buy", "BUY:Y,Q,M,W,D", ("W", "D"), {"Y": "not_ready", "Q": "not_seen", "M": "not_seen"}, ["W"], ["W", "D"], ["D"]),
    ("stock", "stock:SH:600350", "buy", "BUY:Y,M,W,D", ("M", "W"), {"Y": "not_ready"}, ["M"], ["M", "W"], ["W"]),
    ("stock", "stock:SH:600380", "buy", "BUY:Y,Q,W,D", ("W", "D"), {"Y": "not_ready"}, ["W"], ["W", "D"], ["D"]),
    ("stock", "stock:SH:600895", "buy", "BUY:Y,Q,M,W,D", ("W", "D"), {"Y": "not_ready"}, ["W"], ["W", "D"], ["D"]),
    ("stock", "stock:SZ:000661", "buy", "BUY:Y,Q,M,W,D", ("W", "D"), {"Y": "not_ready", "Q": "not_seen"}, ["W"], ["W", "D"], ["D"]),
    ("stock", "stock:SZ:002223", "buy", "BUY:Y,Q,M,W,D", ("M", "W"), {"Y": "not_ready"}, ["M"], ["M", "W"], ["W"]),
    ("stock", "stock:SZ:002532", "buy", "BUY:Y,Q,M,W,D", ("W", "D"), {"Y": "not_ready", "Q": "not_seen"}, ["W"], ["W", "D"], ["D"]),
    ("stock", "stock:SZ:002675", "buy", "BUY:Y,Q,W,D", ("W", "D"), {"Y": "not_ready"}, ["W"], ["W", "D"], ["D"]),
    ("stock", "stock:SZ:300308", "buy", "BUY:M,W,D", ("W", "D"), {"M": "not_seen"}, ["W"], ["W", "D"], ["D"]),
    ("stock", "stock:SZ:301207", "buy", "BUY:Y,Q,M,W,D", ("W", "D"), {"Y": "not_ready"}, ["W"], ["W", "D"], ["D"]),
    ("stock", "stock:SZ:301267", "buy", "BUY:Y,Q,M,W,D", ("W", "D"), {"Y": "not_ready", "Q": "not_seen", "M": "not_seen"}, ["W"], ["W", "D"], ["D"]),
    ("board", "board:TDX:881177", "sell", "SELL:Y,M,W,D", ("M", "W"), {"Y": "not_ready"}, ["M"], ["M", "W"], ["W"]),
)


def same_day_fail_closed_mutations(
    multi_valid: dict[str, object],
    disjoint_valid: dict[str, object],
) -> list[dict[str, object]]:
    invalid_plans: list[dict[str, object]] = []

    def trace_sources(plan: dict[str, object]) -> tuple[dict[str, object], ...]:
        return (plan, plan["rule_proof"], plan["rule_eval_result"])

    def tamper_compressed_trace(field: str, value: object) -> dict[str, object]:
        invalid = copy.deepcopy(multi_valid)
        for source in trace_sources(invalid):
            source["period_escalation_trace"]["periods"]["W"][field] = value
        for detail in invalid["rule_proof"]["period_evaluation_details"]:
            if detail["period"] == "W":
                detail["period_escalation_trace"][field] = value
        return invalid

    invalid_plans.extend(
        (
            tamper_compressed_trace("current_formal_pass_periods", ["M", "W"]),
            tamper_compressed_trace("evidence_source", "tampered_trace"),
            tamper_compressed_trace("direction", "sell"),
            tamper_compressed_trace("policy_version", "tampered_policy"),
            tamper_compressed_trace("policy_hash", "tampered_hash"),
            tamper_compressed_trace("target_period", "Q"),
            tamper_compressed_trace("expected_window_kind", "quarter"),
            tamper_compressed_trace("expected_required_transition", "low_volume_down"),
            tamper_compressed_trace("context_contract_version", "unexpected_context"),
            tamper_compressed_trace("context_hash", "unexpected_hash"),
            tamper_compressed_trace("gate_status", "not_ready"),
            tamper_compressed_trace("gate_pass", False),
            tamper_compressed_trace("evidence_ready", False),
            tamper_compressed_trace("reason", "unexpected_reason"),
            tamper_compressed_trace("extra_frozen_field", True),
        )
    )

    triggered_order = copy.deepcopy(disjoint_valid)
    triggered_order["rule_proof"]["triggered_period_details"].reverse()
    invalid_plans.append(triggered_order)
    triggered_classification = copy.deepcopy(multi_valid)
    triggered_classification["rule_proof"]["triggered_period_details"][0]["classification"] = "no_op"
    invalid_plans.append(triggered_classification)
    triggered_evaluation_mismatch = copy.deepcopy(multi_valid)
    triggered_evaluation_mismatch["rule_proof"]["triggered_period_details"][0]["reason"] = "tampered"
    invalid_plans.append(triggered_evaluation_mismatch)

    trace_self_proof = copy.deepcopy(multi_valid)
    for detail in trace_self_proof["rule_proof"]["period_evaluation_details"]:
        if detail["period"] == "D":
            detail["classification"] = "no_op"
    invalid_plans.append(trace_self_proof)

    non_mapping_triggered_detail = copy.deepcopy(multi_valid)
    non_mapping_triggered_detail["rule_proof"]["triggered_period_details"][0] = None
    invalid_plans.append(non_mapping_triggered_detail)
    empty_period_detail = copy.deepcopy(multi_valid)
    empty_period_detail["rule_proof"]["period_evaluation_details"][-1]["period"] = ""
    invalid_plans.append(empty_period_detail)
    unknown_period_detail = copy.deepcopy(multi_valid)
    unknown_period_detail["rule_proof"]["period_evaluation_details"][-1]["period"] = "Z"
    invalid_plans.append(unknown_period_detail)
    extra_evaluation_detail = copy.deepcopy(multi_valid)
    extra_detail = copy.deepcopy(extra_evaluation_detail["rule_proof"]["period_evaluation_details"][-1])
    extra_detail["period"] = "Q"
    extra_evaluation_detail["rule_proof"]["period_evaluation_details"].append(extra_detail)
    invalid_plans.append(extra_evaluation_detail)
    extra_triggered_detail = copy.deepcopy(multi_valid)
    extra_triggered_detail["rule_proof"]["triggered_period_details"].append(
        copy.deepcopy(extra_triggered_detail["rule_proof"]["period_evaluation_details"][1])
    )
    invalid_plans.append(extra_triggered_detail)

    non_mapping_trace = copy.deepcopy(multi_valid)
    for source in trace_sources(non_mapping_trace):
        source["period_escalation_trace"]["periods"]["W"] = "not-a-mapping"
    for detail in non_mapping_trace["rule_proof"]["period_evaluation_details"]:
        if detail["period"] == "W":
            detail["period_escalation_trace"] = "not-a-mapping"
    invalid_plans.append(non_mapping_trace)
    extra_trace = copy.deepcopy(multi_valid)
    extra_trace_value = copy.deepcopy(extra_trace["period_escalation_trace"]["periods"]["W"])
    extra_trace_value["target_period"] = "Z"
    for source in trace_sources(extra_trace):
        source["period_escalation_trace"]["periods"]["Z"] = copy.deepcopy(extra_trace_value)
    invalid_plans.append(extra_trace)

    source_conflict = copy.deepcopy(multi_valid)
    source_conflict["rule_eval_result"]["all_trigger_periods"] = ["M", "W", "D"]
    invalid_plans.append(source_conflict)
    proof_source_conflict = copy.deepcopy(multi_valid)
    proof_source_conflict["rule_proof"]["ordinary_period_escalation_policy_hash"] = "conflicting_hash"
    invalid_plans.append(proof_source_conflict)
    non_mapping_source = copy.deepcopy(multi_valid)
    non_mapping_source["rule_eval_result"] = "not-a-mapping"
    invalid_plans.append(non_mapping_source)

    markerless_missing_contract = copy.deepcopy(multi_valid)
    for source in trace_sources(markerless_missing_contract):
        source["period_escalation_trace"].pop("same_day_formal_evidence", None)
        for period_trace in source["period_escalation_trace"]["periods"].values():
            period_trace.pop("evidence_source", None)
    for detail_field in ("period_evaluation_details", "triggered_period_details"):
        for detail in markerless_missing_contract["rule_proof"][detail_field]:
            detail_trace = detail.get("period_escalation_trace")
            if isinstance(detail_trace, dict):
                detail_trace.pop("evidence_source", None)
    for source in (markerless_missing_contract, markerless_missing_contract["rule_eval_result"]):
        source.pop("all_trigger_periods", None)
        source.pop("prerequisite_periods", None)
    invalid_plans.append(markerless_missing_contract)

    markerless_damaged_missing_output = copy.deepcopy(multi_valid)
    for source in trace_sources(markerless_damaged_missing_output):
        source["period_escalation_trace"].pop("same_day_formal_evidence", None)
        for period_trace in source["period_escalation_trace"]["periods"].values():
            period_trace.pop("evidence_source", None)
    for detail_field in ("period_evaluation_details", "triggered_period_details"):
        for detail in markerless_damaged_missing_output["rule_proof"][detail_field]:
            detail_trace = detail.get("period_escalation_trace")
            if isinstance(detail_trace, dict):
                detail_trace.pop("evidence_source", None)
            detail["classification"] = "no_op"
            detail["reason"] = "tampered_formal_detail"
    for source in (
        markerless_damaged_missing_output,
        markerless_damaged_missing_output["rule_eval_result"],
    ):
        source.pop("all_trigger_periods", None)
        source.pop("prerequisite_periods", None)
    invalid_plans.append(markerless_damaged_missing_output)

    production_forged_legacy_run_id = copy.deepcopy(multi_valid)
    for source in trace_sources(production_forged_legacy_run_id):
        source["period_escalation_trace"].pop("same_day_formal_evidence", None)
        for period_trace in source["period_escalation_trace"]["periods"].values():
            period_trace.pop("evidence_source", None)
    for detail_field in ("period_evaluation_details", "triggered_period_details"):
        for detail in production_forged_legacy_run_id["rule_proof"][detail_field]:
            detail_trace = detail.get("period_escalation_trace")
            if isinstance(detail_trace, dict):
                detail_trace.pop("evidence_source", None)
    production_forged_legacy_run_id["trace"]["trigger_context_run_id"] = next(
        iter(LEGACY_PERIOD_ESCALATION_REPLAY_CONTEXT_RUN_IDS)
    )
    invalid_plans.append(production_forged_legacy_run_id)

    provisional_downgrade_empty_eval = copy.deepcopy(multi_valid)
    provisional_downgrade_empty_eval["provisional"] = False
    provisional_downgrade_empty_eval["rule_eval_result"] = {}
    invalid_plans.append(provisional_downgrade_empty_eval)

    terminal_d_reintroduced = copy.deepcopy(multi_valid)
    terminal_d_detail = next(
        detail
        for detail in terminal_d_reintroduced["rule_proof"]["period_evaluation_details"]
        if detail["period"] == "D"
    )
    terminal_d_reintroduced["rule_proof"]["triggered_period_details"].append(
        copy.deepcopy(terminal_d_detail)
    )
    for source in (terminal_d_reintroduced, terminal_d_reintroduced["rule_eval_result"]):
        source["triggered_periods"] = ["M", "D"]
        source["all_trigger_periods"] = ["M", "W", "D"]
    invalid_plans.append(terminal_d_reintroduced)

    synchronized_extra_d_trace = copy.deepcopy(multi_valid)
    synchronized_d_value = copy.deepcopy(
        synchronized_extra_d_trace["period_escalation_trace"]["periods"]["W"]
    )
    synchronized_d_value["target_period"] = "D"
    synchronized_d_value["prerequisite_period"] = ""
    for source in trace_sources(synchronized_extra_d_trace):
        source["period_escalation_trace"]["periods"]["D"] = copy.deepcopy(
            synchronized_d_value
        )
    for detail in synchronized_extra_d_trace["rule_proof"]["period_evaluation_details"]:
        if detail["period"] == "D":
            detail["period_escalation_trace"] = copy.deepcopy(synchronized_d_value)
    invalid_plans.append(synchronized_extra_d_trace)

    missing_proof_required_field = copy.deepcopy(multi_valid)
    del missing_proof_required_field["rule_proof"]["period_evaluation_details"]
    invalid_plans.append(missing_proof_required_field)
    missing_rule_eval_result = copy.deepcopy(multi_valid)
    del missing_rule_eval_result["rule_eval_result"]
    invalid_plans.append(missing_rule_eval_result)

    for field, value in (
        ("existing_formal_pass", False),
        ("reason", "tampered_formal_reason"),
        ("transition_amount_pass", False),
        ("trigger_amount_chain_pass", False),
    ):
        prerequisite_formal_conflict = copy.deepcopy(multi_valid)
        for detail in prerequisite_formal_conflict["rule_proof"]["period_evaluation_details"]:
            if detail["period"] == "D":
                detail[field] = value
        invalid_plans.append(prerequisite_formal_conflict)

    for field, value in (
        ("legacy_replay", True),
        ("context_contract_version", "unexpected_context"),
        ("context_hash", "unexpected_hash"),
        ("extra_top_trace_field", True),
    ):
        top_trace_tamper = copy.deepcopy(multi_valid)
        for source in trace_sources(top_trace_tamper):
            source["period_escalation_trace"][field] = value
        invalid_plans.append(top_trace_tamper)

    extra_d_trace = copy.deepcopy(multi_valid)
    injected_d_trace = copy.deepcopy(extra_d_trace["period_escalation_trace"]["periods"]["W"])
    injected_d_trace["target_period"] = "D"
    injected_d_trace["prerequisite_period"] = ""
    for source in trace_sources(extra_d_trace):
        source["period_escalation_trace"]["periods"]["D"] = copy.deepcopy(injected_d_trace)
    invalid_plans.append(extra_d_trace)

    compressed_target_reintroduced = copy.deepcopy(multi_valid)
    compressed_target_reintroduced["triggered_periods"] = ["M", "W"]
    invalid_plans.append(compressed_target_reintroduced)
    multi_wrong_all = copy.deepcopy(multi_valid)
    multi_wrong_all["all_trigger_periods"] = ["M", "W", "D"]
    invalid_plans.append(multi_wrong_all)
    multi_wrong_primary = copy.deepcopy(multi_valid)
    multi_wrong_primary["primary_trigger_period"] = "W"
    invalid_plans.append(multi_wrong_primary)
    multi_wrong_prerequisite = copy.deepcopy(multi_valid)
    multi_wrong_prerequisite["prerequisite_periods"] = ["W", "D"]
    invalid_plans.append(multi_wrong_prerequisite)
    return invalid_plans


def _period_escalation_contract_hash(value: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _production_period_escalation_entry(
    *,
    period: str,
    direction: str,
    status: str,
    exact_stock_300308_m: bool = False,
) -> dict[str, object]:
    requirement = PERIOD_ESCALATION_REQUIREMENTS[period]
    expected_count = {"W": 1, "M": 9, "Q": 9, "Y": 125}[period]
    window_start = {"W": "20260713", "M": "20260701", "Q": "20260701", "Y": "20260101"}[period]
    entry: dict[str, object] = {
        "target_period": period,
        "prerequisite_period": requirement["prerequisite_period"],
        "window_kind": requirement["window_kind"],
        "window_key": {"W": "2026W29", "M": "202607", "Q": "2026Q3", "Y": "2026"}[period],
        "window_start": window_start,
        "required_transition": PERIOD_ESCALATION_DIRECTION_TRANSITIONS[direction],
        "reset_for_trade_date": False,
        "state_epoch_trade_date": window_start,
        "observation_end": "20260713",
        "expected_source_trade_date_count": expected_count,
        "observed_source_trade_date_count": expected_count,
        "missing_source_trade_dates": [],
        "observation_count": 1,
        "previous_incremental_state_used": expected_count > 1,
        "first_source_trade_date": window_start,
        "last_source_trade_date": "20260713",
        "status": "ready",
        "coverage_status": "passed",
        "seen": True,
        "latest_source_basis_ref": f"fixture:{period}:{direction}:20260713",
        "latest_source_condition_run_id": PRODUCTION_20260714_SOURCE_CONDITION_RUN_ID,
    }
    if status == "not_seen":
        entry.update(
            {
                "observation_count": 0,
                "first_source_trade_date": None,
                "last_source_trade_date": None,
                "status": "not_seen",
                "seen": False,
                "latest_source_basis_ref": None,
                "latest_source_condition_run_id": None,
            }
        )
    elif status == "not_ready":
        missing_date = window_start
        observed_count = expected_count - 1
        entry.update(
            {
                "observed_source_trade_date_count": observed_count,
                "missing_source_trade_dates": [missing_date],
                "observation_count": 0,
                "status": "not_ready",
                "coverage_status": "incomplete",
                "seen": False,
                "state_epoch_trade_date": (
                    None
                    if observed_count == 0
                    else {"M": "20260702", "Q": "20260702", "Y": "20260102"}[period]
                ),
                "previous_incremental_state_used": observed_count > 1,
                "first_source_trade_date": None,
                "last_source_trade_date": None,
                "latest_source_basis_ref": None,
                "latest_source_condition_run_id": None,
            }
        )
    elif status != "ready":
        raise AssertionError(f"unsupported fixture status: {status}")

    if exact_stock_300308_m:
        entry.update(
            {
                "target_period": "M",
                "prerequisite_period": "W",
                "window_kind": "month",
                "window_key": "202607",
                "window_start": "20260701",
                "required_transition": "volume_up",
                "reset_for_trade_date": False,
                "state_epoch_trade_date": "20260701",
                "observation_end": "20260713",
                "expected_source_trade_date_count": 9,
                "observed_source_trade_date_count": 9,
                "missing_source_trade_dates": [],
                "observation_count": 0,
                "previous_incremental_state_used": True,
                "first_source_trade_date": None,
                "last_source_trade_date": None,
                "status": "not_seen",
                "coverage_status": "passed",
                "seen": False,
                "latest_source_basis_ref": None,
                "latest_source_condition_run_id": None,
            }
        )
    entry["entry_hash"] = _period_escalation_contract_hash(entry)
    return entry


def production_20260714_1322_negative_evidence_fixture(
    *,
    asset_kind: str,
    identity_key: str,
    direction: str,
    condition_key: str,
    formal_periods: tuple[str, ...],
    negative_statuses: dict[str, str],
) -> tuple[dict[str, object], dict[str, object]]:
    prefix = "BUY" if direction == "buy" else "SELL"
    context = context_row(
        identity_key,
        direction,
        condition_key,
        [prefix],
        asset_kind=asset_kind,
        run_id=SAME_DAY_CONTEXT_RUN_ID,
    )
    context.update(
        {
            "source_condition_run_id": PRODUCTION_20260714_SOURCE_CONDITION_RUN_ID,
            "for_trade_date": "20260714",
            "source_trade_date": "20260713",
            "prev_trade_date": "20260713",
            "condition_periods": condition_key.split(":", 1)[1].split(","),
        }
    )
    if identity_key == "stock:SZ:300308":
        context.update(
            {
                "source_condition_pool_id": 236323,
                "source_condition_basis_id": 338608,
                "source_minute_target_scope_id": 224715,
            }
        )

    baseline = context["period_trigger_baseline_json"]
    current_keys = {"Y": "2026", "Q": "2026Q3", "M": "202607", "W": "2026W29", "D": "20260713"}
    for period, period_baseline in baseline["periods"].items():
        period_baseline.update(
            {
                "period_key_current": current_keys[period],
                "previous_avg_amount_unit": "yuan",
                "trigger_previous_amount_baseline_unit": "yuan",
                "amount_metric": "amount" if period == "D" else "avg_amount",
            }
        )
        isolated_negative_formal_period = (
            identity_key == "stock:SZ:301207" and period == "Y"
        )
        if period not in formal_periods and not isolated_negative_formal_period:
            if direction == "buy":
                period_baseline["trigger_previous_entity_high"] = "12"
            else:
                period_baseline["trigger_previous_entity_low"] = "8"
    if identity_key == "stock:SZ:300308":
        baseline["periods"]["D"].update(
            {
                "previous_transition": "flat",
                "trigger_previous_entity_high": "1108",
                "trigger_previous_entity_low": "1100.01",
                "previous_avg_amount": "38390820848.000",
            }
        )
        baseline["periods"]["W"].update(
            {
                "previous_transition": "flat",
                "trigger_previous_entity_high": "1136.54",
                "trigger_previous_entity_low": "1093.98",
                "previous_avg_amount": "38874708605.14000",
            }
        )
        baseline["periods"]["M"].update(
            {
                "previous_transition": "low_volume_down",
                "trigger_previous_entity_high": "1270",
                "trigger_previous_entity_low": "1161",
                "previous_avg_amount": "38121200575.352380952000",
            }
        )

    direction_entries = {
        period: _production_period_escalation_entry(
            period=period,
            direction=direction,
            status=negative_statuses.get(period, "ready"),
            exact_stock_300308_m=(identity_key == "stock:SZ:300308" and period == "M"),
        )
        for period in PERIOD_ESCALATION_REQUIREMENTS
    }
    escalation_context: dict[str, object] = {
        "contract_version": PERIOD_ESCALATION_CONTEXT_VERSION,
        "source_layer": "N2_condition",
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "for_trade_date": "20260714",
        "source_trade_date": "20260713",
        "directions": {direction: direction_entries},
    }
    escalation_context["context_hash"] = _period_escalation_contract_hash(escalation_context)
    baseline["period_escalation_context"] = escalation_context

    amount_value = 150.0 if direction == "buy" else 50.0
    formal_proof = formal_period_amount_proof_factory(
        periods=formal_periods,
        amount_unit="yuan",
        source_kind="N3_standard_period_metric",
        amount_pass=True,
        amount_value=amount_value,
    )
    price: object = "10.50" if direction == "buy" else "9.50"
    amount: object = amount_value
    if identity_key == "stock:SZ:300308":
        price = "1186.01"
        amount = "34009447460.848"
        formal_proof["amount_chain_metrics"].update(
            {
                "today_virt_amount": 47531495564.42243,
                "weekly_avg_with_today": 42961158206.21121,
                "monthly_avg_with_today": 38897576558.64224,
                "quarterly_avg_with_today": 38897576558.64224,
                "yearly_avg_with_today": 25549359753.321606,
            }
        )
    metric = n3p_metric_row(
        asset_kind,
        identity_key,
        direction=direction,
        formal_period_amount_proof=formal_proof,
        price=price,
        amount=amount,
    )
    metric.update(
        {
            "projection_run_id": PRODUCTION_20260714_1322_METRIC_RUN_ID,
            "source_condition_run_id": PRODUCTION_20260714_SOURCE_CONDITION_RUN_ID,
            "for_trade_date": "20260714",
            "trade_date": "20260714",
            "metric_time": "2026-07-14T13:22:00+08:00",
            "metric_time_label": "2026-07-14 13:22",
            "metric_minute_label": "13:22",
        }
    )
    metric["raw_json"]["closed_minute_proof"]["selected_metric_time"] = (
        "2026-07-14T13:22:00+08:00"
    )
    if identity_key == "stock:SZ:300308":
        metric["action_confirmation_metric_id"] = 10514379
    add_condition_grain_lineage(metric, context)
    return context, metric


def production_20260714_1322_stock_300308_non_same_day_not_seen(
) -> tuple[dict[str, object], dict[str, object]]:
    return production_20260714_1322_negative_evidence_fixture(
        asset_kind="stock",
        identity_key="stock:SZ:300308",
        direction="buy",
        condition_key="BUY:M,W,D",
        formal_periods=("W", "D"),
        negative_statuses={"M": "not_seen"},
    )


class ProvisionalOrdinaryMatcherTest(unittest.TestCase):
    def test_condition_projection_context_is_trace_only_for_ordinary_and_full(self) -> None:
        cases = (
            ("stock", "stock:SH:600000", "buy", "BUY:D", ["BUY"]),
            ("stock", "stock:SH:600001", "sell", "SELL:D", ["SELL"]),
            ("stock", "stock:SH:600002", "buy", "BUY:FULL", ["BUY:FULL"]),
            ("stock", "stock:SH:600003", "sell", "SELL:FULL", ["SELL:FULL"]),
            ("index", "index:SH:000001", "buy", "BUY:D", ["BUY"]),
            ("index", "index:SH:000905", "buy", "BUY:FULL", ["BUY:FULL"]),
            ("board", "board:TDX:BK001", "sell", "SELL:D", ["SELL"]),
            ("board", "board:TDX:BK002", "sell", "SELL:FULL", ["SELL:FULL"]),
        )
        for asset_kind, identity_key, direction, condition_key, signal_types in cases:
            with self.subTest(asset_kind=asset_kind, condition_key=condition_key):
                valid_context = context_row_with_condition_projection(
                    identity_key,
                    direction,
                    condition_key,
                    signal_types,
                    asset_kind=asset_kind,
                )
                invalid_context = copy.deepcopy(valid_context)
                invalid_context["period_trigger_baseline_json"]["condition_projection_context"]["fields"][
                    "close"
                ] = "10.6"
                metric = n3p_metric_row(asset_kind, identity_key, direction=direction)

                valid_plan = build_provisional_ordinary_matcher_plans(
                    trigger_context_run_id=CONTEXT_RUN_ID,
                    source_metric_run_id=N3P_RUN_ID,
                    context_rows=[valid_context],
                    metric_rows=[metric],
                )[0]
                invalid_plan = build_provisional_ordinary_matcher_plans(
                    trigger_context_run_id=CONTEXT_RUN_ID,
                    source_metric_run_id=N3P_RUN_ID,
                    context_rows=[invalid_context],
                    metric_rows=[metric],
                )[0]

                self.assertEqual(valid_plan["condition_projection_context_status"], "ready")
                self.assertEqual(invalid_plan["condition_projection_context_status"], "not_ready")
                self.assertIn(
                    "condition_projection_context_hash_mismatch",
                    invalid_plan["condition_projection_context_trace"]["validation_reasons"],
                )
                self.assertEqual(
                    valid_plan["condition_projection_context"],
                    valid_context["period_trigger_baseline_json"]["condition_projection_context"],
                )
                for field in (
                    "plan_status",
                    "output_event_type",
                    "trigger_type",
                    "trigger_period",
                    "triggered_periods",
                    "signal_type",
                    "candidate_trigger_identity_key",
                ):
                    self.assertEqual(valid_plan.get(field), invalid_plan.get(field), field)

    def test_production_20260714_1322_stock_300308_non_same_day_not_seen(self) -> None:
        context, metric = production_20260714_1322_stock_300308_non_same_day_not_seen()

        plan = build_provisional_ordinary_matcher_plans(
            trigger_context_run_id=SAME_DAY_CONTEXT_RUN_ID,
            source_metric_run_id=PRODUCTION_20260714_1322_METRIC_RUN_ID,
            context_rows=[context],
            metric_rows=[metric],
        )[0]

        assert_same_day_period_escalation_output_contract(plan)
        self.assertEqual(plan["triggered_periods"], ["W"])
        self.assertEqual(plan["all_trigger_periods"], ["W", "D"])
        self.assertEqual(plan["primary_trigger_period"], "W")
        self.assertEqual(plan["prerequisite_periods"], ["D"])
        traces = plan["period_escalation_trace"]["periods"]
        self.assertEqual(traces["M"]["gate_status"], "not_seen")
        self.assertFalse(traces["M"]["gate_pass"])
        self.assertTrue(traces["M"]["evidence_ready"])
        self.assertEqual(
            traces["M"]["source_entry"]["entry_hash"],
            "51bb67f8524412758c8f2cf5f59641194f8f3e6612b839a9245daf41dadd04ed",
        )
        self.assertEqual(traces["W"]["evidence_source"], "current_same_day_formal_pass")
        self.assertEqual(traces["W"]["current_formal_pass_periods"], ["W", "D"])

    def test_20260715_stock_600480_sell_q_same_day_pair_keeps_exact_output_contract(self) -> None:
        context, metric = production_20260714_1322_negative_evidence_fixture(
            asset_kind="stock",
            identity_key="stock:SH:600480",
            direction="sell",
            condition_key="SELL:Y,Q,M",
            formal_periods=("Q", "M"),
            negative_statuses={"Y": "not_ready"},
        )

        plan = build_provisional_ordinary_matcher_plans(
            trigger_context_run_id=SAME_DAY_CONTEXT_RUN_ID,
            source_metric_run_id=PRODUCTION_20260714_1322_METRIC_RUN_ID,
            context_rows=[context],
            metric_rows=[metric],
        )[0]

        assert_same_day_period_escalation_output_contract(plan)
        self.assertEqual(plan["triggered_periods"], ["Q"])
        self.assertEqual(plan["all_trigger_periods"], ["Q", "M"])
        self.assertEqual(plan["primary_trigger_period"], "Q")
        self.assertEqual(plan["prerequisite_periods"], ["M"])
        traces = plan["period_escalation_trace"]["periods"]
        self.assertEqual(traces["Y"]["gate_status"], "not_ready")
        self.assertEqual(traces["Q"]["evidence_source"], "current_same_day_formal_pass")

    def test_lifecycle_output_event_authority_is_stage_specific_and_fail_closed(self) -> None:
        context, metric = production_20260714_1322_negative_evidence_fixture(
            asset_kind="stock",
            identity_key="stock:SH:600048",
            direction="buy",
            condition_key="BUY:Y,Q,M,W,D",
            formal_periods=("W", "D"),
            negative_statuses={"Y": "not_ready", "Q": "not_seen", "M": "not_seen"},
        )
        raw_plan = build_provisional_ordinary_matcher_plans(
            trigger_context_run_id=SAME_DAY_CONTEXT_RUN_ID,
            source_metric_run_id=PRODUCTION_20260714_1322_METRIC_RUN_ID,
            context_rows=[context],
            metric_rows=[metric],
        )[0]
        previous = {
            "asset_kind": raw_plan["asset_kind"],
            "identity_key": raw_plan["identity_key"],
            "direction": raw_plan["direction"],
            "signal_type": raw_plan["signal_type"],
            "condition_key": raw_plan["condition_key"],
            "trigger_period": raw_plan["trigger_period"],
            "current_status": "matched",
            "raw_json": {
                "trigger_type": raw_plan["trigger_type"],
                "trigger_mark_candidate": "legacy_mark",
                "primary_trigger_period": raw_plan["primary_trigger_period"],
                "triggered_periods": raw_plan["triggered_periods"],
                "all_trigger_periods": raw_plan["all_trigger_periods"],
            },
        }

        initial_match = build_lifecycle_output_plans([raw_plan], previous_states=[])[0]
        matched_changed = build_lifecycle_output_plans([raw_plan], previous_states=[previous])[0]
        raw_inactive = copy.deepcopy(raw_plan)
        raw_inactive.update(
            {
                "plan_status": "no_op",
                "output_event_type": None,
                "current_status": "no_op",
                "trigger_live": False,
                "metric_ready": True,
                "projection_status": "ready",
                "projection_quality_status": "passed",
                "trace_status": "passed",
            }
        )
        raw_inactive["rule_eval_result"].update(
            {
                "outcome_classification": "no_op",
                "output_event_type": None,
                "trigger_live": False,
                "pending_reasons": [],
                "quality_reasons": [],
                "blocked_reason": None,
            }
        )
        matched_to_inactive = build_lifecycle_output_plans(
            [raw_inactive], previous_states=[previous]
        )[0]

        for valid in (initial_match, matched_changed, matched_to_inactive):
            assert_same_day_period_escalation_output_contract(valid)
        self.assertEqual(initial_match["output_event_type"], "TriggerMatched")
        self.assertEqual(initial_match["lifecycle_output_reason"], "inactive_to_matched")
        self.assertEqual(matched_changed["output_event_type"], "TriggerStateChanged")
        self.assertEqual(matched_changed["rule_eval_result"]["output_event_type"], "TriggerMatched")
        self.assertEqual(matched_changed["lifecycle_output_reason"], "matched_changed")
        self.assertEqual(matched_to_inactive["output_event_type"], "TriggerStateChanged")
        self.assertIsNone(matched_to_inactive["rule_eval_result"]["output_event_type"])
        self.assertEqual(matched_to_inactive["lifecycle_output_reason"], "matched_to_inactive")

        invalid_plans = []
        for field, value in (
            ("output_event_type", "TriggerMatched"),
            ("current_status", "inactive"),
            ("lifecycle_output_reason", "inactive_to_matched"),
            ("state_change_reason", "tampered"),
            ("previous_status", "inactive"),
            ("writes_trigger_match", True),
        ):
            invalid = copy.deepcopy(matched_changed)
            invalid[field] = value
            invalid_plans.append(invalid)
        previous_alias_tamper = copy.deepcopy(matched_changed)
        previous_alias_tamper["previous_current_status"] = "inactive"
        invalid_plans.append(previous_alias_tamper)
        raw_event_tamper = copy.deepcopy(matched_changed)
        raw_event_tamper["rule_eval_result"]["output_event_type"] = None
        invalid_plans.append(raw_event_tamper)
        raw_outcome_tamper = copy.deepcopy(matched_changed)
        raw_outcome_tamper["rule_eval_result"]["outcome_classification"] = "no_op"
        invalid_plans.append(raw_outcome_tamper)
        forged_rule_proof = copy.deepcopy(matched_changed)
        forged_rule_proof["rule_proof"]["output_event_type"] = "TriggerStateChanged"
        invalid_plans.append(forged_rule_proof)
        shared_field_tamper = copy.deepcopy(matched_changed)
        shared_field_tamper["rule_eval_result"]["all_trigger_periods"] = ["M", "W", "D"]
        invalid_plans.append(shared_field_tamper)

        for invalid in invalid_plans:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    assert_same_day_period_escalation_output_contract(invalid)

    def test_20260715_1017_mixed_same_day_and_n2_context_keeps_terminal_contract(self) -> None:
        cases = (
            (
                "stock:SH:688321",
                "BUY:Y,Q,W",
                ("Y", "Q", "W"),
                ["Y", "W"],
                ["Y", "Q", "W"],
                "Y",
                ["Q", "D"],
                "Y",
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
                "Q",
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
            same_day_period,
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

                plan = build_provisional_ordinary_matcher_plans(
                    trigger_context_run_id=SAME_DAY_CONTEXT_RUN_ID,
                    source_metric_run_id=PRODUCTION_20260714_1322_METRIC_RUN_ID,
                    context_rows=[context],
                    metric_rows=[metric],
                )[0]

                assert_same_day_period_escalation_output_contract(plan)
                self.assertEqual(plan["triggered_periods"], expected_triggered)
                self.assertEqual(plan["all_trigger_periods"], expected_all)
                self.assertEqual(plan["primary_trigger_period"], expected_primary)
                self.assertEqual(plan["prerequisite_periods"], expected_prerequisites)
                traces = plan["period_escalation_trace"]["periods"]
                self.assertEqual(
                    traces[same_day_period]["evidence_source"],
                    "current_same_day_formal_pass",
                )
                self.assertIsNone(traces[same_day_period]["context_contract_version"])
                self.assertIsNone(traces[same_day_period]["context_hash"])
                self.assertEqual(traces["W"]["evidence_source"], "n2_period_escalation_context")
                self.assertEqual(
                    plan["period_escalation_trace"]["context_contract_version"],
                    traces["W"]["context_contract_version"],
                )
                self.assertEqual(
                    plan["period_escalation_trace"]["context_hash"],
                    traces["W"]["context_hash"],
                )
                self.assertEqual("W" in plan["triggered_periods"], w_triggered)

    def test_same_day_q_pair_allows_independent_daily_trigger_without_n2_trace(self) -> None:
        expected_by_formal_periods = {
            ("Q", "M"): (["Q"], ["Q", "M"], "Q", ["M"]),
            ("Q", "M", "D"): (["Q", "D"], ["Q", "M", "D"], "Q", ["M"]),
        }
        for direction in ("buy", "sell"):
            with self.subTest(direction=direction):
                prefix = "BUY" if direction == "buy" else "SELL"
                plans: dict[tuple[str, ...], dict[str, object]] = {}
                contexts: dict[tuple[str, ...], dict[str, object]] = {}
                for formal_periods, expected in expected_by_formal_periods.items():
                    context, metric = production_20260714_1322_negative_evidence_fixture(
                        asset_kind="stock",
                        identity_key="stock:SZ:002414",
                        direction=direction,
                        condition_key=f"{prefix}:Y,Q,M,W,D",
                        formal_periods=formal_periods,
                        negative_statuses={},
                    )
                    plan = build_provisional_ordinary_matcher_plans(
                        trigger_context_run_id=SAME_DAY_CONTEXT_RUN_ID,
                        source_metric_run_id=PRODUCTION_20260714_1322_METRIC_RUN_ID,
                        context_rows=[context],
                        metric_rows=[metric],
                    )[0]

                    assert_same_day_period_escalation_output_contract(plan)
                    self.assertEqual(plan["triggered_periods"], expected[0])
                    self.assertEqual(plan["all_trigger_periods"], expected[1])
                    self.assertEqual(plan["primary_trigger_period"], expected[2])
                    self.assertEqual(plan["prerequisite_periods"], expected[3])
                    self.assertEqual(
                        plan["period_escalation_trace"]["periods"]["Q"]["evidence_source"],
                        "current_same_day_formal_pass",
                    )
                    plans[formal_periods] = plan
                    contexts[formal_periods] = context

                previous_context = contexts[("Q", "M")]["period_trigger_baseline_json"][
                    "period_escalation_context"
                ]
                current_context = contexts[("Q", "M", "D")]["period_trigger_baseline_json"][
                    "period_escalation_context"
                ]
                self.assertEqual(
                    previous_context["context_hash"],
                    current_context["context_hash"],
                )
                self.assertEqual(
                    {
                        period: entry["entry_hash"]
                        for period, entry in previous_context["directions"][direction].items()
                    },
                    {
                        period: entry["entry_hash"]
                        for period, entry in current_context["directions"][direction].items()
                    },
                )

                current = plans[("Q", "M", "D")]
                self.assertNotIn("D", current["period_escalation_trace"]["periods"])
                d_evaluation = next(
                    detail
                    for detail in current["rule_proof"]["period_evaluation_details"]
                    if detail["period"] == "D"
                )
                d_triggered = next(
                    detail
                    for detail in current["rule_proof"]["triggered_period_details"]
                    if detail["period"] == "D"
                )
                self.assertEqual(d_evaluation, d_triggered)
                self.assertEqual(d_evaluation["classification"], "triggered")
                self.assertNotIn("period_escalation_trace", d_evaluation)

    def test_independent_daily_trigger_still_requires_canonical_formal_detail(self) -> None:
        context, metric = production_20260714_1322_negative_evidence_fixture(
            asset_kind="stock",
            identity_key="stock:SZ:002414",
            direction="buy",
            condition_key="BUY:Y,Q,M,W,D",
            formal_periods=("Q", "M", "D"),
            negative_statuses={},
        )
        valid = build_provisional_ordinary_matcher_plans(
            trigger_context_run_id=SAME_DAY_CONTEXT_RUN_ID,
            source_metric_run_id=PRODUCTION_20260714_1322_METRIC_RUN_ID,
            context_rows=[context],
            metric_rows=[metric],
        )[0]

        def mutate_daily_detail(
            plan: dict[str, object],
            field: str,
            value: object,
        ) -> None:
            for detail_field in ("period_evaluation_details", "triggered_period_details"):
                for detail in plan["rule_proof"][detail_field]:
                    if detail["period"] == "D":
                        detail[field] = value

        def remove_daily_from_formal_trace(plan: dict[str, object]) -> None:
            for source in (plan, plan["rule_proof"], plan["rule_eval_result"]):
                source["period_escalation_trace"]["periods"]["Q"][
                    "current_formal_pass_periods"
                ] = ["Q", "M"]
            for detail_field in ("period_evaluation_details", "triggered_period_details"):
                for detail in plan["rule_proof"][detail_field]:
                    if detail["period"] == "Q":
                        detail["period_escalation_trace"]["current_formal_pass_periods"] = [
                            "Q",
                            "M",
                        ]

        for field, value in (
            ("current_transition", "flat"),
            ("transition_amount_pass", False),
            ("trigger_amount_chain_pass", False),
            ("current_amount_metric", None),
            ("used_for_period", "W"),
        ):
            with self.subTest(field=field):
                invalid = copy.deepcopy(valid)
                mutate_daily_detail(invalid, field, value)
                remove_daily_from_formal_trace(invalid)
                with self.assertRaisesRegex(
                    ValueError,
                    "independent_triggered_period_n2_proof_invalid",
                ):
                    assert_same_day_period_escalation_output_contract(invalid)

        for field, value in (
            ("classification", "no_op"),
            ("period", "Z"),
        ):
            with self.subTest(field=field):
                invalid = copy.deepcopy(valid)
                mutate_daily_detail(invalid, field, value)
                with self.assertRaises(ValueError):
                    assert_same_day_period_escalation_output_contract(invalid)

    def test_independent_daily_match_can_deactivate_with_unrelated_q_y_not_ready(self) -> None:
        context, initial_metric = production_20260714_1322_negative_evidence_fixture(
            asset_kind="stock",
            identity_key="stock:SH:601985",
            direction="buy",
            condition_key="BUY:Y,Q,M,W,D",
            formal_periods=("D",),
            negative_statuses={"Q": "not_ready", "Y": "not_ready"},
        )
        initial = build_provisional_ordinary_matcher_plans(
            trigger_context_run_id=SAME_DAY_CONTEXT_RUN_ID,
            source_metric_run_id=PRODUCTION_20260714_1322_METRIC_RUN_ID,
            context_rows=[context],
            metric_rows=[initial_metric],
        )[0]
        initial["for_trade_date"] = "20260714"
        previous = {
            "for_trade_date": "20260714",
            "asset_kind": initial["asset_kind"],
            "identity_key": initial["identity_key"],
            "direction": initial["direction"],
            "signal_type": initial["signal_type"],
            "condition_key": initial["condition_key"],
            "trigger_period": initial["trigger_period"],
            "current_status": "matched",
            "raw_json": copy.deepcopy(initial),
        }

        current_metric = copy.deepcopy(initial_metric)
        current_metric["current_price"] = "9.00"
        current = build_provisional_ordinary_matcher_plans(
            trigger_context_run_id=SAME_DAY_CONTEXT_RUN_ID,
            source_metric_run_id=PRODUCTION_20260714_1322_METRIC_RUN_ID,
            context_rows=[context],
            metric_rows=[current_metric],
        )[0]
        current.update(
            {
                "for_trade_date": "20260714",
                "plan_status": "no_op",
                "output_event_type": None,
                "current_status": "no_op",
                "trigger_live": False,
                "metric_ready": True,
                "data_quality_status": "passed",
                "metric_quality_status": "passed",
            }
        )
        current["rule_eval_result"].update(
            {
                "outcome_classification": "quality_blocked",
                "output_event_type": None,
                "pending_reasons": [],
                "quality_reasons": [
                    "period_escalation_prerequisite_not_ready:Q",
                    "period_escalation_prerequisite_not_ready:Y",
                ],
                "blocked_reason": "period_escalation_prerequisite_not_ready:Q",
            }
        )

        outputs = build_lifecycle_output_plans([current], previous_states=[previous])

        self.assertEqual(len(outputs), 1)
        self.assertEqual(outputs[0]["output_event_type"], "TriggerStateChanged")
        self.assertEqual(outputs[0]["current_status"], "inactive")
        self.assertFalse(outputs[0]["trigger_live"])
        self.assertEqual(outputs[0]["trigger_mark_candidate"], "normal")
        self.assertEqual(outputs[0]["previous_trigger_mark_candidate"], "normal")
        self.assertFalse(outputs[0]["writes_trigger_match"])
        self.assertFalse(outputs[0]["n5_entry_allowed"])

    def test_ready_not_seen_and_not_ready_are_valid_untriggered_audit_states(self) -> None:
        expected_gate_status = {
            "ready": "passed",
            "not_seen": "not_seen",
            "not_ready": "not_ready",
        }
        for status in ("ready", "not_seen", "not_ready"):
            with self.subTest(status=status):
                context, metric = production_20260714_1322_negative_evidence_fixture(
                    asset_kind="stock",
                    identity_key="stock:SH:600480",
                    direction="sell",
                    condition_key="SELL:Y,Q,M",
                    formal_periods=("Q", "M"),
                    negative_statuses={} if status == "ready" else {"Y": status},
                )
                plan = build_provisional_ordinary_matcher_plans(
                    trigger_context_run_id=SAME_DAY_CONTEXT_RUN_ID,
                    source_metric_run_id=PRODUCTION_20260714_1322_METRIC_RUN_ID,
                    context_rows=[context],
                    metric_rows=[metric],
                )[0]

                assert_same_day_period_escalation_output_contract(plan)
                self.assertEqual(plan["triggered_periods"], ["Q"])
                self.assertEqual(plan["all_trigger_periods"], ["Q", "M"])
                self.assertEqual(plan["primary_trigger_period"], "Q")
                self.assertEqual(plan["prerequisite_periods"], ["M"])
                self.assertEqual(
                    plan["period_escalation_trace"]["periods"]["Y"]["gate_status"],
                    expected_gate_status[status],
                )

    def test_20260714_1322_false_positive_state_combinations_keep_terminal_targets(self) -> None:
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
            with self.subTest(identity_key=identity_key, condition_key=condition_key):
                context, metric = production_20260714_1322_negative_evidence_fixture(
                    asset_kind=asset_kind,
                    identity_key=identity_key,
                    direction=direction,
                    condition_key=condition_key,
                    formal_periods=formal_periods,
                    negative_statuses=negative_statuses,
                )
                plan = build_provisional_ordinary_matcher_plans(
                    trigger_context_run_id=SAME_DAY_CONTEXT_RUN_ID,
                    source_metric_run_id=PRODUCTION_20260714_1322_METRIC_RUN_ID,
                    context_rows=[context],
                    metric_rows=[metric],
                )[0]

                assert_same_day_period_escalation_output_contract(plan)
                self.assertEqual(plan["triggered_periods"], expected_triggered)
                self.assertEqual(plan["all_trigger_periods"], expected_all)
                self.assertEqual(plan["primary_trigger_period"], expected_triggered[0])
                self.assertEqual(plan["prerequisite_periods"], expected_prerequisites)
                traces = plan["period_escalation_trace"]["periods"]
                self.assertEqual(
                    {period: traces[period]["gate_status"] for period in negative_statuses},
                    negative_statuses,
                )
                if identity_key == "stock:SZ:301207":
                    self.assertEqual(
                        traces["W"]["current_formal_pass_periods"],
                        ["Y", "W", "D"],
                    )
                    y_detail = next(
                        detail
                        for detail in plan["rule_proof"]["period_evaluation_details"]
                        if detail["period"] == "Y"
                    )
                    self.assertTrue(y_detail["existing_formal_pass"])
                    self.assertEqual(y_detail["classification"], "quality_blocked")

    def test_negative_evidence_state_and_hash_tampering_stays_fail_closed(self) -> None:
        context, metric = production_20260714_1322_stock_300308_non_same_day_not_seen()
        valid = build_provisional_ordinary_matcher_plans(
            trigger_context_run_id=SAME_DAY_CONTEXT_RUN_ID,
            source_metric_run_id=PRODUCTION_20260714_1322_METRIC_RUN_ID,
            context_rows=[context],
            metric_rows=[metric],
        )[0]

        def mutate_m_trace(plan: dict[str, object], mutation) -> None:
            traces = [
                plan["period_escalation_trace"]["periods"]["M"],
                plan["rule_proof"]["period_escalation_trace"]["periods"]["M"],
                plan["rule_eval_result"]["period_escalation_trace"]["periods"]["M"],
            ]
            traces.extend(
                detail["period_escalation_trace"]
                for detail in plan["rule_proof"]["period_evaluation_details"]
                if detail["period"] == "M"
            )
            for trace in traces:
                mutation(trace)

        def mutate_entry(field: str, value: object, *, rehash: bool = True):
            def mutation(trace: dict[str, object]) -> None:
                trace["source_entry"][field] = value
                if rehash:
                    entry = trace["source_entry"]
                    entry.pop("entry_hash", None)
                    entry["entry_hash"] = _period_escalation_contract_hash(entry)

            return mutation

        invalid_plans: list[dict[str, object]] = []
        entry_hash = copy.deepcopy(valid)
        mutate_m_trace(entry_hash, mutate_entry("entry_hash", "tampered", rehash=False))
        invalid_plans.append(entry_hash)

        for field, value in (
            ("status", "ready"),
            ("seen", True),
            ("coverage_status", "incomplete"),
            ("observation_count", 1),
            ("expected_source_trade_date_count", 10),
            ("target_period", "Q"),
            ("window_kind", "quarter"),
            ("window_key", "2026Q3"),
            ("state_epoch_trade_date", "20260630"),
            ("previous_incremental_state_used", False),
            ("previous_incremental_state_used", 1),
        ):
            invalid = copy.deepcopy(valid)
            mutate_m_trace(invalid, mutate_entry(field, value))
            if field in {"status", "seen", "coverage_status", "target_period"}:
                mutate_m_trace(invalid, lambda trace, field=field, value=value: trace.__setitem__(field, value))
            if field == "window_kind":
                mutate_m_trace(invalid, lambda trace: trace.__setitem__("expected_window_kind", "quarter"))
            if field == "window_key":
                mutate_m_trace(invalid, lambda trace: trace.__setitem__("expected_window_key", "2026Q3"))
            invalid_plans.append(invalid)

        for field in ("state_epoch_trade_date", "previous_incremental_state_used"):
            invalid = copy.deepcopy(valid)

            def remove_field(trace: dict[str, object], field: str = field) -> None:
                entry = trace["source_entry"]
                entry.pop(field, None)
                entry.pop("entry_hash", None)
                entry["entry_hash"] = _period_escalation_contract_hash(entry)

            mutate_m_trace(invalid, remove_field)
            invalid_plans.append(invalid)

        for field, value in (
            ("gate_pass", True),
            ("gate_status", "passed"),
            ("evidence_ready", False),
            ("reason", None),
            ("direction", "sell"),
            ("target_period", "Q"),
            ("expected_window_kind", "quarter"),
            ("expected_window_key", "2026Q3"),
        ):
            invalid = copy.deepcopy(valid)
            mutate_m_trace(invalid, lambda trace, field=field, value=value: trace.__setitem__(field, value))
            invalid_plans.append(invalid)

        context_hash = copy.deepcopy(valid)
        context_hash["rule_eval_result"]["period_escalation_trace"]["context_hash"] = "tampered"
        invalid_plans.append(context_hash)

        primary_injection = copy.deepcopy(valid)
        primary_injection["primary_trigger_period"] = "M"
        primary_injection["rule_eval_result"]["primary_trigger_period"] = "M"
        invalid_plans.append(primary_injection)

        for invalid in invalid_plans:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    assert_same_day_period_escalation_output_contract(invalid)

    def test_not_ready_period_cannot_be_injected_as_independent_trigger(self) -> None:
        context, metric = production_20260714_1322_negative_evidence_fixture(
            asset_kind="stock",
            identity_key="stock:SZ:301207",
            direction="buy",
            condition_key="BUY:Y,Q,M,W,D",
            formal_periods=("W", "D"),
            negative_statuses={"Y": "not_ready"},
        )
        invalid = build_provisional_ordinary_matcher_plans(
            trigger_context_run_id=SAME_DAY_CONTEXT_RUN_ID,
            source_metric_run_id=PRODUCTION_20260714_1322_METRIC_RUN_ID,
            context_rows=[context],
            metric_rows=[metric],
        )[0]
        evaluation_details = invalid["rule_proof"]["period_evaluation_details"]
        w_detail = next(detail for detail in evaluation_details if detail["period"] == "W")
        y_trace = next(
            detail["period_escalation_trace"]
            for detail in evaluation_details
            if detail["period"] == "Y"
        )
        y_detail = copy.deepcopy(w_detail)
        y_detail.update(
            {
                "period": "Y",
                "transition_amount_field": "yearly_avg_with_today",
                "amount_metric": "yearly_avg_with_today",
                "used_for_period": "Y",
                "compare_to": "previous_avg_amount[Y]",
                "trigger_amount_chain_pass": "not_applicable",
                "period_escalation_trace": copy.deepcopy(y_trace),
                "prerequisite_periods": [],
            }
        )
        evaluation_details[0] = y_detail
        invalid["rule_proof"]["triggered_period_details"] = [
            copy.deepcopy(y_detail),
            copy.deepcopy(w_detail),
        ]
        for source in (invalid, invalid["rule_eval_result"]):
            source["triggered_periods"] = ["Y", "W"]
            source["all_trigger_periods"] = ["Y", "W", "D"]
            source["primary_trigger_period"] = "Y"

        with self.assertRaises(ValueError):
            assert_same_day_period_escalation_output_contract(invalid)

    def test_same_day_v2_fields_forward_for_all_assets_directions_and_period_chains(self) -> None:
        assets = (
            ("stock", "stock:SH:600000"),
            ("index", "index:SH:000300"),
            ("board", "board:TDX:881001"),
        )
        period_chains = (
            (("W", "D"), ["W"], ["W", "D"], ["D"]),
            (("M", "W"), ["M"], ["M", "W"], ["W"]),
            (("Q", "M"), ["Q"], ["Q", "M"], ["M"]),
            (("Q", "M", "D"), ["Q", "D"], ["Q", "M", "D"], ["M"]),
            (("Y", "Q"), ["Y"], ["Y", "Q"], ["Q"]),
            (("Y", "Q", "D"), ["Y", "D"], ["Y", "Q", "D"], ["Q"]),
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
                            50000.0 if asset_kind == "stock" else (150.0 if direction == "buy" else 50.0)
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

                        plan = build_provisional_ordinary_matcher_plans(
                            trigger_context_run_id=SAME_DAY_CONTEXT_RUN_ID,
                            source_metric_run_id=N3P_RUN_ID,
                            context_rows=[context],
                            metric_rows=[metric],
                        )[0]

                        self.assertEqual(plan["triggered_periods"], expected_triggered)
                        self.assertEqual(plan["all_trigger_periods"], expected_all)
                        self.assertEqual(plan["primary_trigger_period"], expected_triggered[0])
                        self.assertEqual(plan["prerequisite_periods"], expected_prerequisites)
                        self.assertEqual(
                            plan["ordinary_period_escalation_policy_version"],
                            ORDINARY_PERIOD_ESCALATION_POLICY_VERSION,
                        )
                        self.assertEqual(
                            plan["ordinary_period_escalation_policy_hash"],
                            ORDINARY_PERIOD_ESCALATION_POLICY_HASH,
                        )
                        expected_trace_targets = {
                            candidate
                            for candidate, required_period in prerequisite_by_target.items()
                            if candidate in formal_periods and required_period in formal_periods
                        }
                        self.assertEqual(
                            {
                                period
                                for period, trace in plan["period_escalation_trace"]["periods"].items()
                                if trace.get("evidence_source") == "current_same_day_formal_pass"
                            },
                            expected_trace_targets,
                        )
                        self.assertEqual(
                            plan["rule_eval_result"]["prerequisite_periods"],
                            expected_prerequisites,
                        )

    def test_same_day_v2_output_contract_fails_closed_for_missing_or_conflicting_fields(self) -> None:
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
        valid = build_provisional_ordinary_matcher_plans(
            trigger_context_run_id=SAME_DAY_CONTEXT_RUN_ID,
            source_metric_run_id=N3P_RUN_ID,
            context_rows=[context],
            metric_rows=[metric],
        )[0]
        invalid_plans = []
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
        wrong_direction = copy.deepcopy(valid)
        wrong_direction["direction"] = "sell"
        invalid_plans.append(wrong_direction)
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
        multi_valid = build_provisional_ordinary_matcher_plans(
            trigger_context_run_id=SAME_DAY_CONTEXT_RUN_ID,
            source_metric_run_id=N3P_RUN_ID,
            context_rows=[multi_context],
            metric_rows=[multi_metric],
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
        disjoint_valid = build_provisional_ordinary_matcher_plans(
            trigger_context_run_id=SAME_DAY_CONTEXT_RUN_ID,
            source_metric_run_id=N3P_RUN_ID,
            context_rows=[disjoint_context],
            metric_rows=[disjoint_metric],
        )[0]
        invalid_plans.extend(same_day_fail_closed_mutations(multi_valid, disjoint_valid))

        for invalid in invalid_plans:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    assert_same_day_period_escalation_output_contract(invalid)

    def test_buy_sell_and_full_conditions_match_from_n3p_metric_rows(self) -> None:
        context_rows = [
            context_row("stock:SH:600000", "buy", "BUY:D", ["BUY"]),
            context_row("stock:SH:600001", "sell", "SELL:D", ["SELL"]),
            context_row("stock:SH:600002", "buy", "BUY:FULL", ["BUY:FULL"]),
            context_row("stock:SH:600003", "sell", "SELL:FULL", ["SELL:FULL"]),
        ]
        metric_rows = [
            n3p_metric_row("stock", "stock:SH:600000", direction="buy"),
            n3p_metric_row("stock", "stock:SH:600001", direction="sell"),
            n3p_metric_row("stock", "stock:SH:600002", direction="buy"),
            n3p_metric_row("stock", "stock:SH:600003", direction="sell"),
        ]

        plans = build_provisional_ordinary_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            source_metric_run_id=N3P_RUN_ID,
            context_rows=context_rows,
            metric_rows=metric_rows,
        )
        summary = summarize_provisional_ordinary_matcher_plans(plans)

        self.assertEqual(summary["candidate_count"], 4)
        self.assertEqual(summary["matched_count"], 4)
        self.assertEqual(summary["matched_by_trigger_type"], {"BUY": 1, "BUY:FULL": 1, "SELL": 1, "SELL:FULL": 1})
        self.assertEqual({plan["output_event_type"] for plan in plans}, {"TriggerMatched"})
        self.assertEqual({plan["source_metric_kind"] for plan in plans}, {"realtime_action_confirmation_metric"})
        self.assertEqual({plan["source_metric_run_id"] for plan in plans}, {N3P_RUN_ID})
        self.assertEqual({plan["trigger_mark_candidate"] for plan in plans}, {"normal"})
        self.assertTrue(all(plan["provisional"] is True for plan in plans))
        self.assertTrue(all(plan["selected_metric_id"] is not None for plan in plans))
        self.assertTrue(all(plan["selected_metric_time"] == "2026-06-24T13:52:00+08:00" for plan in plans))
        self.assertTrue(all(plan["metric_minute_label"] == "13:52" for plan in plans))
        self.assertTrue(all(plan["rule_eval_result"]["output_event_type"] == "TriggerMatched" for plan in plans))
        self.assertTrue(all(plan["candidate_trigger_identity_key"] for plan in plans))

    def test_full_conditions_match_current_state_without_transition_upgrade(self) -> None:
        buy_context = context_row("stock:SH:600002", "buy", "BUY:FULL", ["BUY:FULL"])
        sell_context = context_row("stock:SH:600003", "sell", "SELL:FULL", ["SELL:FULL"])
        buy_context["period_trigger_baseline_json"]["periods"]["D"]["previous_transition"] = "volume_up"
        sell_context["period_trigger_baseline_json"]["periods"]["D"]["previous_transition"] = "low_volume_down"

        plans = build_provisional_ordinary_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            source_metric_run_id=N3P_RUN_ID,
            context_rows=[buy_context, sell_context],
            metric_rows=[
                n3p_metric_row("stock", "stock:SH:600002", direction="buy"),
                n3p_metric_row("stock", "stock:SH:600003", direction="sell"),
            ],
        )

        self.assertEqual({plan["trigger_type"] for plan in plans}, {"BUY:FULL", "SELL:FULL"})
        self.assertEqual({plan["output_event_type"] for plan in plans}, {"TriggerMatched"})
        self.assertEqual({plan["rule_eval_result"]["outcome_classification"] for plan in plans}, {"matched"})

    def test_ordinary_buy_sell_still_need_transition_upgrade(self) -> None:
        buy_context = context_row("stock:SH:600000", "buy", "BUY:D", ["BUY"])
        sell_context = context_row("stock:SH:600001", "sell", "SELL:D", ["SELL"])
        buy_context["period_trigger_baseline_json"]["periods"]["D"]["previous_transition"] = "volume_up"
        sell_context["period_trigger_baseline_json"]["periods"]["D"]["previous_transition"] = "low_volume_down"

        plans = build_provisional_ordinary_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            source_metric_run_id=N3P_RUN_ID,
            context_rows=[buy_context, sell_context],
            metric_rows=[
                n3p_metric_row("stock", "stock:SH:600000", direction="buy"),
                n3p_metric_row("stock", "stock:SH:600001", direction="sell"),
            ],
        )

        self.assertEqual({plan["trigger_type"] for plan in plans}, {"BUY", "SELL"})
        self.assertEqual({plan["output_event_type"] for plan in plans}, {None})
        self.assertEqual({plan["rule_eval_result"]["outcome_classification"] for plan in plans}, {"no_op"})

    def test_buy_hint_and_sell_hint_are_isolated_from_ordinary_matcher(self) -> None:
        plans = build_provisional_ordinary_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            source_metric_run_id=N3P_RUN_ID,
            context_rows=[
                context_row("stock:SH:600000", "buy", "BUY_HINT", ["BUY_HINT"]),
                context_row("stock:SH:600001", "sell", "SELL_HINT", ["SELL_HINT"]),
                context_row("stock:SH:600002", "buy", "BUY:D", ["BUY"]),
            ],
            metric_rows=[
                n3p_metric_row("stock", "stock:SH:600000", direction="buy"),
                n3p_metric_row("stock", "stock:SH:600001", direction="sell"),
                n3p_metric_row("stock", "stock:SH:600002", direction="buy"),
            ],
        )

        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["condition_key"], "BUY:D")
        self.assertNotIn("BUY_HINT", {plan["condition_key"] for plan in plans})
        self.assertNotIn("SELL_HINT", {plan["condition_key"] for plan in plans})

    def test_n3p_json_condition_grain_lineage_selects_matching_metric(self) -> None:
        buy_context = context_row("stock:SH:600000", "buy", "BUY:D", ["BUY"])
        sell_context = context_row("stock:SH:600000", "sell", "SELL:D", ["SELL"])
        buy_metric = n3p_metric_row("stock", "stock:SH:600000", direction="buy")
        sell_metric = n3p_metric_row("stock", "stock:SH:600000", direction="sell")
        add_condition_grain_lineage(buy_metric, buy_context)
        add_condition_grain_lineage(sell_metric, sell_context)

        plans = build_provisional_ordinary_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            source_metric_run_id=N3P_RUN_ID,
            context_rows=[buy_context, sell_context],
            metric_rows=[buy_metric, sell_metric],
        )

        self.assertEqual(len(plans), 2)
        selected_by_condition = {plan["condition_key"]: plan["selected_metric_id"] for plan in plans}
        self.assertEqual(selected_by_condition["BUY:D"], buy_metric["action_confirmation_metric_id"])
        self.assertEqual(selected_by_condition["SELL:D"], sell_metric["action_confirmation_metric_id"])
        self.assertEqual({plan["output_event_type"] for plan in plans}, {"TriggerMatched"})

    def test_n3p_json_condition_grain_lineage_does_not_fallback_to_identity(self) -> None:
        buy_context = context_row("stock:SH:600000", "buy", "BUY:D", ["BUY"])
        sell_context = context_row("stock:SH:600000", "sell", "SELL:D", ["SELL"])
        sell_metric = n3p_metric_row("stock", "stock:SH:600000", direction="sell")
        add_condition_grain_lineage(sell_metric, sell_context)

        plans = build_provisional_ordinary_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            source_metric_run_id=N3P_RUN_ID,
            context_rows=[buy_context, sell_context],
            metric_rows=[sell_metric],
        )

        plan_by_condition = {plan["condition_key"]: plan for plan in plans}
        self.assertIsNone(plan_by_condition["BUY:D"]["selected_metric_id"])
        self.assertIsNone(plan_by_condition["BUY:D"]["output_event_type"])
        self.assertEqual(plan_by_condition["SELL:D"]["selected_metric_id"], sell_metric["action_confirmation_metric_id"])
        self.assertEqual(plan_by_condition["SELL:D"]["output_event_type"], "TriggerMatched")

    def test_unclosed_minute_can_match_but_preserves_is_closed_false(self) -> None:
        plans = build_provisional_ordinary_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            source_metric_run_id=N3P_RUN_ID,
            context_rows=[context_row("stock:SH:600000", "buy", "BUY:D", ["BUY"])],
            metric_rows=[n3p_metric_row("stock", "stock:SH:600000", direction="buy", is_closed_1m=False)],
        )

        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["output_event_type"], "TriggerMatched")
        self.assertFalse(plans[0]["is_closed_1m"])
        self.assertFalse(plans[0]["rule_proof"]["selected_metric"]["is_closed_1m"])

    def test_live_current_1m_source_mode_is_preserved_for_n4p_payload(self) -> None:
        plans = build_provisional_ordinary_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            source_metric_run_id=N3P_RUN_ID,
            context_rows=[context_row("stock:SH:600000", "buy", "BUY:D", ["BUY"])],
            metric_rows=[
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

        self.assertEqual(plans[0]["output_event_type"], "TriggerMatched")
        self.assertEqual(plans[0]["source_mode"], "live_current_1m")
        self.assertFalse(plans[0]["c1_dependency"])
        self.assertEqual(plans[0]["trace"]["source_mode"], "live_current_1m")
        self.assertFalse(plans[0]["trace"]["c1_dependency"])

    def test_adapter_reuses_rule_v4_input_shape_without_b2_projection_metric(self) -> None:
        metric = n3p_metric_row("stock", "stock:SH:600000", direction="buy")
        adapted = adapt_n3p_metric_row_for_rule_v4(
            metric,
            context_row=context_row("stock:SH:600000", "buy", "BUY:D", ["BUY"]),
        )

        self.assertEqual(adapted["projection_run_id"], N3P_RUN_ID)
        self.assertEqual(adapted["current_price_or_close"], "10.50")
        self.assertEqual(adapted["current_amount_metric_source_kind"], "N3_standard_period_metric")
        self.assertEqual(adapted["trigger_amount_chain_pass"], {"D": True})
        self.assertEqual(adapted["projection_30m_type"], "none")
        self.assertEqual(adapted["source_metric_kind"], "realtime_action_confirmation_metric")

    def test_adapter_reads_n3p_formal_amount_proof_for_multi_period_chain(self) -> None:
        context = context_row("stock:SH:600000", "buy", "BUY:Y,Q,M,W,D", ["BUY"])
        metric = n3p_metric_row(
            "stock",
            "stock:SH:600000",
            direction="buy",
            trigger_amount_chain_pass=None,
            formal_period_amount_proof=formal_period_amount_proof_factory(
                periods=("Y", "Q", "M", "W", "D"),
                amount_unit="yuan",
                source_kind="N3_standard_period_metric",
                amount_pass=True,
            ),
        )
        metric["current_d_virtual_amount"] = 999.0

        adapted = adapt_n3p_metric_row_for_rule_v4(metric, context_row=context)

        self.assertEqual(adapted["current_amount_metric_unit"], "yuan")
        self.assertEqual(adapted["amount_unit"], "yuan")
        self.assertEqual(adapted["current_amount_metric_source_kind"], "N3_standard_period_metric")
        self.assertEqual(adapted["today_virt_amount"], 150.0)
        self.assertEqual(adapted["weekly_avg_with_today"], 150.0)
        self.assertEqual(adapted["monthly_avg_with_today"], 150.0)
        self.assertEqual(adapted["quarterly_avg_with_today"], 150.0)
        self.assertEqual(adapted["yearly_avg_with_today"], 150.0)
        self.assertEqual(
            adapted["trigger_amount_chain_pass"],
            {"Y": "not_applicable", "Q": True, "M": True, "W": True, "D": True},
        )
        self.assertEqual(adapted["trigger_amount_chain_pass"]["Y"], "not_applicable")

    def test_adapter_does_not_infer_formal_unit_without_trusted_formal_proof(self) -> None:
        context = context_row("stock:SH:600000", "buy", "BUY:Y,Q,M,W,D", ["BUY"])
        metric = n3p_metric_row(
            "stock",
            "stock:SH:600000",
            direction="buy",
            trigger_amount_chain_pass=None,
            include_amount_unit_fields=False,
            formal_period_amount_proof=formal_period_amount_proof_factory(
                periods=("Y", "Q", "M", "W", "D"),
                amount_unit=None,
                source_kind=None,
                amount_pass=True,
            ),
        )

        adapted = adapt_n3p_metric_row_for_rule_v4(metric, context_row=context)

        self.assertIsNone(adapted.get("current_amount_metric_unit"))
        self.assertIsNone(adapted.get("amount_unit"))
        self.assertNotEqual(adapted.get("current_amount_metric_source_kind"), "N3_standard_period_metric")
        self.assertEqual(adapted["trigger_amount_chain_pass"], {})

    def test_multi_period_formal_amount_proof_allows_rule_v4_match(self) -> None:
        context = context_row("stock:SH:600000", "buy", "BUY:Y,Q,M,W,D", ["BUY"])
        metric = n3p_metric_row(
            "stock",
            "stock:SH:600000",
            direction="buy",
            trigger_amount_chain_pass=None,
            formal_period_amount_proof=formal_period_amount_proof_factory(
                periods=("Y", "Q", "M", "W", "D"),
                amount_unit="yuan",
                source_kind="N3_standard_period_metric",
                amount_pass=True,
                amount_value=150000.0,
            ),
        )

        plans = build_provisional_ordinary_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            source_metric_run_id=N3P_RUN_ID,
            context_rows=[context],
            metric_rows=[metric],
        )

        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["output_event_type"], "TriggerMatched")
        self.assertEqual(plans[0]["triggered_periods"], ["Y", "Q", "M", "W", "D"])
        self.assertEqual(
            plans[0]["rule_proof"]["period_evaluation_details"][0]["trigger_amount_chain_pass"],
            "not_applicable",
        )

    def test_dry_run_report_has_required_side_effect_guard(self) -> None:
        report = build_provisional_ordinary_matcher_dry_run_report(
            trigger_context_run_id=CONTEXT_RUN_ID,
            source_metric_run_id=N3P_RUN_ID,
            context_rows=[context_row("stock:SH:600000", "buy", "BUY:D", ["BUY"])],
            metric_rows=[n3p_metric_row("stock", "stock:SH:600000", direction="buy")],
        )

        self.assertEqual(report["result"], "DRY_RUN_PASS")
        self.assertEqual(report["summary"]["matched_count"], 1)
        self.assertFalse(report["side_effect_guard"]["db_written"])
        self.assertFalse(report["side_effect_guard"]["outbox_written"])
        self.assertFalse(report["side_effect_guard"]["inbox_written"])
        self.assertFalse(report["side_effect_guard"]["checkpoint_written"])
        self.assertFalse(report["side_effect_guard"]["n5_executed"])
        self.assertFalse(report["side_effect_guard"]["n6_written"])
        self.assertFalse(report["side_effect_guard"]["sim_trade_virtual_written"])

    def test_stock_buy_full_converts_missing_n2_unit_and_rejects_300759_false_match(self) -> None:
        context = context_row("stock:SZ:300759", "buy", "BUY:FULL", ["BUY:FULL"])
        baseline = context["period_trigger_baseline_json"]["periods"]["D"]
        baseline.update(
            {
                "previous_transition": "flat",
                "trigger_previous_entity_high": "33.90",
                "trigger_previous_entity_low": "32.00",
                "previous_avg_amount": "3394611.01782",
            }
        )
        metric = n3p_metric_row(
            "stock",
            "stock:SZ:300759",
            direction="buy",
            price="34.05",
            amount="2752606058.850448",
            formal_period_amount_proof=formal_period_amount_proof_factory(
                periods=("D",),
                amount_unit="yuan",
                source_kind="N3_standard_period_metric",
                amount_pass=True,
                amount_value=2752606058.850448,
            ),
        )

        plan = build_provisional_ordinary_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            source_metric_run_id=N3P_RUN_ID,
            context_rows=[context],
            metric_rows=[metric],
        )[0]

        detail = plan["rule_proof"]["period_evaluation_details"][0]
        trace = detail["amount_unit_status"]["amount_normalization_trace"]
        self.assertIsNone(plan["output_event_type"])
        self.assertEqual(detail["current_transition"], "low_volume_up")
        self.assertFalse(detail["transition_amount_pass"])
        self.assertAlmostEqual(detail["previous_amount_baseline"], 3394611017.82)
        self.assertEqual(trace["source_unit"], "thousand_yuan")
        self.assertEqual(trace["n2_baseline_unit_conversion_factor"], 1000)
        self.assertEqual(trace["canonical_unit"], "yuan")

    def test_stock_missing_units_convert_for_all_ordinary_periods(self) -> None:
        context = context_row("stock:SZ:300001", "buy", "BUY:Y,Q,M,W,D", ["BUY"])
        for baseline in context["period_trigger_baseline_json"]["periods"].values():
            baseline["previous_avg_amount"] = "100"
        metric = n3p_metric_row(
            "stock",
            "stock:SZ:300001",
            direction="buy",
            price="11",
            amount="150000",
            formal_period_amount_proof=formal_period_amount_proof_factory(
                periods=("Y", "Q", "M", "W", "D"),
                amount_unit="yuan",
                source_kind="N3_standard_period_metric",
                amount_pass=True,
                amount_value=150000.0,
            ),
        )

        plan = build_provisional_ordinary_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            source_metric_run_id=N3P_RUN_ID,
            context_rows=[context],
            metric_rows=[metric],
        )[0]

        self.assertEqual(plan["output_event_type"], "TriggerMatched")
        self.assertEqual(plan["triggered_periods"], ["Y", "Q", "M", "W", "D"])
        for detail in plan["rule_proof"]["period_evaluation_details"]:
            trace = detail["amount_unit_status"]["amount_normalization_trace"]
            self.assertEqual(detail["previous_amount_baseline"], 100000.0)
            self.assertEqual(trace["source_unit"], "thousand_yuan")
            self.assertEqual(trace["n2_baseline_unit_conversion_factor"], 1000)

    def test_stock_sell_and_sell_full_use_converted_baseline(self) -> None:
        contexts = [
            context_row("stock:SZ:300002", "sell", "SELL:Y,Q,M,W,D", ["SELL"]),
            context_row("stock:SZ:300003", "sell", "SELL:FULL", ["SELL:FULL"]),
        ]
        for context in contexts:
            for baseline in context["period_trigger_baseline_json"]["periods"].values():
                baseline["previous_avg_amount"] = "100"
        metrics = [
            n3p_metric_row(
                "stock",
                "stock:SZ:300002",
                direction="sell",
                amount="50000",
                formal_period_amount_proof=formal_period_amount_proof_factory(
                    periods=("Y", "Q", "M", "W", "D"),
                    amount_unit="yuan",
                    source_kind="N3_standard_period_metric",
                    amount_pass=True,
                    amount_value=50000.0,
                ),
            ),
            n3p_metric_row("stock", "stock:SZ:300003", direction="sell", amount="50000"),
        ]

        plans = build_provisional_ordinary_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            source_metric_run_id=N3P_RUN_ID,
            context_rows=contexts,
            metric_rows=metrics,
        )

        self.assertEqual({plan["output_event_type"] for plan in plans}, {"TriggerMatched"})
        self.assertEqual({plan["trigger_type"] for plan in plans}, {"SELL", "SELL:FULL"})
        self.assertEqual(plans[0]["triggered_periods"], ["Y", "Q", "M", "W", "D"])
        self.assertEqual(plans[1]["triggered_periods"], ["D"])
        self.assertTrue(
            all(
                plan["rule_proof"]["period_evaluation_details"][0]["current_transition"]
                == "low_volume_down"
                for plan in plans
            )
        )

    def test_explicit_yuan_and_index_board_missing_units_do_not_double_convert(self) -> None:
        contexts = [
            context_row("stock:SZ:300004", "buy", "BUY:D", ["BUY"]),
            context_row("index:SH:000016", "buy", "BUY:D", ["BUY"], asset_kind="index"),
            context_row("board:TDX:BK001", "buy", "BUY:D", ["BUY"], asset_kind="board"),
        ]
        stock_baseline = contexts[0]["period_trigger_baseline_json"]["periods"]["D"]
        stock_baseline["previous_avg_amount"] = "100"
        stock_baseline["previous_avg_amount_unit"] = "yuan"
        metrics = [
            n3p_metric_row(str(context["asset_kind"]), str(context["identity_key"]), direction="buy", amount="150")
            for context in contexts
        ]

        plans = build_provisional_ordinary_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            source_metric_run_id=N3P_RUN_ID,
            context_rows=contexts,
            metric_rows=metrics,
        )

        self.assertEqual({plan["output_event_type"] for plan in plans}, {"TriggerMatched"})
        for plan in plans:
            detail = plan["rule_proof"]["period_evaluation_details"][0]
            trace = detail["amount_unit_status"]["amount_normalization_trace"]
            self.assertEqual(detail["previous_amount_baseline"], 100.0)
            self.assertEqual(trace["n2_baseline_unit_conversion_factor"], 1)
            self.assertEqual(trace["canonical_unit"], "yuan")

    def test_unsupported_n2_amount_unit_fails_closed(self) -> None:
        context = context_row("stock:SZ:300005", "buy", "BUY:D", ["BUY"])
        baseline = context["period_trigger_baseline_json"]["periods"]["D"]
        baseline["previous_avg_amount"] = "100"
        baseline["previous_avg_amount_unit"] = "wan_yuan"

        plan = build_provisional_ordinary_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            source_metric_run_id=N3P_RUN_ID,
            context_rows=[context],
            metric_rows=[n3p_metric_row("stock", "stock:SZ:300005", direction="buy", amount="150")],
        )[0]

        detail = plan["rule_proof"]["period_evaluation_details"][0]
        trace = detail["amount_unit_status"]["amount_normalization_trace"]
        self.assertIsNone(plan["output_event_type"])
        self.assertEqual(detail["classification"], "pending")
        self.assertEqual(detail["amount_unit_status"]["status"], "mismatch")
        self.assertEqual(trace["unit_conversion_policy"], "unsupported_n2_period_trigger_baseline_amount_unit")

    def test_rule_reuse_and_b2_hint_module_isolation_static_guard(self) -> None:
        from ashare_v3.trigger import projection_matcher
        from ashare_v3.trigger import provisional_ordinary_execute
        import ashare_v3.trigger.provisional_ordinary_matcher as ordinary_matcher
        from ashare_v3.trigger import provisional_projection_execute

        module_source = inspect.getsource(ordinary_matcher)
        b2_module_source = inspect.getsource(provisional_projection_matcher)
        passthrough_source = "\n".join(
            inspect.getsource(module)
            for module in (
                projection_matcher,
                ordinary_matcher,
                provisional_ordinary_execute,
                provisional_projection_matcher,
                provisional_projection_execute,
            )
        )

        self.assertIn("evaluate_v4_plan", module_source)
        self.assertNotIn("stock_realtime_projection_metric", module_source)
        self.assertNotIn("index_realtime_projection_metric", module_source)
        self.assertNotIn("board_realtime_projection_metric", module_source)
        self.assertNotIn("common_event_outbox", module_source)
        self.assertNotIn("common_event_inbox", module_source)
        self.assertIn("build_provisional_projection_matcher_plans", b2_module_source)
        for forbidden in (
            "stock_condition_basis",
            "index_condition_basis",
            "board_condition_basis",
            "stock_daily_bar_fact",
            "index_daily_bar_fact",
            "board_daily_bar_fact",
        ):
            self.assertNotIn(forbidden, passthrough_source)


def n3p_metric_row(
    asset_kind: str,
    identity_key: str,
    *,
    direction: str,
    is_closed_1m: bool = True,
    trigger_amount_chain_pass: dict[str, bool] | None = None,
    formal_period_amount_proof: dict[str, object] | None = None,
    include_amount_unit_fields: bool = True,
    source_mode: str | None = None,
    c1_dependency: bool | None = None,
    price: object | None = None,
    amount: object | None = None,
) -> dict[str, object]:
    price = price if price is not None else ("10.50" if direction == "buy" else "9.50")
    if amount is None:
        if asset_kind == "stock":
            amount = "150000" if direction == "buy" else "50000"
        else:
            amount = "150" if direction == "buy" else "50"
    if trigger_amount_chain_pass is None and formal_period_amount_proof is None:
        trigger_amount_chain_pass = {"D": True}
        formal_period_amount_proof = formal_period_amount_proof_factory(
            periods=("D",),
            amount_unit="yuan",
            source_kind="N3_standard_period_metric",
            amount_pass=True,
            amount_value=float(amount),
        )
    row = {
        "action_confirmation_metric_id": stable_int(identity_key + direction + "n3p_metric"),
        "projection_run_id": N3P_RUN_ID,
        "projection_schema_version": "v3.realtime_virtual_metric.writer.v1",
        "source_condition_run_id": "condition_layer_20260623_source_20260623_for_20260624_v1",
        "source_subscription_run_id": "market_data_subscription_20260624_condition_layer_20260623_source_20260623_for_20260624_v1",
        "source_snapshot_run_id": "realtime_daily_snapshot_20260624_until_1352__market_data_subscription_20260624_condition_layer_20260623_source_20260623_for_20260624_v1",
        "source_today_minute_run_id": "today_minute_bar_1m_20260624_until_1352__market_data_subscription_20260624_condition_layer_20260623_source_20260623_for_20260624_v1",
        "source_previous_day_minute_run_id": "previous_day_minute_preload_20260623_for_20260624__market_data_subscription_20260624_condition_layer_20260623_source_20260623_for_20260624_v1",
        "for_trade_date": "20260624",
        "trade_date": "20260624",
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "display_code": identity_key.rsplit(":", 1)[-1],
        "name": identity_key,
        "metric_time": "2026-06-24T13:52:00+08:00",
        "metric_time_label": "2026-06-24 13:52",
        "metric_minute_label": "13:52",
        "is_closed_1m": is_closed_1m,
        "metric_ready": True,
        "metric_quality_status": "passed",
        "current_price": price,
        "current_d_virtual_amount": amount,
        "raw_json": {
            "closed_minute_proof": {
                "selected_metric_time": "2026-06-24T13:52:00+08:00",
                "is_closed_1m": is_closed_1m,
            }
        },
        "trace_json": {},
    }
    if source_mode is not None:
        row["raw_json"]["source_mode"] = source_mode
        row["raw_json"]["closed_minute_proof"]["source_mode"] = source_mode
        row["trace_json"]["source_mode"] = source_mode
        row["source_fact_ids"] = {"source_mode": source_mode}
    if c1_dependency is not None:
        row["raw_json"]["c1_dependency"] = c1_dependency
        row["raw_json"]["closed_minute_proof"]["c1_dependency"] = c1_dependency
        row["trace_json"]["c1_dependency"] = c1_dependency
        row.setdefault("source_fact_ids", {})["c1_dependency"] = c1_dependency
    if trigger_amount_chain_pass is not None:
        row["trigger_amount_chain_pass"] = trigger_amount_chain_pass
    if include_amount_unit_fields:
        row["current_amount_metric_unit"] = "yuan"
        row["current_amount_metric_source_kind"] = "N3_standard_period_metric"
    if formal_period_amount_proof is not None:
        row["trace_json"].update(
            {
                "formal_period_amount_proof": formal_period_amount_proof,
                "formal_amount_chain_metrics": formal_period_amount_proof.get("amount_chain_metrics", {}),
            }
        )
    return row


def add_condition_grain_lineage(metric: dict[str, object], context: dict[str, object]) -> None:
    lineage = {
        "source_condition_pool_id": context["source_condition_pool_id"],
        "source_condition_basis_id": context["source_condition_basis_id"],
        "source_minute_target_scope_id": context["source_minute_target_scope_id"],
    }
    metric["raw_json"]["condition_key"] = context["condition_key"]
    metric["raw_json"]["higher_period_context_source"] = dict(lineage)
    metric["raw_json"]["b1_source_returned_payload_selection"] = {
        "selection_policy": "n4_context_condition_grain_expands_b1_object_snapshot",
        "source_condition_pool_id": context["source_condition_pool_id"],
        "source_minute_target_scope_id": context["source_minute_target_scope_id"],
    }
    metric["trace_json"]["higher_period_context_source"] = dict(lineage)


def formal_period_amount_proof_factory(
    *,
    periods: tuple[str, ...],
    amount_unit: str | None,
    source_kind: str | None,
    amount_pass: bool,
    amount_value: float = 150.0,
) -> dict[str, object]:
    return {
        "source_kind": source_kind,
        "amount_unit": amount_unit,
        "amount_chain_metrics": {
            "today_virt_amount": amount_value,
            "weekly_avg_with_today": amount_value,
            "monthly_avg_with_today": amount_value,
            "quarterly_avg_with_today": amount_value,
            "yearly_avg_with_today": amount_value,
        },
        "periods": {
            period: {
                "current_amount_source_kind": source_kind,
                "current_amount_unit": amount_unit,
                "amount_unit": amount_unit,
                "avg_status": "passed",
                "amount_pass": amount_pass,
                "trigger_amount_chain_pass": amount_pass,
            }
            for period in periods
        },
    }


if __name__ == "__main__":
    unittest.main()
