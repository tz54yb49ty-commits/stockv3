"""Index and board daily bar dry-run ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Protocol, Sequence

from ashare_v3.ingestion.common import (
    IngestionValidationError,
    QualityGateResult,
    infer_index_exchange_from_code,
    make_board_identity_key,
    make_index_identity_key,
    make_source_batch_id,
    require_six_digit_code,
    require_yyyymmdd,
    stable_raw_hash,
)


@dataclass(frozen=True)
class IndexDailySymbol:
    code: str
    exchange: str
    name: str | None = None

    @property
    def index_identity_key(self) -> str:
        return make_index_identity_key(self.exchange, self.code)


@dataclass(frozen=True)
class BoardDailySymbol:
    board_code: str
    board_name: str | None = None
    board_type: str = "tdx_other"

    @property
    def board_identity_key(self) -> str:
        return make_board_identity_key("TDX", self.board_code)


class DailyBarRawSource(Protocol):
    def fetch_index_daily_bars(
        self,
        *,
        indexes: Sequence[IndexDailySymbol],
        start_date: str,
        end_date: str,
    ) -> Sequence[Mapping[str, Any]]:
        """Return raw index daily bar rows."""

    def fetch_board_daily_bars(
        self,
        *,
        boards: Sequence[BoardDailySymbol],
        start_date: str,
        end_date: str,
    ) -> Sequence[Mapping[str, Any]]:
        """Return raw board daily bar rows."""


@dataclass(frozen=True)
class DailyBarIngestionDryRun:
    start_date: str
    end_date: str
    expected_trade_dates: tuple[str, ...]
    source_version: str
    batches: dict[str, str]
    raw_hashes: dict[str, str]
    index_daily_bar_rows: list[dict[str, Any]]
    board_daily_bar_rows: list[dict[str, Any]]
    quality_gates: list[QualityGateResult]

    @property
    def passed(self) -> bool:
        return all(gate.passed for gate in self.quality_gates)

    def summary(self) -> dict[str, Any]:
        return {
            "start_date": self.start_date,
            "end_date": self.end_date,
            "expected_trade_dates": list(self.expected_trade_dates),
            "source_version": self.source_version,
            "batches": self.batches,
            "raw_hashes": self.raw_hashes,
            "row_counts": {
                "index_daily_bar_fact": len(self.index_daily_bar_rows),
                "board_daily_bar_fact": len(self.board_daily_bar_rows),
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


def run_daily_bar_ingestion_dry_run(
    source: DailyBarRawSource,
    *,
    indexes: Sequence[IndexDailySymbol],
    boards: Sequence[BoardDailySymbol],
    start_date: str,
    end_date: str,
    expected_trade_dates: Sequence[str] | None = None,
    version: str = "v1",
) -> DailyBarIngestionDryRun:
    require_yyyymmdd(start_date, "start_date")
    require_yyyymmdd(end_date, "end_date")
    if start_date > end_date:
        raise IngestionValidationError("start_date must be <= end_date")
    if not indexes:
        raise IngestionValidationError("at least one index symbol is required")
    if not boards:
        raise IngestionValidationError("at least one board symbol is required")

    normalized_expected_trade_dates = tuple(
        require_yyyymmdd(trade_date, "expected_trade_date")
        for trade_date in (expected_trade_dates or (end_date,))
    )
    period = f"{start_date}_{end_date}"
    batches = {
        "index_daily_bar_fact": make_source_batch_id("index_daily", period, version),
        "board_daily_bar_fact": make_source_batch_id("board_daily", period, version),
    }

    raw_index_rows = list(source.fetch_index_daily_bars(indexes=indexes, start_date=start_date, end_date=end_date))
    raw_board_rows = list(source.fetch_board_daily_bars(boards=boards, start_date=start_date, end_date=end_date))

    index_daily_bar_rows = [
        normalize_index_daily_bar_row(
            row,
            source="mootdx.index",
            source_batch_id=batches["index_daily_bar_fact"],
            source_version=batches["index_daily_bar_fact"],
        )
        for row in raw_index_rows
    ]
    board_daily_bar_rows = [
        normalize_board_daily_bar_row(
            row,
            source="mootdx.index",
            source_batch_id=batches["board_daily_bar_fact"],
            source_version=batches["board_daily_bar_fact"],
        )
        for row in raw_board_rows
    ]

    quality_gates = [
        gate_non_empty("index_daily_bar_non_empty", index_daily_bar_rows),
        gate_non_empty("board_daily_bar_non_empty", board_daily_bar_rows),
        gate_required_identity_keys(index_daily_bar_rows, ("index_identity_key",), "index_daily_identity_key_coverage"),
        gate_required_identity_keys(board_daily_bar_rows, ("board_identity_key",), "board_daily_identity_key_coverage"),
        gate_unique_daily_key(index_daily_bar_rows, ("index_identity_key", "trade_date"), "index_daily_unique_key"),
        gate_unique_daily_key(board_daily_bar_rows, ("board_identity_key", "trade_date"), "board_daily_unique_key"),
        gate_rows_within_range(index_daily_bar_rows, start_date=start_date, end_date=end_date, gate_name="index_daily_range"),
        gate_rows_within_range(board_daily_bar_rows, start_date=start_date, end_date=end_date, gate_name="board_daily_range"),
        gate_index_board_physical_split(index_daily_bar_rows, board_daily_bar_rows),
        gate_no_88xxxx_index_rows(index_daily_bar_rows),
        gate_board_codes_are_88xxxx(board_daily_bar_rows),
        gate_missing_daily_rows(
            index_daily_bar_rows,
            requested_keys=[symbol.index_identity_key for symbol in indexes],
            expected_trade_dates=normalized_expected_trade_dates,
            identity_key_field="index_identity_key",
            gate_name="index_official_daily_missing",
        ),
        gate_missing_daily_rows(
            board_daily_bar_rows,
            requested_keys=[symbol.board_identity_key for symbol in boards],
            expected_trade_dates=normalized_expected_trade_dates,
            identity_key_field="board_identity_key",
            gate_name="board_official_daily_missing",
        ),
    ]

    return DailyBarIngestionDryRun(
        start_date=start_date,
        end_date=end_date,
        expected_trade_dates=normalized_expected_trade_dates,
        source_version=version,
        batches=batches,
        raw_hashes={
            "index_daily_bar_fact": stable_raw_hash(raw_index_rows),
            "board_daily_bar_fact": stable_raw_hash(raw_board_rows),
        },
        index_daily_bar_rows=index_daily_bar_rows,
        board_daily_bar_rows=board_daily_bar_rows,
        quality_gates=quality_gates,
    )


def normalize_index_daily_bar_row(
    raw: Mapping[str, Any],
    *,
    source: str,
    source_batch_id: str,
    source_version: str,
) -> dict[str, Any]:
    code = require_six_digit_code(require_text(raw, "code"), "index code")
    exchange = optional_text(raw, "exchange") or infer_index_exchange_from_code(code)
    trade_date = parse_trade_date(raw)

    return {
        "index_identity_key": make_index_identity_key(exchange, code),
        "trade_date": trade_date,
        "code": code,
        "exchange": exchange,
        "name": optional_text(raw, "name"),
        "open": require_decimal(raw, "open"),
        "high": require_decimal(raw, "high"),
        "low": require_decimal(raw, "low"),
        "close": require_decimal(raw, "close"),
        "volume": optional_decimal(raw, "vol") or optional_decimal(raw, "volume"),
        "amount": optional_decimal(raw, "amount"),
        "source": source,
        "source_batch_id": source_batch_id,
        "source_version": source_version,
        "raw_payload": dict(raw),
    }


def normalize_board_daily_bar_row(
    raw: Mapping[str, Any],
    *,
    source: str,
    source_batch_id: str,
    source_version: str,
) -> dict[str, Any]:
    board_code = require_six_digit_code(require_text(raw, "board_code"), "board code")
    if not board_code.startswith("88"):
        raise IngestionValidationError(f"board_code must be 88xxxx: {board_code!r}")
    trade_date = parse_trade_date(raw)

    return {
        "board_identity_key": make_board_identity_key("TDX", board_code),
        "trade_date": trade_date,
        "board_code": board_code,
        "board_name": optional_text(raw, "board_name"),
        "board_type": optional_text(raw, "board_type") or "tdx_other",
        "open": require_decimal(raw, "open"),
        "high": require_decimal(raw, "high"),
        "low": require_decimal(raw, "low"),
        "close": require_decimal(raw, "close"),
        "volume": optional_decimal(raw, "vol") or optional_decimal(raw, "volume"),
        "amount": optional_decimal(raw, "amount"),
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


def gate_required_identity_keys(
    rows: Sequence[Mapping[str, Any]],
    key_fields: Sequence[str],
    gate_name: str,
) -> QualityGateResult:
    missing = [
        {"row_index": idx, "field": field}
        for idx, row in enumerate(rows)
        for field in key_fields
        if not row.get(field)
    ]
    return QualityGateResult(
        gate_name=gate_name,
        status="passed" if not missing else "failed",
        expected_value="100%",
        actual_value=f"{len(rows) * len(key_fields) - len(missing)}/{len(rows) * len(key_fields)}",
        details={"key_fields": list(key_fields), "missing": missing[:50]},
    )


def gate_unique_daily_key(
    rows: Sequence[Mapping[str, Any]],
    key_fields: Sequence[str],
    gate_name: str,
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


def gate_rows_within_range(
    rows: Sequence[Mapping[str, Any]],
    *,
    start_date: str,
    end_date: str,
    gate_name: str,
) -> QualityGateResult:
    bad_rows = [
        {"row_index": idx, "trade_date": row.get("trade_date")}
        for idx, row in enumerate(rows)
        if str(row.get("trade_date") or "") < start_date or str(row.get("trade_date") or "") > end_date
    ]
    return QualityGateResult(
        gate_name=gate_name,
        status="passed" if not bad_rows else "failed",
        expected_value=f"{start_date} <= trade_date <= {end_date}",
        actual_value=str(len(bad_rows)),
        details={"bad_rows": bad_rows[:50]},
    )


def gate_index_board_physical_split(
    index_rows: Sequence[Mapping[str, Any]],
    board_rows: Sequence[Mapping[str, Any]],
) -> QualityGateResult:
    bad_index_rows = [
        idx
        for idx, row in enumerate(index_rows)
        if not str(row.get("index_identity_key") or "").startswith("index:") or row.get("board_identity_key")
    ]
    bad_board_rows = [
        idx
        for idx, row in enumerate(board_rows)
        if not str(row.get("board_identity_key") or "").startswith("board:") or row.get("index_identity_key")
    ]
    passed = not bad_index_rows and not bad_board_rows
    return QualityGateResult(
        gate_name="index_board_daily_physical_split",
        status="passed" if passed else "failed",
        expected_value="index rows only in index table; board rows only in board table",
        actual_value="0" if passed else str(len(bad_index_rows) + len(bad_board_rows)),
        details={"bad_index_rows": bad_index_rows[:50], "bad_board_rows": bad_board_rows[:50]},
    )


def gate_no_88xxxx_index_rows(rows: Sequence[Mapping[str, Any]]) -> QualityGateResult:
    bad_codes = sorted({str(row.get("code") or "") for row in rows if str(row.get("code") or "").startswith("88")})
    return QualityGateResult(
        gate_name="index_daily_88xxxx_board_violation",
        status="passed" if not bad_codes else "failed",
        expected_value="0",
        actual_value=str(len(bad_codes)),
        details={"codes": bad_codes[:50]},
    )


def gate_board_codes_are_88xxxx(rows: Sequence[Mapping[str, Any]]) -> QualityGateResult:
    bad_codes = sorted({str(row.get("board_code") or "") for row in rows if not str(row.get("board_code") or "").startswith("88")})
    return QualityGateResult(
        gate_name="board_daily_code_shape",
        status="passed" if not bad_codes else "failed",
        expected_value="all board_code starts with 88",
        actual_value=str(len(bad_codes)),
        details={"codes": bad_codes[:50]},
    )


def gate_missing_daily_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    requested_keys: Sequence[str],
    expected_trade_dates: Sequence[str],
    identity_key_field: str,
    gate_name: str,
) -> QualityGateResult:
    expected = {(identity_key, trade_date) for identity_key in requested_keys for trade_date in expected_trade_dates}
    actual = {
        (str(row.get(identity_key_field)), str(row.get("trade_date")))
        for row in rows
        if row.get(identity_key_field) and row.get("trade_date")
    }
    missing = sorted(expected - actual)
    return QualityGateResult(
        gate_name=gate_name,
        status="passed" if not missing else "failed",
        expected_value="0 missing",
        actual_value=str(len(missing)),
        details={"missing": [{"identity_key": key, "trade_date": trade_date} for key, trade_date in missing[:50]]},
    )


def parse_trade_date(raw: Mapping[str, Any]) -> str:
    value = raw.get("trade_date") or raw.get("datetime") or raw.get("date")
    if value is None or str(value).strip() == "":
        raise IngestionValidationError("trade_date/datetime/date is required")
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y%m%d")
    text = str(value).strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return require_yyyymmdd(text[:10].replace("-", ""), "trade_date")
    return require_yyyymmdd(text[:8], "trade_date")


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
