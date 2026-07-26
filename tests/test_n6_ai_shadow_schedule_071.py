"""N6 Shadow 071 nine-slot runtime and LaunchAgent contract tests."""

import argparse
from datetime import datetime
import inspect
from pathlib import Path
import unittest

from ashare_v3.user.ai_agent import (
    DISPLAY_TIMEZONE,
    PRODUCTION_KNOWLEDGE_MANIFEST_FILE_ENV,
    PRODUCTION_KNOWLEDGE_MANIFEST_FILE_SHA256,
    PRODUCTION_KNOWLEDGE_MANIFEST_SHA256_ENV,
    SHADOW_FEATURE_FLAG,
    SHADOW_SCHEDULE_POLICY_VERSION,
    SHADOW_SCHEDULE_SLOTS,
    run_agent_once,
    shadow_schedule_slot,
)
from ashare_v3.user.n6_ai_deepseek_adapter import (
    DEEPSEEK_EGRESS_MODE_ENV,
    DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
    DeepSeekChatCompletionsModelAdapter,
)
from scripts.plan_n6_ai_shadow_launchd import (
    AGENT_RECOVERY_WINDOWS_MINUTES,
    AGENT_START_CALENDAR_INTERVALS,
    build_launchd_plan,
)
from scripts.run_n6_ai_agent_once import run_from_args
from tests.test_n6_ai_agent import context_payload
from tests.test_n6_ai_deepseek_adapter import API_KEY, FakeTransport


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_MANIFEST = (
    ROOT / "docs/N6_AI_PRODUCTION_KNOWLEDGE_BUNDLE_MANIFEST_V1.json"
)


