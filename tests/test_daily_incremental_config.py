import unittest
from pathlib import Path

from ashare_v3.ingestion.common import IngestionValidationError
from ashare_v3.ingestion.daily_incremental_config import (
    build_daily_incremental_plan_from_config,
    daily_incremental_config_from_mapping,
    load_daily_incremental_config,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / "daily_incremental.example.toml"


class DailyIncrementalConfigTest(unittest.TestCase):
    def test_example_config_loads_without_embedded_secret(self) -> None:
        config = load_daily_incremental_config(CONFIG_PATH)
        config_text = CONFIG_PATH.read_text(encoding="utf-8")

        self.assertEqual(config.trade_date, "20260522")
        self.assertEqual(config.version, "v1")
        self.assertEqual(config.data_root, "/Volumes/MacRaid/database")
        self.assertEqual(config.tdx_root, "/Volumes/MacRaid/tdxdata/tdx")
        self.assertEqual(config.tushare_token_env, "TUSHARE_TOKEN")
        self.assertNotIn("c8b091", config_text)

    def test_config_builds_daily_plan(self) -> None:
        plan = build_daily_incremental_plan_from_config(CONFIG_PATH)

        self.assertTrue(plan.passed)
        self.assertEqual(plan.trade_date, "20260522")
        self.assertEqual(plan.version, "v1")
        self.assertEqual(len(plan.tasks), 11)
        self.assertEqual(plan.data_root, "/Volumes/MacRaid/database")
        self.assertFalse(plan.will_call_external_sources)
        self.assertFalse(plan.will_read_tdx_files)
        self.assertFalse(plan.will_connect_database)
        self.assertFalse(plan.will_execute_sql)
        self.assertFalse(plan.will_write_data_files)

    def test_daily_batch_ids_are_single_trade_date(self) -> None:
        plan = build_daily_incremental_plan_from_config(CONFIG_PATH)
        batch_ids = [task.batch_spec.batch_id for task in plan.tasks]

        self.assertIn("stock_daily_20260522_v1", batch_ids)
        self.assertIn("stock_daily_basic_20260522_v1", batch_ids)
        self.assertIn("index_membership_20260522_v1", batch_ids)
        self.assertIn("board_membership_20260522_v1", batch_ids)
        for task in plan.tasks:
            self.assertEqual(task.batch_spec.source_version, task.batch_spec.batch_id)
            self.assertTrue(task.active_source_version_plan.activation_allowed)

    def test_tdx_sources_are_marked_daily_read_local_txt(self) -> None:
        config = load_daily_incremental_config(CONFIG_PATH)

        self.assertEqual(config.sources["board_identity"]["refresh_policy"], "daily_read_local_txt")
        self.assertEqual(config.sources["index_membership"]["refresh_policy"], "daily_read_local_txt")
        self.assertEqual(config.sources["board_membership"]["refresh_policy"], "daily_read_local_txt")

    def test_config_rejects_enabled_side_effects(self) -> None:
        data = minimal_valid_config()
        data["side_effects"]["allow_tdx_file_read"] = True

        with self.assertRaises(IngestionValidationError):
            daily_incremental_config_from_mapping(data)

    def test_config_rejects_embedded_token_key(self) -> None:
        data = minimal_valid_config()
        data["security"]["tushare_token"] = "do-not-store-this"

        with self.assertRaises(IngestionValidationError):
            daily_incremental_config_from_mapping(data)

    def test_config_rejects_missing_source_section(self) -> None:
        data = minimal_valid_config()
        del data["sources"]["stock_daily_basic"]

        with self.assertRaises(IngestionValidationError):
            daily_incremental_config_from_mapping(data)

    def test_config_rejects_mixed_daily_table_override(self) -> None:
        data = minimal_valid_config()
        data["sources"]["stock_daily"]["target_table"] = "daily_bar_fact"

        with self.assertRaises(IngestionValidationError):
            daily_incremental_config_from_mapping(data)


def minimal_valid_config() -> dict[str, object]:
    config = load_daily_incremental_config(CONFIG_PATH).to_dict()
    return {
        "daily_incremental": {
            "trade_date": config["trade_date"],
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
