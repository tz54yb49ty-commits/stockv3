from pathlib import Path
import re
import unittest


MIGRATION_SQL = Path("sql/N3P_trigger_proof_ready_schema_compat_migration.sql")
ROLLBACK_SQL = Path("sql/N3P_trigger_proof_ready_schema_compat_rollback.sql")

TABLES = (
    "stock_action_confirmation_projection_metric",
    "index_action_confirmation_projection_metric",
    "board_action_confirmation_projection_metric",
)


def _normalize_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


def _migration_block(sql: str, table: str) -> str:
    marker = f"ALTER TABLE {table}\n  ADD CONSTRAINT {table}_check CHECK ("
    start = sql.index(marker)
    end = sql.index("\n);\n", start) + len("\n);")
    return sql[start:end]


def _generic_ready_legacy_branch(row: dict) -> bool:
    if not row.get("metric_ready"):
        return True
    return (
        row.get("metric_quality_status") == "passed"
        and row.get("current_price") is not None
        and row.get("current_price_time") is not None
        and row.get("previous_120m_body_high") is not None
        and row.get("previous_120m_body_low") is not None
        and row.get("previous_30m_body_high") is not None
        and row.get("previous_30m_body_low") is not None
        and row.get("previous_5m_body_high") is not None
        and row.get("previous_5m_body_low") is not None
        and row.get("previous_1m_body_high") is not None
        and row.get("previous_1m_body_low") is not None
        and row.get("current_1m_amount") is not None
        and row.get("current_5m_virtual_amount") is not None
        and (row.get("is_first_1m_of_day") or row.get("previous_1m_amount") is not None)
        and (row.get("is_first_5m_of_day") or row.get("previous_5m_full_amount") is not None)
        and row.get("previous_1m_period_source") != "not_available"
        and row.get("previous_5m_period_source") != "not_available"
        and row.get("previous_30m_period_source") != "not_available"
        and row.get("previous_120m_period_source") != "not_available"
        and bool(row.get("source_fact_ids"))
        and len(row.get("source_minute_refs") or []) > 0
    )


def _trigger_proof_ready_branch(row: dict) -> bool:
    raw_json = row.get("raw_json") or {}
    source_fact_ids = row.get("source_fact_ids") or {}
    compat = raw_json.get("trigger_proof_segment_source_db_compat") or {}
    return (
        row.get("metric_ready") is True
        and row.get("metric_quality_status") == "passed"
        and row.get("current_price") is not None
        and row.get("current_price_time") is not None
        and bool(source_fact_ids)
        and len(row.get("source_minute_refs") or []) > 0
        and row.get("previous_1m_period_source") == "not_available"
        and row.get("previous_5m_period_source") == "not_available"
        and row.get("previous_30m_period_source") == "not_available"
        and row.get("previous_120m_period_source") == "not_available"
        and raw_json.get("metric_role") == "trigger_proof"
        and raw_json.get("proof_owner") == "N3"
        and raw_json.get("proof_consumer") == "N4"
        and raw_json.get("not_n5_final_proof") is True
        and raw_json.get("action_confirmation_ready") is False
        and raw_json.get("previous_day_cumulative_source") is True
        and source_fact_ids.get("source_mode") == "b1_source_returned_snapshot"
        and compat.get("db_facing_value") == "not_available"
        and compat.get("reason") == "trigger_proof_does_not_use_action_confirmation_segments"
    )


def _revised_ready_check(row: dict) -> bool:
    return (
        row.get("metric_ready") is False
        or _generic_ready_legacy_branch(row)
        or _trigger_proof_ready_branch(row)
    )


