"""Phase 3 N3 structured query audit adoption helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ashare_v3.observability.query_audit import (
    AuditSink,
    audited_connect,
    audited_psycopg_connect,
    make_artifact_audit_sink,
    make_audit_context,
)


PHASE3_GATE_ID = "N3_N4_N5_STRUCTURED_QUERY_AUDIT_PHASE3_N3_ADOPTION_IMPLEMENTATION_GATE"
N3_LAYER_ROLE = "N3_market_data"


def audited_n3_market_execute_connect(
    dsn: str,
    *,
    stage_id: str = "n3_market_execute",
    source_run_id: str | None = None,
    readonly_expected: bool = False,
    sink: AuditSink | None = None,
    connect: Callable[..., Any] | None = None,
    artifact_dir: Path | str | None = None,
    **kwargs: Any,
) -> Any:
    """Audited connection for N3 market-data execute/write paths."""

    return _audited_n3_market_connect(
        dsn,
        stage_id=stage_id,
        source_run_id=source_run_id,
        path_role="n3_intraday_execute",
        readonly_expected=readonly_expected,
        sink=sink,
        connect=connect,
        artifact_dir=artifact_dir,
        **kwargs,
    )


def audited_n3_market_readonly_plan_connect(
    dsn: str,
    *,
    stage_id: str = "n3_market_readonly_plan",
    source_run_id: str | None = None,
    sink: AuditSink | None = None,
    connect: Callable[..., Any] | None = None,
    artifact_dir: Path | str | None = None,
    **kwargs: Any,
) -> Any:
    """Audited connection for read-only N3 plan/dry-run/preflight paths."""

    return _audited_n3_market_connect(
        dsn,
        stage_id=stage_id,
        source_run_id=source_run_id,
        path_role="n3_readonly_plan",
        readonly_expected=True,
        bypass_classification="explicit_bypass_readonly_plan",
        sink=sink,
        connect=connect,
        artifact_dir=artifact_dir,
        **kwargs,
    )


def audited_n3_market_schema_review_connect(
    dsn: str,
    *,
    stage_id: str = "n3_market_schema_review",
    source_run_id: str | None = None,
    sink: AuditSink | None = None,
    connect: Callable[..., Any] | None = None,
    artifact_dir: Path | str | None = None,
    **kwargs: Any,
) -> Any:
    """Audited connection for N3 schema review or migration helper paths."""

    return _audited_n3_market_connect(
        dsn,
        stage_id=stage_id,
        source_run_id=source_run_id,
        path_role="n3_schema_review",
        readonly_expected=True,
        bypass_classification="out_of_scope_migration_or_schema_review",
        sink=sink,
        connect=connect,
        artifact_dir=artifact_dir,
        **kwargs,
    )


def _audited_n3_market_connect(
    dsn: str,
    *,
    stage_id: str,
    source_run_id: str | None,
    path_role: str,
    readonly_expected: bool,
    bypass_classification: str | None = None,
    sink: AuditSink | None = None,
    connect: Callable[..., Any] | None = None,
    artifact_dir: Path | str | None = None,
    **kwargs: Any,
) -> Any:
    context = make_audit_context(
        layer_role=N3_LAYER_ROLE,
        source_run_id=source_run_id,
        stage_id=stage_id,
        gate_id=PHASE3_GATE_ID,
        path_role=path_role,
        readonly_expected=readonly_expected,
        bypass_classification=bypass_classification,
    )
    if connect is not None:
        audit_sink = sink or make_artifact_audit_sink(context, artifact_dir=artifact_dir)
        return audited_connect(
            connect,
            dsn,
            context=context,
            sink=audit_sink,
            write_report_on_exit=sink is None,
            **kwargs,
        )
    return audited_psycopg_connect(
        dsn,
        context=context,
        sink=sink,
        artifact_dir=artifact_dir,
        **kwargs,
    )
