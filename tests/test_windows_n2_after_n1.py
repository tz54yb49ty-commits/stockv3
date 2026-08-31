from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Mapping, Sequence
import unittest
from unittest.mock import MagicMock, patch

from ashare_v3.condition.windows_n2_after_n1 import (
    ActiveConditionRun,
    CalendarContext,
    PostgresAfterN1Repository,
    run_windows_n2_after_n1,
)


POLICY_HASH = "policy-v19"
SOURCE_DATE = "20260827"
FOR_DATE = "20260828"
RECOVERY_SOURCE_DATE = "20260831"
RECOVERY_FOR_DATE = "20260901"


@dataclass
class FakeRepository:
    is_open: bool = True
    for_trade_date: str | None = FOR_DATE
    n1_statuses: list[str | None] = field(default_factory=lambda: ["passed"])
    latest_completed_date: str | None = SOURCE_DATE
    calendars: Mapping[str, CalendarContext] = field(default_factory=dict)
    active_runs: Sequence[ActiveConditionRun] = ()
    completion_calls: int = 0
    latest_completion_calls: int = 0
    calendar_calls: list[str] = field(default_factory=list)

    def calendar_context(self, trade_date: str) -> CalendarContext:
        self.calendar_calls.append(trade_date)
        if trade_date in self.calendars:
            return self.calendars[trade_date]
        return CalendarContext(trade_date, self.is_open, self.for_trade_date)

    def n1_completion_status(self, trade_date: str) -> str | None:
        index = min(self.completion_calls, len(self.n1_statuses) - 1)
        self.completion_calls += 1
        return self.n1_statuses[index]

    def latest_completed_n1_date(self, on_or_before: str) -> str | None:
        self.latest_completion_calls += 1
        return self.latest_completed_date

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


