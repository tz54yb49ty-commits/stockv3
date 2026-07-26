"""Fixed-endpoint OpenAI Responses adapter for the N6 shadow agent."""

from __future__ import annotations

from collections.abc import Mapping
import errno
import http.client
import json
import os
from pathlib import Path
import ssl
import stat
import time
from typing import Any, Protocol


OPENAI_MODEL = "gpt-5.6-sol"
OPENAI_HOST = "api.openai.com"
OPENAI_PATH = "/v1/responses"
OPENAI_API_KEY_FILE_ENV = "ASHARE_V3_N6_AI_OPENAI_API_KEY_FILE"
OPENAI_REASONING_EFFORT = "high"
OPENAI_TIMEOUT_SECONDS = 45
MAX_RESPONSE_BYTES = 1_048_576
TRANSPORT_METADATA_KEY = "_n6_transport_metadata"
FORBIDDEN_OPENAI_ENV = frozenset(
    {
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_ORG_ID",
        "OPENAI_ORGANIZATION",
        "OPENAI_PROXY",
    }
)

DECISION_JSON_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "decision_type": {
            "type": "string",
            "enum": ["buy", "sell", "hold"],
        },
        "identity_key": {
            "type": ["string", "null"],
            "pattern": r"^stock:(SH|SZ):[0-9]{6}$",
        },
        "source_signal_projection_id": {
            "type": ["string", "null"],
            "pattern": r"^[1-9][0-9]{0,18}$",
        },
        "source_virtual_position_id": {
            "type": ["string", "null"],
            "pattern": r"^[1-9][0-9]{0,18}$",
        },
        "confidence": {
            "type": "string",
            "pattern": r"^(0(?:\.[0-9]{1,6})?|1(?:\.0{1,6})?)$",
        },
        "reason_summary": {"type": "string", "maxLength": 1000},
        "evidence": {
            "type": "array",
            "maxItems": 20,
            "items": {"type": "string", "maxLength": 300},
        },
        "counter_evidence": {
            "type": "array",
            "maxItems": 20,
            "items": {"type": "string", "maxLength": 300},
        },
        "risk_assessment": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "trigger": {
                    "type": "string",
                    "enum": [
                        "signal",
                        "portfolio_risk",
                        "stop_loss",
                        "none",
                    ],
                },
                "level": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "critical"],
                },
                "summary": {"type": "string", "maxLength": 500},
            },
            "required": ["trigger", "level", "summary"],
        },
        "strategy_candidate_notes": {
            "type": ["string", "null"],
            "maxLength": 2000,
        },
    },
    "required": [
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
    ],
}

SYSTEM_INSTRUCTIONS = """\
You are the N6 paper-only AI investor. Use only the supplied frozen N6 JSON.
Return exactly one decision matching the strict schema. Never infer or output
account, principal, trade date, price, quantity, credentials, hidden reasoning,
or facts absent from the snapshot. A buy requires a current stock buy signal.
A sell requires an AI-owned position and an allowed sell trigger. When evidence
is insufficient, return hold. Reasons must be concise and auditable.
"""


class OpenAIAdapterError(RuntimeError):
    """Stable fail-closed error without provider response or secret detail."""


class ResponsesTransport(Protocol):
    def create(
        self,
        *,
        api_key: str,
        payload: Mapping[str, Any],
        timeout_seconds: int,
    ) -> Mapping[str, Any]:
        ...


