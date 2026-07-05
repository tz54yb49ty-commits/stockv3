import json
import tempfile
import unittest
from pathlib import Path

from psycopg.types.json import Jsonb

from ashare_v3.user.delivery_execute import (
    ALLOWED_WRITE_TABLES,
    DEFAULT_DELIVERY_MATERIALIZATION_RUN_ID,
    DEFAULT_SOURCE_PROJECTION_RUN_ID,
    FORBIDDEN_PROVIDER_PAYLOAD_KEYS,
    TARGET_CHANNEL,
    TARGET_NOTIFICATION_SOURCE,
    TARGET_QUEUE_STATUS,
    DeliveryExecuteSnapshot,
    SourceNotificationRow,
    build_materialized_notification_row,
    build_sanitized_payload,
    jsonb_if_needed,
    run_delivery_materialization_execute,
    validate_delivery_artifacts,
)
from ashare_v3.user.delivery_provider import (
    DryRunProviderAdapter,
    NoopLocalPreviewAdapter,
    ProviderCapability,
    ProviderPolicyHooks,
    ProviderSendInput,
    RealProviderAdapterSkeleton,
    provider_payload_has_forbidden_keys,
    redact_provider_report,
)


class FakeDeliveryRepository:
    def __init__(self, snapshot: DeliveryExecuteSnapshot) -> None:
        self.snapshot = snapshot
        self.fetch_calls = 0
        self.commit_calls = 0
        self.committed_plan = None

    def fetch_delivery_snapshot(
        self,
        *,
        source_projection_run_id: str,
        delivery_materialization_run_id: str,
    ) -> DeliveryExecuteSnapshot:
        self.fetch_calls += 1
        self.snapshot.source_projection_run_id = source_projection_run_id
        self.snapshot.delivery_materialization_run_id = delivery_materialization_run_id
        return self.snapshot

    def commit_delivery_materialization(self, plan):
        self.commit_calls += 1
        self.committed_plan = plan
        return {
            "committed": True,
            "write_tables": plan.write_tables,
            "write_counts": plan.write_counts,
        }


