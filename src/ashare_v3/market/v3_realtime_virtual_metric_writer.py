"""V3 realtime virtual metric writer/runner.

The runner is inert by default.  It can build N3-owned realtime virtual metric
rows from reviewed 1m source records and context payloads, but it only writes to
the runtime DB when both ``--execute`` and ``--user-confirmed`` are present.
It never writes or consumes event infrastructure and never enters N4/N5/N6.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
import re
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ashare_v3.market.action_confirmation_projection_execute import (
    insert_action_confirmation_metric_rows,
)
from ashare_v3.market.minute_label_normalization import (
    MinuteLabelNormalizationError,
    minute_label_normalization_trace,
    normalize_mootdx_intraday_1m_labels,
)
from ashare_v3.market.previous_day_preload_execute import utc_now_iso
from ashare_v3.market.query_audit_phase3 import audited_n3_market_execute_connect
from ashare_v3.market.realtime_virtual_metric import (
    LEGACY_MIDDAY_BRIDGE_POLICY,
    PREVIOUS_DAY_MIDDAY_BRIDGE_NORMALIZATION_POLICY,
    build_realtime_virtual_metric,
    build_realtime_trigger_proof_metric_from_elapsed_amount,
    canonicalize_realtime_virtual_metric_fields,
)

try:
    from check_condition_source_ready import DEFAULT_DSN
except ModuleNotFoundError:  # pragma: no cover - script import fallback
    from scripts.check_condition_source_ready import DEFAULT_DSN


DEFAULT_CONTRACT_PATH = "docs/V3_20260612_REALTIME_VIRTUAL_METRIC_WRITER_RUNNER_CONTRACT.json"
DEFAULT_PREFLIGHT_PATH = "docs/V3_20260612_REALTIME_VIRTUAL_METRIC_WRITER_RUNNER_PREFLIGHT.json"
DEFAULT_SOURCE_PAYLOAD_PATH = "docs/V3_20260612_realtime_virtual_metric_writer_payload.json"
DEFAULT_REPORT_PATH = "docs/V3_20260612_REALTIME_VIRTUAL_METRIC_WRITER_RUNNER_IMPLEMENTATION_REPORT.json"
DEFAULT_REPORT_MD_PATH = "docs/V3_20260612_REALTIME_VIRTUAL_METRIC_WRITER_RUNNER_IMPLEMENTATION_REPORT.md"

METRIC_TABLES = {
    "stock": "stock_action_confirmation_projection_metric",
    "index": "index_action_confirmation_projection_metric",
    "board": "board_action_confirmation_projection_metric",
}
A1_CUMULATIVE_TABLES = {
    "stock": "stock_previous_day_minute_cumulative",
    "index": "index_previous_day_minute_cumulative",
    "board": "board_previous_day_minute_cumulative",
}
ASSET_KINDS = ("stock", "index", "board")
N3P_ASSET_KINDS = (*ASSET_KINDS, "all")
N3P_DEFAULT_SOURCE_VARIANT = "default"
N3P_LIVE_CURRENT_1M_SOURCE_VARIANT = "live_current_1m"
N3P_AMOUNT_CHAIN_V2_SOURCE_VARIANT = "live_current_1m_amount_chain_v2"
N3P_AMOUNT_CHAIN_V2_LIFECYCLE_V2_SOURCE_VARIANT = "live_current_1m_amount_chain_v2_lifecycle_v2"
N3P_AMOUNT_CHAIN_V2_CORRECTED_REPLAY_SOURCE_VARIANT = "live_current_1m_amount_chain_v2_corrected_replay"
N3P_AMOUNT_CHAIN_V2_UNIFIED_PAYLOAD_V1_SOURCE_VARIANT = "live_current_1m_amount_chain_v2_unified_payload_v1"
N3P_AMOUNT_CHAIN_V2_ASSET_UNIT_FIX_V1_SOURCE_VARIANT = "live_current_1m_amount_chain_v2_asset_unit_fix_v1"
N3P_B1_SOURCE_RETURNED_AMOUNT_CHAIN_V2_ASSET_UNIT_FIX_V1_SOURCE_VARIANT = (
    "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1"
)
N3P_B1_SOURCE_RETURNED_CURRENT_PERIOD_AVG_V1_SOURCE_VARIANT = (
    "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1"
)
N3P_ALLOWED_SOURCE_VARIANTS = frozenset(
    {
        N3P_DEFAULT_SOURCE_VARIANT,
        N3P_LIVE_CURRENT_1M_SOURCE_VARIANT,
        N3P_AMOUNT_CHAIN_V2_SOURCE_VARIANT,
        N3P_AMOUNT_CHAIN_V2_LIFECYCLE_V2_SOURCE_VARIANT,
        N3P_AMOUNT_CHAIN_V2_CORRECTED_REPLAY_SOURCE_VARIANT,
        N3P_AMOUNT_CHAIN_V2_UNIFIED_PAYLOAD_V1_SOURCE_VARIANT,
        N3P_AMOUNT_CHAIN_V2_ASSET_UNIT_FIX_V1_SOURCE_VARIANT,
        N3P_B1_SOURCE_RETURNED_AMOUNT_CHAIN_V2_ASSET_UNIT_FIX_V1_SOURCE_VARIANT,
        N3P_B1_SOURCE_RETURNED_CURRENT_PERIOD_AVG_V1_SOURCE_VARIANT,
    }
)
N3P_MARKET_DATA_SUBSCRIPTION_SUFFIX_RE = re.compile(r"^market_data_subscription_[A-Za-z0-9][A-Za-z0-9_]*$")
N3P_RUN_ID_RE = re.compile(
    r"^realtime_action_confirmation_metric_"
    r"(?P<for_trade_date>\d{8})_until_(?P<until_hhmm>\d{4})__asset_(?P<asset_kind>stock|index|board|all)"
    r"(?:__(?P<suffix>.+))?$"
)
TARGET_ABSENCE_COUNT_KEYS = (
    "common_market_data_run",
    "stock_action_confirmation_projection_metric",
    "index_action_confirmation_projection_metric",
    "board_action_confirmation_projection_metric",
    "common_market_data_quality_item",
    "common_event_outbox",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
)
LIVE_CURRENT_1M_SOURCE_MODE = "live_current_1m"
B1_SOURCE_RETURNED_SNAPSHOT_SOURCE_MODE = "b1_source_returned_snapshot"
SOURCE_RETURNED_TIME_POLICY_MODE = "source_returned_time"
B1_SOURCE_RETURNED_SNAPSHOT_COMPAT_POLICY = "b1_source_returned_snapshot_alias"
N3P_TRIGGER_PROOF_REALTIME_SOURCE_MODEL = "n3p_trigger_proof_realtime_v1"
N3P_STOCK_QUOTE_BATCH_SIZE = 80
N3P_STOCK_QUOTE_ZERO_PRICE_OHLC_VOLUME_REASON = "stock_quote_zero_price_ohlc_volume"
N3P_MIXED_REALTIME_SOURCE_PAYLOAD_REGISTRATION_STAGE = "N3P_mixed_realtime_source_payload_registration"
DEFAULT_LIVE_CURRENT_SPARSE_NO_TRADE_EXCEPTION_THRESHOLD = 20
LIVE_CURRENT_SPARSE_NO_TRADE_REASONS = {
    "adapter_sparse_no_trade",
    "no_trade",
    "quality_visible_no_trade",
    "source_no_trade",
    "suspended",
}
LIVE_CURRENT_SPARSE_NO_TRADE_EXCEPTION_KEYS = (
    "live_current_sparse_no_trade_exceptions",
    "quality_visible_sparse_no_trade_exceptions",
    "quality_visible_missing_objects",
    "live_current_missing_objects",
)
B1_SOURCE_RETURNED_SNAPSHOT_PAYLOAD_KEYS = (
    "b1_snapshot_rows",
    "b1_source_returned_snapshot_rows",
    "source_snapshot_rows",
    "realtime_daily_snapshot_rows",
)
HIGHER_PERIOD_CONTEXT_PERIODS = ("D", "W", "M", "Q", "Y")
HIGHER_PERIOD_CONTEXT_TOTAL_UNITS = {"D": 1, "W": 5, "M": 20, "Q": 60, "Y": 240}
HIGHER_PERIOD_CONTEXT_NUMERIC_FIELDS = {
    "current_open",
    "previous_open",
    "previous_close",
    "previous_amount",
    "previous_avg_amount",
    "current_amount_seed",
    "current_amount_total_seed",
    "current_trade_days_seed",
    "elapsed_units",
    "total_units",
}
N4_CONTEXT_SNAPSHOT_PAYLOAD_KEYS = (
    "n4_context_snapshot_rows",
    "trigger_context_snapshot_rows",
    "n4_context_rows",
)
N2_CONTEXT_SCOPE_PAYLOAD_KEYS = (
    "n2_minute_target_scope_rows",
    "minute_target_scope_rows",
    "n2_scope_rows",
    "condition_scope_rows",
    "condition_pool_rows",
)
DB_CURRENT_PRICE_SOURCES = {"realtime_daily_snapshot", "minute_bar_1m", "adapter_projection", "unknown"}
CURRENT_PRICE_SOURCE_ALIASES = {
    "n3_realtime_virtual_metric.current_1m.close": "minute_bar_1m",
}
FALLBACK_SOURCE_RUN_ID_PREFIX = "v3_realtime_virtual_metric_source_payload_"
N3P_PLAN_ONLY_PROOF_SUMMARY_VERSION = "n3p_plan_only_proof_summary_v1"


class VirtualMetricWriterBlocked(RuntimeError):
    """Raised when the V3 realtime virtual metric writer gate is blocked."""


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, data: Mapping[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(normalize_jsonable(data), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: str | Path, text: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


def _sql_literal(value: Any) -> str:
    return "'" + str(value or "").replace("'", "''") + "'"


def build_n3p_trigger_proof_rollback_sql(*, target_run_id: str, source_payload_run_id: str = "") -> str:
    target = _sql_literal(target_run_id)
    source_comment = source_payload_run_id or "source payload lineage run intentionally preserved"
    return f"""-- Scoped rollback for:
-- {target_run_id}
--
-- This rollback intentionally does not delete the source payload lineage run:
-- {source_comment}

BEGIN;

DO $$
DECLARE
    target_run_id text := {target};
BEGIN
    IF EXISTS (
        SELECT 1
        FROM common_event_outbox
        WHERE source_run_id = target_run_id
          AND status IN ('delivering', 'delivered')
    ) THEN
        RAISE EXCEPTION 'rollback blocked: delivered/delivering outbox exists for %', target_run_id;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM common_event_inbox
        WHERE source_run_id = target_run_id
           OR payload_json::text LIKE '%' || target_run_id || '%'
           OR raw_json::text LIKE '%' || target_run_id || '%'
    ) THEN
        RAISE EXCEPTION 'rollback blocked: inbox refs exist for %', target_run_id;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM common_event_consumer_checkpoint
        WHERE checkpoint_payload::text LIKE '%' || target_run_id || '%'
           OR last_outbox_id IN (
              SELECT outbox_id
              FROM common_event_outbox
              WHERE source_run_id = target_run_id
           )
    ) THEN
        RAISE EXCEPTION 'rollback blocked: checkpoint refs exist for %', target_run_id;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM common_trigger_run
        WHERE source_market_data_run_id = target_run_id
           OR raw_json::text LIKE '%' || target_run_id || '%'
    ) THEN
        RAISE EXCEPTION 'rollback blocked: N4 trigger refs exist for %', target_run_id;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM common_action_run
        WHERE source_trigger_run_id = target_run_id
           OR raw_json::text LIKE '%' || target_run_id || '%'
    ) THEN
        RAISE EXCEPTION 'rollback blocked: N5/action refs exist for %', target_run_id;
    END IF;

    IF to_regclass('public.user_projection_run') IS NOT NULL AND EXISTS (
        SELECT 1 FROM user_projection_run WHERE to_jsonb(user_projection_run)::text LIKE '%' || target_run_id || '%'
    ) THEN
        RAISE EXCEPTION 'rollback blocked: user refs exist for %', target_run_id;
    END IF;

    IF to_regclass('public.user_signal_projection') IS NOT NULL AND EXISTS (
        SELECT 1 FROM user_signal_projection WHERE to_jsonb(user_signal_projection)::text LIKE '%' || target_run_id || '%'
    ) THEN
        RAISE EXCEPTION 'rollback blocked: user refs exist for %', target_run_id;
    END IF;

    IF to_regclass('public.user_signal_card') IS NOT NULL AND EXISTS (
        SELECT 1 FROM user_signal_card WHERE to_jsonb(user_signal_card)::text LIKE '%' || target_run_id || '%'
    ) THEN
        RAISE EXCEPTION 'rollback blocked: user refs exist for %', target_run_id;
    END IF;

    IF to_regclass('public.user_sim_order') IS NOT NULL AND EXISTS (
        SELECT 1 FROM user_sim_order WHERE to_jsonb(user_sim_order)::text LIKE '%' || target_run_id || '%'
    ) THEN
        RAISE EXCEPTION 'rollback blocked: sim refs exist for %', target_run_id;
    END IF;

    IF to_regclass('public.user_sim_trade') IS NOT NULL AND EXISTS (
        SELECT 1 FROM user_sim_trade WHERE to_jsonb(user_sim_trade)::text LIKE '%' || target_run_id || '%'
    ) THEN
        RAISE EXCEPTION 'rollback blocked: sim refs exist for %', target_run_id;
    END IF;

    IF to_regclass('public.user_sim_position') IS NOT NULL AND EXISTS (
        SELECT 1 FROM user_sim_position WHERE to_jsonb(user_sim_position)::text LIKE '%' || target_run_id || '%'
    ) THEN
        RAISE EXCEPTION 'rollback blocked: sim refs exist for %', target_run_id;
    END IF;
END $$;

DELETE FROM stock_action_confirmation_projection_metric
WHERE projection_run_id = {target};

DELETE FROM index_action_confirmation_projection_metric
WHERE projection_run_id = {target};

DELETE FROM board_action_confirmation_projection_metric
WHERE projection_run_id = {target};

DELETE FROM common_market_data_quality_item
WHERE run_id = {target};

DELETE FROM common_market_data_run
WHERE run_id = {target};

