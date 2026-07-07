"""N3P mixed realtime current source fetch provider seam.

This module owns the production-shaped provider contract for the combined N3
child runner. The actual market/database I/O is injected through a backend so
patch tests can validate the contract without pulling行情 or writing DB.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta, timezone
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
from typing import Any


N3_READY_RESULT = "EXECUTE_READY_REAL_IO_CONTRACT"
N3P_SOURCE_FETCH_PROVIDER_BACKEND_BLOCKER = "BLOCKED_N3P_SOURCE_FETCH_PROVIDER_BACKEND"
N3P_SOURCE_FETCH_BACKEND_CONFIG_BLOCKER = "BLOCKED_N3P_SOURCE_FETCH_BACKEND_CONFIG"
N3P_SOURCE_FETCH_BACKEND_FETCHER_BLOCKER = "BLOCKED_N3P_SOURCE_FETCH_BACKEND_FETCHER"
N3P_SOURCE_FETCH_BACKEND_ARTIFACT_WRITER_BLOCKER = "BLOCKED_N3P_SOURCE_FETCH_BACKEND_ARTIFACT_WRITER"
N3P_SOURCE_FETCH_BACKEND_REGISTRATION_BLOCKER = "BLOCKED_N3P_SOURCE_FETCH_BACKEND_REGISTRATION"
N3P_SOURCE_SCOPE_NOT_READY_BLOCKER = "BLOCKED_N3P_SOURCE_SCOPE_NOT_READY"
N3P_SOURCE_FETCH_PRECHECK_BLOCKER = "BLOCKED_N3P_SOURCE_FETCH_PRECHECK"
N3P_SOURCE_FETCH_PAYLOAD_BLOCKER = "BLOCKED_N3P_SOURCE_PAYLOAD_INVALID"
N3P_SOURCE_TIME_RELABEL_BLOCKER = "BLOCKED_N3P_SOURCE_TIME_RELABEL_RISK"
N3P_SOURCE_POST_CLOSE_PROOF_MINUTE_BLOCKER = "BLOCKED_N3P_SOURCE_POST_CLOSE_PROOF_MINUTE"
N3P_SOURCE_CANONICAL_MINUTE_ALIGNMENT_BLOCKER = "BLOCKED_N3P_SOURCE_CANONICAL_MINUTE_ALIGNMENT"
N3P_SOURCE_MIDDAY_STOCK_TIME_STALE_BLOCKER = "BLOCKED_N3P_SOURCE_MIDDAY_STOCK_TIME_STALE"
N3P_SOURCE_ALIGNMENT_ALIGNED = "aligned"
N3P_SOURCE_ALIGNMENT_INDEPENDENT_REALTIME_OK = "independent_realtime_sources_ok"
N3P_SOURCE_ALIGNMENT_ADJACENT_REALTIME_OK = "adjacent_minute_realtime_ok"
N3P_SOURCE_ALIGNMENT_BLOCKED = "blocked"
N3P_SOURCE_ALIGNMENT_ADJACENT_RACE = "adjacent_minute_source_boundary_race"
N3P_SOURCE_ALIGNMENT_CANONICAL_MISMATCH = "canonical_minute_mismatch"
N3P_SOURCE_ALIGNMENT_MIDDAY_STOCK_STALE = "midday_stock_quote_time_stale"
N3P_SOURCE_PAYLOAD_REGISTRATION_BACKEND_BLOCKER = "BLOCKED_N3P_SOURCE_PAYLOAD_REGISTRATION_BACKEND"
N3P_TRIGGER_PROOF_PREFLIGHT_BACKEND_BLOCKER = "BLOCKED_N3P_PREFLIGHT_ENTRYPOINT_CONTRACT"
N3P_TRIGGER_PROOF_SOURCE_PAYLOAD_BLOCKER = "BLOCKED_SOURCE_PAYLOAD_CONTRACT"
N3P_TRIGGER_PROOF_TARGET_ABSENCE_BLOCKER = "BLOCKED_TARGET_ABSENCE_CONTRACT"
N3P_TRIGGER_PROOF_PREFLIGHT_ARTIFACT_PATH_MISSING_BLOCKER = "BLOCKED_N3P_PREFLIGHT_ARTIFACT_PATH_MISSING"
N3P_TRIGGER_PROOF_PREFLIGHT_ARTIFACT_CONTRACT_BLOCKER = "BLOCKED_N3P_PREFLIGHT_ARTIFACT_CONTRACT"
N3P_TRIGGER_PROOF_PREFLIGHT_ARTIFACT_MATERIALIZATION_BLOCKER = "BLOCKED_N3P_PREFLIGHT_ARTIFACT_MATERIALIZATION"

N3P_SOURCE_MODEL = "n3p_trigger_proof_realtime_v1"
N3P_MAX_CANONICAL_PROOF_HHMM = "1500"
N3P_STOCK_QUOTE_CANONICAL_PROOF_MINUTE_POLICY = "stock_quote_servertime_to_a1_canonical_proof_minute_v1"
_DEFAULT_BACKEND = object()

N3P_TRIGGER_PROOF_PREFLIGHT_ALLOWED_WRITE_TABLES = (
    "common_market_data_run",
    "common_market_data_quality_item",
    "stock_action_confirmation_projection_metric",
    "index_action_confirmation_projection_metric",
    "board_action_confirmation_projection_metric",
)
N3P_TRIGGER_PROOF_EXPECTED_NOT_READY_BLOCKED_REASONS = (
    "stock_quote_zero_price_ohlc_volume",
)
N3P_TRIGGER_PROOF_EXPECTED_NOT_READY_BLOCKED_REASON_PREFIXES = (
    "formal_amount_chain_missing:",
)
N3P_TRIGGER_PROOF_PREFLIGHT_FORBIDDEN_WRITE_TABLES = (
    "common_event_outbox",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "common_trigger_run",
    "common_trigger_state",
    "common_trigger_match",
    "common_action_run",
    "common_action_event",
    "stock_action_fact",
    "index_action_fact",
    "board_action_fact",
    "user_projection_run",
    "user_signal_projection",
    "user_signal_card",
    "user_notification_queue",
    "user_sim_order",
    "user_sim_trade",
    "user_sim_position",
)

_FORBIDDEN_SIDE_EFFECTS = {
    "runtime_executed": False,
    "outbox_consumed": False,
    "inbox_or_checkpoint_updated": False,
    "worker_started": False,
    "rollback_executed": False,
    "schema_changed": False,
    "n4_n5_n6_touched": False,
    "n5_n6_touched": False,
}


class N3PCurrentMarketFetchAdapter:
    """Lazy low-level market adapter for N3P current-source fetch.

    Construction must not import or call mootdx. The client is resolved only
    when a fetch method is invoked by an explicitly authorized execute gate.
    """

    def __init__(self, *, client_factory: Callable[[], Any] | None = None) -> None:
        self._client_factory = client_factory or _default_mootdx_client
        self._client: Any = None

    def fetch_stock_quote_rows(self, *, obj: Mapping[str, Any] | None = None, symbol: str | None = None, **_kwargs: Any) -> Any:
        return self.quotes(symbol=str(symbol or (obj or {}).get("code") or ""))

    def fetch_index_board_1m_rows(
        self,
        *,
        obj: Mapping[str, Any] | None = None,
        symbol: str | None = None,
        frequency: int = 8,
        start: int = 0,
        offset: int = 800,
        market: int | None = None,
        **_kwargs: Any,
    ) -> Any:
        return self.index_bars(
            symbol=str(symbol or (obj or {}).get("code") or ""),
            frequency=frequency,
            start=start,
            offset=offset,
            market=market,
        )

    def fetch_stock_quotes(self, stock_objects: Sequence[Mapping[str, Any]], *_args: Any, **_kwargs: Any) -> list[Mapping[str, Any]]:
        rows: list[Mapping[str, Any]] = []
        for obj in stock_objects:
            rows.extend(_records_from_frame(self.fetch_stock_quote_rows(obj=obj, symbol=str(obj.get("code") or ""))))
        return rows

    def fetch_index_board_1m(
        self,
        index_objects: Sequence[Mapping[str, Any]],
        board_objects: Sequence[Mapping[str, Any]],
        *_args: Any,
        **_kwargs: Any,
    ) -> list[Mapping[str, Any]]:
        rows: list[Mapping[str, Any]] = []
        for obj in (*index_objects, *board_objects):
            rows.extend(
                _records_from_frame(
                    self.fetch_index_board_1m_rows(
                        obj=obj,
                        symbol=str(obj.get("code") or ""),
                        frequency=8,
                        start=0,
                        offset=800,
                        market=_market_code_for_object(obj),
                    )
                )
            )
        return rows

    def quotes(self, *, symbol: str, **kwargs: Any) -> Any:
        if not symbol:
            raise RuntimeError("stock quote symbol is required")
        method = getattr(self._resolve_client(), "quotes", None)
        if not callable(method):
            raise RuntimeError("mootdx client does not expose quotes()")
        return _call_with_supported_kwargs(method, symbol=symbol, **kwargs)

    def index_bars(self, *, symbol: str, frequency: int = 8, start: int = 0, offset: int = 800, market: int | None = None, **kwargs: Any) -> Any:
        if not symbol:
            raise RuntimeError("index/board symbol is required")
        client = self._resolve_client()
        method = getattr(client, "index_bars", None) or getattr(client, "index", None)
        if not callable(method):
            raise RuntimeError("mootdx client does not expose index_bars()/index()")
        return _call_with_supported_kwargs(
            method,
            symbol=symbol,
            frequency=frequency,
            start=start,
            offset=offset,
            market=market,
            **kwargs,
        )

    def _resolve_client(self) -> Any:
        if self._client is None:
            client = self._client_factory()
            if client is None:
                raise RuntimeError("mootdx client factory unavailable")
            self._client = client
        return self._client


class N3PCurrentSourceArtifactWriter:
    """Local JSON artifact writer for normalized N3P current-source payloads."""

    def __init__(self, *, output_root: str | os.PathLike[str] | None = None) -> None:
        self.output_root = str(output_root) if output_root is not None else ""

    def write_n3p_current_source_artifacts(
        self,
        *,
        args: Any,
        report: Mapping[str, Any],
        dependencies: Any,
        payload: Mapping[str, Any],
        fetch_report: Mapping[str, Any],
        config: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        del report, dependencies
        config = config or {}
        for_trade_date = str(payload.get("for_trade_date") or getattr(args, "for_trade_date", "") or "")
        actual_until_hhmm = str(payload.get("actual_until_hhmm") or fetch_report.get("actual_until_hhmm") or "")
        if not for_trade_date or not actual_until_hhmm:
            return _blocked(
                N3P_SOURCE_FETCH_BACKEND_ARTIFACT_WRITER_BLOCKER,
                "for_trade_date and actual_until_hhmm are required for source artifact write",
            )

        output_root = str(
            self.output_root
            or config.get("artifact_output_root")
            or config.get("source_artifact_output_root")
            or "docs/intraday_live_current"
        )
        output_dir = Path(output_root) / for_trade_date
        payload_path = output_dir / f"N3P_mixed_realtime_{actual_until_hhmm}_source_fetch_payload.json"
        report_path = output_dir / f"N3P_mixed_realtime_{actual_until_hhmm}_source_fetch_report.json"

        payload_to_write = dict(payload)
        payload_hash = compute_n3p_current_source_payload_hash(payload_to_write)
        payload_to_write.update(
            {
                "payload_hash": payload_hash,
                "source_payload_hash": payload_hash,
                "source_payload_counts": {
                    "stock_quote_rows": len(_rows(payload_to_write, "stock_quote_rows", "stock_quotes_rows")),
                    "index_board_1m_rows": len(_rows(payload_to_write, "index_board_1m_rows", "index_1m_rows", "board_1m_rows")),
                },
            }
        )
        if fetch_report.get("source_scope") is not None:
            payload_to_write.setdefault("source_scope", fetch_report.get("source_scope"))

        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            payload_bytes = _canonical_json_bytes(payload_to_write)
            payload_path.write_bytes(payload_bytes)
            file_sha256 = hashlib.sha256(payload_bytes).hexdigest()

            report_to_write = {
                **dict(fetch_report),
                "result": N3_READY_RESULT,
                "validation_result": {"valid": True, "blocked_reasons": []},
                "payload_hash": payload_hash,
                "payload_path": str(payload_path),
                "report_path": str(report_path),
                "file_sha256": file_sha256,
                "artifact_written": True,
                "writes_outbox": False,
                "writes_n3p_metric_rows": False,
                "database_written": False,
                "consumes_outbox": False,
                "updates_inbox_or_checkpoint": False,
                "starts_worker": False,
                "touches_n4_n5_n6": False,
                "touches_n5_n6": False,
            }
            report_to_write.setdefault("normalization_trace", payload_to_write.get("normalization_trace") or {})
            report_path.write_bytes(_canonical_json_bytes(report_to_write))
        except OSError as exc:
            return _blocked(
                N3P_SOURCE_FETCH_BACKEND_ARTIFACT_WRITER_BLOCKER,
                f"artifact_write_failed:{type(exc).__name__}:{exc}",
            )

        return {
            "payload_path": str(payload_path),
            "report_path": str(report_path),
            "payload_hash": payload_hash,
            "source_payload_hash": payload_hash,
            "file_sha256": file_sha256,
            "source_artifact_file_sha256": file_sha256,
            "artifact_written": True,
            "database_written": False,
            "writes_outbox": False,
            "writes_n3p_metric_rows": False,
        }


class N3PCurrentSourcePayloadRegistrar:
    """Register normalized N3P source payload artifacts as N3 lineage only."""

    def register_n3p_source_payload_run(
        self,
        *,
        args: Any,
        report: Mapping[str, Any],
        dependencies: Any,
        source_payload: Mapping[str, Any],
        config: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        del report, dependencies
        source_payload_run_id = str(source_payload.get("source_payload_run_id") or "")
        source_payload_hash = _source_payload_hash(source_payload)
        if not source_payload_run_id:
            return _registration_blocked("missing_source_payload_run_id")
        if not source_payload_hash:
            return _registration_blocked("missing_source_payload_hash", source_payload_run_id=source_payload_run_id)
        if bool(source_payload.get("writes_outbox")):
            return _registration_blocked("source_payload_writes_outbox_forbidden", source_payload_run_id=source_payload_run_id)
        if bool(source_payload.get("writes_n3p_metric_rows")):
            return _registration_blocked("source_payload_writes_metric_rows_forbidden", source_payload_run_id=source_payload_run_id)

        registration_timestamp = _now_shanghai_iso()
        try:
            with _connect_db(config) as conn:
                cur = conn.cursor()
                existing = _existing_source_payload_run(cur, source_payload_run_id)
                if existing is not None:
                    existing_status, existing_raw_json = existing
                    if existing_status != "passed":
                        return _registration_blocked(
                            "dirty_target_status",
                            source_payload_run_id=source_payload_run_id,
                            observed_status=existing_status,
                        )
                    existing_hash = _existing_source_payload_hash(existing_raw_json)
                    if existing_hash != source_payload_hash:
                        return _registration_blocked(
                            "dirty_target_payload_hash_mismatch",
                            source_payload_run_id=source_payload_run_id,
                            expected_payload_hash=source_payload_hash,
                            observed_payload_hash=existing_hash,
                        )
                    ref_blocker = _existing_source_payload_downstream_ref_blocker(cur, source_payload_run_id)
                    if ref_blocker:
                        return _registration_blocked(ref_blocker, source_payload_run_id=source_payload_run_id)
                    return _registration_ready(
                        source_payload_run_id=source_payload_run_id,
                        source_payload_hash=source_payload_hash,
                        registration_result="idempotent_pass",
                        database_written=False,
                        started_at=registration_timestamp,
                        finished_at=registration_timestamp,
                    )

                contract = _source_payload_registration_contract(args=args, source_payload=source_payload)
                inserted = _ensure_source_payload_run(
                    cur=cur,
                    contract=contract,
                    source_payload=source_payload,
                    started_at=registration_timestamp,
                )
                if inserted != 1:
                    return _registration_blocked(
                        "source_payload_registration_contract_not_applicable",
                        source_payload_run_id=source_payload_run_id,
                    )
                if callable(getattr(conn, "commit", None)):
                    conn.commit()
                return _registration_ready(
                    source_payload_run_id=source_payload_run_id,
                    source_payload_hash=source_payload_hash,
                    registration_result="registered",
                    database_written=True,
                    started_at=registration_timestamp,
                    finished_at=registration_timestamp,
                )
        except Exception as exc:  # pragma: no cover - defensive DB boundary.
            return _registration_blocked(
                f"registration_exception:{type(exc).__name__}:{exc}",
                source_payload_run_id=source_payload_run_id,
            )


class N3PCurrentSourceFetchBackend:
    """Concrete dependency binder for N3P current-source fetch.

    The backend is intentionally dependency-injected. It binds the production
    shape while failing closed when DB/config, market fetch, artifact, or
    registration dependencies are not supplied.
    """

    def __init__(
        self,
        *,
        env: Mapping[str, str] | None = None,
        config: Mapping[str, Any] | None = None,
        scope_loader: Any = None,
        market_fetcher: Any = None,
        artifact_writer: Any = None,
        registrar: Any = None,
    ) -> None:
        self.env = os.environ if env is None else env
        self.config = dict(config or {})
        self.scope_loader = scope_loader
        self.market_fetcher = market_fetcher
        self.artifact_writer = artifact_writer if artifact_writer is not None else N3PCurrentSourceArtifactWriter()
        self.registrar = registrar if registrar is not None else N3PCurrentSourcePayloadRegistrar()

    def load_n3p_current_source_scope(self, *, args: Any, report: Mapping[str, Any], dependencies: Any) -> Mapping[str, Any]:
        config = self._resolve_config()
        if _is_blocked(config):
            return config
        loader = _component_callable(self.scope_loader, "load_n3p_current_source_scope") or _dependency_method(
            dependencies,
            "db_connection",
            "load_n3p_current_source_scope",
        )
        if loader is None:
            return load_n3p_current_source_scope_from_db(
                args=args,
                report=report,
                dependencies=dependencies,
                config=config,
            )
        return _call_with_supported_kwargs(
            loader,
            args=args,
            report=report,
            dependencies=dependencies,
            config=config,
        )

    def fetch_n3p_current_market_rows(
        self,
        *,
        args: Any,
        report: Mapping[str, Any],
        dependencies: Any,
        scope: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        config = self._resolve_config()
        if _is_blocked(config):
            return config
        fetcher = _component_callable(self.market_fetcher, "fetch_n3p_current_market_rows") or _dependency_method(
            dependencies,
            "market_fetch_adapter",
            "fetch_n3p_current_market_rows",
        )
        if fetcher is not None:
            return _call_with_supported_kwargs(
                fetcher,
                args=args,
                report=report,
                dependencies=dependencies,
                scope=scope,
                config=config,
            )
        return fetch_n3p_current_market_rows_from_adapter(
            args=args,
            report=report,
            dependencies=dependencies,
            scope=scope,
            config=config,
            adapter=self.market_fetcher,
        )

    def write_n3p_current_source_artifacts(
        self,
        *,
        args: Any,
        report: Mapping[str, Any],
        dependencies: Any,
        payload: Mapping[str, Any],
        fetch_report: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        config = self._resolve_config()
        if _is_blocked(config):
            return config
        writer = _component_callable(self.artifact_writer, "write_n3p_current_source_artifacts") or _dependency_method(
            dependencies,
            "artifact_writer",
            "write_n3p_current_source_artifacts",
        )
        if writer is None:
            return _blocked(
                N3P_SOURCE_FETCH_BACKEND_CONFIG_BLOCKER,
                "artifact writer dependency is required for N3P current source fetch",
            )
        return _call_with_supported_kwargs(
            writer,
            args=args,
            report=report,
            dependencies=dependencies,
            payload=payload,
            fetch_report=fetch_report,
            config=config,
        )

    def register_n3p_source_payload_run(
        self,
        *,
        args: Any,
        report: Mapping[str, Any],
        dependencies: Any,
        source_payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        config = self._resolve_config()
        if _is_blocked(config):
            return config
        registrar = _component_callable(self.registrar, "register_n3p_source_payload_run") or _dependency_method(
            dependencies,
            "source_payload_registrar",
            "register_n3p_source_payload_run",
        )
        if registrar is None:
            return _blocked(
                N3P_SOURCE_FETCH_BACKEND_REGISTRATION_BLOCKER,
                "source payload registration dependency is required for N3P current source fetch",
            )
        return _call_with_supported_kwargs(
            registrar,
            args=args,
            report=report,
            dependencies=dependencies,
            source_payload=source_payload,
            config=config,
        )

    def _resolve_config(self) -> Mapping[str, Any]:
        if self.config:
            return self.config
        database_url = (
            self.env.get("ASHARE_V3_POSTGRES_DSN")
            or self.env.get("DATABASE_URL")
            or self.env.get("PG_DSN")
            or self.env.get("POSTGRES_DSN")
        )
        if database_url:
            return {"database_url": database_url}
        if self.env.get("PGHOST") and self.env.get("PGDATABASE"):
            return {
                "pg_host": self.env.get("PGHOST"),
                "pg_database": self.env.get("PGDATABASE"),
                "pg_user": self.env.get("PGUSER"),
                "pg_port": self.env.get("PGPORT"),
            }
        default_dsn = _project_default_dsn()
        if default_dsn:
            return {"database_url": default_dsn}
        return _blocked(
            N3P_SOURCE_FETCH_BACKEND_CONFIG_BLOCKER,
            "database config is required for N3P current source fetch backend",
        )


class N3PCurrentSourceFetchProvider:
    """Thin contract adapter around injected source-fetch/artifact backends."""

    def __init__(self, *, backend: Any = _DEFAULT_BACKEND) -> None:
        self.backend = N3PCurrentSourceFetchBackend() if backend is _DEFAULT_BACKEND else backend

    def fetch_n3p_current_source_payload(self, *, args: Any, report: Mapping[str, Any], dependencies: Any) -> Mapping[str, Any]:
        if self.backend is None:
            return _blocked(
                N3P_SOURCE_FETCH_PROVIDER_BACKEND_BLOCKER,
                "missing injected backend for fetch_n3p_current_source_payload",
            )

        scope_loader = getattr(self.backend, "load_n3p_current_source_scope", None)
        row_fetcher = getattr(self.backend, "fetch_n3p_current_market_rows", None)
        artifact_writer = getattr(self.backend, "write_n3p_current_source_artifacts", None)
        if not callable(scope_loader) or not callable(row_fetcher):
            return _blocked(
                N3P_SOURCE_FETCH_PROVIDER_BACKEND_BLOCKER,
                "backend must expose load_n3p_current_source_scope and fetch_n3p_current_market_rows",
            )

        scope = dict(scope_loader(args=args, report=report, dependencies=dependencies) or {})
        if _is_blocked(scope):
            return scope
        scope_blocker = _validate_source_scope(scope)
        if scope_blocker is not None:
            return scope_blocker

        fetched = dict(row_fetcher(args=args, report=report, dependencies=dependencies, scope=scope) or {})
        if _is_blocked(fetched):
            return fetched
        for_trade_date = str(getattr(args, "for_trade_date", "") or scope.get("for_trade_date") or "")
        fetched_trace = fetched.get("normalization_trace")
        if isinstance(fetched_trace, Mapping):
            stock_quote_rows = [dict(row) for row in _rows(fetched, "stock_quote_rows", "stock_quotes_rows")]
            index_board_1m_rows = [dict(row) for row in _rows(fetched, "index_board_1m_rows", "index_1m_rows", "board_1m_rows")]
            normalization_trace = dict(fetched_trace)
            stock_quote_rows, normalization_blocked_reasons = _normalize_stock_quote_rows_for_canonical_minutes(
                stock_quote_rows=stock_quote_rows,
                for_trade_date=for_trade_date,
                normalization_trace=normalization_trace,
            )
        else:
            normalization = normalize_n3p_current_source_rows_before_validation(
                stock_quote_rows=_rows(fetched, "stock_quote_rows", "stock_quotes_rows"),
                index_board_1m_rows=_rows(fetched, "index_board_1m_rows", "index_1m_rows", "board_1m_rows"),
                for_trade_date=for_trade_date,
            )
            stock_quote_rows = normalization["stock_quote_rows"]
            index_board_1m_rows = normalization["index_board_1m_rows"]
            normalization_trace = normalization["normalization_trace"]
            normalization_blocked_reasons = normalization["blocked_reasons"]
        if normalization_blocked_reasons:
            return _blocked(
                N3P_SOURCE_FETCH_PAYLOAD_BLOCKER,
                ",".join(normalization_blocked_reasons),
                blocked_reasons=normalization_blocked_reasons,
                normalization_trace=normalization_trace,
            )

        source_minute_alignment = _source_realtime_freshness_trace(
            stock_quote_rows=stock_quote_rows,
            index_board_1m_rows=index_board_1m_rows,
        )
        alignment_blocker = _source_canonical_minute_alignment_blocker_from_trace(source_minute_alignment)
        if alignment_blocker is not None:
            return alignment_blocker

        normalized_proof_input_time = _derive_market_fetch_proof_input_time(
            stock_quote_rows=stock_quote_rows,
            index_board_1m_rows=index_board_1m_rows,
        )
        proof_input_time = str(
            normalized_proof_input_time
            or fetched.get("proof_input_time")
            or fetched.get("source_returned_time")
            or fetched.get("actual_proof_time")
            or ""
        )
        actual_until_hhmm = _hhmm_from_time(proof_input_time)
        if not actual_until_hhmm:
            return _blocked(N3P_SOURCE_FETCH_PAYLOAD_BLOCKER, "proof_input_time is required")

        post_close_blocker = _post_close_proof_minute_blocker(
            proof_input_time=proof_input_time,
            actual_until_hhmm=actual_until_hhmm,
        )
        if post_close_blocker is not None:
            return post_close_blocker

        relabel_blocker = _validate_requested_until(args=args, actual_until_hhmm=actual_until_hhmm)
        if relabel_blocker is not None:
            return relabel_blocker

        payload = {
            "source_model": N3P_SOURCE_MODEL,
            "source_origin": "local_mootdx_fetch_artifact",
            "source_payload_run_id": _source_payload_run_id(args=args, actual_until_hhmm=actual_until_hhmm),
            "proof_input_time": proof_input_time,
            "canonical_proof_time": proof_input_time,
            "canonical_proof_minute": actual_until_hhmm,
            "actual_proof_minute": actual_until_hhmm,
            "actual_until_hhmm": actual_until_hhmm,
            "for_trade_date": for_trade_date,
            "n4_context_run_id": str(getattr(args, "n4_context_run_id", "") or scope.get("n4_context_run_id") or ""),
            "subscription_run_id": str(getattr(args, "subscription_run_id", "") or scope.get("subscription_run_id") or ""),
            "stock_quote_rows": stock_quote_rows,
            "index_board_1m_rows": index_board_1m_rows,
            "normalization_trace": normalization_trace,
            "source_minute_alignment": source_minute_alignment,
            "previous_day_minute_rows": [],
            "writes_outbox": False,
            "writes_n3p_metric_rows": False,
            "not_n5_final_proof": True,
        }
        payload.update(source_minute_alignment)
        validation = validate_n3p_current_source_payload(
            payload,
            for_trade_date=payload["for_trade_date"],
            proof_input_time=proof_input_time,
            source_scope=scope,
        )
        if not validation["valid"]:
            return _blocked(
                N3P_SOURCE_FETCH_PAYLOAD_BLOCKER,
                ",".join(validation["blocked_reasons"]),
                blocked_reasons=validation["blocked_reasons"],
                normalization_trace=normalization_trace,
            )

        counts = {
            "stock_quote_rows": len(payload["stock_quote_rows"]),
            "index_board_1m_rows": len(payload["index_board_1m_rows"]),
        }
        fetch_report = {
            "source_scope": _source_scope_counts(scope),
            "source_payload_counts": counts,
            "proof_input_time": proof_input_time,
            "canonical_proof_time": proof_input_time,
            "canonical_proof_minute": actual_until_hhmm,
            "actual_until_hhmm": actual_until_hhmm,
            "writes_n3p_metric_rows": False,
            "writes_outbox": False,
            "normalization_trace": normalization_trace,
            "source_minute_alignment": source_minute_alignment,
        }
        artifact = (
            dict(artifact_writer(args=args, report=report, dependencies=dependencies, payload=payload, fetch_report=fetch_report) or {})
            if callable(artifact_writer)
            else {}
        )
        if _is_blocked(artifact):
            return artifact
        computed_payload_hash = compute_n3p_current_source_payload_hash(payload)
        artifact_payload_hash = str(artifact.get("payload_hash") or artifact.get("source_payload_hash") or "")
        if artifact_payload_hash and artifact_payload_hash != computed_payload_hash:
            return _blocked(
                N3P_SOURCE_FETCH_PAYLOAD_BLOCKER,
                "payload_hash_mismatch",
                blocked_reasons=["payload_hash_mismatch"],
                expected_payload_hash=computed_payload_hash,
                observed_payload_hash=artifact_payload_hash,
            )
        payload_hash = artifact_payload_hash or computed_payload_hash
        payload.update(
            {
                "result": N3_READY_RESULT,
                "payload_hash": payload_hash,
                "source_payload_hash": payload_hash,
                "payload_path": str(artifact.get("payload_path") or artifact.get("source_artifact_path") or ""),
                "report_path": str(artifact.get("report_path") or artifact.get("source_report_path") or ""),
                "source_artifact_path": str(artifact.get("payload_path") or artifact.get("source_artifact_path") or ""),
                "source_artifact_file_sha256": str(artifact.get("file_sha256") or artifact.get("source_artifact_file_sha256") or ""),
                "source_scope": _source_scope_counts(scope),
                "source_payload_counts": counts,
                "market_data_pulled": True,
                "database_written": False,
            }
        )
        _apply_forbidden_side_effect_guards(payload)
        return payload

    def register_n3p_source_payload_run(
        self,
        *,
        args: Any,
        report: Mapping[str, Any],
        dependencies: Any,
        source_payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if self.backend is None:
            return _blocked(
                N3P_SOURCE_PAYLOAD_REGISTRATION_BACKEND_BLOCKER,
                "missing injected backend for source payload run registration",
            )
        registrar = getattr(self.backend, "register_n3p_source_payload_run", None)
        if not callable(registrar):
            return _blocked(
                N3P_SOURCE_PAYLOAD_REGISTRATION_BACKEND_BLOCKER,
                "backend must expose register_n3p_source_payload_run",
            )
        payload = dict(registrar(args=args, report=report, dependencies=dependencies, source_payload=source_payload) or {})
        payload.setdefault("registration_attempted", True)
        if _is_blocked(payload):
            payload["source_payload_registered"] = False
            payload["database_written"] = False
            payload.setdefault("registration_result", payload["result"])
        else:
            payload.setdefault("result", N3_READY_RESULT)
            payload.setdefault("source_payload_registered", True)
            payload.setdefault("database_written", False)
            payload.setdefault(
                "registration_result",
                "registered" if bool(payload.get("database_written")) else "idempotent_pass",
            )
        payload.setdefault("writes_n3p_metric_rows", False)
        payload.setdefault("writes_outbox", False)
        _apply_forbidden_side_effect_guards(payload)
        return payload


class N3PTriggerProofPreflightBackend:
    """Read-only production backend for N3P trigger-proof plan-only preflight."""

    def __init__(self, *, env: Mapping[str, str] | None = None, config: Mapping[str, Any] | None = None) -> None:
        self._config_resolver = N3PCurrentSourceFetchBackend(env=env, config=config)

    def build_n3p_trigger_proof_preflight(self, *, args: Any, report: Mapping[str, Any], dependencies: Any) -> Mapping[str, Any]:
        del report, dependencies
        config = self._config_resolver._resolve_config()
        if _is_blocked(config):
            return config
        source_payload_run_id = str(getattr(args, "source_run_id", "") or "")
        target_run_id = str(getattr(args, "target_run_id", "") or "")
        for_trade_date = str(getattr(args, "for_trade_date", "") or "")
        subscription_run_id = str(getattr(args, "subscription_run_id", "") or "")
        n4_context_run_id = str(getattr(args, "n4_context_run_id", "") or "")
        missing = [
            name
            for name, value in (
                ("source_run_id", source_payload_run_id),
                ("target_run_id", target_run_id),
                ("for_trade_date", for_trade_date),
                ("subscription_run_id", subscription_run_id),
                ("n4_context_run_id", n4_context_run_id),
            )
            if not value
        ]
        if missing:
            return _blocked(N3P_TRIGGER_PROOF_SOURCE_PAYLOAD_BLOCKER, f"missing_preflight_input:{','.join(missing)}")

        try:
            source_payload = _read_source_payload_for_preflight(args=args, source_payload_run_id=source_payload_run_id)
        except Exception as exc:
            return _blocked(N3P_TRIGGER_PROOF_SOURCE_PAYLOAD_BLOCKER, f"source_payload_read_failed:{type(exc).__name__}:{exc}")
        payload_hash = compute_n3p_current_source_payload_hash(source_payload)
        embedded_hash = _source_payload_hash(source_payload)
        if embedded_hash and embedded_hash != payload_hash:
            return _blocked(
                N3P_TRIGGER_PROOF_SOURCE_PAYLOAD_BLOCKER,
                "source_payload_hash_mismatch",
                expected_payload_hash=payload_hash,
                observed_payload_hash=embedded_hash,
            )
        actual_until_hhmm = _source_payload_canonical_hhmm(source_payload, source_payload_run_id=source_payload_run_id)
        post_close_blocker = _post_close_proof_minute_blocker(
            proof_input_time=_source_payload_canonical_proof_time(source_payload),
            actual_until_hhmm=actual_until_hhmm,
            source_payload_classification="historical_bad_source_payload",
        )
        if post_close_blocker is not None:
            return post_close_blocker

        try:
            with _connect_db(config) as conn:
                conn.execute("BEGIN READ ONLY")
                try:
                    from psycopg.rows import dict_row

                    with conn.cursor(row_factory=dict_row) as cur:
                        return _build_n3p_trigger_proof_preflight_with_cursor(
                            cur=cur,
                            args=args,
                            source_payload=source_payload,
                            source_payload_hash=payload_hash,
                        )
                finally:
                    conn.execute("ROLLBACK")
        except Exception as exc:
            return _blocked(N3P_TRIGGER_PROOF_PREFLIGHT_BACKEND_BLOCKER, f"preflight_exception:{type(exc).__name__}:{exc}")


class N3PTriggerProofPreflightProvider:
    """Thin provider that exposes the production entrypoint expected by hooks."""

    def __init__(self, *, backend: Any = _DEFAULT_BACKEND) -> None:
        self.backend = N3PTriggerProofPreflightBackend() if backend is _DEFAULT_BACKEND else backend

    def build_n3p_trigger_proof_preflight(self, *, args: Any, report: Mapping[str, Any], dependencies: Any) -> Mapping[str, Any]:
        if self.backend is None:
            return _blocked(
                N3P_TRIGGER_PROOF_PREFLIGHT_BACKEND_BLOCKER,
                "missing injected backend for build_n3p_trigger_proof_preflight",
            )
        builder = getattr(self.backend, "build_n3p_trigger_proof_preflight", None)
        if not callable(builder):
            return _blocked(
                N3P_TRIGGER_PROOF_PREFLIGHT_BACKEND_BLOCKER,
                "backend must expose build_n3p_trigger_proof_preflight",
            )
        payload = dict(builder(args=args, report=report, dependencies=dependencies) or {})
        if _is_blocked(payload):
            payload.setdefault("database_written", False)
            payload.setdefault("market_data_pulled", False)
        else:
            payload.setdefault("result", N3_READY_RESULT)
            payload.setdefault("database_written", False)
            payload.setdefault("market_data_pulled", False)
            payload.setdefault("writes_n3p_metric_rows", False)
            payload.setdefault("not_n5_final_proof", True)
            payload.setdefault("action_confirmation_ready", False)
            materialization = _materialize_n3p_trigger_proof_preflight_artifacts(args=args, payload=payload)
            if _is_blocked(materialization):
                payload = dict(materialization)
            else:
                payload.update(materialization)
                payload.pop("writer_contract", None)
                payload.pop("writer_preflight", None)
        payload.setdefault("preflight_entrypoint", "build_n3p_trigger_proof_preflight")
        _apply_forbidden_side_effect_guards(payload)
        return payload


def _materialize_n3p_trigger_proof_preflight_artifacts(*, args: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Write writer-consumable contract/preflight artifacts when available."""

    has_contract = "writer_contract" in payload
    has_preflight = "writer_preflight" in payload
    if not has_contract and not has_preflight:
        return {}
    contract_path = str(getattr(args, "contract_path", "") or "")
    preflight_path = str(getattr(args, "preflight_path", "") or "")
    missing_paths = [
        name
        for name, value in (
            ("contract_path", contract_path),
            ("preflight_path", preflight_path),
        )
        if not value
    ]
    if missing_paths:
        return _blocked(
            N3P_TRIGGER_PROOF_PREFLIGHT_ARTIFACT_MATERIALIZATION_BLOCKER,
            f"missing_artifact_path:{','.join(missing_paths)}",
            target_run_id=payload.get("target_run_id") or payload.get("proposed_n3p_metric_target_run_id"),
            source_payload_run_id=payload.get("source_payload_run_id"),
        )

    contract = payload.get("writer_contract")
    preflight = payload.get("writer_preflight")
    if not isinstance(contract, Mapping) or not isinstance(preflight, Mapping):
        return _blocked(
            N3P_TRIGGER_PROOF_PREFLIGHT_ARTIFACT_CONTRACT_BLOCKER,
            "writer_contract_and_writer_preflight_required",
            target_run_id=payload.get("target_run_id") or payload.get("proposed_n3p_metric_target_run_id"),
            source_payload_run_id=payload.get("source_payload_run_id"),
        )

    contract_doc = _n3p_writer_contract_artifact_document(contract=contract, payload=payload)
    preflight_doc = _n3p_writer_preflight_artifact_document(
        preflight=preflight,
        contract_doc=contract_doc,
        payload=payload,
    )
    try:
        for path_text, document in ((contract_path, contract_doc), (preflight_path, preflight_doc)):
            path = Path(path_text)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")
    except Exception as exc:
        return _blocked(
            N3P_TRIGGER_PROOF_PREFLIGHT_ARTIFACT_MATERIALIZATION_BLOCKER,
            f"artifact_write_failed:{type(exc).__name__}:{exc}",
            target_run_id=payload.get("target_run_id") or payload.get("proposed_n3p_metric_target_run_id"),
            source_payload_run_id=payload.get("source_payload_run_id"),
        )

    return {
        "preflight_artifacts_materialized": True,
        "contract_path": contract_path,
        "preflight_path": preflight_path,
        "contract_artifact_path": contract_path,
        "preflight_artifact_path": preflight_path,
        "database_written": False,
        "market_data_pulled": False,
        "writes_outbox": False,
    }


