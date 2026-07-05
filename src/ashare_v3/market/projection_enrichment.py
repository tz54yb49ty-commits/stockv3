"""N3 projection enrichment payload helpers for N4 v4.

The helpers are pure functions. They do not read or write the database, pull
market data, write outbox/inbox/checkpoint rows, or enter downstream layers.
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping


PROJECTION_ENRICHMENT_VERSION = "n3.projection_enrichment.v1"
PROJECTION_ENRICHMENT_REQUIRED_FIELDS = (
    "current_price_or_close",
    "current_amount_metric",
    "current_metric_time",
    "current_metric_quality_status",
    "projection_period",
    "projection_30m_flag",
    "projection_30m_type",
    "current_30m_virtual_amount",
    "reference_30m_amount",
    "reference_30m_entity_high",
    "reference_30m_entity_low",
    "trigger_amount_chain_pass",
    "projection_lineage_json",
    "source_freshness_status",
    "source_snapshot_run_id",
    "source_minute_run_id",
    "source_previous_day_minute_run_id",
)

PERIODS = ("Y", "Q", "M", "W", "D")
TRIGGER_AMOUNT_CHAIN_INPUTS = (
    "N2 period_trigger_baseline_json",
    "N3 current_chain_metrics",
)


def build_projection_enrichment_v1(
    *,
    metric_row: Mapping[str, Any],
    n2_context: Mapping[str, Any] | None = None,
    current_chain_metrics: Mapping[str, Any] | None = None,
    current_30m_virtual_amount: Any = None,
    reference_30m_amount: Any = None,
    reference_30m_entity_high: Any = None,
    reference_30m_entity_low: Any = None,
) -> dict[str, Any]:
    """Build the N4-facing projection enrichment payload.

    The payload is intended to live in ``raw_json.enrichment_v1`` until a later
    gate decides whether additive physical columns are needed.
    """

    current_price = decimal_or_none(metric_row.get("current_price") or metric_row.get("close"))
    current_30m = decimal_or_none(current_30m_virtual_amount)
    reference_amount = decimal_or_none(reference_30m_amount)
    reference_high = decimal_or_none(reference_30m_entity_high)
    reference_low = decimal_or_none(reference_30m_entity_low)
    projection_type = classify_projection_30m(
        current_price=current_price,
        current_30m_virtual_amount=current_30m,
        reference_30m_amount=reference_amount,
        reference_30m_entity_high=reference_high,
        reference_30m_entity_low=reference_low,
    )
    projection_flag = projection_type in {"volume_up", "shrink_down"}
    source_snapshot_run_id = metric_row.get("source_snapshot_run_id")
    source_minute_run_id = metric_row.get("source_today_minute_run_id") or metric_row.get("source_minute_run_id")
    source_previous_day_minute_run_id = metric_row.get("source_previous_day_minute_run_id")
    source_trace = source_mode_trace(metric_row)
    metric_quality_status = str(metric_row.get("metric_quality_status") or "missing")
    current_metric_time = metric_row.get("metric_time") or metric_row.get("current_price_time")
    current_amount_metric = current_30m if current_30m is not None else decimal_or_none(
        metric_row.get("current_5m_virtual_amount") or metric_row.get("current_1m_amount")
    )
    trigger_amount_chain_pass = build_trigger_amount_chain_pass(
        n2_context=n2_context,
        current_chain_metrics=current_chain_metrics,
        projection_30m_pass=projection_flag,
    )
    lineage = {
        "contract_version": PROJECTION_ENRICHMENT_VERSION,
        "source_condition_run_id": metric_row.get("source_condition_run_id"),
        "source_subscription_run_id": metric_row.get("source_subscription_run_id"),
        "source_snapshot_run_id": source_snapshot_run_id,
        "source_minute_run_id": source_minute_run_id,
        "source_previous_day_minute_run_id": source_previous_day_minute_run_id,
        "n2_baseline_refs": summarize_n2_baseline_refs(n2_context),
        "source_fact_ids": metric_row.get("source_fact_ids") or {},
        "source_minute_refs": metric_row.get("source_minute_refs") or [],
        "previous_day_minute_refs": metric_row.get("previous_day_minute_refs") or [],
        "calculation_config_hash": metric_row.get("calculation_config_hash"),
        "n4_recompute_allowed": False,
        **source_trace,
    }
    return {
        "current_price_or_close": json_number(current_price),
        "current_amount_metric": json_number(current_amount_metric),
        "current_metric_time": current_metric_time,
        "current_metric_quality_status": normalize_metric_quality_status(metric_quality_status),
        "projection_period": "30m",
        "projection_30m_flag": projection_flag,
        "projection_30m_type": projection_type,
        "current_30m_virtual_amount": json_number(current_30m),
        "reference_30m_amount": json_number(reference_amount),
        "reference_30m_entity_high": json_number(reference_high),
        "reference_30m_entity_low": json_number(reference_low),
        "trigger_amount_chain_pass": trigger_amount_chain_pass,
        "projection_lineage_json": lineage,
        "source_freshness_status": source_freshness_status(
            source_snapshot_run_id=source_snapshot_run_id,
            source_minute_run_id=source_minute_run_id,
            source_previous_day_minute_run_id=source_previous_day_minute_run_id,
            current_metric_time=current_metric_time,
            metric_quality_status=metric_quality_status,
        ),
        "source_snapshot_run_id": source_snapshot_run_id,
        "source_minute_run_id": source_minute_run_id,
        "source_previous_day_minute_run_id": source_previous_day_minute_run_id,
    }


def source_mode_trace(metric_row: Mapping[str, Any]) -> dict[str, Any]:
    source_fact_ids = metric_row.get("source_fact_ids") if isinstance(metric_row.get("source_fact_ids"), Mapping) else {}
    trace_json = metric_row.get("trace_json") if isinstance(metric_row.get("trace_json"), Mapping) else {}
    raw_json = metric_row.get("raw_json") if isinstance(metric_row.get("raw_json"), Mapping) else {}
    source_mode = (
        metric_row.get("source_mode")
        or source_fact_ids.get("source_mode")
        or trace_json.get("source_mode")
        or raw_json.get("source_mode")
    )
    c1_dependency = first_present(
        metric_row.get("c1_dependency"),
        source_fact_ids.get("c1_dependency"),
        trace_json.get("c1_dependency"),
        raw_json.get("c1_dependency"),
    )
    source_live_minute_run_id = (
        metric_row.get("source_live_minute_run_id")
        or source_fact_ids.get("source_live_minute_run_id")
        or trace_json.get("source_live_minute_run_id")
        or raw_json.get("source_live_minute_run_id")
    )
    output: dict[str, Any] = {}
    if source_mode:
        output["source_mode"] = str(source_mode)
    if c1_dependency is not None:
        output["c1_dependency"] = bool(c1_dependency)
    if source_live_minute_run_id:
        output["source_live_minute_run_id"] = str(source_live_minute_run_id)
    return output


def first_present(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def build_trigger_amount_chain_pass(
    *,
    n2_context: Mapping[str, Any] | None,
    current_chain_metrics: Mapping[str, Any] | None,
    projection_30m_pass: bool | None = None,
) -> dict[str, Any]:
    direction = infer_direction(n2_context)
    current = dict(current_chain_metrics or {})
    periods = extract_n2_period_baselines(n2_context)
    result: dict[str, Any] = {period: None for period in PERIODS}
    result["projection_30m"] = projection_30m_pass
    trace = {
        "owner": "N3_market_data",
        "inputs": list(TRIGGER_AMOUNT_CHAIN_INPUTS),
        "direction": direction,
        "n4_recompute_allowed": False,
        "missing_inputs": [],
    }

    if direction not in {"buy", "sell"}:
        trace["missing_inputs"].append("direction")
        result["_trace"] = trace
        return result

    result["Y"] = True
    chain_specs = {
        "D": ("today_virt_amount", "weekly_avg_with_today", "W"),
        "W": ("weekly_virt_amount", "monthly_avg_with_today", "M"),
        "M": ("monthly_virt_amount", "quarterly_avg_with_today", "Q"),
        "Q": ("quarterly_virt_amount", "yearly_avg_with_today", "Y"),
    }
    for period, (left_key, middle_key, baseline_period) in chain_specs.items():
        left = decimal_or_none(current.get(left_key))
        middle = decimal_or_none(current.get(middle_key))
        baseline = decimal_or_none((periods.get(baseline_period) or {}).get("previous_amount_baseline"))
        baseline_ready = bool((periods.get(baseline_period) or {}).get("period_baseline_ready"))
        if left is None or middle is None or baseline is None or not baseline_ready:
            result[period] = None
            if left is None:
                trace["missing_inputs"].append(left_key)
            if middle is None:
                trace["missing_inputs"].append(middle_key)
            if baseline is None or not baseline_ready:
                trace["missing_inputs"].append(f"N2.{baseline_period}.previous_amount_baseline")
            continue
        if direction == "buy":
            result[period] = left >= middle >= baseline
        else:
            result[period] = left <= middle <= baseline
    result["_trace"] = trace
    return result


def classify_projection_30m(
    *,
    current_price: Decimal | None,
    current_30m_virtual_amount: Decimal | None,
    reference_30m_amount: Decimal | None,
    reference_30m_entity_high: Decimal | None,
    reference_30m_entity_low: Decimal | None,
) -> str:
    if (
        current_price is None
        or current_30m_virtual_amount is None
        or reference_30m_amount is None
        or reference_30m_entity_high is None
        or reference_30m_entity_low is None
    ):
        return "unknown"
    if current_30m_virtual_amount > reference_30m_amount and current_price > reference_30m_entity_high:
        return "volume_up"
    if current_30m_virtual_amount < reference_30m_amount and current_price < reference_30m_entity_low:
        return "shrink_down"
    return "none"


def summarize_projection_enrichment_rows(rows_by_asset: Mapping[str, list[Mapping[str, Any]]]) -> dict[str, Any]:
    all_rows = [row for rows in rows_by_asset.values() for row in rows]
    missing_counter: Counter[str] = Counter()
    rows_with_enrichment = 0
    n4_recompute_allowed = False
    trigger_amount_chain_generated = 0
    for row in all_rows:
        enrichment = (row.get("raw_json") or {}).get("enrichment_v1")
        if not isinstance(enrichment, Mapping):
            missing_counter.update(PROJECTION_ENRICHMENT_REQUIRED_FIELDS)
            continue
        rows_with_enrichment += 1
        missing = [field for field in PROJECTION_ENRICHMENT_REQUIRED_FIELDS if field not in enrichment]
        missing_counter.update(missing)
        lineage = enrichment.get("projection_lineage_json")
        if isinstance(lineage, Mapping) and bool(lineage.get("n4_recompute_allowed")):
            n4_recompute_allowed = True
        chain = enrichment.get("trigger_amount_chain_pass")
        trace = chain.get("_trace") if isinstance(chain, Mapping) else None
        inputs = set(trace.get("inputs") or []) if isinstance(trace, Mapping) else set()
        if {"N2 period_trigger_baseline_json", "N3 current_chain_metrics"} <= inputs:
            trigger_amount_chain_generated += 1
    return {
        "contract_version": PROJECTION_ENRICHMENT_VERSION,
        "total_rows": len(all_rows),
        "rows_with_enrichment_v1": rows_with_enrichment,
        "missing_required_field_rows": sum(
            1
            for row in all_rows
            if not isinstance((row.get("raw_json") or {}).get("enrichment_v1"), Mapping)
            or any(field not in (row.get("raw_json") or {}).get("enrichment_v1", {}) for field in PROJECTION_ENRICHMENT_REQUIRED_FIELDS)
        ),
        "missing_required_fields": dict(sorted(missing_counter.items())),
        "trigger_amount_chain_generated_by_n2_n3": trigger_amount_chain_generated,
        "n4_recompute_allowed": n4_recompute_allowed,
        "storage_path": "raw_json.enrichment_v1",
    }


def extract_n2_period_baselines(n2_context: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    if not isinstance(n2_context, Mapping):
        return {}
    baseline = n2_context.get("period_trigger_baseline_json")
    if not isinstance(baseline, Mapping):
        baseline = n2_context.get("trigger_amount_chain_baseline_json")
    periods = baseline.get("periods") if isinstance(baseline, Mapping) else None
    if not isinstance(periods, Mapping):
        return {}
    output: dict[str, Mapping[str, Any]] = {}
    for period in PERIODS:
        entry = periods.get(period)
        if isinstance(entry, Mapping):
            output[period] = entry
    return output


def infer_direction(n2_context: Mapping[str, Any] | None) -> str:
    if not isinstance(n2_context, Mapping):
        return "unknown"
    for key in ("direction", "signal_direction", "condition_direction"):
        value = str(n2_context.get(key) or "").lower()
        if value in {"buy", "sell"}:
            return value
    signal_values: list[str] = []
    for key in ("signal_type", "selected_signal_type", "allowed_signal_types", "selected_signal_types_json"):
        value = n2_context.get(key)
        if isinstance(value, str):
            signal_values.append(value)
        elif isinstance(value, list):
            signal_values.extend(str(item) for item in value)
    joined = ",".join(signal_values).upper()
    if "BUY" in joined:
        return "buy"
    if "SELL" in joined:
        return "sell"
    return "unknown"


def source_freshness_status(
    *,
    source_snapshot_run_id: Any,
    source_minute_run_id: Any,
    source_previous_day_minute_run_id: Any,
    current_metric_time: Any,
    metric_quality_status: str,
) -> str:
    if not source_snapshot_run_id or not source_minute_run_id or not source_previous_day_minute_run_id:
        return "missing"
    if not current_metric_time:
        return "unknown"
    if normalize_metric_quality_status(metric_quality_status) == "passed":
        return "fresh"
    return "stale"


def summarize_n2_baseline_refs(n2_context: Mapping[str, Any] | None) -> dict[str, Any]:
    periods = extract_n2_period_baselines(n2_context)
    return {
        "context_present": bool(periods),
        "periods": {
            period: {
                "period_baseline_ready": bool((periods.get(period) or {}).get("period_baseline_ready")),
                "previous_amount_baseline_present": (periods.get(period) or {}).get("previous_amount_baseline") not in (None, ""),
                "freshness_status": (periods.get(period) or {}).get("freshness_status"),
                "source_version": (periods.get(period) or {}).get("source_version"),
            }
            for period in PERIODS
        },
    }


def normalize_metric_quality_status(value: str) -> str:
    return value if value in {"passed", "warning", "missing", "failed", "blocked"} else "missing"


def decimal_or_none(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def json_number(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")