def local_time(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(DISPLAY_TIMEZONE)


def runner_environment() -> dict[str, str]:
    return {
        SHADOW_FEATURE_FLAG: "1",
        "PGSERVICE": "n6_ai_agent",
        "PGSERVICEFILE": "/tmp/service",
        "PGPASSFILE": "/tmp/pass",
        DEEPSEEK_EGRESS_MODE_ENV:
            DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
        PRODUCTION_KNOWLEDGE_MANIFEST_FILE_ENV:
            str(PRODUCTION_MANIFEST),
        PRODUCTION_KNOWLEDGE_MANIFEST_SHA256_ENV:
            PRODUCTION_KNOWLEDGE_MANIFEST_FILE_SHA256,
    }


def arguments(run_at: str | None = None) -> argparse.Namespace:
    return argparse.Namespace(
        run_at=run_at,
        max_signals=1000,
        autonomous=False,
        execute=True,
        synthetic_network_canary=False,
    )


class ScheduleRepository:
    def __init__(self, status: str = "open_slot_ready") -> None:
        self.status = status
        self.calls: list[tuple[str, object]] = []

    def shadow_schedule_preflight(self, **kwargs):
        self.calls.append(("shadow_schedule_preflight", dict(kwargs)))
        return {"ok": True, "status": self.status}

    def load_context(self, **kwargs):
        self.calls.append(("load_context", dict(kwargs)))
        return context_payload()

    def record_shadow_observation(self, payload):
        self.calls.append(("record_shadow_observation", dict(payload)))
        return {"ok": True, "status": "observation_audit_recorded"}


class SequenceClock:
    def __init__(self, *values: str) -> None:
        self.values = [local_time(value) for value in values]

    def __call__(self) -> datetime:
        if not self.values:
            raise AssertionError("unexpected_clock_read")
        return self.values.pop(0)


class N6AIShadowSchedule071Test(unittest.TestCase):
    def test_public_agent_function_signature_is_unchanged(self):
        self.assertEqual(
            tuple(inspect.signature(run_agent_once).parameters),
            (
                "repository",
                "model_adapter",
                "now",
                "requested_mode",
                "shadow_enabled",
                "autonomous_enabled",
                "max_signals",
                "risk_policy",
                "observation_audit_factory",
            ),
        )

    def test_local_gate_has_exact_nine_half_open_windows(self):
        cases = {
            "2026-07-20T09:29:59+08:00": None,
            "2026-07-20T09:30:00+08:00": "09:30",
            "2026-07-20T09:34:59+08:00": "09:30",
            "2026-07-20T09:35:00+08:00": None,
            "2026-07-20T10:00:00+08:00": "10:00",
            "2026-07-20T10:04:59+08:00": "10:00",
            "2026-07-20T10:05:00+08:00": None,
            "2026-07-20T10:30:00+08:00": "10:30",
            "2026-07-20T10:34:59+08:00": "10:30",
            "2026-07-20T11:00:00+08:00": "11:00",
            "2026-07-20T11:04:59+08:00": "11:00",
            "2026-07-20T11:30:00+08:00": "11:30",
            "2026-07-20T11:30:59+08:00": "11:30",
            "2026-07-20T11:31:00+08:00": None,
            "2026-07-20T13:30:00+08:00": "13:30",
            "2026-07-20T13:34:59+08:00": "13:30",
            "2026-07-20T14:00:00+08:00": "14:00",
            "2026-07-20T14:04:59+08:00": "14:00",
            "2026-07-20T14:30:00+08:00": "14:30",
            "2026-07-20T14:34:59+08:00": "14:30",
            "2026-07-20T15:00:00+08:00": "15:00",
            "2026-07-20T15:00:59+08:00": "15:00",
            "2026-07-20T15:01:00+08:00": None,
            "2026-07-25T10:00:00+08:00": None,
        }
        for timestamp, expected in cases.items():
            with self.subTest(timestamp=timestamp):
                self.assertEqual(
                    shadow_schedule_slot(local_time(timestamp)), expected
                )
        with self.assertRaisesRegex(
            ValueError, "timezone_aware_run_time_required"
        ):
            shadow_schedule_slot(datetime(2026, 7, 20, 10, 0))

    def test_closed_trade_date_and_weekend_use_zero_provider_requests(self):
        repository = ScheduleRepository("not_open_trade_date")
        provider_calls: list[str] = []
        closed = run_from_args(
            arguments("2026-07-20T10:00:00+08:00"),
            environment=runner_environment(),
            repository_factory=lambda: (repository, lambda: None),
            model_adapter_factory=lambda: provider_calls.append("provider"),
        )
        self.assertEqual(closed["status"], "not_open_trade_date")
        self.assertEqual(closed["deepseek_request_count"], 0)
        self.assertEqual(provider_calls, [])

        io_calls: list[str] = []
        weekend = run_from_args(
            arguments("2026-07-25T10:00:00+08:00"),
            environment=runner_environment(),
            repository_factory=lambda: io_calls.append("database"),
            model_adapter_factory=lambda: io_calls.append("provider"),
        )
        self.assertEqual(weekend["status"], "outside_shadow_slot")
        self.assertEqual(weekend["deepseek_request_count"], 0)
        self.assertEqual(io_calls, [])

    def test_window_is_rechecked_immediately_before_identity_probe(self):
        repository = ScheduleRepository()
        transport = FakeTransport()
        adapter = DeepSeekChatCompletionsModelAdapter(
            api_key=API_KEY,
            transport=transport,
            egress_mode=DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
            expected_system_fingerprint="fp_test",
        )
        result = run_from_args(
            arguments(),
            environment=runner_environment(),
            now_factory=SequenceClock(
                "2026-07-20T15:00:10+08:00",
                "2026-07-20T15:01:00+08:00",
            ),
            repository_factory=lambda: (repository, lambda: None),
            model_adapter_factory=lambda: adapter,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reason"],
            "shadow_schedule_window_closed_before_identity_probe",
        )
        self.assertEqual(result["deepseek_request_count"], 0)
        self.assertEqual(transport.calls, [])

    def test_same_slot_on_later_date_cannot_reopen_stale_run(self):
        repository = ScheduleRepository()
        transport = FakeTransport()
        adapter = DeepSeekChatCompletionsModelAdapter(
            api_key=API_KEY,
            transport=transport,
            egress_mode=DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
            expected_system_fingerprint="fp_test",
        )
        result = run_from_args(
            arguments(),
            environment=runner_environment(),
            now_factory=SequenceClock(
                "2026-07-20T10:00:10+08:00",
                "2026-07-21T10:00:10+08:00",
            ),
            repository_factory=lambda: (repository, lambda: None),
            model_adapter_factory=lambda: adapter,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reason"],
            "shadow_schedule_window_closed_before_identity_probe",
        )
        self.assertEqual(result["deepseek_request_count"], 0)
        self.assertEqual(transport.calls, [])

    def test_window_is_rechecked_immediately_before_decision_request(self):
        repository = ScheduleRepository()
        transport = FakeTransport()
        adapter = DeepSeekChatCompletionsModelAdapter(
            api_key=API_KEY,
            transport=transport,
            egress_mode=DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
            expected_system_fingerprint="fp_test",
        )
        result = run_from_args(
            arguments(),
            environment=runner_environment(),
            now_factory=SequenceClock(
                "2026-07-20T11:30:10+08:00",
                "2026-07-20T11:30:20+08:00",
                "2026-07-20T11:31:00+08:00",
            ),
            repository_factory=lambda: (repository, lambda: None),
            model_adapter_factory=lambda: adapter,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reason"],
            "shadow_schedule_window_closed_before_decision",
        )
        self.assertTrue(result["provider_probe_called"])
        self.assertFalse(result["decision_model_called"])
        self.assertEqual(result["deepseek_request_count"], 1)
        self.assertEqual(len(transport.calls), 1)
        self.assertTrue(
            any(call[0] == "record_shadow_observation"
                for call in repository.calls)
        )

    def test_provider_failure_has_no_automatic_retry(self):
        repository = ScheduleRepository()
        transport = FakeTransport(raises=True)
        adapter = DeepSeekChatCompletionsModelAdapter(
            api_key=API_KEY,
            transport=transport,
            egress_mode=DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
            expected_system_fingerprint="fp_test",
        )
        result = run_from_args(
            arguments(),
            environment=runner_environment(),
            now_factory=SequenceClock(
                "2026-07-20T10:00:10+08:00",
                "2026-07-20T10:00:20+08:00",
            ),
            repository_factory=lambda: (repository, lambda: None),
            model_adapter_factory=lambda: adapter,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reason"], "deepseek_provider_identity_probe_failed"
        )
        self.assertEqual(result["deepseek_request_count"], 1)
        self.assertEqual(len(transport.calls), 1)

    def test_nine_slots_lock_nine_plus_nine_daily_request_budget(self):
        self.assertEqual(
            SHADOW_SCHEDULE_POLICY_VERSION,
            "n6_ai_shadow_open_trade_date_nine_slots_071_v1",
        )
        self.assertEqual(len(SHADOW_SCHEDULE_SLOTS), 9)
        self.assertEqual(
            len({(hour, minute) for hour, minute, _label, _window
                 in SHADOW_SCHEDULE_SLOTS}),
            9,
        )
        maximum_identity_probes = len(SHADOW_SCHEDULE_SLOTS)
        maximum_decision_calls = len(SHADOW_SCHEDULE_SLOTS)
        self.assertEqual(maximum_identity_probes, 9)
        self.assertEqual(maximum_decision_calls, 9)
        self.assertEqual(
            maximum_identity_probes + maximum_decision_calls, 18
        )

    def test_launchagent_has_exact_nine_calendar_descriptors(self):
        expected = [
            {"Hour": 9, "Minute": 30},
            {"Hour": 10, "Minute": 0},
            {"Hour": 10, "Minute": 30},
            {"Hour": 11, "Minute": 0},
            {"Hour": 11, "Minute": 30},
            {"Hour": 13, "Minute": 30},
            {"Hour": 14, "Minute": 0},
            {"Hour": 14, "Minute": 30},
            {"Hour": 15, "Minute": 0},
        ]
        self.assertEqual(AGENT_START_CALENDAR_INTERVALS, expected)
        self.assertEqual(
            AGENT_RECOVERY_WINDOWS_MINUTES,
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
        report = build_launchd_plan(
            release_path=Path(
                "/Users/chuanfuchen/.local/share/ashare-v3/releases/"
                "n6-ai/20260718_120000__" + "a" * 40
            ),
            runtime_env_path=Path(
                "/Users/chuanfuchen/.local/share/ashare-v3/runtime-envs/"
                "n6-ai/n6-ai-shadow-v1-20260718"
            ),
            pg_service_file=Path(
                "/Users/chuanfuchen/.config/ashare-v3/postgresql/"
                "pg_service.conf"
            ),
            pg_pass_file=Path(
                "/Users/chuanfuchen/.config/ashare-v3/postgresql/"
                "n6_ai_agent.pgpass"
            ),
            deepseek_api_key_file=Path(
                "/Users/chuanfuchen/.config/ashare-v3/deepseek/"
                "n6_ai_agent_api_key"
            ),
            deepseek_system_fingerprint="fp_reviewed_test_v1",
        )
        plist = report["agent_shadow"]["plist"]
        self.assertEqual(plist["StartCalendarInterval"], expected)
        self.assertNotIn("StartInterval", plist)
        self.assertFalse(plist["RunAtLoad"])
        self.assertFalse(plist["KeepAlive"])


if __name__ == "__main__":
    unittest.main()