COMMIT;
"""


def normalize_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): normalize_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [normalize_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def stable_payload_hash(value: Any) -> str:
    encoded = json.dumps(normalize_jsonable(value), ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return sha256(encoded).hexdigest()


def require_execute_flags(*, execute: bool, user_confirmed: bool) -> None:
    if execute and not user_confirmed:
        raise VirtualMetricWriterBlocked("V3 realtime virtual metric writer blocked: missing --user-confirmed")
    if user_confirmed and not execute:
        raise VirtualMetricWriterBlocked("V3 realtime virtual metric writer blocked: missing --execute")


def _target_run_id(contract: Mapping[str, Any]) -> str:
    return str(contract.get("target_run_id") or contract.get("projection_run_id") or "")


def _is_n3p_realtime_action_contract(contract: Mapping[str, Any]) -> bool:
    target_run_id = _target_run_id(contract)
    return (
        contract.get("metric_family") == "realtime_action_confirmation_metric"
        or contract.get("run_id_contract") == "n3p.realtime_action_confirmation_metric.v1"
        or target_run_id.startswith("realtime_action_confirmation_metric_")
    )


def _validate_trade_date(value: Any) -> str:
    text = str(value or "")
    if not re.fullmatch(r"\d{8}", text):
        raise VirtualMetricWriterBlocked("invalid_n3p_trade_date")
    return text


def _validate_hhmm(value: Any) -> str:
    text = str(value or "")
    if not re.fullmatch(r"\d{4}", text):
        raise VirtualMetricWriterBlocked("invalid_n3p_until_hhmm")
    hour = int(text[:2])
    minute = int(text[2:])
    if hour > 23 or minute > 59:
        raise VirtualMetricWriterBlocked("invalid_n3p_until_hhmm")
    return text


def build_n3p_realtime_action_confirmation_metric_run_id(
    *,
    for_trade_date: Any,
    until_hhmm: Any,
    asset_kind: str = "all",
    suffix: str | None = None,
) -> str:
    trade_date = _validate_trade_date(for_trade_date)
    hhmm = _validate_hhmm(until_hhmm)
    asset = str(asset_kind or "")
    if asset not in N3P_ASSET_KINDS:
        raise VirtualMetricWriterBlocked("invalid_n3p_asset_kind")
    run_id = f"realtime_action_confirmation_metric_{trade_date}_until_{hhmm}__asset_{asset}"
    if suffix:
        suffix_text = str(suffix)
        _parse_n3p_run_id_suffix(suffix_text)
        run_id += f"__{suffix_text}"
    return run_id


def _parse_n3p_run_id_suffix(suffix: str) -> tuple[str, str]:
    suffix_text = str(suffix or "")
    if not suffix_text:
        return N3P_DEFAULT_SOURCE_VARIANT, ""
    if N3P_MARKET_DATA_SUBSCRIPTION_SUFFIX_RE.fullmatch(suffix_text):
        return N3P_DEFAULT_SOURCE_VARIANT, suffix_text
    parts = suffix_text.split("__", 1)
    if len(parts) != 2:
        raise VirtualMetricWriterBlocked("invalid_n3p_run_id")
    source_variant, source_subscription_run_id = parts
    if source_variant not in N3P_ALLOWED_SOURCE_VARIANTS or source_variant == N3P_DEFAULT_SOURCE_VARIANT:
        raise VirtualMetricWriterBlocked("invalid_n3p_run_id")
    if not N3P_MARKET_DATA_SUBSCRIPTION_SUFFIX_RE.fullmatch(source_subscription_run_id):
        raise VirtualMetricWriterBlocked("invalid_n3p_run_id")
    return source_variant, source_subscription_run_id


def parse_n3p_realtime_action_confirmation_metric_run_id(run_id: str) -> dict[str, str]:
    match = N3P_RUN_ID_RE.match(str(run_id or ""))
    if not match:
        raise VirtualMetricWriterBlocked("invalid_n3p_run_id")
    parsed = match.groupdict()
    try:
        hhmm = _validate_hhmm(parsed["until_hhmm"])
        source_variant, source_subscription_run_id = _parse_n3p_run_id_suffix(parsed.get("suffix") or "")
    except VirtualMetricWriterBlocked as exc:
        raise VirtualMetricWriterBlocked("invalid_n3p_run_id") from exc
    return {
        "run_id": str(run_id),
        "metric_family": "realtime_action_confirmation_metric",
        "for_trade_date": parsed["for_trade_date"],
        "trade_date": parsed["for_trade_date"],
        "until_hhmm": hhmm,
        "until_minute": hhmm,
        "asset_kind": parsed["asset_kind"],
        "suffix": parsed.get("suffix") or "",
        "source_variant": source_variant,
        "source_subscription_run_id": source_subscription_run_id,
        "run_label": f"until_{hhmm}",
    }


def _source_scope(contract: Mapping[str, Any]) -> Mapping[str, Any]:
    return contract.get("source_scope") or contract


def _db_input_contract(contract: Mapping[str, Any]) -> Mapping[str, Any]:
    value = contract.get("db_backed_input_contract")
    return value if isinstance(value, Mapping) else {}


def _source_mode(contract: Mapping[str, Any], candidate: Mapping[str, Any] | None = None) -> str:
    candidate = candidate or {}
    scope = _source_scope(contract)
    db_contract = _db_input_contract(contract)
    return str(
        candidate.get("source_mode")
        or db_contract.get("source_mode")
        or scope.get("source_mode")
        or contract.get("source_mode")
        or "db_backed_preflight_contract"
    )


def _is_live_current_1m_source(contract: Mapping[str, Any], candidate: Mapping[str, Any] | None = None) -> bool:
    return _source_mode(contract, candidate) == LIVE_CURRENT_1M_SOURCE_MODE


def _is_b1_source_returned_snapshot_source(
    contract: Mapping[str, Any],
    candidate: Mapping[str, Any] | None = None,
) -> bool:
    return _source_mode(contract, candidate) == B1_SOURCE_RETURNED_SNAPSHOT_SOURCE_MODE


def _is_no_c1_source_mode(contract: Mapping[str, Any], candidate: Mapping[str, Any] | None = None) -> bool:
    return _source_mode(contract, candidate) in {
        LIVE_CURRENT_1M_SOURCE_MODE,
        B1_SOURCE_RETURNED_SNAPSHOT_SOURCE_MODE,
    }


def _source_time_policy_mode_from_value(value: Any) -> str:
    if isinstance(value, Mapping):
        return str(value.get("mode") or "")
    return str(value or "")


def _source_time_policy_mode(contract: Mapping[str, Any], candidate: Mapping[str, Any] | None = None) -> str:
    candidate = candidate or {}
    scope = _source_scope(contract)
    db_contract = _db_input_contract(contract)
    for container in (candidate, db_contract, scope, contract):
        if not isinstance(container, Mapping) or "source_time_policy" not in container:
            continue
        mode = _source_time_policy_mode_from_value(container.get("source_time_policy"))
        if mode:
            return mode
    return ""


def _first_lineage_value(*containers: Mapping[str, Any], keys: Sequence[str]) -> str:
    for container in containers:
        for key in keys:
            value = container.get(key) if isinstance(container, Mapping) else None
            if value not in (None, ""):
                return str(value)
    return ""


def _hhmm_from_time_value(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    normalized = text.replace("T", " ")
    if len(normalized) >= 16 and normalized[10] == " ":
        return normalized[11:16].replace(":", "")
    if re.fullmatch(r"\d{2}:\d{2}", normalized):
        return normalized.replace(":", "")
    if re.fullmatch(r"\d{4}", normalized):
        return _validate_hhmm(normalized)
    return ""


def _b1_source_returned_proof_input_time(
    contract: Mapping[str, Any],
    candidate: Mapping[str, Any] | None = None,
) -> str:
    candidate = candidate or {}
    scope = _source_scope(contract)
    db_contract = _db_input_contract(contract)
    return _first_lineage_value(
        candidate,
        db_contract,
        scope,
        contract,
        keys=(
            "proof_input_time",
            "source_snapshot_time",
            "effective_source_time",
            "source_time",
            "observed_at",
            "fetched_at",
        ),
    )


def _raw_target_minute_label(contract: Mapping[str, Any], candidate: Mapping[str, Any] | None = None) -> str:
    candidate = candidate or {}
    scope = _source_scope(contract)
    db_contract = _db_input_contract(contract)
    return _first_lineage_value(
        candidate,
        db_contract,
        scope,
        contract,
        keys=("raw_target_minute_label", "requested_until_minute_label", "until_minute_label"),
    )


def _assert_b1_source_returned_target_time(contract: Mapping[str, Any]) -> str:
    if not _is_b1_source_returned_snapshot_source(contract):
        return ""
    if _source_time_policy_mode(contract) != SOURCE_RETURNED_TIME_POLICY_MODE:
        raise VirtualMetricWriterBlocked(
            "BLOCKED_NEED_INPUT_RESOLVER: b1_source_returned_time_policy_missing"
        )
    parsed_run_id = parse_n3p_realtime_action_confirmation_metric_run_id(_target_run_id(contract))
    proof_input_time = _b1_source_returned_proof_input_time(contract)
    proof_hhmm = _hhmm_from_time_value(proof_input_time)
    if not proof_hhmm:
        raise VirtualMetricWriterBlocked(
            "BLOCKED_NEED_INPUT_RESOLVER: b1_source_returned_proof_input_time_missing"
        )
    if proof_hhmm != parsed_run_id["until_hhmm"]:
        raise VirtualMetricWriterBlocked(
            "BLOCKED_NEED_INPUT_RESOLVER: b1_source_returned_until_hhmm_mismatch"
        )
    return proof_input_time


def _assert_b1_source_returned_candidate_time(
    *,
    contract: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> None:
    if not _is_b1_source_returned_snapshot_source(contract, candidate):
        return
    proof_input_time = _b1_source_returned_proof_input_time(contract, candidate)
    proof_hhmm = _hhmm_from_time_value(proof_input_time)
    candidate_hhmm = _hhmm_from_time_value(candidate.get("minute_label"))
    if not proof_hhmm or not candidate_hhmm or proof_hhmm != candidate_hhmm:
        raise VirtualMetricWriterBlocked(
            "BLOCKED_NEED_INPUT_RESOLVER: b1_source_returned_candidate_time_mismatch"
        )


def _source_today_minute_run_id_compat_policy(
    contract: Mapping[str, Any],
    candidate: Mapping[str, Any] | None = None,
) -> str:
    if _is_b1_source_returned_snapshot_source(contract, candidate):
        return B1_SOURCE_RETURNED_SNAPSHOT_COMPAT_POLICY
    if _is_live_current_1m_source(contract, candidate):
        return "live_current_1m_alias"
    return ""


def _b1_source_returned_today_alias(
    *,
    candidate: Mapping[str, Any],
    contract: Mapping[str, Any],
    source_snapshot_run_id: str,
) -> str:
    explicit = _first_lineage_value(
        candidate,
        _source_scope(contract),
        _db_input_contract(contract),
        contract,
        keys=("source_today_minute_run_id",),
    )
    if explicit and explicit != source_snapshot_run_id:
        raise VirtualMetricWriterBlocked(
            "BLOCKED_NEED_INPUT_RESOLVER: b1_source_returned_today_alias_mismatch"
        )
    return source_snapshot_run_id


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _live_current_sparse_no_trade_policy(contract: Mapping[str, Any]) -> dict[str, Any]:
    policy: dict[str, Any] = {
        "enabled": True,
        "exception_count_threshold": DEFAULT_LIVE_CURRENT_SPARSE_NO_TRADE_EXCEPTION_THRESHOLD,
        "missing_live_current_minute_rows_default": "fail_closed",
        "fake_bar_policy": "forbidden",
        "previous_minute_fill_policy": "forbidden",
        "metric_ready_for_missing_object": False,
    }
    for container in (contract, _source_scope(contract), _db_input_contract(contract)):
        configured = container.get("live_current_sparse_no_trade_exception_policy")
        if isinstance(configured, Mapping):
            policy.update(dict(configured))
    threshold = policy.get("exception_count_threshold")
    if threshold in (None, ""):
        threshold = DEFAULT_LIVE_CURRENT_SPARSE_NO_TRADE_EXCEPTION_THRESHOLD
    try:
        policy["exception_count_threshold"] = int(threshold)
    except (TypeError, ValueError) as exc:
        raise VirtualMetricWriterBlocked("invalid_live_current_sparse_no_trade_exception_threshold") from exc
    policy["enabled"] = bool(policy.get("enabled", True))
    return policy


def _iter_sparse_no_trade_exception_candidates(
    *,
    contract: Mapping[str, Any],
    source_payload: Mapping[str, Any] | None = None,
) -> list[Mapping[str, Any]]:
    candidates: list[Mapping[str, Any]] = []
    for container in (contract, _source_scope(contract), _db_input_contract(contract), source_payload or {}):
        for key in LIVE_CURRENT_SPARSE_NO_TRADE_EXCEPTION_KEYS:
            value = container.get(key) if isinstance(container, Mapping) else None
            if isinstance(value, Mapping):
                items = value.get("items") or value.get("exceptions")
                if isinstance(items, Sequence) and not isinstance(items, (str, bytes)):
                    candidates.extend(item for item in items if isinstance(item, Mapping))
                else:
                    for identity_key, item in value.items():
                        if not isinstance(item, Mapping):
                            continue
                        row = dict(item)
                        row.setdefault("identity_key", str(identity_key))
                        candidates.append(row)
            elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                candidates.extend(item for item in value if isinstance(item, Mapping))
    return candidates


def _normalize_sparse_no_trade_exception(raw: Mapping[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    invalid: list[str] = []
    asset_kind = str(raw.get("asset_kind") or "").strip()
    identity_key = str(raw.get("identity_key") or "").strip()
    reason = str(raw.get("reason") or raw.get("exception_reason") or raw.get("quality_reason") or "").strip()
    latest_row = raw.get("latest_row") if isinstance(raw.get("latest_row"), Mapping) else {}
    latest_row_minute = (
        raw.get("latest_row_minute")
        or raw.get("latest_minute_label")
        or raw.get("latest_bar_time")
        or latest_row.get("bar_time")
        or latest_row.get("datetime")
        or latest_row.get("minute_label")
    )
    expected_target_minute = (
        raw.get("expected_target_minute")
        or raw.get("target_minute")
        or raw.get("until_minute_label")
    )
    writes_fake_bar = _truthy(
        raw.get("writes_fake_bar")
        or raw.get("fake_bar_written")
        or raw.get("target_minute_faked")
        or raw.get("target_minute_fabricated")
    )
    uses_previous_minute_as_target = _truthy(
        raw.get("uses_previous_minute_as_target")
        or raw.get("previous_minute_fill")
        or raw.get("filled_from_previous_minute")
    )
    metric_ready = _truthy(raw.get("metric_ready")) if "metric_ready" in raw else False
    if not asset_kind:
        invalid.append("asset_kind_missing")
    elif asset_kind not in ASSET_KINDS:
        invalid.append("asset_kind_invalid")
    if not identity_key:
        invalid.append("identity_key_missing")
    if reason not in LIVE_CURRENT_SPARSE_NO_TRADE_REASONS:
        invalid.append("reason_not_quality_visible_no_trade")
    if not latest_row_minute:
        invalid.append("latest_row_missing")
    if not expected_target_minute:
        invalid.append("expected_target_minute_missing")
    if writes_fake_bar:
        invalid.append("fake_bar_forbidden")
    if uses_previous_minute_as_target:
        invalid.append("previous_minute_fill_forbidden")
    if metric_ready:
        invalid.append("missing_object_metric_ready_forbidden")
    if invalid:
        return None, invalid
    return (
        {
            "asset_kind": asset_kind,
            "identity_key": identity_key,
            "exchange": raw.get("exchange"),
            "code": raw.get("code"),
            "display_code": raw.get("display_code") or raw.get("code"),
            "name": raw.get("name"),
            "reason": reason,
            "latest_row_minute": str(latest_row_minute),
            "expected_target_minute": str(expected_target_minute),
            "latest_row": normalize_jsonable(latest_row),
            "source_adapter": raw.get("source_adapter"),
            "subscription_id": raw.get("subscription_id"),
            "writes_fake_bar": False,
            "uses_previous_minute_as_target": False,
            "metric_ready": False,
            "quality_status": "quality_visible_missing",
            "raw_trace": normalize_jsonable(raw.get("raw_trace") or dict(raw)),
        },
        [],
    )


def build_live_current_sparse_no_trade_exception_report(
    contract: Mapping[str, Any],
    *,
    source_payload: Mapping[str, Any] | None = None,
    rows_by_asset: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
) -> dict[str, Any]:
    if not _is_live_current_1m_source(contract):
        return {"status": "not_applicable", "exception_count": 0, "exceptions": []}
    policy = _live_current_sparse_no_trade_policy(contract)
    raw_exceptions = _iter_sparse_no_trade_exception_candidates(contract=contract, source_payload=source_payload)
    exceptions: list[dict[str, Any]] = []
    blocked_reasons: list[str] = []
    for raw in raw_exceptions:
        normalized, invalid = _normalize_sparse_no_trade_exception(raw)
        if invalid:
            blocked_reasons.extend(invalid)
            continue
        exceptions.append(normalized)
    threshold = int(policy["exception_count_threshold"])
    if not policy["enabled"] and exceptions:
        blocked_reasons.append("live_current_sparse_no_trade_exception_policy_disabled")
    if len(exceptions) > threshold:
        blocked_reasons.append("live_current_sparse_no_trade_exception_threshold_exceeded")
    duplicate_keys = [
        key
        for key, count in Counter((row["asset_kind"], row["identity_key"]) for row in exceptions).items()
        if count > 1
    ]
    if duplicate_keys:
        blocked_reasons.append("duplicate_live_current_sparse_no_trade_exception")
    if rows_by_asset is not None:
        generated_keys = {
            (str(row.get("asset_kind") or asset), str(row.get("identity_key") or ""))
            for asset in ASSET_KINDS
            for row in rows_by_asset.get(asset, [])
        }
        exception_keys = {(row["asset_kind"], row["identity_key"]) for row in exceptions}
        if generated_keys & exception_keys:
            blocked_reasons.append("sparse_no_trade_exception_also_generated_ready_metric")
    return {
        "status": "blocked" if blocked_reasons else "passed",
        "policy": policy,
        "exception_count_threshold": threshold,
        "exception_count": len(exceptions),
        "exceptions": exceptions,
        "blocked_reasons": sorted(set(blocked_reasons)),
        "missing_live_current_minute_rows_default": "fail_closed",
        "no_fake_bar": True,
        "no_previous_minute_fill": True,
        "missing_object_metric_ready": False,
    }


def _contract_with_sparse_no_trade_report(
    contract: Mapping[str, Any],
    *,
    source_payload: Mapping[str, Any] | None,
    rows_by_asset: Mapping[str, Sequence[Mapping[str, Any]]] | None,
) -> dict[str, Any]:
    output = dict(contract)
    report = build_live_current_sparse_no_trade_exception_report(
        output,
        source_payload=source_payload,
        rows_by_asset=rows_by_asset,
    )
    output["_live_current_sparse_no_trade_exception_report"] = report
    output["_resolved_live_current_sparse_no_trade_exceptions"] = report.get("exceptions") or []
    return output


def _resolved_sparse_no_trade_report(
    contract: Mapping[str, Any],
    *,
    rows_by_asset: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
) -> dict[str, Any]:
    report = contract.get("_live_current_sparse_no_trade_exception_report")
    if isinstance(report, Mapping):
        return dict(report)
    return build_live_current_sparse_no_trade_exception_report(contract, rows_by_asset=rows_by_asset)


def build_live_current_1m_source_run_id(
    *,
    for_trade_date: Any,
    until_hhmm: Any,
    source_subscription_run_id: Any,
) -> str:
    trade_date = _validate_trade_date(for_trade_date)
    hhmm = _validate_hhmm(until_hhmm)
    subscription = str(source_subscription_run_id or "")
    if not subscription:
        raise VirtualMetricWriterBlocked("BLOCKED_NEED_INPUT_RESOLVER: missing source_subscription_run_id")
    return f"live_current_1m_source_{trade_date}_until_{hhmm}__{subscription}"


def _live_source_run_id(
    *,
    contract: Mapping[str, Any],
    candidate: Mapping[str, Any] | None = None,
) -> str:
    candidate = candidate or {}
    scope = _source_scope(contract)
    db_contract = _db_input_contract(contract)
    parsed_run_id = parse_n3p_realtime_action_confirmation_metric_run_id(_target_run_id(contract))
    value = (
        candidate.get("source_live_minute_run_id")
        or candidate.get("source_today_minute_run_id")
        or db_contract.get("source_live_minute_run_id")
        or db_contract.get("source_today_minute_run_id")
        or scope.get("source_live_minute_run_id")
        or scope.get("source_today_minute_run_id")
        or contract.get("source_live_minute_run_id")
        or contract.get("source_today_minute_run_id")
    )
    if value:
        return str(value)
    subscription = (
        candidate.get("source_subscription_run_id")
        or db_contract.get("source_subscription_run_id")
        or scope.get("source_subscription_run_id")
        or contract.get("source_subscription_run_id")
    )
    return build_live_current_1m_source_run_id(
        for_trade_date=scope.get("for_trade_date") or contract.get("for_trade_date") or parsed_run_id["for_trade_date"],
        until_hhmm=parsed_run_id["until_hhmm"],
        source_subscription_run_id=subscription,
    )


def _c1_dependency(contract: Mapping[str, Any], candidate: Mapping[str, Any] | None = None) -> bool:
    candidate = candidate or {}
    scope = _source_scope(contract)
    db_contract = _db_input_contract(contract)
    if _is_no_c1_source_mode(contract, candidate):
        return False
    value = (
        candidate.get("c1_dependency")
        if "c1_dependency" in candidate
        else db_contract.get("c1_dependency")
        if "c1_dependency" in db_contract
        else scope.get("c1_dependency")
        if "c1_dependency" in scope
        else contract.get("c1_dependency")
    )
    return bool(value) if value is not None else True


def _minute_hhmm(minute_label: str) -> str:
    text = str(minute_label)
    if len(text) >= 16 and " " in text:
        return text[-5:]
    return text


def _metric_time_iso(minute_label: str) -> str:
    text = str(minute_label)
    if len(text) == 16 and " " in text:
        return text.replace(" ", "T") + ":00+08:00"
    if len(text) == 19 and " " in text:
        return text.replace(" ", "T") + "+08:00"
    return text


def _lineage_value(
    *,
    candidate: Mapping[str, Any],
    contract: Mapping[str, Any],
    key: str,
    fallback: str,
) -> str:
    scope = _source_scope(contract)
    db_contract = _db_input_contract(contract)
    value = candidate.get(key) or scope.get(key) or db_contract.get(key) or contract.get(key) or fallback
    return str(value)


def _required_source_lineage(
    *,
    candidate: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> dict[str, str]:
    scope = _source_scope(contract)
    for_trade_date = str(scope.get("for_trade_date") or contract.get("for_trade_date") or "")
    source_trade_date = str(scope.get("source_trade_date") or contract.get("source_trade_date") or "")
    live_source_run_id = _live_source_run_id(contract=contract, candidate=candidate) if _is_live_current_1m_source(contract, candidate) else ""
    source_snapshot_run_id = _lineage_value(
        candidate=candidate,
        contract=contract,
        key="source_snapshot_run_id",
        fallback=f"v3_realtime_virtual_metric_source_payload_{for_trade_date}_no_snapshot_source",
    )
    source_today_run_id = ""
    today_fallback = live_source_run_id or f"v3_realtime_virtual_metric_source_payload_{for_trade_date}_retained_today_1m"
    if _is_b1_source_returned_snapshot_source(contract, candidate):
        source_today_run_id = _b1_source_returned_today_alias(
            candidate=candidate,
            contract=contract,
            source_snapshot_run_id=source_snapshot_run_id,
        )
    else:
        source_today_run_id = _lineage_value(
            candidate=candidate,
            contract=contract,
            key="source_today_minute_run_id",
            fallback=today_fallback,
        )
    return {
        "source_snapshot_run_id": source_snapshot_run_id,
        "source_today_minute_run_id": source_today_run_id,
        "source_previous_day_minute_run_id": _lineage_value(
            candidate=candidate,
            contract=contract,
            key="source_previous_day_minute_run_id",
            fallback=f"v3_realtime_virtual_metric_source_payload_{source_trade_date}_retained_previous_day_1m",
        ),
        "source_live_minute_run_id": live_source_run_id,
    }


def build_target_absence_report(*, target_run_id: str, counts: Mapping[str, Any]) -> dict[str, Any]:
    normalized_counts = {key: int(counts.get(key) or 0) for key in TARGET_ABSENCE_COUNT_KEYS}
    dirty_tables = {key: value for key, value in normalized_counts.items() if value > 0}
    report: dict[str, Any] = {
        "target_run_id": target_run_id,
        "status": "passed" if not dirty_tables else "blocked",
        "counts": normalized_counts,
        "dirty_tables": dirty_tables,
    }
    if dirty_tables:
        report["blocked_reason"] = "BLOCKED_TARGET_NOT_EMPTY"
    return report


def assert_target_absent(report: Mapping[str, Any]) -> None:
    if report.get("status") == "blocked":
        dirty_tables = report.get("dirty_tables") or {}
        raise VirtualMetricWriterBlocked(f"BLOCKED_TARGET_NOT_EMPTY: {dirty_tables}")


def _table_exists(cur: Any, table: str) -> bool:
    cur.execute("SELECT to_regclass(%s) AS table_name", (f"public.{table}",))
    row = cur.fetchone() or {}
    return bool(row.get("table_name"))


def _column_exists(cur: Any, table: str, column: str) -> bool:
    cur.execute(
        """
        SELECT 1 AS exists
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s AND column_name = %s
        LIMIT 1
        """,
        (table, column),
    )
    return bool(cur.fetchone())


def _safe_count_by_first_existing_column(cur: Any, *, table: str, columns: Sequence[str], value: str) -> int:
    if not _table_exists(cur, table):
        return 0
    for column in columns:
        if not _column_exists(cur, table, column):
            continue
        cur.execute(f"SELECT count(*)::bigint AS row_count FROM {table} WHERE {column} = %s", (value,))
        row = cur.fetchone() or {}
        return int(row.get("row_count") or 0)
    return 0


def fetch_target_absence_counts(cur: Any, target_run_id: str) -> dict[str, int]:
    counts = {
        "common_market_data_run": _safe_count_by_first_existing_column(
            cur, table="common_market_data_run", columns=("run_id",), value=target_run_id
        ),
        "stock_action_confirmation_projection_metric": _safe_count_by_first_existing_column(
            cur, table="stock_action_confirmation_projection_metric", columns=("projection_run_id",), value=target_run_id
        ),
        "index_action_confirmation_projection_metric": _safe_count_by_first_existing_column(
            cur, table="index_action_confirmation_projection_metric", columns=("projection_run_id",), value=target_run_id
        ),
        "board_action_confirmation_projection_metric": _safe_count_by_first_existing_column(
            cur, table="board_action_confirmation_projection_metric", columns=("projection_run_id",), value=target_run_id
        ),
        "common_market_data_quality_item": _safe_count_by_first_existing_column(
            cur, table="common_market_data_quality_item", columns=("run_id",), value=target_run_id
        ),
        "common_event_outbox": _safe_count_by_first_existing_column(
            cur, table="common_event_outbox", columns=("source_run_id", "run_id"), value=target_run_id
        ),
        "common_event_inbox": _safe_count_by_first_existing_column(
            cur, table="common_event_inbox", columns=("source_run_id", "run_id"), value=target_run_id
        ),
        "common_event_consumer_checkpoint": _safe_count_by_first_existing_column(
            cur, table="common_event_consumer_checkpoint", columns=("source_run_id", "run_id"), value=target_run_id
        ),
    }
    return {key: int(counts.get(key) or 0) for key in TARGET_ABSENCE_COUNT_KEYS}


def build_db_backed_input_contract_report(contract: Mapping[str, Any]) -> dict[str, Any]:
    if not _is_n3p_realtime_action_contract(contract):
        return {"status": "not_applicable"}
    parsed_run_id = parse_n3p_realtime_action_confirmation_metric_run_id(_target_run_id(contract))
    scope = _source_scope(contract)
    db_contract = contract.get("db_backed_input_contract")
    if not isinstance(db_contract, Mapping):
        raise VirtualMetricWriterBlocked("BLOCKED_NEED_INPUT_RESOLVER: missing db_backed_input_contract")
    source_mode = _source_mode(contract)
    live_mode = source_mode == LIVE_CURRENT_1M_SOURCE_MODE
    b1_source_returned_mode = source_mode == B1_SOURCE_RETURNED_SNAPSHOT_SOURCE_MODE
    required_ref_keys = (
        "source_snapshot_run_id",
        "source_previous_day_minute_run_id",
        "source_condition_run_id",
        "source_subscription_run_id",
        "n2_period_context_source",
    )
    if not live_mode and not b1_source_returned_mode:
        required_ref_keys = ("source_today_minute_run_id", *required_ref_keys)
    missing = [key for key in required_ref_keys if not db_contract.get(key)]
    source_live_minute_run_id = ""
    if live_mode:
        source_live_minute_run_id = str(db_contract.get("source_live_minute_run_id") or "")
    for_trade_date = str(scope.get("for_trade_date") or contract.get("for_trade_date") or parsed_run_id["for_trade_date"])
    source_trade_date = str(scope.get("source_trade_date") or contract.get("source_trade_date") or "")
    if not for_trade_date:
        missing.append("for_trade_date")
    if not source_trade_date:
        missing.append("source_trade_date")
    if missing:
        raise VirtualMetricWriterBlocked("BLOCKED_NEED_INPUT_RESOLVER: missing " + ",".join(sorted(set(missing))))
    asset_kinds = list(db_contract.get("asset_kinds") or ASSET_KINDS)
    invalid_assets = [asset for asset in asset_kinds if asset not in ASSET_KINDS]
    if invalid_assets:
        raise VirtualMetricWriterBlocked("BLOCKED_NEED_INPUT_RESOLVER: invalid asset_kinds " + ",".join(invalid_assets))
    input_refs = {key: str(db_contract.get(key) or "") for key in required_ref_keys}
    if live_mode:
        source_live_minute_run_id = source_live_minute_run_id or build_live_current_1m_source_run_id(
            for_trade_date=for_trade_date,
            until_hhmm=parsed_run_id["until_hhmm"],
            source_subscription_run_id=db_contract.get("source_subscription_run_id"),
        )
        input_refs["source_live_minute_run_id"] = source_live_minute_run_id
        input_refs["source_today_minute_run_id"] = source_live_minute_run_id
    proof_input_time = ""
    proof_input_time_source = ""
    raw_target_minute_label = ""
    source_time_policy = _source_time_policy_mode(contract)
    if b1_source_returned_mode:
        proof_input_time = _assert_b1_source_returned_target_time(contract)
        proof_input_time_source = _first_lineage_value(
            db_contract,
            scope,
            contract,
            keys=("proof_input_time_source", "source_time_source"),
        ) or "B1_source_snapshot_time"
        raw_target_minute_label = _raw_target_minute_label(contract)
        input_refs["source_today_minute_run_id"] = _b1_source_returned_today_alias(
            candidate={},
            contract=contract,
            source_snapshot_run_id=input_refs["source_snapshot_run_id"],
        )
    return {
        "status": "passed",
        "for_trade_date": for_trade_date,
        "source_trade_date": source_trade_date,
        "until_hhmm": parsed_run_id["until_hhmm"],
        "until_minute": parsed_run_id["until_minute"],
        "input_refs": input_refs,
        "asset_kinds": asset_kinds,
        "source_mode": source_mode,
        "c1_dependency": _c1_dependency(contract),
        "live_source_run_id": source_live_minute_run_id,
        "source_today_minute_run_id_compat": source_live_minute_run_id if live_mode else input_refs.get("source_today_minute_run_id"),
        "source_today_minute_run_id_compat_policy": _source_today_minute_run_id_compat_policy(contract),
        "source_time_policy": source_time_policy,
        "proof_input_time": proof_input_time,
        "proof_input_time_source": proof_input_time_source,
        "raw_target_minute_label": raw_target_minute_label,
        "no_c1_table_rows_read": live_mode or b1_source_returned_mode,
        "no_c1_table_rows_written": live_mode or b1_source_returned_mode,
    }


def _lineage_policy(required_lineage: Mapping[str, str]) -> str:
    if any(str(value).startswith(FALLBACK_SOURCE_RUN_ID_PREFIX) for value in required_lineage.values()):
        return "deterministic_fallback_for_required_legacy_projection_columns"
    return "contract_reviewed_source_run_id_fk_lineage"


def _has_unresolved_fk_lineage(row: Mapping[str, Any]) -> bool:
    for key in ("source_snapshot_run_id", "source_today_minute_run_id", "source_previous_day_minute_run_id"):
        if str(row.get(key) or "").startswith(FALLBACK_SOURCE_RUN_ID_PREFIX):
            return True
    return False


def canonicalize_current_price_source(raw_source: Any) -> tuple[str, str | None]:
    raw = str(raw_source or "unknown")
    canonical = CURRENT_PRICE_SOURCE_ALIASES.get(raw, raw)
    if canonical not in DB_CURRENT_PRICE_SOURCES:
        canonical = "unknown"
    if raw == canonical:
        return canonical, None
    return canonical, f"{raw}->{canonical}"


def _mapping_from_jsonish(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, Mapping):
            return dict(parsed)
    return {}


def _first_present(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return None


def _context_identity_key(row: Mapping[str, Any], asset_kind: str) -> str:
    return str(
        row.get("identity_key")
        or row.get(f"{asset_kind}_identity_key")
        or row.get("stock_identity_key")
        or row.get("index_identity_key")
        or row.get("board_identity_key")
        or ""
    )


def _context_index_key(row: Mapping[str, Any]) -> tuple[str, str, str] | None:
    identity = _context_identity_tuple(row)
    if identity is None:
        return None
    asset_kind, identity_key = identity
    condition_key = str(row.get("condition_key") or "")
    if not condition_key:
        return None
    return (asset_kind, identity_key, condition_key)


def _context_identity_tuple(row: Mapping[str, Any]) -> tuple[str, str] | None:
    asset_kind = str(row.get("asset_kind") or "")
    if asset_kind not in ASSET_KINDS:
        identity_key = str(row.get("identity_key") or "")
        if identity_key.startswith("stock:"):
            asset_kind = "stock"
        elif identity_key.startswith("index:"):
            asset_kind = "index"
        elif identity_key.startswith("board:"):
            asset_kind = "board"
    if asset_kind not in ASSET_KINDS:
        return None
    identity_key = _context_identity_key(row, asset_kind)
    if not identity_key:
        return None
    return (asset_kind, identity_key)


def _stable_context_id(value: Any) -> str:
    if value in (None, ""):
        return ""
    return str(value)


def _stable_values_from_container(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        values = [_stable_context_id(item) for item in value]
    else:
        values = [_stable_context_id(value)]
    output: list[str] = []
    seen: set[str] = set()
    for item in values:
        if not item or item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


def _candidate_values(
    candidate: Mapping[str, Any],
    *,
    scalar_keys: Sequence[str] = (),
    sequence_keys: Sequence[str] = (),
) -> list[str]:
    values: list[str] = []
    for key in scalar_keys:
        values.extend(_stable_values_from_container(candidate.get(key)))
    for key in sequence_keys:
        values.extend(_stable_values_from_container(candidate.get(key)))
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def _context_pool_scope_key(row: Mapping[str, Any]) -> tuple[str, str] | None:
    pool_id = _stable_context_id(row.get("source_condition_pool_id"))
    scope_id = _stable_context_id(row.get("source_minute_target_scope_id") or row.get("source_scope_id"))
    if not pool_id or not scope_id:
        return None
    return (pool_id, scope_id)


def _context_direction_key(row: Mapping[str, Any]) -> tuple[str, str, str] | None:
    identity = _context_identity_tuple(row)
    direction = str(row.get("direction") or "")
    if identity is None or not direction:
        return None
    return (*identity, direction)


def _period_trigger_baseline_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    raw_json = _mapping_from_jsonish(row.get("raw_json"))
    for container in (row, raw_json):
        baseline = container.get("period_trigger_baseline_json") if isinstance(container, Mapping) else None
        baseline_map = _mapping_from_jsonish(baseline)
        if isinstance(baseline_map.get("periods"), Mapping):
            return baseline_map
        baseline = container.get("period_trigger_baseline") if isinstance(container, Mapping) else None
        baseline_map = _mapping_from_jsonish(baseline)
        if isinstance(baseline_map.get("periods"), Mapping):
            return baseline_map
    if isinstance(row.get("periods"), Mapping):
        return dict(row)
    return {}


def higher_period_context_from_period_baseline_row(
    row: Mapping[str, Any],
    *,
    source_kind: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    baseline = _period_trigger_baseline_from_row(row)
    periods = baseline.get("periods") if isinstance(baseline.get("periods"), Mapping) else {}
    context: dict[str, dict[str, Any]] = {}
    for period in HIGHER_PERIOD_CONTEXT_PERIODS:
        item = periods.get(period)
        if not isinstance(item, Mapping):
            continue
        context[period] = {
            "current_open": _first_present(item, "current_open", "current_open_seed"),
            "previous_open": item.get("previous_open"),
            "previous_close": item.get("previous_close"),
            "previous_amount": _first_present(item, "previous_amount", "previous_amount_baseline"),
            "previous_avg_amount": _first_present(
                item,
                "previous_avg_amount",
                "previous_amount_baseline",
                "classification_previous_amount_baseline",
            ),
            "current_amount_seed": item.get("current_amount_seed"),
            "current_amount_total_seed": item.get("current_amount_total_seed"),
            "current_trade_days_seed": item.get("current_trade_days_seed"),
            "elapsed_units": _first_present(item, "elapsed_units", "current_trade_days_seed"),
            "total_units": _first_present(item, "total_units") or HIGHER_PERIOD_CONTEXT_TOTAL_UNITS[period],
            "period_baseline_ready": item.get("period_baseline_ready"),
            "previous_transition": item.get("previous_transition"),
            "freshness_status": item.get("freshness_status"),
            "baseline_source_trade_date": item.get("baseline_source_trade_date"),
        }
    trace = {
        "period_trigger_baseline_source": source_kind,
        "source_context_run_id": str(row.get("run_id") or row.get("source_context_run_id") or ""),
        "source_condition_run_id": str(row.get("source_condition_run_id") or ""),
        "source_condition_pool_id": row.get("source_condition_pool_id"),
        "source_minute_target_scope_id": row.get("source_minute_target_scope_id"),
        "source_condition_basis_id": row.get("source_condition_basis_id"),
        "context_condition_key": row.get("condition_key"),
        "context_direction": row.get("direction"),
        "baseline_version": baseline.get("baseline_version"),
        "amount_metric_rule": baseline.get("amount_metric_rule"),
        "periods": sorted(context),
    }
    return context, trace


def _iter_context_payload_rows(
    source_payload: Mapping[str, Any],
    keys: Sequence[str],
) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    for key in keys:
        value = source_payload.get(key)
        if isinstance(value, Mapping):
            items = value.get("rows") or value.get("items")
            if isinstance(items, Sequence) and not isinstance(items, (str, bytes)):
                rows.extend(item for item in items if isinstance(item, Mapping))
            else:
                rows.extend(item for item in value.values() if isinstance(item, Mapping))
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            rows.extend(item for item in value if isinstance(item, Mapping))
    return rows


def _n2_scope_higher_period_context_fallback_allowed(
    contract: Mapping[str, Any],
    source_payload: Mapping[str, Any],
) -> bool:
    for container in (contract, _source_scope(contract), _db_input_contract(contract), source_payload):
        if not isinstance(container, Mapping):
            continue
        for key in (
            "allow_n2_scope_higher_period_context_fallback",
            "allow_n2_period_context_fallback",
        ):
            if key in container:
                return _truthy(container.get(key))
    return False


def build_higher_period_context_index(
    contract: Mapping[str, Any],
    source_payload: Mapping[str, Any],
) -> dict[str, dict[tuple[str, ...], list[dict[str, Any]]]]:
    index: dict[str, dict[tuple[str, ...], list[dict[str, Any]]]] = {
        "by_pool_scope": {},
        "by_identity_condition": {},
        "by_identity_direction": {},
    }
    entry_id = 0
    for row in _iter_context_payload_rows(source_payload, N4_CONTEXT_SNAPSHOT_PAYLOAD_KEYS):
        if str(row.get("quality_status") or "passed") != "passed":
            continue
        context, trace = higher_period_context_from_period_baseline_row(row, source_kind="n4_context_snapshot")
        if context:
            _register_higher_period_context_entry(
                index,
                row=row,
                entry={"context": context, "trace": trace, "entry_id": entry_id},
                allow_existing=True,
            )
            entry_id += 1
    if not _n2_scope_higher_period_context_fallback_allowed(contract, source_payload):
        return index
    for row in _iter_context_payload_rows(source_payload, N2_CONTEXT_SCOPE_PAYLOAD_KEYS):
        context, trace = higher_period_context_from_period_baseline_row(row, source_kind="n2_scope")
        if context:
            _register_higher_period_context_entry(
                index,
                row=row,
                entry={"context": context, "trace": trace, "entry_id": entry_id},
                allow_existing=False,
            )
            entry_id += 1
    return index


def _append_context_entry(
    index: dict[str, dict[tuple[str, ...], list[dict[str, Any]]]],
    bucket: str,
    key: tuple[str, ...] | None,
    entry: dict[str, Any],
    *,
    allow_existing: bool,
) -> None:
    if key is None or any(part == "" for part in key):
        return
    entries = index[bucket].setdefault(key, [])
    if entries and not allow_existing:
        return
    entries.append(entry)


def _register_higher_period_context_entry(
    index: dict[str, dict[tuple[str, ...], list[dict[str, Any]]]],
    *,
    row: Mapping[str, Any],
    entry: dict[str, Any],
    allow_existing: bool,
) -> None:
    _append_context_entry(index, "by_pool_scope", _context_pool_scope_key(row), entry, allow_existing=allow_existing)
    _append_context_entry(index, "by_identity_condition", _context_index_key(row), entry, allow_existing=allow_existing)
    _append_context_entry(index, "by_identity_direction", _context_direction_key(row), entry, allow_existing=allow_existing)


def _candidate_pool_scope_keys(candidate: Mapping[str, Any]) -> list[tuple[str, str]]:
    pool_ids = _candidate_values(
        candidate,
        scalar_keys=("source_condition_pool_id",),
        sequence_keys=("source_condition_pool_ids",),
    )
    scope_ids = _candidate_values(
        candidate,
        scalar_keys=("source_minute_target_scope_id", "source_scope_id"),
        sequence_keys=("source_minute_target_scope_ids", "source_scope_ids"),
    )
    return [(pool_id, scope_id) for pool_id in pool_ids for scope_id in scope_ids]


def _candidate_identity_tuple(candidate: Mapping[str, Any]) -> tuple[str, str] | None:
    return _context_identity_tuple(candidate)


def _candidate_identity_condition_keys(
    candidate: Mapping[str, Any],
    condition_keys: Sequence[str],
) -> list[tuple[str, str, str]]:
    identity = _candidate_identity_tuple(candidate)
    if identity is None:
        return []
    return [(*identity, condition_key) for condition_key in condition_keys if condition_key]


def _candidate_direction_key(candidate: Mapping[str, Any]) -> tuple[str, str, str] | None:
    identity = _candidate_identity_tuple(candidate)
    if identity is None:
        return None
    direction = str(candidate.get("direction") or _direction_for_signal(candidate.get("signal_type"), candidate.get("condition_key")))
    if not direction:
        return None
    return (*identity, direction)


def _dedupe_context_entries(entries: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    output: list[Mapping[str, Any]] = []
    seen: set[Any] = set()
    for entry in entries:
        entry_id = entry.get("entry_id")
        if entry_id in seen:
            continue
        seen.add(entry_id)
        output.append(entry)
    return output


def _with_match_trace(
    entry: Mapping[str, Any],
    *,
    candidate: Mapping[str, Any],
    strategy: str,
) -> dict[str, Any]:
    trace = dict(entry.get("trace") or {})
    trace["higher_period_context_match_strategy"] = strategy
    original_condition_key = str(candidate.get("original_condition_key") or "")
    if original_condition_key:
        trace["original_condition_key"] = original_condition_key
    condition_keys = _candidate_values(candidate, sequence_keys=("condition_keys",))
    if condition_keys:
        trace["candidate_condition_keys"] = condition_keys
    return {
        "context": entry.get("context") or {},
        "trace": trace,
        "entry_id": entry.get("entry_id"),
    }


def _select_context_entry(
    context_index: Mapping[str, Mapping[tuple[str, ...], Sequence[Mapping[str, Any]]]],
    *,
    bucket: str,
    keys: Sequence[tuple[str, ...]],
    candidate: Mapping[str, Any],
    strategy: str,
) -> Mapping[str, Any]:
    entries: list[Mapping[str, Any]] = []
    bucket_index = context_index.get(bucket) or {}
    for key in keys:
        entries.extend(bucket_index.get(key) or [])
    matches = _dedupe_context_entries(entries)
    if len(matches) > 1:
        raise VirtualMetricWriterBlocked(
            "BLOCKED_NEED_INPUT_RESOLVER: higher_period_context_ambiguous_match "
            f"{strategy} {candidate.get('identity_key')} {candidate.get('condition_key')}"
        )
    if len(matches) == 1:
        return _with_match_trace(matches[0], candidate=candidate, strategy=strategy)
    return {}


def _higher_period_context_entry(
    context_index: Mapping[str, Mapping[tuple[str, ...], Sequence[Mapping[str, Any]]]],
    candidate: Mapping[str, Any],
) -> Mapping[str, Any]:
    entry = _select_context_entry(
        context_index,
        bucket="by_pool_scope",
        keys=_candidate_pool_scope_keys(candidate),
        candidate=candidate,
        strategy="source_condition_pool_id+source_minute_target_scope_id",
    )
    if entry:
        return entry
    original_condition_keys = _candidate_values(candidate, scalar_keys=("original_condition_key",))
    entry = _select_context_entry(
        context_index,
        bucket="by_identity_condition",
        keys=_candidate_identity_condition_keys(candidate, original_condition_keys),
        candidate=candidate,
        strategy="asset_kind+identity_key+original_condition_key",
    )
    if entry:
        return entry
    condition_keys = _candidate_values(candidate, sequence_keys=("condition_keys",))
    entry = _select_context_entry(
        context_index,
        bucket="by_identity_condition",
        keys=_candidate_identity_condition_keys(candidate, condition_keys),
        candidate=candidate,
        strategy="asset_kind+identity_key+condition_keys",
    )
    if entry:
        return entry
    exact_condition_keys = _candidate_values(candidate, scalar_keys=("condition_key",))
    entry = _select_context_entry(
        context_index,
        bucket="by_identity_condition",
        keys=_candidate_identity_condition_keys(candidate, exact_condition_keys),
        candidate=candidate,
        strategy="asset_kind+identity_key+condition_key",
    )
    if entry:
        return entry
    direction_key = _candidate_direction_key(candidate)
    direction_keys = [direction_key] if direction_key is not None else []
    return _select_context_entry(
        context_index,
        bucket="by_identity_direction",
        keys=direction_keys,
        candidate=candidate,
        strategy="asset_kind+identity_key+direction_unique",
    )


def _context_values_conflict(left: Any, right: Any) -> bool:
    if left in (None, "") or right in (None, ""):
        return False
    left_decimal = decimal_or_none(left)
    right_decimal = decimal_or_none(right)
    if left_decimal is not None and right_decimal is not None:
        return not decimals_close(left_decimal, right_decimal)
    return str(left) != str(right)


def merge_higher_period_context(
    *,
    candidate: Mapping[str, Any],
    resolved_entry: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    candidate_context_raw = candidate.get("higher_period_context")
    candidate_context = candidate_context_raw if isinstance(candidate_context_raw, Mapping) else {}
    resolved_context = resolved_entry.get("context") if isinstance(resolved_entry.get("context"), Mapping) else {}
    resolved_trace = resolved_entry.get("trace") if isinstance(resolved_entry.get("trace"), Mapping) else {}
    merged: dict[str, dict[str, Any]] = {}
    conflicts: list[str] = []
    for period in HIGHER_PERIOD_CONTEXT_PERIODS:
        candidate_item = candidate_context.get(period) if isinstance(candidate_context.get(period), Mapping) else {}
        resolved_item = resolved_context.get(period) if isinstance(resolved_context.get(period), Mapping) else {}
        output = dict(candidate_item or {})
        for field, value in dict(resolved_item or {}).items():
            if field in output:
                if field in HIGHER_PERIOD_CONTEXT_NUMERIC_FIELDS and _context_values_conflict(output.get(field), value):
                    conflicts.append(f"{period}.{field}")
                continue
            if value not in (None, ""):
                output[field] = value
        if output:
            merged[period] = output
    if conflicts:
        identity_key = candidate.get("identity_key")
        condition_key = candidate.get("condition_key")
        raise VirtualMetricWriterBlocked(
            "BLOCKED_NEED_INPUT_RESOLVER: higher_period_context_conflict "
            f"{identity_key} {condition_key} {','.join(sorted(conflicts))}"
        )
    trace = dict(resolved_trace)
    if trace:
        trace["merge_policy"] = "db_backed_context_fills_missing_candidate_fields"
        trace["candidate_context_periods"] = sorted(
            period for period, item in candidate_context.items() if isinstance(item, Mapping) and item
        )
        trace["merged_context_periods"] = sorted(merged)
    return merged, trace


def _required_amount_chain_periods(condition_key: Any, signal_type: Any) -> list[str]:
    key = str(condition_key or signal_type or "")
    if key in {"BUY_HINT", "SELL_HINT"}:
        return []
    if ":FULL" in key:
        return ["D"]
    if ":" not in key:
        return []
    period_text = key.split(":", 1)[1]
    periods = [
        period.strip().upper()
        for period in period_text.split(",")
        if period.strip().upper() in {"D", "W", "M", "Q"}
    ]
    return sorted(set(periods), key=("D", "W", "M", "Q").index)


def _amount_chain_condition_key(candidate: Mapping[str, Any]) -> Any:
    for key in _candidate_values(candidate, scalar_keys=("original_condition_key",), sequence_keys=("condition_keys",)):
        if _required_amount_chain_periods(key, candidate.get("signal_type")):
            return key
    return candidate.get("condition_key")


def _formal_amount_chain_specs() -> dict[str, dict[str, str]]:
    return {
        "D": {
            "left": "today_virt_amount",
            "middle": "weekly_avg_with_today",
            "baseline": "prev_weekly_avg",
            "proof_period": "W",
        },
        "W": {
            "left": "weekly_avg_with_today",
            "middle": "monthly_avg_with_today",
            "baseline": "prev_monthly_avg",
            "proof_period": "M",
        },
        "M": {
            "left": "monthly_avg_with_today",
            "middle": "quarterly_avg_with_today",
            "baseline": "prev_quarterly_avg",
            "proof_period": "Q",
        },
        "Q": {
            "left": "quarterly_avg_with_today",
            "middle": "yearly_avg_with_today",
            "baseline": "prev_yearly_avg",
            "proof_period": "Y",
        },
    }


def _current_period_avg_with_today_fields() -> dict[str, str]:
    return {
        "D": "today_virt_amount",
        "W": "weekly_avg_with_today",
        "M": "monthly_avg_with_today",
        "Q": "quarterly_avg_with_today",
        "Y": "yearly_avg_with_today",
    }


def _direction_for_signal(signal_type: Any, condition_key: Any) -> str:
    text = f"{signal_type} {condition_key}".upper()
    if "SELL" in text or "S_SELL" in text:
        return "sell"
    if "BUY" in text or "B_BUY" in text:
        return "buy"
    return ""


def _formal_amount_input_trace_by_period(
    *,
    output: Mapping[str, Any],
    specs: Mapping[str, Mapping[str, str]],
    direction: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    transition_inputs: dict[str, dict[str, Any]] = {}
    amount_chain_inputs: dict[str, dict[str, Any]] = {}
    comparison = "left <= middle <= baseline" if direction == "sell" else "left >= middle >= baseline"
    current_avg_fields = _current_period_avg_with_today_fields()
    for period in ("D", "W", "M", "Q", "Y"):
        current_avg_field = current_avg_fields[period]
        transition_inputs[period] = {
            "current_price_or_close_field": "current_price",
            "price_compare_to": f"trigger_previous_entity_high[{period}]"
            if direction != "sell"
            else f"trigger_previous_entity_low[{period}]",
            "current_period_avg_with_today_field": current_avg_field,
            "current_period_avg_with_today_value": output.get(current_avg_field),
            "used_for_period": period,
            "compare_to": f"previous_avg_amount[{period}]",
            "semantic": "current_period_avg_with_today[P] uses the same period as P for transition checks",
        }
    for period in ("D", "W", "M", "Q"):
        spec = specs[period]
        amount_chain_inputs[period] = {
            "left_field": spec["left"],
            "left_value": output.get(spec["left"]),
            "middle_field": spec["middle"],
            "middle_value": output.get(spec["middle"]),
            "baseline_field": spec["baseline"],
            "baseline_value": output.get(spec["baseline"]),
            "used_for_period": period,
            "comparison": comparison,
            "semantic": "period average amount-chain input, separate from transition current_period_avg_with_today[P]",
        }
    return transition_inputs, amount_chain_inputs


def apply_formal_amount_chain_contract(
    *,
    metric: Mapping[str, Any],
    candidate: Mapping[str, Any],
    higher_period_context_source: Mapping[str, Any],
) -> dict[str, Any]:
    output = dict(metric)
    trace_json = dict(output.get("trace_json") or {})
    raw_json = dict(output.get("raw_json") or {})
    proof = trace_json.get("formal_period_amount_proof")
    proof_periods = proof.get("periods") if isinstance(proof, Mapping) and isinstance(proof.get("periods"), Mapping) else {}
    required_periods = _required_amount_chain_periods(_amount_chain_condition_key(candidate), candidate.get("signal_type"))
    specs = _formal_amount_chain_specs()
    direction = _direction_for_signal(candidate.get("signal_type"), candidate.get("condition_key"))
    trigger_pass: dict[str, Any] = {"Y": "not_applicable"}
    input_ready: dict[str, bool] = {}
    missing_inputs: dict[str, list[str]] = {}
    for period in ("D", "W", "M", "Q"):
        spec = specs[period]
        proof_period = proof_periods.get(spec["proof_period"]) if isinstance(proof_periods.get(spec["proof_period"]), Mapping) else {}
        missing = [
            field
            for field in (spec["left"], spec["middle"], spec["baseline"])
            if output.get(field) in (None, "")
        ]
        if proof_period.get("avg_status") != "passed":
            reason = str(proof_period.get("avg_blocked_reason") or f"{spec['proof_period']}_avg_not_passed")
            missing.append(reason)
        input_ready[period] = not missing
        missing_inputs[period] = sorted(set(missing))
        if missing:
            trigger_pass[period] = None
            continue
        left = decimal_or_none(output.get(spec["left"]))
        middle = decimal_or_none(output.get(spec["middle"]))
        baseline = decimal_or_none(output.get(spec["baseline"]))
        if left is None or middle is None or baseline is None or not direction:
            trigger_pass[period] = None
            continue
        if direction == "sell":
            trigger_pass[period] = left <= middle <= baseline
        else:
            trigger_pass[period] = left >= middle >= baseline
    blocked_reasons = list(output.get("blocked_reasons") or [])
    for period in required_periods:
        if input_ready.get(period):
            continue
        for missing in missing_inputs.get(period) or ["formal_amount_chain_input_missing"]:
            blocked_reasons.append(f"formal_amount_chain_missing:{period}:{missing}")
    if higher_period_context_source:
        trace_json["higher_period_context_source"] = dict(higher_period_context_source)
        raw_json["higher_period_context_source"] = dict(higher_period_context_source)
    trace_json["formal_amount_chain_required_periods"] = required_periods
    trace_json["formal_amount_chain_input_ready"] = input_ready
    trace_json["formal_amount_chain_missing_inputs"] = missing_inputs
    trace_json["trigger_amount_chain_pass"] = trigger_pass
    raw_json["formal_amount_chain_required_periods"] = required_periods
    raw_json["formal_amount_chain_input_ready"] = input_ready
    raw_json["formal_amount_chain_missing_inputs"] = missing_inputs
    raw_json["trigger_amount_chain_pass"] = trigger_pass
    transition_inputs, amount_chain_inputs = _formal_amount_input_trace_by_period(
        output=output,
        specs=specs,
        direction=direction,
    )
    trace_json["transition_input_by_period"] = transition_inputs
    trace_json["amount_chain_input_by_period"] = amount_chain_inputs
    raw_json["transition_input_by_period"] = transition_inputs
    raw_json["amount_chain_input_by_period"] = amount_chain_inputs
    if blocked_reasons:
        output["metric_ready"] = False
        output["quality_status"] = "failed"
        output["blocked_reasons"] = sorted(set(str(reason) for reason in blocked_reasons))
        trace_json["blocked_reasons"] = output["blocked_reasons"]
        raw_json["blocked_reasons"] = output["blocked_reasons"]
    output["trace_json"] = trace_json
    output["raw_json"] = raw_json
    return output


def _is_b1_trigger_proof_segment_blocker(reason: str) -> bool:
    return reason in {
        "previous_5m_not_found",
        "previous_30m_not_found",
        "previous_120m_not_found",
    } or reason.startswith(
        (
            "current_5m_virtual_amount_calibration_failed:",
            "current_30m_virtual_amount_calibration_failed:",
        )
    )


def apply_b1_source_returned_trigger_proof_readiness(
    *,
    contract: Mapping[str, Any],
    candidate: Mapping[str, Any],
    metric: Mapping[str, Any],
) -> dict[str, Any]:
    output = dict(metric)
    if not _is_b1_source_returned_snapshot_source(contract, candidate):
        return output

    trace_json = dict(output.get("trace_json") or {})
    raw_json = dict(output.get("raw_json") or {})
    original_blockers = sorted(set(str(reason) for reason in output.get("blocked_reasons") or []))
    segment_blockers = [reason for reason in original_blockers if _is_b1_trigger_proof_segment_blocker(reason)]
    trigger_blockers = [reason for reason in original_blockers if not _is_b1_trigger_proof_segment_blocker(reason)]
    trigger_proof_ready = not trigger_blockers

    output["metric_ready"] = trigger_proof_ready
    output["quality_status"] = "passed" if trigger_proof_ready else "failed"
    output["blocked_reasons"] = trigger_blockers
    trigger_proof_ready_reason = (
        "n4_ordinary_trigger_proof_ready"
        if trigger_proof_ready
        else "trigger_proof_blocked:" + ",".join(trigger_blockers)
    )
    action_confirmation_blocked_reasons = original_blockers
    proof_fields = {
        "metric_role": "trigger_proof",
        "proof_owner": "N3",
        "proof_consumer": "N4",
        "not_n5_final_proof": True,
        "trigger_proof_ready": trigger_proof_ready,
        "trigger_proof_ready_reason": trigger_proof_ready_reason,
        "action_confirmation_ready": False,
        "action_confirmation_ready_reason": "not_n5_final_proof",
        "previous_5m_required_for_trigger_proof": False,
        "previous_5m_status": "not_required_for_trigger_proof",
        "segment_30m_status": "not_required_for_trigger_proof",
        "segment_120m_status": "not_required_for_trigger_proof",
        "action_confirmation_blocked_reasons": action_confirmation_blocked_reasons,
    }
    trace_json.update(proof_fields)
    raw_json.update(proof_fields)
    trace_json["blocked_reasons"] = trigger_blockers
    raw_json["blocked_reasons"] = trigger_blockers
    if segment_blockers:
        trace_json["segment_blocked_reasons_not_required_for_trigger_proof"] = segment_blockers
        raw_json["segment_blocked_reasons_not_required_for_trigger_proof"] = segment_blockers
    db_segment_source_compat = {
        "previous_1m_period_source": output.get("previous_1m_period_source"),
        "previous_5m_period_source": output.get("previous_5m_period_source"),
        "previous_30m_period_source": output.get("previous_30m_period_source"),
        "previous_120m_period_source": output.get("previous_120m_period_source"),
        "db_facing_value": "not_available",
        "reason": "trigger_proof_does_not_use_action_confirmation_segments",
    }
    for key in (
        "previous_1m_period_source",
        "previous_5m_period_source",
        "previous_30m_period_source",
        "previous_120m_period_source",
    ):
        output[key] = "not_available"
    trace_json["trigger_proof_segment_source_db_compat"] = db_segment_source_compat
    raw_json["trigger_proof_segment_source_db_compat"] = db_segment_source_compat
    output["trace_json"] = trace_json
    output["raw_json"] = raw_json
    return output


def _iter_b1_source_returned_snapshot_rows(source_payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return _iter_context_payload_rows(source_payload, B1_SOURCE_RETURNED_SNAPSHOT_PAYLOAD_KEYS)


def _identity_kind_from_key(identity_key: str) -> str:
    if identity_key.startswith("stock:"):
        return "stock"
    if identity_key.startswith("index:"):
        return "index"
    if identity_key.startswith("board:"):
        return "board"
    return ""


def _b1_snapshot_identity_tuple(row: Mapping[str, Any]) -> tuple[str, str]:
    asset_kind = str(row.get("asset_kind") or "")
    identity_key = _context_identity_key(row, asset_kind)
    if asset_kind not in ASSET_KINDS or not identity_key:
        raise VirtualMetricWriterBlocked("BLOCKED_N3P_B1_PAYLOAD_SELECTION_ASSET_MISMATCH")
    identity_kind = _identity_kind_from_key(identity_key)
    if identity_kind and identity_kind != asset_kind:
        raise VirtualMetricWriterBlocked("BLOCKED_N3P_B1_PAYLOAD_SELECTION_ASSET_MISMATCH")
    return asset_kind, identity_key


def _b1_snapshot_proof_input_time(row: Mapping[str, Any]) -> str:
    raw_json = _mapping_from_jsonish(row.get("raw_json"))
    return _first_lineage_value(
        row,
        raw_json,
        keys=(
            "proof_input_time",
            "source_snapshot_time",
            "effective_source_time",
            "snapshot_time",
            "source_time",
            "observed_at",
            "fetched_at",
        ),
    )


def _minute_label_from_proof_time(value: Any) -> str:
    text = str(value or "").replace("T", " ")
    if len(text) >= 16 and text[10] == " ":
        return text[:16]
    return ""


def _snapshot_row_key(row: Mapping[str, Any], *, asset_kind: str, identity_key: str, proof_hhmm: str) -> str:
    value = (
        row.get("source_snapshot_row_id")
        or row.get("source_snapshot_id")
        or row.get("snapshot_row_id")
        or row.get("snapshot_id")
    )
    if value not in (None, ""):
        return str(value)
    return f"{asset_kind}:{identity_key}:{proof_hhmm}"


def _context_signal_type(row: Mapping[str, Any]) -> str:
    signal_type = str(row.get("signal_type") or "")
    if signal_type:
        return signal_type
    direction = str(row.get("direction") or "").lower()
    if direction == "sell":
        return "S_SELL"
    if direction == "buy":
        return "B_BUY"
    return ""


def _b1_source_returned_stable_candidate_key(candidate: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        candidate.get("asset_kind"),
        candidate.get("identity_key"),
        candidate.get("direction"),
        candidate.get("signal_type"),
        candidate.get("condition_key"),
        candidate.get("original_condition_key"),
        candidate.get("source_condition_pool_id"),
        candidate.get("source_minute_target_scope_id"),
        candidate.get("proof_input_minute_label"),
    )


def _snapshot_condition_ids_allow_context(
    snapshot_row: Mapping[str, Any],
    *,
    scalar_key: str,
    sequence_keys: Sequence[str],
    expected: Any,
) -> bool:
    values = _candidate_values(snapshot_row, scalar_keys=(scalar_key,), sequence_keys=sequence_keys)
    if not values:
        return True
    return _stable_context_id(expected) in values


def _build_b1_source_returned_candidate(
    *,
    contract: Mapping[str, Any],
    snapshot_row: Mapping[str, Any],
    context_row: Mapping[str, Any],
    proof_input_time: str,
    proof_hhmm: str,
    proof_minute_label: str,
) -> dict[str, Any]:
    context_identity = _context_identity_tuple(context_row)
    snapshot_asset_kind, snapshot_identity_key = _b1_snapshot_identity_tuple(snapshot_row)
    if context_identity is None or context_identity != (snapshot_asset_kind, snapshot_identity_key):
        raise VirtualMetricWriterBlocked("BLOCKED_N3P_B1_PAYLOAD_SELECTION_ASSET_MISMATCH")
    context, context_trace = higher_period_context_from_period_baseline_row(
        context_row,
        source_kind="n4_context_snapshot",
    )
    if not context:
        raise VirtualMetricWriterBlocked("BLOCKED_N3P_B1_PAYLOAD_SELECTION_MISSING_CONTEXT")
    condition_key = str(context_row.get("condition_key") or "")
    direction = str(context_row.get("direction") or _direction_for_signal(context_row.get("signal_type"), condition_key))
    signal_type = _context_signal_type(context_row)
    if not condition_key or not direction or not signal_type:
        raise VirtualMetricWriterBlocked("BLOCKED_N3P_B1_PAYLOAD_SELECTION_MISSING_CONTEXT")
    if not _snapshot_condition_ids_allow_context(
        snapshot_row,
        scalar_key="source_condition_pool_id",
        sequence_keys=("source_condition_pool_ids",),
        expected=context_row.get("source_condition_pool_id"),
    ) or not _snapshot_condition_ids_allow_context(
        snapshot_row,
        scalar_key="source_minute_target_scope_id",
        sequence_keys=("source_minute_target_scope_ids", "source_scope_ids"),
        expected=context_row.get("source_minute_target_scope_id"),
    ):
        raise VirtualMetricWriterBlocked("BLOCKED_N3P_B1_PAYLOAD_SELECTION_SCOPE_MISMATCH")
    raw_target_minute_label = _raw_target_minute_label(contract, snapshot_row)
    source_snapshot_run_id = _lineage_value(
        candidate=snapshot_row,
        contract=contract,
        key="source_snapshot_run_id",
        fallback="",
    )
    source_snapshot_row_id = _snapshot_row_key(
        snapshot_row,
        asset_kind=snapshot_asset_kind,
        identity_key=snapshot_identity_key,
        proof_hhmm=proof_hhmm,
    )
    raw_json = dict(snapshot_row.get("raw_json") or {})
    raw_json["b1_source_returned_payload_selection"] = {
        "selection_policy": "n4_context_condition_grain_expands_b1_object_snapshot",
        "source_context_run_id": context_trace.get("source_context_run_id"),
        "source_condition_pool_id": context_row.get("source_condition_pool_id"),
        "source_minute_target_scope_id": context_row.get("source_minute_target_scope_id"),
        "source_snapshot_run_id": source_snapshot_run_id,
        "source_snapshot_row_id": source_snapshot_row_id,
        "proof_input_minute_label": proof_hhmm,
        "raw_target_minute_label": raw_target_minute_label,
    }
    return {
        "asset_kind": snapshot_asset_kind,
        "identity_key": snapshot_identity_key,
        "exchange": snapshot_row.get("exchange"),
        "code": str(snapshot_row.get("code") or snapshot_row.get("display_code") or snapshot_identity_key.rsplit(":", 1)[-1]),
        "display_code": snapshot_row.get("display_code") or snapshot_row.get("code"),
        "name": snapshot_row.get("name") or snapshot_identity_key,
        "signal_type": signal_type,
        "condition_key": condition_key,
        "original_condition_key": str(context_row.get("original_condition_key") or condition_key),
        "condition_keys": [condition_key],
        "direction": direction,
        "source_condition_pool_id": context_row.get("source_condition_pool_id"),
        "source_minute_target_scope_id": context_row.get("source_minute_target_scope_id"),
        "source_scope_id": context_row.get("source_minute_target_scope_id"),
        "source_condition_basis_id": context_row.get("source_condition_basis_id"),
        "source_context_run_id": context_row.get("run_id") or context_row.get("source_context_run_id"),
        "source_trigger_context_id": context_row.get("trigger_context_id"),
        "source_snapshot_run_id": source_snapshot_run_id,
        "source_snapshot_row_id": source_snapshot_row_id,
        "source_snapshot_id": snapshot_row.get("source_snapshot_id") or snapshot_row.get("snapshot_id"),
        "source_record_key": str(snapshot_row.get("source_record_key") or snapshot_row.get("code") or ""),
        "minute_label": proof_minute_label,
        "observed_at": snapshot_row.get("observed_at"),
        "fetched_at": snapshot_row.get("fetched_at"),
        "source_time_policy": SOURCE_RETURNED_TIME_POLICY_MODE,
        "proof_input_time": proof_input_time,
        "proof_input_time_source": "B1_source_snapshot_time",
        "proof_input_minute_label": proof_hhmm,
        "source_snapshot_time": proof_input_time,
        "raw_target_minute_label": raw_target_minute_label,
        "higher_period_context": context,
        "raw_json": raw_json,
    }


def build_b1_source_returned_payload_selection(
    contract: Mapping[str, Any],
    source_payload: Mapping[str, Any],
) -> dict[str, Any]:
    if not _is_b1_source_returned_snapshot_source(contract):
        return dict(source_payload)
    if source_payload.get("candidates"):
        return dict(source_payload)

    contract_proof_input_time = _assert_b1_source_returned_target_time(contract)
    expected_hhmm = _hhmm_from_time_value(contract_proof_input_time)
    snapshot_rows = _iter_b1_source_returned_snapshot_rows(source_payload)
    context_rows = [
        row
        for row in _iter_context_payload_rows(source_payload, N4_CONTEXT_SNAPSHOT_PAYLOAD_KEYS)
        if str(row.get("quality_status") or "passed") == "passed"
    ]
    snapshots_by_identity: dict[tuple[str, str], Mapping[str, Any]] = {}
    for snapshot_row in snapshot_rows:
        key = _b1_snapshot_identity_tuple(snapshot_row)
        if key in snapshots_by_identity:
            raise VirtualMetricWriterBlocked("BLOCKED_N3P_B1_PAYLOAD_SELECTION_DUPLICATE")
        snapshots_by_identity[key] = snapshot_row

    selected: list[dict[str, Any]] = []
    missing_snapshot_count = 0
    missing_context_count = 0
    for context_row in context_rows:
        context_identity = _context_identity_tuple(context_row)
        if context_identity is None:
            missing_context_count += 1
            continue
        if not _period_trigger_baseline_from_row(context_row):
            missing_context_count += 1
            continue
        snapshot_row = snapshots_by_identity.get(context_identity)
        if snapshot_row is None:
            missing_snapshot_count += 1
            continue
        proof_input_time = _b1_snapshot_proof_input_time(snapshot_row)
        proof_hhmm = _hhmm_from_time_value(proof_input_time)
        if proof_hhmm != expected_hhmm:
            raise VirtualMetricWriterBlocked("BLOCKED_N3P_SOURCE_TIME_RELABEL_RISK")
        proof_minute_label = _minute_label_from_proof_time(proof_input_time)
        if not proof_minute_label:
            raise VirtualMetricWriterBlocked("BLOCKED_N3P_SOURCE_TIME_RELABEL_RISK")
        selected.append(
            _build_b1_source_returned_candidate(
                contract=contract,
                snapshot_row=snapshot_row,
                context_row=context_row,
                proof_input_time=proof_input_time,
                proof_hhmm=proof_hhmm,
                proof_minute_label=proof_minute_label,
            )
        )

    duplicate_keys = [
        key
        for key, count in Counter(_b1_source_returned_stable_candidate_key(candidate) for candidate in selected).items()
        if count > 1
    ]
    duplicate_count = len(duplicate_keys)
    selected_counts_by_asset = {asset: 0 for asset in ASSET_KINDS}
    for candidate in selected:
        selected_counts_by_asset[str(candidate.get("asset_kind"))] += 1

    report = {
        "status": "passed",
        "selection_policy": "n4_context_condition_grain_expands_b1_object_snapshot",
        "b1_snapshot_object_count": len(snapshot_rows),
        "n4_context_row_count": len(context_rows),
        "selected_candidate_count": len(selected),
        "selected_counts_by_asset": selected_counts_by_asset,
        "duplicate_count": duplicate_count,
        "missing_snapshot_count": missing_snapshot_count,
        "missing_context_count": missing_context_count,
        "proof_input_minute_label": expected_hhmm,
    }
    if duplicate_count:
        report["status"] = "blocked"
        raise VirtualMetricWriterBlocked("BLOCKED_N3P_B1_PAYLOAD_SELECTION_DUPLICATE")
    if missing_snapshot_count:
        report["status"] = "blocked"
        raise VirtualMetricWriterBlocked("BLOCKED_N3P_B1_PAYLOAD_SELECTION_MISSING_SNAPSHOT")
    if missing_context_count:
        report["status"] = "blocked"
        raise VirtualMetricWriterBlocked("BLOCKED_N3P_B1_PAYLOAD_SELECTION_MISSING_CONTEXT")
    if not selected:
        report["status"] = "blocked"
        raise VirtualMetricWriterBlocked("BLOCKED_N3P_B1_PAYLOAD_SELECTION_MISSING_CONTEXT")

    output = dict(source_payload)
    output["candidates"] = selected
    output["b1_source_returned_payload_selection_report"] = report
    return output


def build_n3p_stock_quote_symbol_batches(
    symbols: Sequence[Any],
    *,
    batch_size: int = N3P_STOCK_QUOTE_BATCH_SIZE,
) -> list[list[str]]:
    normalized = [str(symbol) for symbol in symbols if str(symbol or "")]
    return [normalized[idx : idx + batch_size] for idx in range(0, len(normalized), batch_size)]


def _payload_rows(source_payload: Mapping[str, Any], *keys: str) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    for key in keys:
        value = source_payload.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            rows.extend(row for row in value if isinstance(row, Mapping))
    return rows


def _n3p_float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _stock_quote_zero_price_ohlc_volume(row: Mapping[str, Any]) -> bool:
    price = _n3p_float_or_none(row.get("price") if row.get("price") is not None else row.get("close"))
    quote_open = _n3p_float_or_none(row.get("open"))
    high = _n3p_float_or_none(row.get("high"))
    low = _n3p_float_or_none(row.get("low"))
    volume = _n3p_float_or_none(row.get("volume"))
    price_ohlc = (price, quote_open, high, low)
    if any(value is not None and value <= 0 for value in price_ohlc):
        return True
    quote_values = (*price_ohlc, volume)
    return all(value is not None and value == 0 for value in quote_values)


def _has_b1_realtime_trigger_proof_source_payload(source_payload: Mapping[str, Any]) -> bool:
    return any(
        key in source_payload
        for key in (
            "stock_quote_rows",
            "stock_quotes_rows",
            "index_board_1m_rows",
            "index_1m_rows",
            "board_1m_rows",
            "previous_day_minute_rows",
        )
    )


def _source_row_is_fake(row: Mapping[str, Any]) -> bool:
    marker = str(
        row.get("source_marker")
        or row.get("source_time_marker")
        or row.get("source_kind")
        or row.get("raw_source_kind")
        or ""
    ).lower()
    return any(token in marker for token in ("fake", "synthetic", "fabricated"))


def _source_row_matches_candidate(row: Mapping[str, Any], candidate: Mapping[str, Any]) -> bool:
    row_asset_kind = str(row.get("asset_kind") or "")
    candidate_asset_kind = str(candidate.get("asset_kind") or "")
    if row_asset_kind and row_asset_kind != candidate_asset_kind:
        return False
    row_identity = str(row.get("identity_key") or row.get(f"{candidate_asset_kind}_identity_key") or "")
    candidate_identity = str(candidate.get("identity_key") or "")
    if row_identity and candidate_identity and row_identity == candidate_identity:
        return True
    return str(row.get("code") or "") == str(candidate.get("code") or "")


def _for_trade_date_label(contract: Mapping[str, Any]) -> str:
    raw = str(_source_scope(contract).get("for_trade_date") or contract.get("for_trade_date") or "")
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    return raw


def _source_minute_label_from_row(row: Mapping[str, Any], *, contract: Mapping[str, Any]) -> str:
    for key in ("proof_input_time", "source_time", "datetime", "bar_time", "minute_label"):
        value = row.get(key)
        if value:
            return _minute_label_from_proof_time(value)
    servertime = str(row.get("servertime") or "")
    if servertime:
        date_label = _for_trade_date_label(contract)
        return f"{date_label} {servertime[:5]}"
    return ""


def _candidate_previous_day_rows(candidate: Mapping[str, Any], source_payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    indexed = source_payload.get("previous_day_minute_rows_by_identity")
    if isinstance(indexed, Mapping):
        candidate_asset_kind = str(candidate.get("asset_kind") or "")
        candidate_identity = str(candidate.get("identity_key") or "")
        candidate_code = str(candidate.get("code") or "")
        for key in (
            f"{candidate_asset_kind}|{candidate_identity}",
            f"{candidate_asset_kind}|{candidate_code}",
            candidate_identity,
            candidate_code,
        ):
            value = indexed.get(key)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
                return [row for row in value if isinstance(row, Mapping)]
    rows = _payload_rows(
        source_payload,
        "previous_day_minute_rows",
        "a1_previous_day_minute_rows",
        "source_previous_day_minute_rows",
    )
    return [row for row in rows if _source_row_matches_candidate(row, candidate)]


def _contract_requires_previous_day_cumulative_rows(contract: Mapping[str, Any]) -> bool:
    scope = _source_scope(contract)
    db_contract = _db_input_contract(contract)
    return bool(
        scope.get("require_previous_day_cumulative_rows")
        or db_contract.get("require_previous_day_cumulative_rows")
        or contract.get("require_previous_day_cumulative_rows")
    )


def _yyyymmdd_to_date_label(value: Any) -> str:
    text = str(value or "")
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
        return text[:10]
    return text


def _hhmm_from_minute_label(value: Any) -> str:
    text = str(value or "").replace("T", " ")
    if len(text) >= 16 and text[10] == " ":
        return text[11:16]
    if re.fullmatch(r"\d{4}", text):
        return f"{text[:2]}:{text[2:]}"
    if re.fullmatch(r"\d{2}:\d{2}", text):
        return text
    return ""


def _previous_day_cumulative_canonical_label(*, source_trade_date: str, proof_minute_label: str) -> str:
    hhmm = _hhmm_from_minute_label(proof_minute_label)
    if not hhmm:
        raise VirtualMetricWriterBlocked("previous_day_cumulative_invalid_proof_minute_label")
    return f"{_yyyymmdd_to_date_label(source_trade_date)} {hhmm}"


def _positive_float(value: Any, *, reason: str) -> float:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise VirtualMetricWriterBlocked(reason) from None
    if number <= 0:
        raise VirtualMetricWriterBlocked(reason)
    return float(number)


def _normalize_previous_day_cumulative_asset_scope(
    asset_scope: Mapping[str, Sequence[Any]] | Sequence[Mapping[str, Any]] | None,
) -> dict[str, set[str]]:
    normalized: dict[str, set[str]] = {asset: set() for asset in ASSET_KINDS}
    if not asset_scope:
        return normalized
    if isinstance(asset_scope, Mapping):
        for asset_kind, values in asset_scope.items():
            asset = str(asset_kind)
            if asset not in normalized:
                continue
            for value in values or []:
                if isinstance(value, Mapping):
                    identity_key = str(value.get("identity_key") or value.get(f"{asset}_identity_key") or "")
                else:
                    identity_key = str(value or "")
                if identity_key:
                    normalized[asset].add(identity_key)
        return normalized
    for row in asset_scope:
        if not isinstance(row, Mapping):
            continue
        asset = str(row.get("asset_kind") or "")
        if asset not in normalized:
            continue
        identity_key = str(row.get("identity_key") or row.get(f"{asset}_identity_key") or "")
        if identity_key:
            normalized[asset].add(identity_key)
    return normalized


def alias_previous_day_cumulative_db_row_for_payload(
    row: Mapping[str, Any],
    *,
    expected_asset_kind: str,
    source_previous_day_minute_run_id: str,
    for_trade_date: str,
    source_trade_date: str,
    proof_minute_label: str,
) -> dict[str, Any]:
    """Map persisted A1 cumulative DB rows into N3P source payload shape."""

    expected_label = _previous_day_cumulative_canonical_label(
        source_trade_date=source_trade_date,
        proof_minute_label=proof_minute_label,
    )
    row_asset_kind = str(row.get("asset_kind") or "")
    if row_asset_kind != expected_asset_kind:
        raise VirtualMetricWriterBlocked("previous_day_cumulative_asset_kind_mismatch")
    if str(row.get("source_previous_day_minute_run_id") or "") != source_previous_day_minute_run_id:
        raise VirtualMetricWriterBlocked("previous_day_cumulative_source_run_mismatch")
    if str(row.get("for_trade_date") or "") != str(for_trade_date):
        raise VirtualMetricWriterBlocked("previous_day_cumulative_for_trade_date_mismatch")
    if str(row.get("source_trade_date") or "") != str(source_trade_date):
        raise VirtualMetricWriterBlocked("previous_day_cumulative_source_trade_date_mismatch")
    if str(row.get("canonical_minute_label") or "") != expected_label:
        raise VirtualMetricWriterBlocked("previous_day_cumulative_canonical_minute_mismatch")
    if int(row.get("duplicate_count") or 1) > 1:
        raise VirtualMetricWriterBlocked("previous_day_cumulative_duplicate")

    previous_day_elapsed_amount = _positive_float(
        row.get("cumulative_amount_yuan"),
        reason="previous_day_cumulative_non_positive_amount",
    )
    previous_day_full_amount = _positive_float(
        row.get("full_day_amount_yuan"),
        reason="previous_day_cumulative_non_positive_amount",
    )
    elapsed_count = int(row.get("elapsed_count") or 0)
    full_count = int(row.get("full_count") or 0)
    if elapsed_count <= 0:
        raise VirtualMetricWriterBlocked("previous_day_cumulative_elapsed_count_invalid")
    if full_count != 240:
        raise VirtualMetricWriterBlocked("previous_day_cumulative_full_count_invalid")

    raw_json = _mapping_from_jsonish(row.get("raw_json"))
    trace_json = _mapping_from_jsonish(row.get("trace_json"))
    raw_first_label = row.get("raw_first_label") or trace_json.get("raw_first_label")
    raw_last_label = row.get("raw_last_label") or trace_json.get("raw_last_label")
    raw_source_refs = row.get("raw_source_refs") or trace_json.get("raw_source_refs") or []
    source_bar_ids = row.get("source_bar_ids") or trace_json.get("source_bar_ids") or []

    return {
        "asset_kind": row_asset_kind,
        "identity_key": row.get("identity_key"),
        "code": row.get("code"),
        "exchange": row.get("exchange"),
        "canonical_minute_label": expected_label,
        "canonical_bar_time": row.get("canonical_bar_time") or expected_label,
        "raw_bar_time": row.get("raw_bar_time") or raw_json.get("raw_bar_time"),
        "elapsed_count": elapsed_count,
        "full_count": full_count,
        "previous_day_elapsed_amount": previous_day_elapsed_amount,
        "previous_day_full_amount": previous_day_full_amount,
        "source_previous_day_minute_run_id": source_previous_day_minute_run_id,
        "normalization_policy": row.get("normalization_policy"),
        "raw_first_label": raw_first_label,
        "raw_last_label": raw_last_label,
        "raw_source_refs": list(raw_source_refs or []),
        "source_bar_ids": list(source_bar_ids or []),
        "source_amount_unit": row.get("source_amount_unit"),
        "canonical_amount_unit": row.get("canonical_amount_unit"),
        "unit_conversion_factor": float(row.get("unit_conversion_factor") or 0),
        "raw_json": raw_json,
        "trace_json": trace_json,
        "db_source_fields": {
            "cumulative_amount_yuan": previous_day_elapsed_amount,
            "full_day_amount_yuan": previous_day_full_amount,
        },
    }


def load_previous_day_cumulative_rows_from_db(
    cur: Any,
    *,
    source_previous_day_minute_run_id: str,
    for_trade_date: str,
    source_trade_date: str,
    proof_minute_label: str,
    asset_scope: Mapping[str, Sequence[Any]] | Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Read proof-minute A1 cumulative rows from physical tables for N3P payloads."""

    expected_label = _previous_day_cumulative_canonical_label(
        source_trade_date=source_trade_date,
        proof_minute_label=proof_minute_label,
    )
    expected_scope = _normalize_previous_day_cumulative_asset_scope(asset_scope)
    output: list[dict[str, Any]] = []
    for asset_kind in ASSET_KINDS:
        table_name = A1_CUMULATIVE_TABLES[asset_kind]
        cur.execute(
            f"""
            SELECT
              source_previous_day_minute_run_id,
              for_trade_date,
              source_trade_date,
              asset_kind,
              identity_key,
              code,
              exchange,
              canonical_minute_label,
              canonical_bar_time,
              raw_bar_time,
              elapsed_count,
              full_count,
              cumulative_amount_yuan,
              full_day_amount_yuan,
              source_amount_unit,
              canonical_amount_unit,
              unit_conversion_factor,
              normalization_policy,
              raw_json,
              trace_json,
              count(*) OVER (
                PARTITION BY source_previous_day_minute_run_id, identity_key, canonical_minute_label
              ) AS duplicate_count
            FROM {table_name}
            WHERE source_previous_day_minute_run_id = %s
              AND for_trade_date = %s
              AND source_trade_date = %s
              AND canonical_minute_label = %s
            """,
            (source_previous_day_minute_run_id, for_trade_date, source_trade_date, expected_label),
        )
        rows = [dict(row) for row in cur.fetchall()]
        expected_identities = expected_scope.get(asset_kind) or set()
        if expected_identities:
            rows = [row for row in rows if str(row.get("identity_key") or "") in expected_identities]
            present = {str(row.get("identity_key") or "") for row in rows}
            missing = sorted(expected_identities - present)
            if missing:
                raise VirtualMetricWriterBlocked(
                    "previous_day_cumulative_row_missing:" + ",".join(missing[:5])
                )
        elif not rows:
            continue
        for row in rows:
            output.append(
                alias_previous_day_cumulative_db_row_for_payload(
                    row,
                    expected_asset_kind=asset_kind,
                    source_previous_day_minute_run_id=source_previous_day_minute_run_id,
                    for_trade_date=for_trade_date,
                    source_trade_date=source_trade_date,
                    proof_minute_label=proof_minute_label,
                )
            )
    if not output:
        raise VirtualMetricWriterBlocked("previous_day_cumulative_row_missing")
    return output


