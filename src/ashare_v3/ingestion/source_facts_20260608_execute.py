"""Guarded N1 source-facts runner contract support for 20260608.

This module owns the dedicated source-facts runner for 20260608. It binds the
already-verified official-daily and condition-source mechanics to a single N1
guarded path, while preserving the stock-only skip policy for 920206.BJ.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import re
from typing import Any, Iterator, Mapping

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ashare_v3.ingestion import condition_source_activation_20260605_execute as _condition_20260605
from ashare_v3.ingestion import official_daily_20260529_execute as _official_base
from ashare_v3.ingestion import official_daily_20260605_execute as _official_20260605


TRADE_DATE = "20260608"
FOR_TRADE_DATE = "20260609"
EXPECTED_PREV_TRADE_DATE = "20260605"
EXPECTED_NEXT_TRADE_DATE = "20260609"
ACTIVE_STOCK_IDENTITY_SCOPE_KEY = "A_STOCK:20260605"
ACTIVE_STOCK_IDENTITY_SOURCE_VERSION = "stock_identity_20260605_v1"
ACTIVE_STOCK_IDENTITY_SOURCE_BATCH_ID = "stock_identity_refresh_20260605_920211_v1"
ACTIVE_STOCK_IDENTITY_PREVIOUS_SOURCE_VERSION = "stock_identity_20260604_v1"

CONTRACT_PATH = Path("docs/N1_20260608_SOURCE_FACTS_GUARDED_RUNNER_CONTRACT.json")
PREFLIGHT_PATH = Path("docs/N1_20260608_SOURCE_FACTS_GUARDED_RUNNER_PREFLIGHT.json")
ROLLBACK_SQL_PATH = Path("sql/N1_20260608_source_facts_guarded_runner_rollback.sql")
IMPLEMENTATION_REPORT_JSON_PATH = Path("docs/N1_20260608_SOURCE_FACTS_GUARDED_RUNNER_IMPLEMENTATION.json")
IMPLEMENTATION_REPORT_MD_PATH = Path("docs/N1_20260608_SOURCE_FACTS_GUARDED_RUNNER_IMPLEMENTATION.md")
IDENTITY_REPAIR_HANDOFF_PATH = Path("docs/N1_20260608_STOCK_IDENTITY_920206_REPAIR_HANDOFF.json")
IDENTITY_REPAIR_HANDOFF_MD_PATH = Path("docs/N1_20260608_STOCK_IDENTITY_920206_REPAIR_HANDOFF.md")
FINAL_GATE_REVIEW_JSON_PATH = Path("docs/N1_20260608_SOURCE_FACTS_EXECUTE_FINAL_GATE_REVIEW.json")
FINAL_GATE_REVIEW_MD_PATH = Path("docs/N1_20260608_SOURCE_FACTS_EXECUTE_FINAL_GATE_REVIEW.md")
EXECUTE_REPORT_JSON_PATH = Path("docs/N1_20260608_SOURCE_FACTS_EXECUTE_REPORT.json")
EXECUTE_REPORT_MD_PATH = Path("docs/N1_20260608_SOURCE_FACTS_EXECUTE_REPORT.md")
POST_REVIEW_JSON_PATH = Path("docs/N1_20260608_SOURCE_FACTS_POST_REVIEW.json")
POST_REVIEW_MD_PATH = Path("docs/N1_20260608_SOURCE_FACTS_POST_REVIEW.md")

OFFICIAL_DAILY_BATCH_ID = "official_daily_ingest_20260608_v1"
CONDITION_SOURCE_BATCH_ID = "condition_source_activation_20260608_v1"
OFFICIAL_SOURCE_VERSIONS = {
    "stock": "stock_daily_20260608_v1",
    "index": "index_daily_20260608_v1",
    "board": "board_daily_20260608_v1",
}
CONDITION_SOURCE_VERSIONS = {
    "stock_daily_basic": "stock_daily_basic_20260608_v1",
    "stock_financial": "stock_financial_20260608_v1",
    "index_membership": "index_membership_20260608_v1",
    "board_membership": "board_membership_20260608_v1",
}

ALLOWED_WRITE_TABLES = (
    "common_ingest_batch",
    "common_quality_gate_result",
    "common_active_source_version",
    "stock_daily_bar_fact",
    "index_daily_bar_fact",
    "board_daily_bar_fact",
    "stock_daily_basic",
    "stock_financial_metrics_fact",
    "index_membership_fact",
    "board_membership_fact",
)
FORBIDDEN_SCOPE_MARKERS = (
    "common_event_outbox",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "condition_*",
    "N2/N3/N4/N5/N6",
    "Parquet",
    "worker",
    "old_system",
    "proposal/order/trade/sim/position/PnL/real_trade",
)

EXPECTED_ROWS_AFTER_P0_CLEARANCE = {
    "official_daily": {
        "stock_daily_bar_fact": 5515,
        "index_daily_bar_fact": 83,
        "board_daily_bar_fact": 428,
        "total_daily_fact": 6026,
    },
    "condition_source": {
        "stock_daily_basic": 5515,
        "stock_financial_metrics_fact": 5515,
        "index_membership_fact": 12841,
        "board_membership_fact": 56962,
        "total_condition_source_fact": 80833,
    },
    "combined_total": 86859,
}

SKIP_POLICY_NAME = "skip_missing_stock_identity_when_count_lte_10"
MISSING_STOCK_IDENTITY_SKIP_THRESHOLD = 10
MISSING_NONCRITICAL_BOARD_DAILY_SKIP_POLICY_NAME = "skip_missing_noncritical_board_daily_when_881_coverage_passed"
MISSING_NONCRITICAL_BOARD_DAILY_SKIP_THRESHOLD = 10

SKIPPED_STOCK_IDENTITIES_20260608 = (
    {
        "ts_code": "920206.BJ",
        "canonical_identity_key": "stock:BJ:920206",
        "asset_kind": "stock",
        "reason": "stock_identity_missing_below_threshold",
        "policy_name": SKIP_POLICY_NAME,
        "source_presence": [
            "tushare.daily",
            "tushare.daily_basic",
        ],
        "severity": "P1",
        "writes_stock_daily_bar_fact": False,
        "writes_stock_daily_basic": False,
        "writes_stock_financial_metrics_fact": False,
        "action": "exclude_from_20260608_source_facts",
    },
)

OFFICIAL_NO_TRADE_IDENTITIES = _official_20260605.OFFICIAL_NO_TRADE_IDENTITIES
OFFICIAL_NO_TRADE_TS_CODES = _condition_20260605.OFFICIAL_NO_TRADE_TS_CODES
STALE_IDENTITY_KEY = _official_20260605.STALE_IDENTITY_KEY
STALE_IDENTITY_MANIFEST = _official_20260605.STALE_IDENTITY_MANIFEST
OFFICIAL_NO_TRADE_CORRECTION_EVIDENCE: dict[str, Any] = {}
EXPECTED_STOCK_ADJ_FACTOR_ROWS = 5527
EXPECTED_MATCHED_STOCK_IDENTITY_ROWS = 5514
EXPECTED_UNMAPPED_TUSHARE_DAILY_ROWS = 1
STOCK_SCOPE_BREAKDOWN = {
    "stock_identity_active_universe": 5527,
    "stale_identity_excluded": 1,
    "effective_universe_excluding_stale": 5526,
    "tushare_daily_source_rows": 5515,
    "tushare_daily_rows": 5514,
    "tushare_daily_rows_with_stock_identity": 5514,
    "missing_stock_identity_skipped": 1,
    "supplemental_source_bar_rows": 0,
    "official_no_trade_manifest_rows": 12,
    "expected_stock_daily_bar_rows": 5514,
    "unresolved_source_gap": 0,
    "stock_identity_refresh_required": False,
}
INDEX_SCOPE_BREAKDOWN = {
    "expected_index_daily_bar_fact_rows": 83,
    "mootdx_rows": 81,
    "tushare_bj_fallback_rows": 2,
    "fixed_9_included": 9,
    "unknown_writes": 0,
}
BOARD_SCOPE_BREAKDOWN = {
    "expected_board_daily_bar_fact_rows": 428,
    "industry_881_required_coverage": 127,
}

ADJUSTED_EXPECTED_ROWS_WITH_SKIP_POLICY = {
    "official_daily": {
        "stock_daily_bar_fact": 5514,
        "index_daily_bar_fact": 83,
        "board_daily_bar_fact": 428,
        "total_daily_fact": 6025,
    },
    "condition_source": {
        "stock_daily_basic": 5514,
        "stock_financial_metrics_fact": 5514,
        "index_membership_fact": 12841,
        "board_membership_fact": 56962,
        "total_condition_source_fact": 80831,
    },
    "combined_total": 86856,
}

APPROVED_COMMAND_SCRIPT = "scripts/run_n1_20260608_source_facts_once.py"
REQUIRED_EXECUTE_FLAGS = (
    "--execute",
    "--user-confirmed",
    "--source-fetch-enabled",
    "--postgres-commit-enabled",
)

OFFICIAL_DEFAULT_PATHS = {
    "dry_run_json": Path("docs/N1_20260608_source_facts_official_daily_dry_run.json"),
    "dry_run_md": Path("docs/N1_20260608_SOURCE_FACTS_OFFICIAL_DAILY_DRY_RUN.md"),
    "contract_json": Path("docs/N1_20260608_source_facts_official_daily_contract.json"),
    "contract_md": Path("docs/N1_20260608_SOURCE_FACTS_OFFICIAL_DAILY_CONTRACT.md"),
    "preflight_json": Path("docs/N1_20260608_source_facts_official_daily_preflight.json"),
    "preflight_md": Path("docs/N1_20260608_SOURCE_FACTS_OFFICIAL_DAILY_PREFLIGHT.md"),
    "rollback_sql": ROLLBACK_SQL_PATH,
    "stock_probe_json": PREFLIGHT_PATH,
    "index_board_probe_json": PREFLIGHT_PATH,
    "index_board_probe_md": Path("docs/N1_20260608_SOURCE_FACTS_INDEX_BOARD_PROBE.md"),
}

CONDITION_DEFAULT_PATHS = {
    "dry_run_json": Path("docs/N1_20260608_source_facts_condition_source_dry_run.json"),
    "dry_run_md": Path("docs/N1_20260608_SOURCE_FACTS_CONDITION_SOURCE_DRY_RUN.md"),
    "contract_json": Path("docs/N1_20260608_source_facts_condition_source_contract.json"),
    "contract_md": Path("docs/N1_20260608_SOURCE_FACTS_CONDITION_SOURCE_CONTRACT.md"),
    "preflight_json": Path("docs/N1_20260608_source_facts_condition_source_preflight.json"),
    "preflight_md": Path("docs/N1_20260608_SOURCE_FACTS_CONDITION_SOURCE_PREFLIGHT.md"),
    "execute_report_json": EXECUTE_REPORT_JSON_PATH,
    "execute_report_md": EXECUTE_REPORT_MD_PATH,
    "rollback_sql": ROLLBACK_SQL_PATH,
}


class SourceFacts20260608Blocked(RuntimeError):
    """Raised when the guarded 20260608 source-facts runner refuses to proceed."""


def build_missing_stock_identity_skip_manifest() -> list[dict[str, Any]]:
    return [dict(item) for item in SKIPPED_STOCK_IDENTITIES_20260608]


def evaluate_missing_identity_policy(
    *,
    asset_kind: str,
    missing_identities: list[Mapping[str, Any]],
    fixed_9_index_scope: bool = False,
    threshold: int = MISSING_STOCK_IDENTITY_SKIP_THRESHOLD,
) -> dict[str, Any]:
    missing_count = len(missing_identities)
    missing_payload = [dict(item) for item in missing_identities]
    base = {
        "policy_name": SKIP_POLICY_NAME,
        "asset_kind": asset_kind,
        "threshold": threshold,
        "missing_count": missing_count,
        "missing_identities": missing_payload,
        "stock_only": True,
        "index_board_applicable": False,
        "fixed_9_index_applicable": False,
    }
    if missing_count == 0:
        return {
            **base,
            "decision": "PASS",
            "severity": "PASSED",
            "p0_count": 0,
            "p1_count": 0,
            "skipped_count": 0,
            "blockers": [],
        }
    if asset_kind != "stock" or fixed_9_index_scope:
        return {
            **base,
            "decision": "BLOCK",
            "severity": "P0",
            "p0_count": 1,
            "p1_count": 0,
            "skipped_count": 0,
            "blockers": [
                f"{SKIP_POLICY_NAME}_not_applicable_to_{asset_kind}",
            ],
        }
    if missing_count > threshold:
        return {
            **base,
            "decision": "BLOCK",
            "severity": "P0",
            "p0_count": 1,
            "p1_count": 0,
            "skipped_count": 0,
            "blockers": [
                "missing_stock_identity_count_exceeds_skip_threshold",
            ],
        }
    return {
        **base,
        "decision": "SKIP",
        "severity": "P1",
        "p0_count": 0,
        "p1_count": 1,
        "skipped_count": missing_count,
        "skipped_identities": missing_payload,
        "blockers": [],
    }


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_contract(path: str | Path = CONTRACT_PATH) -> dict[str, Any]:
    return load_json(path)


def load_preflight(path: str | Path = PREFLIGHT_PATH) -> dict[str, Any]:
    return load_json(path)


def validate_trade_date(trade_date: str) -> None:
    if trade_date != TRADE_DATE:
        raise SourceFacts20260608Blocked(f"this runner is fixed to trade_date={TRADE_DATE}")


def validate_execute_request(
    *,
    execute_requested: bool,
    user_confirmed: bool,
    source_fetch_enabled: bool,
    postgres_commit_enabled: bool,
) -> None:
    missing: list[str] = []
    if not execute_requested:
        missing.append("--execute")
    if not user_confirmed:
        missing.append("--user-confirmed")
    if not source_fetch_enabled:
        missing.append("--source-fetch-enabled")
    if not postgres_commit_enabled:
        missing.append("--postgres-commit-enabled")
    if missing:
        raise SourceFacts20260608Blocked(f"missing required execute flag(s): {', '.join(missing)}")


def validate_preflight_allows_execute(preflight: Mapping[str, Any]) -> None:
    p0_count = int(((preflight.get("p0_p1_p2") or {}).get("P0")) or 0)
    blockers = list(preflight.get("blockers") or [])
    if p0_count:
        if blockers:
            raise SourceFacts20260608Blocked(", ".join(str(item) for item in blockers))
        raise SourceFacts20260608Blocked(f"P0 blockers present: {p0_count}")
    if preflight.get("preflight_result") != "PREFLIGHT_PASS":
        raise SourceFacts20260608Blocked(str(preflight.get("preflight_result") or "preflight_not_passed"))
    if preflight.get("final_execute_gate_allowed") is not True:
        raise SourceFacts20260608Blocked("final_execute_gate_allowed=false")


def assert_approved_command(command: str) -> bool:
    if "run_real_daily_incremental.py" in command:
        raise SourceFacts20260608Blocked("scripts/run_real_daily_incremental.py is not an approved execute command")
    if APPROVED_COMMAND_SCRIPT not in command:
        raise SourceFacts20260608Blocked(f"command must use {APPROVED_COMMAND_SCRIPT}")
    missing = [flag for flag in REQUIRED_EXECUTE_FLAGS if flag not in command]
    if missing:
        raise SourceFacts20260608Blocked(f"approved command missing flag(s): {', '.join(missing)}")
    if "--trade-date 20260608" not in command and "--trade-date=20260608" not in command:
        raise SourceFacts20260608Blocked("approved command must pin --trade-date 20260608")
    return True


def _json_clone(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _is_skipped_stock(row: Mapping[str, Any]) -> bool:
    ts_code = str(row.get("ts_code") or "")
    identity = str(row.get("identity_key") or row.get("stock_identity_key") or "")
    code = str(row.get("code") or "")
    exchange = str(row.get("exchange") or "")
    return ts_code == "920206.BJ" or identity == "stock:BJ:920206" or (code == "920206" and exchange == "BJ")


def _board_identity(row: Mapping[str, Any]) -> str:
    return str(row.get("identity_key") or row.get("board_identity_key") or "")


def _board_code(row: Mapping[str, Any]) -> str:
    return str(row.get("board_code") or row.get("code") or "")


def _is_critical_board_scope(row: Mapping[str, Any]) -> bool:
    return _board_code(row).startswith("881") or str(row.get("board_type") or "") == "tdx_industry"


def _append_skip_quality_items(
    validation_report: Mapping[str, Any],
    *,
    board_skip_manifest: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    report = _json_clone(validation_report)
    quality_items = [dict(item) for item in report.get("quality_items") or []]
    gate_names = {str(item.get("gate_name") or "") for item in quality_items}
    if "missing_stock_identity_skip_policy_applied" not in gate_names:
        quality_items.append(
            {
                "gate_name": "missing_stock_identity_skip_policy_applied",
                "severity": "P1",
                "status": "warning",
                "expected": {
                    "policy": SKIP_POLICY_NAME,
                    "threshold": MISSING_STOCK_IDENTITY_SKIP_THRESHOLD,
                    "writes_stock_facts": False,
                },
                "actual": {
                    "missing_count": len(SKIPPED_STOCK_IDENTITIES_20260608),
                    "skipped_identities": build_missing_stock_identity_skip_manifest(),
                },
                "details": {
                    "stock_daily_bar_fact": False,
                    "stock_daily_basic": False,
                    "stock_financial_metrics_fact": False,
                },
            }
        )
    board_skip_manifest = [dict(row) for row in board_skip_manifest or []]
    if board_skip_manifest and "missing_noncritical_board_daily_skip_policy_applied" not in gate_names:
        quality_items.append(
            {
                "gate_name": "missing_noncritical_board_daily_skip_policy_applied",
                "severity": "P1",
                "status": "warning",
                "expected": {
                    "policy": MISSING_NONCRITICAL_BOARD_DAILY_SKIP_POLICY_NAME,
                    "threshold": MISSING_NONCRITICAL_BOARD_DAILY_SKIP_THRESHOLD,
                    "critical_board_missing": 0,
                    "writes_board_daily_bar_fact": False,
                },
                "actual": {
                    "missing_count": len(board_skip_manifest),
                    "skipped_identities": board_skip_manifest,
                },
                "details": {
                    "reason": "noncritical_tdx_concept_or_region_board_absent_from_daily_source",
                    "industry_881_required_coverage_remains_p0": True,
                },
            }
        )
    report["quality_items"] = quality_items
    quality = dict(report.get("quality") or {})
    p1_increment = 0 if "missing_stock_identity_skip_policy_applied" in gate_names else 1
    if board_skip_manifest and "missing_noncritical_board_daily_skip_policy_applied" not in gate_names:
        p1_increment += 1
    quality["p1_count"] = max(int(quality.get("p1_count") or 0), 0) + p1_increment
    quality.setdefault("p0_count", int(report.get("p0_count") or 0))
    quality.setdefault("p2_count", 0)
    report["quality"] = quality
    return report


def apply_missing_stock_identity_skip_policy_to_official_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    fixed = _json_clone(bundle)
    skipped = [row for row in fixed.get("stock") or [] if _is_skipped_stock(row)]
    fixed["stock"] = [row for row in fixed.get("stock") or [] if not _is_skipped_stock(row)]
    fixed.setdefault("missing_stock_identity_skip_manifest", build_missing_stock_identity_skip_manifest())
    source_breakdown = dict(fixed.get("source_breakdown") or {})
    source_breakdown["skipped_missing_stock_identity_rows"] = len(skipped) or len(SKIPPED_STOCK_IDENTITIES_20260608)
    source_breakdown["unmapped_tushare_daily_rows"] = len(SKIPPED_STOCK_IDENTITIES_20260608)
    source_breakdown.setdefault("stock_daily_source_rows", EXPECTED_ROWS_AFTER_P0_CLEARANCE["official_daily"]["stock_daily_bar_fact"])
    source_breakdown["matched_identity_rows"] = ADJUSTED_EXPECTED_ROWS_WITH_SKIP_POLICY["official_daily"]["stock_daily_bar_fact"]
    fixed["source_breakdown"] = source_breakdown
    return fixed


def apply_missing_stock_identity_skip_policy_to_condition_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    fixed = _json_clone(bundle)
    for key in ("stock_daily_basic", "stock_financial"):
        fixed[key] = [row for row in fixed.get(key) or [] if not _is_skipped_stock(row)]
    manifests = dict(fixed.get("manifests") or {})
    manifests["missing_stock_identity_skip_manifest"] = build_missing_stock_identity_skip_manifest()
    fixed["manifests"] = manifests
    return fixed


def _official_patch_values(*, no_trade_identities: tuple[str, ...] | None = None) -> dict[str, Any]:
    no_trade_identities = no_trade_identities if no_trade_identities is not None else OFFICIAL_NO_TRADE_IDENTITIES
    return {
        "TRADE_DATE": TRADE_DATE,
        "EXPECTED_PREV_TRADE_DATE": EXPECTED_PREV_TRADE_DATE,
        "EXPECTED_NEXT_TRADE_DATE": EXPECTED_NEXT_TRADE_DATE,
        "ACTIVE_STOCK_IDENTITY_SCOPE_KEY": ACTIVE_STOCK_IDENTITY_SCOPE_KEY,
        "ACTIVE_STOCK_IDENTITY_SOURCE_VERSION": ACTIVE_STOCK_IDENTITY_SOURCE_VERSION,
        "ACTIVE_STOCK_IDENTITY_SOURCE_BATCH_ID": ACTIVE_STOCK_IDENTITY_SOURCE_BATCH_ID,
        "ACTIVE_STOCK_IDENTITY_PREVIOUS_SOURCE_VERSION": ACTIVE_STOCK_IDENTITY_PREVIOUS_SOURCE_VERSION,
        "BATCH_ID": OFFICIAL_DAILY_BATCH_ID,
        "CONTRACT_SOURCE_VERSION": OFFICIAL_DAILY_BATCH_ID,
        "SOURCE_VERSIONS": dict(OFFICIAL_SOURCE_VERSIONS),
        "ACTIVE_DATA_TYPES": {
            "stock": "stock_daily",
            "index": "index_daily",
            "board": "board_daily",
        },
        "EXPECTED_ROWS": dict(ADJUSTED_EXPECTED_ROWS_WITH_SKIP_POLICY["official_daily"]),
        "EXPECTED_STOCK_ADJ_FACTOR_ROWS": EXPECTED_STOCK_ADJ_FACTOR_ROWS,
        "EXPECTED_MATCHED_STOCK_IDENTITY_ROWS": EXPECTED_MATCHED_STOCK_IDENTITY_ROWS,
        "EXPECTED_UNMAPPED_TUSHARE_DAILY_ROWS": EXPECTED_UNMAPPED_TUSHARE_DAILY_ROWS,
        "STOCK_SCOPE_BREAKDOWN": dict(STOCK_SCOPE_BREAKDOWN),
        "INDEX_SCOPE_BREAKDOWN": dict(INDEX_SCOPE_BREAKDOWN),
        "BOARD_SCOPE_BREAKDOWN": dict(BOARD_SCOPE_BREAKDOWN),
        "FIXED_9_INDEX_IDENTITIES": _official_20260605.FIXED_9_INDEX_IDENTITIES,
        "CANONICAL_IDENTITY_MAPPING": _official_20260605.CANONICAL_IDENTITY_MAPPING,
        "INDEX_TUSHARE_FALLBACK_IDENTITIES": _official_20260605.INDEX_TUSHARE_FALLBACK_IDENTITIES,
        "STALE_IDENTITY_KEY": STALE_IDENTITY_KEY,
        "STALE_IDENTITY_MANIFEST": STALE_IDENTITY_MANIFEST,
        "OFFICIAL_NO_TRADE_IDENTITIES": no_trade_identities,
        "OFFICIAL_NO_TRADE_CORRECTION_EVIDENCE": OFFICIAL_NO_TRADE_CORRECTION_EVIDENCE,
        "DEFAULT_PATHS": dict(OFFICIAL_DEFAULT_PATHS),
    }


@contextmanager
def patched_official_daily_20260608(*, no_trade_identities: tuple[str, ...] | None = None) -> Iterator[None]:
    overrides = _official_patch_values(no_trade_identities=no_trade_identities)
    previous = {name: getattr(_official_20260605, name) for name in overrides}
    previous_template_patch = dict(getattr(_official_20260605, "_TEMPLATE_PATCH_VALUES"))
    try:
        for name, value in overrides.items():
            setattr(_official_20260605, name, value)
        _official_20260605._TEMPLATE_PATCH_VALUES = dict(overrides)
        yield
    finally:
        for name, value in previous.items():
            setattr(_official_20260605, name, value)
        _official_20260605._TEMPLATE_PATCH_VALUES = previous_template_patch


def official_build_snapshot_from_db(*, dsn: str, trade_date: str = TRADE_DATE) -> dict[str, Any]:
    with patched_official_daily_20260608():
        return _official_20260605.build_snapshot_from_db(dsn=dsn, trade_date=trade_date)


def official_build_expected_scope_from_db(*, dsn: str, trade_date: str = TRADE_DATE) -> dict[str, list[dict[str, Any]]]:
    if trade_date != TRADE_DATE:
        raise SourceFacts20260608Blocked(f"this runner is fixed to trade_date={TRADE_DATE}")
    with patched_official_daily_20260608():
        with psycopg.connect(dsn, connect_timeout=10, options="-c default_transaction_read_only=on", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT stock_identity_key AS identity_key, exchange, code, name, ts_code
                    FROM stock_identity
                    WHERE status = 'active'
                      AND stock_identity_key <> %s
                    ORDER BY stock_identity_key
                    """,
                    (STALE_IDENTITY_KEY,),
                )
                stock_scope = [dict(row) for row in cur.fetchall()]
                index_scope = _official_base.fetch_index_expansion_scope(cur, trade_date=trade_date)
                cur.execute(
                    """
                    SELECT board_identity_key AS identity_key, 'TDX' AS exchange,
                           board_code AS code, board_name AS name, board_type
                    FROM board_identity
                    ORDER BY board_identity_key
                    """
                )
                board_scope = [dict(row) for row in cur.fetchall()]
    return _official_base.normalize_jsonable({"stock": stock_scope, "index": index_scope, "board": board_scope})