def _n3p_writer_contract_artifact_document(*, contract: Mapping[str, Any], payload: Mapping[str, Any]) -> dict[str, Any]:
    output = dict(contract)
    source_scope = dict(output.get("source_scope") or {})
    target_run_id = str(payload.get("target_run_id") or payload.get("proposed_n3p_metric_target_run_id") or output.get("target_run_id") or "")
    output["target_run_id"] = target_run_id
    source_scope.setdefault("for_trade_date", payload.get("for_trade_date"))
    source_scope.setdefault("source_trade_date", payload.get("source_trade_date"))
    source_scope.setdefault("source_payload_run_id", payload.get("source_payload_run_id"))
    source_scope.setdefault("source_payload_hash", payload.get("source_payload_hash"))
    source_scope.setdefault("n4_context_run_id", payload.get("n4_context_run_id"))
    source_scope.setdefault("source_subscription_run_id", payload.get("subscription_run_id"))
    source_scope["writes_outbox"] = False
    output["source_scope"] = source_scope

    expected_rows = dict(output.get("expected_rows") or {})
    plan_counts = dict(payload.get("plan_only_row_counts") or {})
    for key, value in plan_counts.items():
        expected_rows.setdefault(key, value)
    if payload.get("metric_ready") is not None:
        expected_rows["metric_ready"] = payload.get("metric_ready")
    if payload.get("metric_not_ready") is not None:
        expected_rows["metric_not_ready"] = payload.get("metric_not_ready")
        expected_rows.setdefault("expected_not_ready_count", payload.get("metric_not_ready"))
    output["expected_rows"] = expected_rows

    output.setdefault("allowed_write_tables", list(N3P_TRIGGER_PROOF_PREFLIGHT_ALLOWED_WRITE_TABLES))
    output.setdefault("forbidden_write_tables", list(N3P_TRIGGER_PROOF_PREFLIGHT_FORBIDDEN_WRITE_TABLES))
    output["writes_outbox"] = False
    output["not_n5_final_proof"] = True
    output["preflight_artifact_context"] = _n3p_preflight_artifact_context(contract_doc=output, payload=payload)
    return output


