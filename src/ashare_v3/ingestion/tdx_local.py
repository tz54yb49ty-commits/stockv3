"""Local TDX txt parsing and standardization for v3 raw ingestion."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from ashare_v3.ingestion.common import (
    IngestionValidationError,
    QualityGateResult,
    make_board_identity_key,
    make_index_identity_key_from_code,
    make_source_batch_id,
    make_stock_identity_key_from_code,
    require_six_digit_code,
    require_yyyymmdd,
    stable_raw_hash,
)


TDX_SOURCE = "tdx.local_txt"
TDX_ENCODING = "gbk"
INDEX_MEMBERSHIP_FILE = "指数板块.txt"
BOARD_FILE_TYPES = {
    "地区板块.txt": "tdx_region",
    "概念板块.txt": "tdx_concept",
    "行业板块.txt": "tdx_industry",
}


class TDXLocalSource(Protocol):
    def fetch_board_membership_rows(self) -> Sequence[Mapping[str, Any]]:
        """Return raw rows from board-class local TDX txt files."""

    def fetch_index_membership_rows(self) -> Sequence[Mapping[str, Any]]:
        """Return raw rows from local TDX index membership txt file."""


class TDXLocalSourceError(IngestionValidationError):
    """Raised when local TDX source files cannot be parsed safely."""


class TDXLocalTxtSource:
    """Read local TDX membership txt files.

    Reading happens on every fetch call so the dry-run reflects current local
    txt contents instead of a derived cache.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def fetch_board_membership_rows(self) -> Sequence[Mapping[str, Any]]:
        rows: list[dict[str, Any]] = []
        for file_name, board_type in BOARD_FILE_TYPES.items():
            rows.extend(_read_tdx_txt_rows(self.root / file_name, kind="board", board_type=board_type))
        return rows

    def fetch_index_membership_rows(self) -> Sequence[Mapping[str, Any]]:
        return _read_tdx_txt_rows(self.root / INDEX_MEMBERSHIP_FILE, kind="index", board_type=None)


