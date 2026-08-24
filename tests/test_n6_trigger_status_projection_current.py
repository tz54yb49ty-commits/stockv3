from __future__ import annotations

import argparse
import json
import stat
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from ashare_v3.runtime.bounded_worker_control import SingletonLockHeld
from ashare_v3.runtime.intraday_worker_lineage import ASIA_SHANGHAI, LineageConfigError
from ashare_v3.user.trigger_status_projection import (
    CONSUMER_NAME,
    TriggerStatusProjectionError,
)
from scripts.run_n6_trigger_status_projection_current_once import (
    FORBIDDEN_FIELD,
    HISTORY_MAX_LINES,
    run_n6_trigger_status_projection_current_once,
)


TRADE_DATE = "20260803"
PROJECTION_RUN_ID = f"n6_trigger_status_projection_current_{TRADE_DATE}_v1"


class CurrentTriggerStatusProjectionRunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.report = self.root / "report.json"
        self.history = self.root / "history.jsonl"
        self.lock = self.root / "worker.lock"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def argv(self, *extra: str, limit: int = 5000) -> list[str]:
        return [
            "--lineage-config",
            str(self.root / "lineage.json"),
            "--limit",
            str(limit),
            "--singleton-lock-path",
            str(self.lock),
            "--json-report-path",
            str(self.report),
            "--history-path",
            str(self.history),
            *extra,
        ]

    @staticmethod
    def now() -> datetime:
        return datetime(2026, 8, 3, 10, 0, tzinfo=ASIA_SHANGHAI)

    @staticmethod
    def lineage() -> dict[str, object]:
        return {
            "enabled": True,
            "for_trade_date": TRADE_DATE,
            "source_trade_date": "20260731",
            "n4_context_run_id": "n4_context",
        }

    @staticmethod
    def calendar(*_args: object) -> dict[str, object]:
        return {"calendar_rows": 1, "is_open": True}

    @staticmethod
    def core_result(*, execute: bool = False, selected: int = 0) -> dict[str, object]:
        if not execute:
            return {
                "verdict": "N6_TRIGGER_STATUS_PROJECTION_PLAN_ONLY",
                "consumer_name": CONSUMER_NAME,
                "writes_database": False,
                "outbox_status_updates": 0,
            }
        return {
            "verdict": "N6_TRIGGER_STATUS_PROJECTION_EXECUTE_PASS",
            "consumer_name": CONSUMER_NAME,
            "trade_date": TRADE_DATE,
            "projection_run_id": PROJECTION_RUN_ID,
            "selected": selected,
            "inserted": 0,
            "updated": 0,
            "invalidated": 0,
            "ignored_action_outcomes": 0,
            "replay_skipped": 0,
            "last_outbox_id": None,
            "outbox_status_updates": 0,
            "writes_database": True,
        }

    def run_tick(
        self,
        *,
        lineage_loader=None,
        calendar=None,
        core=None,
        extra=(),
        limit: int = 5000,
        lock=None,
    ):
        return run_n6_trigger_status_projection_current_once(
            self.argv(*extra, limit=limit),
            now_provider=self.now,
            lineage_loader=lineage_loader or (lambda _path: self.lineage()),
            calendar_reader=calendar or self.calendar,
            core_runner=core or (lambda _args: self.core_result()),
            lock_acquirer=lock or self._lock,
        )

    @staticmethod
    @contextmanager
    def _lock(*_args: object, **_kwargs: object):
        yield object()

    def test_closed_date_is_noop_without_core_call(self) -> None:
        called = []
        result = self.run_tick(
            calendar=lambda *_: {"calendar_rows": 0, "is_open": False},
            core=lambda args: called.append(args),
        )
        self.assertEqual(result["verdict"], "NOOP_CLOSED_DATE")
        self.assertEqual(result["counts"]["selected"], 0)
        self.assertEqual(called, [])

    def test_open_date_lineage_drift_blocks(self) -> None:
        result = self.run_tick(
            lineage_loader=lambda _path: {
                **self.lineage(),
                "for_trade_date": "20260731",
            }
        )
        self.assertEqual(result["verdict"], "BLOCKED_DATE_DRIFT")

    def test_malformed_or_stale_lineage_blocks(self) -> None:
        for message in ("malformed", "stale lineage"):
            with self.subTest(message=message):
                self.report.unlink(missing_ok=True)
                result = self.run_tick(
                    lineage_loader=lambda _path, value=message: (
                        _ for _ in ()
                    ).throw(LineageConfigError(value))
                )
                self.assertEqual(result["verdict"], "BLOCKED_LINEAGE_INVALID")

    def test_plan_only_uses_core_without_instantiating_consumer(self) -> None:
        from scripts import run_n6_trigger_status_projection_once as core

        with patch.object(core, "PostgresTriggerStatusProjectionConsumer") as consumer:
            result = run_n6_trigger_status_projection_current_once(
                self.argv(),
                now_provider=self.now,
                lineage_loader=lambda _path: self.lineage(),
                calendar_reader=self.calendar,
                lock_acquirer=self._lock,
            )
        self.assertEqual(
            result["verdict"],
            "N6_TRIGGER_STATUS_PROJECTION_CURRENT_PLAN_ONLY_PASS",
        )
        consumer.assert_not_called()

    def test_execute_calls_core_with_exact_current_scope(self) -> None:
        calls: list[argparse.Namespace] = []

        def core(args: argparse.Namespace) -> dict[str, object]:
            calls.append(args)
            return self.core_result(execute=True, selected=3)

        result = self.run_tick(
            core=core,
            extra=("--execute", "--user-confirmed"),
        )
        self.assertEqual(
            result["verdict"], "N6_TRIGGER_STATUS_PROJECTION_CURRENT_EXECUTE_PASS"
        )
        args = calls[0]
        self.assertEqual(args.for_trade_date, TRADE_DATE)
        self.assertEqual(args.projection_run_id, PROJECTION_RUN_ID)
        self.assertEqual(args.limit, 5000)
        self.assertTrue(args.execute)
        self.assertTrue(args.user_confirmed)
        self.assertEqual(result["partition_key"], f"trigger-status:{TRADE_DATE}")
        self.assertEqual(result["counts"]["selected"], 3)

    def test_duplicate_execute_tick_can_select_zero(self) -> None:
        result = self.run_tick(
            core=lambda _args: self.core_result(execute=True, selected=0),
            extra=("--execute", "--user-confirmed"),
        )
        self.assertEqual(result["result"], "PASS")
        self.assertEqual(result["counts"]["selected"], 0)

    def test_singleton_contention_is_noop(self) -> None:
        @contextmanager
        def held(*_args, **_kwargs):
            raise SingletonLockHeld("held")
            yield

        result = self.run_tick(lock=held)
        self.assertEqual(result["verdict"], "NOOP_SINGLETON_LOCK_HELD")

    def test_prior_commit_unknown_blocks_without_core_call(self) -> None:
        self.report.write_text(
            json.dumps({"requires_post_check": True}), encoding="utf-8"
        )
        called = []
        result = self.run_tick(core=lambda args: called.append(args))
        self.assertEqual(result["verdict"], "BLOCKED_PRIOR_COMMIT_UNKNOWN")
        self.assertTrue(result["requires_post_check"])
        self.assertEqual(called, [])

    def test_projection_error_is_rolled_back_without_sticky_post_check(self) -> None:
        result = self.run_tick(
            core=lambda _args: (_ for _ in ()).throw(
                TriggerStatusProjectionError("missing_status_update_target")
            ),
            extra=("--execute", "--user-confirmed"),
        )
        self.assertEqual(result["result"], "BLOCKED")
        self.assertEqual(result["verdict"], "BLOCKED_CORE_PROJECTION_INPUT")
        self.assertEqual(result["failure_phase"], "projection_rolled_back")
        self.assertFalse(result["requires_post_check"])
        self.assertIsNone(result["incident_id"])
        self.assertIsNone(result["incident_path"])

        recovered = self.run_tick()
        self.assertEqual(
            recovered["verdict"],
            "N6_TRIGGER_STATUS_PROJECTION_CURRENT_PLAN_ONLY_PASS",
        )

    def test_execute_exception_creates_immutable_incident_and_blocks_next_tick(self) -> None:
        result = self.run_tick(
            core=lambda _args: (_ for _ in ()).throw(RuntimeError("socket lost")),
            extra=("--execute", "--user-confirmed"),
        )
        self.assertEqual(result["verdict"], "BLOCKED_COMMIT_UNKNOWN")
        self.assertEqual(result["result"], "COMMIT_UNKNOWN")
        self.assertEqual(result["failure_phase"], "write")
        self.assertTrue(result["requires_post_check"])
        incident_path = Path(result["incident_path"])
        self.assertTrue(incident_path.is_file())
        self.assertEqual(stat.S_IMODE(incident_path.parent.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(incident_path.stat().st_mode), 0o444)
        first_bytes = incident_path.read_bytes()

        called = []
        result = self.run_tick(core=lambda args: called.append(args))
        self.assertEqual(result["verdict"], "BLOCKED_PRIOR_COMMIT_UNKNOWN")
        self.assertEqual(result["failure_phase"], "write")
        self.assertEqual(result["incident_path"], str(incident_path))
        self.assertEqual(called, [])
        self.assertEqual(incident_path.read_bytes(), first_bytes)

    def test_report_and_capped_history_are_written(self) -> None:
        self.history.write_text(
            "".join(
                json.dumps({"n": index}) + "\n"
                for index in range(HISTORY_MAX_LINES)
            ),
            encoding="utf-8",
        )
        result = self.run_tick()
        stored = json.loads(self.report.read_text(encoding="utf-8"))
        self.assertEqual(stored["verdict"], result["verdict"])
        lines = self.history.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), HISTORY_MAX_LINES)
        self.assertEqual(json.loads(lines[-1])["policy_id"], result["policy_id"])

    def test_limit_bounds_and_execute_confirmation_fail_closed(self) -> None:
        for limit in (0, 5001):
            with self.subTest(limit=limit):
                self.report.unlink(missing_ok=True)
                result = self.run_tick(limit=limit)
                self.assertEqual(result["verdict"], "BLOCKED_INVALID_ARGUMENTS")
        self.report.unlink(missing_ok=True)
        result = self.run_tick(extra=("--execute",))
        self.assertEqual(result["reason"], "execute_requires_user_confirmed")

    def test_invalid_core_identity_counts_and_boundary_block(self) -> None:
        cases = []
        wrong_consumer = self.core_result(execute=True)
        wrong_consumer["consumer_name"] = "other"
        cases.append(wrong_consumer)
        wrong_date = self.core_result(execute=True)
        wrong_date["trade_date"] = "20260731"
        cases.append(wrong_date)
        wrong_run = self.core_result(execute=True)
        wrong_run["projection_run_id"] = "other"
        cases.append(wrong_run)
        negative = self.core_result(execute=True)
        negative["updated"] = -1
        cases.append(negative)
        outbox_update = self.core_result(execute=True)
        outbox_update["outbox_status_updates"] = 1
        cases.append(outbox_update)
        forbidden = self.core_result(execute=True)
        forbidden[FORBIDDEN_FIELD] = "must-block"
        cases.append(forbidden)
        for core_result in cases:
            with self.subTest(core_result=core_result):
                self.report.unlink(missing_ok=True)
                result = self.run_tick(
                    core=lambda _args, value=core_result: value,
                    extra=("--execute", "--user-confirmed"),
                )
                self.assertEqual(result["verdict"], "BLOCKED_CORE_RESULT_INVALID")

    def test_normal_report_and_new_sources_exclude_forbidden_field(self) -> None:
        result = self.run_tick()
        source_paths = (
            Path(__file__).resolve(),
            Path(__file__).resolve().parents[1]
            / "scripts/run_n6_trigger_status_projection_current_once.py",
        )
        for path in source_paths:
            self.assertNotIn(FORBIDDEN_FIELD, path.read_text(encoding="utf-8"))
        self.assertNotIn(
            FORBIDDEN_FIELD,
            json.dumps(result, ensure_ascii=False, sort_keys=True),
        )

    def test_default_calendar_reader_uses_read_only_connection(self) -> None:
        from scripts import run_n6_trigger_status_projection_current_once as runner

        connection = MagicMock()
        cursor = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value.__enter__.return_value = cursor
        cursor.fetchone.return_value = {"calendar_rows": 1, "is_open": True}
        with patch.object(runner.psycopg, "connect", return_value=connection) as connect:
            result = runner._read_open_date("dsn", TRADE_DATE)
        self.assertTrue(result["is_open"])
        self.assertIn(
            "default_transaction_read_only=on", connect.call_args.kwargs["options"]
        )


if __name__ == "__main__":
    unittest.main()
