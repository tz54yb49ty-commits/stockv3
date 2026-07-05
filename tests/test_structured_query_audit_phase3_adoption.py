import tempfile
import unittest
from pathlib import Path

from ashare_v3.observability.query_audit import (
    ArtifactAuditSink,
    DeniedTableAccessError,
    inventory_psycopg_connect_sites,
)
from ashare_v3.market.query_audit_phase3 import (
    audited_n3_market_execute_connect,
    audited_n3_market_readonly_plan_connect,
    audited_n3_market_schema_review_connect,
)


PHASE3_MARKET_TARGET = [Path("src/ashare_v3/market")]


class FakeCursor:
    rowcount = 1

    def __init__(self) -> None:
        self.executed: list[tuple[str, object | None]] = []

    def execute(self, sql_text: str, params: object | None = None) -> None:
        self.executed.append((sql_text, params))

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class FakeConnection:
    def __init__(self) -> None:
        self.cursor_obj = FakeCursor()

    def cursor(self) -> FakeCursor:
        return self.cursor_obj

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def fake_connect_returning(connection: FakeConnection):
    def _connect(*_: object, **__: object) -> FakeConnection:
        return connection

    return _connect


class StructuredQueryAuditPhase3AdoptionTest(unittest.TestCase):
    def test_phase3_market_files_have_no_direct_psycopg_connect_sites(self) -> None:
        sites = inventory_psycopg_connect_sites(PHASE3_MARKET_TARGET)

        self.assertEqual(
            [],
            [f"{site.path}:{site.line_number}" for site in sites],
            "Phase 3 N3 market files must use the structured query audit wrapper instead of direct psycopg.connect",
        )

    def test_n3_market_execute_blocks_denied_table_before_cursor_execute(self) -> None:
        fake_connection = FakeConnection()

        with tempfile.TemporaryDirectory() as tmpdir:
            sink = ArtifactAuditSink(Path(tmpdir) / "audit.json", audit_run_id="phase3_market_execute")
            conn = audited_n3_market_execute_connect(
                "dsn",
                stage_id="phase3_n3_execute_test",
                source_run_id="market_run",
                sink=sink,
                connect=fake_connect_returning(fake_connection),
            )
            with self.assertRaises(DeniedTableAccessError):
                with conn as audited_conn, audited_conn.cursor() as cur:
                    cur.execute("SELECT * FROM stock_condition_display_basis")

        self.assertEqual(fake_connection.cursor_obj.executed, [])

    def test_n3_readonly_and_schema_helpers_record_bypass_classification(self) -> None:
        for helper, expected_classification in (
            (audited_n3_market_readonly_plan_connect, "explicit_bypass_readonly_plan"),
            (audited_n3_market_schema_review_connect, "out_of_scope_migration_or_schema_review"),
        ):
            fake_connection = FakeConnection()
            with tempfile.TemporaryDirectory() as tmpdir:
                report_path = Path(tmpdir) / "audit.json"
                sink = ArtifactAuditSink(report_path, audit_run_id="phase3_bypass")
                conn = helper(
                    "dsn",
                    stage_id="phase3_n3_bypass_test",
                    source_run_id="market_run",
                    sink=sink,
                    connect=fake_connect_returning(fake_connection),
                )
                with conn as audited_conn, audited_conn.cursor() as cur:
                    cur.execute("SELECT * FROM common_market_data_run WHERE run_id = %s", ("run",))
                sink.write_report()
                report = __import__("json").loads(report_path.read_text())

            self.assertEqual(report["entries"][0]["bypass_classification"], expected_classification)


if __name__ == "__main__":
    unittest.main()
