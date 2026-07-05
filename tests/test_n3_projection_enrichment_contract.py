import json
from pathlib import Path
import unittest


CONTRACT_JSON = Path("docs/N3_projection_enrichment_schema_contract.json")
CONTRACT_MD = Path("docs/N3_PROJECTION_ENRICHMENT_SCHEMA_CONTRACT.md")
DRY_RUN_JSON = Path("docs/N3_projection_enrichment_dry_run_report.json")
DRY_RUN_MD = Path("docs/N3_PROJECTION_ENRICHMENT_DRY_RUN_REPORT.md")

REQUIRED_FIELDS = {
    "current_price_or_close",
    "current_amount_metric",
    "current_metric_time",
    "current_metric_quality_status",
    "projection_period",
    "projection_30m_flag",
    "projection_30m_type",
    "current_30m_virtual_amount",
    "reference_30m_amount",
    "reference_30m_entity_high",
    "reference_30m_entity_low",
    "trigger_amount_chain_pass",
    "projection_lineage_json",
    "source_freshness_status",
    "source_snapshot_run_id",
    "source_minute_run_id",
    "source_previous_day_minute_run_id",
}


class N3ProjectionEnrichmentContractTest(unittest.TestCase):
    def test_contract_and_dry_run_artifacts_exist_and_parse(self) -> None:
        for path in (CONTRACT_JSON, CONTRACT_MD, DRY_RUN_JSON, DRY_RUN_MD):
            self.assertTrue(path.exists(), f"missing artifact: {path}")

        json.loads(CONTRACT_JSON.read_text())
        json.loads(DRY_RUN_JSON.read_text())

    def test_contract_covers_all_required_n4_v4_fields(self) -> None:
        contract = load_contract()

        self.assertEqual(set(contract["target_fields"]), REQUIRED_FIELDS)
        self.assertEqual(set(contract["field_contract"]), REQUIRED_FIELDS)
        for field_name, field_contract in contract["field_contract"].items():
            self.assertEqual(field_contract["field_name"], field_name)
            self.assertIn("owner", field_contract)
            self.assertIn("source", field_contract)
            self.assertIn("quality_rule", field_contract)

    def test_trigger_amount_chain_is_owned_by_n3_and_not_n4(self) -> None:
        contract = load_contract()
        amount_contract = contract["field_contract"]["trigger_amount_chain_pass"]

        self.assertEqual(amount_contract["owner"], "N3_market_data")
        self.assertIn("N2 period_trigger_baseline_json", amount_contract["source"])
        self.assertIn("N3 current_amount_metric", amount_contract["source"])
        self.assertFalse(amount_contract["n4_recompute_allowed"])
        self.assertFalse(contract["n4_consumption_boundary"]["n4_may_recompute_enrichment"])
        self.assertIn("N4_TRIGGER_RULE_SPEC_v4", contract["n4_consumption_boundary"]["source_spec"])

    def test_enums_and_trace_fields_are_explicit(self) -> None:
        contract = load_contract()

        self.assertEqual(
            set(contract["enums"]["projection_30m_type"]),
            {"volume_up", "shrink_down", "none", "unknown"},
        )
        self.assertEqual(
            set(contract["enums"]["source_freshness_status"]),
            {"fresh", "stale", "missing", "unknown"},
        )
        self.assertEqual(
            set(contract["enums"]["current_metric_quality_status"]),
            {"passed", "warning", "missing", "failed", "blocked"},
        )
        lineage = contract["lineage_contract"]["projection_lineage_json_required_keys"]
        for key in (
            "source_condition_run_id",
            "source_snapshot_run_id",
            "source_minute_run_id",
            "source_previous_day_minute_run_id",
            "n2_baseline_refs",
            "source_fact_ids",
            "calculation_config_hash",
        ):
            self.assertIn(key, lineage)

    def test_dry_run_is_read_only_and_all_fields_are_contract_validated(self) -> None:
        report = load_report()

        self.assertEqual(report["result"], "DRY_RUN_PASS")
        self.assertEqual(set(report["field_validation"]["contracted_fields"]), REQUIRED_FIELDS)
        self.assertEqual(report["quality_summary"], {"P0": 0, "P1": 0, "P2": 0})
        self.assertTrue(report["implementation_gate"]["allowed"])
        self.assertFalse(report["execute_gate"]["allowed"])

        side_effects = report["side_effects"]
        for key in (
            "database_written",
            "market_data_pulled",
            "outbox_written",
            "outbox_consumed",
            "downstream_layers_touched",
            "worker_started",
            "historical_runs_modified",
        ):
            self.assertFalse(side_effects[key])

    def test_markdown_documents_state_ownership_and_no_execute_boundary(self) -> None:
        contract_md = CONTRACT_MD.read_text()
        dry_run_md = DRY_RUN_MD.read_text()

        self.assertIn("N4 must not recompute", contract_md)
        self.assertIn("trigger_amount_chain_pass", contract_md)
        self.assertIn("No database writes", dry_run_md)
        self.assertIn("DRY_RUN_PASS", dry_run_md)


def load_contract() -> dict:
    return json.loads(CONTRACT_JSON.read_text())


def load_report() -> dict:
    return json.loads(DRY_RUN_JSON.read_text())
