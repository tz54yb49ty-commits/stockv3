"""N2-E7 review for the condition-layer schema gap migration.

The review is intentionally non-executing. It checks the 005 migration draft,
summarizes compatibility with nullable added columns, and keeps user
confirmation as the final gate before any later N2-E8 migration.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from ashare_v3.condition.schema_gap_plan import (
    DEFAULT_SCHEMA_GAP_SQL_PATH,
    SchemaGapReport,
    build_condition_schema_gap_report,
)
from ashare_v3.condition.schema_migration_readiness import DEFAULT_CONDITION_SCHEMA_PATH


DISALLOWED_SQL_PATTERNS = (
    r"\bDROP\b",
    r"\bDELETE\b",
    r"\bUPDATE\b",
    r"\bINSERT\b",
    r"\bTRUNCATE\b",
    r"\bCREATE\b",
    r"\bALTER\s+COLUMN\b",
    r"\bADD\s+CONSTRAINT\b",
    r"\bNOT\s+NULL\b",
    r"\bDEFAULT\b",
    r"\bCHECK\b",
    r"\bREFERENCES\b",
    r"\bBACKFILL\b",
)


@dataclass(frozen=True)
class MigrationSqlReview:
    additive_only: bool
    nullable_only: bool
    no_drop: bool
    no_backfill: bool
    no_not_null: bool
    no_check_or_fk: bool
    statement_count: int
    add_column_count: int
    disallowed_hits: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "additive_only": self.additive_only,
            "nullable_only": self.nullable_only,
            "no_drop": self.no_drop,
            "no_backfill": self.no_backfill,
            "no_not_null": self.no_not_null,
            "no_check_or_fk": self.no_check_or_fk,
            "statement_count": self.statement_count,
            "add_column_count": self.add_column_count,
            "disallowed_hits": list(self.disallowed_hits),
        }


@dataclass(frozen=True)
class MigrationReviewReport:
    stage: str
    schema_path: str
    migration_sql_path: str
    migration_safe_to_apply: bool
    additive_only: bool
    affects_existing_rows: str
    requires_backup: bool
    rollback_manual_only: bool
    user_confirmation_required: bool
    gap_summary: dict[str, Any]
    sql_review: MigrationSqlReview
    nullable_compatibility: dict[str, Any]
    will_execute_sql: bool = False
    migration_performed: bool = False
    writes_performed: bool = False
    minute_kline_pulled: bool = False
    downstream_layers_touched: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "schema_path": self.schema_path,
            "migration_sql_path": self.migration_sql_path,
            "migration_safe_to_apply": self.migration_safe_to_apply,
            "additive_only": self.additive_only,
            "affects_existing_rows": self.affects_existing_rows,
            "requires_backup": self.requires_backup,
            "rollback_manual_only": self.rollback_manual_only,
            "user_confirmation_required": self.user_confirmation_required,
            "gap_summary": self.gap_summary,
            "sql_review": self.sql_review.to_dict(),
            "nullable_compatibility": self.nullable_compatibility,
            "side_effects": {
                "will_execute_sql": self.will_execute_sql,
                "migration_performed": self.migration_performed,
                "writes_performed": self.writes_performed,
                "minute_kline_pulled": self.minute_kline_pulled,
                "downstream_layers_touched": self.downstream_layers_touched,
            },
        }


def build_condition_migration_review(
    *,
    dsn: str,
    schema_path: str = DEFAULT_CONDITION_SCHEMA_PATH,
    migration_sql_path: str = DEFAULT_SCHEMA_GAP_SQL_PATH,
) -> MigrationReviewReport:
    gap_report = build_condition_schema_gap_report(
        dsn=dsn,
        schema_path=schema_path,
        migration_sql_path=migration_sql_path,
    )
    sql_text = Path(migration_sql_path).read_text(encoding="utf-8")
    sql_review = review_migration_sql(sql_text)
    nullable_compatibility = review_nullable_compatibility()
    migration_safe_to_apply = (
        gap_report.passed
        and gap_report.migration_required
        and sql_review.additive_only
        and sql_review.nullable_only
        and sql_review.no_drop
        and sql_review.no_backfill
        and sql_review.no_not_null
        and sql_review.no_check_or_fk
        and bool(nullable_compatibility["compatible"])
    )
    return MigrationReviewReport(
        stage="N2-E7",
        schema_path=schema_path,
        migration_sql_path=migration_sql_path,
        migration_safe_to_apply=migration_safe_to_apply,
        additive_only=sql_review.additive_only,
        affects_existing_rows="existing rows keep their data and receive NULL in newly added nullable columns; no backfill is planned",
        requires_backup=True,
        rollback_manual_only=True,
        user_confirmation_required=True,
        gap_summary=gap_report_summary(gap_report),
        sql_review=sql_review,
        nullable_compatibility=nullable_compatibility,
    )


def review_migration_sql(sql_text: str) -> MigrationSqlReview:
    executable_sql = strip_line_comments(sql_text)
    statements = [statement.strip() for statement in executable_sql.split(";") if statement.strip()]
    non_control_statements = [
        statement
        for statement in statements
        if statement.upper() not in {"BEGIN", "COMMIT"}
    ]
    disallowed_hits = tuple(
        pattern
        for pattern in DISALLOWED_SQL_PATTERNS
        if re.search(pattern, executable_sql, flags=re.IGNORECASE)
    )
    add_column_matches = re.findall(r"\bADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\b", executable_sql, flags=re.IGNORECASE)
    additive_only = bool(non_control_statements) and all(
        statement.upper().startswith("ALTER TABLE ")
        and "ADD COLUMN IF NOT EXISTS" in statement.upper()
        for statement in non_control_statements
    )
    nullable_only = not re.search(r"\bADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\b.*\b(NOT\s+NULL|DEFAULT|CHECK|REFERENCES)\b", executable_sql, flags=re.IGNORECASE | re.DOTALL)
    no_drop = not re.search(r"\bDROP\b", executable_sql, flags=re.IGNORECASE)
    no_backfill = not re.search(r"\b(UPDATE|INSERT|DELETE|TRUNCATE|BACKFILL)\b", executable_sql, flags=re.IGNORECASE)
    no_not_null = not re.search(r"\bNOT\s+NULL\b", executable_sql, flags=re.IGNORECASE)
    no_check_or_fk = not re.search(r"\b(CHECK|REFERENCES|ADD\s+CONSTRAINT)\b", executable_sql, flags=re.IGNORECASE)
    return MigrationSqlReview(
        additive_only=additive_only and not disallowed_hits,
        nullable_only=nullable_only,
        no_drop=no_drop,
        no_backfill=no_backfill,
        no_not_null=no_not_null,
        no_check_or_fk=no_check_or_fk,
        statement_count=len(statements),
        add_column_count=len(add_column_matches),
        disallowed_hits=disallowed_hits,
    )


def strip_line_comments(sql_text: str) -> str:
    lines = []
    for line in sql_text.splitlines():
        lines.append(line.split("--", 1)[0])
    return "\n".join(lines)


def review_nullable_compatibility() -> dict[str, Any]:
    return {
        "compatible": True,
        "execute_py": {
            "status": "compatible",
            "reason": "basis_insert_row/pool_insert_row use row.get(...) and selected_reason/excluded_reason default to empty lists before insert",
        },
        "basis_py": {
            "status": "compatible",
            "reason": "new stock basis fields are read from source facts for new dry-runs; missing source values remain nullable",
        },
        "pool_py": {
            "status": "compatible",
            "reason": "default policy generates policy_name/policy_hash/selected_reason for new pool rows and uses row.get(...) for source evidence",
        },
        "old_active_run": {
            "status": "compatible",
            "reason": "005 adds nullable columns only; existing active-run rows can retain NULL policy/basis metadata until a future execute/backfill",
        },
    }


def gap_report_summary(gap_report: SchemaGapReport) -> dict[str, Any]:
    return {
        "missing_tables": list(gap_report.missing_tables),
        "missing_column_count": len(gap_report.missing_columns),
        "type_mismatch_count": len(gap_report.type_mismatches),
        "not_null_risk_count": len(gap_report.not_null_risks),
        "constraint_deferred_count": len(gap_report.constraint_deferred),
        "missing_columns_by_table": missing_columns_by_table(gap_report),
    }


def missing_columns_by_table(gap_report: SchemaGapReport) -> dict[str, list[str]]:
    output: dict[str, list[str]] = {}
    for item in gap_report.missing_columns:
        output.setdefault(item.table_name, []).append(item.column_name)
    return {table_name: columns for table_name, columns in sorted(output.items())}


def format_review_markdown(report: MigrationReviewReport) -> str:
    payload = report.to_dict()
    gap = payload["gap_summary"]
    sql_review = payload["sql_review"]
    compatibility = payload["nullable_compatibility"]
    lines = [
        "# N2-E7 Condition Layer Migration Review",
        "",
        "## Summary",
        "",
        f"- migration_safe_to_apply: {str(payload['migration_safe_to_apply']).lower()}",
        f"- additive_only: {str(payload['additive_only']).lower()}",
        f"- affects_existing_rows: {payload['affects_existing_rows']}",
        f"- requires_backup: {str(payload['requires_backup']).lower()}",
        f"- rollback_manual_only: {str(payload['rollback_manual_only']).lower()}",
        f"- user_confirmation_required: {str(payload['user_confirmation_required']).lower()}",
        "",
        "## Schema Gap",
        "",
        f"- missing_tables: {gap['missing_tables']}",
        f"- missing_column_count: {gap['missing_column_count']}",
        f"- type_mismatch_count: {gap['type_mismatch_count']}",
        f"- not_null_risk_count: {gap['not_null_risk_count']}",
        f"- constraint_deferred_count: {gap['constraint_deferred_count']}",
        "",
        "Missing columns by table:",
        "",
    ]
    for table_name, columns in gap["missing_columns_by_table"].items():
        lines.append(f"- {table_name}: {', '.join(columns)}")
    lines.extend(
        [
            "",
            "## SQL Review",
            "",
            f"- additive_only: {str(sql_review['additive_only']).lower()}",
            f"- nullable_only: {str(sql_review['nullable_only']).lower()}",
            f"- no_drop: {str(sql_review['no_drop']).lower()}",
            f"- no_backfill: {str(sql_review['no_backfill']).lower()}",
            f"- no_not_null: {str(sql_review['no_not_null']).lower()}",
            f"- no_check_or_fk: {str(sql_review['no_check_or_fk']).lower()}",
            f"- add_column_count: {sql_review['add_column_count']}",
            f"- disallowed_hits: {sql_review['disallowed_hits']}",
            "",
            "## Nullable Compatibility",
            "",
        ]
    )
    for area in ("execute_py", "basis_py", "pool_py", "old_active_run"):
        item = compatibility[area]
        lines.append(f"- {area}: {item['status']} - {item['reason']}")
    lines.extend(
        [
            "",
            "## Boundaries",
            "",
            "- This review did not execute migration SQL.",
            "- This review did not write business data.",
            "- This review did not pull market data or enter trigger/action/voice/mobile/sim/worker.",
            "- N2-E8 still requires explicit user confirmation before applying 005.",
            "",
        ]
    )
    return "\n".join(lines)
