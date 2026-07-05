"""Fail-closed N6 delivery provider adapter primitives.

This module defines provider-facing abstractions only. It does not read
credentials, update outbox rows, start workers, or call external providers by
default. Real provider support remains a disabled skeleton until a later final
execute gate explicitly enables network sends and supplies audited policy hooks.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Mapping, Protocol


NOOP_PROVIDER_ID = "noop_local_provider_v1"
DRY_RUN_PROVIDER_ID = "dry_run_provider_v1"
REAL_PROVIDER_SKELETON_ID = "real_provider_skeleton_v1"
DEFAULT_CHANNEL = "in_app_notification_preview"

FORBIDDEN_PROVIDER_PAYLOAD_KEYS = frozenset(
    {
        "trace_json",
        "source_payload_json",
        "card_payload_json",
        "display_payload_json",
        "raw_n5_payload",
        "source_outbox_id",
        "source_event_id",
        "source_action_event_id",
        "source_action_run_id",
        "source_event_dedup_key",
        "payload_json",
        "raw_payload",
        "outbox_payload_json",
        "action_run_internal_payload",
        "credential_secret",
        "credential_value",
        "secret",
        "secret_value",
        "token",
        "access_token",
    }
)

SECRET_REPORT_KEYS = frozenset(
    {
        "credential_secret",
        "credential_value",
        "secret",
        "secret_value",
        "token",
        "access_token",
        "password",
        "api_key",
    }
)


@dataclass(frozen=True)
class ProviderCapability:
    provider_id: str
    adapter_kind: str
    channel: str = DEFAULT_CHANNEL
    can_materialize_preview: bool = False
    can_send_network: bool = False
    requires_credentials: bool = False
    supports_provider_ack: bool = False
    writes_provider_attempt_audit: bool = False
    credential_ref_required: bool = False
    consent_required: bool = True
    retry_policy_required: bool = True
    audit_policy_required: bool = True
    n5_ack_policy_required: bool = True
    rollback_supersession_required: bool = True
    can_update_n5_outbox_status: bool = False


@dataclass(frozen=True)
class ProviderPolicyHooks:
    final_gate_allowed: bool = False
    network_send_enabled: bool = False
    consent_allowed: bool = False
    retry_policy_ready: bool = False
    attempt_audit_ready: bool = False
    n5_ack_policy_ready: bool = False
    rollback_supersession_ready: bool = False
    final_gate_id: str | None = None


@dataclass(frozen=True)
class ProviderSendInput:
    delivery_materialization_run_id: str
    source_notification_queue_id: int
    provider_id: str
    channel: str
    title: str
    message: str
    notification_payload_json: Mapping[str, Any] = field(default_factory=dict)
    credential_ref: str | None = None
    secret_value: str | None = None
    policy_hooks: ProviderPolicyHooks = field(default_factory=ProviderPolicyHooks)


@dataclass(frozen=True)
class ProviderSendResult:
    result: str
    provider_id: str
    adapter_kind: str
    channel: str
    blockers: tuple[str, ...] = ()
    network_send_attempted: bool = False
    provider_delivery_confirmed: bool = False
    provider_message_id: str | None = None
    n5_outbox_status_updated: bool = False
    payload: Mapping[str, Any] = field(default_factory=dict)

    def to_report(self) -> dict[str, Any]:
        return redact_provider_report(
            {
                "result": self.result,
                "provider_id": self.provider_id,
                "adapter_kind": self.adapter_kind,
                "channel": self.channel,
                "blockers": list(self.blockers),
                "network_send_attempted": self.network_send_attempted,
                "provider_delivery_confirmed": self.provider_delivery_confirmed,
                "provider_message_id": self.provider_message_id,
                "n5_outbox_status_updated": self.n5_outbox_status_updated,
                "payload": dict(self.payload),
            }
        )


class DeliveryProviderAdapter(Protocol):
    def capability(self) -> ProviderCapability:
        ...

    def build_provider_visible_payload(self, input: ProviderSendInput) -> dict[str, Any]:
        ...

    def send(self, input: ProviderSendInput, *, final_gate_token: str | None = None) -> ProviderSendResult:
        ...


Transport = Callable[[dict[str, Any]], Mapping[str, Any]]


class BaseProviderAdapter:
    def __init__(self, *, transport: Transport | None = None) -> None:
        self.transport = transport

    def capability(self) -> ProviderCapability:
        raise NotImplementedError

    def build_provider_visible_payload(self, input: ProviderSendInput) -> dict[str, Any]:
        payload = {
            "schema_version": "n6_delivery_provider_payload_v1",
            "delivery_materialization_run_id": input.delivery_materialization_run_id,
            "source_notification_queue_id": input.source_notification_queue_id,
            "provider_id": self.capability().provider_id,
            "channel": input.channel,
            "title": choose_text(input, "title"),
            "message": choose_text(input, "message"),
        }
        return {key: value for key, value in payload.items() if value is not None}


class NoopLocalPreviewAdapter(BaseProviderAdapter):
    def capability(self) -> ProviderCapability:
        return ProviderCapability(
            provider_id=NOOP_PROVIDER_ID,
            adapter_kind="noop_local_preview",
            can_materialize_preview=True,
            can_send_network=False,
            requires_credentials=False,
            credential_ref_required=False,
            consent_required=False,
            retry_policy_required=False,
            audit_policy_required=False,
            n5_ack_policy_required=False,
            rollback_supersession_required=False,
        )

    def send(self, input: ProviderSendInput, *, final_gate_token: str | None = None) -> ProviderSendResult:
        payload = self.build_provider_visible_payload(input)
        return ProviderSendResult(
            result="NOOP",
            provider_id=self.capability().provider_id,
            adapter_kind=self.capability().adapter_kind,
            channel=input.channel,
            network_send_attempted=False,
            provider_delivery_confirmed=False,
            payload=payload,
        )


class DryRunProviderAdapter(BaseProviderAdapter):
    def capability(self) -> ProviderCapability:
        return ProviderCapability(
            provider_id=DRY_RUN_PROVIDER_ID,
            adapter_kind="dry_run_provider",
            can_materialize_preview=False,
            can_send_network=False,
            requires_credentials=False,
            credential_ref_required=False,
            supports_provider_ack=False,
            writes_provider_attempt_audit=False,
        )

    def send(self, input: ProviderSendInput, *, final_gate_token: str | None = None) -> ProviderSendResult:
        payload = self.build_provider_visible_payload(input)
        return ProviderSendResult(
            result="DRY_RUN",
            provider_id=self.capability().provider_id,
            adapter_kind=self.capability().adapter_kind,
            channel=input.channel,
            blockers=(),
            network_send_attempted=False,
            provider_delivery_confirmed=False,
            payload=payload,
        )


class RealProviderAdapterSkeleton(BaseProviderAdapter):
    def capability(self) -> ProviderCapability:
        return ProviderCapability(
            provider_id=REAL_PROVIDER_SKELETON_ID,
            adapter_kind="real_provider_skeleton",
            can_materialize_preview=False,
            can_send_network=False,
            requires_credentials=True,
            supports_provider_ack=False,
            writes_provider_attempt_audit=False,
            credential_ref_required=True,
            consent_required=True,
            retry_policy_required=True,
            audit_policy_required=True,
            n5_ack_policy_required=True,
            rollback_supersession_required=True,
            can_update_n5_outbox_status=False,
        )

    def send(self, input: ProviderSendInput, *, final_gate_token: str | None = None) -> ProviderSendResult:
        capability = self.capability()
        payload = self.build_provider_visible_payload(input)
        blockers = real_provider_blockers(input, capability=capability, final_gate_token=final_gate_token)
        if blockers:
            return ProviderSendResult(
                result="BLOCKED",
                provider_id=capability.provider_id,
                adapter_kind=capability.adapter_kind,
                channel=input.channel,
                blockers=tuple(blockers),
                network_send_attempted=False,
                provider_delivery_confirmed=False,
                payload=payload,
            )

        if self.transport is None:
            return ProviderSendResult(
                result="BLOCKED",
                provider_id=capability.provider_id,
                adapter_kind=capability.adapter_kind,
                channel=input.channel,
                blockers=("provider_transport_missing",),
                network_send_attempted=False,
                provider_delivery_confirmed=False,
                payload=payload,
            )

        # This branch is intentionally unreachable while can_send_network=false.
        provider_response = self.transport(payload)  # pragma: no cover - future gated implementation
        return ProviderSendResult(  # pragma: no cover - future gated implementation
            result="SENT",
            provider_id=capability.provider_id,
            adapter_kind=capability.adapter_kind,
            channel=input.channel,
            network_send_attempted=True,
            provider_delivery_confirmed=True,
            provider_message_id=str(provider_response.get("provider_message_id") or ""),
            payload=payload,
        )


def choose_text(input: ProviderSendInput, key: str) -> str:
    value = input.notification_payload_json.get(key)
    if isinstance(value, str) and value:
        return value
    return input.title if key == "title" else input.message


def real_provider_blockers(
    input: ProviderSendInput,
    *,
    capability: ProviderCapability,
    final_gate_token: str | None,
) -> list[str]:
    hooks = input.policy_hooks
    blockers: list[str] = []
    if not hooks.final_gate_allowed or not final_gate_token:
        blockers.append("missing_final_execute_gate")
    if not hooks.network_send_enabled:
        blockers.append("network_send_not_enabled")
    if not capability.can_send_network:
        blockers.append("can_send_network_false")
    if capability.credential_ref_required and not input.credential_ref:
        blockers.append("credential_ref_missing")
    if input.credential_ref and not is_opaque_credential_ref(input.credential_ref):
        blockers.append("credential_ref_not_opaque")
    if input.secret_value is not None:
        blockers.append("secret_supplied")
    if capability.consent_required and not hooks.consent_allowed:
        blockers.append("consent_not_allowed")
    if capability.retry_policy_required and not hooks.retry_policy_ready:
        blockers.append("retry_policy_missing")
    if capability.audit_policy_required and not hooks.attempt_audit_ready:
        blockers.append("attempt_audit_policy_missing")
    if capability.n5_ack_policy_required and not hooks.n5_ack_policy_ready:
        blockers.append("n5_ack_policy_missing")
    if capability.rollback_supersession_required and not hooks.rollback_supersession_ready:
        blockers.append("rollback_supersession_policy_missing")
    if provider_payload_has_forbidden_keys(input.notification_payload_json):
        blockers.append("provider_payload_contains_forbidden_keys")
    return dedupe_preserve_order(blockers)


def is_opaque_credential_ref(value: str) -> bool:
    return value.startswith(("secret://", "credential://", "vault://", "ref://")) and "\n" not in value


def provider_payload_has_forbidden_keys(payload: Mapping[str, Any]) -> bool:
    found = False

    def walk(value: Any) -> None:
        nonlocal found
        if found:
            return
        if isinstance(value, Mapping):
            for key, child in value.items():
                if str(key) in FORBIDDEN_PROVIDER_PAYLOAD_KEYS:
                    found = True
                    return
                walk(child)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(payload)
    return found


def redact_provider_report(value: Any) -> Any:
    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for key, child in value.items():
            key_text = str(key)
            if key_text in SECRET_REPORT_KEYS:
                continue
            redacted[key_text] = redact_provider_report(child)
        return redacted
    if isinstance(value, list):
        return [redact_provider_report(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_provider_report(item) for item in value)
    return value


def capability_snapshot(adapter: DeliveryProviderAdapter) -> dict[str, Any]:
    return asdict(adapter.capability())


def dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
