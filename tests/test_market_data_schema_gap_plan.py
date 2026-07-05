import re
import unittest

from ashare_v3.market.schema_gap_plan import (
    CurrentColumn,
    CurrentSchemaMetadata,
    CurrentUniqueConstraint,
    MissingUniqueConstraint,
    build_market_data_schema_gap_report_from_metadata,
    generate_additive_migration_sql,
    parse_target_schema,
)


class MarketDataSchemaGapPlanTest(unittest.TestCase):
    def test_parser_reads_006_007_008_tables_columns_and_unique_constraints(self) -> None:
        schema = parse_target_schema(
            (
                "sql/006_market_data_layer_schema.sql",
                "sql/007_market_data_fact_schema.sql",
                "sql/008_common_event_infra_schema.sql",
            )
        )

        self.assertIn("common_market_data_subscription", schema.tables)
        self.assertIn("stock_realtime_daily_snapshot", schema.tables)
        self.assertIn("common_event_outbox", schema.tables)
        self.assertIn("source_scope_ids", schema.tables["common_market_data_subscription"].columns)
        self.assertIn("snapshot_time", schema.tables["stock_realtime_daily_snapshot"].columns)
        outbox_uniques = {
            item.constraint_name: item.columns
            for item in schema.tables["common_event_outbox"].unique_constraints
        }
        self.assertEqual(outbox_uniques["uq_common_event_outbox_event_id"], ("event_id",))
        self.assertEqual(
            outbox_uniques["uq_common_event_outbox_dedup"],
            ("source_layer", "event_type", "source_run_id", "dedup_key", "event_schema_version"),
        )
        ledger_uniques = {
            item.constraint_name: item.columns
            for item in schema.tables["common_event_ledger"].unique_constraints
        }
        self.assertEqual(
            ledger_uniques["uq_common_event_ledger_dedup"],
            ("source_layer", "event_type", "source_run_id", "dedup_key", "event_schema_version"),
        )
        self.assertEqual(schema.forbidden_runtime_table_hits, ())
        self.assertEqual(schema.forbidden_user_event_hits, ())

    def test_missing_tables_are_additive_safe_and_generate_create_table_sql(self) -> None:
        schema = parse_target_schema(("sql/008_common_event_infra_schema.sql",))
        metadata = CurrentSchemaMetadata(
            checked_readonly=True,
            existing_tables=(),
            missing_dependency_tables=(),
            columns_by_table={},
            unique_constraints_by_table={},
        )

        report = build_market_data_schema_gap_report_from_metadata(
            target_schema=schema,
            current_metadata=metadata,
        )
        migration_sql = generate_additive_migration_sql(report)

        self.assertIn("common_event_outbox", report.missing_tables)
        self.assertFalse(report.manual_review_required)
        self.assertTrue(report.migration_safe_to_apply)
        self.assertIn("CREATE TABLE IF NOT EXISTS common_event_outbox", migration_sql)
        self.assertIn(
            "CREATE INDEX IF NOT EXISTS idx_common_event_outbox_pending "
            "ON common_event_outbox(status, next_attempt_at NULLS FIRST, created_at, outbox_id);",
            migration_sql,
        )
        self.assertIsNone(
            re.search(r"(^|;)\s*(DROP|INSERT|UPDATE|DELETE)\b", migration_sql, flags=re.IGNORECASE)
        )

    def test_existing_table_gaps_report_missing_column_type_mismatch_and_unique_constraint(self) -> None:
        schema = parse_target_schema(("sql/008_common_event_infra_schema.sql",))
        current_columns = {
            "common_event_outbox": {
                "outbox_id": CurrentColumn("common_event_outbox", "outbox_id", "bigint", True, None),
                "event_id": CurrentColumn("common_event_outbox", "event_id", "text", True, None),
                "event_type": CurrentColumn("common_event_outbox", "event_type", "integer", True, None),
            }
        }
        metadata = CurrentSchemaMetadata(
            checked_readonly=True,
            existing_tables=("common_event_outbox",),
            missing_dependency_tables=(),
            columns_by_table=current_columns,
            unique_constraints_by_table={
                "common_event_outbox": (
                    CurrentUniqueConstraint(
                        table_name="common_event_outbox",
                        constraint_name="common_event_outbox_pkey",
                        columns=("outbox_id",),
                        kind="primary_key",
                    ),
                )
            },
        )

        report = build_market_data_schema_gap_report_from_metadata(
            target_schema=schema,
            current_metadata=metadata,
        )
        missing_columns = {(item.table_name, item.column_name) for item in report.missing_columns}
        mismatches = {(item.table_name, item.column_name) for item in report.type_mismatches}
        missing_uniques = {item.constraint_name for item in report.missing_unique_constraints}

        self.assertIn(("common_event_outbox", "event_schema_version"), missing_columns)
        self.assertIn(("common_event_outbox", "event_type"), mismatches)
        self.assertIn("uq_common_event_outbox_event_id", missing_uniques)
        self.assertTrue(report.manual_review_required)
        self.assertFalse(report.migration_safe_to_apply)
        self.assertGreater(report.p0_count, 0)

    def test_generated_sql_handles_missing_columns_and_unique_constraints_as_additive_draft(self) -> None:
        schema = parse_target_schema(("sql/008_common_event_infra_schema.sql",))
        metadata = CurrentSchemaMetadata(
            checked_readonly=True,
            existing_tables=("common_event_outbox",),
            missing_dependency_tables=(),
            columns_by_table={
                "common_event_outbox": {
                    "outbox_id": CurrentColumn("common_event_outbox", "outbox_id", "bigint", True, None),
                    "event_id": CurrentColumn("common_event_outbox", "event_id", "text", True, None),
                    "event_type": CurrentColumn("common_event_outbox", "event_type", "text", True, None),
                    "event_schema_version": CurrentColumn(
                        "common_event_outbox", "event_schema_version", "text", True, None
                    ),
                    "trade_date": CurrentColumn("common_event_outbox", "trade_date", "text", True, None),
                    "asset_kind": CurrentColumn("common_event_outbox", "asset_kind", "text", True, None),
                    "identity_key": CurrentColumn("common_event_outbox", "identity_key", "text", True, None),
                    "event_time": CurrentColumn(
                        "common_event_outbox", "event_time", "timestamp with time zone", True, None
                    ),
                    "source_layer": CurrentColumn("common_event_outbox", "source_layer", "text", True, None),
                    "source_run_id": CurrentColumn("common_event_outbox", "source_run_id", "text", True, None),
                    "dedup_key": CurrentColumn("common_event_outbox", "dedup_key", "text", True, None),
                    "partition_key": CurrentColumn("common_event_outbox", "partition_key", "text", True, None),
                    "payload_json": CurrentColumn("common_event_outbox", "payload_json", "jsonb", True, None),
                    "status": CurrentColumn("common_event_outbox", "status", "text", True, None),
                    "attempt_count": CurrentColumn("common_event_outbox", "attempt_count", "integer", True, None),
                    "created_at": CurrentColumn(
                        "common_event_outbox", "created_at", "timestamp with time zone", True, None
                    ),
                }
            },
            unique_constraints_by_table={},
        )

        report = build_market_data_schema_gap_report_from_metadata(
            target_schema=schema,
            current_metadata=metadata,
        )
        report = report.__class__(
            **{
                **report.__dict__,
                "missing_unique_constraints": (
                    MissingUniqueConstraint(
                        table_name="common_event_outbox",
                        constraint_name="uq_common_event_outbox_event_id",
                        columns=("event_id",),
                        kind="unique_constraint",
                        raw_definition="CONSTRAINT uq_common_event_outbox_event_id UNIQUE(event_id)",
                    ),
                ),
            }
        )

        migration_sql = generate_additive_migration_sql(report)

        self.assertIn("ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ", migration_sql)
        self.assertIn("ADD CONSTRAINT uq_common_event_outbox_event_id UNIQUE (event_id)", migration_sql)
        self.assertNotIn("UserMarketProjectionUpdated", migration_sql)
        self.assertNotIn("_runtime", migration_sql)


if __name__ == "__main__":
    unittest.main()