class N6DeliveryExecuteTest(unittest.TestCase):
    def test_missing_execute_blocks_before_repository_read(self) -> None:
        repo = FakeDeliveryRepository(default_snapshot())

        report = run_delivery_materialization_execute(
            repository=repo,
            execute=False,
            user_confirmed=True,
            expected_source_count=2,
            **artifact_paths(),
        )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("missing_execute_flag", report["blockers"])
        self.assertEqual(repo.fetch_calls, 0)
        self.assertEqual(repo.commit_calls, 0)

    def test_missing_user_confirmed_blocks_before_repository_read(self) -> None:
        repo = FakeDeliveryRepository(default_snapshot())

        report = run_delivery_materialization_execute(
            repository=repo,
            execute=True,
            user_confirmed=False,
            expected_source_count=2,
            **artifact_paths(),
        )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("missing_user_confirmed", report["blockers"])
        self.assertEqual(repo.fetch_calls, 0)
        self.assertEqual(repo.commit_calls, 0)

    def test_sanitizer_strips_internal_payload(self) -> None:
        row = source_row(
            notification_payload_json={
                "source_outbox_id": 123,
                "source_event_id": "evt_internal",
                "source_action_run_id": "action_run_internal",
                "trace_json": {"secret": True},
                "raw_n5_payload": {"secret": True},
                "action_state": "blocked",
                "identity_key": "stock:SZ:300001",
            }
        )

        sanitized = build_sanitized_payload(row, DEFAULT_DELIVERY_MATERIALIZATION_RUN_ID)

        for key in FORBIDDEN_PROVIDER_PAYLOAD_KEYS:
            self.assertNotIn(key, sanitized)
        self.assertEqual(
            sorted(sanitized.keys()),
            [
                "action_state",
                "asset_kind",
                "channel",
                "dedup_key",
                "delivery_materialization_run_id",
                "display_state",
                "failure",
                "identity_key",
                "policy",
                "provider",
                "retry",
                "schema_version",
            ],
        )

    def test_execute_materializes_append_only_preview_rows(self) -> None:
        repo = FakeDeliveryRepository(default_snapshot())

        report = run_delivery_materialization_execute(
            repository=repo,
            execute=True,
            user_confirmed=True,
            expected_source_count=2,
            **artifact_paths(),
        )

        self.assertEqual(report["result"], "EXECUTED")
        self.assertEqual(report["preflight_result"], "PREFLIGHT_PASS")
        self.assertEqual(repo.commit_calls, 1)
        self.assertEqual(set(repo.committed_plan.write_tables), set(ALLOWED_WRITE_TABLES))
        self.assertEqual(repo.committed_plan.write_counts, {"user_notification_queue": 2})
        self.assertEqual(report["write_summary"]["write_counts"]["user_notification_queue"], 2)

        for row in repo.committed_plan.notification_rows:
            self.assertEqual(row["notification_source"], TARGET_NOTIFICATION_SOURCE)
            self.assertEqual(row["queue_status"], TARGET_QUEUE_STATUS)
            self.assertEqual(row["channel"], TARGET_CHANNEL)
            self.assertIsNone(row["trace_json"])
            self.assertEqual(row["projection_policy"], "noop_local_preview_materialized_no_delivery")
            for key in FORBIDDEN_PROVIDER_PAYLOAD_KEYS:
                self.assertNotIn(key, row["notification_payload_json"])

    def test_trace_json_none_binds_as_sql_null_while_payload_binds_jsonb_object(self) -> None:
        row = build_materialized_notification_row(source_row(), DEFAULT_DELIVERY_MATERIALIZATION_RUN_ID)

        trace_param = jsonb_if_needed("trace_json", row["trace_json"])
        payload_param = jsonb_if_needed("notification_payload_json", row["notification_payload_json"])

        self.assertIsNone(row["trace_json"])
        self.assertIsNone(trace_param)
        self.assertIsInstance(row["notification_payload_json"], dict)
        self.assertIsInstance(payload_param, Jsonb)

    def test_existing_materialized_rows_block_idempotency(self) -> None:
        snapshot = default_snapshot()
        snapshot.existing_materialized_count = 1
        repo = FakeDeliveryRepository(snapshot)

        report = run_delivery_materialization_execute(
            repository=repo,
            execute=True,
            user_confirmed=True,
            expected_source_count=2,
            **artifact_paths(),
        )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("delivery_materialization_baseline_not_zero", report["blockers"])
        self.assertEqual(repo.commit_calls, 0)

    def test_forbidden_side_effects_are_false(self) -> None:
        repo = FakeDeliveryRepository(default_snapshot())

        report = run_delivery_materialization_execute(
            repository=repo,
            execute=True,
            user_confirmed=True,
            expected_source_count=2,
            **artifact_paths(),
        )

        for key, value in report["side_effects"].items():
            if key in {"database_write", "writes_user_notification_queue"}:
                self.assertTrue(value)
            else:
                self.assertFalse(value)

    def test_invalid_artifact_status_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            contract_path = tmp / "contract.json"
            preflight_path = tmp / "preflight.json"
            rollback_path = tmp / "rollback.sql"
            contract_path.write_text(json.dumps({"status": "BAD"}), encoding="utf-8")
            preflight_path.write_text(json.dumps({"status": "EXECUTE_FINAL_PREFLIGHT_PASS"}), encoding="utf-8")
            rollback_path.write_text("RAISE EXCEPTION 'guard';\nDELETE FROM user_notification_queue;\n", encoding="utf-8")

            errors = validate_delivery_artifacts(str(contract_path), str(preflight_path), str(rollback_path))

        self.assertIn("missing_or_invalid_contract_json:status_not_allowed", errors)

    def test_rollback_sql_hard_fails_before_delete(self) -> None:
        sql = Path("sql/N6_20260603_delivery_notification_rollback.sql").read_text(encoding="utf-8")
        first_delete = sql.upper().find("DELETE FROM")
        first_raise = sql.upper().find("RAISE EXCEPTION")

        self.assertGreaterEqual(first_delete, 0)
        self.assertGreaterEqual(first_raise, 0)
        self.assertLess(first_raise, first_delete)
        for token in ("voice", "mobile", "position", "sim", "to_regclass"):
            self.assertIn(token, sql)
        self.assertNotIn("common_event_outbox", sql)

    def test_provider_adapter_capabilities_default_network_disabled(self) -> None:
        adapters = [
            NoopLocalPreviewAdapter(),
            DryRunProviderAdapter(),
            RealProviderAdapterSkeleton(),
        ]

        for adapter in adapters:
            capability = adapter.capability()
            self.assertIsInstance(capability, ProviderCapability)
            self.assertFalse(capability.can_send_network)
            self.assertFalse(capability.can_update_n5_outbox_status)

        self.assertTrue(NoopLocalPreviewAdapter().capability().can_materialize_preview)
        self.assertTrue(RealProviderAdapterSkeleton().capability().requires_credentials)

    def test_missing_final_execute_gate_blocks_real_send_before_transport(self) -> None:
        transport = FakeProviderTransport()
        adapter = RealProviderAdapterSkeleton(transport=transport)

        result = adapter.send(provider_input(credential_ref="secret://n6/provider/admin"))

        self.assertEqual(result.result, "BLOCKED")
        self.assertIn("missing_final_execute_gate", result.blockers)
        self.assertFalse(result.network_send_attempted)
        self.assertFalse(result.provider_delivery_confirmed)
        self.assertEqual(transport.call_count, 0)

    def test_can_send_network_false_blocks_real_send(self) -> None:
        transport = FakeProviderTransport()
        adapter = RealProviderAdapterSkeleton(transport=transport)

        result = adapter.send(
            provider_input(
                credential_ref="secret://n6/provider/admin",
                policy_hooks=ProviderPolicyHooks(
                    final_gate_allowed=True,
                    network_send_enabled=True,
                    consent_allowed=True,
                    retry_policy_ready=True,
                    attempt_audit_ready=True,
                    n5_ack_policy_ready=True,
                    rollback_supersession_ready=True,
                ),
            ),
            final_gate_token="future-final-gate-token",
        )

        self.assertEqual(result.result, "BLOCKED")
        self.assertIn("can_send_network_false", result.blockers)
        self.assertFalse(result.network_send_attempted)
        self.assertEqual(transport.call_count, 0)

    def test_noop_and_dry_run_never_call_network(self) -> None:
        transport = FakeProviderTransport()

        noop_result = NoopLocalPreviewAdapter(transport=transport).send(provider_input())
        dry_run_result = DryRunProviderAdapter(transport=transport).send(provider_input())

        self.assertEqual(noop_result.result, "NOOP")
        self.assertEqual(dry_run_result.result, "DRY_RUN")
        self.assertFalse(noop_result.network_send_attempted)
        self.assertFalse(dry_run_result.network_send_attempted)
        self.assertFalse(noop_result.provider_delivery_confirmed)
        self.assertFalse(dry_run_result.provider_delivery_confirmed)
        self.assertEqual(transport.call_count, 0)

    def test_real_provider_skeleton_without_explicit_enable_never_calls_network(self) -> None:
        transport = FakeProviderTransport()
        adapter = RealProviderAdapterSkeleton(transport=transport)

        result = adapter.send(
            provider_input(
                credential_ref="secret://n6/provider/admin",
                policy_hooks=ProviderPolicyHooks(final_gate_allowed=True),
            ),
            final_gate_token="future-final-gate-token",
        )

        self.assertEqual(result.result, "BLOCKED")
        self.assertIn("network_send_not_enabled", result.blockers)
        self.assertFalse(result.network_send_attempted)
        self.assertEqual(transport.call_count, 0)

    def test_secret_values_never_appear_in_provider_report_or_artifact(self) -> None:
        adapter = RealProviderAdapterSkeleton()
        result = adapter.send(
            provider_input(
                credential_ref="secret://n6/provider/admin",
                secret_value="SUPER_SECRET_VALUE_SHOULD_NOT_LEAK",
            )
        )

        report = redact_provider_report(result.to_report())
        report_text = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertNotIn("SUPER_SECRET_VALUE_SHOULD_NOT_LEAK", report_text)
        self.assertNotIn("secret_value", report_text)
        self.assertIn("secret_supplied", result.blockers)

    def test_n5_outbox_status_unchanged_by_provider_adapters(self) -> None:
        for adapter in (NoopLocalPreviewAdapter(), DryRunProviderAdapter(), RealProviderAdapterSkeleton()):
            capability = adapter.capability()
            result = adapter.send(provider_input(credential_ref="secret://n6/provider/admin"))
            self.assertFalse(capability.can_update_n5_outbox_status)
            self.assertFalse(result.n5_outbox_status_updated)

    def test_provider_payload_excludes_trace_source_raw_payload(self) -> None:
        adapter = DryRunProviderAdapter()
        payload = adapter.build_provider_visible_payload(
            provider_input(
                notification_payload_json={
                    "title": "允许标题",
                    "message": "允许消息",
                    "trace_json": {"internal": True},
                    "source_payload_json": {"raw": True},
                    "raw_n5_payload": {"raw": True},
                    "source_outbox_id": 1,
                    "payload_json": {"raw": True},
                }
            )
        )

        self.assertFalse(provider_payload_has_forbidden_keys(payload))
        for key in FORBIDDEN_PROVIDER_PAYLOAD_KEYS:
            self.assertNotIn(key, payload)
        self.assertEqual(payload["title"], "允许标题")
        self.assertEqual(payload["message"], "允许消息")

    def test_policy_hooks_required_before_real_send(self) -> None:
        adapter = RealProviderAdapterSkeleton()
        result = adapter.send(
            provider_input(
                credential_ref="secret://n6/provider/admin",
                policy_hooks=ProviderPolicyHooks(
                    final_gate_allowed=True,
                    network_send_enabled=True,
                    consent_allowed=False,
                    retry_policy_ready=False,
                    attempt_audit_ready=False,
                    n5_ack_policy_ready=False,
                    rollback_supersession_ready=False,
                ),
            ),
            final_gate_token="future-final-gate-token",
        )

        self.assertEqual(result.result, "BLOCKED")
        for blocker in (
            "can_send_network_false",
            "consent_not_allowed",
            "retry_policy_missing",
            "attempt_audit_policy_missing",
            "n5_ack_policy_missing",
            "rollback_supersession_policy_missing",
        ):
            self.assertIn(blocker, result.blockers)
        self.assertFalse(result.network_send_attempted)