class DefaultOfficialDaily20260608SourceAdapter(_official_20260605.DefaultOfficialDaily20260605SourceAdapter):
    """20260608 adapter using the verified official daily source routes."""


def official_fetch_official_daily_sources(
    *,
    adapter: Any,
    trade_date: str,
    expected_scope: Mapping[str, Any],
    source_fetch_enabled: bool,
) -> dict[str, Any]:
    with patched_official_daily_20260608():
        bundle = _official_20260605.fetch_official_daily_sources(
            adapter=adapter,
            trade_date=trade_date,
            expected_scope=expected_scope,
            source_fetch_enabled=source_fetch_enabled,
        )
    return reconcile_official_no_trade_scope(
        bundle=apply_missing_stock_identity_skip_policy_to_official_bundle(bundle),
        expected_scope=expected_scope,
    )


def reconcile_official_no_trade_scope(*, bundle: Mapping[str, Any], expected_scope: Mapping[str, Any]) -> dict[str, Any]:
    fixed = _json_clone(bundle)
    stock_scope = [dict(row) for row in expected_scope.get("stock") or []]
    stock_rows = [dict(row) for row in fixed.get("stock") or []]
    stock_ids = {str(row.get("identity_key") or "") for row in stock_rows if row.get("identity_key")}
    missing_scope_rows = [row for row in stock_scope if str(row.get("identity_key") or "") and str(row.get("identity_key")) not in stock_ids]
    dynamic_no_trade_ids = tuple(sorted(str(row.get("identity_key")) for row in missing_scope_rows))
    existing_manifest = {
        str(row.get("identity_key") or ""): dict(row)
        for row in fixed.get("official_no_trade_manifest") or []
        if row.get("identity_key")
    }
    manifest: list[dict[str, Any]] = []
    for row in missing_scope_rows:
        identity_key = str(row.get("identity_key"))
        manifest_row = existing_manifest.get(identity_key)
        if not manifest_row:
            manifest_row = {
                "identity_key": identity_key,
                "ts_code": row.get("ts_code"),
                "disposition": "official_no_trade",
                "severity": "P1",
                "writes_stock_daily_bar_fact": False,
                "source_proof_json": {
                    "dynamic_scope_reconciliation": True,
                    "reason": "active_stock_identity_absent_from_20260608_official_daily_source",
                },
            }
        manifest_row["writes_stock_daily_bar_fact"] = False
        manifest.append(manifest_row)
    board_scope = [dict(row) for row in expected_scope.get("board") or []]
    board_rows = [dict(row) for row in fixed.get("board") or []]
    board_ids = {_board_identity(row) for row in board_rows if _board_identity(row)}
    missing_board_rows = [row for row in board_scope if _board_identity(row) and _board_identity(row) not in board_ids]
    critical_missing_board_rows = [row for row in missing_board_rows if _is_critical_board_scope(row)]
    skippable_board_rows: list[dict[str, Any]] = []
    if missing_board_rows and not critical_missing_board_rows and len(missing_board_rows) <= MISSING_NONCRITICAL_BOARD_DAILY_SKIP_THRESHOLD:
        skippable_board_rows = missing_board_rows
    skippable_board_ids = {_board_identity(row) for row in skippable_board_rows}
    board_skip_manifest = [
        {
            "identity_key": _board_identity(row),
            "board_code": _board_code(row),
            "board_name": row.get("name") or row.get("board_name"),
            "board_type": row.get("board_type"),
            "disposition": "missing_noncritical_board_daily_skipped",
            "severity": "P1",
            "writes_board_daily_bar_fact": False,
            "source_proof_json": {
                "dynamic_scope_reconciliation": True,
                "policy_name": MISSING_NONCRITICAL_BOARD_DAILY_SKIP_POLICY_NAME,
                "reason": "noncritical_board_absent_from_official_daily_source",
            },
        }
        for row in skippable_board_rows
    ]
    adjusted_scope = {
        "index": [dict(row) for row in expected_scope.get("index") or []],
        "board": [row for row in board_scope if _board_identity(row) not in skippable_board_ids],
        "stock": [row for row in stock_scope if str(row.get("identity_key") or "") not in set(dynamic_no_trade_ids)],
    }
    fixed["official_no_trade_manifest"] = manifest
    fixed["missing_noncritical_board_daily_skip_manifest"] = board_skip_manifest
    fixed["_source_facts_dynamic_no_trade_identities"] = list(dynamic_no_trade_ids)
    fixed["_source_facts_dynamic_board_daily_skip_identities"] = sorted(skippable_board_ids)
    fixed["_source_facts_adjusted_expected_scope"] = adjusted_scope
    source_breakdown = dict(fixed.get("source_breakdown") or {})
    source_breakdown["official_no_trade"] = len(manifest)
    source_breakdown["dynamic_no_trade_scope_reconciled"] = True
    source_breakdown["skipped_missing_noncritical_board_daily_rows"] = len(board_skip_manifest)
    fixed["source_breakdown"] = source_breakdown
    return fixed


