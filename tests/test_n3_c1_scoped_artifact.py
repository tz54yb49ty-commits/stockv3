import inspect
import unittest

from ashare_v3.market import c1_scoped_artifact
from ashare_v3.market.c1_scoped_artifact import (
    BLOCKED_C1_MINUTE_NOT_CLOSED,
    BLOCKED_C1_SOURCE_ROWS_CONTRACT_MISMATCH,
    BLOCKED_FULL_MARKET_FALLBACK_RISK,
    BLOCKED_N3_C1_SCOPE_CONTRACT_MISMATCH,
    BLOCKED_SOURCE_CLOSE_LABEL_NOT_MAPPABLE,
    SOURCE_CLOSE_LABEL_POLICY,
    apply_source_close_label_policy_to_row,
    build_n3_c1_n3t_metric_context_source_artifact,
    build_n3_c1_scoped_current_day_pull_plan,
    build_n3_c1_scoped_current_day_staging_artifact,
    build_n3_c1_scoped_artifact_plan,
    build_source_close_label_plan_for_target_minute,
    is_c1_minute_closed_for_scoped_artifact,
    source_close_label_to_physical_start_label,
)
from ashare_v3.market.minute_label_normalization import BLOCKED_C1_MINUTE_LABEL_NOT_TRADABLE


TRADE_DATE = "20260702"


def active_scope_artifact(scope_rows=None, **overrides):
    artifact = {
        "artifact_type": "n5_active_scope_snapshot_v1",
        "artifact_schema_version": "v1",
        "producer_layer": "N5_action",
        "for_trade_date": TRADE_DATE,
        "scope_status": "active",
        "empty_scope_noop": False,
        "scope_count": 1,
        "scope_rows": scope_rows if scope_rows is not None else [active_scope_row()],
        "full_market_fallback_allowed": False,
        "n3_scans_n5_internals": False,
        "db_write_allowed": False,
        "n4_outbox_status_update_allowed": False,
        "updates_n4_outbox": False,
    }
    artifact.update(overrides)
    return artifact


def active_scope_row(**overrides):
    row = {
        "for_trade_date": TRADE_DATE,
        "asset_kind": "stock",
        "identity_key": "stock:SZ:300803",
        "direction": "buy",
        "signal_type": "B_BUY",
        "condition_key": "BUY_MAIN",
        "source_trigger_event_id": "n4-match-300803",
        "source_trigger_run_id": "n4_trigger_20260702_v1",
        "scope_status": "active",
    }
    row.update(overrides)
    return row


def metric_context_row(**overrides):
    row = {
        "for_trade_date": TRADE_DATE,
        "asset_kind": "stock",
        "identity_key": "stock:SZ:300803",
        "direction": "buy",
        "signal_type": "B_BUY",
        "condition_key": "BUY_MAIN",
        "source_trigger_event_id": "n4-match-300803",
        "source_trigger_run_id": "n4_trigger_20260702_v1",
        "scope_status": "active",
        "source_closed_minute_bar_ids": [101, 102, 103],
        "previous_day_minute_refs": [201, 202, 203],
        "metric_values": {
            "current_price": 12,
            "previous_120m_body_high": 10,
            "previous_120m_body_low": 9,
            "previous_30m_body_high": 10,
            "previous_30m_body_low": 9,
            "previous_5m_body_high": 10,
            "previous_5m_body_low": 9,
            "previous_1m_body_high": 10,
            "previous_1m_body_low": 9,
            "current_1m_amount": 20,
            "previous_1m_amount": 10,
            "current_5m_amount": 80,
            "previous_5m_amount": 60,
            "current_30m_closed_elapsed_amount": 200,
            "previous_day_same_window_amount": 100,
            "is_first_1m_of_day": True,
            "is_first_5m_of_day": True,
            "first_1m_amount_default_pass": True,
            "first_5m_amount_default_pass": True,
        },
    }
    row.update(overrides)
    return row


def active_scope_rows_60():
    rows = []
    for idx in range(57):
        rows.append(
            active_scope_row(
                identity_key=f"stock:SH:{600000 + idx:06d}",
                condition_key="BUY:Y,Q,M",
                source_trigger_event_id=f"evt-stock-{idx:02d}",
            )
        )
    for idx, board_code in enumerate(("881111", "881157", "881234")):
        rows.append(
            active_scope_row(
                asset_kind="board",
                identity_key=f"board:TDX:{board_code}",
                condition_key="BUY:Y,Q,M",
                source_trigger_event_id=f"evt-board-{idx:02d}",
            )
        )
    return rows