def passed_report(
    source_trade_date: str = SOURCE_DATE,
    for_trade_date: str = FOR_DATE,
) -> Mapping[str, Any]:
    return {
        "execute_run_id": "condition_layer_20260827_to_20260828_execute",
        "source_trade_date": source_trade_date,
        "for_trade_date": for_trade_date,
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

    def test_normal_window_waits_for_today_then_selects_latest_completion(self) -> None:
        repository = FakeRepository(n1_statuses=[None, "passed"])
        clock = FakeClock()
        result = run_windows_n2_after_n1(
            repository=repository,
            policy_hash=POLICY_HASH,
            execute_n2=lambda _: passed_report(),
            now_fn=clock.now,
            sleep_fn=clock.sleep,
            poll_seconds=1,
        )
        self.assertEqual(result.result, "N2_AFTER_N1_PASS")
        self.assertEqual(repository.completion_calls, 2)
        self.assertEqual(repository.latest_completion_calls, 1)

    def test_fixed_source_date_executes_without_polling_or_latest_selection(self) -> None:
        repository = FakeRepository(
            n1_statuses=["passed"],
            latest_completed_date="20260828",
            calendars={
                RECOVERY_SOURCE_DATE: CalendarContext(
                    RECOVERY_SOURCE_DATE, True, RECOVERY_FOR_DATE
                ),
            },
        )
        calls: list[str] = []
        result = run_windows_n2_after_n1(
            repository=repository,
            policy_hash=POLICY_HASH,
            execute_n2=lambda source: calls.append(source) or passed_report(
                RECOVERY_SOURCE_DATE, RECOVERY_FOR_DATE
            ),
            source_trade_date=RECOVERY_SOURCE_DATE,
            now_fn=lambda: datetime(2026, 9, 1, 0, 15),
            sleep_fn=lambda _: (_ for _ in ()).throw(
                AssertionError("fixed recovery must not poll")
            ),
        )
        self.assertEqual(result.result, "N2_AFTER_N1_PASS")
        self.assertEqual(result.source_trade_date, RECOVERY_SOURCE_DATE)
        self.assertEqual(result.for_trade_date, RECOVERY_FOR_DATE)
        self.assertEqual(result.n1_status, "passed")
        self.assertEqual(calls, [RECOVERY_SOURCE_DATE])
        self.assertEqual(repository.completion_calls, 1)
        self.assertEqual(repository.latest_completion_calls, 0)
        self.assertEqual(repository.calendar_calls, [RECOVERY_SOURCE_DATE])

    def test_fixed_source_date_failed_marker_blocks_immediately(self) -> None:
        repository = FakeRepository(
            n1_statuses=["failed"],
            calendars={
                RECOVERY_SOURCE_DATE: CalendarContext(
                    RECOVERY_SOURCE_DATE, True, RECOVERY_FOR_DATE
                ),
            },
        )
        result = run_windows_n2_after_n1(
            repository=repository,
            policy_hash=POLICY_HASH,
            execute_n2=lambda _: (_ for _ in ()).throw(
                AssertionError("must not execute")
            ),
            source_trade_date=RECOVERY_SOURCE_DATE,
            now_fn=lambda: datetime(2026, 9, 1, 0, 15),
            sleep_fn=lambda _: (_ for _ in ()).throw(
                AssertionError("fixed recovery must not poll")
            ),
        )
        self.assertEqual(result.result, "BLOCKED_N1_FAILED")
        self.assertEqual(result.n1_status, "failed")
        self.assertEqual(repository.completion_calls, 1)
        self.assertEqual(repository.latest_completion_calls, 0)

    def test_fixed_source_date_missing_passed_marker_blocks_immediately(self) -> None:
        repository = FakeRepository(
            n1_statuses=[None],
            calendars={
                RECOVERY_SOURCE_DATE: CalendarContext(
                    RECOVERY_SOURCE_DATE, True, RECOVERY_FOR_DATE
                ),
            },
        )
        result = run_windows_n2_after_n1(
            repository=repository,
            policy_hash=POLICY_HASH,
            execute_n2=lambda _: (_ for _ in ()).throw(
                AssertionError("must not execute")
            ),
            source_trade_date=RECOVERY_SOURCE_DATE,
            now_fn=lambda: datetime(2026, 9, 1, 0, 15),
        )
        self.assertEqual(result.result, "BLOCKED_N1_COMPLETION_MISSING")
        self.assertIsNone(result.n1_status)
        self.assertEqual(repository.latest_completion_calls, 0)

    def test_fixed_source_date_identical_active_is_idempotent(self) -> None:
        repository = FakeRepository(
            n1_statuses=["passed"],
            calendars={
                RECOVERY_SOURCE_DATE: CalendarContext(
                    RECOVERY_SOURCE_DATE, True, RECOVERY_FOR_DATE
                ),
            },
            active_runs=(
                ActiveConditionRun("recovery-run", "passed_active", POLICY_HASH),
            ),
        )
        result = run_windows_n2_after_n1(
            repository=repository,
            policy_hash=POLICY_HASH,
            execute_n2=lambda _: (_ for _ in ()).throw(
                AssertionError("must not execute")
            ),
            source_trade_date=RECOVERY_SOURCE_DATE,
            now_fn=lambda: datetime(2026, 9, 1, 0, 15),
        )
        self.assertEqual(result.result, "SKIPPED_IDENTICAL_PASSED_ACTIVE")
        self.assertEqual(result.active_run_id, "recovery-run")

    def test_fixed_source_date_active_conflict_blocks(self) -> None:
        repository = FakeRepository(
            n1_statuses=["passed"],
            calendars={
                RECOVERY_SOURCE_DATE: CalendarContext(
                    RECOVERY_SOURCE_DATE, True, RECOVERY_FOR_DATE
                ),
            },
            active_runs=(
                ActiveConditionRun("conflict-run", "passed_active", "other-policy"),
            ),
        )
        result = run_windows_n2_after_n1(
            repository=repository,
            policy_hash=POLICY_HASH,
            execute_n2=lambda _: (_ for _ in ()).throw(
                AssertionError("must not execute")
            ),
            source_trade_date=RECOVERY_SOURCE_DATE,
            now_fn=lambda: datetime(2026, 9, 1, 0, 15),
        )
        self.assertEqual(result.result, "BLOCKED_ACTIVE_RUN_CONFLICT")
        self.assertEqual(result.active_run_id, "conflict-run")

    def test_fixed_source_date_rejects_closed_or_future_date(self) -> None:
        closed_repository = FakeRepository(
            calendars={
                RECOVERY_SOURCE_DATE: CalendarContext(
                    RECOVERY_SOURCE_DATE, False, None
                ),
            },
        )
        closed = run_windows_n2_after_n1(
            repository=closed_repository,
            policy_hash=POLICY_HASH,
            execute_n2=lambda _: (_ for _ in ()).throw(
                AssertionError("must not execute")
            ),
            source_trade_date=RECOVERY_SOURCE_DATE,
            now_fn=lambda: datetime(2026, 9, 1, 0, 15),
        )
        self.assertEqual(closed.result, "BLOCKED_SOURCE_DATE_NOT_OPEN")
        self.assertEqual(closed_repository.completion_calls, 0)

        with self.assertRaisesRegex(ValueError, "future"):
            run_windows_n2_after_n1(
                repository=FakeRepository(),
                policy_hash=POLICY_HASH,
                execute_n2=lambda _: passed_report(),
                source_trade_date="20260902",
                now_fn=lambda: datetime(2026, 9, 1, 0, 15),
            )

    def test_delayed_morning_uses_latest_completed_n1_date(self) -> None:
        repository = FakeRepository(
            latest_completed_date=SOURCE_DATE,
            calendars={
                "20260828": CalendarContext("20260828", True, "20260831"),
                SOURCE_DATE: CalendarContext(SOURCE_DATE, True, FOR_DATE),
            },
        )
        calls: list[str] = []
        result = run_windows_n2_after_n1(
            repository=repository,
            policy_hash=POLICY_HASH,
            execute_n2=lambda source_date: calls.append(source_date) or passed_report(),
            now_fn=lambda: datetime(2026, 8, 28, 9, 0),
        )
        self.assertEqual(result.result, "N2_AFTER_N1_PASS")
        self.assertEqual(result.source_trade_date, SOURCE_DATE)
        self.assertEqual(result.for_trade_date, FOR_DATE)
        self.assertEqual(calls, [SOURCE_DATE])
        self.assertEqual(repository.completion_calls, 0)
        self.assertEqual(repository.latest_completion_calls, 1)
        self.assertEqual(repository.calendar_calls, ["20260828", SOURCE_DATE])

    def test_delayed_cross_weekend_uses_friday_completion_for_monday(self) -> None:
        source_date = "20260828"
        for_date = "20260831"
        repository = FakeRepository(
            latest_completed_date=source_date,
            calendars={
                for_date: CalendarContext(for_date, True, "20260901"),
                source_date: CalendarContext(source_date, True, for_date),
            },
        )
        calls: list[str] = []
        result = run_windows_n2_after_n1(
            repository=repository,
            policy_hash=POLICY_HASH,
            execute_n2=lambda source: calls.append(source) or passed_report(source, for_date),
            now_fn=lambda: datetime(2026, 8, 31, 8, 45),
        )
        self.assertEqual(result.result, "N2_AFTER_N1_PASS")
        self.assertEqual(result.source_trade_date, source_date)
        self.assertEqual(result.for_trade_date, for_date)
        self.assertEqual(calls, [source_date])

    def test_delayed_start_without_any_completed_n1_blocks(self) -> None:
        repository = FakeRepository(
            latest_completed_date=None,
            calendars={
                "20260828": CalendarContext("20260828", True, "20260831"),
            },
        )
        result = run_windows_n2_after_n1(
            repository=repository,
            policy_hash=POLICY_HASH,
            execute_n2=lambda _: (_ for _ in ()).throw(AssertionError("must not execute")),
            now_fn=lambda: datetime(2026, 8, 28, 9, 0),
        )
        self.assertEqual(result.result, "BLOCKED_N1_COMPLETION_MISSING")
        self.assertEqual(repository.completion_calls, 0)

    def test_after_deadline_uses_latest_completion_without_polling(self) -> None:
        repository = FakeRepository(latest_completed_date=SOURCE_DATE)
        result = run_windows_n2_after_n1(
            repository=repository,
            policy_hash=POLICY_HASH,
            execute_n2=lambda _: passed_report(),
            now_fn=lambda: datetime(2026, 8, 27, 21, 5),
        )
        self.assertEqual(result.result, "N2_AFTER_N1_PASS")
        self.assertEqual(repository.completion_calls, 0)
        self.assertEqual(repository.latest_completion_calls, 1)

    def test_normal_window_does_not_fall_back_to_older_completion(self) -> None:
        repository = FakeRepository(
            n1_statuses=["passed"],
            latest_completed_date="20260826",
        )
        result = run_windows_n2_after_n1(
            repository=repository,
            policy_hash=POLICY_HASH,
            execute_n2=lambda _: (_ for _ in ()).throw(AssertionError("must not execute")),
            now_fn=FakeClock().now,
        )
        self.assertEqual(result.result, "BLOCKED_N1_COMPLETION_MISSING")
        self.assertEqual(result.source_trade_date, SOURCE_DATE)
        self.assertEqual(repository.completion_calls, 1)
        self.assertEqual(repository.latest_completion_calls, 1)

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
            now_fn=FakeClock().now,
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
        self.assertEqual(repository.latest_completion_calls, 0)

    def test_identical_passed_active_is_idempotent(self) -> None:
        repository = FakeRepository(active_runs=(
            ActiveConditionRun("condition-run", "passed_active", POLICY_HASH),
        ))
        result = run_windows_n2_after_n1(
            repository=repository,
            policy_hash=POLICY_HASH,
            execute_n2=lambda _: (_ for _ in ()).throw(AssertionError("must not execute")),
            now_fn=FakeClock().now,
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
            now_fn=FakeClock().now,
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
            now_fn=FakeClock().now,
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
            now_fn=FakeClock().now,
        )
        self.assertEqual(result.result, "N2_EXECUTE_POSTCHECK_FAILED")


class PostgresAfterN1RepositoryTest(unittest.TestCase):
    def test_latest_completed_n1_date_is_read_only_and_cut_off(self) -> None:
        connection = MagicMock()
        cursor = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        cursor.fetchone.return_value = (SOURCE_DATE,)
        with patch(
            "ashare_v3.condition.windows_n2_after_n1.psycopg.connect"
        ) as connect:
            connect.return_value.__enter__.return_value = connection
            result = PostgresAfterN1Repository("postgresql://example").latest_completed_n1_date(
                "20260828"
            )

        self.assertEqual(result, SOURCE_DATE)
        connect.assert_called_once_with(
            "postgresql://example",
            connect_timeout=10,
            options="-c default_transaction_read_only=on",
        )
        statement, parameters = cursor.execute.call_args.args
        self.assertIn("trade_date <= %s", statement)
        self.assertIn("data_type='fastlane_complete'", statement)
        self.assertIn("status='passed'", statement)
        self.assertIn("ORDER BY trade_date DESC", statement)
        self.assertEqual(parameters, ("20260828",))
