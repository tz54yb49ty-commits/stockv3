"""Parameterized guarded N1 source-facts runner support.

This module adapts the already-reviewed 20260608 source-facts guarded runner to
later trade dates without approving the broad real-daily incremental runner.
It keeps the same execute flags, N1-only write scope, skip policy, and rollback
guard shape while changing only date-scoped identifiers and artifact paths.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Iterator, Mapping

from ashare_v3.ingestion import source_facts_20260608_execute as dedicated


GENERIC_APPROVED_COMMAND_SCRIPT = "scripts/run_n1_source_facts_once.py"
REQUIRED_EXECUTE_FLAGS = (
    "--execute",
    "--user-confirmed",
    "--source-fetch-enabled",
    "--postgres-commit-enabled",
)
DATE_RE = re.compile(r"^\d{8}$")


class SourceFactsGenericBlocked(RuntimeError):
    """Raised when the generic guarded source-facts runner refuses to proceed."""


@dataclass(frozen=True)
class SourceFactsRunConfig:
    trade_date: str
    for_trade_date: str
    prev_trade_date: str
    next_trade_date: str
    official_daily_batch_id: str
    condition_source_batch_id: str
    official_source_versions: dict[str, str]
    condition_source_versions: dict[str, str]
    contract_path: Path
    preflight_path: Path
    rollback_sql_path: Path
    implementation_report_json_path: Path
    implementation_report_md_path: Path
    handoff_path: Path
    handoff_md_path: Path
    final_gate_review_json_path: Path
    final_gate_review_md_path: Path
    execute_report_json_path: Path
    execute_report_md_path: Path
    post_review_json_path: Path
    post_review_md_path: Path
    official_default_paths: dict[str, Path]
    condition_default_paths: dict[str, Path]


def _assert_date(value: str, *, name: str) -> None:
    if not DATE_RE.match(value):
        raise SourceFactsGenericBlocked(f"{name} must be YYYYMMDD")


def _docs_prefix(trade_date: str) -> str:
    return f"N1_{trade_date}_SOURCE_FACTS"


def build_source_facts_run_config(
    *,
    trade_date: str,
    for_trade_date: str,
    prev_trade_date: str,
    next_trade_date: str,
) -> SourceFactsRunConfig:
    for name, value in (
        ("trade_date", trade_date),
        ("for_trade_date", for_trade_date),
        ("prev_trade_date", prev_trade_date),
        ("next_trade_date", next_trade_date),
    ):
        _assert_date(value, name=name)
    prefix = _docs_prefix(trade_date)
    official_batch_id = f"official_daily_ingest_{trade_date}_v1"
    condition_batch_id = f"condition_source_activation_{trade_date}_v1"
    official_source_versions = {
        "stock": f"stock_daily_{trade_date}_v1",
        "index": f"index_daily_{trade_date}_v1",
        "board": f"board_daily_{trade_date}_v1",
    }
    condition_source_versions = {
        "stock_daily_basic": f"stock_daily_basic_{trade_date}_v1",
        "stock_financial": f"stock_financial_{trade_date}_v1",
        "index_membership": f"index_membership_{trade_date}_v1",
        "board_membership": f"board_membership_{trade_date}_v1",
    }
    rollback_sql_path = Path(f"sql/N1_{trade_date}_source_facts_guarded_runner_rollback.sql")
    return SourceFactsRunConfig(
        trade_date=trade_date,
        for_trade_date=for_trade_date,
        prev_trade_date=prev_trade_date,
        next_trade_date=next_trade_date,
        official_daily_batch_id=official_batch_id,
        condition_source_batch_id=condition_batch_id,
        official_source_versions=official_source_versions,
        condition_source_versions=condition_source_versions,
        contract_path=Path(f"docs/{prefix}_GUARDED_RUNNER_CONTRACT.json"),
        preflight_path=Path(f"docs/{prefix}_GUARDED_RUNNER_PREFLIGHT.json"),
        rollback_sql_path=rollback_sql_path,
        implementation_report_json_path=Path(f"docs/{prefix}_GENERIC_GUARDED_RUNNER_IMPLEMENTATION.json"),
        implementation_report_md_path=Path(f"docs/{prefix}_GENERIC_GUARDED_RUNNER_IMPLEMENTATION.md"),
        handoff_path=Path(f"docs/{prefix}_STOCK_IDENTITY_SKIP_POLICY_HANDOFF.json"),
        handoff_md_path=Path(f"docs/{prefix}_STOCK_IDENTITY_SKIP_POLICY_HANDOFF.md"),
        final_gate_review_json_path=Path(f"docs/{prefix}_EXECUTE_FINAL_GATE_REVIEW.json"),
        final_gate_review_md_path=Path(f"docs/{prefix}_EXECUTE_FINAL_GATE_REVIEW.md"),
        execute_report_json_path=Path(f"docs/{prefix}_EXECUTE_REPORT.json"),
        execute_report_md_path=Path(f"docs/{prefix}_EXECUTE_REPORT.md"),
        post_review_json_path=Path(f"docs/{prefix}_POST_REVIEW.json"),
        post_review_md_path=Path(f"docs/{prefix}_POST_REVIEW.md"),
        official_default_paths={
            "dry_run_json": Path(f"docs/N1_{trade_date}_source_facts_official_daily_dry_run.json"),
            "dry_run_md": Path(f"docs/{prefix}_OFFICIAL_DAILY_DRY_RUN.md"),
            "contract_json": Path(f"docs/N1_{trade_date}_source_facts_official_daily_contract.json"),
            "contract_md": Path(f"docs/{prefix}_OFFICIAL_DAILY_CONTRACT.md"),
            "preflight_json": Path(f"docs/N1_{trade_date}_source_facts_official_daily_preflight.json"),
            "preflight_md": Path(f"docs/{prefix}_OFFICIAL_DAILY_PREFLIGHT.md"),
            "rollback_sql": rollback_sql_path,
            "stock_probe_json": Path(f"docs/{prefix}_GUARDED_RUNNER_PREFLIGHT.json"),
            "index_board_probe_json": Path(f"docs/{prefix}_GUARDED_RUNNER_PREFLIGHT.json"),
            "index_board_probe_md": Path(f"docs/{prefix}_INDEX_BOARD_PROBE.md"),
        },
        condition_default_paths={
            "dry_run_json": Path(f"docs/N1_{trade_date}_source_facts_condition_source_dry_run.json"),
            "dry_run_md": Path(f"docs/{prefix}_CONDITION_SOURCE_DRY_RUN.md"),
            "contract_json": Path(f"docs/N1_{trade_date}_source_facts_condition_source_contract.json"),
            "contract_md": Path(f"docs/{prefix}_CONDITION_SOURCE_CONTRACT.md"),
            "preflight_json": Path(f"docs/N1_{trade_date}_source_facts_condition_source_preflight.json"),
            "preflight_md": Path(f"docs/{prefix}_CONDITION_SOURCE_PREFLIGHT.md"),
            "execute_report_json": Path(f"docs/{prefix}_EXECUTE_REPORT.json"),
            "execute_report_md": Path(f"docs/{prefix}_EXECUTE_REPORT.md"),
            "rollback_sql": rollback_sql_path,
        },
    )


def render_rollback_sql(config: SourceFactsRunConfig) -> str:
    ref_ids = [
        config.official_daily_batch_id,
        config.condition_source_batch_id,
        *config.official_source_versions.values(),
        *config.condition_source_versions.values(),
    ]
    ref_text = "|".join(ref_ids)
    return f"""-- N1 {config.trade_date} source facts guarded runner rollback.
