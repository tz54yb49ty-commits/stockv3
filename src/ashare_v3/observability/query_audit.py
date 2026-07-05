"""Artifact-first structured query audit helpers.

This module intentionally does not create database objects or open database
connections. It can wrap an already-created cursor in later gates, but the
initial sink is a local JSON artifact.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from time import perf_counter
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence


DENIED_DIRECT_READ_TABLES: frozenset[str] = frozenset(
    {
        "stock_condition_display_basis",
        "index_condition_display_basis",
        "board_condition_display_basis",
        "index_membership_fact",
        "board_membership_fact",
    }
)

DENIED_INTRADAY_PATH_ROLES: frozenset[str] = frozenset(
    {
        "n3_intraday_worker",
        "n3_intraday_execute",
        "n4_intraday_worker",
        "n4_intraday_execute",
        "n5_intraday_worker",
        "n5_intraday_execute",
    }
)

APPROVED_ONE_TIME_CONTEXT_REFRESH_TABLES: frozenset[str] = frozenset(
    {
        "common_condition_run",
        "stock_condition_basis",
        "index_condition_basis",
        "board_condition_basis",
        "stock_condition_pool",
        "index_condition_pool",
        "board_condition_pool",
        "stock_minute_target_scope",
        "index_minute_target_scope",
        "board_minute_target_scope",
        "stock_condition_context_enrichment",
        "index_condition_context_enrichment",
        "board_condition_context_enrichment",
    }
)

WRITE_STATEMENT_KINDS: frozenset[str] = frozenset(
    {"INSERT", "UPDATE", "DELETE", "MERGE", "CREATE", "ALTER", "DROP", "TRUNCATE"}
)

VALID_CONNECTION_SITE_CLASSIFICATIONS: frozenset[str] = frozenset(
    {
        "must_wrap",
        "explicit_bypass_readonly_plan",
        "explicit_bypass_one_time_context_refresh",
        "explicit_bypass_metadata_repair",
        "out_of_scope_migration_or_schema_review",
        "out_of_scope_n1_n2_or_migration",
        "blocked_until_refactored",
    }
)

MAX_AUDIT_ARTIFACT_FILENAME_BYTES = 180


class DeniedTableAccessError(RuntimeError):
    """Raised when a guarded path references a denied upstream table."""


@dataclass(frozen=True)
class AuditContext:
    layer_role: str
    source_run_id: str
    stage_id: str
    gate_id: str
    path_role: str
    readonly_expected: bool = True
    bypass_classification: str | None = None
    worker_started: bool = False
    outbox_consumed: bool = False
    checkpoint_updated: bool = False


@dataclass(frozen=True)
class AuditEntry:
    audit_event_id: str
    audit_run_id: str
    layer_role: str
    source_run_id: str
    stage_id: str
    gate_id: str
    path_role: str
    application_name: str
    statement_kind: str
    statement_fingerprint: str
    referenced_tables: list[str]
    denied_table_hit: bool
    started_at: str
    finished_at: str
    duration_ms: float
    rowcount: int | None
    readonly_transaction: bool
    worker_started: bool
    outbox_consumed: bool
    checkpoint_updated: bool
    db_write_attempted: bool
    bypass_classification: str | None = None
    blocked: bool = False
    error_code: str | None = None


class AuditSink(Protocol):
    def emit(self, entry: AuditEntry) -> None:
        """Record one audit entry."""


class ArtifactAuditSink:
    """Collect audit entries and write a local JSON artifact on demand."""

    def __init__(self, artifact_path: Path | str, *, audit_run_id: str) -> None:
        self.artifact_path = Path(artifact_path)
        self.audit_run_id = audit_run_id
        self.entries: list[AuditEntry] = []

    def emit(self, entry: AuditEntry) -> None:
        self.entries.append(entry)

    def write_report(self, *, extra_summary: Mapping[str, Any] | None = None) -> dict[str, Any]:
        report = {
            "audit_run_id": self.audit_run_id,
            "generated_at": _utc_now_iso(),
            "entries": [asdict(entry) for entry in self.entries],
            "summary": self._summary(),
        }
        if extra_summary:
            report["summary"].update(dict(extra_summary))
        self.artifact_path.parent.mkdir(parents=True, exist_ok=True)
        self.artifact_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report

    def _summary(self) -> dict[str, int]:
        return {
            "total_entries": len(self.entries),
            "blocked_entries": sum(1 for entry in self.entries if entry.blocked),
            "denied_table_hit_entries": sum(1 for entry in self.entries if entry.denied_table_hit),
            "db_write_attempted_entries": sum(1 for entry in self.entries if entry.db_write_attempted),
            "worker_started_entries": sum(1 for entry in self.entries if entry.worker_started),
            "outbox_consumed_entries": sum(1 for entry in self.entries if entry.outbox_consumed),
            "checkpoint_updated_entries": sum(1 for entry in self.entries if entry.checkpoint_updated),
        }


class AuditedCursor:
    """Cursor proxy that routes SQL execution through the audit guard."""

    def __init__(self, cursor: Any, *, context: AuditContext, sink: AuditSink) -> None:
        self._cursor = cursor
        self._context = context
        self._sink = sink

    def execute(self, sql_text: str, params: object | None = None) -> Any:
        audit_execute(self._cursor, sql_text, params, self._context, self._sink)
        return self

    def executemany(self, sql_text: str, params_seq: object | None = None) -> Any:
        audit_executemany(self._cursor, sql_text, params_seq, self._context, self._sink)
        return self

    def __enter__(self) -> "AuditedCursor":
        enter = getattr(self._cursor, "__enter__", None)
        if enter is not None:
            entered = enter()
            if entered is not self._cursor:
                self._cursor = entered
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> Any:
        exit_method = getattr(self._cursor, "__exit__", None)
        if exit_method is not None:
            return exit_method(exc_type, exc, tb)
        return None

    def __iter__(self) -> Any:
        return iter(self._cursor)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cursor, name)


class AuditedConnection:
    """Connection proxy that returns audited cursor proxies."""

    def __init__(
        self,
        connection: Any,
        *,
        context: AuditContext,
        sink: AuditSink,
        write_report_on_exit: bool = False,
    ) -> None:
        self._connection = connection
        self._context = context
        self._sink = sink
        self._write_report_on_exit = write_report_on_exit

    def cursor(self, *args: Any, **kwargs: Any) -> AuditedCursor:
        return AuditedCursor(self._connection.cursor(*args, **kwargs), context=self._context, sink=self._sink)

    def __enter__(self) -> "AuditedConnection":
        enter = getattr(self._connection, "__enter__", None)
        if enter is not None:
            entered = enter()
            if entered is not self._connection:
                self._connection = entered
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> Any:
        try:
            exit_method = getattr(self._connection, "__exit__", None)
            if exit_method is not None:
                return exit_method(exc_type, exc, tb)
            return None
        finally:
            if self._write_report_on_exit and isinstance(self._sink, ArtifactAuditSink):
                self._sink.write_report()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)


@dataclass(frozen=True)
class ConnectionSite:
    path: str
    relative_path: str
    line_number: int
    line_text: str

    def key(self) -> str:
        return f"{self.relative_path}:{self.line_number}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "relative_path": self.relative_path,
            "line_number": self.line_number,
            "line_text": self.line_text.strip(),
            "key": self.key(),
        }


def build_application_name(context: AuditContext) -> str:
    full = ":".join(
        [
            "ashare_v3",
            _safe_component(context.layer_role),
            _safe_component(context.stage_id),
            _safe_component(context.source_run_id),
            _safe_component(context.gate_id),
        ]
    )
    if len(full) <= 63:
        return full
    digest = sha256(full.encode("utf-8")).hexdigest()[:8]
    compact = ":".join(
        [
            "ashare_v3",
            _safe_component(context.layer_role),
            _safe_component(context.stage_id),
            digest,
        ]
    )
    if len(compact) <= 63:
        return compact
    prefix = f"ashare_v3:{_safe_component(context.layer_role)}:"
    max_stage_len = max(1, 63 - len(prefix) - len(digest) - 1)
    return f"{prefix}{_safe_component(context.stage_id)[:max_stage_len]}:{digest}"


def fingerprint_sql(sql_text: str) -> str:
    normalized = _normalize_sql(sql_text)
    return sha256(normalized.encode("utf-8")).hexdigest()


def classify_statement_kind(sql_text: str) -> str:
    normalized = sql_text.lstrip()
    if not normalized:
        return "UNKNOWN"
    first = re.match(r"([A-Za-z]+)", normalized)
    if not first:
        return "UNKNOWN"
    return first.group(1).upper()


def extract_referenced_tables(sql_text: str) -> list[str]:
    cte_names = _extract_cte_names(sql_text)
    tables: list[str] = []
    for pattern in (
        r"\bFROM\s+([A-Za-z_][\w$]*|\"[^\"]+\")(?:\s*\.\s*([A-Za-z_][\w$]*|\"[^\"]+\"))?",
        r"\bJOIN\s+([A-Za-z_][\w$]*|\"[^\"]+\")(?:\s*\.\s*([A-Za-z_][\w$]*|\"[^\"]+\"))?",
        r"\bUPDATE\s+([A-Za-z_][\w$]*|\"[^\"]+\")(?:\s*\.\s*([A-Za-z_][\w$]*|\"[^\"]+\"))?",
        r"\bINTO\s+([A-Za-z_][\w$]*|\"[^\"]+\")(?:\s*\.\s*([A-Za-z_][\w$]*|\"[^\"]+\"))?",
        r"\bTRUNCATE\s+(?:TABLE\s+)?([A-Za-z_][\w$]*|\"[^\"]+\")(?:\s*\.\s*([A-Za-z_][\w$]*|\"[^\"]+\"))?",
    ):
        for match in re.finditer(pattern, sql_text, flags=re.IGNORECASE):
            table = _table_name_from_match(match)
            if table and table not in cte_names and table not in tables:
                tables.append(table)
    return tables


def assert_no_denied_tables(context: AuditContext, sql_text: str) -> None:
    tables = set(extract_referenced_tables(sql_text))
    denied_hits = tables.intersection(DENIED_DIRECT_READ_TABLES)
    if context.path_role in DENIED_INTRADAY_PATH_ROLES and denied_hits:
        raise DeniedTableAccessError(
            f"Denied direct table access in {context.path_role}: {', '.join(sorted(denied_hits))}"
        )
    if context.bypass_classification == "explicit_bypass_one_time_context_refresh" and denied_hits:
        raise DeniedTableAccessError(
            "N4 one-time context refresh bypass cannot read denied external display/membership tables: "
            + ", ".join(sorted(denied_hits))
        )
    if context.bypass_classification == "explicit_bypass_metadata_repair" and denied_hits:
        raise DeniedTableAccessError(
            "N5 metadata repair bypass cannot read denied external display/membership tables: "
            + ", ".join(sorted(denied_hits))
        )
    if context.path_role == "n4_one_time_context_refresh":
        disallowed = tables.difference(APPROVED_ONE_TIME_CONTEXT_REFRESH_TABLES)
        if denied_hits or disallowed:
            hits = denied_hits.union(disallowed)
            raise DeniedTableAccessError(
                "N4 one-time context refresh may only access approved context sources: "
                + ", ".join(sorted(hits))
            )


def audit_execute(
    cursor: Any,
    sql_text: str,
    params: object | None,
    context: AuditContext,
    sink: AuditSink,
) -> AuditEntry:
    started_at = _utc_now_iso()
    started = perf_counter()
    referenced_tables = extract_referenced_tables(sql_text)
    statement_kind = classify_statement_kind(sql_text)
    db_write_attempted = statement_kind in WRITE_STATEMENT_KINDS
    try:
        assert_no_denied_tables(context, sql_text)
    except DeniedTableAccessError:
        entry = _build_entry(
            context=context,
            sink=sink,
            sql_text=sql_text,
            referenced_tables=referenced_tables,
            statement_kind=statement_kind,
            started_at=started_at,
            started=started,
            rowcount=None,
            db_write_attempted=db_write_attempted,
            blocked=True,
            error_code="denied_table_access",
        )
        sink.emit(entry)
        raise
    cursor.execute(sql_text, params)
    rowcount = getattr(cursor, "rowcount", None)
    entry = _build_entry(
        context=context,
        sink=sink,
        sql_text=sql_text,
        referenced_tables=referenced_tables,
        statement_kind=statement_kind,
        started_at=started_at,
        started=started,
        rowcount=rowcount if isinstance(rowcount, int) else None,
        db_write_attempted=db_write_attempted,
    )
    sink.emit(entry)
    return entry


def audit_executemany(
    cursor: Any,
    sql_text: str,
    params_seq: object | None,
    context: AuditContext,
    sink: AuditSink,
) -> AuditEntry:
    started_at = _utc_now_iso()
    started = perf_counter()
    referenced_tables = extract_referenced_tables(sql_text)
    statement_kind = classify_statement_kind(sql_text)
    db_write_attempted = statement_kind in WRITE_STATEMENT_KINDS
    try:
        assert_no_denied_tables(context, sql_text)
    except DeniedTableAccessError:
        entry = _build_entry(
            context=context,
            sink=sink,
            sql_text=sql_text,
            referenced_tables=referenced_tables,
            statement_kind=statement_kind,
            started_at=started_at,
            started=started,
            rowcount=None,
            db_write_attempted=db_write_attempted,
            blocked=True,
            error_code="denied_table_access",
        )
        sink.emit(entry)
        raise
    cursor.executemany(sql_text, params_seq)
    rowcount = getattr(cursor, "rowcount", None)
    entry = _build_entry(
        context=context,
        sink=sink,
        sql_text=sql_text,
        referenced_tables=referenced_tables,
        statement_kind=statement_kind,
        started_at=started_at,
        started=started,
        rowcount=rowcount if isinstance(rowcount, int) else None,
        db_write_attempted=db_write_attempted,
    )
    sink.emit(entry)
    return entry


def audited_connect(
    connect: Callable[..., Any],
    *args: Any,
    context: AuditContext,
    sink: AuditSink,
    write_report_on_exit: bool = False,
    **kwargs: Any,
) -> AuditedConnection:
    kwargs.setdefault("application_name", build_application_name(context))
    return AuditedConnection(
        connect(*args, **kwargs),
        context=context,
        sink=sink,
        write_report_on_exit=write_report_on_exit,
    )


def audited_psycopg_connect(
    *args: Any,
    context: AuditContext,
    sink: AuditSink | None = None,
    artifact_dir: Path | str | None = None,
    **kwargs: Any,
) -> AuditedConnection:
    import psycopg

    audit_sink = sink or make_artifact_audit_sink(context, artifact_dir=artifact_dir)
    return audited_connect(
        psycopg.connect,
        *args,
        context=context,
        sink=audit_sink,
        write_report_on_exit=sink is None,
        **kwargs,
    )


def make_artifact_audit_sink(
    context: AuditContext,
    *,
    artifact_dir: Path | str | None = None,
) -> ArtifactAuditSink:
    audit_run_id = "_".join(
        _safe_component(part)
        for part in (
            context.layer_role,
            context.stage_id,
            context.source_run_id,
            context.gate_id,
        )
    )
    root = Path(artifact_dir or os.environ.get("ASHARE_QUERY_AUDIT_DIR", "docs/query_audit"))
    return ArtifactAuditSink(root / _bounded_audit_artifact_filename(audit_run_id), audit_run_id=audit_run_id)


def make_audit_context(
    *,
    layer_role: str,
    stage_id: str,
    gate_id: str,
    path_role: str,
    source_run_id: str | None = None,
    readonly_expected: bool = True,
    bypass_classification: str | None = None,
    worker_started: bool = False,
    outbox_consumed: bool = False,
    checkpoint_updated: bool = False,
) -> AuditContext:
    return AuditContext(
        layer_role=layer_role,
        source_run_id=source_run_id or os.environ.get("ASHARE_QUERY_AUDIT_SOURCE_RUN_ID", "unbound_source_run"),
        stage_id=stage_id,
        gate_id=gate_id,
        path_role=path_role,
        readonly_expected=readonly_expected,
        bypass_classification=bypass_classification,
        worker_started=worker_started,
        outbox_consumed=outbox_consumed,
        checkpoint_updated=checkpoint_updated,
    )


def inventory_psycopg_connect_sites(paths: Sequence[Path | str]) -> list[ConnectionSite]:
    roots = [Path(path) for path in paths]
    sites: list[ConnectionSite] = []
    for root in roots:
        files = [root] if root.is_file() else sorted(root.rglob("*.py"))
        for file_path in files:
            if "__pycache__" in file_path.parts:
                continue
            try:
                lines = file_path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            for line_number, line_text in enumerate(lines, start=1):
                if "psycopg.connect" in line_text:
                    sites.append(
                        ConnectionSite(
                            path=str(file_path),
                            relative_path=_relative_path(file_path, root),
                            line_number=line_number,
                            line_text=line_text,
                        )
                    )
    return sites


def build_static_coverage_report(
    paths: Sequence[Path | str],
    classifications: Mapping[str, str],
) -> dict[str, Any]:
    invalid = sorted(set(classifications.values()).difference(VALID_CONNECTION_SITE_CLASSIFICATIONS))
    if invalid:
        raise ValueError(f"Invalid connection site classification(s): {', '.join(invalid)}")
    sites = inventory_psycopg_connect_sites(paths)
    classified_sites: list[dict[str, Any]] = []
    unclassified_sites: list[dict[str, Any]] = []
    classification_counts = {state: 0 for state in sorted(VALID_CONNECTION_SITE_CLASSIFICATIONS)}
    for site in sites:
        classification = classifications.get(site.key())
        site_dict = site.as_dict()
        if classification is None:
            unclassified_sites.append(site_dict)
            continue
        classification_counts[classification] += 1
        site_dict["classification"] = classification
        classified_sites.append(site_dict)
    return {
        "result": "PASS" if not unclassified_sites else "BLOCKED",
        "total_sites": len(sites),
        "classified_count": len(classified_sites),
        "unclassified_count": len(unclassified_sites),
        "classification_counts": classification_counts,
        "classified_sites": classified_sites,
        "unclassified_sites": unclassified_sites,
    }


def _build_entry(
    *,
    context: AuditContext,
    sink: AuditSink,
    sql_text: str,
    referenced_tables: list[str],
    statement_kind: str,
    started_at: str,
    started: float,
    rowcount: int | None,
    db_write_attempted: bool,
    blocked: bool = False,
    error_code: str | None = None,
) -> AuditEntry:
    finished_at = _utc_now_iso()
    duration_ms = round((perf_counter() - started) * 1000, 3)
    denied_table_hit = bool(set(referenced_tables).intersection(DENIED_DIRECT_READ_TABLES))
    audit_run_id = getattr(sink, "audit_run_id", "audit_run")
    event_material = "|".join(
        [
            audit_run_id,
            context.layer_role,
            context.source_run_id,
            context.stage_id,
            context.gate_id,
            fingerprint_sql(sql_text),
            started_at,
        ]
    )
    return AuditEntry(
        audit_event_id=sha256(event_material.encode("utf-8")).hexdigest(),
        audit_run_id=audit_run_id,
        layer_role=context.layer_role,
        source_run_id=context.source_run_id,
        stage_id=context.stage_id,
        gate_id=context.gate_id,
        path_role=context.path_role,
        application_name=build_application_name(context),
        statement_kind=statement_kind,
        statement_fingerprint=fingerprint_sql(sql_text),
        referenced_tables=referenced_tables,
        denied_table_hit=denied_table_hit,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        rowcount=rowcount,
        readonly_transaction=context.readonly_expected,
        worker_started=context.worker_started,
        outbox_consumed=context.outbox_consumed,
        checkpoint_updated=context.checkpoint_updated,
        db_write_attempted=db_write_attempted,
        bypass_classification=context.bypass_classification,
        blocked=blocked,
        error_code=error_code,
    )


def _extract_cte_names(sql_text: str) -> set[str]:
    prefix = sql_text.lstrip()
    if not prefix.upper().startswith("WITH"):
        return set()
    before_main_select = prefix[: prefix.upper().find("SELECT", 6)] if "SELECT" in prefix.upper()[6:] else prefix
    names = set()
    for match in re.finditer(r"(?:WITH|,)\s+([A-Za-z_][\w$]*|\"[^\"]+\")\s+AS\s*\(", before_main_select, re.IGNORECASE):
        names.add(_clean_identifier(match.group(1)))
    return names


def _table_name_from_match(match: re.Match[str]) -> str:
    first = _clean_identifier(match.group(1))
    second = _clean_identifier(match.group(2)) if match.lastindex and match.group(2) else ""
    return second or first


def _clean_identifier(identifier: str) -> str:
    return identifier.strip().strip('"').lower()


def _normalize_sql(sql_text: str) -> str:
    without_string_literals = re.sub(r"'(?:''|[^'])*'", "?", sql_text)
    without_numeric_literals = re.sub(r"\b\d+(?:\.\d+)?\b", "?", without_string_literals)
    return re.sub(r"\s+", " ", without_numeric_literals).strip().lower()


def _safe_component(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value)
    return safe.strip("_") or "na"


def _bounded_audit_artifact_filename(audit_run_id: str) -> str:
    suffix = ".json"
    safe = _safe_component(audit_run_id)
    candidate = f"{safe}{suffix}"
    if len(candidate.encode("utf-8")) <= MAX_AUDIT_ARTIFACT_FILENAME_BYTES:
        return candidate
    digest = sha256(safe.encode("utf-8")).hexdigest()[:16]
    max_prefix_bytes = MAX_AUDIT_ARTIFACT_FILENAME_BYTES - len(suffix.encode("utf-8")) - len(digest) - 1
    prefix = safe.encode("utf-8")[:max_prefix_bytes].decode("utf-8", errors="ignore").rstrip("._-")
    return f"{prefix or 'audit'}_{digest}{suffix}"


def _relative_path(file_path: Path, root: Path) -> str:
    try:
        return str(file_path.relative_to(root))
    except ValueError:
        return file_path.name


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
