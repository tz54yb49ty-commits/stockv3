from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import ashare_v3.runtime as runtime_exports
import ashare_v3.runtime.bounded_worker_control as bounded_worker_control
from ashare_v3.runtime.bounded_worker_control import (
    BoundedResult,
    BoundedWorkerStatus,
    SingletonLockHeld,
    acquire_global_chain_lock,
    atomic_write_json,
    build_invocation_id,
    build_run_id,
    check_stop_file,
    deadline_from_now,
    remaining_deadline_seconds,
    result_to_exit_code,
    run_child_with_timeout,
)


PARTIAL_RESULT = "PARTIAL"
LOCK_PATH_BUILDER = "build_phase1_realtime_chain_lock_path"


class BoundedWorkerControlTest(unittest.TestCase):
    def _wait_for_path(self, path: Path, timeout_seconds: float = 3.0) -> bool:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if path.exists():
                return True
            time.sleep(0.02)
        return path.exists()

    def _process_is_active(self, pid: int) -> bool:
        if os.name != "posix":
            return False
        completed = subprocess.run(
            ["ps", "-p", str(pid), "-o", "stat="],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            return False
        stat = completed.stdout.strip()
        return bool(stat) and not stat.startswith("Z")

    def _wait_for_process_exit(self, pid: int, timeout_seconds: float = 3.0) -> bool:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if not self._process_is_active(pid):
                return True
            time.sleep(0.02)
        return not self._process_is_active(pid)

    def _status(self, result: str, requires_post_check: bool) -> BoundedWorkerStatus:
        return BoundedWorkerStatus(
            result=result,
            stop_reason=None,
            requires_post_check=requires_post_check,
            invocation_id=build_invocation_id(),
            run_id=build_run_id("phase1_chain", "20260621"),
            trade_date="20260621",
            worker_name="phase1_chain",
        )

    def _partial_status(self, **overrides: object) -> BoundedWorkerStatus:
        payload = {
            "result": PARTIAL_RESULT,
            "stop_reason": "bounded_plan_incomplete",
            "requires_post_check": False,
            "invocation_id": build_invocation_id(),
            "run_id": build_run_id("phase1_chain", "20260621"),
            "trade_date": "20260621",
            "worker_name": "phase1_chain",
            "completed_stages": ["B1_snapshot"],
            "pending_stages": ["C1_projection"],
            "partial_reason": "C1_projection_not_started",
            "output_run_ids": {"B1_snapshot": "snapshot_run_1"},
            "rollback_artifacts": {"B1_snapshot": "rollback_b1.sql"},
            "downstream_consumption_allowed": False,
        }
        payload.update(overrides)
        return BoundedWorkerStatus(**payload)

    def _lock_path_builder(self):
        self.assertTrue(hasattr(bounded_worker_control, LOCK_PATH_BUILDER))
        return getattr(bounded_worker_control, LOCK_PATH_BUILDER)

    def test_invocation_id_is_uuid_like_and_unique(self) -> None:
        first = build_invocation_id()
        second = build_invocation_id()

        self.assertNotEqual(first, second)
        self.assertEqual(uuid.UUID(hex=first).hex, first)
        self.assertEqual(uuid.UUID(hex=second).hex, second)

    def test_run_id_is_not_minute_only(self) -> None:
        fixed_now = datetime(2026, 6, 21, 9, 36, 25, 123456, tzinfo=timezone.utc)

        first = build_run_id("n3_bounded", "20260621", now=fixed_now)
        second = build_run_id("n3_bounded", "20260621", now=fixed_now)

        self.assertIn("n3_bounded", first)
        self.assertIn("20260621", first)
        self.assertIn("20260621T093625123456Z", first)
        self.assertNotEqual(first, second)
        self.assertRegex(first, r"^n3_bounded_20260621_20260621T093625123456Z_[0-9a-f]{32}$")

    def test_run_id_rejects_unsafe_inputs(self) -> None:
        invalid_cases = [
            ("", "20260621", None),
            ("bad/prefix", "20260621", None),
            ("bad prefix", "20260621", None),
            ("bad\nprefix", "20260621", None),
            ("x" * 65, "20260621", None),
            ("n3_bounded", "2026-06-21", None),
            ("n3_bounded", "20260230", None),
            ("n3_bounded", "20260621", "not-a-uuid"),
        ]

        for prefix, trade_date, invocation_id in invalid_cases:
            with self.subTest(prefix=prefix, trade_date=trade_date, invocation_id=invocation_id):
                with self.assertRaises(ValueError):
                    build_run_id(prefix, trade_date, invocation_id=invocation_id)

    def test_run_id_normalizes_supplied_invocation_uuid(self) -> None:
        fixed_now = datetime(2026, 6, 21, 9, 36, 25, 123456, tzinfo=timezone.utc)
        invocation_id = "12345678-1234-5678-1234-567812345678"

        run_id = build_run_id("n3_bounded", "20260621", invocation_id=invocation_id, now=fixed_now)

        self.assertTrue(run_id.endswith("_12345678123456781234567812345678"))

    def test_global_chain_lock_second_instance_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / "chain.lock"

            with acquire_global_chain_lock(lock_path, {"worker_name": "phase1_chain"}) as lock_file:
                self.assertFalse(lock_file.closed)
                with self.assertRaises(SingletonLockHeld):
                    with acquire_global_chain_lock(lock_path, {"worker_name": "phase1_chain"}):
                        self.fail("second instance should not acquire the lock")

                status = BoundedWorkerStatus(
                    result=BoundedResult.NOOP,
                    stop_reason="singleton_lock_held",
                    requires_post_check=False,
                    invocation_id=build_invocation_id(),
                    run_id=build_run_id("phase1_chain", "20260621"),
                    trade_date="20260621",
                    worker_name="phase1_chain",
                )
                payload = status.to_dict()

                self.assertEqual(payload["result"], BoundedResult.NOOP)
                self.assertEqual(payload["stop_reason"], "singleton_lock_held")
                self.assertEqual(result_to_exit_code(payload["result"]), 0)
            self.assertTrue(lock_file.closed)

    def test_global_chain_lock_rejects_second_real_process(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            lock_path = root / "chain.lock"
            first_ready = root / "first_ready.json"
            release_file = root / "release"
            second_status = root / "second_status.json"
            holder_script = root / "holder.py"
            contender_script = root / "contender.py"
            env = dict(os.environ)
            env["PYTHONPATH"] = os.pathsep.join(
                part
                for part in [str(Path.cwd() / "src"), env.get("PYTHONPATH", "")]
                if part
            )

            holder_script.write_text(
                textwrap.dedent(
                    """
                    import json
                    import os
                    import sys
                    import time
                    from pathlib import Path

                    from ashare_v3.runtime.bounded_worker_control import acquire_global_chain_lock

                    lock_path = Path(sys.argv[1])
                    ready_path = Path(sys.argv[2])
                    release_path = Path(sys.argv[3])

                    with acquire_global_chain_lock(lock_path, {"owner": "first", "pid": os.getpid()}):
                        ready_path.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
                        while not release_path.exists():
                            time.sleep(0.05)
                    """
                ),
                encoding="utf-8",
            )
            contender_script.write_text(
                textwrap.dedent(
                    """
                    import json
                    import os
                    import sys
                    from pathlib import Path

                    from ashare_v3.runtime.bounded_worker_control import (
                        BoundedResult,
                        BoundedWorkerStatus,
                        SingletonLockHeld,
                        acquire_global_chain_lock,
                        build_invocation_id,
                        build_run_id,
                        result_to_exit_code,
                    )

                    lock_path = Path(sys.argv[1])
                    status_path = Path(sys.argv[2])

                    try:
                        with acquire_global_chain_lock(lock_path, {"owner": "second", "pid": os.getpid()}):
                            raise SystemExit(9)
                    except SingletonLockHeld:
                        status = BoundedWorkerStatus(
                            result=BoundedResult.NOOP,
                            stop_reason="singleton_lock_held",
                            requires_post_check=False,
                            invocation_id=build_invocation_id(),
                            run_id=build_run_id("phase1_chain", "20260621"),
                            trade_date="20260621",
                            worker_name="phase1_chain",
                        )
                        status_path.write_text(
                            json.dumps(
                                {
                                    "status": status.to_dict(),
                                    "exit_code": result_to_exit_code(status.result),
                                    "child_invoked": False,
                                    "database_written": False,
                                    "lock_metadata": lock_path.read_text(encoding="utf-8"),
                                },
                                sort_keys=True,
                            ),
                            encoding="utf-8",
                        )
                        raise SystemExit(result_to_exit_code(status.result))
                    """
                ),
                encoding="utf-8",
            )

            first = subprocess.Popen(
                [sys.executable, str(holder_script), str(lock_path), str(first_ready), str(release_file)],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                self.assertTrue(self._wait_for_path(first_ready), "first process did not acquire lock")
                first_metadata = json.loads(lock_path.read_text(encoding="utf-8"))
                self.assertEqual(first_metadata["owner"], "first")

                second = subprocess.run(
                    [sys.executable, str(contender_script), str(lock_path), str(second_status)],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                self.assertEqual(second.returncode, 0, second.stderr)
                payload = json.loads(second_status.read_text(encoding="utf-8"))

                self.assertEqual(payload["status"]["result"], BoundedResult.NOOP)
                self.assertEqual(payload["status"]["stop_reason"], "singleton_lock_held")
                self.assertEqual(payload["exit_code"], 0)
                self.assertFalse(payload["child_invoked"])
                self.assertFalse(payload["database_written"])
                self.assertEqual(json.loads(payload["lock_metadata"])["owner"], "first")
                self.assertEqual(json.loads(lock_path.read_text(encoding="utf-8"))["owner"], "first")

                release_file.write_text("release\n", encoding="utf-8")
                first_stdout, first_stderr = first.communicate(timeout=5)
                self.assertEqual(first.returncode, 0, first_stderr)

                with acquire_global_chain_lock(lock_path, {"owner": "third"}):
                    self.assertEqual(json.loads(lock_path.read_text(encoding="utf-8"))["owner"], "third")
            finally:
                if first.poll() is None:
                    first.kill()
                    first.communicate(timeout=5)

    def test_atomic_write_json_uses_replace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "status.json"
            payload = {
                "result": BoundedResult.NOOP,
                "stop_reason": "singleton_lock_held",
                "requires_post_check": False,
            }

            with mock.patch(
                "ashare_v3.runtime.bounded_worker_control.os.replace",
                wraps=os.replace,
            ) as replace_mock:
                atomic_write_json(target, payload)

            self.assertTrue(replace_mock.called)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), payload)

    def test_atomic_write_json_regression_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "status.json"
            payload = {"z": 1, "a": {"b": 2}}
            replace_calls = []
            original_replace = os.replace

            def replace_spy(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
                replace_calls.append((Path(src), Path(dst)))
                original_replace(src, dst)

            with mock.patch(
                "ashare_v3.runtime.bounded_worker_control.os.replace",
                side_effect=replace_spy,
            ), mock.patch("ashare_v3.runtime.bounded_worker_control.os.fsync", wraps=os.fsync) as fsync_mock:
                atomic_write_json(target, payload)

            self.assertEqual(replace_calls[0][0].parent, target.parent)
            self.assertEqual(replace_calls[0][1], target)
            self.assertGreaterEqual(fsync_mock.call_count, 2)
            self.assertEqual(
                target.read_text(encoding="utf-8"),
                '{\n  "a": {\n    "b": 2\n  },\n  "z": 1\n}\n',
            )
            self.assertEqual(list(target.parent.glob(".status.json.tmp.*")), [])

    def test_atomic_write_json_cleans_temp_file_on_replace_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "status.json"

            with mock.patch(
                "ashare_v3.runtime.bounded_worker_control.os.replace",
                side_effect=RuntimeError("replace failed"),
            ):
                with self.assertRaises(RuntimeError):
                    atomic_write_json(target, {"result": BoundedResult.NOOP})

            self.assertEqual(list(target.parent.glob(".status.json.tmp.*")), [])
            self.assertFalse(target.exists())

    def test_stop_file_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stop_file = Path(tmpdir) / "STOP"

            present, reason = check_stop_file(stop_file)
            self.assertFalse(present)
            self.assertIsNone(reason)

            stop_file.write_text("stop\n", encoding="utf-8")
            present, reason = check_stop_file(stop_file)
            self.assertTrue(present)
            self.assertEqual(reason, "stop_file_present")

    def test_deadline_remaining_seconds(self) -> None:
        now = datetime(2026, 6, 21, 9, 36, 25, tzinfo=timezone.utc)
        future_deadline = deadline_from_now(10, now=now)
        past_deadline = now - timedelta(seconds=1)

        self.assertEqual(remaining_deadline_seconds(future_deadline, now=now), 10.0)
        self.assertEqual(remaining_deadline_seconds(past_deadline, now=now), 0.0)

    def test_existing_result_invariants_are_unchanged(self) -> None:
        legal_cases = [
            (BoundedResult.PASS, False),
            (BoundedResult.NOOP, False),
            (BoundedResult.BLOCKED, False),
            (BoundedResult.CRASHED, False),
            (BoundedResult.UNKNOWN_AFTER_TIMEOUT, True),
            (BoundedResult.COMMIT_UNKNOWN, True),
        ]
        for result, requires_post_check in legal_cases:
            with self.subTest(result=result, requires_post_check=requires_post_check):
                payload = self._status(result, requires_post_check).to_dict()
                self.assertEqual(payload["result"], result)
                self.assertEqual(payload["requires_post_check"], requires_post_check)

        illegal_cases = [
            (BoundedResult.PASS, True),
            (BoundedResult.NOOP, True),
            (BoundedResult.BLOCKED, True),
            (BoundedResult.CRASHED, True),
            (BoundedResult.UNKNOWN_AFTER_TIMEOUT, False),
            (BoundedResult.COMMIT_UNKNOWN, False),
            ("NOT_A_RESULT", False),
        ]
        for result, requires_post_check in illegal_cases:
            with self.subTest(result=result, requires_post_check=requires_post_check):
                with self.assertRaises(ValueError):
                    self._status(result, requires_post_check)

    def test_partial_result_exit_code_and_post_check_contract(self) -> None:
        self.assertEqual(getattr(BoundedResult, "PARTIAL", None), PARTIAL_RESULT)
        self.assertEqual(result_to_exit_code(PARTIAL_RESULT), 2)
        self.assertFalse(self._partial_status().requires_post_check)

    def test_partial_status_to_dict_includes_additive_fields(self) -> None:
        payload = self._partial_status(
            input_run_ids={"subscription": "sub_run_1"},
            output_run_id="legacy_single_run",
        ).to_dict()

        self.assertEqual(payload["result"], PARTIAL_RESULT)
        self.assertEqual(payload["completed_stages"], ["B1_snapshot"])
        self.assertEqual(payload["pending_stages"], ["C1_projection"])
        self.assertEqual(payload["partial_reason"], "C1_projection_not_started")
        self.assertEqual(payload["output_run_ids"], {"B1_snapshot": "snapshot_run_1"})
        self.assertEqual(payload["rollback_artifacts"], {"B1_snapshot": "rollback_b1.sql"})
        self.assertFalse(payload["downstream_consumption_allowed"])
        self.assertEqual(payload["output_run_id"], "legacy_single_run")

    def test_partial_rejects_empty_completed_stages(self) -> None:
        with self.assertRaises(ValueError):
            self._partial_status(completed_stages=[])

    def test_partial_rejects_empty_pending_stages(self) -> None:
        with self.assertRaises(ValueError):
            self._partial_status(pending_stages=[])

    def test_partial_rejects_completed_pending_overlap(self) -> None:
        with self.assertRaises(ValueError):
            self._partial_status(
                completed_stages=["B1_snapshot"],
                pending_stages=["B1_snapshot"],
            )

    def test_partial_rejects_duplicate_stage_names(self) -> None:
        invalid_cases = [
            {"completed_stages": ["B1_snapshot", "B1_snapshot"]},
            {"pending_stages": ["C1_projection", "C1_projection"]},
        ]
        for overrides in invalid_cases:
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):
                    self._partial_status(**overrides)

    def test_partial_rejects_empty_partial_reason(self) -> None:
        invalid_cases = ["", "   ", None]
        for partial_reason in invalid_cases:
            with self.subTest(partial_reason=partial_reason):
                with self.assertRaises(ValueError):
                    self._partial_status(partial_reason=partial_reason)

    def test_partial_rejects_downstream_consumption_allowed_true(self) -> None:
        with self.assertRaises(ValueError):
            self._partial_status(downstream_consumption_allowed=True)

    def test_partial_rejects_requires_post_check_true(self) -> None:
        with self.assertRaises(ValueError):
            self._partial_status(requires_post_check=True)

    def test_partial_requires_output_run_ids_and_rollback_artifacts(self) -> None:
        invalid_cases = [
            {"output_run_ids": {}},
            {"rollback_artifacts": {}},
        ]
        for overrides in invalid_cases:
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):
                    self._partial_status(**overrides)

    def test_phase1_realtime_chain_lock_path_is_deterministic(self) -> None:
        build_path = self._lock_path_builder()
        repo_root = Path("/tmp/v3_repo")

        first = build_path(repo_root, "20260621")
        second = build_path(repo_root, "20260621")

        self.assertEqual(first, repo_root / "tmp" / "v3_phase1_realtime_chain_20260621.lock")
        self.assertEqual(first, second)

    def test_phase1_realtime_chain_lock_name_is_not_layer_specific(self) -> None:
        build_path = self._lock_path_builder()
        lock_path = build_path(Path("/tmp/v3_repo"), "20260621")

        lowered_name = lock_path.name.lower()
        self.assertNotIn("n3", lowered_name)
        self.assertNotIn("n4", lowered_name)
        self.assertNotIn("n5", lowered_name)

    def test_phase1_realtime_chain_lock_path_rejects_invalid_inputs(self) -> None:
        build_path = self._lock_path_builder()
        with self.assertRaises(ValueError):
            build_path(Path("/tmp/v3_repo"), "2026-06-21")
        with self.assertRaises(ValueError):
            build_path(Path("/tmp/v3_repo"), "20260230")
        with self.assertRaises(ValueError):
            build_path("", "20260621")

    def test_child_timeout_returns_unknown_after_timeout(self) -> None:
        result = run_child_with_timeout(
            [sys.executable, "-c", "import time; time.sleep(1)"],
            timeout_seconds=0.05,
        )

        self.assertEqual(result["result"], BoundedResult.UNKNOWN_AFTER_TIMEOUT)
        self.assertEqual(result["exit_code"], 3)
        self.assertTrue(result["requires_post_check"])

    def test_child_timeout_terminates_process_group_and_grandchild(self) -> None:
        if os.name != "posix":
            self.skipTest("process-group timeout contract is POSIX-only")

        grandchild_pid = None
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            child_script = root / "child.py"
            grandchild_script = root / "grandchild.py"
            child_pid_path = root / "child.pid"
            grandchild_pid_path = root / "grandchild.pid"
            grandchild_term_path = root / "grandchild.term"
            heartbeat_path = root / "grandchild.heartbeat"

            grandchild_script.write_text(
                textwrap.dedent(
                    """
                    import signal
                    import sys
                    import time
                    from pathlib import Path

                    pid_path = Path(sys.argv[1])
                    term_path = Path(sys.argv[2])
                    heartbeat_path = Path(sys.argv[3])
                    pid_path.write_text(str(__import__("os").getpid()), encoding="utf-8")

                    def on_term(signum, frame):
                        term_path.write_text(str(signum), encoding="utf-8")
                        raise SystemExit(0)

                    signal.signal(signal.SIGTERM, on_term)
                    counter = 0
                    while True:
                        counter += 1
                        heartbeat_path.write_text(str(counter), encoding="utf-8")
                        time.sleep(0.05)
                    """
                ),
                encoding="utf-8",
            )
            child_script.write_text(
                textwrap.dedent(
                    """
                    import os
                    import subprocess
                    import sys
                    import time
                    from pathlib import Path

                    child_pid_path = Path(sys.argv[1])
                    grandchild_script = Path(sys.argv[2])
                    grandchild_pid_path = Path(sys.argv[3])
                    grandchild_term_path = Path(sys.argv[4])
                    heartbeat_path = Path(sys.argv[5])

                    child_pid_path.write_text(str(os.getpid()), encoding="utf-8")
                    subprocess.Popen(
                        [
                            sys.executable,
                            str(grandchild_script),
                            str(grandchild_pid_path),
                            str(grandchild_term_path),
                            str(heartbeat_path),
                        ],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    while True:
                        time.sleep(1)
                    """
                ),
                encoding="utf-8",
            )

            try:
                result = run_child_with_timeout(
                    [
                        sys.executable,
                        str(child_script),
                        str(child_pid_path),
                        str(grandchild_script),
                        str(grandchild_pid_path),
                        str(grandchild_term_path),
                        str(heartbeat_path),
                    ],
                    timeout_seconds=0.2,
                )
                self.assertTrue(self._wait_for_path(grandchild_pid_path), "grandchild pid not written")
                grandchild_pid = int(grandchild_pid_path.read_text(encoding="utf-8"))

                self.assertEqual(result["result"], BoundedResult.UNKNOWN_AFTER_TIMEOUT)
                self.assertEqual(result["exit_code"], 3)
                self.assertTrue(result["requires_post_check"])
                self.assertTrue(result["timeout_sigterm_sent"])
                self.assertIn("timeout_sigkill_sent", result)
                self.assertTrue(
                    self._wait_for_path(grandchild_term_path),
                    "grandchild did not receive process-group SIGTERM",
                )
                heartbeat_after_term = heartbeat_path.read_text(encoding="utf-8")
                time.sleep(0.2)
                self.assertEqual(heartbeat_path.read_text(encoding="utf-8"), heartbeat_after_term)
                self.assertTrue(
                    self._wait_for_process_exit(grandchild_pid),
                    f"grandchild pid {grandchild_pid} is still active",
                )
            finally:
                if grandchild_pid is not None and self._process_is_active(grandchild_pid):
                    os.kill(grandchild_pid, signal.SIGKILL)
                    self._wait_for_process_exit(grandchild_pid)

    def test_child_success_returns_pass(self) -> None:
        result = run_child_with_timeout(
            [sys.executable, "-c", "print('ok')"],
            timeout_seconds=2,
        )

        self.assertEqual(result["result"], BoundedResult.PASS)
        self.assertEqual(result["returncode"], 0)
        self.assertEqual(result["stdout"].strip(), "ok")
        self.assertFalse(result["requires_post_check"])

    def test_contract_provided_symbols_match_runtime_exports(self) -> None:
        contract = json.loads(
            Path("docs/V3_PHASE1_COMMON_BOUNDED_WORKER_CONTROL_CONTRACT.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(set(contract["provided_symbols"]), set(runtime_exports.__all__))
        self.assertEqual(set(bounded_worker_control.__all__), set(runtime_exports.__all__))
        self.assertIn("SingletonLockHeld", contract["provided_symbols"])
        self.assertIn(LOCK_PATH_BUILDER, contract["provided_symbols"])
        markdown = Path("docs/V3_PHASE1_COMMON_BOUNDED_WORKER_CONTROL_CONTRACT.md").read_text(
            encoding="utf-8"
        )
        for symbol in runtime_exports.__all__:
            self.assertIn(symbol, markdown)
        self.assertIn(PARTIAL_RESULT, markdown)
        self.assertIn("downstream_consumption_allowed", markdown)
        self.assertIn("n4_consumption_allowed", markdown)

    def test_json_contract_matches_partial_runtime_contract(self) -> None:
        contract = json.loads(
            Path("docs/V3_PHASE1_COMMON_BOUNDED_WORKER_CONTROL_CONTRACT.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(contract["exit_code_contract"][PARTIAL_RESULT], 2)
        self.assertFalse(
            contract["status_invariant_contract"]["requires_post_check_by_result"][
                PARTIAL_RESULT
            ]
        )
        self.assertFalse(
            contract["status_invariant_contract"]["partial"]["downstream_consumption_allowed"]
        )
        self.assertEqual(
            contract["shared_chain_lock_path"]["filename_template"],
            "v3_phase1_realtime_chain_<trade_date>.lock",
        )
        self.assertIn(
            "downstream_consumption_allowed",
            contract["status_json_contract"]["required_fields"],
        )
        self.assertNotIn(
            "n4_consumption_allowed",
            contract["status_json_contract"]["required_fields"],
        )

    def test_result_to_exit_code(self) -> None:
        self.assertEqual(result_to_exit_code(BoundedResult.PASS), 0)
        self.assertEqual(result_to_exit_code(BoundedResult.NOOP), 0)
        self.assertEqual(result_to_exit_code(PARTIAL_RESULT), 2)
        self.assertEqual(result_to_exit_code(BoundedResult.BLOCKED), 2)
        self.assertEqual(result_to_exit_code(BoundedResult.CRASHED), 1)
        self.assertEqual(result_to_exit_code(BoundedResult.UNKNOWN_AFTER_TIMEOUT), 3)
        self.assertEqual(result_to_exit_code(BoundedResult.COMMIT_UNKNOWN), 3)


if __name__ == "__main__":
    unittest.main()