class FixedOpenAIResponsesTransport:
    """Direct TLS transport; no proxy, redirect, or configurable base URL."""

    def create(
        self,
        *,
        api_key: str,
        payload: Mapping[str, Any],
        timeout_seconds: int,
    ) -> Mapping[str, Any]:
        body = json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        started_ns = time.monotonic_ns()
        connection = http.client.HTTPSConnection(
            OPENAI_HOST,
            443,
            timeout=timeout_seconds,
            context=ssl.create_default_context(),
        )
        try:
            connection.request(
                "POST",
                OPENAI_PATH,
                body=body,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "ashare-v3-n6-ai-agent/1",
                },
            )
            response = connection.getresponse()
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            request_id = str(
                response.getheader("x-request-id") or ""
            ).strip()
            latency_ms = max(
                0,
                (time.monotonic_ns() - started_ns) // 1_000_000,
            )
        except Exception as exc:
            raise OpenAIAdapterError(
                "model_service_unavailable"
            ) from exc
        finally:
            connection.close()
        if response.status != 200:
            raise OpenAIAdapterError("model_service_unavailable")
        if len(raw) > MAX_RESPONSE_BYTES:
            raise OpenAIAdapterError("model_response_too_large")
        try:
            value = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OpenAIAdapterError("model_response_invalid") from exc
        if not isinstance(value, Mapping):
            raise OpenAIAdapterError("model_response_invalid")
        return {
            **value,
            TRANSPORT_METADATA_KEY: {
                "provider_request_id": request_id,
                "latency_ms": latency_ms,
            },
        }


class OpenAIResponsesModelAdapter:
    adapter_name = "openai_responses"
    model_version = OPENAI_MODEL

    def __init__(
        self,
        *,
        api_key: str,
        transport: ResponsesTransport | None = None,
        timeout_seconds: int = OPENAI_TIMEOUT_SECONDS,
    ) -> None:
        if not _valid_api_key(api_key):
            raise OpenAIAdapterError("model_credential_invalid")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, int)
            or not 1 <= timeout_seconds <= 120
        ):
            raise OpenAIAdapterError("model_timeout_invalid")
        self._api_key = api_key
        self._transport = transport or FixedOpenAIResponsesTransport()
        self._timeout_seconds = timeout_seconds
        self._last_call_metadata: dict[str, Any] = {}

    @property
    def last_call_metadata(self) -> Mapping[str, Any]:
        return dict(self._last_call_metadata)

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str],
        *,
        transport: ResponsesTransport | None = None,
    ) -> "OpenAIResponsesModelAdapter":
        _validate_environment(environ)
        api_key = _read_api_key_file(
            environ.get(OPENAI_API_KEY_FILE_ENV)
        )
        return cls(api_key=api_key, transport=transport)

    def generate_decision(
        self, context: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        request = {
            "model": OPENAI_MODEL,
            "instructions": SYSTEM_INSTRUCTIONS,
            "input": json.dumps(
                context,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ),
            "reasoning": {"effort": OPENAI_REASONING_EFFORT},
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "n6_ai_decision_v1",
                    "strict": True,
                    "schema": DECISION_JSON_SCHEMA,
                },
                "verbosity": "low",
            },
            "tools": [],
            "tool_choice": "none",
            "store": False,
            "max_output_tokens": 2000,
        }
        self._last_call_metadata = {}
        response = self._transport.create(
            api_key=self._api_key,
            payload=request,
            timeout_seconds=self._timeout_seconds,
        )
        self._last_call_metadata = _extract_call_metadata(response)
        return _parse_completed_output(response)


def _validate_environment(environ: Mapping[str, str]) -> None:
    for key in environ:
        upper = key.upper()
        if upper in FORBIDDEN_OPENAI_ENV:
            raise OpenAIAdapterError("model_environment_not_allowed")
        if upper.startswith("OPENAI_"):
            raise OpenAIAdapterError("model_environment_not_allowed")
    path_value = str(environ.get(OPENAI_API_KEY_FILE_ENV) or "")
    if not path_value:
        raise OpenAIAdapterError("model_credential_file_required")


