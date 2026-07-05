import unittest
from pathlib import Path

from ashare_v3.ingestion.backfill_config import build_initial_backfill_plan_from_config, initial_backfill_config_from_mapping, load_initial_backfill_config
from ashare_v3.ingestion.common import IngestionValidationError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / "initial_backfill.example.toml"


class InitialBackfillConfigTest(unittest.TestCase):
    def test_example_config_loads_without_embedded_secret(self) -> None:
        config = load_initial_backfill_config(CONFIG_PATH)
        config_text = CONFIG_PATH.read_text(encoding="utf-8")

        self.assertEqual(config.start_date, "20230101")
        self.assertEqual(config.end_date, "20260521")
        self.assertEqual(config.snapshot_date, "20260521")
        self.assertEqual(config.data_root, "/Volumes/MacRaid/database")
        self.assertEqual(config.tdx_root, "/Volumes/MacRaid/tdxdata/tdx")
        self.assertEqual(config.tushare_token_env, "TUSHARE_TOKEN")
        self.assertNotIn("c8b091", config_text)

    def test_config_builds_default_backfill_plan(self) -> None:
        plan = build_initial_backfill_plan_from_config(CONFIG_PATH)

        self.assertTrue(plan.passed)
        self.assertEqual(plan.batch_count, 211)
        self.assertEqual(plan.data_root, "/Volumes/MacRaid/database")
        self.assertFalse(plan.will_call_external_sources)
        self.assertFalse(plan.will_connect_database)
        self.assertFalse(plan.will_write_data_files)

    def test_config_rejects_enabled_side_effects(self) -> None:
        data = minimal_valid_config()
        data["side_effects"]["allow_network"] = True

        with self.assertRaises(IngestionValidationError):
            initial_backfill_config_from_mapping(data)

    def test_config_rejects_embedded_token_key(self) -> None:
        data = minimal_valid_config()
        data["security"]["tushare_token"] = "do-not-store-this"

        with self.assertRaises(IngestionValidationError):
            initial_backfill_config_from_mapping(data)

    def test_config_rejects_missing_source_section(self) -> None:
        data = minimal_valid_config()
        del data["sources"]["stock_daily"]

        with self.assertRaises(IngestionValidationError):
            initial_backfill_config_from_mapping(data)

    def test_config_rejects_mixed_daily_table_override(self) -> None:
        data = minimal_valid_config()
        data["sources"]["stock_daily"]["target_table"] = "daily_bar_fact"

        with self.assertRaises(IngestionValidationError):
            initial_backfill_config_from_mapping(data)


def minimal_valid_config() -> dict[str, object]:
    config = load_initial_backfill_config(CONFIG_PATH).to_dict()
    return {
        "backfill": {
            "start_date": config["start_date"],
            "end_date": config["end_date"],
            "snapshot_date": config["snapshot_date"],
            "version": config["version"],
        },
        "paths": {
            "data_root": config["data_root"],
            "tdx_root": config["tdx_root"],
        },
        "security": {
            "tushare_token_env": config["tushare_token_env"],
            "postgres_dsn_env": config["postgres_dsn_env"],
            "store_secret_in_config": False,
        },
        "side_effects": {
            "allow_network": False,
            "allow_tdx_file_read": False,
            "allow_database_write": False,
            "allow_data_file_write": False,
            "allow_worker_start": False,
        },
        "sources": {
            key: dict(value)
            for key, value in config["sources"].items()
        },
    }


if __name__ == "__main__":
    unittest.main()
