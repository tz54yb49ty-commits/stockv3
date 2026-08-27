from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import unittest

from ashare_v3.ingestion.windows_n1_postgres import (
    N1_WRITABLE_TABLES, REQUIRED_READY_DATA_TYPES, WindowsN1PostgresRepository,
    jsonb_dumps, stable_rows_hash, validate_schema_sql, validate_write_target,
)


class WindowsN1PostgresTest(unittest.TestCase):
    def test_only_n1_tables_are_writable(self):
        self.assertIn("stock_daily_bar_fact", N1_WRITABLE_TABLES)
        for table in ("common_trade_calendar", "stock_condition_basis", "common_trigger_state", "common_action_run", "user_projection_run"):
            with self.assertRaisesRegex(RuntimeError, "rejected"):
                validate_write_target(table)

    def test_ready_set_is_exactly_n1_non_calendar_sources(self):
        self.assertEqual(len(REQUIRED_READY_DATA_TYPES), 10)
        self.assertNotIn("common_trade_calendar", REQUIRED_READY_DATA_TYPES)
        self.assertNotIn(
            "common_trade_calendar must remain empty in Windows N1",
            WindowsN1PostgresRepository.assert_n1_data_ready.__code__.co_consts,
        )

    def test_hash_is_deterministic_and_sensitive(self):
        first = stable_rows_hash([{"code": "1", "value": 2}])
        self.assertEqual(first, stable_rows_hash([{"value": 2, "code": "1"}]))
        self.assertNotEqual(first, stable_rows_hash([{"code": "1", "value": 3}]))

    def test_jsonb_dumps_accepts_eltdx_bytes_and_dates(self):
        raw_bytes = b"\x00\xff"
        self.assertEqual(
            json.loads(jsonb_dumps({"raw": raw_bytes, "asof": date(2026, 8, 27)})),
            {"raw": str(raw_bytes), "asof": "2026-08-27"},
        )

    def test_frozen_schema_has_exact_n1_table_allowlist(self):
        schema = Path("sql/001_raw_ingestion_schema.sql").read_text(encoding="utf-8")
        validate_schema_sql(schema)
        with self.assertRaisesRegex(RuntimeError, "unexpected"):
            validate_schema_sql(schema + "\nCREATE TABLE common_trigger_state (id integer);")

    def test_identical_passed_batch_is_idempotent_but_collision_fails(self):
        class Cursor:
            def __init__(self, row): self.row = row
            def execute(self, sql, params): self.params = params
            def fetchone(self): return self.row
        repository = WindowsN1PostgresRepository(connection=None)
        self.assertTrue(repository._passed_batch_is_identical(
            Cursor(("passed", "abc", 2)), batch_id="batch", raw_hash="abc", row_count=2
        ))
        with self.assertRaisesRegex(RuntimeError, "collision"):
            repository._passed_batch_is_identical(
                Cursor(("passed", "different", 2)), batch_id="batch", raw_hash="abc", row_count=2
            )

    def test_fastlane_completion_marker_is_idempotent_across_run_ids(self):
        class Context:
            def __init__(self, value): self.value = value
            def __enter__(self): return self.value
            def __exit__(self, exc_type, exc, traceback): return False

        class Cursor:
            def __init__(self): self.execute_count = 0
            def execute(self, sql, params): self.execute_count += 1
            def fetchone(self):
                return ("passed", "20260827", "common", "fastlane_complete")

        class Connection:
            def __init__(self): self.cursor_value = Cursor()
            def transaction(self): return Context(None)
            def cursor(self): return Context(self.cursor_value)

        connection = Connection()
        repository = WindowsN1PostgresRepository(connection=connection)
        repository.mark_fastlane_complete(
            trade_date="20260827",
            run_id="second_run",
            row_count=6080,
            details={"stock": 5551, "index": 100, "board": 429},
        )
        self.assertEqual(connection.cursor_value.execute_count, 1)


if __name__ == "__main__": unittest.main()