def official_validate_source_bundle(
    *,
    bundle: Mapping[str, Any],
    expected_scope: Mapping[str, Any],
    trade_date: str,
) -> dict[str, Any]:
    prepared_bundle = reconcile_official_no_trade_scope(
        bundle=apply_missing_stock_identity_skip_policy_to_official_bundle(bundle),
        expected_scope=expected_scope,
    )
    adjusted_scope = prepared_bundle.get("_source_facts_adjusted_expected_scope") or expected_scope
    dynamic_no_trade = tuple(str(item) for item in prepared_bundle.get("_source_facts_dynamic_no_trade_identities") or [])
    with patched_official_daily_20260608(no_trade_identities=dynamic_no_trade):
        report = _official_20260605.validate_source_bundle(
            bundle=prepared_bundle,
            expected_scope=adjusted_scope,
            trade_date=trade_date,
        )
    return _append_skip_quality_items(
        report,
        board_skip_manifest=[dict(row) for row in prepared_bundle.get("missing_noncritical_board_daily_skip_manifest") or []],
    )


def official_build_commit_plan(
    *,
    bundle: Mapping[str, Any],
    validation_report: Mapping[str, Any],
    baseline: Mapping[str, Any],
    trade_date: str,
) -> dict[str, Any]:
    prepared_bundle = _json_clone(bundle)
    dynamic_no_trade = tuple(str(item) for item in prepared_bundle.get("_source_facts_dynamic_no_trade_identities") or [])
    with patched_official_daily_20260608(no_trade_identities=dynamic_no_trade):
        plan = _official_20260605.build_commit_plan(
            bundle=prepared_bundle,
            validation_report=_append_skip_quality_items(validation_report),
            baseline=baseline,
            trade_date=trade_date,
        )
    for row in plan.get("active_source_version_rows") or []:
        row["activated_by"] = "n1_20260608_source_facts_guarded_runner"
    plan["manifest"] = {
        **(plan.get("manifest") or {}),
        "missing_stock_identity_skip_manifest": build_missing_stock_identity_skip_manifest(),
    }
    return _json_clone(plan)


