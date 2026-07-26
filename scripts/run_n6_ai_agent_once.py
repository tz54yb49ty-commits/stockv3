#!/usr/bin/env python3
"""One scheduled N6 AI-agent attempt; never a resident worker."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta
from hashlib import sha256
import json
import os
from typing import Any

import psycopg
from psycopg.rows import dict_row

from ashare_v3.user.ai_agent import (
    AI_AGENT_SERVICE,
    AUTONOMOUS_FEATURE_FLAG,
    DisabledModelAdapter,
    FunctionOnlyAIAgentRepository,
    DISPLAY_TIMEZONE,
    MAX_CONTEXT_SIGNALS,
    ModelAdapter,
    SHADOW_SCHEDULE_POLICY_VERSION,
    SHADOW_FEATURE_FLAG,
    ValidatedContext,
    feature_enabled,
    five_minute_bucket,
    load_production_knowledge_manifest,
    run_agent_once,
    shadow_schedule_slot,
    validate_agent_environment,
    validate_model_output,
    _ModelRequestGateClosed,
)
from ashare_v3.user.n6_ai_deepseek_adapter import (
    DEEPSEEK_API_KEY_FILE_ENV,
    DEEPSEEK_EGRESS_MODE_ENV,
    DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
    DEEPSEEK_EGRESS_SYNTHETIC_ONLY,
    DEEPSEEK_MODEL,
    DEEPSEEK_MODEL_PROVIDER,
    DEEPSEEK_MODEL_PROVIDER_ENV,
    DEEPSEEK_SYSTEM_FINGERPRINT_ENV,
    LEGACY_OPENAI_API_KEY_FILE_ENV,
    SYNTHETIC_NETWORK_CANARY_CONTEXT,
    DeepSeekAdapterError,
    DeepSeekChatCompletionsModelAdapter,
    fingerprint_pause_marker_active,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--run-at",
        help="Timezone-aware ISO-8601 time; defaults to Asia/Shanghai now.",
    )
    parser.add_argument(
        "--max-signals", type=int, default=MAX_CONTEXT_SIGNALS
    )
    parser.add_argument("--autonomous", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--synthetic-network-canary",
        action="store_true",
        help="Call DeepSeek once with a fixed synthetic hold context; no DB.",
    )
    return parser


def _default_repository_factory():
    connection = psycopg.connect(
        f"service={AI_AGENT_SERVICE}",
        connect_timeout=10,
        row_factory=dict_row,
        autocommit=False,
    )
    return FunctionOnlyAIAgentRepository(connection), connection.close


def _default_model_adapter_factory(
    environment: Mapping[str, str],
) -> ModelAdapter:
    if not any(
        (
            key in {
                DEEPSEEK_MODEL_PROVIDER_ENV,
                DEEPSEEK_API_KEY_FILE_ENV,
                DEEPSEEK_EGRESS_MODE_ENV,
                DEEPSEEK_SYSTEM_FINGERPRINT_ENV,
                LEGACY_OPENAI_API_KEY_FILE_ENV,
            }
            or key.upper().startswith("DEEPSEEK_")
            or key.upper().startswith("OPENAI_")
            or key.upper().startswith("ASHARE_V3_N6_AI_DEEPSEEK_")
            or key.upper().startswith("ASHARE_V3_N6_AI_OPENAI_")
            or key.upper().startswith("ASHARE_V3_N6_AI_MODEL_")
        )
        for key in environment
    ):
        return DisabledModelAdapter()
    return DeepSeekChatCompletionsModelAdapter.from_environment(
        environment
    )


def _synthetic_provider_probe(
    adapter: DeepSeekChatCompletionsModelAdapter,
) -> dict[str, Any]:
    decision = adapter.generate_decision(
        SYNTHETIC_NETWORK_CANARY_CONTEXT
    )
    try:
        validated = validate_model_output(
            decision,
            context=ValidatedContext(
                context_snapshot_id=1,
                decision_input_hash="0" * 64,
                knowledge_bundle_hash="1" * 64,
                universe_snapshot_hash="2" * 64,
                memory_snapshot_hash="3" * 64,
                workset_hash="4" * 64,
                for_trade_date="20000101",
                signals=(),
                market_context=(),
                positions=(),
                portfolio={},
                strategy_id=1,
                strategy_version="synthetic_canary_v1",
                strategy_hash="5" * 64,
                daily_metrics={},
            ),
        )
    except (TypeError, ValueError):
        raise DeepSeekAdapterError("model_probe_invalid") from None
    if validated.decision_type != "hold":
        raise DeepSeekAdapterError("model_probe_invalid")
    evidence = _deepseek_call_evidence(adapter)
    if (
        evidence.get("provider") != "deepseek"
        or evidence.get("model") != DEEPSEEK_MODEL
        or "system_fingerprint" not in evidence
        or "response_id" not in evidence
    ):
        raise DeepSeekAdapterError("model_probe_invalid")
    evidence["network_called"] = True
    return evidence


def _forbidden_model_environment_present(
    environment: Mapping[str, str],
) -> bool:
    allowed_deepseek = {
        DEEPSEEK_API_KEY_FILE_ENV,
        DEEPSEEK_EGRESS_MODE_ENV,
        DEEPSEEK_SYSTEM_FINGERPRINT_ENV,
    }
    for key in environment:
        upper = key.upper()
        if (
            upper.startswith("OPENAI_")
            or upper.startswith("DEEPSEEK_")
            or upper.startswith("ASHARE_V3_N6_AI_OPENAI_")
            or (
                upper.startswith("ASHARE_V3_N6_AI_DEEPSEEK_")
                and upper not in allowed_deepseek
            )
        ):
            return True
    return False


def _deepseek_call_evidence(
    adapter: ModelAdapter,
) -> dict[str, Any]:
    """Return only the reviewed non-content DeepSeek call evidence."""

    if not isinstance(adapter, DeepSeekChatCompletionsModelAdapter):
        return {}
    raw = adapter.last_call_metadata
    if (
        not isinstance(raw, Mapping)
        or raw.get("provider") != "deepseek"
        or raw.get("model") != DEEPSEEK_MODEL
    ):
        return {}
    result: dict[str, Any] = {
        "provider": "deepseek",
        "model": DEEPSEEK_MODEL,
    }
    for key in ("response_id", "system_fingerprint"):
        value = raw.get(key)
        if (
            isinstance(value, str)
            and 1 <= len(value) <= 200
            and value.isascii()
            and all(
                character.isalnum() or character in "._:-"
                for character in value
            )
        ):
            result[key] = value
    for key in (
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "prompt_cache_hit_tokens",
        "prompt_cache_miss_tokens",
        "reasoning_tokens",
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


def _public_call_evidence(
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    """Remove the provider response identifier from external surfaces."""

    return {
        key: value
        for key, value in evidence.items()
        if key != "response_id"
    }


def _observation_audit_factory(
    *,
    provider_probe: Mapping[str, Any],
    run_at: datetime,
    trade_date: str,
) -> Callable[[Mapping[str, Any]], dict[str, Any]]:
    """Build only the fixed shadow zero-side-effect audit payload."""

    response_id = provider_probe.get("response_id")
    if not isinstance(response_id, str) or not response_id:
        raise ValueError("observation_probe_response_id_missing")
    started_at = run_at.astimezone(DISPLAY_TIMEZONE)
    seed = "|".join(
        (
            "n6_ai_shadow_observation_062",
            str(provider_probe["provider"]),
            str(provider_probe["model"]),
            str(provider_probe["system_fingerprint"]),
            response_id,
        )
    )
    observation_run_id = "n6-shadow-" + sha256(
        seed.encode("ascii")
    ).hexdigest()[:32]
    dedup_key = sha256(
        ("dedup|" + seed).encode("ascii")
    ).hexdigest()

    def build(event: Mapping[str, Any]) -> dict[str, Any]:
        decision_call = event.get("model_call")
        if not isinstance(decision_call, Mapping):
            decision_call = {}
        decision_fingerprint = decision_call.get(
            "system_fingerprint"
        )
        if (
            decision_fingerprint is not None
            and decision_fingerprint
            != provider_probe["system_fingerprint"]
        ):
            raise ValueError("observation_system_fingerprint_mismatch")
        calls = [provider_probe]
        if event.get("decision_call_attempted") is True:
            calls.append(decision_call)

        def total(key: str) -> int | None:
            values = [
                call.get(key)
                for call in calls
                if isinstance(call.get(key), int)
                and not isinstance(call.get(key), bool)
            ]
            return sum(values) if values else None

        latency_ms = total("latency_ms") or 0
        payload: dict[str, Any] = {
            "observation_run_id": observation_run_id,
            "dedup_key": dedup_key,
            "trade_date": trade_date,
            "provider": provider_probe["provider"],
            "model": provider_probe["model"],
            "system_fingerprint": provider_probe[
                "system_fingerprint"
            ],
            "one_shot_status": event["one_shot_status"],
            "identity_probe_succeeded": True,
            "decision_call_attempted": (
                event.get("decision_call_attempted") is True
            ),
            "proposal_created": False,
            "proposal_created_count": 0,
            "order_created_count": 0,
            "trade_created_count": 0,
            "position_mutation_count": 0,
            "lot_mutation_count": 0,
            "cash_mutation_count": 0,
            "started_at": started_at.isoformat(
                timespec="microseconds"
            ),
            "finished_at": (
                started_at + timedelta(milliseconds=latency_ms)
            ).isoformat(timespec="microseconds"),
        }
        if event.get("decision_call_attempted") is True:
            payload["structure_valid"] = (
                event.get("structure_valid") is True
            )
        context_snapshot_id = event.get("context_snapshot_id")
        if (
            isinstance(context_snapshot_id, int)
            and not isinstance(context_snapshot_id, bool)
            and context_snapshot_id > 0
        ):
            payload["context_snapshot_id"] = context_snapshot_id
        for source, target in (
            ("input_tokens", "input_token_count"),
            ("output_tokens", "output_token_count"),
            ("total_tokens", "total_token_count"),
            ("prompt_cache_hit_tokens", "cache_hit_token_count"),
            ("prompt_cache_miss_tokens", "cache_miss_token_count"),
        ):
            value = total(source)
            if value is not None:
                payload[target] = value
        payload["latency_ms"] = latency_ms
        return payload

    return build


def _nondecision_observation_event(
    result: Mapping[str, Any],
) -> dict[str, Any]:
    attempted = result.get("model_called") is True
    status = str(result.get("status") or "failed_closed")
    if result.get("reason") == "model_or_decision_validation_failed":
        status = "decision_structure_invalid"
    elif result.get("reason") == "decision_record_rejected":
        status = "decision_record_rejected"
    if not status.isascii() or not all(
        character.islower()
        or character.isdigit()
        or character == "_"
        for character in status
    ):
        status = "failed_closed"
    return {
        "one_shot_status": status,
        "decision_call_attempted": attempted,
        "structure_valid": (
            result.get("structure_valid") is True
            if attempted
            else None
        ),
        "model_call": (
            result.get("model_call")
            if isinstance(result.get("model_call"), Mapping)
            else {}
        ),
    }


def _with_schedule_audit(
    result: Mapping[str, Any],
    *,
    schedule_slot: str | None,
    schedule_preflight_status: str,
    provider_probe_called: bool,
    decision_model_called: bool,
) -> dict[str, Any]:
    payload = dict(result)
    payload.update(
        {
            "schedule_policy_version":
                SHADOW_SCHEDULE_POLICY_VERSION,
            "schedule_slot": schedule_slot,
            "schedule_preflight_status":
                schedule_preflight_status,
            "provider_probe_called": provider_probe_called,
            "decision_model_called": decision_model_called,
            "deepseek_request_count":
                int(provider_probe_called)
                + int(decision_model_called),
        }
    )
    return payload


def _shadow_request_window_open(
    *,
    expected_slot: str,
    expected_trade_date: date,
    now_factory: Callable[[], datetime],
) -> bool:
    """Fail closed unless a provider request is still in its exact slot."""

    try:
        request_time = now_factory()
        if (
            request_time.tzinfo is None
            or request_time.utcoffset() is None
        ):
            return False
        local_request_time = request_time.astimezone(DISPLAY_TIMEZONE)
        return (
            local_request_time.date() == expected_trade_date
            and shadow_schedule_slot(local_request_time) == expected_slot
        )
    except Exception:
        return False


class _WindowGatedModelAdapter:
    """Keep the public agent API stable while gating the actual egress call."""

    def __init__(
        self,
        delegate: ModelAdapter,
        request_gate: Callable[[], bool],
    ) -> None:
        self._delegate = delegate
        self._request_gate = request_gate

    @property
    def adapter_name(self) -> str:
        return self._delegate.adapter_name

    @property
    def model_version(self) -> str:
        return self._delegate.model_version

    @property
    def last_call_metadata(self) -> object:
        return getattr(self._delegate, "last_call_metadata", None)

    def generate_decision(
        self, context: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        try:
            request_allowed = self._request_gate()
        except Exception:
            request_allowed = False
        if request_allowed is not True:
            raise _ModelRequestGateClosed
        return self._delegate.generate_decision(context)


def run_from_args(
    args: argparse.Namespace,
    *,
    environment: Mapping[str, str] | None = None,
    now_factory: Callable[[], datetime] | None = None,
    repository_factory: Callable[[], tuple[Any, Callable[[], None]]] | None = None,
    model_adapter_factory: Callable[[], ModelAdapter] | None = None,
) -> dict[str, Any]:
    env = os.environ if environment is None else environment
    shadow_enabled = feature_enabled(env, SHADOW_FEATURE_FLAG)
    autonomous_enabled = feature_enabled(env, AUTONOMOUS_FEATURE_FLAG)
    autonomous_requested = bool(getattr(args, "autonomous", False))
    synthetic_canary = bool(
        getattr(args, "synthetic_network_canary", False)
    )
    requested_mode = (
        "autonomous" if autonomous_requested else "shadow"
    )
    if not args.execute:
        return {
            "ok": True,
            "status": "dry_run_preflight",
            "requested_mode": requested_mode,
            "synthetic_network_canary": synthetic_canary,
            "shadow_enabled": shadow_enabled,
            "autonomous_enabled": autonomous_enabled,
            "db_connected": False,
            "model_called": False,
            "decision_recorded": False,
            "proposal_created": False,
        }
    if not synthetic_canary and not shadow_enabled:
        return _with_schedule_audit(
            {
                "ok": True,
                "status": "feature_disabled",
                "reason": "shadow_feature_disabled",
                "db_connected": False,
                "model_called": False,
                "decision_recorded": False,
                "proposal_created": False,
            },
            schedule_slot=None,
            schedule_preflight_status="not_attempted",
            provider_probe_called=False,
            decision_model_called=False,
        )
    if (
        autonomous_requested
        and env.get(DEEPSEEK_MODEL_PROVIDER_ENV)
        == DEEPSEEK_MODEL_PROVIDER
    ):
        result = {
            "ok": True,
            "status": "feature_disabled",
            "reason": "deepseek_autonomous_always_blocked",
            "db_connected": False,
            "model_called": False,
            "decision_recorded": False,
            "proposal_created": False,
        }
        return (
            result
            if synthetic_canary
            else _with_schedule_audit(
                result,
                schedule_slot=None,
                schedule_preflight_status="not_attempted",
                provider_probe_called=False,
                decision_model_called=False,
            )
        )
    if synthetic_canary and _forbidden_model_environment_present(env):
        result = {
            "ok": False,
            "status": "failed_closed",
            "reason": "model_adapter_configuration_invalid",
            "db_connected": False,
            "model_called": False,
            "decision_recorded": False,
            "proposal_created": False,
        }
        return (
            result
            if synthetic_canary
            else _with_schedule_audit(
                result,
                schedule_slot=None,
                schedule_preflight_status="not_attempted",
                provider_probe_called=False,
                decision_model_called=False,
            )
        )
    egress_mode = str(
        env.get(DEEPSEEK_EGRESS_MODE_ENV)
        or DEEPSEEK_EGRESS_SYNTHETIC_ONLY
    )
    if (
        synthetic_canary
        and egress_mode != DEEPSEEK_EGRESS_SYNTHETIC_ONLY
    ):
        return {
            "ok": False,
            "status": "failed_closed",
            "reason": "synthetic_canary_egress_mode_invalid",
            "db_connected": False,
            "model_called": False,
            "decision_recorded": False,
            "proposal_created": False,
        }
    invalid_max_signals = (
        isinstance(args.max_signals, bool)
        or not isinstance(args.max_signals, int)
        or args.max_signals != MAX_CONTEXT_SIGNALS
    )
    if synthetic_canary and invalid_max_signals:
        result = {
            "ok": False,
            "status": "failed_closed",
            "reason": "invalid_max_signals",
            "db_connected": False,
            "model_called": False,
            "decision_recorded": False,
            "proposal_created": False,
        }
        return (
            result
            if synthetic_canary
            else _with_schedule_audit(
                result,
                schedule_slot=None,
                schedule_preflight_status="not_attempted",
                provider_probe_called=False,
                decision_model_called=False,
            )
        )

    if synthetic_canary:
        if fingerprint_pause_marker_active():
            return {
                "ok": False,
                "status": "failed_closed",
                "reason": "deepseek_system_fingerprint_paused",
                "db_connected": False,
                "model_called": False,
                "decision_recorded": False,
                "proposal_created": False,
            }
        try:
            adapter = (
                model_adapter_factory()
                if model_adapter_factory is not None
                else _default_model_adapter_factory(env)
            )
        except Exception:
            return {
                "ok": False,
                "status": "failed_closed",
                "reason": "model_adapter_configuration_invalid",
                "db_connected": False,
                "model_called": False,
                "decision_recorded": False,
                "proposal_created": False,
            }
        if not isinstance(
            adapter, DeepSeekChatCompletionsModelAdapter
        ):
            return {
                "ok": False,
                "status": "failed_closed",
                "reason": (
                    "model_adapter_not_configured"
                    if isinstance(adapter, DisabledModelAdapter)
                    else "model_adapter_not_deepseek"
                ),
                "db_connected": False,
                "model_called": False,
                "decision_recorded": False,
                "proposal_created": False,
            }
        if (
            egress_mode != DEEPSEEK_EGRESS_SYNTHETIC_ONLY
            or adapter.egress_mode
            != DEEPSEEK_EGRESS_SYNTHETIC_ONLY
        ):
            return {
                "ok": False,
                "status": "failed_closed",
                "reason": "synthetic_canary_egress_mode_invalid",
                "db_connected": False,
                "model_called": False,
                "decision_recorded": False,
                "proposal_created": False,
            }
        try:
            provider_probe = _synthetic_provider_probe(adapter)
        except Exception:
            return {
                "ok": False,
                "status": "failed_closed",
                "reason": (
                    "deepseek_system_fingerprint_paused"
                    if fingerprint_pause_marker_active()
                    else "deepseek_provider_identity_probe_failed"
                ),
                "db_connected": False,
                "model_called": True,
                "decision_recorded": False,
                "proposal_created": False,
            }
        return {
            "ok": True,
            "status": "synthetic_network_canary_passed",
            "db_connected": False,
            "model_called": True,
            "decision_recorded": False,
            "proposal_created": False,
            "model_call": _public_call_evidence(provider_probe),
        }

    now_factory = now_factory or (
        lambda: datetime.now(DISPLAY_TIMEZONE)
    )
    try:
        run_at = (
            datetime.fromisoformat(args.run_at)
            if args.run_at
            else now_factory()
        )
        if (
            run_at.tzinfo is None
            or run_at.utcoffset() is None
        ):
            raise ValueError("timezone_aware_run_time_required")
        schedule_slot = shadow_schedule_slot(run_at)
    except (TypeError, ValueError):
        return _with_schedule_audit(
            {
                "ok": False,
                "status": "failed_closed",
                "reason": "invalid_run_time",
                "db_connected": False,
                "model_called": False,
                "decision_recorded": False,
                "proposal_created": False,
            },
            schedule_slot=None,
            schedule_preflight_status="not_attempted",
            provider_probe_called=False,
            decision_model_called=False,
        )
    if schedule_slot is None:
        return _with_schedule_audit(
            {
                "ok": True,
                "status": "outside_shadow_slot",
                "reason": "local_schedule_gate_closed",
                "db_connected": False,
                "model_called": False,
                "decision_recorded": False,
                "proposal_created": False,
            },
            schedule_slot=None,
            schedule_preflight_status="outside_shadow_slot",
            provider_probe_called=False,
            decision_model_called=False,
        )

    if invalid_max_signals:
        return _with_schedule_audit(
            {
                "ok": False,
                "status": "failed_closed",
                "reason": "invalid_max_signals",
                "db_connected": False,
                "model_called": False,
                "decision_recorded": False,
                "proposal_created": False,
            },
            schedule_slot=schedule_slot,
            schedule_preflight_status="not_attempted",
            provider_probe_called=False,
            decision_model_called=False,
        )
    if _forbidden_model_environment_present(env):
        return _with_schedule_audit(
            {
                "ok": False,
                "status": "failed_closed",
                "reason": "model_adapter_configuration_invalid",
                "db_connected": False,
                "model_called": False,
                "decision_recorded": False,
                "proposal_created": False,
            },
            schedule_slot=schedule_slot,
            schedule_preflight_status="not_attempted",
            provider_probe_called=False,
            decision_model_called=False,
        )
    try:
        validate_agent_environment(env)
        knowledge_manifest = load_production_knowledge_manifest(env)
    except (OSError, ValueError):
        return _with_schedule_audit(
            {
                "ok": False,
                "status": "failed_closed",
                "reason": "production_knowledge_manifest_invalid",
                "db_connected": False,
                "model_called": False,
                "decision_recorded": False,
                "proposal_created": False,
            },
            schedule_slot=schedule_slot,
            schedule_preflight_status="not_attempted",
            provider_probe_called=False,
            decision_model_called=False,
        )
    if (
        requested_mode == "autonomous"
        and knowledge_manifest.get("autonomous_trading_usable")
        is not True
    ):
        return _with_schedule_audit(
            {
                "ok": True,
                "status": "feature_disabled",
                "reason": "knowledge_manifest_autonomous_disabled",
                "db_connected": False,
                "model_called": False,
                "decision_recorded": False,
                "proposal_created": False,
            },
            schedule_slot=schedule_slot,
            schedule_preflight_status="not_attempted",
            provider_probe_called=False,
            decision_model_called=False,
        )
    if egress_mode != DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW:
        return _with_schedule_audit(
            {
                "ok": False,
                "status": "failed_closed",
                "reason": "real_data_egress_blocked",
                "db_connected": False,
                "model_called": False,
                "decision_recorded": False,
                "proposal_created": False,
            },
            schedule_slot=schedule_slot,
            schedule_preflight_status="not_attempted",
            provider_probe_called=False,
            decision_model_called=False,
        )

    local_date = run_at.astimezone(DISPLAY_TIMEZONE).date()
    run_bucket = five_minute_bucket(run_at)
    factory = repository_factory or _default_repository_factory
    try:
        repository, close = factory()
    except Exception:
        return _with_schedule_audit(
            {
                "ok": False,
                "status": "failed_closed",
                "reason": "schedule_preflight_service_unavailable",
                "db_connected": False,
                "model_called": False,
                "decision_recorded": False,
                "proposal_created": False,
            },
            schedule_slot=schedule_slot,
            schedule_preflight_status="service_unavailable",
            provider_probe_called=False,
            decision_model_called=False,
        )
    try:
        try:
            preflight = repository.shadow_schedule_preflight(
                run_bucket=run_bucket,
                for_trade_date=local_date,
            )
        except Exception:
            return _with_schedule_audit(
                {
                    "ok": False,
                    "status": "failed_closed",
                    "reason": "schedule_preflight_service_unavailable",
                    "db_connected": True,
                    "model_called": False,
                    "decision_recorded": False,
                    "proposal_created": False,
                },
                schedule_slot=schedule_slot,
                schedule_preflight_status="service_unavailable",
                provider_probe_called=False,
                decision_model_called=False,
            )
        preflight_status = (
            str(preflight.get("status") or "")
            if isinstance(preflight, Mapping)
            else ""
        )
        allowed_preflight_statuses = {
            "open_slot_ready",
            "outside_shadow_slot",
            "not_open_trade_date",
            "already_processed",
        }
        if (
            not isinstance(preflight, Mapping)
            or preflight.get("ok") is not True
            or preflight_status not in allowed_preflight_statuses
        ):
            return _with_schedule_audit(
                {
                    "ok": False,
                    "status": "failed_closed",
                    "reason": "schedule_preflight_rejected",
                    "db_connected": True,
                    "model_called": False,
                    "decision_recorded": False,
                    "proposal_created": False,
                },
                schedule_slot=schedule_slot,
                schedule_preflight_status="rejected",
                provider_probe_called=False,
                decision_model_called=False,
            )
        if preflight_status != "open_slot_ready":
            return _with_schedule_audit(
                {
                    "ok": True,
                    "status": preflight_status,
                    "db_connected": True,
                    "model_called": False,
                    "decision_recorded": False,
                    "proposal_created": False,
                },
                schedule_slot=schedule_slot,
                schedule_preflight_status=preflight_status,
                provider_probe_called=False,
                decision_model_called=False,
            )

        if fingerprint_pause_marker_active():
            return _with_schedule_audit(
                {
                    "ok": False,
                    "status": "failed_closed",
                    "reason": "deepseek_system_fingerprint_paused",
                    "db_connected": True,
                    "model_called": False,
                    "decision_recorded": False,
                    "proposal_created": False,
                },
                schedule_slot=schedule_slot,
                schedule_preflight_status=preflight_status,
                provider_probe_called=False,
                decision_model_called=False,
            )
        try:
            adapter = (
                model_adapter_factory()
                if model_adapter_factory is not None
                else _default_model_adapter_factory(env)
            )
        except Exception:
            return _with_schedule_audit(
                {
                    "ok": False,
                    "status": "failed_closed",
                    "reason": "model_adapter_configuration_invalid",
                    "db_connected": True,
                    "model_called": False,
                    "decision_recorded": False,
                    "proposal_created": False,
                },
                schedule_slot=schedule_slot,
                schedule_preflight_status=preflight_status,
                provider_probe_called=False,
                decision_model_called=False,
            )
        if not isinstance(
            adapter, DeepSeekChatCompletionsModelAdapter
        ):
            return _with_schedule_audit(
                {
                    "ok": False,
                    "status": "failed_closed",
                    "reason": (
                        "model_adapter_not_configured"
                        if isinstance(adapter, DisabledModelAdapter)
                        else "model_adapter_not_deepseek"
                    ),
                    "db_connected": True,
                    "model_called": False,
                    "decision_recorded": False,
                    "proposal_created": False,
                },
                schedule_slot=schedule_slot,
                schedule_preflight_status=preflight_status,
                provider_probe_called=False,
                decision_model_called=False,
            )
        if (
            adapter.egress_mode
            != DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW
        ):
            return _with_schedule_audit(
                {
                    "ok": False,
                    "status": "failed_closed",
                    "reason": "real_data_egress_blocked",
                    "db_connected": True,
                    "model_called": False,
                    "decision_recorded": False,
                    "proposal_created": False,
                },
                schedule_slot=schedule_slot,
                schedule_preflight_status=preflight_status,
                provider_probe_called=False,
                decision_model_called=False,
            )
        if not _shadow_request_window_open(
            expected_slot=schedule_slot,
            expected_trade_date=local_date,
            now_factory=now_factory,
        ):
            return _with_schedule_audit(
                {
                    "ok": False,
                    "status": "failed_closed",
                    "reason": (
                        "shadow_schedule_window_closed_before_"
                        "identity_probe"
                    ),
                    "db_connected": True,
                    "model_called": False,
                    "decision_recorded": False,
                    "proposal_created": False,
                },
                schedule_slot=schedule_slot,
                schedule_preflight_status=preflight_status,
                provider_probe_called=False,
                decision_model_called=False,
            )
        try:
            provider_probe = _synthetic_provider_probe(adapter)
        except Exception:
            return _with_schedule_audit(
                {
                    "ok": False,
                    "status": "failed_closed",
                    "reason": (
                        "deepseek_system_fingerprint_paused"
                        if fingerprint_pause_marker_active()
                        else "deepseek_provider_identity_probe_failed"
                    ),
                    "db_connected": True,
                    "model_called": True,
                    "decision_recorded": False,
                    "proposal_created": False,
                },
                schedule_slot=schedule_slot,
                schedule_preflight_status=preflight_status,
                provider_probe_called=True,
                decision_model_called=False,
            )

        audit_factory = _observation_audit_factory(
            provider_probe=provider_probe,
            run_at=run_at,
            trade_date=local_date.isoformat(),
        )
        result = run_agent_once(
            repository=repository,
            model_adapter=_WindowGatedModelAdapter(
                adapter,
                lambda: _shadow_request_window_open(
                    expected_slot=schedule_slot,
                    expected_trade_date=local_date,
                    now_factory=now_factory,
                ),
            ),
            now=run_at,
            requested_mode=requested_mode,
            shadow_enabled=shadow_enabled,
            autonomous_enabled=autonomous_enabled,
            max_signals=args.max_signals,
            observation_audit_factory=audit_factory,
        )
        if result.get("reason") == "model_request_gate_closed":
            result = dict(result)
            result["reason"] = (
                "shadow_schedule_window_closed_before_decision"
            )
        if (
            result.get("observation_audit_attempted") is not True
            and result.get("observation_audit_skipped") is not True
        ):
            try:
                audit = repository.record_shadow_observation(
                    audit_factory(
                        _nondecision_observation_event(result)
                    )
                )
            except Exception:
                return _with_schedule_audit(
                    {
                        "ok": False,
                        "status": "failed_closed",
                        "reason":
                            "observation_audit_service_unavailable",
                        "db_connected": True,
                        "model_called":
                            result.get("model_called") is True,
                        "decision_recorded": False,
                        "proposal_created": False,
                        "observation_audit_recorded": False,
                    },
                    schedule_slot=schedule_slot,
                    schedule_preflight_status=preflight_status,
                    provider_probe_called=True,
                    decision_model_called=(
                        result.get("model_called") is True
                    ),
                )
            if not isinstance(audit, Mapping) or audit.get("ok") is not True:
                return _with_schedule_audit(
                    {
                        "ok": False,
                        "status": "failed_closed",
                        "reason": "observation_audit_rejected",
                        "db_connected": True,
                        "model_called":
                            result.get("model_called") is True,
                        "decision_recorded": False,
                        "proposal_created": False,
                        "observation_audit_recorded": False,
                    },
                    schedule_slot=schedule_slot,
                    schedule_preflight_status=preflight_status,
                    provider_probe_called=True,
                    decision_model_called=(
                        result.get("model_called") is True
                    ),
                )
            result["observation_audit_attempted"] = True
            result["observation_audit_recorded"] = True
            result.pop("observation_audit_followup_required", None)
        if fingerprint_pause_marker_active():
            return _with_schedule_audit(
                {
                    "ok": False,
                    "status": "failed_closed",
                    "reason": "deepseek_system_fingerprint_paused",
                    "db_connected": True,
                    "model_called": result.get("model_called") is True,
                    "decision_recorded": (
                        result.get("decision_recorded") is True
                    ),
                    "proposal_created": (
                        result.get("proposal_created") is True
                    ),
                },
                schedule_slot=schedule_slot,
                schedule_preflight_status=preflight_status,
                provider_probe_called=True,
                decision_model_called=(
                    result.get("model_called") is True
                ),
            )
        model_call_evidence = _deepseek_call_evidence(adapter)
        if (
            result.get("model_called") is True
            and model_call_evidence
        ):
            result["model_call"] = _public_call_evidence(
                model_call_evidence
            )
        else:
            result.pop("model_call", None)
        result["provider_identity_probe"] = _public_call_evidence(
            provider_probe
        )
        result["knowledge_bundle_hash"] = knowledge_manifest[
            "bundle_sha256"
        ]
        return _with_schedule_audit(
            result,
            schedule_slot=schedule_slot,
            schedule_preflight_status=preflight_status,
            provider_probe_called=True,
            decision_model_called=result.get("model_called") is True,
        )
    finally:
        close()


def main() -> int:
    payload = run_from_args(build_parser().parse_args())
    print(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, default=str
        )
    )
    return 0 if payload.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
