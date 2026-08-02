from __future__ import annotations

import argparse
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import inspect
import unittest

from ashare_v3.user import projection_plan
from ashare_v3.user.trigger_status_projection import (
    ACTION_EVENT_TYPES,
    CONSUMER_NAME,
    CONTRACT_VERSION,
    MESSAGE_ROLE,
    PostgresTriggerStatusProjectionConsumer,
    TriggerStatusProjectionError,
    canonical_triggered_periods,
    episode_from_action_eligible,
    status_mutation_from_event,
)
from ashare_v3.web.n6_user_app import PostgresN6UserRepository
import run_n6_trigger_status_projection_once as runner


ROOT = Path(__file__).resolve().parents[1]
FORWARD = (ROOT / "sql/089_n6_trigger_status_current.sql").read_text(encoding="utf-8")
ROLLBACK = (ROOT / "sql/089_n6_trigger_status_current_rollback.sql").read_text(encoding="utf-8")
SCHEMA_HASH = "e50cea0987f7f3b99989e2c23ef2d0f9d526617c688ac7f61a18e765ec439ef2"


def eligible_event(
    *,
    outbox_id: int = 1,
    event_id: str = "eligible-1",
    entry_event_id: str = "trigger-entry-1",
    condition_key: str = "BUY:W,D",
) -> dict:
    return {
        "outbox_id": outbox_id,
        "event_id": event_id,
        "event_type": "ActionEligible",
        "event_schema_version": "n5.action.v1",
        "event_time": "2026-07-31T09:31:00+08:00",
        "trade_date": "20260731",
        "asset_kind": "stock",
        "identity_key": "stock:SH:600000",
        "source_layer": "N5_action",
        "source_run_id": "n5-entry-run",
        "dedup_key": event_id,
        "partition_key": "stock:SH:600000",
        "status": "pending",
        "payload_json": {
            "trade_date": "20260731",
            "asset_kind": "stock",
            "identity_key": "stock:SH:600000",
            "asset_code": "600000",
            "asset_name": "浦发银行",
            "direction": "buy",
            "signal_type": "B_BUY",
            "condition_key": condition_key,
            "projection_message_status": "ready",
            "trigger_time": "2026-07-31T09:31:00+08:00",
            "trigger_pct": "must-not-be-read",
            "trigger_price": "10.100000",
            "trigger_period": "W",
            "triggered_periods": ["W", "D"],
            "source_trigger_event_id": entry_event_id,
            "trace_json": {"tracking_state_key": f"state:{entry_event_id}"},
            "action_entry_trigger_matched_ref": {
                "source_trigger_event_id": entry_event_id,
                "source_trigger_event_type": "TriggerMatched",
                "source_trigger_event_time": "2026-07-31T09:31:00+08:00",
                "source_trigger_run_id": "n4-entry-run",
                "source_n4_payload": {
                    "trade_date": "20260731",
                    "asset_kind": "stock",
                    "identity_key": "stock:SH:600000",
                    "asset_code": "600000",
                    "asset_name": "浦发银行",
                    "direction": "buy",
                    "signal_type": "B_BUY",
                    "condition_key": condition_key,
                    "trigger_live": True,
                    "current_status": "matched",
                },
            },
        },
    }


def status_event(
    *,
    event_type: str = "TriggerStatusUpdated",
    outbox_id: int = 2,
    entry_event_id: str = "trigger-entry-1",
    action_eligible_event_id: str = "eligible-1",
    condition_key: str = "BUY:W,D",
) -> dict:
    operation = "update" if event_type == "TriggerStatusUpdated" else "invalidate"
    return {
        "outbox_id": outbox_id,
        "event_id": f"status-{outbox_id}",
        "event_type": event_type,
        "event_schema_version": "n5.trigger-status.v1",
        "event_time": "2026-07-31T09:35:00+08:00",
        "trade_date": "20260731",
        "asset_kind": "stock",
        "identity_key": "stock:SH:600000",
        "source_layer": "N5_action",
        "source_run_id": "n5-status-run",
        "dedup_key": f"status-{outbox_id}",
        "partition_key": "stock:SH:600000",
        "status": "pending",
        "payload_json": {
            "contract_version": CONTRACT_VERSION,
            "message_role": MESSAGE_ROLE,
            "operation": operation,
            "trade_date": "20260731",
            "tracking_state_key": f"state:{entry_event_id}",
            "entry_trigger_event_id": entry_event_id,
            "action_eligible_event_id": action_eligible_event_id,
            "source_trigger_event_id": f"n4-state-{outbox_id}",
            "asset_kind": "stock",
            "identity_key": "stock:SH:600000",
            "asset_code": "MUTATION_MUST_NOT_REPLACE_CODE",
            "asset_name": "MUTATION_MUST_NOT_REPLACE_NAME",
            "direction": "buy",
            "signal_type": "B_BUY",
            "condition_key": condition_key,
            "trigger_time": "2099-01-01T00:00:00+08:00",
            "trigger_pct": "5.555556",
            "trigger_price": "10.555556",
            "trigger_period": "M",
            "triggered_periods": ["D", "M", "W"],
            "trigger_live": event_type == "TriggerStatusUpdated",
            "current_status": "matched" if event_type == "TriggerStatusUpdated" else "inactive",
            "action_eligible_entry_allowed": False,
        },
    }


