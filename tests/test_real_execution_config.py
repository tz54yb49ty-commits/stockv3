import unittest
from pathlib import Path

from ashare_v3.ingestion.common import IngestionValidationError
from ashare_v3.ingestion.real_execution_config import EXPECTED_CONFIRMATION_ITEMS, load_real_execution_config, real_execution_config_from_mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / "real_execution.example.toml"


class RealExecutionConfigTest(unittest.TestCase):
    def test_example_config_loads_as_not_ready_to_execute(self) -> None:
        config = load_real_execution_config(CONFIG_PATH)

        self.assertEqual(config.mode, "preflight_only")
        self.assertEqual(config.approved_stage, "none")
        self.assertFalse(config.allow_real_execution)
        self.assertFalse(config.ready_to_execute)

    def test_example_config_has_no_embedded_secrets(self) -> None:
        config = load_real_execution_config(CONFIG_PATH)
        config_text = CONFIG_PATH.read_text(encoding="utf-8")

        self.assertEqual(config.tushare_token_env, "TUSHARE_TOKEN")
        self.assertEqual(config.postgres_dsn_env, "ASHARE_V3_POSTGRES_DSN")
        self.assertNotIn("c8b091", config_text)
        self.assertNotIn("postgres://", config_text)
        self.assertNotIn("postgresql://", config_text)

    def test_example_config_keeps_paths_and_permissions_safe(self) -> None:
        config = load_real_execution_config(CONFIG_PATH)

        self.assertEqual(config.data_root, "/Volumes/MacRaid/database")
        self.assertEqual(config.tdx_root, "/Volumes/MacRaid/tdxdata/tdx")
        self.assertTrue(all(value is False for value in config.permissions.values()))
        self.assertFalse(config.permissions["allow_old_system_access"])
        self.assertFalse(config.permissions["allow_worker_start"])

    def test_example_config_requires_quality_gate_and_rollback_guards(self) -> None:
        config = load_real_execution_config(CONFIG_PATH)

        self.assertTrue(all(value is True for value in config.quality_gate.values()))
        self.assertEqual(config.rollback["strategy"], "delete_by_source_batch_id_then_restore_previous_active_source_version")
        self.assertTrue(config.rollback["require_manifest_rollback_plan"])
        self.assertTrue(config.rollback["require_failed_audit_retention"])

    def test_example_config_lists_all_preflight_items(self) -> None:
        config = load_real_execution_config(CONFIG_PATH)

        self.assertEqual(set(config.required_confirmation_items), set(EXPECTED_CONFIRMATION_ITEMS))
        self.assertEqual(len(config.required_confirmation_items), 13)
        self.assertIn("source.tdx_local_txt_read", config.required_confirmation_items)
        self.assertIn("database.postgresql_schema_and_write", config.required_confirmation_items)
        self.assertIn("safety.old_system_boundary", config.required_confirmation_items)

    def test_config_rejects_real_execution_authorization_in_template(self) -> None:
        data = minimal_valid_config()
        data["real_execution"]["allow_real_execution"] = True

        with self.assertRaises(IngestionValidationError):
            real_execution_config_from_mapping(data)

    def test_config_rejects_embedded_token_key(self) -> None:
        data = minimal_valid_config()
        data["security"]["tushare_token"] = "do-not-store-this"

        with self.assertRaises(IngestionValidationError):
            real_execution_config_from_mapping(data)

    def test_config_rejects_enabled_database_write(self) -> None:
        data = minimal_valid_config()
        data["permissions"]["allow_database_write"] = True

        with self.assertRaises(IngestionValidationError):
            real_execution_config_from_mapping(data)


def minimal_valid_config() -> dict[str, object]:
    config = load_real_execution_config(CONFIG_PATH).to_dict()
    return {
        "real_execution": {
            "mode": config["mode"],
            "approved_stage": config["approved_stage"],
            "allow_real_execution": config["allow_real_execution"],
            "operator_confirmation_id": config["operator_confirmation_id"],
        },
        "configs": dict(config["configs"]),
        "paths": dict(config["paths"]),
        "security": {
            **dict(config["security"]),
            "store_secret_in_config": False,
        },
        "permissions": dict(config["permissions"]),
        "quality_gate": dict(config["quality_gate"]),
        "rollback": dict(config["rollback"]),
        "preflight": {
            "required_confirmation_items": list(config["preflight"]["required_confirmation_items"]),
        },
    }


if __name__ == "__main__":
    unittest.main()
