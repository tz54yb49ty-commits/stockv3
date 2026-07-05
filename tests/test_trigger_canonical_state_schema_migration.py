import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = PROJECT_ROOT / "sql" / "024_trigger_canonical_state_compatibility_migration.sql"
ROLLBACK_PATH = PROJECT_ROOT / "sql" / "024_trigger_canonical_state_compatibility_rollback.sql"
READINESS_JSON_PATH = PROJECT_ROOT / "docs" / "N4_CANONICAL_TRIGGER_STATE_SCHEMA_COMPATIBILITY_READINESS.json"
READINESS_MD_PATH = PROJECT_ROOT / "docs" / "N4_CANONICAL_TRIGGER_STATE_SCHEMA_COMPATIBILITY_READINESS.md"


class TriggerCanonicalStateSchemaMigrationTest(unittest.TestCase):
    def test_migration_is_schema_only_and_touches_only_trigger_tables(self) -> None:
        sql = strip_sql_comments(MIGRATION_PATH.read_text(encoding="utf-8"))

        self.assertNotRegex(sql, r"\b(INSERT|UPDATE|DELETE|TRUNCATE|COPY)\b")
        self.assertNotIn("common_event_outbox", sql)
        self.assertNotIn("common_event_inbox", sql)
        self.assertNotIn("common_event_consumer_checkpoint", sql)
        self.assertNotIn("TriggerStateChanged", sql)
        self.assertEqual(set(re.findall(r"ALTER\s+TABLE\s+([a-z_]+)", sql, flags=re.IGNORECASE)), {
            "common_trigger_state",
            "common_trigger_match",
        })

    def test_migration_relaxes_hint_signal_checks_and_keeps_legacy_compatible(self) -> None:
        sql = strip_sql_comments(MIGRATION_PATH.read_text(encoding="utf-8"))

        self.assertIn("condition_key <> 'BUY_HINT' OR signal_type IN ('B_BUY', 'BUY_HINT')", sql)
        self.assertIn("condition_key <> 'SELL_HINT' OR signal_type IN ('S_SELL', 'SELL_HINT')", sql)
        self.assertIn("trigger_mark_candidate TEXT", sql)
        self.assertIn("trigger_live BOOLEAN", sql)
        self.assertIn("all_trigger_periods JSONB", sql)
        self.assertIn("projection_30m_type TEXT", sql)
        self.assertIn("CHECK (trigger_mark_candidate IS NULL OR trigger_mark_candidate IN ('normal', '30m_volume', '30m_shrink'))", sql)
        self.assertNotIn("output_event_type IN ('TriggerMatched', 'TriggerPendingMarketData', 'TriggerStateChanged')", sql)

    def test_rollback_blocks_when_canonical_rows_or_additive_values_exist(self) -> None:
        sql = strip_sql_comments(ROLLBACK_PATH.read_text(encoding="utf-8"))

        self.assertNotRegex(sql, r"\b(INSERT|UPDATE|DELETE|TRUNCATE|COPY)\b")
        self.assertIn("condition_key = 'BUY_HINT' AND signal_type = 'B_BUY'", sql)
        self.assertIn("condition_key = 'SELL_HINT' AND signal_type = 'S_SELL'", sql)
        self.assertIn("trigger_mark_candidate IS NOT NULL", sql)
        self.assertIn("trigger_live IS NOT NULL", sql)
        self.assertIn("RAISE EXCEPTION", sql)
        self.assertNotIn("common_event_outbox", sql)
        self.assertNotIn("common_market_data", sql)
        self.assertNotIn("common_action", sql)

    def test_readiness_artifacts_document_scope_and_execute_block(self) -> None:
        report = READINESS_JSON_PATH.read_text(encoding="utf-8")
        markdown = READINESS_MD_PATH.read_text(encoding="utf-8")

        self.assertIn('"result": "DRAFT_PASS"', report)
        self.assertIn('"strictly_compatible": true', report)
        self.assertIn('"common_event_outbox_migration_required": false', report)
        self.assertIn('"common_trigger_match_supports_trigger_state_changed": false', report)
        self.assertIn('"n4_business_execute_still_blocked": true', report)
        self.assertIn("common_trigger_state", markdown)
        self.assertIn("common_trigger_match", markdown)
        self.assertIn("TriggerStateChanged", markdown)


def strip_sql_comments(sql: str) -> str:
    lines = []
    for line in sql.splitlines():
        stripped = line.split("--", 1)[0]
        if stripped.strip():
            lines.append(stripped)
    return "\n".join(lines)


if __name__ == "__main__":
    unittest.main()
