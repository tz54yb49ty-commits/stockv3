"""Read-only FastAPI app for the runtime_control dashboard."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ashare_v3.runtime_control.artifacts import apply_artifact_detections
from ashare_v3.runtime_control.pipeline import (
    READY,
    WAIT_MANUAL_CONFIRM,
    RuntimePipelineRun,
    build_action_confirmation_pipeline_run,
    build_nightly_pipeline_run,
    build_pipeline_timeline,
    summarize_quality,
)


TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DOCS_DIR = PROJECT_ROOT / "docs"
DEFAULT_TRADE_DATE = "20260527"


def create_router(
    *,
    default_trade_date: str = DEFAULT_TRADE_DATE,
    docs_dir: Path | str = DEFAULT_DOCS_DIR,
) -> APIRouter:
    router = APIRouter()
    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
    artifact_docs_dir = Path(docs_dir)

    @router.get("/runtime/", response_class=HTMLResponse)
    async def runtime_index() -> RedirectResponse:
        return RedirectResponse(f"/runtime/{default_trade_date}", status_code=307)

    @router.get("/runtime/{trade_date}", response_class=HTMLResponse)
    async def runtime_dashboard_page(request: Request, trade_date: str) -> HTMLResponse:
        dashboard = build_dashboard_payload(trade_date=trade_date, docs_dir=artifact_docs_dir)
        return templates.TemplateResponse(
            request,
            "runtime_dashboard.html",
            {"dashboard": dashboard, "request": request},
        )

    @router.get("/api/runtime/{trade_date}/dashboard")
    async def runtime_dashboard_api(trade_date: str) -> JSONResponse:
        return JSONResponse(build_dashboard_payload(trade_date=trade_date, docs_dir=artifact_docs_dir))

    return router


def create_app(
    *,
    default_trade_date: str = DEFAULT_TRADE_DATE,
    docs_dir: Path | str = DEFAULT_DOCS_DIR,
) -> FastAPI:
    app = FastAPI(
        title="Ashare v3 Runtime Dashboard",
        description="Read-only runtime_control dashboard. No execution endpoints.",
    )
    app.include_router(create_router(default_trade_date=default_trade_date, docs_dir=docs_dir))
    return app


def build_dashboard_payload(*, trade_date: str, docs_dir: Path | str = DEFAULT_DOCS_DIR) -> dict[str, Any]:
    run = apply_artifact_detections(
        build_dashboard_pipeline_run(trade_date=trade_date),
        docs_dir=docs_dir,
    )
    stages = build_stage_rows(run)
    manual_gate_stages = [
        stage
        for stage in stages
        if stage["status"] in (WAIT_MANUAL_CONFIRM, READY)
    ]
    quality_summary = summarize_quality(run.stages)
    return {
        "pipeline": {
            "run_id": run.run_id,
            "pipeline_name": run.pipeline_name,
            "layer_role": run.layer_role,
            "trade_date": run.trade_date,
            "status": run.status,
            "created_at": run.created_at,
            "side_effects": dict(run.side_effects),
        },
        "stages": stages,
        "timeline": build_pipeline_timeline(run),
        "quality_summary": quality_summary,
        "manual_gate": {
            "status": WAIT_MANUAL_CONFIRM,
            "stage_count": len(manual_gate_stages),
            "stages": manual_gate_stages,
        },
        "command_registry": {
            key: entry.to_dict()
            for key, entry in run.command_registry.items()
        },
        "rollback_registry": {
            key: entry.to_dict()
            for key, entry in run.rollback_registry.items()
        },
        "boundaries": {
            "executes_nightly_run": False,
            "executes_commands": False,
            "executes_rollback": False,
            "modifies_n1_n6_execute_contract": False,
            "consumes_outbox": False,
            "starts_worker": False,
            "touches_old_system": False,
        },
    }


def build_dashboard_pipeline_run(*, trade_date: str) -> RuntimePipelineRun:
    if trade_date == "20260602":
        return build_action_confirmation_pipeline_run(trade_date=trade_date)
    return build_nightly_pipeline_run(trade_date=trade_date)


def build_stage_rows(run: RuntimePipelineRun) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sequence, stage in enumerate(run.stages, start=1):
        command = run.command_registry[stage.command_key]
        rollback = run.rollback_registry[stage.rollback_key]
        stage_dict = stage.to_dict(command=command, rollback=rollback)
        stage_dict.update(
            {
                "sequence": sequence,
                "execute_command": " ".join(command.command),
                "rollback_path": rollback.rollback_sql_path,
                "rows_summary_text": format_rows_summary(stage_dict["rows_summary"]),
                "status_class": status_class(str(stage_dict["status"])),
            }
        )
        rows.append(stage_dict)
    return rows


def format_rows_summary(rows_summary: object) -> str:
    if not isinstance(rows_summary, dict) or not rows_summary:
        return ""
    chunks: list[str] = []
    for index, (key, value) in enumerate(rows_summary.items()):
        if index >= 5:
            chunks.append("...")
            break
        if isinstance(value, dict):
            rendered = ", ".join(f"{child_key}={child_value}" for child_key, child_value in list(value.items())[:4])
            chunks.append(f"{key}={{ {rendered} }}")
        else:
            chunks.append(f"{key}={value}")
    return " · ".join(chunks)


def status_class(status: str) -> str:
    return {
        "PASS": "safe",
        "PASSED": "safe",
        "READY": "ready",
        "WAIT_MANUAL_CONFIRM": "wait",
        "NOT_RUN": "wait",
        "BLOCKED": "blocked",
        "FAILED": "failed",
    }.get(status, "wait")


app = create_app()


def main() -> None:
    import os
    import uvicorn

    host = os.environ.get("ASHARE_V3_RUNTIME_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("ASHARE_V3_RUNTIME_WEB_PORT", "8788"))
    uvicorn.run("ashare_v3.web.runtime_dashboard:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
