"""Stock raw ingestion standardization and quality gates."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from ashare_v3.ingestion.common import (
    IngestionValidationError,
    QualityGateResult,
    make_stock_identity_key,
    normalize_exchange_from_ts_code,
    require_yyyymmdd,
)


def normalize_stock_identity_row(
    raw: Mapping[str, Any],
    *,
    source: str,
    source_batch_id: str,
    source_version: str,
) -> dict[str, Any]:
    ts_code = require_text(raw, "ts_code")
    exchange, code = normalize_exchange_from_ts_code(ts_code)
    name = require_text(raw, "name")
    list_date = optional_text(raw, "list_date")

    return {
        "stock_identity_key": make_stock_identity_key(exchange, code),
        "ts_code": ts_code,
        "code": code,
        "exchange": exchange,
        "name": name,
        "display_code": f"{code}.{exchange}",
        "area": optional_text(raw, "area"),
        "industry": optional_text(raw, "industry"),
        "market": optional_text(raw, "market"),
        "listed_date": require_yyyymmdd(list_date, "list_date") if list_date else None,
        "delisted_date": optional_text(raw, "delist_date") or optional_text(raw, "delisted_date"),
        "is_st": is_st_name(name),
        "status": normalize_stock_status(raw),
        "source": source,
        "source_batch_id": source_batch_id,
        "source_version": source_version,
        "raw_payload": dict(raw),
    }


def normalize_stock_daily_bar_row(
    raw: Mapping[str, Any],
    *,
    source: str,
    source_batch_id: str,
    source_version: str,
    official_daily_proof: bool,
) -> dict[str, Any]:
    ts_code = require_text(raw, "ts_code")
    exchange, code = normalize_exchange_from_ts_code(ts_code)
    trade_date = require_yyyymmdd(require_text(raw, "trade_date"), "trade_date")

    return {
        "stock_identity_key": make_stock_identity_key(exchange, code),
        "trade_date": trade_date,
        "ts_code": ts_code,
        "code": code,
        "exchange": exchange,
        "name": optional_text(raw, "name"),
        "open": require_decimal(raw, "open"),
        "high": require_decimal(raw, "high"),
        "low": require_decimal(raw, "low"),
        "close": require_decimal(raw, "close"),
        "volume": optional_decimal(raw, "vol") or optional_decimal(raw, "volume"),
        "amount": optional_decimal(raw, "amount"),
        "adj_factor": optional_decimal(raw, "adj_factor"),
        "adjust_type": "qfq",
        "source": source,
        "source_batch_id": source_batch_id,
        "source_version": source_version,
        "official_daily_proof": official_daily_proof,
        "raw_payload": dict(raw),
    }


def normalize_stock_daily_basic_row(
    raw: Mapping[str, Any],
    *,
    source: str,
    source_batch_id: str,
    source_version: str,
) -> dict[str, Any]:
    ts_code = require_text(raw, "ts_code")
    exchange, code = normalize_exchange_from_ts_code(ts_code)
    trade_date = require_yyyymmdd(require_text(raw, "trade_date"), "trade_date")

    return {
        "stock_identity_key": make_stock_identity_key(exchange, code),
        "trade_date": trade_date,
        "ts_code": ts_code,
        "code": code,
        "exchange": exchange,
        "close": optional_decimal(raw, "close"),
        "turnover_rate": optional_decimal(raw, "turnover_rate"),
        "turnover_rate_f": optional_decimal(raw, "turnover_rate_f"),
        "volume_ratio": optional_decimal(raw, "volume_ratio"),
        "pe": optional_decimal(raw, "pe"),
        "pe_ttm": optional_decimal(raw, "pe_ttm"),
        "pb": optional_decimal(raw, "pb"),
        "ps": optional_decimal(raw, "ps"),
        "ps_ttm": optional_decimal(raw, "ps_ttm"),
        "dv_ratio": optional_decimal(raw, "dv_ratio"),
        "dv_ttm": optional_decimal(raw, "dv_ttm"),
        "total_share": optional_decimal(raw, "total_share"),
        "float_share": optional_decimal(raw, "float_share"),
        "free_share": optional_decimal(raw, "free_share"),
        "total_mv": optional_decimal(raw, "total_mv"),
        "circ_mv": optional_decimal(raw, "circ_mv"),
        "source": source,
        "source_batch_id": source_batch_id,
        "source_version": source_version,
        "raw_payload": dict(raw),
    }


def gate_identity_key_coverage(rows: Sequence[Mapping[str, Any]]) -> QualityGateResult:
    missing = [idx for idx, row in enumerate(rows) if not row.get("stock_identity_key")]
    return QualityGateResult(
        gate_name="stock_identity_key_coverage",
        status="passed" if not missing else "failed",
        expected_value="100%",
        actual_value=f"{len(rows) - len(missing)}/{len(rows)}",
        details={"missing_row_indexes": missing[:20]},
    )


def gate_no_board_codes_in_stock(rows: Sequence[Mapping[str, Any]]) -> QualityGateResult:
    bad_codes = sorted({str(row.get("code") or "") for row in rows if str(row.get("code") or "").startswith("88")})
    return QualityGateResult(
        gate_name="88xxxx_stock_violation",
        status="passed" if not bad_codes else "failed",
        expected_value="0",
        actual_value=str(len(bad_codes)),
        details={"codes": bad_codes[:50]},
    )


def gate_official_daily_proof(rows: Sequence[Mapping[str, Any]]) -> QualityGateResult:
    missing = [row.get("stock_identity_key") for row in rows if row.get("official_daily_proof") is not True]
    return QualityGateResult(
        gate_name="stock_official_daily_proof",
        status="passed" if not missing else "failed",
        expected_value="0 missing",
        actual_value=str(len(missing)),
        details={"missing_identity_keys": missing[:50]},
    )


def gate_stock_universe_alignment(
    fact_rows: Sequence[Mapping[str, Any]],
    identity_rows: Sequence[Mapping[str, Any]],
) -> QualityGateResult:
    fact_keys = {str(row.get("stock_identity_key")) for row in fact_rows if row.get("stock_identity_key")}
    identity_keys = {str(row.get("stock_identity_key")) for row in identity_rows if row.get("stock_identity_key")}
    missing = sorted(fact_keys - identity_keys)
    return QualityGateResult(
        gate_name="stock_universe_alignment",
        status="passed" if not missing else "failed",
        expected_value="all fact keys in stock_identity",
        actual_value=str(len(missing)),
        details={"missing_identity_keys": missing[:50]},
    )


def require_text(raw: Mapping[str, Any], field: str) -> str:
    value = raw.get(field)
    if value is None or str(value).strip() == "":
        raise IngestionValidationError(f"{field} is required")
    return str(value).strip()


def optional_text(raw: Mapping[str, Any], field: str) -> str | None:
    value = raw.get(field)
    if value is None or str(value).strip() == "":
        return None
    return str(value).strip()


def require_decimal(raw: Mapping[str, Any], field: str) -> Decimal:
    value = optional_decimal(raw, field)
    if value is None:
        raise IngestionValidationError(f"{field} is required")
    return value


def optional_decimal(raw: Mapping[str, Any], field: str) -> Decimal | None:
    value = raw.get(field)
    if value is None or str(value).strip() == "":
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise IngestionValidationError(f"{field} must be numeric: {value!r}") from exc


def is_st_name(name: str) -> bool:
    normalized = name.upper().replace(" ", "")
    return "ST" in normalized or normalized.startswith("*ST")


def normalize_stock_status(raw: Mapping[str, Any]) -> str:
    raw_status = optional_text(raw, "list_status") or optional_text(raw, "status")
    if raw_status is None:
        return "active"
    status_map = {
        "L": "active",
        "D": "delisted",
        "P": "paused",
        "active": "active",
        "delisted": "delisted",
        "paused": "paused",
    }
    return status_map.get(raw_status, "unknown")