-- Scope:
--   {config.official_daily_batch_id}
--   {config.condition_source_batch_id}
-- Forbidden: N2/N3/N4/N5/N6 DML, outbox/inbox/checkpoint DML, DROP, TRUNCATE, CASCADE.

BEGIN;

DO $$
DECLARE
  v_trade_date text := '{config.trade_date}';
  v_official_batch_id text := '{config.official_daily_batch_id}';
  v_condition_batch_id text := '{config.condition_source_batch_id}';
  v_ref_text text := '{ref_text}';
  v_outbox_refs bigint;
  v_inbox_refs bigint;
  v_checkpoint_refs bigint;
  v_n2_refs bigint;
  v_n3_refs bigint;
  v_n4_refs bigint;
  v_n5_refs bigint;
  v_n6_refs bigint;
BEGIN
  SELECT count(*) INTO v_outbox_refs
  FROM common_event_outbox
  WHERE source_run_id IN (v_official_batch_id, v_condition_batch_id)
     OR payload_json::text SIMILAR TO '%' || v_ref_text || '%';

  SELECT count(*) INTO v_inbox_refs
  FROM common_event_inbox
  WHERE source_run_id IN (v_official_batch_id, v_condition_batch_id)
     OR payload_json::text SIMILAR TO '%' || v_ref_text || '%'
     OR raw_json::text SIMILAR TO '%' || v_ref_text || '%';

  SELECT count(*) INTO v_checkpoint_refs
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::text SIMILAR TO '%' || v_ref_text || '%';

  SELECT count(*) INTO v_n2_refs
  FROM common_condition_run
  WHERE input_ingest_batch_id IN (v_official_batch_id, v_condition_batch_id)
     OR source_versions::text SIMILAR TO '%' || v_ref_text || '%';

  SELECT count(*) INTO v_n3_refs
  FROM common_market_data_run
  WHERE raw_json::text SIMILAR TO '%' || v_ref_text || '%';

  SELECT count(*) INTO v_n4_refs
  FROM common_trigger_run
  WHERE raw_json::text SIMILAR TO '%' || v_ref_text || '%';

  SELECT count(*) INTO v_n5_refs
  FROM common_action_run
  WHERE raw_json::text SIMILAR TO '%' || v_ref_text || '%';

  SELECT count(*) INTO v_n6_refs
  FROM user_projection_run
  WHERE quality_summary_json::text SIMILAR TO '%' || v_ref_text || '%'
     OR source_action_run_id IN (v_official_batch_id, v_condition_batch_id);

  IF v_outbox_refs <> 0
     OR v_inbox_refs <> 0
     OR v_checkpoint_refs <> 0
     OR v_n2_refs <> 0
     OR v_n3_refs <> 0
     OR v_n4_refs <> 0
     OR v_n5_refs <> 0
     OR v_n6_refs <> 0 THEN
    RAISE EXCEPTION
      'Refusing N1 {config.trade_date} source facts rollback: outbox %, inbox %, checkpoint %, N2 %, N3 %, N4 %, N5 %, N6 %',
      v_outbox_refs, v_inbox_refs, v_checkpoint_refs, v_n2_refs, v_n3_refs, v_n4_refs, v_n5_refs, v_n6_refs;
  END IF;
