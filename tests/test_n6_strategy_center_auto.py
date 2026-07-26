from __future__ import annotations

from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import tempfile
import time
import unittest
from unittest.mock import patch

from ashare_v3.user.strategy_center import EVALUATOR_POLICY_HASH
from ashare_v3.user.strategy_center_worker import (
    AutoEvaluationState,
    N6DisplayBatchAuthority,
    N6TradeDateAuthority,
    StrategyEvaluatorScope,
    StrategyCenterWorkerBlocked,
)
from scripts.run_n6_strategy_center_auto_once import (
    AutoEvaluatorDeadlineExceeded,
    AutoEvaluatorStateBlocked,
    DEFAULT_MAX_RUNTIME_SECONDS,
    EVIDENCE_MAX_RUNTIME_SECONDS,
    EXPECTED_RUNTIME_PATHS,
    HISTORY_MAX_BYTES,
    HISTORY_ROTATION_COUNT,
    _append_history,
    _evidence_timeout_handler,
    _evaluation_budget_seconds,
    _persist_runtime_evidence,
    _should_emit_report,
    _singleton_lock,
    _timeout_handler,
    build_parser,
    run_auto_once,
    validate_runtime_paths,
)


RELEASE_ID = "20260722_120000__" + "a" * 40
NEXT_RELEASE_ID = "20260722_120500__" + "b" * 40
NOW = datetime(2026, 7, 24, 4, 0, 0, tzinfo=timezone.utc)
N6_AUTHORITY = N6TradeDateAuthority(
    trade_date="20260724",
    batches=(
        N6DisplayBatchAuthority(
            asset_kind="stock",
            source_trade_date="20260723",
            for_trade_date="20260724",
            source_run_id="stock-reviewed-run",
            row_count=1559,
        ),
        N6DisplayBatchAuthority(
            asset_kind="index",
            source_trade_date="20260723",
            for_trade_date="20260724",
            source_run_id="index-reviewed-run",
            row_count=9,
        ),
        N6DisplayBatchAuthority(
            asset_kind="board",
            source_trade_date="20260723",
            for_trade_date="20260724",
            source_run_id="board-reviewed-run",
            row_count=127,
        ),
    ),
)


def authority_for(trade_date: str) -> N6TradeDateAuthority:
    return N6TradeDateAuthority(
        trade_date=trade_date,
        batches=tuple(
            N6DisplayBatchAuthority(
                asset_kind=batch.asset_kind,
                source_trade_date=batch.source_trade_date,
                for_trade_date=trade_date,
                source_run_id=batch.source_run_id,
                row_count=batch.row_count,
            )
            for batch in N6_AUTHORITY.batches
        ),
    )


def evaluator_scope(revision_id: int) -> StrategyEvaluatorScope:
    return StrategyEvaluatorScope(
        principal_id=revision_id,
        user_id=revision_id,
        selection_revision_id=revision_id,
    )


def auto_state(
    *,
    pending: tuple[int, ...] = (),
    fingerprint: str = "f" * 64,
    projection_events: int = 1,
    active: tuple[int, ...] = (1,),
    replay_pending_active: tuple[int, ...] = (),
    trade_date: str = "20260724",
    authority: N6TradeDateAuthority = N6_AUTHORITY,
) -> AutoEvaluationState:
    pending = tuple(sorted(pending))
    active = tuple(sorted(active))
    return AutoEvaluationState(
        trade_date=trade_date,
        pending_revision_ids=pending,
        source_watermarks={"projection_event_count": projection_events},
        source_fingerprint=fingerprint,
        pending_scopes=tuple(evaluator_scope(value) for value in pending),
        active_scopes=tuple(evaluator_scope(value) for value in active),
        replay_pending_active_scopes=tuple(
            evaluator_scope(value) for value in replay_pending_active
        ),
        trade_date_authority=authority,
    )


class FakeRepository:
    def __init__(self, state: AutoEvaluationState) -> None:
        self.state = state
        self.status_calls: list[tuple[tuple[int, ...], str]] = []
        self.load_calls = 0

    def load_auto_evaluation_state(self) -> AutoEvaluationState:
        self.load_calls += 1
        return self.state

    def mark_pending_replay_status(
        self, revision_ids, status: str
    ) -> tuple[int, ...]:
        normalized = tuple(int(value) for value in revision_ids)
        self.status_calls.append((normalized, status))
        return normalized


def previous_state(fingerprint: str) -> dict[str, object]:
    return {
        "state_version": 1,
        "source_cursor": {
            "trade_date": "20260724",
            "fingerprint": fingerprint,
            "release_id": RELEASE_ID,
            "evaluator_policy_hash": EVALUATOR_POLICY_HASH,
        },
        "consecutive_failures": 0,
        "release_id": RELEASE_ID,
        "evaluator_policy_hash": EVALUATOR_POLICY_HASH,
    }


def write_private_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")
    path.chmod(0o600)


