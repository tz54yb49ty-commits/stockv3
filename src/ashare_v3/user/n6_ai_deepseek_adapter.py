"""Fixed-endpoint DeepSeek Chat Completions adapter for N6 shadow."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import errno
import http.client
import json
import os
from pathlib import Path
import re
import secrets
import ssl
import stat
import time
from typing import Any, Protocol


DEEPSEEK_MODEL_PROVIDER = "deepseek_v4_pro"
DEEPSEEK_MODEL_PROVIDER_ENV = "ASHARE_V3_N6_AI_MODEL_PROVIDER"
DEEPSEEK_API_KEY_FILE_ENV = (
    "ASHARE_V3_N6_AI_DEEPSEEK_API_KEY_FILE"
)
DEEPSEEK_EGRESS_MODE_ENV = "ASHARE_V3_N6_AI_DEEPSEEK_EGRESS_MODE"
DEEPSEEK_EGRESS_SYNTHETIC_ONLY = "synthetic_only"
DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW = "pseudonymous_shadow_v1"
DEEPSEEK_SYSTEM_FINGERPRINT_ENV = (
    "ASHARE_V3_N6_AI_DEEPSEEK_SYSTEM_FINGERPRINT"
)
LEGACY_OPENAI_API_KEY_FILE_ENV = (
    "ASHARE_V3_N6_AI_OPENAI_API_KEY_FILE"
)
DEEPSEEK_API_KEY_FILE = Path(
    "/Users/chuanfuchen/.config/ashare-v3/deepseek/"
    "n6_ai_agent_api_key"
)
DEEPSEEK_FINGERPRINT_PAUSE_FILE = Path(
    "/Users/chuanfuchen/.local/state/ashare-v3/n6-ai-agent/"
    "deepseek_system_fingerprint.paused"
)
DEEPSEEK_MODEL = "deepseek-v4-pro"
DEEPSEEK_HOST = "api.deepseek.com"
DEEPSEEK_PATH = "/chat/completions"
DEEPSEEK_REASONING_EFFORT = "high"
DEEPSEEK_TIMEOUT_SECONDS = 120
DEEPSEEK_MAX_TOKENS = 8192
DEEPSEEK_USER_ID = "n6_ai_agent_shadow_v1"
MAX_REQUEST_BYTES = 1_048_576
MAX_RESPONSE_BYTES = 1_048_576
TRANSPORT_METADATA_KEY = "_n6_transport_metadata"
SYSTEM_CA_BUNDLE = Path("/etc/ssl/cert.pem")
SSL_KEY_LOG_FILE_ENV = "SSLKEYLOGFILE"
SYNTHETIC_NETWORK_CANARY_CONTEXT: Mapping[str, Any] = {
    "synthetic_network_canary": True,
}

_PROVIDER_OUTPUT_FIELDS = frozenset(
    {
        "context_token",
        "decision_type",
        "asset_token",
        "source_signal_token",
        "source_position_token",
        "confidence",
        "reason_summary",
        "evidence",
        "counter_evidence",
        "risk_assessment",
        "strategy_candidate_notes",
    }
)
_RISK_ASSESSMENT_FIELDS = frozenset({"trigger", "level", "summary"})
_FORBIDDEN_MODEL_ENV = frozenset(
    {
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_BASE_URL",
        "DEEPSEEK_HOST",
        "DEEPSEEK_MODEL",
        "DEEPSEEK_PROXY",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_MODEL",
        "OPENAI_PROXY",
        SSL_KEY_LOG_FILE_ENV,
    }
)

DECISION_JSON_EXAMPLE: Mapping[str, Any] = {
    "context_token": "context_0123456789abcdef0123456789abcdef",
    "decision_type": "hold",
    "asset_token": None,
    "source_signal_token": None,
    "source_position_token": None,
    "confidence": "0.50",
    "reason_summary": "Insufficient approved evidence; keep observing.",
    "evidence": [],
    "counter_evidence": ["missing_trade_evidence"],
    "risk_assessment": {
        "trigger": "none",
        "level": "low",
        "summary": "No simulated trade proposal.",
    },
    "strategy_candidate_notes": None,
}
_DECISION_JSON_EXAMPLE_TEXT = json.dumps(
    DECISION_JSON_EXAMPLE,
    ensure_ascii=True,
    sort_keys=True,
    separators=(",", ":"),
)
SYSTEM_INSTRUCTIONS = f"""\
You are the N6 paper-only AI investor. Use only the supplied pseudonymous json.
Return exactly one json object with exactly the fields shown in the complete
example below. asset_token, source_signal_token, and source_position_token are
opaque one-call tokens; never invent, transform, decode, or combine them.
Never infer or output a real identity, code, date, time, database ID, price,
quantity, money amount, credential, hidden reasoning, hash, strategy, or fact
absent from the pseudonymous input.
Free-text fields must not contain digits, hexadecimal identifiers, canonical
identity/reference prefixes, or any supplied ephemeral token.
A buy requires a supplied buy signal token. A sell requires a supplied
position token and an allowed sell trigger. When evidence is insufficient,
return hold. Reasons must be concise and auditable.
Field rules: context_token must exactly echo the supplied context_token;
decision_type is buy, sell, or hold; asset_token is null or one exact supplied
asset_token; source_signal_token is null or one exact supplied signal_token;
source_position_token is null or one exact supplied position_token; confidence
is between 0 and 1; evidence and counter_evidence are arrays of strings.
Evidence for a selected signal must contain the exact string
signal:<signal_token>, and evidence for a selected position must contain the
exact string position:<position_token>. risk_assessment contains only trigger,
level, and summary; trigger is signal, portfolio_risk, stop_loss, or none;
level is low, medium, high, or critical. Do not add any other field.
Complete json output example:
{_DECISION_JSON_EXAMPLE_TEXT}
"""

_SAFE_FINGERPRINT_CHARACTERS = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789._:-"
)
_SAFE_ACTION_STATES = frozenset(
    {"eligible", "executed", "blocked", "skipped", "expired"}
)
_SAFE_STOP_STATES = frozenset(
    {"not_ready", "frozen", "armed", "triggered", "disabled"}
)
_EPHEMERAL_TOKEN_RE = re.compile(
    r"(?:context|asset|signal|position|market)_[0-9a-f]{32}",
    re.IGNORECASE,
)
_RESERVED_REFERENCE_RE = re.compile(
    r"(?:stock|index|board|projection|position|signal):",
    re.IGNORECASE,
)
_SENSITIVE_HEX_RE = re.compile(
    r"(?<![0-9a-f])(?:[0-9a-f]{32}|[0-9a-f]{40}|[0-9a-f]{64})"
    r"(?![0-9a-f])",
    re.IGNORECASE,
)
_PROVIDER_TOP_LEVEL_FIELDS = frozenset(
    {
        "egress_contract",
        "context_token",
        "context_scope",
        "signals",
        "market_context",
        "positions",
        "portfolio",
        "decision_policy",
    }
)
_PROVIDER_SIGNAL_FIELDS = frozenset(
    {
        "signal_token",
        "asset_token",
        "direction",
        "action_state",
        "action_mark",
        "primary_trigger_period",
        "all_trigger_periods",
        "buy_expected_return_band",
        "sell_expected_return_band",
        "score_band",
        "pe_core_band",
    }
)
_PROVIDER_MARKET_FIELDS = frozenset(
    {
        "market_token",
        "asset_token",
        "asset_kind",
        "direction",
        "action_state",
        "action_mark",
        "primary_trigger_period",
        "all_trigger_periods",
    }
)
_PROVIDER_POSITION_FIELDS = frozenset(
    {
        "position_token",
        "asset_token",
        "sellable",
        "available_ratio_band",
        "exposure_ratio_band",
        "stop_loss_status",
        "quote_fresh",
    }
)
_PROVIDER_PORTFOLIO_FIELDS = frozenset(
    {
        "cash_ratio_bucket",
        "market_exposure_bucket",
        "drawdown_bucket",
        "daily_buy_activity_bucket",
        "post_canary_phase",
    }
)
_PROVIDER_DECISION_POLICY_FIELDS = frozenset(
    {
        "buy_requires_current_signal",
        "sell_requires_owned_position",
        "t_plus_one",
        "paper_only",
    }
)
_RETURN_BANDS = frozenset(
    {
        "unavailable",
        "negative",
        "very_low",
        "low",
        "medium",
        "high",
        "very_high",
    }
)
_SCORE_BANDS = frozenset(
    {"unavailable", "low", "medium", "high", "very_high"}
)
_PE_BANDS = frozenset(
    {
        "unavailable",
        "nonpositive",
        "low",
        "medium",
        "high",
        "very_high",
    }
)
_RATIO_BANDS = frozenset(
    {
        "unavailable",
        "zero",
        "very_low",
        "low",
        "moderate",
        "high",
        "very_high",
    }
)


class DeepSeekAdapterError(RuntimeError):
    """Stable fail-closed error without provider or secret detail."""


class ChatCompletionsTransport(Protocol):
    def create(
        self,
        *,
        api_key: str,
        payload: Mapping[str, Any],
        timeout_seconds: int,
    ) -> Mapping[str, Any]:
        ...


class FixedDeepSeekChatCompletionsTransport:
    """Direct TLS transport; no proxy, redirect, retry, or custom URL."""

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
        if len(body) > MAX_REQUEST_BYTES:
            raise DeepSeekAdapterError("model_request_too_large")
        started_ns = time.monotonic_ns()
        connection: http.client.HTTPSConnection | None = None
        try:
            connection = http.client.HTTPSConnection(
                DEEPSEEK_HOST,
                443,
                timeout=timeout_seconds,
                context=_fixed_tls_context(),
            )
            connection.request(
                "POST",
                DEEPSEEK_PATH,
                body=body,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "ashare-v3-n6-ai-agent/1",
                },
            )
            response = connection.getresponse()
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            latency_ms = max(
                0,
                (time.monotonic_ns() - started_ns) // 1_000_000,
            )
        except DeepSeekAdapterError:
            raise
        except Exception:
            raise DeepSeekAdapterError(
                "model_service_unavailable"
            ) from None
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass
        if response.status != 200:
            raise DeepSeekAdapterError("model_service_unavailable")
        if len(raw) > MAX_RESPONSE_BYTES:
            raise DeepSeekAdapterError("model_response_too_large")
        try:
            value = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise DeepSeekAdapterError(
                "model_response_invalid"
            ) from None
        if not isinstance(value, Mapping):
            raise DeepSeekAdapterError("model_response_invalid")
        return {
            **value,
            TRANSPORT_METADATA_KEY: {"latency_ms": latency_ms},
        }


class DeepSeekChatCompletionsModelAdapter:
    adapter_name = "deepseek_chat_completions"
    model_version = DEEPSEEK_MODEL

    def __init__(
        self,
        *,
        api_key: str,
        transport: ChatCompletionsTransport | None = None,
        timeout_seconds: int = DEEPSEEK_TIMEOUT_SECONDS,
        egress_mode: str = DEEPSEEK_EGRESS_SYNTHETIC_ONLY,
        expected_system_fingerprint: str | None = None,
    ) -> None:
        if not _valid_api_key(api_key):
            raise DeepSeekAdapterError("model_credential_invalid")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, int)
            or timeout_seconds != DEEPSEEK_TIMEOUT_SECONDS
        ):
            raise DeepSeekAdapterError("model_timeout_invalid")
        if egress_mode not in {
            DEEPSEEK_EGRESS_SYNTHETIC_ONLY,
            DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
        }:
            raise DeepSeekAdapterError("model_egress_mode_invalid")
        expected_fingerprint = (
            None
            if expected_system_fingerprint is None
            else validate_system_fingerprint(
                expected_system_fingerprint
            )
        )
        if (
            egress_mode == DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW
            and expected_fingerprint is None
        ):
            raise DeepSeekAdapterError(
                "model_system_fingerprint_required"
            )
        validate_tls_runtime()
        self._api_key = api_key
        self._transport = (
            transport or FixedDeepSeekChatCompletionsTransport()
        )
        self._timeout_seconds = timeout_seconds
        self._egress_mode = egress_mode
        self._expected_system_fingerprint = expected_fingerprint
        self._last_call_metadata: dict[str, Any] = {}

    @property
    def last_call_metadata(self) -> Mapping[str, Any]:
        return dict(self._last_call_metadata)

    @property
    def egress_mode(self) -> str:
        return self._egress_mode

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str],
        *,
        transport: ChatCompletionsTransport | None = None,
    ) -> "DeepSeekChatCompletionsModelAdapter":
        _validate_environment(environ)
        api_key = _read_api_key_file(
            environ.get(DEEPSEEK_API_KEY_FILE_ENV)
        )
        return cls(
            api_key=api_key,
            transport=transport,
            egress_mode=str(
                environ.get(DEEPSEEK_EGRESS_MODE_ENV)
                or DEEPSEEK_EGRESS_SYNTHETIC_ONLY
            ),
            expected_system_fingerprint=(
                str(environ.get(DEEPSEEK_SYSTEM_FINGERPRINT_ENV))
                if environ.get(DEEPSEEK_SYSTEM_FINGERPRINT_ENV)
                is not None
                else None
            ),
        )

    def generate_decision(
        self, context: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        is_synthetic = context == SYNTHETIC_NETWORK_CANARY_CONTEXT
        if (
            self._egress_mode == DEEPSEEK_EGRESS_SYNTHETIC_ONLY
            and not is_synthetic
        ):
            raise DeepSeekAdapterError("real_data_egress_blocked")
        provider_context, token_map = _privacy_project_context(
            context,
            synthetic=is_synthetic,
        )
        request = {
            "model": DEEPSEEK_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                {
                    "role": "user",
                    "content": json.dumps(
                        provider_context,
                        ensure_ascii=True,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                },
            ],
            "thinking": {"type": "enabled"},
            "reasoning_effort": DEEPSEEK_REASONING_EFFORT,
            "response_format": {"type": "json_object"},
            "stream": False,
            "tools": [],
            "tool_choice": "none",
            "max_tokens": DEEPSEEK_MAX_TOKENS,
            "user_id": DEEPSEEK_USER_ID,
        }
        request_bytes = json.dumps(
            request,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(request_bytes) > MAX_REQUEST_BYTES:
            raise DeepSeekAdapterError("model_request_too_large")
        self._last_call_metadata = {}
        try:
            response = self._transport.create(
                api_key=self._api_key,
                payload=request,
                timeout_seconds=self._timeout_seconds,
            )
        except DeepSeekAdapterError:
            raise
        except Exception:
            raise DeepSeekAdapterError(
                "model_service_unavailable"
            ) from None
        self._last_call_metadata = _extract_call_metadata(response)
        try:
            _validate_response_identity(
                response,
                expected_system_fingerprint=(
                    self._expected_system_fingerprint
                    if self._egress_mode
                    == DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW
                    else None
                ),
            )
        except DeepSeekAdapterError as exc:
            if (
                self._egress_mode
                == DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW
                and str(exc) == "model_identity_mismatch"
            ):
                create_fingerprint_pause_marker()
            raise
        provider_decision = _parse_completed_output(response)
        return _remap_provider_decision(
            provider_decision,
            token_map=token_map,
        )


def _validate_environment(environ: Mapping[str, str]) -> None:
    if (
        str(environ.get(DEEPSEEK_MODEL_PROVIDER_ENV) or "")
        != DEEPSEEK_MODEL_PROVIDER
    ):
        raise DeepSeekAdapterError("model_provider_invalid")
    if LEGACY_OPENAI_API_KEY_FILE_ENV in environ:
        raise DeepSeekAdapterError("model_environment_not_allowed")
    for key in environ:
        upper = key.upper()
        if (
            upper in _FORBIDDEN_MODEL_ENV
            or upper.startswith("DEEPSEEK_")
            or upper.startswith("OPENAI_")
            or upper.startswith("ASHARE_V3_N6_AI_OPENAI_")
            or (
                upper.startswith("ASHARE_V3_N6_AI_DEEPSEEK_")
                and upper
                not in {
                    DEEPSEEK_API_KEY_FILE_ENV,
                    DEEPSEEK_EGRESS_MODE_ENV,
                    DEEPSEEK_SYSTEM_FINGERPRINT_ENV,
                }
            )
            or (
                upper.startswith("ASHARE_V3_N6_AI_MODEL_")
                and upper != DEEPSEEK_MODEL_PROVIDER_ENV
            )
        ):
            raise DeepSeekAdapterError("model_environment_not_allowed")
    path_value = str(environ.get(DEEPSEEK_API_KEY_FILE_ENV) or "")
    if path_value != str(DEEPSEEK_API_KEY_FILE):
        raise DeepSeekAdapterError("model_credential_path_invalid")
    egress_mode = str(
        environ.get(DEEPSEEK_EGRESS_MODE_ENV)
        or DEEPSEEK_EGRESS_SYNTHETIC_ONLY
    )
    if egress_mode not in {
        DEEPSEEK_EGRESS_SYNTHETIC_ONLY,
        DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
    }:
        raise DeepSeekAdapterError("model_egress_mode_invalid")
    fingerprint = environ.get(DEEPSEEK_SYSTEM_FINGERPRINT_ENV)
    if fingerprint is not None:
        validate_system_fingerprint(str(fingerprint))
    if (
        egress_mode == DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW
        and fingerprint is None
    ):
        raise DeepSeekAdapterError(
            "model_system_fingerprint_required"
        )


def validate_system_ca_bundle() -> None:
    """Require one fixed root-owned system trust bundle."""

    try:
        metadata = os.lstat(SYSTEM_CA_BUNDLE)
    except OSError:
        raise DeepSeekAdapterError(
            "model_tls_trust_unavailable"
        ) from None
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != 0
        or stat.S_IMODE(metadata.st_mode)
        & (stat.S_IWGRP | stat.S_IWOTH)
        or not 1_024 <= metadata.st_size <= 5_000_000
    ):
        raise DeepSeekAdapterError("model_tls_trust_unsafe")


def validate_tls_environment() -> None:
    """Reject process-wide TLS key logging before any connection."""

    if SSL_KEY_LOG_FILE_ENV in os.environ:
        raise DeepSeekAdapterError(
            "model_tls_environment_not_allowed"
        )


def validate_tls_runtime() -> None:
    """Construct the fixed TLS context without making a network call."""

    _fixed_tls_context()


def _fixed_tls_context() -> ssl.SSLContext:
    validate_tls_environment()
    validate_system_ca_bundle()
    try:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(
            cafile=str(SYSTEM_CA_BUNDLE)
        )
    except (OSError, ssl.SSLError, ValueError):
        raise DeepSeekAdapterError(
            "model_tls_trust_unavailable"
        ) from None
    if (
        not context.check_hostname
        or context.verify_mode != ssl.CERT_REQUIRED
        or getattr(context, "keylog_filename", None) is not None
    ):
        raise DeepSeekAdapterError("model_tls_context_unsafe")
    return context


def _read_api_key_file(value: str | None) -> str:
    if str(value or "") != str(DEEPSEEK_API_KEY_FILE):
        raise DeepSeekAdapterError("model_credential_path_invalid")
    path = DEEPSEEK_API_KEY_FILE
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise DeepSeekAdapterError(
                "model_credential_file_unsafe"
            ) from None
        raise DeepSeekAdapterError(
            "model_credential_unavailable"
        ) from None
    try:
        try:
            file_stat = os.fstat(descriptor)
            if (
                not stat.S_ISREG(file_stat.st_mode)
                or file_stat.st_uid != os.geteuid()
                or stat.S_IMODE(file_stat.st_mode) != 0o600
                or not 20 <= file_stat.st_size <= 512
            ):
                raise DeepSeekAdapterError(
                    "model_credential_file_unsafe"
                )
            raw = os.read(descriptor, 513)
            if len(raw) != file_stat.st_size:
                raise DeepSeekAdapterError(
                    "model_credential_file_changed"
                )
            file_stat_after = os.fstat(descriptor)
            if (
                file_stat_after.st_dev != file_stat.st_dev
                or file_stat_after.st_ino != file_stat.st_ino
                or file_stat_after.st_size != file_stat.st_size
                or file_stat_after.st_mtime_ns
                != file_stat.st_mtime_ns
                or file_stat_after.st_ctime_ns
                != file_stat.st_ctime_ns
            ):
                raise DeepSeekAdapterError(
                    "model_credential_file_changed"
                )
        except DeepSeekAdapterError:
            raise
        except OSError:
            raise DeepSeekAdapterError(
                "model_credential_unavailable"
            ) from None
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass
    try:
        api_key = raw.decode("ascii")
    except UnicodeError:
        raise DeepSeekAdapterError(
            "model_credential_invalid"
        ) from None
    if not _valid_api_key(api_key):
        raise DeepSeekAdapterError("model_credential_invalid")
    return api_key


def _valid_api_key(value: str) -> bool:
    return (
        isinstance(value, str)
        and 20 <= len(value) <= 512
        and value.isascii()
        and all(33 <= ord(character) <= 126 for character in value)
    )


@dataclass(frozen=True, slots=True)
class _PrivacyTokenMap:
    context_token: str
    assets: dict[str, str]
    signals: dict[str, dict[str, Any]]
    positions: dict[str, dict[str, Any]]


def validate_system_fingerprint(value: str) -> str:
    """Return one safe, nonempty provider fingerprint."""

    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 200
        or not value.isascii()
        or any(
            character not in _SAFE_FINGERPRINT_CHARACTERS
            for character in value
        )
    ):
        raise DeepSeekAdapterError(
            "model_system_fingerprint_invalid"
        )
    return value


def fingerprint_pause_marker_active() -> bool:
    """Treat any object at the fixed pause path as an active fail-closed gate."""

    try:
        os.lstat(DEEPSEEK_FINGERPRINT_PAUSE_FILE)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return True


def create_fingerprint_pause_marker() -> None:
    """Atomically install the fixed 0600 pause marker without provider detail."""

    target = DEEPSEEK_FINGERPRINT_PAUSE_FILE
    parent = target.parent
    try:
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        parent_metadata = os.lstat(parent)
        if (
            not stat.S_ISDIR(parent_metadata.st_mode)
            or parent_metadata.st_uid != os.geteuid()
            or stat.S_IMODE(parent_metadata.st_mode)
            & (stat.S_IWGRP | stat.S_IWOTH)
        ):
            raise DeepSeekAdapterError(
                "model_pause_marker_directory_unsafe"
            )
        temporary = parent / (
            f".{target.name}.{os.getpid()}.{secrets.token_hex(12)}"
        )
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
        )
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(temporary, flags, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
            payload = b"deepseek_system_fingerprint_changed\n"
            if os.write(descriptor, payload) != len(payload):
                raise OSError("short_write")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, target)
        marker_metadata = os.lstat(target)
        if (
            not stat.S_ISREG(marker_metadata.st_mode)
            or marker_metadata.st_uid != os.geteuid()
            or stat.S_IMODE(marker_metadata.st_mode) != 0o600
        ):
            raise DeepSeekAdapterError(
                "model_pause_marker_unsafe"
            )
        directory_flags = (
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        if hasattr(os, "O_NOFOLLOW"):
            directory_flags |= os.O_NOFOLLOW
        directory_descriptor = os.open(parent, directory_flags)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except DeepSeekAdapterError:
        raise
    except OSError:
        raise DeepSeekAdapterError(
            "model_pause_marker_unavailable"
        ) from None
    finally:
        temporary_value = locals().get("temporary")
        if isinstance(temporary_value, Path):
            try:
                temporary_value.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass


def _privacy_project_context(
    context: Mapping[str, Any],
    *,
    synthetic: bool,
) -> tuple[dict[str, Any], _PrivacyTokenMap]:
    if not isinstance(context, Mapping):
        raise DeepSeekAdapterError("model_context_invalid")
    if synthetic:
        if context != SYNTHETIC_NETWORK_CANARY_CONTEXT:
            raise DeepSeekAdapterError("synthetic_context_invalid")
        used_tokens: set[str] = set()
        context_token = _new_token("context", used_tokens)
        payload = {
            "egress_contract": "synthetic_canary_v1",
            "context_token": context_token,
            "context_scope": "synthetic_only",
            "signals": [],
            "market_context": [],
            "positions": [],
            "portfolio": {
                "cash_ratio_bucket": "unavailable",
                "market_exposure_bucket": "unavailable",
                "drawdown_bucket": "unavailable",
                "daily_buy_activity_bucket": "unavailable",
                "post_canary_phase": False,
            },
            "decision_policy": {
                "buy_requires_current_signal": True,
                "sell_requires_owned_position": True,
                "t_plus_one": True,
                "paper_only": True,
            },
        }
        _assert_provider_payload_privacy(payload)
        return payload, _PrivacyTokenMap(
            context_token, {}, {}, {}
        )

    used_tokens: set[str] = set()
    context_token = _new_token("context", used_tokens)
    asset_token_by_identity: dict[str, str] = {}
    asset_identity_by_token: dict[str, str] = {}
    signal_map: dict[str, dict[str, Any]] = {}
    position_map: dict[str, dict[str, Any]] = {}

    def asset_token(identity_value: Any) -> str:
        identity = str(identity_value or "")
        if not identity or len(identity) > 200:
            raise DeepSeekAdapterError("model_context_invalid")
        token = asset_token_by_identity.get(identity)
        if token is None:
            token = _new_token("asset", used_tokens)
            asset_token_by_identity[identity] = token
            asset_identity_by_token[token] = identity
        return token

    portfolio = context.get("portfolio")
    if not isinstance(portfolio, Mapping):
        raise DeepSeekAdapterError("model_context_invalid")
    total_equity = _decimal_or_none(portfolio.get("total_equity"))
    market_value = _decimal_or_none(portfolio.get("market_value"))
    cash_balance = _decimal_or_none(portfolio.get("cash_balance"))

    provider_signals: list[dict[str, Any]] = []
    raw_signals = context.get("signals")
    if not isinstance(raw_signals, list):
        raise DeepSeekAdapterError("model_context_invalid")
    seen_signal_ids: set[int] = set()
    for raw in raw_signals:
        if not isinstance(raw, Mapping):
            raise DeepSeekAdapterError("model_context_invalid")
        source_id = _positive_source_id(
            raw.get("user_signal_projection_id")
        )
        if source_id in seen_signal_ids:
            raise DeepSeekAdapterError("model_context_invalid")
        seen_signal_ids.add(source_id)
        direction = str(raw.get("direction") or "")
        if direction not in {"buy", "sell"}:
            raise DeepSeekAdapterError("model_context_invalid")
        signal_token = _new_token("signal", used_tokens)
        selected_asset_token = asset_token(raw.get("identity_key"))
        signal_map[signal_token] = {
            "source_id": source_id,
            "identity_key": asset_identity_by_token[
                selected_asset_token
            ],
            "asset_token": selected_asset_token,
            "direction": direction,
        }
        provider_signals.append(
            {
                "signal_token": signal_token,
                "asset_token": selected_asset_token,
                "direction": direction,
                "action_state": _action_state_bucket(
                    raw.get("action_state")
                ),
                "action_mark": _action_mark_bucket(
                    raw.get("reason_fields")
                ),
                "primary_trigger_period": _primary_period_bucket(
                    raw.get("reason_fields")
                ),
                "all_trigger_periods": _trigger_periods_bucket(
                    raw.get("reason_fields")
                ),
                "buy_expected_return_band": _numeric_band(
                    raw.get("reason_fields"),
                    ("buy_expected_return_pct", "buy_return"),
                ),
                "sell_expected_return_band": _numeric_band(
                    raw.get("reason_fields"),
                    ("sell_expected_return_pct", "sell_return"),
                ),
                "score_band": _score_band(
                    raw.get("reason_fields")
                ),
                "pe_core_band": _pe_band(
                    raw.get("reason_fields")
                ),
            }
        )

    provider_market_context: list[dict[str, Any]] = []
    raw_market_context = context.get("market_context", [])
    if not isinstance(raw_market_context, list):
        raise DeepSeekAdapterError("model_context_invalid")
    for raw in raw_market_context:
        if not isinstance(raw, Mapping):
            raise DeepSeekAdapterError("model_context_invalid")
        asset_kind = str(raw.get("asset_kind") or "")
        direction = str(raw.get("direction") or "")
        if (
            asset_kind not in {"index", "board"}
            or direction not in {"buy", "sell"}
        ):
            raise DeepSeekAdapterError("model_context_invalid")
        provider_market_context.append(
            {
                "market_token": _new_token("market", used_tokens),
                "asset_token": asset_token(raw.get("identity_key")),
                "asset_kind": asset_kind,
                "direction": direction,
                "action_state": _action_state_bucket(
                    raw.get("action_state")
                ),
                "action_mark": _action_mark_bucket(
                    raw.get("reason_fields")
                ),
                "primary_trigger_period": _primary_period_bucket(
                    raw.get("reason_fields")
                ),
                "all_trigger_periods": _trigger_periods_bucket(
                    raw.get("reason_fields")
                ),
            }
        )

    provider_positions: list[dict[str, Any]] = []
    raw_positions = context.get("positions")
    if not isinstance(raw_positions, list):
        raise DeepSeekAdapterError("model_context_invalid")
    seen_position_ids: set[int] = set()
    for raw in raw_positions:
        if not isinstance(raw, Mapping):
            raise DeepSeekAdapterError("model_context_invalid")
        source_id = _positive_source_id(
            raw.get("virtual_position_id")
        )
        if source_id in seen_position_ids:
            raise DeepSeekAdapterError("model_context_invalid")
        seen_position_ids.add(source_id)
        position_token = _new_token("position", used_tokens)
        selected_asset_token = asset_token(raw.get("identity_key"))
        position_map[position_token] = {
            "source_id": source_id,
            "identity_key": asset_identity_by_token[
                selected_asset_token
            ],
            "asset_token": selected_asset_token,
        }
        quantity = _decimal_or_none(raw.get("quantity"))
        available = _decimal_or_none(raw.get("available_quantity"))
        position_value = _decimal_or_none(raw.get("market_value"))
        provider_positions.append(
            {
                "position_token": position_token,
                "asset_token": selected_asset_token,
                "sellable": bool(
                    available is not None and available > 0
                ),
                "available_ratio_band": _ratio_bucket(
                    available, quantity
                ),
                "exposure_ratio_band": _ratio_bucket(
                    position_value, total_equity
                ),
                "stop_loss_status": _stop_loss_bucket(
                    raw.get("stop_loss_status")
                ),
                "quote_fresh": (
                    str(raw.get("quote_quality_status") or "")
                    == "passed"
                ),
            }
        )

    payload = {
        "egress_contract": "n6_deepseek_privacy_projection_v1",
        "context_token": context_token,
        "context_scope": DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
        "signals": provider_signals,
        "market_context": provider_market_context,
        "positions": provider_positions,
        "portfolio": {
            "cash_ratio_bucket": _ratio_bucket(
                cash_balance, total_equity
            ),
            "market_exposure_bucket": _ratio_bucket(
                market_value, total_equity
            ),
            "drawdown_bucket": _drawdown_bucket(
                portfolio.get("max_drawdown_pct")
            ),
            "daily_buy_activity_bucket": _activity_bucket(
                portfolio.get("daily_new_buy_count")
            ),
            "post_canary_phase": _post_canary_phase(
                portfolio.get("autonomous_trade_day_no")
            ),
        },
        "decision_policy": {
            "buy_requires_current_signal": True,
            "sell_requires_owned_position": True,
            "t_plus_one": True,
            "paper_only": True,
        },
    }
    provider_signals.sort(key=lambda item: item["signal_token"])
    provider_market_context.sort(key=lambda item: item["market_token"])
    provider_positions.sort(key=lambda item: item["position_token"])
    _assert_provider_payload_privacy(payload)
    return payload, _PrivacyTokenMap(
        context_token,
        asset_identity_by_token,
        signal_map,
        position_map,
    )


def _new_token(prefix: str, used_tokens: set[str]) -> str:
    for _ in range(100):
        token = f"{prefix}_{secrets.token_hex(16)}"
        if token not in used_tokens:
            used_tokens.add(token)
            return token
    raise DeepSeekAdapterError("privacy_token_generation_failed")


def _positive_source_id(value: Any) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
    ):
        raise DeepSeekAdapterError("model_context_invalid")
    return value


def _decimal_or_none(value: Any) -> Decimal | None:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not result.is_finite():
        return None
    return result


def _ratio_bucket(
    numerator: Decimal | None,
    denominator: Decimal | None,
) -> str:
    if (
        numerator is None
        or denominator is None
        or denominator <= 0
        or numerator < 0
    ):
        return "unavailable"
    ratio = numerator / denominator
    if ratio == 0:
        return "zero"
    if ratio <= Decimal("0.01"):
        return "very_low"
    if ratio <= Decimal("0.05"):
        return "low"
    if ratio <= Decimal("0.10"):
        return "moderate"
    if ratio <= Decimal("0.25"):
        return "high"
    return "very_high"


def _drawdown_bucket(value: Any) -> str:
    number = _decimal_or_none(value)
    if number is None or number < 0:
        return "unavailable"
    if number == 0:
        return "none"
    if number < Decimal("2"):
        return "low"
    if number < Decimal("5"):
        return "medium"
    return "pause_threshold_or_higher"


def _activity_bucket(value: Any) -> str:
    if isinstance(value, bool):
        return "unavailable"
    try:
        number = int(value)
    except (TypeError, ValueError):
        return "unavailable"
    if number < 0:
        return "unavailable"
    if number == 0:
        return "none"
    if number == 1:
        return "one"
    if number <= 3:
        return "few"
    return "many"


def _post_canary_phase(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        return int(value) >= 3
    except (TypeError, ValueError):
        return False


def _action_state_bucket(value: Any) -> str:
    text = str(value or "")
    return text if text in _SAFE_ACTION_STATES else "other"


def _stop_loss_bucket(value: Any) -> str:
    text = str(value or "")
    return text if text in _SAFE_STOP_STATES else "other"


def _reason_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _action_mark_bucket(value: Any) -> str:
    text = str(_reason_mapping(value).get("action_mark") or "")
    return (
        text
        if text in {"normal", "30m_volume", "30m_shrink"}
        else "none"
    )


def _primary_period_bucket(value: Any) -> str:
    text = str(
        _reason_mapping(value).get("primary_trigger_period") or ""
    ).upper()
    return text if text in {"Y", "Q", "M", "W", "D"} else "none"


def _trigger_periods_bucket(value: Any) -> list[str]:
    raw = str(
        _reason_mapping(value).get("all_trigger_periods") or ""
    ).upper()
    periods = [
        period
        for period in ("Y", "Q", "M", "W", "D")
        if period in raw
    ]
    return periods


def _numeric_band(
    value: Any,
    keys: tuple[str, ...],
) -> str:
    mapping = _reason_mapping(value)
    number = None
    for key in keys:
        if key in mapping:
            number = _decimal_or_none(mapping.get(key))
            if number is not None:
                break
    if number is None:
        return "unavailable"
    if number < 0:
        return "negative"
    if number < Decimal("3"):
        return "very_low"
    if number < Decimal("8"):
        return "low"
    if number < Decimal("20"):
        return "medium"
    if number < Decimal("50"):
        return "high"
    return "very_high"


def _score_band(value: Any) -> str:
    mapping = _reason_mapping(value)
    number = _decimal_or_none(mapping.get("score"))
    if number is None:
        return "unavailable"
    if number < Decimal("40"):
        return "low"
    if number < Decimal("60"):
        return "medium"
    if number < Decimal("80"):
        return "high"
    return "very_high"


def _pe_band(value: Any) -> str:
    mapping = _reason_mapping(value)
    number = _decimal_or_none(mapping.get("pe_core"))
    if number is None:
        return "unavailable"
    if number <= 0:
        return "nonpositive"
    if number < Decimal("10"):
        return "low"
    if number < Decimal("25"):
        return "medium"
    if number < Decimal("60"):
        return "high"
    return "very_high"


def _assert_provider_payload_privacy(value: Any) -> None:
    """Validate the complete outbound schema, not a forbidden-field list."""

    payload = _exact_provider_mapping(
        value, _PROVIDER_TOP_LEVEL_FIELDS
    )
    contract = payload.get("egress_contract")
    scope = payload.get("context_scope")
    if (contract, scope) not in {
        ("synthetic_canary_v1", DEEPSEEK_EGRESS_SYNTHETIC_ONLY),
        (
            "n6_deepseek_privacy_projection_v1",
            DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
        ),
    }:
        raise DeepSeekAdapterError("privacy_projection_invalid")
    _required_provider_token(payload.get("context_token"), "context")

    signals = _provider_mapping_list(payload.get("signals"))
    for raw in signals:
        signal = _exact_provider_mapping(
            raw, _PROVIDER_SIGNAL_FIELDS
        )
        _required_provider_token(signal.get("signal_token"), "signal")
        _required_provider_token(signal.get("asset_token"), "asset")
        _require_provider_enum(
            signal.get("direction"), {"buy", "sell"}
        )
        _require_provider_enum(
            signal.get("action_state"),
            set(_SAFE_ACTION_STATES) | {"other"},
        )
        _require_provider_enum(
            signal.get("action_mark"),
            {"normal", "30m_volume", "30m_shrink", "none"},
        )
        _require_provider_enum(
            signal.get("primary_trigger_period"),
            {"Y", "Q", "M", "W", "D", "none"},
        )
        _require_provider_periods(signal.get("all_trigger_periods"))
        _require_provider_enum(
            signal.get("buy_expected_return_band"),
            _RETURN_BANDS,
        )
        _require_provider_enum(
            signal.get("sell_expected_return_band"),
            _RETURN_BANDS,
        )
        _require_provider_enum(signal.get("score_band"), _SCORE_BANDS)
        _require_provider_enum(signal.get("pe_core_band"), _PE_BANDS)

    market_context = _provider_mapping_list(
        payload.get("market_context")
    )
    for raw in market_context:
        market = _exact_provider_mapping(
            raw, _PROVIDER_MARKET_FIELDS
        )
        _required_provider_token(market.get("market_token"), "market")
        _required_provider_token(market.get("asset_token"), "asset")
        _require_provider_enum(
            market.get("asset_kind"), {"index", "board"}
        )
        _require_provider_enum(
            market.get("direction"), {"buy", "sell"}
        )
        _require_provider_enum(
            market.get("action_state"),
            set(_SAFE_ACTION_STATES) | {"other"},
        )
        _require_provider_enum(
            market.get("action_mark"),
            {"normal", "30m_volume", "30m_shrink", "none"},
        )
        _require_provider_enum(
            market.get("primary_trigger_period"),
            {"Y", "Q", "M", "W", "D", "none"},
        )
        _require_provider_periods(market.get("all_trigger_periods"))

    positions = _provider_mapping_list(payload.get("positions"))
    for raw in positions:
        position = _exact_provider_mapping(
            raw, _PROVIDER_POSITION_FIELDS
        )
        _required_provider_token(
            position.get("position_token"), "position"
        )
        _required_provider_token(position.get("asset_token"), "asset")
        if not isinstance(position.get("sellable"), bool):
            raise DeepSeekAdapterError("privacy_projection_invalid")
        if not isinstance(position.get("quote_fresh"), bool):
            raise DeepSeekAdapterError("privacy_projection_invalid")
        _require_provider_enum(
            position.get("available_ratio_band"), _RATIO_BANDS
        )
        _require_provider_enum(
            position.get("exposure_ratio_band"), _RATIO_BANDS
        )
        _require_provider_enum(
            position.get("stop_loss_status"),
            set(_SAFE_STOP_STATES) | {"other"},
        )

    portfolio = _exact_provider_mapping(
        payload.get("portfolio"), _PROVIDER_PORTFOLIO_FIELDS
    )
    _require_provider_enum(
        portfolio.get("cash_ratio_bucket"), _RATIO_BANDS
    )
    _require_provider_enum(
        portfolio.get("market_exposure_bucket"), _RATIO_BANDS
    )
    _require_provider_enum(
        portfolio.get("drawdown_bucket"),
        {
            "unavailable",
            "none",
            "low",
            "medium",
            "pause_threshold_or_higher",
        },
    )
    _require_provider_enum(
        portfolio.get("daily_buy_activity_bucket"),
        {"unavailable", "none", "one", "few", "many"},
    )
    if not isinstance(portfolio.get("post_canary_phase"), bool):
        raise DeepSeekAdapterError("privacy_projection_invalid")

    policy = _exact_provider_mapping(
        payload.get("decision_policy"),
        _PROVIDER_DECISION_POLICY_FIELDS,
    )
    if any(value is not True for value in policy.values()):
        raise DeepSeekAdapterError("privacy_projection_invalid")


def _exact_provider_mapping(
    value: Any,
    expected_fields: frozenset[str],
) -> Mapping[str, Any]:
    if (
        not isinstance(value, Mapping)
        or frozenset(value) != expected_fields
    ):
        raise DeepSeekAdapterError("privacy_projection_invalid")
    return value


def _provider_mapping_list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or any(
        not isinstance(item, Mapping) for item in value
    ):
        raise DeepSeekAdapterError("privacy_projection_invalid")
    return value


def _required_provider_token(value: Any, prefix: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != len(prefix) + 1 + 32
        or not value.startswith(f"{prefix}_")
        or any(
            character not in "0123456789abcdef"
            for character in value[len(prefix) + 1 :]
        )
    ):
        raise DeepSeekAdapterError("privacy_projection_invalid")
    return value


def _require_provider_enum(
    value: Any, allowed: frozenset[str] | set[str]
) -> None:
    if not isinstance(value, str) or value not in allowed:
        raise DeepSeekAdapterError("privacy_projection_invalid")


def _require_provider_periods(value: Any) -> None:
    if not isinstance(value, list) or value != [
        period
        for period in ("Y", "Q", "M", "W", "D")
        if period in value
    ]:
        raise DeepSeekAdapterError("privacy_projection_invalid")


def _validate_response_identity(
    response: Mapping[str, Any],
    *,
    expected_system_fingerprint: str | None,
) -> None:
    if response.get("model") != DEEPSEEK_MODEL:
        raise DeepSeekAdapterError("model_identity_mismatch")
    try:
        actual_fingerprint = validate_system_fingerprint(
            response.get("system_fingerprint")
        )
    except DeepSeekAdapterError:
        raise DeepSeekAdapterError(
            "model_identity_mismatch"
        ) from None
    if (
        expected_system_fingerprint is not None
        and actual_fingerprint != expected_system_fingerprint
    ):
        raise DeepSeekAdapterError("model_identity_mismatch")


def _parse_completed_output(
    response: Mapping[str, Any],
) -> Mapping[str, Any]:
    if response.get("error") is not None:
        raise DeepSeekAdapterError("model_response_not_completed")
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise DeepSeekAdapterError("model_response_invalid")
    choice = choices[0]
    if not isinstance(choice, Mapping):
        raise DeepSeekAdapterError("model_response_invalid")
    index = choice.get("index")
    if isinstance(index, bool) or not isinstance(index, int) or index != 0:
        raise DeepSeekAdapterError("model_response_invalid")
    if choice.get("finish_reason") != "stop":
        raise DeepSeekAdapterError("model_response_not_completed")
    message = choice.get("message")
    if not isinstance(message, Mapping):
        raise DeepSeekAdapterError("model_response_invalid")
    if message.get("role") != "assistant":
        raise DeepSeekAdapterError("model_response_invalid")
    tool_calls = message.get("tool_calls")
    if tool_calls not in (None, []):
        raise DeepSeekAdapterError("model_response_invalid")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise DeepSeekAdapterError("model_output_invalid")
    try:
        decision = json.loads(content)
    except json.JSONDecodeError:
        raise DeepSeekAdapterError("model_output_invalid") from None
    if not isinstance(decision, Mapping):
        raise DeepSeekAdapterError("model_output_invalid")
    if frozenset(decision) != _PROVIDER_OUTPUT_FIELDS:
        raise DeepSeekAdapterError("model_output_fields_invalid")
    risk = decision.get("risk_assessment")
    if (
        not isinstance(risk, Mapping)
        or frozenset(risk) != _RISK_ASSESSMENT_FIELDS
    ):
        raise DeepSeekAdapterError("model_output_fields_invalid")
    return dict(decision)


def _remap_provider_decision(
    decision: Mapping[str, Any],
    *,
    token_map: _PrivacyTokenMap,
) -> Mapping[str, Any]:
    context_token = _optional_token(
        decision.get("context_token"), "context"
    )
    if context_token != token_map.context_token:
        raise DeepSeekAdapterError("model_output_unknown_token")
    decision_type = str(decision.get("decision_type") or "")
    if decision_type not in {"buy", "sell", "hold"}:
        raise DeepSeekAdapterError("model_output_invalid")
    asset_token = _optional_token(
        decision.get("asset_token"), "asset"
    )
    signal_token = _optional_token(
        decision.get("source_signal_token"), "signal"
    )
    position_token = _optional_token(
        decision.get("source_position_token"), "position"
    )
    asset_identity = (
        None
        if asset_token is None
        else token_map.assets.get(asset_token)
    )
    signal = (
        None
        if signal_token is None
        else token_map.signals.get(signal_token)
    )
    position = (
        None
        if position_token is None
        else token_map.positions.get(position_token)
    )
    if asset_token is not None and asset_identity is None:
        raise DeepSeekAdapterError("model_output_unknown_token")
    if signal_token is not None and signal is None:
        raise DeepSeekAdapterError("model_output_unknown_token")
    if position_token is not None and position is None:
        raise DeepSeekAdapterError("model_output_unknown_token")
    risk = decision.get("risk_assessment")
    if not isinstance(risk, Mapping):
        raise DeepSeekAdapterError("model_output_invalid")
    trigger = str(risk.get("trigger") or "")
    if decision_type == "hold":
        if any(
            token is not None
            for token in (asset_token, signal_token, position_token)
        ):
            raise DeepSeekAdapterError("model_output_token_scope_invalid")
    elif asset_token is None:
        raise DeepSeekAdapterError("model_output_token_scope_invalid")
    elif decision_type == "buy":
        if (
            signal is None
            or position is not None
            or signal["asset_token"] != asset_token
            or signal["direction"] != "buy"
            or trigger != "signal"
        ):
            raise DeepSeekAdapterError(
                "model_output_token_scope_invalid"
            )
    elif (
        position is None
        or position["asset_token"] != asset_token
        or trigger
        not in {"signal", "portfolio_risk", "stop_loss"}
    ):
        raise DeepSeekAdapterError("model_output_token_scope_invalid")
    elif trigger == "signal":
        if (
            signal is None
            or signal["asset_token"] != asset_token
            or signal["direction"] != "sell"
        ):
            raise DeepSeekAdapterError(
                "model_output_token_scope_invalid"
            )
    elif signal is not None:
        raise DeepSeekAdapterError("model_output_token_scope_invalid")

    evidence = _remap_evidence(
        decision.get("evidence"),
        token_map=token_map,
    )
    _reject_ephemeral_tokens_in_text_fields(
        decision,
        token_map=token_map,
    )
    return {
        "decision_type": decision_type,
        "identity_key": asset_identity,
        "source_signal_projection_id": (
            None if signal is None else signal["source_id"]
        ),
        "source_virtual_position_id": (
            None if position is None else position["source_id"]
        ),
        "confidence": decision.get("confidence"),
        "reason_summary": decision.get("reason_summary"),
        "evidence": evidence,
        "counter_evidence": decision.get("counter_evidence"),
        "risk_assessment": dict(risk),
        "strategy_candidate_notes": decision.get(
            "strategy_candidate_notes"
        ),
    }


def _optional_token(value: Any, prefix: str) -> str | None:
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or not value.startswith(f"{prefix}_")
        or len(value) != len(prefix) + 1 + 32
        or any(
            character not in "0123456789abcdef"
            for character in value[len(prefix) + 1 :]
        )
    ):
        raise DeepSeekAdapterError("model_output_token_invalid")
    return value


def _remap_evidence(
    value: Any,
    *,
    token_map: _PrivacyTokenMap,
) -> list[Any]:
    if not isinstance(value, list):
        raise DeepSeekAdapterError("model_output_invalid")
    result: list[Any] = []
    for item in value:
        if not isinstance(item, str):
            raise DeepSeekAdapterError("model_output_invalid")
        if item.startswith("signal:"):
            token = _optional_token(item[7:], "signal")
            signal = token_map.signals.get(str(token))
            if signal is None:
                raise DeepSeekAdapterError(
                    "model_output_unknown_token"
                )
            result.append(f"projection:{signal['source_id']}")
        elif item.startswith("position:"):
            token = _optional_token(item[9:], "position")
            position = token_map.positions.get(str(token))
            if position is None:
                raise DeepSeekAdapterError(
                    "model_output_unknown_token"
                )
            result.append(f"position:{position['source_id']}")
        else:
            if not _provider_free_text_is_safe(item, token_map):
                raise DeepSeekAdapterError(
                    "model_output_token_leak"
                )
            result.append(item)
    return result


def _reject_ephemeral_tokens_in_text_fields(
    decision: Mapping[str, Any],
    *,
    token_map: _PrivacyTokenMap,
) -> None:
    values: list[Any] = [
        decision.get("reason_summary"),
        decision.get("strategy_candidate_notes"),
    ]
    counter = decision.get("counter_evidence")
    if isinstance(counter, list):
        values.extend(counter)
    risk = decision.get("risk_assessment")
    if isinstance(risk, Mapping):
        values.append(risk.get("summary"))
    if any(
        isinstance(value, str)
        and not _provider_free_text_is_safe(value, token_map)
        for value in values
    ):
        raise DeepSeekAdapterError("model_output_token_leak")


def _provider_free_text_is_safe(
    value: str,
    token_map: _PrivacyTokenMap,
) -> bool:
    return not (
        _contains_ephemeral_token(value, token_map)
        or _RESERVED_REFERENCE_RE.search(value)
        or _SENSITIVE_HEX_RE.search(value)
        or any(character.isdigit() for character in value)
    )


def _contains_ephemeral_token(
    value: str,
    token_map: _PrivacyTokenMap,
) -> bool:
    if _EPHEMERAL_TOKEN_RE.search(value):
        return True
    tokens = (
        token_map.context_token,
        *token_map.assets.keys(),
        *token_map.signals.keys(),
        *token_map.positions.keys(),
    )
    folded = value.casefold()
    return any(token.casefold() in folded for token in tokens)


def _extract_call_metadata(
    response: Mapping[str, Any],
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "provider": "deepseek",
        "model": DEEPSEEK_MODEL,
    }
    transport = response.get(TRANSPORT_METADATA_KEY)
    if isinstance(transport, Mapping):
        _copy_safe_int(
            metadata, "latency_ms", transport.get("latency_ms")
        )
    _copy_safe_text(metadata, "response_id", response.get("id"))
    _copy_safe_text(
        metadata,
        "system_fingerprint",
        response.get("system_fingerprint"),
    )
    usage = response.get("usage")
    if isinstance(usage, Mapping):
        for source, target in (
            ("prompt_tokens", "input_tokens"),
            ("completion_tokens", "output_tokens"),
            ("total_tokens", "total_tokens"),
            ("prompt_cache_hit_tokens", "prompt_cache_hit_tokens"),
            ("prompt_cache_miss_tokens", "prompt_cache_miss_tokens"),
        ):
            _copy_safe_int(metadata, target, usage.get(source))
        completion_details = usage.get("completion_tokens_details")
        if isinstance(completion_details, Mapping):
            _copy_safe_int(
                metadata,
                "reasoning_tokens",
                completion_details.get("reasoning_tokens"),
            )
    return metadata


def _copy_safe_text(
    target: dict[str, Any], key: str, value: Any
) -> None:
    if (
        isinstance(value, str)
        and 1 <= len(value) <= 200
        and value.isascii()
        and all(
            character.isalnum() or character in "._:-"
            for character in value
        )
    ):
        target[key] = value


def _copy_safe_int(
    target: dict[str, Any], key: str, value: Any
) -> None:
    if (
        isinstance(value, int)
        and not isinstance(value, bool)
        and 0 <= value <= 100_000_000
    ):
        target[key] = value
