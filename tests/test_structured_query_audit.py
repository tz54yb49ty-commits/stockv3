import json
import tempfile
import unittest
from pathlib import Path

from ashare_v3.observability.query_audit import (
    APPROVED_ONE_TIME_CONTEXT_REFRESH_TABLES,
    AuditContext,
    ArtifactAuditSink,
    DeniedTableAccessError,
    assert_no_denied_tables,
    audit_execute,
    build_application_name,
    classify_statement_kind,
    extract_referenced_tables,
    fingerprint_sql,
    make_artifact_audit_sink,
)


class FakeCursor:
    def __init__(self, rowcount: int = 7) -> None:
        self.executed: list[tuple[str, object | None]] = []
        self.rowcount = rowcount

    def execute(self, sql_text: str, params: object | None = None) -> None:
        self.executed.append((sql_text, params))


class StructuredQueryAuditTest(unittest.TestCase):
    def test_extract_referenced_tables_handles_ctes_and_basic_statement_kinds(self) -> None:
        sql_text = """
        WITH recent AS (
            SELECT * FROM common_trigger_match
        )
        SELECT *
          FROM recent r
          JOIN public.common_action_event cae ON cae.source_trigger_event_id = r.event_id
          JOIN "stock_trigger_context_snapshot" s ON s.identity_key = cae.identity_key
         WHERE EXISTS (
            SELECT 1 FROM index_membership_fact im WHERE im.stock_identity_key = cae.identity_key
         )
        """

        tables = extract_referenced_tables(sql_text)

        self.assertIn("common_trigger_match", tables)
        self.assertIn("common_action_event", tables)
        self.assertIn("stock_trigger_context_snapshot", tables)
        self.assertIn("index_membership_fact", tables)
        self.assertNotIn("recent", tables)

    def test_statement_kind_and_fingerprint_are_stable_without_logging_literals(self) -> None:
        first = "select * from common_action_event where event_id = 'secret-id'"
        second = " SELECT  *  FROM common_action_event WHERE event_id = 'another-secret' "

        self.assertEqual(classify_statement_kind(first), "SELECT")
        self.assertEqual(fingerprint_sql(first), fingerprint_sql(second))

    def test_application_name_contains_required_context_and_is_bounded(self) -> None:
        context = AuditContext(
            layer_role="N4_trigger",
            source_run_id="trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
            stage_id="n4_intraday_matcher",
            gate_id="N3_N4_N5_STRUCTURED_QUERY_AUDIT_IMPLEMENTATION_GATE",
            path_role="n4_intraday_execute",
        )

        application_name = build_application_name(context)

        self.assertLessEqual(len(application_name), 63)
        self.assertIn("ashare_v3", application_name)
        self.assertIn("N4_trigger", application_name)
        self.assertIn("n4_intraday_matcher", application_name)
        self.assertNotIn(" ", application_name)

    def test_denied_table_blocks_intraday_path_before_db_execution(self) -> None:
        context = AuditContext(
            layer_role="N4_trigger",
            source_run_id="trigger_run",
            stage_id="n4_match",
            gate_id="gate",
            path_role="n4_intraday_execute",
        )
        cursor = FakeCursor()

        with tempfile.TemporaryDirectory() as tmpdir:
            sink = ArtifactAuditSink(Path(tmpdir) / "audit.json", audit_run_id="audit_test")
            with self.assertRaises(DeniedTableAccessError):
                audit_execute(
                    cursor,
                    "SELECT * FROM stock_condition_display_basis WHERE run_id = %s",
                    ("condition_run",),
                    context,
                    sink,
                )
            sink.write_report()
            report = json.loads((Path(tmpdir) / "audit.json").read_text())

        self.assertEqual(cursor.executed, [])
        self.assertEqual(report["summary"]["blocked_entries"], 1)
        self.assertTrue(report["entries"][0]["denied_table_hit"])
        self.assertNotIn("condition_run", json.dumps(report))

    def test_one_time_context_refresh_allows_only_approved_sources(self) -> None:
        context = AuditContext(
            layer_role="N4_trigger",
            source_run_id="trigger_context_refresh",
            stage_id="n4_context_refresh",
            gate_id="gate",
            path_role="n4_one_time_context_refresh",
        )

        self.assertIn("stock_condition_basis", APPROVED_ONE_TIME_CONTEXT_REFRESH_TABLES)
        assert_no_denied_tables(context, "SELECT * FROM stock_condition_basis")

        with self.assertRaises(DeniedTableAccessError):
            assert_no_denied_tables(context, "SELECT * FROM stock_condition_display_basis")

    def test_artifact_sink_records_required_fields_and_no_side_effect_defaults(self) -> None:
        context = AuditContext(
            layer_role="N5_action",
            source_run_id="action_run",
            stage_id="n5_readiness",
            gate_id="gate",
            path_role="n5_intraday_execute",
        )
        cursor = FakeCursor(rowcount=3)

        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "audit.json"
            sink = ArtifactAuditSink(report_path, audit_run_id="audit_run")
            entry = audit_execute(
                cursor,
                "SELECT event_id FROM common_action_event WHERE action_run_id = %s",
                ("action_run",),
                context,
                sink,
            )
            sink.write_report()
            report = json.loads(report_path.read_text())

        self.assertEqual(entry.rowcount, 3)
        self.assertFalse(entry.worker_started)
        self.assertFalse(entry.outbox_consumed)
        self.assertFalse(entry.checkpoint_updated)
        self.assertFalse(entry.db_write_attempted)
        self.assertEqual(report["summary"]["total_entries"], 1)
        self.assertEqual(report["summary"]["db_write_attempted_entries"], 0)
        self.assertNotIn("raw_sql", report["entries"][0])
        self.assertIn("statement_fingerprint", report["entries"][0])

    def test_make_artifact_sink_bounds_filename_and_preserves_full_audit_run_id(self) -> None:
        context = AuditContext(
            layer_role="N4_trigger",
            source_run_id=(
                "realtime_projection_metric_20260605_live2_compat__"
                "realtime_snapshot_20260605_live2_market_data_subscription_20260605_"
                "condition_layer_20260604_source_20260604_v1"
            ),
            stage_id="n4_projection_matcher_fetch_projection",
            gate_id="N3_N4_N5_STRUCTURED_QUERY_AUDIT_PHASE1_N4_ADOPTION_IMPLEMENTATION_GATE",
            path_role="n4_readonly_plan",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            sink = make_artifact_audit_sink(context, artifact_dir=tmpdir)
            sink.write_report()
            report = json.loads(sink.artifact_path.read_text())

        self.assertLessEqual(len(sink.artifact_path.name.encode("utf-8")), 180)
        self.assertEqual(report["audit_run_id"], sink.audit_run_id)
        self.assertIn(context.source_run_id, report["audit_run_id"])

    def test_write_statement_is_flagged_without_mutating_real_database(self) -> None:
        context = AuditContext(
            layer_role="N5_action",
            source_run_id="action_run",
            stage_id="metadata_repair_probe",
            gate_id="gate",
            path_role="explicit_bypass_readonly_plan",
        )
        cursor = FakeCursor(rowcount=1)

        with tempfile.TemporaryDirectory() as tmpdir:
            sink = ArtifactAuditSink(Path(tmpdir) / "audit.json", audit_run_id="audit_write_probe")
            entry = audit_execute(
                cursor,
                "UPDATE common_action_event SET payload_json = payload_json WHERE action_run_id = %s",
                ("action_run",),
                context,
                sink,
            )

        self.assertEqual(len(cursor.executed), 1)
        self.assertEqual(entry.statement_kind, "UPDATE")
        self.assertTrue(entry.db_write_attempted)


if __name__ == "__main__":
    unittest.main()
