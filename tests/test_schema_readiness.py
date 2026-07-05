import unittest
from pathlib import Path
from ashare_v3.ingestion.schema_readiness import (
    REQUIRED_SCHEMA_TABLES,
    build_schema_readiness_report,
    build_schema_readiness_report_from_sql,
    parse_create_tables,
)


SCHEMA_PATH = "sql/001_raw_ingestion_schema.sql"


class SchemaReadinessTest(unittest.TestCase):
    def test_schema_readiness_passes_for_current_schema(self) -> None:
        report = build_schema_readiness_report(SCHEMA_PATH)

        self.assertTrue(report.passed)
        self.assertEqual(report.required_table_count, 14)
        self.assertEqual(report.table_count, 14)
        self.assertEqual(len(report.table_summaries), 14)
        self.assertEqual({summary.table_name for summary in report.table_summaries}, set(REQUIRED_SCHEMA_TABLES))

    def test_schema_has_required_core_tables_and_no_mixed_daily_table(self) -> None:
        tables = parse_create_tables(Path(SCHEMA_PATH).read_text(encoding="utf-8"))

        self.assertIn("stock_daily_bar_fact", tables)
        self.assertIn("index_daily_bar_fact", tables)
        self.assertIn("board_daily_bar_fact", tables)
        self.assertIn("stock_daily_basic", tables)
        self.assertNotIn("daily_bar_fact", tables)

    def test_schema_target_tables_have_source_metadata(self) -> None:
        report = build_schema_readiness_report(SCHEMA_PATH)
        summaries = {summary.table_name: summary for summary in report.table_summaries}

        for table_name in (
            "common_trade_calendar",
            "stock_identity",
            "index_identity",
            "board_identity",
            "stock_daily_bar_fact",
            "stock_daily_basic",
            "index_daily_bar_fact",
            "board_daily_bar_fact",
            "stock_financial_metrics_fact",
            "index_membership_fact",
            "board_membership_fact",
        ):
            self.assertTrue(summaries[table_name].has_source_batch_id, table_name)
            self.assertTrue(summaries[table_name].has_source_version, table_name)

    def test_schema_fact_tables_keep_identity_keys(self) -> None:
        report = build_schema_readiness_report(SCHEMA_PATH)
        summaries = {summary.table_name: summary for summary in report.table_summaries}

        self.assertEqual(summaries["stock_daily_bar_fact"].identity_key_columns, ("stock_identity_key",))
        self.assertEqual(summaries["stock_daily_basic"].identity_key_columns, ("stock_identity_key",))
        self.assertEqual(summaries["index_daily_bar_fact"].identity_key_columns, ("index_identity_key",))
        self.assertEqual(summaries["board_daily_bar_fact"].identity_key_columns, ("board_identity_key",))
        self.assertEqual(summaries["index_membership_fact"].identity_key_columns, ("index_identity_key", "stock_identity_key"))
        self.assertEqual(summaries["board_membership_fact"].identity_key_columns, ("board_identity_key", "stock_identity_key"))

    def test_schema_has_audit_quality_gate_and_rollback_columns(self) -> None:
        tables = parse_create_tables(Path(SCHEMA_PATH).read_text(encoding="utf-8"))

        self.assertTrue({"rollback_strategy", "status", "quality_gate_summary", "error_summary"}.issubset(tables["common_ingest_batch"]))
        self.assertTrue({"source_batch_id", "source_version", "gate_name", "severity", "status", "details"}.issubset(tables["common_quality_gate_result"]))
        self.assertTrue({"source_batch_id", "source_version", "previous_source_version", "activated_at"}.issubset(tables["common_active_source_version"]))

    def test_schema_readiness_has_no_side_effects(self) -> None:
        report = build_schema_readiness_report(SCHEMA_PATH)

        self.assertFalse(report.will_connect_database)
        self.assertFalse(report.will_execute_sql)
        self.assertFalse(report.will_write_data_files)
        self.assertFalse(report.will_call_external_sources)
        self.assertFalse(report.will_read_tdx_files)

    def test_schema_readiness_rejects_forbidden_mixed_table(self) -> None:
        sql = """
        CREATE TABLE common_ingest_batch (batch_id TEXT, rollback_strategy TEXT, status TEXT, error_summary TEXT, quality_gate_summary JSONB);
        CREATE TABLE daily_bar_fact (source_batch_id TEXT, source_version TEXT);
        """
        report = build_schema_readiness_report_from_sql(sql)
        failed_gate_names = {gate.gate_name for gate in report.quality_gates if not gate.passed}

        self.assertFalse(report.passed)
        self.assertIn("schema_no_mixed_daily_bar_fact", failed_gate_names)


if __name__ == "__main__":
    unittest.main()