class N6StrategyCenterAutoTest(unittest.TestCase):
    def test_production_evaluator_freezes_evaluation_time_for_execute(self) -> None:
        source = Path(
            "scripts/run_n6_strategy_center_auto_once.py"
        ).read_text()
        self.assertIn("evaluation_time=observed_at.astimezone", source)

    def test_input_cas_drift_is_safe_noop_without_backoff(self) -> None:
        source = Path("scripts/run_n6_strategy_center_auto_once.py").read_text()
        self.assertIn('status": "noop_input_drift"', source)
        self.assertIn('"strategy_worker_snapshot_cas_mismatch"', source)

    EVIDENCE_KEYS = {
        "trigger_kind",
        "duration_ms",
        "trade_date",
        "source_fingerprint",
        "source_watermarks",
        "trade_date_authority",
        "source_authority_status",
        "pending_revision_ids",
        "pending_revision_count",
        "pending_authority_status",
        "selected_scope",
        "remaining_count",
        "cursor",
        "per_scope_result",
        "consecutive_failures",
        "database_committed",
        "write_called",
        "release_id",
        "release_commit",
        "evaluator_policy_hash",
    }

    def _paths(self, root: Path) -> tuple[Path, Path]:
        return root / "state.json", root / "evaluator.lock"

    def _assert_evidence_contract(self, result: dict[str, object]) -> None:
        self.assertTrue(self.EVIDENCE_KEYS.issubset(result))
        self.assertGreaterEqual(float(result["duration_ms"]), 0.0)
        self.assertEqual(result["release_id"], RELEASE_ID)
        self.assertEqual(result["release_commit"], "a" * 40)
        self.assertEqual(result["evaluator_policy_hash"], EVALUATOR_POLICY_HASH)
        if result["source_authority_status"] == (
            "reviewed_n6_display_consensus"
        ):
            self.assertEqual(
                result["trade_date_authority"],
                {
                    "trade_date": "20260724",
                    "batches": (
                        {
                            "asset_kind": "stock",
                            "source_trade_date": "20260723",
                            "for_trade_date": "20260724",
                            "source_run_id": "stock-reviewed-run",
                            "row_count": 1559,
                        },
                        {
                            "asset_kind": "index",
                            "source_trade_date": "20260723",
                            "for_trade_date": "20260724",
                            "source_run_id": "index-reviewed-run",
                            "row_count": 9,
                        },
                        {
                            "asset_kind": "board",
                            "source_trade_date": "20260723",
                            "for_trade_date": "20260724",
                            "source_run_id": "board-reviewed-run",
                            "row_count": 127,
                        },
                    ),
                },
            )
        else:
            self.assertIsNone(result["trade_date_authority"])

    def test_future_open_trade_date_waits_without_worker_or_failure_growth(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            state_path, lock_path = self._paths(root)
            prior = {
                **previous_state("f" * 64),
                "consecutive_failures": 2,
                "last_failed_attempt_key": "a" * 64,
                "next_retry_at": "2026-07-27T00:00:00Z",
                "last_trigger_kind": "time_tick",
            }
            write_private_json(state_path, prior)
            before = state_path.read_bytes()
            repository = FakeRepository(
                auto_state(
                    active=(1,),
                    trade_date="20260727",
                    authority=authority_for("20260727"),
                )
            )
            result = run_auto_once(
                repository=repository,
                state_path=state_path,
                lock_path=lock_path,
                release_id=RELEASE_ID,
                execute=True,
                runtime_authorized=True,
                now=datetime(
                    2026, 7, 26, 4, 0, 0, tzinfo=timezone.utc
                ),
                evaluate_once=lambda *_args: self.fail("must not evaluate"),
            )
            self.assertEqual(result["status"], "WAITING_OPEN_TRADE_DATE")
            self.assertEqual(result["consecutive_failures"], 2)
            self.assertFalse(result["database_committed"])
            self.assertEqual(state_path.read_bytes(), before)
            self.assertEqual(repository.status_calls, [])

    def test_stale_trade_date_authority_fails_closed_without_worker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            state_path, lock_path = self._paths(root)
            repository = FakeRepository(
                auto_state(
                    active=(1,),
                    trade_date="20260727",
                    authority=authority_for("20260727"),
                )
            )
            result = run_auto_once(
                repository=repository,
                state_path=state_path,
                lock_path=lock_path,
                release_id=RELEASE_ID,
                execute=False,
                now=datetime(
                    2026, 7, 28, 4, 0, 0, tzinfo=timezone.utc
                ),
                evaluate_once=lambda *_args: self.fail("must not evaluate"),
            )
            self.assertEqual(
                result["status"], "BLOCKED_STALE_TRADE_DATE_AUTHORITY"
            )
            self.assertFalse(result["ok"])
            self.assertEqual(result["consecutive_failures"], 0)

    def test_current_trade_date_evaluates_normally(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            state_path, lock_path = self._paths(root)
            calls: list[int] = []
            result = run_auto_once(
                repository=FakeRepository(auto_state(active=(3,))),
                state_path=state_path,
                lock_path=lock_path,
                release_id=RELEASE_ID,
                execute=False,
                now=NOW,
                evaluate_once=lambda _trade_date, _run_id, scope, *_args: (
                    calls.append(scope.selection_revision_id)
                    or {"write_called": False}
                ),
            )
            self.assertEqual(result["status"], "dry_run")
            self.assertEqual(calls, [3])

    def test_pending_then_replay_pending_then_active_round_robin_priority(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            state_path, lock_path = self._paths(root)
            evaluated: list[int] = []

            pending_result = run_auto_once(
                repository=FakeRepository(
                    auto_state(
                        pending=(8,),
                        active=(3, 5),
                        replay_pending_active=(5,),
                    )
                ),
                state_path=state_path,
                lock_path=lock_path,
                release_id=RELEASE_ID,
                execute=False,
                now=NOW,
                evaluate_once=lambda _date, _run, scope, *_args: (
                    evaluated.append(scope.selection_revision_id)
                    or {"write_called": False}
                ),
            )
            self.assertEqual(
                pending_result["trigger_kind"], "pending_selection"
            )
            self.assertEqual(evaluated, [8])

            replay_result = run_auto_once(
                repository=FakeRepository(
                    auto_state(
                        active=(3, 5),
                        replay_pending_active=(5,),
                    )
                ),
                state_path=state_path,
                lock_path=lock_path,
                release_id=RELEASE_ID,
                execute=False,
                now=NOW,
                evaluate_once=lambda _date, _run, scope, *_args: (
                    evaluated.append(scope.selection_revision_id)
                    or {"write_called": False}
                ),
            )
            self.assertEqual(
                replay_result["trigger_kind"], "active_replay_pending"
            )
            self.assertEqual(evaluated, [8, 5])

    def test_quiet_logging_only_suppresses_identical_waiting_or_noop(self) -> None:
        waiting = {
            "ok": True,
            "status": "WAITING_OPEN_TRADE_DATE",
            "trigger_kind": "trade_date_authority_wait",
            "trade_date": "20260727",
            "selected_scope": None,
        }
        self.assertFalse(_should_emit_report(waiting, waiting))
        self.assertTrue(
            _should_emit_report(
                {**waiting, "status": "noop_unchanged"},
                waiting,
            )
        )
        self.assertTrue(
            _should_emit_report(
                {**waiting, "status": "committed"},
                waiting,
            )
        )
        self.assertTrue(
            _should_emit_report(
                {**waiting, "history_rotated": True},
                waiting,
            )
        )

    def test_pending_selection_is_prioritized_and_cursor_is_not_overclaimed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            state_path, lock_path = self._paths(root)
            fingerprint = "1" * 64
            old_fingerprint = "0" * 64
            write_private_json(state_path, previous_state(old_fingerprint))
            repository = FakeRepository(
                auto_state(pending=(7, 8), fingerprint=fingerprint)
            )
            calls: list[tuple[object, ...]] = []

            def evaluate(trade_date, run_id, revision_ids, execute, authorized):
                calls.append((trade_date, run_id, revision_ids, execute, authorized))
                return {"ok": True, "write_called": True, "work_item_count": 1}

            result = run_auto_once(
                repository=repository,
                state_path=state_path,
                lock_path=lock_path,
                release_id=RELEASE_ID,
                execute=True,
                runtime_authorized=True,
                now=NOW,
                evaluate_once=evaluate,
            )

            self.assertTrue(result["ok"])
            self._assert_evidence_contract(result)
            self.assertEqual(result["trigger_kind"], "pending_selection")
            self.assertEqual(result["pending_revision_count"], 2)
            self.assertEqual(result["consecutive_failures"], 0)
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][2], evaluator_scope(7))
            self.assertEqual(result["selected_scope"], {
                "principal_id": 7,
                "user_id": 7,
                "selection_revision_id": 7,
            })
            self.assertEqual(result["remaining_count"], 1)
            self.assertEqual(repository.status_calls, [])
            persisted = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(
                persisted["source_cursor"]["fingerprint"], old_fingerprint
            )
            self.assertEqual(
                persisted["trade_date_authority"]["trade_date"],
                "20260724",
            )
            self.assertEqual(state_path.stat().st_mode & 0o777, 0o600)

    def test_five_pending_scopes_converge_one_per_tick_in_revision_order(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            state_path, lock_path = self._paths(root)
            fingerprint = "a" * 64
            write_private_json(state_path, previous_state(fingerprint))
            repository = FakeRepository(
                auto_state(
                    pending=(15, 11, 14, 12, 13),
                    fingerprint=fingerprint,
                )
            )
            selected: list[int] = []
            remaining: list[int] = []

            def evaluate(_trade_date, _run_id, scope, _execute, _authorized):
                selected.append(scope.selection_revision_id)
                pending = tuple(
                    value
                    for value in repository.state.pending_revision_ids
                    if value != scope.selection_revision_id
                )
                repository.state = auto_state(
                    pending=pending,
                    fingerprint=fingerprint,
                )
                return {"ok": True, "write_called": True, "work_item_count": 1}

            for offset in range(5):
                result = run_auto_once(
                    repository=repository,
                    state_path=state_path,
                    lock_path=lock_path,
                    release_id=RELEASE_ID,
                    execute=True,
                    runtime_authorized=True,
                    now=NOW + timedelta(seconds=offset * 5),
                    evaluate_once=evaluate,
                )
                self.assertEqual(result["status"], "committed")
                self.assertEqual(result["evaluation"]["work_item_count"], 1)
                remaining.append(result["remaining_count"])

            self.assertEqual(selected, [11, 12, 13, 14, 15])
            self.assertEqual(remaining, [4, 3, 2, 1, 0])

    def test_formal_runner_calls_worker_with_one_explicit_scope_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            state_path, lock_path = self._paths(root)
            repository = FakeRepository(auto_state(pending=(21, 22)))
            with patch(
                "scripts.run_n6_strategy_center_auto_once.run_strategy_center_once",
                return_value={
                    "ok": True,
                    "write_called": True,
                    "scope_mode": "single_user_revision",
                },
            ) as worker:
                result = run_auto_once(
                    repository=repository,
                    state_path=state_path,
                    lock_path=lock_path,
                    release_id=RELEASE_ID,
                    execute=True,
                    runtime_authorized=True,
                    now=NOW,
                )

            self.assertEqual(result["status"], "committed")
            self.assertEqual(worker.call_count, 1)
            kwargs = worker.call_args.kwargs
            self.assertEqual(kwargs["scope"], evaluator_scope(21))
            self.assertNotIn("selection_revision_ids", kwargs)
            self.assertTrue(kwargs["runtime_authorized"])

    def test_missing_n6_trade_date_authority_fails_closed_without_evaluation(
        self,
    ) -> None:
        class MissingAuthorityRepository(FakeRepository):
            def load_auto_evaluation_state(self) -> AutoEvaluationState:
                self.load_calls += 1
                raise StrategyCenterWorkerBlocked(
                    "n6_trade_date_authority_invalid"
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            state_path, lock_path = self._paths(root)
            repository = MissingAuthorityRepository(auto_state(pending=(7,)))
            result = run_auto_once(
                repository=repository,
                state_path=state_path,
                lock_path=lock_path,
                release_id=RELEASE_ID,
                execute=True,
                runtime_authorized=True,
                now=NOW,
                evaluate_once=lambda *_args: self.fail("must not evaluate"),
            )
            self.assertFalse(result["ok"])
            self.assertEqual(result["status"], "failed_source_state")
            self.assertEqual(result["trigger_kind"], "source_state")
            self.assertEqual(result["error_message"], "n6_trade_date_authority_invalid")
            self.assertFalse(result["write_called"])
            self.assertFalse(result["database_committed"])
            self.assertTrue(state_path.exists())
            self.assertEqual(repository.status_calls, [])

    def test_pending_scope_without_reviewed_events_waits_without_failure_write(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            state_path, lock_path = self._paths(root)
            original = previous_state("f" * 64)
            write_private_json(state_path, original)
            repository = FakeRepository(auto_state(pending=(7,)))

            def evaluate(*_args):
                raise StrategyCenterWorkerBlocked(
                    "reviewed_n6_natural_event_group_missing"
                )

            result = run_auto_once(
                repository=repository,
                state_path=state_path,
                lock_path=lock_path,
                release_id=RELEASE_ID,
                execute=True,
                runtime_authorized=True,
                now=NOW,
                evaluate_once=evaluate,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(
                result["status"],
                "noop_waiting_for_reviewed_n6_events",
            )
            self.assertFalse(result["write_called"])
            self.assertFalse(result["database_committed"])
            self.assertEqual(result["marked_failed_revision_ids"], [])
            self.assertEqual(repository.status_calls, [])
            self.assertEqual(
                json.loads(state_path.read_text(encoding="utf-8")),
                original,
            )

    def test_auto_runner_has_no_calendar_authority_semantics(self) -> None:
        runner = (
            Path(__file__).parents[1]
            / "scripts"
            / "run_n6_strategy_center_auto_once.py"
        ).read_text(encoding="utf-8")
        worker = (
            Path(__file__).parents[1]
            / "src"
            / "ashare_v3"
            / "user"
            / "strategy_center_worker.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "common_trade_calendar",
            "calendar_closed",
            "noop_no_open_trade_date",
            "StrategyCenterNoOpenTradeDate",
        ):
            self.assertNotIn(forbidden, runner)
            self.assertNotIn(forbidden, worker)

    def test_source_change_is_followed_by_one_scope_temporal_tick(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            state_path, lock_path = self._paths(root)
            write_private_json(state_path, previous_state("0" * 64))
            repository = FakeRepository(
                auto_state(fingerprint="2" * 64, projection_events=100)
            )
            calls = []

            def evaluate(trade_date, run_id, revision_ids, execute, authorized):
                calls.append((trade_date, revision_ids))
                return {"ok": True, "write_called": True, "work_item_count": 6}

            first = run_auto_once(
                repository=repository,
                state_path=state_path,
                lock_path=lock_path,
                release_id=RELEASE_ID,
                execute=True,
                runtime_authorized=True,
                now=NOW,
                evaluate_once=evaluate,
            )
            second = run_auto_once(
                repository=repository,
                state_path=state_path,
                lock_path=lock_path,
                release_id=RELEASE_ID,
                execute=True,
                runtime_authorized=True,
                now=NOW + timedelta(seconds=5),
                evaluate_once=evaluate,
            )

            self.assertEqual(first["trigger_kind"], "source_changed")
            self.assertEqual(second["status"], "committed")
            self._assert_evidence_contract(second)
            self.assertEqual(second["trigger_kind"], "time_tick")
            self.assertEqual(
                second["source_watermarks"],
                {"projection_event_count": 100},
            )
            self.assertEqual(
                calls,
                [
                    ("20260724", evaluator_scope(1)),
                    ("20260724", evaluator_scope(1)),
                ],
            )

    def test_failure_preserves_cursor_marks_failed_and_retries_after_backoff(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            state_path, lock_path = self._paths(root)
            old_fingerprint = "3" * 64
            write_private_json(state_path, previous_state(old_fingerprint))
            repository = FakeRepository(
                auto_state(pending=(9, 10), fingerprint=old_fingerprint)
            )
            attempts = 0

            def evaluate(_trade_date, _run_id, _revision_ids, _execute, _authorized):
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    raise RuntimeError("transient_failure")
                return {"ok": True, "write_called": True}

            failed = run_auto_once(
                repository=repository,
                state_path=state_path,
                lock_path=lock_path,
                release_id=RELEASE_ID,
                execute=True,
                runtime_authorized=True,
                now=NOW,
                evaluate_once=evaluate,
            )
            backed_off = run_auto_once(
                repository=repository,
                state_path=state_path,
                lock_path=lock_path,
                release_id=RELEASE_ID,
                execute=True,
                runtime_authorized=True,
                now=NOW + timedelta(seconds=1),
                evaluate_once=evaluate,
            )
            retried = run_auto_once(
                repository=repository,
                state_path=state_path,
                lock_path=lock_path,
                release_id=RELEASE_ID,
                execute=True,
                runtime_authorized=True,
                now=NOW + timedelta(seconds=5),
                evaluate_once=evaluate,
            )

            self.assertFalse(failed["ok"])
            self._assert_evidence_contract(failed)
            self.assertEqual(failed["consecutive_failures"], 1)
            self.assertEqual(backed_off["status"], "noop_backoff")
            self.assertTrue(retried["ok"])
            self.assertEqual(attempts, 2)
            self.assertTrue(
                failed["evaluator_run_id"].startswith(
                    "strategy-center-auto-20260724-pending_selection-r9-"
                )
            )
            self.assertTrue(failed["write_called"])
            self.assertEqual(failed["marked_failed_revision_ids"], [9])
            self.assertEqual(
                repository.status_calls,
                [((9,), "failed")],
            )
            self.assertEqual(failed["selected_scope"], {
                "principal_id": 9,
                "user_id": 9,
                "selection_revision_id": 9,
            })
            self.assertEqual(failed["remaining_count"], 2)
            self.assertEqual(retried["selected_scope"], failed["selected_scope"])
            persisted = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(
                persisted["source_cursor"]["fingerprint"], old_fingerprint
            )

    def test_lock_held_is_safe_noop_and_does_not_evaluate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            state_path, lock_path = self._paths(root)
            repository = FakeRepository(auto_state(pending=(10,)))
            lock_path.touch()
            lock_path.chmod(0o600)
            with lock_path.open("a+", encoding="utf-8") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                result = run_auto_once(
                    repository=repository,
                    state_path=state_path,
                    lock_path=lock_path,
                    release_id=RELEASE_ID,
                    execute=True,
                    runtime_authorized=True,
                    now=NOW,
                    evaluate_once=lambda *_args: self.fail("must not evaluate"),
                )
            self.assertEqual(result["status"], "noop_lock_held")
            self._assert_evidence_contract(result)
            self.assertEqual(result["trigger_kind"], "local_lock")
            self.assertIsNone(result["pending_revision_count"])
            self.assertEqual(repository.status_calls, [])

    def test_retry_uses_stable_attempt_scoped_evaluator_run_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            state_path, lock_path = self._paths(root)
            write_private_json(state_path, previous_state("4" * 64))
            repository = FakeRepository(
                auto_state(pending=(12,), fingerprint="4" * 64)
            )
            run_ids: list[str] = []

            def evaluate(_trade_date, run_id, *_args):
                run_ids.append(run_id)
                if len(run_ids) == 1:
                    raise RuntimeError("retry_me")
                return {"ok": True, "write_called": True}

            run_auto_once(
                repository=repository,
                state_path=state_path,
                lock_path=lock_path,
                release_id=RELEASE_ID,
                execute=True,
                runtime_authorized=True,
                now=NOW,
                evaluate_once=evaluate,
            )
            run_auto_once(
                repository=repository,
                state_path=state_path,
                lock_path=lock_path,
                release_id=RELEASE_ID,
                execute=True,
                runtime_authorized=True,
                now=NOW + timedelta(seconds=5),
                evaluate_once=evaluate,
            )
            self.assertEqual(len(run_ids), 2)
            self.assertEqual(run_ids[0], run_ids[1])

    def test_source_change_rotates_active_scopes_and_restart_restores_cursor(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            state_path, lock_path = self._paths(root)
            write_private_json(state_path, previous_state("1" * 64))
            current = auto_state(
                fingerprint="2" * 64,
                active=(31, 32, 33),
            )
            repository = FakeRepository(current)
            selected: list[int] = []

            def evaluate(_trade_date, _run_id, scope, _execute, _authorized):
                selected.append(scope.selection_revision_id)
                return {"ok": True, "write_called": True, "work_item_count": 1}

            first = run_auto_once(
                repository=repository,
                state_path=state_path,
                lock_path=lock_path,
                release_id=RELEASE_ID,
                execute=True,
                runtime_authorized=True,
                now=NOW,
                evaluate_once=evaluate,
            )
            restarted_repository = FakeRepository(current)
            second = run_auto_once(
                repository=restarted_repository,
                state_path=state_path,
                lock_path=lock_path,
                release_id=RELEASE_ID,
                execute=True,
                runtime_authorized=True,
                now=NOW + timedelta(seconds=5),
                evaluate_once=evaluate,
            )
            third = run_auto_once(
                repository=restarted_repository,
                state_path=state_path,
                lock_path=lock_path,
                release_id=RELEASE_ID,
                execute=True,
                runtime_authorized=True,
                now=NOW + timedelta(seconds=10),
                evaluate_once=evaluate,
            )
            fourth = run_auto_once(
                repository=restarted_repository,
                state_path=state_path,
                lock_path=lock_path,
                release_id=RELEASE_ID,
                execute=True,
                runtime_authorized=True,
                now=NOW + timedelta(seconds=15),
                evaluate_once=evaluate,
            )

            self.assertEqual(selected, [31, 32, 33, 31])
            self.assertEqual(
                [
                    first["remaining_count"],
                    second["remaining_count"],
                    third["remaining_count"],
                    fourth["remaining_count"],
                ],
                [2, 1, 0, 2],
            )
            self.assertEqual(fourth["status"], "committed")
            self.assertEqual(fourth["trigger_kind"], "time_tick")
            persisted = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["source_cursor"]["fingerprint"], "2" * 64)
            self.assertEqual(
                [
                    item["selection_revision_id"]
                    for item in persisted["scope_cursor"]["remaining_scopes"]
                ],
                [32, 33],
            )

    def test_tampered_scope_cursor_order_fails_closed_before_evaluation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            state_path, lock_path = self._paths(root)
            payload = previous_state("1" * 64)
            payload["scope_cursor"] = {
                "trade_date": "20260722",
                "fingerprint": "2" * 64,
                "release_id": RELEASE_ID,
                "evaluator_policy_hash": EVALUATOR_POLICY_HASH,
                "authority_scopes": [
                    {
                        "principal_id": 31,
                        "user_id": 31,
                        "selection_revision_id": 31,
                    },
                    {
                        "principal_id": 32,
                        "user_id": 32,
                        "selection_revision_id": 32,
                    },
                ],
                "remaining_scopes": [
                    {
                        "principal_id": 31,
                        "user_id": 31,
                        "selection_revision_id": 31,
                    }
                ],
                "last_completed_scope": {
                    "principal_id": 32,
                    "user_id": 32,
                    "selection_revision_id": 32,
                },
            }
            write_private_json(state_path, payload)
            repository = FakeRepository(
                auto_state(fingerprint="2" * 64, active=(31, 32))
            )
            result = run_auto_once(
                repository=repository,
                state_path=state_path,
                lock_path=lock_path,
                release_id=RELEASE_ID,
                execute=True,
                runtime_authorized=True,
                now=NOW,
                evaluate_once=lambda *_args: self.fail("must not evaluate"),
            )
            self.assertEqual(result["status"], "blocked_state_invalid")
            self.assertEqual(repository.load_calls, 0)

    def test_runtime_budget_preserves_twelve_second_total_bound(self) -> None:
        observed_scope_seconds = 10.7
        legacy_evaluation_budget = _evaluation_budget_seconds(10)
        self.assertEqual(legacy_evaluation_budget, 9.0)
        self.assertGreater(observed_scope_seconds, legacy_evaluation_budget)
        self.assertEqual(DEFAULT_MAX_RUNTIME_SECONDS, 12)
        self.assertEqual(EVIDENCE_MAX_RUNTIME_SECONDS, 1.0)
        self.assertEqual(
            _evaluation_budget_seconds(DEFAULT_MAX_RUNTIME_SECONDS),
            11.0,
        )
        self.assertLess(
            observed_scope_seconds,
            _evaluation_budget_seconds(DEFAULT_MAX_RUNTIME_SECONDS),
        )

    def test_evaluator_timer_is_cancelled_before_bounded_evidence_phase(
        self,
    ) -> None:
        source = Path(
            "scripts/run_n6_strategy_center_auto_once.py"
        ).read_text(encoding="utf-8")
        main_source = source[source.index("def main() -> int:"):]
        evaluation_cancel = main_source.index(
            "signal.setitimer(signal.ITIMER_REAL, 0)"
        )
        evidence_handler = main_source.index(
            "signal.signal(signal.SIGALRM, _evidence_timeout_handler)"
        )
        evidence_persist = main_source.index("_persist_runtime_evidence(")
        self.assertLess(evaluation_cancel, evidence_handler)
        self.assertLess(evidence_handler, evidence_persist)
        with self.assertRaisesRegex(
            AutoEvaluatorDeadlineExceeded, "evaluation_deadline"
        ):
            _timeout_handler(0, None)
        with self.assertRaisesRegex(
            AutoEvaluatorDeadlineExceeded, "evidence_deadline"
        ):
            _evidence_timeout_handler(0, None)

    def test_runtime_budget_rejects_values_above_twelve_seconds(self) -> None:
        with self.assertRaisesRegex(ValueError, "between_2_and_12"):
            _evaluation_budget_seconds(13)

    def test_cli_defaults_to_twelve_second_total_deadline(self) -> None:
        args = build_parser().parse_args(
            [
                "--state-path",
                str(EXPECTED_RUNTIME_PATHS["state_path"]),
                "--singleton-lock-path",
                str(EXPECTED_RUNTIME_PATHS["lock_path"]),
                "--json-report-path",
                str(EXPECTED_RUNTIME_PATHS["report_path"]),
                "--history-path",
                str(EXPECTED_RUNTIME_PATHS["history_path"]),
                "--release-id",
                RELEASE_ID,
            ]
        )
        self.assertEqual(args.max_runtime_seconds, 12)

    def test_singleton_lock_prevents_overlap_under_total_deadline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            lock_path = Path(directory).resolve() / "evaluator.lock"
            with _singleton_lock(lock_path) as first_acquired:
                self.assertTrue(first_acquired)
                with _singleton_lock(lock_path) as second_acquired:
                    self.assertFalse(second_acquired)
            self.assertEqual(
                _evaluation_budget_seconds(DEFAULT_MAX_RUNTIME_SECONDS)
                + EVIDENCE_MAX_RUNTIME_SECONDS,
                12,
            )

    def test_singleton_lock_rejects_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            state_path, lock_path = self._paths(root)
            lock_target = root / "lock-target"
            lock_target.touch()
            lock_path.symlink_to(lock_target)
            repository = FakeRepository(auto_state(pending=(13,)))
            with self.assertRaises(AutoEvaluatorStateBlocked):
                run_auto_once(
                    repository=repository,
                    state_path=state_path,
                    lock_path=lock_path,
                    release_id=RELEASE_ID,
                    execute=True,
                    runtime_authorized=True,
                    now=NOW,
                )

    def test_crash_left_running_revision_remains_due_without_prewrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            state_path, lock_path = self._paths(root)
            write_private_json(state_path, previous_state("5" * 64))
            repository = FakeRepository(
                auto_state(pending=(14,), fingerprint="5" * 64)
            )
            result = run_auto_once(
                repository=repository,
                state_path=state_path,
                lock_path=lock_path,
                release_id=RELEASE_ID,
                execute=True,
                runtime_authorized=True,
                now=NOW,
                evaluate_once=lambda *_args: {
                    "ok": True,
                    "write_called": True,
                },
            )
            self.assertEqual(result["status"], "committed")
            self.assertEqual(repository.status_calls, [])

    def test_db_commit_is_not_reclassified_when_state_persist_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            state_path, lock_path = self._paths(root)
            write_private_json(state_path, previous_state("6" * 64))
            repository = FakeRepository(
                auto_state(pending=(15,), fingerprint="6" * 64)
            )
            with patch(
                "scripts.run_n6_strategy_center_auto_once._atomic_write_json",
                side_effect=OSError("disk_full"),
            ):
                result = run_auto_once(
                    repository=repository,
                    state_path=state_path,
                    lock_path=lock_path,
                    release_id=RELEASE_ID,
                    execute=True,
                    runtime_authorized=True,
                    now=NOW,
                    evaluate_once=lambda *_args: {
                        "ok": True,
                        "write_called": True,
                    },
                )
            self.assertFalse(result["ok"])
            self.assertEqual(result["status"], "committed_state_persist_failed")
            self.assertTrue(result["database_committed"])
            self.assertEqual(repository.status_calls, [])

    def test_corrupt_state_blocks_before_repository_access(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            state_path, lock_path = self._paths(root)
            state_path.write_text("{broken", encoding="utf-8")
            state_path.chmod(0o600)
            repository = FakeRepository(auto_state(pending=(16,)))
            result = run_auto_once(
                repository=repository,
                state_path=state_path,
                lock_path=lock_path,
                release_id=RELEASE_ID,
                execute=True,
                runtime_authorized=True,
                now=NOW,
            )
            self.assertEqual(result["status"], "blocked_state_invalid")
            self._assert_evidence_contract(result)
            self.assertEqual(result["trigger_kind"], "state_validation")
            self.assertEqual(repository.load_calls, 0)
            self.assertEqual(state_path.read_text(encoding="utf-8"), "{broken")

    def test_json_valid_state_schema_and_backoff_timestamp_fail_closed(self) -> None:
        for label, mutation in (
            ("cursor_type", {"source_cursor": []}),
            (
                "retry_timestamp",
                {
                    "consecutive_failures": 1,
                    "last_failed_attempt_key": "c" * 64,
                    "next_retry_at": "not-a-timestamp",
                },
            ),
        ):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                state_path, lock_path = self._paths(root)
                payload = {**previous_state("9" * 64), **mutation}
                write_private_json(state_path, payload)
                repository = FakeRepository(auto_state(pending=(19,)))
                result = run_auto_once(
                    repository=repository,
                    state_path=state_path,
                    lock_path=lock_path,
                    release_id=RELEASE_ID,
                    execute=True,
                    runtime_authorized=True,
                    now=NOW,
                    evaluate_once=lambda *_args: self.fail("must not evaluate"),
                )
                self.assertEqual(result["status"], "blocked_state_invalid")
                self.assertEqual(repository.load_calls, 0)

    def test_report_write_failure_is_recorded_as_failure_in_history(self) -> None:
        captured: list[dict[str, object]] = []
        with patch(
            "scripts.run_n6_strategy_center_auto_once._atomic_write_json",
            side_effect=OSError("report_disk_full"),
        ), patch(
            "scripts.run_n6_strategy_center_auto_once._append_history",
            side_effect=lambda _path, payload: (
                captured.append(dict(payload))
                or {
                    "history_rotated": False,
                    "history_rotation_count": HISTORY_ROTATION_COUNT,
                    "history_max_bytes": HISTORY_MAX_BYTES,
                }
            ),
        ):
            final, errors = _persist_runtime_evidence(
                report={
                    "ok": True,
                    "status": "committed",
                    "database_committed": True,
                },
                report_path=Path("/fixed/report.json"),
                history_path=Path("/fixed/history.jsonl"),
            )
        self.assertFalse(final["ok"])
        self.assertEqual(len(errors), 1)
        self.assertEqual(len(captured), 1)
        self.assertFalse(captured[0]["ok"])
        self.assertIn("report:OSError:report_disk_full", errors[0])

    def test_watchdog_deadline_cannot_be_swallowed_by_evidence_writes(self) -> None:
        prior_handler = signal.signal(
            signal.SIGALRM, _evidence_timeout_handler
        )
        started = time.monotonic()
        signal.alarm(1)
        try:
            with patch(
                "scripts.run_n6_strategy_center_auto_once._atomic_write_json",
                side_effect=lambda *_args: time.sleep(2),
            ), patch(
                "scripts.run_n6_strategy_center_auto_once._append_history",
                side_effect=lambda *_args: time.sleep(2),
            ):
                with self.assertRaises(AutoEvaluatorDeadlineExceeded):
                    _persist_runtime_evidence(
                        report={"ok": True, "status": "committed"},
                        report_path=Path("/fixed/report.json"),
                        history_path=Path("/fixed/history.jsonl"),
                    )
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, prior_handler)
        self.assertLess(time.monotonic() - started, 1.75)

    def test_evaluation_deadline_preserves_cursor_and_enters_backoff(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            state_path, lock_path = self._paths(root)
            fingerprint = "e" * 64
            write_private_json(state_path, previous_state(fingerprint))
            repository = FakeRepository(
                auto_state(pending=(20,), fingerprint=fingerprint)
            )
            result = run_auto_once(
                repository=repository,
                state_path=state_path,
                lock_path=lock_path,
                release_id=RELEASE_ID,
                execute=True,
                runtime_authorized=True,
                now=NOW,
                evaluate_once=lambda *_args: (_ for _ in ()).throw(
                    AutoEvaluatorDeadlineExceeded("deadline")
                ),
            )
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["consecutive_failures"], 1)
            self.assertEqual(result["marked_failed_revision_ids"], [])
            self.assertEqual(repository.status_calls, [])
            persisted = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(
                persisted["source_cursor"]["fingerprint"],
                fingerprint,
            )

    def test_source_state_failure_persists_backoff_without_db_evaluation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            state_path, lock_path = self._paths(root)
            write_private_json(state_path, previous_state("8" * 64))

            class FailingRepository(FakeRepository):
                def load_auto_evaluation_state(self):
                    self.load_calls += 1
                    raise RuntimeError("source_state_unavailable")

            repository = FailingRepository(auto_state(fingerprint="8" * 64))
            first = run_auto_once(
                repository=repository,
                state_path=state_path,
                lock_path=lock_path,
                release_id=RELEASE_ID,
                execute=True,
                runtime_authorized=True,
                now=NOW,
            )
            second = run_auto_once(
                repository=repository,
                state_path=state_path,
                lock_path=lock_path,
                release_id=RELEASE_ID,
                execute=True,
                runtime_authorized=True,
                now=NOW + timedelta(seconds=1),
            )
            self.assertEqual(first["status"], "failed_source_state")
            self._assert_evidence_contract(first)
            self.assertEqual(first["trigger_kind"], "source_state")
            self.assertEqual(second["status"], "noop_backoff")
            self._assert_evidence_contract(second)
            self.assertEqual(repository.load_calls, 1)

    def test_source_state_recovery_clears_stale_failure_counter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            state_path, lock_path = self._paths(root)
            fingerprint = "d" * 64
            payload = previous_state(fingerprint)
            source_attempt_key = hashlib.sha256(
                json.dumps(
                    {
                        "evaluator_policy_hash": EVALUATOR_POLICY_HASH,
                        "release_id": RELEASE_ID,
                        "stage": "source_state",
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            payload.update(
                {
                    "consecutive_failures": 2,
                    "last_failed_attempt_key": source_attempt_key,
                    "next_retry_at": "2026-07-22T03:59:59Z",
                    "last_trigger_kind": "source_state",
                }
            )
            write_private_json(state_path, payload)
            repository = FakeRepository(auto_state(fingerprint=fingerprint))
            result = run_auto_once(
                repository=repository,
                state_path=state_path,
                lock_path=lock_path,
                release_id=RELEASE_ID,
                execute=True,
                runtime_authorized=True,
                now=NOW,
                evaluate_once=lambda *_args: self.fail("must not evaluate"),
            )
            self.assertEqual(result["status"], "noop_source_state_recovered")
            self.assertEqual(result["consecutive_failures"], 0)
            persisted = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["consecutive_failures"], 0)
            self.assertEqual(persisted["next_retry_at"], "")

    def test_release_change_forces_one_full_evaluation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            state_path, lock_path = self._paths(root)
            fingerprint = "7" * 64
            write_private_json(state_path, previous_state(fingerprint))
            repository = FakeRepository(auto_state(fingerprint=fingerprint))
            run_ids: list[str] = []

            def evaluate(_trade_date, run_id, *_args):
                run_ids.append(run_id)
                return {"ok": True, "write_called": True}

            first = run_auto_once(
                repository=repository,
                state_path=state_path,
                lock_path=lock_path,
                release_id=NEXT_RELEASE_ID,
                execute=True,
                runtime_authorized=True,
                now=NOW,
                evaluate_once=evaluate,
            )
            second = run_auto_once(
                repository=repository,
                state_path=state_path,
                lock_path=lock_path,
                release_id=NEXT_RELEASE_ID,
                execute=True,
                runtime_authorized=True,
                now=NOW + timedelta(seconds=5),
                evaluate_once=evaluate,
            )
            self.assertEqual(first["trigger_kind"], "release_changed")
            self.assertEqual(second["status"], "committed")
            self.assertEqual(second["trigger_kind"], "time_tick")
            self.assertEqual(len(run_ids), 2)
            self.assertNotEqual(run_ids[0], run_ids[1])

    def test_lock_rejects_hardlink_and_wrong_mode_parent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            state_path, lock_path = self._paths(root)
            lock_target = root / "lock-target"
            lock_target.touch(mode=0o600)
            lock_target.chmod(0o600)
            os.link(lock_target, lock_path)
            repository = FakeRepository(auto_state(pending=(17,)))
            with self.assertRaises(AutoEvaluatorStateBlocked):
                run_auto_once(
                    repository=repository,
                    state_path=state_path,
                    lock_path=lock_path,
                    release_id=RELEASE_ID,
                    execute=True,
                    runtime_authorized=True,
                    now=NOW,
                )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            state_path, lock_path = self._paths(root)
            root.chmod(0o755)
            try:
                repository = FakeRepository(auto_state(pending=(18,)))
                with self.assertRaises(AutoEvaluatorStateBlocked):
                    run_auto_once(
                        repository=repository,
                        state_path=state_path,
                        lock_path=lock_path,
                        release_id=RELEASE_ID,
                        execute=True,
                        runtime_authorized=True,
                        now=NOW,
                    )
            finally:
                root.chmod(0o700)

    def test_history_is_o1_append_private_and_bounded_rotation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            history_path = root / "history.jsonl"
            history_path.write_bytes(b"x" * (HISTORY_MAX_BYTES - 64))
            history_path.chmod(0o600)
            with patch(
                "scripts.run_n6_strategy_center_auto_once._read_private_text",
                side_effect=AssertionError("history_must_not_be_read"),
            ):
                metadata = _append_history(
                    history_path, {"sequence": 1}
                )
            self.assertTrue(metadata["history_rotated"])
            self.assertTrue(Path(f"{history_path}.1").exists())
            current = json.loads(
                history_path.read_text(encoding="utf-8")
            )
            self.assertEqual(current["sequence"], 1)
            self.assertTrue(current["history_rotated"])
            self.assertEqual(history_path.stat().st_mode & 0o777, 0o600)
            for sequence in range(2, HISTORY_ROTATION_COUNT + 4):
                history_path.write_bytes(
                    b"x" * (HISTORY_MAX_BYTES - 64)
                )
                history_path.chmod(0o600)
                _append_history(history_path, {"sequence": sequence})
            self.assertFalse(
                Path(
                    f"{history_path}.{HISTORY_ROTATION_COUNT + 1}"
                ).exists()
            )

    def test_execute_requires_runtime_authorization_before_repository_access(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            state_path, lock_path = self._paths(root)
            repository = FakeRepository(auto_state(pending=(11,)))
            with self.assertRaisesRegex(ValueError, "runtime_authorization_required"):
                run_auto_once(
                    repository=repository,
                    state_path=state_path,
                    lock_path=lock_path,
                    release_id=RELEASE_ID,
                    execute=True,
                    runtime_authorized=False,
                    now=NOW,
                )
            self.assertEqual(repository.status_calls, [])

    def test_cli_runtime_paths_are_fixed_not_merely_absolute(self) -> None:
        paths = dict(EXPECTED_RUNTIME_PATHS)
        paths["state_path"] = Path("/tmp/alternate-state.json")
        with self.assertRaisesRegex(ValueError, "fixed_runtime_path"):
            validate_runtime_paths(paths)


if __name__ == "__main__":
    unittest.main()
