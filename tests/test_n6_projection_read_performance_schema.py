from __future__ import annotations

import inspect
from pathlib import Path
import unittest

from scripts.backfill_n6_projection_read_model_once import BackfillConfig, status_blockers
from ashare_v3.web.n6_user_app import PostgresN6UserRepository


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/073_n6_projection_read_performance.sql"
ROLLBACK = ROOT / "sql/073_n6_projection_read_performance_rollback.sql"


class N6ProjectionReadPerformanceSchemaTest(unittest.TestCase):
    def test_073_is_additive_backfillable_and_concurrent_index_safe(self) -> None:
        sql = MIGRATION.read_text(encoding="utf-8")

        for column in ("for_trade_date DATE", "list_payload_version TEXT", "list_payload_json JSONB"):
            self.assertIn(f"ADD COLUMN IF NOT EXISTS {column}", sql)
        self.assertIn("n6_projection_read_model_v1_fill", sql)
        self.assertIn("BEFORE INSERT OR UPDATE OF", sql)
        self.assertEqual(sql.count("NOT VALID"), 3)
        self.assertIn("n6_ai_shared_signal_projection", sql)
        self.assertIn("CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_073_n6_projection_shared_date_order", sql)
        self.assertIn("CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_073_n6_projection_user_date_order", sql)
        self.assertEqual(sql.count("WHERE projection_status IN ('visible', 'blocked')"), 2)
        self.assertLess(
            sql.index("COMMIT;"),
            sql.index("CREATE INDEX CONCURRENTLY IF NOT EXISTS"),
        )
        self.assertIn("\\if :{?n6_projection_read_create_indexes}", sql)
        self.assertIn("\\if :{?n6_projection_read_finalize}", sql)
        self.assertNotIn("pg_catalog.coalesce", sql)
        self.assertNotIn("pg_catalog.nullif", sql)
        for column in ("for_trade_date", "list_payload_version", "list_payload_json"):
            self.assertIn(f"ALTER COLUMN {column} SET NOT NULL", sql)

    def test_073_rollback_removes_only_read_model_objects(self) -> None:
        sql = ROLLBACK.read_text(encoding="utf-8")

        self.assertEqual(sql.count("DROP INDEX CONCURRENTLY IF EXISTS"), 2)
        self.assertLess(sql.rindex("DROP INDEX CONCURRENTLY IF EXISTS"), sql.index("BEGIN;"))
        self.assertIn("DROP TRIGGER IF EXISTS trg_073_n6_projection_read_model_v1_fill", sql)
        self.assertIn("DROP FUNCTION IF EXISTS public.n6_projection_read_model_v1_fill()", sql)
        for column in ("for_trade_date", "list_payload_version", "list_payload_json"):
            self.assertIn(f"DROP COLUMN IF EXISTS {column}", sql)
        for forbidden in ("DELETE FROM", "TRUNCATE", "DROP TABLE"):
            self.assertNotIn(forbidden, sql.upper())

    def test_backfill_is_bounded_and_blocks_broken_shared_lineage(self) -> None:
        for batch_size in (250, 500):
            BackfillConfig("postgresql://unused", batch_size=batch_size).validate()
        for batch_size in (249, 501):
            with self.assertRaises(ValueError):
                BackfillConfig("postgresql://unused", batch_size=batch_size).validate()

        blockers = status_blockers(
            {
                "missing_shared_projection_count": 1,
                "trade_date_mismatch_count": 2,
                "projection_run_mismatch_count": 3,
                "invalid_run_date_count": 4,
                "incomplete_count": 5,
            },
            require_complete=True,
        )
        self.assertEqual(
            blockers,
            [
                "missing_shared_projection_count:1",
                "trade_date_mismatch_count:2",
                "projection_run_mismatch_count:3",
                "invalid_run_date_count:4",
                "incomplete_count:5",
            ],
        )

    def test_list_and_sse_are_slim_while_detail_loads_large_json(self) -> None:
        list_source = inspect.getsource(PostgresN6UserRepository._app_v1_signal_select_list)
        sse_source = inspect.getsource(PostgresN6UserRepository._app_v1_signal_sse_select_list)
        detail_source = inspect.getsource(PostgresN6UserRepository._app_v1_signal_detail_select_list)

        for source in (list_source, sse_source):
            for large_column in (
                "p.source_payload_json",
                "p.display_payload_json",
                "p.trace_json",
                "c.card_payload_json",
            ):
                self.assertNotIn(large_column, source)
            self.assertIn("p.list_payload_json", source)
        for large_column in (
            "p.source_payload_json",
            "p.display_payload_json",
            "p.trace_json",
            "c.card_payload_json",
        ):
            self.assertIn(large_column, detail_source)
        for frozen_field in (
            "condition_projection_context",
            "condition_projection_context_status",
            "condition_projection_context_trace",
            "projection_message_contract_version",
            "projection_message_contract_hash",
            "projection_message_status",
            "projection_message_not_ready_reasons",
            "trigger_pct_status",
            "action_pct_status",
            "all_trigger_periods",
            "industry_status",
            "industry_provenance",
        ):
            self.assertIn(frozen_field, list_source)

    def test_hot_queries_use_typed_date_and_one_deduplicated_monitor_join(self) -> None:
        trade_date_source = inspect.getsource(PostgresN6UserRepository._app_v1_trade_date_expr)
        list_source = inspect.getsource(PostgresN6UserRepository._app_v1_signal_select_list)
        metadata_source = inspect.getsource(PostgresN6UserRepository.fetch_app_signal_scope_metadata)
        where_source = inspect.getsource(PostgresN6UserRepository._app_v1_signal_where)

        self.assertIn("p.for_trade_date", trade_date_source)
        self.assertNotIn("payload_json", trade_date_source)
        self.assertIn("monitor_scope.source_type_raw", list_source)
        self.assertNotIn("_app_v1_effective_monitor_scope_lookup", list_source)
        shared_monitor_join_source = inspect.getsource(
            PostgresN6UserRepository._app_v1_effective_monitor_scope_join
        )
        web_monitor_join_source = inspect.getsource(
            PostgresN6UserRepository._app_v1_web_signal_scope_join
        )
        web_monitor_cte_source = inspect.getsource(
            PostgresN6UserRepository._app_v1_web_signal_scope_cte
        )
        self.assertIn("JOIN LATERAL", shared_monitor_join_source)
        self.assertNotIn("LATERAL", web_monitor_join_source)
        self.assertIn("JOIN deduplicated_monitor_scope monitor_scope", web_monitor_join_source)
        self.assertIn("deduplicated_monitor_scope AS MATERIALIZED", web_monitor_cte_source)
        self.assertIn(
            "asset_kind,\n                   identity_key,\n                   direction,\n                   valid_for_trade_date",
            web_monitor_cte_source,
        )
        self.assertIn("monitor_id DESC", web_monitor_cte_source)
        self.assertNotIn("AS MATERIALIZED", metadata_source)
        self.assertNotIn("JOIN user_signal_card", metadata_source)
        self.assertIn("p.for_trade_date", metadata_source)
        self.assertIn("p.for_trade_date =", where_source)
        self.assertNotIn("self._app_v1_trade_date_expr()", where_source)
        self.assertIn(
            "(p.created_at, p.user_signal_projection_id)",
            where_source,
        )
        self.assertIn("< (%(before_created_at)s, %(before_id)s)", where_source)


if __name__ == "__main__":
    unittest.main()