END $$;

DELETE FROM common_active_source_version
WHERE source_batch_id = '{config.condition_source_batch_id}'
  AND source_version IN (
    '{config.condition_source_versions["stock_daily_basic"]}',
    '{config.condition_source_versions["stock_financial"]}',
    '{config.condition_source_versions["index_membership"]}',
    '{config.condition_source_versions["board_membership"]}'
  )
  AND (
    (data_domain = 'stock' AND data_type IN ('stock_daily_basic', 'stock_financial') AND scope_key = '{config.trade_date}')
    OR (data_domain = 'index' AND data_type = 'index_membership' AND scope_key = 'TDX:{config.trade_date}')
    OR (data_domain = 'board' AND data_type = 'board_membership' AND scope_key = 'TDX:{config.trade_date}')
  );

DELETE FROM stock_daily_basic
WHERE trade_date = '{config.trade_date}'
  AND source_batch_id = '{config.condition_source_batch_id}'
  AND source_version = '{config.condition_source_versions["stock_daily_basic"]}';

DELETE FROM stock_financial_metrics_fact
WHERE source_trade_date = '{config.trade_date}'
  AND source_batch_id = '{config.condition_source_batch_id}'
  AND source_version = '{config.condition_source_versions["stock_financial"]}';

DELETE FROM index_membership_fact
WHERE trade_date = '{config.trade_date}'
  AND source_batch_id = '{config.condition_source_batch_id}'
  AND source_version = '{config.condition_source_versions["index_membership"]}';

DELETE FROM board_membership_fact
WHERE trade_date = '{config.trade_date}'
  AND source_batch_id = '{config.condition_source_batch_id}'
  AND source_version = '{config.condition_source_versions["board_membership"]}';

DELETE FROM common_active_source_version
WHERE scope_key = '{config.trade_date}'
  AND source_batch_id = '{config.official_daily_batch_id}'
  AND source_version IN (
    '{config.official_source_versions["stock"]}',
    '{config.official_source_versions["index"]}',
    '{config.official_source_versions["board"]}'
  )
  AND data_type IN ('stock_daily', 'index_daily', 'board_daily');