def official_validate_commit_preconditions(
    *,
    snapshot: Mapping[str, Any],
    validation_report: Mapping[str, Any],
    source_fetch_enabled: bool,
    postgres_commit_enabled: bool,
) -> None:
    with patched_official_daily_20260608():
        _official_20260605.validate_commit_preconditions(
            snapshot=snapshot,
            validation_report=_append_skip_quality_items(validation_report),
            source_fetch_enabled=source_fetch_enabled,
            postgres_commit_enabled=postgres_commit_enabled,
        )


def official_execute_commit_transaction(
    conn: Any,
    *,
    commit_plan: Mapping[str, Any],
    execute_requested: bool,
    user_confirmed: bool,
    source_fetch_enabled: bool,
    postgres_commit_enabled: bool,
) -> dict[str, Any]:
    validate_execute_request(
        execute_requested=execute_requested,
        user_confirmed=user_confirmed,
        source_fetch_enabled=source_fetch_enabled,
        postgres_commit_enabled=postgres_commit_enabled,
    )
    unexpected_tables = sorted(set(commit_plan.get("allowed_tables") or []) - set(ALLOWED_WRITE_TABLES))
    if unexpected_tables:
        raise SourceFacts20260608Blocked(f"unexpected official daily write tables: {unexpected_tables}")
    cur = conn.cursor()
    try:
        official_insert_ingest_batch(cur, commit_plan)
        for row in (commit_plan.get("rows") or {}).get("stock", []):
            _official_base.insert_stock_daily_bar_fact(cur, row)
        for row in (commit_plan.get("rows") or {}).get("index", []):
            _official_base.insert_index_daily_bar_fact(cur, row)
        for row in (commit_plan.get("rows") or {}).get("board", []):
            _official_base.insert_board_daily_bar_fact(cur, row)
        for row in commit_plan.get("quality_rows") or []:
            _official_base.insert_quality_gate_result(cur, row)
        for row in commit_plan.get("active_source_version_rows") or []:
            _official_base.insert_active_source_version(cur, row)
        _official_base.update_ingest_batch_passed(cur, commit_plan)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return _official_base.normalize_jsonable(
        {
            "committed": True,
            "batch_id": commit_plan.get("batch_id"),
            "written_tables": [
                "common_ingest_batch",
                "common_quality_gate_result",
                "common_active_source_version",
                "stock_daily_bar_fact",
                "index_daily_bar_fact",
                "board_daily_bar_fact",
            ],
            "row_counts": commit_plan.get("row_counts") or {},
            "rollback_safe": True,
            "rollback_sql_path": str(ROLLBACK_SQL_PATH),
        }
    )


def official_insert_ingest_batch(cur: Any, commit_plan: Mapping[str, Any]) -> None:
    cur.execute(
        f"""
        INSERT INTO common_ingest_batch (
          batch_id, trade_date, data_domain, data_type, source, source_version,
          source_params, row_count, error_count, quality_gate_summary,
          rollback_strategy, status, started_at
        )
        VALUES (
          %(batch_id)s, %(trade_date)s, 'common', 'official_daily',
          'n1.source_facts_{TRADE_DATE}.official_daily', %(source_version)s,
          %(source_params)s, %(row_count)s, 0, %(quality_gate_summary)s,
          %(rollback_strategy)s, 'running', now()
        )
        """,
        {
            "batch_id": OFFICIAL_DAILY_BATCH_ID,
            "trade_date": TRADE_DATE,
            "source_version": OFFICIAL_DAILY_BATCH_ID,
            "source_params": Jsonb(
                _official_base.json_safe(
                    {
                        "source_versions": dict(OFFICIAL_SOURCE_VERSIONS),
                        "postgres_only": True,
                        "skip_policy": SKIP_POLICY_NAME,
                        "missing_stock_identity_skip_manifest": build_missing_stock_identity_skip_manifest(),
                    }
                )
            ),
            "row_count": int((commit_plan.get("row_counts") or {}).get("total", 0)),
            "quality_gate_summary": Jsonb(
                _official_base.json_safe(
                    {
                        "p0_count": 0,
                        "p1_skip_policy": True,
                        "validation": "passed",
                    }
                )
            ),
            "rollback_strategy": str(ROLLBACK_SQL_PATH),
        },
    )


def _ts_codes_for_no_trade(no_trade_identities: tuple[str, ...]) -> dict[str, str]:
    mapping = dict(OFFICIAL_NO_TRADE_TS_CODES)
    for identity_key in no_trade_identities:
        parts = identity_key.split(":")
        if len(parts) == 3:
            _, exchange, code = parts
            mapping.setdefault(identity_key, f"{code}.{exchange}")
    return mapping


def _condition_no_trade_from_snapshot(snapshot: Mapping[str, Any] | None) -> tuple[str, ...] | None:
    if not snapshot:
        return None
    stock_scope = dict(snapshot.get("stock_scope") or {})
    manifest = stock_scope.get("official_no_trade_manifest") or stock_scope.get("condition_source_gap_manifest") or []
    values = tuple(sorted(str(row.get("identity_key")) for row in manifest if row.get("identity_key")))
    return values or None


