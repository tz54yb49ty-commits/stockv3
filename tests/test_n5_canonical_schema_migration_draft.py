import json
import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = PROJECT_ROOT / "sql" / "025_n5_canonical_action_schema_alignment.sql"
ROLLBACK_PATH = PROJECT_ROOT / "sql" / "025_n5_canonical_action_schema_alignment_rollback.sql"
READINESS_JSON_PATH = PROJECT_ROOT / "docs" / "N5_canonical_action_schema_migration_draft_readiness.json"
READINESS_MD_PATH = PROJECT_ROOT / "docs" / "N5_CANONICAL_ACTION_SCHEMA_MIGRATION_DRAFT_READINESS.md"

ACTION_FACT_TABLES = ("stock_action_fact", "index_action_fact", "board_action_fact")
CANONICAL_COLUMNS = (
    "source_trigger_state_id",
    "original_condition_key",
    "trigger_mark_candidate",
    "action_mark",
    "action_state",
    "confirmation_status",
    "tracking_until",
    "last_checked_minute_label",
    "trace_json",
)
CANONICAL_EVENT_TYPES = ("ActionEligible", "ActionBlocked", "ActionExecuted", "ActionSkipped")
LEGACY_EVENT_TYPES = ("ActionEvent", "HintEvent", "RiskEvent", "PositionEvent")


class N5CanonicalSchemaMigrationDraftTest(unittest.TestCase):
    def test_migration_is_schema_only_and_touches_only_n5_action_tables(self) -> None:
        sql = strip_sql_comments(MIGRATION_PATH.read_text(encoding="utf-8"))

        self.assertNotRegex(sql, r"\b(INSERT|UPDATE|DELETE|TRUNCATE|COPY)\b")
        self.assertNotIn("common_event_outbox", sql)
        self.assertNotIn("common_event_inbox", sql)
        self.assertNotIn("common_event_consumer_checkpoint", sql)
        self.assertEqual(
            set(re.findall(r"ALTER\s+TABLE\s+([a-z_]+)", sql, flags=re.IGNORECASE)),
            {"stock_action_fact", "index_action_fact", "board_action_fact", "common_action_event"},
        )

    def test_action_fact_tables_gain_canonical_columns_and_compatible_checks(self) -> None:
        sql = strip_sql_comments(MIGRATION_PATH.read_text(encoding="utf-8"))

        for table in ACTION_FACT_TABLES:
            block = extract_alter_block(sql, table)
            for column in CANONICAL_COLUMNS:
                self.assertIn(f"ADD COLUMN IF NOT EXISTS {column}", block)
            self.assertIn("TriggerMatched", sql)
            self.assertIn("TriggerPendingMarketData", sql)
            self.assertIn("TriggerStateChanged", sql)
            self.assertIn("TriggerCleared", sql)
            self.assertIn("B_BUY_30M_VOL", sql)
            self.assertIn("S_SELL_30M_SHRINK", sql)
            self.assertIn("BUY_HINT", sql)
            self.assertIn("SELL_HINT", sql)
            self.assertIn("CHECK (action_state IS NULL OR action_state IN ('eligible', 'blocked', 'executed', 'skipped', 'expired'))", sql)
            self.assertIn("CHECK (action_mark IS NULL OR action_mark IN ('normal', '30m_volume', '30m_shrink'))", sql)
            self.assertIn("CHECK (trigger_mark_candidate IS NULL OR trigger_mark_candidate IN ('normal', '30m_volume', '30m_shrink'))", sql)

    def test_common_action_event_accepts_legacy_and_canonical_event_types(self) -> None:
        sql = strip_sql_comments(MIGRATION_PATH.read_text(encoding="utf-8"))
        block = extract_alter_block(sql, "common_action_event")

        for column in CANONICAL_COLUMNS:
            self.assertIn(f"ADD COLUMN IF NOT EXISTS {column}", block)
        for event_type in LEGACY_EVENT_TYPES + CANONICAL_EVENT_TYPES:
            self.assertIn(event_type, sql)
        self.assertIn("chk_common_action_event_event_type_n5_canonical_compat", sql)

    def test_rollback_blocks_when_canonical_rows_or_additive_values_exist(self) -> None:
        sql = strip_sql_comments(ROLLBACK_PATH.read_text(encoding="utf-8"))

        self.assertNotRegex(sql, r"\b(INSERT|UPDATE|DELETE|TRUNCATE|COPY)\b")
        self.assertIn("event_type IN ('ActionEligible', 'ActionBlocked', 'ActionExecuted', 'ActionSkipped')", sql)
        self.assertIn("RAISE EXCEPTION", sql)
        for table in ACTION_FACT_TABLES + ("common_action_event",):
            self.assertIn(f"FROM {table}", sql)
        for column in CANONICAL_COLUMNS:
            self.assertIn(f"{column} IS NOT NULL", sql)
        self.assertNotIn("common_event_outbox", sql)
        self.assertNotIn("common_event_inbox", sql)
        self.assertNotIn("common_event_consumer_checkpoint", sql)
        self.assertNotIn("common_trigger_", sql)
        self.assertNotIn("minute_bar", sql)

    def test_readiness_artifacts_document_scope_and_remaining_execute_gate(self) -> None:
        report = json.loads(READINESS_JSON_PATH.read_text(encoding="utf-8"))
        markdown = READINESS_MD_PATH.read_text(encoding="utf-8")

        self.assertEqual(report["result"], "DRAFT_PASS")
        self.assertTrue(report["strictly_compatible"])
        self.assertFalse(report["common_event_outbox_migration_required"])
        self.assertTrue(report["legacy_compatibility"])
        self.assertTrue(report["canonical_runner_gate_required"])
        self.assertTrue(report["n5_business_execute_still_blocked"])
        self.assertEqual(set(report["touched_tables"]), set(ACTION_FACT_TABLES + ("common_action_event",)))
        self.assertIn("ActionBlocked", markdown)
        self.assertIn("TriggerStateChanged", markdown)
        self.assertIn("deprecated runtime signal_type", markdown)
        self.assertIn("final gate", markdown)


def strip_sql_comments(sql: str) -> str:
    lines = []
    for line in sql.splitlines():
        stripped = line.split("--", 1)[0]
        if stripped.strip():
            lines.append(stripped)
    return "\n".join(lines)


def extract_alter_block(sql: str, table_name: str) -> str:
    match = re.search(
        rf"ALTER\s+TABLE\s+{table_name}\b(?P<body>.*?);",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing ALTER TABLE block for {table_name}")
    return match.group("body")


if __name__ == "__main__":
    unittest.main()
