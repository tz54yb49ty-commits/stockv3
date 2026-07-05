import re
import inspect
import unittest
from pathlib import Path

from ashare_v3.market import n3t_action_confirmation_metric
from ashare_v3.market.n3t_action_confirmation_metric import (
    N3TMetricContractError,
    build_n3t_action_confirmation_metric_writer_draft_plan,
    build_n3t_action_confirmation_metric_row,
    build_n3t_action_confirmation_metric_schema_contract,
    build_n3t_scoped_metric_from_c1_artifact_plan,
    build_n3t_metric_run_id,
    is_c1_minute_closed_for_action_confirmation,
    parse_n3t_metric_run_id,
)
from ashare_v3.market.minute_label_normalization import BLOCKED_C1_MINUTE_LABEL_NOT_TRADABLE

ROOT = Path(__file__).resolve().parents[1]
N3T_SCHEMA_DRAFT_SQL = ROOT / "sql/N3T_action_confirmation_metric_schema_draft.sql"
N3T_SCHEMA_DRAFT_ROLLBACK_SQL = ROOT / "sql/N3T_action_confirmation_metric_schema_draft_rollback.sql"
N3T_DESIGN_DOC = ROOT / "docs/V3_N3_MARKET_DATA_LAYER_DEVELOPMENT_DESIGN.md"


