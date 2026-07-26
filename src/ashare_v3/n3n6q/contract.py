from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Literal


CONTRACT_VERSION = "1.0.0"
SOURCE_ADAPTER = "mootdx.std"
SOURCE_TIME_SEMANTICS = "provider_intraday_time_without_trade_date"

Exchange = Literal["SH", "SZ", "BJ"]
BatchStatus = Literal["passed", "partial", "failed"]
QualityStatus = Literal["passed", "not_ready"]
QualityReason = Literal[
    "ok",
    "missing",
    "identity_mismatch",
    "invalid_price",
    "invalid_source_time",
    "provider_error",
    "unsupported_exchange",
]

_IDENTITY_PATTERN = re.compile(r"^stock:(SH|SZ|BJ):([0-9]{6})$")
_STOCK_CODE_PATTERN = re.compile(r"^[0-9]{6}$")


@dataclass(frozen=True, slots=True)
class QuoteIdentity:
    identity_key: str
    exchange: Exchange
    stock_code: str

    def __post_init__(self) -> None:
        match = _IDENTITY_PATTERN.fullmatch(self.identity_key)
        if (
            match is None
            or self.exchange not in {"SH", "SZ", "BJ"}
            or _STOCK_CODE_PATTERN.fullmatch(self.stock_code) is None
            or match.group(1) != self.exchange
            or match.group(2) != self.stock_code
        ):
            raise ValueError("invalid QuoteIdentity v1")


@dataclass(frozen=True, slots=True)
class QuoteItem:
    identity_key: str
    exchange: Exchange
    market: int | None
    stock_code: str
    current_price: str | None
    last_close: str | None
    day_open: str | None
    day_high: str | None
    day_low: str | None
    source_time_text: str | None
    fetched_at: str
    quality_status: QualityStatus
    quality_reason: QualityReason

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class QuoteBatch:
    contract_version: str
    batch_id: str
    source_adapter: str
    source_version: str
    source_time_semantics: str
    requested_at: str
    completed_at: str
    batch_status: BatchStatus
    item_count: int
    items: tuple[QuoteItem, ...]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["items"] = [item.to_dict() for item in self.items]
        return payload
