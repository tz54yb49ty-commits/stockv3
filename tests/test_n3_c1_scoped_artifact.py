import inspect
import unittest
from unittest.mock import patch

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
    source_close_label_for_physical_start_label,
    source_close_label_to_physical_start_label,
)
from ashare_v3.market.minute_label_normalization import (
    BLOCKED_C1_MINUTE_LABEL_NOT_TRADABLE,
    MinuteLabelNormalizationError,
    normalize_c1_physical_intraday_1m_labels,
)
from ashare_v3.market.n3t_action_confirmation_metric import build_n3t_scoped_metric_from_c1_artifact_plan


TRADE_DATE = "20260702"
LIVE_20260721_PREVIOUS_CONTEXT_ARTIFACT_SHA256 = (
    "ce97db900eec9b2ba8ad08ad91fa3acf487495554bf9e5f84443cbfc4b97c1db"
)


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


def active_object_scope_row(**overrides):
    refs = overrides.pop(
        "active_tracking_refs",
        [
            active_scope_row(condition_key="BUY_MAIN", source_trigger_event_id="n4-match-main"),
            active_scope_row(condition_key="BUY_FULL", source_trigger_event_id="n4-match-full"),
        ],
    )
    row = {
        "for_trade_date": TRADE_DATE,
        "asset_kind": "stock",
        "identity_key": "stock:SZ:300803",
        "scope_status": "active",
        "active_tracking_refs": refs,
        "attention_event_refs": [],
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
            "is_first_30m_of_day": True,
            "is_first_120m_of_day": True,
            "first_1m_amount_default_pass": True,
            "first_5m_amount_default_pass": True,
            "previous_1m_period_source": "previous_trade_date_last_period",
            "previous_5m_period_source": "previous_trade_date_last_period",
            "previous_30m_period_source": "previous_trade_date_last_period",
            "previous_120m_period_source": "previous_trade_date_last_period",
            "boundary_policy_version": "n3.action_confirmation_boundary.v1",
        },
    }
    row.update(overrides)
    return row


def current_day_c1_row(label: str, idx: int, **overrides):
    row = {
        **active_scope_row(),
        "physical_c1_label": label,
        "raw_source_label": c1_scoped_artifact.source_close_label_for_physical_start_label(TRADE_DATE, label)["raw_source_label"],
        "open": 10.0 + idx / 100,
        "high": 10.2 + idx / 100,
        "low": 9.8 + idx / 100,
        "close": 10.1 + idx / 100,
        "amount": 1000.0 + idx,
        "source_row_ref": f"current:300803:{label.replace(':', '')}",
        "fake_or_synthetic_row": False,
    }
    row.update(overrides)
    return row


def current_day_object_c1_row(label: str, idx: int, **overrides):
    row = {
        "for_trade_date": TRADE_DATE,
        "asset_kind": "stock",
        "identity_key": "stock:SZ:300803",
        "scope_status": "active",
        "physical_c1_label": label,
        "raw_source_label": c1_scoped_artifact.source_close_label_for_physical_start_label(TRADE_DATE, label)["raw_source_label"],
        "open": 10.0 + idx / 100,
        "high": 10.2 + idx / 100,
        "low": 9.8 + idx / 100,
        "close": 10.1 + idx / 100,
        "amount": 1000.0 + idx,
        "source_row_ref": f"current:300803:{label.replace(':', '')}",
    }
    row.update(overrides)
    return row


