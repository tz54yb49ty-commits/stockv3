"""N2 context enrichment contract for N4 v4 trigger matching.

The enrichment stays inside JSON context for now. It does not require schema
migration and must not make N4 recalculate N2-owned period baselines.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence


PERIODS = ("Y", "Q", "M", "W", "D")
CONTEXT_ENRICHMENT_VERSION = "N2-context-enrichment-v1"
TRIGGER_AMOUNT_CHAIN_FORMULA_VERSION = "N4-v4-trigger-amount-chain-v1"
FULL_BLOCKED_STATUS = "blocked_trace_only"
HINT_PASSED_STATUS = "passed"
NOT_APPLICABLE_STATUS = "not_applicable"


def build_context_enrichment_contract() -> dict[str, Any]:
    return {
        "gate": "N2_CONTEXT_ENRICHMENT_SCHEMA_CONTRACT_DRY_RUN_GATE",
        "layer_role": "N2_condition",
        "downstream_consumer": "N4_trigger",
        "contract_version": CONTEXT_ENRICHMENT_VERSION,
        "physical_columns_required": False,
        "schema_migration_required": False,
        "n4_can_recompute_context": False,
        "n4_context_source": "N2 frozen context snapshot",
        "json_extension_paths": [
            "period_trigger_baseline_json.context_enrichment",
            "period_trigger_baseline_json.periods.*.classification_previous_open",
            "period_trigger_baseline_json.periods.*.classification_previous_close",
            "period_trigger_baseline_json.periods.*.classification_previous_entity_high",
            "period_trigger_baseline_json.periods.*.classification_previous_entity_low",
            "period_trigger_baseline_json.periods.*.classification_previous_amount_baseline",
            "period_trigger_baseline_json.periods.*.classification_period_key_previous",
            "period_trigger_baseline_json.periods.*.trigger_previous_open",
            "period_trigger_baseline_json.periods.*.trigger_previous_close",
            "period_trigger_baseline_json.periods.*.trigger_previous_entity_high",
            "period_trigger_baseline_json.periods.*.trigger_previous_entity_low",
            "period_trigger_baseline_json.periods.*.current_seed_entity_high",
            "period_trigger_baseline_json.periods.*.current_seed_entity_low",
            "period_trigger_baseline_json.periods.*.trigger_previous_amount_baseline",
            "period_trigger_baseline_json.periods.*.previous_transition",
            "period_trigger_baseline_json.periods.*.previous_amount_baseline",
            "period_trigger_baseline_json.periods.*.period_baseline_ready",
            "period_trigger_baseline_json.periods.*.baseline_source_trade_date",
            "period_trigger_baseline_json.periods.*.source_version",
            "period_trigger_baseline_json.periods.*.freshness_status",
            "raw_json.trigger_amount_chain_baseline_json",
            "raw_json.FULL_prerequisite_trace_json",
            "raw_json.HINT_prerequisite_trace_json",
        ],
        "target_fields": [
            "classification_previous_open",
            "classification_previous_close",
            "classification_previous_entity_high",
            "classification_previous_entity_low",
            "classification_previous_amount_baseline",
            "classification_period_key_previous",
            "trigger_previous_open",
            "trigger_previous_close",
            "trigger_previous_entity_high",
            "trigger_previous_entity_low",
            "current_seed_entity_high",
            "current_seed_entity_low",
            "trigger_previous_amount_baseline",
            "previous_transition",
            "previous_entity_high",
            "previous_entity_low",
            "previous_amount_baseline",
            "period_baseline_ready",
            "baseline_source_trade_date",
            "source_version",
            "freshness_status",
            "trigger_amount_chain_baseline_json",
            "trigger_amount_chain_formula_hash",
            "FULL_prerequisite_trace_json",
            "FULL_prerequisite_quality_status",
            "HINT_prerequisite_trace_json",
            "HINT_prerequisite_quality_status",
            "context_enrichment_version",
            "context_enrichment_hash",
        ],
        "full_policy": {
            "BUY:FULL": "trace_only_blocked_for_v4_execute",
            "SELL:FULL": "trace_only_blocked_for_v4_execute",
        },
        "hint_policy": {
            "BUY_HINT": "N2 proves prerequisite; N4 confirms standardized N3 projection",
            "SELL_HINT": "N2 proves prerequisite; N4 confirms standardized N3 projection",
        },
        "forbidden": [
            "N4 recalculates N2 period baseline",
            "N4 queries N1 daily facts for trigger context",
            "N4 uses legacy previous_* as trigger baseline",
            "N4 uses current_* seed fields as formal price trigger baseline",
            "BUY:FULL / SELL:FULL used as v4 execute matcher basis",
            "database writes in this gate",
        ],
    }


def build_context_enrichment_snapshot(
    row: Mapping[str, Any],
    *,
    baseline_source_trade_date: str | None = None,
    baseline_source_version: str | None = None,
) -> dict[str, Any]:
    source_trade_date = str(baseline_source_trade_date or row.get("source_trade_date") or "")
    source_version = str(baseline_source_version or row.get("source_version") or "")
    enriched_baseline = enrich_period_trigger_baseline_json(
        row.get("period_trigger_baseline_json"),
        baseline_source_trade_date=source_trade_date,
        baseline_source_version=source_version,
    )
    amount_chain = build_trigger_amount_chain_baseline_json(enriched_baseline)
    full_trace = build_full_prerequisite_trace(row)
    hint_trace = build_hint_prerequisite_trace(row)
    full_status = full_prerequisite_quality_status(full_trace)
    hint_status = hint_prerequisite_quality_status(hint_trace)
    payload = {
        "context_enrichment_version": CONTEXT_ENRICHMENT_VERSION,
        "period_trigger_baseline_json": enriched_baseline,
        "trigger_amount_chain_baseline_json": amount_chain,
        "trigger_amount_chain_formula_hash": stable_hash(trigger_amount_chain_formula_spec()),
        "FULL_prerequisite_trace_json": full_trace,
        "FULL_prerequisite_quality_status": full_status,
        "HINT_prerequisite_trace_json": hint_trace,
        "HINT_prerequisite_quality_status": hint_status,
    }
    payload["context_enrichment_hash"] = stable_hash(payload)
    context = enriched_baseline.setdefault("context_enrichment", {})
    if isinstance(context, dict):
        context.update(
            {
                "trigger_amount_chain_baseline_json": amount_chain,
                "trigger_amount_chain_formula_hash": payload["trigger_amount_chain_formula_hash"],
                "FULL_prerequisite_trace_json": full_trace,
                "FULL_prerequisite_quality_status": full_status,
                "HINT_prerequisite_trace_json": hint_trace,
                "HINT_prerequisite_quality_status": hint_status,
                "context_enrichment_hash": payload["context_enrichment_hash"],
            }
        )
    return payload


def attach_context_enrichment_to_row(row: Mapping[str, Any]) -> dict[str, Any]:
    output = dict(row)
    snapshot = build_context_enrichment_snapshot(
        output,
        baseline_source_trade_date=str(output.get("source_trade_date") or ""),
        baseline_source_version=str(output.get("source_version") or ""),
    )
    output["period_trigger_baseline_json"] = snapshot["period_trigger_baseline_json"]
    output["context_enrichment_version"] = snapshot["context_enrichment_version"]
    output["context_enrichment_hash"] = snapshot["context_enrichment_hash"]
    raw_json = normalize_json_object(output.get("raw_json") or {})
    raw_json["context_enrichment"] = {
        "context_enrichment_version": snapshot["context_enrichment_version"],
        "context_enrichment_hash": snapshot["context_enrichment_hash"],
        "trigger_amount_chain_baseline_json": snapshot["trigger_amount_chain_baseline_json"],
        "trigger_amount_chain_formula_hash": snapshot["trigger_amount_chain_formula_hash"],
        "FULL_prerequisite_trace_json": snapshot["FULL_prerequisite_trace_json"],
        "FULL_prerequisite_quality_status": snapshot["FULL_prerequisite_quality_status"],
        "HINT_prerequisite_trace_json": snapshot["HINT_prerequisite_trace_json"],
        "HINT_prerequisite_quality_status": snapshot["HINT_prerequisite_quality_status"],
    }
    output["raw_json"] = raw_json
    return output


def enrich_period_trigger_baseline_json(
    value: Any,
    *,
    baseline_source_trade_date: str | None = None,
    baseline_source_version: str | None = None,
) -> dict[str, Any]:
    baseline = normalize_json_object(value)
    periods = baseline.get("periods")
    if not isinstance(periods, Mapping):
        periods = {}
    enriched_periods: dict[str, dict[str, Any]] = {}
    for period in PERIODS:
        entry = deepcopy(periods.get(period) if isinstance(periods.get(period), Mapping) else {})
        amount_metric = str(entry.get("amount_metric") or ("amount" if period == "D" else "avg_amount"))
        classification_previous_open = entry.get("previous_open")
        classification_previous_close = entry.get("previous_close")
        classification_previous_entity_high = entry.get("previous_entity_high")
        classification_previous_entity_low = entry.get("previous_entity_low")
        classification_period_key_previous = entry.get("period_key_previous")
        classification_previous_amount_baseline = (
            entry.get("previous_amount")
            if amount_metric == "amount"
            else entry.get("previous_avg_amount")
        )
        if classification_previous_amount_baseline in (None, ""):
            classification_previous_amount_baseline = entry.get("previous_amount") or entry.get("previous_avg_amount")
        trigger_previous_amount_baseline = entry.get("current_amount_seed") or entry.get("current_avg_amount_seed")
        current_open = entry.get("current_open_seed")
        current_close = entry.get("current_close_seed")
        current_seed_entity_high = max_decimal_text(current_open, current_close)
        current_seed_entity_low = min_decimal_text(current_open, current_close)
        if period == "D":
            # D formal trigger baseline is anchored to the source/current
            # completed day; W/M/Q/Y continue to use previous complete periods.
            d_previous_amount = entry.get("current_amount_seed")
            d_previous_avg_amount = entry.get("current_avg_amount_seed") or d_previous_amount
            entry.update(
                {
                    "period_key_previous": entry.get("period_key_current"),
                    "previous_open": current_open,
                    "previous_close": current_close,
                    "previous_entity_high": current_seed_entity_high,
                    "previous_entity_low": current_seed_entity_low,
                    "previous_amount": d_previous_amount,
                    "previous_avg_amount": d_previous_avg_amount,
                    "previous_amount_total": entry.get("current_amount_total_seed"),
                    "previous_window_start": entry.get("current_window_start"),
                    "previous_window_end": entry.get("current_window_end"),
                }
            )
        trigger_entity_high = entry.get("previous_entity_high")
        trigger_entity_low = entry.get("previous_entity_low")
        baseline_ready = bool(entry.get("baseline_ready"))
        entry.update(
            {
                "classification_previous_open": classification_previous_open,
                "classification_previous_close": classification_previous_close,
                "classification_previous_entity_high": classification_previous_entity_high,
                "classification_previous_entity_low": classification_previous_entity_low,
                "classification_previous_amount_baseline": classification_previous_amount_baseline,
                "classification_period_key_previous": classification_period_key_previous,
                "trigger_previous_open": entry.get("previous_open"),
                "trigger_previous_close": entry.get("previous_close"),
                "trigger_previous_entity_high": trigger_entity_high,
                "trigger_previous_entity_low": trigger_entity_low,
                "current_seed_entity_high": current_seed_entity_high,
                "current_seed_entity_low": current_seed_entity_low,
                "trigger_previous_amount_baseline": trigger_previous_amount_baseline,
                "previous_transition": entry.get("previous_transition")
                or entry.get("period_transition")
                or "unknown",
                "previous_amount_baseline": (
                    entry.get("previous_amount")
                    if amount_metric == "amount"
                    else entry.get("previous_avg_amount")
                )
                or entry.get("previous_amount")
                or entry.get("previous_avg_amount")
                or classification_previous_amount_baseline,
                "period_baseline_ready": baseline_ready,
                "baseline_source_trade_date": baseline_source_trade_date,
                "source_version": baseline_source_version,
                "freshness_status": freshness_status(baseline_source_trade_date),
            }
        )
        missing = list(entry.get("baseline_missing_fields") or [])
        if classification_previous_amount_baseline in (None, "") and "previous_amount_baseline" not in missing:
            missing.append("previous_amount_baseline")
        for field, field_value in (
            ("trigger_previous_entity_high", trigger_entity_high),
            ("trigger_previous_entity_low", trigger_entity_low),
            ("trigger_previous_amount_baseline", trigger_previous_amount_baseline),
        ):
            if field_value in (None, "") and field not in missing:
                missing.append(field)
        entry["baseline_missing_fields"] = missing
        if missing:
            entry["period_baseline_ready"] = False
        enriched_periods[period] = entry
    baseline["periods"] = enriched_periods
    baseline["context_enrichment"] = {
        "context_enrichment_version": CONTEXT_ENRICHMENT_VERSION,
        "baseline_source_trade_date": baseline_source_trade_date,
        "source_version": baseline_source_version,
        "freshness_status": freshness_status(baseline_source_trade_date),
        "n4_can_recompute_context": False,
    }
    return baseline


def build_trigger_amount_chain_baseline_json(enriched_baseline: Mapping[str, Any]) -> dict[str, Any]:
    periods = enriched_baseline.get("periods")
    period_payload: dict[str, dict[str, Any]] = {}
    if isinstance(periods, Mapping):
        for period in PERIODS:
            entry = periods.get(period)
            if not isinstance(entry, Mapping):
                entry = {}
            period_payload[period] = {
                "amount_metric": entry.get("amount_metric") or ("amount" if period == "D" else "avg_amount"),
                "trigger_previous_amount_baseline": entry.get("trigger_previous_amount_baseline"),
                "classification_previous_amount_baseline": entry.get("classification_previous_amount_baseline"),
                "previous_amount_baseline": entry.get("previous_amount_baseline"),
                "baseline_ready": bool(entry.get("period_baseline_ready") if "period_baseline_ready" in entry else entry.get("baseline_ready")),
                "source_version": entry.get("source_version"),
                "freshness_status": entry.get("freshness_status"),
            }
    spec = trigger_amount_chain_formula_spec()
    return {
        "formula_version": TRIGGER_AMOUNT_CHAIN_FORMULA_VERSION,
        "formula_hash": stable_hash(spec),
        "owner": "N2_condition",
        "consumer": "N4_trigger",
        "n4_can_recompute": False,
        "rules": spec["rules"],
        "periods": period_payload,
    }


def trigger_amount_chain_formula_spec() -> dict[str, Any]:
    return {
        "formula_version": TRIGGER_AMOUNT_CHAIN_FORMULA_VERSION,
        "inputs": [
            "N2.period_trigger_baseline_json.periods[P].trigger_previous_amount_baseline",
            "N3.standardized_current_amount_metric[P]",
        ],
        "rules": {
            "ordinary_buy": "condition_key periods P require trigger_amount_chain_pass[P] from standardized N2/N3 fields",
            "ordinary_sell": "condition_key periods P require trigger_amount_chain_pass[P] from standardized N2/N3 fields",
            "buy_full": "trace_only; D amount-chain baseline is provided but v4 execute matcher is blocked",
            "sell_full": "trace_only; D amount-chain baseline is provided but v4 execute matcher is blocked",
            "buy_hint": "N2 prerequisite trace only; 30m projection confirmation is N4/N3 responsibility",
            "sell_hint": "N2 prerequisite trace only; 30m projection confirmation is N4/N3 responsibility",
        },
    }


def build_full_prerequisite_trace(row: Mapping[str, Any]) -> dict[str, Any]:
    condition_key = str(row.get("condition_key") or "")
    buy_present = bool(row.get("buy_full_necessary_base") or row.get("buy_full_necessary_key") or condition_key == "BUY:FULL")
    sell_present = bool(row.get("sell_full_necessary_base") or row.get("sell_full_necessary_key") or condition_key == "SELL:FULL")
    return {
        "trace_version": CONTEXT_ENRICHMENT_VERSION,
        "execute_matcher_allowed": False,
        "blocked_reason": "FULL_prerequisite_trace_only_not_v4_execute_matcher",
        "buy_full": {
            "present": buy_present,
            "condition_key": row.get("buy_full_necessary_key") or ("BUY:FULL" if buy_present else None),
            "required_periods": ["D"] if buy_present else [],
        },
        "sell_full": {
            "present": sell_present,
            "condition_key": row.get("sell_full_necessary_key") or ("SELL:FULL" if sell_present else None),
            "required_periods": ["D"] if sell_present else [],
        },
    }


def build_hint_prerequisite_trace(row: Mapping[str, Any]) -> dict[str, Any]:
    condition_key = str(row.get("condition_key") or "")
    buy_present = bool(row.get("oversold_hint_necessary_base") or row.get("oversold_hint_key") or condition_key == "BUY_HINT")
    sell_present = bool(row.get("overbought_hint_necessary_base") or row.get("overbought_hint_key") or condition_key == "SELL_HINT")
    return {
        "trace_version": CONTEXT_ENRICHMENT_VERSION,
        "n2_prerequisite_owner": "N2_condition",
        "n4_projection_confirmation_required": True,
        "buy_hint": {
            "present": buy_present,
            "condition_key": row.get("oversold_hint_key") or ("BUY_HINT" if buy_present else None),
            "requires_period_entity_baseline": False,
        },
        "sell_hint": {
            "present": sell_present,
            "condition_key": row.get("overbought_hint_key") or ("SELL_HINT" if sell_present else None),
            "requires_period_entity_baseline": False,
        },
    }


def full_prerequisite_quality_status(trace: Mapping[str, Any]) -> str:
    if bool(trace.get("buy_full", {}).get("present")) or bool(trace.get("sell_full", {}).get("present")):
        return FULL_BLOCKED_STATUS
    return NOT_APPLICABLE_STATUS


def hint_prerequisite_quality_status(trace: Mapping[str, Any]) -> str:
    if bool(trace.get("buy_hint", {}).get("present")) or bool(trace.get("sell_hint", {}).get("present")):
        return HINT_PASSED_STATUS
    return NOT_APPLICABLE_STATUS


def summarize_context_enrichment_rows(rows_by_domain: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, Any]:
    row_counts = {domain: len(list(rows)) for domain, rows in rows_by_domain.items()}
    all_rows = [row for rows in rows_by_domain.values() for row in rows]
    full_counts = Counter(str(row.get("FULL_prerequisite_quality_status") or "missing") for row in all_rows)
    hint_counts = Counter(str(row.get("HINT_prerequisite_quality_status") or "missing") for row in all_rows)
    return {
        "gate_result": "DRY_RUN_PASS",
        "writes_performed": False,
        "will_execute_sql": False,
        "schema_migration_required": False,
        "physical_columns_required": False,
        "rows": row_counts,
        "coverage": {
            "context_hash_missing": sum(1 for row in all_rows if not row.get("context_enrichment_hash")),
            "amount_chain_missing": sum(1 for row in all_rows if not row.get("trigger_amount_chain_baseline_json")),
            "formula_hash_missing": sum(1 for row in all_rows if not row.get("trigger_amount_chain_formula_hash")),
            "full_trace_missing": sum(1 for row in all_rows if not row.get("FULL_prerequisite_trace_json")),
            "hint_trace_missing": sum(1 for row in all_rows if not row.get("HINT_prerequisite_trace_json")),
        },
        "full_prerequisite_quality_status_counts": dict(full_counts),
        "hint_prerequisite_quality_status_counts": dict(hint_counts),
    }


def normalize_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return deepcopy(dict(value))
    if isinstance(value, str) and value.strip():
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(decoded, Mapping):
            return deepcopy(dict(decoded))
    return {}


def freshness_status(baseline_source_trade_date: str | None) -> str:
    return "fresh" if baseline_source_trade_date else "unknown"


def stable_hash(payload: Mapping[str, Any]) -> str:
    return sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def max_decimal_text(left: Any, right: Any) -> str | None:
    left_decimal = decimal_or_none(left)
    right_decimal = decimal_or_none(right)
    if left_decimal is None or right_decimal is None:
        return None
    return decimal_to_text(max(left_decimal, right_decimal))


def min_decimal_text(left: Any, right: Any) -> str | None:
    left_decimal = decimal_or_none(left)
    right_decimal = decimal_or_none(right)
    if left_decimal is None or right_decimal is None:
        return None
    return decimal_to_text(min(left_decimal, right_decimal))


def decimal_or_none(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def decimal_to_text(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"
