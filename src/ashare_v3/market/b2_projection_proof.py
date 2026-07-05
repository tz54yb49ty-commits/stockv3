"""N3-B2 30m projection proof contract helpers.

The proof is owned by N3 and consumed by N4 hint/projection matching. It is
not an N5 ActionExecuted final confirmation proof.
"""

from __future__ import annotations

from typing import Any, Mapping

from ashare_v3.market.n3_source_time_policy import (
    SOURCE_RETURNED_TIME_POLICY,
    map_source_time_to_30m_window,
    parse_source_datetime,
)


B2_PROJECTION_METRIC_ROLE = "projection_trigger_proof"
B2_PROJECTION_PROOF_OWNER = "N3"
B2_PROJECTION_PROOF_CONSUMER = "N4"
B2_30M_PROJECTION_PROOF_KIND = "n3_b2_30m_projection"
B2_PROJECTION_FREQUENCY = "30m"
B2_PROJECTION_ADAPTER_FREQUENCY = 2
B2_DIRECT_30M_K_SOURCE_MODE = "direct_30m_k"
B2_DIRECT_30M_REQUIRED_DATA_KIND = "minute_bar_30m"


def b2_30m_projection_adapter_contract(asset_kind: str) -> dict[str, Any]:
    if asset_kind == "stock":
        adapter_method = "bars"
    elif asset_kind in {"index", "board"}:
        adapter_method = "index"
    else:
        raise ValueError(f"unsupported asset_kind for B2 30m projection adapter contract: {asset_kind}")
    return {
        "frequency": B2_PROJECTION_FREQUENCY,
        "adapter_frequency": B2_PROJECTION_ADAPTER_FREQUENCY,
        "adapter_method": adapter_method,
    }


def b2_projection_30m_type_for_signal_status(projection_signal_status: str) -> str:
    if projection_signal_status == "up_volume_expanding":
        return "volume_up"
    if projection_signal_status == "down_volume_shrinking":
        return "shrink_down"
    if projection_signal_status in {"missing", "unknown", ""}:
        return "unknown"
    return "none"


def b2_trigger_mark_candidate_for_projection_type(projection_30m_type: str) -> str:
    if projection_30m_type == "volume_up":
        return "30m_volume"
    if projection_30m_type == "shrink_down":
        return "30m_shrink"
    return "normal"


def build_b2_30m_projection_proof_fields(
    *,
    asset_kind: str,
    projection_run_id: str,
    projection_id: Any = None,
    projection_time: Any = None,
    projection_signal_status: str = "",
    projection_30m_type: str | None = None,
    source_mode: str | None = None,
    for_trade_date: Any = None,
    source_30m_k_run_id: Any = None,
    source_30m_k_bar_id: Any = None,
    source_30m_k_row_key: Any = None,
    source_30m_k_time: Any = None,
    source_30m_k_window_start: Any = None,
    source_30m_k_window_end: Any = None,
    source_30m_k_closed_status: Any = None,
    source_30m_k_adapter_method: str | None = None,
    source_30m_k_source_marker: Any = None,
) -> dict[str, Any]:
    resolved_projection_30m_type = projection_30m_type or b2_projection_30m_type_for_signal_status(
        projection_signal_status
    )
    adapter_contract = b2_30m_projection_adapter_contract(asset_kind)
    fields = {
        "metric_role": B2_PROJECTION_METRIC_ROLE,
        "proof_owner": B2_PROJECTION_PROOF_OWNER,
        "proof_consumer": B2_PROJECTION_PROOF_CONSUMER,
        "proof_kind": B2_30M_PROJECTION_PROOF_KIND,
        "not_n5_final_proof": True,
        **adapter_contract,
        "projection_30m_type": resolved_projection_30m_type,
        "trigger_mark_candidate": b2_trigger_mark_candidate_for_projection_type(resolved_projection_30m_type),
        "source_projection_proof_run_id": projection_run_id,
        "source_projection_proof_metric_id": projection_id,
        "source_projection_proof_time": first_present(projection_time, source_30m_k_time),
    }
    if source_mode == B2_DIRECT_30M_K_SOURCE_MODE:
        mapped_30m_window: dict[str, Any] = {}
        if str(source_30m_k_source_marker or "").strip().lower() in {"fake", "synthetic", "fabricated"}:
            raise ValueError("fake_source_time_forbidden")
        parsed_source_time = parse_source_datetime(source_30m_k_time)
        if parsed_source_time is not None:
            mapped_30m_window = map_source_time_to_30m_window(
                source_time=parsed_source_time,
                for_trade_date=str(for_trade_date or parsed_source_time.strftime("%Y%m%d")),
            )
        fields.update(
            {
                "source_time_policy": SOURCE_RETURNED_TIME_POLICY,
                "projection_mode": "realtime_virtual_30m",
                "source_mode": B2_DIRECT_30M_K_SOURCE_MODE,
                "required_data_kind": B2_DIRECT_30M_REQUIRED_DATA_KIND,
                "source_30m_k_run_id": source_30m_k_run_id,
                "source_30m_k_bar_id": source_30m_k_bar_id,
                "source_30m_k_row_key": source_30m_k_row_key,
                "source_30m_k_time": _iso_or_original(mapped_30m_window.get("source_30m_k_time"), source_30m_k_time),
                "source_30m_k_window_start": _iso_or_original(
                    mapped_30m_window.get("source_30m_k_window_start"),
                    source_30m_k_window_start,
                ),
                "source_30m_k_window_end": _iso_or_original(
                    mapped_30m_window.get("source_30m_k_window_end"),
                    source_30m_k_window_end,
                ),
                "source_30m_k_closed_status": source_30m_k_closed_status
                or mapped_30m_window.get("source_30m_k_closed_status"),
                "source_30m_k_adapter_method": source_30m_k_adapter_method or adapter_contract["adapter_method"],
                "source_30m_k_source_marker": source_30m_k_source_marker,
            }
        )
    return fields