class N3TActionConfirmationMetricContractTest(unittest.TestCase):
    @staticmethod
    def _scoped_c1_artifact(scope_rows: list[dict[str, object]] | None = None, **overrides: object) -> dict[str, object]:
        artifact = {
            "artifact_type": "n3_c1_scoped_closed_1m_artifact_v1",
            "artifact_schema_version": "v1",
            "producer_layer": "N3_market_data",
            "for_trade_date": "20260702",
            "target_minute_label": "09:52",
            "artifact_status": "planned",
            "blocked_reason": None,
            "scope_count": 1,
            "empty_scope_noop": False,
            "full_market_fallback_allowed": False,
            "n3_scans_n5_internals": False,
            "database_written": False,
            "market_data_pulled": False,
            "writes_canonical_minute_bar_1m": False,
            "writes_n3_outbox": False,
            "consumes_n4_outbox": False,
            "updates_n4_outbox": False,
            "full_market_fallback_used": False,
            "scope_rows": scope_rows
            if scope_rows is not None
            else [
                {
                    "for_trade_date": "20260702",
                    "asset_kind": "stock",
                    "identity_key": "stock:SZ:300803",
                    "direction": "buy",
                    "signal_type": "B_BUY",
                    "condition_key": "BUY_MAIN",
                    "source_trigger_event_id": "n4-match-300803",
                    "source_trigger_run_id": "n4_trigger_20260702_v1",
                    "scope_status": "active",
                }
            ],
        }
        artifact.update(overrides)
        return artifact

    @staticmethod
    def _complete_metric_values() -> dict[str, object]:
        return {
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
        }

    def test_schema_contract_declares_option_a_tables_and_n5_lineage(self) -> None:
        contract = build_n3t_action_confirmation_metric_schema_contract()

        self.assertEqual(
            contract["table_by_asset_kind"],
            {
                "stock": "stock_n3t_action_confirmation_metric",
                "index": "index_n3t_action_confirmation_metric",
                "board": "board_n3t_action_confirmation_metric",
            },
        )
        self.assertEqual(contract["lineage"]["source_basis"], "N3T_C1_CLOSED")
        self.assertEqual(contract["lineage"]["metric_role"], "action_confirmation")
        self.assertEqual(contract["lineage"]["proof_consumer"], "N5")
        self.assertFalse(contract["lineage"]["not_n5_final_proof"])
        self.assertFalse(contract["boundary"]["writes_n3_to_n4_outbox"])
        self.assertFalse(contract["boundary"]["uses_n3p_b1_b2_or_realtime_action_confirmation_metric"])

        ddl = "\n".join(contract["ddl_draft_by_asset_kind"].values())
        for table in contract["table_by_asset_kind"].values():
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", ddl)
        self.assertIn("CHECK (source_basis = 'N3T_C1_CLOSED')", ddl)
        self.assertIn("CHECK (metric_role = 'action_confirmation')", ddl)
        self.assertIn("CHECK (proof_consumer = 'N5')", ddl)
        self.assertIn("CHECK (not_n5_final_proof = false)", ddl)
        self.assertIsNone(re.search(r"\b(ALTER|INSERT|UPDATE|DELETE|TRUNCATE|DROP)\b", ddl, re.IGNORECASE))
        self.assertNotIn("common_event_outbox", ddl)
        self.assertNotIn("realtime_action_confirmation_metric", ddl)

    def test_schema_contract_declares_n5_consumable_compatibility_fields(self) -> None:
        contract = build_n3t_action_confirmation_metric_schema_contract()

        required_fields = (
            "current_30m_closed_elapsed_amount",
            "current_5m_amount",
            "previous_5m_amount",
            "current_30m_virtual_amount",
            "current_5m_virtual_amount",
            "previous_5m_full_amount",
            "is_first_1m_of_day",
            "is_first_5m_of_day",
            "first_1m_amount_default_pass",
            "first_5m_amount_default_pass",
        )
        for field in required_fields:
            self.assertIn(field, contract["output_fields"])

        ddl = "\n".join(contract["ddl_draft_by_asset_kind"].values())
        for field in (
            "current_30m_virtual_amount NUMERIC",
            "current_5m_virtual_amount NUMERIC",
            "previous_5m_full_amount NUMERIC",
            "is_first_1m_of_day BOOLEAN NOT NULL DEFAULT false",
            "is_first_5m_of_day BOOLEAN NOT NULL DEFAULT false",
            "first_1m_amount_default_pass BOOLEAN NOT NULL DEFAULT false",
            "first_5m_amount_default_pass BOOLEAN NOT NULL DEFAULT false",
        ):
            self.assertIn(field, ddl)

        self.assertIn(
            "CHECK (current_30m_virtual_amount IS NULL OR current_30m_closed_elapsed_amount IS NULL OR current_30m_virtual_amount = current_30m_closed_elapsed_amount)",
            ddl,
        )
        self.assertIn(
            "CHECK (current_5m_virtual_amount IS NULL OR current_5m_amount IS NULL OR current_5m_virtual_amount = current_5m_amount)",
            ddl,
        )
        self.assertIn(
            "CHECK (previous_5m_full_amount IS NULL OR previous_5m_amount IS NULL OR previous_5m_full_amount = previous_5m_amount)",
            ddl,
        )

    def test_option_a_schema_migration_draft_matches_n3t_contract(self) -> None:
        schema_sql = N3T_SCHEMA_DRAFT_SQL.read_text(encoding="utf-8")
        rollback_sql = N3T_SCHEMA_DRAFT_ROLLBACK_SQL.read_text(encoding="utf-8")

        for asset_kind in ("stock", "index", "board"):
            table = f"{asset_kind}_n3t_action_confirmation_metric"
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", schema_sql)
            self.assertIn(f"CHECK (asset_kind = '{asset_kind}')", schema_sql)
            self.assertIn(f"CHECK (identity_key LIKE '{asset_kind}:%')", schema_sql)
            self.assertIn(f"DROP TABLE IF EXISTS {table}", rollback_sql)

        for token in (
            "source_basis TEXT NOT NULL DEFAULT 'N3T_C1_CLOSED' CHECK (source_basis = 'N3T_C1_CLOSED')",
            "metric_role TEXT NOT NULL DEFAULT 'action_confirmation' CHECK (metric_role = 'action_confirmation')",
            "proof_consumer TEXT NOT NULL DEFAULT 'N5' CHECK (proof_consumer = 'N5')",
            "not_n5_final_proof BOOLEAN NOT NULL DEFAULT false CHECK (not_n5_final_proof = false)",
            "current_30m_closed_elapsed_amount NUMERIC",
            "current_5m_amount NUMERIC",
            "previous_5m_amount NUMERIC",
            "current_30m_virtual_amount NUMERIC",
            "current_5m_virtual_amount NUMERIC",
            "previous_5m_full_amount NUMERIC",
            "is_first_1m_of_day BOOLEAN NOT NULL DEFAULT false",
            "is_first_5m_of_day BOOLEAN NOT NULL DEFAULT false",
            "first_1m_amount_default_pass BOOLEAN NOT NULL DEFAULT false",
            "first_5m_amount_default_pass BOOLEAN NOT NULL DEFAULT false",
            "CHECK (current_30m_virtual_amount IS NULL OR current_30m_closed_elapsed_amount IS NULL OR current_30m_virtual_amount = current_30m_closed_elapsed_amount)",
            "CHECK (current_5m_virtual_amount IS NULL OR current_5m_amount IS NULL OR current_5m_virtual_amount = current_5m_amount)",
            "CHECK (previous_5m_full_amount IS NULL OR previous_5m_amount IS NULL OR previous_5m_full_amount = previous_5m_amount)",
        ):
            self.assertIn(token, schema_sql)

        self.assertIsNone(re.search(r"\b(ALTER|INSERT|UPDATE|DELETE|TRUNCATE|DROP)\b", schema_sql, re.IGNORECASE))
        for forbidden in (
            "common_event_outbox",
            "common_event_inbox",
            "common_event_consumer_checkpoint",
            "trigger_",
            "action_eligible",
            "action_executed",
            "user_",
            "voice_",
            "sim_",
            "position_",
        ):
            self.assertNotIn(forbidden, schema_sql)
            self.assertNotIn(forbidden, rollback_sql)

        drop_tables = re.findall(r"DROP TABLE IF EXISTS ([a-z0-9_]+)", rollback_sql)
        self.assertEqual(
            sorted(drop_tables),
            [
                "board_n3t_action_confirmation_metric",
                "index_n3t_action_confirmation_metric",
                "stock_n3t_action_confirmation_metric",
            ],
        )
        self.assertIn("n3t action-confirmation schema rollback blocked", rollback_sql)
        self.assertNotRegex(rollback_sql, r"\b(INSERT|UPDATE|DELETE|TRUNCATE)\b", re.IGNORECASE)

        design_doc = N3T_DESIGN_DOC.read_text(encoding="utf-8")
        self.assertIn("sql/N3T_action_confirmation_metric_schema_draft.sql", design_doc)
        self.assertIn("sql/N3T_action_confirmation_metric_schema_draft_rollback.sql", design_doc)
        self.assertIn("migration execute = not authorized in this draft gate", design_doc)
        self.assertIn("build_n3t_action_confirmation_metric_writer_draft_plan", design_doc)
        self.assertIn("future write allowlist = stock_n3t_action_confirmation_metric", design_doc)
        self.assertIn("BLOCKED_C1_MINUTE_NOT_CLOSED before any future insert path", design_doc)

    def test_n3t_ready_row_uses_closed_c1_authority_and_canonical_lineage(self) -> None:
        run_id = build_n3t_metric_run_id(
            trade_date="20260701",
            until_hhmm="1412",
            suffix="market_data_subscription_20260701_v1",
        )

        row = build_n3t_action_confirmation_metric_row(
            projection_run_id=run_id,
            asset_kind="stock",
            identity_key="stock:SH:600000",
            trade_date="20260701",
            metric_minute_label="14:12",
            as_of_time="2026-07-01T14:13:00+08:00",
            metric_values=self._complete_metric_values(),
            source_closed_minute_bar_ids=[101, 102, 103],
            previous_day_minute_refs=[201, 202, 203],
        )

        self.assertTrue(row["metric_ready"])
        self.assertEqual(row["metric_quality_status"], "passed")
        self.assertEqual(row["source_basis"], "N3T_C1_CLOSED")
        self.assertEqual(row["metric_role"], "action_confirmation")
        self.assertEqual(row["proof_consumer"], "N5")
        self.assertFalse(row["not_n5_final_proof"])
        self.assertEqual(row["source_closed_minute_bar_ids"], [101, 102, 103])
        self.assertEqual(row["previous_day_minute_refs"], [201, 202, 203])
        self.assertTrue(is_c1_minute_closed_for_action_confirmation("20260701", "14:12", "2026-07-01T14:13:00+08:00"))
        self.assertEqual(row["current_30m_virtual_amount"], row["current_30m_closed_elapsed_amount"])
        self.assertEqual(row["current_5m_virtual_amount"], row["current_5m_amount"])
        self.assertEqual(row["previous_5m_full_amount"], row["previous_5m_amount"])
        self.assertTrue(row["is_first_1m_of_day"])
        self.assertTrue(row["is_first_5m_of_day"])
        self.assertTrue(row["first_1m_amount_default_pass"])
        self.assertTrue(row["first_5m_amount_default_pass"])
        self.assertEqual(
            row["trace_json"]["alias_relationships"],
            {
                "current_30m_virtual_amount": "current_30m_closed_elapsed_amount",
                "current_5m_virtual_amount": "current_5m_amount",
                "previous_5m_full_amount": "previous_5m_amount",
            },
        )

    def test_forbidden_n3p_trace_cannot_override_n3t_lineage(self) -> None:
        row = build_n3t_action_confirmation_metric_row(
            projection_run_id=build_n3t_metric_run_id("20260701", "1412", "scope"),
            asset_kind="stock",
            identity_key="stock:SH:600000",
            trade_date="20260701",
            metric_minute_label="14:12",
            as_of_time="2026-07-01T14:13:00+08:00",
            metric_values={"current_price": 12},
            source_closed_minute_bar_ids=[101],
            previous_day_minute_refs=[201],
            candidate_trace={
                "source_basis": "N3P_B1_SOURCE_RETURNED",
                "metric_role": "trigger_proof",
                "proof_consumer": "N4",
                "not_n5_final_proof": True,
                "projection_run_id": "realtime_action_confirmation_metric_20260701_until_1412__asset_all",
            },
        )

        self.assertEqual(row["source_basis"], "N3T_C1_CLOSED")
        self.assertEqual(row["metric_role"], "action_confirmation")
        self.assertEqual(row["proof_consumer"], "N5")
        self.assertFalse(row["not_n5_final_proof"])
        self.assertEqual(row["trace_json"]["candidate_trace"]["metric_role"], "trigger_proof")
        self.assertEqual(row["trace_json"]["candidate_trace_authority"], "trace_only_not_authoritative")

    def test_writer_draft_plan_targets_only_n3t_tables_and_preserves_n5_aliases(self) -> None:
        plan = build_n3t_action_confirmation_metric_writer_draft_plan(
            projection_run_id=build_n3t_metric_run_id("20260701", "1412", "scope"),
            asset_kind="stock",
            identity_key="stock:SH:600000",
            trade_date="20260701",
            metric_minute_label="14:12",
            as_of_time="2026-07-01T14:13:00+08:00",
            metric_values=self._complete_metric_values(),
            source_closed_minute_bar_ids=[101, 102, 103],
            previous_day_minute_refs=[201, 202, 203],
            candidate_trace={
                "source_basis": "N3P_B1_SOURCE_RETURNED",
                "projection_run_id": "realtime_action_confirmation_metric_20260701_until_1412__asset_all",
            },
        )

        self.assertEqual(plan["writer_mode"], "draft_only")
        self.assertFalse(plan["runtime_execute"])
        self.assertFalse(plan["db_write_executed"])
        self.assertFalse(plan["pulls_market_data"])
        self.assertEqual(
            plan["input_contract"]["allowed_input_tables"],
            ["stock_minute_bar_1m", "stock_previous_day_minute_cumulative"],
        )
        self.assertEqual(plan["input_contract"]["minute_bar_table"], "stock_minute_bar_1m")
        self.assertEqual(plan["input_contract"]["current_day_minute_filter"], {"is_previous_day_preload": False})
        self.assertEqual(plan["input_contract"]["previous_day_raw_minute_filter"], {"is_previous_day_preload": True})
        self.assertEqual(plan["input_contract"]["same_window_cumulative_table"], "stock_previous_day_minute_cumulative")
        self.assertEqual(
            plan["input_contract"]["logical_previous_day_minute_table"],
            {
                "name": "stock_previous_day_minute_bar_1m",
                "physical_table_required": False,
                "stored_in": "stock_minute_bar_1m",
                "selector": "is_previous_day_preload=true",
            },
        )
        self.assertTrue(plan["input_contract"]["requires_closed_c1"])
        self.assertIn("legacy realtime_action_confirmation_metric as final action proof", plan["input_contract"]["forbidden_inputs"])
        self.assertEqual(plan["write_contract"]["target_table"], "stock_n3t_action_confirmation_metric")
        self.assertEqual(
            sorted(plan["write_contract"]["allowed_write_tables"]),
            [
                "board_n3t_action_confirmation_metric",
                "index_n3t_action_confirmation_metric",
                "stock_n3t_action_confirmation_metric",
            ],
        )
        self.assertFalse(plan["write_contract"]["writes_common_event_outbox"])
        self.assertFalse(plan["write_contract"]["writes_n4_n5_n6"])
        self.assertEqual(plan["insert_plan"]["operation"], "INSERT_DRAFT_ONLY")
        self.assertEqual(plan["insert_plan"]["target_table"], "stock_n3t_action_confirmation_metric")
        self.assertEqual(len(plan["insert_plan"]["rows"]), 1)

        row = plan["insert_plan"]["rows"][0]
        self.assertTrue(row["metric_ready"])
        self.assertEqual(row["source_basis"], "N3T_C1_CLOSED")
        self.assertEqual(row["metric_role"], "action_confirmation")
        self.assertEqual(row["proof_consumer"], "N5")
        self.assertEqual(row["current_30m_virtual_amount"], row["current_30m_closed_elapsed_amount"])
        self.assertEqual(row["current_5m_virtual_amount"], row["current_5m_amount"])
        self.assertEqual(row["previous_5m_full_amount"], row["previous_5m_amount"])
        self.assertEqual(row["trace_json"]["candidate_trace_authority"], "trace_only_not_authoritative")

        for field in (
            "current_30m_virtual_amount",
            "current_5m_virtual_amount",
            "previous_5m_full_amount",
            "source_closed_minute_bar_ids",
            "previous_day_minute_refs",
        ):
            self.assertIn(field, plan["insert_plan"]["columns"])

        joined_plan = "\n".join(str(value) for value in plan["insert_plan"].values())
        for forbidden in (
            "common_event_outbox",
            "common_event_inbox",
            "common_event_consumer_checkpoint",
            "trigger_state",
            "action_eligible",
            "action_executed",
            "user_",
            "voice_",
            "sim_",
            "position_",
        ):
            self.assertNotIn(forbidden, joined_plan)

    def test_writer_draft_rejects_unclosed_c1_minute(self) -> None:
        with self.assertRaisesRegex(N3TMetricContractError, "BLOCKED_C1_MINUTE_NOT_CLOSED"):
            build_n3t_action_confirmation_metric_writer_draft_plan(
                projection_run_id=build_n3t_metric_run_id("20260701", "1412", "scope"),
                asset_kind="stock",
                identity_key="stock:SH:600000",
                trade_date="20260701",
                metric_minute_label="14:12",
                as_of_time="2026-07-01T14:12:59+08:00",
                metric_values=self._complete_metric_values(),
                source_closed_minute_bar_ids=[101, 102, 103],
                previous_day_minute_refs=[201, 202, 203],
            )

    def test_missing_closed_c1_or_unclosed_minute_fails_closed(self) -> None:
        missing_refs = build_n3t_action_confirmation_metric_row(
            projection_run_id=build_n3t_metric_run_id("20260701", "1412", "scope"),
            asset_kind="stock",
            identity_key="stock:SH:600000",
            trade_date="20260701",
            metric_minute_label="14:12",
            as_of_time="2026-07-01T14:13:00+08:00",
            metric_values={"current_price": 12},
            source_closed_minute_bar_ids=[],
            previous_day_minute_refs=[201],
        )
        unclosed = build_n3t_action_confirmation_metric_row(
            projection_run_id=build_n3t_metric_run_id("20260701", "1412", "scope"),
            asset_kind="stock",
            identity_key="stock:SH:600000",
            trade_date="20260701",
            metric_minute_label="14:12",
            as_of_time="2026-07-01T14:12:59+08:00",
            metric_values={"current_price": 12},
            source_closed_minute_bar_ids=[101],
            previous_day_minute_refs=[201],
        )

        self.assertFalse(missing_refs["metric_ready"])
        self.assertEqual(missing_refs["metric_quality_status"], "blocked")
        self.assertIn("BLOCKED_N3T_CLOSED_C1_CONTEXT_REQUIRED", missing_refs["blocked_reasons"])
        self.assertFalse(unclosed["metric_ready"])
        self.assertEqual(unclosed["metric_quality_status"], "blocked")
        self.assertIn("BLOCKED_C1_MINUTE_NOT_CLOSED", unclosed["blocked_reasons"])

    def test_lunch_boundary_label_fails_closed_and_1300_uses_1301_close(self) -> None:
        self.assertFalse(
            is_c1_minute_closed_for_action_confirmation(
                "20260702",
                "13:00",
                "2026-07-02T13:00:59+08:00",
            )
        )
        self.assertTrue(
            is_c1_minute_closed_for_action_confirmation(
                "20260702",
                "13:00",
                "2026-07-02T13:01:00+08:00",
            )
        )
        with self.assertRaisesRegex(N3TMetricContractError, BLOCKED_C1_MINUTE_LABEL_NOT_TRADABLE):
            is_c1_minute_closed_for_action_confirmation(
                "20260702",
                "11:30",
                "2026-07-02T13:01:00+08:00",
            )

        row = build_n3t_action_confirmation_metric_row(
            projection_run_id=build_n3t_metric_run_id("20260702", "1130", "scope"),
            asset_kind="stock",
            identity_key="stock:SH:600000",
            trade_date="20260702",
            metric_minute_label="11:30",
            as_of_time="2026-07-02T13:01:00+08:00",
            metric_values=self._complete_metric_values(),
            source_closed_minute_bar_ids=[101],
            previous_day_minute_refs=[201],
        )

        self.assertFalse(row["metric_ready"])
        self.assertIn(BLOCKED_C1_MINUTE_LABEL_NOT_TRADABLE, row["blocked_reasons"])
        self.assertEqual(row["metric_time"], "")

    def test_scoped_metric_plan_consumes_only_scoped_c1_artifact(self) -> None:
        plan = build_n3t_scoped_metric_from_c1_artifact_plan(
            self._scoped_c1_artifact(
                metric_context_status="ready",
                metric_context_rows=[
                    {
                        **self._scoped_c1_artifact()["scope_rows"][0],
                        "source_closed_minute_bar_ids": [101, 102, 103],
                        "previous_day_minute_refs": [201, 202, 203],
                        "metric_values": self._complete_metric_values(),
                    }
                ],
            ),
            source_artifact_path="docs/runtime/n3_c1_scoped_0952.json",
            source_artifact_hash="sha256:c1-scope",
        )

        self.assertEqual(plan["plan_type"], "n3t_scoped_metric_from_c1_artifact_plan_v1")
        self.assertEqual(plan["input_artifact_type"], "n3_c1_scoped_closed_1m_artifact_v1")
        self.assertEqual(plan["source_c1_artifact"]["path"], "docs/runtime/n3_c1_scoped_0952.json")
        self.assertEqual(plan["source_c1_artifact"]["hash"], "sha256:c1-scope")
        self.assertEqual(plan["plan_status"], "planned")
        self.assertEqual(plan["for_trade_date"], "20260702")
        self.assertEqual(plan["target_minute_label"], "09:52")
        self.assertFalse(plan["n3_scans_n5_internals"])
        self.assertFalse(plan["full_market_fallback_allowed"])
        self.assertEqual(
            sorted(plan["write_contract"]["allowed_write_tables"]),
            [
                "board_n3t_action_confirmation_metric",
                "index_n3t_action_confirmation_metric",
                "stock_n3t_action_confirmation_metric",
            ],
        )
        self.assertEqual(len(plan["metric_plan_rows"]), 1)
        row = plan["metric_plan_rows"][0]
        self.assertEqual(row["target_table"], "stock_n3t_action_confirmation_metric")
        self.assertEqual(row["source_basis"], "N3T_C1_CLOSED")
        self.assertEqual(row["metric_role"], "action_confirmation")
        self.assertEqual(row["proof_consumer"], "N5")
        self.assertFalse(row["not_n5_final_proof"])
        self.assertEqual(row["source_trigger_event_id"], "n4-match-300803")
        self.assertEqual(row["source_closed_minute_bar_ids"], [101, 102, 103])
        self.assertEqual(row["previous_day_minute_refs"], [201, 202, 203])
        self.assertEqual(row["metric_values"]["current_price"], 12)
        self.assertFalse(plan["side_effects"]["database_written"])
        self.assertFalse(plan["side_effects"]["market_data_pulled"])
        self.assertFalse(plan["side_effects"]["writes_canonical_minute_bar_1m"])
        self.assertFalse(plan["side_effects"]["writes_n3_outbox"])
        self.assertFalse(plan["side_effects"]["consumes_n4_outbox"])
        self.assertFalse(plan["side_effects"]["updates_n4_outbox"])
        self.assertFalse(plan["side_effects"]["full_market_fallback_used"])
        self.assertFalse(plan["side_effects"]["runtime_execute"])

    def test_scoped_metric_plan_uses_previous_day_same_window_amount_from_metric_context(self) -> None:
        metric_values = self._complete_metric_values()
        metric_values["previous_day_same_window_amount"] = 100271508.75

        plan = build_n3t_scoped_metric_from_c1_artifact_plan(
            self._scoped_c1_artifact(
                metric_context_status="ready",
                metric_context_rows=[
                    {
                        **self._scoped_c1_artifact()["scope_rows"][0],
                        "source_closed_minute_bar_ids": [101, 102, 103],
                        "previous_day_minute_refs": [201, 202, 203],
                        "metric_values": metric_values,
                        "deterministic_derivation_inputs": {
                            "previous_day_same_window_amount_source": "scoped_previous_day_raw_c1",
                            "a1_cumulative_contract_modified": False,
                        },
                    }
                ],
            )
        )

        self.assertEqual(plan["plan_status"], "planned")
        self.assertEqual(plan["metric_plan_rows"][0]["metric_values"]["previous_day_same_window_amount"], 100271508.75)
        self.assertEqual(
            plan["metric_plan_rows"][0]["deterministic_derivation_inputs"]["previous_day_same_window_amount_source"],
            "scoped_previous_day_raw_c1",
        )
        self.assertFalse(plan["metric_plan_rows"][0]["deterministic_derivation_inputs"]["a1_cumulative_contract_modified"])

    def test_scoped_metric_plan_blocks_without_metric_context_rows(self) -> None:
        plan = build_n3t_scoped_metric_from_c1_artifact_plan(self._scoped_c1_artifact())

        self.assertEqual(plan["plan_status"], "blocked")
        self.assertEqual(plan["blocked_reason"], "BLOCKED_N3T_EXECUTE_CONTEXT_INSUFFICIENT")
        self.assertEqual(plan["metric_plan_rows"], [])
        self.assertFalse(plan["side_effects"]["database_written"])
        self.assertFalse(plan["side_effects"]["market_data_pulled"])

    def test_scoped_metric_plan_empty_c1_artifact_is_explicit_noop(self) -> None:
        plan = build_n3t_scoped_metric_from_c1_artifact_plan(
            self._scoped_c1_artifact(
                scope_rows=[],
                scope_count=0,
                artifact_status="noop",
                empty_scope_noop=True,
            )
        )

        self.assertEqual(plan["plan_status"], "noop")
        self.assertTrue(plan["empty_scope_noop"])
        self.assertEqual(plan["metric_plan_rows"], [])
        self.assertIsNone(plan["blocked_reason"])
        self.assertFalse(plan["side_effects"]["full_market_fallback_used"])

    def test_scoped_metric_plan_invalid_stale_or_blocked_artifact_fails_closed(self) -> None:
        invalid = build_n3t_scoped_metric_from_c1_artifact_plan(
            self._scoped_c1_artifact(artifact_type="wrong_artifact")
        )
        stale = build_n3t_scoped_metric_from_c1_artifact_plan(
            self._scoped_c1_artifact(
                scope_rows=[
                    {
                        "for_trade_date": "20260701",
                        "asset_kind": "stock",
                        "identity_key": "stock:SZ:300803",
                        "direction": "buy",
                        "signal_type": "B_BUY",
                        "condition_key": "BUY_MAIN",
                        "source_trigger_event_id": "n4-match-300803",
                        "source_trigger_run_id": "n4_trigger_20260702_v1",
                        "scope_status": "active",
                    }
                ]
            )
        )
        non_closed = build_n3t_scoped_metric_from_c1_artifact_plan(
            self._scoped_c1_artifact(
                artifact_status="blocked",
                blocked_reason="BLOCKED_C1_MINUTE_NOT_CLOSED",
            )
        )
        invalid_label = build_n3t_scoped_metric_from_c1_artifact_plan(
            self._scoped_c1_artifact(target_minute_label="11:30")
        )

        self.assertEqual(invalid["plan_status"], "blocked")
        self.assertEqual(invalid["blocked_reason"], "BLOCKED_N3T_SCOPED_INPUT_CONTRACT_MISMATCH")
        self.assertEqual(stale["plan_status"], "blocked")
        self.assertEqual(stale["blocked_reason"], "BLOCKED_N3T_SCOPED_INPUT_CONTRACT_MISMATCH")
        self.assertEqual(non_closed["plan_status"], "blocked")
        self.assertEqual(non_closed["blocked_reason"], "BLOCKED_C1_MINUTE_NOT_CLOSED")
        self.assertEqual(invalid_label["plan_status"], "blocked")
        self.assertEqual(invalid_label["blocked_reason"], BLOCKED_C1_MINUTE_LABEL_NOT_TRADABLE)

    def test_scoped_metric_plan_forbids_full_market_fallback(self) -> None:
        plan = build_n3t_scoped_metric_from_c1_artifact_plan(
            self._scoped_c1_artifact(full_market_fallback_allowed=True)
        )

        self.assertEqual(plan["plan_status"], "blocked")
        self.assertEqual(plan["blocked_reason"], "BLOCKED_FULL_MARKET_FALLBACK_RISK")
        self.assertFalse(plan["full_market_fallback_allowed"])
        self.assertFalse(plan["side_effects"]["full_market_fallback_used"])

    def test_scoped_metric_plan_has_no_db_adapter_or_runtime_path(self) -> None:
        source = inspect.getsource(n3t_action_confirmation_metric)

        for forbidden in (
            "psycopg",
            "mootdx",
            "tushare",
            "requests",
            "launchctl",
            "subprocess",
        ):
            self.assertNotIn(forbidden, source.lower())

    def test_legacy_run_id_is_rejected(self) -> None:
        with self.assertRaises(N3TMetricContractError):
            parse_n3t_metric_run_id("realtime_action_confirmation_metric_20260701_until_1412__asset_all")


if __name__ == "__main__":
    unittest.main()
