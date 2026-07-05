import unittest

from ashare_v3.ingestion.active_source_version import build_active_source_version_plan
from ashare_v3.ingestion.common import IngestionValidationError, QualityGateResult


class ActiveSourceVersionPlanTest(unittest.TestCase):
    def test_activation_plan_passes_when_all_quality_gates_pass(self) -> None:
        plan = build_active_source_version_plan(
            data_domain="stock",
            data_type="stock_daily",
            scope_key="global",
            source_version="stock_daily_20260521_v1",
            source_batch_id="stock_daily_20260521_v1",
            quality_gates=[QualityGateResult(gate_name="stock_official_daily_proof", status="passed")],
        )

        self.assertTrue(plan.activation_allowed)
        self.assertIn("INSERT INTO common_active_source_version", plan.activation_sql_template)
        self.assertIn("ON CONFLICT (data_domain, data_type, scope_key)", plan.activation_sql_template)
        self.assertIn("DELETE FROM common_active_source_version", plan.rollback_sql_template)
        self.assertFalse(plan.to_dict()["will_execute_sql"])

    def test_failed_quality_gate_blocks_activation(self) -> None:
        plan = build_active_source_version_plan(
            data_domain="stock",
            data_type="stock_daily",
            scope_key="global",
            source_version="stock_daily_20260521_v1",
            source_batch_id="stock_daily_20260521_v1",
            quality_gates=[QualityGateResult(gate_name="stock_official_daily_proof", status="failed")],
        )

        self.assertFalse(plan.activation_allowed)
        failed_gate_names = {gate.gate_name for gate in plan.quality_gates if not gate.passed}
        self.assertIn("active_source_input_quality_gates_all_passed", failed_gate_names)

    def test_warning_quality_gate_blocks_activation(self) -> None:
        plan = build_active_source_version_plan(
            data_domain="index",
            data_type="index_daily",
            scope_key="global",
            source_version="index_daily_20260521_v1",
            source_batch_id="index_daily_20260521_v1",
            quality_gates=[{"gate_name": "index_official_daily_missing", "status": "warning", "severity": "P1"}],
        )

        self.assertFalse(plan.activation_allowed)

    def test_previous_version_rollback_uses_update_template(self) -> None:
        plan = build_active_source_version_plan(
            data_domain="board",
            data_type="board_membership",
            scope_key="global",
            source_version="board_membership_20260522_v1",
            source_batch_id="board_membership_20260522_v1",
            previous_source_version="board_membership_20260521_v1",
            previous_source_batch_id="board_membership_20260521_v1",
            quality_gates=[QualityGateResult(gate_name="board_membership_identity_key_coverage", status="passed")],
        )

        self.assertTrue(plan.activation_allowed)
        self.assertIn("UPDATE common_active_source_version", plan.rollback_sql_template)
        self.assertTrue(plan.to_dict()["rollback"]["requires_previous_source_batch_id"])

    def test_previous_version_without_previous_batch_blocks_activation(self) -> None:
        plan = build_active_source_version_plan(
            data_domain="board",
            data_type="board_membership",
            scope_key="global",
            source_version="board_membership_20260522_v1",
            source_batch_id="board_membership_20260522_v1",
            previous_source_version="board_membership_20260521_v1",
            quality_gates=[QualityGateResult(gate_name="board_membership_identity_key_coverage", status="passed")],
        )

        self.assertFalse(plan.activation_allowed)
        failed_gate_names = {gate.gate_name for gate in plan.quality_gates if not gate.passed}
        self.assertIn("active_source_previous_batch_available_for_rollback", failed_gate_names)

    def test_empty_quality_gates_block_activation(self) -> None:
        plan = build_active_source_version_plan(
            data_domain="common",
            data_type="trade_calendar",
            scope_key="global",
            source_version="trade_calendar_20260521_v1",
            source_batch_id="trade_calendar_20260521_v1",
            quality_gates=[],
        )

        self.assertFalse(plan.activation_allowed)
        failed_gate_names = {gate.gate_name for gate in plan.quality_gates if not gate.passed}
        self.assertIn("active_source_input_quality_gates_non_empty", failed_gate_names)

    def test_unsupported_data_type_blocks_activation(self) -> None:
        plan = build_active_source_version_plan(
            data_domain="stock",
            data_type="stock_trigger",
            scope_key="global",
            source_version="stock_trigger_20260521_v1",
            source_batch_id="stock_trigger_20260521_v1",
            quality_gates=[QualityGateResult(gate_name="sample", status="passed")],
        )

        self.assertFalse(plan.activation_allowed)
        failed_gate_names = {gate.gate_name for gate in plan.quality_gates if not gate.passed}
        self.assertIn("active_source_domain_type_allowed", failed_gate_names)

    def test_unsafe_scope_key_is_rejected(self) -> None:
        with self.assertRaises(IngestionValidationError):
            build_active_source_version_plan(
                data_domain="stock",
                data_type="stock_daily",
                scope_key="../global",
                source_version="stock_daily_20260521_v1",
                source_batch_id="stock_daily_20260521_v1",
                quality_gates=[QualityGateResult(gate_name="sample", status="passed")],
            )


if __name__ == "__main__":
    unittest.main()
