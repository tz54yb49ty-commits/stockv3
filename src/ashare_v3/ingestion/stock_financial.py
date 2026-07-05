"""Stock financial metrics dry-run ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Protocol, Sequence

from ashare_v3.ingestion.common import (
    IngestionValidationError,
    QualityGateResult,
    infer_stock_exchange_from_code,
    make_source_batch_id,
    make_stock_identity_key,
    normalize_exchange_from_ts_code,
    require_stock_code,
    require_yyyymmdd,
    stable_raw_hash,
)


FINANCIAL_METRIC_FIELDS = (
    "roe",
    "revenue_yoy",
    "profit_yoy",
    "total_revenue",
    "net_profit",
    "net_assets",
    "eps",
    "bps",
)


@dataclass(frozen=True)
class StockFinancialSymbol:
    code: str
    exchange: str
    name: str | None = None

    @property
    def stock_identity_key(self) -> str:
        return make_stock_identity_key(self.exchange, self.code)

    @property
    def ts_code(self) -> str:
        return f"{self.code}.{self.exchange}"


class StockFinancialRawSource(Protocol):
    def fetch_stock_financial_metrics(
        self,
        *,
        symbols: Sequence[StockFinancialSymbol],
        asof_date: str,
    ) -> Sequence[Mapping[str, Any]]:
        """Return raw stock financial metric rows."""


@dataclass(frozen=True)
class StockFinancialIngestionDryRun:
    asof_date: str
    source_version: str
    batches: dict[str, str]
    raw_hashes: dict[str, str]
    stock_financial_metrics_rows: list[dict[str, Any]]
    quality_gates: list[QualityGateResult]

    @property
    def passed(self) -> bool:
        return all(gate.passed for gate in self.quality_gates)

    def summary(self) -> dict[str, Any]:
        return {
            "asof_date": self.asof_date,
            "source_version": self.source_version,
            "batches": self.batches,
            "raw_hashes": self.raw_hashes,
            "row_counts": {
                "stock_financial_metrics_fact": len(self.stock_financial_metrics_rows),
            },
            "quality_gates": [
                {
                    "gate_name": gate.gate_name,
                    "status": gate.status,
                    "severity": gate.severity,
                    "expected_value": gate.expected_value,
                    "actual_value": gate.actual_value,
                    "details": dict(gate.details or {}),
                }
                for gate in self.quality_gates
            ],
            "passed": self.passed,
            "will_connect_database": False,
            "will_write_data_files": False,
        }


def run_stock_financial_ingestion_dry_run(
    source: StockFinancialRawSource,
    *,
    symbols: Sequence[StockFinancialSymbol],
    asof_date: str,
    version: str = "v1",
    stock_universe_keys: Sequence[str] | None = None,
) -> StockFinancialIngestionDryRun:
    asof_date = require_yyyymmdd(asof_date, "asof_date")
    if not symbols:
        raise IngestionValidationError("at least one stock financial symbol is required")

    source_batch_id = make_source_batch_id("stock_financial", asof_date, version)
    requested_keys = [symbol.stock_identity_key for symbol in symbols]
    universe_keys = tuple(stock_universe_keys or requested_keys)
    raw_rows = list(source.fetch_stock_financial_metrics(symbols=symbols, asof_date=asof_date))
    normalized_rows = [
        normalize_stock_financial_metrics_row(
            row,
            source="mootdx.finance",
            source_batch_id=source_batch_id,
            source_version=source_batch_id,
            fallback_asof_date=asof_date,
        )
        for row in raw_rows
    ]

    quality_gates = [
        gate_non_empty("stock_financial_non_empty", normalized_rows),
        gate_required_identity_keys(normalized_rows),
        gate_no_board_codes_in_stock_financial(normalized_rows),
        gate_unique_stock_financial_key(normalized_rows),
        gate_financial_metric_presence(normalized_rows),
        gate_stock_financial_universe_alignment(normalized_rows, universe_keys),
        gate_requested_stock_financial_present(normalized_rows, requested_keys),
    ]

    return StockFinancialIngestionDryRun(
        asof_date=asof_date,
        source_version=version,
        batches={"stock_financial_metrics_fact": source_batch_id},
        raw_hashes={"stock_financial_metrics_fact": stable_raw_hash(raw_rows)},
        stock_financial_metrics_rows=normalized_rows,
        quality_gates=quality_gates,
    )


def normalize_stock_financial_metrics_row(
    raw: Mapping[str, Any],
    *,
    source: str,
    source_batch_id: str,
    source_version: str,
    fallback_asof_date: str,
) -> dict[str, Any]:
    exchange, code = parse_stock_code_exchange(raw)
    asof_date = parse_financial_date(raw, ("asof_date", "updated_date", "update_date", "ann_date"), fallback_asof_date)
    report_period = parse_optional_financial_date(raw, ("report_period", "end_date", "report_date"))

    return {
        "stock_identity_key": make_stock_identity_key(exchange, code),
        "asof_date": asof_date,
        "report_period": report_period,
        "ts_code": optional_text(raw, "ts_code") or f"{code}.{exchange}",
        "code": code,
        "exchange": exchange,
        "roe": pick_decimal(raw, "roe", "净资产收益率"),
        "revenue_yoy": pick_decimal(raw, "revenue_yoy", "or_yoy"),
        "profit_yoy": pick_decimal(raw, "profit_yoy", "netprofit_yoy"),
        "total_revenue": pick_decimal(raw, "total_revenue", "zhuyingshouru", "revenue"),
        "net_profit": pick_decimal(raw, "net_profit", "jinglirun"),
        "net_assets": pick_decimal(raw, "net_assets", "jingzichan"),
        "eps": pick_decimal(raw, "eps", "meigushouyi"),
        "bps": pick_decimal(raw, "bps", "meigujingzichan"),
        "source": source,
        "source_batch_id": source_batch_id,
        "source_version": source_version,
        "raw_payload": dict(raw),
    }


def parse_stock_code_exchange(raw: Mapping[str, Any]) -> tuple[str, str]:
    ts_code = optional_text(raw, "ts_code")
    if ts_code:
        return normalize_exchange_from_ts_code(ts_code)

    raw_code = optional_text(raw, "code") or optional_text(raw, "symbol")
    if raw_code is None:
        raise IngestionValidationError("code or ts_code is required")

    if "." in raw_code:
        return normalize_exchange_from_ts_code(raw_code)

    code = require_stock_code(raw_code)
    return infer_stock_exchange_from_code(code), code


def gate_non_empty(gate_name: str, rows: Sequence[Mapping[str, Any]]) -> QualityGateResult:
    return QualityGateResult(
        gate_name=gate_name,
        status="passed" if rows else "failed",
        expected_value=">0",
        actual_value=str(len(rows)),
        details={},
    )


def gate_required_identity_keys(rows: Sequence[Mapping[str, Any]]) -> QualityGateResult:
    missing = [
        {"row_index": idx, "field": "stock_identity_key"}
        for idx, row in enumerate(rows)
        if not row.get("stock_identity_key")
    ]
    return QualityGateResult(
        gate_name="stock_financial_identity_key_coverage",
        status="passed" if not missing else "failed",
        expected_value="100%",
        actual_value=f"{len(rows) - len(missing)}/{len(rows)}",
        details={"missing": missing[:50]},
    )


def gate_no_board_codes_in_stock_financial(rows: Sequence[Mapping[str, Any]]) -> QualityGateResult:
    bad_codes = sorted({str(row.get("code") or "") for row in rows if str(row.get("code") or "").startswith("88")})
    return QualityGateResult(
        gate_name="stock_financial_88xxxx_stock_violation",
        status="passed" if not bad_codes else "failed",
        expected_value="0",
        actual_value=str(len(bad_codes)),
        details={"codes": bad_codes[:50]},
    )


def gate_unique_stock_financial_key(rows: Sequence[Mapping[str, Any]]) -> QualityGateResult:
    seen: set[tuple[Any, ...]] = set()
    duplicates: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        key = (row.get("stock_identity_key"), row.get("asof_date"))
        if key in seen:
            duplicates.append({"row_index": idx, "key": [str(value) for value in key]})
        seen.add(key)
    return QualityGateResult(
        gate_name="stock_financial_unique_key",
        status="passed" if not duplicates else "failed",
        expected_value="0 duplicates",
        actual_value=str(len(duplicates)),
        details={"key_fields": ["stock_identity_key", "asof_date"], "duplicates": duplicates[:50]},
    )


def gate_financial_metric_presence(rows: Sequence[Mapping[str, Any]]) -> QualityGateResult:
    empty_rows = [
        idx
        for idx, row in enumerate(rows)
        if all(row.get(field) is None for field in FINANCIAL_METRIC_FIELDS)
    ]
    return QualityGateResult(
        gate_name="stock_financial_metric_presence",
        status="passed" if not empty_rows else "failed",
        expected_value="at least one financial metric per row",
        actual_value=str(len(empty_rows)),
        details={"empty_row_indexes": empty_rows[:50]},
    )


def gate_stock_financial_universe_alignment(
    rows: Sequence[Mapping[str, Any]],
    stock_universe_keys: Sequence[str],
) -> QualityGateResult:
    universe = set(stock_universe_keys)
    fact_keys = {str(row.get("stock_identity_key")) for row in rows if row.get("stock_identity_key")}
    missing = sorted(fact_keys - universe)
    return QualityGateResult(
        gate_name="stock_financial_universe_alignment",
        status="passed" if not missing else "failed",
        expected_value="all financial keys in stock universe",
        actual_value=str(len(missing)),
        details={"missing_identity_keys": missing[:50]},
    )


def gate_requested_stock_financial_present(
    rows: Sequence[Mapping[str, Any]],
    requested_keys: Sequence[str],
) -> QualityGateResult:
    actual_keys = {str(row.get("stock_identity_key")) for row in rows if row.get("stock_identity_key")}
    missing = sorted(set(requested_keys) - actual_keys)
    return QualityGateResult(
        gate_name="stock_financial_requested_keys_present",
        status="passed" if not missing else "failed",
        expected_value="0 missing",
        actual_value=str(len(missing)),
        details={"missing_identity_keys": missing[:50]},
    )


def parse_financial_date(raw: Mapping[str, Any], fields: Sequence[str], fallback: str) -> str:
    parsed = parse_optional_financial_date(raw, fields)
    return parsed or require_yyyymmdd(fallback, "fallback_asof_date")


def parse_optional_financial_date(raw: Mapping[str, Any], fields: Sequence[str]) -> str | None:
    for field in fields:
        value = raw.get(field)
        if value is None or str(value).strip() == "":
            continue
        return normalize_date_value(value, field)
    return None


def normalize_date_value(value: Any, field_name: str) -> str:
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y%m%d")
    text = str(value).strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return require_yyyymmdd(text[:10].replace("-", ""), field_name)
    if len(text) >= 8:
        return require_yyyymmdd(text[:8], field_name)
    raise IngestionValidationError(f"{field_name} must be YYYYMMDD-like: {value!r}")


def pick_decimal(raw: Mapping[str, Any], *fields: str) -> Decimal | None:
    for field in fields:
        value = raw.get(field)
        if value is not None and str(value).strip() != "":
            return parse_decimal(value, field)
    return None


def parse_decimal(value: Any, field: str) -> Decimal:
    try:
        return Decimal(str(value).replace(",", ""))
    except InvalidOperation as exc:
        raise IngestionValidationError(f"{field} must be numeric: {value!r}") from exc


def optional_text(raw: Mapping[str, Any], field: str) -> str | None:
    value = raw.get(field)
    if value is None or str(value).strip() == "":
        return None
    return str(value).strip()