def artifact_paths() -> dict[str, str]:
    tmp = Path(tempfile.mkdtemp())
    contract_path = tmp / "contract.json"
    preflight_path = tmp / "preflight.json"
    rollback_path = tmp / "rollback.sql"
    contract_path.write_text(json.dumps({"status": "CONTRACT_MATERIALIZATION_PASS"}), encoding="utf-8")
    preflight_path.write_text(json.dumps({"status": "EXECUTE_FINAL_PREFLIGHT_PASS"}), encoding="utf-8")
    rollback_path.write_text("RAISE EXCEPTION 'guard';\nDELETE FROM user_notification_queue;\n", encoding="utf-8")
    return {
        "contract_json_path": str(contract_path),
        "preflight_json_path": str(preflight_path),
        "rollback_sql_path": str(rollback_path),
    }


def default_snapshot() -> DeliveryExecuteSnapshot:
    return DeliveryExecuteSnapshot(
        source_projection_run_id=DEFAULT_SOURCE_PROJECTION_RUN_ID,
        delivery_materialization_run_id=DEFAULT_DELIVERY_MATERIALIZATION_RUN_ID,
        source_rows=[source_row(1), source_row(2)],
        existing_materialized_count=0,
        forbidden_ref_counts={
            "provider_delivery_attempt": 0,
            "voice": 0,
            "mobile": 0,
            "sim": 0,
            "position": 0,
            "real_trade": 0,
        },
        n5_outbox_counts={"ActionBlocked:pending": 863},
    )


