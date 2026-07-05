import tempfile
import unittest
from pathlib import Path

from ashare_v3.observability.query_audit import (
    DENIED_DIRECT_READ_TABLES,
    VALID_CONNECTION_SITE_CLASSIFICATIONS,
    ArtifactAuditSink,
    DeniedTableAccessError,
    inventory_psycopg_connect_sites,
)
from ashare_v3.action.query_audit_phase2 import (
    audited_n5_action_connect,
    audited_n5_metadata_repair_connect,
)


PHASE2_SELECTED_TARGETS = [
    Path("src/ashare_v3/action/execute.py"),
    Path("src/ashare_v3/action/metadata_repair.py"),
    Path("src/ashare_v3/action/execute_preflight.py"),
    Path("src/ashare_v3/action/preflight.py"),
    Path("src/ashare_v3/action/consumer_dry_run.py"),
    Path("src/ashare_v3/action/run_once_dry_run.py"),
]


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


def fake_connect(**_: object) -> FakeConnection:
    return FakeConnection()


class StructuredQueryAuditPhase2AdoptionTest(unittest.TestCase):
    def test_phase2_selected_n5_files_have_no_direct_psycopg_connect_sites(self) -> None:
        sites = inventory_psycopg_connect_sites(PHASE2_SELECTED_TARGETS)

        self.assertEqual(
            [],
            [f"{site.path}:{site.line_number}" for site in sites],
            "Phase 2 selected N5 files must use the structured query audit wrapper instead of direct psycopg.connect",
        )

    def test_phase2_classification_taxonomy_is_supported(self) -> None:
        self.assertIn("explicit_bypass_metadata_repair", VALID_CONNECTION_SITE_CLASSIFICATIONS)
        self.assertIn("out_of_scope_migration_or_schema_review", VALID_CONNECTION_SITE_CLASSIFICATIONS)

    def test_n5_action_denied_table_blocks_before_cursor_execute(self) -> None:
        self.assertIn("stock_condition_display_basis", DENIED_DIRECT_READ_TABLES)
        fake_connection = FakeConnection()

        with tempfile.TemporaryDirectory() as tmpdir:
            sink = ArtifactAuditSink(Path(tmpdir) / "audit.json", audit_run_id="phase2_action")
            conn = audited_n5_action_connect(
                "dsn",
                stage_id="phase2_n5_action_test",
                source_run_id="action_run",
                sink=sink,
                connect=fake_connect_returning(fake_connection),
            )
            with self.assertRaises(DeniedTableAccessError):
                with conn as audited_conn, audited_conn.cursor() as cur:
                    cur.execute("SELECT * FROM stock_condition_display_basis")

        self.assertEqual(fake_connection.cursor_obj.executed, [])

    def test_n5_metadata_repair_records_write_attempt_as_metadata_bypass(self) -> None:
        fake_connection = FakeConnection()

        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "audit.json"
            sink = ArtifactAuditSink(report_path, audit_run_id="phase2_metadata")
            conn = audited_n5_metadata_repair_connect(
                "dsn",
                stage_id="phase2_n5_metadata_test",
                source_run_id="action_run",
                sink=sink,
                connect=fake_connect_returning(fake_connection),
            )
            with conn as audited_conn, audited_conn.cursor() as cur:
                cur.execute("UPDATE common_action_event SET payload_json = payload_json WHERE run_id = %s", ("run",))
            sink.write_report()
            report = __import__("json").loads(report_path.read_text())

        self.assertEqual(fake_connection.cursor_obj.executed[0][0].split()[0], "UPDATE")
        self.assertTrue(report["entries"][0]["db_write_attempted"])
        self.assertEqual(report["entries"][0]["bypass_classification"], "explicit_bypass_metadata_repair")


def fake_connect_returning(connection: FakeConnection):
    def _connect(*_: object, **__: object) -> FakeConnection:
        return connection

    return _connect


if __name__ == "__main__":
    unittest.main()