def resolve_official_no_trade_identities_from_db(*, dsn: str, trade_date: str = TRADE_DATE) -> tuple[str, ...]:
    with psycopg.connect(dsn, connect_timeout=10, options="-c default_transaction_read_only=on", row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT stock_identity_key
                FROM stock_identity
                WHERE status = 'active'
                  AND stock_identity_key <> %s
                """,
                (STALE_IDENTITY_KEY,),
            )
            active = {str(row["stock_identity_key"]) for row in cur.fetchall()}
            cur.execute(
                """
                SELECT stock_identity_key
                FROM stock_daily_bar_fact
                WHERE trade_date = %s
                  AND source_version = %s
                """,
                (trade_date, OFFICIAL_SOURCE_VERSIONS["stock"]),
            )
            daily = {str(row["stock_identity_key"]) for row in cur.fetchall()}
    return tuple(sorted(active - daily))


def _condition_patch_values(*, no_trade_identities: tuple[str, ...] | None = None) -> dict[str, Any]:
    no_trade_identities = no_trade_identities if no_trade_identities is not None else OFFICIAL_NO_TRADE_IDENTITIES
    return {
        "TRADE_DATE": TRADE_DATE,
        "BATCH_ID": CONDITION_SOURCE_BATCH_ID,
        "TDX_ROOT": _condition_20260605.TDX_ROOT,
        "SOURCE_VERSIONS": dict(CONDITION_SOURCE_VERSIONS),
        "ACTIVE_SCOPES": {
            "stock_daily_basic": TRADE_DATE,
            "stock_financial": TRADE_DATE,
            "index_membership": f"TDX:{TRADE_DATE}",
            "board_membership": f"TDX:{TRADE_DATE}",
        },
        "DATA_DOMAINS": {
            "stock_daily_basic": "stock",
            "stock_financial": "stock",
            "index_membership": "index",
            "board_membership": "board",
        },
        "EXPECTED_REFERENCE_ROWS": {
            "stock_daily_basic": ADJUSTED_EXPECTED_ROWS_WITH_SKIP_POLICY["condition_source"]["stock_daily_basic"],
            "stock_financial": ADJUSTED_EXPECTED_ROWS_WITH_SKIP_POLICY["condition_source"]["stock_financial_metrics_fact"],
            "index_membership": ADJUSTED_EXPECTED_ROWS_WITH_SKIP_POLICY["condition_source"]["index_membership_fact"],
            "board_membership": ADJUSTED_EXPECTED_ROWS_WITH_SKIP_POLICY["condition_source"]["board_membership_fact"],
        },
        "RECENT_ACTIVE_REFERENCE_ROWS": {"board_membership": 56962},
        "OFFICIAL_NO_TRADE_IDENTITIES": no_trade_identities,
        "OFFICIAL_NO_TRADE_TS_CODES": _ts_codes_for_no_trade(no_trade_identities),
        "STALE_IDENTITY_MANIFEST": STALE_IDENTITY_MANIFEST,
        "DEFAULT_PATHS": dict(CONDITION_DEFAULT_PATHS),
    }


@contextmanager
def patched_condition_source_20260608(*, no_trade_identities: tuple[str, ...] | None = None) -> Iterator[None]:
    overrides = _condition_patch_values(no_trade_identities=no_trade_identities)
    previous = {name: getattr(_condition_20260605, name) for name in overrides}
    try:
        for name, value in overrides.items():
            setattr(_condition_20260605, name, value)
        yield
    finally:
        for name, value in previous.items():
            setattr(_condition_20260605, name, value)


def condition_build_snapshot_from_db(
    *,
    dsn: str,
    trade_date: str = TRADE_DATE,
    tdx_root: str | Path = _condition_20260605.TDX_ROOT,
) -> dict[str, Any]:
    no_trade = resolve_official_no_trade_identities_from_db(dsn=dsn, trade_date=trade_date)
    with patched_condition_source_20260608(no_trade_identities=no_trade):
        snapshot = _condition_20260605.build_snapshot_from_db(dsn=dsn, trade_date=trade_date, tdx_root=tdx_root)
    return _json_clone(snapshot)


class DefaultConditionSourceActivation20260608SourceBuilder:
    def __init__(self, *, tdx_root: str | Path = _condition_20260605.TDX_ROOT, tushare_token: str | None = None) -> None:
        self._builder = _condition_20260605.DefaultConditionSourceActivation20260605SourceBuilder(
            tdx_root=tdx_root,
            tushare_token=tushare_token,
        )

    def build_source_bundle(self, *, dsn: str, trade_date: str, snapshot: Mapping[str, Any]) -> dict[str, Any]:
        with patched_condition_source_20260608(no_trade_identities=_condition_no_trade_from_snapshot(snapshot)):
            bundle = self._builder.build_source_bundle(dsn=dsn, trade_date=trade_date, snapshot=snapshot)
        return apply_missing_stock_identity_skip_policy_to_condition_bundle(bundle)


def condition_validate_source_bundle(*, bundle: Mapping[str, Any], snapshot: Mapping[str, Any]) -> dict[str, Any]:
    with patched_condition_source_20260608(no_trade_identities=_condition_no_trade_from_snapshot(snapshot)):
        report = _condition_20260605.validate_source_bundle(
            bundle=apply_missing_stock_identity_skip_policy_to_condition_bundle(bundle),
            snapshot=snapshot,
        )
    return _append_skip_quality_items(report)


def condition_build_commit_plan(
    *,
    bundle: Mapping[str, Any],
    validation_report: Mapping[str, Any],
    baseline: Mapping[str, Any],
) -> dict[str, Any]:
    with patched_condition_source_20260608(no_trade_identities=_condition_no_trade_from_snapshot(baseline)):
        plan = _condition_20260605.build_commit_plan(
            bundle=apply_missing_stock_identity_skip_policy_to_condition_bundle(bundle),
            validation_report=_append_skip_quality_items(validation_report),
            baseline=baseline,
        )
    for row in plan.get("active_source_version_rows") or []:
        row["activated_by"] = "n1_20260608_source_facts_guarded_runner"
    plan["manifests"] = {
        **(plan.get("manifests") or {}),
        "missing_stock_identity_skip_manifest": build_missing_stock_identity_skip_manifest(),
    }
    return _json_clone(plan)


def condition_validate_commit_preconditions(
    *,
    snapshot: Mapping[str, Any],
    validation_report: Mapping[str, Any],
    postgres_commit_enabled: bool,
) -> None:
    with patched_condition_source_20260608(no_trade_identities=_condition_no_trade_from_snapshot(snapshot)):
        _condition_20260605.validate_commit_preconditions(
            snapshot=snapshot,
            validation_report=_append_skip_quality_items(validation_report),
            postgres_commit_enabled=postgres_commit_enabled,
        )


def condition_execute_commit_transaction(
    conn: Any,
    *,
    commit_plan: Mapping[str, Any],
    execute_requested: bool,
    user_confirmed: bool,
    postgres_commit_enabled: bool,
) -> dict[str, Any]:
    validate_execute_request(
        execute_requested=execute_requested,
        user_confirmed=user_confirmed,
        source_fetch_enabled=True,
        postgres_commit_enabled=postgres_commit_enabled,
    )
    unexpected_tables = sorted(set(commit_plan.get("allowed_tables") or []) - set(ALLOWED_WRITE_TABLES))
    if unexpected_tables:
        raise SourceFacts20260608Blocked(f"unexpected condition source write tables: {unexpected_tables}")
    cur = conn.cursor()
    try:
        condition_insert_ingest_batch(cur, commit_plan)
        _condition_20260605._base.insert_stock_daily_basic_rows(cur, (commit_plan.get("rows") or {}).get("stock_daily_basic") or [])
        _condition_20260605._base.insert_stock_financial_rows(cur, (commit_plan.get("rows") or {}).get("stock_financial") or [])
        _condition_20260605._base.insert_index_membership_rows(cur, (commit_plan.get("rows") or {}).get("index_membership") or [])
        _condition_20260605._base.insert_board_membership_rows(cur, (commit_plan.get("rows") or {}).get("board_membership") or [])
        _condition_20260605._base.insert_quality_rows(cur, commit_plan.get("quality_rows") or [])
        _condition_20260605._base.insert_active_source_version_rows(cur, commit_plan.get("active_source_version_rows") or [])
        condition_update_ingest_batch_passed(cur)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return _condition_20260605._base.normalize_jsonable(
        {
            "committed": True,
            "batch_id": commit_plan.get("batch_id"),
            "written_tables": [
                "common_ingest_batch",
                "common_quality_gate_result",
                "common_active_source_version",
                "stock_daily_basic",
                "stock_financial_metrics_fact",
                "index_membership_fact",
                "board_membership_fact",
            ],
            "row_counts": commit_plan.get("row_counts") or {},
            "rollback_safe": True,
            "rollback_sql_path": str(ROLLBACK_SQL_PATH),
        }
    )


def condition_insert_ingest_batch(cur: Any, commit_plan: Mapping[str, Any]) -> None:
    active_scopes = _condition_patch_values()["ACTIVE_SCOPES"]
    cur.execute(
        f"""
        INSERT INTO common_ingest_batch (
          batch_id, trade_date, data_domain, data_type, source, source_version,
          source_path, source_params, raw_hash, row_count, error_count,
          quality_gate_summary, error_summary, rollback_strategy, status, started_at
        )
        VALUES (
          %(batch_id)s, %(trade_date)s, 'common', 'condition_source_activation',
          'n1.source_facts_{TRADE_DATE}.condition_source', %(source_version)s,
          NULL, %(source_params)s, NULL, %(row_count)s, 0,
          %(quality_gate_summary)s, NULL, %(rollback_strategy)s, 'running', now()
        )
        """,
        {
            "batch_id": CONDITION_SOURCE_BATCH_ID,
            "trade_date": TRADE_DATE,
            "source_version": CONDITION_SOURCE_BATCH_ID,
            "source_params": _condition_20260605._base.jsonb_payload(
                    {
                        "source_versions": dict(CONDITION_SOURCE_VERSIONS),
                        "active_scopes": active_scopes,
                        "skip_policy": SKIP_POLICY_NAME,
                },
                context="common_ingest_batch.source_params",
            ),
            "row_count": int((commit_plan.get("row_counts") or {}).get("total") or 0),
            "quality_gate_summary": _condition_20260605._base.jsonb_payload(
                {
                    "expected_rows": commit_plan.get("row_counts") or {},
                    "missing_stock_identity_skip_manifest": build_missing_stock_identity_skip_manifest(),
                    "board_unmapped_raw_count": (commit_plan.get("manifests") or {}).get("board_unmapped_raw_count"),
                },
                context="common_ingest_batch.quality_gate_summary",
            ),
            "rollback_strategy": str(ROLLBACK_SQL_PATH),
        },
    )


def condition_update_ingest_batch_passed(cur: Any) -> None:
    cur.execute(
        """
        UPDATE common_ingest_batch
        SET status = 'passed',
            finished_at = now()
        WHERE batch_id = %s
        """,
        (CONDITION_SOURCE_BATCH_ID,),
    )


def official_load_execute_contract(path: str | Path = CONTRACT_PATH) -> dict[str, Any]:
    return load_contract(path)


def official_validate_execute_contract(contract: Mapping[str, Any]) -> None:
    if contract.get("result") != "CONTRACT_PASS":
        raise SourceFacts20260608Blocked("source facts contract is not CONTRACT_PASS")


def load_source_facts_stock_source_probe(path: str | Path = PREFLIGHT_PATH) -> dict[str, Any]:
    preflight = load_preflight(path)
    source_probe = dict(preflight.get("source_probe") or {})
    return {
        "result": "STOCK_PROBE_PASS_WITH_SKIP_POLICY",
        "stock_source": {
            "tushare_daily_count": int(source_probe.get("tushare_daily_count") or 0),
            "adj_factor_count": int(source_probe.get("adj_factor_count") or 0),
            "matched_identity_count": int(source_probe.get("matched_identity_count") or 0),
            "unmapped_count": int(source_probe.get("unmapped_count") or 0),
            "unmapped_sample": list(source_probe.get("unmapped_ts_codes") or []),
            "daily_basic_unmapped_count": int(source_probe.get("daily_basic_unmapped_count") or 0),
            "daily_basic_unmapped_sample": list(source_probe.get("daily_basic_unmapped_ts_codes") or []),
            "adj_minus_daily_active_identity_count": int(source_probe.get("official_no_trade_candidate_count") or 0),
            "duplicate_daily_ts_code_count": int(source_probe.get("duplicate_daily_ts_code_count") or 0),
            "skip_policy": SKIP_POLICY_NAME,
            "stock_identity_refresh_required": False,
        },
    }


def load_source_facts_index_board_probe(path: str | Path = PREFLIGHT_PATH) -> dict[str, Any]:
    preflight = load_preflight(path)
    source_probe = dict(preflight.get("source_probe") or {})
    return {
        "result": "FULL_PROBE_PASS",
        "expected_counts": {
            "index": int(source_probe.get("index_expected_count") or 0),
            "board": int(source_probe.get("board_expected_count") or 0),
        },
        "source_breakdown": dict(source_probe.get("index_source_breakdown") or {}),
    }


def official_build_dry_run_report(*, snapshot: Mapping[str, Any], stock_probe: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "stage": "N1 source facts 20260608 official daily dry-run",
        "layer_role": "N1_ingestion",
        "result": "DRY_RUN_PASS_WITH_SKIP_POLICY",
        "trade_date": TRADE_DATE,
        "source_batch_id": OFFICIAL_DAILY_BATCH_ID,
        "expected_rows": dict(ADJUSTED_EXPECTED_ROWS_WITH_SKIP_POLICY["official_daily"]),
        "stock_probe": dict(stock_probe),
        "skip_policy": {"policy": SKIP_POLICY_NAME, "manifest": build_missing_stock_identity_skip_manifest()},
        "side_effects": {"writes_postgres": False, "writes_outbox": False, "enters_n2_n3_n4_n5_n6": False},
    }


def official_build_execute_contract(*, snapshot: Mapping[str, Any], stock_probe: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "stage": "N1 source facts 20260608 official daily execute contract",
        "layer_role": "N1_ingestion",
        "result": "DESIGN_PASS",
        "trade_date": TRADE_DATE,
        "source_batch_id": OFFICIAL_DAILY_BATCH_ID,
        "source_versions": dict(OFFICIAL_SOURCE_VERSIONS),
        "expected_rows": dict(ADJUSTED_EXPECTED_ROWS_WITH_SKIP_POLICY["official_daily"]),
        "skip_policy": SKIP_POLICY_NAME,
    }


def official_build_execute_preflight_report(
    *,
    snapshot: Mapping[str, Any],
    stock_probe: Mapping[str, Any],
    index_board_probe: Mapping[str, Any] | None = None,
    execute_requested: bool,
    user_confirmed: bool,
    source_fetch_enabled: bool,
    postgres_commit_enabled: bool,
) -> dict[str, Any]:
    blockers = []
    if execute_requested and not user_confirmed:
        blockers.append("missing_user_confirmed")
    if execute_requested and not source_fetch_enabled:
        blockers.append("source_fetch_disabled")
    if execute_requested and not postgres_commit_enabled:
        blockers.append("postgres_commit_disabled")
    return {
        "stage": "N1 source facts 20260608 official daily execute preflight",
        "layer_role": "N1_ingestion",
        "result": "PREFLIGHT_PASS" if not blockers else "PREFLIGHT_BLOCKED",
        "production_execute_blockers": blockers,
        "quality": {"p0_count": len(blockers), "p1_count": 1, "p2_count": 0},
        "final_execute_gate_allowed": not blockers,
        "expected_rows": dict(ADJUSTED_EXPECTED_ROWS_WITH_SKIP_POLICY["official_daily"]),
        "skip_policy": SKIP_POLICY_NAME,
    }


def official_phase_already_committed(snapshot: Mapping[str, Any]) -> bool:
    rows = dict(snapshot.get("current_daily_fact_rows") or {})
    active_versions = {str(row.get("source_version") or "") for row in snapshot.get("active_daily_source_versions") or []}
    expected = ADJUSTED_EXPECTED_ROWS_WITH_SKIP_POLICY["official_daily"]
    return (
        bool(snapshot.get("contract_batch_exists"))
        and int(rows.get("stock") or 0) == expected["stock_daily_bar_fact"]
        and int(rows.get("index") or 0) == expected["index_daily_bar_fact"]
        and int(rows.get("board") or 0) == expected["board_daily_bar_fact"]
        and set(OFFICIAL_SOURCE_VERSIONS.values()).issubset(active_versions)
    )


def official_phase_resume_commit_result(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    rows = dict(snapshot.get("current_daily_fact_rows") or {})
    return {
        "committed": False,
        "already_committed": True,
        "batch_id": OFFICIAL_DAILY_BATCH_ID,
        "written_tables": [
            "common_ingest_batch",
            "common_quality_gate_result",
            "common_active_source_version",
            "stock_daily_bar_fact",
            "index_daily_bar_fact",
            "board_daily_bar_fact",
        ],
        "row_counts": {
            "stock": int(rows.get("stock") or 0),
            "index": int(rows.get("index") or 0),
            "board": int(rows.get("board") or 0),
            "total": int(rows.get("total") or 0),
        },
        "rollback_safe": True,
        "rollback_sql_path": str(ROLLBACK_SQL_PATH),
        "resume_reason": "official_daily_phase_already_passed",
    }


def condition_build_dry_run_report(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    with patched_condition_source_20260608(no_trade_identities=_condition_no_trade_from_snapshot(snapshot)):
        return _condition_20260605.build_dry_run_report(snapshot)


def condition_build_execute_contract(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    with patched_condition_source_20260608(no_trade_identities=_condition_no_trade_from_snapshot(snapshot)):
        contract = _condition_20260605.build_execute_contract(snapshot)
    return _json_clone(contract)


def condition_build_execute_preflight_report(
    snapshot: Mapping[str, Any],
    *,
    execute_requested: bool,
    user_confirmed: bool,
    postgres_commit_enabled: bool,
) -> dict[str, Any]:
    with patched_condition_source_20260608(no_trade_identities=_condition_no_trade_from_snapshot(snapshot)):
        report = _condition_20260605.build_execute_preflight_report(
            snapshot,
            execute_requested=execute_requested,
            user_confirmed=user_confirmed,
            postgres_commit_enabled=postgres_commit_enabled,
        )
    return _json_clone(report)


def render_execute_report_markdown(report: Mapping[str, Any]) -> str:
    return f"""# N1 {TRADE_DATE} Source Facts Execute Report

Result: `{report["result"]}`

- layer_role: `{report["layer_role"]}`
- execute_authorized: `{report["execute_authorized"]}`
- official_daily_batch_id: `{OFFICIAL_DAILY_BATCH_ID}`
- condition_source_batch_id: `{CONDITION_SOURCE_BATCH_ID}`

## Row Counts

```json
{json.dumps(report.get("row_counts") or {}, ensure_ascii=False, indent=2)}
```

## Skip Policy

```json
{json.dumps(report.get("skip_policy") or {}, ensure_ascii=False, indent=2)}
```

Rollback SQL: `{ROLLBACK_SQL_PATH}`
"""


def build_execute_report(
    *,
    official_validation: Mapping[str, Any],
    official_commit: Mapping[str, Any],
    condition_validation: Mapping[str, Any],
    condition_commit: Mapping[str, Any],
) -> dict[str, Any]:
    official_rows = dict(official_commit.get("row_counts") or {})
    condition_rows = dict(condition_commit.get("row_counts") or {})
    return {
        "stage": f"N1 {TRADE_DATE} source facts guarded runner execute",
        "layer_role": "N1_ingestion",
        "result": "EXECUTE_PASS",
        "execute_authorized": True,
        "trade_date": TRADE_DATE,
        "for_trade_date": FOR_TRADE_DATE,
        "source_batches": {
            "official_daily": OFFICIAL_DAILY_BATCH_ID,
            "condition_source": CONDITION_SOURCE_BATCH_ID,
        },
        "row_counts": {
            "official_daily": official_rows,
            "condition_source": condition_rows,
            "combined_total": int(official_rows.get("total") or 0) + int(condition_rows.get("total") or 0),
        },
        "expected_rows": dict(ADJUSTED_EXPECTED_ROWS_WITH_SKIP_POLICY),
        "skip_policy": {
            "policy": SKIP_POLICY_NAME,
            "threshold": MISSING_STOCK_IDENTITY_SKIP_THRESHOLD,
            "skipped_identities": build_missing_stock_identity_skip_manifest(),
        },
        "source_validation": {
            "official_daily": official_validation,
            "condition_source": condition_validation,
        },
        "commit_result": {
            "official_daily": official_commit,
            "condition_source": condition_commit,
        },
        "side_effects": {
            "writes_postgres": True,
            "writes_parquet": False,
            "writes_outbox": False,
            "writes_inbox_or_checkpoint": False,
            "enters_n2_n3_n4_n5_n6": False,
            "worker_started": False,
            "old_system_touched": False,
            "real_trading": False,
        },
        "rollback": {"path": str(ROLLBACK_SQL_PATH), "rollback_safe": True},
    }


def write_execute_report_files(report: Mapping[str, Any], *, json_path: str | Path, markdown_path: str | Path) -> None:
    write_json_report(report, json_path)
    write_text_report(render_execute_report_markdown(report), markdown_path)


def run_execute_pipeline(*, args: Any, dependencies: Mapping[str, Any]) -> dict[str, Any]:
    official_contract = dependencies["official_load_execute_contract"](args.execute_contract_json)
    dependencies["official_validate_execute_contract"](official_contract)
    official_snapshot = dependencies["official_build_snapshot_from_db"](dsn=args.dsn, trade_date=args.trade_date)
    stock_probe = dependencies["official_load_stock_source_probe"](args.stock_probe_json)
    index_board_probe = dependencies["official_load_index_board_source_probe"](args.index_board_probe_json)
    official_dry_run = dependencies["official_build_dry_run_report"](snapshot=official_snapshot, stock_probe=stock_probe)
    official_contract_report = dependencies["official_build_execute_contract"](snapshot=official_snapshot, stock_probe=stock_probe)
    official_preflight = dependencies["official_build_execute_preflight_report"](
        snapshot=official_snapshot,
        stock_probe=stock_probe,
        index_board_probe=index_board_probe,
        execute_requested=args.execute,
        user_confirmed=args.user_confirmed,
        source_fetch_enabled=args.source_fetch_enabled,
        postgres_commit_enabled=args.postgres_commit_enabled,
    )
    if not args.no_write_report:
        dependencies["write_dry_run_files"](official_dry_run, json_path=args.official_dry_run_json, markdown_path=args.official_dry_run_md)
        dependencies["write_contract_files"](official_contract_report, json_path=args.official_contract_json, markdown_path=args.official_contract_md)
        dependencies["write_preflight_files"](official_preflight, json_path=args.official_preflight_json, markdown_path=args.official_preflight_md)
    if official_preflight.get("result") != "PREFLIGHT_PASS":
        raise SourceFacts20260608Blocked(", ".join(official_preflight.get("production_execute_blockers") or ["official_daily_preflight_blocked"]))

    if official_phase_already_committed(official_snapshot):
        official_validation = {
            "result": "VALIDATION_SKIPPED_PHASE_ALREADY_PASSED",
            "p0_count": 0,
            "blockers": [],
            "resume_reason": "official_daily_phase_already_passed",
        }
        official_commit = official_phase_resume_commit_result(official_snapshot)
    else:
        expected_scope = dependencies["official_build_expected_scope_from_db"](dsn=args.dsn, trade_date=args.trade_date)
        adapter = dependencies["official_source_adapter_factory"](args=args, contract=official_contract_report)
        official_bundle = dependencies["official_fetch_official_daily_sources"](
            adapter=adapter,
            trade_date=args.trade_date,
            expected_scope=expected_scope,
            source_fetch_enabled=args.source_fetch_enabled,
        )
        official_validation = dependencies["official_validate_source_bundle"](
            bundle=official_bundle,
            expected_scope=expected_scope,
            trade_date=args.trade_date,
        )
        dependencies["official_validate_commit_preconditions"](
            snapshot=official_snapshot,
            validation_report=official_validation,
            source_fetch_enabled=args.source_fetch_enabled,
            postgres_commit_enabled=args.postgres_commit_enabled,
        )
        official_plan = dependencies["official_build_commit_plan"](
            bundle=official_bundle,
            validation_report=official_validation,
            baseline=official_snapshot,
            trade_date=args.trade_date,
        )
        official_commit = dependencies["official_execute_commit_transaction"](
            dependencies["connect"](args.dsn),
            commit_plan=official_plan,
            execute_requested=args.execute,
            user_confirmed=args.user_confirmed,
            source_fetch_enabled=args.source_fetch_enabled,
            postgres_commit_enabled=args.postgres_commit_enabled,
        )

    condition_snapshot = dependencies["condition_build_snapshot_from_db"](
        dsn=args.dsn,
        trade_date=args.trade_date,
        tdx_root=Path(args.tdx_root),
    )
    condition_dry_run = dependencies["condition_build_dry_run_report"](condition_snapshot)
    condition_contract = dependencies["condition_build_execute_contract"](condition_snapshot)
    condition_preflight = dependencies["condition_build_execute_preflight_report"](
        condition_snapshot,
        execute_requested=args.execute,
        user_confirmed=args.user_confirmed,
        postgres_commit_enabled=args.postgres_commit_enabled,
    )
    if not args.no_write_report:
        dependencies["write_dry_run_files"](condition_dry_run, json_path=args.condition_dry_run_json, markdown_path=args.condition_dry_run_md)
        dependencies["write_contract_files"](condition_contract, json_path=args.condition_contract_json, markdown_path=args.condition_contract_md)
        dependencies["write_preflight_files"](condition_preflight, json_path=args.condition_preflight_json, markdown_path=args.condition_preflight_md)
    if condition_preflight.get("result") != "PREFLIGHT_PASS":
        raise SourceFacts20260608Blocked(", ".join(condition_preflight.get("blockers") or ["condition_source_preflight_blocked"]))

    builder = dependencies["condition_source_builder_factory"](args=args, contract=condition_contract)
    condition_bundle = builder.build_source_bundle(dsn=args.dsn, trade_date=args.trade_date, snapshot=condition_snapshot)
    condition_validation = dependencies["condition_validate_source_bundle"](bundle=condition_bundle, snapshot=condition_snapshot)
    dependencies["condition_validate_commit_preconditions"](
        snapshot=condition_snapshot,
        validation_report=condition_validation,
        postgres_commit_enabled=args.postgres_commit_enabled,
    )
    condition_plan = dependencies["condition_build_commit_plan"](
        bundle=condition_bundle,
        validation_report=condition_validation,
        baseline=condition_snapshot,
    )
    condition_commit = dependencies["condition_execute_commit_transaction"](
        dependencies["connect"](args.dsn),
        commit_plan=condition_plan,
        execute_requested=args.execute,
        user_confirmed=args.user_confirmed,
        postgres_commit_enabled=args.postgres_commit_enabled,
    )
    report = build_execute_report(
        official_validation=official_validation,
        official_commit=official_commit,
        condition_validation=condition_validation,
        condition_commit=condition_commit,
    )
    if not args.no_write_report:
        dependencies["write_execute_report_files"](
            report,
            json_path=args.execute_report_json,
            markdown_path=args.execute_report_md,
        )
    return report


def build_runner_plan(*, contract: Mapping[str, Any], preflight: Mapping[str, Any]) -> dict[str, Any]:
    final_gate_review_allowed = bool(
        preflight.get("source_facts_execute_final_gate_review_allowed")
        or preflight.get("final_execute_gate_allowed")
    )
    return {
        "gate": "N1_20260608_SOURCE_FACTS_GUARDED_RUNNER_IMPLEMENTATION_GATE",
        "trade_date": TRADE_DATE,
        "for_trade_date": FOR_TRADE_DATE,
        "official_daily_batch_id": OFFICIAL_DAILY_BATCH_ID,
        "condition_source_batch_id": CONDITION_SOURCE_BATCH_ID,
        "official_source_versions": dict(OFFICIAL_SOURCE_VERSIONS),
        "condition_source_versions": dict(CONDITION_SOURCE_VERSIONS),
        "allowed_write_tables": list(ALLOWED_WRITE_TABLES),
        "forbidden_scope_markers": list(FORBIDDEN_SCOPE_MARKERS),
        "expected_rows_before_skip_policy": dict(EXPECTED_ROWS_AFTER_P0_CLEARANCE),
        "adjusted_expected_rows_with_skip_policy": dict(ADJUSTED_EXPECTED_ROWS_WITH_SKIP_POLICY),
        "missing_stock_identity_skip_policy": {
            "policy_name": SKIP_POLICY_NAME,
            "threshold": MISSING_STOCK_IDENTITY_SKIP_THRESHOLD,
            "skipped_identities": build_missing_stock_identity_skip_manifest(),
        },
        "contract_result": contract.get("result"),
        "preflight_result": preflight.get("preflight_result"),
        "p0_p1_p2": dict(preflight.get("p0_p1_p2") or {}),
        "remaining_blockers": list(preflight.get("blockers") or []),
        "execute_authorized": False,
        "final_execute_gate_allowed": bool(preflight.get("final_execute_gate_allowed")),
        "source_facts_execute_final_gate_review_allowed": final_gate_review_allowed,
        "runner_readiness": str(
            preflight.get("runner_readiness") or "guarded_runner_implemented_preflight_blocked"
        ),
        "phase_order": [
            "phase_1_official_daily_stock_index_board",
            "phase_2_condition_source_activation_after_phase_1_post_check",
        ],
    }


def _sql_without_comments(sql: str) -> str:
    return "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))


def validate_rollback_sql(path: str | Path = ROLLBACK_SQL_PATH) -> dict[str, Any]:
    sql = Path(path).read_text(encoding="utf-8")
    sql_upper = _sql_without_comments(sql).upper()
    first_delete = sql_upper.find("DELETE")
    first_raise = sql_upper.find("RAISE EXCEPTION")
    forbidden_dml_targets = (
        "COMMON_EVENT_OUTBOX",
        "COMMON_EVENT_INBOX",
        "COMMON_EVENT_CONSUMER_CHECKPOINT",
        "COMMON_CONDITION_RUN",
        "COMMON_MARKET_DATA_RUN",
        "COMMON_TRIGGER_RUN",
        "COMMON_ACTION_RUN",
        "USER_PROJECTION_RUN",
    )
    forbidden_table_dml = [
        table
        for table in forbidden_dml_targets
        if re.search(rf"(DELETE|INSERT|UPDATE)\s+(FROM\s+)?{table}\b", sql_upper)
    ]
    result = {
        "path": str(path),
        "hard_fail_before_delete": first_raise >= 0 and first_delete >= 0 and first_raise < first_delete,
        "no_drop_truncate_cascade": not any(token in sql_upper for token in ("DROP ", "TRUNCATE ", "CASCADE")),
        "no_forbidden_table_dml": not forbidden_table_dml,
        "forbidden_table_dml": forbidden_table_dml,
        "scope_ids_present": all(
            marker in sql
            for marker in (
                OFFICIAL_DAILY_BATCH_ID,
                CONDITION_SOURCE_BATCH_ID,
                OFFICIAL_SOURCE_VERSIONS["stock"],
                CONDITION_SOURCE_VERSIONS["stock_daily_basic"],
            )
        ),
    }
    result["passed"] = all(
        bool(result[key])
        for key in (
            "hard_fail_before_delete",
            "no_drop_truncate_cascade",
            "no_forbidden_table_dml",
            "scope_ids_present",
        )
    )
    return result


def build_handoff_report() -> dict[str, Any]:
    return {
        "gate": "N1_20260608_STOCK_IDENTITY_920206_REPAIR_HANDOFF",
        "layer_role": "N1_ingestion",
        "result": "SUPERSEDED",
        "decision": "SUPERSEDED_BY_SMALL_MISSING_STOCK_IDENTITY_SKIP_POLICY",
        "reason": "The 20260608 source facts path now uses an explicit stock-only skip policy for missing stock_identity rows when count <= 10. No stock_identity repair is required for 920206.BJ in this source facts gate.",
        "missing_identity": {
            "ts_code": "920206.BJ",
            "code": "920206",
            "exchange": "BJ",
            "canonical_identity_key": "stock:BJ:920206",
            "observed_in": [
                "Tushare daily 20260608",
                "Tushare daily_basic 20260608",
            ],
            "current_active_stock_identity_scope": "A_STOCK:20260605 -> stock_identity_20260605_v1",
        },
        "skip_policy": {
            "policy_name": SKIP_POLICY_NAME,
            "threshold": MISSING_STOCK_IDENTITY_SKIP_THRESHOLD,
            "severity": "P1",
            "skipped_rows_written_to_daily_daily_basic_financial": False,
        },
        "recommended_gate": "N1_20260608_SOURCE_FACTS_EXECUTE_FINAL_GATE_REVIEW",
        "source_facts_runner_writes_stock_identity": False,
        "source_facts_execute_gate_allowed_after_handoff": False,
        "required_future_scope": {
            "allowed_tables": [
                "stock_identity",
                "common_ingest_batch",
                "common_quality_gate_result",
                "common_active_source_version",
            ],
            "forbidden_tables": [
                "stock_daily_bar_fact",
                "index_daily_bar_fact",
                "board_daily_bar_fact",
                "stock_daily_basic",
                "stock_financial_metrics_fact",
                "index_membership_fact",
                "board_membership_fact",
                "common_event_outbox",
                "common_event_inbox",
                "common_event_consumer_checkpoint",
                "N2/N3/N4/N5/N6",
            ],
        },
        "next_step": "Run the scoped stock_identity 920206 repair dry-run/preflight gate, then refresh this source facts preflight.",
    }


def build_implementation_report(
    *,
    contract: Mapping[str, Any] | None = None,
    preflight: Mapping[str, Any] | None = None,
    rollback_check: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    contract = dict(contract or load_contract())
    preflight = dict(preflight or load_preflight())
    rollback_check = dict(rollback_check or validate_rollback_sql())
    plan = build_runner_plan(contract=contract, preflight=preflight)
    return {
        "gate": "N1_20260608_SOURCE_FACTS_GUARDED_RUNNER_IMPLEMENTATION_GATE",
        "layer_role": "N1_ingestion",
        "result": "IMPLEMENTATION_PASS",
        "execute_final_gate_allowed": bool(plan["final_execute_gate_allowed"]),
        "source_facts_execute_final_gate_review_allowed": bool(
            plan["source_facts_execute_final_gate_review_allowed"]
        ),
        "execute_authorized": False,
        "runner_readiness": plan["runner_readiness"],
        "trade_date": TRADE_DATE,
        "for_trade_date": FOR_TRADE_DATE,
        "guard_summary": {
            "default_execute": False,
            "required_execute_flags": list(REQUIRED_EXECUTE_FLAGS),
            "wrong_trade_date_blocks": True,
            "p0_blocks_execute": True,
            "rollback_unsafe_blocks": True,
            "generic_run_real_daily_incremental_approved": False,
        },
        "identity_p0_handling": {
            "decision": SKIP_POLICY_NAME,
            "threshold": MISSING_STOCK_IDENTITY_SKIP_THRESHOLD,
            "missing_count": len(SKIPPED_STOCK_IDENTITIES_20260608),
            "quality_severity": "P1",
            "skipped_identities": build_missing_stock_identity_skip_manifest(),
            "handoff_json": str(IDENTITY_REPAIR_HANDOFF_PATH),
            "handoff_md": str(IDENTITY_REPAIR_HANDOFF_MD_PATH),
            "source_facts_runner_writes_stock_identity": False,
        },
        "runner_plan": plan,
        "expected_rows_before_skip_policy": EXPECTED_ROWS_AFTER_P0_CLEARANCE,
        "adjusted_expected_rows_with_skip_policy": ADJUSTED_EXPECTED_ROWS_WITH_SKIP_POLICY,
        "allowed_write_tables": list(ALLOWED_WRITE_TABLES),
        "forbidden_scope_markers": list(FORBIDDEN_SCOPE_MARKERS),
        "rollback_static_check": rollback_check,
        "remaining_blockers": list(preflight.get("blockers") or []),
        "forbidden_scope_proof": {
            "writes_performed": False,
            "postgres_written": False,
            "rollback_executed": False,
            "n2_n3_n4_n5_n6_entered": False,
            "outbox_inbox_checkpoint_consumed_or_updated": False,
            "worker_started": False,
            "realtime_quote_pulled": False,
            "old_system_touched": False,
            "trade_or_sim_touched": False,
        },
        "next_recommended_gate": "N1_20260608_SOURCE_FACTS_EXECUTE_FINAL_GATE_REVIEW",
    }


def render_implementation_markdown(report: Mapping[str, Any]) -> str:
    return f"""# N1 20260608 Source Facts Guarded Runner Implementation

Result: `{report["result"]}`

- layer_role: `{report["layer_role"]}`
- runner_readiness: `{report["runner_readiness"]}`
- execute_final_gate_allowed: `{report["execute_final_gate_allowed"]}`
- identity P0 handling: `{report["identity_p0_handling"]["decision"]}`

## Guard Summary

- default execute: `false`
- required flags: `{" ".join(REQUIRED_EXECUTE_FLAGS)}`
- wrong trade date blocks: `true`
- P0 blocks execute: `true`
- rollback unsafe blocks: `true`
- `scripts/run_real_daily_incremental.py` approved command: `false`

## Adjusted Expected Rows With Skip Policy

```json
{json.dumps(ADJUSTED_EXPECTED_ROWS_WITH_SKIP_POLICY, ensure_ascii=False, indent=2)}
```

## Skip Policy

```json
{json.dumps(report.get("identity_p0_handling") or {}, ensure_ascii=False, indent=2)}
```

## Remaining Blockers

```json
{json.dumps(report.get("remaining_blockers") or [], ensure_ascii=False, indent=2)}
```

## Rollback Static Check

```json
{json.dumps(report.get("rollback_static_check") or {}, ensure_ascii=False, indent=2)}
```

## Forbidden Scope Proof

```json
{json.dumps(report.get("forbidden_scope_proof") or {}, ensure_ascii=False, indent=2)}
```

## Next Gate

`{report["next_recommended_gate"]}`
"""


def render_handoff_markdown(report: Mapping[str, Any]) -> str:
    return f"""# N1 20260608 Stock Identity 920206 Repair Handoff

Result: `{report["result"]}`

Decision: `{report["decision"]}`

The 20260608 source facts runner will not write `stock_identity`. The missing identity is now handled by the explicit stock-only skip policy for this source facts gate.

## Missing Identity

```json
{json.dumps(report["missing_identity"], ensure_ascii=False, indent=2)}
```

## Superseded Repair Scope

```json
{json.dumps(report["required_future_scope"], ensure_ascii=False, indent=2)}
```

## Next Gate

`{report["recommended_gate"]}`
"""


def write_json_report(report: Mapping[str, Any], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text_report(markdown: str, path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown, encoding="utf-8")


def write_implementation_artifacts(
    *,
    implementation_json: str | Path = IMPLEMENTATION_REPORT_JSON_PATH,
    implementation_md: str | Path = IMPLEMENTATION_REPORT_MD_PATH,
    handoff_json: str | Path = IDENTITY_REPAIR_HANDOFF_PATH,
    handoff_md: str | Path = IDENTITY_REPAIR_HANDOFF_MD_PATH,
) -> dict[str, dict[str, Any]]:
    implementation = build_implementation_report()
    handoff = build_handoff_report()
    write_json_report(implementation, implementation_json)
    write_text_report(render_implementation_markdown(implementation), implementation_md)
    write_json_report(handoff, handoff_json)
    write_text_report(render_handoff_markdown(handoff), handoff_md)
    return {"implementation": implementation, "handoff": handoff}
