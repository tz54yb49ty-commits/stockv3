import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path


ASIA_SHANGHAI = timezone(timedelta(hours=8))
TRADE_DATE = "20260611"
SOURCE_CONDITION_RUN_ID = "condition_layer_20260610_source_20260610_v1"
SUBSCRIPTION_RUN_ID = f"market_data_subscription_{TRADE_DATE}_{SOURCE_CONDITION_RUN_ID}"
PRELOAD_RUN_ID = f"previous_day_minute_preload_20260610_for_{TRADE_DATE}__{SUBSCRIPTION_RUN_ID}"


def load_runner():
    try:
        import run_n3_bounded_worker_once as runner
    except ModuleNotFoundError as exc:  # pragma: no cover - red before implementation
        raise AssertionError("run_n3_bounded_worker_once module is required") from exc
    return runner


class ChildResult:
    def __init__(self, returncode=0, *, timed_out=False, result=None, stdout="", stderr=""):
        self.returncode = returncode
        self.timed_out = timed_out
        self.result = result
        self.stdout = stdout
        self.stderr = stderr


def make_plan(root: Path, *, forbidden: bool = False) -> dict:
    docs = root / "docs"
    sql = root / "sql"
    command_marker = "scripts/run_n4_forbidden.py" if forbidden else None
    return {
        "status": "ready",
        "reason": "closed_minute_available",
        "for_trade_date": TRADE_DATE,
        "latest_closed_minute": "2026-06-11T10:00:00+08:00",
        "latest_closed_minute_hhmm": "1000",
        "projection_input_mode": "closed_minute",
        "subscription_run_id": SUBSCRIPTION_RUN_ID,
        "preload_run_id": PRELOAD_RUN_ID,
        "child_steps": [
            make_step("B1", "snapshot_run_1", docs, sql, command_marker=command_marker),
            make_step("C1", "today_minute_run_1", docs, sql),
            make_step("B2", "projection_run_1", docs, sql),
        ],
    }


def make_step(stage: str, run_id: str, docs: Path, sql: Path, *, command_marker: str | None = None) -> dict:
    report_path = docs / f"{stage}_report.json"
    rollback_path = sql / f"{stage}_rollback.sql"
    script = command_marker
    if script is None:
        script = {
            "B1": "scripts/run_realtime_daily_snapshot_once.py",
            "C1": "scripts/run_today_minute_bar_1m_once.py",
            "B2": "scripts/run_realtime_projection_metric_once.py",
        }[stage]
    run_flag = {"B1": "--snapshot-run-id", "C1": "--today-minute-run-id", "B2": "--projection-run-id"}[stage]
    return {
        "stage": stage,
        "step_id": stage.lower(),
        "run_id": run_id,
        "json_report_path": str(report_path),
        "rollback_sql_path": str(rollback_path),
        "source_runs": {
            "subscription_run_id": SUBSCRIPTION_RUN_ID,
            "preload_run_id": PRELOAD_RUN_ID,
            "snapshot_run_id": "snapshot_run_1",
            "today_minute_run_id": "today_minute_run_1",
        },
        "command": [
            "python3",
            script,
            "--json-report-path",
            str(report_path),
            "--rollback-sql-path",
            str(rollback_path),
            run_flag,
            run_id,
            "--for-trade-date",
            TRADE_DATE,
            "--execute",
            "--user-confirmed",
            "--json",
        ],
    }


def fake_plan_builder(root: Path, *, forbidden: bool = False):
    def builder(**_kwargs):
        return make_plan(root, forbidden=forbidden)

    return builder


def fake_artifact_plan_builder(**_kwargs):
    return {"generated_artifacts": {}, "stage_run_ids": {"B1": "snapshot_run_1", "C1": "today_minute_run_1", "B2": "projection_run_1"}}


def fake_artifact_writer(plan, *, allow_overwrite=False):
    return {"status": "written", "artifact_count": len(plan.get("stage_run_ids", {}))}


def fake_artifact_validator(_plan):
    return {"status": "passed", "checks": [], "failed_checks": []}


