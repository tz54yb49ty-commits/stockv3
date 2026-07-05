"""Read-only artifact-first RAG helpers for the N6 admin UI."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


MAX_LIMIT = 20
DEFAULT_LIMIT = 8
MAX_TEXT_BYTES = 512_000
PREVIEW_CHARS = 360
SKIP_NAME_PARTS = (
    "_snapshot_v1",
    "probe_cache",
    "tushare_probe_cache",
    "sample_snapshot",
    "backup_before",
    "backup_after",
)
READ_ONLY_RAG_SAFETY = {
    "executes_commands": False,
    "writes_database": False,
    "starts_worker": False,
    "reads_secret": False,
    "uses_external_llm": False,
    "updates_outbox_inbox_checkpoint": False,
}


def read_rag_status_answer(
    *,
    docs_root: Path | str,
    sql_root: Path | str,
    query: str,
    limit: int = DEFAULT_LIMIT,
    layer_role: str | None = None,
    trade_date: str | None = None,
    artifact_type: str | None = None,
) -> dict[str, Any]:
    normalized_limit = min(max(int(limit or DEFAULT_LIMIT), 1), MAX_LIMIT)
    q = str(query or "").strip()
    if not q:
        return no_evidence_answer(q, "请输入要检索的问题。")

    artifacts = list(iter_artifacts(Path(docs_root), Path(sql_root)))
    matches = rank_artifacts(
        artifacts,
        query=q,
        layer_role=str(layer_role or "").strip(),
        trade_date=normalize_trade_date(trade_date),
        artifact_type=str(artifact_type or "").strip(),
    )[:normalized_limit]
    if not matches:
        return no_evidence_answer(q, "没有找到可引用的本地 artifact 证据。")

    return {
        "ok": True,
        "component": "A-Track Read-only RAG",
        "answer_status": "ANSWERED",
        "query": q,
        "answer": build_answer(q, matches),
        "evidence": [evidence_item(row) for row in matches],
        "safety": dict(READ_ONLY_RAG_SAFETY),
        "suggested_next_question": suggested_next_question(q, matches),
        "disabled_entrypoints": {
            "execute": True,
            "retry": True,
            "rollback": True,
            "worker": True,
            "delivery": True,
            "trade": True,
        },
    }


def no_evidence_answer(query: str, answer: str) -> dict[str, Any]:
    return {
        "ok": True,
        "component": "A-Track Read-only RAG",
        "answer_status": "NO_EVIDENCE",
        "query": query,
        "answer": answer,
        "evidence": [],
        "safety": dict(READ_ONLY_RAG_SAFETY),
        "suggested_next_question": "",
        "disabled_entrypoints": {
            "execute": True,
            "retry": True,
            "rollback": True,
            "worker": True,
            "delivery": True,
            "trade": True,
        },
    }


def iter_artifacts(docs_root: Path, sql_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for root, patterns in ((docs_root, ("*.json", "*.md")), (sql_root, ("*rollback*.sql",))):
        if not root.exists():
            continue
        for pattern in patterns:
            for path in root.rglob(pattern):
                row = load_artifact(path, root)
                if row is not None:
                    rows.append(row)
    return rows


def load_artifact(path: Path, root: Path) -> dict[str, Any] | None:
    name = path.name
    lowered = name.lower()
    if any(part in lowered for part in SKIP_NAME_PARTS):
        return None
    try:
        stat = path.stat()
    except OSError:
        return None
    if stat.st_size > MAX_TEXT_BYTES and path.suffix.lower() != ".sql":
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    metadata = extract_metadata(path, text)
    relative_path = str(path.relative_to(root.parent if root.name in {"docs", "sql"} else root))
    title = metadata.get("title") or title_from_text(path, text)
    search_text = " ".join(
        str(value)
        for value in (
            relative_path,
            title,
            metadata.get("result"),
            metadata.get("status"),
            metadata.get("run_id"),
            metadata.get("source_trade_date"),
            metadata.get("for_trade_date"),
            text[:4000],
        )
        if value
    )
    return {
        "path": relative_path,
        "file_name": name,
        "mtime": stat.st_mtime,
        "size_bytes": stat.st_size,
        "title": title,
        "text_preview": compact_text(text[:PREVIEW_CHARS]),
        "search_text": search_text,
        "artifact_type": infer_artifact_type(path),
        "layer_role": infer_layer_role(relative_path, search_text),
        "gate_name": infer_gate_name(path),
        **metadata,
    }


def extract_metadata(path: Path, text: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            metadata["result"] = stringify(data.get("result") or data.get("status"))
            metadata["status"] = stringify(data.get("status") or data.get("preflight_result"))
            metadata["source_trade_date"] = stringify(data.get("source_trade_date"))
            metadata["for_trade_date"] = stringify(data.get("for_trade_date"))
            metadata["run_id"] = first_present(
                data,
                "run_id",
                "execute_run_id",
                "action_run_id",
                "source_run_id",
                "source_batch_id",
                "target_run_id",
                "n2_active_condition_run",
                "n3_subscription_run",
            )
            metadata["rerun_required"] = data.get("rerun_required")
            metadata["recommended_next_gate"] = stringify(data.get("recommended_next_gate"))
            proof = data.get("current_one_shot_proof")
            if isinstance(proof, dict):
                if not metadata.get("result"):
                    metadata["result"] = stringify(proof.get("result"))
                if not metadata.get("source_trade_date"):
                    metadata["source_trade_date"] = stringify(proof.get("source_trade_date"))
                if not metadata.get("for_trade_date"):
                    metadata["for_trade_date"] = stringify(proof.get("for_trade_date"))
    return metadata


def rank_artifacts(
    artifacts: list[dict[str, Any]],
    *,
    query: str,
    layer_role: str,
    trade_date: str,
    artifact_type: str,
) -> list[dict[str, Any]]:
    query_dates = set(re.findall(r"(?:19|20)\d{6}", query))
    if trade_date:
        query_dates.add(trade_date)
    query_tokens = tokenize(query)
    ranked: list[dict[str, Any]] = []
    for row in artifacts:
        if layer_role and row.get("layer_role") != layer_role:
            continue
        if artifact_type and row.get("artifact_type") != artifact_type:
            continue
        haystack = str(row.get("search_text") or "")
        if query_dates and not any(date in haystack for date in query_dates):
            continue
        score = score_artifact(row, query_tokens, query_dates, query)
        if score <= 0:
            continue
        ranked.append({**row, "score": score, "matched_fields": matched_fields(row, query_tokens, query_dates)})
    ranked.sort(key=lambda item: (int(item.get("score") or 0), float(item.get("mtime") or 0)), reverse=True)
    return ranked


def score_artifact(row: dict[str, Any], tokens: list[str], dates: set[str], query: str) -> int:
    haystack = str(row.get("search_text") or "").lower()
    file_stem = str(row.get("file_name") or "").lower().removesuffix(".json").removesuffix(".md").removesuffix(".sql")
    score = 0
    if file_stem and file_stem in query.lower():
        score += 60
    for date in dates:
        if date in haystack:
            score += 12
    for token in tokens:
        if token in haystack:
            score += 3
    artifact_type = str(row.get("artifact_type") or "")
    lower_query = query.lower()
    if "rerun" in lower_query or "重跑" in query:
        if row.get("rerun_required") is not None or "revalidation" in haystack:
            score += 25
    if "完成" in query or "pass" in lower_query:
        if row.get("result") in {"EXECUTE_PASS", "POST_REVIEW_PASS", "REVALIDATION_PASS"}:
            score += 14
    if "rollback" in lower_query or "回滚" in query:
        if artifact_type == "rollback":
            score += 25
    if "closeout" in lower_query or "收口" in query:
        if artifact_type == "closeout":
            score += 25
        if row.get("result") == "CLOSEOUT_PASS":
            score += 6
    if "active" in lower_query or "当前" in query:
        if row.get("run_id") or "passed_active" in haystack:
            score += 8
    if row.get("file_name") == "00_status.json" and (
        dates or "fast lane" in lower_query or "post close" in lower_query or "完成" in query
    ):
        score += 10
    if artifact_type == "post_review":
        score += 4
    return score


def build_answer(query: str, matches: list[dict[str, Any]]) -> str:
    top = matches[0]
    lower_query = query.lower()
    if "rerun" in lower_query or "重跑" in query:
        rerun = top.get("rerun_required")
        if rerun is not None:
            value = "true" if bool(rerun) else "false"
            next_gate = top.get("recommended_next_gate") or "NONE"
            return f"rerun_required={value}; recommended_next_gate={next_gate}。"
    if top.get("file_name") == "00_status.json" or "是否完成" in query or "完成" in query:
        result = top.get("result") or "UNKNOWN"
        source_trade_date = top.get("source_trade_date") or "—"
        for_trade_date = top.get("for_trade_date") or "—"
        return f"找到 Fast Lane 状态：result={result}; source_trade_date={source_trade_date}; for_trade_date={for_trade_date}。"
    if top.get("artifact_type") == "rollback":
        return f"找到 rollback SQL evidence：{top.get('path')}。"
    result = top.get("result") or top.get("status") or "FOUND"
    return f"找到 {len(matches)} 条本地 artifact 证据；最高相关结果为 {result}，路径 {top.get('path')}。"


def evidence_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": str(row.get("path") or ""),
        "title": str(row.get("title") or ""),
        "result": stringify(row.get("result") or row.get("status")),
        "artifact_type": str(row.get("artifact_type") or ""),
        "layer_role": str(row.get("layer_role") or ""),
        "gate_name": str(row.get("gate_name") or ""),
        "run_id": stringify(row.get("run_id")),
        "matched_fields": [str(item) for item in list(row.get("matched_fields") or [])],
        "text_preview": str(row.get("text_preview") or ""),
    }


def suggested_next_question(query: str, matches: list[dict[str, Any]]) -> str:
    text = query.lower()
    top = matches[0] if matches else {}
    for_trade_date = top.get("for_trade_date") or ""
    if "rerun" in text or "重跑" in query:
        return f"查看 {for_trade_date} Fast Lane 状态" if for_trade_date else "查看最新 Fast Lane 状态"
    if "完成" in query:
        return "是否需要重跑"
    return ""


def matched_fields(row: dict[str, Any], tokens: list[str], dates: set[str]) -> list[str]:
    fields: list[str] = []
    for key in ("path", "title", "result", "status", "run_id", "source_trade_date", "for_trade_date"):
        value = str(row.get(key) or "").lower()
        if any(token in value for token in tokens) or any(date in value for date in dates):
            fields.append(key)
    return fields or ["text"]


def infer_artifact_type(path: Path) -> str:
    name = path.name.lower()
    if path.suffix.lower() == ".sql":
        return "rollback"
    if "closeout" in name:
        return "closeout"
    if "00_status" in name:
        return "status"
    if "post_review" in name:
        return "post_review"
    if "execute_report" in name:
        return "execute_report"
    if "contract" in name or "spec" in name or "design" in name:
        return "spec"
    return "artifact"


def infer_layer_role(path: str, text: str) -> str:
    blob = f"{path} {text}".upper()
    if "RUNTIME_CONTROL" in blob:
        return "runtime_control"
    for layer in ("N1", "N2", "N3", "N4", "N5", "N6"):
        if layer in blob:
            return {
                "N1": "N1_ingestion",
                "N2": "N2_condition",
                "N3": "N3_market_data",
                "N4": "N4_trigger",
                "N5": "N5_action",
                "N6": "N6_user",
            }[layer]
    return ""


def infer_gate_name(path: Path) -> str:
    stem = path.stem
    return stem[:-5] if stem.endswith(".json") else stem


def title_from_text(path: Path, text: str) -> str:
    for line in text.splitlines()[:12]:
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return path.name


def tokenize(value: str) -> list[str]:
    raw = re.findall(r"[A-Za-z0-9_:\-]+|[\u4e00-\u9fff]{2,}", value.lower())
    stop = {"是否", "什么", "当前", "这个", "那个"}
    tokens: list[str] = []
    for item in raw:
        if not item or item in stop:
            continue
        tokens.append(item)
        if "_" in item or "-" in item:
            tokens.extend(part for part in re.split(r"[_\-:]+", item) if len(part) > 1)
    seen: set[str] = set()
    return [item for item in tokens if not (item in seen or seen.add(item))]


def normalize_trade_date(value: str | None) -> str:
    text = str(value or "").strip()
    return text if re.fullmatch(r"20\d{6}", text) else ""


def compact_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def stringify(value: Any) -> str:
    return "" if value is None else str(value)


def first_present(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if value is not None and value != "":
            return str(value)
    return ""
