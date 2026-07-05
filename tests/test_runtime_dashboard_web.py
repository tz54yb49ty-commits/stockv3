import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from ashare_v3.runtime_control.artifacts import detect_stage_artifact
from ashare_v3.web.runtime_dashboard import build_dashboard_payload, create_app


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def write_json(docs_dir: Path, filename: str, payload: dict[str, object]) -> None:
    (docs_dir / filename).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def populate_runtime_artifacts(docs_dir: Path) -> None:
    write_json(
        docs_dir,
        "N1_trade_calendar_20260527_patch_preflight.json",
        {
            "result": "PREFLIGHT_PASS",
            "trade_date": "20260527",
            "quality": {"items": []},
            "patch": {"source_batch_id": "trade_calendar_20260527_patch_v1"},
            "rollback_sql_path": "sql/N1_trade_calendar_20260527_patch_rollback.sql",
        },
    )
    write_json(
        docs_dir,
        "N2_condition_layer_20260526_final_execute_report.json",
        {
            "for_trade_date": "20260527",
            "execute_run_id": "condition_layer_20260526_source_20260526_v1",
            "preflight": {"quality_summary": {"p0_count": 0, "p1_count": 0, "p2_count": 0}},
            "actual_row_counts": {
                "stock_condition_pool": 4291,
                "index_condition_pool": 19,
                "board_condition_pool": 264,
            },
        },
    )
    write_json(
        docs_dir,
        "N3_subscription_20260527_execute_report.json",
        {
            "for_trade_date": "20260527",
            "market_data_run_id": "market_data_subscription_20260527_condition_layer_20260526_source_20260526_v1",
            "post_execute": {
                "market_data_run_row": {
                    "status": "passed",
                    "p0_count": 0,
                    "p1_count": 0,
                    "p2_count": 0,
                }
            },
            "write_result": {"subscription_rows_written": 6543, "pull_plan_rows_written": 9},
        },
    )
    write_json(
        docs_dir,
        "N3_A1_previous_day_minute_preload_execute_report.json",
        {
            "for_trade_date": "20260527",
            "preload_run_id": "previous_day_minute_preload_20260527_from_20260526_subscription",
            "post_execute": {
                "preload_run_row": {
                    "status": "passed",
                    "p0_count": 0,
                    "p1_count": 1,
                    "p2_count": 0,
                }
            },
            "write_result": {"minute_rows_written": 521040, "quality_item_rows_written": 12},
        },
    )
    write_json(
        docs_dir,
        "N3_B1_realtime_daily_snapshot_execute_report.json",
        {
            "for_trade_date": "20260527",
            "snapshot_run_id": "realtime_snapshot_20260527_subscription",
            "source_run_id": "market_data_subscription_20260527_condition_layer_20260526_source_20260526_v1",
            "post_execute": {
                "snapshot_run_row": {
                    "status": "passed",
                    "p0_count": 0,
                    "p1_count": 1,
                    "p2_count": 0,
                }
            },
            "write_result": {"snapshot_rows_written": 2181, "event_outbox_rows_written": 0},
        },
    )


