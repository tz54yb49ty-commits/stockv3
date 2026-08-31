"""Windows N2 runner that waits for the daily N1 completion marker.

The module owns only N2 orchestration.  It reads N1/calendar state and invokes
an injected N2 execute callback; it never runs N1 or any downstream layer.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, time
import time as time_module
from typing import Any, Callable, Mapping, Protocol, Sequence

import psycopg


CANONICAL_ACTIVE_STATUS = "passed_active"
TERMINAL_N1_FAILURE_STATUSES = frozenset({"failed", "blocked", "rolled_back"})


@dataclass(frozen=True)
class CalendarContext:
    source_trade_date: str
    is_open: bool
    for_trade_date: str | None


@dataclass(frozen=True)
class ActiveConditionRun:
    run_id: str
    status: str
    policy_hash: str


@dataclass(frozen=True)
class WindowsN2AfterN1Result:
    result: str
    source_trade_date: str
    for_trade_date: str | None
    policy_hash: str
    active_run_id: str | None = None
    n1_status: str | None = None
    execute_report: Mapping[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AfterN1Repository(Protocol):
    def calendar_context(self, trade_date: str) -> CalendarContext: ...

    def n1_completion_status(self, trade_date: str) -> str | None: ...

    def latest_completed_n1_date(self, on_or_before: str) -> str | None: ...

    def active_condition_runs(
        self, source_trade_date: str, for_trade_date: str,
    ) -> Sequence[ActiveConditionRun]: ...


@dataclass
class PostgresAfterN1Repository:
    dsn: str

    def calendar_context(self, trade_date: str) -> CalendarContext:
        with psycopg.connect(
            self.dsn,
            connect_timeout=10,
            options="-c default_transaction_read_only=on",
        ) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT is_open FROM common_trade_calendar WHERE trade_date=%s",
                (trade_date,),
            )
            row = cur.fetchone()
            if row is None:
                raise RuntimeError(f"trade calendar missing date: {trade_date}")
            is_open = bool(row[0])
            if not is_open:
                return CalendarContext(trade_date, False, None)
            cur.execute(
                """
                SELECT trade_date
                FROM common_trade_calendar
                WHERE trade_date > %s AND is_open = true
                ORDER BY trade_date
                LIMIT 1
                """,
                (trade_date,),
            )
            next_row = cur.fetchone()
            if next_row is None:
                raise RuntimeError(f"next open trade date missing after: {trade_date}")
            return CalendarContext(trade_date, True, str(next_row[0]))

    def n1_completion_status(self, trade_date: str) -> str | None:
        with psycopg.connect(
            self.dsn,
            connect_timeout=10,
            options="-c default_transaction_read_only=on",
        ) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT status
                FROM common_ingest_batch
                WHERE trade_date=%s
                  AND data_domain='common'
                  AND data_type='fastlane_complete'
                ORDER BY finished_at DESC NULLS LAST, started_at DESC
                LIMIT 1
                """,
                (trade_date,),
            )
            row = cur.fetchone()
            return None if row is None else str(row[0])

    def latest_completed_n1_date(self, on_or_before: str) -> str | None:
        with psycopg.connect(
            self.dsn,
            connect_timeout=10,
            options="-c default_transaction_read_only=on",
        ) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT trade_date
                FROM common_ingest_batch
                WHERE trade_date <= %s
                  AND data_domain='common'
                  AND data_type='fastlane_complete'
                  AND status='passed'
                ORDER BY trade_date DESC,
                         finished_at DESC NULLS LAST,
                         started_at DESC
                LIMIT 1
                """,
                (on_or_before,),
            )
            row = cur.fetchone()
            return None if row is None else str(row[0])

    def active_condition_runs(
        self, source_trade_date: str, for_trade_date: str,
    ) -> Sequence[ActiveConditionRun]:
        with psycopg.connect(
            self.dsn,
            connect_timeout=10,
            options="-c default_transaction_read_only=on",
        ) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT run_id, status,
                       COALESCE(raw_json #>> '{policy_metadata,policy_hash}', '')
                FROM common_condition_run
                WHERE source_trade_date=%s
                  AND for_trade_date=%s
                  AND status IN ('running', 'passed_active', 'passed')
                ORDER BY created_at DESC
                """,
                (source_trade_date, for_trade_date),
            )
            return tuple(
                ActiveConditionRun(
                    run_id=str(row[0]),
                    status=str(row[1]),
                    policy_hash=str(row[2] or ""),
                )
                for row in cur.fetchall()
            )