def _read_api_key_file(value: str | None) -> str:
    path = Path(str(value or ""))
    if not path.is_absolute() or any(
        char in str(path) for char in "\x00\r\n"
    ):
        raise OpenAIAdapterError("model_credential_path_invalid")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise OpenAIAdapterError(
                "model_credential_file_unsafe"
            ) from exc
        raise OpenAIAdapterError(
            "model_credential_unavailable"
        ) from exc
    try:
        file_stat = os.fstat(descriptor)
        if (
            not stat.S_ISREG(file_stat.st_mode)
            or file_stat.st_uid != os.geteuid()
            or stat.S_IMODE(file_stat.st_mode) != 0o600
            or not 1 <= file_stat.st_size <= 512
        ):
            raise OpenAIAdapterError("model_credential_file_unsafe")
        raw = os.read(descriptor, 513)
        if len(raw) != file_stat.st_size:
            raise OpenAIAdapterError("model_credential_file_changed")
    finally:
        os.close(descriptor)
    try:
        return raw.decode("utf-8").strip()
    except UnicodeError as exc:
        raise OpenAIAdapterError("model_credential_invalid") from exc


def _valid_api_key(value: str) -> bool:
    return (
        isinstance(value, str)
        and 20 <= len(value) <= 512
        and value.startswith("sk-")
        and value.isascii()
        and not any(char.isspace() for char in value)
    )


def _parse_completed_output(
    response: Mapping[str, Any],
) -> Mapping[str, Any]:
    if response.get("status") != "completed" or response.get("error"):
        raise OpenAIAdapterError("model_response_not_completed")
    output = response.get("output")
    if not isinstance(output, list):
        raise OpenAIAdapterError("model_response_invalid")
    texts: list[str] = []
    for item in output:
        if not isinstance(item, Mapping):
            raise OpenAIAdapterError("model_response_invalid")
        if item.get("type") == "reasoning":
            continue
        if item.get("type") != "message" or item.get("status") != "completed":
            raise OpenAIAdapterError("model_response_invalid")
        content = item.get("content")
        if not isinstance(content, list):
            raise OpenAIAdapterError("model_response_invalid")
        for part in content:
            if not isinstance(part, Mapping):
                raise OpenAIAdapterError("model_response_invalid")
            if part.get("type") == "refusal":
                raise OpenAIAdapterError("model_refused")
            if part.get("type") != "output_text":
                raise OpenAIAdapterError("model_response_invalid")
            text = part.get("text")
            if not isinstance(text, str):
                raise OpenAIAdapterError("model_response_invalid")
            texts.append(text)
    if len(texts) != 1:
        raise OpenAIAdapterError("model_response_invalid")
    try:
        decision = json.loads(texts[0])
    except json.JSONDecodeError as exc:
        raise OpenAIAdapterError("model_output_invalid") from exc
    if not isinstance(decision, Mapping):
        raise OpenAIAdapterError("model_output_invalid")
    return dict(decision)


def _extract_call_metadata(
    response: Mapping[str, Any],
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "provider": "openai",
        "model": OPENAI_MODEL,
    }
    transport = response.get(TRANSPORT_METADATA_KEY)
    if isinstance(transport, Mapping):
        request_id = str(
            transport.get("provider_request_id") or ""
        ).strip()
        latency_ms = transport.get("latency_ms")
        if (
            request_id
            and len(request_id) <= 200
            and request_id.isascii()
            and all(char.isalnum() or char in "_-" for char in request_id)
        ):
            metadata["provider_request_id"] = request_id
        if (
            isinstance(latency_ms, int)
            and not isinstance(latency_ms, bool)
            and 0 <= latency_ms <= 600_000
        ):
            metadata["latency_ms"] = latency_ms
    response_id = str(response.get("id") or "").strip()
    if (
        response_id
        and len(response_id) <= 200
        and response_id.isascii()
        and all(char.isalnum() or char in "_-" for char in response_id)
    ):
        metadata["response_id"] = response_id
    usage = response.get("usage")
    if isinstance(usage, Mapping):
        for source, target in (
            ("input_tokens", "input_tokens"),
            ("output_tokens", "output_tokens"),
            ("total_tokens", "total_tokens"),
        ):
            value = usage.get(source)
            if (
                isinstance(value, int)
                and not isinstance(value, bool)
                and 0 <= value <= 100_000_000
            ):
                metadata[target] = value
    return metadata