def populate_action_confirmation_20260602_artifacts(docs_dir: Path) -> None:
    write_json(
        docs_dir,
        "runtime_action_confirmation_chain_20260602_closure.json",
        {
            "result": "CHAIN_CLOSURE_PASS",
            "for_trade_date": "20260602",
            "stage_results": {
                "n6_shadow_projection": {
                    "status": "passed",
                    "user_projection_run_id": (
                        "user_projection_shadow_20260602_1105__"
                        "action_consumer_action_confirmation_metric_execute_20260602_1105__"
                        "trigger_action_confirmation_metric_execute_20260602_1105__"
                        "condition_layer_20260601_source_20260601_v1"
                    ),
                    "rows": {
                        "user_projection_run": 1,
                        "user_signal_projection": 5,
                        "user_signal_card": 5,
                        "user_notification_queue": 5,
                    },
                    "quality": {"p0_count": 0, "p1_count": 5, "p2_count": 2},
                    "rollback_sql_path": "sql/N6_projection_business_rollback.sql",
                }
            },
        },
    )
    write_json(
        docs_dir,
        "N2_condition_layer_20260601_to_20260602_execute_report.json",
        {
            "for_trade_date": "20260602",
            "execute_run_id": "condition_layer_20260601_source_20260601_v1",
            "postcheck": {"run_status": "passed_active"},
            "actual_row_counts": {
                "stock_condition_display_basis": 1976,
                "index_condition_display_basis": 83,
                "board_condition_display_basis": 428,
            },
            "rollback_sql_path": "sql/N2_condition_layer_20260601_to_20260602_rollback.sql",
        },
    )
    write_json(
        docs_dir,
        "N3_subscription_20260602_execute_report.json",
        {
            "for_trade_date": "20260602",
            "market_data_run_id": "market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1",
            "post_execute": {
                "market_data_run_row": {
                    "status": "passed",
                    "p0_count": 0,
                    "p1_count": 0,
                    "p2_count": 0,
                }
            },
            "write_result": {"subscription_rows_written": 4425, "pull_plan_rows_written": 9},
            "rollback_sql_path": "sql/N3_subscription_20260602_rollback.sql",
        },
    )
    write_json(
        docs_dir,
        "N3_A1_previous_day_minute_20260602_execute_report.json",
        {
            "for_trade_date": "20260602",
            "preload_run_id": "previous_day_minute_preload_20260602_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1",
            "post_execute": {
                "preload_run_row": {
                    "status": "passed",
                    "p0_count": 0,
                    "p1_count": 0,
                    "p2_count": 0,
                }
            },
            "write_result": {"minute_rows_written": 232560, "preload_status_rows_written": 969},
            "rollback_sql_path": "sql/N3_A1_previous_day_minute_20260602_rollback.sql",
        },
    )
    write_json(
        docs_dir,
        "N3_B1_realtime_snapshot_20260602_live3_outbox_execute_report.json",
        {
            "for_trade_date": "20260602",
            "snapshot_run_id": "realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1",
            "post_execute": {
                "snapshot_run_row": {
                    "status": "passed",
                    "p0_count": 0,
                    "p1_count": 0,
                    "p2_count": 0,
                }
            },
            "write_result": {"snapshot_rows_written": 2487, "event_outbox_rows_written": 2487},
            "rollback_sql_path": "sql/N3_B1_realtime_snapshot_20260602_live3_outbox_rollback.sql",
        },
    )
    write_json(
        docs_dir,
        "N3_C1_today_minute_bar_1m_20260602_until_1105_execute_report.json",
        {
            "for_trade_date": "20260602",
            "today_minute_run_id": "today_minute_bar_1m_20260602_until_1105__market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1",
            "quality": {"p0_count": 0, "p1_count": 0, "p2_count": 0},
            "write_result": {"minute_rows_written": 92055, "quality_item_rows_written": 8},
            "rollback_sql_path": "sql/N3_C1_today_minute_bar_1m_20260602_until_1105_rollback.sql",
        },
    )
    write_json(
        docs_dir,
        "N3_action_confirmation_projection_writer_execute_report.json",
        {
            "for_trade_date": "20260602",
            "projection_run_id": "action_confirmation_projection_metric_20260602_1105__realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1",
            "result": "EXECUTED",
            "quality": {"p0_count": 0, "p1_count": 0, "p2_count": 0},
            "write_result": {"rows_written": {"stock": 765, "index": 54, "board": 150, "total": 969}},
            "rollback": {"rollback_sql_path": "sql/N3_action_confirmation_projection_metric_business_rollback.sql"},
        },
    )
    write_json(
        docs_dir,
        "N4_action_confirmation_metric_business_execute_report.json",
        {
            "for_trade_date": "20260602",
            "execute_run_id": "trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1",
            "result": "EXECUTED",
            "quality": {"p0_count": 0, "p1_count": 1, "p2_count": 0},
            "write_counts": {
                "common_trigger_run": 1,
                "common_trigger_state": 5941,
                "common_trigger_match": 5941,
                "common_event_outbox": 5941,
                "TriggerMatched": 6,
                "TriggerPendingMarketData": 5935,
            },
            "rollback_sql_path": "sql/N4_action_confirmation_metric_business_execute_rollback.sql",
        },
    )
    write_json(
        docs_dir,
        "N5_20260602_action_confirmation_metric_execute_report.json",
        {
            "for_trade_date": "20260602",
            "action_run_id": (
                "action_consumer_action_confirmation_metric_execute_20260602_1105__"
                "trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1"
            ),
            "result": "EXECUTED",
            "quality": {"p0_count": 0, "p1_count": 0, "p2_count": 0},
            "inserted_counts": {
                "common_action_run": 1,
                "common_action_quality_item": 5935,
                "stock_action_fact": 1,
                "index_action_fact": 4,
                "board_action_fact": 0,
                "common_action_event": 5,
                "common_event_outbox": 5,
            },
            "output_event_plan_summary": {
                "by_event_type": {
                    "ActionExecuted": 4,
                    "ActionBlocked": 1,
                    "ActionEligible": 0,
                    "ActionSkipped": 0,
                }
            },
            "rollback_plan": {"rollback_sql_path": "sql/N5_20260602_action_confirmation_metric_execute_rollback.sql"},
        },
    )