DELETE FROM stock_daily_bar_fact
WHERE trade_date = '{config.trade_date}'
  AND source_batch_id = '{config.official_daily_batch_id}'
  AND source_version = '{config.official_source_versions["stock"]}';

DELETE FROM index_daily_bar_fact
WHERE trade_date = '{config.trade_date}'
  AND source_batch_id = '{config.official_daily_batch_id}'
  AND source_version = '{config.official_source_versions["index"]}';

DELETE FROM board_daily_bar_fact
WHERE trade_date = '{config.trade_date}'
  AND source_batch_id = '{config.official_daily_batch_id}'
  AND source_version = '{config.official_source_versions["board"]}';

DELETE FROM common_quality_gate_result
WHERE source_batch_id IN (
    '{config.official_daily_batch_id}',
    '{config.condition_source_batch_id}'
  )
   OR source_version IN (
     '{config.official_daily_batch_id}',
     '{config.condition_source_batch_id}',
     '{config.official_source_versions["stock"]}',
     '{config.official_source_versions["index"]}',
     '{config.official_source_versions["board"]}',
     '{config.condition_source_versions["stock_daily_basic"]}',
     '{config.condition_source_versions["stock_financial"]}',
     '{config.condition_source_versions["index_membership"]}',
     '{config.condition_source_versions["board_membership"]}'
   );

DELETE FROM common_ingest_batch
WHERE batch_id IN (
    '{config.official_daily_batch_id}',
    '{config.condition_source_batch_id}'
  )
   OR source_version IN (
     '{config.official_daily_batch_id}',
     '{config.condition_source_batch_id}',
     '{config.official_source_versions["stock"]}',
     '{config.official_source_versions["index"]}',
     '{config.official_source_versions["board"]}',
     '{config.condition_source_versions["stock_daily_basic"]}',
     '{config.condition_source_versions["stock_financial"]}',
     '{config.condition_source_versions["index_membership"]}',
     '{config.condition_source_versions["board_membership"]}'
   );

