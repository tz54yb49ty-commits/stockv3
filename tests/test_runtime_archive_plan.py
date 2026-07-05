import unittest
from pathlib import Path
import tempfile

from ashare_v3.ingestion.runtime_archive import (
    DEFAULT_RUNTIME_ARCHIVE_ROOT,
    build_runtime_archive_plan,
    inspect_archive_storage,
)


class RuntimeArchivePlanTest(unittest.TestCase):
    def test_runtime_archive_plan_uses_macraid_trade_date_layer_paths(self) -> None:
        plan = build_runtime_archive_plan(
            trade_date="20260612",
            table_summaries=[
                {
                    "layer": "n3",
                    "table": "stock_minute_bar_1m",
                    "row_count": 705120,
                    "checksum": "sha256:n3-stock-minute",
                },
                {"layer": "n4", "table": "common_trigger_match", "row_count": 4454},
                {"layer": "n5", "table": "common_action_event", "row_count": 43},
                {"layer": "n6", "table": "user_signal_projection", "row_count": 0},
            ],
            sealed_layers={"n3": True, "n4": True, "n5": True, "n6": True},
            storage_status={"mounted": True, "writable": True, "free_bytes": 10 * 1024**3},
        )

        self.assertEqual(plan.trade_date, "20260612")
        self.assertEqual(plan.archive_root, DEFAULT_RUNTIME_ARCHIVE_ROOT)
        self.assertEqual(plan.status, "ARCHIVE_PREFLIGHT_PASS")
        self.assertFalse(plan.cleanup_eligible)
        self.assertIn("manual_cleanup_required", plan.cleanup_blockers)
        self.assertEqual(
            plan.files[0].path,
            "/Volumes/MacRaid/stock_db_archive/v3_runtime/trade_date=20260612/n3/stock_minute_bar_1m.parquet",
        )
        self.assertEqual(
            plan.manifest_path,
            "/Volumes/MacRaid/stock_db_archive/v3_runtime/trade_date=20260612/manifests/archive_manifest.json",
        )
        manifest = plan.to_manifest_dict()
        self.assertEqual(manifest["files"][0]["checksum"], "sha256:n3-stock-minute")
        self.assertFalse(manifest["side_effects"]["writes_database"])
        self.assertFalse(manifest["side_effects"]["writes_archive_files"])
        self.assertFalse(manifest["side_effects"]["cleanup_local_runtime"])

    def test_runtime_archive_blocks_when_macraid_is_unavailable(self) -> None:
        plan = build_runtime_archive_plan(
            trade_date="20260612",
            table_summaries=[{"layer": "n3", "table": "common_market_data_run", "row_count": 1}],
            sealed_layers={"n3": True},
            storage_status={"mounted": False, "writable": False, "free_bytes": 0},
        )

        self.assertEqual(plan.status, "BLOCKED")
        self.assertIn("macraid_not_mounted", plan.blockers)
        self.assertFalse(plan.cleanup_eligible)

    def test_runtime_archive_blocks_unsealed_layers_and_delivering_outbox(self) -> None:
        plan = build_runtime_archive_plan(
            trade_date="20260612",
            table_summaries=[
                {"layer": "n4", "table": "common_event_outbox", "row_count": 4454},
            ],
            sealed_layers={"n4": False},
            storage_status={"mounted": True, "writable": True, "free_bytes": 10 * 1024**3},
            delivering_outbox_count=2,
        )

        self.assertEqual(plan.status, "BLOCKED")
        self.assertIn("layer_not_sealed:n4", plan.blockers)
        self.assertIn("outbox_delivering_not_zero", plan.blockers)

    def test_inspect_archive_storage_reports_tempdir_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            status = inspect_archive_storage(Path(tmp), minimum_free_bytes=1)

        self.assertTrue(status["mounted"])
        self.assertTrue(status["writable"])
        self.assertGreater(int(status["free_bytes"]), 0)

    def test_inspect_archive_storage_uses_existing_parent_for_missing_target_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "stock_db_archive" / "v3_runtime"
            status = inspect_archive_storage(target, minimum_free_bytes=1)

        self.assertTrue(status["mounted"])
        self.assertTrue(status["writable"])
        self.assertFalse(status["archive_root_exists"])
        self.assertEqual(status["probe_path"], tmp)


if __name__ == "__main__":
    unittest.main()
