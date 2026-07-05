import tempfile
import unittest
from pathlib import Path

from ashare_v3.observability.query_audit import (
    AuditContext,
    ArtifactAuditSink,
    DeniedTableAccessError,
    audited_connect,
    inventory_psycopg_connect_sites,
)


PHASE1_TARGETS = [
    Path("src/ashare_v3/trigger/context_execute.py"),
    Path("src/ashare_v3/trigger/run_once_execute.py"),
    Path("src/ashare_v3/trigger/rule_v4_execute.py"),
    Path("src/ashare_v3/trigger/standard_trigger_execute.py"),
    Path("src/ashare_v3/trigger/action_confirmation_metric_matcher.py"),
    Path("scripts/run_n4_20260605_matched_only_execute_once.py"),
    Path("scripts/run_n4_20260605_v4_corrected_execute_once.py"),
    Path("scripts/plan_n4_20260605_v4_corrected_execute_contract.py"),
    Path("scripts/plan_n4_20260605_v4_corrected_dry_run.py"),
]


class FakeCursor:
    rowcount = 0

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


class StructuredQueryAuditPhase1AdoptionTest(unittest.TestCase):
    def test_phase1_target_files_have_no_direct_psycopg_connect_sites(self) -> None:
        sites = inventory_psycopg_connect_sites(PHASE1_TARGETS)

        self.assertEqual(
            [],
            [f"{site.path}:{site.line_number}" for site in sites],
            "Phase 1 target files must use the structured query audit wrapper instead of direct psycopg.connect",
        )

    def test_audited_connection_blocks_denied_table_before_cursor_execute(self) -> None:
        fake_connection = FakeConnection()
        context = AuditContext(
            layer_role="N4_trigger",
            source_run_id="trigger_execute_phase1_test",
            stage_id="phase1_n4_adoption",
            gate_id="N3_N4_N5_STRUCTURED_QUERY_AUDIT_PHASE1_N4_ADOPTION_IMPLEMENTATION_GATE",
            path_role="n4_intraday_execute",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            sink = ArtifactAuditSink(Path(tmpdir) / "audit.json", audit_run_id="phase1_test")
            conn = audited_connect(lambda **_: fake_connection, context=context, sink=sink)
            with self.assertRaises(DeniedTableAccessError):
                with conn as audited_conn, audited_conn.cursor() as cur:
                    cur.execute("SELECT * FROM stock_condition_display_basis")
            sink.write_report()

        self.assertEqual(fake_connection.cursor_obj.executed, [])


if __name__ == "__main__":
    unittest.main()
