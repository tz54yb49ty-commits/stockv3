import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = PROJECT_ROOT / "sql" / "026_n6_canonical_user_projection_schema_alignment.sql"
ROLLBACK_PATH = PROJECT_ROOT / "sql" / "026_n6_canonical_user_projection_schema_alignment_rollback.sql"
CONTRACT_MD_PATH = PROJECT_ROOT / "docs" / "N6_CANONICAL_SCHEMA_ALIGNMENT_CONTRACT.md"
READINESS_MD_PATH = PROJECT_ROOT / "docs" / "N6_CANONICAL_SCHEMA_MIGRATION_DRAFT_READINESS.md"

TOUCHED_TABLES = (
    "user_projection_run",
    "user_signal_projection",
    "user_signal_card",
    "user_notification_queue",
)
UNTOUCHED_N6_TABLES = (
    "user_account",
    "user_session",
    "user_filter_profile",
    "user_watchlist",
    "user_watchlist_item",
    "user_signal_decision",
    "user_sim_account",
    "user_sim_order",
    "user_sim_trade",
    "user_sim_position",
)
CANONICAL_EVENT_TYPES = ("ActionEligible", "ActionBlocked", "ActionExecuted", "ActionSkipped")
LEGACY_EVENT_TYPES = ("ActionEvent", "HintEvent")
TRACE_COLUMNS = (
    "source_action_event_type",
    "action_state",
    "action_mark",
    "condition_key",
    "original_condition_key",
    "trace_json",
    "projection_policy",
)


class N6CanonicalSchemaMigrationDraftTest(unittest.TestCase):
    def test_migration_is_schema_only_and_touches_only_projection_tables(self) -> None:
        sql = strip_sql_comments(MIGRATION_PATH.read_text(encoding="utf-8"))

        self.assertNotRegex(sql, r"\b(INSERT|UPDATE|DELETE|TRUNCATE|COPY)\b")
        self.assertNotIn("common_event_outbox", sql)
        self.assertNotIn("common_event_inbox", sql)
        self.assertNotIn("common_event_consumer_checkpoint", sql)
        self.assertEqual(
            set(re.findall(r"ALTER\s+TABLE\s+([a-z_]+)", sql, flags=re.IGNORECASE)),
            set(TOUCHED_TABLES),
        )
        for table in UNTOUCHED_N6_TABLES:
            self.assertNotIn(f"ALTER TABLE {table}", sql)

    def test_constraints_accept_legacy_and_canonical_event_types(self) -> None:
        sql = strip_sql_comments(MIGRATION_PATH.read_text(encoding="utf-8"))

        for event_type in LEGACY_EVENT_TYPES + CANONICAL_EVENT_TYPES:
            self.assertIn(event_type, sql)
        self.assertIn("chk_user_projection_run_source_event_types_n6_canonical_compat", sql)
        self.assertIn("chk_user_signal_projection_source_event_type_n6_canonical_compat", sql)
        self.assertIn("chk_user_signal_projection_source_action_event_type_n6_canonical_compat", sql)

    def test_projection_card_and_queue_gain_canonical_trace_columns(self) -> None:
        sql = strip_sql_comments(MIGRATION_PATH.read_text(encoding="utf-8"))

        projection_block = extract_alter_block(sql, "user_signal_projection")
        for column in TRACE_COLUMNS:
            self.assertIn(f"ADD COLUMN IF NOT EXISTS {column}", projection_block)

        card_block = extract_alter_block(sql, "user_signal_card")
        queue_block = extract_alter_block(sql, "user_notification_queue")
        for block in (card_block, queue_block):
            self.assertIn("ADD COLUMN IF NOT EXISTS source_action_event_id", block)
            for column in TRACE_COLUMNS:
                self.assertIn(f"ADD COLUMN IF NOT EXISTS {column}", block)

    def test_notification_source_and_card_state_support_canonical_policy(self) -> None:
        sql = strip_sql_comments(MIGRATION_PATH.read_text(encoding="utf-8"))

        for value in (
            "n5_action_event",
            "n5_hint_event",
            "n5_action_eligible",
            "n5_action_blocked",
            "n5_action_executed",
            "n5_action_skipped",
        ):
            self.assertIn(value, sql)
        for value in ("blocked", "action_confirmed", "skipped", "informational"):
            self.assertIn(value, sql)
        self.assertIn("idx_user_signal_projection_canonical_action", sql)
        self.assertIn("idx_user_signal_card_canonical_action", sql)
        self.assertIn("idx_user_notification_queue_canonical_action", sql)

    def test_rollback_is_guarded_and_does_not_touch_upstream_or_business_delete(self) -> None:
        sql = strip_sql_comments(ROLLBACK_PATH.read_text(encoding="utf-8"))

        self.assertNotRegex(sql, r"\b(INSERT|UPDATE|DELETE|TRUNCATE|COPY)\b")
        self.assertIn("RAISE EXCEPTION", sql)
        self.assertIn("source_event_types && ARRAY['ActionEligible', 'ActionBlocked', 'ActionExecuted', 'ActionSkipped']", sql)
        self.assertIn("source_action_event_type IS NOT NULL", sql)
        self.assertIn("notification_source IN ('n5_action_eligible', 'n5_action_blocked', 'n5_action_executed', 'n5_action_skipped')", sql)
        self.assertNotIn("common_event_outbox", sql)
        self.assertNotIn("common_event_inbox", sql)
        self.assertNotIn("common_event_consumer_checkpoint", sql)
        self.assertNotIn("common_action_event", sql)
        self.assertNotIn("common_trigger_", sql)

    def test_readiness_artifacts_document_boundaries_and_remaining_gates(self) -> None:
        contract_md = CONTRACT_MD_PATH.read_text(encoding="utf-8")
        readiness_md = READINESS_MD_PATH.read_text(encoding="utf-8")

        self.assertIn("Status: DRAFT_PASS", contract_md)
        self.assertIn("migration_executed=false", contract_md)
        self.assertIn("Future N6 execute remains blocked", contract_md)
        self.assertIn("Status: DRAFT_PASS", readiness_md)
        self.assertIn("migration_executed=false", readiness_md)
        for table in TOUCHED_TABLES:
            self.assertIn(table, readiness_md)
        self.assertIn("ActionBlocked", contract_md)
        self.assertIn("blocked / 未确认", contract_md)
        self.assertIn("N6 canonical schema migration final gate", readiness_md)


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
