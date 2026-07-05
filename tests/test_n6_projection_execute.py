import copy
import json
import tempfile
import unittest
from pathlib import Path

from ashare_v3.user.projection_execute import (
    ALLOWED_WRITE_TABLES,
    CONTRACT_JSON_PATH,
    DEFAULT_PROJECTION_RUN_ID,
    PREFLIGHT_JSON_PATH,
    ROLLBACK_SQL_PATH,
    ProjectionExecuteSnapshot,
    run_projection_shadow_execute,
    validate_design_artifacts,
)
from test_n6_projection_plan import FakeProjectionRepository, default_snapshot, projection_event


class FakeExecuteRepository:
    def __init__(self, snapshot: ProjectionExecuteSnapshot) -> None:
        self.snapshot = snapshot
        self.fetch_calls = 0
        self.commit_calls = 0
        self.committed_plan = None

    def fetch_execute_snapshot(self, projection_run_id: str) -> ProjectionExecuteSnapshot:
        self.fetch_calls += 1
        return self.snapshot

    def commit_shadow_projection(self, plan):
        self.commit_calls += 1
        self.committed_plan = plan
        return {
            "committed": True,
            "write_counts": plan.write_counts,
            "write_tables": plan.write_tables,
            "n5_outbox_after": dict(plan.n5_outbox_before),
        }


