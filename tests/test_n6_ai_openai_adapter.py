from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from ashare_v3.user.ai_agent import (
    PRODUCTION_KNOWLEDGE_MANIFEST_FILE_ENV,
    PRODUCTION_KNOWLEDGE_MANIFEST_FILE_SHA256,
    PRODUCTION_KNOWLEDGE_MANIFEST_SHA256_ENV,
    SHADOW_FEATURE_FLAG,
)
from ashare_v3.user.n6_ai_openai_adapter import (
    DECISION_JSON_SCHEMA,
    OPENAI_API_KEY_FILE_ENV,
    OPENAI_HOST,
    OPENAI_MODEL,
    OPENAI_PATH,
    OpenAIAdapterError,
    OpenAIResponsesModelAdapter,
)
from scripts.run_n6_ai_agent_once import run_from_args


API_KEY = "sk-test-" + "a" * 40
ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_MANIFEST = (
    ROOT
    / "docs/N6_AI_PRODUCTION_KNOWLEDGE_BUNDLE_MANIFEST_V1.json"
)


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


def completed_response(payload=None):
    return {
        "id": "resp_test",
        "status": "completed",
        "error": None,
        "usage": {
            "input_tokens": 120,
            "output_tokens": 30,
            "total_tokens": 150,
        },
        "_n6_transport_metadata": {
            "provider_request_id": "req_test",
            "latency_ms": 321,
        },
        "output": [
            {"type": "reasoning", "id": "reasoning_test"},
            {
                "type": "message",
                "status": "completed",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(
                            payload or decision_payload(),
                            ensure_ascii=False,
                        ),
                    }
                ],
            },
        ],
    }


class FakeTransport:
    def __init__(self, response=None, *, raises=False):
        self.response = response or completed_response()
        self.raises = raises
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.raises:
            raise RuntimeError("provider secret detail")
        return self.response


