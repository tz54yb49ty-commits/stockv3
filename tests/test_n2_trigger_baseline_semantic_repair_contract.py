import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "docs" / "N2_TRIGGER_BASELINE_SEMANTIC_REPAIR_CONTRACT.json"
PREFLIGHT_PATH = ROOT / "docs" / "N2_TRIGGER_BASELINE_SEMANTIC_REPAIR_PREFLIGHT.json"


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


class N2TriggerBaselineSemanticRepairContractTest(unittest.TestCase):
    def test_contract_splits_classification_and_trigger_baselines(self) -> None:
        contract = load_json(CONTRACT_PATH)

        self.assertEqual(contract["gate"], "N2_TRIGGER_BASELINE_SEMANTIC_REPAIR_CONTRACT_GATE")
        self.assertEqual(contract["layer_role"], "N2_condition")
        self.assertEqual(contract["contract_result"], "CONTRACT_PASS")

        mapping = contract["field_mapping"]
        classification = mapping["classification_baseline"]
        trigger = mapping["trigger_baseline_for_n4"]

        self.assertEqual(
            classification["classification_previous_open"]["source"],
            "period_trigger_baseline_json.periods[P].previous_open",
        )
        self.assertEqual(
            classification["classification_period_key_previous"]["source"],
            "period_trigger_baseline_json.periods[P].period_key_previous",
        )
        self.assertEqual(
            trigger["trigger_previous_open"]["source"],
            "period_trigger_baseline_json.periods[P].previous_open",
        )
        self.assertEqual(
            trigger["trigger_previous_close"]["source"],
            "period_trigger_baseline_json.periods[P].previous_close",
        )
        self.assertEqual(
            trigger["trigger_previous_entity_high"]["source"],
            "period_trigger_baseline_json.periods[P].previous_entity_high",
        )
        self.assertEqual(
            trigger["trigger_previous_entity_low"]["source"],
            "period_trigger_baseline_json.periods[P].previous_entity_low",
        )
        self.assertEqual(
            trigger["current_seed_entity_high"]["formula"],
            "max(current_open_seed,current_close_seed)",
        )
        self.assertEqual(
            trigger["current_seed_entity_low"]["formula"],
            "min(current_open_seed,current_close_seed)",
        )
        self.assertEqual(
            trigger["baseline_source_trade_date"]["source"],
            "source_trade_date",
        )

        compatibility = contract["compatibility_policy"]
        self.assertTrue(compatibility["legacy_previous_fields_retained_as_classification_trace"])
        self.assertFalse(compatibility["legacy_previous_fields_allowed_for_n4_trigger_baseline"])
        self.assertTrue(compatibility["n4_must_read_trigger_fields"])

        blocker_codes = {item["code"] for item in contract["p0_blockers"]}
        self.assertIn("n4_context_trigger_baseline_from_current_seed", blocker_codes)
        self.assertIn("trigger_previous_entity_missing", blocker_codes)
        self.assertIn("baseline_source_trade_date_mismatch", blocker_codes)
        self.assertIn("n4_uses_legacy_previous_as_trigger_baseline", blocker_codes)
        self.assertIn("trigger_amount_baseline_missing", blocker_codes)

    def test_preflight_samples_capture_current_failure_and_expected_trigger_values(self) -> None:
        preflight = load_json(PREFLIGHT_PATH)

        self.assertEqual(preflight["gate"], "N2_TRIGGER_BASELINE_SEMANTIC_REPAIR_PREFLIGHT_GATE")
        self.assertEqual(preflight["layer_role"], "N2_condition")
        self.assertEqual(preflight["preflight_result"], "PASS")
        self.assertEqual(preflight["current_live_semantic_status"], "SEMANTIC_FAIL")
        self.assertTrue(preflight["repair_contract_ready"])
        self.assertFalse(preflight["writes_performed"])
        self.assertFalse(preflight["will_execute_sql"])
        self.assertFalse(preflight["downstream_layers_entered"])

        stock = preflight["sample_validation"]["stock:SZ:002399"]
        self.assertEqual(stock["current_legacy_previous_entity_high"], "9.79")
        self.assertEqual(stock["current_legacy_previous_entity_low"], "9.67")
        self.assertEqual(stock["legacy_period_key_previous"], "20260603")
        self.assertEqual(stock["expected_trigger_previous_open"], "9.79")
        self.assertEqual(stock["expected_trigger_previous_close"], "9.67")
        self.assertEqual(stock["expected_trigger_previous_entity_high"], "9.79")
        self.assertEqual(stock["expected_trigger_previous_entity_low"], "9.67")
        self.assertEqual(stock["expected_baseline_source_trade_date"], "20260604")

        index = preflight["sample_validation"]["index:SZ:399006"]
        self.assertEqual(index["current_legacy_previous_entity_high"], "4122.99")
        self.assertEqual(index["current_legacy_previous_entity_low"], "4089.02")
        self.assertEqual(index["legacy_period_key_previous"], "20260603")
        self.assertEqual(index["expected_trigger_previous_entity_high"], "4122.99")
        self.assertEqual(index["expected_trigger_previous_entity_low"], "4089.02")
        self.assertEqual(index["expected_baseline_source_trade_date"], "20260604")

        board_881078 = preflight["sample_validation"]["board:TDX:881078"]
        self.assertEqual(board_881078["period"], "W")
        self.assertEqual(board_881078["expected_trigger_previous_entity_low"], "632.78")
        self.assertEqual(board_881078["expected_trigger_previous_entity_high"], "696.8")
        self.assertEqual(board_881078["expected_current_seed_entity_low"], "706.84")
        self.assertEqual(board_881078["expected_current_seed_entity_high"], "712.3")

        board = preflight["sample_validation"]["board_sample_contract"]
        self.assertEqual(board["asset_kind"], "board")
        self.assertEqual(board["expected_behavior"], "same_mapping_as_stock_and_index")
        self.assertEqual(board["trigger_field_source"], "previous complete period entity fields")

        self.assertEqual(preflight["quality"]["P0"], 0)
        self.assertTrue(preflight["implementation_gate"]["allowed"])


if __name__ == "__main__":
    unittest.main()
