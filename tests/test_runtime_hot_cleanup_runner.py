import json
from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import scripts.run_runtime_hot_keep5_cleanup_once as keep5_runner
from scripts.run_runtime_dirty_hot_keep2_cleanup_once import (
    is_success_result,
    run_runtime_dirty_hot_keep2_cleanup_once,
)
from scripts.run_runtime_hot_keep5_cleanup_once import (
    cleanup_local_runtime_artifacts,
    run_runtime_hot_keep5_cleanup_once,
)
from ashare_v3.ingestion.runtime_hot_cleanup import DIRECT_DELETE_NO_ARCHIVE_CONFIRM_TOKEN, KEEP5_CONFIRM_TOKEN


class RuntimeHotCleanupRunnerTest(unittest.TestCase):
    def test_process_detectors_tolerate_non_utf8_ps_output(self) -> None:
        ps_output = b"\n".join(
            (
                b"101 00:01 S other other --label=bad-\xff-argv",
                (
                    b"102 00:01 S python3 python3 "
                    b"scripts/run_v3_runtime_archive_keep5_daily_once.py --label=bad-\xfe-argv"
                ),
                (
                    b"103 00:01 S python3 python3 "
                    b"scripts/run_n4_intraday_proof_discovery_poll_once.py --label=bad-\xfd-argv"
                ),
            )
        )
        with patch.object(keep5_runner.subprocess, "check_output", side_effect=[ps_output, ps_output]):
            archive_processes = keep5_runner.detect_active_archive_processes()
            runtime_writer_processes = keep5_runner.detect_active_runtime_writer_processes()

        self.assertEqual([row["pid"] for row in archive_processes], [102])
        self.assertEqual([row["pid"] for row in runtime_writer_processes], [103])
        encoded = json.dumps(
            {"archive": archive_processes, "runtime_writer": runtime_writer_processes},
            ensure_ascii=False,
        ).encode("utf-8")
        self.assertIn("\ufffd".encode("utf-8"), encoded)

    def test_runtime_writer_detector_ignores_only_readonly_research_bridge(self) -> None:
        ps_output = b"\n".join(
            (
                (
                    b"201 01:00 S Python Python /tmp/scripts/"
                    b"run_n6_ai_research_bridge.py --expected-manifest-sha256 abc"
                ),
                (
                    b"202 00:08 S Python Python /tmp/scripts/"
                    b"run_n6_ai_public_snapshot_once.py --execute"
                ),
                (
                    b"203 00:08 S Python Python /tmp/scripts/"
                    b"run_n6_b_track_signal_projection_poller_once.py --execute"
                ),
            )
        )
        with patch.object(keep5_runner.subprocess, "check_output", return_value=ps_output):
            processes = keep5_runner.detect_active_runtime_writer_processes()

        self.assertEqual([row["pid"] for row in processes], [202, 203])

    def test_runtime_writer_detector_ignores_exact_n6_only_writers(self) -> None:
        ps_output = b"\n".join(
            (
                b"301 00:01 R Python Python /release/scripts/run_n6_virtual_executor_once.py --execute",
                b"302 00:01 R Python Python /release/scripts/run_n6_virtual_stop_loss_once.py --execute",
                b"303 00:01 R Python Python /release/scripts/run_n6_virtual_quote_once.py --scheduled --execute",
                b"304 00:01 R Python Python /release/scripts/run_n6_unknown_writer_once.py --execute",
                b"305 00:01 R Python Python /release/scripts/run_n3_writer_once.py --execute",
                b"306 00:01 R Python Python /release/scripts/run_n4_writer_once.py --execute",
                b"307 00:01 R Python Python /release/scripts/run_n5_writer_once.py --execute",
            )
        )
        with patch.object(keep5_runner.subprocess, "check_output", return_value=ps_output):
            processes = keep5_runner.detect_active_runtime_writer_processes()

        self.assertEqual([row["pid"] for row in processes], [304, 305, 306, 307])

    def test_archive_required_runner_process_inspection_failure_is_fail_closed(self) -> None:
        def raise_process_error() -> list[dict[str, object]]:
            raise OSError("sensitive process argv must not be persisted")

        with tempfile.TemporaryDirectory() as tmp:
            report = run_runtime_hot_keep5_cleanup_once(
                report_dir=Path(tmp) / "reports",
                runtime_writer_process_detector=raise_process_error,
            )
            saved_text = Path(report["docs_report_path"]).read_text(encoding="utf-8")

        self.assertEqual(report["result"], "BLOCKED_PROCESS_INSPECTION_FAILED")
        self.assertEqual(report["failed_detector"], "runtime_writer_process")
        self.assertEqual(report["blockers"], ["process_inspection_failed"])
        self.assertFalse(report["cleanup_executed"])
        self.assertFalse(report["database_written"])
        self.assertEqual(report["deleted_total_rows"], 0)
        self.assertNotIn("sensitive process argv", saved_text)
        self.assertFalse(any(bool(value) for value in report["side_effects"].values()))

    @unittest.skip("superseded by archive-required v2 runner")
    def test_process_inspection_failure_is_persisted_fail_closed(self) -> None:
        for failed_detector in ("archive_process", "runtime_writer_process"):
            with self.subTest(failed_detector=failed_detector), tempfile.TemporaryDirectory() as tmp:
                counter_calls: list[str] = []
                deleter_calls: list[str] = []

                def raise_process_error() -> list[dict[str, object]]:
                    raise OSError("sensitive process argv must not be persisted")

                archive_detector = raise_process_error if failed_detector == "archive_process" else lambda: []
                runtime_writer_detector = (
                    raise_process_error if failed_detector == "runtime_writer_process" else lambda: []
                )
                with patch.object(keep5_runner, "cleanup_local_runtime_artifacts") as local_cleanup:
                    report = run_runtime_hot_keep5_cleanup_once(
                        report_dir=Path(tmp) / "reports",
                        local_artifact_project_root=Path(tmp),
                        archive_root=Path(tmp) / "archive",
                        direct_delete_no_archive=True,
                        execute=True,
                        confirm_token=DIRECT_DELETE_NO_ARCHIVE_CONFIRM_TOKEN,
                        trade_dates=["20260708", "20260709", "20260710", "20260713", "20260714", "20260715"],
                        archive_process_detector=archive_detector,
                        runtime_writer_process_detector=runtime_writer_detector,
                        table_counter=lambda spec, _trade_date: counter_calls.append(spec.table) or 1,
                        table_deleter=lambda spec, _trade_date: deleter_calls.append(spec.table) or 1,
                    )

                saved_path = Path(report["docs_report_path"])
                saved_text = saved_path.read_text(encoding="utf-8")
                saved = json.loads(saved_text)
                self.assertEqual(report["result"], "BLOCKED_PROCESS_INSPECTION_FAILED")
                self.assertEqual(report["failed_stage"], "process_inspection")
                self.assertEqual(report["failed_detector"], failed_detector)
                self.assertEqual(report["error_type"], "OSError")
                self.assertEqual(report["blockers"], ["process_inspection_failed"])
                self.assertFalse(report["cleanup_success"])
                self.assertFalse(report["cleanup_executed"])
                self.assertFalse(report["cleanup_complete"])
                self.assertFalse(report["database_written"])
                self.assertEqual(report["deleted_total_rows"], 0)
                self.assertEqual(report["local_file_cleanup"]["result"], "BLOCKED_LOCAL_FILE_CLEANUP")
                self.assertIn("process_inspection_failed", report["local_file_cleanup"]["blockers"])
                self.assertEqual(counter_calls, [])
                self.assertEqual(deleter_calls, [])
                local_cleanup.assert_not_called()
                self.assertEqual(saved["result"], "BLOCKED_PROCESS_INSPECTION_FAILED")
                self.assertNotIn("error_message", saved)
                self.assertNotIn("sensitive process argv", saved_text)
                self.assertFalse(any(bool(value) for value in saved["side_effects"].values()))

    def test_default_run_writes_plan_only_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = run_runtime_dirty_hot_keep2_cleanup_once(
                report_dir=Path(tmp) / "docs",
                trade_dates=["20260612", "20260701", "20260702"],
                table_counter=lambda _spec, trade_date: 1 if trade_date == "20260612" else 0,
            )

            saved = json.loads(Path(report["docs_report_path"]).read_text(encoding="utf-8"))

        self.assertEqual(report["result"], "DIRTY_HOT_KEEP2_CLEANUP_PLAN_PASS")
        self.assertFalse(report["execute"])
        self.assertFalse(report["cleanup_executed"])
        self.assertEqual(report["retained_trade_dates"], ["20260701", "20260702"])
        self.assertEqual(saved["cleanup_trade_dates"], ["20260612"])
        self.assertFalse(report["side_effects"]["writes_database"])

    def test_execute_requires_confirm_token_before_deleter(self) -> None:
        calls: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            report = run_runtime_dirty_hot_keep2_cleanup_once(
                report_dir=Path(tmp) / "docs",
                execute=True,
                confirm_token="WRONG",
                trade_dates=["20260612", "20260701", "20260702"],
                table_counter=lambda _spec, _trade_date: 1,
                table_deleter=lambda spec, _trade_date: calls.append(spec.table) or 1,
            )

        self.assertEqual(report["result"], "BLOCKED_CONFIRM_TOKEN_REQUIRED")
        self.assertEqual(calls, [])
        self.assertFalse(report["cleanup_executed"])
        self.assertFalse(report["side_effects"]["writes_database"])

    def test_blocked_plan_not_pass_is_not_success_result(self) -> None:
        self.assertTrue(is_success_result("DIRTY_HOT_KEEP2_CLEANUP_PLAN_PASS"))
        self.assertTrue(is_success_result("DIRTY_HOT_KEEP2_CLEANUP_EXECUTE_PASS"))
        self.assertFalse(is_success_result("BLOCKED_PLAN_NOT_PASS"))

    @unittest.skip("superseded by calendar-authoritative v2 plan contract")
    def test_keep5_runner_requires_verified_archive_before_cleanup_plan_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = run_runtime_hot_keep5_cleanup_once(
                report_dir=Path(tmp) / "docs",
                archive_root=Path(tmp) / "archive",
                trade_dates=["20260612", "20260615", "20260616", "20260617", "20260618", "20260619"],
                table_counter=lambda _spec, _trade_date: 1,
            )

            saved = json.loads(Path(report["docs_report_path"]).read_text(encoding="utf-8"))

        self.assertEqual(report["result"], "DIRTY_HOT_KEEP2_CLEANUP_PLAN_BLOCKED")
        self.assertTrue(report["archive_required"])
        self.assertEqual(report["retained_trade_dates"], ["20260615", "20260616", "20260617", "20260618", "20260619"])
        self.assertIn("archive_manifest_not_verified:20260612", report["blockers"])
        self.assertFalse(saved["side_effects"]["writes_database"])

    @unittest.skip("direct-delete-no-archive is permanently rejected")
    def test_keep5_direct_delete_no_archive_plan_skips_manifest_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = run_runtime_hot_keep5_cleanup_once(
                report_dir=Path(tmp) / "docs",
                archive_root=Path(tmp) / "archive",
                direct_delete_no_archive=True,
                trade_dates=["20260612", "20260615", "20260616", "20260617", "20260618", "20260619"],
                table_counter=lambda _spec, trade_date: 1 if trade_date == "20260612" else 0,
                runtime_writer_process_detector=lambda: [],
                fk_closure_auditor=lambda **_kwargs: {
                    "missing_child_scope_count": 0,
                    "order_bad_count": 0,
                    "missing_child_scope": [],
                    "order_bad": [],
                },
            )

        self.assertEqual(report["result"], "DIRTY_HOT_KEEP2_CLEANUP_PLAN_PASS")
        self.assertFalse(report["archive_required"])
        self.assertTrue(report["direct_delete_no_archive"])
        self.assertEqual(report["confirm_token_required"], DIRECT_DELETE_NO_ARCHIVE_CONFIRM_TOKEN)
        self.assertEqual(report["cleanup_trade_dates"], ["20260612"])

    @unittest.skip("direct-delete-no-archive is permanently rejected")
    def test_keep5_direct_delete_no_archive_execute_requires_direct_confirm_token(self) -> None:
        deleted: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            report = run_runtime_hot_keep5_cleanup_once(
                report_dir=Path(tmp) / "docs",
                archive_root=Path(tmp) / "archive",
                direct_delete_no_archive=True,
                execute=True,
                confirm_token=KEEP5_CONFIRM_TOKEN,
                trade_dates=["20260612", "20260615", "20260616", "20260617", "20260618", "20260619"],
                table_counter=lambda _spec, trade_date: 1 if trade_date == "20260612" else 0,
                table_deleter=lambda spec, _trade_date: deleted.append(spec.table) or 1,
                runtime_writer_process_detector=lambda: [],
                fk_closure_auditor=lambda **_kwargs: {
                    "missing_child_scope_count": 0,
                    "order_bad_count": 0,
                    "missing_child_scope": [],
                    "order_bad": [],
                },
            )

        self.assertEqual(report["result"], "BLOCKED_CONFIRM_TOKEN_REQUIRED")
        self.assertEqual(deleted, [])
        self.assertFalse(report["cleanup_executed"])
        self.assertEqual(report["local_file_cleanup"]["result"], "BLOCKED_LOCAL_FILE_CLEANUP")
        self.assertIn("hot_row_cleanup_not_complete", report["local_file_cleanup"]["blockers"])

    @unittest.skip("direct-delete-no-archive is permanently rejected")
    def test_keep5_direct_delete_no_archive_blocks_active_archive_process(self) -> None:
        counter_calls: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            report = run_runtime_hot_keep5_cleanup_once(
                report_dir=Path(tmp) / "docs",
                archive_root=Path(tmp) / "archive",
                direct_delete_no_archive=True,
                trade_dates=["20260612", "20260615", "20260616", "20260617", "20260618", "20260619"],
                table_counter=lambda spec, trade_date: counter_calls.append(f"{trade_date}:{spec.table}") or 1,
                archive_process_detector=lambda: [{"pid": 60731, "command": "run_v3_runtime_archive_keep5_daily_once.py"}],
                runtime_writer_process_detector=lambda: [],
                fk_closure_auditor=lambda **_kwargs: {
                    "missing_child_scope_count": 0,
                    "order_bad_count": 0,
                    "missing_child_scope": [],
                    "order_bad": [],
                },
            )

        self.assertEqual(report["result"], "DIRTY_HOT_KEEP2_CLEANUP_PLAN_BLOCKED")
        self.assertIn("archive_process_conflict", report["blockers"])
        self.assertEqual(counter_calls, [])

    @unittest.skip("direct-delete-no-archive is permanently rejected")
    def test_keep5_direct_delete_no_archive_blocks_active_runtime_writer_before_plan(self) -> None:
        counter_calls: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            report = run_runtime_hot_keep5_cleanup_once(
                report_dir=Path(tmp) / "docs",
                archive_root=Path(tmp) / "archive",
                direct_delete_no_archive=True,
                trade_dates=["20260612", "20260615", "20260616", "20260617", "20260618", "20260619"],
                table_counter=lambda spec, trade_date: counter_calls.append(f"{trade_date}:{spec.table}") or 1,
                archive_process_detector=lambda: [],
                runtime_writer_process_detector=lambda: [{"pid": 60732, "command": "python3 scripts/run_n4_intraday_proof_discovery_poll_once.py"}],
                fk_closure_auditor=lambda **_kwargs: {
                    "missing_child_scope_count": 0,
                    "order_bad_count": 0,
                    "missing_child_scope": [],
                    "order_bad": [],
                },
            )

        self.assertEqual(report["result"], "BLOCKED_RUNTIME_WRITER_ACTIVE")
        self.assertEqual(report["active_runtime_writer_processes"][0]["pid"], 60732)
        self.assertEqual(counter_calls, [])
        self.assertFalse(report["cleanup_executed"])
        self.assertFalse(report["cleanup_success"])
        self.assertFalse(report["side_effects"]["writes_database"])

    @unittest.skip("direct-delete-no-archive is permanently rejected")
    def test_keep5_direct_delete_no_archive_can_skip_row_count_plan_for_fast_execute(self) -> None:
        counter_calls: list[str] = []
        deleted: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            report = run_runtime_hot_keep5_cleanup_once(
                report_dir=Path(tmp) / "docs",
                archive_root=Path(tmp) / "archive",
                direct_delete_no_archive=True,
                skip_row_count_plan=True,
                execute=True,
                confirm_token=DIRECT_DELETE_NO_ARCHIVE_CONFIRM_TOKEN,
                trade_dates=["20260612", "20260615", "20260616", "20260617", "20260618", "20260619"],
                table_counter=lambda spec, trade_date: counter_calls.append(f"{trade_date}:{spec.table}") or 1,
                table_deleter=lambda spec, _trade_date: deleted.append(spec.table) or 0,
                runtime_writer_process_detector=lambda: [],
                fk_closure_auditor=lambda **_kwargs: {
                    "missing_child_scope_count": 0,
                    "order_bad_count": 0,
                    "missing_child_scope": [],
                    "order_bad": [],
                },
            )

        self.assertEqual(report["result"], "DIRTY_HOT_KEEP2_CLEANUP_EXECUTE_PASS")
        self.assertEqual(counter_calls, [])
        self.assertTrue(deleted)
        self.assertTrue(report["row_count_plan_skipped"])

    @unittest.skip("direct-delete-no-archive is permanently rejected")
    def test_keep5_direct_delete_execute_report_contains_compact_table_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = run_runtime_hot_keep5_cleanup_once(
                report_dir=Path(tmp) / "docs",
                archive_root=Path(tmp) / "archive",
                direct_delete_no_archive=True,
                skip_row_count_plan=True,
                execute=True,
                confirm_token=DIRECT_DELETE_NO_ARCHIVE_CONFIRM_TOKEN,
                trade_dates=["20260612", "20260615", "20260616", "20260617", "20260618", "20260619"],
                archive_process_detector=lambda: [],
                runtime_writer_process_detector=lambda: [],
                table_deleter=lambda spec, _trade_date: 7 if spec.table == "common_market_data_run" else 0,
                fk_closure_auditor=lambda **_kwargs: {
                    "missing_child_scope_count": 0,
                    "order_bad_count": 0,
                    "missing_child_scope": [],
                    "order_bad": [],
                },
            )
            saved = json.loads(Path(report["docs_report_path"]).read_text(encoding="utf-8"))
            closeout = json.loads((Path(tmp) / "docs" / "keep5_cleanup_closeout.json").read_text(encoding="utf-8"))
            temporary_files = list((Path(tmp) / "docs").glob(".*.tmp"))

        self.assertEqual(report["result"], "DIRTY_HOT_KEEP2_CLEANUP_EXECUTE_PASS")
        self.assertTrue(report["cleanup_success"])
        self.assertIn("started_at", report)
        self.assertIn("finished_at", report)
        self.assertGreaterEqual(report["duration_ms"], 0)
        summary = [row for row in report["deleted_table_summary"] if row["table"] == "common_market_data_run"]
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["trade_date_count"], 1)
        self.assertEqual(summary[0]["deleted_rows"], 7)
        self.assertEqual(report["deleted_table_summary_count"], len(report["deleted_table_summary"]))
        self.assertEqual(report["retained_trade_dates_after"], ["20260615", "20260616", "20260617", "20260618", "20260619"])
        self.assertEqual(report["current_hot_trade_dates_after"], ["20260615", "20260616", "20260617", "20260618", "20260619"])
        self.assertEqual(saved["deleted_table_summary"], report["deleted_table_summary"])
        self.assertEqual(closeout["deleted_table_summary"], report["deleted_table_summary"])
        self.assertEqual(temporary_files, [])

    def test_local_file_execute_keeps_latest_five_dates_and_deletes_only_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dates = ["20260708", "20260709", "20260710", "20260713", "20260714", "20260715", "20260716"]
            for trade_date in dates:
                runtime_date = root / "docs/runtime" / trade_date
                (runtime_date / "n3_daily").mkdir(parents=True)
                (runtime_date / "n3_daily/payload.bin").write_bytes(b"n3-data")
                (runtime_date / "N4_daily_report.json").write_bytes(b"n4")
                (runtime_date / "n5_daily").mkdir()
                (runtime_date / "n5_daily/payload.json").write_bytes(b"n5")
                (root / "tmp").mkdir(exist_ok=True)
                (root / "tmp" / f"N3P_{trade_date}_1000_trigger_proof_contract.json").write_bytes(b"n3p")
                (root / "tmp" / f"N3_hint_{trade_date}_1001_midday_bridge_v1_contract.json").write_bytes(b"hint")
                (root / "tmp" / f"N4_{trade_date}_1002_ordinary_matcher_execute_report.json").write_bytes(b"n4-report")
                precheck = root / "tmp/N5_N3T_action_confirmation_fastlane_open_monitor_precheck" / trade_date
                precheck.mkdir(parents=True)
                (precheck / "status.json").write_bytes(b"n5-status")

            old_runtime = root / "docs/runtime/20260708"
            (old_runtime / "n2_keep.json").write_text("keep", encoding="utf-8")
            external = root / "outside.txt"
            external.write_text("outside", encoding="utf-8")
            (old_runtime / "n3_symlink").symlink_to(external)
            future = root / "docs/runtime/20260717/n3_future"
            future.mkdir(parents=True)
            (future / "payload.json").write_text("future", encoding="utf-8")
            invalid = root / "tmp/N3P_20290231_1000_trigger_proof_contract.json"
            invalid.write_text("invalid", encoding="utf-8")

            report = cleanup_local_runtime_artifacts(
                project_root=root,
                retained_trade_dates=dates[-5:],
                cleanup_trade_dates=dates[:-5],
                execute=True,
                direct_delete_no_archive=True,
                confirm_token=DIRECT_DELETE_NO_ARCHIVE_CONFIRM_TOKEN,
                current_date=date(2026, 7, 16),
            )

            self.assertEqual(report["result"], "LOCAL_FILE_KEEP5_EXECUTE_PASS")
            self.assertEqual(report["retained_trade_dates"], ["20260710", "20260713", "20260714", "20260715", "20260716"])
            self.assertEqual(report["cleanup_trade_dates"], ["20260708", "20260709"])
            self.assertFalse((old_runtime / "n3_daily").exists())
            self.assertFalse((old_runtime / "N4_daily_report.json").exists())
            self.assertFalse((old_runtime / "n5_daily").exists())
            self.assertFalse((root / "tmp/N3P_20260708_1000_trigger_proof_contract.json").exists())
            self.assertFalse((root / "tmp/N4_20260709_1002_ordinary_matcher_execute_report.json").exists())
            self.assertFalse((root / "tmp/N5_N3T_action_confirmation_fastlane_open_monitor_precheck/20260708").exists())
            self.assertTrue((root / "docs/runtime/20260710/n3_daily/payload.bin").exists())
            self.assertTrue((old_runtime / "n2_keep.json").exists())
            self.assertTrue((old_runtime / "n3_symlink").is_symlink())
            self.assertTrue(external.exists())
            self.assertTrue(future.exists())
            self.assertTrue(invalid.exists())
            self.assertGreater(report["deleted_file_count"], 0)
            self.assertGreater(report["deleted_directory_count"], 0)
            self.assertGreater(report["released_bytes"], 0)
            self.assertGreater(report["per_layer"]["n3"]["released_bytes"], 0)
            self.assertGreater(report["per_layer"]["n4"]["released_bytes"], 0)
            self.assertGreater(report["per_layer"]["n5"]["released_bytes"], 0)

    def test_local_file_dry_run_deletes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for trade_date in ("20260708", "20260709", "20260710", "20260713", "20260714", "20260715"):
                target = root / "docs/runtime" / trade_date / "n3_daily/payload.json"
                target.parent.mkdir(parents=True)
                target.write_text(trade_date, encoding="utf-8")

            report = cleanup_local_runtime_artifacts(
                project_root=root,
                retained_trade_dates=["20260709", "20260710", "20260713", "20260714", "20260715"],
                cleanup_trade_dates=["20260708"],
                current_date=date(2026, 7, 16),
            )

            self.assertEqual(report["result"], "LOCAL_FILE_KEEP5_DRY_RUN_PASS")
            self.assertEqual(report["cleanup_trade_dates"], ["20260708"])
            self.assertGreater(report["candidate_file_count"], 0)
            self.assertEqual(report["deleted_file_count"], 0)
            self.assertEqual(report["deleted_directory_count"], 0)
            self.assertEqual(report["released_bytes"], 0)
            self.assertTrue((root / "docs/runtime/20260708/n3_daily/payload.json").exists())

    def test_local_file_partition_uses_authoritative_trade_dates_not_weekend_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for trade_date in (
                "20260708",
                "20260709",
                "20260710",
                "20260711",
                "20260712",
                "20260713",
                "20260714",
                "20260715",
            ):
                target = root / "docs/runtime" / trade_date / "n3_daily/payload.json"
                target.parent.mkdir(parents=True)
                target.write_text(trade_date, encoding="utf-8")

            report = cleanup_local_runtime_artifacts(
                project_root=root,
                retained_trade_dates=["20260709", "20260710", "20260713", "20260714", "20260715"],
                cleanup_trade_dates=["20260708"],
                current_date=date(2026, 7, 16),
            )

        self.assertEqual(report["retained_trade_dates"], ["20260709", "20260710", "20260713", "20260714", "20260715"])
        self.assertEqual(report["cleanup_trade_dates"], ["20260708"])

    def test_local_artifact_discovery_rejects_symlink_inside_declared_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = root / "docs/runtime/20260708/n3_daily"
            runtime.mkdir(parents=True)
            target = root / "outside.json"
            target.write_text("outside", encoding="utf-8")
            (runtime / "escape.json").symlink_to(target)

            with self.assertRaisesRegex(ValueError, "local_artifact_discovery_symlink"):
                keep5_runner.discover_local_artifact_files(
                    project_root=root, current_date=date(2026, 7, 16)
                )

    @unittest.skip("superseded by DB/local independent v2 execution")
    def test_blocked_hot_row_cleanup_never_calls_local_file_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(keep5_runner, "cleanup_local_runtime_artifacts") as local_cleanup:
                report = run_runtime_hot_keep5_cleanup_once(
                    report_dir=Path(tmp) / "reports",
                    local_artifact_project_root=Path(tmp),
                    archive_root=Path(tmp) / "archive",
                    direct_delete_no_archive=True,
                    execute=True,
                    confirm_token=DIRECT_DELETE_NO_ARCHIVE_CONFIRM_TOKEN,
                    trade_dates=["20260708", "20260709", "20260710", "20260713", "20260714", "20260715"],
                    archive_process_detector=lambda: [],
                    runtime_writer_process_detector=lambda: [],
                    table_counter=lambda _spec, _trade_date: 1,
                    table_deleter=lambda _spec, _trade_date: 0,
                    fk_closure_auditor=lambda **_kwargs: {
                        "missing_child_scope_count": 1,
                        "order_bad_count": 0,
                        "missing_child_scope": [{"child_table": "blocked"}],
                        "order_bad": [],
                    },
                )

        self.assertEqual(report["result"], "BLOCKED_PLAN_NOT_PASS")
        local_cleanup.assert_not_called()
        self.assertEqual(report["local_file_cleanup"]["result"], "BLOCKED_LOCAL_FILE_CLEANUP")
        self.assertIn("hot_row_cleanup_not_complete", report["local_file_cleanup"]["blockers"])

    @unittest.skip("superseded by exact-file archive allowlist v2")
    def test_local_file_partial_makes_combined_execute_fail(self) -> None:
        local_partial = {
            "result": "LOCAL_FILE_KEEP5_EXECUTE_PARTIAL",
            "cleanup_executed": True,
            "errors": ["delete_failed"],
            "blockers": ["local_artifact_cleanup_errors"],
            "side_effects": {"cleanup_local_runtime_files": True},
        }
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(keep5_runner, "cleanup_local_runtime_artifacts", return_value=local_partial):
                report = run_runtime_hot_keep5_cleanup_once(
                    report_dir=Path(tmp) / "reports",
                    local_artifact_project_root=Path(tmp),
                    archive_root=Path(tmp) / "archive",
                    direct_delete_no_archive=True,
                    skip_row_count_plan=True,
                    execute=True,
                    confirm_token=DIRECT_DELETE_NO_ARCHIVE_CONFIRM_TOKEN,
                    trade_dates=["20260708", "20260709", "20260710", "20260713", "20260714", "20260715"],
                    archive_process_detector=lambda: [],
                    runtime_writer_process_detector=lambda: [],
                    table_deleter=lambda _spec, _trade_date: 0,
                    fk_closure_auditor=lambda **_kwargs: {
                        "missing_child_scope_count": 0,
                        "order_bad_count": 0,
                        "missing_child_scope": [],
                        "order_bad": [],
                    },
                )

        self.assertEqual(report["result"], "RUNTIME_HOT_KEEP5_CLEANUP_EXECUTE_PARTIAL")
        self.assertFalse(report["cleanup_success"])
        self.assertFalse(str(report["result"]).endswith("_PASS"))

    @unittest.skip("superseded by exact active-path v2 guard")
    def test_active_writer_blocks_local_file_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "docs/runtime/20260708/n3_daily/payload.json"
            target.parent.mkdir(parents=True)
            target.write_text("keep", encoding="utf-8")

            report = run_runtime_hot_keep5_cleanup_once(
                report_dir=root / "reports",
                local_artifact_project_root=root,
                archive_root=root / "archive",
                direct_delete_no_archive=True,
                execute=True,
                confirm_token=DIRECT_DELETE_NO_ARCHIVE_CONFIRM_TOKEN,
                trade_dates=["20260708", "20260709", "20260710", "20260713", "20260714", "20260715"],
                archive_process_detector=lambda: [],
                runtime_writer_process_detector=lambda: [{"pid": 77, "command": "python3 scripts/run_n3_writer.py"}],
            )

            self.assertEqual(report["local_file_cleanup"]["result"], "BLOCKED_LOCAL_FILE_CLEANUP")
            self.assertIn("runtime_writer_active", report["local_file_cleanup"]["blockers"])
            self.assertTrue(target.exists())

    @unittest.skip("superseded by verified-archive-required v2")
    def test_keep5_runner_executes_local_file_phase_with_existing_confirm_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trade_dates = ["20260708", "20260709", "20260710", "20260713", "20260714", "20260715"]
            for trade_date in trade_dates:
                target = root / "docs/runtime" / trade_date / "n3_daily/payload.json"
                target.parent.mkdir(parents=True)
                target.write_text(trade_date, encoding="utf-8")

            report = run_runtime_hot_keep5_cleanup_once(
                report_dir=root / "reports",
                local_artifact_project_root=root,
                local_artifact_current_date=date(2026, 7, 16),
                archive_root=root / "archive",
                direct_delete_no_archive=True,
                skip_row_count_plan=True,
                execute=True,
                confirm_token=DIRECT_DELETE_NO_ARCHIVE_CONFIRM_TOKEN,
                trade_dates=trade_dates,
                archive_process_detector=lambda: [],
                runtime_writer_process_detector=lambda: [],
                table_deleter=lambda _spec, _trade_date: 0,
                fk_closure_auditor=lambda **_kwargs: {
                    "missing_child_scope_count": 0,
                    "order_bad_count": 0,
                    "missing_child_scope": [],
                    "order_bad": [],
                },
            )

            self.assertEqual(report["result"], "DIRTY_HOT_KEEP2_CLEANUP_EXECUTE_PASS")
            self.assertEqual(report["local_file_cleanup"]["result"], "LOCAL_FILE_KEEP5_EXECUTE_PASS")
            self.assertFalse((root / "docs/runtime/20260708/n3_daily").exists())
            self.assertTrue((root / "docs/runtime/20260709/n3_daily/payload.json").exists())
            saved = json.loads((root / "reports/keep5_cleanup_status.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["local_file_cleanup"]["released_bytes"], len("20260708"))


if __name__ == "__main__":
    unittest.main()
