"""Runtime pipeline state machine and dashboard rendering."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Iterable

from ashare_v3.runtime_control.registry import (
    ExecuteCommandRegistryEntry,
    RollbackRegistryEntry,
    build_action_confirmation_execute_command_registry,
    build_action_confirmation_rollback_registry,
    build_default_execute_command_registry,
    build_default_rollback_registry,
)


PENDING = "PENDING"
WAIT_MANUAL_CONFIRM = "WAIT_MANUAL_CONFIRM"
RUNNING = "RUNNING"
READY = "READY"
PASS = "PASS"
PASSED = "PASSED"
FAILED = "FAILED"
BLOCKED = "BLOCKED"
NOT_RUN = "NOT_RUN"
ROLLBACK_READY = "ROLLBACK_READY"
ROLLED_BACK = "ROLLED_BACK"


TERMINAL_STATES = frozenset({PASS, PASSED, FAILED, BLOCKED, ROLLED_BACK})


@dataclass(frozen=True)
class RuntimePipelineStage:
    stage_id: str
    title: str
    layer_role: str
    status: str
    dependencies: tuple[str, ...]
    command_key: str
    rollback_key: str
    requires_manual_confirm: bool = True
    modifies_execute_contract: bool = False
    starts_worker: bool = False
    report_path: str = ""
    quality: dict[str, int] | None = None
    details: str = ""
    artifact_status: str = NOT_RUN
    artifact_path: str = ""
    artifact_rollback_path: str = ""
    run_id: str = ""
    source_batch_id: str = ""
    rows_summary: dict[str, object] | None = None

    def can_execute(self, *, user_confirmed: bool) -> bool:
        if self.status != WAIT_MANUAL_CONFIRM:
            return False
        if self.requires_manual_confirm and not user_confirmed:
            return False
        return True

    def with_status(self, status: str, *, details: str = "") -> "RuntimePipelineStage":
        return replace(self, status=status, details=details or self.details)

    def to_dict(
        self,
        *,
        command: ExecuteCommandRegistryEntry | None = None,
        rollback: RollbackRegistryEntry | None = None,
    ) -> dict[str, object]:
        return {
            "stage_id": self.stage_id,
            "title": self.title,
            "layer_role": self.layer_role,
            "status": self.status,
            "dependencies": list(self.dependencies),
            "command_key": self.command_key,
            "rollback_key": self.rollback_key,
            "requires_manual_confirm": self.requires_manual_confirm,
            "modifies_execute_contract": self.modifies_execute_contract,
            "starts_worker": self.starts_worker,
            "report_path": self.report_path,
            "quality": normalize_quality(self.quality),
            "details": self.details,
            "artifact_status": self.artifact_status,
            "artifact_path": self.artifact_path,
            "artifact_rollback_path": self.artifact_rollback_path,
            "run_id": self.run_id,
            "source_batch_id": self.source_batch_id,
            "rows_summary": dict(self.rows_summary or {}),
            "command": command.to_dict() if command else None,
            "rollback": rollback.to_dict() if rollback else None,
        }


@dataclass(frozen=True)
class RuntimePipelineRun:
    run_id: str
    pipeline_name: str
    layer_role: str
    trade_date: str
    status: str
    stages: tuple[RuntimePipelineStage, ...]
    command_registry: dict[str, ExecuteCommandRegistryEntry]
    rollback_registry: dict[str, RollbackRegistryEntry]
    created_at: str
    side_effects: dict[str, bool]

    def stage_by_id(self, stage_id: str) -> RuntimePipelineStage:
        for stage in self.stages:
            if stage.stage_id == stage_id:
                return stage
        raise KeyError(stage_id)

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "pipeline_name": self.pipeline_name,
            "layer_role": self.layer_role,
            "trade_date": self.trade_date,
            "status": self.status,
            "created_at": self.created_at,
            "side_effects": dict(self.side_effects),
            "stages": [
                stage.to_dict(
                    command=self.command_registry.get(stage.command_key),
                    rollback=self.rollback_registry.get(stage.rollback_key),
                )
                for stage in self.stages
            ],
            "timeline": build_pipeline_timeline(self),
        }


def build_nightly_pipeline_run(*, trade_date: str, created_at: str | None = None) -> RuntimePipelineRun:
    command_registry = build_default_execute_command_registry(trade_date=trade_date)
    rollback_registry = build_default_rollback_registry(trade_date=trade_date)
    stages = (
        RuntimePipelineStage(
            stage_id="calendar",
            title="Calendar gate",
            layer_role="N1_ingestion",
            status=WAIT_MANUAL_CONFIRM,
            dependencies=(),
            command_key="calendar",
            rollback_key="calendar",
            report_path=f"docs/N1_trade_calendar_{trade_date}_patch_preflight.json",
            details="Operator must confirm trade calendar patch command before any write.",
        ),
        RuntimePipelineStage(
            stage_id="n1_official_daily",
            title="N1 official daily",
            layer_role="N1_ingestion",
            status=WAIT_MANUAL_CONFIRM,
            dependencies=("calendar",),
            command_key="n1_official_daily",
            rollback_key="n1_official_daily",
            report_path=f"docs/N1_official_daily_{trade_date}_ingestion_execute_preflight.json",
            details="Official daily ingestion remains a separate N1 run-once gate.",
        ),
        RuntimePipelineStage(
            stage_id="n1_condition_source",
            title="N1 condition source",
            layer_role="N1_ingestion",
            status=WAIT_MANUAL_CONFIRM,
            dependencies=("n1_official_daily",),
            command_key="n1_condition_source",
            rollback_key="n1_condition_source",
            report_path=f"docs/N1_condition_source_{trade_date}_v2_activation_preflight.json",
            details="Condition source activation remains an N1 gate.",
        ),
        RuntimePipelineStage(
            stage_id="n2_condition_layer",
            title="N2 condition layer",
            layer_role="N2_condition",
            status=WAIT_MANUAL_CONFIRM,
            dependencies=("n1_condition_source",),
            command_key="n2_condition_layer",
            rollback_key="n2_condition_layer",
            report_path=f"docs/N2_condition_layer_{trade_date}_execute_preflight.json",
            details="N2 execute contract is only referenced by registry.",
        ),
        RuntimePipelineStage(
            stage_id="n3_subscription",
            title="N3 subscription",
            layer_role="N3_market_data",
            status=WAIT_MANUAL_CONFIRM,
            dependencies=("n2_condition_layer",),
            command_key="n3_subscription",
            rollback_key="n3_subscription",
            report_path=f"docs/N3_subscription_{trade_date}_execute_preflight.json",
            details="N3 subscription remains a separate manual run-once gate.",
        ),
        RuntimePipelineStage(
            stage_id="a1_previous_day_preload",
            title="A1 previous-day preload",
            layer_role="N3_market_data",
            status=WAIT_MANUAL_CONFIRM,
            dependencies=("n3_subscription",),
            command_key="a1_previous_day_preload",
            rollback_key="a1_previous_day_preload",
            report_path=f"docs/N3_A1_previous_day_minute_{trade_date}_execute_preflight.json",
            details="A1 preload command is registered but not executed by runtime control.",
        ),
        RuntimePipelineStage(
            stage_id="b1_realtime_snapshot_fact_only",
            title="B1 realtime snapshot fact-only",
            layer_role="N3_market_data",
            status=WAIT_MANUAL_CONFIRM,
            dependencies=("a1_previous_day_preload",),
            command_key="b1_realtime_snapshot_fact_only",
            rollback_key="b1_realtime_snapshot_fact_only",
            report_path=f"docs/N3_B1_realtime_snapshot_{trade_date}_execute_preflight.json",
            details="B1 fact-only keeps outbox disabled and requires explicit manual confirmation.",
        ),
    )
    return RuntimePipelineRun(
        run_id=f"runtime_pipeline_{trade_date}_nightly_v0",
        pipeline_name="nightly_runtime_v0",
        layer_role="runtime_control",
        trade_date=trade_date,
        status=WAIT_MANUAL_CONFIRM,
        stages=stages,
        command_registry=command_registry,
        rollback_registry=rollback_registry,
        created_at=created_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        side_effects={
            "connects_database": False,
            "executes_sql": False,
            "executes_commands": False,
            "executes_rollback": False,
            "starts_worker": False,
            "modifies_n1_n6_execute_contract": False,
            "executes_nightly_run": False,
        },
    )


def build_action_confirmation_pipeline_run(*, trade_date: str, created_at: str | None = None) -> RuntimePipelineRun:
    command_registry = build_action_confirmation_execute_command_registry(trade_date=trade_date)
    rollback_registry = build_action_confirmation_rollback_registry(trade_date=trade_date)
    source_trade_date = "20260601" if trade_date == "20260602" else "<source_trade_date>"
    condition_run_id = f"condition_layer_{source_trade_date}_source_{source_trade_date}_v1"
    stages = (
        RuntimePipelineStage(
            stage_id="n2_condition_layer_active",
            title="N2 condition layer active",
            layer_role="N2_condition",
            status=WAIT_MANUAL_CONFIRM,
            dependencies=(),
            command_key="n2_condition_layer_active",
            rollback_key="n2_condition_layer_active",
            report_path=f"docs/N2_condition_layer_{source_trade_date}_to_{trade_date}_execute_report.json",
            details="N2 active lineage is displayed from reviewed docs artifacts only.",
        ),
        RuntimePipelineStage(
            stage_id="n3_subscription",
            title="N3 subscription",
            layer_role="N3_market_data",
            status=WAIT_MANUAL_CONFIRM,
            dependencies=("n2_condition_layer_active",),
            command_key="n3_subscription",
            rollback_key="n3_subscription",
            report_path=f"docs/N3_subscription_{trade_date}_execute_report.json",
            details="N3 subscription artifact is read-only; runtime_control does not execute it.",
        ),
        RuntimePipelineStage(
            stage_id="n3_a1_previous_day_preload",
            title="N3 A1 previous-day preload",
            layer_role="N3_market_data",
            status=WAIT_MANUAL_CONFIRM,
            dependencies=("n3_subscription",),
            command_key="n3_a1_previous_day_preload",
            rollback_key="n3_a1_previous_day_preload",
            report_path=f"docs/N3_A1_previous_day_minute_{trade_date}_execute_report.json",
            details="A1 previous-day minute preload artifact is displayed without execution.",
        ),
        RuntimePipelineStage(
            stage_id="n3_b1_live3_snapshot",
            title="N3 B1 live3 snapshot",
            layer_role="N3_market_data",
            status=WAIT_MANUAL_CONFIRM,
            dependencies=("n3_a1_previous_day_preload",),
            command_key="n3_b1_live3_snapshot",
            rollback_key="n3_b1_live3_snapshot",
            report_path=f"docs/N3_B1_realtime_snapshot_{trade_date}_live3_outbox_execute_report.json",
            details="B1 live3 outbox snapshot artifact is displayed without consuming outbox.",
        ),
        RuntimePipelineStage(
            stage_id="n3_c1_today_minute",
            title="N3 C1 today minute",
            layer_role="N3_market_data",
            status=WAIT_MANUAL_CONFIRM,
            dependencies=("n3_b1_live3_snapshot",),
            command_key="n3_c1_today_minute",
            rollback_key="n3_c1_today_minute",
            report_path=f"docs/N3_C1_today_minute_bar_1m_{trade_date}_until_1105_execute_report.json",
            details="C1 today minute artifact is displayed without pulling market data.",
        ),
        RuntimePipelineStage(
            stage_id="n3_action_confirmation_projection",
            title="N3 action-confirmation projection",
            layer_role="N3_market_data",
            status=WAIT_MANUAL_CONFIRM,
            dependencies=("n3_c1_today_minute",),
            command_key="n3_action_confirmation_projection",
            rollback_key="n3_action_confirmation_projection",
            report_path="docs/N3_action_confirmation_projection_writer_execute_report.json",
            details="N3 action-confirmation metric facts are displayed from execute report.",
        ),
        RuntimePipelineStage(
            stage_id="n4_action_confirmation_metric_execute",
            title="N4 action-confirmation metric execute",
            layer_role="N4_trigger",
            status=WAIT_MANUAL_CONFIRM,
            dependencies=("n3_action_confirmation_projection",),
            command_key="n4_action_confirmation_metric_execute",
            rollback_key="n4_action_confirmation_metric_execute",
            report_path="docs/N4_action_confirmation_metric_business_execute_report.json",
            details="N4 trigger execute artifact is displayed without consuming or mutating outbox.",
        ),
        RuntimePipelineStage(
            stage_id="n5_action_confirmation_metric_execute",
            title="N5 action-confirmation metric execute",
            layer_role="N5_action",
            status=WAIT_MANUAL_CONFIRM,
            dependencies=("n4_action_confirmation_metric_execute",),
            command_key="n5_action_confirmation_metric_execute",
            rollback_key="n5_action_confirmation_metric_execute",
            report_path=f"docs/N5_{trade_date}_action_confirmation_metric_execute_report.json",
            details="N5 action execute artifact is displayed while N5 outbox remains pending.",
        ),
        RuntimePipelineStage(
            stage_id="n6_shadow_projection",
            title="N6 shadow projection",
            layer_role="N6_user",
            status=WAIT_MANUAL_CONFIRM,
            dependencies=("n5_action_confirmation_metric_execute",),
            command_key="n6_shadow_projection",
            rollback_key="n6_shadow_projection",
            report_path=f"docs/runtime_action_confirmation_chain_{trade_date}_closure.json",
            details="N6 shadow closure is displayed from runtime_control closure artifact.",
        ),
    )
    return RuntimePipelineRun(
        run_id=f"runtime_pipeline_{trade_date}_action_confirmation_v0_2",
        pipeline_name="action_confirmation_runtime_v0_2",
        layer_role="runtime_control",
        trade_date=trade_date,
        status=WAIT_MANUAL_CONFIRM,
        stages=stages,
        command_registry=command_registry,
        rollback_registry=rollback_registry,
        created_at=created_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        side_effects={
            "connects_database": False,
            "executes_sql": False,
            "executes_commands": False,
            "executes_rollback": False,
            "starts_worker": False,
            "modifies_n1_n6_execute_contract": False,
            "executes_nightly_run": False,
            "consumes_outbox": False,
            "updates_outbox_status": False,
        },
    )


def build_pipeline_timeline(run: RuntimePipelineRun) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, stage in enumerate(run.stages, start=1):
        rows.append(
            {
                "sequence": index,
                "stage_id": stage.stage_id,
                "title": stage.title,
                "status": stage.status,
                "layer_role": stage.layer_role,
                "dependencies": list(stage.dependencies),
                "manual_confirm_required": stage.requires_manual_confirm,
                "report_path": stage.report_path,
                "quality": normalize_quality(stage.quality),
                "artifact_status": stage.artifact_status,
                "run_id": stage.run_id,
                "source_batch_id": stage.source_batch_id,
                "rows_summary": dict(stage.rows_summary or {}),
                "rollback_sql_path": run.rollback_registry[stage.rollback_key].rollback_sql_path,
            }
        )
    return rows


def render_dashboard_markdown(run: RuntimePipelineRun) -> str:
    lines = [
        "# Runtime Pipeline Dashboard v0",
        "",
        f"- pipeline_run_id: `{run.run_id}`",
        f"- pipeline_name: `{run.pipeline_name}`",
        f"- layer_role=runtime_control",
        f"- trade_date: `{run.trade_date}`",
        f"- status: `{run.status}`",
        "- boundary: does not execute nightly run",
        "- boundary: does not modify N1-N6 execute contracts",
        "- boundary: does not start workers, consume outbox, write N6, voice, mobile, sim, or real trades",
        "",
        "| # | stage_id | layer | status | rollback |",
        "|---:|---|---|---|---|",
    ]
    for row in build_pipeline_timeline(run):
        lines.append(
            "| {sequence} | `{stage_id}` | `{layer_role}` | `{status}` | `{rollback_sql_path}` |".format(**row)
        )

    lines.extend(["", "## Execute Command Registry", ""])
    for stage in run.stages:
        entry = run.command_registry[stage.command_key]
        lines.append(f"- `{stage.stage_id}`: `{' '.join(entry.command)}`")

    return "\n".join(lines) + "\n"


def statuses(stages: Iterable[RuntimePipelineStage]) -> tuple[str, ...]:
    return tuple(stage.status for stage in stages)


def normalize_quality(quality: dict[str, int] | None) -> dict[str, int]:
    quality = quality or {}
    return {
        "p0_count": int(quality.get("p0_count", 0)),
        "p1_count": int(quality.get("p1_count", 0)),
        "p2_count": int(quality.get("p2_count", 0)),
    }


def summarize_quality(stages: Iterable[RuntimePipelineStage]) -> dict[str, int]:
    totals = {"p0_count": 0, "p1_count": 0, "p2_count": 0}
    for stage in stages:
        quality = normalize_quality(stage.quality)
        for key in totals:
            totals[key] += quality[key]
    return totals
