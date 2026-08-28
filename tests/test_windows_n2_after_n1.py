from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Mapping, Sequence
import unittest

from ashare_v3.condition.windows_n2_after_n1 import (
    ActiveConditionRun,
    CalendarContext,
    run_windows_n2_after_n1,
)


POLICY_HASH = "policy-v19"
SOURCE_DATE = "20260827"
FOR_DATE = "20260828"


@dataclass
class FakeRepository:
    is_open: bool = True
    for_trade_date: str | None = FOR_DATE
    n1_statuses: list[str | None] = field(default_factory=lambda: ["passed"])
    active_runs: Sequence[ActiveConditionRun] = ()
    completion_calls: int = 0

    def calendar_context(self, trade_date: str) -> CalendarContext:
        return CalendarContext(trade_date, self.is_open, self.for_trade_date)

    def n1_completion_status(self, trade_date: str) -> str | None:
        index = min(self.completion_calls, len(self.n1_statuses) - 1)
        self.completion_calls += 1
        return self.n1_statuses[index]

    def active_condition_runs(
        self, source_trade_date: str, for_trade_date: str,
    ) -> Sequence[ActiveConditionRun]:
        return self.active_runs


@dataclass
class FakeClock:
    current: datetime = datetime(2026, 8, 27, 16, 35)

    def now(self) -> datetime:
        return self.current

    def sleep(self, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)


def passed_report() -> Mapping[str, Any]:
    return {
        "execute_run_id": "condition_layer_20260827_to_20260828_execute",
        "source_trade_date": SOURCE_DATE,
        "for_trade_date": FOR_DATE,
        "policy_hash": POLICY_HASH,
        "postcheck": {
            "run_status": "passed_active",
            "canonical_active_run_count": 1,
        },
    }


class WindowsN2AfterN1Test(unittest.TestCase):
    def test_executes_after_n1_passes(self) -> None:
        calls: list[str] = []
        result = run_windows_n2_after_n1(
            repository=FakeRepository(n1_statuses=[None, "running", "passed"]),
            policy_hash=POLICY_HASH,
            execute_n2=lambda source_date: calls.append(source_date) or passed_report(),
            now_fn=FakeClock().now,
            sleep_fn=lambda _: None,
        )
        self.assertEqual(result.result, "N2_AFTER_N1_PASS")
        self.assertEqual(result.active_run_id, "condition_layer_20260827_to_20260828_execute")
        self.assertEqual(calls, [SOURCE_DATE])

    def test_n1_failure_blocks_without_execute(self) -> None:
        called = False

        def execute(_: str) -> Mapping[str, Any]:
            nonlocal called
            called = True
            return passed_report()

        result = run_windows_n2_after_n1(
            repository=FakeRepository(n1_statuses=["failed"]),
            policy_hash=POLICY_HASH,
            execute_n2=execute,
        )
        self.assertEqual(result.result, "BLOCKED_N1_FAILED")
        self.assertFalse(called)

    def test_non_trading_day_skips_without_polling_or_execute(self) -> None:
        repository = FakeRepository(is_open=False, for_trade_date=None)
        result = run_windows_n2_after_n1(
            repository=repository,
            policy_hash=POLICY_HASH,
            execute_n2=lambda _: (_ for _ in ()).throw(AssertionError("must not execute")),
        )
        self.assertEqual(result.result, "SKIPPED_NON_TRADING_DAY")
        self.assertEqual(repository.completion_calls, 0)

    def test_identical_passed_active_is_idempotent(self) -> None:
        repository = FakeRepository(active_runs=(
            ActiveConditionRun("condition-run", "passed_active", POLICY_HASH),
        ))
        result = run_windows_n2_after_n1(
            repository=repository,
            policy_hash=POLICY_HASH,
            execute_n2=lambda _: (_ for _ in ()).throw(AssertionError("must not execute")),
        )
        self.assertEqual(result.result, "SKIPPED_IDENTICAL_PASSED_ACTIVE")
        self.assertEqual(result.active_run_id, "condition-run")

    def test_different_policy_active_run_blocks_without_overwrite(self) -> None:
        repository = FakeRepository(active_runs=(
            ActiveConditionRun("condition-run", "passed_active", "different-policy"),
        ))
        result = run_windows_n2_after_n1(
            repository=repository,
            policy_hash=POLICY_HASH,
            execute_n2=lambda _: (_ for _ in ()).throw(AssertionError("must not execute")),
        )
        self.assertEqual(result.result, "BLOCKED_ACTIVE_RUN_CONFLICT")
        self.assertEqual(result.active_run_id, "condition-run")

    def test_multiple_active_runs_block(self) -> None:
        repository = FakeRepository(active_runs=(
            ActiveConditionRun("run-a", "passed_active", POLICY_HASH),
            ActiveConditionRun("run-b", "passed", POLICY_HASH),
        ))
        result = run_windows_n2_after_n1(
            repository=repository,
            policy_hash=POLICY_HASH,
            execute_n2=lambda _: (_ for _ in ()).throw(AssertionError("must not execute")),
        )
        self.assertEqual(result.result, "BLOCKED_ACTIVE_RUN_CONFLICT")

    def test_missing_marker_times_out_at_2100(self) -> None:
        clock = FakeClock(current=datetime(2026, 8, 27, 20, 59, 59))
        result = run_windows_n2_after_n1(
            repository=FakeRepository(n1_statuses=[None]),
            policy_hash=POLICY_HASH,
            execute_n2=lambda _: (_ for _ in ()).throw(AssertionError("must not execute")),
            now_fn=clock.now,
            sleep_fn=clock.sleep,
            poll_seconds=1,
        )
        self.assertEqual(result.result, "BLOCKED_N1_TIMEOUT")

    def test_execute_postcheck_mismatch_fails(self) -> None:
        report = dict(passed_report())
        report["policy_hash"] = "wrong"
        result = run_windows_n2_after_n1(
            repository=FakeRepository(),
            policy_hash=POLICY_HASH,
            execute_n2=lambda _: report,
        )
        self.assertEqual(result.result, "N2_EXECUTE_POSTCHECK_FAILED")