def _n3p_writer_preflight_artifact_document(
    *,
    preflight: Mapping[str, Any],
    contract_doc: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    output = dict(preflight)
    output["result"] = "PREFLIGHT_PASS"
    output.update(_n3p_preflight_artifact_context(contract_doc=contract_doc, payload=payload))
    output["allowed_write_tables"] = list(contract_doc.get("allowed_write_tables") or [])
    output["forbidden_write_tables"] = list(contract_doc.get("forbidden_write_tables") or [])
    output["not_n5_final_proof"] = True
    output["writes_outbox"] = False
    output["database_written"] = False
    output["market_data_pulled"] = False
    return output


def _n3p_preflight_artifact_context(*, contract_doc: Mapping[str, Any], payload: Mapping[str, Any]) -> dict[str, Any]:
    source_scope = dict(contract_doc.get("source_scope") or {})
    return {
        "target_run_id": payload.get("target_run_id") or payload.get("proposed_n3p_metric_target_run_id") or contract_doc.get("target_run_id"),
        "source_payload_run_id": payload.get("source_payload_run_id") or source_scope.get("source_payload_run_id"),
        "source_payload_hash": payload.get("source_payload_hash") or source_scope.get("source_payload_hash"),
        "for_trade_date": payload.get("for_trade_date") or source_scope.get("for_trade_date"),
        "source_trade_date": payload.get("source_trade_date") or source_scope.get("source_trade_date"),
        "n4_context_run_id": payload.get("n4_context_run_id") or source_scope.get("n4_context_run_id"),
        "subscription_run_id": payload.get("subscription_run_id") or source_scope.get("source_subscription_run_id"),
        "plan_only_row_counts": dict(payload.get("plan_only_row_counts") or {}),
        "metric_ready": payload.get("metric_ready"),
        "metric_not_ready": payload.get("metric_not_ready"),
        "target_absence": dict(payload.get("target_absence") or {}),
        "rollback_readiness": dict(payload.get("rollback_readiness") or {}),
    }


def _read_source_payload_for_preflight(*, args: Any, source_payload_run_id: str) -> dict[str, Any]:
    path = str(getattr(args, "source_payload_path", "") or getattr(args, "source_artifact_path", "") or "")
    if not path:
        actual_until_hhmm = _until_from_run_id(source_payload_run_id)
        for_trade_date = str(getattr(args, "for_trade_date", "") or "")
        path = str(Path("docs/intraday_live_current") / for_trade_date / f"N3P_mixed_realtime_{actual_until_hhmm}_source_fetch_payload.json")
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("source payload artifact must be a JSON object")
    output = dict(payload)
    output.setdefault("source_artifact_path", path)
    payload_run_id = str(output.get("source_payload_run_id") or "")
    if payload_run_id and payload_run_id != source_payload_run_id:
        raise ValueError(f"source_payload_run_id mismatch: artifact={payload_run_id} expected={source_payload_run_id}")
    output["source_payload_run_id"] = source_payload_run_id
    return output


def _source_payload_canonical_proof_time(source_payload: Mapping[str, Any]) -> str:
    return str(source_payload.get("canonical_proof_time") or source_payload.get("proof_input_time") or "")


def _source_payload_canonical_hhmm(source_payload: Mapping[str, Any], *, source_payload_run_id: str) -> str:
    value = str(
        source_payload.get("canonical_proof_minute")
        or source_payload.get("actual_until_hhmm")
        or source_payload.get("actual_proof_minute")
        or _until_from_run_id(source_payload_run_id)
        or ""
    )
    return value.replace(":", "")


def _build_n3p_trigger_proof_preflight_with_cursor(
    *,
    cur: Any,
    args: Any,
    source_payload: Mapping[str, Any],
    source_payload_hash: str,
) -> Mapping[str, Any]:
    from ashare_v3.market import v3_realtime_virtual_metric_writer as writer

    source_payload_run_id = str(getattr(args, "source_run_id", "") or "")
    target_run_id = str(getattr(args, "target_run_id", "") or "")
    for_trade_date = str(getattr(args, "for_trade_date", "") or "")
    subscription_run_id = str(getattr(args, "subscription_run_id", "") or "")
    n4_context_run_id = str(getattr(args, "n4_context_run_id", "") or "")
    source_condition_run_id = str(getattr(args, "source_condition_run_id", "") or "")

    source_run = _existing_source_payload_run(cur, source_payload_run_id)
    if source_run is None:
        return _blocked(N3P_TRIGGER_PROOF_SOURCE_PAYLOAD_BLOCKER, "source_payload_run_missing")
    source_status, source_raw_json = source_run
    if source_status != "passed":
        return _blocked(N3P_TRIGGER_PROOF_SOURCE_PAYLOAD_BLOCKER, f"source_payload_run_status={source_status or 'missing'}")
    registered_hash = _existing_source_payload_hash(source_raw_json)
    if registered_hash and registered_hash != source_payload_hash:
        return _blocked(
            N3P_TRIGGER_PROOF_SOURCE_PAYLOAD_BLOCKER,
            "registered_source_payload_hash_mismatch",
            expected_payload_hash=registered_hash,
            observed_payload_hash=source_payload_hash,
        )

    calendar = _fetchone_from_cursor(
        cur,
        "SELECT is_open, prev_trade_date FROM common_trade_calendar WHERE trade_date=%s",
        (for_trade_date,),
    )
    if not calendar:
        return _blocked(N3P_TRIGGER_PROOF_PREFLIGHT_BACKEND_BLOCKER, f"trade_calendar_missing:{for_trade_date}")
    if not bool(_row_value(calendar, 0, "is_open")):
        return _blocked(N3P_TRIGGER_PROOF_PREFLIGHT_BACKEND_BLOCKER, f"trade_date_not_open:{for_trade_date}")
    source_trade_date = str(_row_value(calendar, 1, "prev_trade_date") or "")
    source_previous_day_minute_run_id = _derive_a1_preload_run_id(
        for_trade_date=for_trade_date,
        prev_trade_date=source_trade_date,
        subscription_run_id=subscription_run_id,
    )

    status_checks = {
        "subscription": _run_status_from_cursor(cur, "common_market_data_run", subscription_run_id),
        "a1_preload": _run_status_from_cursor(cur, "common_market_data_run", source_previous_day_minute_run_id),
        "n4_context": _run_status_from_cursor(cur, "common_trigger_run", n4_context_run_id),
    }
    failed_status = [f"{key}={value or 'missing'}" for key, value in status_checks.items() if value != "passed"]
    if failed_status:
        return _blocked(N3P_TRIGGER_PROOF_PREFLIGHT_BACKEND_BLOCKER, ",".join(failed_status))

    context_rows_by_asset = {
        "stock": _trigger_context_snapshot_rows_for_preflight(cur, "stock_trigger_context_snapshot", n4_context_run_id),
        "index": _trigger_context_snapshot_rows_for_preflight(cur, "index_trigger_context_snapshot", n4_context_run_id),
        "board": _trigger_context_snapshot_rows_for_preflight(cur, "board_trigger_context_snapshot", n4_context_run_id),
    }
    context_rows = [
        row
        for rows in context_rows_by_asset.values()
        for row in rows
        if str(row.get("quality_status") or "passed") == "passed"
    ]
    if not context_rows:
        return _blocked(N3P_TRIGGER_PROOF_PREFLIGHT_BACKEND_BLOCKER, "n4_context_rows_missing")

    parsed_target = writer.parse_n3p_realtime_action_confirmation_metric_run_id(target_run_id)
    actual_until_hhmm = _source_payload_canonical_hhmm(source_payload, source_payload_run_id=source_payload_run_id)
    if actual_until_hhmm != parsed_target["until_hhmm"]:
        return _blocked(
            N3P_TRIGGER_PROOF_SOURCE_PAYLOAD_BLOCKER,
            f"source_payload_until_mismatch:{actual_until_hhmm}:{parsed_target['until_hhmm']}",
        )
    proof_input_time = _source_payload_canonical_proof_time(source_payload)
    if not proof_input_time:
        return _blocked(N3P_TRIGGER_PROOF_SOURCE_PAYLOAD_BLOCKER, "source_payload_proof_input_time_missing")

    contract = _build_n3p_trigger_proof_preflight_contract(
        writer=writer,
        target_run_id=target_run_id,
        parsed_target=parsed_target,
        for_trade_date=for_trade_date,
        source_trade_date=source_trade_date,
        source_condition_run_id=source_condition_run_id,
        subscription_run_id=subscription_run_id,
        n4_context_run_id=n4_context_run_id,
        source_payload_run_id=source_payload_run_id,
        source_previous_day_minute_run_id=source_previous_day_minute_run_id,
        source_payload=source_payload,
        source_payload_hash=source_payload_hash,
        proof_input_time=proof_input_time,
        context_rows=context_rows,
    )
    candidates = _build_n3p_trigger_proof_candidates(
        writer=writer,
        contract=contract,
        context_rows=context_rows,
        proof_input_time=proof_input_time,
        proof_hhmm=actual_until_hhmm,
    )
    if not candidates:
        return _blocked(N3P_TRIGGER_PROOF_PREFLIGHT_BACKEND_BLOCKER, "n3p_candidates_missing")
    duplicate_keys = [key for key, count in Counter(_candidate_unique_key(candidate) for candidate in candidates).items() if count > 1]
    if duplicate_keys:
        return _blocked(N3P_TRIGGER_PROOF_PREFLIGHT_BACKEND_BLOCKER, "duplicate_condition_grain_keys")

    previous_day_cumulative_rows = writer.load_previous_day_cumulative_rows_from_db(
        cur,
        source_previous_day_minute_run_id=source_previous_day_minute_run_id,
        for_trade_date=for_trade_date,
        source_trade_date=source_trade_date,
        proof_minute_label=proof_input_time,
        asset_scope=context_rows,
    )
    writer_payload = dict(source_payload)
    writer_payload.update(
        {
            "source_payload_run_id": source_payload_run_id,
            "source_payload_hash": source_payload_hash,
            "source_artifact_path": source_payload.get("source_artifact_path"),
            "candidates": candidates,
            "n4_context_snapshot_rows": context_rows,
            "previous_day_cumulative_rows": previous_day_cumulative_rows,
            "previous_day_minute_rows": [],
            "require_previous_day_cumulative_rows": True,
        }
    )
    contract["materialized_source_payload_overlay"] = {
        "source_payload_run_id": source_payload_run_id,
        "source_payload_hash": source_payload_hash,
        "source_artifact_path": source_payload.get("source_artifact_path"),
        "candidates": candidates,
        "n4_context_snapshot_rows": context_rows,
        "previous_day_cumulative_rows": previous_day_cumulative_rows,
        "previous_day_minute_rows": [],
        "require_previous_day_cumulative_rows": True,
    }

    signal_counts = Counter(str(candidate.get("signal_type") or "") for candidate in candidates)
    contract["expected_rows"] = {
        "total": len(candidates),
        "by_signal_type": dict(signal_counts),
        "expected_not_ready_blocked_reasons": list(N3P_TRIGGER_PROOF_EXPECTED_NOT_READY_BLOCKED_REASONS),
        "expected_not_ready_blocked_reason_prefixes": list(
            N3P_TRIGGER_PROOF_EXPECTED_NOT_READY_BLOCKED_REASON_PREFIXES
        ),
    }
    try:
        rows_by_asset = writer.build_rows_by_asset_from_source_payload(contract, writer_payload)
    except Exception as exc:
        return _blocked(N3P_TRIGGER_PROOF_PREFLIGHT_BACKEND_BLOCKER, f"plan_only_row_build_failed:{type(exc).__name__}:{exc}")
    ready_count = sum(1 for rows in rows_by_asset.values() for row in rows if bool(row.get("metric_ready")))
    total_count = sum(len(rows) for rows in rows_by_asset.values())
    not_ready_count = total_count - ready_count
    not_ready_reasons = _not_ready_reason_distribution(rows_by_asset)
    contract["expected_rows"].update(
        {
            "metric_ready": ready_count,
            "metric_not_ready": not_ready_count,
            "expected_not_ready_count": not_ready_count,
        }
    )

    target_absence_counts = writer.fetch_target_absence_counts(cur, target_run_id)
    target_absence = writer.build_target_absence_report(target_run_id=target_run_id, counts=target_absence_counts)
    if target_absence.get("status") == "blocked":
        return _blocked(
            N3P_TRIGGER_PROOF_TARGET_ABSENCE_BLOCKER,
            "target_not_empty",
            target_absence=target_absence,
        )

    try:
        writer_report = writer.run_virtual_metric_writer(
            contract=contract,
            preflight={"result": "PREFLIGHT_PASS"},
            source_payload=writer_payload,
            execute=False,
            user_confirmed=False,
            target_absence_counts=target_absence_counts,
        )
    except Exception as exc:
        return _blocked(N3P_TRIGGER_PROOF_PREFLIGHT_BACKEND_BLOCKER, f"writer_plan_only_failed:{type(exc).__name__}:{exc}")

    row_counts = dict(writer_report.get("metric_counts_by_asset") or writer_report.get("planned_rows") or {})
    row_counts["total"] = int(row_counts.get("total") or sum(int(row_counts.get(asset) or 0) for asset in ("stock", "index", "board")))
    transition_trace = _transition_trace_contract(rows_by_asset)
    writer_preflight = {
        "result": "PREFLIGHT_PASS",
        "target_run_id": target_run_id,
        "source_payload_run_id": source_payload_run_id,
        "source_payload_hash": source_payload_hash,
        "for_trade_date": for_trade_date,
        "source_trade_date": source_trade_date,
        "n4_context_run_id": n4_context_run_id,
        "subscription_run_id": subscription_run_id,
        "plan_only_row_counts": row_counts,
        "metric_ready": ready_count,
        "metric_not_ready": not_ready_count,
        "target_absence": target_absence,
        "rollback_readiness": {
            "status": "ready",
            "rollback_sql_scope": "in_memory_preflight_only",
            "guards": ["outbox", "inbox", "checkpoint", "N4", "N5", "N6", "user", "sim"],
        },
        "not_n5_final_proof": True,
        "writes_outbox": False,
        "allowed_write_tables": list(contract.get("allowed_write_tables") or []),
        "forbidden_write_tables": list(contract.get("forbidden_write_tables") or []),
    }
    output = {
        "result": N3_READY_RESULT,
        "writer_result": writer_report.get("result"),
        "proposed_n3p_metric_target_run_id": target_run_id,
        "target_run_id": target_run_id,
        "source_payload_run_id": source_payload_run_id,
        "source_payload_hash": source_payload_hash,
        "for_trade_date": for_trade_date,
        "source_trade_date": source_trade_date,
        "n4_context_run_id": n4_context_run_id,
        "subscription_run_id": subscription_run_id,
        "proof_input_time": proof_input_time,
        "actual_until_hhmm": actual_until_hhmm,
        "plan_only_row_counts": row_counts,
        "metric_ready": ready_count,
        "metric_not_ready": not_ready_count,
        "not_ready_reason_distribution": not_ready_reasons,
        "source_amount_kind_distribution": _source_amount_kind_distribution(rows_by_asset),
        "target_absence": target_absence,
        "rollback_ready": True,
        "rollback_readiness": {
            "status": "ready",
            "rollback_sql_scope": "in_memory_preflight_only",
            "guards": ["outbox", "inbox", "checkpoint", "N4", "N5", "N6", "user", "sim"],
        },
        "source_payload_contract": {
            "source_payload_run_status": source_status,
            "source_payload_hash_matches_registration": True,
            "previous_day_minute_rows_in_payload": len(writer_payload.get("previous_day_minute_rows") or []),
            "previous_day_cumulative_rows": len(previous_day_cumulative_rows),
            "require_previous_day_cumulative_rows": True,
        },
        "plan_only_contract": {
            "metric_role": "trigger_proof",
            "proof_owner": "N3",
            "proof_consumer": "N4",
            "not_n5_final_proof": True,
            "action_confirmation_ready": False,
        },
        "current_period_avg_trace": transition_trace,
        "not_n5_final_proof": True,
        "action_confirmation_ready": False,
        "database_written": False,
        "market_data_pulled": False,
        "writes_n3p_metric_rows": False,
        "writes_outbox": False,
        "writer_contract": contract,
        "writer_preflight": writer_preflight,
    }
    _apply_forbidden_side_effect_guards(output)
    return output


def validate_n3p_current_source_payload(
    source_payload: Mapping[str, Any],
    *,
    for_trade_date: str,
    proof_input_time: str,
    source_scope: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate current source rows before artifact/registration handoff."""

    blocked_reasons: list[str] = []
    proof_dt = _parse_dt(proof_input_time)
    expected_trade_date = _normalize_trade_date(for_trade_date)
    index_board_rows = _rows(source_payload, "index_board_1m_rows", "index_1m_rows", "board_1m_rows")
    stock_quote_rows = _rows(source_payload, "stock_quote_rows", "stock_quotes_rows")
    scope_counts = _source_scope_counts(source_scope or {})
    if scope_counts["stock_object_count"] > 0 and not stock_quote_rows:
        blocked_reasons.append("missing_stock_quote_rows_for_scope")
    if scope_counts["index_object_count"] + scope_counts["board_object_count"] > 0 and not index_board_rows:
        blocked_reasons.append("missing_index_board_1m_rows_for_scope")
    if _rows(source_payload, "stock_minute_rows", "stock_1m_rows"):
        blocked_reasons.append("stock_minute_rows_forbidden")
    stock_scope_ids = _scope_identity_keys(source_scope or {}, "stock_quote_objects")
    if stock_scope_ids:
        stock_row_ids = {str(row.get("identity_key") or "") for row in stock_quote_rows}
        missing_stock_ids = sorted(identity for identity in stock_scope_ids if identity not in stock_row_ids)
        if missing_stock_ids:
            blocked_reasons.append(f"missing_stock_quote_objects:{len(missing_stock_ids)}")
    index_board_scope_ids = {
        *_scope_identity_keys(source_scope or {}, "index_1m_objects"),
        *_scope_identity_keys(source_scope or {}, "board_1m_objects"),
    }
    if index_board_scope_ids:
        index_board_row_ids = {str(row.get("identity_key") or "") for row in index_board_rows}
        missing_index_board_ids = sorted(identity for identity in index_board_scope_ids if identity not in index_board_row_ids)
        if missing_index_board_ids:
            blocked_reasons.append(f"missing_index_board_1m_objects:{len(missing_index_board_ids)}")

    seen_keys: set[tuple[str, str, str]] = set()
    for row in (*stock_quote_rows, *index_board_rows):
        if _row_has_fake_marker(row):
            blocked_reasons.append("fake_source_marker")
            break

    for row in index_board_rows:
        label = _row_minute_label(row)
        if label == "11:30":
            blocked_reasons.append("canonical_1130_forbidden")
        row_dt = _parse_dt(str(row.get("bar_time") or row.get("datetime") or row.get("minute_label") or ""))
        if proof_dt is not None and row_dt is not None and row_dt > proof_dt:
            blocked_reasons.append("row_after_proof_input_time")
        if expected_trade_date and _row_trade_date(row, row_dt=row_dt) != expected_trade_date:
            blocked_reasons.append("source_trade_date_mismatch")
        duplicate_key = (
            str(row.get("asset_kind") or ""),
            str(row.get("identity_key") or row.get("code") or row.get("symbol") or ""),
            label,
        )
        if duplicate_key in seen_keys:
            blocked_reasons.append("duplicate_object_minute")
        seen_keys.add(duplicate_key)
        missing_fields = [
            field
            for field in ("open", "high", "low", "close", "amount")
            if row.get(field) in (None, "")
        ]
        if missing_fields:
            blocked_reasons.append(f"missing_index_board_fields:{','.join(missing_fields)}")

    for row in stock_quote_rows:
        if row.get("price") in (None, ""):
            blocked_reasons.append("missing_stock_price")
        if row.get("amount") in (None, ""):
            blocked_reasons.append("missing_stock_amount")
        row_dt = _parse_dt(str(row.get("source_time") or row.get("servertime") or row.get("datetime") or ""))
        raw_trade_date = row_dt.strftime("%Y%m%d") if row_dt is not None else _row_trade_date(row, row_dt=row_dt)
        if expected_trade_date and raw_trade_date not in ("", expected_trade_date):
            blocked_reasons.append("source_trade_date_mismatch")
        stock_proof_dt = _parse_dt(str(row.get("canonical_stock_quote_proof_time") or row.get("canonical_proof_time") or ""))
        comparable_dt = stock_proof_dt or row_dt
        if proof_dt is not None and comparable_dt is not None and comparable_dt > proof_dt:
            blocked_reasons.append("row_after_proof_input_time")

    ordered_reasons = list(dict.fromkeys(blocked_reasons))
    return {
        "valid": not ordered_reasons,
        "blocked_reasons": ordered_reasons,
    }


def normalize_n3p_current_source_rows_before_validation(
    *,
    stock_quote_rows: Sequence[Mapping[str, Any]],
    index_board_1m_rows: Sequence[Mapping[str, Any]],
    for_trade_date: str,
) -> dict[str, Any]:
    """Filter adapter over-fetch while preserving fail-closed source contracts."""

    expected_trade_date = _normalize_trade_date(for_trade_date)
    trace = {
        "raw_rows_before_filter": {
            "stock_quote_rows": len(stock_quote_rows),
            "index_board_1m_rows": len(index_board_1m_rows),
        },
        "rows_dropped_date_mismatch": 0,
        "rows_dropped_1130": 0,
        "duplicate_rows_collapsed": 0,
        "duplicate_conflicts": 0,
    }
    blocked_reasons: list[str] = []
    normalized_stock_rows, stock_blocked_reasons = _normalize_stock_quote_rows_for_canonical_minutes(
        stock_quote_rows=stock_quote_rows,
        for_trade_date=for_trade_date,
        normalization_trace=trace,
    )
    blocked_reasons.extend(stock_blocked_reasons)
    normalized_index_board_rows: list[dict[str, Any]] = []
    seen: dict[tuple[str, str, str], dict[str, Any]] = {}

    for source_row in index_board_1m_rows:
        row = dict(source_row)
        row_dt = _parse_dt(str(row.get("bar_time") or row.get("datetime") or row.get("minute_label") or ""))
        if expected_trade_date and _row_trade_date(row, row_dt=row_dt) != expected_trade_date:
            trace["rows_dropped_date_mismatch"] += 1
            continue
        label = _row_minute_label(row)
        if label == "11:30":
            trace["rows_dropped_1130"] += 1
            continue
        duplicate_key = (
            str(row.get("asset_kind") or ""),
            str(row.get("identity_key") or row.get("code") or row.get("symbol") or ""),
            label,
        )
        previous = seen.get(duplicate_key)
        if previous is not None:
            if _n3p_current_source_duplicate_equivalent(previous, row):
                trace["duplicate_rows_collapsed"] += 1
                continue
            trace["duplicate_conflicts"] += 1
            blocked_reasons.append("duplicate_object_minute_conflict")
            continue
        seen[duplicate_key] = row
        normalized_index_board_rows.append(row)

    return {
        "stock_quote_rows": normalized_stock_rows,
        "index_board_1m_rows": normalized_index_board_rows,
        "normalization_trace": trace,
        "blocked_reasons": list(dict.fromkeys(blocked_reasons)),
    }


def fetch_n3p_current_market_rows_from_adapter(
    *,
    args: Any,
    report: Mapping[str, Any],
    dependencies: Any,
    scope: Mapping[str, Any],
    config: Mapping[str, Any],
    adapter: Any = None,
) -> Mapping[str, Any]:
    """Fetch N3P current-source rows through a low-level market client only."""

    del report, config
    for_trade_date = str(getattr(args, "for_trade_date", "") or scope.get("for_trade_date") or "")
    stock_objects = _rows(scope, "stock_quote_objects")
    index_objects = _rows(scope, "index_1m_objects")
    board_objects = _rows(scope, "board_1m_objects")
    if not (stock_objects or index_objects or board_objects):
        return _blocked(
            N3P_SOURCE_FETCH_BACKEND_FETCHER_BLOCKER,
            "market fetch scope objects are required for N3P current source fetch",
        )
    market_adapter = _resolve_market_fetch_adapter(adapter=adapter, dependencies=dependencies)
    if isinstance(market_adapter, Mapping) and _is_blocked(market_adapter):
        return market_adapter

    observed_at = _now_shanghai_iso()
    stock_quote_rows: list[dict[str, Any]] = []
    index_board_1m_rows: list[dict[str, Any]] = []
    fetch_errors: list[str] = []

    for obj in stock_objects:
        try:
            records = _fetch_stock_quote_records(market_adapter, obj)
        except Exception as exc:  # pragma: no cover - defensive adapter boundary.
            fetch_errors.append(f"stock:{obj.get('identity_key')}:{type(exc).__name__}:{exc}")
            continue
        if not records:
            continue
        stock_quote_rows.append(
            _normalize_stock_quote_row(
                raw=records[0],
                obj=obj,
                for_trade_date=for_trade_date,
                observed_at=observed_at,
            )
        )

    for obj in (*index_objects, *board_objects):
        try:
            records = _fetch_index_board_1m_records(market_adapter, obj)
        except Exception as exc:  # pragma: no cover - defensive adapter boundary.
            fetch_errors.append(f"{obj.get('asset_kind')}:{obj.get('identity_key')}:{type(exc).__name__}:{exc}")
            continue
        for raw in records:
            row = _normalize_index_board_1m_row(
                raw=raw,
                obj=obj,
                for_trade_date=for_trade_date,
                observed_at=observed_at,
            )
            if row is not None:
                index_board_1m_rows.append(row)

    normalization = normalize_n3p_current_source_rows_before_validation(
        stock_quote_rows=stock_quote_rows,
        index_board_1m_rows=index_board_1m_rows,
        for_trade_date=for_trade_date,
    )
    stock_quote_rows = normalization["stock_quote_rows"]
    index_board_1m_rows = normalization["index_board_1m_rows"]
    normalization_trace = normalization["normalization_trace"]
    if normalization["blocked_reasons"]:
        return _blocked(
            N3P_SOURCE_FETCH_PAYLOAD_BLOCKER,
            ",".join(normalization["blocked_reasons"]),
            blocked_reasons=normalization["blocked_reasons"],
            fetch_errors=fetch_errors,
            normalization_trace=normalization_trace,
        )

    source_minute_alignment = _source_realtime_freshness_trace(
        stock_quote_rows=stock_quote_rows,
        index_board_1m_rows=index_board_1m_rows,
    )
    alignment_blocker = _source_canonical_minute_alignment_blocker_from_trace(source_minute_alignment)
    if alignment_blocker is not None:
        return alignment_blocker

    proof_input_time = _derive_market_fetch_proof_input_time(
        stock_quote_rows=stock_quote_rows,
        index_board_1m_rows=index_board_1m_rows,
    )
    if not proof_input_time:
        return _blocked(
            N3P_SOURCE_FETCH_PAYLOAD_BLOCKER,
            "proof_input_time is required",
            fetch_errors=fetch_errors,
            normalization_trace=normalization_trace,
        )
    for row in (*stock_quote_rows, *index_board_1m_rows):
        row["proof_input_time"] = proof_input_time

    payload = {
        "stock_quote_rows": stock_quote_rows,
        "index_board_1m_rows": index_board_1m_rows,
    }
    validation = validate_n3p_current_source_payload(
        payload,
        for_trade_date=for_trade_date,
        proof_input_time=proof_input_time,
        source_scope=scope,
    )
    if fetch_errors:
        validation["blocked_reasons"].append(f"fetch_errors:{len(fetch_errors)}")
        validation["valid"] = False
    if not validation["valid"]:
        return _blocked(
            N3P_SOURCE_FETCH_PAYLOAD_BLOCKER,
            ",".join(list(dict.fromkeys(validation["blocked_reasons"]))),
            blocked_reasons=list(dict.fromkeys(validation["blocked_reasons"])),
            fetch_errors=fetch_errors,
            normalization_trace=normalization_trace,
        )

    index_row_ids = {row["identity_key"] for row in index_board_1m_rows if row.get("asset_kind") == "index"}
    board_row_ids = {row["identity_key"] for row in index_board_1m_rows if row.get("asset_kind") == "board"}
    return {
        "proof_input_time": proof_input_time,
        "canonical_proof_time": proof_input_time,
        "canonical_proof_minute": _hhmm_from_time(proof_input_time),
        "actual_until_hhmm": _hhmm_from_time(proof_input_time),
        "stock_quote_rows": stock_quote_rows,
        "index_board_1m_rows": index_board_1m_rows,
        "fetch_counts": {
            "stock": len({row["identity_key"] for row in stock_quote_rows}),
            "index": len(index_row_ids),
            "board": len(board_row_ids),
            "stock_quote_rows": len(stock_quote_rows),
            "index_board_1m_rows": len(index_board_1m_rows),
        },
        "missing_objects": {
            "stock": [],
            "index": [],
            "board": [],
        },
        "fetch_errors": [],
        "normalization_trace": normalization_trace,
        "source_minute_alignment": source_minute_alignment,
        **source_minute_alignment,
        "market_data_pulled": True,
        "database_written": False,
        "writes_outbox": False,
        "writes_n3p_metric_rows": False,
    }


def load_n3p_current_source_scope_from_db(
    *,
    args: Any,
    report: Mapping[str, Any],
    dependencies: Any,
    config: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Load N3P current source object scope from passed N3/N4 lineage only."""

    del report, dependencies
    for_trade_date = str(getattr(args, "for_trade_date", "") or "")
    subscription_run_id = str(getattr(args, "subscription_run_id", "") or "")
    n4_context_run_id = str(getattr(args, "n4_context_run_id", "") or "")
    missing = [
        name
        for name, value in (
            ("for_trade_date", for_trade_date),
            ("subscription_run_id", subscription_run_id),
            ("n4_context_run_id", n4_context_run_id),
        )
        if not value
    ]
    if missing:
        return _blocked(N3P_SOURCE_SCOPE_NOT_READY_BLOCKER, f"missing_scope_input:{','.join(missing)}")

    try:
        with _connect_db(config) as conn:
            conn.execute("BEGIN READ ONLY")
            try:
                return _load_n3p_current_source_scope_with_connection(
                    conn=conn,
                    for_trade_date=for_trade_date,
                    subscription_run_id=subscription_run_id,
                    n4_context_run_id=n4_context_run_id,
                )
            finally:
                conn.execute("ROLLBACK")
    except Exception as exc:
        return _blocked(N3P_SOURCE_SCOPE_NOT_READY_BLOCKER, f"scope_loader_exception:{type(exc).__name__}:{exc}")


def validate_n3p_current_source_scope(scope: Mapping[str, Any]) -> dict[str, Any]:
    blocked_reasons: list[str] = []
    if int(scope.get("stock_minute_bar_scope_count") or 0) != 0:
        blocked_reasons.append("stock_minute_bar_scope_forbidden")
    if _rows(scope, "stock_1m_objects", "stock_minute_bar_objects"):
        blocked_reasons.append("stock_minute_bar_scope_forbidden")
    if (
        int(scope.get("stock_object_count") or 0)
        + int(scope.get("index_object_count") or 0)
        + int(scope.get("board_object_count") or 0)
        == 0
    ):
        blocked_reasons.append("source_scope_empty")
    ordered_reasons = list(dict.fromkeys(blocked_reasons))
    return {"valid": not ordered_reasons, "blocked_reasons": ordered_reasons}


def _load_n3p_current_source_scope_with_connection(
    *,
    conn: Any,
    for_trade_date: str,
    subscription_run_id: str,
    n4_context_run_id: str,
) -> Mapping[str, Any]:
    calendar = _fetchone(
        conn,
        "SELECT is_open, prev_trade_date FROM common_trade_calendar WHERE trade_date=%s",
        (for_trade_date,),
    )
    if not calendar:
        return _blocked(N3P_SOURCE_SCOPE_NOT_READY_BLOCKER, f"trade_calendar_missing:{for_trade_date}")
    if not bool(calendar[0]):
        return _blocked(N3P_SOURCE_SCOPE_NOT_READY_BLOCKER, f"trade_date_not_open:{for_trade_date}")
    prev_trade_date = str(calendar[1] or "")

    subscription_status = _run_status(conn, "common_market_data_run", subscription_run_id)
    if subscription_status != "passed":
        return _blocked(N3P_SOURCE_SCOPE_NOT_READY_BLOCKER, f"subscription_status={subscription_status or 'missing'}")

    source_previous_day_minute_run_id = _derive_a1_preload_run_id(
        for_trade_date=for_trade_date,
        prev_trade_date=prev_trade_date,
        subscription_run_id=subscription_run_id,
    )
    a1_status = _run_status(conn, "common_market_data_run", source_previous_day_minute_run_id)
    if a1_status != "passed":
        return _blocked(N3P_SOURCE_SCOPE_NOT_READY_BLOCKER, f"a1_preload_status={a1_status or 'missing'}")

    n4_context_status = _run_status(conn, "common_trigger_run", n4_context_run_id)
    if n4_context_status != "passed":
        return _blocked(N3P_SOURCE_SCOPE_NOT_READY_BLOCKER, f"n4_context_status={n4_context_status or 'missing'}")

    context_rows = {
        "stock": _context_rows(conn, "stock_trigger_context_snapshot", n4_context_run_id),
        "index": _context_rows(conn, "index_trigger_context_snapshot", n4_context_run_id),
        "board": _context_rows(conn, "board_trigger_context_snapshot", n4_context_run_id),
    }
    bad_quality = [
        f"{asset}:{row.get('identity_key')}:{row.get('quality_status')}"
        for asset, rows in context_rows.items()
        for row in rows
        if str(row.get("quality_status") or "passed") != "passed"
    ]
    if bad_quality:
        return _blocked(N3P_SOURCE_SCOPE_NOT_READY_BLOCKER, f"context_quality_not_passed:{bad_quality[0]}")

    stock_hint_excluded_count = sum(1 for row in context_rows["stock"] if bool(row.get("is_hint_scope")))
    stock_scope_rows = [row for row in context_rows["stock"] if not bool(row.get("is_hint_scope"))]
    deduped_or_blocked = {
        "stock": _dedupe_context_objects(stock_scope_rows, asset_kind="stock"),
        "index": _dedupe_context_objects(context_rows["index"], asset_kind="index"),
        "board": _dedupe_context_objects(context_rows["board"], asset_kind="board"),
    }
    for value in deduped_or_blocked.values():
        if isinstance(value, Mapping) and _is_blocked(value):
            return value

    stock_objects = list(deduped_or_blocked["stock"])
    index_objects = list(deduped_or_blocked["index"])
    board_objects = list(deduped_or_blocked["board"])
    cumulative_counts = {
        "stock": _cumulative_count(conn, "stock_previous_day_minute_cumulative", source_previous_day_minute_run_id),
        "index": _cumulative_count(conn, "index_previous_day_minute_cumulative", source_previous_day_minute_run_id),
        "board": _cumulative_count(conn, "board_previous_day_minute_cumulative", source_previous_day_minute_run_id),
    }
    for asset, objects in (("stock", stock_objects), ("index", index_objects), ("board", board_objects)):
        if objects and cumulative_counts[asset] <= 0:
            return _blocked(N3P_SOURCE_SCOPE_NOT_READY_BLOCKER, f"a1_cumulative_missing:{asset}")

    scope = {
        "for_trade_date": for_trade_date,
        "source_trade_date": prev_trade_date,
        "prev_trade_date": prev_trade_date,
        "subscription_run_id": subscription_run_id,
        "n4_context_run_id": n4_context_run_id,
        "source_previous_day_minute_run_id": source_previous_day_minute_run_id,
        "subscription_status": "passed",
        "n4_context_status": "passed",
        "a1_preload_status": "passed",
        "a1_cumulative_status": "passed",
        "source_scope_policy": "n4_context_dedup_for_n3p_current_source_v1",
        "stock_quote_objects": stock_objects,
        "index_1m_objects": index_objects,
        "board_1m_objects": board_objects,
        "stock_object_count": len(stock_objects),
        "index_object_count": len(index_objects),
        "board_object_count": len(board_objects),
        "stock_quote_count": len(stock_objects),
        "index_board_1m_count": len(index_objects) + len(board_objects),
        "stock_minute_bar_scope_count": 0,
        "stock_hint_excluded_count": stock_hint_excluded_count,
        "context_row_counts": {asset: len(rows) for asset, rows in context_rows.items()},
        "dedupe_counts": {
            "stock": len(stock_objects),
            "index": len(index_objects),
            "board": len(board_objects),
        },
        "cumulative_row_counts": cumulative_counts,
    }
    validation = validate_n3p_current_source_scope(scope)
    if not validation["valid"]:
        return _blocked(
            N3P_SOURCE_SCOPE_NOT_READY_BLOCKER,
            ",".join(validation["blocked_reasons"]),
            blocked_reasons=validation["blocked_reasons"],
        )
    return scope


def _validate_source_scope(scope: Mapping[str, Any]) -> Mapping[str, Any] | None:
    checks = {
        "n4_context_status": "passed",
        "subscription_status": "passed",
        "a1_cumulative_status": "passed",
    }
    failed = [
        f"{key}={scope.get(key)}"
        for key, expected in checks.items()
        if key in scope and str(scope.get(key)) != expected
    ]
    if failed:
        return _blocked(N3P_SOURCE_FETCH_PRECHECK_BLOCKER, ",".join(failed))
    return None


def _validate_requested_until(*, args: Any, actual_until_hhmm: str) -> Mapping[str, Any] | None:
    requested = str(getattr(args, "requested_until_hhmm", "") or "")
    target_until = _until_from_run_id(str(getattr(args, "target_run_id", "") or ""))
    expected = requested or target_until
    if expected and expected != actual_until_hhmm:
        return _blocked(
            N3P_SOURCE_TIME_RELABEL_BLOCKER,
            f"requested_until_hhmm={expected} actual_until_hhmm={actual_until_hhmm}",
            actual_until_hhmm=actual_until_hhmm,
            requested_until_hhmm=expected,
        )
    return None


def _post_close_proof_minute_blocker(
    *,
    proof_input_time: str,
    actual_until_hhmm: str,
    source_payload_classification: str = "",
) -> Mapping[str, Any] | None:
    actual_hhmm = str(actual_until_hhmm or _hhmm_from_time(proof_input_time) or "")
    if not actual_hhmm:
        return None
    try:
        actual_value = int(actual_hhmm)
        max_value = int(N3P_MAX_CANONICAL_PROOF_HHMM)
    except ValueError:
        return None
    if actual_value <= max_value:
        return None

    extra: dict[str, Any] = {
        "raw_source_time": str(proof_input_time or ""),
        "actual_until_hhmm": actual_hhmm,
        "max_canonical_proof_hhmm": N3P_MAX_CANONICAL_PROOF_HHMM,
        "post_close_proof_minute_blocked": True,
        "artifact_written": False,
        "source_payload_registered": False,
        "database_written": False,
    }
    if source_payload_classification:
        extra["source_payload_classification"] = source_payload_classification
    return _blocked(
        N3P_SOURCE_POST_CLOSE_PROOF_MINUTE_BLOCKER,
        f"actual_until_hhmm={actual_hhmm} max_canonical_proof_hhmm={N3P_MAX_CANONICAL_PROOF_HHMM}",
        **extra,
    )


def _source_payload_run_id(*, args: Any, actual_until_hhmm: str) -> str:
    target_run_id = str(getattr(args, "target_run_id", "") or "")
    if target_run_id.startswith("n3p_mixed_realtime_source_payload_") and _until_from_run_id(target_run_id) == actual_until_hhmm:
        return target_run_id
    for_trade_date = str(getattr(args, "for_trade_date", "") or "")
    return f"n3p_mixed_realtime_source_payload_{for_trade_date}_until_{actual_until_hhmm}_v1"


def _until_from_run_id(run_id: str) -> str:
    match = re.search(r"_until_(\d{4})(?:_|$)", run_id)
    return match.group(1) if match else ""


def _source_scope_counts(scope: Mapping[str, Any]) -> dict[str, int]:
    return {
        "stock_object_count": int(scope.get("stock_object_count") or scope.get("stock_objects") or 0),
        "index_object_count": int(scope.get("index_object_count") or scope.get("index_objects") or 0),
        "board_object_count": int(scope.get("board_object_count") or scope.get("board_objects") or 0),
    }


def _rows(payload: Mapping[str, Any], *keys: str) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            rows.extend(row for row in value if isinstance(row, Mapping))
    return rows


def _scope_identity_keys(scope: Mapping[str, Any], key: str) -> set[str]:
    return {str(row.get("identity_key") or "") for row in _rows(scope, key) if row.get("identity_key")}


def _source_payload_hash(source_payload: Mapping[str, Any]) -> str:
    return str(source_payload.get("source_payload_hash") or source_payload.get("payload_hash") or "")


def _existing_source_payload_run(cur: Any, source_payload_run_id: str) -> tuple[str, Any] | None:
    cur.execute(
        "SELECT status, raw_json FROM common_market_data_run WHERE run_id = %s LIMIT 1",
        (source_payload_run_id,),
    )
    row = cur.fetchone()
    if not row:
        return None
    if isinstance(row, Mapping):
        return str(row.get("status") or ""), row.get("raw_json")
    return str(row[0] or ""), row[1] if len(row) > 1 else None


def _existing_source_payload_hash(raw_json: Any) -> str:
    raw = _registration_raw_json(raw_json)
    return str(raw.get("source_payload_hash") or raw.get("payload_hash") or "")


def _registration_raw_json(raw_json: Any) -> Mapping[str, Any]:
    if isinstance(raw_json, Mapping):
        return raw_json
    if raw_json in (None, ""):
        return {}
    try:
        parsed = json.loads(str(raw_json))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, Mapping) else {}


def _existing_source_payload_downstream_ref_blocker(cur: Any, source_payload_run_id: str) -> str:
    guard_queries = (
        ("outbox_refs", "SELECT count(*) FROM common_event_outbox WHERE source_run_id = %s", (source_payload_run_id,)),
        ("inbox_refs", "SELECT count(*) FROM common_event_inbox WHERE source_run_id = %s", (source_payload_run_id,)),
        (
            "trigger_refs",
            "SELECT count(*) FROM common_trigger_run WHERE source_market_data_run_id = %s OR run_id = %s",
            (source_payload_run_id, source_payload_run_id),
        ),
        (
            "action_refs",
            "SELECT count(*) FROM common_action_run WHERE source_trigger_run_id = %s OR run_id = %s",
            (source_payload_run_id, source_payload_run_id),
        ),
    )
    for label, sql, params in guard_queries:
        cur.execute(sql, params)
        row = cur.fetchone()
        value = int((row.get("count") if isinstance(row, Mapping) else row[0]) or 0) if row else 0
        if value:
            return f"dirty_target_{label}"
    return ""


def _source_payload_registration_contract(*, args: Any, source_payload: Mapping[str, Any]) -> dict[str, Any]:
    subscription_run_id = str(
        source_payload.get("subscription_run_id")
        or getattr(args, "subscription_run_id", "")
        or ""
    )
    for_trade_date = str(source_payload.get("for_trade_date") or getattr(args, "for_trade_date", "") or "")
    source_trade_date = str(source_payload.get("source_trade_date") or _source_trade_date_from_subscription(subscription_run_id))
    source_condition_run_id = str(
        source_payload.get("source_condition_run_id")
        or _source_condition_run_id_from_subscription(subscription_run_id)
    )
    source_scope = {
        "source_payload_run_id": str(source_payload.get("source_payload_run_id") or ""),
        "source_condition_run_id": source_condition_run_id,
        "for_trade_date": for_trade_date,
        "source_trade_date": source_trade_date,
        "source_mode": str(source_payload.get("source_mode") or "b1_source_returned_snapshot"),
        "source_origin": str(source_payload.get("source_origin") or "local_mootdx_fetch_artifact"),
        "source_artifact_path": str(source_payload.get("source_artifact_path") or source_payload.get("payload_path") or ""),
        "source_payload_hash": _source_payload_hash(source_payload),
        "writes_outbox": False,
    }
    return {
        "source_model": str(source_payload.get("source_model") or N3P_SOURCE_MODEL),
        "source_mode": source_scope["source_mode"],
        "source_scope": source_scope,
        "db_backed_input_contract": dict(source_scope),
        "writes_outbox": False,
        "writes_n3p_metric_rows": False,
        "not_n5_final_proof": True,
    }


def _source_trade_date_from_subscription(subscription_run_id: str) -> str:
    match = re.search(r"_source_(\d{8})_for_", subscription_run_id)
    return match.group(1) if match else ""


def _source_condition_run_id_from_subscription(subscription_run_id: str) -> str:
    match = re.search(r"_condition_layer_(\d{8})_source_(\d{8})_for_(\d{8})_v(\d+)", subscription_run_id)
    if not match:
        return ""
    condition_date, source_date, for_trade_date, version = match.groups()
    return f"condition_layer_{condition_date}_source_{source_date}_for_{for_trade_date}_v{version}"


def _ensure_source_payload_run(
    *,
    cur: Any,
    contract: Mapping[str, Any],
    source_payload: Mapping[str, Any],
    started_at: str,
) -> int:
    from ashare_v3.market.v3_realtime_virtual_metric_writer import ensure_mixed_realtime_source_payload_run

    return int(
        ensure_mixed_realtime_source_payload_run(
            cur=cur,
            contract=contract,
            source_payload=source_payload,
            started_at=started_at,
        )
        or 0
    )


def _registration_ready(
    *,
    source_payload_run_id: str,
    source_payload_hash: str,
    registration_result: str,
    database_written: bool,
    started_at: str,
    finished_at: str,
) -> dict[str, Any]:
    payload = {
        "result": N3_READY_RESULT,
        "source_payload_run_id": source_payload_run_id,
        "source_payload_hash": source_payload_hash,
        "registration_attempted": True,
        "registration_result": registration_result,
        "source_payload_registered": True,
        "database_written": database_written,
        "started_at": started_at,
        "finished_at": finished_at,
        "timestamp_order_valid": finished_at >= started_at,
        "writes_n3p_metric_rows": False,
        "writes_outbox": False,
    }
    _apply_forbidden_side_effect_guards(payload)
    return payload


def _registration_blocked(reason: str, **extra: Any) -> dict[str, Any]:
    return _blocked(
        N3P_SOURCE_FETCH_BACKEND_REGISTRATION_BLOCKER,
        reason,
        registration_attempted=True,
        registration_result=reason,
        source_payload_registered=False,
        database_written=False,
        **extra,
    )


def _fetchone_from_cursor(cur: Any, sql: str, params: Sequence[Any] = ()) -> Any:
    cur.execute(sql, tuple(params))
    return cur.fetchone()


def _fetchall_from_cursor(cur: Any, sql: str, params: Sequence[Any] = ()) -> list[Any]:
    cur.execute(sql, tuple(params))
    return list(cur.fetchall())


def _row_value(row: Any, index: int, key: str) -> Any:
    if isinstance(row, Mapping):
        return row.get(key)
    try:
        return row[index]
    except (IndexError, TypeError):
        return None


def _run_status_from_cursor(cur: Any, table_name: str, run_id: str) -> str:
    allowed_tables = {"common_market_data_run", "common_trigger_run"}
    if table_name not in allowed_tables:
        raise ValueError(f"unsupported run status table: {table_name}")
    row = _fetchone_from_cursor(cur, f"SELECT status FROM {table_name} WHERE run_id=%s", (run_id,))
    return str(_row_value(row, 0, "status") or "") if row else ""


def _trigger_context_snapshot_rows_for_preflight(cur: Any, table_name: str, n4_context_run_id: str) -> list[dict[str, Any]]:
    allowed_tables = {
        "stock_trigger_context_snapshot",
        "index_trigger_context_snapshot",
        "board_trigger_context_snapshot",
    }
    if table_name not in allowed_tables:
        raise ValueError(f"unsupported context table: {table_name}")
    rows = _fetchall_from_cursor(
        cur,
        f"SELECT * FROM {table_name} WHERE run_id=%s ORDER BY identity_key, trigger_context_id",
        (n4_context_run_id,),
    )
    return [dict(row) if isinstance(row, Mapping) else {} for row in rows]


def _build_n3p_trigger_proof_preflight_contract(
    *,
    writer: Any,
    target_run_id: str,
    parsed_target: Mapping[str, Any],
    for_trade_date: str,
    source_trade_date: str,
    source_condition_run_id: str,
    subscription_run_id: str,
    n4_context_run_id: str,
    source_payload_run_id: str,
    source_previous_day_minute_run_id: str,
    source_payload: Mapping[str, Any],
    source_payload_hash: str,
    proof_input_time: str,
    context_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    until_hhmm = str(parsed_target.get("until_hhmm") or "")
    until_minute_label = f"{_yyyymmdd_to_date_label(for_trade_date)} {until_hhmm[:2]}:{until_hhmm[2:]}"
    source_artifact_path = str(source_payload.get("source_artifact_path") or source_payload.get("payload_path") or "")
    source_scope = {
        "for_trade_date": for_trade_date,
        "source_trade_date": source_trade_date,
        "source_condition_run_id": source_condition_run_id,
        "source_subscription_run_id": subscription_run_id,
        "source_previous_day_minute_run_id": source_previous_day_minute_run_id,
        "source_snapshot_run_id": source_payload_run_id,
        "source_payload_run_id": source_payload_run_id,
        "source_model": N3P_SOURCE_MODEL,
        "source_mode": "b1_source_returned_snapshot",
        "source_variant": parsed_target.get("source_variant"),
        "source_time_policy": {"mode": "source_returned_time"},
        "source_snapshot_time": proof_input_time,
        "proof_input_time": proof_input_time,
        "proof_input_time_source": "N3P_mixed_realtime_source_payload",
        "target_until_hhmm_source": "source_payload_actual_until_hhmm",
        "raw_target_minute_label": until_minute_label,
        "requested_until_minute_label": until_minute_label,
        "until_minute_label": until_minute_label,
        "require_previous_day_cumulative_rows": True,
        "n4_context_run_id": n4_context_run_id,
        "source_artifact_path": source_artifact_path,
        "source_payload_hash": source_payload_hash,
        "source_origin": "local_mootdx_fetch_artifact",
        "writes_outbox": False,
    }
    return {
        "result": "CONTRACT_PASS",
        "metric_family": "realtime_action_confirmation_metric",
        "run_id_contract": "n3p.realtime_action_confirmation_metric.v1",
        "target_run_id": target_run_id,
        "until_minute_label": until_minute_label,
        "projection_schema_version": "v3.realtime_virtual_metric.writer.contract.v1",
        "source_scope": source_scope,
        "db_backed_input_contract": {
            **source_scope,
            "source_snapshot_time": proof_input_time,
            "observed_at": proof_input_time,
            "c1_dependency": False,
            "n2_period_context_source": "trigger_context_snapshot",
            "asset_kinds": ["stock", "index", "board"],
            "context_row_count": len(context_rows),
        },
        "allowed_write_tables": list(N3P_TRIGGER_PROOF_PREFLIGHT_ALLOWED_WRITE_TABLES),
        "forbidden_write_tables": list(N3P_TRIGGER_PROOF_PREFLIGHT_FORBIDDEN_WRITE_TABLES),
        "expected_not_ready_blocked_reasons": list(N3P_TRIGGER_PROOF_EXPECTED_NOT_READY_BLOCKED_REASONS),
        "expected_not_ready_blocked_reason_prefixes": list(
            N3P_TRIGGER_PROOF_EXPECTED_NOT_READY_BLOCKED_REASON_PREFIXES
        ),
    }


def _build_n3p_trigger_proof_candidates(
    *,
    writer: Any,
    contract: Mapping[str, Any],
    context_rows: Sequence[Mapping[str, Any]],
    proof_input_time: str,
    proof_hhmm: str,
) -> list[dict[str, Any]]:
    proof_minute_label = proof_input_time.replace("T", " ")[:16]
    candidates: list[dict[str, Any]] = []
    for context_row in context_rows:
        asset_kind = str(context_row.get("asset_kind") or "")
        identity_key = str(context_row.get("identity_key") or "")
        if asset_kind not in {"stock", "index", "board"} or not identity_key:
            continue
        snapshot_row = {
            "asset_kind": asset_kind,
            "identity_key": identity_key,
            "exchange": context_row.get("exchange"),
            "code": context_row.get("code") or str(identity_key).rsplit(":", 1)[-1],
            "display_code": context_row.get("display_code") or context_row.get("code"),
            "name": context_row.get("name") or identity_key,
            "source_snapshot_run_id": contract["source_scope"]["source_snapshot_run_id"],
            "source_snapshot_row_id": f"{asset_kind}:{identity_key}:{proof_hhmm}",
            "source_record_key": context_row.get("code") or str(identity_key).rsplit(":", 1)[-1],
            "proof_input_time": proof_input_time,
            "source_snapshot_time": proof_input_time,
            "observed_at": proof_input_time,
            "fetched_at": proof_input_time,
            "raw_json": {
                "source_payload_run_id": contract["source_scope"]["source_payload_run_id"],
                "source_model": N3P_SOURCE_MODEL,
            },
        }
        candidates.append(
            writer._build_b1_source_returned_candidate(
                contract=contract,
                snapshot_row=snapshot_row,
                context_row=context_row,
                proof_input_time=proof_input_time,
                proof_hhmm=proof_hhmm,
                proof_minute_label=proof_minute_label,
            )
        )
    return candidates


def _candidate_unique_key(candidate: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        candidate.get("asset_kind"),
        candidate.get("identity_key"),
        candidate.get("direction"),
        candidate.get("signal_type"),
        candidate.get("condition_key"),
        candidate.get("original_condition_key"),
        candidate.get("source_condition_pool_id"),
        candidate.get("source_minute_target_scope_id"),
        candidate.get("proof_input_minute_label"),
    )


def _not_ready_reason_distribution(rows_by_asset: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for rows in rows_by_asset.values():
        for row in rows:
            if bool(row.get("metric_ready")):
                continue
            raw_json = _mapping_from_jsonish(row.get("raw_json"))
            trace_json = _mapping_from_jsonish(row.get("trace_json"))
            reasons: list[str] = []
            for container in (row, raw_json, trace_json):
                for key in ("blocked_reasons", "not_ready_reasons", "metric_not_ready_reasons"):
                    value = container.get(key) if isinstance(container, Mapping) else None
                    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
                        reasons.extend(str(item) for item in value)
            missing_inputs = raw_json.get("formal_amount_chain_missing_inputs") or trace_json.get("formal_amount_chain_missing_inputs")
            if isinstance(missing_inputs, Mapping):
                for period, fields in missing_inputs.items():
                    if isinstance(fields, Sequence) and not isinstance(fields, (str, bytes, bytearray)):
                        reasons.extend(f"formal_amount_chain_missing:{period}:{field}" for field in fields)
                    elif fields:
                        reasons.append(f"formal_amount_chain_missing:{period}:{fields}")
            if not reasons:
                reasons.append("unknown_not_ready")
            counts.update(dict.fromkeys(reasons, 1))
    return dict(sorted(counts.items()))


def _source_amount_kind_distribution(rows_by_asset: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for rows in rows_by_asset.values():
        for row in rows:
            raw_json = _mapping_from_jsonish(row.get("raw_json"))
            trace_json = _mapping_from_jsonish(row.get("trace_json"))
            kind = (
                raw_json.get("amount_source_kind")
                or raw_json.get("current_amount_source_kind")
                or trace_json.get("amount_source_kind")
                or trace_json.get("current_amount_source_kind")
                or "unknown"
            )
            counts[str(kind)] += 1
    return dict(sorted(counts.items()))


def _transition_trace_contract(rows_by_asset: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, Any]:
    required_periods = {"D", "W", "M", "Q", "Y"}
    field_counts: dict[str, Counter[str]] = {period: Counter() for period in sorted(required_periods)}
    rows_total = 0
    all_period_rows = 0
    old_conflict_expression_count = 0
    for rows in rows_by_asset.values():
        for row in rows:
            rows_total += 1
            raw_json = _mapping_from_jsonish(row.get("raw_json"))
            trace_json = _mapping_from_jsonish(row.get("trace_json"))
            transition = raw_json.get("transition_input_by_period") or trace_json.get("transition_input_by_period") or {}
            if isinstance(transition, Mapping) and required_periods.issubset(set(str(key) for key in transition)):
                all_period_rows += 1
            if isinstance(transition, Mapping):
                for period, item in transition.items():
                    if str(period) not in field_counts or not isinstance(item, Mapping):
                        continue
                    field = str(item.get("current_period_avg_with_today_field") or item.get("field") or "")
                    if field:
                        field_counts[str(period)][field] += 1
            encoded = json.dumps({"raw_json": raw_json, "trace_json": trace_json}, ensure_ascii=False, default=str)
            if any(token in encoded for token in ("today_virt_amount(M)", "today_virt_amount(Q)", "today_virt_amount(Y)", "today_virt_amount used_for_period=M")):
                old_conflict_expression_count += 1
    return {
        "rows_total": rows_total,
        "all_dwmqy_rows": all_period_rows,
        "period_field_counts": {period: dict(counter) for period, counter in field_counts.items()},
        "old_conflict_expression_count": old_conflict_expression_count,
    }


def _mapping_from_jsonish(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if value in (None, ""):
        return {}
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError):
        return {}
    return dict(parsed) if isinstance(parsed, Mapping) else {}


def _yyyymmdd_to_date_label(value: str) -> str:
    text = _normalize_trade_date(value)
    if len(text) == 8:
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return str(value)


def _resolve_market_fetch_adapter(*, adapter: Any, dependencies: Any) -> Any:
    if _looks_like_market_fetch_adapter(adapter):
        return adapter
    dependency_adapter = getattr(dependencies, "market_fetch_adapter", None)
    if _looks_like_market_fetch_adapter(dependency_adapter):
        return dependency_adapter
    return _blocked(
        N3P_SOURCE_FETCH_BACKEND_FETCHER_BLOCKER,
        "market fetch dependency is required for N3P current source fetch",
    )


def _looks_like_market_fetch_adapter(component: Any) -> bool:
    if component is None:
        return False
    if component.__class__.__name__ in {"N3ProductionRealIOAdapter", "N3PCurrentSourceFetchProvider"}:
        return False
    methods = (
        "quotes",
        "fetch_stock_quote_rows",
        "fetch_stock_quote",
        "index_bars",
        "index",
        "fetch_index_board_1m_rows",
    )
    return any(callable(getattr(component, method, None)) for method in methods)


def _default_mootdx_client() -> Any:
    try:
        from mootdx.quotes import Quotes
    except Exception:  # pragma: no cover - optional runtime dependency.
        return None
    try:
        return Quotes.factory(market="std")
    except Exception:  # pragma: no cover - optional runtime dependency.
        return None


def _now_shanghai_iso() -> str:
    return _format_shanghai_iso(datetime.now(timezone(timedelta(hours=8))))


def _fetch_stock_quote_records(adapter: Any, obj: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    method = (
        getattr(adapter, "fetch_stock_quote_rows", None)
        or getattr(adapter, "fetch_stock_quote", None)
        or getattr(adapter, "quotes", None)
    )
    if not callable(method):
        return []
    value = _call_with_supported_kwargs(
        method,
        objects=[obj],
        obj=obj,
        asset=obj,
        identity_key=obj.get("identity_key"),
        exchange=obj.get("exchange"),
        code=obj.get("code"),
        symbol=obj.get("code"),
    )
    return _records_from_frame(value)


def _fetch_index_board_1m_records(adapter: Any, obj: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    method = (
        getattr(adapter, "fetch_index_board_1m_rows", None)
        or getattr(adapter, "index_bars", None)
        or getattr(adapter, "index", None)
    )
    if not callable(method):
        return []
    value = _call_with_supported_kwargs(
        method,
        objects=[obj],
        obj=obj,
        asset=obj,
        asset_kind=obj.get("asset_kind"),
        identity_key=obj.get("identity_key"),
        exchange=obj.get("exchange"),
        market=_market_code_for_object(obj),
        code=obj.get("code"),
        symbol=obj.get("code"),
        frequency=8,
        start=0,
        offset=800,
    )
    return _records_from_frame(value)


def _records_from_frame(value: Any) -> list[Mapping[str, Any]]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        return [dict(value)]
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            records = to_dict("records")
        except TypeError:
            records = to_dict()
        return [dict(row) for row in records if isinstance(row, Mapping)] if isinstance(records, Sequence) else []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [dict(row) for row in value if isinstance(row, Mapping)]
    return []


def _normalize_stock_quote_row(
    *,
    raw: Mapping[str, Any],
    obj: Mapping[str, Any],
    for_trade_date: str,
    observed_at: str,
) -> dict[str, Any]:
    price = _first_present(raw, "price", "close", "last_price", "current_price")
    source_time = _stock_quote_source_time(raw=raw, for_trade_date=for_trade_date, observed_at=observed_at)
    row = {
        "asset_kind": "stock",
        "identity_key": str(obj.get("identity_key") or ""),
        "exchange": str(obj.get("exchange") or ""),
        "code": str(obj.get("code") or raw.get("code") or ""),
        "name": str(obj.get("name") or raw.get("name") or ""),
        "price": price,
        "open": _first_present(raw, "open"),
        "high": _first_present(raw, "high"),
        "low": _first_present(raw, "low"),
        "close": _first_present(raw, "close", "price"),
        "amount": _first_present(raw, "amount", "turnover"),
        "volume": _first_present(raw, "volume", "vol"),
        "servertime": str(raw.get("servertime") or raw.get("time") or ""),
        "source_time": source_time,
        "observed_at": observed_at,
        "fetched_at": observed_at,
        "source_marker": str(raw.get("source_marker") or "mootdx_quotes"),
        "source_adapter_method": "quotes",
        "trade_date": _normalize_trade_date(for_trade_date),
        "source_trade_date": _normalize_trade_date(for_trade_date),
        "raw_payload": dict(raw),
    }
    return _with_stock_quote_canonical_proof_minute(row, for_trade_date=for_trade_date)


def _normalize_stock_quote_rows_for_canonical_minutes(
    *,
    stock_quote_rows: Sequence[Mapping[str, Any]],
    for_trade_date: str,
    normalization_trace: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    normalized_rows: list[dict[str, Any]] = []
    blocked_reasons: list[str] = []
    canonicalized_count = 0
    for source_row in stock_quote_rows:
        try:
            row = _with_stock_quote_canonical_proof_minute(source_row, for_trade_date=for_trade_date)
            canonicalized_count += 1
        except ValueError as exc:
            row = dict(source_row)
            blocked_reasons.append(f"stock_quote_canonical_proof_minute_invalid:{exc}")
        normalized_rows.append(row)
    normalization_trace["stock_quote_time_mapping_policy"] = N3P_STOCK_QUOTE_CANONICAL_PROOF_MINUTE_POLICY
    normalization_trace["stock_quote_canonicalized_rows"] = canonicalized_count
    normalization_trace["stock_quote_canonicalization_failures"] = len(blocked_reasons)
    return normalized_rows, list(dict.fromkeys(blocked_reasons))


def _with_stock_quote_canonical_proof_minute(row: Mapping[str, Any], *, for_trade_date: str) -> dict[str, Any]:
    output = dict(row)
    raw_source_time = _first_present(output, "raw_source_time", "source_time", "servertime", "datetime", "time")
    if raw_source_time in (None, ""):
        raise ValueError("missing_raw_source_time")
    mapping = canonicalize_stock_quote_proof_minute(raw_source_time, for_trade_date=for_trade_date)
    output["raw_source_time"] = mapping["raw_source_time"]
    output["canonical_stock_quote_proof_minute"] = mapping["canonical_stock_quote_proof_minute"]
    output["canonical_stock_quote_proof_hhmm"] = mapping["canonical_stock_quote_proof_hhmm"]
    output["canonical_stock_quote_proof_time"] = mapping["canonical_stock_quote_proof_time"]
    output["stock_quote_time_mapping_policy"] = mapping["stock_quote_time_mapping_policy"]
    output["stock_quote_time_mapping_reason"] = mapping["stock_quote_time_mapping_reason"]
    output.setdefault("trade_date", _normalize_trade_date(for_trade_date))
    output.setdefault("source_trade_date", _normalize_trade_date(for_trade_date))
    return output


def _normalize_index_board_1m_row(
    *,
    raw: Mapping[str, Any],
    obj: Mapping[str, Any],
    for_trade_date: str,
    observed_at: str,
) -> dict[str, Any] | None:
    row_dt = _market_datetime_from_value(
        _first_present(raw, "bar_time", "datetime", "time"),
        for_trade_date=for_trade_date,
    )
    if row_dt is None:
        return None
    bar_time = _format_shanghai_iso(row_dt)
    return {
        "asset_kind": str(obj.get("asset_kind") or ""),
        "identity_key": str(obj.get("identity_key") or ""),
        "exchange": str(obj.get("exchange") or ""),
        "code": str(obj.get("code") or raw.get("code") or ""),
        "name": str(obj.get("name") or raw.get("name") or ""),
        "bar_time": bar_time,
        "datetime": bar_time,
        "minute_label": row_dt.strftime("%H:%M"),
        "open": _first_present(raw, "open"),
        "high": _first_present(raw, "high"),
        "low": _first_present(raw, "low"),
        "close": _first_present(raw, "close", "price"),
        "amount": _first_present(raw, "amount", "turnover"),
        "volume": _first_present(raw, "volume", "vol"),
        "source_adapter_method": "index",
        "source_frequency": 8,
        "source_marker": str(raw.get("source_marker") or "mootdx_index_frequency_8"),
        "trade_date": row_dt.strftime("%Y%m%d"),
        "source_trade_date": row_dt.strftime("%Y%m%d"),
        "observed_at": observed_at,
        "fetched_at": observed_at,
        "raw_payload": dict(raw),
    }


def _derive_market_fetch_proof_input_time(
    *,
    stock_quote_rows: Sequence[Mapping[str, Any]],
    index_board_1m_rows: Sequence[Mapping[str, Any]],
) -> str:
    candidates: list[datetime] = []
    for row in stock_quote_rows:
        row_dt = _parse_dt(str(row.get("canonical_stock_quote_proof_time") or row.get("canonical_proof_time") or ""))
        if row_dt is None:
            row_dt = _parse_dt(str(row.get("source_time") or row.get("servertime") or ""))
        if row_dt is not None:
            candidates.append(row_dt)
    for row in index_board_1m_rows:
        row_dt = _parse_dt(str(row.get("bar_time") or row.get("datetime") or ""))
        if row_dt is not None:
            candidates.append(row_dt)
    if not candidates:
        return ""
    return _format_shanghai_iso(max(candidates))


def _source_canonical_minute_alignment_blocker(
    *,
    stock_quote_rows: Sequence[Mapping[str, Any]],
    index_board_1m_rows: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    return _source_realtime_freshness_blocker_from_trace(
        _source_realtime_freshness_trace(
            stock_quote_rows=stock_quote_rows,
            index_board_1m_rows=index_board_1m_rows,
        )
    )


def _source_canonical_minute_alignment_trace(
    *,
    stock_quote_rows: Sequence[Mapping[str, Any]],
    index_board_1m_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return _source_realtime_freshness_trace(
        stock_quote_rows=stock_quote_rows,
        index_board_1m_rows=index_board_1m_rows,
    )


def _source_realtime_freshness_trace(
    *,
    stock_quote_rows: Sequence[Mapping[str, Any]],
    index_board_1m_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    stock_candidates = [
        _parse_dt(str(row.get("canonical_stock_quote_proof_time") or row.get("canonical_proof_time") or ""))
        for row in stock_quote_rows
    ]
    index_board_candidates = [
        _parse_dt(str(row.get("bar_time") or row.get("datetime") or ""))
        for row in index_board_1m_rows
    ]
    stock_candidates = [value for value in stock_candidates if value is not None]
    index_board_candidates = [value for value in index_board_candidates if value is not None]
    if not stock_candidates or not index_board_candidates:
        return {}
    stock_proof_time = _format_shanghai_iso(max(stock_candidates))
    index_board_proof_time = _format_shanghai_iso(max(index_board_candidates))
    stock_hhmm = _hhmm_from_time(stock_proof_time)
    index_board_hhmm = _hhmm_from_time(index_board_proof_time)
    minute_delta = _hhmm_minute_delta(stock_hhmm, index_board_hhmm)
    trace: dict[str, Any] = {
        "stock_canonical_until_hhmm": stock_hhmm,
        "index_board_until_hhmm": index_board_hhmm,
        "stock_canonical_hhmm": stock_hhmm,
        "index_board_hhmm": index_board_hhmm,
        "minute_delta": minute_delta,
        "stock_canonical_proof_time": stock_proof_time,
        "index_board_proof_time": index_board_proof_time,
    }
    if stock_hhmm == index_board_hhmm:
        trace["alignment_status"] = N3P_SOURCE_ALIGNMENT_ALIGNED
        return trace
    if stock_hhmm == "1130" and index_board_hhmm == "1300" and minute_delta == 90:
        trace["alignment_status"] = N3P_SOURCE_ALIGNMENT_BLOCKED
        trace["alignment_failure_class"] = N3P_SOURCE_ALIGNMENT_MIDDAY_STOCK_STALE
        return trace
    trace["alignment_status"] = N3P_SOURCE_ALIGNMENT_INDEPENDENT_REALTIME_OK
    return trace


def _source_canonical_minute_alignment_blocker_from_trace(trace: Mapping[str, Any]) -> Mapping[str, Any] | None:
    return _source_realtime_freshness_blocker_from_trace(trace)


def _source_realtime_freshness_blocker_from_trace(trace: Mapping[str, Any]) -> Mapping[str, Any] | None:
    if not trace:
        return None
    alignment_status = str(trace.get("alignment_status") or "")
    if alignment_status in {
        N3P_SOURCE_ALIGNMENT_ALIGNED,
        N3P_SOURCE_ALIGNMENT_ADJACENT_REALTIME_OK,
        N3P_SOURCE_ALIGNMENT_INDEPENDENT_REALTIME_OK,
    }:
        return None
    stock_hhmm = str(trace.get("stock_canonical_hhmm") or "")
    index_board_hhmm = str(trace.get("index_board_hhmm") or "")
    if trace.get("alignment_failure_class") == N3P_SOURCE_ALIGNMENT_MIDDAY_STOCK_STALE:
        return _blocked(
            N3P_SOURCE_MIDDAY_STOCK_TIME_STALE_BLOCKER,
            "stock_quote_servertime_stale_at_midday_wait_for_alignment",
            blocked_reasons=["midday_stock_quote_time_stale_wait_for_alignment"],
            **dict(trace),
            artifact_written=False,
            source_payload_registered=False,
            database_written=False,
            market_data_pulled=False,
            writes_outbox=False,
            writes_n3p_metric_rows=False,
        )
    return _blocked(
        N3P_SOURCE_CANONICAL_MINUTE_ALIGNMENT_BLOCKER,
        f"mixed_canonical_proof_minute_mismatch:stock={stock_hhmm}:index_board={index_board_hhmm}",
        blocked_reasons=["mixed_canonical_proof_minute_mismatch"],
        **dict(trace),
        artifact_written=False,
        source_payload_registered=False,
        database_written=False,
        market_data_pulled=True,
        writes_outbox=False,
        writes_n3p_metric_rows=False,
    )


def _hhmm_minute_delta(left_hhmm: str, right_hhmm: str) -> int:
    left = _hhmm_to_minutes(left_hhmm)
    right = _hhmm_to_minutes(right_hhmm)
    if left is None or right is None:
        return -1
    return abs(left - right)


def _hhmm_to_minutes(hhmm: str) -> int | None:
    value = re.sub(r"\D", "", str(hhmm or ""))
    if len(value) != 4:
        return None
    hour = int(value[:2])
    minute = int(value[2:])
    if hour > 23 or minute > 59:
        return None
    return hour * 60 + minute


def _stock_quote_source_time(*, raw: Mapping[str, Any], for_trade_date: str, observed_at: str) -> str:
    for key in ("source_time", "datetime", "bar_time", "servertime", "time"):
        row_dt = _market_datetime_from_value(raw.get(key), for_trade_date=for_trade_date)
        if row_dt is not None:
            return _format_shanghai_iso(row_dt)
    return observed_at


def canonicalize_stock_quote_proof_minute(raw_source_time: Any, *, for_trade_date: str) -> dict[str, str]:
    """Map quote servertime to the A1 cumulative canonical proof minute."""

    raw_dt = _market_datetime_from_value(raw_source_time, for_trade_date=for_trade_date)
    if raw_dt is None:
        raise ValueError("unparseable_raw_source_time")
    raw_dt = _ensure_shanghai_tz(raw_dt)
    trade_date = _normalize_trade_date(for_trade_date)
    if len(trade_date) != 8:
        raise ValueError("invalid_for_trade_date")
    year, month, day = int(trade_date[:4]), int(trade_date[4:6]), int(trade_date[6:8])
    shanghai = timezone(timedelta(hours=8))

    def at(hour: int, minute: int) -> datetime:
        return datetime(year, month, day, hour, minute, tzinfo=shanghai)

    def ceil_minute(value: datetime) -> datetime:
        value = value.astimezone(shanghai)
        rounded = value.replace(second=0, microsecond=0)
        return rounded if (value.second == 0 and value.microsecond == 0) else rounded + timedelta(minutes=1)

    morning_open = at(9, 31)
    morning_close = at(11, 30)
    afternoon_open = at(13, 0)
    market_close = at(15, 0)

    if raw_dt < morning_open:
        canonical = morning_open
        reason = "pre_open_to_0931"
    elif raw_dt <= morning_close:
        canonical = min(ceil_minute(raw_dt), morning_close)
        reason = "exact_minute_boundary" if raw_dt == canonical else "ceil_to_next_minute"
    elif raw_dt < afternoon_open:
        canonical = morning_close
        reason = "lunch_break_to_1130"
    elif raw_dt <= market_close:
        canonical = min(ceil_minute(raw_dt), market_close)
        reason = "exact_minute_boundary" if raw_dt == canonical else "ceil_to_next_minute"
    else:
        canonical = market_close
        reason = "post_close_to_1500"

    label = canonical.strftime("%H:%M")
    return {
        "raw_source_time": _format_shanghai_iso(raw_dt),
        "canonical_stock_quote_proof_minute": label,
        "canonical_stock_quote_proof_hhmm": label.replace(":", ""),
        "canonical_stock_quote_proof_time": _format_shanghai_iso(canonical),
        "stock_quote_time_mapping_policy": N3P_STOCK_QUOTE_CANONICAL_PROOF_MINUTE_POLICY,
        "stock_quote_time_mapping_reason": reason,
    }


def _market_datetime_from_value(value: Any, *, for_trade_date: str) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return _ensure_shanghai_tz(value)
    text = str(value)
    date_match = re.search(r"(\d{4})-?(\d{2})-?(\d{2})", text)
    time_match = re.search(r"(\d{1,2}):(\d{2})(?::(\d{2})(?:\.(\d{1,6}))?)?", text)
    if not time_match:
        return None
    if date_match:
        year, month, day = (int(part) for part in date_match.groups())
    else:
        trade_date = _normalize_trade_date(for_trade_date)
        if len(trade_date) != 8:
            return None
        year, month, day = int(trade_date[:4]), int(trade_date[4:6]), int(trade_date[6:8])
    hour = int(time_match.group(1))
    minute = int(time_match.group(2))
    second = int(time_match.group(3) or 0)
    micro_text = (time_match.group(4) or "").ljust(6, "0")
    microsecond = int(micro_text or 0)
    return datetime(year, month, day, hour, minute, second, microsecond, tzinfo=timezone(timedelta(hours=8)))


def _ensure_shanghai_tz(value: datetime) -> datetime:
    shanghai = timezone(timedelta(hours=8))
    return value.replace(tzinfo=shanghai) if value.tzinfo is None else value.astimezone(shanghai)


def _format_shanghai_iso(value: datetime) -> str:
    return _ensure_shanghai_tz(value).isoformat()


def _first_present(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _market_code_for_object(obj: Mapping[str, Any]) -> int | None:
    exchange = str(obj.get("exchange") or "")
    if exchange == "SH":
        return 1
    if exchange == "SZ":
        return 0
    return None


def _payload_hash(payload: Mapping[str, Any]) -> str:
    payload_for_hash = {
        "proof_input_time": payload.get("proof_input_time"),
        "stock_quote_rows": payload.get("stock_quote_rows") or [],
        "index_board_1m_rows": payload.get("index_board_1m_rows") or [],
    }
    encoded = json.dumps(payload_for_hash, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, default=str).encode("utf-8")


def compute_n3p_current_source_payload_hash(payload: Mapping[str, Any]) -> str:
    """Return the canonical hash over rows consumed by the N3P proof builder."""

    return _payload_hash(payload)


def _row_has_fake_marker(row: Mapping[str, Any]) -> bool:
    marker_values = [
        row.get("source_marker"),
        row.get("source_time_marker"),
        row.get("source_quality"),
        row.get("marker"),
    ]
    marker_text = " ".join(str(value).lower() for value in marker_values if value is not None)
    return any(token in marker_text for token in ("fake", "synthetic", "fabricated"))


def _row_minute_label(row: Mapping[str, Any]) -> str:
    raw = str(row.get("bar_time") or row.get("datetime") or row.get("minute_label") or row.get("time") or "")
    match = re.search(r"(\d{2}):(\d{2})", raw)
    return f"{match.group(1)}:{match.group(2)}" if match else raw[-5:]


def _row_trade_date(row: Mapping[str, Any], *, row_dt: datetime | None) -> str:
    explicit = row.get("trade_date")
    if explicit:
        return _normalize_trade_date(str(explicit))
    if row_dt is not None:
        return row_dt.strftime("%Y%m%d")
    raw = str(row.get("bar_time") or row.get("datetime") or "")
    match = re.match(r"(\d{4})-?(\d{2})-?(\d{2})", raw)
    return "".join(match.groups()) if match else ""


def _n3p_current_source_duplicate_equivalent(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    material_keys = (
        "asset_kind",
        "identity_key",
        "exchange",
        "code",
        "name",
        "bar_time",
        "datetime",
        "minute_label",
        "open",
        "high",
        "low",
        "close",
        "amount",
        "volume",
        "source_adapter_method",
        "source_frequency",
        "source_marker",
        "trade_date",
        "source_trade_date",
    )
    left_signature = {key: _json_stable_value(left.get(key)) for key in material_keys}
    right_signature = {key: _json_stable_value(right.get(key)) for key in material_keys}
    return left_signature == right_signature


def _json_stable_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _normalize_trade_date(value: str) -> str:
    digits = re.sub(r"\D", "", str(value))
    return digits[:8]


def _hhmm_from_time(value: str) -> str:
    match = re.search(r"(\d{2}):(\d{2})", value)
    return f"{match.group(1)}{match.group(2)}" if match else ""


def _parse_dt(value: str) -> datetime | None:
    text = str(value or "")
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y%m%d %H:%M:%S", "%Y%m%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _blocked(result: str, reason: str, **extra: Any) -> dict[str, Any]:
    normalized_reason = reason if reason.startswith(result) else f"{result}:{reason}"
    payload = {
        "result": result,
        "reason": normalized_reason,
        "execute_contract_ready": False,
        "real_io_operation_wired": True,
        "production_adapter_wired": True,
        "market_data_pulled": False,
        "database_written": False,
        "writes_n3p_metric_rows": False,
        "writes_outbox": False,
        "consumes_outbox": False,
        "updates_inbox_or_checkpoint": False,
        "starts_worker": False,
        "touches_n4_n5_n6": False,
        "touches_n5_n6": False,
    }
    payload.update(extra)
    _apply_forbidden_side_effect_guards(payload)
    return payload


def _project_default_dsn() -> str:
    try:
        from scripts.check_condition_source_ready import DEFAULT_DSN
    except ImportError:
        try:
            from check_condition_source_ready import DEFAULT_DSN
        except ImportError:
            return ""
    return str(DEFAULT_DSN or "")


def _connect_db(config: Mapping[str, Any]) -> Any:
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - environment dependency
        raise RuntimeError("psycopg is required for N3P scope DB loading") from exc

    database_url = str(config.get("database_url") or "")
    if database_url:
        return psycopg.connect(database_url)

    pg_database = str(config.get("pg_database") or "")
    if not pg_database:
        raise ValueError("database_url or pg_database is required for N3P scope DB loading")
    kwargs: dict[str, Any] = {"dbname": pg_database}
    if config.get("pg_host"):
        kwargs["host"] = str(config["pg_host"])
    if config.get("pg_user"):
        kwargs["user"] = str(config["pg_user"])
    if config.get("pg_port"):
        kwargs["port"] = str(config["pg_port"])
    return psycopg.connect(**kwargs)


def _fetchone(conn: Any, sql: str, params: Sequence[Any] = ()) -> Any:
    cursor = conn.execute(sql, params)
    return cursor.fetchone()


def _fetchall(conn: Any, sql: str, params: Sequence[Any] = ()) -> list[Any]:
    cursor = conn.execute(sql, params)
    return list(cursor.fetchall())


def _run_status(conn: Any, table_name: str, run_id: str) -> str:
    allowed_tables = {"common_market_data_run", "common_trigger_run"}
    if table_name not in allowed_tables:
        raise ValueError(f"unsupported run status table: {table_name}")
    row = _fetchone(conn, f"SELECT status FROM {table_name} WHERE run_id=%s", (run_id,))
    if not row:
        return ""
    return str(row[0] if not isinstance(row, Mapping) else row.get("status") or "")


def _derive_a1_preload_run_id(*, for_trade_date: str, prev_trade_date: str, subscription_run_id: str) -> str:
    return f"previous_day_minute_preload_{prev_trade_date}_for_{for_trade_date}__{subscription_run_id}"


def _context_rows(conn: Any, table_name: str, n4_context_run_id: str) -> list[dict[str, Any]]:
    allowed_tables = {
        "stock_trigger_context_snapshot",
        "index_trigger_context_snapshot",
        "board_trigger_context_snapshot",
    }
    if table_name not in allowed_tables:
        raise ValueError(f"unsupported context table: {table_name}")
    rows = _fetchall(
        conn,
        f"""
        SELECT
          trigger_context_id,
          asset_kind,
          identity_key,
          exchange,
          code,
          display_code,
          name,
          direction,
          condition_key,
          is_hint_scope,
          quality_status,
          source_condition_pool_id,
          source_minute_target_scope_id
        FROM {table_name}
        WHERE run_id=%s
        ORDER BY identity_key, trigger_context_id
        """,
        (n4_context_run_id,),
    )
    return [_context_row_dict(row) for row in rows]


def _context_row_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, Mapping):
        return {
            "trigger_context_id": row.get("trigger_context_id"),
            "asset_kind": row.get("asset_kind"),
            "identity_key": row.get("identity_key"),
            "exchange": row.get("exchange"),
            "code": row.get("code"),
            "display_code": row.get("display_code"),
            "name": row.get("name"),
            "direction": row.get("direction"),
            "condition_key": row.get("condition_key"),
            "is_hint_scope": bool(row.get("is_hint_scope")),
            "quality_status": row.get("quality_status"),
            "source_condition_pool_id": row.get("source_condition_pool_id"),
            "source_minute_target_scope_id": row.get("source_minute_target_scope_id"),
        }
    return {
        "trigger_context_id": row[0],
        "asset_kind": row[1],
        "identity_key": row[2],
        "exchange": row[3],
        "code": row[4],
        "display_code": row[5],
        "name": row[6],
        "direction": row[7],
        "condition_key": row[8],
        "is_hint_scope": bool(row[9]),
        "quality_status": row[10],
        "source_condition_pool_id": row[11],
        "source_minute_target_scope_id": row[12],
    }


def _dedupe_context_objects(rows: Sequence[Mapping[str, Any]], *, asset_kind: str) -> list[dict[str, Any]] | Mapping[str, Any]:
    objects_by_identity: dict[str, dict[str, Any]] = {}
    for row in rows:
        identity_key = str(row.get("identity_key") or "")
        if not identity_key:
            return _blocked(N3P_SOURCE_SCOPE_NOT_READY_BLOCKER, f"missing_identity_key:{asset_kind}")
        candidate = {
            "asset_kind": asset_kind,
            "identity_key": identity_key,
            "exchange": str(row.get("exchange") or ""),
            "code": str(row.get("code") or ""),
            "display_code": str(row.get("display_code") or row.get("code") or ""),
            "name": str(row.get("name") or ""),
        }
        existing = objects_by_identity.get(identity_key)
        if existing is not None and any(existing.get(field) != candidate.get(field) for field in candidate):
            return _blocked(
                N3P_SOURCE_SCOPE_NOT_READY_BLOCKER,
                f"duplicate_identity_ambiguity:{asset_kind}:{identity_key}",
            )
        objects_by_identity[identity_key] = candidate
    return [objects_by_identity[key] for key in sorted(objects_by_identity)]


def _cumulative_count(conn: Any, table_name: str, source_previous_day_minute_run_id: str) -> int:
    allowed_tables = {
        "stock_previous_day_minute_cumulative",
        "index_previous_day_minute_cumulative",
        "board_previous_day_minute_cumulative",
    }
    if table_name not in allowed_tables:
        raise ValueError(f"unsupported cumulative table: {table_name}")
    row = _fetchone(
        conn,
        f"SELECT count(*) FROM {table_name} WHERE source_previous_day_minute_run_id=%s",
        (source_previous_day_minute_run_id,),
    )
    if not row:
        return 0
    value = row[0] if not isinstance(row, Mapping) else row.get("count") or row.get("count(*)") or 0
    return int(value or 0)


def _is_blocked(payload: Mapping[str, Any]) -> bool:
    return str(payload.get("result", "")).startswith("BLOCKED")


def _dependency_method(dependencies: Any, dependency_name: str, method_name: str) -> Callable[..., Any] | None:
    dependency = getattr(dependencies, dependency_name, None)
    if dependency is None:
        return None
    method = getattr(dependency, method_name, None)
    if not callable(method):
        return None
    # Avoid recursing through the higher-level combined adapter/provider wrapper.
    if dependency.__class__.__name__ in {"N3ProductionRealIOAdapter", "N3PCurrentSourceFetchProvider"}:
        return None
    return method


def _component_callable(component: Any, method_name: str) -> Callable[..., Any] | None:
    if component is None:
        return None
    if callable(component):
        return component
    method = getattr(component, method_name, None)
    return method if callable(method) else None


def _call_with_supported_kwargs(callback: Callable[..., Any], **kwargs: Any) -> Any:
    try:
        signature = inspect.signature(callback)
    except (TypeError, ValueError):
        return callback(**kwargs)
    if any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values()):
        return callback(**kwargs)
    supported = {key: value for key, value in kwargs.items() if key in signature.parameters}
    return callback(**supported)


def _apply_forbidden_side_effect_guards(payload: dict[str, Any]) -> None:
    payload["writes_outbox"] = False
    payload["consumes_outbox"] = False
    payload["updates_inbox_or_checkpoint"] = False
    payload["starts_worker"] = False
    payload["touches_n4_n5_n6"] = False
    payload["touches_n5_n6"] = False
    side_effects = dict(payload.get("side_effects") or {})
    side_effects.update(_FORBIDDEN_SIDE_EFFECTS)
    side_effects["database_written"] = False
    side_effects["market_data_pulled"] = False
    payload["side_effects"] = side_effects
