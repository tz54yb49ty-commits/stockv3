"""FastAPI app for the N2 condition-layer policy console MVP."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates

from ashare_v3.condition.web_policy import (
    N2PolicyConsoleConfig,
    N2PolicyConsoleService,
    default_project_root,
    default_web_policy,
    policy_from_control_payload,
    policy_json_text,
)


TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
WAIT_MANUAL_CONFIRM_STATUS = "WAIT_MANUAL_CONFIRM"


def build_service() -> N2PolicyConsoleService:
    return N2PolicyConsoleService(
        N2PolicyConsoleConfig(
            project_root=default_project_root(),
            dsn=os.environ.get("ASHARE_V3_POSTGRES_DSN", "postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3"),
            use_database=os.environ.get("ASHARE_V3_N2_WEB_USE_DB", "1") != "0",
        )
    )


app = FastAPI(
    title="Ashare v3 N2 Policy Console",
    description="Read-only N2 policy dry-run console. No overwrite execution in MVP.",
)
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
service = build_service()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    context = service.console_context()
    return templates.TemplateResponse(request, "n2_policy_console.html", context)


@app.get("/api/n2/active-run")
async def api_active_run() -> dict[str, Any]:
    return service.active_run()


@app.get("/api/n2/policy/default")
async def api_default_policy() -> dict[str, Any]:
    return service.default_policy_for_console()


@app.get("/api/n2/runs/latest/summary")
async def api_latest_summary() -> dict[str, Any]:
    active = service.active_run()
    return service.pool_scope_summaries(active.get("run_id"))


@app.get("/api/n2/details")
async def api_condition_details(request: Request) -> JSONResponse:
    domain = str(request.query_params.get("domain") or "index")
    table_kind = str(request.query_params.get("table_kind") or "basis")
    result = service.condition_detail(domain, table_kind, request.query_params)
    return JSONResponse(result, status_code=200 if result.get("ok") else 409)


@app.get("/details-fragment", response_class=HTMLResponse)
async def condition_details_fragment(request: Request) -> HTMLResponse:
    domain = str(request.query_params.get("domain") or "index")
    table_kind = str(request.query_params.get("table_kind") or "basis")
    detail = service.condition_detail(domain, table_kind, request.query_params)
    return templates.TemplateResponse(request, "n2_policy_details.html", {"detail": detail})


@app.get("/details-export.xlsx")
async def condition_details_export(request: Request) -> Response:
    domain = str(request.query_params.get("domain") or "index")
    table_kind = str(request.query_params.get("table_kind") or "basis")
    result = service.condition_detail_export(domain, table_kind, request.query_params)
    if not result.get("ok"):
        return JSONResponse(result, status_code=409)
    return Response(
        content=result["content"],
        media_type=result["content_type"],
        headers={"Content-Disposition": f'attachment; filename="{result["filename"]}"'},
    )


@app.get("/policy/default-fragment", response_class=HTMLResponse)
async def default_policy_fragment() -> HTMLResponse:
    return HTMLResponse(policy_json_text(service.default_policy_for_console()))


@app.post("/api/n2/policy/dry-run")
async def api_policy_dry_run(request: Request) -> JSONResponse:
    payload = await request.json()
    policy_payload = payload.get("policy_json")
    if not policy_payload:
        policy_payload = json.dumps(payload.get("policy") or default_web_policy(), ensure_ascii=False)
    result = service.dry_run_policy(str(policy_payload), source_trade_date=payload.get("source_trade_date"))
    return JSONResponse(result, status_code=200 if result.get("ok") else 409)


@app.post("/api/n2/policy/save-default-draft")
async def api_save_default_policy_draft(request: Request) -> JSONResponse:
    payload = await request.json()
    policy_payload = payload.get("policy_json")
    if not policy_payload:
        policy_payload = json.dumps(payload.get("policy") or default_web_policy(), ensure_ascii=False)
    try:
        result = service.save_default_policy_draft(str(policy_payload))
    except ValueError as exc:
        result = {"ok": False, "error": str(exc), "writes_performed": False, "database_written": False}
    return JSONResponse(result, status_code=200 if result.get("ok") else 409)


@app.post("/api/n2/policy/generate-execute-gate")
async def api_generate_execute_gate_draft(request: Request) -> JSONResponse:
    payload = await request.json()
    policy_payload = payload.get("policy_json")
    if not policy_payload:
        policy_payload = json.dumps(payload.get("policy") or default_web_policy(), ensure_ascii=False)
    try:
        result = service.generate_execute_gate_draft(
            str(policy_payload),
            source_trade_date=payload.get("source_trade_date"),
        )
    except ValueError as exc:
        result = {"ok": False, "error": str(exc), "writes_performed": False, "database_written": False}
    return JSONResponse(result, status_code=200 if result.get("ok") else 409)


@app.post("/dry-run", response_class=HTMLResponse)
async def dry_run_fragment(request: Request) -> HTMLResponse:
    body = (await request.body()).decode("utf-8")
    form = parse_qs(body, keep_blank_values=True)
    policy_payload = str((form.get("policy_json") or [""])[0])
    if not policy_payload.strip():
        policy_payload = policy_json_text(policy_from_control_payload(form))
    source_trade_date = str((form.get("source_trade_date") or [""])[0]) or None
    try:
        result = service.dry_run_policy(policy_payload, source_trade_date=source_trade_date)
    except ValueError as exc:
        result = {"ok": False, "error": str(exc)}
    return templates.TemplateResponse(request, "n2_policy_dry_run.html", {"result": result})


@app.post("/api/n2/policy/execute-overwrite")
async def api_execute_overwrite_disabled() -> JSONResponse:
    return JSONResponse(
        {
            "enabled": False,
            "status": "disabled_in_mvp",
            "writes_performed": False,
            "message": "execute-overwrite is intentionally disabled in the N2 web console MVP.",
        },
        status_code=409,
    )


@app.post("/api/n2/policy/confirm-overwrite")
async def api_confirm_overwrite(request: Request) -> JSONResponse:
    payload = await request.json()
    result = service.confirm_overwrite_gate(
        source_trade_date=payload.get("source_trade_date"),
        confirmation_text=str(payload.get("confirmation_text") or ""),
    )
    return JSONResponse(result, status_code=200 if result.get("ok") else 409)


@app.get("/execute-overwrite", response_class=HTMLResponse)
async def execute_overwrite_placeholder(request: Request) -> HTMLResponse:
    source_trade_date = str(request.query_params.get("source_trade_date") or "")
    model = service.overwrite_confirmation_model(source_trade_date=source_trade_date or None)
    return templates.TemplateResponse(
        request,
        "n2_policy_overwrite_confirm.html",
        {"layer_role": "N2_condition", "confirm": model},
    )


def main() -> None:
    import uvicorn

    host = os.environ.get("ASHARE_V3_N2_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("ASHARE_V3_N2_WEB_PORT", "8782"))
    uvicorn.run("ashare_v3.web.n2_policy_console:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
