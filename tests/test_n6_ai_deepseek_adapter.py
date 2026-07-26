from __future__ import annotations

import argparse
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import ssl
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from ashare_v3.user.ai_agent import (
    DECISION_RECORD_SQL,
    DisabledModelAdapter,
    FunctionOnlyAIAgentRepository,
    OBSERVATION_AUDIT_RECORD_SQL,
    PRODUCTION_KNOWLEDGE_MANIFEST_FILE_ENV,
    PRODUCTION_KNOWLEDGE_MANIFEST_FILE_SHA256,
    PRODUCTION_KNOWLEDGE_MANIFEST_SHA256_ENV,
    SHADOW_FEATURE_FLAG,
    SHADOW_SCHEDULE_POLICY_VERSION,
    SHADOW_SCHEDULE_SLOTS,
    ValidatedContext,
    validate_model_output,
)
from ashare_v3.user.n6_ai_deepseek_adapter import (
    DECISION_JSON_EXAMPLE,
    DEEPSEEK_API_KEY_FILE,
    DEEPSEEK_API_KEY_FILE_ENV,
    DEEPSEEK_EGRESS_MODE_ENV,
    DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
    DEEPSEEK_EGRESS_SYNTHETIC_ONLY,
    DEEPSEEK_FINGERPRINT_PAUSE_FILE,
    DEEPSEEK_HOST,
    DEEPSEEK_MAX_TOKENS,
    DEEPSEEK_MODEL,
    DEEPSEEK_MODEL_PROVIDER,
    DEEPSEEK_MODEL_PROVIDER_ENV,
    DEEPSEEK_PATH,
    DEEPSEEK_SYSTEM_FINGERPRINT_ENV,
    DEEPSEEK_TIMEOUT_SECONDS,
    DEEPSEEK_USER_ID,
    LEGACY_OPENAI_API_KEY_FILE_ENV,
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    SSL_KEY_LOG_FILE_ENV,
    SYSTEM_INSTRUCTIONS,
    SYSTEM_CA_BUNDLE,
    SYNTHETIC_NETWORK_CANARY_CONTEXT,
    DeepSeekAdapterError,
    DeepSeekChatCompletionsModelAdapter,
    FixedDeepSeekChatCompletionsTransport,
    _PROVIDER_DECISION_POLICY_FIELDS,
    _PROVIDER_MARKET_FIELDS,
    _PROVIDER_POSITION_FIELDS,
    _PROVIDER_PORTFOLIO_FIELDS,
    _PROVIDER_SIGNAL_FIELDS,
    _PROVIDER_TOP_LEVEL_FIELDS,
    _activity_bucket,
    _assert_provider_payload_privacy,
    _drawdown_bucket,
    _fixed_tls_context,
    _numeric_band,
    _pe_band,
    _ratio_bucket,
    _score_band,
    create_fingerprint_pause_marker,
    fingerprint_pause_marker_active,
    validate_system_ca_bundle,
    validate_system_fingerprint,
    validate_tls_environment,
    validate_tls_runtime,
)
from scripts.run_n6_ai_agent_once import (
    _observation_audit_factory,
    run_from_args,
)


API_KEY = "opaque-deepseek-key-" + "a" * 32
ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT / "docs/N6_AI_DEEPSEEK_V4_PRO_ADAPTER_CONTRACT.json"
)
SCHEDULE_067_CONTRACT = (
    ROOT
    / "docs/N6_AI_SHADOW_OPEN_TRADE_DATE_FOUR_SLOTS_067_CONTRACT.json"
)
SCHEDULE_071_CONTRACT = (
    ROOT
    / "docs/N6_AI_SHADOW_OPEN_TRADE_DATE_NINE_SLOTS_071_CONTRACT.json"
)
SCHEDULE_071_MIGRATION = (
    ROOT / "sql/071_n6_ai_shadow_nine_slot_schedule_preflight.sql"
)
SCHEDULE_071_ROLLBACK = (
    ROOT
    / "sql/071_n6_ai_shadow_nine_slot_schedule_preflight_rollback.sql"
)
SCHEDULE_067_CONTRACT_SHA256 = (
    "aa10f84db4af2d3024656b60f085adec7140e45f5392c5441f"
    "f92c999b5bd5dd"
)
SCHEDULE_071_MIGRATION_SHA256 = (
    "801e0a0f174c3969fc71e03850e54ea08cfecddb66d3ea145"
    "43e5176b74c1fd7"
)
SCHEDULE_071_ROLLBACK_SHA256 = (
    "4526267b2ce54df8ad09e89249f9489af78a447a552b57e40"
    "a19dcb826f0806b"
)
PRODUCTION_MANIFEST = (
    ROOT
    / "docs/N6_AI_PRODUCTION_KNOWLEDGE_BUNDLE_MANIFEST_V1.json"
)
PHASE_A_HASHES = {
    "sql/062_n6_ai_shadow_observation_run_audit.sql":
        "69e7c9b882b397aa419e26e6f96e512939db857cb2cbd4d7627415202fe3628c",
    "sql/062_n6_ai_shadow_observation_run_audit_rollback.sql":
        "5be8b6f37e6afc37d7e89bbb3ab4a3f2125ee4ef96fa6ec41e7d8545d652a173",
    "tests/test_n6_ai_shadow_observation_run_audit_schema.py":
        "acd63a21e4e1a01281c7e51ec2ae4948749ff205670977f49e60c751f52ac919",
}


def open_071_request_time() -> datetime:
    return datetime.fromisoformat("2026-07-20T10:30:30+08:00")


def decision_payload():
    return {
        "decision_type": "hold",
        "identity_key": None,
        "source_signal_projection_id": None,
        "source_virtual_position_id": None,
        "confidence": "0.50",
        "reason_summary": "证据不足，保持观察。",
        "evidence": [],
        "counter_evidence": ["missing_trade_evidence"],
        "risk_assessment": {
            "trigger": "none",
            "level": "low",
            "summary": "未申请交易。",
        },
        "strategy_candidate_notes": None,
    }


def provider_decision_payload(
    *,
    context_token="context_0123456789abcdef0123456789abcdef",
    **overrides,
):
    payload = {
        "context_token": context_token,
        "decision_type": "hold",
        "asset_token": None,
        "source_signal_token": None,
        "source_position_token": None,
        "confidence": "0.50",
        "reason_summary": "证据不足，保持观察。",
        "evidence": [],
        "counter_evidence": ["missing_trade_evidence"],
        "risk_assessment": {
            "trigger": "none",
            "level": "low",
            "summary": "未申请交易。",
        },
        "strategy_candidate_notes": None,
    }
    payload.update(overrides)
    return payload


def real_context_payload():
    return {
        "knowledge_bundle_hash": "a" * 64,
        "for_trade_date": "20260718",
        "signals": [
            {
                "user_signal_projection_id": 101,
                "identity_key": "stock:SH:600000",
                "direction": "buy",
                "action_state": "eligible",
                "event_time": "2026-07-18T10:01:00+08:00",
                "reason_fields": {
                    "condition_key": "BUY:Y,M,W,D",
                    "primary_trigger_period": "D",
                    "all_trigger_periods": "Y,M,W,D",
                    "buy_expected_return_pct": "12.34",
                    "score": "78.5",
                    "pe_core": "15.2",
                    "action_mark": "normal",
                },
            }
        ],
        "market_context": [
            {
                "user_signal_projection_id": 301,
                "asset_kind": "index",
                "identity_key": "index:SH:000300",
                "direction": "buy",
                "action_state": "eligible",
                "event_time": "2026-07-18T10:01:00+08:00",
                "reason_fields": {
                    "condition_key": "BUY_HINT:D",
                    "primary_trigger_period": "D",
                },
            }
        ],
        "positions": [
            {
                "virtual_position_id": 201,
                "identity_key": "stock:SH:600001",
                "quantity": "1000",
                "available_quantity": "800",
                "current_price": "10.12",
                "market_value": "10120",
                "quote_minute": "2026-07-18T10:02:00+08:00",
                "quote_quality_status": "passed",
                "stop_loss_status": "frozen",
            }
        ],
        "portfolio": {
            "cash_balance": "99989880",
            "total_equity": "100000000",
            "market_value": "10120",
            "max_drawdown_pct": "1.2",
            "daily_new_buy_count": 0,
            "autonomous_trade_day_no": 4,
        },
        "strategy": {
            "strategy_version": "private-v1",
            "strategy_hash": "b" * 64,
        },
        "decision_rules": {"t_plus_one": True},
        "risk_limits": {"buy_budget_cny": "300000"},
    }


def completed_response(payload=None, *, fingerprint="fp_test"):
    return {
        "id": "chatcmpl_test",
        "model": DEEPSEEK_MODEL,
        "system_fingerprint": fingerprint,
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": json.dumps(
                        payload or provider_decision_payload(),
                        ensure_ascii=False,
                    ),
                    "reasoning_content": "must_never_be_retained",
                },
            }
        ],
        "usage": {
            "prompt_tokens": 120,
            "completion_tokens": 30,
            "total_tokens": 150,
            "prompt_cache_hit_tokens": 90,
            "prompt_cache_miss_tokens": 30,
            "completion_tokens_details": {"reasoning_tokens": 20},
        },
        "_n6_transport_metadata": {"latency_ms": 321},
    }


class FakeTransport:
    def __init__(self, response=None, *, raises=False):
        self.response = response
        self.raises = raises
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.raises:
            raise RuntimeError("provider secret detail")
        if self.response is not None:
            return self.response
        request_context = json.loads(
            kwargs["payload"]["messages"][1]["content"]
        )
        return completed_response(
            provider_decision_payload(
                context_token=request_context["context_token"]
            )
        )


class SelectingTransport(FakeTransport):
    def __init__(self, decision_type="buy"):
        super().__init__()
        self.decision_type = decision_type

    def create(self, **kwargs):
        self.calls.append(kwargs)
        context = json.loads(
            kwargs["payload"]["messages"][1]["content"]
        )
        signal = context["signals"][0]
        payload = provider_decision_payload(
            context_token=context["context_token"],
            decision_type=self.decision_type,
            asset_token=signal["asset_token"],
            source_signal_token=signal["signal_token"],
            confidence="0.80",
            reason_summary="Approved pseudonymous evidence.",
            evidence=[f"signal:{signal['signal_token']}"],
            counter_evidence=["market_volatility"],
            risk_assessment={
                "trigger": "signal",
                "level": "medium",
                "summary": "Local risk recheck required.",
            },
        )
        return completed_response(payload)


class FakeHTTPResponse:
    def __init__(self, payload, *, status=200):
        self.status = status
        self.payload = payload
        self.read_limit = None

    def read(self, limit):
        self.read_limit = limit
        return self.payload


class FakeHTTPSConnection:
    def __init__(self, response, *, close_raises=False):
        self.response = response
        self.close_raises = close_raises
        self.requests = []
        self.closed = False

    def request(self, *args, **kwargs):
        self.requests.append((args, kwargs))

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True
        if self.close_raises:
            raise RuntimeError("close secret detail")