class N6ProjectionExecuteTest(unittest.TestCase):
    def test_missing_execute_blocks_before_repository_read(self) -> None:
        repo = FakeExecuteRepository(default_execute_snapshot())

        report = run_projection_shadow_execute(
            repository=repo,
            execute=False,
            user_confirmed=True,
        )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("missing_execute_flag", report["blockers"])
        self.assertEqual(repo.fetch_calls, 0)
        self.assertEqual(repo.commit_calls, 0)

    def test_missing_user_confirmed_blocks_before_repository_read(self) -> None:
        repo = FakeExecuteRepository(default_execute_snapshot())

        report = run_projection_shadow_execute(
            repository=repo,
            execute=True,
            user_confirmed=False,
        )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("missing_user_confirmed", report["blockers"])
        self.assertEqual(repo.fetch_calls, 0)
        self.assertEqual(repo.commit_calls, 0)

    def test_baseline_nonzero_blocks(self) -> None:
        snapshot = default_execute_snapshot()
        snapshot.scoped_counts["user_signal_projection"] = 1
        repo = FakeExecuteRepository(snapshot)

        report = run_projection_shadow_execute(
            repository=repo,
            execute=True,
            user_confirmed=True,
        )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("projection_run_scoped_rows_not_zero:user_signal_projection", report["blockers"])
        self.assertEqual(repo.commit_calls, 0)

    def test_admin_missing_blocks(self) -> None:
        repo = FakeExecuteRepository(default_execute_snapshot(admin_missing=True))

        report = run_projection_shadow_execute(
            repository=repo,
            execute=True,
            user_confirmed=True,
        )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("missing_active_admin", report["blockers"])
        self.assertEqual(repo.commit_calls, 0)

    def test_admin_user_id_must_be_one(self) -> None:
        snapshot = default_execute_snapshot()
        snapshot.input_snapshot.admin.user_id = 2
        repo = FakeExecuteRepository(snapshot)

        report = run_projection_shadow_execute(
            repository=repo,
            execute=True,
            user_confirmed=True,
        )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("admin_user_id_not_1", report["blockers"])
        self.assertEqual(repo.commit_calls, 0)

    def test_n5_outbox_missing_blocks(self) -> None:
        snapshot = default_execute_snapshot()
        snapshot.input_snapshot.n5_outbox_counts = {}
        repo = FakeExecuteRepository(snapshot)

        report = run_projection_shadow_execute(
            repository=repo,
            execute=True,
            user_confirmed=True,
        )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("n5_outbox_count_mismatch_without_new_gate", report["blockers"])
        self.assertEqual(repo.commit_calls, 0)

    def test_p0_event_quality_blocks(self) -> None:
        snapshot = default_execute_snapshot()
        snapshot.input_snapshot.events[0].payload_json.pop("direction")
        repo = FakeExecuteRepository(snapshot)

        report = run_projection_shadow_execute(
            repository=repo,
            execute=True,
            user_confirmed=True,
        )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("required_payload_field_missing:direction", report["blockers"])
        self.assertEqual(repo.commit_calls, 0)

    def test_p1_missing_fields_are_allowed(self) -> None:
        repo = FakeExecuteRepository(default_execute_snapshot())

        report = run_projection_shadow_execute(
            repository=repo,
            execute=True,
            user_confirmed=True,
        )

        self.assertEqual(report["result"], "EXECUTED")
        self.assertEqual(report["preflight_result"], "PREFLIGHT_PASS")
        self.assertEqual(report["quality"]["p0_count"], 0)
        self.assertGreaterEqual(report["quality"]["p1_count"], 1)
        self.assertEqual(repo.commit_calls, 1)
        self.assertEqual(repo.committed_plan.projection_run_row["source_event_types"], ["ActionBlocked"])
        self.assertEqual(
            repo.committed_plan.projection_run_row["projection_contract_version"],
            "N6-canonical-user-projection-shadow-execute-v1",
        )

    def test_allowed_writes_only_and_no_n5_outbox_update(self) -> None:
        repo = FakeExecuteRepository(default_execute_snapshot())

        report = run_projection_shadow_execute(
            repository=repo,
            execute=True,
            user_confirmed=True,
        )

        self.assertEqual(set(repo.committed_plan.write_tables), set(ALLOWED_WRITE_TABLES))
        self.assertEqual(report["write_summary"]["write_tables"], list(ALLOWED_WRITE_TABLES))
        self.assertFalse(report["side_effects"]["updates_n5_outbox_status"])
        self.assertFalse(report["side_effects"]["n5_outbox_consumed"])
        self.assertFalse(report["side_effects"]["writes_n5_inbox_or_checkpoint"])
        self.assertEqual(report["n5_outbox_after"], report["n5_outbox_before"])

    def test_no_session_decision_sim_or_watchlist_writes(self) -> None:
        repo = FakeExecuteRepository(default_execute_snapshot())

        report = run_projection_shadow_execute(
            repository=repo,
            execute=True,
            user_confirmed=True,
        )

        self.assertFalse(report["side_effects"]["writes_user_session"])
        self.assertFalse(report["side_effects"]["writes_user_signal_decision"])
        self.assertFalse(report["side_effects"]["writes_user_sim_tables"])
        self.assertFalse(report["side_effects"]["writes_user_watchlist"])
        for forbidden in ["user_session", "user_signal_decision", "user_sim_order", "user_watchlist"]:
            self.assertNotIn(forbidden, repo.committed_plan.write_counts)

    def test_canonical_trace_columns_are_in_write_plan(self) -> None:
        repo = FakeExecuteRepository(default_execute_snapshot())

        report = run_projection_shadow_execute(
            repository=repo,
            execute=True,
            user_confirmed=True,
        )

        self.assertEqual(report["result"], "EXECUTED")
        projection_row = repo.committed_plan.projection_rows[0]
        card_row = repo.committed_plan.card_rows[0]
        notification_row = repo.committed_plan.notification_rows[0]

        for row in (projection_row, card_row, notification_row):
            self.assertEqual(row["source_action_event_type"], "ActionBlocked")
            self.assertEqual(row["action_state"], "blocked")
            self.assertEqual(row["condition_key"], "BUY:Y")
            self.assertEqual(row["original_condition_key"], "BUY:Y")
            self.assertEqual(row["projection_policy"], "blocked_unconfirmed_no_push_no_decision_no_sim_no_trade")
            self.assertIsInstance(row["trace_json"], dict)

        self.assertEqual(card_row["card_type"], "blocked")
        self.assertEqual(card_row["card_status"], "blocked")
        self.assertFalse(card_row["card_payload_json"]["decision_buttons"])
        self.assertFalse(card_row["card_payload_json"]["sim_allowed"])
        self.assertFalse(card_row["card_payload_json"]["real_trade_allowed"])
        self.assertEqual(notification_row["notification_source"], "n5_action_blocked")
        self.assertEqual(notification_row["queue_status"], "queued_only")
        self.assertFalse(notification_row["notification_payload_json"]["actual_push"])
        self.assertFalse(notification_row["notification_payload_json"]["voice_mobile_push"])

    def test_explicit_20260602_baseline_maps_action_executed_without_outbox_update(self) -> None:
        expected = {"ActionExecuted:pending": 4, "ActionBlocked:pending": 1}
        input_snapshot = default_snapshot(
            n5_outbox_counts=expected,
            events=[
                projection_event(
                    event_id="evt_executed_1",
                    event_type="ActionExecuted",
                    direction="sell",
                    signal_type="S_SELL",
                    action_mark="30m_shrink",
                ),
                projection_event(
                    event_id="evt_executed_2",
                    event_type="ActionExecuted",
                    direction="sell",
                    signal_type="S_SELL",
                    action_mark="30m_shrink",
                ),
                projection_event(
                    event_id="evt_executed_3",
                    event_type="ActionExecuted",
                    direction="sell",
                    signal_type="S_SELL",
                    action_mark="30m_shrink",
                ),
                projection_event(
                    event_id="evt_executed_4",
                    event_type="ActionExecuted",
                    direction="sell",
                    signal_type="S_SELL",
                    action_mark="30m_shrink",
                ),
                projection_event(event_id="evt_blocked_1", event_type="ActionBlocked", direction="buy", signal_type="B_BUY"),
            ],
        )
        snapshot = ProjectionExecuteSnapshot(
            input_snapshot=input_snapshot,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            scoped_counts={
                "user_projection_run": 0,
                "user_signal_projection": 0,
                "user_signal_card": 0,
                "user_notification_queue": 0,
            },
            linked_counts={
                "user_signal_decision": 0,
                "user_sim_order": 0,
                "user_sim_trade": 0,
                "user_sim_position": 0,
            },
        )
        repo = FakeExecuteRepository(snapshot)

        report = run_projection_shadow_execute(
            repository=repo,
            execute=True,
            user_confirmed=True,
            expected_n5_outbox_counts=expected,
        )

        self.assertEqual(report["result"], "EXECUTED")
        self.assertEqual(report["preflight_result"], "PREFLIGHT_PASS")
        self.assertEqual(report["quality"]["p0_count"], 0)
        self.assertEqual(report["event_summary"]["by_event_type"], {"ActionBlocked": 1, "ActionExecuted": 4})
        self.assertEqual(report["write_summary"]["write_counts"]["user_signal_projection"], 5)
        self.assertEqual(report["n5_outbox_after"], report["n5_outbox_before"])
        executed_card = next(row for row in repo.committed_plan.card_rows if row["source_event_id"] == "evt_executed_1")
        executed_queue = next(row for row in repo.committed_plan.notification_rows if row["source_event_id"] == "evt_executed_1")
        self.assertEqual(executed_card["card_status"], "action_confirmed")
        self.assertEqual(executed_card["action_state"], "executed")
        self.assertEqual(executed_card["action_mark"], "30m_shrink")
        self.assertEqual(executed_queue["notification_source"], "n5_action_executed")
        self.assertEqual(executed_queue["queue_status"], "queued_only")
        self.assertFalse(executed_queue["notification_payload_json"]["actual_push"])
        self.assertFalse(report["side_effects"]["n5_outbox_consumed"])
        self.assertFalse(report["side_effects"]["updates_n5_outbox_status"])

    def test_deferred_notification_policy_writes_projection_and_cards_without_queue(self) -> None:
        snapshot = default_execute_snapshot()
        event_count = len(snapshot.input_snapshot.events)
        repo = FakeExecuteRepository(snapshot)
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            contract_path = tmp / "contract.json"
            preflight_path = tmp / "preflight.json"
            contract_path.write_text(
                json.dumps(
                    {
                        "status": "ROLLBACK_ALIGNMENT_PASS",
                        "notification_queue_policy": "deferred",
                        "user_message_event_filter": {
                            "include_event_types": ["ActionEligible", "ActionBlocked", "ActionExecuted", "ActionSkipped"]
                        },
                        "planned_writes": {
                            "user_projection_run": 1,
                            "user_signal_projection": event_count,
                            "user_signal_card": event_count,
                            "user_notification_queue": 0,
                        },
                    }
                ),
                encoding="utf-8",
            )
            preflight_path.write_text(json.dumps({"status": "EXECUTE_FINAL_PREFLIGHT_PASS"}), encoding="utf-8")

            report = run_projection_shadow_execute(
                repository=repo,
                execute=True,
                user_confirmed=True,
                contract_json_path=str(contract_path),
                preflight_json_path=str(preflight_path),
            )

        self.assertEqual(report["result"], "EXECUTED")
        self.assertEqual(repo.commit_calls, 1)
        self.assertEqual(repo.committed_plan.write_counts["user_projection_run"], 1)
        self.assertEqual(repo.committed_plan.write_counts["user_signal_projection"], event_count)
        self.assertEqual(repo.committed_plan.write_counts["user_signal_card"], event_count)
        self.assertEqual(repo.committed_plan.write_counts["user_notification_queue"], 0)
        self.assertEqual(repo.committed_plan.notification_rows, [])
        self.assertNotIn("user_notification_queue", repo.committed_plan.write_tables)
        self.assertFalse(report["side_effects"]["actual_push"])
        self.assertFalse(report["side_effects"]["voice_mobile_push"])

    def test_deferred_notification_policy_blocks_if_contract_plans_queue_rows(self) -> None:
        repo = FakeExecuteRepository(default_execute_snapshot())
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            contract_path = tmp / "contract.json"
            preflight_path = tmp / "preflight.json"
            contract_path.write_text(
                json.dumps(
                    {
                        "status": "ROLLBACK_ALIGNMENT_PASS",
                        "notification_queue_policy": "deferred",
                        "user_message_event_filter": {
                            "include_event_types": ["ActionEligible", "ActionBlocked", "ActionExecuted", "ActionSkipped"]
                        },
                        "planned_writes": {"user_notification_queue": 1},
                    }
                ),
                encoding="utf-8",
            )
            preflight_path.write_text(json.dumps({"status": "EXECUTE_FINAL_PREFLIGHT_PASS"}), encoding="utf-8")

            report = run_projection_shadow_execute(
                repository=repo,
                execute=True,
                user_confirmed=True,
                contract_json_path=str(contract_path),
                preflight_json_path=str(preflight_path),
            )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("notification_queue_deferred_contract_plans_queue_rows", report["blockers"])
        self.assertEqual(repo.fetch_calls, 0)
        self.assertEqual(repo.commit_calls, 0)

    def test_deferred_no_queue_write_policy_writes_projection_and_cards_without_queue(self) -> None:
        snapshot = default_execute_snapshot()
        event_count = len(snapshot.input_snapshot.events)
        repo = FakeExecuteRepository(snapshot)
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            contract_path = tmp / "contract.json"
            preflight_path = tmp / "preflight.json"
            contract_path.write_text(
                json.dumps(
                    {
                        "status": "ROLLBACK_ALIGNMENT_PASS",
                        "notification_queue_policy": "deferred_no_queue_write",
                        "user_message_event_filter": {
                            "include_event_types": ["ActionEligible", "ActionBlocked", "ActionExecuted", "ActionSkipped"]
                        },
                        "planned_writes": {
                            "user_projection_run": 1,
                            "user_signal_projection": event_count,
                            "user_signal_card": event_count,
                            "user_notification_queue": 0,
                        },
                    }
                ),
                encoding="utf-8",
            )
            preflight_path.write_text(json.dumps({"status": "EXECUTE_FINAL_PREFLIGHT_PASS"}), encoding="utf-8")

            report = run_projection_shadow_execute(
                repository=repo,
                execute=True,
                user_confirmed=True,
                contract_json_path=str(contract_path),
                preflight_json_path=str(preflight_path),
            )

        self.assertEqual(report["result"], "EXECUTED")
        self.assertEqual(repo.commit_calls, 1)
        self.assertEqual(repo.committed_plan.write_counts["user_projection_run"], 1)
        self.assertEqual(repo.committed_plan.write_counts["user_signal_projection"], event_count)
        self.assertEqual(repo.committed_plan.write_counts["user_signal_card"], event_count)
        self.assertEqual(repo.committed_plan.write_counts["user_notification_queue"], 0)
        self.assertEqual(repo.committed_plan.notification_rows, [])
        self.assertNotIn("user_notification_queue", repo.committed_plan.write_tables)

    def test_deferred_no_queue_write_policy_blocks_if_contract_plans_queue_rows(self) -> None:
        repo = FakeExecuteRepository(default_execute_snapshot())
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            contract_path = tmp / "contract.json"
            preflight_path = tmp / "preflight.json"
            contract_path.write_text(
                json.dumps(
                    {
                        "status": "ROLLBACK_ALIGNMENT_PASS",
                        "notification_queue_policy": "deferred_no_queue_write",
                        "user_message_event_filter": {
                            "include_event_types": ["ActionEligible", "ActionBlocked", "ActionExecuted", "ActionSkipped"]
                        },
                        "planned_writes": {"user_notification_queue": 1},
                    }
                ),
                encoding="utf-8",
            )
            preflight_path.write_text(json.dumps({"status": "EXECUTE_FINAL_PREFLIGHT_PASS"}), encoding="utf-8")

            report = run_projection_shadow_execute(
                repository=repo,
                execute=True,
                user_confirmed=True,
                contract_json_path=str(contract_path),
                preflight_json_path=str(preflight_path),
            )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("notification_queue_deferred_contract_plans_queue_rows", report["blockers"])
        self.assertEqual(repo.fetch_calls, 0)
        self.assertEqual(repo.commit_calls, 0)

    def test_unknown_notification_queue_policy_blocks_before_repository_read(self) -> None:
        repo = FakeExecuteRepository(default_execute_snapshot())
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            contract_path = tmp / "contract.json"
            preflight_path = tmp / "preflight.json"
            contract_path.write_text(
                json.dumps(
                    {
                        "status": "ROLLBACK_ALIGNMENT_PASS",
                        "notification_queue_policy": "deferred_typo",
                        "user_message_event_filter": {
                            "include_event_types": ["ActionEligible", "ActionBlocked", "ActionExecuted", "ActionSkipped"]
                        },
                        "planned_writes": {"user_notification_queue": 0},
                    }
                ),
                encoding="utf-8",
            )
            preflight_path.write_text(json.dumps({"status": "EXECUTE_FINAL_PREFLIGHT_PASS"}), encoding="utf-8")

            report = run_projection_shadow_execute(
                repository=repo,
                execute=True,
                user_confirmed=True,
                contract_json_path=str(contract_path),
                preflight_json_path=str(preflight_path),
            )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("notification_queue_policy_not_allowed", report["blockers"])
        self.assertEqual(repo.fetch_calls, 0)
        self.assertEqual(repo.commit_calls, 0)

    def test_user_message_filter_action_blocked_only_commits_run_without_projection_card_or_queue(self) -> None:
        expected = {"ActionBlocked:pending": 836}
        snapshot = ProjectionExecuteSnapshot(
            input_snapshot=default_snapshot(
                n5_outbox_counts=expected,
                events=[
                    projection_event(event_id=f"evt_blocked_{idx}", event_type="ActionBlocked", direction="buy", signal_type="B_BUY")
                    for idx in range(3)
                ],
            ),
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            scoped_counts={
                "user_projection_run": 0,
                "user_signal_projection": 0,
                "user_signal_card": 0,
                "user_notification_queue": 0,
            },
            linked_counts={
                "user_signal_decision": 0,
                "user_sim_order": 0,
                "user_sim_trade": 0,
                "user_sim_position": 0,
            },
        )
        repo = FakeExecuteRepository(snapshot)
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            contract_path = tmp / "contract.json"
            preflight_path = tmp / "preflight.json"
            contract_path.write_text(
                json.dumps(
                    {
                        "result": "CONTRACT_PASS",
                        "notification_queue_policy": "deferred",
                        "user_message_event_filter": {
                            "include_event_types": ["ActionEligible", "ActionExecuted"],
                            "exclude_event_types": ["ActionBlocked", "ActionSkipped"],
                        },
                        "planned_writes": {
                            "user_projection_run": 1,
                            "user_signal_projection": 0,
                            "user_signal_card": 0,
                            "user_notification_queue": 0,
                        },
                    }
                ),
                encoding="utf-8",
            )
            preflight_path.write_text(json.dumps({"result": "PREFLIGHT_PASS"}), encoding="utf-8")

            report = run_projection_shadow_execute(
                repository=repo,
                execute=True,
                user_confirmed=True,
                expected_n5_outbox_counts=expected,
                contract_json_path=str(contract_path),
                preflight_json_path=str(preflight_path),
            )

        self.assertEqual(report["result"], "PROJECTION_PASS_ZERO_USER_MESSAGES")
        self.assertEqual(repo.commit_calls, 1)
        self.assertEqual(repo.committed_plan.write_counts["user_projection_run"], 1)
        self.assertEqual(repo.committed_plan.write_counts["user_signal_projection"], 0)
        self.assertEqual(repo.committed_plan.write_counts["user_signal_card"], 0)
        self.assertEqual(repo.committed_plan.write_counts["user_notification_queue"], 0)
        self.assertEqual(repo.committed_plan.projection_rows, [])
        self.assertEqual(repo.committed_plan.card_rows, [])
        self.assertEqual(repo.committed_plan.notification_rows, [])

    def test_user_message_filter_unknown_event_type_blocks_before_repository_read(self) -> None:
        repo = FakeExecuteRepository(default_execute_snapshot())
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            contract_path = tmp / "contract.json"
            preflight_path = tmp / "preflight.json"
            contract_path.write_text(
                json.dumps(
                    {
                        "result": "CONTRACT_PASS",
                        "notification_queue_policy": "deferred",
                        "user_message_event_filter": {"include_event_types": ["ActionFoo"]},
                    }
                ),
                encoding="utf-8",
            )
            preflight_path.write_text(json.dumps({"result": "PREFLIGHT_PASS"}), encoding="utf-8")

            report = run_projection_shadow_execute(
                repository=repo,
                execute=True,
                user_confirmed=True,
                contract_json_path=str(contract_path),
                preflight_json_path=str(preflight_path),
            )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("unsupported_user_message_event_filter", report["blockers"])
        self.assertEqual(repo.fetch_calls, 0)
        self.assertEqual(repo.commit_calls, 0)

    def test_user_message_filter_missing_blocks_before_repository_read(self) -> None:
        repo = FakeExecuteRepository(default_execute_snapshot())
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            contract_path = tmp / "contract.json"
            preflight_path = tmp / "preflight.json"
            contract_path.write_text(
                json.dumps(
                    {
                        "result": "CONTRACT_PASS",
                        "notification_queue_policy": "deferred",
                    }
                ),
                encoding="utf-8",
            )
            preflight_path.write_text(json.dumps({"result": "PREFLIGHT_PASS"}), encoding="utf-8")

            report = run_projection_shadow_execute(
                repository=repo,
                execute=True,
                user_confirmed=True,
                contract_json_path=str(contract_path),
                preflight_json_path=str(preflight_path),
            )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("missing_user_message_event_filter", report["blockers"])
        self.assertEqual(repo.fetch_calls, 0)
        self.assertEqual(repo.commit_calls, 0)

    def test_user_message_filter_keeps_source_expected_count_fail_closed(self) -> None:
        expected = {"ActionBlocked:pending": 836}
        snapshot = default_execute_snapshot()
        snapshot.input_snapshot.n5_outbox_counts = {"ActionBlocked:pending": 835}
        repo = FakeExecuteRepository(snapshot)
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            contract_path = tmp / "contract.json"
            preflight_path = tmp / "preflight.json"
            contract_path.write_text(
                json.dumps(
                    {
                        "result": "CONTRACT_PASS",
                        "notification_queue_policy": "deferred",
                        "user_message_event_filter": {"include_event_types": ["ActionEligible", "ActionExecuted"]},
                    }
                ),
                encoding="utf-8",
            )
            preflight_path.write_text(json.dumps({"result": "PREFLIGHT_PASS"}), encoding="utf-8")

            report = run_projection_shadow_execute(
                repository=repo,
                execute=True,
                user_confirmed=True,
                expected_n5_outbox_counts=expected,
                contract_json_path=str(contract_path),
                preflight_json_path=str(preflight_path),
            )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("n5_outbox_count_mismatch_without_new_gate", report["blockers"])
        self.assertEqual(repo.commit_calls, 0)

    def test_existing_session_and_sim_account_do_not_block_projection_execute(self) -> None:
        snapshot = default_execute_snapshot()
        snapshot.input_snapshot.table_counts["user_session"] = 28
        snapshot.input_snapshot.table_counts["user_sim_account"] = 3
        repo = FakeExecuteRepository(snapshot)

        report = run_projection_shadow_execute(
            repository=repo,
            execute=True,
            user_confirmed=True,
        )

        self.assertEqual(report["result"], "EXECUTED")
        self.assertNotIn("forbidden_n6_table_not_zero:user_session", report["blockers"])
        self.assertNotIn("forbidden_n6_table_not_zero:user_sim_account", report["blockers"])

    def test_rollback_sql_exists(self) -> None:
        self.assertEqual(ROLLBACK_SQL_PATH, "sql/N6_projection_business_rollback.sql")
        self.assertTrue(Path(ROLLBACK_SQL_PATH).exists())

    def test_rollback_sql_hard_fails_all_linked_refs_before_first_delete(self) -> None:
        sql = Path(ROLLBACK_SQL_PATH).read_text()
        normalized = sql.lower()
        first_delete = normalized.index("delete from user_notification_queue")
        guard_region = normalized[:first_delete]

        self.assertIn("raise exception", guard_region)
        self.assertIn("to_regclass", guard_region)
        required_guard_markers = [
            "user_signal_decision",
            "user_sim_order",
            "user_sim_trade",
            "user_sim_position",
            "user_voice_delivery",
            "user_voice_queue",
            "user_voice_delivery_log",
            "user_mobile_delivery",
            "user_mobile_queue",
            "user_device_ack",
            "user_notification_delivery",
            "user_position_projection",
            "user_position_state",
            "common_position_state",
            "common_position_event",
        ]
        for marker in required_guard_markers:
            with self.subTest(marker=marker):
                self.assertIn(marker, guard_region)

    def test_rollback_sql_delete_order_and_n5_boundary(self) -> None:
        sql = Path(ROLLBACK_SQL_PATH).read_text().lower()
        delete_order = [
            "delete from user_notification_queue",
            "delete from user_signal_card",
            "delete from user_signal_projection",
            "delete from user_projection_run",
        ]
        positions = [sql.index(statement) for statement in delete_order]
        self.assertEqual(positions, sorted(positions))

        forbidden_dml_targets = [
            "delete from common_event_outbox",
            "update common_event_outbox",
            "delete from common_action_",
            "update common_action_",
            "delete from common_trigger_",
            "update common_trigger_",
            "delete from common_position_",
            "update common_position_",
        ]
        for marker in forbidden_dml_targets:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, sql)

    def test_20260602_execute_final_artifact_statuses_are_accepted(self) -> None:
        errors = validate_design_artifacts(
            "docs/N6_20260602_action_confirmation_projection_contract.json",
            "docs/N6_20260602_action_confirmation_projection_preflight.json",
            ROLLBACK_SQL_PATH,
        )

        self.assertEqual(errors, [])

    def test_invalid_execute_artifact_statuses_still_block(self) -> None:
        repo = FakeExecuteRepository(default_execute_snapshot())
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            contract_path = tmp / "contract.json"
            preflight_path = tmp / "preflight.json"
            contract_path.write_text(json.dumps({"status": "NOPE"}), encoding="utf-8")
            preflight_path.write_text(json.dumps({"status": "NOPE"}), encoding="utf-8")

            errors = validate_design_artifacts(str(contract_path), str(preflight_path), ROLLBACK_SQL_PATH)

            report = run_projection_shadow_execute(
                repository=repo,
                execute=True,
                user_confirmed=True,
                contract_json_path=str(contract_path),
                preflight_json_path=str(preflight_path),
            )

        self.assertIn("missing_or_invalid_contract_json:status_not_allowed", errors)
        self.assertIn("missing_or_invalid_preflight_json:status_not_allowed", errors)
        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("missing_or_invalid_contract_json:status_not_allowed", report["blockers"])
        self.assertIn("missing_or_invalid_preflight_json:status_not_allowed", report["blockers"])
        self.assertEqual(repo.fetch_calls, 0)
        self.assertEqual(repo.commit_calls, 0)

    def test_default_contract_paths_are_canonical(self) -> None:
        self.assertEqual(CONTRACT_JSON_PATH, "docs/N6_canonical_projection_execute_contract.json")
        self.assertEqual(PREFLIGHT_JSON_PATH, "docs/N6_canonical_projection_execute_preflight.json")
        self.assertTrue(Path(CONTRACT_JSON_PATH).exists())
        self.assertTrue(Path(PREFLIGHT_JSON_PATH).exists())


def default_execute_snapshot(*, admin_missing: bool = False) -> ProjectionExecuteSnapshot:
    snapshot = copy.deepcopy(default_snapshot(admin=None, default_profile=None) if admin_missing else default_snapshot())
    return ProjectionExecuteSnapshot(
        input_snapshot=snapshot,
        projection_run_id=DEFAULT_PROJECTION_RUN_ID,
        scoped_counts={
            "user_projection_run": 0,
            "user_signal_projection": 0,
            "user_signal_card": 0,
            "user_notification_queue": 0,
        },
        linked_counts={
            "user_signal_decision": 0,
            "user_sim_order": 0,
            "user_sim_trade": 0,
            "user_sim_position": 0,
        },
    )


if __name__ == "__main__":
    unittest.main()
