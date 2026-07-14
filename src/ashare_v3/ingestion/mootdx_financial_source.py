"""Mootdx Affair source adapter for authoritative stock financial reports."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import date
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import re
import stat
from typing import Any, Callable
import uuid
from zipfile import BadZipFile, ZipFile

from ashare_v3.ingestion.common import IngestionValidationError, require_yyyymmdd
from ashare_v3.ingestion.stock_financial import StockFinancialSymbol


class MootdxFinancialSourceError(IngestionValidationError):
    """Raised when Mootdx financial source configuration is invalid."""


AFFAIR_SOURCE = "mootdx_affair"
AFFAIR_PARSER_VERSION = "mootdx_affair_raw_fn_v1"
AFFAIR_FIELD_REGISTRY_VERSION = "affair_fn_registry_v1"
AFFAIR_PACKAGE_LIMIT = 10
AFFAIR_PLACEHOLDER_MAX_BYTES = 1024
AFFAIR_INVALID_NUMERIC_SENTINEL = -4.039810e34
DEFAULT_AFFAIR_CACHE_DIR = Path.home() / ".cache" / "ashare_v3" / "mootdx_affair"
AFFAIR_REMOTE_MANIFEST_FALLBACK_WARNING = (
    "affair_remote_manifest_unavailable_local_cache_used"
)
AFFAIR_FIELD_REGISTRY = {
    "revenue": "FN74",
    "operating_cost": "FN75",
    "taxes_and_surcharges": "FN76",
    "selling_expense": "FN77",
    "administrative_expense": "FN78",
    "finance_expense": "FN80",
    "operating_cashflow": "FN107",
    "total_shares": "FN238",
    "rd_expense": "FN304",
    "interest_expense": "FN305",
    "announcement_date": "FN314",
}
AFFAIR_UNIT_AUDIT_FIELDS = {
    "single_quarter_revenue_audit": "FN312",
    "single_quarter_cost_audit": "FN328",
}
_AFFAIR_PACKAGE_RE = re.compile(r"gpcw(\d{8})\.zip")


def normalize_affair_number(value: Any) -> Any:
    """Return NULL for every documented invalid Affair numeric representation."""

    if value is None or isinstance(value, bool):
        return None if value is None else value
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if text.lower() in {
            "",
            "-",
            "--",
            "n/a",
            "na",
            "none",
            "null",
            "nan",
            "inf",
            "+inf",
            "-inf",
        }:
            return None
        try:
            numeric = float(text)
        except ValueError:
            return value.strip()
    elif isinstance(value, (int, float)):
        numeric = float(value)
    else:
        return value
    if not math.isfinite(numeric):
        return None
    if abs(numeric) >= 1e30 or math.isclose(
        numeric,
        AFFAIR_INVALID_NUMERIC_SENTINEL,
        rel_tol=1e-12,
    ):
        return None
    if numeric in {
        -999,
        -9999,
        -99999,
        -999999,
        -9999999,
        -99999999,
        -999999999,
        -999999999999,
    }:
        return None
    return value


def normalize_affair_value(value: Any) -> Any:
    """Compatibility alias for the canonical Affair numeric normalizer."""

    return normalize_affair_number(value)


def normalize_affair_date(
    value: Any,
    *,
    field_name: str = "affair_date",
) -> str | None:
    """Normalize YYYYMMDD or TDX YYMMDD numeric dates without guessing invalid data."""

    value = normalize_affair_number(value)
    if value is None:
        return None
    if isinstance(value, date):
        text = value.strftime("%Y%m%d")
    else:
        text = str(value).strip()
        decimal_match = re.fullmatch(r"(\d+)\.(\d+)", text)
        if decimal_match:
            if any(character != "0" for character in decimal_match.group(2)):
                return None
            text = decimal_match.group(1)
        else:
            text = text.replace("-", "").replace("/", "")
    if 1 <= len(text) <= 6 and text.isdigit():
        short_date = text.zfill(6)
        short_year = int(short_date[:2])
        century = "20" if short_year <= 69 else "19"
        text = f"{century}{short_date}"
    if len(text) != 8 or not text.isdigit():
        return None
    try:
        date(int(text[:4]), int(text[4:6]), int(text[6:8]))
        return require_yyyymmdd(text, field_name)
    except (TypeError, ValueError, IngestionValidationError):
        return None


def affair_raw_field(record: Mapping[str, Any], fn_name: str) -> Any:
    """Read only stable FN/col fields; duplicated Chinese labels are ignored."""

    number = int(fn_name[2:])
    for key in (
        fn_name,
        fn_name.lower(),
        f"col{number}",
        f"COL{number}",
        number,
        str(number),
    ):
        if key in record:
            return normalize_affair_number(record.get(key))
    return None


def _legacy_affair_field(
    record: Mapping[str, Any],
    *names: str,
) -> Any:
    """Preserve direct helper compatibility; production never uses this path."""

    for name in names:
        if name in record:
            value = normalize_affair_number(record.get(name))
            if value is not None:
                return value
    return None


def _identity_record(value: Any) -> tuple[str, Mapping[str, Any]]:
    if isinstance(value, Mapping):
        return str(value.get("stock_identity_key") or ""), value
    return str(value or ""), {}


def _identity_map_from_expected(
    expected_identity_keys: Sequence[str],
) -> dict[str, Mapping[str, Any]]:
    identity_by_code: dict[str, Mapping[str, Any]] = {}
    for raw_key in expected_identity_keys:
        identity_key = str(raw_key or "")
        match = re.fullmatch(r"stock:(SH|SZ|BJ):(\d{6})", identity_key)
        if not match:
            raise MootdxFinancialSourceError("affair_expected_identity_key_invalid")
        code = match.group(2)
        existing = identity_by_code.get(code)
        if existing and existing.get("stock_identity_key") != identity_key:
            raise MootdxFinancialSourceError("affair_frozen_identity_code_ambiguous")
        exchange = match.group(1)
        identity_by_code[code] = {
            "stock_identity_key": identity_key,
            "ts_code": f"{code}.{exchange}",
        }
    return identity_by_code


def normalize_affair_record(
    record: Mapping[str, Any],
    *,
    source_trade_date: str,
    report_period: str | None = None,
    identity_by_code: Mapping[str, Any] | None = None,
    source_batch_id: str | None = None,
    source_version: str | None = None,
) -> dict[str, Any] | None:
    """Bind one raw Affair row to a frozen stock identity and stable FN fields."""

    legacy_direct_call = identity_by_code is None
    code_value = record.get("code")
    if code_value is None:
        code_value = record.get("col0") if "col0" in record else record.get(0)
    code = str(code_value or "").strip().split(".", 1)[0].zfill(6)
    if not re.fullmatch(r"\d{6}", code):
        return None
    identity_key, identity_metadata = _identity_record(
        (identity_by_code or {}).get(code)
    )
    if not identity_key:
        explicit_identity = str(record.get("stock_identity_key") or "")
        explicit_exchange = str(record.get("exchange") or "").upper()
        ts_code = str(record.get("ts_code") or "").upper()
        suffix = ts_code.rsplit(".", 1)[-1] if "." in ts_code else ""
        if re.fullmatch(r"stock:(?:SH|SZ|BJ):\d{6}", explicit_identity):
            identity_key = explicit_identity
        elif explicit_exchange in {"SH", "SZ", "BJ"}:
            identity_key = f"stock:{explicit_exchange}:{code}"
        elif suffix in {"SH", "SZ", "BJ"}:
            identity_key = f"stock:{suffix}:{code}"
        elif legacy_direct_call:
            # Compatibility for callers of the public normalization helper.
            # The production source always supplies the frozen identity map.
            exchange = (
                "SH"
                if code.startswith(("5", "6", "68", "9"))
                else "SZ"
            )
            identity_key = f"stock:{exchange}:{code}"
    if (
        not re.fullmatch(r"stock:(?:SH|SZ|BJ):\d{6}", identity_key)
        or identity_key.rsplit(":", 1)[-1] != code
    ):
        return None
    source_trade_date = require_yyyymmdd(
        source_trade_date,
        "source_trade_date",
    )
    normalized_report_period = normalize_affair_date(
        report_period
        or record.get("report_period")
        or record.get("end_date")
        or record.get("report_date"),
        field_name="report_period",
    )
    if not normalized_report_period:
        return None

    def raw_value(fn_name: str, *legacy_names: str) -> Any:
        value = affair_raw_field(record, fn_name)
        if value is None and legacy_direct_call:
            return _legacy_affair_field(record, *legacy_names)
        return value

    announcement_date = normalize_affair_date(
        raw_value(
            AFFAIR_FIELD_REGISTRY["announcement_date"],
            "announcement_date",
            "ann_date",
            "财报公告日期",
            "财报公告日期 ",
            "公告日期",
        ),
        field_name="announcement_date",
    )
    interest = raw_value(
        AFFAIR_FIELD_REGISTRY["interest_expense"],
        "interest_expense",
        "interest_exp",
        "利息费用",
        "其中:利息费用(利润表-财务费用)",
    )
    finance = raw_value(
        AFFAIR_FIELD_REGISTRY["finance_expense"],
        "finance_expense",
        "fin_exp",
        "财务费用",
    )
    warnings: list[str] = []
    expense_provenance = "FN305"
    if interest is None and finance is not None:
        warnings.append("interest_expense_missing_finance_expense_used")
        expense_provenance = "FN80_fallback"
    exchange = identity_key.split(":", 2)[1]
    revenue = raw_value(
        AFFAIR_FIELD_REGISTRY["revenue"],
        "operating_revenue",
        "total_revenue",
        "营业收入",
        "其中：营业收入",
        "营业总收入(万元)",
    )
    admin_expense = raw_value(
        AFFAIR_FIELD_REGISTRY["administrative_expense"],
        "admin_expense",
        "admin_exp",
        "管理费用",
    )
    raw_fn_payload = {
        fn_name: affair_raw_field(record, fn_name)
        for fn_name in sorted(
            set(AFFAIR_FIELD_REGISTRY.values())
            | set(AFFAIR_UNIT_AUDIT_FIELDS.values())
        )
    }
    return {
        "stock_identity_key": identity_key,
        "ts_code": str(
            identity_metadata.get("ts_code") or f"{code}.{exchange}"
        ),
        "code": code,
        "exchange": exchange,
        "industry": identity_metadata.get("industry")
        or identity_metadata.get("stock_industry"),
        "report_period": normalized_report_period,
        "announcement_date": announcement_date,
        "revenue": revenue,
        "operating_revenue": revenue,
        "total_revenue": revenue,
        "operating_cost": raw_value(
            AFFAIR_FIELD_REGISTRY["operating_cost"],
            "operating_cost",
            "oper_cost",
            "营业成本",
            "其中：营业成本",
        ),
        "taxes_and_surcharges": raw_value(
            AFFAIR_FIELD_REGISTRY["taxes_and_surcharges"],
            "taxes_and_surcharges",
            "营业税金及附加",
        ),
        "selling_expense": raw_value(
            AFFAIR_FIELD_REGISTRY["selling_expense"],
            "selling_expense",
            "sell_exp",
            "销售费用",
        ),
        "admin_expense": admin_expense,
        "administrative_expense": admin_expense,
        "rd_expense": raw_value(
            AFFAIR_FIELD_REGISTRY["rd_expense"],
            "rd_expense",
            "研发费用",
            "研发费用(利润表)",
        ),
        "interest_expense": interest,
        "finance_expense": finance,
        "operating_cashflow": raw_value(
            AFFAIR_FIELD_REGISTRY["operating_cashflow"],
            "operating_cashflow",
            "经营活动产生的现金流量净额",
            "经营活动产生的现金流量净额2",
        ),
        "total_shares": raw_value(
            AFFAIR_FIELD_REGISTRY["total_shares"],
            "total_shares",
        ),
        "financial_period_basis": "year_to_date_cumulative",
        "source": AFFAIR_SOURCE,
        "source_type": AFFAIR_SOURCE,
        "source_trade_date": source_trade_date,
        "source_batch_id": source_batch_id,
        "source_version": source_version,
        "forecast_type": None,
        "forecast_score": None,
        "financial_warning_json": {
            "warnings": warnings,
            "interest_or_finance_expense_provenance": expense_provenance,
        },
        "raw_payload": {
            "field_registry_version": AFFAIR_FIELD_REGISTRY_VERSION,
            "raw_fn_fields": raw_fn_payload,
            "unit_audit": {
                name: raw_fn_payload[fn_name]
                for name, fn_name in AFFAIR_UNIT_AUDIT_FIELDS.items()
            },
        },
    }


def affair_report_period(item: Mapping[str, Any]) -> str | None:
    explicit = normalize_affair_date(
        item.get("report_period"),
        field_name="report_period",
    )
    if explicit:
        return explicit
    match = _AFFAIR_PACKAGE_RE.fullmatch(
        Path(str(item.get("filename") or "")).name
    )
    return (
        normalize_affair_date(match.group(1), field_name="report_period")
        if match
        else None
    )


def normalize_affair_manifest(
    files: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Normalize the remote manifest; local-only receipts use a separate path."""

    normalized: list[dict[str, Any]] = []
    for raw in files:
        filename = Path(str(raw.get("filename") or "")).name
        report_period = affair_report_period(raw)
        md5 = str(raw.get("md5") or raw.get("hash") or "").lower()
        try:
            filesize = int(raw.get("filesize") or raw.get("size") or 0)
        except (TypeError, ValueError):
            continue
        if (
            not _AFFAIR_PACKAGE_RE.fullmatch(filename)
            or not report_period
            or not re.fullmatch(r"[0-9a-f]{32}", md5)
            or filesize <= 0
        ):
            continue
        normalized.append(
            {
                "filename": filename,
                "filesize": filesize,
                "md5": md5,
                "hash": md5,
                "report_period": report_period,
            }
        )
    return sorted(
        normalized,
        key=lambda item: (item["report_period"], item["filename"]),
    )