class N3PTriggerProofReadySchemaCompatTest(unittest.TestCase):
    def test_migration_artifact_replaces_only_generic_ready_checks(self) -> None:
        sql = MIGRATION_SQL.read_text()

        self.assertNotIn("INSERT INTO", sql.upper())
        self.assertNotIn("DELETE FROM", sql.upper())
        self.assertNotIn("UPDATE ", sql.upper())
        self.assertNotIn("common_event_outbox", sql)

        for table in TABLES:
            self.assertIn(f"ALTER TABLE {table}\n  DROP CONSTRAINT {table}_check;", sql)
            block = _migration_block(sql, table)
            self.assertIn("raw_json->>'metric_role' = 'trigger_proof'", block)
            self.assertIn("raw_json->>'proof_owner' = 'N3'", block)
            self.assertIn("raw_json->>'proof_consumer' = 'N4'", block)
            self.assertIn("raw_json->>'not_n5_final_proof' = 'true'", block)
            self.assertIn("raw_json->>'action_confirmation_ready' = 'false'", block)
            self.assertIn("previous_5m_period_source = 'not_available'", block)
            self.assertIn("previous_5m_period_source <> 'not_available'", block)

    def test_stock_index_board_constraints_are_symmetric(self) -> None:
        sql = MIGRATION_SQL.read_text()
        normalized = []
        for table in TABLES:
            asset_kind = table.split("_", 1)[0]
            block = _migration_block(sql, table)
            block = block.replace(table, "<table>")
            block = block.replace(f"asset_kind = '{asset_kind}'", "asset_kind = '<asset_kind>'")
            normalized.append(_normalize_sql(block))

        self.assertEqual(normalized[0], normalized[1])
        self.assertEqual(normalized[1], normalized[2])

    def test_trigger_proof_ready_row_can_use_not_available_segment_sources(self) -> None:
        row = {
            "metric_ready": True,
            "metric_quality_status": "passed",
            "current_price": 12.3,
            "current_price_time": "2026-06-29T14:55:00+08:00",
            "previous_1m_period_source": "not_available",
            "previous_5m_period_source": "not_available",
            "previous_30m_period_source": "not_available",
            "previous_120m_period_source": "not_available",
            "source_fact_ids": {"source_mode": "b1_source_returned_snapshot"},
            "source_minute_refs": [{"source": "n3p_mixed_realtime_source_payload_20260629_until_1455_v1"}],
            "raw_json": {
                "metric_role": "trigger_proof",
                "proof_owner": "N3",
                "proof_consumer": "N4",
                "not_n5_final_proof": True,
                "action_confirmation_ready": False,
                "previous_day_cumulative_source": True,
                "trigger_proof_segment_source_db_compat": {
                    "db_facing_value": "not_available",
                    "reason": "trigger_proof_does_not_use_action_confirmation_segments",
                },
            },
        }

        self.assertTrue(_revised_ready_check(row))

    def test_legacy_ready_row_still_requires_valid_segment_sources(self) -> None:
        legacy_row = {
            "metric_ready": True,
            "metric_quality_status": "passed",
            "current_price": 12.3,
            "current_price_time": "2026-06-29T14:55:00+08:00",
            "previous_120m_body_high": 13,
            "previous_120m_body_low": 11,
            "previous_30m_body_high": 13,
            "previous_30m_body_low": 11,
            "previous_5m_body_high": 13,
            "previous_5m_body_low": 11,
            "previous_1m_body_high": 13,
            "previous_1m_body_low": 11,
            "current_1m_amount": 1,
            "current_5m_virtual_amount": 5,
            "is_first_1m_of_day": False,
            "is_first_5m_of_day": False,
            "previous_1m_amount": 1,
            "previous_5m_full_amount": 5,
            "previous_1m_period_source": "same_trade_date_previous_period",
            "previous_5m_period_source": "not_available",
            "previous_30m_period_source": "same_trade_date_previous_period",
            "previous_120m_period_source": "same_trade_date_previous_period",
            "source_fact_ids": {"source": "legacy_action_confirmation"},
            "source_minute_refs": [{"minute": "14:55"}],
            "raw_json": {},
        }
        self.assertFalse(_revised_ready_check(legacy_row))

        legacy_row["previous_5m_period_source"] = "same_trade_date_previous_period"
        self.assertTrue(_revised_ready_check(legacy_row))

    def test_not_n5_final_proof_false_cannot_bypass_segment_checks(self) -> None:
        row = {
            "metric_ready": True,
            "metric_quality_status": "passed",
            "current_price": 12.3,
            "current_price_time": "2026-06-29T14:55:00+08:00",
            "previous_1m_period_source": "not_available",
            "previous_5m_period_source": "not_available",
            "previous_30m_period_source": "not_available",
            "previous_120m_period_source": "not_available",
            "source_fact_ids": {"source_mode": "b1_source_returned_snapshot"},
            "source_minute_refs": [{"source": "n3p_mixed_realtime_source_payload_20260629_until_1455_v1"}],
            "raw_json": {
                "metric_role": "trigger_proof",
                "proof_owner": "N3",
                "proof_consumer": "N4",
                "not_n5_final_proof": False,
                "action_confirmation_ready": False,
                "previous_day_cumulative_source": True,
                "trigger_proof_segment_source_db_compat": {
                    "db_facing_value": "not_available",
                    "reason": "trigger_proof_does_not_use_action_confirmation_segments",
                },
            },
        }

        self.assertFalse(_revised_ready_check(row))

    def test_rollback_restores_legacy_constraint_without_trigger_proof_branch(self) -> None:
        rollback_sql = ROLLBACK_SQL.read_text()

        self.assertNotIn("trigger_proof", rollback_sql)
        self.assertNotIn("not_n5_final_proof", rollback_sql)
        for table in TABLES:
            self.assertIn(f"ALTER TABLE {table}\n  DROP CONSTRAINT {table}_check;", rollback_sql)
            block = _migration_block(rollback_sql, table)
            self.assertIn("previous_5m_period_source <> 'not_available'", block)
            self.assertNotIn("previous_5m_period_source = 'not_available'", block)


if __name__ == "__main__":
    unittest.main()