class N3C1ScopedArtifactDraftTest(unittest.TestCase):
    def test_current_day_pull_plan_uses_only_explicit_active_scope_rows(self):
        scope_rows = active_scope_rows_60()
        plan = build_n3_c1_scoped_current_day_pull_plan(
            active_scope_artifact(scope_rows=scope_rows, scope_count=60),
            target_minute_label="09:44",
            observed_at="2026-07-02T09:45:00+08:00",
            source_artifact_path="docs/runtime/20260702/n5_active_scope_snapshot_v1.json",
            source_artifact_hash="sha256:n5-scope",
        )

        self.assertEqual(plan["artifact_type"], "n3_c1_scoped_current_day_pull_plan_v1")
        self.assertEqual(plan["input_artifact_type"], "n5_active_scope_snapshot_v1")
        self.assertEqual(plan["producer_layer"], "N3_market_data")
        self.assertEqual(plan["plan_status"], "planned")
        self.assertIsNone(plan["blocked_reason"])
        self.assertEqual(plan["for_trade_date"], TRADE_DATE)
        self.assertEqual(plan["target_minute_label"], "09:44")
        self.assertEqual(plan["expected_closed_time"], "2026-07-02T09:45:00+08:00")
        self.assertEqual(plan["source_label_policy"], SOURCE_CLOSE_LABEL_POLICY)
        self.assertEqual(plan["source_label_semantics"], "close_label")
        self.assertEqual(plan["physical_label_semantics"], "start_label")
        self.assertEqual(plan["required_physical_labels"][0], "09:30")
        self.assertEqual(plan["required_physical_labels"][-1], "09:44")
        self.assertEqual(plan["required_raw_source_labels"][0], "09:31")
        self.assertEqual(plan["required_raw_source_labels"][-1], "09:45")
        self.assertEqual(len(plan["required_physical_labels"]), 15)
        self.assertEqual(len(plan["required_raw_source_labels"]), 15)
        self.assertEqual(plan["expected_rows_after_pull"], 900)
        self.assertEqual(plan["scope_count"], 60)
        self.assertEqual(len(plan["plan_rows"]), 60)
        self.assertEqual({row["asset_kind"] for row in plan["plan_rows"]}, {"stock", "board"})
        self.assertEqual({row["required_data_kind"] for row in plan["plan_rows"]}, {"minute_bar_1m"})
        self.assertTrue(all(row["source_label_policy"] == SOURCE_CLOSE_LABEL_POLICY for row in plan["plan_rows"]))
        self.assertTrue(all(row["required_raw_source_labels"][0] == "09:31" for row in plan["plan_rows"]))
        self.assertTrue(all(row["required_raw_source_labels"][-1] == "09:45" for row in plan["plan_rows"]))
        self.assertTrue(all(row["artifact_staging_only"] for row in plan["plan_rows"]))
        self.assertFalse(plan["full_market_fallback_allowed"])
        self.assertFalse(plan["n3_scans_n5_internals"])
        self.assertEqual(plan["future_pull_execute_gate_required"], "N3_C1_SCOPED_CURRENT_DAY_PULL_EXECUTE_GATE")
        self.assertEqual(plan["canonical_c1_write_gate_required"], "N3_C1_SCOPED_EXECUTE_GATE")
        self.assertTrue(plan["n3t_remains_blocked_until_metric_context_ready"])
        self.assertFalse(plan["side_effects"]["database_written"])
        self.assertFalse(plan["side_effects"]["market_data_pulled"])
        self.assertFalse(plan["side_effects"]["writes_canonical_minute_bar_1m"])
        self.assertFalse(plan["side_effects"]["writes_n3_outbox"])
        self.assertFalse(plan["side_effects"]["consumes_n4_outbox"])
        self.assertFalse(plan["side_effects"]["updates_n4_outbox"])
        self.assertFalse(plan["side_effects"]["full_market_fallback_used"])

    def test_source_close_label_policy_maps_raw_close_to_physical_start_labels(self):
        first = source_close_label_to_physical_start_label(TRADE_DATE, "09:31")
        target = source_close_label_to_physical_start_label(TRADE_DATE, "09:45")

        self.assertEqual(first["status"], "mapped")
        self.assertEqual(first["source_label_policy"], SOURCE_CLOSE_LABEL_POLICY)
        self.assertEqual(first["raw_source_label"], "09:31")
        self.assertEqual(first["physical_c1_label"], "09:30")
        self.assertEqual(target["status"], "mapped")
        self.assertEqual(target["raw_source_label"], "09:45")
        self.assertEqual(target["physical_c1_label"], "09:44")

    def test_current_day_staging_rejects_source_rows_outside_pull_plan_scope(self):
        scope = active_scope_artifact()
        plan = build_n3_c1_scoped_current_day_pull_plan(
            scope,
            target_minute_label="09:31",
            observed_at="2026-07-02T09:32:00+08:00",
        )
        current_rows = [
            {
                **active_scope_row(),
                "physical_c1_label": "09:30",
                "raw_source_label": "09:31",
                "open": 12,
                "high": 12.5,
                "low": 11.9,
                "close": 12.1,
                "amount": 1000,
                "source_row_ref": "current:300803:0930",
                "fake_or_synthetic_row": False,
            },
            {
                **active_scope_row(),
                "physical_c1_label": "09:31",
                "raw_source_label": "09:32",
                "open": 12.1,
                "high": 12.6,
                "low": 12,
                "close": 12.2,
                "amount": 1001,
                "source_row_ref": "current:300803:0931",
                "fake_or_synthetic_row": False,
            },
            {
                **active_scope_row(identity_key="stock:SZ:300804", source_trigger_event_id="n4-match-300804"),
                "physical_c1_label": "09:30",
                "raw_source_label": "09:31",
                "open": 10,
                "high": 10.2,
                "low": 9.9,
                "close": 10.1,
                "amount": 900,
                "source_row_ref": "current:300804:0930",
                "fake_or_synthetic_row": False,
            },
        ]

        staging = build_n3_c1_scoped_current_day_staging_artifact(
            scope,
            pull_plan_artifact=plan,
            source_rows_artifact={
                "artifact_type": "n3_c1_scoped_current_day_source_rows_v1",
                "for_trade_date": TRADE_DATE,
                "target_hhmm": "0931",
                "closed_minute_rows": current_rows,
                "full_market_fallback_used": False,
                "database_written": False,
                "writes_canonical_minute_bar_1m": False,
                "writes_n3_outbox": False,
            },
            target_hhmm="0931",
            observed_at="2026-07-02T09:32:00+08:00",
        )

        self.assertEqual(staging["artifact_status"], "blocked")
        self.assertEqual(staging["blocked_reason"], BLOCKED_C1_SOURCE_ROWS_CONTRACT_MISMATCH)
        self.assertFalse(staging["database_written"])
        self.assertFalse(staging["writes_canonical_minute_bar_1m"])
        self.assertFalse(staging["writes_n3_outbox"])

    def test_source_close_label_policy_preserves_raw_payload_without_fake_row(self):
        source_row = {
            "bar_time": "2026-07-02T09:31:00+08:00",
            "open": 10,
            "close": 11,
            "raw_payload": {"provider_row_id": "raw-0931"},
        }

        row = apply_source_close_label_policy_to_row(source_row, for_trade_date=TRADE_DATE)

        self.assertEqual(row["bar_time"], "2026-07-02T09:30:00+08:00")
        self.assertEqual(row["raw_source_bar_time"], "2026-07-02T09:31:00+08:00")
        self.assertEqual(row["raw_source_label"], "09:31")
        self.assertEqual(row["physical_c1_label"], "09:30")
        self.assertEqual(row["source_label_policy"], SOURCE_CLOSE_LABEL_POLICY)
        self.assertFalse(row["fake_or_synthetic_row"])
        self.assertEqual(row["raw_payload"]["provider_row_id"], "raw-0931")
        self.assertEqual(row["raw_payload"]["raw_source_label"], "09:31")
        self.assertEqual(row["raw_payload"]["physical_c1_label"], "09:30")

    def test_source_close_label_policy_does_not_bridge_1300_to_1130(self):
        blocked = source_close_label_to_physical_start_label(TRADE_DATE, "13:00")

        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(blocked["reason"], BLOCKED_SOURCE_CLOSE_LABEL_NOT_MAPPABLE)
        self.assertEqual(blocked["raw_source_label"], "13:00")
        self.assertIsNone(blocked["physical_c1_label"])
        self.assertEqual(blocked["source_label_policy"], SOURCE_CLOSE_LABEL_POLICY)

    def test_source_close_label_plan_marks_lunch_close_gap_without_bridge_or_fake_row(self):
        plan = build_source_close_label_plan_for_target_minute(
            for_trade_date=TRADE_DATE,
            target_minute_label="13:01",
        )

        self.assertEqual(plan["status"], "planned")
        self.assertEqual(plan["source_label_policy"], SOURCE_CLOSE_LABEL_POLICY)
        self.assertEqual(plan["source_gap_policy"], "session_boundary_source_gap_excluded_v1")
        self.assertNotIn("11:30", plan["required_raw_source_labels"])
        self.assertNotIn("13:00", plan["required_raw_source_labels"])
        self.assertNotIn("11:29", plan["required_physical_labels"])
        self.assertIn("13:00", plan["required_physical_labels"])
        self.assertIn("13:01", plan["required_physical_labels"])
        self.assertEqual(
            plan["source_gap_physical_labels"],
            [
                {
                    "physical_c1_label": "11:29",
                    "missing_raw_source_label": "11:30",
                    "reason": "lunch_close_missing_source",
                    "metric_context_dependency": "session_boundary_previous_raw_c1_context_required",
                    "fake_or_synthetic_row": False,
                }
            ],
        )

    def test_current_day_pull_plan_maps_close_boundary_1500_to_physical_1459(self):
        plan = build_n3_c1_scoped_current_day_pull_plan(
            active_scope_artifact(scope_rows=active_scope_rows_60(), scope_count=60),
            target_minute_label="15:00",
            observed_at="2026-07-02T15:00:00+08:00",
        )

        self.assertEqual(plan["plan_status"], "planned")
        self.assertEqual(plan["target_minute_label"], "15:00")
        self.assertEqual(plan["normalized_target_minute_label"], "14:59")
        self.assertEqual(plan["target_minute_boundary_policy"], "session_close_boundary_latest_physical_label_v1")
        self.assertEqual(plan["closed_minute_contract"]["minute_label"], "14:59")
        self.assertEqual(plan["required_physical_labels"][-1], "14:59")
        self.assertEqual(plan["required_raw_source_labels"][-1], "15:00")
        self.assertNotIn("11:30", plan["required_raw_source_labels"])
        self.assertNotIn("13:00", plan["required_raw_source_labels"])
        self.assertFalse(plan["side_effects"]["full_market_fallback_used"])

    def test_current_day_pull_plan_empty_scope_returns_noop(self):
        plan = build_n3_c1_scoped_current_day_pull_plan(
            active_scope_artifact(scope_rows=[], scope_status="empty", empty_scope_noop=True, scope_count=0),
            target_minute_label="09:44",
            observed_at="2026-07-02T09:45:00+08:00",
        )

        self.assertEqual(plan["plan_status"], "noop")
        self.assertTrue(plan["empty_scope_noop"])
        self.assertEqual(plan["scope_count"], 0)
        self.assertEqual(plan["plan_rows"], [])
        self.assertFalse(plan["side_effects"]["full_market_fallback_used"])

    def test_current_day_pull_plan_invalid_or_stale_scope_fails_closed(self):
        invalid = build_n3_c1_scoped_current_day_pull_plan(
            active_scope_artifact(artifact_type="wrong_scope"),
            target_minute_label="09:44",
            observed_at="2026-07-02T09:45:00+08:00",
        )
        stale = build_n3_c1_scoped_current_day_pull_plan(
            active_scope_artifact(scope_rows=[active_scope_row(for_trade_date="20260701")]),
            target_minute_label="09:44",
            observed_at="2026-07-02T09:45:00+08:00",
        )

        self.assertEqual(invalid["plan_status"], "blocked")
        self.assertEqual(invalid["blocked_reason"], BLOCKED_N3_C1_SCOPE_CONTRACT_MISMATCH)
        self.assertEqual(stale["plan_status"], "blocked")
        self.assertEqual(stale["blocked_reason"], BLOCKED_N3_C1_SCOPE_CONTRACT_MISMATCH)

    def test_current_day_pull_plan_forbids_full_market_fallback(self):
        plan = build_n3_c1_scoped_current_day_pull_plan(
            active_scope_artifact(full_market_fallback_allowed=True),
            target_minute_label="09:44",
            observed_at="2026-07-02T09:45:00+08:00",
        )

        self.assertEqual(plan["plan_status"], "blocked")
        self.assertEqual(plan["blocked_reason"], BLOCKED_FULL_MARKET_FALLBACK_RISK)
        self.assertFalse(plan["full_market_fallback_allowed"])
        self.assertFalse(plan["side_effects"]["full_market_fallback_used"])

    def test_valid_active_scope_builds_scoped_artifact_plan(self):
        artifact = build_n3_c1_scoped_artifact_plan(
            active_scope_artifact(),
            target_minute_label="09:52",
            observed_at="2026-07-02T09:53:00+08:00",
            source_artifact_path="docs/runtime/n5_scope.json",
            source_artifact_hash="sha256:scope",
        )

        self.assertEqual(artifact["artifact_type"], "n3_c1_scoped_closed_1m_artifact_v1")
        self.assertEqual(artifact["input_artifact_type"], "n5_active_scope_snapshot_v1")
        self.assertEqual(artifact["producer_layer"], "N3_market_data")
        self.assertEqual(artifact["for_trade_date"], TRADE_DATE)
        self.assertEqual(artifact["target_minute_label"], "09:52")
        self.assertEqual(artifact["artifact_status"], "planned")
        self.assertIsNone(artifact["blocked_reason"])
        self.assertEqual(artifact["scope_count"], 1)
        self.assertEqual(artifact["scope_rows"], [active_scope_row()])
        self.assertFalse(artifact["empty_scope_noop"])
        self.assertFalse(artifact["full_market_fallback_allowed"])
        self.assertFalse(artifact["n3_scans_n5_internals"])
        self.assertEqual(artifact["source_scope_artifact"]["path"], "docs/runtime/n5_scope.json")
        self.assertEqual(artifact["source_scope_artifact"]["hash"], "sha256:scope")
        self.assertEqual(artifact["canonical_c1_write_gate_required"], "N3_C1_SCOPED_EXECUTE_GATE")
        self.assertFalse(artifact["side_effects"]["database_written"])
        self.assertFalse(artifact["side_effects"]["market_data_pulled"])
        self.assertFalse(artifact["side_effects"]["writes_canonical_minute_bar_1m"])
        self.assertFalse(artifact["side_effects"]["writes_n3_outbox"])
        self.assertFalse(artifact["side_effects"]["consumes_n4_outbox"])
        self.assertFalse(artifact["side_effects"]["updates_n4_outbox"])
        self.assertFalse(artifact["side_effects"]["full_market_fallback_used"])

    def test_valid_active_scope_can_carry_closed_c1_metric_context(self):
        artifact = build_n3_c1_scoped_artifact_plan(
            active_scope_artifact(),
            target_minute_label="09:52",
            observed_at="2026-07-02T09:53:00+08:00",
            metric_context_rows=[metric_context_row()],
        )

        self.assertEqual(artifact["artifact_status"], "planned")
        self.assertEqual(artifact["metric_context_status"], "ready")
        self.assertEqual(artifact["metric_context_count"], 1)
        self.assertEqual(len(artifact["metric_context_rows"]), 1)
        context = artifact["metric_context_rows"][0]
        self.assertEqual(context["source_closed_minute_bar_ids"], [101, 102, 103])
        self.assertEqual(context["previous_day_minute_refs"], [201, 202, 203])
        self.assertEqual(context["metric_values"]["current_price"], 12)
        self.assertFalse(artifact["side_effects"]["database_written"])
        self.assertFalse(artifact["side_effects"]["market_data_pulled"])

    def test_metric_context_source_artifact_builds_from_staging_and_previous_day_rows(self):
        scope_row = active_scope_row()
        staging_artifact = {
            "artifact_type": "n3_c1_scoped_current_day_staging_v1",
            "artifact_status": "passed",
            "for_trade_date": TRADE_DATE,
            "scope_count": 1,
            "closed_minute_row_count": 2,
            "closed_minute_rows": [
                {
                    **scope_row,
                    "physical_c1_label": "09:51",
                    "raw_source_label": "09:52",
                    "open": 11.0,
                    "high": 12.3,
                    "low": 10.8,
                    "close": 12.0,
                    "amount": 1000.0,
                    "source_row_ref": "current:300803:0951",
                    "fake_or_synthetic_row": False,
                },
                {
                    **scope_row,
                    "physical_c1_label": "09:52",
                    "raw_source_label": "09:53",
                    "open": 12.0,
                    "high": 12.8,
                    "low": 11.7,
                    "close": 12.5,
                    "amount": 1500.0,
                    "source_row_ref": "current:300803:0952",
                    "fake_or_synthetic_row": False,
                },
            ],
            "database_written": False,
            "market_data_pulled": True,
            "writes_canonical_minute_bar_1m": False,
            "writes_n3_outbox": False,
            "full_market_fallback_used": False,
        }
        previous_day_rows = [
            {
                "asset_kind": "stock",
                "identity_key": "stock:SZ:300803",
                "physical_c1_label": "09:51",
                "open": 10.0,
                "close": 10.5,
                "high": 10.6,
                "low": 9.8,
                "amount": 800.0,
                "source_row_ref": "previous:300803:0951",
                "fake_or_synthetic_row": False,
            },
            {
                "asset_kind": "stock",
                "identity_key": "stock:SZ:300803",
                "physical_c1_label": "09:52",
                "open": 10.5,
                "close": 10.2,
                "high": 10.7,
                "low": 10.1,
                "amount": 900.0,
                "source_row_ref": "previous:300803:0952",
                "fake_or_synthetic_row": False,
            },
        ]

        artifact = build_n3_c1_n3t_metric_context_source_artifact(
            active_scope_artifact(),
            staging_artifact=staging_artifact,
            previous_day_minute_rows=previous_day_rows,
            target_hhmm="0952",
            observed_at="2026-07-02T09:53:00+08:00",
            source_staging_artifact_path="docs/runtime/staging.json",
            source_staging_artifact_hash="sha256:staging",
        )

        self.assertEqual(artifact["artifact_type"], "n3_c1_n3t_metric_context_source_v1")
        self.assertEqual(artifact["artifact_status"], "planned")
        self.assertEqual(artifact["metric_context_status"], "ready")
        self.assertEqual(artifact["scope_count"], 1)
        self.assertEqual(artifact["metric_context_count"], 1)
        self.assertFalse(artifact["database_written"])
        self.assertFalse(artifact["market_data_pulled"])
        self.assertFalse(artifact["writes_canonical_minute_bar_1m"])
        self.assertFalse(artifact["writes_n3_outbox"])
        self.assertFalse(artifact["full_market_fallback_used"])
        context = artifact["metric_context_rows"][0]
        self.assertEqual(context["source_closed_minute_bar_ids"], ["current:300803:0951", "current:300803:0952"])
        self.assertEqual(context["previous_day_minute_refs"], ["previous:300803:0951", "previous:300803:0952"])
        self.assertEqual(context["metric_values"]["current_price"], 12.5)
        self.assertEqual(context["metric_values"]["current_1m_amount"], 1500.0)
        self.assertEqual(context["metric_values"]["current_5m_amount"], 2500.0)
        self.assertEqual(context["metric_values"]["current_30m_closed_elapsed_amount"], 2500.0)
        self.assertEqual(context["metric_values"]["previous_1m_amount"], 900.0)
        self.assertEqual(context["metric_values"]["previous_5m_amount"], 1700.0)
        self.assertEqual(context["metric_values"]["previous_day_same_window_amount"], 1700.0)
        self.assertEqual(
            context["deterministic_derivation_inputs"]["previous_day_same_window_amount_source"],
            "scoped_previous_day_raw_c1_sum",
        )

    def test_empty_scope_returns_explicit_noop_artifact(self):
        artifact = build_n3_c1_scoped_artifact_plan(
            active_scope_artifact(
                scope_rows=[],
                scope_status="empty",
                empty_scope_noop=True,
                scope_count=0,
            ),
            target_minute_label="09:52",
            observed_at="2026-07-02T09:53:00+08:00",
        )

        self.assertEqual(artifact["artifact_status"], "noop")
        self.assertTrue(artifact["empty_scope_noop"])
        self.assertEqual(artifact["scope_rows"], [])
        self.assertEqual(artifact["scope_count"], 0)
        self.assertIsNone(artifact["blocked_reason"])
        self.assertFalse(artifact["side_effects"]["full_market_fallback_used"])

    def test_invalid_scope_artifact_type_fails_closed(self):
        artifact = build_n3_c1_scoped_artifact_plan(
            active_scope_artifact(artifact_type="wrong_scope"),
            target_minute_label="09:52",
            observed_at="2026-07-02T09:53:00+08:00",
        )

        self.assertEqual(artifact["artifact_status"], "blocked")
        self.assertEqual(artifact["blocked_reason"], BLOCKED_N3_C1_SCOPE_CONTRACT_MISMATCH)
        self.assertEqual(artifact["scope_rows"], [])
        self.assertFalse(artifact["side_effects"]["database_written"])

    def test_stale_or_missing_required_scope_grain_fails_closed(self):
        stale = build_n3_c1_scoped_artifact_plan(
            active_scope_artifact(scope_rows=[active_scope_row(for_trade_date="20260701")]),
            target_minute_label="09:52",
            observed_at="2026-07-02T09:53:00+08:00",
        )
        missing = build_n3_c1_scoped_artifact_plan(
            active_scope_artifact(scope_rows=[active_scope_row(source_trigger_event_id="")]),
            target_minute_label="09:52",
            observed_at="2026-07-02T09:53:00+08:00",
        )

        self.assertEqual(stale["artifact_status"], "blocked")
        self.assertEqual(stale["blocked_reason"], BLOCKED_N3_C1_SCOPE_CONTRACT_MISMATCH)
        self.assertEqual(missing["artifact_status"], "blocked")
        self.assertEqual(missing["blocked_reason"], BLOCKED_N3_C1_SCOPE_CONTRACT_MISMATCH)

    def test_full_market_fallback_flag_fails_closed(self):
        artifact = build_n3_c1_scoped_artifact_plan(
            active_scope_artifact(full_market_fallback_allowed=True),
            target_minute_label="09:52",
            observed_at="2026-07-02T09:53:00+08:00",
        )

        self.assertEqual(artifact["artifact_status"], "blocked")
        self.assertEqual(artifact["blocked_reason"], BLOCKED_FULL_MARKET_FALLBACK_RISK)
        self.assertFalse(artifact["full_market_fallback_allowed"])
        self.assertFalse(artifact["side_effects"]["full_market_fallback_used"])

    def test_unclosed_minute_blocks_with_closed_minute_reason(self):
        minute_status = is_c1_minute_closed_for_scoped_artifact(
            TRADE_DATE,
            "09:52",
            "2026-07-02T09:52:59+08:00",
        )
        artifact = build_n3_c1_scoped_artifact_plan(
            active_scope_artifact(),
            target_minute_label="09:52",
            observed_at="2026-07-02T09:52:59+08:00",
        )

        self.assertEqual(minute_status["status"], "blocked")
        self.assertEqual(minute_status["reason"], BLOCKED_C1_MINUTE_NOT_CLOSED)
        self.assertEqual(artifact["artifact_status"], "blocked")
        self.assertEqual(artifact["blocked_reason"], BLOCKED_C1_MINUTE_NOT_CLOSED)
        self.assertFalse(artifact["side_effects"]["market_data_pulled"])

    def test_lunch_close_boundary_is_not_physical_c1_bar_label(self):
        invalid = is_c1_minute_closed_for_scoped_artifact(
            TRADE_DATE,
            "11:30",
            "2026-07-02T13:01:00+08:00",
        )
        artifact = build_n3_c1_scoped_artifact_plan(
            active_scope_artifact(),
            target_minute_label="11:30",
            observed_at="2026-07-02T13:01:00+08:00",
        )
        afternoon_open = is_c1_minute_closed_for_scoped_artifact(
            TRADE_DATE,
            "13:00",
            "2026-07-02T13:01:00+08:00",
        )

        self.assertEqual(invalid["status"], "blocked")
        self.assertEqual(invalid["reason"], BLOCKED_C1_MINUTE_LABEL_NOT_TRADABLE)
        self.assertEqual(artifact["artifact_status"], "blocked")
        self.assertEqual(artifact["blocked_reason"], BLOCKED_C1_MINUTE_LABEL_NOT_TRADABLE)
        self.assertEqual(afternoon_open["status"], "closed")
        self.assertEqual(afternoon_open["usable_after"], "2026-07-02T13:01:00+08:00")

    def test_no_full_market_or_runtime_paths_exist_in_module(self):
        source = inspect.getsource(c1_scoped_artifact)

        for forbidden in (
            "psycopg",
            "mootdx",
            "tushare",
            "requests",
            "launchctl",
            "common_event_outbox",
            "subprocess",
        ):
            self.assertNotIn(forbidden, source.lower())


if __name__ == "__main__":
    unittest.main()