@dataclass(frozen=True)
class TDXLocalIngestionDryRun:
    trade_date: str
    source_version: str
    batches: dict[str, str]
    raw_hashes: dict[str, str]
    board_identity_rows: list[dict[str, Any]]
    board_membership_rows: list[dict[str, Any]]
    index_membership_rows: list[dict[str, Any]]
    quality_gates: list[QualityGateResult]

    @property
    def passed(self) -> bool:
        return all(gate.passed for gate in self.quality_gates)

    def summary(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "source_version": self.source_version,
            "batches": self.batches,
            "raw_hashes": self.raw_hashes,
            "row_counts": {
                "board_identity": len(self.board_identity_rows),
                "board_membership_fact": len(self.board_membership_rows),
                "index_membership_fact": len(self.index_membership_rows),
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


def run_tdx_local_ingestion_dry_run(
    source: TDXLocalSource,
    *,
    trade_date: str,
    version: str = "v1",
) -> TDXLocalIngestionDryRun:
    require_yyyymmdd(trade_date, "trade_date")
    batches = {
        "board_identity": make_source_batch_id("board_identity", trade_date, version),
        "board_membership_fact": make_source_batch_id("board_membership", trade_date, version),
        "index_membership_fact": make_source_batch_id("index_membership", trade_date, version),
    }

    raw_board_rows = list(source.fetch_board_membership_rows())
    raw_index_rows = list(source.fetch_index_membership_rows())

    board_identity_rows = build_board_identity_rows(
        raw_board_rows,
        source_batch_id=batches["board_identity"],
        source_version=batches["board_identity"],
    )
    board_membership_rows = [
        normalize_board_membership_row(
            row,
            trade_date=trade_date,
            source_batch_id=batches["board_membership_fact"],
            source_version=batches["board_membership_fact"],
        )
        for row in raw_board_rows
    ]
    index_membership_rows = [
        normalize_index_membership_row(
            row,
            trade_date=trade_date,
            source_batch_id=batches["index_membership_fact"],
            source_version=batches["index_membership_fact"],
        )
        for row in raw_index_rows
    ]

    quality_gates = [
        gate_non_empty("board_identity_non_empty", board_identity_rows),
        gate_non_empty("board_membership_non_empty", board_membership_rows),
        gate_non_empty("index_membership_non_empty", index_membership_rows),
        gate_required_identity_keys(board_identity_rows, ("board_identity_key",)),
        gate_required_identity_keys(board_membership_rows, ("board_identity_key", "stock_identity_key")),
        gate_required_identity_keys(index_membership_rows, ("index_identity_key", "stock_identity_key")),
        gate_board_identity_conflicts(raw_board_rows),
        gate_no_stock_board_codes(board_membership_rows, "board_membership_fact"),
        gate_no_stock_board_codes(index_membership_rows, "index_membership_fact"),
        gate_tdx_file_split(raw_board_rows, raw_index_rows),
        gate_unique_membership(board_membership_rows, ("trade_date", "board_identity_key", "stock_identity_key")),
        gate_unique_membership(index_membership_rows, ("trade_date", "index_identity_key", "stock_identity_key")),
    ]

    return TDXLocalIngestionDryRun(
        trade_date=trade_date,
        source_version=version,
        batches=batches,
        raw_hashes={
            "board_membership_raw": stable_raw_hash(raw_board_rows),
            "index_membership_raw": stable_raw_hash(raw_index_rows),
        },
        board_identity_rows=board_identity_rows,
        board_membership_rows=board_membership_rows,
        index_membership_rows=index_membership_rows,
        quality_gates=quality_gates,
    )


def normalize_board_identity_row(
    raw: Mapping[str, Any],
    *,
    source_batch_id: str,
    source_version: str,
) -> dict[str, Any]:
    board_code = _require_text(raw, "board_code")
    board_name = _require_text(raw, "board_name")
    board_type = _require_text(raw, "board_type")
    require_six_digit_code(board_code, "board code")
    if board_type not in set(BOARD_FILE_TYPES.values()) | {"tdx_other"}:
        raise TDXLocalSourceError(f"unsupported board_type: {board_type!r}")

    return {
        "board_identity_key": make_board_identity_key("TDX", board_code),
        "board_code": board_code,
        "board_name": board_name,
        "board_type": board_type,
        "source_namespace": "TDX",
        "source_file": _require_text(raw, "source_file"),
        "status": "active",
        "source": TDX_SOURCE,
        "source_batch_id": source_batch_id,
        "source_version": source_version,
        "raw_payload": dict(raw),
    }


def build_board_identity_rows(
    raw_rows: Sequence[Mapping[str, Any]],
    *,
    source_batch_id: str,
    source_version: str,
) -> list[dict[str, Any]]:
    rows_by_code: dict[str, dict[str, Any]] = {}
    for raw in raw_rows:
        board_code = _require_text(raw, "board_code")
        if board_code not in rows_by_code:
            rows_by_code[board_code] = normalize_board_identity_row(
                raw,
                source_batch_id=source_batch_id,
                source_version=source_version,
            )
    return [rows_by_code[code] for code in sorted(rows_by_code)]


def normalize_board_membership_row(
    raw: Mapping[str, Any],
    *,
    trade_date: str,
    source_batch_id: str,
    source_version: str,
) -> dict[str, Any]:
    trade_date = require_yyyymmdd(trade_date, "trade_date")
    board_code = _require_text(raw, "board_code")
    stock_code = _require_text(raw, "stock_code")
    require_six_digit_code(board_code, "board code")

    return {
        "trade_date": trade_date,
        "board_identity_key": make_board_identity_key("TDX", board_code),
        "stock_identity_key": make_stock_identity_key_from_code(stock_code),
        "board_code": board_code,
        "board_name": _require_text(raw, "board_name"),
        "board_type": _require_text(raw, "board_type"),
        "stock_code": stock_code,
        "stock_name": _require_text(raw, "stock_name"),
        "source": TDX_SOURCE,
        "source_file": _require_text(raw, "source_file"),
        "source_batch_id": source_batch_id,
        "source_version": source_version,
        "raw_payload": dict(raw),
    }


def normalize_index_membership_row(
    raw: Mapping[str, Any],
    *,
    trade_date: str,
    source_batch_id: str,
    source_version: str,
) -> dict[str, Any]:
    trade_date = require_yyyymmdd(trade_date, "trade_date")
    index_code = _require_text(raw, "index_code")
    stock_code = _require_text(raw, "stock_code")

    return {
        "trade_date": trade_date,
        "index_identity_key": make_index_identity_key_from_code(index_code),
        "stock_identity_key": make_stock_identity_key_from_code(stock_code),
        "index_code": index_code,
        "index_name": _require_text(raw, "index_name"),
        "stock_code": stock_code,
        "stock_name": _require_text(raw, "stock_name"),
        "source": TDX_SOURCE,
        "source_file": _require_text(raw, "source_file"),
        "source_batch_id": source_batch_id,
        "source_version": source_version,
        "raw_payload": dict(raw),
    }


def gate_required_identity_keys(rows: Sequence[Mapping[str, Any]], key_fields: Sequence[str]) -> QualityGateResult:
    missing = [
        {"row_index": idx, "field": field}
        for idx, row in enumerate(rows)
        for field in key_fields
        if not row.get(field)
    ]
    return QualityGateResult(
        gate_name="identity_key_coverage",
        status="passed" if not missing else "failed",
        expected_value="100%",
        actual_value=f"{len(rows) * len(key_fields) - len(missing)}/{len(rows) * len(key_fields)}",
        details={"key_fields": list(key_fields), "missing": missing[:50]},
    )


def gate_non_empty(gate_name: str, rows: Sequence[Mapping[str, Any]]) -> QualityGateResult:
    return QualityGateResult(
        gate_name=gate_name,
        status="passed" if rows else "failed",
        expected_value=">0",
        actual_value=str(len(rows)),
        details={},
    )


def gate_board_identity_conflicts(raw_rows: Sequence[Mapping[str, Any]]) -> QualityGateResult:
    seen: dict[str, set[tuple[str, str]]] = {}
    for row in raw_rows:
        board_code = str(row.get("board_code") or "")
        seen.setdefault(board_code, set()).add((str(row.get("board_name") or ""), str(row.get("board_type") or "")))
    conflicts = {
        board_code: sorted(values)
        for board_code, values in seen.items()
        if board_code and len(values) > 1
    }
    return QualityGateResult(
        gate_name="board_identity_conflicts",
        status="passed" if not conflicts else "failed",
        expected_value="0",
        actual_value=str(len(conflicts)),
        details={"conflicts": conflicts},
    )


def gate_no_stock_board_codes(rows: Sequence[Mapping[str, Any]], data_type: str) -> QualityGateResult:
    bad_codes = sorted({str(row.get("stock_code") or "") for row in rows if str(row.get("stock_code") or "").startswith("88")})
    return QualityGateResult(
        gate_name=f"{data_type}_88xxxx_stock_violation",
        status="passed" if not bad_codes else "failed",
        expected_value="0",
        actual_value=str(len(bad_codes)),
        details={"codes": bad_codes[:50]},
    )


def gate_tdx_file_split(
    raw_board_rows: Sequence[Mapping[str, Any]],
    raw_index_rows: Sequence[Mapping[str, Any]],
) -> QualityGateResult:
    bad_board_files = sorted({row.get("source_file") for row in raw_board_rows if row.get("source_file") == INDEX_MEMBERSHIP_FILE})
    bad_index_files = sorted({row.get("source_file") for row in raw_index_rows if row.get("source_file") != INDEX_MEMBERSHIP_FILE})
    problems = {"board_rows_from_index_file": bad_board_files, "index_rows_from_non_index_file": bad_index_files}
    passed = not bad_board_files and not bad_index_files
    return QualityGateResult(
        gate_name="tdx_local_txt_physical_split",
        status="passed" if passed else "failed",
        expected_value="index txt only in index_membership; board txt only in board tables",
        actual_value="0" if passed else str(len(bad_board_files) + len(bad_index_files)),
        details=problems,
    )


def gate_unique_membership(rows: Sequence[Mapping[str, Any]], key_fields: Sequence[str]) -> QualityGateResult:
    seen: set[tuple[Any, ...]] = set()
    duplicates: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        key = tuple(row.get(field) for field in key_fields)
        if key in seen:
            duplicates.append({"row_index": idx, "key": [str(value) for value in key]})
        seen.add(key)
    return QualityGateResult(
        gate_name="membership_unique_key",
        status="passed" if not duplicates else "failed",
        expected_value="0 duplicates",
        actual_value=str(len(duplicates)),
        details={"key_fields": list(key_fields), "duplicates": duplicates[:50]},
    )


def _read_tdx_txt_rows(path: Path, *, kind: str, board_type: str | None) -> list[dict[str, Any]]:
    if not path.exists():
        raise TDXLocalSourceError(f"TDX local txt file not found: {path}")

    rows: list[dict[str, Any]] = []
    with path.open("r", encoding=TDX_ENCODING, newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        for line_number, columns in enumerate(reader, start=1):
            stripped = [column.strip() for column in columns]
            if not any(stripped):
                continue
            if len(stripped) < 4:
                raise TDXLocalSourceError(f"{path.name}:{line_number} expected 4 tab-separated columns")

            first_code, first_name, stock_code, stock_name = stripped[:4]
            raw_common = {
                "stock_code": stock_code,
                "stock_name": stock_name,
                "source_file": path.name,
                "line_number": line_number,
            }
            if kind == "board":
                if board_type is None:
                    raise TDXLocalSourceError("board_type is required for board rows")
                rows.append(
                    {
                        "board_code": first_code,
                        "board_name": first_name,
                        "board_type": board_type,
                        **raw_common,
                    }
                )
            elif kind == "index":
                rows.append(
                    {
                        "index_code": first_code,
                        "index_name": first_name,
                        **raw_common,
                    }
                )
            else:
                raise TDXLocalSourceError(f"unsupported TDX row kind: {kind!r}")
    return rows


def _require_text(raw: Mapping[str, Any], field: str) -> str:
    value = raw.get(field)
    if value is None or str(value).strip() == "":
        raise TDXLocalSourceError(f"{field} is required")
    return str(value).strip()