def _with_previous_day_cumulative_rows_by_identity_index(source_payload: Mapping[str, Any]) -> dict[str, Any]:
    output = dict(source_payload)
    if isinstance(output.get("previous_day_cumulative_rows_by_identity_minute"), Mapping):
        return output
    rows = _payload_rows(
        output,
        "previous_day_cumulative_rows",
        "a1_previous_day_cumulative_rows",
        "source_previous_day_cumulative_rows",
    )
    if not rows:
        return output
    indexed: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        asset_kind = str(row.get("asset_kind") or "")
        identity_key = str(row.get("identity_key") or row.get(f"{asset_kind}_identity_key") or "")
        code = str(row.get("code") or "")
        label = str(row.get("canonical_minute_label") or row.get("minute_label") or "")
        hhmm = label[-5:] if len(label) >= 16 else ""
        keys = [
            key
            for key in (
                f"{asset_kind}|{identity_key}|{hhmm}",
                f"{asset_kind}|{code}|{hhmm}",
                f"{identity_key}|{hhmm}",
                f"{code}|{hhmm}",
            )
            if key and not key.startswith("||")
        ]
        for key in keys:
            indexed.setdefault(key, []).append(row)
    output["previous_day_cumulative_rows_by_identity_minute"] = indexed
    return output