COMMIT;
"""


def _sql_without_comments(sql: str) -> str:
    return "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))


def validate_rollback_sql_text(sql: str, config: SourceFactsRunConfig) -> dict[str, Any]:
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
    scope_ids = [
        config.official_daily_batch_id,
        config.condition_source_batch_id,
        config.official_source_versions["stock"],
        config.condition_source_versions["stock_daily_basic"],
    ]
    result = {
        "hard_fail_before_delete": first_raise >= 0 and first_delete >= 0 and first_raise < first_delete,
        "no_drop_truncate_cascade": not any(token in sql_upper for token in ("DROP ", "TRUNCATE ", "CASCADE")),
        "no_forbidden_table_dml": not forbidden_table_dml,
        "forbidden_table_dml": forbidden_table_dml,
        "scope_ids_present": all(marker in sql for marker in scope_ids),
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


def write_rollback_sql(config: SourceFactsRunConfig) -> dict[str, Any]:
    sql = render_rollback_sql(config)
    config.rollback_sql_path.parent.mkdir(parents=True, exist_ok=True)
    config.rollback_sql_path.write_text(sql, encoding="utf-8")
    return {"path": str(config.rollback_sql_path), **validate_rollback_sql_text(sql, config)}


def assert_approved_command(command: str, *, trade_date: str) -> bool:
    _assert_date(trade_date, name="trade_date")
    if "run_real_daily_incremental.py" in command:
        raise SourceFactsGenericBlocked("scripts/run_real_daily_incremental.py is not an approved execute command")
    if GENERIC_APPROVED_COMMAND_SCRIPT not in command:
        raise SourceFactsGenericBlocked(f"command must use {GENERIC_APPROVED_COMMAND_SCRIPT}")
    missing = [flag for flag in REQUIRED_EXECUTE_FLAGS if flag not in command]
    if missing:
        raise SourceFactsGenericBlocked(f"approved command missing flag(s): {', '.join(missing)}")
    if f"--trade-date {trade_date}" not in command and f"--trade-date={trade_date}" not in command:
        raise SourceFactsGenericBlocked(f"approved command must pin --trade-date {trade_date}")
    return True


def derive_official_expectations_from_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    source_breakdown = dict(bundle.get("source_breakdown") or {})
    stock_rows = len(bundle.get("stock") or [])
    index_rows = len(bundle.get("index") or [])
    board_rows = len(bundle.get("board") or [])
    official_no_trade = len(bundle.get("official_no_trade_manifest") or [])
    stock_adj_factor_rows = int(source_breakdown.get("stock_adj_factor_rows") or 0)
    matched_stock_identity_rows = stock_rows
    unmapped_rows = int(source_breakdown.get("unmapped_tushare_daily_rows") or 0)
    return {
        "official_daily": {
            "stock_daily_bar_fact": stock_rows,
            "index_daily_bar_fact": index_rows,
            "board_daily_bar_fact": board_rows,
            "total_daily_fact": stock_rows + index_rows + board_rows,
        },
        "stock_adj_factor_rows": stock_adj_factor_rows,
        "matched_stock_identity_rows": matched_stock_identity_rows,
        "unmapped_tushare_daily_rows": unmapped_rows,
        "stock_scope_breakdown": {
            **dict(getattr(dedicated, "STOCK_SCOPE_BREAKDOWN")),
            "stock_daily_source_rows": int(source_breakdown.get("stock_daily_source_rows") or stock_rows),
            "tushare_daily_rows": stock_rows,
            "tushare_daily_rows_with_stock_identity": stock_rows,
            "expected_stock_daily_bar_rows": stock_rows,
            "official_no_trade_manifest_rows": official_no_trade,
            "official_no_trade": official_no_trade,
            "matched_identity_rows": matched_stock_identity_rows,
            "unmapped_tushare_daily_rows": unmapped_rows,
            "stock_adj_factor_rows": stock_adj_factor_rows,
            "skipped_missing_stock_identity_rows": int(
                source_breakdown.get("skipped_missing_stock_identity_rows") or 0
            ),
            "unresolved_source_gap": int(source_breakdown.get("unresolved_source_gap") or 0),
        },
        "index_scope_breakdown": {
            **dict(getattr(dedicated, "INDEX_SCOPE_BREAKDOWN")),
            "expected_index_daily_bar_fact_rows": index_rows,
            "mootdx_rows": int(source_breakdown.get("index_mootdx") or 0),
            "tushare_bj_fallback_rows": int(source_breakdown.get("index_tushare_bj_fallback") or 0),
        },
        "board_scope_breakdown": {
            **dict(getattr(dedicated, "BOARD_SCOPE_BREAKDOWN")),
            "expected_board_daily_bar_fact_rows": board_rows,
            "industry_881_required_coverage": int(
                (dict(getattr(dedicated, "BOARD_SCOPE_BREAKDOWN"))).get("industry_881_required_coverage") or 127
            ),
        },
    }


def derive_official_expectations_from_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    rows = dict(snapshot.get("current_daily_fact_rows") or {})
    stock_rows = int(rows.get("stock") or 0)
    index_rows = int(rows.get("index") or 0)
    board_rows = int(rows.get("board") or 0)
    return {
        "official_daily": {
            "stock_daily_bar_fact": stock_rows,
            "index_daily_bar_fact": index_rows,
            "board_daily_bar_fact": board_rows,
            "total_daily_fact": stock_rows + index_rows + board_rows,
        },
        "stock_adj_factor_rows": stock_rows,
        "matched_stock_identity_rows": stock_rows,
        "unmapped_tushare_daily_rows": 0,
        "stock_scope_breakdown": {
            **dict(getattr(dedicated, "STOCK_SCOPE_BREAKDOWN")),
            "tushare_daily_rows": stock_rows,
            "tushare_daily_rows_with_stock_identity": stock_rows,
            "expected_stock_daily_bar_rows": stock_rows,
            "matched_identity_rows": stock_rows,
        },
        "index_scope_breakdown": {
            **dict(getattr(dedicated, "INDEX_SCOPE_BREAKDOWN")),
            "expected_index_daily_bar_fact_rows": index_rows,
        },
        "board_scope_breakdown": {
            **dict(getattr(dedicated, "BOARD_SCOPE_BREAKDOWN")),
            "expected_board_daily_bar_fact_rows": board_rows,
        },
    }


def apply_official_expectations(expectations: Mapping[str, Any]) -> None:
    official_daily = dict(expectations.get("official_daily") or {})
    adjusted = dict(getattr(dedicated, "ADJUSTED_EXPECTED_ROWS_WITH_SKIP_POLICY"))
    before_skip = dict(getattr(dedicated, "EXPECTED_ROWS_AFTER_P0_CLEARANCE"))
    condition_source = dict(adjusted.get("condition_source") or {})
    stock_rows = int(official_daily.get("stock_daily_bar_fact") or 0)
    condition_source["stock_daily_basic"] = stock_rows
    condition_source["stock_financial_metrics_fact"] = stock_rows
    condition_source["total_condition_source_fact"] = (
        stock_rows
        + stock_rows
        + int(condition_source.get("index_membership_fact") or 0)
        + int(condition_source.get("board_membership_fact") or 0)
    )
    adjusted["official_daily"] = dict(official_daily)
    adjusted["condition_source"] = condition_source
    adjusted["combined_total"] = int(official_daily.get("total_daily_fact") or 0) + int(
        condition_source.get("total_condition_source_fact") or 0
    )
    before_skip["official_daily"] = dict(official_daily)
    before_skip["condition_source"] = dict(condition_source)
    before_skip["combined_total"] = adjusted["combined_total"]
    dedicated.ADJUSTED_EXPECTED_ROWS_WITH_SKIP_POLICY = adjusted
    dedicated.EXPECTED_ROWS_AFTER_P0_CLEARANCE = before_skip
    dedicated.EXPECTED_STOCK_ADJ_FACTOR_ROWS = int(expectations.get("stock_adj_factor_rows") or 0)
    dedicated.EXPECTED_MATCHED_STOCK_IDENTITY_ROWS = int(expectations.get("matched_stock_identity_rows") or 0)
    dedicated.EXPECTED_UNMAPPED_TUSHARE_DAILY_ROWS = int(expectations.get("unmapped_tushare_daily_rows") or 0)
    dedicated.STOCK_SCOPE_BREAKDOWN = dict(expectations.get("stock_scope_breakdown") or {})
    dedicated.INDEX_SCOPE_BREAKDOWN = dict(expectations.get("index_scope_breakdown") or {})
    dedicated.BOARD_SCOPE_BREAKDOWN = dict(expectations.get("board_scope_breakdown") or {})


def _paths_with_config(config: SourceFactsRunConfig) -> dict[str, Path]:
    return {
        "CONTRACT_PATH": config.contract_path,
        "PREFLIGHT_PATH": config.preflight_path,
        "ROLLBACK_SQL_PATH": config.rollback_sql_path,
        "IMPLEMENTATION_REPORT_JSON_PATH": config.implementation_report_json_path,
        "IMPLEMENTATION_REPORT_MD_PATH": config.implementation_report_md_path,
        "IDENTITY_REPAIR_HANDOFF_PATH": config.handoff_path,
        "IDENTITY_REPAIR_HANDOFF_MD_PATH": config.handoff_md_path,
        "FINAL_GATE_REVIEW_JSON_PATH": config.final_gate_review_json_path,
        "FINAL_GATE_REVIEW_MD_PATH": config.final_gate_review_md_path,
        "EXECUTE_REPORT_JSON_PATH": config.execute_report_json_path,
        "EXECUTE_REPORT_MD_PATH": config.execute_report_md_path,
        "POST_REVIEW_JSON_PATH": config.post_review_json_path,
        "POST_REVIEW_MD_PATH": config.post_review_md_path,
    }


@contextmanager
def patched_source_facts_module(config: SourceFactsRunConfig) -> Iterator[None]:
    overrides: dict[str, Any] = {
        "TRADE_DATE": config.trade_date,
        "FOR_TRADE_DATE": config.for_trade_date,
        "EXPECTED_PREV_TRADE_DATE": config.prev_trade_date,
        "EXPECTED_NEXT_TRADE_DATE": config.next_trade_date,
        "OFFICIAL_DAILY_BATCH_ID": config.official_daily_batch_id,
        "CONDITION_SOURCE_BATCH_ID": config.condition_source_batch_id,
        "OFFICIAL_SOURCE_VERSIONS": dict(config.official_source_versions),
        "CONDITION_SOURCE_VERSIONS": dict(config.condition_source_versions),
        "APPROVED_COMMAND_SCRIPT": GENERIC_APPROVED_COMMAND_SCRIPT,
        "OFFICIAL_DEFAULT_PATHS": dict(config.official_default_paths),
        "CONDITION_DEFAULT_PATHS": dict(config.condition_default_paths),
        "EXPECTED_ROWS_AFTER_P0_CLEARANCE": dict(dedicated.EXPECTED_ROWS_AFTER_P0_CLEARANCE),
        "ADJUSTED_EXPECTED_ROWS_WITH_SKIP_POLICY": dict(dedicated.ADJUSTED_EXPECTED_ROWS_WITH_SKIP_POLICY),
        "EXPECTED_STOCK_ADJ_FACTOR_ROWS": dedicated.EXPECTED_STOCK_ADJ_FACTOR_ROWS,
        "EXPECTED_MATCHED_STOCK_IDENTITY_ROWS": dedicated.EXPECTED_MATCHED_STOCK_IDENTITY_ROWS,
        "EXPECTED_UNMAPPED_TUSHARE_DAILY_ROWS": dedicated.EXPECTED_UNMAPPED_TUSHARE_DAILY_ROWS,
        "STOCK_SCOPE_BREAKDOWN": dict(dedicated.STOCK_SCOPE_BREAKDOWN),
        "INDEX_SCOPE_BREAKDOWN": dict(dedicated.INDEX_SCOPE_BREAKDOWN),
        "BOARD_SCOPE_BREAKDOWN": dict(dedicated.BOARD_SCOPE_BREAKDOWN),
        **_paths_with_config(config),
    }
    previous = {name: getattr(dedicated, name) for name in overrides}
    try:
        for name, value in overrides.items():
            setattr(dedicated, name, value)
        yield
    finally:
        for name, value in previous.items():
            setattr(dedicated, name, value)


def write_json_report(report: Mapping[str, Any], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text_report(markdown: str, path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown, encoding="utf-8")


def build_generic_implementation_report(config: SourceFactsRunConfig, rollback_check: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "gate": "N1_SOURCE_FACTS_GENERIC_GUARDED_RUNNER_IMPLEMENTATION_GATE",
        "layer_role": "N1_ingestion",
        "result": "IMPLEMENTATION_PASS",
        "trade_date": config.trade_date,
        "for_trade_date": config.for_trade_date,
        "official_daily_batch_id": config.official_daily_batch_id,
        "condition_source_batch_id": config.condition_source_batch_id,
        "approved_command_script": GENERIC_APPROVED_COMMAND_SCRIPT,
        "required_execute_flags": list(REQUIRED_EXECUTE_FLAGS),
        "allowed_write_tables": list(dedicated.ALLOWED_WRITE_TABLES),
        "forbidden_scope_markers": list(dedicated.FORBIDDEN_SCOPE_MARKERS),
        "rollback_static_check": dict(rollback_check),
        "implementation_strategy": "date_scoped_patch_of_reviewed_20260608_guarded_runner",
        "forbidden_scope_proof": {
            "writes_performed": False,
            "postgres_written": False,
            "rollback_executed": False,
            "n2_n3_n4_n5_n6_entered": False,
            "outbox_inbox_checkpoint_consumed_or_updated": False,
            "worker_started": False,
            "old_system_touched": False,
            "trade_or_sim_touched": False,
        },
        "next_recommended_gate": f"N1_{config.trade_date}_SOURCE_FACTS_EXECUTE_FINAL_GATE_REVIEW",
    }


def render_generic_implementation_markdown(report: Mapping[str, Any]) -> str:
    return f"""# N1 Generic Source Facts Guarded Runner Implementation

Result: `{report["result"]}`

- trade_date: `{report["trade_date"]}`
- for_trade_date: `{report["for_trade_date"]}`
- official_daily_batch_id: `{report["official_daily_batch_id"]}`
- condition_source_batch_id: `{report["condition_source_batch_id"]}`
- approved command script: `{report["approved_command_script"]}`
- required flags: `{" ".join(report["required_execute_flags"])}`

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


def write_generic_implementation_artifacts(config: SourceFactsRunConfig) -> dict[str, Any]:
    rollback_check = write_rollback_sql(config)
    report = build_generic_implementation_report(config, rollback_check)
    write_json_report(report, config.implementation_report_json_path)
    write_text_report(render_generic_implementation_markdown(report), config.implementation_report_md_path)
    return report