class OpenAIResponsesAdapterTest(unittest.TestCase):
    def test_request_is_fixed_stateless_strict_and_tool_free(self):
        transport = FakeTransport()
        adapter = OpenAIResponsesModelAdapter(
            api_key=API_KEY,
            transport=transport,
        )
        context = {
            "knowledge_bundle_hash": "a" * 64,
            "signals": [],
            "positions": [],
        }
        self.assertEqual(adapter.generate_decision(context), decision_payload())
        self.assertEqual(
            adapter.last_call_metadata,
            {
                "provider": "openai",
                "model": OPENAI_MODEL,
                "provider_request_id": "req_test",
                "response_id": "resp_test",
                "input_tokens": 120,
                "output_tokens": 30,
                "total_tokens": 150,
                "latency_ms": 321,
            },
        )
        self.assertEqual(len(transport.calls), 1)
        call = transport.calls[0]
        request = call["payload"]
        self.assertEqual(request["model"], OPENAI_MODEL)
        self.assertEqual(request["reasoning"], {"effort": "high"})
        self.assertIs(request["store"], False)
        self.assertEqual(request["tools"], [])
        self.assertEqual(request["tool_choice"], "none")
        self.assertNotIn("previous_response_id", request)
        self.assertNotIn(API_KEY, json.dumps(request))
        self.assertEqual(json.loads(request["input"]), context)
        output_format = request["text"]["format"]
        self.assertEqual(output_format["type"], "json_schema")
        self.assertIs(output_format["strict"], True)
        self.assertEqual(output_format["schema"], DECISION_JSON_SCHEMA)
        self.assertEqual(OPENAI_HOST, "api.openai.com")
        self.assertEqual(OPENAI_PATH, "/v1/responses")

    def test_environment_uses_only_owner_0600_key_file(self):
        with tempfile.TemporaryDirectory() as directory:
            key_path = Path(directory) / "api-key"
            key_path.write_text(API_KEY + "\n", encoding="utf-8")
            key_path.chmod(0o600)
            transport = FakeTransport()
            adapter = OpenAIResponsesModelAdapter.from_environment(
                {OPENAI_API_KEY_FILE_ENV: str(key_path)},
                transport=transport,
            )
            self.assertEqual(
                adapter.generate_decision({}), decision_payload()
            )

            key_path.chmod(0o644)
            with self.assertRaisesRegex(
                OpenAIAdapterError, "credential_file_unsafe"
            ):
                OpenAIResponsesModelAdapter.from_environment(
                    {OPENAI_API_KEY_FILE_ENV: str(key_path)}
                )

    def test_environment_rejects_secret_base_url_and_openai_overrides(self):
        with tempfile.TemporaryDirectory() as directory:
            key_path = Path(directory) / "api-key"
            key_path.write_text(API_KEY, encoding="utf-8")
            key_path.chmod(0o600)
            base = {OPENAI_API_KEY_FILE_ENV: str(key_path)}
            for forbidden in (
                {"OPENAI_API_KEY": API_KEY},
                {"OPENAI_BASE_URL": "https://example.invalid"},
                {"OPENAI_PROXY": "http://example.invalid"},
            ):
                with self.assertRaisesRegex(
                    OpenAIAdapterError, "environment_not_allowed"
                ):
                    OpenAIResponsesModelAdapter.from_environment(
                        {**base, **forbidden}
                    )

    def test_ambient_proxy_environment_cannot_change_fixed_transport(self):
        with tempfile.TemporaryDirectory() as directory:
            key_path = Path(directory) / "api-key"
            key_path.write_text(API_KEY, encoding="utf-8")
            key_path.chmod(0o600)
            transport = FakeTransport()
            adapter = OpenAIResponsesModelAdapter.from_environment(
                {
                    OPENAI_API_KEY_FILE_ENV: str(key_path),
                    "HTTP_PROXY": "http://127.0.0.1:7890",
                    "HTTPS_PROXY": "http://127.0.0.1:7890",
                    "ALL_PROXY": "socks5://127.0.0.1:7890",
                    "NO_PROXY": "localhost,127.0.0.1",
                    "custom_proxy": "http://example.invalid",
                },
                transport=transport,
            )
            self.assertEqual(
                adapter.generate_decision({}), decision_payload()
            )
            self.assertEqual(transport.calls[0]["timeout_seconds"], 45)

    def test_key_path_symlink_and_invalid_key_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            real_path = Path(directory) / "real-key"
            real_path.write_text(API_KEY, encoding="utf-8")
            real_path.chmod(0o600)
            link_path = Path(directory) / "link-key"
            link_path.symlink_to(real_path)
            with self.assertRaisesRegex(
                OpenAIAdapterError, "credential_file_unsafe"
            ):
                OpenAIResponsesModelAdapter.from_environment(
                    {OPENAI_API_KEY_FILE_ENV: str(link_path)}
                )
            with self.assertRaisesRegex(
                OpenAIAdapterError, "credential_invalid"
            ):
                OpenAIResponsesModelAdapter(api_key="not-a-key")

    def test_provider_failures_never_return_unvalidated_output(self):
        cases = [
            {"status": "incomplete", "error": None, "output": []},
            {"status": "completed", "error": None, "output": []},
            {
                "status": "completed",
                "error": None,
                "output": [
                    {
                        "type": "message",
                        "status": "completed",
                        "content": [
                            {"type": "refusal", "refusal": "cannot comply"}
                        ],
                    }
                ],
            },
            {
                "status": "completed",
                "error": None,
                "output": [
                    {
                        "type": "message",
                        "status": "completed",
                        "content": [
                            {"type": "output_text", "text": "not-json"}
                        ],
                    }
                ],
            },
        ]
        for response in cases:
            adapter = OpenAIResponsesModelAdapter(
                api_key=API_KEY,
                transport=FakeTransport(response),
            )
            with self.assertRaises(OpenAIAdapterError):
                adapter.generate_decision({})

    def test_runner_never_falls_back_to_openai_or_connects_database(self):
        calls = []
        base_environment = {
            SHADOW_FEATURE_FLAG: "1",
            "PGSERVICE": "n6_ai_agent",
            "PGSERVICEFILE": "/tmp/service",
            "PGPASSFILE": "/tmp/pass",
            PRODUCTION_KNOWLEDGE_MANIFEST_FILE_ENV: str(
                PRODUCTION_MANIFEST
            ),
            PRODUCTION_KNOWLEDGE_MANIFEST_SHA256_ENV: (
                PRODUCTION_KNOWLEDGE_MANIFEST_FILE_SHA256
            ),
        }
        for forbidden in (
            {OPENAI_API_KEY_FILE_ENV: "/tmp/key"},
            {"OPENAI_API_KEY": API_KEY},
        ):
            environment = {**base_environment, **forbidden}
            with self.subTest(forbidden=forbidden):
                with mock.patch.object(
                    OpenAIResponsesModelAdapter,
                    "from_environment",
                    side_effect=AssertionError("OpenAI fallback used"),
                ) as openai_factory:
                    result = run_from_args(
                        argparse.Namespace(
                            run_at="2026-07-20T10:30:00+08:00",
                            max_signals=1000,
                            autonomous=False,
                            execute=True,
                        ),
                        environment=environment,
                        repository_factory=lambda: calls.append(
                            "database"
                        ),
                    )
                openai_factory.assert_not_called()
                self.assertEqual(
                    result["reason"],
                    "model_adapter_configuration_invalid",
                )
                self.assertNotIn("fallback", json.dumps(result))
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