def write_report_and_rollback(step: dict, *, mismatched_run_id: bool = False, illegal_json: bool = False, omit_rollback: bool = False):
    report_path = Path(step["json_report_path"])
    rollback_path = Path(step["rollback_sql_path"])
    report_path.parent.mkdir(parents=True, exist_ok=True)
    rollback_path.parent.mkdir(parents=True, exist_ok=True)
    if illegal_json:
        report_path.write_text("{not-json", encoding="utf-8")
    else:
        run_id = "wrong_run_id" if mismatched_run_id else step["run_id"]
        key = {"B1": "snapshot_run_id", "C1": "today_minute_run_id", "B2": "projection_run_id"}[step["stage"]]
        report_path.write_text(json.dumps({key: run_id, "status": "passed"}), encoding="utf-8")
    if not omit_rollback:
        rollback_path.write_text("DO $$ BEGIN RAISE EXCEPTION 'guard'; END $$;\nDELETE FROM t WHERE run_id = 'x';\n", encoding="utf-8")


class ScriptedChildRunner:
    def __init__(self, plan: dict, sequence: list[ChildResult], *, stop_file: Path | None = None, stop_after_stage: str | None = None, bad_report_stage: str | None = None, mismatched_stage: str | None = None, missing_rollback_stage: str | None = None):
        self.plan = plan
        self.sequence = list(sequence)
        self.calls = []
        self.stop_file = stop_file
        self.stop_after_stage = stop_after_stage
        self.bad_report_stage = bad_report_stage
        self.mismatched_stage = mismatched_stage
        self.missing_rollback_stage = missing_rollback_stage

    def __call__(self, argv, timeout_seconds=None, cwd=None, env=None):
        stage = self.plan["child_steps"][len(self.calls)]["stage"]
        step = self.plan["child_steps"][len(self.calls)]
        self.calls.append({"argv": argv, "timeout_seconds": timeout_seconds, "stage": stage})
        result = self.sequence.pop(0)
        if result.returncode == 0 and not result.timed_out:
            write_report_and_rollback(
                step,
                illegal_json=stage == self.bad_report_stage,
                mismatched_run_id=stage == self.mismatched_stage,
                omit_rollback=stage == self.missing_rollback_stage,
            )
        if self.stop_file is not None and self.stop_after_stage == stage:
            self.stop_file.write_text("stop", encoding="utf-8")
        return {
            "argv": list(argv),
            "returncode": result.returncode,
            "timed_out": result.timed_out,
            "result": result.result or ("UNKNOWN_AFTER_TIMEOUT" if result.timed_out else ("PASS" if result.returncode == 0 else "CRASHED")),
            "requires_post_check": bool(result.timed_out),
            "stdout": result.stdout,
            "stderr": result.stderr,
        }


def rolled_back_post_check(**_kwargs):
    return {"state": "rolled_back", "evidence": {"fake": True}}


def committed_post_check(**_kwargs):
    return {"state": "committed", "evidence": {"fake": True}}


def unresolved_post_check(**_kwargs):
    return {"state": "unresolved", "evidence": {"fake": True}}


def base_kwargs(root: Path, **overrides):
    kwargs = {
        "repo_root": root,
        "for_trade_date": TRADE_DATE,
        "source_condition_run_id": SOURCE_CONDITION_RUN_ID,
        "source_subscription_run_id": SUBSCRIPTION_RUN_ID,
        "previous_day_preload_run_id": PRELOAD_RUN_ID,
        "dsn": "postgresql://unused",
        "status_json": root / "status.json",
        "rollback_manifest_json": root / "rollback_manifest.json",
        "docs_root": root / "docs",
        "sql_root": root / "sql",
        "python_executable": "python3",
        "now": datetime(2026, 6, 11, 10, 0, tzinfo=ASIA_SHANGHAI),
        "plan_builder": fake_plan_builder(root),
        "artifact_plan_builder": fake_artifact_plan_builder,
        "artifact_writer": fake_artifact_writer,
        "artifact_validator": fake_artifact_validator,
        "post_checker": rolled_back_post_check,
    }
    kwargs.update(overrides)
    return kwargs


