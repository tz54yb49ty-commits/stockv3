"""Deterministic sentinel-only parity for quote transports.

This module does not execute on its own and stores no rollout state.  In
particular, it cannot claim the later three-trading-day transport-switch gate.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Any

from ashare_v3.quote_transport import QuoteTransport


PARITY_SCHEMA_VERSION = "quote_transport_sentinel_parity_v1"
ROLLOUT_ELIGIBILITY_SCHEMA_VERSION = "quote_transport_rollout_eligibility_v1"
ROLLOUT_REQUIRED_OPEN_TRADE_DAYS = 3
MAX_SENTINELS_PER_ASSET_KIND = 3
SUPPORTED_SENTINEL_METHODS = frozenset({"bars", "index", "index_bars"})
SUPPORTED_SENTINEL_FREQUENCY_ALIASES = frozenset(
    {"5m", "15m", "30m", "1h", "day", "week", "mon", "1m", "3mon", "year"}
)
OHLC_FIELDS = ("open", "high", "low", "close")


class QuoteTransportParityError(RuntimeError):
    """Raised when parity scope or transport authority is invalid."""


@dataclass(frozen=True)
class SentinelRequest:
    asset_kind: str
    identity_key: str
    symbol: str
    method: str
    frequency: int | str = 9
    start: int = 0
    offset: int = 3


def deterministic_sentinel_requests(
    scopes: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    frequency: int | str = 9,
    start: int = 0,
    offset: int = 3,
) -> tuple[SentinelRequest, ...]:
    """Select first/middle/last from each ordered N1 asset scope."""

    requests: list[SentinelRequest] = []
    for asset_kind in ("stock", "index", "board"):
        rows = list(scopes.get(asset_kind, ()))
        indexes = _sentinel_indexes(len(rows))
        method = "bars" if asset_kind == "stock" else "index"
        for index in indexes:
            row = rows[index]
            symbol = str(row.get("code") or row.get("board_code") or "").strip()
            identity_key = str(row.get("identity_key") or "").strip()
            if not symbol or not identity_key:
                raise QuoteTransportParityError(
                    f"{asset_kind} sentinel requires identity_key and code"
                )
            requests.append(
                SentinelRequest(
                    asset_kind=asset_kind,
                    identity_key=identity_key,
                    symbol=symbol,
                    method=method,
                    frequency=frequency,
                    start=start,
                    offset=offset,
                )
            )
    return tuple(requests)


def compare_sentinel_parity(
    *,
    trade_date: str,
    requests: Sequence[SentinelRequest],
    baseline: QuoteTransport,
    candidate: QuoteTransport,
) -> dict[str, Any]:
    """Double-read deterministic sentinels and compare normalized bar facts."""

    normalized_trade_date = _trade_date(trade_date)
    frozen_requests = tuple(requests)
    _validate_requests(frozen_requests)
    if baseline.transport_name == candidate.transport_name:
        raise QuoteTransportParityError(
            "parity requires two distinct transport names"
        )

    results: list[dict[str, Any]] = []
    for request in frozen_requests:
        left = _fetch_and_normalize(
            transport=baseline,
            request=request,
            expected_trade_date=normalized_trade_date,
        )
        right = _fetch_and_normalize(
            transport=candidate,
            request=request,
            expected_trade_date=normalized_trade_date,
        )
        mismatches: list[str] = []
        if not left["non_empty"] or not right["non_empty"]:
            mismatches.append("non_empty")
        expected_identity = [request.identity_key]
        if (
            left["identity"] != expected_identity
            or right["identity"] != expected_identity
        ):
            mismatches.append("identity")
        for field_name in ("ohlc", "dates", "row_count", "normalized_hash"):
            if left[field_name] != right[field_name]:
                mismatches.append(field_name)
        results.append(
            {
                "request": asdict(request),
                "baseline": left,
                "candidate": right,
                "mismatches": mismatches,
                "passed": not mismatches,
            }
        )

    return {
        "schema_version": PARITY_SCHEMA_VERSION,
        "trade_date": normalized_trade_date,
        "scope_policy": "deterministic_first_middle_last_sentinels_only",
        "baseline_transport": baseline.transport_name,
        "candidate_transport": candidate.transport_name,
        "sentinel_count": len(frozen_requests),
        "asset_kind_counts": dict(
            sorted(Counter(request.asset_kind for request in frozen_requests).items())
        ),
        "results": results,
        "passed": bool(results) and all(result["passed"] for result in results),
        "consecutive_trading_days_proven": 0,
        "runtime_switch_eligible": False,
    }


def evaluate_quote_transport_rollout_eligibility(
    *,
    daily_reports: Sequence[Mapping[str, Any]],
    ordered_open_trade_dates: Sequence[str],
) -> dict[str, Any]:
    """Evaluate the frozen three-open-day parity gate without side effects."""

    blocking_reasons: list[str] = []
    normalized_open_dates: list[str] = []
    for value in ordered_open_trade_dates:
        try:
            normalized_open_dates.append(_trade_date(value))
        except QuoteTransportParityError:
            blocking_reasons.append("invalid_ordered_open_trade_date")

    if len(set(normalized_open_dates)) != len(normalized_open_dates):
        blocking_reasons.append("duplicate_ordered_open_trade_date")
    if normalized_open_dates != sorted(normalized_open_dates):
        blocking_reasons.append("ordered_open_trade_dates_out_of_order")

    open_dates_are_valid = not blocking_reasons
    used_trade_dates = (
        normalized_open_dates[-ROLLOUT_REQUIRED_OPEN_TRADE_DAYS:]
        if open_dates_are_valid
        else []
    )
    if len(used_trade_dates) < ROLLOUT_REQUIRED_OPEN_TRADE_DAYS:
        blocking_reasons.append("insufficient_ordered_open_trade_dates")

    open_date_set = set(normalized_open_dates)
    daily_status_by_date: dict[str, bool] = {}
    report_dates: list[str] = []
    previous_report_date = ""
    for report in daily_reports:
        if not isinstance(report, Mapping):
            blocking_reasons.append("invalid_daily_report")
            continue
        try:
            report_date = _trade_date(report.get("trade_date"))
        except QuoteTransportParityError:
            blocking_reasons.append("invalid_report_trade_date")
            continue

        report_dates.append(report_date)
        if report_date in daily_status_by_date:
            blocking_reasons.append("duplicate_report_trade_date")
        if previous_report_date and report_date < previous_report_date:
            blocking_reasons.append("daily_reports_out_of_order")
        previous_report_date = report_date
        if report_date not in open_date_set:
            blocking_reasons.append("report_trade_date_not_open")
        if report.get("schema_version") != PARITY_SCHEMA_VERSION:
            blocking_reasons.append("schema_version_mismatch")
        if (
            report.get("baseline_transport") != "mootdx"
            or report.get("candidate_transport") != "tdxpy"
        ):
            blocking_reasons.append("transport_authority_mismatch")

        contract_reasons = (
            _frozen_daily_report_contract_reasons(report, report_date)
            if report_date in used_trade_dates
            else []
        )
        blocking_reasons.extend(contract_reasons)
        sentinel_count = report.get("sentinel_count")
        daily_status_by_date[report_date] = (
            not contract_reasons
            and report.get("passed") is True
            and isinstance(sentinel_count, int)
            and not isinstance(sentinel_count, bool)
            and sentinel_count > 0
        )

    missing_trade_dates = [
        trade_date
        for trade_date in used_trade_dates
        if trade_date not in daily_status_by_date
    ]
    failed_trade_dates = [
        trade_date
        for trade_date in used_trade_dates
        if daily_status_by_date.get(trade_date) is False
    ]
    if missing_trade_dates:
        blocking_reasons.append("missing_recent_open_trade_date")
    if failed_trade_dates:
        blocking_reasons.append("recent_open_trade_date_failed")

    structural_failure = any(
        reason
        not in {
            "insufficient_ordered_open_trade_dates",
            "missing_recent_open_trade_date",
            "recent_open_trade_date_failed",
        }
        for reason in blocking_reasons
    )
    consecutive_days = 0
    if not structural_failure:
        for trade_date in reversed(used_trade_dates):
            if daily_status_by_date.get(trade_date) is not True:
                break
            consecutive_days += 1

    earlier_dates = set(normalized_open_dates[:-ROLLOUT_REQUIRED_OPEN_TRADE_DAYS])
    earlier_failed_trade_dates = sorted(
        {
            trade_date
            for trade_date in report_dates
            if trade_date in earlier_dates
            and daily_status_by_date.get(trade_date) is False
        }
    )
    audit_reasons = (
        ["earlier_failed_trade_dates_ignored"]
        if earlier_failed_trade_dates
        else []
    )
    reasons = list(dict.fromkeys(blocking_reasons))
    eligible = (
        not reasons
        and consecutive_days == ROLLOUT_REQUIRED_OPEN_TRADE_DAYS
    )
    if eligible:
        reasons.append("recent_three_open_trade_dates_passed")

    return {
        "schema_version": ROLLOUT_ELIGIBILITY_SCHEMA_VERSION,
        "baseline_transport": "mootdx",
        "candidate_transport": "tdxpy",
        "required_consecutive_trading_days": ROLLOUT_REQUIRED_OPEN_TRADE_DAYS,
        "used_trade_dates": list(used_trade_dates),
        "consecutive_trading_days_proven": consecutive_days,
        "runtime_switch_eligible": eligible,
        "reasons": reasons,
        "audit_reasons": audit_reasons,
        "missing_trade_dates": missing_trade_dates,
        "failed_trade_dates": failed_trade_dates,
        "earlier_failed_trade_dates": earlier_failed_trade_dates,
    }


def _frozen_daily_report_contract_reasons(
    report: Mapping[str, Any],
    report_trade_date: str,
) -> list[str]:
    reasons: list[str] = []
    if report.get("scope_policy") != "deterministic_first_middle_last_sentinels_only":
        reasons.append("scope_policy_mismatch")

    results = report.get("results")
    if not _is_non_string_sequence(results) or not results:
        return [*reasons, "results_missing_or_invalid"]

    sentinel_count = report.get("sentinel_count")
    valid_sentinel_count = (
        isinstance(sentinel_count, int)
        and not isinstance(sentinel_count, bool)
        and sentinel_count > 0
    )
    if not valid_sentinel_count:
        reasons.append("sentinel_count_invalid")
    elif len(results) != sentinel_count:
        reasons.append("sentinel_count_mismatch")

    asset_kind_counts = report.get("asset_kind_counts")
    valid_counts = isinstance(asset_kind_counts, Mapping) and bool(asset_kind_counts)
    if valid_counts:
        for asset_kind, count in asset_kind_counts.items():
            if (
                asset_kind not in {"stock", "index", "board"}
                or not isinstance(count, int)
                or isinstance(count, bool)
                or count <= 0
                or count > MAX_SENTINELS_PER_ASSET_KIND
            ):
                valid_counts = False
                break
    if not valid_counts:
        reasons.append("asset_kind_counts_invalid")
    elif (
        not valid_sentinel_count
        or sum(asset_kind_counts.values()) != sentinel_count
    ):
        reasons.append("asset_kind_counts_total_mismatch")

    requests: list[SentinelRequest] = []
    child_passed: list[bool] = []
    request_keys: set[tuple[str, str, str]] = set()
    result_kind_counts: Counter[str] = Counter()
    for result in results:
        if not isinstance(result, Mapping):
            reasons.append("result_invalid")
            continue
        passed = result.get("passed")
        child_passed.append(passed is True)
        if passed is not True:
            reasons.append("child_result_failed")
        mismatches = result.get("mismatches")
        if not _is_non_string_sequence(mismatches) or mismatches:
            reasons.append("child_mismatches_not_empty")

        request = result.get("request")
        if not isinstance(request, Mapping):
            reasons.append("sentinel_request_invalid")
            continue
        try:
            sentinel_request = _frozen_sentinel_request(request)
        except QuoteTransportParityError:
            reasons.append("sentinel_request_contract_invalid")
            continue
        requests.append(sentinel_request)
        result_kind_counts[sentinel_request.asset_kind] += 1
        request_key = (
            sentinel_request.asset_kind,
            sentinel_request.identity_key,
            sentinel_request.method,
        )
        if request_key in request_keys:
            reasons.append("duplicate_sentinel")
        request_keys.add(request_key)

        normalized_sides: dict[str, Mapping[str, Any]] = {}
        for side_name in ("baseline", "candidate"):
            normalized = result.get(side_name)
            if not isinstance(normalized, Mapping):
                reasons.append(f"{side_name}_normalized_invalid")
                continue
            required_fields = {
                "non_empty",
                "identity",
                "ohlc",
                "dates",
                "row_count",
                "normalized_hash",
            }
            if not required_fields.issubset(normalized):
                reasons.append(f"{side_name}_normalized_fields_missing")
                continue
            normalized_sides[side_name] = normalized
            row_count = normalized.get("row_count")
            valid_row_count = (
                isinstance(row_count, int)
                and not isinstance(row_count, bool)
                and row_count > 0
            )
            if normalized.get("non_empty") is not True or not valid_row_count:
                reasons.append(f"{side_name}_normalized_empty")
            if normalized.get("identity") != [sentinel_request.identity_key]:
                reasons.append(f"{side_name}_identity_mismatch")
            dates = normalized.get("dates")
            valid_dates = not (
                not _is_non_string_sequence(dates)
                or not valid_row_count
                or len(dates) != row_count
                or any(_safe_trade_date(value) != report_trade_date for value in dates)
            )
            if not valid_dates:
                reasons.append(f"{side_name}_dates_mismatch")
            ohlc = normalized.get("ohlc")
            valid_ohlc_shape = not (
                not _is_non_string_sequence(ohlc)
                or not valid_row_count
                or len(ohlc) != row_count
            )
            if not valid_ohlc_shape:
                reasons.append(f"{side_name}_ohlc_mismatch")
            normalized_hash = normalized.get("normalized_hash")
            valid_hash_format = (
                isinstance(normalized_hash, str)
                and len(normalized_hash) == 64
                and all(character in "0123456789abcdef" for character in normalized_hash)
            )
            if not valid_hash_format:
                reasons.append(f"{side_name}_normalized_hash_invalid")
            if valid_dates and valid_ohlc_shape:
                try:
                    recomputed_hash = _canonical_normalized_hash(
                        identity_key=sentinel_request.identity_key,
                        dates=dates,
                        ohlc=ohlc,
                    )
                except QuoteTransportParityError:
                    reasons.append(f"{side_name}_ohlc_invalid")
                else:
                    if valid_hash_format and normalized_hash != recomputed_hash:
                        reasons.append(f"{side_name}_normalized_hash_mismatch")
        if len(normalized_sides) == 2 and any(
            normalized_sides["baseline"].get(field_name)
            != normalized_sides["candidate"].get(field_name)
            for field_name in ("ohlc", "dates", "row_count", "normalized_hash")
        ):
            reasons.append("normalized_parity_mismatch")

    try:
        _validate_requests(requests)
    except QuoteTransportParityError:
        reasons.append("sentinel_request_contract_invalid")
    if valid_counts and dict(result_kind_counts) != dict(asset_kind_counts):
        reasons.append("asset_kind_counts_result_mismatch")
    if report.get("passed") is not all(child_passed):
        reasons.append("top_level_passed_mismatch")
    return list(dict.fromkeys(reasons))


def _frozen_sentinel_request(request: Mapping[str, Any]) -> SentinelRequest:
    required_fields = {
        "asset_kind",
        "identity_key",
        "symbol",
        "method",
        "frequency",
        "start",
        "offset",
    }
    if not required_fields.issubset(request):
        raise QuoteTransportParityError("sentinel request fields are incomplete")
    string_fields = {
        field_name: request.get(field_name)
        for field_name in ("asset_kind", "identity_key", "symbol", "method")
    }
    if any(
        not isinstance(value, str)
        or not value
        or value != value.strip()
        for value in string_fields.values()
    ):
        raise QuoteTransportParityError("sentinel request string fields are invalid")
    asset_kind = string_fields["asset_kind"]
    identity_key = string_fields["identity_key"]
    symbol = string_fields["symbol"]
    method = string_fields["method"]
    if len(symbol) != 6 or not symbol.isdigit():
        raise QuoteTransportParityError("sentinel symbol must be six digits")
    if identity_key != _identity_key(asset_kind, symbol):
        raise QuoteTransportParityError("sentinel identity_key does not match symbol")

    frequency = request.get("frequency")
    valid_frequency = (
        isinstance(frequency, int)
        and not isinstance(frequency, bool)
        and frequency in range(12)
    ) or (
        isinstance(frequency, str)
        and frequency in SUPPORTED_SENTINEL_FREQUENCY_ALIASES
    )
    start = request.get("start")
    offset = request.get("offset")
    if not valid_frequency:
        raise QuoteTransportParityError("sentinel frequency is invalid")
    if not isinstance(start, int) or isinstance(start, bool) or start < 0:
        raise QuoteTransportParityError("sentinel start is invalid")
    if (
        not isinstance(offset, int)
        or isinstance(offset, bool)
        or offset <= 0
        or offset > 800
    ):
        raise QuoteTransportParityError("sentinel offset is invalid")
    return SentinelRequest(
        asset_kind=asset_kind,
        identity_key=identity_key,
        symbol=symbol,
        method=method,
        frequency=frequency,
        start=start,
        offset=offset,
    )


def _canonical_normalized_hash(
    *,
    identity_key: str,
    dates: Sequence[Any],
    ohlc: Sequence[Any],
) -> str:
    canonical_rows: list[dict[str, Any]] = []
    for trade_date, values in zip(dates, ohlc):
        if not isinstance(values, Mapping) or set(values) != set(OHLC_FIELDS):
            raise QuoteTransportParityError("normalized OHLC row is invalid")
        canonical_rows.append(
            {
                "identity_key": identity_key,
                "trade_date": _trade_date(trade_date),
                **{
                    field_name: _decimal_text(values.get(field_name))
                    for field_name in OHLC_FIELDS
                },
            }
        )
    canonical_rows.sort(
        key=lambda row: (
            row["trade_date"],
            row["identity_key"],
            *(row[field_name] for field_name in OHLC_FIELDS),
        )
    )
    encoded = json.dumps(
        canonical_rows,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _is_non_string_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _safe_trade_date(value: Any) -> str:
    try:
        return _trade_date(value)
    except QuoteTransportParityError:
        return ""


def _fetch_and_normalize(
    *,
    transport: QuoteTransport,
    request: SentinelRequest,
    expected_trade_date: str,
) -> dict[str, Any]:
    method = getattr(transport, request.method, None)
    if not callable(method):
        raise QuoteTransportParityError(
            f"{transport.transport_name} does not support {request.method}"
        )
    try:
        raw = method(
            symbol=request.symbol,
            frequency=request.frequency,
            start=request.start,
            offset=request.offset,
        )
    except Exception as exc:
        raise QuoteTransportParityError(
            f"{transport.transport_name} sentinel call failed for "
            f"{request.identity_key}: {type(exc).__name__}"
        ) from exc
    rows = _records(raw)
    canonical_rows: list[dict[str, Any]] = []
    for row in rows:
        row_date = _row_trade_date(row)
        if row_date != expected_trade_date:
            continue
        code = str(row.get("code") or row.get("symbol") or "").strip()
        canonical_rows.append(
            {
                "identity_key": (
                    _identity_key(request.asset_kind, code)
                    if code
                    else ""
                ),
                "trade_date": row_date,
                **{
                    field_name: _decimal_text(row.get(field_name))
                    for field_name in OHLC_FIELDS
                },
            }
        )
    canonical_rows.sort(
        key=lambda row: (
            row["trade_date"],
            row["identity_key"],
            *(row[field_name] for field_name in OHLC_FIELDS),
        )
    )
    identities = sorted({row["identity_key"] for row in canonical_rows})
    ohlc = [
        {field_name: row[field_name] for field_name in OHLC_FIELDS}
        for row in canonical_rows
    ]
    dates = [row["trade_date"] for row in canonical_rows]
    encoded = json.dumps(
        canonical_rows,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "non_empty": bool(canonical_rows),
        "identity": identities,
        "ohlc": ohlc,
        "dates": dates,
        "row_count": len(canonical_rows),
        "normalized_hash": hashlib.sha256(encoded).hexdigest(),
    }


def _validate_requests(requests: Sequence[SentinelRequest]) -> None:
    if not requests:
        raise QuoteTransportParityError("sentinel parity scope must not be empty")
    counts = Counter(request.asset_kind for request in requests)
    unsupported_kinds = sorted(set(counts) - {"stock", "index", "board"})
    if unsupported_kinds:
        raise QuoteTransportParityError(
            f"unsupported sentinel asset_kind: {unsupported_kinds}"
        )
    if any(count > MAX_SENTINELS_PER_ASSET_KIND for count in counts.values()):
        raise QuoteTransportParityError(
            "sentinel-only parity rejects more than three objects per asset kind"
        )
    for request in requests:
        if request.method not in SUPPORTED_SENTINEL_METHODS:
            raise QuoteTransportParityError(
                f"unsupported sentinel method: {request.method}"
            )
        if request.asset_kind == "stock" and request.method != "bars":
            raise QuoteTransportParityError("stock sentinel must use bars")
        if request.asset_kind in {"index", "board"} and request.method not in {
            "index",
            "index_bars",
        }:
            raise QuoteTransportParityError(
                f"{request.asset_kind} sentinel must use index/index_bars"
            )


def _sentinel_indexes(size: int) -> tuple[int, ...]:
    if size <= 0:
        return ()
    return tuple(dict.fromkeys((0, size // 2, size - 1)))


def _records(raw: Any) -> list[dict[str, Any]]:
    if raw is None or raw is False:
        return []
    if hasattr(raw, "to_dict"):
        try:
            values = raw.to_dict(orient="records")
        except TypeError:
            values = raw.to_dict("records")
    elif isinstance(raw, Mapping):
        values = [raw]
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        values = raw
    else:
        raise QuoteTransportParityError(
            f"unsupported sentinel response type: {type(raw).__name__}"
        )
    return [dict(value) for value in values]


def _trade_date(value: Any) -> str:
    normalized = "".join(character for character in str(value or "") if character.isdigit())
    if len(normalized) != 8:
        raise QuoteTransportParityError("trade_date must normalize to YYYYMMDD")
    return normalized


def _row_trade_date(row: Mapping[str, Any]) -> str:
    for field_name in ("trade_date", "datetime", "date"):
        value = row.get(field_name)
        if isinstance(value, datetime):
            return value.strftime("%Y%m%d")
        if isinstance(value, date):
            return value.strftime("%Y%m%d")
        text = str(value or "").strip()
        normalized = "".join(character for character in text[:10] if character.isdigit())
        if len(normalized) == 8:
            return normalized
    return ""


def _identity_key(asset_kind: str, code: str) -> str:
    normalized = str(code or "").strip()
    if asset_kind == "stock":
        if normalized.startswith(("4", "8", "920")):
            exchange = "BJ"
        else:
            exchange = "SH" if normalized.startswith(("5", "6", "7", "9")) else "SZ"
        return f"stock:{exchange}:{normalized}"
    if asset_kind == "index":
        if normalized.startswith("899"):
            exchange = "BJ"
        else:
            exchange = "SH" if normalized.startswith(("00", "88", "99")) else "SZ"
        return f"index:{exchange}:{normalized}"
    return f"board:TDX:{normalized}"


def _decimal_text(value: Any) -> str:
    try:
        normalized = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise QuoteTransportParityError(f"OHLC value is invalid: {value!r}") from exc
    return format(normalized.normalize(), "f")