def source_row(
    user_notification_queue_id: int = 1,
    *,
    notification_payload_json: dict | None = None,
) -> SourceNotificationRow:
    return SourceNotificationRow(
        user_notification_queue_id=user_notification_queue_id,
        user_id=1,
        user_projection_run_id=DEFAULT_SOURCE_PROJECTION_RUN_ID,
        user_signal_projection_id=user_notification_queue_id * 10,
        user_signal_card_id=user_notification_queue_id * 100,
        notification_source="n5_action_blocked",
        queue_status="queued_only",
        channel="broadcast_queue",
        title=f"测试信号 {user_notification_queue_id}",
        message=f"未确认信号 {user_notification_queue_id}",
        priority=50,
        source_event_id=f"evt_{user_notification_queue_id}",
        source_action_run_id="action_consumer_market_action_confirmation_v1_20260603_trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1",
        source_action_event_id=f"evt_{user_notification_queue_id}",
        source_action_event_type="ActionBlocked",
        action_state="blocked",
        action_mark=None,
        condition_key="SELL:M,W,D",
        original_condition_key="SELL:M,W,D",
        trace_json={"internal": True},
        projection_policy="blocked_unconfirmed_no_push_no_decision_no_sim_no_trade",
        asset_kind="stock",
        identity_key=f"stock:SZ:30000{user_notification_queue_id}",
        notification_payload_json=notification_payload_json
        or {
            "source_outbox_id": user_notification_queue_id,
            "source_event_type": "ActionBlocked",
            "action_state": "blocked",
            "trace_json": {"internal": True},
        },
    )


class FakeProviderTransport:
    def __init__(self) -> None:
        self.call_count = 0

    def __call__(self, payload: dict) -> dict:
        self.call_count += 1
        return {"provider_message_id": "provider-1", "payload": payload}


def provider_input(
    *,
    credential_ref: str | None = None,
    secret_value: str | None = None,
    notification_payload_json: dict | None = None,
    policy_hooks: ProviderPolicyHooks | None = None,
) -> ProviderSendInput:
    return ProviderSendInput(
        delivery_materialization_run_id=DEFAULT_DELIVERY_MATERIALIZATION_RUN_ID,
        source_notification_queue_id=1,
        provider_id="real_provider_skeleton",
        channel="in_app_notification_preview",
        title="市场动作未确认",
        message="只读展示",
        credential_ref=credential_ref,
        secret_value=secret_value,
        notification_payload_json=notification_payload_json or {"title": "市场动作未确认", "message": "只读展示"},
        policy_hooks=policy_hooks or ProviderPolicyHooks(),
    )


if __name__ == "__main__":
    unittest.main()