def extract_b2_30m_projection_proof(projection: Mapping[str, Any]) -> dict[str, Any]:
    source_fact_ids = projection.get("source_fact_ids") if isinstance(projection.get("source_fact_ids"), Mapping) else {}
    raw_json = projection.get("raw_json") if isinstance(projection.get("raw_json"), Mapping) else {}
    trace_json = projection.get("trace_json") if isinstance(projection.get("trace_json"), Mapping) else {}
    projection_trace = (
        projection.get("projection_trace") if isinstance(projection.get("projection_trace"), Mapping) else {}
    )

    def get(key: str) -> Any:
        return first_present(
            projection.get(key),
            source_fact_ids.get(key),
            raw_json.get(key),
            trace_json.get(key),
            projection_trace.get(key),
        )

    proof = {
        "metric_role": get("metric_role"),
        "proof_owner": get("proof_owner"),
        "proof_consumer": get("proof_consumer"),
        "proof_kind": get("proof_kind"),
        "not_n5_final_proof": get("not_n5_final_proof"),
        "frequency": get("frequency"),
        "adapter_method": get("adapter_method"),
        "adapter_frequency": get("adapter_frequency"),
        "projection_30m_type": get("projection_30m_type"),
        "trigger_mark_candidate": get("trigger_mark_candidate"),
        "source_projection_proof_run_id": first_present(get("source_projection_proof_run_id"), projection.get("projection_run_id")),
        "source_projection_proof_metric_id": first_present(get("source_projection_proof_metric_id"), projection.get("projection_id")),
        "source_projection_proof_time": first_present(get("source_projection_proof_time"), projection.get("snapshot_time")),
        "source_time_policy": get("source_time_policy"),
        "projection_mode": get("projection_mode"),
        "source_mode": get("source_mode"),
        "required_data_kind": get("required_data_kind"),
        "source_snapshot_run_id": get("source_snapshot_run_id"),
        "snapshot_id": get("snapshot_id"),
        "snapshot_event_id": get("snapshot_event_id"),
        "source_30m_k_run_id": get("source_30m_k_run_id"),
        "source_30m_k_bar_id": get("source_30m_k_bar_id"),
        "source_30m_k_row_key": get("source_30m_k_row_key"),
        "source_30m_k_time": get("source_30m_k_time"),
        "source_30m_k_window_start": get("source_30m_k_window_start"),
        "source_30m_k_window_end": get("source_30m_k_window_end"),
        "source_30m_k_closed_status": get("source_30m_k_closed_status"),
        "source_30m_k_adapter_method": get("source_30m_k_adapter_method"),
    }
    missing = [
        key
        for key, expected in (
            ("metric_role", B2_PROJECTION_METRIC_ROLE),
            ("proof_owner", B2_PROJECTION_PROOF_OWNER),
            ("proof_consumer", B2_PROJECTION_PROOF_CONSUMER),
            ("proof_kind", B2_30M_PROJECTION_PROOF_KIND),
            ("frequency", B2_PROJECTION_FREQUENCY),
        )
        if proof.get(key) != expected
    ]
    if not bool_value(proof.get("not_n5_final_proof")):
        missing.append("not_n5_final_proof")
    if proof.get("adapter_method") not in {"bars", "index"}:
        missing.append("adapter_method")
    if int_or_none(proof.get("adapter_frequency")) != B2_PROJECTION_ADAPTER_FREQUENCY:
        missing.append("adapter_frequency")
    if proof.get("source_mode") == B2_DIRECT_30M_K_SOURCE_MODE:
        for key in (
            "source_30m_k_run_id",
            "source_30m_k_time",
            "source_30m_k_window_start",
            "source_30m_k_window_end",
            "source_30m_k_closed_status",
            "source_30m_k_adapter_method",
        ):
            if not proof.get(key):
                missing.append(key)
        if not first_present(proof.get("source_30m_k_bar_id"), proof.get("source_30m_k_row_key")):
            missing.append("source_30m_k_bar_id")
        if proof.get("required_data_kind") != B2_DIRECT_30M_REQUIRED_DATA_KIND:
            missing.append("required_data_kind")
        if proof.get("source_30m_k_adapter_method") != proof.get("adapter_method"):
            missing.append("source_30m_k_adapter_method")
    else:
        legacy_snapshot_ready = all(
            first_present(proof.get(key), projection.get(key))
            for key in ("source_snapshot_run_id", "snapshot_id", "source_projection_proof_time")
        )
        if not legacy_snapshot_ready:
            missing.append("source_lineage")
    proof["not_n5_final_proof"] = bool_value(proof.get("not_n5_final_proof"))
    proof["valid"] = not missing
    proof["missing_or_invalid_fields"] = missing
    return proof


def first_present(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _iso_or_original(mapped_value: Any, original_value: Any) -> Any:
    value = original_value if original_value not in (None, "") else mapped_value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "t", "yes", "y"}
    return bool(value)


def int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