class N6TriggerStatusProjectionTests(unittest.TestCase):
    def test_forward_is_additive_episode_schema_without_principal_identity(self) -> None:
        for marker in (
            "CREATE TABLE public.n6_trigger_status_current",
            "uq_089_n6_trigger_status_episode",
            "tracking_state_key",
            "entry_trigger_event_id",
            "action_eligible_event_id",
            CONTRACT_VERSION,
            CONSUMER_NAME,
            SCHEMA_HASH,
            "GRANT SELECT ON TABLE public.n6_trigger_status_current TO n6_btrack_web",
        ):
            self.assertIn(marker, FORWARD)
        create_block = FORWARD.split("CREATE TABLE public.n6_trigger_status_current", 1)[1].split(");", 1)[0]
        self.assertNotIn("principal_id", create_block)
        self.assertNotIn("user_id", create_block)
        self.assertNotIn("trigger_pct", create_block)
        self.assertNotRegex(FORWARD, r"(?i)ALTER\s+TABLE\s+public\.(?:user_signal|n6_virtual)")

    def test_rollback_checks_hash_scope_dependencies_and_drops_only_feature(self) -> None:
        for marker in (
            SCHEMA_HASH,
            "rollback column signature drift",
            "rollback blocked by external dependencies",
            "rollback runtime scope drift",
            "consumer_name = 'n6_trigger_status_projection_v1'",
            "DROP TABLE public.n6_trigger_status_current",
        ):
            self.assertIn(marker, ROLLBACK)
        for forbidden in (
            "user_signal_projection",
            "user_signal_card",
            "user_notification_queue",
            "n6_virtual_position",
            "n6_virtual_trade",
        ):
            self.assertNotIn(f"DELETE FROM public.{forbidden}", ROLLBACK)
            self.assertNotIn(f"DROP TABLE public.{forbidden}", ROLLBACK)

    def test_action_eligible_freezes_immutable_entry_snapshot(self) -> None:
        source = eligible_event()
        frozen = deepcopy(source)
        episode = episode_from_action_eligible(source, projection_run_id="n6-projection-run")
        self.assertEqual(source, frozen)
        self.assertEqual(episode["trigger_time"], "2026-07-31T09:31:00+08:00")
        self.assertEqual(episode["asset_name"], "浦发银行")
        self.assertNotIn("trigger_pct", episode)
        self.assertEqual(str(episode["trigger_price"]), "10.100000")
        self.assertEqual(episode["triggered_periods"], ["W", "D"])

    def test_action_eligible_accepts_envelope_payload_or_entry_trade_date(self) -> None:
        for source_name in ("envelope", "payload", "entry"):
            with self.subTest(source_name=source_name):
                source = eligible_event()
                source["trade_date"] = None
                source["payload_json"].pop("trade_date")
                source["payload_json"]["action_entry_trigger_matched_ref"][
                    "source_n4_payload"
                ].pop("trade_date")
                if source_name == "envelope":
                    source["trade_date"] = "20260731"
                elif source_name == "payload":
                    source["payload_json"]["trade_date"] = "20260731"
                else:
                    source["payload_json"]["action_entry_trigger_matched_ref"][
                        "source_n4_payload"
                    ]["trade_date"] = "20260731"
                frozen = deepcopy(source)
                episode = episode_from_action_eligible(
                    source, projection_run_id="n6-projection-run"
                )
                self.assertEqual(source, frozen)
                self.assertEqual(episode["trade_date"], "20260731")

    def test_action_eligible_trade_date_conflict_and_missing_fail_closed(self) -> None:
        conflict = eligible_event()
        conflict["payload_json"]["trade_date"] = "20260730"
        with self.assertRaisesRegex(
            TriggerStatusProjectionError, "eligible_trade_date_conflict"
        ):
            episode_from_action_eligible(conflict, projection_run_id="n6-projection-run")

        missing = eligible_event()
        missing["trade_date"] = None
        missing["payload_json"].pop("trade_date")
        missing["payload_json"]["action_entry_trigger_matched_ref"][
            "source_n4_payload"
        ].pop("trade_date")
        with self.assertRaisesRegex(TriggerStatusProjectionError, "missing_trade_date"):
            episode_from_action_eligible(missing, projection_run_id="n6-projection-run")

        invalid = eligible_event()
        invalid["payload_json"].pop("trade_date")
        invalid["payload_json"]["action_entry_trigger_matched_ref"][
            "source_n4_payload"
        ].pop("trade_date")
        invalid["trade_date"] = "2026-07-31"
        with self.assertRaisesRegex(TriggerStatusProjectionError, "invalid_trade_date"):
            episode_from_action_eligible(invalid, projection_run_id="n6-projection-run")

    def test_frozen_full_batch_predicts_705_without_persistence(self) -> None:
        active_episodes: set[tuple[str, str]] = set()
        selected = 0
        for number in range(1, 1043):
            event = eligible_event(
                outbox_id=4103760 + number,
                event_id=f"eligible:{number}",
                entry_event_id=f"entry:{number}",
                condition_key="BUY:D",
            )
            event["payload_json"].pop("trade_date")
            event["payload_json"]["action_entry_trigger_matched_ref"][
                "source_n4_payload"
            ].pop("trade_date")
            episode = episode_from_action_eligible(
                event,
                projection_run_id="n6_trigger_status_projection_20260731_backfill_v1",
            )
            active_episodes.add(
                (episode["tracking_state_key"], episode["entry_trigger_event_id"])
            )
            selected += 1
        selected += 723  # ActionExecuted remains a projection no-op.
        for number in range(1, 195):
            mutation = status_mutation_from_event(
                status_event(
                    event_type="TriggerStatusUpdated",
                    outbox_id=4105525 + number,
                    entry_event_id=f"entry:{number}",
                    action_eligible_event_id=f"eligible:{number}",
                    condition_key="BUY:D",
                )
            )
            self.assertIn(
                (mutation["tracking_state_key"], mutation["entry_trigger_event_id"]),
                active_episodes,
            )
            selected += 1
        for number in range(706, 1043):
            mutation = status_mutation_from_event(
                status_event(
                    event_type="TriggerStatusInvalidated",
                    outbox_id=4105719 + number,
                    entry_event_id=f"entry:{number}",
                    action_eligible_event_id=f"eligible:{number}",
                    condition_key="BUY:D",
                )
            )
            active_episodes.discard(
                (mutation["tracking_state_key"], mutation["entry_trigger_event_id"])
            )
            selected += 1
        self.assertEqual(selected, 2296)
        self.assertEqual(len(active_episodes), 705)

    def test_action_eligible_requires_ready_projection_and_trigger_matched_ref(self) -> None:
        not_ready = eligible_event()
        not_ready["payload_json"]["projection_message_status"] = "not_ready"
        with self.assertRaisesRegex(TriggerStatusProjectionError, "eligible_projection_not_ready"):
            episode_from_action_eligible(not_ready, projection_run_id="n6-projection-run")
        wrong_entry = eligible_event()
        wrong_entry["payload_json"]["action_entry_trigger_matched_ref"][
            "source_trigger_event_type"
        ] = "TriggerStateChanged"
        with self.assertRaisesRegex(
            TriggerStatusProjectionError, "eligible_entry_ref_not_trigger_matched"
        ):
            episode_from_action_eligible(wrong_entry, projection_run_id="n6-projection-run")

    def test_update_contains_only_mutable_values_and_episode_selector(self) -> None:
        mutation = status_mutation_from_event(status_event())
        self.assertNotIn("trigger_pct", mutation)
        self.assertEqual(str(mutation["trigger_price"]), "10.555556")
        self.assertEqual(mutation["trigger_period"], "M")
        self.assertEqual(mutation["triggered_periods"], ["M", "W", "D"])
        self.assertNotIn("asset_name", mutation)
        self.assertNotIn("trigger_time", mutation)
        update_source = inspect.getsource(PostgresTriggerStatusProjectionConsumer._update_episode)
        for forbidden_assignment in (
            "trigger_time =", "asset_name =", "direction =", "condition_key =",
            "tracking_state_key =", "entry_trigger_event_id =",
        ):
            self.assertNotIn(forbidden_assignment, update_source)

    def test_update_requires_positive_price_and_legal_period_fields(self) -> None:
        non_positive = status_event()
        non_positive["payload_json"]["trigger_price"] = "0"
        with self.assertRaisesRegex(TriggerStatusProjectionError, "invalid_trigger_price"):
            status_mutation_from_event(non_positive)
        invalid_period = status_event()
        invalid_period["payload_json"]["trigger_period"] = "1m"
        with self.assertRaisesRegex(TriggerStatusProjectionError, "invalid_trigger_period"):
            status_mutation_from_event(invalid_period)
        missing_periods = status_event()
        missing_periods["payload_json"].pop("triggered_periods")
        with self.assertRaisesRegex(TriggerStatusProjectionError, "missing_triggered_periods"):
            status_mutation_from_event(missing_periods)
        malformed_periods = status_event()
        malformed_periods["payload_json"]["triggered_periods"] = "M,D"
        with self.assertRaisesRegex(TriggerStatusProjectionError, "invalid_triggered_periods"):
            status_mutation_from_event(malformed_periods)

    def test_invalidate_ignores_price_period_and_percentage_fields(self) -> None:
        event = status_event(event_type="TriggerStatusInvalidated")
        event["payload_json"].update(
            {
                "trigger_pct": "not-a-number",
                "trigger_price": "not-a-number",
                "trigger_period": "not-a-period",
                "triggered_periods": {"not": "a-list"},
            }
        )
        mutation = status_mutation_from_event(event)
        for forbidden in ("trigger_pct", "trigger_price", "trigger_period", "triggered_periods"):
            self.assertNotIn(forbidden, mutation)

    def test_missing_update_fails_closed_and_delete_is_idempotent_by_contract(self) -> None:
        update_source = inspect.getsource(PostgresTriggerStatusProjectionConsumer._update_episode)
        delete_source = inspect.getsource(PostgresTriggerStatusProjectionConsumer._invalidate_episode)
        self.assertIn("missing_status_update_target", update_source)
        self.assertIn("return int(cur.rowcount)", delete_source)

    def test_episode_selector_uses_complete_identity_and_insert_is_idempotent(self) -> None:
        selector_source = inspect.getsource(
            PostgresTriggerStatusProjectionConsumer._episode_where
        )
        for field in (
            "trade_date", "asset_kind", "identity_key", "direction", "signal_type",
            "condition_key", "tracking_state_key", "entry_trigger_event_id",
            "action_eligible_event_id",
        ):
            self.assertIn(f'"{field}"', selector_source)
        insert_source = inspect.getsource(
            PostgresTriggerStatusProjectionConsumer._insert_episode
        )
        self.assertIn(
            "ON CONFLICT (tracking_state_key, entry_trigger_event_id) DO NOTHING",
            insert_source,
        )
        self.assertIn("eligible_episode_conflict", insert_source)

    def test_hint_keeps_public_30m_without_internal_period_leak(self) -> None:
        hint = eligible_event(condition_key="BUY_HINT")
        hint["payload_json"]["trigger_period"] = "30m"
        hint["payload_json"]["triggered_periods"] = ["30m"]
        episode = episode_from_action_eligible(hint, projection_run_id="n6-hint-run")
        self.assertEqual(episode["trigger_period"], "30m")
        self.assertEqual(episode["triggered_periods"], [])
        self.assertEqual(canonical_triggered_periods(["30m"], condition_key="SELL_HINT"), [])

    def test_existing_projection_consumer_contract_is_unchanged(self) -> None:
        self.assertEqual(
            projection_plan.CANONICAL_EVENT_TYPES,
            ("ActionEligible", "ActionBlocked", "ActionExecuted", "ActionSkipped"),
        )
        self.assertEqual(tuple(ACTION_EVENT_TYPES), projection_plan.CANONICAL_EVENT_TYPES)
        self.assertEqual(
            projection_plan.N5_PROJECTION_MESSAGE_CONTRACT_HASH,
            "572078a71de8cf00963f718bc812fbe3a1ae09652a3faaa8bb3774f51b882025",
        )
        self.assertNotIn("TriggerStatusUpdated", projection_plan.ALLOWED_EVENT_TYPES)
        self.assertNotIn(CONSUMER_NAME, inspect.getsource(projection_plan))
        self.assertEqual(
            sha256((ROOT / "src/ashare_v3/user/projection_plan.py").read_bytes()).hexdigest(),
            "501540e987b90715c768c752f912f6a56aef81104c1dd5de35b39724f384c2e7",
        )
        self.assertEqual(
            sha256((ROOT / "src/ashare_v3/user/projection_execute.py").read_bytes()).hexdigest(),
            "1e80aa346edc88210f7784638f23900d365841fb972c9bd560ee3da9a5d86dff",
        )

    def test_repository_reuses_all_three_effective_visibility_sources(self) -> None:
        source = inspect.getsource(PostgresN6UserRepository.fetch_app_trigger_status)
        scope_source = inspect.getsource(PostgresN6UserRepository._app_v1_effective_monitor_scope_cte)
        query_source = inspect.getsource(PostgresN6UserRepository._app_v1_web_signal_scope_cte)
        self.assertIn("_app_v1_web_signal_scope_cte", source)
        self.assertIn("_app_v1_realtime_scope_select", scope_source)
        self.assertIn("_app_v1_holding_scope_select", scope_source)
        self.assertIn("_app_v1_effective_monitor_scope_select", scope_source)
        self.assertIn("deduplicated_monitor_scope", query_source)
        self.assertIn("PARTITION BY episode.asset_kind, episode.identity_key", source)
        self.assertIn("last_status_outbox_id DESC", source)
        self.assertIn("ARRAY['Y', 'Q', 'M', 'W', 'D']", source)

    def test_status_page_has_fixed_columns_and_mobile_offline_evidence(self) -> None:
        template = (ROOT / "src/ashare_v3/web/templates/n6_app_shell.html").read_text(
            encoding="utf-8"
        )
        headers = (
            "触发时间", "资产类型", "代码", "名称", "方向", "触发价格",
            "当前周期", "已触发周期",
        )
        status_block = template.split('{% elif page.page_key == "status-monitor" %}', 1)[1].split(
            '{% elif page.page_key == "portfolio" %}', 1
        )[0]
        self.assertEqual(status_block.count("<th>"), 8)
        for header in headers:
            self.assertIn(f"<th>{header}</th>", status_block)
        self.assertIn('data-n6-trigger-status-columns="8"', status_block)
        self.assertNotIn("trigger_pct", status_block)
        self.assertNotIn("触发涨跌幅", status_block)
        self.assertIn('data-n6-viewport-evidence="320,375,390,430,desktop"', status_block)
        self.assertIn("@media (max-width: 430px)", template)
        self.assertIn(".trigger-status-table { min-width: 980px; }", template)
        for width in (320, 375, 390, 430):
            self.assertLessEqual(width, 430)

    def test_runner_is_plan_only_without_execute_and_requires_confirmation(self) -> None:
        base = argparse.Namespace(
            dsn="not-used",
            for_trade_date="20260731",
            projection_run_id="offline",
            limit=100,
            execute=False,
            user_confirmed=False,
        )
        plan = runner.run(base)
        self.assertEqual(plan["verdict"], "N6_TRIGGER_STATUS_PROJECTION_PLAN_ONLY")
        self.assertFalse(plan["writes_database"])
        blocked = runner.run(argparse.Namespace(**{**vars(base), "execute": True}))
        self.assertEqual(blocked["verdict"], "BLOCKED_N6_TRIGGER_STATUS_PROJECTION")
        self.assertFalse(blocked["writes_database"])
        consume_source = inspect.getsource(
            PostgresTriggerStatusProjectionConsumer.consume_once
        )
        self.assertIn("AND trade_date = %s", consume_source)
        self.assertIn("episode_from_action_eligible(row", consume_source)

    def test_invalid_status_contract_fails_closed(self) -> None:
        event = status_event()
        event["payload_json"]["message_role"] = "wrong"
        with self.assertRaisesRegex(TriggerStatusProjectionError, "status_message_role_invalid"):
            status_mutation_from_event(event)


if __name__ == "__main__":
    unittest.main()
