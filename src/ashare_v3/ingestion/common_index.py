"""Common trade calendar and index identity dry-run ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from ashare_v3.ingestion.common import (
    IngestionValidationError,
    QualityGateResult,
    make_index_identity_key,
    make_source_batch_id,
    normalize_index_exchange_from_ts_code,
    require_yyyymmdd,
    stable_raw_hash,
)


class CommonIndexRawSource(Protocol):
    def fetch_trade_calendar(self, *, start_date: str, end_date: str) -> Sequence[Mapping[str, Any]]:
        """Return raw trade calendar rows."""

    def fetch_index_basic(self, *, asof_date: str) -> Sequence[Mapping[str, Any]]:
        """Return raw index identity rows."""


@dataclass(frozen=True)
class CommonIndexIngestionDryRun:
    start_date: str
    end_date: str
    asof_date: str
    source_version: str
    batches: dict[str, str]
    raw_hashes: dict[str, str]
    trade_calendar_rows: list[dict[str, Any]]
    index_identity_rows: list[dict[str, Any]]
    quality_gates: list[QualityGateResult]

    @property
    def passed(self) -> bool:
        return all(gate.passed for gate in self.quality_gates)

    def summary(self) -> dict[str, Any]:
        return {
            "start_date": self.start_date,
            "end_date": self.end_date,
            "asof_date": self.asof_date,
            "source_version": self.source_version,
            "batches": self.batches,
            "raw_hashes": self.raw_hashes,
            "row_counts": {
                "common_trade_calendar": len(self.trade_calendar_rows),
                "index_identity": len(self.index_identity_rows),
                "open_trade_dates": sum(1 for row in self.trade_calendar_rows if row["is_open"]),
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


def run_common_index_ingestion_dry_run(
    source: CommonIndexRawSource,
    *,
    start_date: str,
    end_date: str,
    asof_date: str | None = None,
    version: str = "v1",
) -> CommonIndexIngestionDryRun:
    require_yyyymmdd(start_date, "start_date")
    require_yyyymmdd(end_date, "end_date")
    if start_date > end_date:
        raise IngestionValidationError("start_date must be <= end_date")

    asof_date = require_yyyymmdd(asof_date or end_date, "asof_date")
    period = f"{start_date}_{end_date}"
    batches = {
        "common_trade_calendar": make_source_batch_id("trade_calendar", period, version),
        "index_identity": make_source_batch_id("index_identity", asof_date, version),
    }

    raw_calendar = list(source.fetch_trade_calendar(start_date=start_date, end_date=end_date))
    raw_index_identity = list(source.fetch_index_basic(asof_date=asof_date))

    trade_calendar_rows = normalize_trade_calendar_rows(
        raw_calendar,
        source="tushare.trade_cal",
        source_batch_id=batches["common_trade_calendar"],
        source_version=batches["common_trade_calendar"],
    )
    index_identity_rows = [
        normalize_index_identity_row(
            row,
            source="tushare.index_basic",
            source_batch_id=batches["index_identity"],
            source_version=batches["index_identity"],
        )
        for row in raw_index_identity
    ]

    quality_gates = [
        gate_non_empty("common_trade_calendar_non_empty", trade_calendar_rows),
        gate_non_empty("index_identity_non_empty", index_identity_rows),
        gate_trade_calendar_range(trade_calendar_rows, start_date=start_date, end_date=end_date),
        gate_trade_calendar_open_days(trade_calendar_rows),
        gate_unique_key("common_trade_calendar_unique_trade_date", trade_calendar_rows, ("trade_date",)),
        gate_required_fields(
            trade_calendar_rows,
            ("trade_date", "exchange", "source_batch_id", "source_version"),
            "common_trade_calendar_required_fields",
        ),
        gate_required_fields(
            index_identity_rows,
            ("index_identity_key", "code", "exchange", "source_batch_id", "source_version"),
            "index_identity_key_coverage",
        ),
        gate_unique_key("index_identity_unique_key", index_identity_rows, ("index_identity_key",)),
        gate_index_namespace_isolated(index_identity_rows),
        gate_no_tdx_board_codes_in_index_identity(index_identity_rows),
    ]

    return CommonIndexIngestionDryRun(
        start_date=start_date,
        end_date=end_date,
        asof_date=asof_date,
        source_version=version,
        batches=batches,
        raw_hashes={
            "common_trade_calendar": stable_raw_hash(raw_calendar),
            "index_identity": stable_raw_hash(raw_index_identity),
        },
        trade_calendar_rows=trade_calendar_rows,
        index_identity_rows=index_identity_rows,
        quality_gates=quality_gates,
    )


def normalize_trade_calendar_rows(
    raw_rows: Sequence[Mapping[str, Any]],
    *,
    source: str,
    source_batch_id: str,
    source_version: str,
) -> list[dict[str, Any]]:
    base_rows = [_normalize_trade_calendar_base_row(row) for row in raw_rows]
    base_rows.sort(key=lambda row: row["trade_date"])
    open_dates = [row["trade_date"] for row in base_rows if row["is_open"]]
    next_open_by_date = _build_next_open_by_date(base_rows, open_dates)

    rows: list[dict[str, Any]] = []
    for row in base_rows:
        rows.append(
            {
                "trade_date": row["trade_date"],
                "exchange": row["exchange"],
                "is_open": row["is_open"],
                "prev_trade_date": row["prev_trade_date"],
                "next_trade_date": next_open_by_date.get(row["trade_date"]),
                "source": source,
                "source_batch_id": source_batch_id,
                "source_version": source_version,
                "raw_payload": dict(row["raw_payload"]),
            }
        )
    return rows


def normalize_index_identity_row(
    raw: Mapping[str, Any],
    *,
    source: str,
    source_batch_id: str,
    source_version: str,
) -> dict[str, Any]:
    ts_code = require_text(raw, "ts_code")
    exchange, code = normalize_index_exchange_from_ts_code(ts_code)
    name = require_text(raw, "name")
    exp_date = optional_text(raw, "exp_date")

    return {
        "index_identity_key": make_index_identity_key(exchange, code),
        "ts_code": ts_code,
        "code": code,
        "exchange": exchange,
        "name": name,
        "source_namespace": "TUSHARE",
        "publisher": optional_text(raw, "publisher"),
        "index_category": optional_text(raw, "category") or optional_text(raw, "index_type"),
        "base_date": optional_date(raw, "base_date"),
        "listed_date": optional_date(raw, "list_date"),
        "status": "inactive" if exp_date else "active",
        "source": source,
        "source_batch_id": source_batch_id,
        "source_version": source_version,
        "raw_payload": dict(raw),
    }


def gate_non_empty(gate_name: str, rows: Sequence[Mapping[str, Any]]) -> QualityGateResult:
    return QualityGateResult(
        gate_name=gate_name,
        status="passed" if rows else "failed",
        expected_value=">0",
        actual_value=str(len(rows)),
        details={},
    )


def gate_trade_calendar_range(
    rows: Sequence[Mapping[str, Any]],
    *,
    start_date: str,
    end_date: str,
) -> QualityGateResult:
    actual_start = min((str(row.get("trade_date")) for row in rows), default=None)
    actual_end = max((str(row.get("trade_date")) for row in rows), default=None)
    passed = actual_start == start_date and actual_end == end_date
    return QualityGateResult(
        gate_name="common_trade_calendar_range",
        status="passed" if passed else "failed",
        expected_value=f"{start_date}_{end_date}",
        actual_value=f"{actual_start}_{actual_end}",
        details={},
    )


def gate_trade_calendar_open_days(rows: Sequence[Mapping[str, Any]]) -> QualityGateResult:
    open_count = sum(1 for row in rows if row.get("is_open") is True)
    return QualityGateResult(
        gate_name="common_trade_calendar_open_days",
        status="passed" if open_count > 0 else "failed",
        expected_value=">0",
        actual_value=str(open_count),
        details={},
    )


def gate_required_fields(
    rows: Sequence[Mapping[str, Any]],
    fields: Sequence[str],
    gate_name: str,
) -> QualityGateResult:
    missing = [
        {"row_index": idx, "field": field}
        for idx, row in enumerate(rows)
        for field in fields
        if row.get(field) in (None, "")
    ]
    return QualityGateResult(
        gate_name=gate_name,
        status="passed" if not missing else "failed",
        expected_value="100%",
        actual_value=f"{len(rows) * len(fields) - len(missing)}/{len(rows) * len(fields)}",
        details={"fields": list(fields), "missing": missing[:50]},
    )


def gate_unique_key(
    gate_name: str,
    rows: Sequence[Mapping[str, Any]],
    key_fields: Sequence[str],
) -> QualityGateResult:
    seen: set[tuple[Any, ...]] = set()
    duplicates: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        key = tuple(row.get(field) for field in key_fields)
        if key in seen:
            duplicates.append({"row_index": idx, "key": [str(value) for value in key]})
        seen.add(key)
    return QualityGateResult(
        gate_name=gate_name,
        status="passed" if not duplicates else "failed",
        expected_value="0 duplicates",
        actual_value=str(len(duplicates)),
        details={"key_fields": list(key_fields), "duplicates": duplicates[:50]},
    )


def gate_index_namespace_isolated(rows: Sequence[Mapping[str, Any]]) -> QualityGateResult:
    bad_rows = [
        {
            "row_index": idx,
            "index_identity_key": row.get("index_identity_key"),
            "stock_identity_key": row.get("stock_identity_key"),
        }
        for idx, row in enumerate(rows)
        if not str(row.get("index_identity_key") or "").startswith("index:") or row.get("stock_identity_key")
    ]
    return QualityGateResult(
        gate_name="index_identity_namespace_isolated",
        status="passed" if not bad_rows else "failed",
        expected_value="only index:* identity keys",
        actual_value=str(len(bad_rows)),
        details={"bad_rows": bad_rows[:50]},
    )


def gate_no_tdx_board_codes_in_index_identity(rows: Sequence[Mapping[str, Any]]) -> QualityGateResult:
    bad_codes = sorted({str(row.get("code") or "") for row in rows if str(row.get("code") or "").startswith("88")})
    return QualityGateResult(
        gate_name="index_identity_88xxxx_board_violation",
        status="passed" if not bad_codes else "failed",
        expected_value="0",
        actual_value=str(len(bad_codes)),
        details={"codes": bad_codes[:50]},
    )


def _normalize_trade_calendar_base_row(raw: Mapping[str, Any]) -> dict[str, Any]:
    trade_date = require_yyyymmdd(require_text(raw, "cal_date"), "cal_date")
    prev_trade_date = optional_date(raw, "pretrade_date")
    return {
        "trade_date": trade_date,
        "exchange": optional_text(raw, "exchange") or "SSE",
        "is_open": parse_is_open(raw.get("is_open")),
        "prev_trade_date": prev_trade_date,
        "raw_payload": dict(raw),
    }


def _build_next_open_by_date(
    rows: Sequence[Mapping[str, Any]],
    open_dates: Sequence[str],
) -> dict[str, str | None]:
    if not open_dates:
        return {str(row["trade_date"]): None for row in rows}

    next_by_date: dict[str, str | None] = {}
    next_open: str | None = None
    open_date_set = set(open_dates)
    for row in reversed(rows):
        trade_date = str(row["trade_date"])
        next_by_date[trade_date] = next_open
        if trade_date in open_date_set:
            next_open = trade_date
    return next_by_date


def parse_is_open(value: Any) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"1", "true"}:
        return True
    if normalized in {"0", "false"}:
        return False
    raise IngestionValidationError(f"is_open must be 0/1: {value!r}")


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


def optional_date(raw: Mapping[str, Any], field: str) -> str | None:
    value = optional_text(raw, field)
    if value is None:
        return None
    return require_yyyymmdd(value, field)