def _candidate_previous_day_cumulative_row(
    candidate: Mapping[str, Any],
    source_payload: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    candidate_asset_kind = str(candidate.get("asset_kind") or "")
    candidate_identity = str(candidate.get("identity_key") or "")
    candidate_code = str(candidate.get("code") or "")
    minute_label = str(candidate.get("minute_label") or "")
    hhmm = minute_label[-5:] if len(minute_label) >= 16 else ""
    indexed = source_payload.get("previous_day_cumulative_rows_by_identity_minute")
    if isinstance(indexed, Mapping):
        for key in (
            f"{candidate_asset_kind}|{candidate_identity}|{hhmm}",
            f"{candidate_asset_kind}|{candidate_code}|{hhmm}",
            f"{candidate_identity}|{hhmm}",
            f"{candidate_code}|{hhmm}",
        ):
            value = indexed.get(key)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
                rows = [row for row in value if isinstance(row, Mapping)]
                if len(rows) > 1:
                    raise VirtualMetricWriterBlocked(
                        f"BLOCKED_NEED_INPUT_RESOLVER: previous_day_cumulative_duplicate:{candidate_identity}:{hhmm}"
                    )
                return rows[0] if rows else None
    rows = _payload_rows(
        source_payload,
        "previous_day_cumulative_rows",
        "a1_previous_day_cumulative_rows",
        "source_previous_day_cumulative_rows",
    )
    matching = [
        row
        for row in rows
        if _source_row_matches_candidate(row, candidate)
        and str(row.get("canonical_minute_label") or row.get("minute_label") or "").endswith(hhmm)
    ]
    if len(matching) > 1:
        raise VirtualMetricWriterBlocked(
            f"BLOCKED_NEED_INPUT_RESOLVER: previous_day_cumulative_duplicate:{candidate_identity}:{hhmm}"
        )
    return matching[0] if matching else None


def _source_payload_has_previous_day_cumulative_rows(source_payload: Mapping[str, Any]) -> bool:
    if isinstance(source_payload.get("previous_day_cumulative_rows_by_identity_minute"), Mapping):
        return bool(source_payload.get("previous_day_cumulative_rows_by_identity_minute"))
    return bool(
        _payload_rows(
            source_payload,
            "previous_day_cumulative_rows",
            "a1_previous_day_cumulative_rows",
            "source_previous_day_cumulative_rows",
        )
    )


def _with_previous_day_rows_by_identity_index(source_payload: Mapping[str, Any]) -> dict[str, Any]:
    output = dict(source_payload)
    if isinstance(output.get("previous_day_minute_rows_by_identity"), Mapping):
        return output
    rows = _payload_rows(
        output,
        "previous_day_minute_rows",
        "a1_previous_day_minute_rows",
        "source_previous_day_minute_rows",
    )
    if not rows:
        return output
    indexed: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        asset_kind = str(row.get("asset_kind") or "")
        identity_key = str(row.get("identity_key") or row.get(f"{asset_kind}_identity_key") or "")
        code = str(row.get("code") or "")
        keys = [key for key in (f"{asset_kind}|{identity_key}", f"{asset_kind}|{code}", identity_key, code) if key]
        for key in keys:
            indexed.setdefault(key, []).append(row)
    output["previous_day_minute_rows_by_identity"] = indexed
    return output


def _previous_day_row_minute_label(row: Mapping[str, Any]) -> str:
    for key in ("datetime", "bar_time", "minute_label"):
        value = row.get(key)
        if value:
            label = _minute_label_from_proof_time(value)
            if label:
                return label
    return ""


def _normalize_a1_previous_day_rows_for_b1_trigger_proof(
    rows: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    """Align A1 previous-day midday bridge labels for N3P mixed realtime proof only."""
    label_counts: Counter[tuple[str, str, str]] = Counter()
    for row in rows:
        label = _previous_day_row_minute_label(row)
        if len(label) < 16:
            continue
        hhmm = label[-5:]
        if hhmm in {"11:30", "13:00"}:
            label_counts[(str(row.get("code") or ""), label[:10], hhmm)] += 1

    duplicate_keys: set[tuple[str, str]] = set()
    for code, trade_date, hhmm in label_counts:
        count = label_counts[(code, trade_date, hhmm)]
        opposite_hhmm = "13:00" if hhmm == "11:30" else "11:30"
        if count > 1 or label_counts.get((code, trade_date, opposite_hhmm), 0):
            duplicate_keys.add((code, trade_date))
    if duplicate_keys:
        detail = ",".join(f"{code}:{trade_date}" for code, trade_date in sorted(duplicate_keys))
        raise VirtualMetricWriterBlocked(
            f"BLOCKED_NEED_INPUT_RESOLVER: previous_day_midday_bridge_duplicate:{detail}"
        )

    normalized_rows: list[Mapping[str, Any]] = []
    for row in rows:
        label = _previous_day_row_minute_label(row)
        if len(label) >= 16 and label[-5:] == "11:30":
            canonical_label = f"{label[:10]} 13:00"
            normalized = dict(row)
            normalized["datetime"] = canonical_label
            normalized["raw_bar_time"] = label
            normalized["canonical_bar_time"] = canonical_label
            normalized["normalization_policy"] = PREVIOUS_DAY_MIDDAY_BRIDGE_NORMALIZATION_POLICY
            normalized_rows.append(normalized)
        else:
            normalized_rows.append(row)
    return normalized_rows


def _stock_quote_source_for_candidate(
    *,
    contract: Mapping[str, Any],
    candidate: Mapping[str, Any],
    source_payload: Mapping[str, Any],
) -> dict[str, Any] | None:
    rows = _payload_rows(source_payload, "stock_quote_rows", "stock_quotes_rows")
    matching = [row for row in rows if _source_row_matches_candidate(row, candidate)]
    if not matching:
        return None
    row = dict(matching[-1])
    if _source_row_is_fake(row):
        raise VirtualMetricWriterBlocked("BLOCKED_NEED_INPUT_RESOLVER: fake_source_row_forbidden")
    minute_label = _source_minute_label_from_row(row, contract=contract)
    if minute_label != str(candidate.get("minute_label") or ""):
        raise VirtualMetricWriterBlocked("BLOCKED_NEED_INPUT_RESOLVER: n3p_realtime_source_time_mismatch")
    zero_quote = _stock_quote_zero_price_ohlc_volume(row)
    source_blocked_reasons = [N3P_STOCK_QUOTE_ZERO_PRICE_OHLC_VOLUME_REASON] if zero_quote else []
    return {
        "current_price": row.get("price") if row.get("price") is not None else row.get("close"),
        "current_open": row.get("open"),
        "current_high": row.get("high"),
        "current_low": row.get("low"),
        "current_elapsed_amount": row.get("amount"),
        "current_amount_source_kind": "stock_quotes_cumulative_amount",
        "source_minute_refs": [f"stock_quote:{candidate.get('code')}@{minute_label}"],
        "source_trace": {
            "n3p_realtime_source_model": N3P_TRIGGER_PROOF_REALTIME_SOURCE_MODEL,
            "amount_source_kind": "stock_quotes_cumulative_amount",
            "stock_quote_batch_size": N3P_STOCK_QUOTE_BATCH_SIZE,
            "stock_quote_servertime": row.get("servertime"),
            "source_quote_servertime": row.get("servertime"),
            "canonical_proof_minute": row.get("canonical_stock_quote_proof_minute") or minute_label[-5:],
            "canonical_stock_quote_proof_minute": row.get("canonical_stock_quote_proof_minute"),
            "source_quote_zero_price_ohlc_volume": zero_quote,
            "source_blocked_reasons": source_blocked_reasons,
            "stock_quote_source_values": {
                "price": row.get("price") if row.get("price") is not None else row.get("close"),
                "open": row.get("open"),
                "high": row.get("high"),
                "low": row.get("low"),
                "volume": row.get("volume"),
                "amount": row.get("amount"),
            },
            "raw_source_time": minute_label,
        },
    }


def _index_board_1m_source_for_candidate(
    *,
    contract: Mapping[str, Any],
    candidate: Mapping[str, Any],
    source_payload: Mapping[str, Any],
) -> dict[str, Any] | None:
    rows = _payload_rows(source_payload, "index_board_1m_rows", "index_1m_rows", "board_1m_rows")
    matching = [dict(row) for row in rows if _source_row_matches_candidate(row, candidate)]
    if not matching:
        return None
    if any(_source_row_is_fake(row) for row in matching):
        raise VirtualMetricWriterBlocked("BLOCKED_NEED_INPUT_RESOLVER: fake_source_row_forbidden")
    proof_minute = str(candidate.get("minute_label") or "")
    usable = [
        row
        for row in matching
        if _source_minute_label_from_row(row, contract=contract) <= proof_minute
        and _source_minute_label_from_row(row, contract=contract)[:10] == proof_minute[:10]
    ]
    if not usable:
        return {
            "current_price": None,
            "current_open": None,
            "current_high": None,
            "current_low": None,
            "current_elapsed_amount": None,
            "current_amount_source_kind": "index_board_1m_cumulative_amount",
            "source_minute_refs": [],
            "source_trace": {
                "n3p_realtime_source_model": N3P_TRIGGER_PROOF_REALTIME_SOURCE_MODEL,
                "amount_source_kind": "index_board_1m_cumulative_amount",
                "source_1m_adapter_method": "index",
                "source_1m_frequency": 8,
            },
        }
    usable.sort(key=lambda row: _source_minute_label_from_row(row, contract=contract))
    latest = usable[-1]
    source_minute_refs = [_source_minute_label_from_row(row, contract=contract) for row in usable]
    return {
        "current_price": latest.get("close"),
        "current_open": usable[0].get("open"),
        "current_high": max(
            _n3p_float_or_none(row.get("high")) or _n3p_float_or_none(row.get("close")) or 0.0 for row in usable
        ),
        "current_low": min(
            _n3p_float_or_none(row.get("low")) or _n3p_float_or_none(row.get("close")) or 0.0 for row in usable
        ),
        "current_elapsed_amount": sum(_n3p_float_or_none(row.get("amount")) or 0.0 for row in usable),
        "current_amount_source_kind": "index_board_1m_cumulative_amount",
        "source_minute_refs": source_minute_refs,
        "source_trace": {
            "n3p_realtime_source_model": N3P_TRIGGER_PROOF_REALTIME_SOURCE_MODEL,
            "amount_source_kind": "index_board_1m_cumulative_amount",
            "source_1m_adapter_method": str(latest.get("source_adapter_method") or "index"),
            "source_1m_frequency": int(latest.get("source_frequency") or 8),
            "raw_source_time": source_minute_refs[-1],
        },
    }


def _b1_realtime_trigger_proof_source_for_candidate(
    *,
    contract: Mapping[str, Any],
    candidate: Mapping[str, Any],
    source_payload: Mapping[str, Any],
) -> dict[str, Any] | None:
    if not (_is_b1_source_returned_snapshot_source(contract) and _has_b1_realtime_trigger_proof_source_payload(source_payload)):
        return None
    if str(candidate.get("asset_kind") or "") == "stock":
        source = _stock_quote_source_for_candidate(contract=contract, candidate=candidate, source_payload=source_payload)
    else:
        source = _index_board_1m_source_for_candidate(contract=contract, candidate=candidate, source_payload=source_payload)
    if source is None:
        raise VirtualMetricWriterBlocked("BLOCKED_NEED_INPUT_RESOLVER: n3p_realtime_source_missing")
    cumulative_row = _candidate_previous_day_cumulative_row(candidate, source_payload)
    if cumulative_row is not None:
        source["previous_day_cumulative_row"] = cumulative_row
        source["previous_day_rows"] = []
        source_trace = dict(source.get("source_trace") or {})
        source_trace.update(
            {
                "previous_day_cumulative_source": True,
                "previous_day_elapsed_amount": cumulative_row.get("previous_day_elapsed_amount"),
                "previous_day_full_amount": cumulative_row.get("previous_day_full_amount"),
                "previous_day_cumulative_elapsed_count": cumulative_row.get("elapsed_count"),
                "previous_day_cumulative_full_count": cumulative_row.get("full_count"),
                "previous_day_cumulative_canonical_minute_label": cumulative_row.get("canonical_minute_label"),
                "previous_day_cumulative_normalization_policy": cumulative_row.get("normalization_policy"),
                "source_previous_day_minute_run_id": cumulative_row.get("source_previous_day_minute_run_id"),
            }
        )
        source["source_trace"] = source_trace
        return source
    if _contract_requires_previous_day_cumulative_rows(contract) or _source_payload_has_previous_day_cumulative_rows(source_payload):
        raise VirtualMetricWriterBlocked("BLOCKED_NEED_INPUT_RESOLVER: previous_day_cumulative_rows_missing")
    source["previous_day_rows"] = _normalize_a1_previous_day_rows_for_b1_trigger_proof(
        _candidate_previous_day_rows(candidate, source_payload)
    )
    return source


def build_rows_by_asset_from_source_payload(
    contract: Mapping[str, Any],
    source_payload: Mapping[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    source_payload = materialize_source_payload_from_contract(contract, source_payload)
    source_payload = normalize_live_current_1m_source_payload(contract, source_payload)
    source_payload = build_b1_source_returned_payload_selection(contract, source_payload)
    source_payload = _with_previous_day_cumulative_rows_by_identity_index(source_payload)
    source_payload = _with_previous_day_rows_by_identity_index(source_payload)
    records_by_code = source_payload.get("source_records") or {}
    candidates = source_payload.get("candidates") or []
    sparse_exception_report = build_live_current_sparse_no_trade_exception_report(contract, source_payload=source_payload)
    if sparse_exception_report.get("status") == "blocked":
        raise VirtualMetricWriterBlocked(
            "BLOCKED_NEED_INPUT_RESOLVER: " + ",".join(sparse_exception_report.get("blocked_reasons") or [])
        )
    if _is_live_current_1m_source(contract) and not candidates and not sparse_exception_report.get("exception_count"):
        raise VirtualMetricWriterBlocked("BLOCKED_NEED_INPUT_RESOLVER: missing live_current_minute_rows")
    higher_period_context_index = build_higher_period_context_index(contract, source_payload)
    rows_by_asset: dict[str, list[dict[str, Any]]] = {asset: [] for asset in ASSET_KINDS}
    for candidate in candidates:
        _assert_b1_source_returned_candidate_time(contract=contract, candidate=candidate)
        code = str(candidate["code"])
        source_record_key = str(candidate.get("source_record_key") or code)
        resolved_context_entry = _higher_period_context_entry(higher_period_context_index, candidate)
        higher_period_context, higher_period_context_source = merge_higher_period_context(
            candidate=candidate,
            resolved_entry=resolved_context_entry,
        )
        realtime_trigger_source = _b1_realtime_trigger_proof_source_for_candidate(
            contract=contract,
            candidate=candidate,
            source_payload=source_payload,
        )
        if realtime_trigger_source is not None:
            metric = build_realtime_trigger_proof_metric_from_elapsed_amount(
                code=code,
                minute_label=str(candidate["minute_label"]),
                observed_at=candidate.get("observed_at"),
                current_price=realtime_trigger_source.get("current_price"),
                current_open=realtime_trigger_source.get("current_open"),
                current_high=realtime_trigger_source.get("current_high"),
                current_low=realtime_trigger_source.get("current_low"),
                current_elapsed_amount=realtime_trigger_source.get("current_elapsed_amount"),
                current_amount_source_kind=str(realtime_trigger_source.get("current_amount_source_kind")),
                previous_day_rows=list(realtime_trigger_source.get("previous_day_rows") or []),
                previous_day_cumulative_row=realtime_trigger_source.get("previous_day_cumulative_row"),
                source_minute_refs=list(realtime_trigger_source.get("source_minute_refs") or []),
                higher_period_context=higher_period_context,
                asset_kind=str(candidate.get("asset_kind") or "stock"),
                source_trace=dict(realtime_trigger_source.get("source_trace") or {}),
            )
        else:
            metric = build_realtime_virtual_metric(
                list(records_by_code.get(source_record_key) or []),
                code=code,
                minute_label=str(candidate["minute_label"]),
                observed_at=candidate.get("observed_at"),
                higher_period_context=higher_period_context,
                asset_kind=str(candidate.get("asset_kind") or "stock"),
            )
        metric = apply_formal_amount_chain_contract(
            metric=metric,
            candidate=candidate,
            higher_period_context_source=higher_period_context_source,
        )
        metric = apply_b1_source_returned_trigger_proof_readiness(
            contract=contract,
            candidate=candidate,
            metric=metric,
        )
        row = build_action_confirmation_metric_row(contract=contract, candidate=candidate, metric=metric)
        rows_by_asset.setdefault(str(candidate["asset_kind"]), []).append(canonicalize_realtime_virtual_metric_fields(row))
    return rows_by_asset


def materialize_source_payload_from_contract(
    contract: Mapping[str, Any],
    source_payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Apply preflight-materialized source inputs from the writer contract."""

    output = dict(source_payload)
    overlay = contract.get("materialized_source_payload_overlay")
    if not isinstance(overlay, Mapping):
        return output
    for key, value in overlay.items():
        existing = output.get(key)
        if _materialized_overlay_conflicts(existing, value):
            raise VirtualMetricWriterBlocked(
                f"BLOCKED_N3P_PREFLIGHT_ARTIFACT_CONTRACT:materialized_source_payload_overlay_conflict:{key}"
            )
        output[key] = value
    return output


def _materialized_overlay_conflicts(existing: Any, value: Any) -> bool:
    if existing in (None, "", [], {}, ()):
        return False
    return existing != value


def build_n3p_plan_only_proof_summary_rows(
    rows_by_asset: Mapping[str, Sequence[Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    """Expose N3P-owned proof metadata for local plan-only replay caching.

    The summary is derived from canonical N3P row trace/raw fields. It does not
    re-evaluate amount-chain logic or change row readiness semantics.
    """

    proof_rows: list[dict[str, Any]] = []
    for asset_kind in sorted(rows_by_asset):
        for row in rows_by_asset.get(asset_kind) or []:
            raw_json = row.get("raw_json") if isinstance(row.get("raw_json"), Mapping) else {}
            trace_json = row.get("trace_json") if isinstance(row.get("trace_json"), Mapping) else {}
            condition_key = str(row.get("condition_key") or raw_json.get("condition_key") or "")
            signal_type = str(row.get("signal_type") or raw_json.get("signal_type") or "")
            trigger_amount_chain_pass = _proof_value(row, raw_json, trace_json, "trigger_amount_chain_pass", {})
            required_periods = list(_proof_value(row, raw_json, trace_json, "formal_amount_chain_required_periods", []) or [])
            requested_periods = _proof_requested_periods(required_periods, row=row, raw_json=raw_json, trace_json=trace_json)
            missing_inputs = dict(_proof_value(row, raw_json, trace_json, "formal_amount_chain_missing_inputs", {}) or {})
            input_ready = dict(_proof_value(row, raw_json, trace_json, "formal_amount_chain_input_ready", {}) or {})
            block_reason = list(_proof_value(row, raw_json, trace_json, "blocked_reasons", []) or [])
            metric_ready = bool(row.get("metric_ready"))
            minute_label = str(row.get("metric_minute_label") or row.get("metric_time_label") or "")[-5:]
            for_trade_date = str(row.get("for_trade_date") or raw_json.get("for_trade_date") or "")
            original_condition_key = _proof_original_condition_key(
                condition_key=condition_key,
                row=row,
                raw_json=raw_json,
                trace_json=trace_json,
            )
            proof_condition_key = original_condition_key or condition_key
            trigger_period = _proof_trigger_period(requested_periods)
            trigger_mark_candidate = str(row.get("trigger_mark_candidate") or raw_json.get("trigger_mark_candidate") or "normal")
            source_time_policy = str(
                row.get("source_time_policy")
                or raw_json.get("source_time_policy")
                or trace_json.get("source_time_policy")
                or ""
            )
            proof_input_time = str(
                row.get("proof_input_time")
                or raw_json.get("proof_input_time")
                or trace_json.get("proof_input_time")
                or raw_json.get("source_snapshot_time")
                or trace_json.get("source_snapshot_time")
                or ""
            )
            proof_input_time_source = str(
                row.get("proof_input_time_source")
                or raw_json.get("proof_input_time_source")
                or trace_json.get("proof_input_time_source")
                or ("B1_source_snapshot_time" if proof_input_time else "")
            )
            higher_period_context_source = _proof_higher_period_context_source(raw_json=raw_json, trace_json=trace_json)
            amount_chain_boundary = {
                "required_periods": requested_periods,
                "input_ready": input_ready,
                "missing_inputs": missing_inputs,
                "formal_amount_chain_metrics": _proof_value(row, raw_json, trace_json, "formal_amount_chain_metrics", {}),
                "formal_period_amount_proof": _proof_value(row, raw_json, trace_json, "formal_period_amount_proof", {}),
            }
            safe_reason, unsafe_reason = _proof_negative_cacheability_reasons(
                condition_key=proof_condition_key,
                signal_type=signal_type,
                required_periods=requested_periods,
                trigger_amount_chain_pass=trigger_amount_chain_pass,
                missing_inputs=missing_inputs,
            )
            source_input_fingerprint = stable_payload_hash(
                {
                    "asset_kind": str(row.get("asset_kind") or asset_kind),
                    "identity_key": row.get("identity_key"),
                    "signal_type": signal_type,
                    "condition_key": proof_condition_key,
                    "requested_periods": requested_periods,
                    "trigger_period": trigger_period,
                    "trigger_mark_candidate": trigger_mark_candidate,
                    "safe_negative_cacheable_reason": safe_reason,
                }
            )
            context_fingerprint = stable_payload_hash(
                {
                    "asset_kind": str(row.get("asset_kind") or asset_kind),
                    "identity_key": row.get("identity_key"),
                    "source_condition_run_id": row.get("source_condition_run_id"),
                    "source_condition_pool_id": higher_period_context_source.get("source_condition_pool_id"),
                    "source_minute_target_scope_id": higher_period_context_source.get("source_minute_target_scope_id"),
                    "original_condition_key": original_condition_key,
                    "requested_periods": requested_periods,
                }
            )
            proof_rows.append(
                {
                    "proof_version": N3P_PLAN_ONLY_PROOF_SUMMARY_VERSION,
                    "metric_role": "trigger_proof",
                    "proof_owner": "N3",
                    "proof_consumer": "N4",
                    "not_n5_final_proof": True,
                    "for_trade_date": for_trade_date,
                    "asset_kind": str(row.get("asset_kind") or asset_kind),
                    "identity_key": str(row.get("identity_key") or ""),
                    "signal_type": signal_type,
                    "condition_key": condition_key,
                    "original_condition_key": original_condition_key,
                    "requested_periods": requested_periods,
                    "source_time_policy": source_time_policy,
                    "proof_input_time": proof_input_time,
                    "proof_input_time_source": proof_input_time_source,
                    "proof_input_minute": minute_label,
                    "trigger_period": trigger_period,
                    "trigger_mark_candidate": trigger_mark_candidate,
                    "trigger_minute": minute_label,
                    "stable_trigger_key": "|".join(
                        [
                            for_trade_date,
                            str(row.get("asset_kind") or asset_kind),
                            str(row.get("identity_key") or ""),
                            signal_type,
                            proof_condition_key,
                            trigger_period,
                            trigger_mark_candidate,
                            minute_label,
                        ]
                    ),
                    "stable_trigger_family_key": "|".join(
                        [
                            for_trade_date,
                            str(row.get("asset_kind") or asset_kind),
                            str(row.get("identity_key") or ""),
                            signal_type,
                            proof_condition_key,
                            trigger_period,
                            trigger_mark_candidate,
                        ]
                    ),
                    "source_input_fingerprint": source_input_fingerprint,
                    "context_fingerprint": context_fingerprint,
                    "metric_ready": metric_ready,
                    "trigger_amount_chain_pass": trigger_amount_chain_pass,
                    "block_reason": block_reason,
                    "amount_chain_boundary": amount_chain_boundary,
                    "next_price_boundary": None,
                    "next_amount_boundary": None,
                    "required_period_boundaries": _proof_required_period_boundaries(
                        requested_periods=requested_periods,
                        trigger_amount_chain_pass=trigger_amount_chain_pass,
                        input_ready=input_ready,
                        missing_inputs=missing_inputs,
                    ),
                    "next_recompute_condition": _proof_next_recompute_condition(
                        safe_negative_cacheable_reason=safe_reason,
                    ),
                    "safe_negative_cacheable": bool(safe_reason),
                    "safe_negative_cacheable_reason": safe_reason,
                    "unsafe_negative_cacheable_reason": unsafe_reason,
                }
            )
    return proof_rows


def _proof_value(
    row: Mapping[str, Any],
    raw_json: Mapping[str, Any],
    trace_json: Mapping[str, Any],
    key: str,
    default: Any,
) -> Any:
    if key in row:
        return row.get(key)
    if key in raw_json:
        return raw_json.get(key)
    if key in trace_json:
        return trace_json.get(key)
    return default


def _proof_trigger_period(required_periods: Sequence[Any]) -> str:
    for period in ("Y", "Q", "M", "W", "D"):
        if period in required_periods:
            return period
    return "D"


def _proof_requested_periods(
    required_periods: Sequence[Any],
    *,
    row: Mapping[str, Any],
    raw_json: Mapping[str, Any],
    trace_json: Mapping[str, Any],
) -> list[str]:
    periods = _normalize_proof_periods(required_periods)
    if periods:
        return periods
    for key in ("requested_periods", "formal_amount_chain_required_periods"):
        periods = _normalize_proof_periods(_proof_value(row, raw_json, trace_json, key, []))
        if periods:
            return periods
    condition_key = _proof_original_condition_key(
        condition_key=str(row.get("condition_key") or raw_json.get("condition_key") or ""),
        row=row,
        raw_json=raw_json,
        trace_json=trace_json,
    )
    return _normalize_proof_periods(_proof_periods_from_condition_key(condition_key))


def _normalize_proof_periods(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        values: Sequence[Any] = [value]
    elif isinstance(value, Sequence):
        values = value
    else:
        return []
    output: list[str] = []
    seen: set[str] = set()
    for item in values:
        period = str(item or "").upper()
        if period not in {"Y", "Q", "M", "W", "D"} or period in seen:
            continue
        seen.add(period)
        output.append(period)
    return output


def _proof_periods_from_condition_key(condition_key: str) -> list[str]:
    if condition_key in {"BUY:FULL", "SELL:FULL"}:
        return ["D"]
    if ":" not in condition_key:
        return ["D"] if condition_key in {"BUY", "SELL", "B_BUY", "S_SELL"} else []
    return _normalize_proof_periods(condition_key.split(":", 1)[1].split(","))


def _proof_higher_period_context_source(
    *,
    raw_json: Mapping[str, Any],
    trace_json: Mapping[str, Any],
) -> Mapping[str, Any]:
    for container in (trace_json, raw_json):
        value = container.get("higher_period_context_source")
        if isinstance(value, Mapping):
            return value
    return {}


def _proof_original_condition_key(
    *,
    condition_key: str,
    row: Mapping[str, Any],
    raw_json: Mapping[str, Any],
    trace_json: Mapping[str, Any],
) -> str:
    higher_period_context_source = _proof_higher_period_context_source(raw_json=raw_json, trace_json=trace_json)
    for container in (row, raw_json, trace_json, higher_period_context_source):
        value = container.get("original_condition_key") if isinstance(container, Mapping) else None
        if value:
            return str(value)
    for container in (raw_json, trace_json, higher_period_context_source):
        values = container.get("condition_keys") or container.get("candidate_condition_keys") if isinstance(container, Mapping) else None
        if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
            for value in values:
                if value:
                    return str(value)
    if condition_key.startswith("LIVE_CURRENT_1M:"):
        context_condition_key = higher_period_context_source.get("context_condition_key")
        if context_condition_key:
            return str(context_condition_key)
    return condition_key


def _proof_period_missing_inputs(missing_inputs: Mapping[str, Any], period: str) -> list[Any]:
    value = missing_inputs.get(period)
    if value in (None, "", []):
        return []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return list(value)
    return [value]


def _proof_negative_cacheability_reasons(
    *,
    condition_key: str,
    signal_type: str,
    required_periods: Sequence[Any],
    trigger_amount_chain_pass: Any,
    missing_inputs: Mapping[str, Any],
) -> tuple[str, str]:
    if signal_type not in {"B_BUY", "S_SELL"} or "HINT" in condition_key.upper():
        return "", "unsupported_signal_or_hint_scope"
    periods = _normalize_proof_periods(required_periods)
    if not periods:
        return "", "requested_periods_missing"
    if not isinstance(trigger_amount_chain_pass, Mapping):
        return "", "trigger_amount_chain_pass_missing"
    has_false_required_period = False
    for period in periods:
        if _proof_period_missing_inputs(missing_inputs, period):
            return "", "missing_inputs_present"
        if period not in trigger_amount_chain_pass or trigger_amount_chain_pass.get(period) is None:
            return "", "trigger_amount_chain_pass_missing"
        if trigger_amount_chain_pass.get(period) is False:
            has_false_required_period = True
    if has_false_required_period:
        return "amount_chain_failed_for_required_period", ""
    return "", "amount_chain_all_required_periods_true_without_boundary_proof"


def _proof_required_period_boundaries(
    *,
    requested_periods: Sequence[Any],
    trigger_amount_chain_pass: Any,
    input_ready: Mapping[str, Any],
    missing_inputs: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    pass_map = trigger_amount_chain_pass if isinstance(trigger_amount_chain_pass, Mapping) else {}
    for period in _normalize_proof_periods(requested_periods):
        missing = _proof_period_missing_inputs(missing_inputs, period)
        safe_reason = (
            "amount_chain_failed_for_required_period"
            if not missing and pass_map.get(period) is False
            else ""
        )
        output[period] = {
            "trigger_amount_chain_pass": pass_map.get(period),
            "formal_amount_chain_input_ready": bool(input_ready.get(period)),
            "formal_amount_chain_missing_inputs": missing,
            "safe_negative_cacheable_reason": safe_reason,
            "next_price_boundary": None,
            "next_amount_boundary": None,
        }
    return output


def _proof_next_recompute_condition(*, safe_negative_cacheable_reason: str) -> str:
    if safe_negative_cacheable_reason == "amount_chain_failed_for_required_period":
        return "source_or_context_or_amount_chain_boundary_changed"
    return "full_n3p_required"


def normalize_live_current_1m_source_payload(
    contract: Mapping[str, Any],
    source_payload: Mapping[str, Any],
) -> dict[str, Any]:
    if not _is_live_current_1m_source(contract):
        return dict(source_payload)
    output = dict(source_payload)
    records_by_code = dict(output.get("source_records") or {})
    candidates = [dict(candidate) for candidate in output.get("candidates") or []]
    scope = _source_scope(contract)
    trade_date = str(scope.get("for_trade_date") or contract.get("for_trade_date") or "")
    intraday_trade_date = str(contract.get("intraday_trade_date") or source_payload.get("intraday_trade_date") or trade_date)
    default_source_adapter = str(scope.get("source_adapter") or contract.get("source_adapter") or source_payload.get("source_adapter") or "")

    normalized_records: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        code = str(candidate.get("code") or "")
        source_record_key = str(candidate.get("source_record_key") or code)
        rows = list(normalized_records.get(source_record_key) or records_by_code.get(source_record_key) or [])
        source_adapter = str(candidate.get("source_adapter") or default_source_adapter)
        try:
            rows = normalize_mootdx_intraday_1m_labels(
                rows,
                trade_date=trade_date,
                intraday_trade_date=intraday_trade_date,
                source_adapter=source_adapter,
                identity_key=str(candidate.get("identity_key") or code),
            )
        except MinuteLabelNormalizationError as exc:
            raise VirtualMetricWriterBlocked(f"BLOCKED_NEED_INPUT_RESOLVER: {exc}") from exc
        assert_no_live_current_raw_1300_label(rows, source_record_key=source_record_key)
        normalized_records[source_record_key] = rows
        trace = _trace_for_candidate_minute(rows, str(candidate.get("minute_label") or ""))
        if trace:
            candidate["minute_label"] = _minute_label_from_iso(str(trace["canonical_bar_time"]))
            candidate["minute_label_normalization"] = trace
            raw_json = dict(candidate.get("raw_json") or {})
            raw_json["minute_label_normalization"] = trace
            candidate["raw_json"] = raw_json

    for key, rows in records_by_code.items():
        normalized_records.setdefault(str(key), list(rows))
    output["source_records"] = normalized_records
    output["candidates"] = candidates
    return output


def assert_no_live_current_raw_1300_label(rows: Sequence[Mapping[str, Any]], *, source_record_key: str) -> None:
    for row in rows:
        value = row.get("bar_time") or row.get("datetime") or row.get("minute_label")
        if value is None:
            continue
        text = str(value).replace("T", " ")
        if len(text) >= 16 and text[11:16] == "13:00":
            trace = minute_label_normalization_trace(row)
            if not trace:
                raise VirtualMetricWriterBlocked(
                    f"BLOCKED_NEED_INPUT_RESOLVER: live_current_1m source {source_record_key} contains raw 13:00 without minute label normalization"
                )


def _trace_for_candidate_minute(rows: Sequence[Mapping[str, Any]], minute_label: str) -> dict[str, Any] | None:
    raw_label = minute_label.replace("T", " ")
    if len(raw_label) >= 16:
        raw_label = raw_label[:16]
    for row in rows:
        trace = minute_label_normalization_trace(row)
        if not trace:
            continue
        raw_bar_time = str(trace.get("raw_bar_time") or "").replace("T", " ")
        if len(raw_bar_time) >= 16 and raw_bar_time[:16] == raw_label:
            return trace
    return None


def _minute_label_from_iso(value: str) -> str:
    text = value.replace("T", " ")
    return text[:16]


def build_action_confirmation_metric_row(
    *,
    contract: Mapping[str, Any],
    candidate: Mapping[str, Any],
    metric: Mapping[str, Any],
) -> dict[str, Any]:
    scope = _source_scope(contract)
    target_run_id = _target_run_id(contract)
    source_condition_run_id = str(scope.get("source_condition_run_id") or contract.get("source_condition_run_id") or "")
    source_subscription_run_id = str(scope.get("source_subscription_run_id") or contract.get("source_subscription_run_id") or "")
    for_trade_date = str(scope.get("for_trade_date") or contract.get("for_trade_date") or "")
    signal_type = str(candidate.get("signal_type") or "")
    condition_key = str(candidate.get("condition_key") or signal_type)
    source_mode = _source_mode(contract, candidate)
    c1_dependency = _c1_dependency(contract, candidate)
    no_c1_table_rows_read = _is_no_c1_source_mode(contract, candidate)
    no_c1_table_rows_written = _is_no_c1_source_mode(contract, candidate)
    metric_ready = bool(metric.get("metric_ready"))
    metric_time_label = str(metric.get("metric_time_label") or candidate.get("minute_label") or "")
    metric_minute_label = _minute_hhmm(metric_time_label)
    required_lineage = _required_source_lineage(candidate=candidate, contract=contract)
    source_live_minute_run_id = required_lineage.get("source_live_minute_run_id") or ""
    source_time_policy = _source_time_policy_mode(contract, candidate)
    proof_input_time = str(
        candidate.get("proof_input_time")
        or candidate.get("source_snapshot_time")
        or candidate.get("source_time")
        or _b1_source_returned_proof_input_time(contract, candidate)
        or ""
    )
    proof_input_time_source = str(
        candidate.get("proof_input_time_source")
        or _first_lineage_value(_db_input_contract(contract), scope, contract, keys=("proof_input_time_source",))
        or ("B1_source_snapshot_time" if proof_input_time else "")
    )
    source_snapshot_time = str(candidate.get("source_snapshot_time") or proof_input_time or "")
    raw_target_minute_label = _raw_target_minute_label(contract, candidate)
    source_today_minute_run_id_compat_policy = _source_today_minute_run_id_compat_policy(contract, candidate)
    source_returned_time_lineage: dict[str, Any] = {}
    if _is_b1_source_returned_snapshot_source(contract, candidate):
        source_returned_time_lineage = {
            "source_mode": source_mode,
            "source_time_policy": source_time_policy,
            "proof_input_time": proof_input_time,
            "proof_input_time_source": proof_input_time_source,
            "source_snapshot_run_id": required_lineage["source_snapshot_run_id"],
            "source_snapshot_time": source_snapshot_time,
            "observed_at": candidate.get("observed_at") or _db_input_contract(contract).get("observed_at"),
            "fetched_at": candidate.get("fetched_at") or _db_input_contract(contract).get("fetched_at"),
            "raw_target_minute_label": raw_target_minute_label,
            "target_until_hhmm_source": _first_lineage_value(
                _db_input_contract(contract),
                scope,
                contract,
                keys=("target_until_hhmm_source",),
            ) or "B1_source_snapshot_time",
            "source_today_minute_run_id_compat": required_lineage["source_today_minute_run_id"],
            "source_today_minute_run_id_compat_policy": source_today_minute_run_id_compat_policy,
            "forbid_source_time_relabel": True,
        }
    closed_minute_proof = {
        "metric_time_label": metric_time_label,
        "metric_minute_label": metric_minute_label,
        "selected_metric_time": _metric_time_iso(metric_time_label),
        "observed_at": metric.get("observed_at") or candidate.get("observed_at"),
        "is_closed_1m": bool(metric.get("is_closed_1m")),
        "source_mode": source_mode,
        "source_live_minute_kind": LIVE_CURRENT_1M_SOURCE_MODE if source_mode == LIVE_CURRENT_1M_SOURCE_MODE else None,
        "source_live_minute_run_id": source_live_minute_run_id,
        "c1_dependency": c1_dependency,
        "no_c1_table_rows_read": no_c1_table_rows_read,
        "no_c1_table_rows_written": no_c1_table_rows_written,
        "source_time_policy": source_time_policy,
        "proof_input_time": proof_input_time,
        "proof_input_time_source": proof_input_time_source,
        "raw_target_minute_label": raw_target_minute_label,
        "source_today_minute_run_id_compat_policy": source_today_minute_run_id_compat_policy,
        "source_today_minute_run_id": _lineage_value(
            candidate=candidate,
            contract=contract,
            key="source_today_minute_run_id",
            fallback="",
        ),
    }
    normalization_trace = candidate.get("minute_label_normalization")
    if normalization_trace:
        closed_minute_proof["minute_label_normalization"] = normalization_trace
    closed_minute_proof["source_today_minute_run_id"] = required_lineage["source_today_minute_run_id"]
    lineage_policy = _lineage_policy(required_lineage)
    source_snapshot_id = candidate.get("source_snapshot_id")
    source_snapshot_id_policy = (
        "candidate_snapshot_fk" if source_snapshot_id is not None else "nullable_for_minute_source_realtime_virtual_metric"
    )
    raw_current_price_source = metric.get("current_price_source")
    current_price_source, current_price_source_canonicalization = canonicalize_current_price_source(raw_current_price_source)
    pass_flags = metric.get("deterministic_pass_flags") or {}
    buy_flags = pass_flags.get("B_BUY") or {}
    sell_flags = pass_flags.get("S_SELL") or {}
    metric_raw_json = metric.get("raw_json") if isinstance(metric.get("raw_json"), Mapping) else {}
    candidate_raw_json = candidate.get("raw_json") if isinstance(candidate.get("raw_json"), Mapping) else {}
    raw_json = {
        **dict(metric_raw_json),
        **dict(candidate_raw_json),
        "signal_type": signal_type,
        "condition_key": condition_key,
        "source_time_policy": source_time_policy,
        "proof_input_time": proof_input_time,
        "proof_input_time_source": proof_input_time_source,
        "source_snapshot_time": source_snapshot_time,
        "raw_target_minute_label": raw_target_minute_label,
        "source_mode": source_mode,
        "source_live_minute_kind": LIVE_CURRENT_1M_SOURCE_MODE if source_mode == LIVE_CURRENT_1M_SOURCE_MODE else None,
        "source_live_minute_run_id": source_live_minute_run_id,
        "c1_dependency": c1_dependency,
        "no_c1_table_rows_read": no_c1_table_rows_read,
        "no_c1_table_rows_written": no_c1_table_rows_written,
        "source_returned_time_lineage": source_returned_time_lineage or None,
        "source": "v3_realtime_virtual_metric_writer",
        "closed_minute_proof": closed_minute_proof,
        "minute_label_normalization": normalization_trace,
        "n4_trigger_matched_events": [
            {
                "signal_type": signal_type,
                "condition_key": condition_key,
                "output_event_id": candidate.get("source_event_id"),
            }
        ],
    }
    if source_mode == LIVE_CURRENT_1M_SOURCE_MODE:
        assert_no_legacy_midday_bridge_semantic(raw_json, trace_json=None)
    row = {
        "projection_run_id": target_run_id,
        "projection_schema_version": contract.get("projection_schema_version") or "v3.realtime_virtual_metric.writer.v1",
        "source_condition_run_id": source_condition_run_id,
        "source_subscription_run_id": source_subscription_run_id,
        "source_snapshot_run_id": required_lineage["source_snapshot_run_id"],
        "source_snapshot_id": source_snapshot_id,
        "source_snapshot_event_id": candidate.get("source_snapshot_event_id"),
        "source_today_minute_run_id": required_lineage["source_today_minute_run_id"],
        "source_previous_day_minute_run_id": required_lineage["source_previous_day_minute_run_id"],
        "for_trade_date": for_trade_date,
        "trade_date": for_trade_date,
        "asset_kind": candidate.get("asset_kind"),
        "identity_key": candidate.get("identity_key"),
        "exchange": candidate.get("exchange"),
        "code": candidate.get("code"),
        "display_code": candidate.get("display_code") or candidate.get("code"),
        "name": candidate.get("name") or candidate.get("identity_key"),
        "metric_time": _metric_time_iso(metric_time_label),
        "metric_minute_label": metric_minute_label,
        "current_price": metric.get("current_price"),
        "current_price_source": current_price_source,
        "current_price_time": metric.get("current_price_time"),
        "previous_120m_body_high": metric.get("previous_120m_body_high"),
        "previous_120m_body_low": metric.get("previous_120m_body_low"),
        "previous_30m_body_high": metric.get("previous_30m_body_high"),
        "previous_30m_body_low": metric.get("previous_30m_body_low"),
        "previous_5m_body_high": metric.get("previous_5m_body_high"),
        "previous_5m_body_low": metric.get("previous_5m_body_low"),
        "previous_1m_body_high": metric.get("previous_1m_body_high"),
        "previous_1m_body_low": metric.get("previous_1m_body_low"),
        "current_1m_amount": metric.get("current_1m_amount"),
        "previous_1m_amount": metric.get("previous_1m_amount"),
        "current_5m_virtual_amount": metric.get("current_5m_virtual_amount"),
        "previous_5m_full_amount": metric.get("previous_5m_full_amount"),
        "is_first_1m_of_day": metric.get("is_first_1m_of_day"),
        "is_first_5m_of_day": metric.get("is_first_5m_of_day"),
        "is_first_30m_of_day": metric.get("is_first_30m_of_day"),
        "is_first_120m_of_day": metric.get("is_first_120m_of_day"),
        "first_1m_amount_default_pass": metric.get("first_1m_amount_default_pass"),
        "first_5m_amount_default_pass": metric.get("first_5m_amount_default_pass"),
        "previous_1m_period_source": metric.get("previous_1m_period_source"),
        "previous_5m_period_source": metric.get("previous_5m_period_source"),
        "previous_30m_period_source": metric.get("previous_30m_period_source"),
        "previous_120m_period_source": metric.get("previous_120m_period_source"),
        "boundary_policy_version": metric.get("boundary_policy_version"),
        "buy_120m_price_pass": buy_flags.get("buy_120m_price_pass"),
        "buy_30m_price_pass": buy_flags.get("buy_30m_price_pass"),
        "buy_5m_price_pass": buy_flags.get("buy_5m_price_pass"),
        "buy_5m_amount_pass": buy_flags.get("buy_5m_amount_pass"),
        "buy_1m_price_pass": buy_flags.get("buy_1m_price_pass"),
        "buy_1m_amount_pass": buy_flags.get("buy_1m_amount_pass"),
        "sell_120m_price_pass": sell_flags.get("sell_120m_price_pass"),
        "sell_30m_price_pass": sell_flags.get("sell_30m_price_pass"),
        "sell_5m_price_pass": sell_flags.get("sell_5m_price_pass"),
        "sell_5m_amount_pass": sell_flags.get("sell_5m_amount_pass"),
        "sell_1m_price_pass": sell_flags.get("sell_1m_price_pass"),
        "sell_1m_amount_pass": sell_flags.get("sell_1m_amount_pass"),
        "metric_quality_status": "passed" if metric_ready else "failed",
        "metric_ready": metric_ready,
        "source_fact_ids": {
            "source": "retained_n3_1m_source_facts",
            "source_mode": source_mode,
            "source_live_minute_kind": LIVE_CURRENT_1M_SOURCE_MODE if source_mode == LIVE_CURRENT_1M_SOURCE_MODE else None,
            "source_live_minute_run_id": source_live_minute_run_id,
            "source_today_minute_run_id_compat": required_lineage["source_today_minute_run_id"],
            "source_today_minute_run_id_compat_policy": source_today_minute_run_id_compat_policy,
            "c1_dependency": c1_dependency,
            "no_c1_table_rows_read": no_c1_table_rows_read,
            "no_c1_table_rows_written": no_c1_table_rows_written,
            "source_condition_run_id": source_condition_run_id,
            "source_subscription_run_id": source_subscription_run_id,
            "source_time_policy": source_time_policy,
            "proof_input_time": proof_input_time,
            "proof_input_time_source": proof_input_time_source,
            "source_returned_time_lineage": source_returned_time_lineage or None,
            **required_lineage,
            "lineage_policy": lineage_policy,
            "source_snapshot_id_policy": source_snapshot_id_policy,
            "candidate_ref": candidate.get("candidate_ref") or candidate.get("source_event_id"),
        },
        "source_minute_refs": metric.get("source_minute_refs") or [],
        "previous_day_minute_refs": metric.get("previous_day_minute_refs") or [],
        "calculation_config_hash": "v3.realtime_virtual_metric.writer.v1",
        "raw_json": raw_json,
    }
    for key, value in metric.items():
        if key in {
            "realtime_metric_schema_version",
            "metric_time_label",
            "source_time",
            "observed_at",
            "snapshot_id",
            "event_id",
            "quality_status",
            "session_kind",
            "period_source",
            "is_closed_1m",
            "is_auction_virtual",
            "midday_bridge_policy",
            "deterministic_pass_flags",
            "current_1m_body_high",
            "current_1m_body_low",
            "current_5m_body_high",
            "current_5m_body_low",
            "current_30m_body_high",
            "current_30m_body_low",
            "current_120m_body_high",
            "current_120m_body_low",
            "current_d_body_high",
            "current_d_body_low",
            "current_w_body_high",
            "current_w_body_low",
            "current_m_body_high",
            "current_m_body_low",
            "current_q_body_high",
            "current_q_body_low",
            "current_y_body_high",
            "current_y_body_low",
            "previous_d_body_high",
            "previous_d_body_low",
            "previous_w_body_high",
            "previous_w_body_low",
            "previous_m_body_high",
            "previous_m_body_low",
            "previous_q_body_high",
            "previous_q_body_low",
            "previous_y_body_high",
            "previous_y_body_low",
            "today_virt_amount",
            "weekly_avg_with_today",
            "monthly_avg_with_today",
            "quarterly_avg_with_today",
            "yearly_avg_with_today",
            "prev_weekly_avg",
            "prev_monthly_avg",
            "prev_quarterly_avg",
            "prev_yearly_avg",
            "current_30m_virtual_amount",
            "previous_day_same_window_amount",
            "previous_day_same_5m_full_amount",
            "previous_day_same_30m_full_amount",
            "previous_30m_full_amount",
            "current_120m_virtual_amount",
            "previous_120m_full_amount",
            "current_d_virtual_amount",
            "previous_d_amount",
            "current_w_virtual_amount",
            "previous_w_amount",
            "current_m_virtual_amount",
            "previous_m_amount",
            "current_q_virtual_amount",
            "previous_q_amount",
            "current_y_virtual_amount",
            "previous_y_amount",
            "trace_json",
        }:
            row[key] = value
    row.setdefault("realtime_metric_schema_version", "v3.realtime_virtual_metric.v1")
    row.setdefault("metric_time_label", metric_time_label)
    trace_json = dict(row.get("trace_json") or {})
    trace_json["closed_minute_proof"] = closed_minute_proof
    if normalization_trace:
        trace_json["minute_label_normalization"] = normalization_trace
    trace_json["source_mode"] = source_mode
    trace_json["source_live_minute_kind"] = LIVE_CURRENT_1M_SOURCE_MODE if source_mode == LIVE_CURRENT_1M_SOURCE_MODE else None
    trace_json["source_live_minute_run_id"] = source_live_minute_run_id
    trace_json["source_today_minute_run_id_compat"] = required_lineage["source_today_minute_run_id"]
    trace_json["source_today_minute_run_id_compat_policy"] = source_today_minute_run_id_compat_policy
    trace_json["c1_dependency"] = c1_dependency
    trace_json["no_c1_table_rows_read"] = no_c1_table_rows_read
    trace_json["no_c1_table_rows_written"] = no_c1_table_rows_written
    trace_json["source_time_policy"] = source_time_policy
    trace_json["proof_input_time"] = proof_input_time
    trace_json["proof_input_time_source"] = proof_input_time_source
    if source_returned_time_lineage:
        trace_json["source_returned_time_lineage"] = source_returned_time_lineage
    trace_json["source_snapshot_id_policy"] = source_snapshot_id_policy
    trace_json["source_run_id_fk_lineage_policy"] = lineage_policy
    trace_json["raw_current_price_source"] = raw_current_price_source
    if current_price_source_canonicalization:
        trace_json["current_price_source_canonicalization"] = current_price_source_canonicalization
    if source_mode == LIVE_CURRENT_1M_SOURCE_MODE:
        assert_no_legacy_midday_bridge_semantic(raw_json, trace_json=trace_json)
    row["trace_json"] = trace_json
    return row


def assert_no_legacy_midday_bridge_semantic(raw_json: Mapping[str, Any], *, trace_json: Mapping[str, Any] | None) -> None:
    haystack = str(raw_json)
    if trace_json is not None:
        haystack += str(trace_json)
    if LEGACY_MIDDAY_BRIDGE_POLICY in haystack:
        raise VirtualMetricWriterBlocked(
            "BLOCKED_NEED_INPUT_RESOLVER: live_current_1m output contains legacy 13:00 midpoint bridge semantic"
        )


def _optional_int(mapping: Mapping[str, Any], *keys: str) -> int | None:
    for key in keys:
        if key in mapping and mapping.get(key) is not None:
            return int(mapping.get(key) or 0)
    return None


def _as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def _row_not_ready_reasons(row: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    for payload_key in ("raw_json", "trace_json"):
        payload = row.get(payload_key) or {}
        if not isinstance(payload, Mapping):
            continue
        for reason_key in ("blocked_reasons", "not_ready_reasons", "metric_not_ready_reasons"):
            reasons.extend(_as_string_list(payload.get(reason_key)))
    return sorted(set(reason for reason in reasons if reason))


def _reason_allowed_by_expected_not_ready_policy(
    reasons: Sequence[str],
    *,
    allowed_reasons: Sequence[str],
    allowed_prefixes: Sequence[str],
) -> bool:
    if not reasons:
        return False
    allowed_reason_set = set(allowed_reasons)
    for reason in reasons:
        if reason in allowed_reason_set:
            return True
        if any(reason.startswith(prefix) for prefix in allowed_prefixes):
            return True
    return False


def _expected_not_ready_quality_warning_report(
    contract: Mapping[str, Any],
    rows_by_asset: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    expected = contract.get("expected_rows") or {}
    rows = [row for asset in ASSET_KINDS for row in rows_by_asset.get(asset, [])]
    not_ready_rows = [row for row in rows if not row.get("metric_ready")]
    reason_counts = Counter(reason for row in not_ready_rows for reason in _row_not_ready_reasons(row))
    expected_not_ready = _optional_int(expected, "metric_not_ready", "metric_not_ready_count", "expected_not_ready_count")
    allowed_reasons = _as_string_list(
        expected.get("expected_not_ready_blocked_reasons") or contract.get("expected_not_ready_blocked_reasons")
    )
    allowed_prefixes = _as_string_list(
        expected.get("expected_not_ready_blocked_reason_prefixes")
        or contract.get("expected_not_ready_blocked_reason_prefixes")
    )
    reason = str(
        expected.get("expected_not_ready_reason")
        or contract.get("expected_not_ready_reason")
        or ""
    )
    if not not_ready_rows and not expected_not_ready:
        status = "not_applicable"
    elif expected_not_ready == len(not_ready_rows) and expected_not_ready and allowed_prefixes:
        status = "warning"
    elif expected_not_ready == len(not_ready_rows) and expected_not_ready and allowed_reasons:
        status = "warning"
    else:
        status = "blocked"
    return {
        "status": status,
        "reason": reason,
        "expected_not_ready_count": int(expected_not_ready or 0),
        "actual_not_ready_count": len(not_ready_rows),
        "blocked_reason_counts": dict(sorted(reason_counts.items())),
        "allowed_blocked_reasons": list(allowed_reasons),
        "allowed_blocked_reason_prefixes": list(allowed_prefixes),
    }


def validate_rows_against_contract(
    rows_by_asset: Mapping[str, Sequence[Mapping[str, Any]]],
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    rows = [row for asset in ASSET_KINDS for row in rows_by_asset.get(asset, [])]
    row_counts = {asset: len(rows_by_asset.get(asset, [])) for asset in ASSET_KINDS}
    row_counts["total"] = sum(row_counts.values())
    signal_counts = Counter(str((row.get("raw_json") or {}).get("signal_type") or row.get("signal_type") or "") for row in rows)
    expected = contract.get("expected_rows") or {}
    blocked: list[str] = []
    if int(expected.get("total") or 0) != row_counts["total"]:
        blocked.append("expected_row_count_mismatch")
    if dict(expected.get("by_signal_type") or {}) != dict(signal_counts):
        blocked.append("expected_signal_distribution_mismatch")
    metric_ready_rows = sum(1 for row in rows if row.get("metric_ready"))
    not_ready_rows = [row for row in rows if not row.get("metric_ready")]
    expected_metric_ready = _optional_int(expected, "metric_ready", "metric_ready_count")
    expected_metric_not_ready = _optional_int(
        expected,
        "metric_not_ready",
        "metric_not_ready_count",
        "expected_not_ready_count",
    )
    if expected_metric_ready is not None and expected_metric_ready != metric_ready_rows:
        blocked.append("expected_metric_ready_count_mismatch")
    if expected_metric_not_ready is not None and expected_metric_not_ready != len(not_ready_rows):
        blocked.append("expected_metric_not_ready_count_mismatch")
    expected_not_ready_warning = _expected_not_ready_quality_warning_report(contract, rows_by_asset)
    if not_ready_rows and int(expected_not_ready_warning.get("expected_not_ready_count") or 0) <= 0:
        blocked.append("metric_not_ready_rows_present")
    elif not_ready_rows and expected_not_ready_warning.get("status") != "warning":
        blocked.append("metric_not_ready_rows_present")
    elif not_ready_rows:
        allowed_reasons = expected_not_ready_warning.get("allowed_blocked_reasons") or []
        allowed_prefixes = expected_not_ready_warning.get("allowed_blocked_reason_prefixes") or []
        unexpected_not_ready_rows = [
            row
            for row in not_ready_rows
            if not _reason_allowed_by_expected_not_ready_policy(
                _row_not_ready_reasons(row),
                allowed_reasons=allowed_reasons,
                allowed_prefixes=allowed_prefixes,
            )
        ]
        if unexpected_not_ready_rows:
            blocked.append("unexpected_metric_not_ready_reason")
    if any(not row.get("source_minute_refs") for row in rows):
        blocked.append("source_minute_refs_missing")
    if any(_has_unresolved_fk_lineage(row) for row in rows):
        blocked.append("source_run_id_fk_lineage_unresolved")
    if _is_b1_source_returned_snapshot_source(contract):
        unique_keys = [
            (
                row.get("asset_kind"),
                row.get("identity_key"),
                row.get("trade_date"),
                row.get("metric_minute_label"),
                row.get("projection_schema_version"),
                (row.get("raw_json") or {}).get("condition_key"),
                (row.get("raw_json") or {}).get("original_condition_key"),
                (row.get("trace_json") or {}).get("higher_period_context_source", {}).get("source_condition_pool_id"),
                (row.get("trace_json") or {}).get("higher_period_context_source", {}).get("source_minute_target_scope_id"),
            )
            for row in rows
        ]
    else:
        unique_keys = [
            (
                row.get("asset_kind"),
                row.get("identity_key"),
                row.get("trade_date"),
                row.get("metric_minute_label"),
                row.get("projection_schema_version"),
            )
            for row in rows
        ]
    duplicate_unique_keys = [key for key, count in Counter(unique_keys).items() if count > 1]
    if duplicate_unique_keys:
        blocked.append("duplicate_metric_unique_key_rows")
    if any(
        row.get("metric_ready")
        and not row.get("previous_day_minute_refs")
        and any(
            row.get(key) == "previous_trade_date_last_period"
            for key in (
                "previous_1m_period_source",
                "previous_5m_period_source",
                "previous_30m_period_source",
                "previous_120m_period_source",
            )
        )
        for row in rows
    ):
        blocked.append("previous_day_minute_refs_missing")
    same_window_policy = contract.get("previous_day_same_window_amount_policy") or {}
    same_window_required = bool(same_window_policy.get("required_for_metric_ready_rows"))
    same_window_non_null = sum(
        1 for row in rows if row.get("metric_ready") and row.get("previous_day_same_window_amount") is not None
    )
    if same_window_required and same_window_non_null != metric_ready_rows:
        blocked.append(
            str(
                same_window_policy.get("writer_validation_blocker")
                or "previous_day_same_window_amount_missing"
            )
        )
    virtual_amount_integrity = validate_virtual_amount_policy_integrity(rows)
    if virtual_amount_integrity["missing_proof_rows"]:
        blocked.append("current_30m_virtual_amount_policy_proof_missing")
    if virtual_amount_integrity["required_trace_missing_rows"]:
        blocked.append("current_virtual_amount_policy_required_trace_missing")
    if virtual_amount_integrity["mismatch_rows"]:
        blocked.append("current_30m_virtual_amount_policy_mismatch")
    uppercase_alias_keys = [
        key
        for row in rows
        for key in row.keys()
        if key.startswith(("current_D", "current_W", "current_M", "current_Q", "current_Y", "previous_D", "previous_W", "previous_M", "previous_Q", "previous_Y"))
    ]
    if uppercase_alias_keys:
        blocked.append("uppercase_display_alias_written_as_db_column")
    sparse_exception_report = _resolved_sparse_no_trade_report(contract, rows_by_asset=rows_by_asset)
    if sparse_exception_report.get("status") == "blocked":
        blocked.extend(str(reason) for reason in sparse_exception_report.get("blocked_reasons") or [])
    return {
        "valid": not blocked,
        "blocked_reasons": sorted(set(blocked)),
        "row_counts": row_counts,
        "signal_counts": dict(signal_counts),
        "metric_ready_count": metric_ready_rows,
        "metric_not_ready_count": len(not_ready_rows),
        "expected_not_ready_quality_warning": expected_not_ready_warning,
        "live_current_sparse_no_trade_exception_report": sparse_exception_report,
        "virtual_amount_policy_integrity": virtual_amount_integrity,
        "previous_day_same_window_amount_coverage": {
            "required_for_metric_ready_rows": same_window_required,
            "metric_ready_rows": metric_ready_rows,
            "non_null_rows": same_window_non_null,
            "missing_rows": metric_ready_rows - same_window_non_null,
        },
    }


def validate_virtual_amount_policy_integrity(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    checked_rows = 0
    missing_proof_rows = 0
    required_trace_missing_rows = 0
    mismatch_rows = 0
    mismatch_samples: list[dict[str, Any]] = []
    required_trace_missing_samples: list[dict[str, Any]] = []
    required_trace_fields = (
        "metric_policy",
        "current_elapsed_amount",
        "previous_day_same_elapsed_amount",
        "previous_day_same_full_amount",
        "amount_unit",
        "current_period_amount_source_kind",
    )
    for row in rows:
        for period in ("5m", "30m"):
            current_amount = decimal_or_none(row.get(f"current_{period}_virtual_amount"))
            if current_amount is None:
                continue
            checked_rows += 1
            proof = virtual_amount_policy_proof(row, period)
            if not proof or str(proof.get("status") or "") != "passed":
                missing_proof_rows += 1
                continue
            missing_fields = [field for field in required_trace_fields if proof.get(field) in (None, "")]
            if (
                proof.get("metric_policy") != "previous_day_same_window_elapsed_ratio_v1"
                or proof.get("amount_unit") != "yuan"
                or proof.get("current_period_amount_source_kind") != "N3_standard_period_metric"
            ):
                missing_fields.append("policy_identity")
            if missing_fields:
                required_trace_missing_rows += 1
                if len(required_trace_missing_samples) < 5:
                    required_trace_missing_samples.append(
                        {
                            "asset_kind": row.get("asset_kind"),
                            "identity_key": row.get("identity_key"),
                            "metric_minute_label": row.get("metric_minute_label"),
                            "period": period,
                            "missing_fields": sorted(set(missing_fields)),
                        }
                    )
                continue
            expected = expected_virtual_amount_from_proof(proof)
            if expected is None or not decimals_close(current_amount, expected):
                mismatch_rows += 1
                if len(mismatch_samples) < 5:
                    mismatch_samples.append(
                        {
                            "asset_kind": row.get("asset_kind"),
                            "identity_key": row.get("identity_key"),
                            "metric_minute_label": row.get("metric_minute_label"),
                            "period": period,
                            "stored_current_virtual_amount": str(current_amount),
                            "proof_current_virtual_amount": None if expected is None else str(expected),
                        }
                    )
    return {
        "checked_rows": checked_rows,
        "missing_proof_rows": missing_proof_rows,
        "required_trace_missing_rows": required_trace_missing_rows,
        "mismatch_rows": mismatch_rows,
        "required_trace_missing_samples": required_trace_missing_samples,
        "mismatch_samples": mismatch_samples,
        "policy": "current_30m_virtual_amount must equal current_elapsed_amount / previous_day_same_elapsed_amount * previous_day_same_full_amount",
    }


def virtual_amount_policy_proof(row: Mapping[str, Any], period: str) -> Mapping[str, Any]:
    for container_name in ("trace_json", "raw_json"):
        container = row.get(container_name)
        if isinstance(container, str):
            try:
                container = json.loads(container)
            except json.JSONDecodeError:
                container = None
        if not isinstance(container, Mapping):
            continue
        policy = container.get("virtual_amount_policy")
        if not isinstance(policy, Mapping):
            continue
        periods = policy.get("periods")
        if not isinstance(periods, Mapping):
            continue
        proof = periods.get(period)
        if isinstance(proof, Mapping):
            return proof
    return {}


def expected_virtual_amount_from_proof(proof: Mapping[str, Any]) -> Decimal | None:
    current_elapsed_amount = decimal_or_none(proof.get("current_elapsed_amount"))
    previous_elapsed_amount = decimal_or_none(proof.get("previous_day_same_elapsed_amount"))
    previous_full_amount = decimal_or_none(proof.get("previous_day_same_full_amount"))
    if (
        current_elapsed_amount is None
        or previous_elapsed_amount is None
        or previous_full_amount is None
        or previous_elapsed_amount <= 0
    ):
        return None
    return current_elapsed_amount / previous_elapsed_amount * previous_full_amount


def decimal_or_none(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def decimals_close(left: Decimal, right: Decimal) -> bool:
    tolerance = Decimal("0.01")
    return abs(left - right) <= tolerance


def _base_side_effects(*, database_written: bool) -> dict[str, bool]:
    return {
        "database_written": database_written,
        "business_rows_written": database_written,
        "outbox_written": False,
        "outbox_inbox_checkpoint_consumed_or_updated": False,
        "wrapper_or_scheduler_started": False,
        "n4_n5_executed": False,
        "n6_entered": False,
        "voice_mobile_sim_trade_touched": False,
        "old_system_touched": False,
    }


def _closed_minute_summary(rows_by_asset: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, Any]:
    by_asset: dict[str, dict[str, int]] = {}
    total = 0
    closed_true = 0
    closed_false = 0
    for asset in ASSET_KINDS:
        rows = list(rows_by_asset.get(asset, []))
        asset_true = sum(1 for row in rows if bool(row.get("is_closed_1m")))
        asset_false = len(rows) - asset_true
        by_asset[asset] = {
            "total": len(rows),
            "closed_1m_true": asset_true,
            "closed_1m_false": asset_false,
        }
        total += len(rows)
        closed_true += asset_true
        closed_false += asset_false
    return {
        "total": total,
        "closed_1m_true": closed_true,
        "closed_1m_false": closed_false,
        "by_asset": by_asset,
    }


def _build_target_absence_for_report(
    *,
    target_run_id: str,
    target_absence_counts: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if target_absence_counts is None:
        return {
            "target_run_id": target_run_id,
            "status": "not_checked",
            "reason": "target_absence_counts_not_provided",
        }
    report = build_target_absence_report(target_run_id=target_run_id, counts=target_absence_counts)
    assert_target_absent(report)
    return report


def _writer_report_fields(
    *,
    contract: Mapping[str, Any],
    validation: Mapping[str, Any] | None,
    rows_by_asset: Mapping[str, Sequence[Mapping[str, Any]]] | None,
    target_absence: Mapping[str, Any] | None,
    side_effects: Mapping[str, Any],
) -> dict[str, Any]:
    target_run_id = _target_run_id(contract)
    scope = _source_scope(contract)
    parsed: dict[str, str] = {}
    input_contract_report: Mapping[str, Any] = {"status": "not_applicable"}
    if _is_n3p_realtime_action_contract(contract):
        parsed = parse_n3p_realtime_action_confirmation_metric_run_id(target_run_id)
        input_contract_report = build_db_backed_input_contract_report(contract)
    until_minute = (
        parsed.get("until_minute")
        or _minute_hhmm(str(contract.get("until_minute_label") or scope.get("until_minute_label") or ""))
        or None
    )
    counts = dict((validation or {}).get("row_counts") or {})
    rows = [row for asset in ASSET_KINDS for row in list((rows_by_asset or {}).get(asset, []))]
    metric_ready_count = sum(1 for row in rows if bool(row.get("metric_ready")))
    metric_not_ready_count = len(rows) - metric_ready_count
    sparse_exception_report = _resolved_sparse_no_trade_report(contract, rows_by_asset=rows_by_asset)
    expected_not_ready_report = (
        dict((validation or {}).get("expected_not_ready_quality_warning") or {})
        if validation
        else _expected_not_ready_quality_warning_report(contract, rows_by_asset or {})
    )
    return {
        "run_id": target_run_id,
        "for_trade_date": str(scope.get("for_trade_date") or contract.get("for_trade_date") or parsed.get("for_trade_date") or ""),
        "until_minute": until_minute,
        "input_refs": dict(input_contract_report.get("input_refs") or {}),
        "db_backed_input_contract": dict(input_contract_report),
        "source_mode": input_contract_report.get("source_mode"),
        "c1_dependency": input_contract_report.get("c1_dependency"),
        "no_c1_table_rows_read": bool(input_contract_report.get("no_c1_table_rows_read")),
        "no_c1_table_rows_written": bool(input_contract_report.get("no_c1_table_rows_written")),
        "target_absence": dict(target_absence or {}),
        "metric_counts_by_asset": counts,
        "rows_by_asset": counts,
        "metric_ready_count": metric_ready_count,
        "metric_not_ready_count": metric_not_ready_count,
        "expected_not_ready_quality_warning": expected_not_ready_report,
        "live_current_sparse_no_trade_exception_report": sparse_exception_report,
        "live_current_sparse_no_trade_exception_count": int(sparse_exception_report.get("exception_count") or 0),
        "closed_minute_summary": _closed_minute_summary(rows_by_asset or {}),
        "side_effect_guard": dict(side_effects),
        "final_status": "passed",
    }


def run_virtual_metric_writer(
    *,
    contract: Mapping[str, Any],
    preflight: Mapping[str, Any],
    source_payload: Mapping[str, Any] | None,
    execute: bool,
    user_confirmed: bool,
    write_fn: Callable[..., Mapping[str, Any]] | None = None,
    target_absence_counts: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    require_execute_flags(execute=execute, user_confirmed=user_confirmed)
    if preflight.get("result") != "PREFLIGHT_PASS":
        raise VirtualMetricWriterBlocked("V3 realtime virtual metric writer blocked: preflight is not PREFLIGHT_PASS")
    target_run_id = _target_run_id(contract)
    if _is_n3p_realtime_action_contract(contract):
        build_db_backed_input_contract_report(contract)
    target_absence = _build_target_absence_for_report(
        target_run_id=target_run_id,
        target_absence_counts=target_absence_counts,
    )
    if not source_payload:
        if execute:
            raise VirtualMetricWriterBlocked("V3 realtime virtual metric writer blocked: missing source payload")
        side_effects = _base_side_effects(database_written=False)
        extra_fields = _writer_report_fields(
            contract=contract,
            validation=None,
            rows_by_asset=None,
            target_absence=target_absence,
            side_effects=side_effects,
        )
        return {
            "result": "PLAN_ONLY",
            "target_run_id": target_run_id,
            "planned_rows": contract.get("expected_rows"),
            "write_result": {"run_rows": 0, "quality_rows": 0, "metric_rows": 0},
            "side_effects": side_effects,
            **extra_fields,
        }
    rows_by_asset = build_rows_by_asset_from_source_payload(contract, source_payload)
    contract_for_run = _contract_with_sparse_no_trade_report(
        contract,
        source_payload=source_payload,
        rows_by_asset=rows_by_asset,
    )
    validation = validate_rows_against_contract(rows_by_asset, contract_for_run)
    if not validation["valid"]:
        raise VirtualMetricWriterBlocked(
            "V3 realtime virtual metric writer blocked: " + ",".join(validation["blocked_reasons"])
        )
    if not execute:
        side_effects = _base_side_effects(database_written=False)
        extra_fields = _writer_report_fields(
            contract=contract_for_run,
            validation=validation,
            rows_by_asset=rows_by_asset,
            target_absence=target_absence,
            side_effects=side_effects,
        )
        return {
            "result": "PLAN_ONLY",
            "target_run_id": target_run_id,
            "planned_rows": validation["row_counts"],
            "signal_counts": validation["signal_counts"],
            "write_result": {"run_rows": 0, "quality_rows": 0, "metric_rows": 0},
            "side_effects": side_effects,
            **extra_fields,
        }
    if write_fn is None:
        write_fn = write_rows_to_db
    if write_fn is write_rows_to_db:
        write_result = dict(write_fn(contract=contract_for_run, rows_by_asset=rows_by_asset, source_payload=source_payload))
    else:
        write_result = dict(write_fn(contract=contract_for_run, rows_by_asset=rows_by_asset))
    side_effects = _base_side_effects(database_written=True)
    extra_fields = _writer_report_fields(
        contract=contract_for_run,
        validation=validation,
        rows_by_asset=rows_by_asset,
        target_absence=target_absence,
        side_effects=side_effects,
    )
    return {
        "result": "EXECUTE_PASS",
        "target_run_id": target_run_id,
        "actual_rows": validation["row_counts"],
        "signal_counts": validation["signal_counts"],
        "write_result": write_result,
        "side_effects": side_effects,
        "finished_at": utc_now_iso(),
        **extra_fields,
    }


def write_rows_to_db(
    *,
    contract: Mapping[str, Any],
    rows_by_asset: Mapping[str, Sequence[Mapping[str, Any]]],
    source_payload: Mapping[str, Any] | None = None,
) -> dict[str, int]:
    dsn = os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN)
    target_run_id = _target_run_id(contract)
    scope = _source_scope(contract)
    rows_total = sum(len(rows_by_asset.get(asset, [])) for asset in ASSET_KINDS)
    sparse_exception_report = _resolved_sparse_no_trade_report(contract, rows_by_asset=rows_by_asset)
    sparse_exception_count = int(sparse_exception_report.get("exception_count") or 0)
    expected_not_ready_report = _expected_not_ready_quality_warning_report(contract, rows_by_asset)
    expected_not_ready_count = (
        int(expected_not_ready_report.get("actual_not_ready_count") or 0)
        if expected_not_ready_report.get("status") == "warning"
        else 0
    )
    started_at = utc_now_iso()
    with audited_n3_market_execute_connect(dsn, connect_timeout=10, row_factory=dict_row) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                target_absence = build_target_absence_report(
                    target_run_id=target_run_id,
                    counts=fetch_target_absence_counts(cur, target_run_id),
                )
                assert_target_absent(target_absence)
                live_source_run_rows = ensure_live_current_1m_source_run(
                    cur=cur,
                    contract=contract,
                    rows_total=rows_total,
                    started_at=started_at,
                )
                source_payload_run_rows = ensure_mixed_realtime_source_payload_run(
                    cur=cur,
                    contract=contract,
                    source_payload=source_payload,
                    started_at=started_at,
                )
                cur.execute(
                    """
                    INSERT INTO common_market_data_run (
                      run_id, source_condition_run_id, for_trade_date, source_trade_date,
                      prev_trade_date, mode, status, p0_count, p1_count, p2_count,
                      source_scope_row_count, candidate_row_count, subscription_row_count,
                      subscription_object_count, dedup_ratio, generated_by,
                      market_data_pulled, market_data_fact_written,
                      downstream_layers_touched, worker_started, started_at, finished_at, raw_json
                    )
                    VALUES (%s, %s, %s, %s, %s, 'execute', 'passed', 0, %s, 0,
                            %s, %s, %s, %s, NULL, 'V3-realtime-virtual-metric-writer',
                            false, true, false, false, %s, now(), %s)
                    """,
                    (
                        target_run_id,
                        scope.get("source_condition_run_id"),
                        scope.get("for_trade_date"),
                        scope.get("source_trade_date"),
                        scope.get("source_trade_date"),
                        sparse_exception_count + expected_not_ready_count,
                        rows_total,
                        rows_total,
                        rows_total,
                        rows_total,
                        started_at,
                        Jsonb(
                            {
                                "stage": "V3_20260612_REALTIME_VIRTUAL_METRIC_WRITER_RUNNER",
                                "writes_outbox": False,
                                "allowed_write_tables": contract.get("allowed_write_tables"),
                                "live_current_sparse_no_trade_exception_report": sparse_exception_report,
                                "expected_not_ready_quality_warning": expected_not_ready_report,
                            }
                        ),
                    ),
                )
                for asset, table in METRIC_TABLES.items():
                    insert_action_confirmation_metric_rows(cur, table=table, rows=rows_by_asset.get(asset, []))
                cur.execute(
                    """
                    INSERT INTO common_market_data_quality_item (
                      run_id, source_condition_run_id, for_trade_date, source_trade_date,
                      data_domain, layer_scope, table_name, gate_code, gate_name,
                      severity, status, expected_value, actual_value, details
                    )
                    VALUES (%s, %s, %s, %s, 'common', 'market_data_run', 'common_market_data_run',
                            'v3_realtime_virtual_metric_writer_execute_pass',
                            'V3 realtime virtual metric writer execute pass',
                            'P0', 'passed', %s, %s, %s)
                    """,
                    (
                        target_run_id,
                        scope.get("source_condition_run_id"),
                        scope.get("for_trade_date"),
                        scope.get("source_trade_date"),
                        str(rows_total),
                        str(rows_total),
                        Jsonb({"metric_scope": "v3_realtime_virtual_metric"}),
                    ),
                )
                quality_rows = 1
                if sparse_exception_count:
                    cur.execute(
                        """
                        INSERT INTO common_market_data_quality_item (
                          run_id, source_condition_run_id, for_trade_date, source_trade_date,
                          data_domain, layer_scope, table_name, gate_code, gate_name,
                          severity, status, expected_value, actual_value, details
                        )
                        VALUES (%s, %s, %s, %s, 'common', 'market_data_run', 'common_market_data_run',
                                'n3p_live_current_sparse_no_trade_quality_visible',
                                'N3P live-current sparse no-trade objects are quality-visible and non-blocking',
                                'P1', 'warning', %s, %s, %s)
                        """,
                        (
                            target_run_id,
                            scope.get("source_condition_run_id"),
                            scope.get("for_trade_date"),
                            scope.get("source_trade_date"),
                            f"<= {sparse_exception_report.get('exception_count_threshold')}",
                            str(sparse_exception_count),
                            Jsonb(sparse_exception_report),
                        ),
                    )
                    quality_rows += 1
                if expected_not_ready_count:
                    cur.execute(
                        """
                        INSERT INTO common_market_data_quality_item (
                          run_id, source_condition_run_id, for_trade_date, source_trade_date,
                          data_domain, layer_scope, table_name, gate_code, gate_name,
                          severity, status, expected_value, actual_value, details
                        )
                        VALUES (%s, %s, %s, %s, 'common', 'market_data_run', 'common_market_data_run',
                                'n3p_amount_chain_v2_expected_not_ready_quality_visible',
                                'N3P amount-chain v2 expected not-ready rows are quality-visible and non-blocking',
                                'P1', 'warning', %s, %s, %s)
                        """,
                        (
                            target_run_id,
                            scope.get("source_condition_run_id"),
                            scope.get("for_trade_date"),
                            scope.get("source_trade_date"),
                            str(expected_not_ready_report.get("expected_not_ready_count") or 0),
                            str(expected_not_ready_count),
                            Jsonb(expected_not_ready_report),
                        ),
                    )
                    quality_rows += 1
    return {
        "run_rows": 1,
        "live_source_run_rows": live_source_run_rows,
        "source_payload_run_rows": source_payload_run_rows,
        "quality_rows": quality_rows,
        "metric_rows": rows_total,
        "live_current_sparse_no_trade_exception_count": sparse_exception_count,
        "expected_not_ready_count": expected_not_ready_count,
    }


def ensure_live_current_1m_source_run(
    *,
    cur: Any,
    contract: Mapping[str, Any],
    rows_total: int,
    started_at: str,
) -> int:
    if not _is_live_current_1m_source(contract):
        return 0
    input_contract = build_db_backed_input_contract_report(contract)
    live_source_run_id = str(input_contract.get("live_source_run_id") or "")
    if not live_source_run_id:
        raise VirtualMetricWriterBlocked("BLOCKED_NEED_INPUT_RESOLVER: missing live_source_run_id")
    sparse_exception_report = _resolved_sparse_no_trade_report(contract)
    sparse_exception_count = int(sparse_exception_report.get("exception_count") or 0)
    cur.execute("SELECT 1 FROM common_market_data_run WHERE run_id = %s LIMIT 1", (live_source_run_id,))
    if cur.fetchone():
        return 0
    scope = _source_scope(contract)
    cur.execute(
        """
        INSERT INTO common_market_data_run (
          run_id, source_condition_run_id, for_trade_date, source_trade_date,
          prev_trade_date, mode, status, p0_count, p1_count, p2_count,
          source_scope_row_count, candidate_row_count, subscription_row_count,
          subscription_object_count, dedup_ratio, generated_by,
          market_data_pulled, market_data_fact_written,
          downstream_layers_touched, worker_started, started_at, finished_at, raw_json
        )
        VALUES (%s, %s, %s, %s, %s, 'execute', 'passed', 0, %s, 0,
                %s, %s, %s, %s, NULL, 'V3-live-current-1m-source-compat',
                false, false, false, false, %s, now(), %s)
        """,
        (
            live_source_run_id,
            scope.get("source_condition_run_id"),
            scope.get("for_trade_date"),
            scope.get("source_trade_date"),
            scope.get("source_trade_date"),
            sparse_exception_count,
            rows_total,
            rows_total,
            rows_total,
            rows_total,
            started_at,
            Jsonb(
                {
                    "stage": "N3P_live_current_1m_source_compat",
                    "source_mode": LIVE_CURRENT_1M_SOURCE_MODE,
                    "c1_dependency": False,
                    "writes_today_minute_bar_1m": False,
                    "writes_outbox": False,
                    "source_today_minute_run_id_compat": live_source_run_id,
                    "live_current_sparse_no_trade_exception_report": sparse_exception_report,
                }
            ),
        ),
    )
    return 1


def _source_payload_run_id(
    *,
    contract: Mapping[str, Any],
    source_payload: Mapping[str, Any] | None = None,
) -> str:
    for container in (source_payload or {}, _db_input_contract(contract), _source_scope(contract), contract):
        if not isinstance(container, Mapping):
            continue
        value = container.get("source_payload_run_id") or container.get("mixed_realtime_source_payload_run_id")
        if value:
            return str(value)
    return ""


def _source_model(
    *,
    contract: Mapping[str, Any],
    source_payload: Mapping[str, Any] | None = None,
) -> str:
    for container in (source_payload or {}, _db_input_contract(contract), _source_scope(contract), contract):
        if not isinstance(container, Mapping):
            continue
        value = container.get("source_model") or container.get("n3p_realtime_source_model")
        if value:
            return str(value)
    return ""


def _source_payload_registration_writes_outbox_forbidden(
    *,
    contract: Mapping[str, Any],
    source_payload: Mapping[str, Any] | None = None,
) -> None:
    for container in (source_payload or {}, _db_input_contract(contract), _source_scope(contract), contract):
        if not isinstance(container, Mapping) or "writes_outbox" not in container:
            continue
        if _truthy(container.get("writes_outbox")):
            raise VirtualMetricWriterBlocked("BLOCKED_N3P_SOURCE_PAYLOAD_REGISTRATION: source_payload_writes_outbox_forbidden")


def _source_payload_counts(source_payload: Mapping[str, Any] | None) -> dict[str, int]:
    source_payload = source_payload or {}

    def count_key(*keys: str) -> int:
        return len(_payload_rows(source_payload, *keys))

    return {
        "stock_quote_rows": count_key("stock_quote_rows", "stock_quotes_rows"),
        "index_board_1m_rows": count_key("index_board_1m_rows", "index_1m_rows", "board_1m_rows"),
        "previous_day_cumulative_rows": count_key(
            "previous_day_cumulative_rows",
            "a1_previous_day_cumulative_rows",
            "source_previous_day_cumulative_rows",
        ),
        "previous_day_minute_rows": count_key("previous_day_minute_rows", "a1_previous_day_minute_rows"),
    }


def _source_artifact_lineage(
    *,
    contract: Mapping[str, Any],
    source_payload: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    lineage: dict[str, str] = {}
    for output_key, keys in {
        "source_artifact_path": ("source_artifact_path", "source_payload_path", "artifact_path"),
        "source_payload_hash": ("source_payload_hash", "source_hash", "sha256"),
        "source_origin": ("source_origin",),
    }.items():
        value = _first_lineage_value(source_payload or {}, _db_input_contract(contract), _source_scope(contract), contract, keys=keys)
        if value:
            lineage[output_key] = value
    return lineage


def ensure_mixed_realtime_source_payload_run(
    *,
    cur: Any,
    contract: Mapping[str, Any],
    source_payload: Mapping[str, Any] | None,
    started_at: str,
) -> int:
    if _source_model(contract=contract, source_payload=source_payload) != N3P_TRIGGER_PROOF_REALTIME_SOURCE_MODEL:
        return 0
    if not _is_b1_source_returned_snapshot_source(contract):
        return 0
    source_payload_run_id = _source_payload_run_id(contract=contract, source_payload=source_payload)
    if not source_payload_run_id:
        return 0
    _source_payload_registration_writes_outbox_forbidden(contract=contract, source_payload=source_payload)
    cur.execute("SELECT 1 FROM common_market_data_run WHERE run_id = %s LIMIT 1", (source_payload_run_id,))
    if cur.fetchone():
        return 0
    scope = _source_scope(contract)
    counts = _source_payload_counts(source_payload)
    payload_row_count = sum(counts.values())
    lineage = _source_artifact_lineage(contract=contract, source_payload=source_payload)
    raw_json = {
        "stage": N3P_MIXED_REALTIME_SOURCE_PAYLOAD_REGISTRATION_STAGE,
        "source_model": N3P_TRIGGER_PROOF_REALTIME_SOURCE_MODEL,
        "source_mode": _source_mode(contract),
        "source_origin": lineage.get("source_origin") or "local_mootdx_fetch_artifact",
        "source_artifact_path": lineage.get("source_artifact_path"),
        "source_payload_hash": lineage.get("source_payload_hash"),
        "source_payload_counts": counts,
        "writes_outbox": False,
        "writes_n3p_metric_rows": False,
        "not_n5_final_proof": True,
    }
    cur.execute(
        """
        INSERT INTO common_market_data_run (
          run_id, source_condition_run_id, for_trade_date, source_trade_date,
          prev_trade_date, mode, status, p0_count, p1_count, p2_count,
          source_scope_row_count, candidate_row_count, subscription_row_count,
          subscription_object_count, dedup_ratio, generated_by,
          market_data_pulled, market_data_fact_written,
          downstream_layers_touched, worker_started, started_at, finished_at, raw_json
        )
        VALUES (%s, %s, %s, %s, %s, 'execute', 'passed', 0, 0, 0,
                %s, %s, %s, %s, NULL, 'V3-n3p-mixed-realtime-source-payload-registration',
                false, false, false, false, %s, %s, %s)
        """,
        (
            source_payload_run_id,
            scope.get("source_condition_run_id"),
            scope.get("for_trade_date"),
            scope.get("source_trade_date"),
            scope.get("source_trade_date"),
            payload_row_count,
            payload_row_count,
            payload_row_count,
            payload_row_count,
            started_at,
            started_at,
            Jsonb(raw_json),
        ),
    )
    cur.execute(
        """
        INSERT INTO common_market_data_quality_item (
          run_id, source_condition_run_id, for_trade_date, source_trade_date,
          data_domain, layer_scope, table_name, gate_code, gate_name,
          severity, status, expected_value, actual_value, details
        )
        VALUES (%s, %s, %s, %s, 'common', 'market_data_run', 'common_market_data_run',
                'n3p_mixed_realtime_source_payload_registered',
                'N3P mixed realtime source payload run registered as N3 lineage only',
                'P0', 'passed', %s, %s, %s)
        """,
        (
            source_payload_run_id,
            scope.get("source_condition_run_id"),
            scope.get("for_trade_date"),
            scope.get("source_trade_date"),
            str(payload_row_count),
            str(payload_row_count),
            Jsonb(raw_json),
        ),
    )
    return 1


def format_report_markdown(report: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# V3 Realtime Virtual Metric Writer Runner Report",
            "",
            f"- result: `{report.get('result')}`",
            f"- target_run_id: `{report.get('target_run_id')}`",
            f"- planned_rows: `{report.get('planned_rows') or report.get('actual_rows')}`",
            f"- write_result: `{report.get('write_result')}`",
            "",
            "## Boundary",
            "",
            *[f"- {key}: `{value}`" for key, value in dict(report.get("side_effects") or {}).items()],
        ]
    ) + "\n"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run V3 realtime virtual metric writer once.")
    parser.add_argument("--contract-path", default=DEFAULT_CONTRACT_PATH)
    parser.add_argument("--preflight-path", default=DEFAULT_PREFLIGHT_PATH)
    parser.add_argument("--source-payload-path", default=DEFAULT_SOURCE_PAYLOAD_PATH)
    parser.add_argument("--json-report-path", default=DEFAULT_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_REPORT_MD_PATH)
    parser.add_argument("--rollback-sql-path", default="")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    contract = load_json(args.contract_path)
    preflight = load_json(args.preflight_path)
    payload = load_json(args.source_payload_path) if Path(args.source_payload_path).exists() else None
    try:
        if args.rollback_sql_path and args.execute and args.user_confirmed:
            if not _is_n3p_realtime_action_contract(contract):
                raise VirtualMetricWriterBlocked("rollback_sql_path_only_supported_for_n3p_trigger_proof")
            source_payload_run_id = _source_payload_run_id(contract=contract, source_payload=payload) or str(
                preflight.get("source_payload_run_id") or ""
            )
            write_text(
                args.rollback_sql_path,
                build_n3p_trigger_proof_rollback_sql(
                    target_run_id=_target_run_id(contract),
                    source_payload_run_id=source_payload_run_id,
                ),
            )
        report = run_virtual_metric_writer(
            contract=contract,
            preflight=preflight,
            source_payload=payload,
            execute=args.execute,
            user_confirmed=args.user_confirmed,
        )
    except VirtualMetricWriterBlocked as exc:
        report = {
            "result": "BLOCKED",
            "target_run_id": _target_run_id(contract),
            "reason": str(exc),
            "side_effects": _base_side_effects(database_written=False),
        }
        write_json(args.json_report_path, report)
        write_text(args.markdown_report_path, format_report_markdown(report))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2
    if args.rollback_sql_path:
        report["rollback_sql_path"] = args.rollback_sql_path
        report["rollback_ready"] = Path(args.rollback_sql_path).exists()
    write_json(args.json_report_path, report)
    write_text(args.markdown_report_path, format_report_markdown(report))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["result"] in {"PLAN_ONLY", "EXECUTE_PASS"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
