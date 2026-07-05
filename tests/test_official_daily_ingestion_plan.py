import json
import subprocess
import sys
import unittest
from pathlib import Path

from ashare_v3.ingestion.official_daily_ingestion_plan import (
    FIXED_9_INDEX_IDENTITIES,
    build_official_daily_ingestion_report,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "plan_official_daily_ingestion_20260525.py"


def base_snapshot() -> dict:
    fixed_indexes = [
        {"identity_key": identity_key, "exchange": identity_key.split(":")[1], "code": identity_key.split(":")[2], "name": identity_key}
        for identity_key in FIXED_9_INDEX_IDENTITIES
    ]
    return {
        "for_trade_date": "20260525",
        "expected_scope": {
            "stock": [
                {"identity_key": "stock:SH:600000", "exchange": "SH", "code": "600000", "name": "浦发银行"},
                {"identity_key": "stock:SZ:000001", "exchange": "SZ", "code": "000001", "name": "平安银行"},
            ],
            "index": fixed_indexes,
            "board": [
                {"identity_key": "board:TDX:881001", "exchange": "TDX", "code": "881001", "name": "行业一"},
                {"identity_key": "board:TDX:881002", "exchange": "TDX", "code": "881002", "name": "行业二"},
            ],
        },
        "current_fact_identity_keys": {
            "stock": set(),
            "index": set(),
            "board": set(),
        },
        "current_fact_rows": {"stock": 0, "index": 0, "board": 0},
        "current_fact_object_counts": {"stock": 0, "index": 0, "board": 0},
        "source_versions_for_trade_date": {"stock": [], "index": [], "board": []},
        "active_source_versions_for_trade_date": [],
        "target_source_version_conflicts": {"stock": 0, "index": 0, "board": 0},
        "contract_batch_exists": False,
        "duplicate_identity_rows": {"stock": 0, "index": 0, "board": 0},
        "same_code_contamination": {"stock": 0, "index": 0, "board": 0},
    }


class OfficialDailyIngestionPlanTest(unittest.TestCase):
    def test_builds_plan_only_missing_counts_without_write_side_effects(self) -> None:
        report = build_official_daily_ingestion_report(base_snapshot())

        self.assertEqual(report["result"], "DRY_RUN_PASS")
        self.assertEqual(report["expected_eod_coverage_objects"], {"stock": 2, "index": 9, "board": 2, "total": 13})
        self.assertEqual(report["available_official_daily_before_execute"], {"stock": 0, "index": 0, "board": 0, "total": 0})
        self.assertEqual(report["missing_official_daily"]["missing_by_asset"], {"stock": 2, "index": 9, "board": 2, "total": 13})
        self.assertEqual(report["source_versions"]["stock"], "stock_daily_20260525_v1")
        self.assertFalse(report["side_effects"]["writes_postgres"])
        self.assertFalse(report["side_effects"]["writes_parquet"])
        self.assertFalse(report["side_effects"]["updates_active_source_version"])
        self.assertFalse(report["side_effects"]["enters_n3_n4_n5_n6"])

    def test_source_version_or_active_conflict_is_p0_blocker(self) -> None:
        snapshot = base_snapshot()
        snapshot["target_source_version_conflicts"] = {"stock": 1, "index": 0, "board": 0}
        snapshot["active_source_versions_for_trade_date"] = [
            {
                "data_domain": "stock",
                "data_type": "stock_daily",
                "scope_key": "20260525",
                "source_version": "stock_daily_20260525_v1",
                "source_batch_id": "official_daily_ingest_20260525_v1",
            }
        ]

        report = build_official_daily_ingestion_report(snapshot)

        self.assertEqual(report["result"], "DRY_RUN_BLOCKED")
        self.assertEqual(report["quality"]["p0_count"], 2)
        failed_gate_names = {item["gate_name"] for item in report["quality"]["items"] if item["status"] == "failed"}
        self.assertIn("existing_source_version_conflict", failed_gate_names)
        self.assertIn("existing_active_source_version_conflict", failed_gate_names)

    def test_fixed_9_index_scope_coverage_is_required(self) -> None:
        snapshot = base_snapshot()
        snapshot["expected_scope"]["index"] = snapshot["expected_scope"]["index"][:-1]

        report = build_official_daily_ingestion_report(snapshot)

        self.assertEqual(report["result"], "DRY_RUN_BLOCKED")
        failed_gate_names = {item["gate_name"] for item in report["quality"]["items"] if item["status"] == "failed"}
        self.assertIn("fixed_9_index_scope_coverage", failed_gate_names)
        self.assertEqual(report["quality"]["p0_count"], 1)

    def test_execute_flag_is_rejected_by_plan_only_cli(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--execute"],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("dry-run planner only", result.stderr)

    def test_report_json_is_serializable(self) -> None:
        report = build_official_daily_ingestion_report(base_snapshot())
        encoded = json.dumps(report, ensure_ascii=False)

        self.assertIn("official_daily_ingest_20260525_v1", encoded)


if __name__ == "__main__":
    unittest.main()
