import json
import tempfile
import unittest
from pathlib import Path

from ashare_v3.observability.query_audit import ArtifactAuditSink, inventory_psycopg_connect_sites


REMAINING_SELECTED_TARGETS = [
    Path("src/ashare_v3/trigger/action_confirmation_metric_execute.py"),
    Path("src/ashare_v3/trigger/c3_replay_audit_execute.py"),
    Path("src/ashare_v3/trigger/c3_replay_plan.py"),
    Path("src/ashare_v3/trigger/context_preflight.py"),
    Path("src/ashare_v3/trigger/local_trigger_dry_run.py"),
    Path("src/ashare_v3/trigger/migration_execute.py"),
    Path("src/ashare_v3/trigger/projection_matcher.py"),
    Path("src/ashare_v3/trigger/projection_matcher_execute.py"),
    Path("src/ashare_v3/trigger/synthetic_dry_run.py"),
    Path("src/ashare_v3/action/schema_migration_execute.py"),
    Path("scripts/plan_n4_trigger_rule_v4_full_lineage_dry_run.py"),
    Path("scripts/probe_board_market_data_adapter.py"),
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


def fake_connect_returning(connection: FakeConnection):
    def _connect(*_: object, **__: object) -> FakeConnection:
        return connection

    return _connect


class StructuredQueryAuditRemainingAdoptionTest(unittest.TestCase):
    def test_remaining_selected_files_have_no_direct_psycopg_connect_sites(self) -> None:
        sites = inventory_psycopg_connect_sites(REMAINING_SELECTED_TARGETS)

        self.assertEqual(
            [],
            [f"{site.path}:{site.line_number}" for site in sites],
            "Remaining selected trigger/action/script files must use audited helpers instead of direct psycopg.connect",
        )

    def test_schema_review_helpers_record_bypass_classification(self) -> None:
        from ashare_v3.action.query_audit_phase2 import audited_n5_schema_review_connect
        from ashare_v3.trigger.query_audit_phase1 import audited_n4_schema_review_connect

        cases = [
            (
                audited_n4_schema_review_connect,
                "remaining_n4_schema_review",
                "SELECT * FROM common_trigger_run WHERE run_id = %s",
            ),
            (
                audited_n5_schema_review_connect,
                "remaining_n5_schema_review",
                "SELECT * FROM common_action_run WHERE run_id = %s",
            ),
        ]
        for helper, stage_id, sql_text in cases:
            fake_connection = FakeConnection()
            with tempfile.TemporaryDirectory() as tmpdir:
                report_path = Path(tmpdir) / "audit.json"
                sink = ArtifactAuditSink(report_path, audit_run_id=stage_id)
                conn = helper(
                    "dsn",
                    stage_id=stage_id,
                    source_run_id="remaining_adoption_test",
                    sink=sink,
                    connect=fake_connect_returning(fake_connection),
                )
                with conn as audited_conn, audited_conn.cursor() as cur:
                    cur.execute(sql_text, ("run",))
                sink.write_report()
                report = json.loads(report_path.read_text())

            self.assertEqual(report["entries"][0]["bypass_classification"], "out_of_scope_migration_or_schema_review")


if __name__ == "__main__":
    unittest.main()
