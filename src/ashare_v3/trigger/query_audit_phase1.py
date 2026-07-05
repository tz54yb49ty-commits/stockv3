"""Phase 1 N4 structured query audit adoption helpers."""

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


PHASE1_GATE_ID = "N3_N4_N5_STRUCTURED_QUERY_AUDIT_PHASE1_N4_ADOPTION_IMPLEMENTATION_GATE"
N4_LAYER_ROLE = "N4_trigger"


def audited_n4_trigger_connect(
    dsn: str,
    *,
    stage_id: str,
    path_role: str = "n4_intraday_execute",
    source_run_id: str | None = None,
    readonly_expected: bool = True,
    bypass_classification: str | None = None,
    sink: AuditSink | None = None,
    connect: Callable[..., Any] | None = None,
    artifact_dir: Path | str | None = None,
    **kwargs: Any,
) -> Any:
    context = make_audit_context(
        layer_role=N4_LAYER_ROLE,
        source_run_id=source_run_id,
        stage_id=stage_id,
        gate_id=PHASE1_GATE_ID,
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


def audited_n4_context_refresh_connect(
    dsn: str,
    *,
    stage_id: str,
    source_run_id: str | None = None,
    readonly_expected: bool = False,
    **kwargs: Any,
) -> Any:
    return audited_n4_trigger_connect(
        dsn,
        stage_id=stage_id,
        source_run_id=source_run_id,
        path_role="n4_context_refresh_execute",
        readonly_expected=readonly_expected,
        bypass_classification="explicit_bypass_one_time_context_refresh",
        **kwargs,
    )


def audited_n4_readonly_plan_connect(
    dsn: str,
    *,
    stage_id: str,
    source_run_id: str | None = None,
    sink: AuditSink | None = None,
    connect: Callable[..., Any] | None = None,
    artifact_dir: Path | str | None = None,
    **kwargs: Any,
) -> Any:
    return audited_n4_trigger_connect(
        dsn,
        stage_id=stage_id,
        source_run_id=source_run_id,
        path_role="n4_readonly_plan",
        readonly_expected=True,
        bypass_classification="explicit_bypass_readonly_plan",
        sink=sink,
        connect=connect,
        artifact_dir=artifact_dir,
        **kwargs,
    )


def audited_n4_schema_review_connect(
    dsn: str,
    *,
    stage_id: str,
    source_run_id: str | None = None,
    readonly_expected: bool = True,
    sink: AuditSink | None = None,
    connect: Callable[..., Any] | None = None,
    artifact_dir: Path | str | None = None,
    **kwargs: Any,
) -> Any:
    return audited_n4_trigger_connect(
        dsn,
        stage_id=stage_id,
        source_run_id=source_run_id,
        path_role="n4_schema_review",
        readonly_expected=readonly_expected,
        bypass_classification="out_of_scope_migration_or_schema_review",
        sink=sink,
        connect=connect,
        artifact_dir=artifact_dir,
        **kwargs,
    )