class RuntimeDashboardWebTest(unittest.TestCase):
    def test_runtime_index_redirects_to_default_trade_date(self) -> None:
        with TemporaryDirectory() as tmp:
            client = TestClient(create_app(default_trade_date="20260527", docs_dir=Path(tmp)))

            response = client.get("/runtime/", follow_redirects=False)

        self.assertEqual(response.status_code, 307)
        self.assertEqual(response.headers["location"], "/runtime/20260527")

    def test_runtime_dashboard_page_is_read_only_and_shows_core_sections(self) -> None:
        with TemporaryDirectory() as tmp:
            docs_dir = Path(tmp)
            populate_runtime_artifacts(docs_dir)
            client = TestClient(create_app(default_trade_date="20260527", docs_dir=docs_dir))

            response = client.get("/runtime/20260527")

        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertIn("Runtime Dashboard", html)
        self.assertIn("Pipeline Summary", html)
        self.assertIn("Stage Timeline", html)
        self.assertIn("Quality Summary", html)
        self.assertIn("Manual Gate", html)
        self.assertIn("Command Registry", html)
        self.assertIn("Rollback Registry", html)
        self.assertIn("PASS", html)
        self.assertIn("READY", html)
        self.assertIn("WAIT_MANUAL_CONFIRM", html)
        self.assertIn("b1_realtime_snapshot_fact_only", html)
        self.assertIn("realtime_snapshot_20260527_subscription", html)
        self.assertIn("snapshot_rows_written", html)
        self.assertIn("P0", html)
        self.assertIn("P1", html)
        self.assertIn("P2", html)
        self.assertIn("sql/N3_B1_realtime_snapshot_20260527_rollback.sql", html)
        self.assertIn("scripts/run_realtime_daily_snapshot_once.py", html)
        self.assertNotIn("<form", html)
        self.assertNotIn('method="post"', html)
        self.assertNotIn("执行 Pipeline", html)
        self.assertNotIn("Run Pipeline", html)

    def test_runtime_dashboard_api_returns_registry_timeline_and_quality(self) -> None:
        with TemporaryDirectory() as tmp:
            docs_dir = Path(tmp)
            populate_runtime_artifacts(docs_dir)
            client = TestClient(create_app(default_trade_date="20260527", docs_dir=docs_dir))

            response = client.get("/api/runtime/20260527/dashboard")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["pipeline"]["layer_role"], "runtime_control")
        self.assertEqual(payload["pipeline"]["trade_date"], "20260527")
        self.assertFalse(payload["pipeline"]["side_effects"]["executes_commands"])
        self.assertFalse(payload["pipeline"]["side_effects"]["executes_rollback"])
        self.assertFalse(payload["pipeline"]["side_effects"]["starts_worker"])
        self.assertEqual(len(payload["timeline"]), 7)
        self.assertEqual(payload["quality_summary"]["p0_count"], 0)
        self.assertEqual(payload["quality_summary"]["p1_count"], 2)
        self.assertEqual(payload["quality_summary"]["p2_count"], 0)
        manual_stage_ids = [stage["stage_id"] for stage in payload["manual_gate"]["stages"]]
        self.assertIn("n1_official_daily", manual_stage_ids)
        b1_stage = next(stage for stage in payload["stages"] if stage["stage_id"] == "b1_realtime_snapshot_fact_only")
        self.assertEqual(b1_stage["status"], "PASS")
        self.assertEqual(b1_stage["artifact_status"], "PASS")
        self.assertEqual(b1_stage["quality"]["p0_count"], 0)
        self.assertEqual(b1_stage["run_id"], "realtime_snapshot_20260527_subscription")
        self.assertEqual(b1_stage["rows_summary"]["snapshot_rows_written"], 2181)
        self.assertEqual(b1_stage["report_path"], "docs/N3_B1_realtime_daily_snapshot_execute_report.json")
        self.assertIn("--no-outbox", b1_stage["execute_command"])
        a1_stage = next(stage for stage in payload["stages"] if stage["stage_id"] == "a1_previous_day_preload")
        self.assertEqual(a1_stage["status"], "PASS")
        self.assertEqual(a1_stage["quality"]["p1_count"], 1)
        subscription_stage = next(stage for stage in payload["stages"] if stage["stage_id"] == "n3_subscription")
        self.assertEqual(subscription_stage["status"], "PASS")
        self.assertEqual(subscription_stage["rows_summary"]["subscription_rows_written"], 6543)
        calendar_stage = next(stage for stage in payload["stages"] if stage["stage_id"] == "calendar")
        self.assertEqual(calendar_stage["status"], "READY")
        missing_stage = next(stage for stage in payload["stages"] if stage["stage_id"] == "n1_official_daily")
        self.assertEqual(missing_stage["artifact_status"], "NOT_RUN")
        self.assertEqual(missing_stage["status"], "WAIT_MANUAL_CONFIRM")
        self.assertEqual(
            payload["rollback_registry"]["b1_realtime_snapshot_fact_only"]["rollback_sql_path"],
            "sql/N3_B1_realtime_snapshot_20260527_rollback.sql",
        )

    def test_runtime_dashboard_api_returns_action_confirmation_timeline_for_20260602(self) -> None:
        with TemporaryDirectory() as tmp:
            docs_dir = Path(tmp)
            populate_action_confirmation_20260602_artifacts(docs_dir)
            client = TestClient(create_app(default_trade_date="20260527", docs_dir=docs_dir))

            response = client.get("/api/runtime/20260602/dashboard")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["pipeline"]["pipeline_name"], "action_confirmation_runtime_v0_2")
        self.assertEqual(payload["pipeline"]["trade_date"], "20260602")
        self.assertEqual(len(payload["timeline"]), 9)
        self.assertEqual(
            [stage["stage_id"] for stage in payload["stages"]],
            [
                "n2_condition_layer_active",
                "n3_subscription",
                "n3_a1_previous_day_preload",
                "n3_b1_live3_snapshot",
                "n3_c1_today_minute",
                "n3_action_confirmation_projection",
                "n4_action_confirmation_metric_execute",
                "n5_action_confirmation_metric_execute",
                "n6_shadow_projection",
            ],
        )
        self.assertTrue(all(stage["status"] == "PASS" for stage in payload["stages"]))
        self.assertFalse(payload["boundaries"]["executes_commands"])
        self.assertFalse(payload["boundaries"]["consumes_outbox"])
        self.assertFalse(payload["boundaries"]["starts_worker"])

        n2_stage = next(stage for stage in payload["stages"] if stage["stage_id"] == "n2_condition_layer_active")
        self.assertEqual(n2_stage["run_id"], "condition_layer_20260601_source_20260601_v1")
        self.assertEqual(n2_stage["artifact_rollback_path"], "sql/N2_condition_layer_20260601_to_20260602_rollback.sql")

        n5_stage = next(stage for stage in payload["stages"] if stage["stage_id"] == "n5_action_confirmation_metric_execute")
        self.assertEqual(n5_stage["rows_summary"]["ActionExecuted"], 4)
        self.assertEqual(n5_stage["rows_summary"]["ActionBlocked"], 1)
        self.assertIn("ActionExecuted=4", n5_stage["rows_summary_text"])
        self.assertEqual(n5_stage["artifact_rollback_path"], "sql/N5_20260602_action_confirmation_metric_execute_rollback.sql")

        n6_stage = next(stage for stage in payload["stages"] if stage["stage_id"] == "n6_shadow_projection")
        self.assertEqual(n6_stage["rows_summary"]["user_signal_projection"], 5)
        self.assertEqual(n6_stage["rows_summary"]["user_signal_card"], 5)
        self.assertEqual(n6_stage["rows_summary"]["user_notification_queue"], 5)
        self.assertEqual(n6_stage["quality"]["p1_count"], 5)
        self.assertEqual(n6_stage["quality"]["p2_count"], 2)
        self.assertEqual(n6_stage["artifact_rollback_path"], "sql/N6_projection_business_rollback.sql")

        rollback_paths = {
            stage["stage_id"]: stage["rollback"]["rollback_sql_path"]
            for stage in payload["stages"]
        }
        self.assertEqual(rollback_paths["n3_subscription"], "sql/N3_subscription_20260602_rollback.sql")
        self.assertEqual(
            rollback_paths["n3_action_confirmation_projection"],
            "sql/N3_action_confirmation_projection_metric_business_rollback.sql",
        )
        self.assertEqual(
            rollback_paths["n4_action_confirmation_metric_execute"],
            "sql/N4_action_confirmation_metric_business_execute_rollback.sql",
        )

    def test_action_confirmation_dashboard_page_is_read_only_and_shows_pending_outbox(self) -> None:
        with TemporaryDirectory() as tmp:
            docs_dir = Path(tmp)
            populate_action_confirmation_20260602_artifacts(docs_dir)
            client = TestClient(create_app(default_trade_date="20260527", docs_dir=docs_dir))

            response = client.get("/runtime/20260602")

        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertIn("action_confirmation_runtime_v0_2", html)
        self.assertIn("n3_action_confirmation_projection", html)
        self.assertIn("n6_shadow_projection", html)
        self.assertIn("ActionExecuted=4", html)
        self.assertIn("ActionBlocked=1", html)
        self.assertIn("user_signal_projection=5", html)
        self.assertIn("sql/N6_projection_business_rollback.sql", html)
        self.assertNotIn("<form", html)
        self.assertNotIn('method="post"', html)
        self.assertNotIn("Run Pipeline", html)

    def test_runtime_dashboard_cli_json_matches_web_api_payload(self) -> None:
        with TemporaryDirectory() as tmp:
            docs_dir = Path(tmp)
            populate_action_confirmation_20260602_artifacts(docs_dir)
            expected = build_dashboard_payload(trade_date="20260602", docs_dir=docs_dir)

            env = dict(os.environ)
            env["PYTHONPATH"] = f"src{os.pathsep}{env.get('PYTHONPATH', '')}"
            output = subprocess.check_output(
                [
                    sys.executable,
                    "scripts/plan_runtime_pipeline_dashboard.py",
                    "--trade-date",
                    "20260602",
                    "--json",
                    "--docs-dir",
                    str(docs_dir),
                ],
                cwd=PROJECT_ROOT,
                env=env,
                text=True,
            )

        actual = json.loads(output)
        actual["pipeline"]["created_at"] = expected["pipeline"]["created_at"]
        self.assertEqual(actual, expected)

    def test_action_confirmation_detector_prefers_n5_summary_over_large_report(self) -> None:
        with TemporaryDirectory() as tmp:
            docs_dir = Path(tmp)
            write_json(
                docs_dir,
                "N5_20260602_action_confirmation_metric_execute_summary.json",
                {
                    "for_trade_date": "20260602",
                    "action_run_id": (
                        "action_consumer_action_confirmation_metric_execute_20260602_1105__"
                        "trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1"
                    ),
                    "result": "EXECUTED",
                    "quality": {"p0_count": 0, "p1_count": 0, "p2_count": 0},
                    "inserted_counts": {
                        "common_action_run": 1,
                        "common_action_quality_item": 5935,
                        "stock_action_fact": 1,
                        "index_action_fact": 4,
                        "board_action_fact": 0,
                        "common_action_event": 5,
                        "common_event_outbox": 5,
                    },
                    "output_event_plan_summary": {
                        "by_event_type": {
                            "ActionExecuted": 4,
                            "ActionBlocked": 1,
                            "ActionEligible": 0,
                            "ActionSkipped": 0,
                        }
                    },
                    "rollback_plan": {
                        "rollback_sql_path": "sql/N5_20260602_action_confirmation_metric_execute_rollback.sql"
                    },
                },
            )
            write_json(
                docs_dir,
                "N5_20260602_action_confirmation_metric_execute_report.json",
                {
                    "for_trade_date": "20260602",
                    "action_run_id": "wrong_raw_report_should_not_be_used",
                    "result": "EXECUTED",
                    "quality": {"p0_count": 1, "p1_count": 0, "p2_count": 0},
                    "output_event_plan_summary": {"by_event_type": {"ActionExecuted": 999}},
                },
            )

            detection = detect_stage_artifact(
                stage_id="n5_action_confirmation_metric_execute",
                trade_date="20260602",
                docs_dir=docs_dir,
            )

        self.assertIsNotNone(detection)
        assert detection is not None
        self.assertEqual(detection.report_path, "docs/N5_20260602_action_confirmation_metric_execute_summary.json")
        self.assertEqual(detection.run_id, "action_consumer_action_confirmation_metric_execute_20260602_1105__trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1")
        self.assertEqual(detection.quality, {"p0_count": 0, "p1_count": 0, "p2_count": 0})
        self.assertEqual(detection.rows_summary["ActionExecuted"], 4)
        self.assertEqual(detection.rows_summary["ActionBlocked"], 1)

    def test_artifact_detector_handles_missing_and_b1_execute_report(self) -> None:
        with TemporaryDirectory() as tmp:
            docs_dir = Path(tmp)
            self.assertIsNone(
                detect_stage_artifact(
                    stage_id="b1_realtime_snapshot_fact_only",
                    trade_date="20260527",
                    docs_dir=docs_dir,
                )
            )
            write_json(
                docs_dir,
                "N3_B1_realtime_daily_snapshot_execute_report.json",
                {
                    "for_trade_date": "20260527",
                    "snapshot_run_id": "realtime_snapshot_20260527_subscription",
                    "post_execute": {
                        "snapshot_run_row": {
                            "status": "passed",
                            "p0_count": 0,
                            "p1_count": 0,
                            "p2_count": 0,
                        }
                    },
                    "write_result": {"snapshot_rows_written": 2181},
                },
            )

            detection = detect_stage_artifact(
                stage_id="b1_realtime_snapshot_fact_only",
                trade_date="20260527",
                docs_dir=docs_dir,
            )

        self.assertIsNotNone(detection)
        assert detection is not None
        self.assertEqual(detection.status, "PASS")
        self.assertEqual(detection.run_id, "realtime_snapshot_20260527_subscription")
        self.assertEqual(detection.quality, {"p0_count": 0, "p1_count": 0, "p2_count": 0})
        self.assertEqual(detection.rows_summary["snapshot_rows_written"], 2181)

    def test_runtime_dashboard_has_no_mutating_routes_or_execution_boundaries(self) -> None:
        with TemporaryDirectory() as tmp:
            app = create_app(default_trade_date="20260527", docs_dir=Path(tmp))
            methods = {
                method
                for route in app.routes
                for method in getattr(route, "methods", set())
            }

        self.assertFalse({"POST", "PUT", "DELETE", "PATCH"} & methods)
        client = TestClient(app)
        payload = client.get("/api/runtime/20260527/dashboard").json()
        self.assertFalse(payload["boundaries"]["executes_commands"])
        self.assertFalse(payload["boundaries"]["consumes_outbox"])
        self.assertFalse(payload["boundaries"]["starts_worker"])


if __name__ == "__main__":
    unittest.main()