def previous_day_c1_row(label: str, idx: int, **overrides):
    row = {
        "asset_kind": "stock",
        "identity_key": "stock:SZ:300803",
        "physical_c1_label": label,
        "open": 8.0 + idx / 100,
        "high": 8.2 + idx / 100,
        "low": 7.8 + idx / 100,
        "close": 8.1 + idx / 100,
        "amount": 800.0 + idx,
        "source_row_ref": f"previous:300803:{label.replace(':', '')}",
        "fake_or_synthetic_row": False,
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
        self.assertEqual(plan["source_label_semantics"], "source_label")
        self.assertEqual(plan["physical_label_semantics"], "start_label")
        self.assertEqual(plan["required_physical_labels"][0], "09:31")
        self.assertEqual(plan["required_physical_labels"][-1], "09:44")
        self.assertEqual(plan["required_raw_source_labels"][0], "09:31")
        self.assertEqual(plan["required_raw_source_labels"][-1], "09:44")
        self.assertEqual(len(plan["required_physical_labels"]), 14)
        self.assertEqual(len(plan["required_raw_source_labels"]), 14)
        self.assertEqual(plan["expected_rows_after_pull"], 840)
        self.assertEqual(plan["scope_count"], 60)
        self.assertEqual(len(plan["plan_rows"]), 60)
        self.assertEqual({row["asset_kind"] for row in plan["plan_rows"]}, {"stock", "board"})
        self.assertEqual({row["required_data_kind"] for row in plan["plan_rows"]}, {"minute_bar_1m"})
        self.assertTrue(all(row["source_label_policy"] == SOURCE_CLOSE_LABEL_POLICY for row in plan["plan_rows"]))
        self.assertTrue(all(row["required_raw_source_labels"][0] == "09:31" for row in plan["plan_rows"]))
        self.assertTrue(all(row["required_raw_source_labels"][-1] == "09:44" for row in plan["plan_rows"]))
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

    def test_object_granularity_pull_plan_dedupes_active_tracking_refs(self):
        scope = active_scope_artifact(
            artifact_schema_version="v2",
            scope_granularity="object",
            scope_rows=[active_object_scope_row()],
            scope_count=1,
        )

        plan = build_n3_c1_scoped_current_day_pull_plan(
            scope,
            target_minute_label="09:31",
            observed_at="2026-07-02T09:32:00+08:00",
        )

        self.assertEqual(plan["plan_status"], "planned")
        self.assertEqual(plan["scope_count"], 1)
        self.assertEqual(len(plan["plan_rows"]), 1)
        row = plan["plan_rows"][0]
        self.assertEqual(row["asset_kind"], "stock")
        self.assertEqual(row["identity_key"], "stock:SZ:300803")
        self.assertEqual(row["scope_status"], "active")
        self.assertNotIn("condition_key", row)
        self.assertEqual(
            {ref["condition_key"] for ref in row["active_tracking_refs"]},
            {"BUY_MAIN", "BUY_FULL"},
        )
        self.assertEqual(plan["expected_rows_after_pull"], 1)
        self.assertFalse(plan["n3_scans_n5_internals"])
        self.assertFalse(plan["side_effects"]["full_market_fallback_used"])

    def test_object_granularity_staging_and_metric_context_fan_out_active_tracking_refs(self):
        labels = c1_scoped_artifact.canonical_ashare_1m_labels(TRADE_DATE)
        target_index = labels.index("09:31")
        scope = active_scope_artifact(
            artifact_schema_version="v2",
            scope_granularity="object",
            scope_rows=[active_object_scope_row()],
            scope_count=1,
        )
        plan = build_n3_c1_scoped_current_day_pull_plan(
            scope,
            target_minute_label="09:31",
            observed_at="2026-07-02T09:32:00+08:00",
        )
        current_rows = [
            current_day_object_c1_row(label, idx)
            for idx, label in enumerate(plan["required_physical_labels"])
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
        previous_day_rows = [previous_day_c1_row(label, idx) for idx, label in enumerate(labels)]

        metric_source = build_n3_c1_n3t_metric_context_source_artifact(
            scope,
            staging_artifact=staging,
            previous_day_minute_rows=previous_day_rows,
            target_hhmm="0931",
            observed_at="2026-07-02T09:32:00+08:00",
        )
        artifact = build_n3_c1_scoped_artifact_plan(
            scope,
            target_minute_label="09:31",
            observed_at="2026-07-02T09:32:00+08:00",
            metric_context_rows=metric_source["metric_context_rows"],
        )

        self.assertEqual(staging["artifact_status"], "passed")
        self.assertEqual(staging["scope_count"], 1)
        self.assertEqual(staging["closed_minute_row_count"], 1)
        self.assertEqual(metric_source["artifact_status"], "planned")
        self.assertEqual(metric_source["metric_context_status"], "ready")
        self.assertEqual(metric_source["scope_count"], 2)
        self.assertEqual(metric_source["metric_context_count"], 2)
        self.assertEqual(
            {row["condition_key"] for row in metric_source["metric_context_rows"]},
            {"BUY_MAIN", "BUY_FULL"},
        )
        self.assertEqual(artifact["artifact_status"], "planned")
        self.assertEqual(artifact["metric_context_status"], "ready")
        self.assertEqual(artifact["scope_count"], 2)
        self.assertEqual(
            {row["condition_key"] for row in artifact["scope_rows"]},
            {"BUY_MAIN", "BUY_FULL"},
        )
        self.assertFalse(staging["writes_canonical_minute_bar_1m"])
        self.assertFalse(metric_source["writes_canonical_minute_bar_1m"])

    def test_object_minute_scope_metric_context_collapses_buy_and_hint_refs(self):
        labels = c1_scoped_artifact.canonical_ashare_1m_labels(TRADE_DATE)
        ordinary_ref = active_scope_row(
            condition_key="BUY:Y,M,W,D",
            source_trigger_event_id="n4-buy",
            source_trigger_event_type="TriggerMatched",
            source_trigger_event_time="2026-07-02T09:31:00+08:00",
        )
        hint_ref = active_scope_row(
            condition_key="BUY_HINT:Y,Q,M,W,D",
            source_trigger_event_id="n4-hint",
            source_trigger_event_type="TriggerMatched",
            source_trigger_event_time="2026-07-02T09:31:00+08:00",
        )
        scope = active_scope_artifact(
            artifact_schema_version="v2",
            scope_granularity="object",
            object_minute_scope=True,
            scope_rows=[active_object_scope_row(active_tracking_refs=[ordinary_ref, hint_ref])],
            scope_count=1,
        )
        plan = build_n3_c1_scoped_current_day_pull_plan(
            scope,
            target_minute_label="09:31",
            observed_at="2026-07-02T09:32:00+08:00",
        )
        current_rows = [
            current_day_object_c1_row(label, idx)
            for idx, label in enumerate(plan["required_physical_labels"])
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
        previous_day_rows = [previous_day_c1_row(label, idx) for idx, label in enumerate(labels)]

        metric_source = build_n3_c1_n3t_metric_context_source_artifact(
            scope,
            staging_artifact=staging,
            previous_day_minute_rows=previous_day_rows,
            target_hhmm="0931",
            observed_at="2026-07-02T09:32:00+08:00",
        )
        artifact = build_n3_c1_scoped_artifact_plan(
            scope,
            target_minute_label="09:31",
            observed_at="2026-07-02T09:32:00+08:00",
            metric_context_rows=metric_source["metric_context_rows"],
        )

        self.assertEqual(metric_source["metric_context_status"], "ready")
        self.assertEqual(metric_source["scope_count"], 1)
        self.assertEqual(metric_source["metric_context_count"], 1)
        context = metric_source["metric_context_rows"][0]
        self.assertEqual(context["condition_key"], "BUY:Y,M,W,D")
        self.assertTrue(context["object_minute_scope"])
        self.assertEqual(context["object_minute_ref_count"], 2)
        self.assertEqual(
            {ref["condition_key"] for ref in context["object_minute_ref_trace"]},
            {"BUY:Y,M,W,D", "BUY_HINT:Y,Q,M,W,D"},
        )
        self.assertEqual(artifact["metric_context_status"], "ready")
        self.assertEqual(artifact["scope_count"], 1)
        self.assertEqual(artifact["metric_context_count"], 1)
        n3t_plan = build_n3t_scoped_metric_from_c1_artifact_plan(artifact)
        self.assertEqual(n3t_plan["plan_status"], "planned")
        self.assertEqual(n3t_plan["scope_count"], 1)
        self.assertEqual(len(n3t_plan["metric_plan_rows"]), 1)
        self.assertEqual(n3t_plan["metric_plan_rows"][0]["object_minute_ref_count"], 2)

    def test_object_granularity_metric_context_allows_ref_without_source_trigger_run_id(self):
        labels = c1_scoped_artifact.canonical_ashare_1m_labels(TRADE_DATE)
        ref = active_scope_row(
            source_trigger_event_id="n4-match-without-run-id",
            source_trigger_run_id="",
        )
        scope = active_scope_artifact(
            artifact_schema_version="v2",
            scope_granularity="object",
            scope_rows=[active_object_scope_row(active_tracking_refs=[ref])],
            scope_count=1,
        )
        plan = build_n3_c1_scoped_current_day_pull_plan(
            scope,
            target_minute_label="09:31",
            observed_at="2026-07-02T09:32:00+08:00",
        )
        current_rows = [
            current_day_object_c1_row(label, idx)
            for idx, label in enumerate(plan["required_physical_labels"])
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
        previous_day_rows = [previous_day_c1_row(label, idx) for idx, label in enumerate(labels)]

        metric_source = build_n3_c1_n3t_metric_context_source_artifact(
            scope,
            staging_artifact=staging,
            previous_day_minute_rows=previous_day_rows,
            target_hhmm="0931",
            observed_at="2026-07-02T09:32:00+08:00",
        )

        self.assertEqual(metric_source["artifact_status"], "planned")
        self.assertEqual(metric_source["metric_context_status"], "ready")
        self.assertEqual(metric_source["metric_context_count"], 1)
        context = metric_source["metric_context_rows"][0]
        self.assertEqual(context["source_trigger_event_id"], "n4-match-without-run-id")
        self.assertEqual(context["source_trigger_run_id"], "")
        self.assertFalse(metric_source["writes_canonical_minute_bar_1m"])
        self.assertFalse(metric_source["writes_n3_outbox"])

    def test_source_label_policy_maps_close_labels_to_physical_start_labels(self):
        first = source_close_label_to_physical_start_label(TRADE_DATE, "09:31")
        target = source_close_label_to_physical_start_label(TRADE_DATE, "09:45")
        regular_current = source_close_label_to_physical_start_label(TRADE_DATE, "10:00")
        regular_source = source_close_label_for_physical_start_label(TRADE_DATE, "10:00")
        morning_close = source_close_label_for_physical_start_label(TRADE_DATE, "11:29")
        morning_close_from_mootdx_intraday = source_close_label_to_physical_start_label(TRADE_DATE, "13:00")
        afternoon_open = source_close_label_to_physical_start_label(TRADE_DATE, "13:00")
        regular_afternoon = source_close_label_to_physical_start_label(TRADE_DATE, "14:42")

        self.assertEqual(first["status"], "mapped")
        self.assertEqual(first["source_label_policy"], SOURCE_CLOSE_LABEL_POLICY)
        self.assertEqual(first["raw_source_label"], "09:31")
        self.assertEqual(first["physical_c1_label"], "09:31")
        self.assertEqual(target["status"], "mapped")
        self.assertEqual(target["raw_source_label"], "09:45")
        self.assertEqual(target["physical_c1_label"], "09:45")
        self.assertEqual(regular_current["status"], "mapped")
        self.assertEqual(regular_current["raw_source_label"], "10:00")
        self.assertEqual(regular_current["physical_c1_label"], "10:00")
        self.assertEqual(regular_source["status"], "mapped")
        self.assertEqual(regular_source["raw_source_label"], "10:00")
        self.assertEqual(regular_source["physical_c1_label"], "10:00")
        self.assertEqual(morning_close["status"], "mapped")
        self.assertEqual(morning_close["raw_source_label"], "11:29")
        self.assertEqual(morning_close["physical_c1_label"], "11:29")
        self.assertEqual(morning_close_from_mootdx_intraday["status"], "mapped")
        self.assertEqual(morning_close_from_mootdx_intraday["raw_source_label"], "13:00")
        self.assertEqual(morning_close_from_mootdx_intraday["physical_c1_label"], "13:00")
        self.assertEqual(afternoon_open["status"], "mapped")
        self.assertEqual(afternoon_open["raw_source_label"], "13:00")
        self.assertEqual(afternoon_open["physical_c1_label"], "13:00")
        self.assertEqual(regular_afternoon["raw_source_label"], "14:42")
        self.assertEqual(regular_afternoon["physical_c1_label"], "14:42")

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

        self.assertEqual(row["bar_time"], "2026-07-02T09:31:00+08:00")
        self.assertEqual(row["raw_source_bar_time"], "2026-07-02T09:31:00+08:00")
        self.assertEqual(row["raw_source_label"], "09:31")
        self.assertEqual(row["physical_c1_label"], "09:31")
        self.assertEqual(row["source_label_policy"], SOURCE_CLOSE_LABEL_POLICY)
        self.assertFalse(row["fake_or_synthetic_row"])
        self.assertEqual(row["raw_payload"]["provider_row_id"], "raw-0931")
        self.assertEqual(row["raw_payload"]["raw_source_label"], "09:31")
        self.assertEqual(row["raw_payload"]["physical_c1_label"], "09:31")

    def test_source_close_label_policy_maps_mootdx_intraday_1300_to_physical_1129(self):
        mapped = source_close_label_to_physical_start_label(TRADE_DATE, "13:00")

        self.assertEqual(mapped["status"], "mapped")
        self.assertIsNone(mapped["reason"])
        self.assertEqual(mapped["raw_source_label"], "13:00")
        self.assertEqual(mapped["physical_c1_label"], "13:00")
        self.assertEqual(mapped["source_label_policy"], SOURCE_CLOSE_LABEL_POLICY)

    def test_source_label_plan_includes_real_morning_close_without_fake_row(self):
        plan = build_source_close_label_plan_for_target_minute(
            for_trade_date=TRADE_DATE,
            target_minute_label="13:01",
        )

        self.assertEqual(plan["status"], "planned")
        self.assertEqual(plan["source_label_policy"], SOURCE_CLOSE_LABEL_POLICY)
        self.assertEqual(plan["source_gap_policy"], "session_boundary_source_gap_excluded_v1")
        self.assertNotIn("11:30", plan["required_raw_source_labels"])
        self.assertIn("13:00", plan["required_raw_source_labels"])
        self.assertIn("13:01", plan["required_raw_source_labels"])
        self.assertIn("11:29", plan["required_physical_labels"])
        self.assertIn("13:00", plan["required_physical_labels"])
        self.assertIn("13:01", plan["required_physical_labels"])
        self.assertEqual(plan["source_gap_physical_labels"], [])

    def test_source_label_policy_accepts_mootdx_raw_1130_as_physical_1300(self):
        mapped = source_close_label_to_physical_start_label(TRADE_DATE, "11:30")

        self.assertEqual(mapped["status"], "mapped")
        self.assertIsNone(mapped["reason"])
        self.assertEqual(mapped["raw_source_label"], "11:30")
        self.assertEqual(mapped["physical_c1_label"], "13:00")
        self.assertEqual(mapped["source_label_policy"], SOURCE_CLOSE_LABEL_POLICY)

    def test_source_close_label_policy_preserves_mootdx_raw_1130_trace_without_fake_row(self):
        source_row = {
            "bar_time": "2026-07-02T11:30:00+08:00",
            "open": 10,
            "close": 11,
            "raw_payload": {"provider_row_id": "raw-1130"},
        }

        row = apply_source_close_label_policy_to_row(source_row, for_trade_date=TRADE_DATE)

        self.assertEqual(row["bar_time"], "2026-07-02T13:00:00+08:00")
        self.assertEqual(row["raw_source_bar_time"], "2026-07-02T11:30:00+08:00")
        self.assertEqual(row["raw_source_label"], "11:30")
        self.assertEqual(row["physical_c1_label"], "13:00")
        self.assertEqual(row["source_label_policy"], SOURCE_CLOSE_LABEL_POLICY)
        self.assertFalse(row["fake_or_synthetic_row"])
        self.assertEqual(row["raw_payload"]["provider_row_id"], "raw-1130")
        self.assertEqual(row["raw_payload"]["raw_source_label"], "11:30")
        self.assertEqual(row["raw_payload"]["physical_c1_label"], "13:00")

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
        self.assertIn("13:00", plan["required_raw_source_labels"])
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
        labels = c1_scoped_artifact.canonical_ashare_1m_labels(TRADE_DATE)
        target_index = labels.index("09:52")
        current_rows = [
            current_day_c1_row(label, idx)
            for idx, label in enumerate(labels[: target_index + 1])
        ]
        for row in current_rows:
            if row["physical_c1_label"] == "09:50":
                row.update(open=10.8, high=11.2, low=10.6, close=11.0, amount=900.0)
            if row["physical_c1_label"] == "09:51":
                row.update(open=11.0, high=12.3, low=10.8, close=12.0, amount=1000.0)
            if row["physical_c1_label"] == "09:52":
                row.update(open=12.0, high=12.8, low=11.7, close=12.5, amount=1500.0)
        previous_day_rows = [
            previous_day_c1_row(label, idx)
            for idx, label in enumerate(labels)
        ]
        staging_artifact = {
            "artifact_type": "n3_c1_scoped_current_day_staging_v1",
            "artifact_status": "passed",
            "for_trade_date": TRADE_DATE,
            "scope_count": 1,
            "closed_minute_row_count": len(current_rows),
            "closed_minute_rows": current_rows,
            "database_written": False,
            "market_data_pulled": True,
            "writes_canonical_minute_bar_1m": False,
            "writes_n3_outbox": False,
            "full_market_fallback_used": False,
        }

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
        self.assertIn("current:300803:0950", context["source_closed_minute_bar_ids"])
        self.assertIn("current:300803:0951", context["source_closed_minute_bar_ids"])
        self.assertIn("current:300803:0952", context["source_closed_minute_bar_ids"])
        self.assertIn("previous:300803:0951", context["previous_day_minute_refs"])
        self.assertIn("previous:300803:0952", context["previous_day_minute_refs"])
        self.assertEqual(context["metric_values"]["current_price"], 12.5)
        self.assertEqual(context["metric_values"]["current_1m_amount"], 1500.0)
        self.assertIsNotNone(context["metric_values"]["current_5m_amount"])
        self.assertEqual(
            context["metric_values"]["current_30m_closed_elapsed_amount"],
            sum(row["amount"] for row in current_rows if row["physical_c1_label"] != "09:30"),
        )
        self.assertEqual(context["metric_values"]["previous_1m_amount"], 1000.0)
        self.assertEqual(context["metric_values"]["previous_1m_period_source"], "same_trade_date_previous_period")
        self.assertEqual(context["metric_values"]["previous_5m_period_source"], "same_trade_date_previous_period")
        self.assertEqual(context["metric_values"]["previous_30m_period_source"], "previous_trade_date_last_period")
        self.assertEqual(context["metric_values"]["previous_120m_period_source"], "previous_trade_date_last_period")
        self.assertEqual(
            context["deterministic_derivation_inputs"]["previous_day_same_window_amount_source"],
            "scoped_previous_day_raw_c1_sum",
        )

    def test_metric_context_uses_raw_1000_as_current_bar_for_regular_morning_minute(self):
        labels = c1_scoped_artifact.canonical_ashare_1m_labels("20260708")
        target_index = labels.index("10:00")
        scope_row = active_scope_row(
            for_trade_date="20260708",
            identity_key="stock:SZ:300144",
            condition_key="BUY:Y,Q,M,W,D",
            source_trigger_event_id="n4-match-300144",
            source_trigger_run_id="n4-trigger-300144",
        )
        current_rows = [
            {
                **scope_row,
                "physical_c1_label": label,
                "raw_source_label": source_close_label_for_physical_start_label("20260708", label)["raw_source_label"],
                "open": 5.8,
                "high": 5.9,
                "low": 5.7,
                "close": 5.85,
                "amount": 1000 + idx,
                "source_row_ref": f"current:300144:{label.replace(':', '')}",
                "fake_or_synthetic_row": False,
            }
            for idx, label in enumerate(labels[: target_index + 1])
        ]
        for row in current_rows:
            if row["physical_c1_label"] == "09:55":
                row.update(open=6.07, high=6.08, low=6.06, close=6.06, amount=7932308)
            if row["physical_c1_label"] == "09:56":
                row.update(open=6.06, high=6.10, low=6.06, close=6.09, amount=12042610)
            if row["physical_c1_label"] == "09:57":
                row.update(open=6.10, high=6.12, low=6.10, close=6.12, amount=9038441)
            if row["physical_c1_label"] == "09:58":
                row.update(open=6.12, high=6.12, low=6.10, close=6.10, amount=6995836)
            if row["physical_c1_label"] == "09:59":
                row.update(open=6.11, high=6.11, low=6.08, close=6.08, amount=6462602)
            if row["physical_c1_label"] == "10:00":
                row.update(open=6.09, high=6.15, low=6.08, close=6.15, amount=16042877)
        previous_day_rows = [
            {
                "asset_kind": "stock",
                "identity_key": "stock:SZ:300144",
                "physical_c1_label": label,
                "open": 5.0,
                "high": 5.5,
                "low": 4.9,
                "close": 5.2,
                "amount": 800,
                "source_row_ref": f"previous:300144:{label.replace(':', '')}",
                "fake_or_synthetic_row": False,
            }
            for label in labels
        ]
        staging_artifact = {
            "artifact_type": "n3_c1_scoped_current_day_staging_v1",
            "artifact_status": "passed",
            "for_trade_date": "20260708",
            "scope_count": 1,
            "closed_minute_row_count": len(current_rows),
            "closed_minute_rows": current_rows,
            "database_written": False,
            "market_data_pulled": True,
            "writes_canonical_minute_bar_1m": False,
            "writes_n3_outbox": False,
            "full_market_fallback_used": False,
        }

        artifact = build_n3_c1_n3t_metric_context_source_artifact(
            active_scope_artifact(for_trade_date="20260708", scope_rows=[scope_row]),
            staging_artifact=staging_artifact,
            previous_day_minute_rows=previous_day_rows,
            target_hhmm="1000",
            observed_at="2026-07-08T10:01:00+08:00",
        )

        metric_values = artifact["metric_context_rows"][0]["metric_values"]
        self.assertEqual(artifact["metric_context_status"], "ready")
        self.assertEqual(current_rows[-1]["physical_c1_label"], "10:00")
        self.assertEqual(current_rows[-1]["raw_source_label"], "10:00")
        self.assertEqual(metric_values["current_price"], 6.15)
        self.assertEqual(metric_values["current_1m_amount"], 16042877.0)
        self.assertEqual(metric_values["previous_1m_amount"], 6462602.0)
        self.assertEqual(metric_values["previous_1m_body_high"], 6.11)
        self.assertEqual(metric_values["current_5m_amount"], 50582366.0)
        self.assertEqual(metric_values["current_5m_elapsed_amount"], 50582366.0)
        self.assertEqual(metric_values["previous_5m_amount"], 7936398.0)

    def test_metric_context_uses_fixed_periods_for_000688_20260720_1450(self):
        source_artifact_sha256 = "32e2c44f6e33ed386aac06319c0f801850b239df84dff992ec6b24523c86fd59"
        labels = [
            label
            for label in c1_scoped_artifact.canonical_ashare_1m_labels("20260720")
            if label != "09:30" and label <= "14:50"
        ]
        current_rows = [
            {
                "for_trade_date": "20260720",
                "asset_kind": "index",
                "identity_key": "index:SH:000688",
                "physical_c1_label": label,
                "raw_source_label": label,
                "open": 1700.0,
                "close": 1700.0,
                "amount": 100.0,
                "source_row_ref": f"fixture:{source_artifact_sha256}:{label}",
                "fake_or_synthetic_row": False,
            }
            for label in labels
        ]
        rows_by_label = {row["physical_c1_label"]: row for row in current_rows}
        rows_by_label["09:31"].update(open=1764.593, close=1754.868)
        rows_by_label["13:00"].update(open=1713.161, close=1712.121)
        rows_by_label["14:01"].update(open=1663.027)
        rows_by_label["14:30"].update(close=1662.847)
        rows_by_label["14:41"].update(open=1664.568, amount=1_000_000_000)
        rows_by_label["14:42"].update(amount=1_000_000_000)
        rows_by_label["14:43"].update(amount=1_000_000_000)
        rows_by_label["14:44"].update(amount=1_000_000_000)
        rows_by_label["14:45"].update(close=1695.061, amount=1_425_289_024)
        rows_by_label["14:46"].update(amount=1_490_729_216)
        rows_by_label["14:47"].update(amount=1_000_000_000)
        rows_by_label["14:48"].update(amount=1_000_000_000)
        rows_by_label["14:49"].update(open=1709.527, close=1701.758, amount=1_090_295_296)
        rows_by_label["14:50"].update(open=1711.055, close=1724.515, amount=1_901_952_384)
        previous_rows = [
            {
                "asset_kind": "index",
                "identity_key": "index:SH:000688",
                "physical_c1_label": label,
                "raw_source_label": source_close_label_for_physical_start_label("20260717", label)["raw_source_label"],
                "open": 1700.0,
                "close": 1700.0,
                "amount": 100.0,
                "source_row_ref": f"previous:index:SH:000688:{label}",
                "fake_or_synthetic_row": False,
            }
            for label in c1_scoped_artifact.canonical_ashare_1m_labels("20260717")[-30:]
        ]

        metric_values = c1_scoped_artifact._derive_metric_values(
            current_rows=current_rows,
            previous_rows=previous_rows,
        )

        self.assertEqual(metric_values["current_price"], 1724.515)
        self.assertEqual(metric_values["previous_120m_body_high"], 1764.593)
        self.assertEqual(metric_values["previous_120m_body_low"], 1712.121)
        self.assertEqual(metric_values["previous_30m_body_high"], 1663.027)
        self.assertEqual(metric_values["previous_30m_body_low"], 1662.847)
        self.assertEqual(metric_values["previous_5m_body_high"], 1695.061)
        self.assertEqual(metric_values["previous_5m_body_low"], 1664.568)
        self.assertEqual(metric_values["previous_1m_body_high"], 1709.527)
        self.assertEqual(metric_values["previous_1m_body_low"], 1701.758)
        self.assertEqual(metric_values["previous_5m_amount"], 5_425_289_024)
        self.assertEqual(metric_values["current_5m_amount"], 6_482_976_896)
        self.assertFalse(metric_values["current_price"] > metric_values["previous_120m_body_high"])

    def test_fixed_period_lunch_layout_maps_intraday_and_postclose_rows(self):
        intraday = c1_scoped_artifact._fixed_period_row_index(
            [
                {"physical_c1_label": "13:00", "raw_source_label": "13:00", "source_row_ref": "intraday:morning-close"},
                {"physical_c1_label": "13:01", "raw_source_label": "13:01", "source_row_ref": "intraday:afternoon-first"},
            ]
        )
        postclose = c1_scoped_artifact._fixed_period_row_index(
            [
                {"physical_c1_label": "13:00", "raw_source_label": "11:30", "source_row_ref": "postclose:morning-close"},
                {"physical_c1_label": "13:00", "raw_source_label": "13:00", "source_row_ref": "postclose:afternoon-first"},
            ]
        )

        self.assertEqual(intraday[120]["source_row_ref"], "intraday:morning-close")
        self.assertEqual(intraday[121]["source_row_ref"], "intraday:afternoon-first")
        self.assertEqual(postclose[120]["source_row_ref"], "postclose:morning-close")
        self.assertEqual(postclose[121]["source_row_ref"], "postclose:afternoon-first")

    def test_fixed_period_preload_close_label_slice_uses_ordinals_through_240(self):
        morning_labels = [f"09:{minute:02d}" for minute in range(31, 60)]
        afternoon_labels = [
            f"{hour:02d}:{minute:02d}"
            for hour in (13, 14)
            for minute in range(60)
        ]
        previous_rows = [
            {
                "asset_kind": asset_kind,
                "identity_key": f"{asset_kind}:fixture:fixed-period",
                "physical_c1_label": label,
                "raw_source_label": (
                    label if label.startswith("09:") else c1_scoped_artifact._next_hhmm_label(label)
                ),
                "open": 100.0,
                "close": 101.0,
                "amount": 1000.0,
                "source_row_ref": (
                    f"{LIVE_20260721_PREVIOUS_CONTEXT_ARTIFACT_SHA256}:{asset_kind}:{label}"
                ),
            }
            for asset_kind in ("stock", "index", "board")
            for label in [*morning_labels, *afternoon_labels]
        ]
        current_row = {
            "physical_c1_label": "09:31",
            "raw_source_label": "09:31",
            "for_trade_date": "20260721",
        }

        for asset_kind in ("stock", "index", "board"):
            asset_rows = [row for row in previous_rows if row["asset_kind"] == asset_kind]
            indexed = c1_scoped_artifact._fixed_period_row_index(asset_rows)
            resolved = c1_scoped_artifact.resolve_fixed_period_windows(
                current_rows=[current_row],
                previous_rows=asset_rows,
            )

            self.assertEqual(len(asset_rows), 149)
            self.assertEqual(max(indexed), 240)
            self.assertEqual(
                {
                    size: [row["physical_c1_label"] for row in resolved["previous_period_rows"][size]]
                    for size in (1, 5, 30, 120)
                },
                {
                    1: ["14:59"],
                    5: [f"14:{minute:02d}" for minute in range(55, 60)],
                    30: [f"14:{minute:02d}" for minute in range(30, 60)],
                    120: afternoon_labels,
                },
            )
            self.assertTrue(
                all(
                    source == "previous_trade_date_last_period"
                    for source in resolved["previous_period_sources"].values()
                )
            )

    def test_fixed_period_preload_close_label_slice_does_not_treat_1129_raw_1130_as_postclose(self):
        morning_labels = [f"{hour:02d}:{minute:02d}" for hour in (10, 11) for minute in range(60)]
        morning_labels = [label for label in morning_labels if "10:30" <= label <= "11:29"]
        afternoon_labels = [
            f"{hour:02d}:{minute:02d}"
            for hour in (13, 14)
            for minute in range(60)
        ]
        previous_rows = [
            {
                "asset_kind": "index",
                "identity_key": "index:SZ:399006",
                "physical_c1_label": label,
                "raw_source_label": c1_scoped_artifact._next_hhmm_label(label),
                "open": 100.0,
                "close": 101.0,
                "amount": 1000.0,
                "source_row_ref": f"preload-close-label:{label}",
            }
            for label in [*morning_labels, *afternoon_labels]
        ]
        current_rows = [
            {
                "for_trade_date": "20260721",
                "physical_c1_label": label,
                "raw_source_label": label,
                "open": 101.0,
                "close": 102.0,
                "amount": 1000.0,
                "source_row_ref": f"current:{label}",
            }
            for label in c1_scoped_artifact.canonical_ashare_1m_labels("20260721")[:86]
        ]

        indexed = c1_scoped_artifact._fixed_period_row_index(previous_rows)
        resolved = c1_scoped_artifact.resolve_fixed_period_windows(
            current_rows=current_rows,
            previous_rows=previous_rows,
        )

        self.assertEqual(len(previous_rows), 180)
        self.assertEqual((min(indexed), max(indexed)), (60, 240))
        self.assertEqual(resolved["status"], "ready")
        self.assertTrue(
            all(
                source in {
                    "same_trade_date_previous_period",
                    "previous_trade_date_last_period",
                }
                for source in resolved["previous_period_sources"].values()
            )
        )
        self.assertEqual(
            [row["physical_c1_label"] for row in resolved["previous_period_rows"][120]],
            afternoon_labels,
        )

    def test_fixed_period_preload_slice_fails_closed_for_missing_or_ambiguous_afternoon_row(self):
        afternoon_labels = [
            f"{hour:02d}:{minute:02d}"
            for hour in (13, 14)
            for minute in range(60)
        ]
        previous_rows = [
            {
                "physical_c1_label": label,
                "raw_source_label": c1_scoped_artifact._next_hhmm_label(label),
                "open": 100.0,
                "close": 101.0,
                "amount": 1000.0,
                "source_row_ref": f"preload:{label}",
            }
            for label in afternoon_labels
        ]
        current_row = {
            "physical_c1_label": "09:31",
            "raw_source_label": "09:31",
            "for_trade_date": "20260721",
        }

        missing = c1_scoped_artifact.resolve_fixed_period_windows(
            current_rows=[current_row],
            previous_rows=[row for row in previous_rows if row["physical_c1_label"] != "14:58"],
        )
        self.assertEqual(missing["previous_period_rows"][120], [])
        self.assertEqual(missing["previous_period_sources"][120], "not_available")

        ambiguous = c1_scoped_artifact.resolve_fixed_period_windows(
            current_rows=[current_row],
            previous_rows=[
                *previous_rows,
                {
                    "physical_c1_label": "13:00",
                    "raw_source_label": "13:00",
                    "source_row_ref": "ambiguous:13:00",
                },
            ],
        )
        self.assertEqual(ambiguous["status"], "not_available")
        self.assertTrue(all(not rows for rows in ambiguous["previous_period_rows"].values()))

    def test_fixed_period_index_rejects_generic_duplicate_normalized_ordinal(self):
        with self.assertRaisesRegex(ValueError, "duplicate normalized fixed-period ordinal"):
            c1_scoped_artifact._fixed_period_row_index(
                [
                    {"physical_c1_label": "09:52", "raw_source_label": "09:52", "source_row_ref": "first"},
                    {"physical_c1_label": "09:52", "raw_source_label": "09:52", "source_row_ref": "duplicate"},
                ]
            )

    def test_fixed_period_index_prefers_contract_close_boundary_raw_1500(self):
        indexed = c1_scoped_artifact._fixed_period_row_index(
            [
                {
                    "asset_kind": "stock",
                    "identity_key": "stock:SZ:300803",
                    "physical_c1_label": "14:59",
                    "raw_source_label": "14:59",
                    "source_row_ref": "close:1459",
                },
                {
                    "asset_kind": "stock",
                    "identity_key": "stock:SZ:300803",
                    "physical_c1_label": "14:59",
                    "raw_source_label": "15:00",
                    "source_row_ref": "close:1500",
                },
            ]
        )

        self.assertEqual(indexed[max(indexed)]["source_row_ref"], "close:1500")

    def test_unified_minute_axis_excludes_non_calculation_labels(self):
        labels = c1_scoped_artifact.FIXED_PERIOD_CALCULATION_LABELS

        self.assertEqual(labels[0], "09:31")
        self.assertNotIn("09:30", labels)
        self.assertNotIn("11:30", labels)
        self.assertEqual(
            labels[labels.index("11:28") : labels.index("13:01") + 1],
            ("11:28", "11:29", "13:00", "13:01"),
        )
        self.assertEqual(len(labels), 239)

    def test_300613_lunch_gap_uses_physical_same_window_and_complete_previous_120m(self):
        for_trade_date = "20260727"
        identity_key = "stock:SZ:300613"
        axis = c1_scoped_artifact.FIXED_PERIOD_CALCULATION_LABELS
        previous_rows = [
            {
                "asset_kind": "stock",
                "identity_key": identity_key,
                "physical_c1_label": label,
                "raw_source_label": (
                    "11:30"
                    if label == "11:29"
                    else (
                        c1_scoped_artifact._next_hhmm_label(label)
                        if label >= "13:00"
                        else label
                    )
                ),
                "open": 10.0,
                "close": 10.1,
                "amount": 1000.0,
                "source_row_ref": f"previous:{identity_key}:{label}",
            }
            for label in axis
        ]

        for target_label in ("11:26", "11:27", "11:28", "11:29", "13:00"):
            position = axis.index(target_label) + 1
            current_rows = [
                {
                    "for_trade_date": for_trade_date,
                    "asset_kind": "stock",
                    "identity_key": identity_key,
                    "physical_c1_label": label,
                    "raw_source_label": label,
                    "open": 11.0,
                    "close": 11.1,
                    "amount": 1200.0,
                    "source_row_ref": f"current:{identity_key}:{label}",
                }
                for label in axis[:position]
            ]
            required_labels = c1_scoped_artifact.required_previous_day_metric_context_labels(
                labels=c1_scoped_artifact.canonical_ashare_1m_labels(for_trade_date),
                current_labels={row["physical_c1_label"] for row in current_rows},
            )
            scoped_previous_rows = [
                row for row in previous_rows if row["physical_c1_label"] in required_labels
            ]
            windows = c1_scoped_artifact.resolve_fixed_period_windows(
                current_rows=current_rows,
                previous_rows=scoped_previous_rows,
            )
            metric_values = c1_scoped_artifact._derive_metric_values(
                current_rows=current_rows,
                previous_rows=scoped_previous_rows,
            )

            self.assertEqual(windows["status"], "ready", target_label)
            self.assertEqual(
                [
                    row["physical_c1_label"]
                    for row in windows["previous_day_same_period_rows"][5]
                ],
                ["11:26", "11:27", "11:28", "11:29", "13:00"],
                target_label,
            )
            self.assertEqual(len(windows["previous_period_rows"][120]), 120, target_label)
            self.assertEqual(
                windows["previous_period_sources"][120],
                c1_scoped_artifact.PREVIOUS_TRADE_DATE_LAST_PERIOD,
                target_label,
            )
            self.assertIsNotNone(metric_values["current_5m_amount"], target_label)

        target_label = "11:26"
        position = axis.index(target_label) + 1
        scope_row = active_scope_row(
            for_trade_date=for_trade_date,
            identity_key=identity_key,
            direction="sell",
            signal_type="S_SELL",
            condition_key="SELL:Y,D",
            source_trigger_event_id="n4-match-300613",
            source_trigger_run_id="n4-trigger-300613",
        )
        current_rows = [
            {
                **scope_row,
                "physical_c1_label": label,
                "raw_source_label": label,
                "open": 11.0,
                "close": 11.1,
                "amount": 1200.0,
                "source_row_ref": f"current:{identity_key}:{label}",
                "fake_or_synthetic_row": False,
            }
            for label in axis[:position]
        ]
        required_labels = c1_scoped_artifact.required_previous_day_metric_context_labels(
            labels=c1_scoped_artifact.canonical_ashare_1m_labels(for_trade_date),
            current_labels=set(axis[:position]),
        )
        scoped_previous_rows = [
            row for row in previous_rows if row["physical_c1_label"] in required_labels
        ]
        scope = active_scope_artifact(
            for_trade_date=for_trade_date,
            scope_rows=[scope_row],
        )
        staging = {
            "artifact_type": "n3_c1_scoped_current_day_staging_v1",
            "artifact_status": "passed",
            "for_trade_date": for_trade_date,
            "closed_minute_rows": current_rows,
            "market_data_pulled": True,
            "writes_canonical_minute_bar_1m": False,
            "writes_n3_outbox": False,
            "full_market_fallback_used": False,
        }
        metric_source = build_n3_c1_n3t_metric_context_source_artifact(
            scope,
            staging_artifact=staging,
            previous_day_minute_rows=scoped_previous_rows,
            target_hhmm="1126",
            observed_at="2026-07-27T11:27:00+08:00",
        )
        scoped_plan = build_n3_c1_scoped_artifact_plan(
            scope,
            target_minute_label=target_label,
            observed_at="2026-07-27T11:27:00+08:00",
            metric_context_rows=metric_source["metric_context_rows"],
        )
        n3t_plan = build_n3t_scoped_metric_from_c1_artifact_plan(scoped_plan)

        self.assertEqual(metric_source["metric_context_status"], "ready")
        self.assertEqual(scoped_plan["metric_context_status"], "ready")
        self.assertEqual(n3t_plan["plan_status"], "planned")
        self.assertEqual(len(n3t_plan["metric_plan_rows"]), 1)

    def test_fixed_period_source_query_covers_all_targets_and_asset_kinds(self):
        for_trade_date = "20260727"
        canonical_labels = c1_scoped_artifact.canonical_ashare_1m_labels(for_trade_date)
        axis = c1_scoped_artifact.FIXED_PERIOD_CALCULATION_LABELS

        for asset_kind in ("stock", "index", "board"):
            identity_key = f"{asset_kind}:fixture:unified-axis"
            previous_rows = [
                {
                    "asset_kind": asset_kind,
                    "identity_key": identity_key,
                    "physical_c1_label": label,
                    "raw_source_label": (
                        "11:30"
                        if label == "11:29"
                        else (
                            c1_scoped_artifact._next_hhmm_label(label)
                            if label >= "13:00"
                            else label
                        )
                    ),
                    "open": 100.0,
                    "close": 101.0,
                    "amount": 1000.0,
                    "source_row_ref": f"previous:{identity_key}:{label}",
                }
                for label in axis
            ]
            for position, target_label in enumerate(axis, start=1):
                current_rows = [
                    {
                        "for_trade_date": for_trade_date,
                        "asset_kind": asset_kind,
                        "identity_key": identity_key,
                        "physical_c1_label": label,
                        "raw_source_label": label,
                        "open": 101.0,
                        "close": 102.0,
                        "amount": 1100.0,
                        "source_row_ref": f"current:{identity_key}:{label}",
                    }
                    for label in axis[:position]
                ]
                required_labels = c1_scoped_artifact.required_previous_day_metric_context_labels(
                    labels=canonical_labels,
                    current_labels=set(axis[:position]),
                )
                scoped_previous_rows = [
                    row for row in previous_rows if row["physical_c1_label"] in required_labels
                ]
                windows = c1_scoped_artifact.resolve_fixed_period_windows(
                    current_rows=current_rows,
                    previous_rows=scoped_previous_rows,
                )
                metric_values = c1_scoped_artifact._derive_metric_values(
                    current_rows=current_rows,
                    previous_rows=scoped_previous_rows,
                )

                self.assertEqual(windows["status"], "ready", (asset_kind, target_label))
                self.assertTrue(
                    all(
                        len(windows["previous_period_rows"][size]) == size
                        for size in (1, 5, 30, 120)
                    ),
                    (asset_kind, target_label),
                )
                self.assertTrue(
                    all(
                        metric_values.get(field) is not None
                        for field in c1_scoped_artifact.REQUIRED_METRIC_CONTEXT_FIELDS
                    ),
                    (asset_kind, target_label),
                )

    def test_intraday_and_postclose_current_rows_share_calculation_axis(self):
        axis = c1_scoped_artifact.FIXED_PERIOD_CALCULATION_LABELS
        intraday_rows = [
            {
                "for_trade_date": "20260727",
                "physical_c1_label": label,
                "raw_source_label": label,
                "open": 100.0,
                "close": 101.0,
                "amount": 1000.0,
                "source_row_ref": f"intraday:{label}",
            }
            for label in axis
        ]
        postclose_rows = [
            *intraday_rows,
            {
                **next(row for row in intraday_rows if row["physical_c1_label"] == "13:00"),
                "raw_source_label": "11:30",
                "source_row_ref": "postclose:11:30",
            },
            {
                **next(row for row in intraday_rows if row["physical_c1_label"] == "14:59"),
                "raw_source_label": "15:00",
                "source_row_ref": "postclose:15:00",
            },
        ]

        intraday_index = c1_scoped_artifact.fixed_period_calculation_row_index(
            intraday_rows
        )
        postclose_index = c1_scoped_artifact.fixed_period_calculation_row_index(
            postclose_rows
        )

        self.assertEqual(tuple(intraday_index), tuple(range(1, 240)))
        self.assertEqual(tuple(postclose_index), tuple(range(1, 240)))
        self.assertEqual(postclose_index[120]["raw_source_label"], "13:00")
        self.assertEqual(postclose_index[239]["raw_source_label"], "15:00")

    def test_metric_context_reports_exact_same_window_missing_stage(self):
        scope_row = active_scope_row()
        staging = {
            "artifact_type": "n3_c1_scoped_current_day_staging_v1",
            "artifact_status": "passed",
            "for_trade_date": TRADE_DATE,
            "closed_minute_rows": [current_day_c1_row("09:31", 1)],
            "market_data_pulled": True,
            "writes_canonical_minute_bar_1m": False,
            "writes_n3_outbox": False,
            "full_market_fallback_used": False,
        }
        metric_values = dict(metric_context_row()["metric_values"])
        metric_values["current_5m_amount"] = None

        with patch.object(
            c1_scoped_artifact,
            "_derive_metric_values",
            return_value=metric_values,
        ):
            artifact = build_n3_c1_n3t_metric_context_source_artifact(
                active_scope_artifact(scope_rows=[scope_row]),
                staging_artifact=staging,
                previous_day_minute_rows=[previous_day_c1_row("14:59", 1)],
                target_hhmm="0931",
                observed_at="2026-07-02T09:32:00+08:00",
            )

        self.assertEqual(artifact["artifact_status"], "blocked")
        self.assertEqual(
            artifact["blocked_reason"],
            c1_scoped_artifact.BLOCKED_N3T_CURRENT_5M_SAME_WINDOW_SOURCE_MISSING,
        )
        self.assertEqual(
            artifact["blocked_stage"],
            "current_5m_same_window_source_missing",
        )
        self.assertEqual(artifact["missing_metric_fields"], ["current_5m_amount"])

    def test_metric_context_uses_target_raw_1442_not_next_raw_1443_for_regular_afternoon_minute(self):
        labels = c1_scoped_artifact.canonical_ashare_1m_labels("20260708")
        target_index = labels.index("14:43")
        scope_row = active_scope_row(
            for_trade_date="20260708",
            identity_key="stock:SH:600350",
            condition_key="BUY:Y,M,W,D",
            source_trigger_event_id="n4-match-600350",
            source_trigger_run_id="n4-trigger-600350",
        )
        current_rows = [
            {
                **scope_row,
                "physical_c1_label": label,
                "raw_source_label": source_close_label_for_physical_start_label("20260708", label)["raw_source_label"],
                "open": 12.5,
                "high": 12.5,
                "low": 12.5,
                "close": 12.5,
                "amount": 1000.0 + idx,
                "source_row_ref": f"current:600350:{label.replace(':', '')}",
                "fake_or_synthetic_row": False,
            }
            for idx, label in enumerate(labels[: target_index + 1])
        ]
        for row in current_rows:
            if row["physical_c1_label"] == "14:41":
                row.update(open=12.65, high=12.67, low=12.65, close=12.67, amount=1629637.0)
            if row["physical_c1_label"] == "14:42":
                row.update(open=12.67, high=12.69, low=12.66, close=12.69, amount=1505872.0)
            if row["physical_c1_label"] == "14:43":
                row.update(open=12.68, high=12.70, low=12.68, close=12.70, amount=2025526.0)
        previous_day_rows = [
            {
                "asset_kind": "stock",
                "identity_key": "stock:SH:600350",
                "physical_c1_label": label,
                "open": 11.0,
                "high": 11.2,
                "low": 10.8,
                "close": 11.1,
                "amount": 800,
                "source_row_ref": f"previous:600350:{label.replace(':', '')}",
                "fake_or_synthetic_row": False,
            }
            for label in labels
        ]
        staging_artifact = {
            "artifact_type": "n3_c1_scoped_current_day_staging_v1",
            "artifact_status": "passed",
            "for_trade_date": "20260708",
            "scope_count": 1,
            "closed_minute_row_count": len(current_rows),
            "closed_minute_rows": current_rows,
            "database_written": False,
            "market_data_pulled": True,
            "writes_canonical_minute_bar_1m": False,
            "writes_n3_outbox": False,
            "full_market_fallback_used": False,
        }

        artifact = build_n3_c1_n3t_metric_context_source_artifact(
            active_scope_artifact(for_trade_date="20260708", scope_rows=[scope_row]),
            staging_artifact=staging_artifact,
            previous_day_minute_rows=previous_day_rows,
            target_hhmm="1442",
            observed_at="2026-07-08T14:43:00+08:00",
        )

        metric_values = artifact["metric_context_rows"][0]["metric_values"]
        closed_rows = artifact["metric_context_rows"][0]["closed_minute_rows"]
        self.assertEqual(artifact["metric_context_status"], "ready")
        self.assertEqual(closed_rows[-1]["physical_c1_label"], "14:42")
        self.assertEqual(closed_rows[-1]["raw_source_label"], "14:42")
        self.assertEqual(metric_values["current_price"], 12.69)
        self.assertEqual(metric_values["current_1m_amount"], 1505872.0)
        self.assertEqual(metric_values["previous_1m_amount"], 1629637.0)
        self.assertEqual(metric_values["previous_1m_body_high"], 12.67)

    def test_mootdx_c1_physical_normalizer_keeps_regular_raw_label_current(self):
        rows = normalize_c1_physical_intraday_1m_labels(
            [
                {
                    "bar_time": "2026-07-08 09:31",
                    "open": 22.03,
                    "high": 22.12,
                    "low": 21.99,
                    "close": 22.0,
                    "amount": 3428079.0,
                }
            ],
            trade_date="20260708",
            intraday_trade_date="20260708",
            source_adapter="mootdx",
        )

        self.assertEqual(rows[0]["physical_c1_label"], "09:31")
        self.assertEqual(rows[0]["raw_source_label"], "09:31")

    def test_mootdx_c1_physical_normalizer_keeps_1129_and_maps_post_close_1130_to_1300(self):
        rows = normalize_c1_physical_intraday_1m_labels(
            [
                {
                    "bar_time": "2026-07-08 11:29",
                    "open": 5.99,
                    "high": 6.0,
                    "low": 5.99,
                    "close": 6.0,
                    "amount": 173336.0,
                },
                {
                    "bar_time": "2026-07-08 11:30",
                    "open": 6.0,
                    "high": 6.0,
                    "low": 5.99,
                    "close": 5.99,
                    "amount": 450360.0,
                },
            ],
            trade_date="20260708",
            intraday_trade_date="20260708",
            source_adapter="mootdx",
        )

        self.assertEqual(len(rows), 2)
        rows_by_label = {row["physical_c1_label"]: row for row in rows}
        self.assertEqual(rows_by_label["11:29"]["raw_source_label"], "11:29")
        self.assertEqual(rows_by_label["11:29"]["amount"], 173336.0)
        self.assertEqual(rows_by_label["13:00"]["raw_source_label"], "11:30")
        self.assertEqual(rows_by_label["13:00"]["amount"], 450360.0)

    def test_mootdx_c1_physical_normalizer_maps_raw_1500_to_final_physical_1459(self):
        rows = normalize_c1_physical_intraday_1m_labels(
            [
                {
                    "bar_time": "2026-07-08 15:00",
                    "open": 6.05,
                    "high": 6.05,
                    "low": 6.04,
                    "close": 6.04,
                    "amount": 1000000.0,
                }
            ],
            trade_date="20260708",
            intraday_trade_date="20260708",
            source_adapter="mootdx",
        )

        self.assertEqual(rows[0]["physical_c1_label"], "14:59")
        self.assertEqual(rows[0]["raw_source_label"], "15:00")

    def test_mootdx_c1_physical_normalizer_prefers_raw_1500_for_final_physical_1459(self):
        rows = normalize_c1_physical_intraday_1m_labels(
            [
                {
                    "bar_time": "2026-07-08 14:59",
                    "open": 6.04,
                    "high": 6.04,
                    "low": 6.04,
                    "close": 6.04,
                    "amount": 0.0,
                },
                {
                    "bar_time": "2026-07-08 15:00",
                    "open": 6.05,
                    "high": 6.05,
                    "low": 6.04,
                    "close": 6.04,
                    "amount": 1000000.0,
                },
            ],
            trade_date="20260708",
            intraday_trade_date="20260708",
            source_adapter="mootdx",
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["physical_c1_label"], "14:59")
        self.assertEqual(rows[0]["raw_source_label"], "15:00")
        self.assertEqual(rows[0]["amount"], 1000000.0)

    def test_mootdx_c1_physical_normalizer_keeps_afternoon_raw_labels_current(self):
        rows = normalize_c1_physical_intraday_1m_labels(
            [
                {
                    "bar_time": "2026-07-08 13:01",
                    "open": 18.48,
                    "high": 18.53,
                    "low": 18.48,
                    "close": 18.53,
                    "amount": 2231867.0,
                },
                {
                    "bar_time": "2026-07-08 14:15",
                    "open": 18.60,
                    "high": 18.62,
                    "low": 18.59,
                    "close": 18.61,
                    "amount": 123456.0,
                },
            ],
            trade_date="20260708",
            intraday_trade_date="20260708",
            source_adapter="mootdx",
        )

        rows_by_label = {row["physical_c1_label"]: row for row in rows}
        self.assertEqual(rows_by_label["13:01"]["raw_source_label"], "13:01")
        self.assertEqual(rows_by_label["14:15"]["raw_source_label"], "14:15")

    def test_metric_context_uses_same_trade_date_previous_windows_for_non_first_periods(self):
        labels = c1_scoped_artifact.canonical_ashare_1m_labels(TRADE_DATE)
        target_label = "10:06"
        target_index = labels.index(target_label)
        current_rows = [
            current_day_c1_row(label, idx)
            for idx, label in enumerate(labels[: target_index + 1])
        ]
        for row in current_rows:
            if row["physical_c1_label"] == "10:05":
                row.update(open=41.82, close=41.61, amount=25728862.0)
            if row["physical_c1_label"] == "10:06":
                row.update(open=41.62, close=41.82, amount=22228156.0)
        previous_day_rows = [
            previous_day_c1_row(label, idx)
            for idx, label in enumerate(labels)
        ]
        staging_artifact = {
            "artifact_type": "n3_c1_scoped_current_day_staging_v1",
            "artifact_status": "passed",
            "for_trade_date": TRADE_DATE,
            "scope_count": 1,
            "closed_minute_row_count": len(current_rows),
            "closed_minute_rows": current_rows,
            "database_written": False,
            "market_data_pulled": True,
            "writes_canonical_minute_bar_1m": False,
            "writes_n3_outbox": False,
            "full_market_fallback_used": False,
        }

        artifact = build_n3_c1_n3t_metric_context_source_artifact(
            active_scope_artifact(),
            staging_artifact=staging_artifact,
            previous_day_minute_rows=previous_day_rows,
            target_hhmm="1006",
            observed_at="2026-07-02T10:07:00+08:00",
        )

        self.assertEqual(artifact["artifact_status"], "planned")
        metric_values = artifact["metric_context_rows"][0]["metric_values"]
        self.assertEqual(metric_values["current_price"], 41.82)
        self.assertEqual(metric_values["previous_1m_body_high"], 41.82)
        self.assertEqual(metric_values["previous_1m_amount"], 25728862.0)
        self.assertEqual(metric_values["previous_1m_period_source"], "same_trade_date_previous_period")
        self.assertEqual(metric_values["previous_5m_period_source"], "same_trade_date_previous_period")
        self.assertEqual(metric_values["previous_30m_period_source"], "same_trade_date_previous_period")
        self.assertEqual(metric_values["previous_120m_period_source"], "previous_trade_date_last_period")
        self.assertFalse(metric_values["is_first_1m_of_day"])
        self.assertFalse(metric_values["is_first_5m_of_day"])
        self.assertFalse(metric_values["is_first_30m_of_day"])
        self.assertTrue(metric_values["is_first_120m_of_day"])

    def test_metric_context_uses_same_day_previous_120m_after_open_boundary_gap(self):
        labels = c1_scoped_artifact.canonical_ashare_1m_labels(TRADE_DATE)
        target_label = "14:55"
        target_index = labels.index(target_label)
        current_rows = [
            current_day_c1_row(label, idx)
            for idx, label in enumerate(labels[: target_index + 1])
            if label != "09:30"
        ]
        previous_day_rows = [
            previous_day_c1_row(label, idx)
            for idx, label in enumerate(labels)
            if label != "09:30"
        ]
        staging_artifact = {
            "artifact_type": "n3_c1_scoped_current_day_staging_v1",
            "artifact_status": "passed",
            "for_trade_date": TRADE_DATE,
            "scope_count": 1,
            "closed_minute_row_count": len(current_rows),
            "closed_minute_rows": current_rows,
            "database_written": False,
            "market_data_pulled": True,
            "writes_canonical_minute_bar_1m": False,
            "writes_n3_outbox": False,
            "full_market_fallback_used": False,
        }

        artifact = build_n3_c1_n3t_metric_context_source_artifact(
            active_scope_artifact(),
            staging_artifact=staging_artifact,
            previous_day_minute_rows=previous_day_rows,
            target_hhmm="1455",
            observed_at="2026-07-02T14:56:00+08:00",
        )

        metric_values = artifact["metric_context_rows"][0]["metric_values"]
        self.assertEqual(metric_values["previous_120m_period_source"], "same_trade_date_previous_period")
        self.assertFalse(metric_values["is_first_120m_of_day"])
        self.assertIsNotNone(metric_values["previous_120m_body_high"])
        self.assertIsNotNone(metric_values["previous_120m_body_low"])

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
        missing_source_run = build_n3_c1_scoped_artifact_plan(
            active_scope_artifact(scope_rows=[active_scope_row(source_trigger_run_id="")]),
            target_minute_label="09:52",
            observed_at="2026-07-02T09:53:00+08:00",
        )

        self.assertEqual(stale["artifact_status"], "blocked")
        self.assertEqual(stale["blocked_reason"], BLOCKED_N3_C1_SCOPE_CONTRACT_MISMATCH)
        self.assertEqual(missing["artifact_status"], "blocked")
        self.assertEqual(missing["blocked_reason"], BLOCKED_N3_C1_SCOPE_CONTRACT_MISMATCH)
        self.assertEqual(missing_source_run["artifact_status"], "blocked")
        self.assertEqual(missing_source_run["blocked_reason"], BLOCKED_N3_C1_SCOPE_CONTRACT_MISMATCH)

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