class N3BoundedWorkerOnceTests(unittest.TestCase):
    def test_db_subscription_summary_feeds_b1_contract_counts_when_artifact_missing(self):
        runner = load_runner()
        rows = [
            {"required_data_kind": "realtime_daily_snapshot", "asset_kind": "stock", "object_count": 1833},
            {"required_data_kind": "realtime_daily_snapshot", "asset_kind": "index", "object_count": 9},
            {"required_data_kind": "realtime_daily_snapshot", "asset_kind": "board", "object_count": 127},
            {"required_data_kind": "minute_bar_1m", "asset_kind": "stock", "object_count": 120},
            {"required_data_kind": "minute_bar_1m", "asset_kind": "board", "object_count": 17},
        ]
        summary = runner.build_db_subscription_summary_from_count_rows(rows, SUBSCRIPTION_RUN_ID)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = make_plan(root)
            captured = {}

            def capture_writer(artifact_plan, *, allow_overwrite=False):
                captured["plan"] = artifact_plan
                return {"status": "written", "artifact_count": len(artifact_plan["stage_run_ids"])}

            child_runner = ScriptedChildRunner(plan, [ChildResult(2)])
            result = runner.run_n3_bounded_worker_once(
                **base_kwargs(
                    root,
                    execute=True,
                    user_confirmed=True,
                    artifact_plan_builder=None,
                    artifact_writer=capture_writer,
                    subscription_summary_fetcher=lambda **_kwargs: summary,
                    child_runner=child_runner,
                )
            )

        b1_contract = json.loads(captured["plan"]["artifact_payloads"]["B1"]["execute_contract_json"])
        self.assertEqual(result["result"], "BLOCKED")
        self.assertEqual(b1_contract["expected_asset_counts"]["stock"]["subscription_count"], 1833)
        self.assertEqual(b1_contract["expected_asset_counts"]["index"]["subscription_count"], 9)
        self.assertEqual(b1_contract["expected_asset_counts"]["board"]["subscription_count"], 127)
        self.assertEqual(b1_contract["expected_row_count"], 1969)

    def test_missing_artifact_and_empty_db_subscription_rows_fail_closed_before_child(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = make_plan(root)
            writer_calls = []

            def missing_subscription_fetcher(**_kwargs):
                return runner.build_db_subscription_summary_from_count_rows([], SUBSCRIPTION_RUN_ID)

            def writer_spy(artifact_plan, *, allow_overwrite=False):
                writer_calls.append(artifact_plan)
                return {"status": "written", "artifact_count": 0}

            child_runner = ScriptedChildRunner(plan, [ChildResult(0)])
            result = runner.run_n3_bounded_worker_once(
                **base_kwargs(
                    root,
                    execute=True,
                    user_confirmed=True,
                    artifact_plan_builder=None,
                    artifact_writer=writer_spy,
                    subscription_summary_fetcher=missing_subscription_fetcher,
                    child_runner=child_runner,
                )
            )

        self.assertEqual(result["result"], "BLOCKED")
        self.assertIn("subscription rows missing", result["stop_reason"])
        self.assertEqual(writer_calls, [])
        self.assertEqual(child_runner.calls, [])

    def test_child_failure_status_and_manifest_include_child_diagnostics(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = make_plan(root)
            child_runner = ScriptedChildRunner(
                plan,
                [ChildResult(1, stdout="before\nstdout-tail", stderr="before\nstderr-tail")],
            )
            result = runner.run_n3_bounded_worker_once(
                **base_kwargs(
                    root,
                    execute=True,
                    user_confirmed=True,
                    child_runner=child_runner,
                    post_checker=unresolved_post_check,
                )
            )
            status = json.loads((root / "status.json").read_text(encoding="utf-8"))
            manifest = json.loads((root / "rollback_manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(result["result"], "COMMIT_UNKNOWN")
        diagnostics = result["child_diagnostics"]
        self.assertEqual(diagnostics, status["child_diagnostics"])
        self.assertEqual(diagnostics, manifest["child_diagnostics"])
        self.assertEqual(len(diagnostics), 1)
        diagnostic = diagnostics[0]
        self.assertEqual(diagnostic["stage"], "B1")
        self.assertEqual(diagnostic["returncode"], 1)
        self.assertIn("scripts/run_realtime_daily_snapshot_once.py", diagnostic["argv"])
        self.assertTrue(diagnostic["stdout_tail"].endswith("stdout-tail"))
        self.assertTrue(diagnostic["stderr_tail"].endswith("stderr-tail"))
        self.assertEqual(diagnostic["report_path"], plan["child_steps"][0]["json_report_path"])
        self.assertFalse(diagnostic["report_exists"])

    def test_plan_only_does_not_start_child(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = make_plan(root)
            child_runner = ScriptedChildRunner(plan, [ChildResult(0)])
            result = runner.run_n3_bounded_worker_once(**base_kwargs(root, child_runner=child_runner))

        self.assertEqual(result["result"], "NOOP")
        self.assertEqual(result["stop_reason"], "plan_only")
        self.assertFalse(result["child_invoked"])
        self.assertEqual(child_runner.calls, [])

    def test_execute_requires_user_confirmed_before_child(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = make_plan(root)
            child_runner = ScriptedChildRunner(plan, [ChildResult(0)])
            result = runner.run_n3_bounded_worker_once(**base_kwargs(root, execute=True, user_confirmed=False, child_runner=child_runner))

        self.assertEqual(result["result"], "BLOCKED")
        self.assertEqual(result["stop_reason"], "missing_user_confirmed")
        self.assertEqual(child_runner.calls, [])

    def test_lineage_missing_blocks_before_child(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = make_plan(root)
            child_runner = ScriptedChildRunner(plan, [ChildResult(0)])
            result = runner.run_n3_bounded_worker_once(**base_kwargs(root, execute=True, user_confirmed=True, source_condition_run_id="", child_runner=child_runner))

        self.assertEqual(result["result"], "BLOCKED")
        self.assertEqual(result["stop_reason"], "lineage_invalid")
        self.assertEqual(child_runner.calls, [])

    def test_auto_latest_fallback_lineage_is_rejected(self):
        runner = load_runner()
        with self.assertRaises(ValueError):
            runner.build_explicit_lineage(
                for_trade_date=TRADE_DATE,
                source_condition_run_id="latest",
                source_subscription_run_id=SUBSCRIPTION_RUN_ID,
                previous_day_preload_run_id=PRELOAD_RUN_ID,
            )
        parser = runner.build_arg_parser()
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(["--auto-resolve-lineage"])

    def test_singleton_conflict_returns_noop(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            lock_path = runner.build_phase1_realtime_chain_lock_path(root, TRADE_DATE)
            plan = make_plan(root)
            child_runner = ScriptedChildRunner(plan, [ChildResult(0)])
            with runner.acquire_global_chain_lock(lock_path, metadata={"owner": "test"}):
                result = runner.run_n3_bounded_worker_once(**base_kwargs(root, execute=True, user_confirmed=True, child_runner=child_runner))

            saved = json.loads((root / "status.json").read_text(encoding="utf-8"))

        self.assertEqual(result["result"], "NOOP")
        self.assertEqual(result["stop_reason"], "singleton_lock_held")
        self.assertFalse(result["child_invoked"])
        self.assertEqual(saved["result"], "NOOP")
        self.assertEqual(child_runner.calls, [])

    def test_stop_before_b1_returns_noop(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            stop_file = root / "stop"
            stop_file.write_text("stop", encoding="utf-8")
            plan = make_plan(root)
            child_runner = ScriptedChildRunner(plan, [ChildResult(0)])
            result = runner.run_n3_bounded_worker_once(**base_kwargs(root, execute=True, user_confirmed=True, stop_file=stop_file, child_runner=child_runner))

        self.assertEqual(result["result"], "NOOP")
        self.assertEqual(result["stop_reason"], "stop_file_present")
        self.assertEqual(result["completed_stages"], [])
        self.assertEqual(child_runner.calls, [])

    def test_deadline_before_b1_returns_blocked(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = make_plan(root)
            child_runner = ScriptedChildRunner(plan, [ChildResult(0)])
            result = runner.run_n3_bounded_worker_once(
                **base_kwargs(
                    root,
                    execute=True,
                    user_confirmed=True,
                    max_runtime_seconds=0,
                    child_runner=child_runner,
                )
            )

        self.assertEqual(result["result"], "BLOCKED")
        self.assertEqual(result["stop_reason"], "deadline_exhausted_before_B1")
        self.assertEqual(child_runner.calls, [])

    def test_deadline_before_b1_ignores_pnl_in_artifact_paths(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "pnl_artifacts"
            root.mkdir()
            plan = make_plan(root)
            child_runner = ScriptedChildRunner(plan, [ChildResult(0)])
            result = runner.run_n3_bounded_worker_once(
                **base_kwargs(
                    root,
                    execute=True,
                    user_confirmed=True,
                    max_runtime_seconds=0,
                    child_runner=child_runner,
                )
            )

        self.assertEqual(result["result"], "BLOCKED")
        self.assertEqual(result["stop_reason"], "deadline_exhausted_before_B1")
        self.assertNotIn("forbidden_command_marker:pnl", result["stop_reason"])
        self.assertEqual(child_runner.calls, [])

    def test_stop_after_b1_returns_partial(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            stop_file = root / "stop"
            plan = make_plan(root)
            child_runner = ScriptedChildRunner(plan, [ChildResult(0)], stop_file=stop_file, stop_after_stage="B1")
            result = runner.run_n3_bounded_worker_once(**base_kwargs(root, execute=True, user_confirmed=True, stop_file=stop_file, child_runner=child_runner))
            manifest = json.loads((root / "rollback_manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(result["result"], "PARTIAL")
        self.assertEqual(result["completed_stages"], ["B1"])
        self.assertEqual(result["pending_stages"], ["C1", "B2"])
        self.assertFalse(result["n4_consumption_allowed"])
        self.assertEqual(list(manifest["stage_rollback_sql"].keys()), ["B1"])

    def test_stop_after_c1_returns_partial(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            stop_file = root / "stop"
            plan = make_plan(root)
            child_runner = ScriptedChildRunner(plan, [ChildResult(0), ChildResult(0)], stop_file=stop_file, stop_after_stage="C1")
            result = runner.run_n3_bounded_worker_once(**base_kwargs(root, execute=True, user_confirmed=True, stop_file=stop_file, child_runner=child_runner))

        self.assertEqual(result["result"], "PARTIAL")
        self.assertEqual(result["completed_stages"], ["B1", "C1"])
        self.assertEqual(result["pending_stages"], ["B2"])

    def test_deadline_after_b1_returns_partial(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = make_plan(root)
            child_runner = ScriptedChildRunner(plan, [ChildResult(0)])
            remaining = iter([10.0, 10.0, 0.0])
            result = runner.run_n3_bounded_worker_once(
                **base_kwargs(
                    root,
                    execute=True,
                    user_confirmed=True,
                    child_runner=child_runner,
                    remaining_deadline_seconds_fn=lambda deadline: next(remaining),
                )
            )

        self.assertEqual(result["result"], "PARTIAL")
        self.assertEqual(result["partial_reason"], "deadline_exhausted_before_C1")
        self.assertEqual(result["completed_stages"], ["B1"])

    def test_child_timeouts_return_unknown_after_timeout(self):
        runner = load_runner()
        for stage_index, stage in enumerate(["B1", "C1", "B2"]):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                plan = make_plan(root)
                sequence = [ChildResult(0)] * stage_index + [ChildResult(returncode=-15, timed_out=True, result="UNKNOWN_AFTER_TIMEOUT")]
                child_runner = ScriptedChildRunner(plan, sequence)
                result = runner.run_n3_bounded_worker_once(
                    **base_kwargs(root, execute=True, user_confirmed=True, child_runner=child_runner, post_checker=unresolved_post_check)
                )
                self.assertEqual(result["result"], "UNKNOWN_AFTER_TIMEOUT")
                self.assertTrue(result["requires_post_check"])

    def test_previous_stage_success_next_controlled_blocked_returns_partial(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = make_plan(root)
            child_runner = ScriptedChildRunner(plan, [ChildResult(0), ChildResult(2)])
            result = runner.run_n3_bounded_worker_once(**base_kwargs(root, execute=True, user_confirmed=True, child_runner=child_runner))

        self.assertEqual(result["result"], "PARTIAL")
        self.assertEqual(result["completed_stages"], ["B1"])
        self.assertEqual(result["pending_stages"], ["C1", "B2"])

    def test_child_exit_1_with_rolled_back_post_check_returns_crashed(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = make_plan(root)
            child_runner = ScriptedChildRunner(plan, [ChildResult(1)])
            result = runner.run_n3_bounded_worker_once(**base_kwargs(root, execute=True, user_confirmed=True, child_runner=child_runner))

        self.assertEqual(result["result"], "CRASHED")
        self.assertEqual(result["stop_reason"], "child_technical_failure_B1")

    def test_report_missing_illegal_or_mismatched_run_id_fail_closed(self):
        runner = load_runner()
        cases = [
            ("missing", {}),
            ("illegal", {"bad_report_stage": "B1"}),
            ("mismatch", {"mismatched_stage": "B1"}),
        ]
        for expected_reason, runner_kwargs in cases:
            with self.subTest(expected_reason=expected_reason), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                plan = make_plan(root)
                child_runner = ScriptedChildRunner(plan, [ChildResult(0)], **runner_kwargs)
                if expected_reason == "missing":
                    child_runner = lambda argv, timeout_seconds=None, cwd=None, env=None: {
                        "returncode": 0,
                        "timed_out": False,
                        "result": "PASS",
                        "requires_post_check": False,
                        "stdout": "",
                        "stderr": "",
                    }
                result = runner.run_n3_bounded_worker_once(
                    **base_kwargs(root, execute=True, user_confirmed=True, child_runner=child_runner, post_checker=unresolved_post_check)
                )
                self.assertEqual(result["result"], "COMMIT_UNKNOWN")
                self.assertIn(expected_reason, result["stop_reason"])

    def test_completed_stage_missing_rollback_sql_is_crashed(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = make_plan(root)
            child_runner = ScriptedChildRunner(plan, [ChildResult(0)], missing_rollback_stage="B1")
            result = runner.run_n3_bounded_worker_once(
                **base_kwargs(root, execute=True, user_confirmed=True, child_runner=child_runner, post_checker=committed_post_check)
            )

        self.assertEqual(result["result"], "CRASHED")
        self.assertEqual(result["stop_reason"], "artifact_contract_corruption_B1")

    def test_pass_records_projection_alias(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = make_plan(root)
            child_runner = ScriptedChildRunner(plan, [ChildResult(0), ChildResult(0), ChildResult(0)])
            result = runner.run_n3_bounded_worker_once(**base_kwargs(root, execute=True, user_confirmed=True, child_runner=child_runner))

        self.assertEqual(result["result"], "PASS")
        self.assertEqual(result["output_run_ids"]["projection_run_id"], "projection_run_1")
        self.assertEqual(result["output_run_ids"]["source_metric_run_id"], "projection_run_1")
        self.assertEqual(result["output_run_id"], "projection_run_1")

    def test_shared_chain_lock_path_contains_no_layer_name(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = runner.build_phase1_realtime_chain_lock_path(Path(tmpdir), TRADE_DATE)
        self.assertIn("v3_phase1_realtime_chain_", path.name)
        self.assertNotIn("n3", path.name.lower())
        self.assertNotIn("n4", path.name.lower())
        self.assertNotIn("n5", path.name.lower())

    def test_forbidden_child_command_is_rejected_before_child(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = make_plan(root, forbidden=True)
            child_runner = ScriptedChildRunner(plan, [ChildResult(0)])
            result = runner.run_n3_bounded_worker_once(
                **base_kwargs(root, execute=True, user_confirmed=True, plan_builder=fake_plan_builder(root, forbidden=True), child_runner=child_runner)
            )

        self.assertEqual(result["result"], "BLOCKED")
        self.assertIn("forbidden_command", result["stop_reason"])
        self.assertEqual(child_runner.calls, [])

    def test_status_and_manifest_use_atomic_writer(self):
        runner = load_runner()
        calls = []

        def atomic_writer(path, payload):
            calls.append((Path(path).name, payload["result"]))
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(json.dumps(payload), encoding="utf-8")

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = make_plan(root)
            child_runner = ScriptedChildRunner(plan, [ChildResult(0), ChildResult(0), ChildResult(0)])
            result = runner.run_n3_bounded_worker_once(
                **base_kwargs(root, execute=True, user_confirmed=True, child_runner=child_runner, atomic_writer=atomic_writer)
            )

        self.assertEqual(result["result"], "PASS")
        self.assertEqual(calls, [("status.json", "PASS"), ("rollback_manifest.json", "PASS")])

    def test_main_returns_bounded_exit_code(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with redirect_stdout(StringIO()):
                rc = runner.main(
                    [
                        "--for-trade-date",
                        TRADE_DATE,
                        "--source-condition-run-id",
                        SOURCE_CONDITION_RUN_ID,
                        "--source-subscription-run-id",
                        SUBSCRIPTION_RUN_ID,
                        "--previous-day-preload-run-id",
                        PRELOAD_RUN_ID,
                        "--status-json",
                        str(root / "status.json"),
                        "--rollback-manifest-json",
                        str(root / "manifest.json"),
                        "--docs-root",
                        str(root / "docs"),
                        "--sql-root",
                        str(root / "sql"),
                        "--json",
                    ],
                    plan_builder=fake_plan_builder(root),
                    artifact_plan_builder=fake_artifact_plan_builder,
                    artifact_writer=fake_artifact_writer,
                    artifact_validator=fake_artifact_validator,
                    child_runner=ScriptedChildRunner(make_plan(root), [ChildResult(0)]),
                )

        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