class DeepSeekChatCompletionsAdapterTest(unittest.TestCase):
    def test_request_is_fixed_json_tool_free_and_non_streaming(self):
        transport = FakeTransport()
        adapter = DeepSeekChatCompletionsModelAdapter(
            api_key=API_KEY,
            transport=transport,
            egress_mode=DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
            expected_system_fingerprint="fp_test",
        )
        context = real_context_payload()

        self.assertEqual(
            adapter.generate_decision(context), decision_payload()
        )
        self.assertEqual(len(transport.calls), 1)
        call = transport.calls[0]
        self.assertEqual(
            call["timeout_seconds"], DEEPSEEK_TIMEOUT_SECONDS
        )
        request = call["payload"]
        self.assertEqual(
            set(request),
            {
                "model",
                "messages",
                "thinking",
                "reasoning_effort",
                "response_format",
                "stream",
                "tools",
                "tool_choice",
                "max_tokens",
                "user_id",
            },
        )
        self.assertEqual(request["model"], DEEPSEEK_MODEL)
        self.assertEqual(request["thinking"], {"type": "enabled"})
        self.assertEqual(request["reasoning_effort"], "high")
        self.assertEqual(
            request["response_format"], {"type": "json_object"}
        )
        self.assertIs(request["stream"], False)
        self.assertEqual(request["tools"], [])
        self.assertEqual(request["tool_choice"], "none")
        self.assertEqual(request["max_tokens"], DEEPSEEK_MAX_TOKENS)
        self.assertEqual(request["user_id"], DEEPSEEK_USER_ID)
        provider_context = json.loads(
            request["messages"][1]["content"]
        )
        self.assertEqual(
            set(provider_context),
            {
                "egress_contract",
                "context_token",
                "context_scope",
                "signals",
                "market_context",
                "positions",
                "portfolio",
                "decision_policy",
            },
        )
        serialized = json.dumps(provider_context, sort_keys=True)
        for forbidden in (
            "stock:SH:600000",
            "stock:SH:600001",
            "index:SH:000300",
            "20260718",
            "2026-07-18",
            "300000",
            "99989880",
            "condition_key",
            "private-v1",
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        ):
            self.assertNotIn(forbidden, serialized)
        self.assertIn("signal_token", provider_context["signals"][0])
        self.assertIn(
            "position_token", provider_context["positions"][0]
        )
        self.assertIn("json", request["messages"][0]["content"])
        self.assertIn(
            json.dumps(
                DECISION_JSON_EXAMPLE,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ),
            request["messages"][0]["content"],
        )
        self.assertIn(
            "signal:<signal_token>",
            request["messages"][0]["content"],
        )
        self.assertIn(
            "position:<position_token>",
            request["messages"][0]["content"],
        )
        self.assertNotIn(API_KEY, json.dumps(request))
        for forbidden in (
            "temperature",
            "top_p",
            "store",
            "previous_response_id",
            "base_url",
            "proxy",
        ):
            self.assertNotIn(forbidden, request)

    def test_outbound_projection_has_exact_schema_and_enum_bands(self):
        transport = FakeTransport()
        adapter = DeepSeekChatCompletionsModelAdapter(
            api_key=API_KEY,
            transport=transport,
            egress_mode=DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
            expected_system_fingerprint="fp_test",
        )
        adapter.generate_decision(real_context_payload())
        projected = json.loads(
            transport.calls[0]["payload"]["messages"][1]["content"]
        )

        _assert_provider_payload_privacy(projected)
        self.assertEqual(frozenset(projected), _PROVIDER_TOP_LEVEL_FIELDS)
        self.assertEqual(
            frozenset(projected["signals"][0]),
            _PROVIDER_SIGNAL_FIELDS,
        )
        self.assertEqual(
            frozenset(projected["market_context"][0]),
            _PROVIDER_MARKET_FIELDS,
        )
        self.assertEqual(
            frozenset(projected["positions"][0]),
            _PROVIDER_POSITION_FIELDS,
        )
        self.assertEqual(
            frozenset(projected["portfolio"]),
            _PROVIDER_PORTFOLIO_FIELDS,
        )
        self.assertEqual(
            frozenset(projected["decision_policy"]),
            _PROVIDER_DECISION_POLICY_FIELDS,
        )
        for list_key, token_key in (
            ("signals", "signal_token"),
            ("market_context", "market_token"),
            ("positions", "position_token"),
        ):
            tokens = [
                item[token_key] for item in projected[list_key]
            ]
            self.assertEqual(tokens, sorted(tokens))

        with self.assertRaisesRegex(
            DeepSeekAdapterError, "privacy_projection_invalid"
        ):
            _assert_provider_payload_privacy(
                {**projected, "identity_key": "stock:SH:600000"}
            )
        invalid = json.loads(json.dumps(projected))
        invalid["signals"][0]["score_band"] = "78.5"
        with self.assertRaisesRegex(
            DeepSeekAdapterError, "privacy_projection_invalid"
        ):
            _assert_provider_payload_privacy(invalid)

    def test_numeric_privacy_bucket_boundaries_are_frozen(self):
        self.assertEqual(
            [
                _numeric_band({"v": value}, ("v",))
                for value in ("-1", "0", "3", "8", "20", "50")
            ],
            [
                "negative",
                "very_low",
                "low",
                "medium",
                "high",
                "very_high",
            ],
        )
        self.assertEqual(
            [
                _score_band({"score": value})
                for value in ("39.99", "40", "60", "80")
            ],
            ["low", "medium", "high", "very_high"],
        )
        self.assertEqual(
            [
                _pe_band({"pe_core": value})
                for value in ("0", "1", "10", "25", "60")
            ],
            [
                "nonpositive",
                "low",
                "medium",
                "high",
                "very_high",
            ],
        )
        self.assertEqual(
            [
                _ratio_bucket(Decimal(value), Decimal("100"))
                for value in ("0", "1", "5", "10", "25", "26")
            ],
            [
                "zero",
                "very_low",
                "low",
                "moderate",
                "high",
                "very_high",
            ],
        )
        self.assertEqual(
            [_drawdown_bucket(value) for value in ("0", "1", "2", "5")],
            ["none", "low", "medium", "pause_threshold_or_higher"],
        )
        self.assertEqual(
            [_activity_bucket(value) for value in (0, 1, 2, 4)],
            ["none", "one", "few", "many"],
        )

    def test_fixed_endpoint_transport_ignores_ambient_proxy(self):
        body = json.dumps(completed_response()).encode("utf-8")
        response = FakeHTTPResponse(body)
        connection = FakeHTTPSConnection(response)
        with (
            mock.patch(
                "ashare_v3.user.n6_ai_deepseek_adapter."
                "http.client.HTTPSConnection",
                return_value=connection,
            ) as factory,
            mock.patch(
                "ashare_v3.user.n6_ai_deepseek_adapter."
                "_fixed_tls_context",
                return_value=object(),
            ) as tls_context,
        ):
            value = FixedDeepSeekChatCompletionsTransport().create(
                api_key=API_KEY,
                payload={"model": DEEPSEEK_MODEL},
                timeout_seconds=DEEPSEEK_TIMEOUT_SECONDS,
            )

        self.assertEqual(DEEPSEEK_HOST, "api.deepseek.com")
        self.assertEqual(DEEPSEEK_PATH, "/chat/completions")
        self.assertEqual(factory.call_args.args[:2], (DEEPSEEK_HOST, 443))
        self.assertEqual(
            factory.call_args.kwargs["timeout"],
            DEEPSEEK_TIMEOUT_SECONDS,
        )
        tls_context.assert_called_once_with()
        self.assertEqual(connection.requests[0][0][0], "POST")
        self.assertEqual(connection.requests[0][0][1], DEEPSEEK_PATH)
        self.assertEqual(response.read_limit, MAX_RESPONSE_BYTES + 1)
        self.assertTrue(connection.closed)
        self.assertEqual(value["id"], "chatcmpl_test")

    def test_tls_uses_only_fixed_root_owned_system_ca_bundle(self):
        safe_metadata = SimpleNamespace(
            st_mode=stat.S_IFREG | 0o644,
            st_uid=0,
            st_size=333_483,
        )
        context = mock.Mock(
            check_hostname=True,
            verify_mode=ssl.CERT_REQUIRED,
            keylog_filename=None,
        )
        with (
            mock.patch(
                "ashare_v3.user.n6_ai_deepseek_adapter.os.lstat",
                return_value=safe_metadata,
            ),
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch(
                "ashare_v3.user.n6_ai_deepseek_adapter.ssl.SSLContext",
                return_value=context,
            ) as context_factory,
        ):
            self.assertIs(_fixed_tls_context(), context)
        context_factory.assert_called_once_with(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations.assert_called_once_with(
            cafile=str(SYSTEM_CA_BUNDLE)
        )

        for unsafe in (
            SimpleNamespace(
                st_mode=stat.S_IFLNK | 0o777,
                st_uid=0,
                st_size=333_483,
            ),
            SimpleNamespace(
                st_mode=stat.S_IFREG | 0o644,
                st_uid=501,
                st_size=333_483,
            ),
            SimpleNamespace(
                st_mode=stat.S_IFREG | 0o666,
                st_uid=0,
                st_size=333_483,
            ),
        ):
            with self.subTest(unsafe=unsafe):
                with mock.patch(
                    "ashare_v3.user.n6_ai_deepseek_adapter.os.lstat",
                    return_value=unsafe,
                ):
                    with self.assertRaises(DeepSeekAdapterError):
                        validate_system_ca_bundle()

    def test_tls_key_logging_is_fail_closed_and_never_configured(self):
        with mock.patch.dict(
            os.environ,
            {SSL_KEY_LOG_FILE_ENV: "/tmp/forbidden-keylog"},
            clear=True,
        ):
            with self.assertRaisesRegex(
                DeepSeekAdapterError,
                "tls_environment_not_allowed",
            ):
                validate_tls_environment()
            with self.assertRaisesRegex(
                DeepSeekAdapterError,
                "tls_environment_not_allowed",
            ):
                _fixed_tls_context()

    def test_contract_json_locks_the_provider_and_egress_gates(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(
            contract["contract_status"],
            "nine_slot_shadow_schedule_implementation_ready_not_deployed",
        )
        self.assertEqual(contract["provider"], DEEPSEEK_MODEL_PROVIDER)
        self.assertEqual(contract["request"]["model"], DEEPSEEK_MODEL)
        self.assertEqual(contract["request"]["host"], DEEPSEEK_HOST)
        self.assertEqual(contract["request"]["path"], DEEPSEEK_PATH)
        self.assertEqual(
            contract["request"]["thinking"], {"type": "enabled"}
        )
        self.assertEqual(
            contract["request"]["reasoning_effort"], "high"
        )
        self.assertEqual(
            contract["request"]["response_format"],
            {"type": "json_object"},
        )
        self.assertIs(contract["request"]["stream"], False)
        self.assertEqual(contract["request"]["tools"], [])
        self.assertEqual(contract["request"]["tool_choice"], "none")
        self.assertEqual(
            contract["request"]["max_tokens"], DEEPSEEK_MAX_TOKENS
        )
        self.assertEqual(
            contract["request"]["user_id"], DEEPSEEK_USER_ID
        )
        self.assertEqual(
            contract["request"]["timeout_seconds"],
            DEEPSEEK_TIMEOUT_SECONDS,
        )
        self.assertEqual(contract["request"]["retry_count"], 0)
        self.assertEqual(
            contract["request"]["maximum_request_bytes"],
            MAX_REQUEST_BYTES,
        )
        self.assertEqual(
            contract["endpoint_policy"]["fixed_system_ca_bundle"],
            str(SYSTEM_CA_BUNDLE),
        )
        self.assertTrue(
            contract["endpoint_policy"][
                "tls_certificate_verification"
            ]
        )
        self.assertFalse(
            contract["endpoint_policy"]["tls_key_logging_allowed"]
        )
        self.assertFalse(
            contract["endpoint_policy"][
                "ambient_sslkeylogfile_allowed"
            ]
        )
        self.assertFalse(contract["fallback"]["openai"])
        self.assertFalse(contract["runtime"]["autonomous_enabled"])
        self.assertEqual(
            contract["runtime"]["schedule_policy_version"],
            SHADOW_SCHEDULE_POLICY_VERSION,
        )
        self.assertEqual(
            contract["runtime"]["agent_start_calendar_intervals"],
            [
                {"Hour": 9, "Minute": 30},
                {"Hour": 10, "Minute": 0},
                {"Hour": 10, "Minute": 30},
                {"Hour": 11, "Minute": 0},
                {"Hour": 11, "Minute": 30},
                {"Hour": 13, "Minute": 30},
                {"Hour": 14, "Minute": 0},
                {"Hour": 14, "Minute": 30},
                {"Hour": 15, "Minute": 0},
            ],
        )
        self.assertEqual(
            contract["runtime"]["slot_recovery_windows_minutes"],
            {
                "09:30": 5,
                "10:00": 5,
                "10:30": 5,
                "11:00": 5,
                "11:30": 1,
                "13:30": 5,
                "14:00": 5,
                "14:30": 5,
                "15:00": 1,
            },
        )
        self.assertEqual(
            contract["runtime"]["provider_request_time_gate"],
            {
                "recheck_immediately_before_identity_probe": True,
                "recheck_immediately_before_decision_call": True,
                "uses_current_timezone_aware_clock_not_historical_run_at":
                    True,
                "new_request_after_window_close": False,
                "in_flight_request_may_finish_after_window_close": True,
                "clock_error_action": "fail_closed",
            },
        )
        self.assertEqual(
            contract["runtime"]["execution_order"],
            [
                "local_shanghai_slot_gate",
                "manifest_and_configuration_validation",
                "database_calendar_and_idempotency_preflight",
                "identity_probe_request_time_gate",
                "provider_identity_probe",
                "private_shadow_context_load",
                "decision_request_time_gate",
                "decision_model_call",
            ],
        )
        self.assertEqual(
            contract["runtime"]["system_fingerprint_change_action"],
            "pause_and_restart_shadow_observation_window",
        )
        self.assertEqual(
            contract["accepted_response"]["system_fingerprint"],
            {
                "synthetic_only": "required_safe_and_reported",
                "pseudonymous_shadow_v1":
                    "required_and_equal_to_reviewed_baseline",
            },
        )
        self.assertEqual(
            contract["runtime"]["provider_call_budget"],
            {
                "identity_probe_calls_per_enabled_one_shot": 1,
                "decision_calls_without_new_input": 0,
                "maximum_decision_calls_with_new_input": 1,
                "maximum_total_provider_calls_per_enabled_one_shot": 2,
                "identity_probe_is_not_a_decision_run": True,
                "maximum_identity_probe_calls_per_open_trade_date": 9,
                "maximum_decision_calls_per_open_trade_date": 9,
                "maximum_total_provider_calls_per_open_trade_date": 18,
                "automatic_retry_count": 0,
                "outside_slot_or_closed_trade_date_calls": 0,
            },
        )
        self.assertEqual(
            contract["runtime"]["provider_identity_probe_audit"],
            {
                "network_called": True,
                "decision_recorded": False,
                "proposal_created": False,
                "metadata_is_separate_from_decision_model_call": True,
            },
        )
        self.assertEqual(
            contract["data_egress"]["real_n6_status"],
            "raw_blocked_pseudonymous_shadow_implemented",
        )
        self.assertTrue(
            contract["data_egress"][
                "software_enforced_real_data_egress_gate"
            ]
        )
        self.assertTrue(
            contract["data_egress"]["runtime_control_gate_required"]
        )
        self.assertEqual(
            contract["data_egress"][
                "pseudonymous_shadow_authorization"
            ],
            {
                "current_status":
                    "blocked_until_explicit_runtime_gate",
                "accepted_authority": [
                    "written_provider_confirmation",
                    "explicit_user_acceptance_of_documented_"
                    "pseudonymous_residual_risk",
                ],
                "readiness_flag":
                    "--authorize-pseudonymous-egress",
                "raw_n6_egress_remains_blocked": True,
            },
        )
        self.assertEqual(
            contract["data_egress"]["egress_contract_values"],
            {
                "synthetic_only": "synthetic_canary_v1",
                "pseudonymous_shadow_v1":
                    "n6_deepseek_privacy_projection_v1",
            },
        )
        self.assertEqual(
            contract["data_egress"]["context_scope_values"],
            {
                "synthetic_only": "synthetic_only",
                "pseudonymous_shadow_v1":
                    DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
            },
        )
        self.assertEqual(
            contract["data_egress"]["provider_free_text_policy"],
            {
                "digits_allowed": False,
                "canonical_reference_prefixes_allowed": False,
                "ephemeral_tokens_allowed": False,
                "hex_identifier_lengths_rejected": [32, 40, 64],
            },
        )
        self.assertTrue(
            contract["data_egress"]["per_call_token_rotation"]
        )
        self.assertTrue(
            contract["data_egress"][
                "per_call_randomized_list_order"
            ]
        )
        self.assertIn(
            "not_claimed_anonymous",
            contract["data_egress"]["pseudonymous_residual_risk"],
        )
        for contract_key, expected_fields in (
            ("pseudonymous_outbound_top_level_fields",
             _PROVIDER_TOP_LEVEL_FIELDS),
            ("pseudonymous_signal_fields", _PROVIDER_SIGNAL_FIELDS),
            (
                "pseudonymous_market_context_fields",
                _PROVIDER_MARKET_FIELDS,
            ),
            (
                "pseudonymous_position_fields",
                _PROVIDER_POSITION_FIELDS,
            ),
            (
                "pseudonymous_portfolio_fields",
                _PROVIDER_PORTFOLIO_FIELDS,
            ),
            (
                "pseudonymous_decision_policy_fields",
                _PROVIDER_DECISION_POLICY_FIELDS,
            ),
        ):
            self.assertEqual(
                frozenset(
                    contract["data_egress"][contract_key]
                ),
                expected_fields,
            )
        self.assertEqual(
            contract["data_egress"]["provider_output_fields"],
            [
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
            ],
        )
        self.assertEqual(
            contract["data_egress"]["local_remap_output_fields"],
            [
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
        )

    def test_071_contract_supersedes_only_the_067_schedule(self):
        adapter_contract = json.loads(
            CONTRACT.read_text(encoding="utf-8")
        )
        schedule_contract = json.loads(
            SCHEDULE_071_CONTRACT.read_text(encoding="utf-8")
        )
        historical_contract = json.loads(
            SCHEDULE_067_CONTRACT.read_text(encoding="utf-8")
        )

        self.assertEqual(
            sha256(SCHEDULE_067_CONTRACT.read_bytes()).hexdigest(),
            SCHEDULE_067_CONTRACT_SHA256,
        )
        self.assertEqual(
            sha256(SCHEDULE_071_MIGRATION.read_bytes()).hexdigest(),
            SCHEDULE_071_MIGRATION_SHA256,
        )
        self.assertEqual(
            sha256(SCHEDULE_071_ROLLBACK.read_bytes()).hexdigest(),
            SCHEDULE_071_ROLLBACK_SHA256,
        )
        self.assertEqual(
            historical_contract["contract_id"],
            "N6_AI_SHADOW_OPEN_TRADE_DATE_FOUR_SLOTS_067",
        )
        self.assertEqual(
            historical_contract["schedule_policy_version"],
            "n6_ai_shadow_open_trade_date_four_slots_067_v1",
        )
        self.assertEqual(
            schedule_contract["status"],
            "implementation_ready_not_deployed",
        )

        supersession = schedule_contract["supersession"]
        self.assertEqual(supersession["scope"], "schedule_only")
        self.assertTrue(
            supersession["historical_067_contract_preserved"]
        )
        self.assertTrue(supersession["historical_067_sql_preserved"])
        self.assertFalse(supersession["deepseek_protocol_changed"])
        self.assertFalse(
            supersession["privacy_egress_contract_changed"]
        )
        self.assertFalse(
            supersession["risk_or_trading_authority_changed"]
        )

        expected_slots = [
            (9, 30, "09:30", 5),
            (10, 0, "10:00", 5),
            (10, 30, "10:30", 5),
            (11, 0, "11:00", 5),
            (11, 30, "11:30", 1),
            (13, 30, "13:30", 5),
            (14, 0, "14:00", 5),
            (14, 30, "14:30", 5),
            (15, 0, "15:00", 1),
        ]
        self.assertEqual(list(SHADOW_SCHEDULE_SLOTS), expected_slots)
        self.assertEqual(
            schedule_contract["schedule_policy_version"],
            SHADOW_SCHEDULE_POLICY_VERSION,
        )
        self.assertEqual(
            [row["slot"] for row in schedule_contract["deepseek_slots"]],
            [row[2] for row in expected_slots],
        )
        self.assertEqual(
            [
                row["recovery_window_minutes"]
                for row in schedule_contract["deepseek_slots"]
            ],
            [row[3] for row in expected_slots],
        )
        self.assertEqual(
            schedule_contract["provider_budget"],
            {
                "closed_date_or_outside_slot_requests": 0,
                "maximum_identity_probes_per_ready_slot": 1,
                "maximum_decision_calls_per_ready_slot": 1,
                "maximum_requests_per_ready_slot": 2,
                "no_new_input_requests_per_ready_slot": 1,
                "maximum_identity_probes_per_open_trade_date": 9,
                "maximum_decision_calls_per_open_trade_date": 9,
                "maximum_total_requests_per_open_trade_date": 18,
                "automatic_retry_count": 0,
            },
        )
        deployment_gate = schedule_contract["database_preflight"][
            "deployment_gate"
        ]
        self.assertTrue(
            deployment_gate.startswith(
                "apply_and_postflight_071_before_release"
            )
        )
        self.assertEqual(
            schedule_contract["database_preflight"]
            ["migration_file_sha256"],
            SCHEDULE_071_MIGRATION_SHA256,
        )
        self.assertEqual(
            schedule_contract["database_preflight"]
            ["rollback_file_sha256"],
            SCHEDULE_071_ROLLBACK_SHA256,
        )
        self.assertEqual(
            schedule_contract["database_preflight"]
            ["migration_pg_proc_prosrc_sha256"],
            "e3b625acaa39cecc7ac41614ea3a3a129968e19efd8cd8e1"
            "cdc41fedbb287aa9",
        )
        self.assertFalse(
            schedule_contract["deployment"]["authorized_by_this_contract"]
        )
        self.assertTrue(
            schedule_contract["rollback"][
                "preserve_067_contract_and_sql_history"
            ]
        )

        adapter_supersession = adapter_contract["runtime"]
        adapter_supersession = adapter_supersession[
            "schedule_supersession"
        ]
        self.assertEqual(adapter_supersession["scope"], "schedule_only")
        self.assertTrue(
            adapter_supersession["historical_067_contract_preserved"]
        )
        self.assertEqual(
            adapter_contract["rollback"]["restore_schedule_policy_version"],
            historical_contract["schedule_policy_version"],
        )
        self.assertEqual(
            adapter_contract["authority"]
            ["current_schedule_preflight_migration_file_sha256"],
            SCHEDULE_071_MIGRATION_SHA256,
        )
        self.assertEqual(
            adapter_contract["rollback"]
            ["database_function_rollback_file_sha256"],
            SCHEDULE_071_ROLLBACK_SHA256,
        )
        self.assertEqual(
            adapter_contract["rollback"]
            ["database_function_rollback_restores_067_pg_proc_prosrc_sha256"],
            "1ec882400c5cb95e1743e7f8829327d6cf42e3bfb7ea68a6"
            "4c70795a1d73731d",
        )
        self.assertTrue(
            adapter_contract["rollback"][
                "preserve_067_contract_and_sql_history"
            ]
        )
        self.assertFalse(
            adapter_contract["rollback"][
                "database_function_rollback_touches_070_or_062"
            ]
        )

    def test_metadata_is_safe_and_reasoning_content_is_discarded(self):
        adapter = DeepSeekChatCompletionsModelAdapter(
            api_key=API_KEY,
            transport=FakeTransport(),
        )
        result = adapter.generate_decision(
            SYNTHETIC_NETWORK_CANARY_CONTEXT
        )

        self.assertEqual(result, decision_payload())
        self.assertEqual(
            adapter.last_call_metadata,
            {
                "provider": "deepseek",
                "model": DEEPSEEK_MODEL,
                "response_id": "chatcmpl_test",
                "system_fingerprint": "fp_test",
                "input_tokens": 120,
                "output_tokens": 30,
                "total_tokens": 150,
                "prompt_cache_hit_tokens": 90,
                "prompt_cache_miss_tokens": 30,
                "reasoning_tokens": 20,
                "latency_ms": 321,
            },
        )
        evidence = json.dumps(
            {"result": result, "metadata": adapter.last_call_metadata}
        )
        self.assertNotIn("must_never_be_retained", evidence)
        self.assertNotIn("reasoning_content", evidence)

    def test_environment_requires_exact_provider_and_secure_key_file(self):
        with tempfile.TemporaryDirectory() as directory:
            key_path = Path(directory) / "n6_ai_agent_api_key"
            key_path.write_text(API_KEY, encoding="ascii")
            key_path.chmod(0o600)
            environment = {
                DEEPSEEK_MODEL_PROVIDER_ENV: DEEPSEEK_MODEL_PROVIDER,
                DEEPSEEK_API_KEY_FILE_ENV: str(key_path),
            }
            with mock.patch(
                "ashare_v3.user.n6_ai_deepseek_adapter."
                "DEEPSEEK_API_KEY_FILE",
                key_path,
            ):
                adapter = (
                    DeepSeekChatCompletionsModelAdapter.from_environment(
                        environment,
                        transport=FakeTransport(),
                    )
                )
            self.assertEqual(
                adapter.generate_decision(
                    SYNTHETIC_NETWORK_CANARY_CONTEXT
                ),
                decision_payload(),
            )

            for invalid in (
                {DEEPSEEK_API_KEY_FILE_ENV: str(key_path)},
                {
                    **environment,
                    DEEPSEEK_MODEL_PROVIDER_ENV: "deepseek",
                },
                {
                    DEEPSEEK_MODEL_PROVIDER_ENV:
                        DEEPSEEK_MODEL_PROVIDER,
                },
            ):
                with self.subTest(invalid=invalid):
                    with self.assertRaises(DeepSeekAdapterError):
                        DeepSeekChatCompletionsModelAdapter.from_environment(
                            invalid
                        )

            key_path.chmod(0o644)
            with mock.patch(
                "ashare_v3.user.n6_ai_deepseek_adapter."
                "DEEPSEEK_API_KEY_FILE",
                key_path,
            ):
                with self.assertRaisesRegex(
                    DeepSeekAdapterError, "credential_file_unsafe"
                ):
                    DeepSeekChatCompletionsModelAdapter.from_environment(
                        environment
                    )

            self.assertEqual(
                str(DEEPSEEK_API_KEY_FILE),
                "/Users/chuanfuchen/.config/ashare-v3/deepseek/"
                "n6_ai_agent_api_key",
            )

    def test_environment_rejects_openai_and_deepseek_overrides(self):
        with tempfile.TemporaryDirectory() as directory:
            key_path = Path(directory) / "n6_ai_agent_api_key"
            key_path.write_text(API_KEY, encoding="ascii")
            key_path.chmod(0o600)
            base = {
                DEEPSEEK_MODEL_PROVIDER_ENV: DEEPSEEK_MODEL_PROVIDER,
                DEEPSEEK_API_KEY_FILE_ENV: str(key_path),
            }
            for forbidden in (
                {LEGACY_OPENAI_API_KEY_FILE_ENV: "/tmp/openai-key"},
                {"OPENAI_API_KEY": API_KEY},
                {"OPENAI_BASE_URL": "https://example.invalid"},
                {"DEEPSEEK_API_KEY": API_KEY},
                {"DEEPSEEK_BASE_URL": "https://example.invalid"},
                {"DEEPSEEK_MODEL": "other"},
                {SSL_KEY_LOG_FILE_ENV: "/tmp/forbidden-keylog"},
                {
                    "ASHARE_V3_N6_AI_DEEPSEEK_HOST":
                        "example.invalid"
                },
            ):
                with self.subTest(forbidden=forbidden):
                    with self.assertRaisesRegex(
                        DeepSeekAdapterError,
                        "environment_not_allowed",
                    ):
                        DeepSeekChatCompletionsModelAdapter.from_environment(
                            {**base, **forbidden}
                        )

    def test_ambient_proxy_environment_cannot_change_adapter(self):
        with tempfile.TemporaryDirectory() as directory:
            key_path = Path(directory) / "n6_ai_agent_api_key"
            key_path.write_text(API_KEY, encoding="ascii")
            key_path.chmod(0o600)
            transport = FakeTransport()
            with mock.patch(
                "ashare_v3.user.n6_ai_deepseek_adapter."
                "DEEPSEEK_API_KEY_FILE",
                key_path,
            ):
                adapter = (
                    DeepSeekChatCompletionsModelAdapter.from_environment(
                        {
                            DEEPSEEK_MODEL_PROVIDER_ENV:
                                DEEPSEEK_MODEL_PROVIDER,
                            DEEPSEEK_API_KEY_FILE_ENV: str(key_path),
                            "HTTP_PROXY":
                                "http://127.0.0.1:7890",
                            "HTTPS_PROXY":
                                "http://127.0.0.1:7890",
                            "ALL_PROXY":
                                "socks5://127.0.0.1:7890",
                            "NO_PROXY": "localhost,127.0.0.1",
                        },
                        transport=transport,
                    )
                )

            self.assertEqual(
                adapter.generate_decision(
                    SYNTHETIC_NETWORK_CANARY_CONTEXT
                ),
                decision_payload(),
            )
            self.assertEqual(
                transport.calls[0]["timeout_seconds"], 120
            )

    def test_key_content_mode_owner_and_symlink_fail_closed(self):
        invalid_values = (
            "short",
            "a" * 513,
            "opaque key " + "a" * 30,
            "opaque-key-" + "你" * 20,
            API_KEY + "\n",
        )
        for value in invalid_values:
            with self.subTest(value_length=len(value)):
                with self.assertRaisesRegex(
                    DeepSeekAdapterError, "credential_invalid"
                ):
                    DeepSeekChatCompletionsModelAdapter(api_key=value)

        with tempfile.TemporaryDirectory() as directory:
            real_path = Path(directory) / "real-key"
            real_path.write_text(API_KEY, encoding="ascii")
            real_path.chmod(0o600)
            link_path = Path(directory) / "link-key"
            link_path.symlink_to(real_path)
            environment = {
                DEEPSEEK_MODEL_PROVIDER_ENV: DEEPSEEK_MODEL_PROVIDER,
                DEEPSEEK_API_KEY_FILE_ENV: str(link_path),
            }
            with mock.patch(
                "ashare_v3.user.n6_ai_deepseek_adapter."
                "DEEPSEEK_API_KEY_FILE",
                link_path,
            ):
                with self.assertRaisesRegex(
                    DeepSeekAdapterError, "credential_file_unsafe"
                ):
                    DeepSeekChatCompletionsModelAdapter.from_environment(
                        environment
                    )

            environment[DEEPSEEK_API_KEY_FILE_ENV] = str(real_path)
            with (
                mock.patch(
                    "ashare_v3.user.n6_ai_deepseek_adapter."
                    "DEEPSEEK_API_KEY_FILE",
                    real_path,
                ),
                mock.patch(
                    "ashare_v3.user.n6_ai_deepseek_adapter."
                    "os.geteuid",
                    return_value=real_path.stat().st_uid + 1,
                ),
            ):
                with self.assertRaisesRegex(
                    DeepSeekAdapterError, "credential_file_unsafe"
                ):
                    DeepSeekChatCompletionsModelAdapter.from_environment(
                        environment
                    )

    def test_key_same_length_in_place_change_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            key_path = Path(directory) / "n6_ai_agent_api_key"
            key_path.write_text(API_KEY, encoding="ascii")
            key_path.chmod(0o600)
            before = key_path.stat()
            after = SimpleNamespace(
                st_mode=before.st_mode,
                st_uid=before.st_uid,
                st_dev=before.st_dev,
                st_ino=before.st_ino,
                st_size=before.st_size,
                st_mtime_ns=before.st_mtime_ns + 1,
                st_ctime_ns=before.st_ctime_ns,
            )
            environment = {
                DEEPSEEK_MODEL_PROVIDER_ENV: DEEPSEEK_MODEL_PROVIDER,
                DEEPSEEK_API_KEY_FILE_ENV: str(key_path),
            }
            with mock.patch(
                "ashare_v3.user.n6_ai_deepseek_adapter."
                "DEEPSEEK_API_KEY_FILE",
                key_path,
            ):
                with mock.patch(
                    "ashare_v3.user.n6_ai_deepseek_adapter.os.fstat",
                    side_effect=(before, after),
                ):
                    with self.assertRaisesRegex(
                        DeepSeekAdapterError,
                        "credential_file_changed",
                    ):
                        DeepSeekChatCompletionsModelAdapter.from_environment(
                            environment
                        )

    def test_response_shape_and_completion_status_fail_closed(self):
        cases = [
            {
                **completed_response(),
                "error": {"message": "provider detail"},
            },
            {**completed_response(), "choices": []},
            {
                **completed_response(),
                "choices": completed_response()["choices"] * 2,
            },
            {
                **completed_response(),
                "choices": [
                    {
                        **completed_response()["choices"][0],
                        "index": True,
                    }
                ],
            },
        ]
        for finish_reason in (
            "length",
            "content_filter",
            "insufficient_system_resource",
        ):
            choice = {
                **completed_response()["choices"][0],
                "finish_reason": finish_reason,
            }
            cases.append({**completed_response(), "choices": [choice]})
        for response in cases:
            with self.subTest(response=response):
                adapter = DeepSeekChatCompletionsModelAdapter(
                    api_key=API_KEY,
                    transport=FakeTransport(response),
                )
                with self.assertRaises(DeepSeekAdapterError):
                    adapter.generate_decision(
                        SYNTHETIC_NETWORK_CANARY_CONTEXT
                    )

    def test_content_tools_and_schema_shape_fail_closed(self):
        base_choice = completed_response()["choices"][0]
        invalid_contents = (
            "",
            "   ",
            "not-json",
            "[]",
            json.dumps(
                {
                    **provider_decision_payload(),
                    "unexpected": "not allowed",
                }
            ),
            json.dumps(
                {
                    **provider_decision_payload(),
                    "risk_assessment": {
                        **provider_decision_payload()[
                            "risk_assessment"
                        ],
                        "unexpected": "not allowed",
                    },
                }
            ),
        )
        responses = []
        for content in invalid_contents:
            responses.append(
                {
                    **completed_response(),
                    "choices": [
                        {
                            **base_choice,
                            "message": {
                                **base_choice["message"],
                                "content": content,
                            },
                        }
                    ],
                }
            )
        responses.append(
            {
                **completed_response(),
                "choices": [
                    {
                        **base_choice,
                        "message": {
                            **base_choice["message"],
                            "tool_calls": [{"id": "tool"}],
                        },
                    }
                ],
            }
        )

        for response in responses:
            adapter = DeepSeekChatCompletionsModelAdapter(
                api_key=API_KEY,
                transport=FakeTransport(response),
            )
            with self.assertRaises(DeepSeekAdapterError):
                adapter.generate_decision(
                    SYNTHETIC_NETWORK_CANARY_CONTEXT
                )

    def test_transport_and_response_size_errors_are_sanitized(self):
        adapter = DeepSeekChatCompletionsModelAdapter(
            api_key=API_KEY,
            transport=FakeTransport(raises=True),
        )
        with self.assertRaisesRegex(
            DeepSeekAdapterError, "^model_service_unavailable$"
        ) as captured:
            adapter.generate_decision(
                SYNTHETIC_NETWORK_CANARY_CONTEXT
            )
        self.assertNotIn("secret", str(captured.exception))

        for payload, status, expected in (
            (
                b"x" * (MAX_RESPONSE_BYTES + 1),
                200,
                "model_response_too_large",
            ),
            (b"{}", 429, "model_service_unavailable"),
            (b"not-json", 200, "model_response_invalid"),
        ):
            response = FakeHTTPResponse(payload, status=status)
            connection = FakeHTTPSConnection(response)
            with mock.patch(
                "ashare_v3.user.n6_ai_deepseek_adapter."
                "http.client.HTTPSConnection",
                return_value=connection,
            ):
                with self.assertRaisesRegex(
                    DeepSeekAdapterError, f"^{expected}$"
                ):
                    FixedDeepSeekChatCompletionsTransport().create(
                        api_key=API_KEY,
                        payload={},
                        timeout_seconds=DEEPSEEK_TIMEOUT_SECONDS,
                    )

        timeout_connection = mock.Mock()
        timeout_connection.request.side_effect = TimeoutError(
            "network secret detail"
        )
        with mock.patch(
            "ashare_v3.user.n6_ai_deepseek_adapter."
            "http.client.HTTPSConnection",
            return_value=timeout_connection,
        ):
            with self.assertRaisesRegex(
                DeepSeekAdapterError,
                "^model_service_unavailable$",
            ) as captured:
                FixedDeepSeekChatCompletionsTransport().create(
                    api_key=API_KEY,
                    payload={},
                    timeout_seconds=DEEPSEEK_TIMEOUT_SECONDS,
                )
        self.assertNotIn("secret", str(captured.exception))
        timeout_connection.close.assert_called_once_with()

        success_response = FakeHTTPResponse(
            json.dumps(completed_response()).encode("utf-8")
        )
        close_failure = FakeHTTPSConnection(
            success_response, close_raises=True
        )
        with mock.patch(
            "ashare_v3.user.n6_ai_deepseek_adapter."
            "http.client.HTTPSConnection",
            return_value=close_failure,
        ):
            value = FixedDeepSeekChatCompletionsTransport().create(
                api_key=API_KEY,
                payload={},
                timeout_seconds=DEEPSEEK_TIMEOUT_SECONDS,
            )
        self.assertEqual(value["id"], "chatcmpl_test")
        self.assertTrue(close_failure.closed)

    def test_runner_configures_deepseek_after_database_preflight(self):
        calls = []
        environment = {
            SHADOW_FEATURE_FLAG: "1",
            "PGSERVICE": "n6_ai_agent",
            "PGSERVICEFILE": "/tmp/service",
            "PGPASSFILE": "/tmp/pass",
            DEEPSEEK_MODEL_PROVIDER_ENV: DEEPSEEK_MODEL_PROVIDER,
            DEEPSEEK_API_KEY_FILE_ENV: str(DEEPSEEK_API_KEY_FILE),
            DEEPSEEK_EGRESS_MODE_ENV:
                DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
            DEEPSEEK_SYSTEM_FINGERPRINT_ENV: "fp_test",
            PRODUCTION_KNOWLEDGE_MANIFEST_FILE_ENV: str(
                PRODUCTION_MANIFEST
            ),
            PRODUCTION_KNOWLEDGE_MANIFEST_SHA256_ENV: (
                PRODUCTION_KNOWLEDGE_MANIFEST_FILE_SHA256
            ),
        }
        arguments = argparse.Namespace(
            run_at="2026-07-20T10:30:00+08:00",
            max_signals=1000,
            autonomous=False,
            execute=True,
        )

        class Repository:
            def shadow_schedule_preflight(self, **kwargs):
                calls.append(("preflight", kwargs))
                return {"ok": True, "status": "open_slot_ready"}

        with mock.patch(
            "scripts.run_n6_ai_agent_once."
            "DeepSeekChatCompletionsModelAdapter.from_environment",
            return_value=DisabledModelAdapter(),
        ) as factory:
            result = run_from_args(
                arguments,
                environment=environment,
                now_factory=open_071_request_time,
                repository_factory=lambda: (
                    calls.append("database") or Repository(),
                    lambda: None,
                ),
            )
        factory.assert_called_once_with(environment)
        self.assertEqual(
            result["reason"], "model_adapter_not_configured"
        )
        self.assertEqual(calls[0], "database")
        self.assertEqual(calls[1][0], "preflight")

        calls.clear()
        with mock.patch(
            "scripts.run_n6_ai_agent_once."
            "DeepSeekChatCompletionsModelAdapter.from_environment",
            side_effect=DeepSeekAdapterError(
                "provider secret detail"
            ),
        ):
            failed = run_from_args(
                arguments,
                environment=environment,
                now_factory=open_071_request_time,
                repository_factory=lambda: (
                    calls.append("database") or Repository(),
                    lambda: None,
                ),
            )
        self.assertEqual(
            failed["reason"],
            "model_adapter_configuration_invalid",
        )
        self.assertNotIn("secret", json.dumps(failed))
        self.assertEqual(calls[0], "database")
        self.assertEqual(calls[1][0], "preflight")

    def test_runner_preserves_only_reviewed_deepseek_call_evidence(self):
        environment = {
            SHADOW_FEATURE_FLAG: "1",
            "PGSERVICE": "n6_ai_agent",
            "PGSERVICEFILE": "/tmp/service",
            "PGPASSFILE": "/tmp/pass",
            DEEPSEEK_MODEL_PROVIDER_ENV: DEEPSEEK_MODEL_PROVIDER,
            DEEPSEEK_API_KEY_FILE_ENV: str(DEEPSEEK_API_KEY_FILE),
            DEEPSEEK_EGRESS_MODE_ENV:
                DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
            DEEPSEEK_SYSTEM_FINGERPRINT_ENV: "fp_test",
            PRODUCTION_KNOWLEDGE_MANIFEST_FILE_ENV: str(
                PRODUCTION_MANIFEST
            ),
            PRODUCTION_KNOWLEDGE_MANIFEST_SHA256_ENV: (
                PRODUCTION_KNOWLEDGE_MANIFEST_FILE_SHA256
            ),
        }
        adapter = DeepSeekChatCompletionsModelAdapter(
            api_key=API_KEY,
            transport=FakeTransport(),
            egress_mode=DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
            expected_system_fingerprint="fp_test",
        )

        def fake_agent_run(**kwargs):
            kwargs["model_adapter"].generate_decision(
                real_context_payload()
            )
            adapter._last_call_metadata[
                "reasoning_content"
            ] = "must_never_be_retained"
            return {
                "ok": True,
                "status": "shadow_decision_recorded",
                "model_called": True,
                "proposal_created": False,
                "observation_audit_attempted": True,
                "observation_audit_recorded": True,
                "model_call": {"provider": "truncated"},
            }

        with mock.patch(
            "scripts.run_n6_ai_agent_once.run_agent_once",
            side_effect=fake_agent_run,
        ):
            result = run_from_args(
                argparse.Namespace(
                    run_at="2026-07-20T10:30:00+08:00",
                    max_signals=1000,
                    autonomous=False,
                    execute=True,
                ),
                environment=environment,
                now_factory=open_071_request_time,
                repository_factory=lambda: (
                    type(
                        "ReadyRepository",
                        (),
                        {
                            "shadow_schedule_preflight":
                                lambda self, **kwargs: {
                                    "ok": True,
                                    "status": "open_slot_ready",
                                },
                        },
                    )(),
                    lambda: None,
                ),
                model_adapter_factory=lambda: adapter,
            )

        self.assertEqual(
            result["model_call"],
            {
                "provider": "deepseek",
                "model": DEEPSEEK_MODEL,
                "system_fingerprint": "fp_test",
                "input_tokens": 120,
                "output_tokens": 30,
                "total_tokens": 150,
                "prompt_cache_hit_tokens": 90,
                "prompt_cache_miss_tokens": 30,
                "reasoning_tokens": 20,
                "latency_ms": 321,
            },
        )
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("response_id", serialized)
        self.assertNotIn("chatcmpl_test", serialized)
        self.assertNotIn("reasoning_content", serialized)
        self.assertNotIn("must_never_be_retained", serialized)

    def test_pseudonymous_buy_remaps_to_canonical_internal_references(self):
        transport = SelectingTransport()
        adapter = DeepSeekChatCompletionsModelAdapter(
            api_key=API_KEY,
            transport=transport,
            egress_mode=DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
            expected_system_fingerprint="fp_test",
        )

        result = adapter.generate_decision(real_context_payload())

        self.assertEqual(result["decision_type"], "buy")
        self.assertEqual(result["identity_key"], "stock:SH:600000")
        self.assertEqual(result["source_signal_projection_id"], 101)
        self.assertIsNone(result["source_virtual_position_id"])
        self.assertEqual(result["evidence"], ["projection:101"])
        validated = validate_model_output(
            result,
            context=ValidatedContext(
                context_snapshot_id=1,
                decision_input_hash="d" * 64,
                knowledge_bundle_hash="a" * 64,
                universe_snapshot_hash="b" * 64,
                memory_snapshot_hash="c" * 64,
                workset_hash="e" * 64,
                for_trade_date="20260718",
                signals=(
                    {
                        "user_signal_projection_id": 101,
                        "identity_key": "stock:SH:600000",
                        "direction": "buy",
                    },
                ),
                market_context=(),
                positions=(),
                portfolio={},
                strategy_id=1,
                strategy_version="v1",
                strategy_hash="f" * 64,
                daily_metrics={},
            ),
        )
        self.assertEqual(validated.source_signal_projection_id, 101)
        serialized_result = json.dumps(result, ensure_ascii=False)
        provider_context = json.loads(
            transport.calls[0]["payload"]["messages"][1]["content"]
        )
        for token in (
            provider_context["context_token"],
            provider_context["signals"][0]["asset_token"],
            provider_context["signals"][0]["signal_token"],
            provider_context["positions"][0]["position_token"],
        ):
            self.assertNotIn(token, serialized_result)

    def test_sell_remap_and_cross_scope_mutations_are_fail_closed(self):
        sell_context = real_context_payload()
        sell_context["signals"][0]["identity_key"] = (
            "stock:SH:600001"
        )
        sell_context["signals"][0]["direction"] = "sell"

        class DecisionTransport:
            def __init__(self, builder):
                self.builder = builder

            def create(self, **kwargs):
                projected = json.loads(
                    kwargs["payload"]["messages"][1]["content"]
                )
                return completed_response(self.builder(projected))

        def sell_payload(projected, trigger):
            signal = projected["signals"][0]
            position = projected["positions"][0]
            use_signal = trigger == "signal"
            evidence = [
                f"position:{position['position_token']}"
            ]
            if use_signal:
                evidence.append(
                    f"signal:{signal['signal_token']}"
                )
            return provider_decision_payload(
                context_token=projected["context_token"],
                decision_type="sell",
                asset_token=position["asset_token"],
                source_signal_token=(
                    signal["signal_token"] if use_signal else None
                ),
                source_position_token=position["position_token"],
                confidence="0.8",
                evidence=evidence,
                risk_assessment={
                    "trigger": trigger,
                    "level": "high",
                    "summary": "local deterministic recheck required",
                },
            )

        for trigger in ("signal", "stop_loss", "portfolio_risk"):
            with self.subTest(trigger=trigger):
                adapter = DeepSeekChatCompletionsModelAdapter(
                    api_key=API_KEY,
                    transport=DecisionTransport(
                        lambda projected, trigger=trigger:
                            sell_payload(projected, trigger)
                    ),
                    egress_mode=(
                        DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW
                    ),
                    expected_system_fingerprint="fp_test",
                )
                result = adapter.generate_decision(sell_context)
                self.assertEqual(result["decision_type"], "sell")
                self.assertEqual(
                    result["identity_key"], "stock:SH:600001"
                )
                self.assertEqual(
                    result["source_virtual_position_id"], 201
                )
                self.assertEqual(
                    result["source_signal_projection_id"],
                    101 if trigger == "signal" else None,
                )

        invalid_builders = (
            lambda projected: provider_decision_payload(
                context_token=projected["context_token"],
                decision_type="buy",
                asset_token=projected["signals"][0]["asset_token"],
                source_signal_token=projected["signals"][0][
                    "signal_token"
                ],
                confidence="0.8",
                evidence=[
                    "signal:"
                    + projected["signals"][0]["signal_token"]
                ],
                risk_assessment={
                    "trigger": "signal",
                    "level": "low",
                    "summary": "wrong direction",
                },
            ),
            lambda projected: provider_decision_payload(
                context_token=projected["context_token"],
                decision_type="sell",
                asset_token=projected["positions"][0]["asset_token"],
                source_signal_token=projected["signals"][0][
                    "signal_token"
                ],
                source_position_token=projected["positions"][0][
                    "position_token"
                ],
                confidence="0.8",
                evidence=[
                    "signal:"
                    + projected["signals"][0]["signal_token"],
                    "position:"
                    + projected["positions"][0]["position_token"],
                ],
                risk_assessment={
                    "trigger": "signal",
                    "level": "high",
                    "summary": "cross asset",
                },
            ),
            lambda projected: provider_decision_payload(
                context_token=projected["context_token"],
                asset_token=projected["positions"][0]["asset_token"],
            ),
        )
        invalid_contexts = (
            sell_context,
            {
                **sell_context,
                "signals": [
                    {
                        **sell_context["signals"][0],
                        "identity_key": "stock:SH:600000",
                    }
                ],
            },
            sell_context,
        )
        for builder, context in zip(
            invalid_builders, invalid_contexts, strict=True
        ):
            with self.subTest(builder=builder):
                adapter = DeepSeekChatCompletionsModelAdapter(
                    api_key=API_KEY,
                    transport=DecisionTransport(builder),
                    egress_mode=(
                        DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW
                    ),
                    expected_system_fingerprint="fp_test",
                )
                with self.assertRaisesRegex(
                    DeepSeekAdapterError, "token_scope_invalid"
                ):
                    adapter.generate_decision(context)

    def test_tokens_rotate_per_call_and_cross_call_replay_is_rejected(self):
        transport = FakeTransport()
        adapter = DeepSeekChatCompletionsModelAdapter(
            api_key=API_KEY,
            transport=transport,
            egress_mode=DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
            expected_system_fingerprint="fp_test",
        )
        adapter.generate_decision(real_context_payload())
        adapter.generate_decision(real_context_payload())
        first = json.loads(
            transport.calls[0]["payload"]["messages"][1]["content"]
        )
        second = json.loads(
            transport.calls[1]["payload"]["messages"][1]["content"]
        )
        self.assertNotEqual(
            first["context_token"], second["context_token"]
        )
        self.assertNotEqual(
            first["signals"][0]["signal_token"],
            second["signals"][0]["signal_token"],
        )

        class ReplayTransport:
            def __init__(self):
                self.first_context_token = None

            def create(self, **kwargs):
                projected = json.loads(
                    kwargs["payload"]["messages"][1]["content"]
                )
                if self.first_context_token is None:
                    self.first_context_token = projected[
                        "context_token"
                    ]
                return completed_response(
                    provider_decision_payload(
                        context_token=self.first_context_token
                    )
                )

        replay = DeepSeekChatCompletionsModelAdapter(
            api_key=API_KEY,
            transport=ReplayTransport(),
            egress_mode=DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
            expected_system_fingerprint="fp_test",
        )
        replay.generate_decision(real_context_payload())
        with self.assertRaisesRegex(
            DeepSeekAdapterError, "unknown_token"
        ):
            replay.generate_decision(real_context_payload())

    def test_random_tokens_remove_original_signal_list_order(self):
        context = real_context_payload()
        template = context["signals"][0]
        context["signals"] = [
            {
                **json.loads(json.dumps(template)),
                "user_signal_projection_id": source_id,
                "identity_key": identity,
            }
            for source_id, identity in (
                (101, "stock:SH:600000"),
                (102, "stock:SH:600001"),
                (103, "stock:SH:600002"),
            )
        ]
        context["market_context"] = []
        context["positions"] = []
        transport = FakeTransport()
        adapter = DeepSeekChatCompletionsModelAdapter(
            api_key=API_KEY,
            transport=transport,
            egress_mode=DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
            expected_system_fingerprint="fp_test",
        )
        with mock.patch(
            "ashare_v3.user.n6_ai_deepseek_adapter."
            "secrets.token_hex",
            side_effect=(
                "0" * 32,
                "f" * 32,
                "1" * 32,
                "1" * 32,
                "2" * 32,
                "8" * 32,
                "3" * 32,
            ),
        ):
            adapter.generate_decision(context)
        projected = json.loads(
            transport.calls[0]["payload"]["messages"][1]["content"]
        )
        self.assertEqual(
            [
                item["signal_token"]
                for item in projected["signals"]
            ],
            [
                "signal_" + "1" * 32,
                "signal_" + "8" * 32,
                "signal_" + "f" * 32,
            ],
        )

    def test_unknown_token_and_ephemeral_token_text_fail_closed(self):
        class MutatingTransport:
            def __init__(self, mutation):
                self.mutation = mutation

            def create(self, **kwargs):
                projected = json.loads(
                    kwargs["payload"]["messages"][1]["content"]
                )
                signal = projected["signals"][0]
                payload = provider_decision_payload(
                    context_token=projected["context_token"],
                    decision_type="buy",
                    asset_token=signal["asset_token"],
                    source_signal_token=signal["signal_token"],
                    confidence="0.8",
                    evidence=[f"signal:{signal['signal_token']}"],
                    risk_assessment={
                        "trigger": "signal",
                        "level": "low",
                        "summary": "local_recheck",
                    },
                )
                self.mutation(payload, projected)
                return completed_response(payload)

        adapter = DeepSeekChatCompletionsModelAdapter(
            api_key=API_KEY,
            transport=MutatingTransport(
                lambda payload, projected: payload.update(
                    asset_token="asset_" + "f" * 32
                )
            ),
            egress_mode=DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
            expected_system_fingerprint="fp_test",
        )
        with self.assertRaisesRegex(
            DeepSeekAdapterError, "unknown_token"
        ):
            adapter.generate_decision(real_context_payload())

        leaking = DeepSeekChatCompletionsModelAdapter(
            api_key=API_KEY,
            transport=MutatingTransport(
                lambda payload, projected: payload.update(
                    reason_summary=(
                        "echo " + projected["context_token"]
                    )
                )
            ),
            egress_mode=DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
            expected_system_fingerprint="fp_test",
        )
        with self.assertRaisesRegex(
            DeepSeekAdapterError, "token_leak"
        ):
            leaking.generate_decision(real_context_payload())

        replay_token = "market_" + "a" * 32
        replay_leaking = DeepSeekChatCompletionsModelAdapter(
            api_key=API_KEY,
            transport=MutatingTransport(
                lambda payload, projected: payload.update(
                    counter_evidence=[
                        "cross_context " + replay_token
                    ]
                )
            ),
            egress_mode=DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
            expected_system_fingerprint="fp_test",
        )
        with self.assertRaisesRegex(
            DeepSeekAdapterError, "token_leak"
        ):
            replay_leaking.generate_decision(
                real_context_payload()
            )

        for mutation in (
            lambda payload, projected: payload.update(
                reason_summary=projected["context_token"].upper()
            ),
            lambda payload, projected: payload.update(
                counter_evidence=["projection:999"]
            ),
            lambda payload, projected: payload.update(
                risk_assessment={
                    "trigger": "signal",
                    "level": "low",
                    "summary": "stock:SH:600000",
                }
            ),
            lambda payload, projected: payload.update(
                reason_summary=(
                    "代码600000 日期20260718 价格10.12 数量1000"
                )
            ),
            lambda payload, projected: payload.update(
                strategy_candidate_notes="a" * 64
            ),
        ):
            with self.subTest(mutation=mutation):
                adapter = DeepSeekChatCompletionsModelAdapter(
                    api_key=API_KEY,
                    transport=MutatingTransport(mutation),
                    egress_mode=(
                        DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW
                    ),
                    expected_system_fingerprint="fp_test",
                )
                with self.assertRaisesRegex(
                    DeepSeekAdapterError, "token_leak"
                ):
                    adapter.generate_decision(
                        real_context_payload()
                    )

    def test_default_mode_blocks_real_context_before_transport(self):
        transport = FakeTransport()
        adapter = DeepSeekChatCompletionsModelAdapter(
            api_key=API_KEY,
            transport=transport,
        )
        with self.assertRaisesRegex(
            DeepSeekAdapterError, "real_data_egress_blocked"
        ):
            adapter.generate_decision(real_context_payload())
        self.assertEqual(transport.calls, [])

    def test_response_model_fingerprint_and_pause_marker_are_strict(self):
        self.assertEqual(
            validate_system_fingerprint("fp.safe:1"), "fp.safe:1"
        )
        for invalid in ("", "has space", "不安全", "x" * 201):
            with self.assertRaises(DeepSeekAdapterError):
                validate_system_fingerprint(invalid)

        wrong_model = completed_response()
        wrong_model["model"] = "deepseek-other"
        with self.assertRaisesRegex(
            DeepSeekAdapterError, "identity_mismatch"
        ):
            DeepSeekChatCompletionsModelAdapter(
                api_key=API_KEY,
                transport=FakeTransport(wrong_model),
            ).generate_decision(
                SYNTHETIC_NETWORK_CANARY_CONTEXT
            )

        with tempfile.TemporaryDirectory() as directory:
            pause_file = Path(directory) / "state" / "paused"
            adapter = DeepSeekChatCompletionsModelAdapter(
                api_key=API_KEY,
                transport=FakeTransport(
                    completed_response(fingerprint="fp_changed")
                ),
                egress_mode=(
                    DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW
                ),
                expected_system_fingerprint="fp_expected",
            )
            with mock.patch(
                "ashare_v3.user.n6_ai_deepseek_adapter."
                "DEEPSEEK_FINGERPRINT_PAUSE_FILE",
                pause_file,
            ):
                with self.assertRaisesRegex(
                    DeepSeekAdapterError,
                    "identity_mismatch",
                ):
                    adapter.generate_decision(
                        SYNTHETIC_NETWORK_CANARY_CONTEXT
                    )
                self.assertTrue(fingerprint_pause_marker_active())
                self.assertEqual(
                    stat.S_IMODE(pause_file.stat().st_mode), 0o600
                )

        with tempfile.TemporaryDirectory() as directory:
            pause_file = Path(directory) / "state" / "paused"
            with (
                mock.patch(
                    "ashare_v3.user.n6_ai_deepseek_adapter."
                    "DEEPSEEK_FINGERPRINT_PAUSE_FILE",
                    pause_file,
                ),
                mock.patch(
                    "ashare_v3.user.n6_ai_deepseek_adapter.os.fsync"
                ) as fsync,
            ):
                create_fingerprint_pause_marker()
            self.assertEqual(fsync.call_count, 2)

    def test_constructor_prevalidates_tls_and_request_size(self):
        with mock.patch(
            "ashare_v3.user.n6_ai_deepseek_adapter."
            "validate_tls_runtime"
        ) as validator:
            DeepSeekChatCompletionsModelAdapter(
                api_key=API_KEY,
                transport=FakeTransport(),
            )
        validator.assert_called_once_with()

        with self.assertRaisesRegex(
            DeepSeekAdapterError, "model_request_too_large"
        ):
            FixedDeepSeekChatCompletionsTransport().create(
                api_key=API_KEY,
                payload={"content": "x" * MAX_REQUEST_BYTES},
                timeout_seconds=DEEPSEEK_TIMEOUT_SECONDS,
            )

    def test_synthetic_network_canary_uses_zero_repository(self):
        repository_calls = []
        adapter = DeepSeekChatCompletionsModelAdapter(
            api_key=API_KEY,
            transport=FakeTransport(),
        )
        result = run_from_args(
            argparse.Namespace(
                run_at=None,
                max_signals=1000,
                autonomous=False,
                execute=True,
                synthetic_network_canary=True,
            ),
            environment={
                DEEPSEEK_EGRESS_MODE_ENV:
                    DEEPSEEK_EGRESS_SYNTHETIC_ONLY,
            },
            repository_factory=lambda: repository_calls.append(
                "database"
            ),
            model_adapter_factory=lambda: adapter,
        )
        self.assertEqual(
            result["status"], "synthetic_network_canary_passed"
        )
        self.assertFalse(result["db_connected"])
        self.assertEqual(repository_calls, [])
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("response_id", serialized)
        self.assertNotIn("chatcmpl_test", serialized)

    def test_synthetic_canary_requires_full_local_model_schema(self):
        invalid_payloads = []
        for mutation in (
            {"confidence": "99"},
            {"reason_summary": ["not", "text"]},
            {"counter_evidence": "not-a-list"},
            {
                "risk_assessment": {
                    "trigger": "none",
                    "level": "unknown",
                    "summary": "invalid level",
                }
            },
            {
                "risk_assessment": {
                    "trigger": "none",
                    "level": "low",
                    "summary": {"not": "text"},
                }
            },
            {
                "reason_summary":
                    "代码600000 日期20260718 价格10.12 数量1000"
            },
            {"strategy_candidate_notes": "a" * 64},
        ):
            payload = provider_decision_payload()
            payload.update(mutation)
            invalid_payloads.append(payload)

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                repository_calls = []
                adapter = DeepSeekChatCompletionsModelAdapter(
                    api_key=API_KEY,
                    transport=FakeTransport(
                        completed_response(payload)
                    ),
                )
                result = run_from_args(
                    argparse.Namespace(
                        run_at=None,
                        max_signals=1000,
                        autonomous=False,
                        execute=True,
                        synthetic_network_canary=True,
                    ),
                    environment={
                        DEEPSEEK_EGRESS_MODE_ENV:
                            DEEPSEEK_EGRESS_SYNTHETIC_ONLY,
                    },
                    repository_factory=lambda: (
                        repository_calls.append("database")
                    ),
                    model_adapter_factory=lambda: adapter,
                )
                self.assertFalse(result["ok"])
                self.assertEqual(
                    result["reason"],
                    "deepseek_provider_identity_probe_failed",
                )
                self.assertFalse(result["db_connected"])
                self.assertEqual(repository_calls, [])

    def test_database_preflight_precedes_provider_probe_and_pause_precedes_network(self):
        order = []
        audit_payloads = []

        class OrderedTransport(FakeTransport):
            def create(self, **kwargs):
                order.append("network_probe")
                return super().create(**kwargs)

        class AuditRepository:
            def shadow_schedule_preflight(self, **kwargs):
                del kwargs
                order.append("database_preflight")
                return {"ok": True, "status": "open_slot_ready"}

            def record_shadow_observation(self, payload):
                audit_payloads.append(dict(payload))
                return {"ok": True, "status": "observation_audit_recorded"}

        adapter = DeepSeekChatCompletionsModelAdapter(
            api_key=API_KEY,
            transport=OrderedTransport(),
            egress_mode=DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
            expected_system_fingerprint="fp_test",
        )
        environment = {
            SHADOW_FEATURE_FLAG: "1",
            "PGSERVICE": "n6_ai_agent",
            "PGSERVICEFILE": "/tmp/service",
            "PGPASSFILE": "/tmp/pass",
            DEEPSEEK_EGRESS_MODE_ENV:
                DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
            PRODUCTION_KNOWLEDGE_MANIFEST_FILE_ENV: str(
                PRODUCTION_MANIFEST
            ),
            PRODUCTION_KNOWLEDGE_MANIFEST_SHA256_ENV: (
                PRODUCTION_KNOWLEDGE_MANIFEST_FILE_SHA256
            ),
        }
        with mock.patch(
            "scripts.run_n6_ai_agent_once.run_agent_once",
            return_value={
                "ok": True,
                "status": "no_new_input",
                "model_called": False,
                "decision_recorded": False,
                "proposal_created": False,
            },
        ):
            no_new_input = run_from_args(
                argparse.Namespace(
                    run_at="2026-07-20T10:30:00+08:00",
                    max_signals=1000,
                    autonomous=False,
                    execute=True,
                    synthetic_network_canary=False,
                ),
                environment=environment,
                now_factory=open_071_request_time,
                repository_factory=lambda: (
                    order.append("database") or AuditRepository(),
                    lambda: None,
                ),
                model_adapter_factory=lambda: adapter,
            )
        self.assertEqual(
            order[:3],
            ["database", "database_preflight", "network_probe"],
        )
        self.assertFalse(no_new_input["model_called"])
        self.assertNotIn("model_call", no_new_input)
        self.assertEqual(
            no_new_input["provider_identity_probe"]["provider"],
            "deepseek",
        )
        self.assertIs(
            no_new_input["provider_identity_probe"]["network_called"],
            True,
        )
        serialized_no_new = json.dumps(
            no_new_input, ensure_ascii=False
        )
        self.assertNotIn("response_id", serialized_no_new)
        self.assertNotIn("chatcmpl_test", serialized_no_new)
        self.assertEqual(len(audit_payloads), 1)
        no_new_audit = audit_payloads[0]
        self.assertEqual(no_new_audit["one_shot_status"], "no_new_input")
        self.assertFalse(no_new_audit["decision_call_attempted"])
        self.assertNotIn("structure_valid", no_new_audit)
        for key in (
            "context_snapshot_id",
            "decision_run_id",
            "decision_id",
            "server_risk_allowed",
            "server_risk_reason",
        ):
            self.assertNotIn(key, no_new_audit)
        for key in (
            "proposal_created_count",
            "order_created_count",
            "trade_created_count",
            "position_mutation_count",
            "lot_mutation_count",
            "cash_mutation_count",
        ):
            self.assertEqual(no_new_audit[key], 0)

        order.clear()
        with mock.patch(
            "scripts.run_n6_ai_agent_once."
            "fingerprint_pause_marker_active",
            return_value=True,
        ):
            paused = run_from_args(
                argparse.Namespace(
                    run_at="2026-07-20T10:30:00+08:00",
                    max_signals=1000,
                    autonomous=False,
                    execute=True,
                    synthetic_network_canary=False,
                ),
                environment=environment,
                now_factory=open_071_request_time,
                repository_factory=lambda: (
                    order.append("database")
                    or type(
                        "ReadyRepository",
                        (),
                        {
                            "shadow_schedule_preflight":
                                lambda self, **kwargs: {
                                    "ok": True,
                                    "status": "open_slot_ready",
                                },
                        },
                    )(),
                    lambda: None,
                ),
                model_adapter_factory=lambda: (
                    order.append("adapter") or adapter
                ),
            )
        self.assertEqual(
            paused["reason"], "deepseek_system_fingerprint_paused"
        )
        self.assertEqual(order, ["database"])

    def test_post_run_pause_preserves_completed_write_audit_facts(self):
        adapter = DeepSeekChatCompletionsModelAdapter(
            api_key=API_KEY,
            transport=FakeTransport(),
            egress_mode=DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
            expected_system_fingerprint="fp_test",
        )
        environment = {
            SHADOW_FEATURE_FLAG: "1",
            "PGSERVICE": "n6_ai_agent",
            "PGSERVICEFILE": "/tmp/service",
            "PGPASSFILE": "/tmp/pass",
            DEEPSEEK_EGRESS_MODE_ENV:
                DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
            PRODUCTION_KNOWLEDGE_MANIFEST_FILE_ENV: str(
                PRODUCTION_MANIFEST
            ),
            PRODUCTION_KNOWLEDGE_MANIFEST_SHA256_ENV: (
                PRODUCTION_KNOWLEDGE_MANIFEST_FILE_SHA256
            ),
        }
        with (
            mock.patch(
                "scripts.run_n6_ai_agent_once."
                "fingerprint_pause_marker_active",
                side_effect=(False, True),
            ),
            mock.patch(
                "scripts.run_n6_ai_agent_once.run_agent_once",
                return_value={
                    "ok": True,
                    "status": "shadow_decision_recorded",
                    "model_called": True,
                    "decision_recorded": True,
                    "proposal_created": False,
                    "observation_audit_attempted": True,
                    "observation_audit_recorded": True,
                },
            ),
        ):
            result = run_from_args(
                argparse.Namespace(
                    run_at="2026-07-20T10:30:00+08:00",
                    max_signals=1000,
                    autonomous=False,
                    execute=True,
                    synthetic_network_canary=False,
                ),
                environment=environment,
                now_factory=open_071_request_time,
                repository_factory=lambda: (
                    type(
                        "ReadyRepository",
                        (),
                        {
                            "shadow_schedule_preflight":
                                lambda self, **kwargs: {
                                    "ok": True,
                                    "status": "open_slot_ready",
                                },
                        },
                    )(),
                    lambda: None,
                ),
                model_adapter_factory=lambda: adapter,
            )
        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reason"], "deepseek_system_fingerprint_paused"
        )
        self.assertTrue(result["model_called"])
        self.assertTrue(result["decision_recorded"])
        self.assertFalse(result["proposal_created"])

    def test_invalid_structure_is_audited_and_audit_rejection_fails_closed(
        self,
    ):
        environment = {
            SHADOW_FEATURE_FLAG: "1",
            "PGSERVICE": "n6_ai_agent",
            "PGSERVICEFILE": "/tmp/service",
            "PGPASSFILE": "/tmp/pass",
            DEEPSEEK_EGRESS_MODE_ENV:
                DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
            PRODUCTION_KNOWLEDGE_MANIFEST_FILE_ENV: str(
                PRODUCTION_MANIFEST
            ),
            PRODUCTION_KNOWLEDGE_MANIFEST_SHA256_ENV: (
                PRODUCTION_KNOWLEDGE_MANIFEST_FILE_SHA256
            ),
        }

        def execute(audit_ok):
            payloads = []

            class Repository:
                def shadow_schedule_preflight(self, **kwargs):
                    del kwargs
                    return {"ok": True, "status": "open_slot_ready"}

                def record_shadow_observation(self, payload):
                    payloads.append(dict(payload))
                    return {
                        "ok": audit_ok,
                        "status": (
                            "observation_audit_recorded"
                            if audit_ok
                            else "observation_audit_value_rejected"
                        ),
                    }

            transport = FakeTransport()
            adapter = DeepSeekChatCompletionsModelAdapter(
                api_key=API_KEY,
                transport=transport,
                egress_mode=DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
                expected_system_fingerprint="fp_test",
            )
            with mock.patch(
                "scripts.run_n6_ai_agent_once.run_agent_once",
                return_value={
                    "ok": False,
                    "status": "failed_closed",
                    "reason": "model_or_decision_validation_failed",
                    "model_called": True,
                    "decision_recorded": False,
                    "proposal_created": False,
                    "model_call": {
                        "provider": "deepseek",
                        "model": DEEPSEEK_MODEL,
                        "system_fingerprint": "fp_test",
                        "input_tokens": 3,
                        "output_tokens": 1,
                        "total_tokens": 4,
                        "prompt_cache_hit_tokens": 2,
                        "prompt_cache_miss_tokens": 1,
                        "latency_ms": 5,
                    },
                },
            ):
                result = run_from_args(
                    argparse.Namespace(
                        run_at="2026-07-20T10:30:00+08:00",
                        max_signals=1000,
                        autonomous=False,
                        execute=True,
                        synthetic_network_canary=False,
                    ),
                    environment=environment,
                    now_factory=open_071_request_time,
                    repository_factory=lambda: (
                        Repository(), lambda: None
                    ),
                    model_adapter_factory=lambda: adapter,
                )
            self.assertEqual(len(transport.calls), 1)
            return result, payloads

        recorded, payloads = execute(True)
        self.assertFalse(recorded["ok"])
        self.assertTrue(recorded["observation_audit_recorded"])
        serialized_recorded = json.dumps(recorded, ensure_ascii=False)
        self.assertNotIn("response_id", serialized_recorded)
        self.assertNotIn("chatcmpl_test", serialized_recorded)
        self.assertEqual(len(payloads), 1)
        invalid = payloads[0]
        self.assertEqual(
            invalid["one_shot_status"], "decision_structure_invalid"
        )
        self.assertTrue(invalid["decision_call_attempted"])
        self.assertFalse(invalid["structure_valid"])
        for key in (
            "context_snapshot_id",
            "decision_run_id",
            "decision_id",
            "server_risk_allowed",
            "server_risk_reason",
        ):
            self.assertNotIn(key, invalid)
        self.assertFalse(invalid["proposal_created"])
        for key in (
            "proposal_created_count",
            "order_created_count",
            "trade_created_count",
            "position_mutation_count",
            "lot_mutation_count",
            "cash_mutation_count",
        ):
            self.assertEqual(invalid[key], 0)

        rejected, rejected_payloads = execute(False)
        self.assertEqual(len(rejected_payloads), 1)
        self.assertFalse(rejected["ok"])
        self.assertEqual(rejected["reason"], "observation_audit_rejected")
        self.assertFalse(rejected["decision_recorded"])
        self.assertFalse(rejected["proposal_created"])
        serialized_rejected = json.dumps(rejected, ensure_ascii=False)
        self.assertNotIn("response_id", serialized_rejected)
        self.assertNotIn("chatcmpl_test", serialized_rejected)

    def test_runner_only_follows_up_when_061_rejected_before_062(self):
        environment = {
            SHADOW_FEATURE_FLAG: "1",
            "PGSERVICE": "n6_ai_agent",
            "PGSERVICEFILE": "/tmp/service",
            "PGPASSFILE": "/tmp/pass",
            DEEPSEEK_EGRESS_MODE_ENV:
                DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
            PRODUCTION_KNOWLEDGE_MANIFEST_FILE_ENV: str(
                PRODUCTION_MANIFEST
            ),
            PRODUCTION_KNOWLEDGE_MANIFEST_SHA256_ENV: (
                PRODUCTION_KNOWLEDGE_MANIFEST_FILE_SHA256
            ),
        }

        def execute(agent_result):
            payloads = []

            class Repository:
                def shadow_schedule_preflight(self, **kwargs):
                    del kwargs
                    return {"ok": True, "status": "open_slot_ready"}

                def record_shadow_observation(self, payload):
                    payloads.append(dict(payload))
                    return {
                        "ok": True,
                        "status": "observation_audit_recorded",
                    }

            transport = FakeTransport()
            adapter = DeepSeekChatCompletionsModelAdapter(
                api_key=API_KEY,
                transport=transport,
                egress_mode=DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
                expected_system_fingerprint="fp_test",
            )
            with mock.patch(
                "scripts.run_n6_ai_agent_once.run_agent_once",
                return_value=dict(agent_result),
            ):
                result = run_from_args(
                    argparse.Namespace(
                        run_at="2026-07-20T10:30:00+08:00",
                        max_signals=1000,
                        autonomous=False,
                        execute=True,
                        synthetic_network_canary=False,
                    ),
                    environment=environment,
                    now_factory=open_071_request_time,
                    repository_factory=lambda: (
                        Repository(), lambda: None
                    ),
                    model_adapter_factory=lambda: adapter,
                )
            self.assertEqual(len(transport.calls), 1)
            return result, payloads

        rejected_061, followup_payloads = execute({
            "ok": False,
            "status": "failed_closed",
            "reason": "decision_record_rejected",
            "model_called": True,
            "structure_valid": True,
            "decision_recorded": False,
            "proposal_created": False,
            "observation_audit_attempted": False,
            "observation_audit_followup_required": True,
        })
        self.assertFalse(rejected_061["ok"])
        self.assertEqual(
            rejected_061["reason"], "decision_record_rejected"
        )
        self.assertTrue(rejected_061["observation_audit_attempted"])
        self.assertTrue(rejected_061["observation_audit_recorded"])
        self.assertNotIn(
            "observation_audit_followup_required", rejected_061
        )
        self.assertFalse(rejected_061["decision_recorded"])
        self.assertFalse(rejected_061["proposal_created"])
        serialized_061 = json.dumps(rejected_061, ensure_ascii=False)
        self.assertNotIn("response_id", serialized_061)
        self.assertNotIn("chatcmpl_test", serialized_061)
        self.assertEqual(len(followup_payloads), 1)
        followup = followup_payloads[0]
        self.assertEqual(
            followup["one_shot_status"], "decision_record_rejected"
        )
        self.assertTrue(followup["decision_call_attempted"])
        self.assertTrue(followup["structure_valid"])
        self.assertFalse(followup["proposal_created"])
        for key in (
            "decision_run_id",
            "decision_id",
            "server_risk_allowed",
            "server_risk_reason",
        ):
            self.assertNotIn(key, followup)
        for key in (
            "proposal_created_count",
            "order_created_count",
            "trade_created_count",
            "position_mutation_count",
            "lot_mutation_count",
            "cash_mutation_count",
        ):
            self.assertEqual(followup[key], 0)

        rejected_062, duplicate_payloads = execute({
            "ok": False,
            "status": "failed_closed",
            "reason": "observation_audit_rejected",
            "model_called": True,
            "structure_valid": True,
            "decision_recorded": False,
            "proposal_created": False,
            "observation_audit_attempted": True,
            "observation_audit_recorded": False,
        })
        self.assertFalse(rejected_062["ok"])
        self.assertEqual(
            rejected_062["reason"], "observation_audit_rejected"
        )
        self.assertEqual(duplicate_payloads, [])
        serialized_062 = json.dumps(rejected_062, ensure_ascii=False)
        self.assertNotIn("response_id", serialized_062)
        self.assertNotIn("chatcmpl_test", serialized_062)

    def test_invalid_run_time_is_rejected_before_model_or_database(self):
        calls = []
        result = run_from_args(
            argparse.Namespace(
                run_at="not-an-iso-time",
                max_signals=1000,
                autonomous=False,
                execute=True,
                synthetic_network_canary=False,
            ),
            environment={
                SHADOW_FEATURE_FLAG: "1",
                "PGSERVICE": "n6_ai_agent",
                "PGSERVICEFILE": "/tmp/service",
                "PGPASSFILE": "/tmp/pass",
                DEEPSEEK_EGRESS_MODE_ENV:
                    DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
                PRODUCTION_KNOWLEDGE_MANIFEST_FILE_ENV: str(
                    PRODUCTION_MANIFEST
                ),
                PRODUCTION_KNOWLEDGE_MANIFEST_SHA256_ENV: (
                    PRODUCTION_KNOWLEDGE_MANIFEST_FILE_SHA256
                ),
            },
            repository_factory=lambda: calls.append("database"),
            model_adapter_factory=lambda: calls.append("model"),
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "invalid_run_time")
        self.assertFalse(result["model_called"])
        self.assertFalse(result["db_connected"])
        self.assertEqual(calls, [])

    def test_deepseek_autonomous_is_always_blocked_before_io(self):
        calls = []
        result = run_from_args(
            argparse.Namespace(
                run_at=None,
                max_signals=1000,
                autonomous=True,
                execute=True,
                synthetic_network_canary=False,
            ),
            environment={
                SHADOW_FEATURE_FLAG: "1",
                DEEPSEEK_MODEL_PROVIDER_ENV:
                    DEEPSEEK_MODEL_PROVIDER,
                DEEPSEEK_EGRESS_MODE_ENV:
                    DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
            },
            repository_factory=lambda: calls.append("database"),
            model_adapter_factory=lambda: calls.append("network"),
        )
        self.assertEqual(
            result["reason"], "deepseek_autonomous_always_blocked"
        )
        self.assertEqual(calls, [])


class ObservationAuditRepositoryContractTest(unittest.TestCase):
    class TraceCursor:
        def __init__(self, trace, rows, execute_error_sqls):
            self.trace = trace
            self.rows = rows
            self.execute_error_sqls = execute_error_sqls

        def __enter__(self):
            self.trace.append("cursor_enter")
            return self

        def __exit__(self, exc_type, exc, traceback):
            del exc_type, exc, traceback
            self.trace.append("cursor_exit")

        def execute(self, sql, params):
            self.trace.append(("execute", sql, params))
            if sql in self.execute_error_sqls:
                raise RuntimeError("injected_execute_failure")

        def fetchone(self):
            self.trace.append("fetchone")
            return {"result": self.rows.pop(0)}

    class TraceConnection:
        def __init__(self, rows, *, execute_error_sqls=()):
            self.trace = []
            self.rows = list(rows)
            self.execute_error_sqls = frozenset(execute_error_sqls)
            self.commit_count = 0
            self.rollback_count = 0

        def cursor(self):
            return ObservationAuditRepositoryContractTest.TraceCursor(
                self.trace, self.rows, self.execute_error_sqls
            )

        def commit(self):
            self.commit_count += 1
            self.trace.append("commit")

        def rollback(self):
            self.rollback_count += 1
            self.trace.append("rollback")

    @staticmethod
    def audit_base():
        return {
            "observation_run_id": "n6-shadow-" + "a" * 32,
            "dedup_key": "b" * 64,
            "trade_date": "2026-07-20",
            "provider": "deepseek",
            "model": DEEPSEEK_MODEL,
            "system_fingerprint": "fp_test",
            "one_shot_status": "shadow_decision_recorded",
            "identity_probe_succeeded": True,
            "decision_call_attempted": True,
            "structure_valid": True,
            "context_snapshot_id": 41,
            "proposal_created": False,
            "proposal_created_count": 0,
            "order_created_count": 0,
            "trade_created_count": 0,
            "position_mutation_count": 0,
            "lot_mutation_count": 0,
            "cash_mutation_count": 0,
            "input_token_count": 20,
            "output_token_count": 4,
            "total_token_count": 24,
            "cache_hit_token_count": 12,
            "cache_miss_token_count": 8,
            "latency_ms": 40,
            "started_at": "2026-07-20T10:00:00+08:00",
            "finished_at": "2026-07-20T10:00:00.001+08:00",
        }

    def test_real_repository_calls_061_then_062_and_commits_once(self):
        connection = self.TraceConnection(
            [
                {
                    "ok": True,
                    "status": "decision_recorded",
                    "decision_id": 51,
                    "server_risk_allowed": False,
                    "server_risk_reason": "hold_no_trade",
                },
                {
                    "ok": True,
                    "status": "observation_audit_recorded",
                    "audit_id": 61,
                },
            ]
        )
        result = FunctionOnlyAIAgentRepository(
            connection
        ).record_shadow_decision_with_observation(
            {"idempotency_key": "c" * 64}, self.audit_base()
        )
        executions = [
            item for item in connection.trace
            if isinstance(item, tuple) and item[0] == "execute"
        ]
        self.assertEqual(
            [item[1] for item in executions],
            [DECISION_RECORD_SQL, OBSERVATION_AUDIT_RECORD_SQL],
        )
        audit_payload = json.loads(executions[1][2][0])
        self.assertTrue(audit_payload["decision_call_attempted"])
        self.assertTrue(audit_payload["structure_valid"])
        self.assertEqual(audit_payload["context_snapshot_id"], 41)
        self.assertEqual(audit_payload["decision_id"], 51)
        self.assertNotIn("decision_run_id", audit_payload)
        self.assertFalse(audit_payload["server_risk_allowed"])
        self.assertEqual(
            audit_payload["server_risk_reason"], "hold_no_trade"
        )
        self.assertFalse(audit_payload["proposal_created"])
        for key in (
            "proposal_created_count",
            "order_created_count",
            "trade_created_count",
            "position_mutation_count",
            "lot_mutation_count",
            "cash_mutation_count",
        ):
            self.assertEqual(audit_payload[key], 0)
        self.assertEqual(connection.commit_count, 1)
        self.assertEqual(connection.rollback_count, 0)
        self.assertTrue(result["observation_audit_recorded"])

    def test_061_rejection_rolls_back_before_062_followup(self):
        connection = self.TraceConnection(
            [{"ok": False, "status": "decision_record_rejected"}]
        )
        result = FunctionOnlyAIAgentRepository(
            connection
        ).record_shadow_decision_with_observation(
            {"idempotency_key": "c" * 64}, self.audit_base()
        )
        executions = [
            item[1] for item in connection.trace
            if isinstance(item, tuple) and item[0] == "execute"
        ]
        self.assertEqual(executions, [DECISION_RECORD_SQL])
        self.assertEqual(connection.commit_count, 0)
        self.assertEqual(connection.rollback_count, 1)
        self.assertFalse(result["observation_audit_attempted"])
        self.assertTrue(result["observation_audit_followup_required"])
        self.assertFalse(result.get("observation_audit_skipped", False))

    def test_pre_062_local_failures_roll_back_and_allow_followup(self):
        valid_decision = {
            "ok": True,
            "status": "decision_recorded",
            "decision_id": 51,
            "server_risk_allowed": False,
            "server_risk_reason": "hold_no_trade",
        }
        cases = []

        invalid_id = dict(valid_decision)
        invalid_id["decision_id"] = 0
        cases.append(("invalid_decision_id", invalid_id, self.audit_base()))

        polluted = self.audit_base()
        polluted["decision_id"] = 999
        cases.append(("polluted_observation", valid_decision, polluted))

        unserializable = self.audit_base()
        unserializable["latency_ms"] = object()
        cases.append(("json_serialization", valid_decision, unserializable))

        for name, decision, observation in cases:
            with self.subTest(name=name):
                connection = self.TraceConnection([decision])
                result = FunctionOnlyAIAgentRepository(
                    connection
                ).record_shadow_decision_with_observation(
                    {"idempotency_key": "c" * 64}, observation
                )
                executions = [
                    item[1] for item in connection.trace
                    if isinstance(item, tuple)
                    and item[0] == "execute"
                ]
                self.assertEqual(executions, [DECISION_RECORD_SQL])
                self.assertEqual(connection.commit_count, 0)
                self.assertEqual(connection.rollback_count, 1)
                self.assertFalse(
                    result["observation_audit_attempted"]
                )
                self.assertTrue(
                    result["observation_audit_followup_required"]
                )

    def test_062_execute_exception_blocks_followup(self):
        connection = self.TraceConnection(
            [{
                "ok": True,
                "status": "decision_recorded",
                "decision_id": 51,
                "server_risk_allowed": False,
                "server_risk_reason": "hold_no_trade",
            }],
            execute_error_sqls=(OBSERVATION_AUDIT_RECORD_SQL,),
        )
        result = FunctionOnlyAIAgentRepository(
            connection
        ).record_shadow_decision_with_observation(
            {"idempotency_key": "c" * 64}, self.audit_base()
        )
        executions = [
            item[1] for item in connection.trace
            if isinstance(item, tuple) and item[0] == "execute"
        ]
        self.assertEqual(
            executions,
            [DECISION_RECORD_SQL, OBSERVATION_AUDIT_RECORD_SQL],
        )
        self.assertEqual(connection.commit_count, 0)
        self.assertEqual(connection.rollback_count, 1)
        self.assertTrue(result["observation_audit_attempted"])
        self.assertFalse(
            result.get("observation_audit_followup_required", False)
        )

    def test_062_failure_rolls_back_without_commit(self):
        connection = self.TraceConnection(
            [
                {
                    "ok": True,
                    "status": "decision_recorded",
                    "decision_id": 51,
                    "server_risk_allowed": True,
                    "server_risk_reason": "risk_allowed",
                },
                {
                    "ok": False,
                    "status": "observation_audit_decision_rejected",
                },
            ]
        )
        result = FunctionOnlyAIAgentRepository(
            connection
        ).record_shadow_decision_with_observation(
            {"idempotency_key": "c" * 64}, self.audit_base()
        )
        executions = [
            item[1] for item in connection.trace
            if isinstance(item, tuple) and item[0] == "execute"
        ]
        self.assertEqual(
            executions,
            [DECISION_RECORD_SQL, OBSERVATION_AUDIT_RECORD_SQL],
        )
        self.assertEqual(connection.commit_count, 0)
        self.assertEqual(connection.rollback_count, 1)
        self.assertEqual(result["status"], "observation_audit_rejected")
        self.assertTrue(result["observation_audit_attempted"])
        self.assertFalse(
            result.get("observation_audit_followup_required", False)
        )

    def test_062_invalid_audit_id_rolls_back_and_blocks_followup(self):
        connection = self.TraceConnection(
            [
                {
                    "ok": True,
                    "status": "decision_recorded",
                    "decision_id": 51,
                    "server_risk_allowed": False,
                    "server_risk_reason": "hold_no_trade",
                },
                {
                    "ok": True,
                    "status": "observation_audit_recorded",
                    "audit_id": 0,
                },
            ]
        )
        result = FunctionOnlyAIAgentRepository(
            connection
        ).record_shadow_decision_with_observation(
            {"idempotency_key": "c" * 64}, self.audit_base()
        )
        executions = [
            item[1] for item in connection.trace
            if isinstance(item, tuple) and item[0] == "execute"
        ]
        self.assertEqual(
            executions,
            [DECISION_RECORD_SQL, OBSERVATION_AUDIT_RECORD_SQL],
        )
        self.assertEqual(connection.commit_count, 0)
        self.assertEqual(connection.rollback_count, 1)
        self.assertTrue(result["observation_audit_attempted"])
        self.assertFalse(
            result.get("observation_audit_followup_required", False)
        )

    def test_builder_is_stable_zero_side_effect_and_content_free(self):
        probe = {
            "provider": "deepseek",
            "model": DEEPSEEK_MODEL,
            "system_fingerprint": "fp_test",
            "response_id": "probe_run_001",
            "input_tokens": 10,
            "output_tokens": 2,
            "total_tokens": 12,
            "prompt_cache_hit_tokens": 6,
            "prompt_cache_miss_tokens": 4,
            "latency_ms": 30,
        }
        run_at = datetime.fromisoformat("2026-07-20T10:02:59+08:00")
        event = {
            "one_shot_status": "decision_structure_invalid",
            "decision_call_attempted": True,
            "structure_valid": False,
            "model_call": {
                **probe,
                "reasoning_content": "forbidden",
                "prompt": "forbidden",
                "api_key": API_KEY,
                "session_id": "forbidden",
            },
        }
        first = _observation_audit_factory(
            provider_probe=probe,
            run_at=run_at,
            trade_date="2026-07-19",
        )(event)
        second = _observation_audit_factory(
            provider_probe=probe,
            run_at=run_at,
            trade_date="2026-07-19",
        )(event)
        self.assertEqual(first, second)
        self.assertEqual(first["trade_date"], "2026-07-19")
        self.assertFalse(first["structure_valid"])
        self.assertNotIn("decision_id", first)
        self.assertEqual(first["input_token_count"], 20)
        for key in (
            "proposal_created_count",
            "order_created_count",
            "trade_created_count",
            "position_mutation_count",
            "lot_mutation_count",
            "cash_mutation_count",
        ):
            self.assertEqual(first[key], 0)
        serialized = json.dumps(first, ensure_ascii=False)
        for forbidden in (
            "reasoning",
            "prompt",
            API_KEY,
            "session",
            "credential",
            "content",
            "response_id",
            "probe_run_001",
        ):
            self.assertNotIn(forbidden, serialized)
        changed_probe = {
            **probe,
            "response_id": "probe_run_002",
            "latency_ms": 99,
            "input_tokens": 11,
            "total_tokens": 13,
        }
        changed = _observation_audit_factory(
            provider_probe=changed_probe,
            run_at=run_at,
            trade_date="2026-07-19",
        )(event)
        self.assertNotEqual(first["observation_run_id"], changed[
            "observation_run_id"
        ])
        self.assertNotEqual(first["dedup_key"], changed["dedup_key"])

    def test_phase_a_hashes_remain_frozen(self):
        for relative_path, expected in PHASE_A_HASHES.items():
            with self.subTest(path=relative_path):
                self.assertEqual(
                    sha256((ROOT / relative_path).read_bytes()).hexdigest(),
                    expected,
                )


if __name__ == "__main__":
    unittest.main()
