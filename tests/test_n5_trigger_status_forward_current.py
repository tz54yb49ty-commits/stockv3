from __future__ import annotations

import json
import hashlib
import stat
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from psycopg.errors import QueryCanceled

from ashare_v3.runtime.bounded_worker_control import SingletonLockHeld
from ashare_v3.runtime.intraday_worker_lineage import ASIA_SHANGHAI, LineageConfigError
from scripts.run_n5_trigger_status_forward_once import (
    N5TriggerStatusForwardWriteAmbiguous,
    run_n5_trigger_status_forward_once,
)
from scripts.run_n5_trigger_status_forward_current_once import (
    CONSUMER_NAME,
    HISTORY_MAX_LINES,
    run_n5_trigger_status_forward_current_once,
)


TRADE_DATE = "20260803"
SOURCE_RUN_ID = "action_authority_20260803_v1"


class CurrentTriggerStatusForwardRunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.report = self.root / "report.json"
        self.history = self.root / "history.jsonl"
        self.lock = self.root / "worker.lock"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def argv(self, *extra: str) -> list[str]:
        return [
            "--lineage-config",
            str(self.root / "lineage.json"),
            "--consumer-name",
            CONSUMER_NAME,
            "--max-events",
            "5000",
            "--max-runtime-seconds",
            "20",
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
    def authority(*_args: object) -> dict[str, object]:
        return {"calendar_rows": 1, "is_open": True, "source_run_ids": [SOURCE_RUN_ID]}

    @staticmethod
    def core_result(*, execute: bool = False, writes: int = 0) -> dict[str, object]:
        return {
            "verdict": (
                "N5_TRIGGER_STATUS_FORWARD_EXECUTE_PASS"
                if execute
                else "N5_TRIGGER_STATUS_FORWARD_PLAN_ONLY"
            ),
            "for_trade_date": TRADE_DATE,
            "action_run_id": f"n5_trigger_status_forward_current_{TRADE_DATE}_v1",
            "source_eligible_action_run_id": SOURCE_RUN_ID,
            "consumer_name": CONSUMER_NAME,
            "scope_mode": "aggregate_day_action_run",
            "plan": {
                "status_events": [],
                "action_events": [],
                "tracking_updates": [],
                "inbox_checkpoint_intent": None,
            },
            "boundary": {
                "common_action_event_written": False,
                "tracking_written": False,
                "common_event_inbox_written": False,
                "common_event_consumer_checkpoint_written": False,
                "n4_inbox_checkpoint_written": False,
                "n4_outbox_status_updated": False,
            },
            "write_result": {
                "executed": execute,
                "common_event_outbox": writes,
                "common_action_event": 0,
                "common_action_tracking_state": 0,
                "common_event_inbox": 0,
                "common_event_consumer_checkpoint": 0,
                "n4_outbox_status_updated": False,
            },
        }

    @staticmethod
    def core_argv(*, execute: bool = False) -> list[str]:
        argv = [
            "--for-trade-date",
            TRADE_DATE,
            "--source-eligible-action-run-id",
            SOURCE_RUN_ID,
            "--action-run-id",
            f"n5_trigger_status_forward_current_{TRADE_DATE}_v1",
            "--consumer-name",
            CONSUMER_NAME,
            "--max-events",
            "5000",
            "--max-runtime-seconds",
            "20",
        ]
        if execute:
            argv.extend(("--execute", "--user-confirmed"))
        return argv

    @staticmethod
    def valid_core_plan() -> dict[str, object]:
        source_run_ids: list[str] = []
        return {
            "planning_mode": "status_forward_only_offline_bounded_v1",
            "scope_mode": "aggregate_day_action_run",
            "source_trigger_run_id": "",
            "source_eligible_action_run_id": SOURCE_RUN_ID,
            "source_trigger_run_count": 0,
            "source_trigger_run_ids": source_run_ids,
            "source_trigger_run_ids_hash": hashlib.sha256(b"[]").hexdigest(),
            "summary": {"action_eligible_count": 1},
            "status_events": [],
            "action_events": [],
            "tracking_updates": [],
            "inbox_checkpoint_intent": None,
            "persistence": {
                "allowed_targets": ["common_event_outbox"],
                "common_action_event_write_allowed": False,
                "database_write_allowed": False,
            },
        }

    def run_tick(self, *, authority=None, lineage_loader=None, core=None, extra=(), lock=None):
        return run_n5_trigger_status_forward_current_once(
            self.argv(*extra),
            now_provider=self.now,
            lineage_loader=lineage_loader or (lambda _path: self.lineage()),
            authority_reader=authority or self.authority,
            core_runner=core or (lambda _argv: self.core_result()),
            lock_acquirer=lock or self._lock,
        )

    @staticmethod
    @contextmanager
    def _lock(*_args: object, **_kwargs: object):
        yield object()

    def test_closed_date_is_noop_without_calling_core(self) -> None:
        called = []
        result = self.run_tick(
            authority=lambda *_: {"calendar_rows": 0, "is_open": False, "source_run_ids": []},
            core=lambda argv: called.append(argv),
        )
        self.assertEqual(result["verdict"], "NOOP_CLOSED_DATE")
        self.assertEqual(result["written_count"], 0)
        self.assertEqual(called, [])

    def test_open_date_lineage_drift_blocks(self) -> None:
        result = self.run_tick(
            lineage_loader=lambda _path: {**self.lineage(), "for_trade_date": "20260731"}
        )
        self.assertEqual(result["verdict"], "BLOCKED_DATE_DRIFT")

    def test_malformed_or_stale_lineage_blocks(self) -> None:
        for message in ("malformed", "stale lineage"):
            with self.subTest(message=message):
                self.report.unlink(missing_ok=True)
                result = self.run_tick(
                    lineage_loader=lambda _path, value=message: (_ for _ in ()).throw(
                        LineageConfigError(value)
                    )
                )
                self.assertEqual(result["verdict"], "BLOCKED_LINEAGE_INVALID")

    def test_zero_or_multiple_action_authorities_block(self) -> None:
        for run_ids in ([], ["a", "b"]):
            with self.subTest(run_ids=run_ids):
                self.report.unlink(missing_ok=True)
                result = self.run_tick(
                    authority=lambda *_, values=run_ids: {
                        "calendar_rows": 1,
                        "is_open": True,
                        "source_run_ids": values,
                    }
                )
                self.assertEqual(result["verdict"], "BLOCKED_ACTION_ELIGIBLE_AUTHORITY")

    def test_unique_authority_calls_core_with_exact_arguments(self) -> None:
        calls = []

        def core(argv):
            calls.append(list(argv))
            return self.core_result()

        result = self.run_tick(core=core)
        self.assertEqual(result["verdict"], "N5_TRIGGER_STATUS_FORWARD_CURRENT_PLAN_ONLY_PASS")
        argv = calls[0]
        self.assertEqual(argv[argv.index("--for-trade-date") + 1], TRADE_DATE)
        self.assertEqual(argv[argv.index("--source-eligible-action-run-id") + 1], SOURCE_RUN_ID)
        self.assertEqual(
            argv[argv.index("--action-run-id") + 1],
            f"n5_trigger_status_forward_current_{TRADE_DATE}_v1",
        )
        self.assertEqual(argv[argv.index("--consumer-name") + 1], CONSUMER_NAME)
        self.assertEqual(argv[argv.index("--max-events") + 1], "5000")
        self.assertEqual(argv[argv.index("--max-runtime-seconds") + 1], "20")
        self.assertNotIn("--execute", argv)

    def test_duplicate_execute_tick_can_idempotently_write_zero(self) -> None:
        result = self.run_tick(
            core=lambda _argv: self.core_result(execute=True, writes=0),
            extra=("--execute", "--user-confirmed"),
        )
        self.assertEqual(result["verdict"], "N5_TRIGGER_STATUS_FORWARD_CURRENT_EXECUTE_PASS")
        self.assertEqual(result["written_count"], 0)

    def test_singleton_contention_is_noop(self) -> None:
        @contextmanager
        def held(*_args, **_kwargs):
            raise SingletonLockHeld("held")
            yield

        result = self.run_tick(lock=held)
        self.assertEqual(result["verdict"], "NOOP_SINGLETON_LOCK_HELD")

    def test_plan_query_canceled_has_no_incident_and_next_tick_recovers(self) -> None:
        result = self.run_tick(
            core=lambda _argv: (_ for _ in ()).throw(
                QueryCanceled("canceling statement due to statement timeout")
            ),
            extra=("--execute", "--user-confirmed"),
        )
        self.assertEqual(result["verdict"], "BLOCKED_CORE_PLAN_READ")
        self.assertEqual(result["failure_phase"], "plan")
        self.assertFalse(result["requires_post_check"])
        self.assertIsNone(result["incident_id"])
        self.assertIsNone(result["incident_path"])
        self.assertFalse(self.report.with_name("report.incidents").exists())

        recovered = self.run_tick(
            core=lambda _argv: self.core_result(execute=True, writes=0),
            extra=("--execute", "--user-confirmed"),
        )
        self.assertEqual(
            recovered["verdict"], "N5_TRIGGER_STATUS_FORWARD_CURRENT_EXECUTE_PASS"
        )
        self.assertFalse(recovered["requires_post_check"])

    def test_writer_exception_creates_immutable_incident_and_blocks_next_tick(self) -> None:
        result = self.run_tick(
            core=lambda _argv: (_ for _ in ()).throw(
                N5TriggerStatusForwardWriteAmbiguous("RuntimeError:socket lost")
            ),
            extra=("--execute", "--user-confirmed"),
        )
        self.assertEqual(result["verdict"], "BLOCKED_COMMIT_UNKNOWN")
        self.assertEqual(result["failure_phase"], "write")
        self.assertTrue(result["requires_post_check"])
        incident_path = Path(result["incident_path"])
        self.assertTrue(incident_path.is_file())
        self.assertEqual(stat.S_IMODE(incident_path.parent.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(incident_path.stat().st_mode), 0o444)
        first_bytes = incident_path.read_bytes()

        called = []
        result = self.run_tick(core=lambda argv: called.append(argv))
        self.assertEqual(result["verdict"], "BLOCKED_PRIOR_COMMIT_UNKNOWN")
        self.assertEqual(result["failure_phase"], "write")
        self.assertTrue(result["requires_post_check"])
        self.assertEqual(result["incident_path"], str(incident_path))
        self.assertEqual(called, [])
        self.assertEqual(incident_path.read_bytes(), first_bytes)

    def test_incident_persistence_failure_uses_rolling_report_as_blocker(self) -> None:
        with patch(
            "scripts.run_n5_trigger_status_forward_current_once."
            "_write_commit_unknown_incident",
            side_effect=OSError("incident storage unavailable"),
        ):
            result = self.run_tick(
                core=lambda _argv: (_ for _ in ()).throw(
                    N5TriggerStatusForwardWriteAmbiguous("RuntimeError:socket lost")
                ),
                extra=("--execute", "--user-confirmed"),
            )
        self.assertEqual(result["verdict"], "BLOCKED_COMMIT_UNKNOWN")
        self.assertEqual(result["failure_phase"], "write")
        self.assertTrue(result["requires_post_check"])
        self.assertEqual(result["incident_path"], str(self.report))

        called = []
        blocked = self.run_tick(core=lambda argv: called.append(argv))
        self.assertEqual(blocked["verdict"], "BLOCKED_PRIOR_COMMIT_UNKNOWN")
        self.assertEqual(blocked["failure_phase"], "write")
        self.assertTrue(blocked["requires_post_check"])
        self.assertEqual(blocked["incident_path"], str(self.report))
        self.assertEqual(called, [])

    def test_legacy_rolling_report_is_not_an_unresolved_incident(self) -> None:
        self.report.write_text(
            json.dumps(
                {
                    "verdict": "BLOCKED_COMMIT_UNKNOWN",
                    "requires_post_check": True,
                    "reason": "legacy_plan_timeout",
                }
            ),
            encoding="utf-8",
        )
        result = self.run_tick()
        self.assertEqual(
            result["verdict"], "N5_TRIGGER_STATUS_FORWARD_CURRENT_PLAN_ONLY_PASS"
        )
        self.assertFalse(result["requires_post_check"])

    def test_report_and_capped_history_are_written(self) -> None:
        self.history.write_text(
            "".join(json.dumps({"n": index}) + "\n" for index in range(HISTORY_MAX_LINES)),
            encoding="utf-8",
        )
        result = self.run_tick()
        self.assertEqual(json.loads(self.report.read_text(encoding="utf-8"))["verdict"], result["verdict"])
        lines = self.history.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), HISTORY_MAX_LINES)
        self.assertEqual(json.loads(lines[-1])["policy_id"], result["policy_id"])
        for key in ("failure_phase", "requires_post_check", "incident_id", "incident_path"):
            self.assertIn(key, result)

    def test_forbidden_event_or_field_blocks(self) -> None:
        cases = []
        bad_event = self.core_result()
        bad_event["plan"]["status_events"] = [{"event_type": "ActionEligible"}]
        cases.append(bad_event)
        trigger_pct = self.core_result()
        trigger_pct["plan"]["status_events"] = [
            {"event_type": "TriggerStatusUpdated", "payload_json": {"trigger_pct": "1.0"}}
        ]
        cases.append(trigger_pct)
        forbidden_write = self.core_result()
        forbidden_write["write_result"]["common_action_event"] = 1
        cases.append(forbidden_write)
        for core_result in cases:
            with self.subTest(core_result=core_result):
                self.report.unlink(missing_ok=True)
                result = self.run_tick(core=lambda _argv, value=core_result: value)
                self.assertEqual(result["verdict"], "BLOCKED_CORE_RESULT_INVALID")

    def test_default_authority_reader_uses_read_only_connection(self) -> None:
        from scripts import run_n5_trigger_status_forward_current_once as runner

        connection = MagicMock()
        cursor = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value.__enter__.return_value = cursor
        cursor.fetchone.return_value = {"calendar_rows": 1, "is_open": True}
        cursor.fetchall.return_value = [{"source_run_id": SOURCE_RUN_ID}]
        with patch.object(runner.psycopg, "connect", return_value=connection) as connect:
            result = runner._read_open_date_and_authority("dsn", TRADE_DATE, 20)
        self.assertEqual(result["source_run_ids"], [SOURCE_RUN_ID])
        self.assertIn("default_transaction_read_only=on", connect.call_args.kwargs["options"])

    def test_core_plan_query_canceled_is_structured_and_writer_is_not_called(self) -> None:
        writer_calls = []
        result = run_n5_trigger_status_forward_once(
            self.core_argv(execute=True),
            plan_provider=lambda _args: (_ for _ in ()).throw(
                QueryCanceled("canceling statement due to statement timeout")
            ),
            writer=lambda args, events: writer_calls.append((args, events)),
        )
        self.assertEqual(result["verdict"], "BLOCKED_N5_TRIGGER_STATUS_FORWARD_PLAN_READ")
        self.assertEqual(result["failure_phase"], "plan")
        self.assertFalse(result["requires_post_check"])
        self.assertFalse(result["writer_called"])
        self.assertEqual(writer_calls, [])
        self.assertEqual(result["write_result"]["common_event_outbox"], 0)

    def test_core_writer_exception_uses_explicit_ambiguity_exception(self) -> None:
        with self.assertRaises(N5TriggerStatusForwardWriteAmbiguous):
            run_n5_trigger_status_forward_once(
                self.core_argv(execute=True),
                plan_provider=lambda _args: self.valid_core_plan(),
                writer=lambda _args, _events: (_ for _ in ()).throw(
                    RuntimeError("commit response lost")
                ),
            )


if __name__ == "__main__":
    unittest.main()