def select_recent_affair_packages(
    files: Sequence[Mapping[str, Any]],
    *,
    target_report_period: str,
    limit: int = AFFAIR_PACKAGE_LIMIT,
) -> list[dict[str, Any]]:
    target = require_yyyymmdd(
        target_report_period,
        "target_report_period",
    )
    if limit != AFFAIR_PACKAGE_LIMIT:
        raise MootdxFinancialSourceError(
            "affair_package_limit_must_equal_10"
        )
    usable = [
        item
        for item in normalize_affair_manifest(files)
        if item["report_period"] <= target
        and int(item["filesize"]) > AFFAIR_PLACEHOLDER_MAX_BYTES
    ]
    if len(usable) < AFFAIR_PACKAGE_LIMIT:
        raise MootdxFinancialSourceError(
            "affair_recent_10_usable_package_manifest_incomplete"
        )
    return usable[-AFFAIR_PACKAGE_LIMIT:]


def _canonical_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _file_hashes(path: Path) -> tuple[int, str, str]:
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            md5.update(chunk)
            sha256.update(chunk)
    return size, md5.hexdigest(), sha256.hexdigest()


def _validate_zip_crc(path: Path) -> int:
    try:
        with ZipFile(path) as archive:
            members = archive.infolist()
            if not members:
                raise MootdxFinancialSourceError(
                    "affair_package_zip_empty"
                )
            bad_member = archive.testzip()
    except (BadZipFile, OSError) as exc:
        raise MootdxFinancialSourceError(
            "affair_package_zip_invalid"
        ) from exc
    if bad_member is not None:
        raise MootdxFinancialSourceError(
            "affair_package_zip_crc_failed"
        )
    return len(members)


