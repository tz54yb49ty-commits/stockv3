"""Pure N6 AI-agent contracts, validation, and one-shot orchestration.

The model never receives a database connection and never chooses account,
principal, trade date, price, or quantity.  Persistence is available only
through reviewed SECURITY DEFINER functions exposed by ``AIAgentRepository``.
This module imports no N1-N5 runtime module and owns no network client.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import stat
from typing import Any, Protocol
from zoneinfo import ZoneInfo


DISPLAY_TIMEZONE = ZoneInfo("Asia/Shanghai")
CONTRACT_VERSION = "n6_ai_agent_v1"
KNOWLEDGE_BUNDLE_VERSION = "n6_ai_agent_knowledge_v1"
RISK_POLICY_VERSION = "n6_ai_agent_conservative_risk_v1"
SHADOW_FEATURE_FLAG = "ASHARE_V3_N6_AI_AGENT_SHADOW_ENABLED"
AUTONOMOUS_FEATURE_FLAG = "ASHARE_V3_N6_AI_AGENT_AUTONOMOUS_ENABLED"
DAILY_SUMMARY_FEATURE_FLAG = "ASHARE_V3_N6_AI_DAILY_SUMMARY_ENABLED"
PRODUCTION_KNOWLEDGE_MANIFEST_FILE_ENV = (
    "ASHARE_V3_N6_AI_PRODUCTION_KNOWLEDGE_MANIFEST_FILE"
)
PRODUCTION_KNOWLEDGE_MANIFEST_SHA256_ENV = (
    "ASHARE_V3_N6_AI_PRODUCTION_KNOWLEDGE_MANIFEST_SHA256"
)
AI_AGENT_SERVICE = "n6_ai_agent"
ALLOWED_LIBPQ_ENV = frozenset({"PGSERVICE", "PGSERVICEFILE", "PGPASSFILE"})
FORBIDDEN_CONNECTION_ENV = frozenset(
    {
        "DATABASE_URL",
        "PGPASSWORD",
        "PG_DSN",
        "POSTGRES_DSN",
        "ASHARE_V3_POSTGRES_DSN",
        "ASHARE_V3_N6_AI_AGENT_DSN",
        "ASHARE_V3_N6_AI_AGENT_PASSWORD",
    }
)
MAX_CONTEXT_SIGNALS = 1000
MAX_REASON_LENGTH = 1000
MAX_NOTES_LENGTH = 2000
MAX_EVIDENCE_ITEMS = 20
MAX_EVIDENCE_ITEM_LENGTH = 300
SHADOW_SCHEDULE_POLICY_VERSION = (
    "n6_ai_shadow_open_trade_date_nine_slots_071_v1"
)
SHADOW_SCHEDULE_SLOTS = (
    (9, 30, "09:30", 5),
    (10, 0, "10:00", 5),
    (10, 30, "10:30", 5),
    (11, 0, "11:00", 5),
    (11, 30, "11:30", 1),
    (13, 30, "13:30", 5),
    (14, 0, "14:00", 5),
    (14, 30, "14:30", 5),
    (15, 0, "15:00", 1),
)

KNOWLEDGE_BUNDLE: Mapping[str, Any] = {
    "contract_version": CONTRACT_VERSION,
    "allowed_sources": (
        "sanitized_n6_ai_shared_signal_projection",
        "ai_owned_virtual_account",
        "ai_owned_virtual_position",
        "approved_n6_virtual_quote_projection",
    ),
    "forbidden_sources": (
        "n1_raw_fact",
        "n2_n5_bare_table",
        "raw_k",
        "direct_live_market_provider",
        "human_session",
        "human_private_scope",
        "broker_account",
        "broker_credential",
        "real_trade_api",
    ),
    "stock_rules": {
        "exchanges": ("SH", "SZ"),
        "buy_source": "current_trade_date_n6_stock_buy_signal",
        "sell_sources": (
            "current_trade_date_n6_stock_sell_signal_with_open_position",
            "ai_owned_position_portfolio_risk",
            "ai_owned_position_stop_loss",
        ),
        "t_plus_one": True,
        "lot_size": 100,
        "price_owner": "fresh_n3n6q_quote_at_executor",
        "quantity_owner": "deterministic_n6_virtual_executor",
    },
    "risk_policy": {
        "buy_budget_cny": "300000",
        "max_identity_exposure_cny": "600000",
        "max_total_exposure_ratio": "0.10",
        "max_daily_new_buys": 10,
        "canary_trade_days": 3,
        "canary_daily_new_buys": 1,
        "pause_drawdown_pct": "5",
    },
    "evolution": {
        "self_modify_runtime": False,
        "candidate_only": True,
        "minimum_shadow_trade_days": 10,
        "admin_promotion_required": True,
    },
}


def canonical_json_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(payload).hexdigest()


KNOWLEDGE_BUNDLE_SHA256 = canonical_json_hash(KNOWLEDGE_BUNDLE)
CONTEXT_KNOWLEDGE_BUNDLE_SHA256 = (
    "1a873d69ef8f14e329b744460d549bcb3c35d99bb6af5fd10c16fc1a9dda15bc"
)
PRODUCTION_KNOWLEDGE_MANIFEST_FILE_SHA256 = (
    "3621e98fb979462d28c976ba8a2e9644e217498861473e223d134455bd70c09f"
)

_IDENTITY_RE = re.compile(r"^stock:(SH|SZ):[0-9]{6}$")
_MARKET_CONTEXT_IDENTITY_RE = re.compile(
    r"^(?:index:(?:SH|SZ):[0-9]{6}|board:TDX:[0-9]{6})$"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_DATE_RE = re.compile(r"^[0-9]{8}$")
_MODEL_OUTPUT_FIELDS = frozenset(
    {
        "decision_type",
        "identity_key",
        "source_signal_projection_id",
        "source_virtual_position_id",
        "confidence",
        "reason_summary",
        "evidence",
        "counter_evidence",
        "risk_assessment",
        "strategy_candidate_notes",
    }
)
_RISK_ASSESSMENT_FIELDS = frozenset({"trigger", "level", "summary"})
_FORBIDDEN_MODEL_KEYS = frozenset(
    {
        "price",
        "action_price",
        "trigger_price",
        "fill_price",
        "quote_price",
        "quantity",
        "order_quantity",
        "account",
        "account_id",
        "virtual_account_id",
        "trade_date",
        "for_trade_date",
        "principal",
        "principal_id",
        "principal_type",
        "user_id",
        "ai_user_id",
    }
)


class ModelAdapter(Protocol):
    """A model adapter returns one strictly structured decision mapping."""

    adapter_name: str
    model_version: str

    def generate_decision(
        self, context: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        ...


class _ModelRequestGateClosed(RuntimeError):
    """Private runner signal: no provider request was initiated."""


class AIAgentRepository(Protocol):
    """Function-only persistence boundary for the AI agent."""

    def shadow_schedule_preflight(
        self, *, run_bucket: str, for_trade_date: date
    ) -> Mapping[str, Any]:
        ...

    def load_context(
        self, *, run_bucket: str, for_trade_date: date, max_signals: int
    ) -> Mapping[str, Any]:
        ...

    def record_shadow_decision(
        self, payload: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        ...

    def record_shadow_observation(
        self, payload: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        ...

    def record_shadow_decision_with_observation(
        self,
        decision_payload: Mapping[str, Any],
        observation_payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        ...

    def create_confirmed_proposal(
        self, payload: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        ...

    def record_daily_summary(
        self, payload: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        ...

    def record_strategy_evaluation(
        self, payload: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        ...


class FunctionConnection(Protocol):
    def cursor(self): ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


CONTEXT_LOAD_SQL = (
    "SELECT public.n6_ai_agent_context_load_v2(%s, %s, %s, %s) AS result"
)
SHADOW_SCHEDULE_PREFLIGHT_SQL = (
    "SELECT public.n6_ai_agent_shadow_schedule_preflight(%s, %s) AS result"
)
DECISION_RECORD_SQL = (
    "SELECT public.n6_ai_agent_shadow_decision_record(%s::jsonb) AS result"
)
OBSERVATION_AUDIT_RECORD_SQL = (
    "SELECT public.n6_ai_shadow_observation_run_audit_record"
    "(%s::jsonb) AS result"
)
PROPOSAL_CREATE_SQL = (
    "SELECT public.n6_ai_agent_proposal_create_confirm(%s::jsonb) AS result"
)
DAILY_SUMMARY_RECORD_SQL = (
    "SELECT public.n6_ai_agent_daily_summary_record(%s::jsonb) AS result"
)
STRATEGY_EVALUATION_RECORD_SQL = (
    "SELECT public.n6_ai_agent_strategy_evaluation_record(%s::jsonb) AS result"
)


def _function_result(row: object) -> dict[str, Any]:
    if row is None:
        raise RuntimeError("ai_agent_function_returned_no_row")
    value = row["result"] if isinstance(row, Mapping) else row[0]
    if not isinstance(value, Mapping):
        raise RuntimeError("ai_agent_function_returned_invalid_payload")
    return dict(value)


class FunctionOnlyAIAgentRepository:
    """Calls fixed reviewed functions and contains no table-level SQL."""

    def __init__(self, connection: FunctionConnection) -> None:
        self._connection = connection

    def _call(
        self, sql: str, params: tuple[object, ...]
    ) -> dict[str, Any]:
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(sql, params)
                result = _function_result(cursor.fetchone())
            if result.get("ok") is True:
                self._connection.commit()
            else:
                self._connection.rollback()
            return result
        except Exception:
            self._connection.rollback()
            raise

    def load_context(
        self, *, run_bucket: str, for_trade_date: date, max_signals: int
    ) -> Mapping[str, Any]:
        return self._call(
            CONTEXT_LOAD_SQL,
            (
                run_bucket,
                for_trade_date,
                max_signals,
                CONTEXT_KNOWLEDGE_BUNDLE_SHA256,
            ),
        )

    def shadow_schedule_preflight(
        self, *, run_bucket: str, for_trade_date: date
    ) -> Mapping[str, Any]:
        return self._call(
            SHADOW_SCHEDULE_PREFLIGHT_SQL,
            (run_bucket, for_trade_date),
        )

    def record_shadow_decision(
        self, payload: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        return self._call(
            DECISION_RECORD_SQL, (_json_payload(payload),)
        )

    def record_shadow_observation(
        self, payload: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        return self._call(
            OBSERVATION_AUDIT_RECORD_SQL, (_json_payload(payload),)
        )

    def record_shadow_decision_with_observation(
        self,
        decision_payload: Mapping[str, Any],
        observation_payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Commit the 061 decision only when its 062 audit also succeeds."""
        decision_execute_started = False
        observation_execute_started = False
        try:
            with self._connection.cursor() as cursor:
                serialized_decision = _json_payload(decision_payload)
                decision_execute_started = True
                cursor.execute(
                    DECISION_RECORD_SQL,
                    (serialized_decision,),
                )
                decision = _function_result(cursor.fetchone())
                if decision.get("ok") is not True:
                    self._connection.rollback()
                    return {
                        "ok": False,
                        "status": "decision_record_rejected",
                        "observation_audit_attempted": False,
                        "observation_audit_followup_required": True,
                    }
                decision_id = decision.get("decision_id")
                server_risk_allowed = decision.get(
                    "server_risk_allowed"
                )
                server_risk_reason = decision.get(
                    "server_risk_reason"
                )
                if (
                    isinstance(decision_id, bool)
                    or not isinstance(decision_id, int)
                    or decision_id <= 0
                    or not isinstance(server_risk_allowed, bool)
                    or not isinstance(server_risk_reason, str)
                    or not re.fullmatch(
                        r"[a-z][a-z0-9_]{0,127}",
                        server_risk_reason,
                    )
                ):
                    raise RuntimeError(
                        "decision_record_authority_invalid"
                    )
                audit_payload = dict(observation_payload)
                if any(
                    key in audit_payload
                    for key in (
                        "decision_run_id",
                        "decision_id",
                        "server_risk_allowed",
                        "server_risk_reason",
                    )
                ):
                    raise RuntimeError(
                        "observation_decision_authority_polluted"
                    )
                audit_payload.update(
                    {
                        "decision_id": decision_id,
                        "server_risk_allowed": server_risk_allowed,
                        "server_risk_reason": server_risk_reason,
                    }
                )
                serialized_observation = _json_payload(audit_payload)
                observation_execute_started = True
                cursor.execute(
                    OBSERVATION_AUDIT_RECORD_SQL,
                    (serialized_observation,),
                )
                audit = _function_result(cursor.fetchone())
                if audit.get("ok") is not True:
                    self._connection.rollback()
                    return {
                        "ok": False,
                        "status": "observation_audit_rejected",
                        "observation_audit_attempted": True,
                    }
                audit_id = audit.get("audit_id")
                if (
                    isinstance(audit_id, bool)
                    or not isinstance(audit_id, int)
                    or audit_id <= 0
                ):
                    raise RuntimeError(
                        "observation_audit_authority_invalid"
                    )
            self._connection.commit()
            return {
                **decision,
                "observation_audit_attempted": True,
                "observation_audit_recorded": True,
            }
        except Exception:
            self._connection.rollback()
            if observation_execute_started:
                return {
                    "ok": False,
                    "status": "observation_audit_rejected",
                    "observation_audit_attempted": True,
                }
            if decision_execute_started:
                return {
                    "ok": False,
                    "status": "decision_record_rejected",
                    "observation_audit_attempted": False,
                    "observation_audit_followup_required": True,
                }
            raise

    def create_confirmed_proposal(
        self, payload: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        return self._call(
            PROPOSAL_CREATE_SQL, (_json_payload(payload),)
        )

    def record_daily_summary(
        self, payload: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        return self._call(
            DAILY_SUMMARY_RECORD_SQL, (_json_payload(payload),)
        )

    def record_strategy_evaluation(
        self, payload: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        return self._call(
            STRATEGY_EVALUATION_RECORD_SQL, (_json_payload(payload),)
        )


@dataclass(frozen=True, slots=True)
class ConservativeRiskPolicy:
    buy_budget_cny: Decimal = Decimal("300000")
    max_identity_exposure_cny: Decimal = Decimal("600000")
    max_total_exposure_ratio: Decimal = Decimal("0.10")
    max_daily_new_buys: int = 10
    canary_trade_days: int = 3
    canary_daily_new_buys: int = 1
    pause_drawdown_pct: Decimal = Decimal("5")


@dataclass(frozen=True, slots=True)
class ValidatedContext:
    context_snapshot_id: int
    decision_input_hash: str
    knowledge_bundle_hash: str
    universe_snapshot_hash: str
    memory_snapshot_hash: str
    workset_hash: str
    for_trade_date: str
    signals: tuple[dict[str, Any], ...]
    market_context: tuple[dict[str, Any], ...]
    positions: tuple[dict[str, Any], ...]
    portfolio: dict[str, Any]
    strategy_id: int
    strategy_version: str
    strategy_hash: str
    daily_metrics: dict[str, Any]

    def model_payload(self) -> dict[str, Any]:
        """Return only approved facts; authority/account identifiers stay server-side."""
        return {
            "contract_version": CONTRACT_VERSION,
            "knowledge_bundle_version": KNOWLEDGE_BUNDLE_VERSION,
            "knowledge_bundle_hash": self.knowledge_bundle_hash,
            "universe_snapshot_hash": self.universe_snapshot_hash,
            "memory_snapshot_hash": self.memory_snapshot_hash,
            "workset_hash": self.workset_hash,
            "for_trade_date": self.for_trade_date,
            "signals": [dict(item) for item in self.signals],
            "market_context": [
                dict(item) for item in self.market_context
            ],
            "positions": [dict(item) for item in self.positions],
            "portfolio": dict(self.portfolio),
            "strategy": {
                "strategy_version": self.strategy_version,
                "strategy_hash": self.strategy_hash,
            },
            "decision_rules": KNOWLEDGE_BUNDLE["stock_rules"],
            "risk_limits": KNOWLEDGE_BUNDLE["risk_policy"],
        }


@dataclass(frozen=True, slots=True)
class ValidatedDecision:
    decision_type: str
    identity_key: str | None
    source_signal_projection_id: int | None
    source_virtual_position_id: int | None
    confidence: Decimal
    reason_summary: str
    evidence: tuple[str, ...]
    counter_evidence: tuple[str, ...]
    risk_assessment: dict[str, str]
    strategy_candidate_notes: str | None


@dataclass(frozen=True, slots=True)
class RiskPolicyResult:
    allowed: bool
    reason: str


class DisabledModelAdapter:
    adapter_name = "disabled"
    model_version = "none"

    def generate_decision(
        self, context: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        del context
        raise RuntimeError("model_adapter_not_configured")


def feature_enabled(
    environ: Mapping[str, str], feature_name: str
) -> bool:
    return str(environ.get(feature_name) or "") == "1"


def validate_agent_environment(environ: Mapping[str, str]) -> None:
    """Accept only service-file based libpq configuration."""
    if environ.get("PGSERVICE") != AI_AGENT_SERVICE:
        raise ValueError("exact_PGSERVICE_n6_ai_agent_required")
    for key in environ:
        upper = key.upper()
        if (
            key in FORBIDDEN_CONNECTION_ENV
            or "DSN" in upper
            or "PASSWORD" in upper
            or upper.endswith("DATABASE_URL")
        ):
            raise ValueError("dsn_or_password_environment_not_allowed")
        if upper.startswith("PG") and upper not in ALLOWED_LIBPQ_ENV:
            raise ValueError("libpq_environment_override_not_allowed")
    for key in ("PGSERVICEFILE", "PGPASSFILE"):
        value = str(environ.get(key) or "")
        if (
            not value
            or not Path(value).is_absolute()
            or any(char in value for char in "\x00\r\n")
        ):
            raise ValueError(f"valid_{key}_path_required")


def load_production_knowledge_manifest(
    environ: Mapping[str, str],
) -> Mapping[str, Any]:
    """Load one exact immutable production knowledge manifest."""
    raw_path = str(
        environ.get(PRODUCTION_KNOWLEDGE_MANIFEST_FILE_ENV) or ""
    )
    expected_file_hash = str(
        environ.get(PRODUCTION_KNOWLEDGE_MANIFEST_SHA256_ENV) or ""
    )
    if (
        not raw_path
        or not Path(raw_path).is_absolute()
        or any(char in raw_path for char in "\x00\r\n")
        or expected_file_hash
        != PRODUCTION_KNOWLEDGE_MANIFEST_FILE_SHA256
    ):
        raise ValueError("production_knowledge_manifest_config_invalid")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(raw_path, flags)
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
            or metadata.st_size <= 0
            or metadata.st_size > 1_000_000
        ):
            raise ValueError(
                "production_knowledge_manifest_file_invalid"
            )
        chunks = []
        remaining = metadata.st_size + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
    finally:
        os.close(descriptor)
    if (
        len(raw) != metadata.st_size
        or sha256(raw).hexdigest() != expected_file_hash
    ):
        raise ValueError("production_knowledge_manifest_hash_mismatch")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            "production_knowledge_manifest_json_invalid"
        ) from exc
    if not isinstance(payload, Mapping):
        raise ValueError("production_knowledge_manifest_payload_invalid")
    bundle_hash = str(payload.get("bundle_sha256") or "")
    without_hash = {
        key: value
        for key, value in payload.items()
        if key not in {"bundle_sha256", "activation_contract"}
    }
    if (
        bundle_hash != CONTEXT_KNOWLEDGE_BUNDLE_SHA256
        or canonical_json_hash(without_hash) != bundle_hash
        or payload.get("production_agent_usable") is not True
        or payload.get("autonomous_trading_usable") is not False
        or payload.get("highest_schema_migration") != "058"
        or payload.get("planned_schema_migrations") != []
        or payload.get("unresolved_production_field_count") != 0
        or payload.get("production_field_count") != 194
    ):
        raise ValueError(
            "production_knowledge_manifest_authority_invalid"
        )
    return payload


def five_minute_bucket(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone_aware_run_time_required")
    local = value.astimezone(DISPLAY_TIMEZONE)
    bucket = local.replace(
        minute=local.minute - local.minute % 5,
        second=0,
        microsecond=0,
    )
    return bucket.strftime("%Y%m%dT%H%M%z")


def shadow_schedule_slot(value: datetime) -> str | None:
    """Return the reviewed Shadow slot for Shanghai local time."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone_aware_run_time_required")
    local = value.astimezone(DISPLAY_TIMEZONE)
    if local.weekday() >= 5:
        return None
    minute_of_day = local.hour * 60 + local.minute
    for hour, minute, label, window_minutes in SHADOW_SCHEDULE_SLOTS:
        slot_start = hour * 60 + minute
        if (
            slot_start
            <= minute_of_day
            < slot_start + window_minutes
        ):
            return label
    return None


def validate_context(
    payload: Mapping[str, Any], *, current_trade_date: date
) -> ValidatedContext:
    if payload.get("ok") is not True or payload.get("status") != "ready":
        raise ValueError("context_not_ready")
    snapshot_id = _positive_int(
        payload.get("context_snapshot_id"), "invalid_context_snapshot_id"
    )
    decision_input_hash = str(payload.get("decision_input_hash") or "")
    if not _SHA256_RE.fullmatch(decision_input_hash):
        raise ValueError("invalid_decision_input_hash")
    knowledge_bundle_hash = str(payload.get("knowledge_bundle_hash") or "")
    if knowledge_bundle_hash != CONTEXT_KNOWLEDGE_BUNDLE_SHA256:
        raise ValueError("invalid_context_knowledge_bundle_hash")
    context_hashes: dict[str, str] = {}
    for field_name in (
        "universe_snapshot_hash",
        "memory_snapshot_hash",
        "workset_hash",
    ):
        field_value = str(payload.get(field_name) or "")
        if not _SHA256_RE.fullmatch(field_value):
            raise ValueError(f"invalid_{field_name}")
        context_hashes[field_name] = field_value
    expected_date = current_trade_date.strftime("%Y%m%d")
    trade_date = _trade_date_text(payload.get("for_trade_date"))
    if trade_date != expected_date:
        raise ValueError("historical_or_future_context_rejected")

    raw_signals = _mapping_sequence(payload.get("signals"), "invalid_signals")
    if len(raw_signals) > MAX_CONTEXT_SIGNALS:
        raise ValueError("signal_context_too_large")
    signals: list[dict[str, Any]] = []
    signal_ids: set[int] = set()
    for raw in raw_signals:
        projection_id = _positive_int(
            raw.get("user_signal_projection_id"),
            "invalid_signal_projection_id",
        )
        if projection_id in signal_ids:
            raise ValueError("duplicate_signal_projection_id")
        signal_ids.add(projection_id)
        identity_key = _stock_identity(raw.get("identity_key"))
        direction = str(raw.get("direction") or "")
        if (
            raw.get("asset_kind") != "stock"
            or direction not in {"buy", "sell"}
            or _trade_date_text(raw.get("for_trade_date")) != trade_date
            or raw.get("ai_eligible") is not True
        ):
            raise ValueError("unapproved_signal_in_context")
        signals.append(
            {
                "user_signal_projection_id": projection_id,
                "identity_key": identity_key,
                "direction": direction,
                "action_state": _bounded_optional_text(
                    raw.get("action_state"), 50
                ),
                "event_time": _bounded_optional_text(
                    raw.get("event_time"), 80
                ),
                "reason_fields": _safe_reason_fields(
                    raw.get("reason_fields")
                ),
            }
        )

    raw_market_context = _mapping_sequence(
        payload.get("market_context"), "invalid_market_context"
    )
    if len(raw_market_context) > MAX_CONTEXT_SIGNALS:
        raise ValueError("market_context_too_large")
    market_context: list[dict[str, Any]] = []
    market_projection_ids: set[int] = set()
    for raw in raw_market_context:
        projection_id = _positive_int(
            raw.get("user_signal_projection_id"),
            "invalid_market_context_projection_id",
        )
        if (
            projection_id in signal_ids
            or projection_id in market_projection_ids
        ):
            raise ValueError("duplicate_context_projection_id")
        market_projection_ids.add(projection_id)
        asset_kind = str(raw.get("asset_kind") or "")
        identity_key = str(raw.get("identity_key") or "")
        direction = str(raw.get("direction") or "")
        if (
            asset_kind not in {"index", "board"}
            or not _MARKET_CONTEXT_IDENTITY_RE.fullmatch(identity_key)
            or direction not in {"buy", "sell"}
            or _trade_date_text(raw.get("for_trade_date")) != trade_date
            or raw.get("context_only") is not True
        ):
            raise ValueError("unapproved_market_context")
        market_context.append(
            {
                "user_signal_projection_id": projection_id,
                "asset_kind": asset_kind,
                "identity_key": identity_key,
                "direction": direction,
                "context_only": True,
                "action_state": _bounded_optional_text(
                    raw.get("action_state"), 50
                ),
                "event_time": _bounded_optional_text(
                    raw.get("event_time"), 80
                ),
                "reason_fields": _safe_reason_fields(
                    raw.get("reason_fields")
                ),
            }
        )

    raw_positions = _mapping_sequence(
        payload.get("positions"), "invalid_positions"
    )
    if len(raw_positions) > 10000:
        raise ValueError("position_context_too_large")
    positions: list[dict[str, Any]] = []
    position_ids: set[int] = set()
    for raw in raw_positions:
        position_id = _positive_int(
            raw.get("virtual_position_id"), "invalid_virtual_position_id"
        )
        if position_id in position_ids:
            raise ValueError("duplicate_virtual_position_id")
        position_ids.add(position_id)
        identity_key = _stock_identity(raw.get("identity_key"))
        quantity = _nonnegative_decimal(
            raw.get("quantity"), "invalid_position_quantity"
        )
        available = _nonnegative_decimal(
            raw.get("available_quantity"),
            "invalid_position_available_quantity",
        )
        current_price = _nonnegative_decimal(
            raw.get("current_price"),
            "invalid_position_current_price",
        )
        market_value = _nonnegative_decimal(
            raw.get("market_value"),
            "invalid_position_market_value",
        )
        if (
            raw.get("asset_kind") != "stock"
            or raw.get("position_status") != "open_virtual"
            or raw.get("quote_quality_status") != "passed"
            or quantity <= 0
            or current_price <= 0
            or available > quantity
            or market_value != quantity * current_price
        ):
            raise ValueError("unapproved_position_in_context")
        positions.append(
            {
                "virtual_position_id": position_id,
                "identity_key": identity_key,
                "quantity": str(quantity),
                "available_quantity": str(available),
                "current_price": str(current_price),
                "quote_minute": _bounded_text(
                    raw.get("quote_minute"),
                    "invalid_position_quote_minute",
                    80,
                ),
                "quote_quality_status": "passed",
                "market_value": str(market_value),
                "stop_loss_status": _bounded_optional_text(
                    raw.get("stop_loss_status"), 50
                ),
            }
        )

    portfolio_raw = payload.get("portfolio")
    if not isinstance(portfolio_raw, Mapping):
        raise ValueError("invalid_portfolio")
    portfolio = {
        "cash_balance": str(
            _nonnegative_decimal(
                portfolio_raw.get("cash_balance"),
                "invalid_cash_balance",
            )
        ),
        "total_equity": str(
            _nonnegative_decimal(
                portfolio_raw.get("total_equity"),
                "invalid_total_equity",
            )
        ),
        "market_value": str(
            _nonnegative_decimal(
                portfolio_raw.get("market_value"),
                "invalid_market_value",
            )
        ),
        "max_drawdown_pct": str(
            _nonnegative_decimal(
                portfolio_raw.get("max_drawdown_pct", "0"),
                "invalid_max_drawdown_pct",
            )
        ),
        "daily_new_buy_count": _nonnegative_int(
            portfolio_raw.get("daily_new_buy_count", 0),
            "invalid_daily_new_buy_count",
        ),
        "autonomous_trade_day_no": _nonnegative_int(
            portfolio_raw.get("autonomous_trade_day_no", 0),
            "invalid_autonomous_trade_day_no",
        ),
    }

    strategy_raw = payload.get("strategy")
    if not isinstance(strategy_raw, Mapping):
        raise ValueError("invalid_strategy")
    strategy_id = _positive_int(
        strategy_raw.get("strategy_id"), "invalid_strategy_id"
    )
    strategy_version = _bounded_text(
        strategy_raw.get("strategy_version"),
        "invalid_strategy_version",
        200,
    )
    strategy_hash = str(strategy_raw.get("strategy_hash") or "")
    if not _SHA256_RE.fullmatch(strategy_hash):
        raise ValueError("invalid_strategy_hash")

    daily_metrics_raw = payload.get("daily_metrics", {})
    if not isinstance(daily_metrics_raw, Mapping):
        raise ValueError("invalid_daily_metrics")
    return ValidatedContext(
        context_snapshot_id=snapshot_id,
        decision_input_hash=decision_input_hash,
        knowledge_bundle_hash=knowledge_bundle_hash,
        universe_snapshot_hash=context_hashes["universe_snapshot_hash"],
        memory_snapshot_hash=context_hashes["memory_snapshot_hash"],
        workset_hash=context_hashes["workset_hash"],
        for_trade_date=trade_date,
        signals=tuple(signals),
        market_context=tuple(market_context),
        positions=tuple(positions),
        portfolio=portfolio,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        strategy_hash=strategy_hash,
        daily_metrics=dict(daily_metrics_raw),
    )


def validate_model_output(
    payload: Mapping[str, Any], *, context: ValidatedContext
) -> ValidatedDecision:
    if not isinstance(payload, Mapping):
        raise ValueError("model_output_must_be_object")
    keys = frozenset(str(key) for key in payload)
    if keys != _MODEL_OUTPUT_FIELDS:
        if keys & _FORBIDDEN_MODEL_KEYS:
            raise ValueError("model_output_contains_server_owned_field")
        raise ValueError("model_output_fields_invalid")
    _reject_forbidden_nested_keys(payload)

    decision_type = str(payload.get("decision_type") or "")
    if decision_type not in {"buy", "sell", "hold"}:
        raise ValueError("decision_type_invalid")
    identity_raw = payload.get("identity_key")
    identity_key = (
        None if identity_raw is None else _stock_identity(identity_raw)
    )
    signal_id = _optional_model_bigint(
        payload.get("source_signal_projection_id"),
        "invalid_source_signal_projection_id",
    )
    position_id = _optional_model_bigint(
        payload.get("source_virtual_position_id"),
        "invalid_source_virtual_position_id",
    )
    confidence = _finite_decimal(
        payload.get("confidence"), "invalid_confidence"
    )
    if confidence < 0 or confidence > 1:
        raise ValueError("invalid_confidence")
    reason_summary = _bounded_text(
        payload.get("reason_summary"),
        "invalid_reason_summary",
        MAX_REASON_LENGTH,
    )
    evidence = _text_items(payload.get("evidence"), "invalid_evidence")
    counter_evidence = _text_items(
        payload.get("counter_evidence"), "invalid_counter_evidence"
    )
    risk_raw = payload.get("risk_assessment")
    if not isinstance(risk_raw, Mapping) or frozenset(risk_raw) != _RISK_ASSESSMENT_FIELDS:
        raise ValueError("invalid_risk_assessment")
    trigger = str(risk_raw.get("trigger") or "")
    level = str(risk_raw.get("level") or "")
    if trigger not in {"signal", "portfolio_risk", "stop_loss", "none"}:
        raise ValueError("invalid_risk_trigger")
    if level not in {"low", "medium", "high", "critical"}:
        raise ValueError("invalid_risk_level")
    risk_assessment = {
        "trigger": trigger,
        "level": level,
        "summary": _bounded_text(
            risk_raw.get("summary"), "invalid_risk_summary", 500
        ),
    }
    notes = payload.get("strategy_candidate_notes")
    strategy_candidate_notes = (
        None
        if notes is None
        else _bounded_text(notes, "invalid_strategy_candidate_notes", MAX_NOTES_LENGTH)
    )
    if decision_type in {"buy", "sell"} and not evidence:
        raise ValueError("trade_decision_requires_evidence")

    signals = {
        int(item["user_signal_projection_id"]): item
        for item in context.signals
    }
    positions = {
        int(item["virtual_position_id"]): item
        for item in context.positions
    }
    signal = signals.get(signal_id) if signal_id is not None else None
    position = positions.get(position_id) if position_id is not None else None

    if decision_type == "hold":
        if identity_key is not None or signal_id is not None or position_id is not None:
            raise ValueError("hold_must_not_select_trade_scope")
        if trigger != "none":
            raise ValueError("hold_risk_trigger_must_be_none")
    elif identity_key is None:
        raise ValueError("trade_identity_required")
    elif decision_type == "buy":
        if (
            signal is None
            or signal["identity_key"] != identity_key
            or signal["direction"] != "buy"
            or position_id is not None
            or trigger != "signal"
        ):
            raise ValueError("buy_requires_current_stock_buy_signal")
    else:
        if (
            position is None
            or position["identity_key"] != identity_key
        ):
            raise ValueError("sell_requires_ai_owned_open_position")
        if trigger == "signal":
            if (
                signal is None
                or signal["identity_key"] != identity_key
                or signal["direction"] != "sell"
            ):
                raise ValueError("sell_signal_scope_invalid")
        elif trigger in {"portfolio_risk", "stop_loss"}:
            if signal_id is not None:
                raise ValueError("risk_sell_must_not_claim_signal")
        else:
            raise ValueError("sell_trigger_invalid")

    if (
        signal_id is not None
        and f"projection:{signal_id}" not in evidence
    ):
        raise ValueError("signal_evidence_reference_required")
    if (
        position_id is not None
        and f"position:{position_id}" not in evidence
    ):
        raise ValueError("position_evidence_reference_required")

    return ValidatedDecision(
        decision_type=decision_type,
        identity_key=identity_key,
        source_signal_projection_id=signal_id,
        source_virtual_position_id=position_id,
        confidence=confidence,
        reason_summary=reason_summary,
        evidence=evidence,
        counter_evidence=counter_evidence,
        risk_assessment=risk_assessment,
        strategy_candidate_notes=strategy_candidate_notes,
    )


def evaluate_conservative_risk(
    decision: ValidatedDecision,
    *,
    context: ValidatedContext,
    policy: ConservativeRiskPolicy = ConservativeRiskPolicy(),
) -> RiskPolicyResult:
    if decision.decision_type == "hold":
        return RiskPolicyResult(False, "hold_no_proposal")
    if decision.decision_type == "sell":
        position = next(
            (
                item
                for item in context.positions
                if item["virtual_position_id"]
                == decision.source_virtual_position_id
            ),
            None,
        )
        if position is None:
            return RiskPolicyResult(False, "position_not_found")
        if Decimal(str(position["available_quantity"])) <= 0:
            return RiskPolicyResult(False, "t1_available_quantity_not_sellable")
        return RiskPolicyResult(True, "sell_scope_ready")

    portfolio = context.portfolio
    drawdown = Decimal(str(portfolio["max_drawdown_pct"]))
    if drawdown >= policy.pause_drawdown_pct:
        return RiskPolicyResult(False, "max_drawdown_pause")
    daily_buys = int(portfolio["daily_new_buy_count"])
    trade_day_no = int(portfolio["autonomous_trade_day_no"])
    daily_limit = (
        policy.max_daily_new_buys
        if trade_day_no >= policy.canary_trade_days
        else policy.canary_daily_new_buys
    )
    if daily_buys >= daily_limit:
        return RiskPolicyResult(False, "daily_buy_limit_reached")
    total_equity = Decimal(str(portfolio["total_equity"]))
    market_value = Decimal(str(portfolio["market_value"]))
    cash = Decimal(str(portfolio["cash_balance"]))
    if total_equity <= 0 or cash <= 0:
        return RiskPolicyResult(False, "account_not_funded")
    if (
        market_value + policy.buy_budget_cny
        > total_equity * policy.max_total_exposure_ratio
    ):
        return RiskPolicyResult(False, "total_exposure_limit")
    identity_market_value = sum(
        (
            Decimal(str(item["market_value"]))
            for item in context.positions
            if item["identity_key"] == decision.identity_key
        ),
        Decimal("0"),
    )
    if (
        identity_market_value + policy.buy_budget_cny
        > policy.max_identity_exposure_cny
    ):
        return RiskPolicyResult(False, "identity_exposure_limit")
    return RiskPolicyResult(True, "buy_scope_ready")


def run_agent_once(
    *,
    repository: AIAgentRepository,
    model_adapter: ModelAdapter,
    now: datetime,
    requested_mode: str = "shadow",
    shadow_enabled: bool = False,
    autonomous_enabled: bool = False,
    max_signals: int = MAX_CONTEXT_SIGNALS,
    risk_policy: ConservativeRiskPolicy = ConservativeRiskPolicy(),
    observation_audit_factory: (
        Callable[[Mapping[str, Any]], Mapping[str, Any]] | None
    ) = None,
) -> dict[str, Any]:
    """Run one bucket.  Any invalid input or exception produces no proposal."""
    if requested_mode not in {"shadow", "autonomous"}:
        return _failed("invalid_agent_mode")
    if not shadow_enabled:
        return _disabled("shadow_feature_disabled")
    if requested_mode == "autonomous" and not autonomous_enabled:
        return _disabled("autonomous_feature_disabled")
    if (
        isinstance(max_signals, bool)
        or not isinstance(max_signals, int)
        or max_signals != MAX_CONTEXT_SIGNALS
    ):
        return _failed("invalid_max_signals")
    try:
        run_bucket = five_minute_bucket(now)
    except (TypeError, ValueError):
        return _failed("invalid_run_time")
    trade_date = now.astimezone(DISPLAY_TIMEZONE).date()
    try:
        raw_context = repository.load_context(
            run_bucket=run_bucket,
            for_trade_date=trade_date,
            max_signals=max_signals,
        )
    except Exception:
        return _failed("context_service_unavailable", run_bucket=run_bucket)
    if not isinstance(raw_context, Mapping):
        return _failed("context_payload_invalid", run_bucket=run_bucket)
    context_status = str(
        raw_context.get("status") or "context_not_ready"
    )
    if context_status in {
        "already_processed",
        "no_new_input",
        "agent_disabled",
        "agent_drawdown_paused",
        "not_open_trade_date",
        "position_quote_not_ready",
    }:
        return {
            "ok": True,
            "status": context_status,
            "run_bucket": run_bucket,
            "model_called": False,
            "decision_recorded": False,
            "proposal_created": False,
        }
    if raw_context.get("ok") is not True:
        return _failed(
            "context_not_ready",
            run_bucket=run_bucket,
            model_called=False,
            decision_recorded=False,
        )
    if context_status == "signal_universe_too_large":
        return _failed(
            "signal_universe_too_large",
            run_bucket=run_bucket,
            model_called=False,
            decision_recorded=False,
        )
    if context_status != "ready":
        return _failed(
            "context_status_unrecognized",
            run_bucket=run_bucket,
            model_called=False,
            decision_recorded=False,
        )
    model_call_metadata: dict[str, Any] = {}
    decision_call_attempted = False
    structure_valid = False
    try:
        context = validate_context(
            raw_context, current_trade_date=trade_date
        )
        adapter_name = _bounded_text(
            model_adapter.adapter_name, "invalid_model_adapter_name", 100
        )
        model_version = _bounded_text(
            model_adapter.model_version, "invalid_model_version", 200
        )
        decision_call_attempted = True
        raw_decision = model_adapter.generate_decision(
            context.model_payload()
        )
        model_call_metadata = _safe_model_call_metadata(model_adapter)
        decision = validate_model_output(
            raw_decision, context=context
        )
        structure_valid = True
        risk = evaluate_conservative_risk(
            decision, context=context, policy=risk_policy
        )
    except _ModelRequestGateClosed:
        return _failed(
            "model_request_gate_closed",
            run_bucket=run_bucket,
            model_called=False,
            decision_recorded=False,
        )
    except Exception:
        if not model_call_metadata:
            model_call_metadata = _safe_model_call_metadata(model_adapter)
        return _failed(
            "model_or_decision_validation_failed",
            run_bucket=run_bucket,
            model_called=decision_call_attempted,
            **(
                {"structure_valid": structure_valid}
                if decision_call_attempted
                else {}
            ),
            **(
                {"model_call": model_call_metadata}
                if model_call_metadata
                else {}
            ),
        )
    model_call_fields = (
        {"model_call": model_call_metadata}
        if model_call_metadata
        else {}
    )

    idempotency_key = _decision_idempotency_key(
        run_bucket=run_bucket,
        context=context,
        decision=decision,
    )
    record_payload = _decision_record_payload(
        context=context,
        decision=decision,
        risk=risk,
        adapter_name=adapter_name,
        model_version=model_version,
        requested_mode=requested_mode,
        run_bucket=run_bucket,
        idempotency_key=idempotency_key,
    )
    try:
        observation_payload = (
            observation_audit_factory(
                {
                    "one_shot_status": "shadow_decision_recorded",
                    "decision_call_attempted": True,
                    "structure_valid": True,
                    "context_snapshot_id": context.context_snapshot_id,
                    "model_call": model_call_metadata,
                }
            )
            if observation_audit_factory is not None
            else None
        )
    except Exception:
        return _failed(
            "observation_audit_payload_invalid",
            run_bucket=run_bucket,
            model_called=True,
            observation_audit_skipped=True,
            **model_call_fields,
        )
    try:
        recorded = (
            repository.record_shadow_decision_with_observation(
                record_payload, observation_payload
            )
            if observation_payload is not None
            else repository.record_shadow_decision(record_payload)
        )
    except Exception:
        return _failed(
            (
                "observation_audit_service_unavailable"
                if observation_payload is not None
                else "decision_record_service_unavailable"
            ),
            run_bucket=run_bucket,
            model_called=True,
            observation_audit_skipped=(
                observation_payload is not None
            ),
            **model_call_fields,
        )
    if not isinstance(recorded, Mapping) or recorded.get("ok") is not True:
        audit_attempted = (
            isinstance(recorded, Mapping)
            and recorded.get("observation_audit_attempted") is True
        )
        audit_skipped = (
            isinstance(recorded, Mapping)
            and recorded.get("observation_audit_skipped") is True
        )
        audit_followup_required = (
            isinstance(recorded, Mapping)
            and recorded.get("observation_audit_followup_required")
            is True
        )
        return _failed(
            (
                "observation_audit_rejected"
                if isinstance(recorded, Mapping)
                and recorded.get("status")
                == "observation_audit_rejected"
                else "decision_record_rejected"
            ),
            run_bucket=run_bucket,
            model_called=True,
            structure_valid=True,
            observation_audit_attempted=audit_attempted,
            observation_audit_skipped=audit_skipped,
            observation_audit_followup_required=(
                audit_followup_required
            ),
            **model_call_fields,
        )
    decision_id = recorded.get("decision_id")
    if isinstance(decision_id, bool) or not isinstance(decision_id, int) or decision_id <= 0:
        return _failed(
            "decision_record_id_invalid",
            run_bucket=run_bucket,
            model_called=True,
            **model_call_fields,
        )
    server_risk_allowed = recorded.get("server_risk_allowed")
    if not isinstance(server_risk_allowed, bool):
        return _failed(
            "decision_record_risk_invalid",
            run_bucket=run_bucket,
            model_called=True,
            **model_call_fields,
        )
    try:
        server_risk_reason = _bounded_text(
            recorded.get("server_risk_reason"),
            "decision_record_risk_invalid",
            200,
        )
    except (TypeError, ValueError):
        return _failed(
            "decision_record_risk_invalid",
            run_bucket=run_bucket,
            model_called=True,
            **model_call_fields,
        )
    risk_allowed = server_risk_allowed and risk.allowed
    risk_reason = (
        server_risk_reason
        if not server_risk_allowed or risk.allowed
        else risk.reason
    )
    result: dict[str, Any] = {
        "ok": True,
        "status": "shadow_decision_recorded",
        "mode": requested_mode,
        "run_bucket": run_bucket,
        "decision_id": decision_id,
        "decision_type": decision.decision_type,
        "risk_allowed": risk_allowed,
        "risk_reason": risk_reason,
        "server_risk_allowed": server_risk_allowed,
        "server_risk_reason": server_risk_reason,
        "model_called": True,
        "decision_recorded": True,
        "proposal_created": False,
        **(
            {
                "observation_audit_attempted": True,
                "observation_audit_recorded": True,
            }
            if observation_payload is not None
            else {}
        ),
        **model_call_fields,
    }
    if (
        requested_mode != "autonomous"
        or not risk_allowed
        or decision.decision_type == "hold"
    ):
        return result
    try:
        proposal = repository.create_confirmed_proposal(
            {
                "decision_id": decision_id,
                "idempotency_key": idempotency_key,
            }
        )
    except Exception:
        return {
            **result,
            "ok": False,
            "status": "proposal_service_unavailable",
        }
    if not isinstance(proposal, Mapping) or proposal.get("ok") is not True:
        return {
            **result,
            "ok": False,
            "status": "proposal_rejected",
        }
    proposal_id = proposal.get("proposal_id")
    if isinstance(proposal_id, bool) or not isinstance(proposal_id, int) or proposal_id <= 0:
        return {
            **result,
            "ok": False,
            "status": "proposal_id_invalid",
        }
    return {
        **result,
        "status": "autonomous_proposal_confirmed",
        "proposal_created": True,
        "proposal_id": proposal_id,
    }


def risk_adjusted_score(
    *,
    net_return_pct: Any,
    max_drawdown_pct: Any,
    turnover_pct: Any,
) -> Decimal:
    net_return = _finite_decimal(net_return_pct, "invalid_net_return_pct")
    drawdown = _nonnegative_decimal(
        max_drawdown_pct, "invalid_max_drawdown_pct"
    )
    turnover = _nonnegative_decimal(turnover_pct, "invalid_turnover_pct")
    return (
        net_return
        - Decimal("1.5") * drawdown
        - Decimal("0.02") * turnover
    ).quantize(Decimal("0.000001"))


def run_daily_summary_once(
    *,
    repository: AIAgentRepository,
    now: datetime,
    for_trade_date: date | None = None,
    enabled: bool = False,
) -> dict[str, Any]:
    if not enabled:
        return _disabled("daily_summary_feature_disabled")
    if now.tzinfo is None or now.utcoffset() is None:
        return _failed("invalid_run_time")
    local_now = now.astimezone(DISPLAY_TIMEZONE)
    local_date = local_now.date()
    trade_date = for_trade_date or local_date
    if trade_date != local_date:
        return _failed("historical_or_future_summary_rejected")
    if (local_now.hour, local_now.minute) < (15, 15):
        return _failed("daily_summary_before_1515")
    run_bucket = f"daily:{trade_date.strftime('%Y%m%d')}"
    try:
        raw_context = repository.load_context(
            run_bucket=run_bucket,
            for_trade_date=trade_date,
            max_signals=MAX_CONTEXT_SIGNALS,
        )
    except Exception:
        return _failed("context_service_unavailable", run_bucket=run_bucket)
    if not isinstance(raw_context, Mapping):
        return _failed("context_not_ready", run_bucket=run_bucket)
    status = str(raw_context.get("status") or "")
    if status in {"already_processed", "no_new_input", "agent_disabled"}:
        return {
            "ok": True,
            "status": status,
            "run_bucket": run_bucket,
            "summary_recorded": False,
        }
    if raw_context.get("ok") is not True:
        return _failed("context_not_ready", run_bucket=run_bucket)
    try:
        context = validate_context(
            raw_context, current_trade_date=trade_date
        )
        summary_payload = _daily_summary_payload(
            context=context, run_bucket=run_bucket
        )
    except Exception:
        return _failed("daily_summary_context_invalid", run_bucket=run_bucket)
    try:
        result = repository.record_daily_summary(summary_payload)
    except Exception:
        return _failed(
            "daily_summary_service_unavailable", run_bucket=run_bucket
        )
    if not isinstance(result, Mapping) or result.get("ok") is not True:
        return _failed("daily_summary_rejected", run_bucket=run_bucket)
    summary_id = result.get("daily_summary_id")
    if isinstance(summary_id, bool) or not isinstance(summary_id, int) or summary_id <= 0:
        return _failed(
            "daily_summary_id_invalid", run_bucket=run_bucket
        )
    return {
        "ok": True,
        "status": "daily_summary_recorded",
        "run_bucket": run_bucket,
        "daily_summary_id": summary_id,
        "risk_adjusted_score": summary_payload["risk_adjusted_score"],
        "summary_recorded": True,
    }


def _decision_record_payload(
    *,
    context: ValidatedContext,
    decision: ValidatedDecision,
    risk: RiskPolicyResult,
    adapter_name: str,
    model_version: str,
    requested_mode: str,
    run_bucket: str,
    idempotency_key: str,
) -> dict[str, Any]:
    del risk
    normalized_decision = {
        "decision_type": decision.decision_type,
        "identity_key": decision.identity_key,
        "source_signal_projection_id":
            decision.source_signal_projection_id,
        "source_virtual_position_id":
            decision.source_virtual_position_id,
        "confidence": str(decision.confidence),
        "reason_summary": decision.reason_summary,
        "evidence": list(decision.evidence),
        "counter_evidence": list(decision.counter_evidence),
        "risk_assessment": dict(decision.risk_assessment),
        "strategy_candidate_notes": decision.strategy_candidate_notes,
    }
    return {
        "context_snapshot_id": context.context_snapshot_id,
        "run_bucket": run_bucket,
        "run_mode": (
            "autonomous_canary"
            if requested_mode == "autonomous"
            else "shadow"
        ),
        "model_adapter": adapter_name,
        "model_version": model_version,
        "strategy_id": context.strategy_id,
        "strategy_version": context.strategy_version,
        "strategy_hash": context.strategy_hash,
        "knowledge_bundle_version": KNOWLEDGE_BUNDLE_VERSION,
        "knowledge_bundle_hash": KNOWLEDGE_BUNDLE_SHA256,
        "input_payload_hash": context.decision_input_hash,
        **normalized_decision,
        "idempotency_key": idempotency_key,
    }


def _decision_idempotency_key(
    *,
    run_bucket: str,
    context: ValidatedContext,
    decision: ValidatedDecision,
) -> str:
    return canonical_json_hash(
        {
            "contract_version": CONTRACT_VERSION,
            "run_bucket": run_bucket,
            "context_snapshot_id": context.context_snapshot_id,
            "strategy_hash": context.strategy_hash,
            "knowledge_bundle_hash": KNOWLEDGE_BUNDLE_SHA256,
            "decision_type": decision.decision_type,
            "identity_key": decision.identity_key,
            "source_signal_projection_id":
                decision.source_signal_projection_id,
            "source_virtual_position_id":
                decision.source_virtual_position_id,
        }
    )


def _daily_summary_payload(
    *, context: ValidatedContext, run_bucket: str
) -> dict[str, Any]:
    metrics = context.daily_metrics
    net_return = _finite_decimal(
        metrics.get("net_return_pct"), "invalid_net_return_pct"
    )
    drawdown = _nonnegative_decimal(
        metrics.get("max_drawdown_pct"), "invalid_max_drawdown_pct"
    )
    turnover = _nonnegative_decimal(
        metrics.get("turnover_pct"), "invalid_turnover_pct"
    )
    score = risk_adjusted_score(
        net_return_pct=net_return,
        max_drawdown_pct=drawdown,
        turnover_pct=turnover,
    )
    buy_count = _nonnegative_int(
        metrics.get("buy_trade_count", 0), "invalid_buy_trade_count"
    )
    sell_count = _nonnegative_int(
        metrics.get("sell_trade_count", 0), "invalid_sell_trade_count"
    )
    decision_count = _nonnegative_int(
        metrics.get("decision_count", 0), "invalid_decision_count"
    )
    summary_text = (
        f"模拟账户当日净收益率 {net_return}%，最大回撤 {drawdown}%，"
        f"换手率 {turnover}%；记录 {decision_count} 个决策，"
        f"完成 {buy_count} 笔买入和 {sell_count} 笔卖出。"
    )
    highlights = _text_items(
        metrics.get("highlights", ()), "invalid_daily_highlights"
    )
    if not highlights:
        highlights = (
            f"当日记录 {decision_count} 个可审计决策，完成 "
            f"{buy_count + sell_count} 笔模拟成交。",
        )
    lessons = _text_items(
        metrics.get("lessons", ()), "invalid_daily_lessons"
    )
    if not lessons:
        lessons = (
            "继续以报价质量、T+1与组合风险门槛作为成交前置条件。",
        )
    next_day_watch = _text_items(
        metrics.get("next_day_watch", ()),
        "invalid_daily_next_day_watch",
    )
    if not next_day_watch:
        next_day_watch = tuple(
            f"继续关注持仓 {position['identity_key']} 的报价质量与止损状态。"
            for position in context.positions[:MAX_EVIDENCE_ITEMS]
        )
    if not next_day_watch:
        next_day_watch = ("等待下一交易日新的共享N6买入信号。",)
    return {
        "context_snapshot_id": context.context_snapshot_id,
        "for_trade_date": context.for_trade_date,
        "strategy_id": context.strategy_id,
        "strategy_version": context.strategy_version,
        "strategy_hash": context.strategy_hash,
        "knowledge_bundle_version": KNOWLEDGE_BUNDLE_VERSION,
        "knowledge_bundle_hash": KNOWLEDGE_BUNDLE_SHA256,
        "net_return_pct": str(net_return),
        "max_drawdown_pct": str(drawdown),
        "turnover_pct": str(turnover),
        "risk_adjusted_score": str(score),
        "decision_count": decision_count,
        "buy_trade_count": buy_count,
        "sell_trade_count": sell_count,
        "summary_text": summary_text,
        "highlights": highlights,
        "lessons": lessons,
        "next_day_watch": next_day_watch,
        "idempotency_key": canonical_json_hash(
            {
                "run_bucket": run_bucket,
                "context_snapshot_id": context.context_snapshot_id,
                "strategy_hash": context.strategy_hash,
                "knowledge_bundle_hash": KNOWLEDGE_BUNDLE_SHA256,
            }
        ),
    }


def _json_payload(payload: Mapping[str, Any]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _failed(
    reason: str, **fields: Any
) -> dict[str, Any]:
    return {
        "ok": False,
        "status": "failed_closed",
        "reason": reason,
        "proposal_created": False,
        **fields,
    }


def _safe_model_call_metadata(
    model_adapter: ModelAdapter,
) -> dict[str, Any]:
    raw = getattr(model_adapter, "last_call_metadata", None)
    if not isinstance(raw, Mapping):
        return {}
    result: dict[str, Any] = {}
    for key in ("provider", "model"):
        value = raw.get(key)
        if (
            isinstance(value, str)
            and 1 <= len(value) <= 200
            and value.isascii()
            and all(
                char.isalnum() or char in "._-"
                for char in value
            )
        ):
            result[key] = value
    for key in (
        "provider_request_id",
        "response_id",
        "system_fingerprint",
    ):
        value = raw.get(key)
        if (
            isinstance(value, str)
            and 1 <= len(value) <= 200
            and value.isascii()
            and all(
                char.isalnum() or char in "._:-"
                for char in value
            )
        ):
            result[key] = value
    for key in (
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "prompt_cache_hit_tokens",
        "prompt_cache_miss_tokens",
        "latency_ms",
    ):
        value = raw.get(key)
        if (
            isinstance(value, int)
            and not isinstance(value, bool)
            and 0 <= value <= 100_000_000
        ):
            result[key] = value
    return result


def _disabled(reason: str) -> dict[str, Any]:
    return {
        "ok": True,
        "status": "feature_disabled",
        "reason": reason,
        "model_called": False,
        "db_connected": False,
        "decision_recorded": False,
        "proposal_created": False,
    }


def _finite_decimal(value: Any, error: str) -> Decimal:
    if value is None or isinstance(value, bool):
        raise ValueError(error)
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(error) from exc
    if not result.is_finite():
        raise ValueError(error)
    return result


def _nonnegative_decimal(value: Any, error: str) -> Decimal:
    result = _finite_decimal(value, error)
    if result < 0:
        raise ValueError(error)
    return result


def _positive_int(value: Any, error: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(error)
    return value


def _nonnegative_int(value: Any, error: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(error)
    return value


def _optional_positive_int(value: Any, error: str) -> int | None:
    return None if value is None else _positive_int(value, error)


def _optional_model_bigint(value: Any, error: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(error)
    if isinstance(value, int):
        return _positive_int(value, error)
    if isinstance(value, str) and re.fullmatch(r"[1-9][0-9]*", value):
        return int(value)
    raise ValueError(error)


def _stock_identity(value: Any) -> str:
    result = str(value or "")
    if not _IDENTITY_RE.fullmatch(result):
        raise ValueError("invalid_stock_identity_key")
    return result


def _trade_date_text(value: Any) -> str:
    if isinstance(value, date):
        result = value.strftime("%Y%m%d")
    else:
        result = str(value or "").replace("-", "")
    if not _DATE_RE.fullmatch(result):
        raise ValueError("invalid_for_trade_date")
    return result


def _bounded_text(value: Any, error: str, limit: int) -> str:
    if not isinstance(value, str):
        raise ValueError(error)
    result = value.strip()
    if not result or len(result) > limit or any(char in result for char in "\x00"):
        raise ValueError(error)
    return result


def _bounded_optional_text(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    return _bounded_text(value, "invalid_optional_text", limit)


def _mapping_sequence(value: Any, error: str) -> tuple[Mapping[str, Any], ...]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
        or any(not isinstance(item, Mapping) for item in value)
    ):
        raise ValueError(error)
    return tuple(value)


def _text_items(value: Any, error: str) -> tuple[str, ...]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
        or len(value) > MAX_EVIDENCE_ITEMS
    ):
        raise ValueError(error)
    return tuple(
        _bounded_text(item, error, MAX_EVIDENCE_ITEM_LENGTH)
        for item in value
    )


def _safe_reason_fields(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("invalid_signal_reason_fields")
    allowed = {
        "condition_key",
        "primary_trigger_period",
        "all_trigger_periods",
        "score",
        "pe_core",
        "buy_expected_return_pct",
        "sell_expected_return_pct",
        "action_state",
        "action_mark",
    }
    if any(str(key) not in allowed for key in value):
        raise ValueError("unapproved_signal_reason_field")
    result: dict[str, Any] = {}
    for key, item in value.items():
        if item is None or isinstance(item, str):
            result[str(key)] = item
        elif isinstance(item, bool):
            raise ValueError("invalid_signal_reason_value")
        elif isinstance(item, int):
            result[str(key)] = item
        elif isinstance(item, float) and math.isfinite(item):
            result[str(key)] = item
        else:
            raise ValueError("invalid_signal_reason_value")
    return result


def _reject_forbidden_nested_keys(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if normalized in _FORBIDDEN_MODEL_KEYS:
                raise ValueError("model_output_contains_server_owned_field")
            _reject_forbidden_nested_keys(item)
    elif isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        for item in value:
            _reject_forbidden_nested_keys(item)
