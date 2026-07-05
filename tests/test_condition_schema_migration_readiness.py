import unittest
from pathlib import Path

from ashare_v3.condition.execute_preflight import REQUIRED_SCHEMA_TABLES
from ashare_v3.condition.schema_migration_readiness import (
    FOREIGN_KEY_DEPENDENCY_TABLES,
    build_condition_schema_migration_readiness_report_from_sql,
)


SCHEMA_PATH = Path("sql/002_condition_layer_schema.sql")


class ConditionSchemaMigrationReadinessTest(unittest.TestCase):
    def test_current_schema_is_static_ready(self) -> None:
        sql_text = SCHEMA_PATH.read_text(encoding="utf-8")
        report = build_condition_schema_migration_readiness_report_from_sql(sql_text)
        payload = report.to_dict()

        self.assertTrue(payload["static_ready"])
        self.assertTrue(payload["ready_for_user_migration_review"])
        self.assertEqual(payload["table_count"], len(REQUIRED_SCHEMA_TABLES))
        self.assertGreater(payload["index_count"], 0)
        self.assertFalse(payload["side_effects"]["will_execute_sql"])

    def test_missing_required_table_fails_static_gate(self) -> None:
        sql_text = "BEGIN;\nCREATE TABLE common_condition_run (run_id TEXT PRIMARY KEY);\nCOMMIT;\n"
        report = build_condition_schema_migration_readiness_report_from_sql(sql_text)
        failed = failed_gate_names(report.to_dict())

        self.assertFalse(report.static_ready)
        self.assertIn("condition_schema_required_tables_present", failed)
        self.assertIn("condition_schema_required_columns_present", failed)

    def test_database_status_can_mark_first_apply_ready(self) -> None:
        sql_text = SCHEMA_PATH.read_text(encoding="utf-8")
        db_status = {
            "checked": True,
            "read_only": True,
            "condition_tables_existing": [],
            "condition_tables_missing": list(REQUIRED_SCHEMA_TABLES),
            "fk_dependency_missing": [],
            "runtime_dependency_missing": [],
            "ready_for_first_apply": True,
            "manual_review_required": False,
            "migration_required": True,
            "migration_performed": False,
        }
        report = build_condition_schema_migration_readiness_report_from_sql(sql_text, database_status=db_status)

        self.assertTrue(report.ready_for_user_migration_review)
        self.assertTrue(report.database_ready_for_first_apply)
        self.assertTrue(report.to_dict()["side_effects"]["read_only_database_checks"])

    def test_existing_condition_table_requires_manual_review(self) -> None:
        sql_text = SCHEMA_PATH.read_text(encoding="utf-8")
        db_status = {
            "checked": True,
            "read_only": True,
            "condition_tables_existing": ["common_condition_run"],
            "condition_tables_missing": [table for table in REQUIRED_SCHEMA_TABLES if table != "common_condition_run"],
            "fk_dependency_missing": [],
            "runtime_dependency_missing": [],
            "ready_for_first_apply": False,
            "manual_review_required": True,
            "migration_required": True,
            "migration_performed": False,
        }
        report = build_condition_schema_migration_readiness_report_from_sql(sql_text, database_status=db_status)

        self.assertFalse(report.ready_for_user_migration_review)
        self.assertFalse(report.database_ready_for_first_apply)

    def test_foreign_key_dependencies_are_declared(self) -> None:
        sql_text = SCHEMA_PATH.read_text(encoding="utf-8")
        report = build_condition_schema_migration_readiness_report_from_sql(sql_text)
        gate = gate_by_name(report.to_dict(), "condition_schema_fk_dependencies_declared")

        self.assertEqual(gate["status"], "passed")
        for table_name in FOREIGN_KEY_DEPENDENCY_TABLES:
            self.assertIn(table_name, gate["details"]["external_reference_tables"])


def failed_gate_names(payload: dict[str, object]) -> set[str]:
    return {
        str(gate["gate_name"])
        for gate in payload["quality_gates"]  # type: ignore[index]
        if gate["status"] != "passed"
    }


def gate_by_name(payload: dict[str, object], gate_name: str) -> dict[str, object]:
    for gate in payload["quality_gates"]:  # type: ignore[index]
        if gate["gate_name"] == gate_name:
            return gate
    raise AssertionError(f"missing gate: {gate_name}")


if __name__ == "__main__":
    unittest.main()