def _validate_local_package(
    path: Path,
    *,
    report_period: str,
) -> dict[str, Any]:
    if path.is_symlink():
        raise MootdxFinancialSourceError(
            "affair_local_package_symlink_not_allowed"
        )
    try:
        file_stat = path.lstat()
    except OSError as exc:
        raise MootdxFinancialSourceError(
            "affair_local_package_stat_failed"
        ) from exc
    if not stat.S_ISREG(file_stat.st_mode):
        raise MootdxFinancialSourceError(
            "affair_local_package_not_regular_file"
        )
    if file_stat.st_size <= AFFAIR_PLACEHOLDER_MAX_BYTES:
        raise MootdxFinancialSourceError(
            "affair_local_package_placeholder_not_usable"
        )
    member_count = _validate_zip_crc(path)
    size, md5, sha256 = _file_hashes(path)
    return {
        "filename": path.name,
        "filesize": size,
        "md5": md5,
        "hash": md5,
        "sha256": sha256,
        "report_period": report_period,
        "downloaded": False,
        "zip_crc_valid": True,
        "zip_member_count": member_count,
        "verification_basis": "local_zip_crc_sha256",
        "path": str(path),
    }


def _scan_local_affair_policy(
    cache_dir: str | Path,
    *,
    source_trade_date: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cache_root = Path(cache_dir).expanduser()
    source_trade_date = require_yyyymmdd(
        source_trade_date,
        "source_trade_date",
    )
    if cache_root.is_symlink():
        raise MootdxFinancialSourceError(
            "affair_cache_root_symlink_not_allowed"
        )
    if not cache_root.exists() or not cache_root.is_dir():
        raise MootdxFinancialSourceError(
            "affair_local_cache_directory_missing"
        )
    candidates: list[tuple[str, Path, int]] = []
    placeholders: list[dict[str, Any]] = []
    for path in cache_root.iterdir():
        match = _AFFAIR_PACKAGE_RE.fullmatch(path.name)
        if not match:
            continue
        report_period = normalize_affair_date(
            match.group(1),
            field_name="report_period",
        )
        if not report_period or report_period > source_trade_date:
            continue
        if path.is_symlink():
            candidates.append((report_period, path, AFFAIR_PLACEHOLDER_MAX_BYTES + 1))
            continue
        try:
            file_stat = path.lstat()
        except OSError:
            candidates.append((report_period, path, AFFAIR_PLACEHOLDER_MAX_BYTES + 1))
            continue
        if not stat.S_ISREG(file_stat.st_mode):
            candidates.append((report_period, path, AFFAIR_PLACEHOLDER_MAX_BYTES + 1))
            continue
        if file_stat.st_size <= AFFAIR_PLACEHOLDER_MAX_BYTES:
            placeholders.append(
                {
                    "filename": path.name,
                    "filesize": int(file_stat.st_size),
                    "report_period": report_period,
                }
            )
            continue
        candidates.append((report_period, path, int(file_stat.st_size)))
    candidates.sort(key=lambda item: (item[0], item[1].name))
    if len(candidates) < AFFAIR_PACKAGE_LIMIT:
        raise MootdxFinancialSourceError(
            "affair_local_cache_recent_10_incomplete"
        )
    selected = [
        _validate_local_package(path, report_period=period)
        for period, path, _ in candidates[-AFFAIR_PACKAGE_LIMIT:]
    ]
    return selected, {
        "placeholder_count": len(placeholders),
        "placeholder_filenames": [
            item["filename"] for item in placeholders
        ],
        "placeholder_manifest_sha256": _canonical_hash(placeholders),
    }


def scan_local_affair_packages(
    cache_dir: str | Path = DEFAULT_AFFAIR_CACHE_DIR,
    *,
    source_trade_date: str,
) -> list[dict[str, Any]]:
    """Return the newest ten CRC-valid local packages at the as-of date."""

    packages, _ = _scan_local_affair_policy(
        cache_dir,
        source_trade_date=source_trade_date,
    )
    return packages


def _default_download_bytes(item: Mapping[str, Any]) -> bytes:
    financial_module = importlib.import_module(
        "mootdx.financial.financial"
    )
    api_module = importlib.import_module("tdxpy.hq")
    crawler = financial_module.Financial()
    api = api_module.TdxHq_API()
    api.need_setup = False
    with api.connect(*crawler.bestip):
        return bytes(
            api.get_report_file_by_size(
                f"tdxfin/{item['filename']}",
                filesize=0,
            )
        )


def ensure_affair_package(
    item: Mapping[str, Any],
    *,
    cache_dir: str | Path,
    download_fn: Callable[[Mapping[str, Any]], Any] | None = None,
) -> dict[str, Any]:
    """Use a verified cache hit or atomically download one remote package."""

    cache_root = Path(cache_dir).expanduser()
    if cache_root.is_symlink():
        raise MootdxFinancialSourceError(
            "affair_cache_root_symlink_not_allowed"
        )
    cache_root.mkdir(parents=True, exist_ok=True)
    filename = str(item.get("filename") or "")
    if not _AFFAIR_PACKAGE_RE.fullmatch(filename):
        raise MootdxFinancialSourceError("affair_cache_filename_invalid")
    target = cache_root / filename
    if target.parent != cache_root or target.name != filename:
        raise MootdxFinancialSourceError("affair_cache_filename_invalid")
    if target.exists() and not target.is_symlink():
        size, md5, sha256 = _file_hashes(target)
        if size == int(item["filesize"]) and md5 == str(item["md5"]):
            member_count = _validate_zip_crc(target)
            return {
                **dict(item),
                "sha256": sha256,
                "downloaded": False,
                "zip_crc_valid": True,
                "zip_member_count": member_count,
                "verification_basis": "remote_size_md5_local_zip_crc_sha256",
                "path": str(target),
            }
    elif target.is_symlink():
        raise MootdxFinancialSourceError(
            "affair_local_package_symlink_not_allowed"
        )
    temp = cache_root / f".{target.name}.{uuid.uuid4().hex}.tmp"
    descriptor: int | None = None
    try:
        descriptor = os.open(
            temp,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        payload = (download_fn or _default_download_bytes)(item)
        chunks = (
            payload
            if isinstance(payload, Iterable)
            and not isinstance(payload, (bytes, bytearray, str, Mapping))
            else [payload]
        )
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            descriptor = None
            for chunk in chunks:
                if not isinstance(chunk, (bytes, bytearray)):
                    raise MootdxFinancialSourceError(
                        "affair_download_payload_invalid"
                    )
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        size, md5, sha256 = _file_hashes(temp)
        if size != int(item["filesize"]) or md5 != str(item["md5"]):
            raise MootdxFinancialSourceError(
                "affair_package_size_or_md5_mismatch"
            )
        member_count = _validate_zip_crc(temp)
        os.replace(temp, target)
        directory_fd = os.open(cache_root, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return {
            **dict(item),
            "sha256": sha256,
            "downloaded": True,
            "zip_crc_valid": True,
            "zip_member_count": member_count,
            "verification_basis": "remote_size_md5_local_zip_crc_sha256",
            "path": str(target),
        }
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temp.exists():
            temp.unlink()


def _frame_to_records(frame: Any) -> list[dict[str, Any]]:
    if frame is None:
        return []
    if hasattr(frame, "reset_index") and hasattr(frame, "to_dict"):
        try:
            frame = frame.reset_index()
        except (TypeError, ValueError):
            pass
    if hasattr(frame, "to_dict"):
        try:
            records = frame.to_dict(orient="records")
        except TypeError:
            records = frame.to_dict("records")
        return [dict(record) for record in records]
    if isinstance(frame, Mapping):
        return [dict(frame)]
    if isinstance(frame, Iterable) and not isinstance(
        frame,
        (str, bytes, bytearray),
    ):
        return [dict(record) for record in frame]
    raise MootdxFinancialSourceError(
        f"unsupported Mootdx frame type: {type(frame).__name__}"
    )


def _affair_frame_records(frame: Any) -> list[dict[str, Any]]:
    return _frame_to_records(frame)


class MootdxAffairFinancialSource:
    """Fetch the newest ten all-market Affair packages with local fallback."""

    def __init__(
        self,
        *,
        files_fn: Callable[[], Sequence[Mapping[str, Any]]] | None = None,
        parse_fn: Callable[..., Any] | None = None,
        cache_dir: str | Path | None = None,
        download_fn: Callable[[Mapping[str, Any]], Any] | None = None,
        identity_by_code: Mapping[str, Any] | None = None,
    ) -> None:
        affair = None
        if files_fn is None or parse_fn is None:
            affair = importlib.import_module("mootdx.affair").Affair
        self._files_fn = files_fn or affair.files
        self._parse_fn = parse_fn or affair.parse
        self._download_fn = download_fn
        self.cache_dir = Path(
            cache_dir or DEFAULT_AFFAIR_CACHE_DIR
        ).expanduser()
        self.identity_by_code = dict(identity_by_code or {})
        self.last_lineage: dict[str, Any] = {}

    @staticmethod
    def manifest(
        files: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        return normalize_affair_manifest(files)

    @staticmethod
    def manifest_sha256(
        manifest: Sequence[Mapping[str, Any]],
    ) -> str:
        return _canonical_hash(list(manifest))

    def fetch_all_financial_metrics(
        self,
        *,
        expected_identity_keys: Sequence[str],
        source_trade_date: str,
        previous_snapshot: Mapping[str, Any] | None = None,
        cutoff_date: str | None = None,
        source_batch_id: str | None = None,
        source_version: str | None = None,
        target_report_period: str | None = None,
    ) -> list[dict[str, Any]]:
        del previous_snapshot
        source_trade_date = require_yyyymmdd(
            source_trade_date,
            "source_trade_date",
        )
        cutoff = require_yyyymmdd(
            cutoff_date or source_trade_date,
            "cutoff_date",
        )
        target = require_yyyymmdd(
            target_report_period or source_trade_date,
            "target_report_period",
        )
        if target > source_trade_date:
            raise MootdxFinancialSourceError(
                "affair_target_report_period_after_source_trade_date"
            )
        expected_identity_map = _identity_map_from_expected(
            expected_identity_keys
        )
        for code, metadata in self.identity_by_code.items():
            identity_key, _ = _identity_record(metadata)
            if (
                code in expected_identity_map
                and identity_key
                and identity_key
                != expected_identity_map[code]["stock_identity_key"]
            ):
                raise MootdxFinancialSourceError(
                    "affair_frozen_identity_mapping_mismatch"
                )
            if code in expected_identity_map:
                expected_identity_map[code] = metadata

        remote_manifest_available = False
        remote_manifest_error_class: str | None = None
        local_cache_error_code: str | None = None
        local_cache_used = False
        manifest_request_count = 0
        warning_codes: list[str] = []
        placeholder_lineage: dict[str, Any] = {
            "placeholder_count": 0,
            "placeholder_filenames": [],
            "placeholder_manifest_sha256": _canonical_hash([]),
        }
        try:
            receipts, placeholder_lineage = _scan_local_affair_policy(
                self.cache_dir,
                source_trade_date=target,
            )
            local_cache_used = True
        except MootdxFinancialSourceError as local_exc:
            local_cache_error_code = str(local_exc)
            if local_cache_error_code not in {
                "affair_local_cache_directory_missing",
                "affair_local_cache_recent_10_incomplete",
            }:
                raise
            manifest_request_count = 1
            try:
                remote_manifest = normalize_affair_manifest(
                    self._files_fn() or []
                )
                packages = select_recent_affair_packages(
                    remote_manifest,
                    target_report_period=target,
                )
            except Exception as exc:
                remote_manifest_error_class = exc.__class__.__name__
                raise MootdxFinancialSourceError(
                    "affair_remote_manifest_unavailable_and_local_cache_incomplete"
                ) from exc
            remote_manifest_available = True
            remote_placeholders = [
                item
                for item in remote_manifest
                if item["report_period"] <= target
                and int(item["filesize"])
                <= AFFAIR_PLACEHOLDER_MAX_BYTES
            ]
            placeholder_lineage = {
                "placeholder_count": len(remote_placeholders),
                "placeholder_filenames": [
                    item["filename"] for item in remote_placeholders
                ],
                "placeholder_manifest_sha256": _canonical_hash(
                    remote_placeholders
                ),
            }
            # A valid remote manifest is authoritative. Package transfer,
            # digest or CRC failures must reach the source-bundle fallback.
            receipts = [
                ensure_affair_package(
                    package,
                    cache_dir=self.cache_dir,
                    download_fn=self._download_fn,
                )
                for package in packages
            ]

        rows: list[dict[str, Any]] = []
        raw_row_count = 0
        unmapped = 0
        future = 0
        missing_announcement = 0
        for receipt in receipts:
            frame = self._parse_fn(
                downdir=str(self.cache_dir),
                filename=receipt["filename"],
                header="raw",
            )
            records = _affair_frame_records(frame)
            raw_row_count += len(records)
            for record in records:
                row = normalize_affair_record(
                    record,
                    report_period=str(receipt["report_period"]),
                    source_trade_date=source_trade_date,
                    identity_by_code=expected_identity_map,
                    source_batch_id=source_batch_id,
                    source_version=source_version,
                )
                if row is None:
                    unmapped += 1
                    continue
                if not row.get("announcement_date"):
                    missing_announcement += 1
                    continue
                if str(row["announcement_date"]) > cutoff:
                    future += 1
                    continue
                rows.append(row)
        rows.sort(
            key=lambda row: (
                str(row.get("stock_identity_key") or ""),
                str(row.get("report_period") or ""),
                str(row.get("announcement_date") or ""),
            )
        )
        package_manifest = [
            {
                key: receipt.get(key)
                for key in (
                    "filename",
                    "filesize",
                    "md5",
                    "sha256",
                    "report_period",
                    "downloaded",
                    "zip_crc_valid",
                    "zip_member_count",
                    "verification_basis",
                )
            }
            for receipt in receipts
        ]
        row_identities = sorted(
            {str(row["stock_identity_key"]) for row in rows}
        )
        manifest_sha = _canonical_hash(package_manifest)
        self.last_lineage = {
            "source": AFFAIR_SOURCE,
            "financial_authority": AFFAIR_SOURCE,
            "parser_version": AFFAIR_PARSER_VERSION,
            "field_registry_version": AFFAIR_FIELD_REGISTRY_VERSION,
            "cache_dir": str(self.cache_dir),
            "package_selection": (
                "latest_10_usable_at_or_before_source_trade_date"
            ),
            "package_count": len(package_manifest),
            "package_manifest": package_manifest,
            "package_manifest_sha256": manifest_sha,
            # Compatibility names consumed by the current source bundle.
            "affair_file_manifest": package_manifest,
            "affair_file_manifest_sha256": manifest_sha,
            "remote_manifest_available": remote_manifest_available,
            "remote_manifest_error_class": remote_manifest_error_class,
            "local_cache_error_code": local_cache_error_code,
            "manifest_source": (
                "local_cache"
                if local_cache_used
                else "remote_manifest"
            ),
            "manifest_request_count": manifest_request_count,
            "local_cache_used": local_cache_used,
            "warning_codes": warning_codes,
            "quality_warnings": [
                {"severity": "P1", "code": code}
                for code in warning_codes
            ],
            **placeholder_lineage,
            "raw_row_count": raw_row_count,
            "accepted_row_count": len(rows),
            "row_identity_count": len(row_identities),
            "row_identity_sha256": _canonical_hash(row_identities),
            "unmapped_identity_count": unmapped,
            "announcement_date_unverified_count": missing_announcement,
            "future_announcement_excluded_count": future,
            "cutoff_date": cutoff,
            "downloads_performed": sum(
                1 for receipt in receipts if receipt.get("downloaded")
            ),
            "package_download_count": sum(
                1 for receipt in receipts if receipt.get("downloaded")
            ),
        }
        return rows


class MootdxFinancialSource:
    """Disabled legacy per-symbol endpoint retained for import compatibility."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        market: str = "std",
    ) -> None:
        self.market = market
        self._client = client

    def fetch_stock_financial_metrics(
        self,
        *,
        symbols: Sequence[StockFinancialSymbol],
        asof_date: str,
    ) -> Sequence[Mapping[str, Any]]:
        del symbols, asof_date
        raise MootdxFinancialSourceError(
            "per-symbol Mootdx finance(symbol) is disabled; "
            "use MootdxAffairFinancialSource"
        )