def run_windows_n2_after_n1(
    *,
    repository: AfterN1Repository,
    policy_hash: str,
    execute_n2: Callable[[str], Mapping[str, Any]],
    source_trade_date: str | None = None,
    now_fn: Callable[[], datetime] = datetime.now,
    sleep_fn: Callable[[float], None] = time_module.sleep,
    poll_seconds: float = 30.0,
    scheduled_start: time = time(16, 35),
    deadline: time = time(21, 0),
) -> WindowsN2AfterN1Result:
    """Select one completed N1 date and execute exactly one N2 run if needed."""
    started_at = now_fn()
    if source_trade_date is not None:
        try:
            parsed_source_date = datetime.strptime(
                source_trade_date, "%Y%m%d"
            ).date()
        except ValueError as exc:
            raise ValueError("source_trade_date must use YYYYMMDD") from exc
        if parsed_source_date > started_at.date():
            raise ValueError("source_trade_date cannot be in the future")
        source_trade_date = parsed_source_date.strftime("%Y%m%d")
        calendar = repository.calendar_context(source_trade_date)
        if not calendar.is_open or not calendar.for_trade_date:
            return WindowsN2AfterN1Result(
                result="BLOCKED_SOURCE_DATE_NOT_OPEN",
                source_trade_date=source_trade_date,
                for_trade_date=calendar.for_trade_date,
                policy_hash=policy_hash,
            )
        n1_status = repository.n1_completion_status(source_trade_date)
        if n1_status != "passed":
            return WindowsN2AfterN1Result(
                result=(
                    "BLOCKED_N1_FAILED"
                    if n1_status in TERMINAL_N1_FAILURE_STATUSES
                    else "BLOCKED_N1_COMPLETION_MISSING"
                ),
                source_trade_date=source_trade_date,
                for_trade_date=calendar.for_trade_date,
                policy_hash=policy_hash,
                n1_status=n1_status,
            )
    else:
        today = started_at.strftime("%Y%m%d")
        today_calendar = repository.calendar_context(today)
        if not today_calendar.is_open:
            return WindowsN2AfterN1Result(
                result="SKIPPED_NON_TRADING_DAY",
                source_trade_date=today,
                for_trade_date=None,
                policy_hash=policy_hash,
            )
        if not today_calendar.for_trade_date:
            raise RuntimeError("open trade date has no for_trade_date")

        deadline_at = datetime.combine(started_at.date(), deadline)
        in_scheduled_window = scheduled_start <= started_at.time() <= deadline
        n1_status = None
        if in_scheduled_window:
            while True:
                n1_status = repository.n1_completion_status(today)
                if n1_status == "passed":
                    break
                if n1_status in TERMINAL_N1_FAILURE_STATUSES:
                    return WindowsN2AfterN1Result(
                        result="BLOCKED_N1_FAILED",
                        source_trade_date=today,
                        for_trade_date=today_calendar.for_trade_date,
                        policy_hash=policy_hash,
                        n1_status=n1_status,
                    )
                if now_fn() >= deadline_at:
                    return WindowsN2AfterN1Result(
                        result="BLOCKED_N1_TIMEOUT",
                        source_trade_date=today,
                        for_trade_date=today_calendar.for_trade_date,
                        policy_hash=policy_hash,
                        n1_status=n1_status,
                    )
                sleep_fn(poll_seconds)

        source_trade_date = repository.latest_completed_n1_date(today)
        if source_trade_date is None or (
            in_scheduled_window and source_trade_date != today
        ):
            return WindowsN2AfterN1Result(
                result="BLOCKED_N1_COMPLETION_MISSING",
                source_trade_date=today,
                for_trade_date=today_calendar.for_trade_date,
                policy_hash=policy_hash,
                n1_status=n1_status,
            )
        calendar = (
            today_calendar
            if source_trade_date == today
            else repository.calendar_context(source_trade_date)
        )
        if not calendar.is_open or not calendar.for_trade_date:
            raise RuntimeError(
                "completed N1 date is not an open date with a successor: "
                f"{source_trade_date}"
            )
        if not in_scheduled_window:
            n1_status = "passed"

    active_runs = tuple(repository.active_condition_runs(
        source_trade_date,
        calendar.for_trade_date,
    ))
    if len(active_runs) == 1:
        active = active_runs[0]
        if active.status == CANONICAL_ACTIVE_STATUS and active.policy_hash == policy_hash:
            return WindowsN2AfterN1Result(
                result="SKIPPED_IDENTICAL_PASSED_ACTIVE",
                source_trade_date=source_trade_date,
                for_trade_date=calendar.for_trade_date,
                policy_hash=policy_hash,
                active_run_id=active.run_id,
                n1_status=n1_status,
            )
    if active_runs:
        return WindowsN2AfterN1Result(
            result="BLOCKED_ACTIVE_RUN_CONFLICT",
            source_trade_date=source_trade_date,
            for_trade_date=calendar.for_trade_date,
            policy_hash=policy_hash,
            active_run_id=",".join(run.run_id for run in active_runs),
            n1_status=n1_status,
        )

    try:
        report = dict(execute_n2(source_trade_date))
    except Exception as exc:
        return WindowsN2AfterN1Result(
            result="N2_EXECUTE_FAILED",
            source_trade_date=source_trade_date,
            for_trade_date=calendar.for_trade_date,
            policy_hash=policy_hash,
            n1_status=n1_status,
            error=str(exc),
        )
    postcheck = dict(report.get("postcheck") or {})
    if (
        str(report.get("source_trade_date") or "") != source_trade_date
        or str(report.get("for_trade_date") or "") != calendar.for_trade_date
        or str(report.get("policy_hash") or "") != policy_hash
        or str(postcheck.get("run_status") or "") != CANONICAL_ACTIVE_STATUS
        or int(postcheck.get("canonical_active_run_count") or 0) != 1
    ):
        return WindowsN2AfterN1Result(
            result="N2_EXECUTE_POSTCHECK_FAILED",
            source_trade_date=source_trade_date,
            for_trade_date=calendar.for_trade_date,
            policy_hash=policy_hash,
            active_run_id=str(report.get("execute_run_id") or "") or None,
            n1_status=n1_status,
            execute_report=report,
        )
    return WindowsN2AfterN1Result(
        result="N2_AFTER_N1_PASS",
        source_trade_date=source_trade_date,
        for_trade_date=calendar.for_trade_date,
        policy_hash=policy_hash,
        active_run_id=str(report.get("execute_run_id") or "") or None,
        n1_status=n1_status,
        execute_report=report,
    )
