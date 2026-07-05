"""Common helpers for raw ingestion batches and quality gates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import re
from typing import Any, Iterable, Mapping


DATE_RE = re.compile(r"^[0-9]{8}$")
SIX_DIGIT_CODE_RE = re.compile(r"^[0-9]{6}$")
STOCK_CODE_RE = SIX_DIGIT_CODE_RE


class IngestionValidationError(ValueError):
    """Raised when raw ingestion input cannot be standardized safely."""


@dataclass(frozen=True)
class BatchSpec:
    batch_id: str
    trade_date: str
    data_domain: str
    data_type: str
    source: str
    source_version: str
    source_path: str | None = None
    source_params: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class QualityGateResult:
    gate_name: str
    status: str
    severity: str = "P0"
    expected_value: str | None = None
    actual_value: str | None = None
    details: Mapping[str, Any] | None = None

    @property
    def passed(self) -> bool:
        return self.status == "passed"


def require_yyyymmdd(value: str, field_name: str = "date") -> str:
    if not DATE_RE.match(value):
        raise IngestionValidationError(f"{field_name} must be YYYYMMDD: {value!r}")
    return value


def normalize_exchange_from_ts_code(ts_code: str) -> tuple[str, str]:
    try:
        code, suffix = ts_code.split(".", 1)
    except ValueError as exc:
        raise IngestionValidationError(f"invalid ts_code: {ts_code!r}") from exc

    exchange_map = {"SH": "SH", "SZ": "SZ", "BJ": "BJ"}
    exchange = exchange_map.get(suffix.upper())
    if exchange is None:
        raise IngestionValidationError(f"unsupported stock exchange suffix: {ts_code!r}")
    require_stock_code(code)
    return exchange, code


def normalize_index_exchange_from_ts_code(ts_code: str) -> tuple[str, str]:
    try:
        code, suffix = ts_code.split(".", 1)
    except ValueError as exc:
        raise IngestionValidationError(f"invalid index ts_code: {ts_code!r}") from exc

    suffix_map = {
        "SH": "SH",
        "SZ": "SZ",
        "BJ": "BJ",
        "CSI": "CSI",
        "CNI": "CNI",
        "SW": "SW",
        "SI": "SW",
        "TDX": "TDX",
        "OTH": "OTH",
    }
    exchange = suffix_map.get(suffix.upper(), "UNKNOWN")
    require_six_digit_code(code, "index code")
    return exchange, code


def require_stock_code(code: str) -> str:
    require_six_digit_code(code, "stock code")
    if code.startswith("88"):
        raise IngestionValidationError(f"stock code must not be a TDX board code: {code!r}")
    return code


def require_six_digit_code(code: str, field_name: str = "code") -> str:
    if not SIX_DIGIT_CODE_RE.match(code):
        raise IngestionValidationError(f"{field_name} must be 6 digits: {code!r}")
    return code


def make_stock_identity_key(exchange: str, code: str) -> str:
    require_stock_code(code)
    return f"stock:{exchange}:{code}"


def infer_stock_exchange_from_code(code: str) -> str:
    require_stock_code(code)
    if code.startswith("6"):
        return "SH"
    if code.startswith(("0", "2", "3")):
        return "SZ"
    if code.startswith(("4", "8", "92")):
        return "BJ"
    if code.startswith("9"):
        return "SH"
    raise IngestionValidationError(f"cannot infer stock exchange from code: {code!r}")


def make_stock_identity_key_from_code(code: str) -> str:
    return make_stock_identity_key(infer_stock_exchange_from_code(code), code)


def infer_index_exchange_from_code(code: str) -> str:
    require_six_digit_code(code, "index code")
    if code.startswith("399"):
        return "SZ"
    if code.startswith("000"):
        return "SH"
    if code.startswith("88"):
        return "TDX"
    return "UNKNOWN"


def make_index_identity_key(exchange: str, code: str) -> str:
    require_six_digit_code(code, "index code")
    return f"index:{exchange}:{code}"


def make_index_identity_key_from_code(code: str) -> str:
    return make_index_identity_key(infer_index_exchange_from_code(code), code)


def make_board_identity_key(source_namespace: str, board_code: str) -> str:
    require_six_digit_code(board_code, "board code")
    return f"board:{source_namespace.upper()}:{board_code}"


def make_source_batch_id(data_type: str, date_or_period: str, version: str = "v1") -> str:
    if not data_type:
        raise IngestionValidationError("data_type is required")
    if not date_or_period:
        raise IngestionValidationError("date_or_period is required")
    if not version.startswith("v"):
        raise IngestionValidationError(f"version must look like vN: {version!r}")
    return f"{data_type}_{date_or_period}_{version}"


def stable_raw_hash(rows: Iterable[Mapping[str, Any]]) -> str:
    payload = json.dumps(list(rows), ensure_ascii=False, sort_keys=True, default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
