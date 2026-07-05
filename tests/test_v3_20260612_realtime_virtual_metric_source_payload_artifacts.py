import json
import unittest
from collections import Counter
from pathlib import Path

from ashare_v3.market import v3_realtime_virtual_metric_writer as writer


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD_PATH = ROOT / "docs" / "V3_20260612_realtime_virtual_metric_writer_payload.json"
PREFLIGHT_PATH = ROOT / "docs" / "V3_20260612_REALTIME_VIRTUAL_METRIC_WRITER_RUNNER_PREFLIGHT.json"
CONTRACT_PATH = ROOT / "docs" / "V3_20260612_REALTIME_VIRTUAL_METRIC_WRITER_RUNNER_CONTRACT.json"
GATE_PATH = ROOT / "docs" / "V3_20260612_REALTIME_VIRTUAL_METRIC_SOURCE_PAYLOAD_CONTRACT_PREFLIGHT.json"


class V320260612RealtimeVirtualMetricSourcePayloadArtifactsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = json.loads(PAYLOAD_PATH.read_text(encoding="utf-8"))
        self.preflight = json.loads(PREFLIGHT_PATH.read_text(encoding="utf-8"))
        self.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        self.gate = json.loads(GATE_PATH.read_text(encoding="utf-8"))

    def test_payload_has_expected_candidate_universe(self) -> None:
        self.assertEqual(self.payload["result"], "SOURCE_PAYLOAD_PREFLIGHT_PASS")
        candidates = self.payload["candidates"]
        self.assertEqual(len(candidates), 100)
        self.assertEqual(Counter(c["signal_type"] for c in candidates), {"B_BUY": 76, "S_SELL": 24})

    def test_payload_has_sufficient_source_records_for_each_candidate(self) -> None:
        records_by_code = self.payload["source_records"]
        missing_codes = []
        missing_current_labels = []
        for candidate in self.payload["candidates"]:
            records = records_by_code.get(candidate["code"], [])
            if not records:
                missing_codes.append(candidate["code"])
                continue
            labels = {record["datetime"] for record in records}
            if candidate["minute_label"] not in labels:
                missing_current_labels.append((candidate["code"], candidate["minute_label"]))

        self.assertEqual(missing_codes, [])
        self.assertEqual(missing_current_labels, [])

    def test_d_w_m_q_y_context_is_complete_for_every_candidate(self) -> None:
        required_fields = {
            "current_open",
            "previous_open",
            "previous_close",
            "previous_amount",
            "elapsed_units",
            "total_units",
            "current_amount_seed",
        }
        missing = []
        for candidate in self.payload["candidates"]:
            context = candidate.get("higher_period_context", {})
            for period in ["D", "W", "M", "Q", "Y"]:
                period_context = context.get(period, {})
                absent = sorted(field for field in required_fields if period_context.get(field) is None)
                if absent:
                    missing.append((candidate["identity_key"], period, absent))

        self.assertEqual(missing, [])

    def test_payload_is_runner_compatible_and_validates_against_contract(self) -> None:
        rows_by_asset = writer.build_rows_by_asset_from_source_payload(self.contract, self.payload)
        validation = writer.validate_rows_against_contract(rows_by_asset, self.contract)

        self.assertTrue(validation["valid"], validation)
        self.assertEqual(validation["row_counts"]["total"], 100)
        self.assertEqual(validation["signal_counts"], {"B_BUY": 76, "S_SELL": 24})
        rows = [row for asset_rows in rows_by_asset.values() for row in asset_rows]
        self.assertEqual(sum(1 for row in rows if not row["metric_ready"]), 0)

    def test_refreshed_preflight_removes_payload_and_schema_blockers(self) -> None:
        self.assertEqual(self.preflight["result"], "PREFLIGHT_PASS")
        self.assertEqual(self.preflight["P0_P1_P2"], {"P0": 0, "P1": 0, "P2": 0})
        self.assertTrue(self.preflight["execute_ready"])
        self.assertEqual(self.preflight["blockers"], [])
        nullable_schema = self.preflight["source_snapshot_id_nullable_schema"]["live_schema"]
        for table_proof in nullable_schema.values():
            self.assertEqual(table_proof["source_snapshot_id_is_nullable"], "YES")
            self.assertTrue(table_proof["fk_present"])
        self.assertNotIn(
            "source_payload_artifact_required_before_execute_final_gate",
            json.dumps(self.preflight, ensure_ascii=False),
        )

    def test_gate_artifact_records_pass_and_authorized_old_db_read_only_boundary(self) -> None:
        self.assertEqual(self.gate["result"], "SOURCE_PAYLOAD_PREFLIGHT_PASS")
        self.assertEqual(self.gate["candidate_proof"]["candidate_count"], 100)
        self.assertEqual(self.gate["candidate_proof"]["signal_distribution"], {"B_BUY": 76, "S_SELL": 24})
        self.assertTrue(self.gate["old_system_reference"]["authorized_read_only"])
        self.assertFalse(self.gate["old_system_reference"]["registered_as_active_lineage"])
        self.assertFalse(self.gate["side_effects"]["v3_database_written"])
        self.assertFalse(self.gate["side_effects"]["old_system_modified"])


if __name__ == "__main__":
    unittest.main()
