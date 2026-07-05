from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import re
import unittest


MIGRATION_SQL = Path("sql/N3P_trigger_proof_condition_grain_unique_schema_compat_migration.sql")
ROLLBACK_SQL = Path("sql/N3P_trigger_proof_condition_grain_unique_schema_compat_rollback.sql")

ASSETS = ("stock", "index", "board")
TABLES = tuple(f"{asset}_action_confirmation_projection_metric" for asset in ASSETS)
LEGACY_UNIQUE_NAMES = {
    "stock": "stock_action_confirmation_pro_projection_run_id_identity_ke_key",
    "index": "index_action_confirmation_pro_projection_run_id_identity_ke_key",
    "board": "board_action_confirmation_pro_projection_run_id_identity_ke_key",
}
POSTGRES_TRUNCATED_INDEX_NAMES = {
    "stock": (
        "stock_action_confirmation_projection_metric_legacy_object_minut",
        "stock_action_confirmation_projection_metric_trigger_proof_condi",
    ),
    "index": (
        "index_action_confirmation_projection_metric_legacy_object_minut",
        "index_action_confirmation_projection_metric_trigger_proof_condi",
    ),
    "board": (
        "board_action_confirmation_projection_metric_legacy_object_minut",
        "board_action_confirmation_projection_metric_trigger_proof_condi",
    ),
}


def _normalize(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


def _is_trigger_proof_row(row: dict) -> bool:
    raw_json = row.get("raw_json") or {}
    return (
        raw_json.get("metric_role") == "trigger_proof"
        and raw_json.get("proof_consumer") == "N4"
        and raw_json.get("proof_owner") == "N3"
        and raw_json.get("not_n5_final_proof") is True
        and raw_json.get("action_confirmation_ready") is False
    )


def _legacy_unique_key(row: dict) -> tuple:
    return (
        row.get("projection_run_id"),
        row.get("identity_key"),
        row.get("trade_date"),
        row.get("metric_minute_label"),
        row.get("projection_schema_version"),
    )


def _condition_grain_unique_key(row: dict) -> tuple:
    raw_json = row.get("raw_json") or {}
    trace_json = row.get("trace_json") or {}
    context = trace_json.get("higher_period_context_source") or {}
    return (
        *_legacy_unique_key(row),
        raw_json.get("direction") or context.get("context_direction") or "",
        raw_json.get("signal_type") or "",
        raw_json.get("condition_key") or "",
        raw_json.get("original_condition_key") or raw_json.get("condition_key") or "",
        str(raw_json.get("source_condition_pool_id") or context.get("source_condition_pool_id") or ""),
        str(raw_json.get("source_minute_target_scope_id") or context.get("source_minute_target_scope_id") or ""),
    )


def _violates_revised_uniqueness(rows: list[dict]) -> bool:
    seen: dict[str, set[tuple]] = defaultdict(set)
    for row in rows:
        bucket = "trigger" if _is_trigger_proof_row(row) else "legacy"
        key = _condition_grain_unique_key(row) if bucket == "trigger" else _legacy_unique_key(row)
        if key in seen[bucket]:
            return True
        seen[bucket].add(key)
    return False


def _base_row(**overrides: object) -> dict:
    row = {
        "projection_run_id": "realtime_action_confirmation_metric_20260629_until_1455__asset_all__b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1__market_data_subscription_x",
        "identity_key": "stock:SH:600026",
        "trade_date": "20260629",
        "metric_minute_label": "14:55",
        "projection_schema_version": "v3.realtime_virtual_metric.writer.v1",
        "raw_json": {
            "metric_role": "trigger_proof",
            "proof_owner": "N3",
            "proof_consumer": "N4",
            "not_n5_final_proof": True,
            "action_confirmation_ready": False,
            "direction": "buy",
            "signal_type": "B_BUY",
            "condition_key": "BUY:M,W,D",
            "original_condition_key": "BUY:M,W,D",
            "source_condition_pool_id": 211486,
            "source_minute_target_scope_id": 199999,
        },
        "trace_json": {
            "higher_period_context_source": {
                "context_direction": "buy",
                "source_condition_pool_id": 211486,
                "source_minute_target_scope_id": 199999,
            }
        },
    }
    row.update(overrides)
    return row


class N3PTriggerProofConditionGrainUniqueSchemaCompatTest(unittest.TestCase):
    def test_migration_replaces_legacy_unique_with_two_partial_unique_indexes(self) -> None:
        sql = MIGRATION_SQL.read_text()
        upper = sql.upper()

        for forbidden in ("INSERT ", "UPDATE ", "DELETE ", "TRUNCATE ", "COMMON_EVENT_OUTBOX", "COMMON_EVENT_INBOX"):
            self.assertNotIn(forbidden, upper)

        for asset, table in zip(ASSETS, TABLES):
            old_name = LEGACY_UNIQUE_NAMES[asset]
            self.assertIn(f"ALTER TABLE {table}\n  DROP CONSTRAINT {old_name};", sql)
            self.assertIn(f"CREATE UNIQUE INDEX {table}_legacy_object_minute_uidx", sql)
            self.assertIn(f"CREATE UNIQUE INDEX {table}_trigger_proof_condition_grain_uidx", sql)

            legacy_block = re.search(
                rf"CREATE UNIQUE INDEX {table}_legacy_object_minute_uidx.*?;\n",
                sql,
                flags=re.S,
            )
            trigger_block = re.search(
                rf"CREATE UNIQUE INDEX {table}_trigger_proof_condition_grain_uidx.*?;\n",
                sql,
                flags=re.S,
            )
            self.assertIsNotNone(legacy_block)
            self.assertIsNotNone(trigger_block)
            legacy_text = legacy_block.group(0)
            trigger_text = trigger_block.group(0)

            self.assertIn("WHERE NOT COALESCE((", legacy_text)
            for marker in (
                "raw_json->>'metric_role' = 'trigger_proof'",
                "raw_json->>'proof_consumer' = 'N4'",
                "raw_json->>'proof_owner' = 'N3'",
                "raw_json->>'not_n5_final_proof' = 'true'",
                "raw_json->>'action_confirmation_ready' = 'false'",
            ):
                self.assertIn(marker, legacy_text)
                self.assertIn(marker, trigger_text)
            for expression in (
                "COALESCE(raw_json->>'direction'",
                "COALESCE(raw_json->>'signal_type'",
                "COALESCE(raw_json->>'condition_key'",
                "COALESCE(raw_json->>'original_condition_key'",
                "COALESCE(raw_json->>'source_condition_pool_id'",
                "COALESCE(raw_json->>'source_minute_target_scope_id'",
            ):
                self.assertIn(expression, trigger_text)

    def test_stock_index_board_sql_is_symmetric(self) -> None:
        sql = MIGRATION_SQL.read_text()
        normalized_blocks = []
        for asset, table in zip(ASSETS, TABLES):
            asset_sql = re.findall(
                rf"(ALTER TABLE {table}.*?;|CREATE UNIQUE INDEX {table}_.*?;\n)",
                sql,
                flags=re.S,
            )
            block = "\n".join(asset_sql)
            block = block.replace(table, "<table>")
            block = block.replace(LEGACY_UNIQUE_NAMES[asset], "<legacy_unique>")
            normalized_blocks.append(_normalize(block))

        self.assertEqual(normalized_blocks[0], normalized_blocks[1])
        self.assertEqual(normalized_blocks[1], normalized_blocks[2])

    def test_condition_grain_rows_allow_same_object_minute_when_condition_differs(self) -> None:
        rows = [
            _base_row(),
            _base_row(
                raw_json={
                    **_base_row()["raw_json"],
                    "condition_key": "BUY:Q,M,W,D",
                    "original_condition_key": "BUY:Q,M,W,D",
                    "source_condition_pool_id": 211487,
                    "source_minute_target_scope_id": 200000,
                }
            ),
        ]

        self.assertFalse(_violates_revised_uniqueness(rows))

    def test_duplicate_identical_trigger_proof_condition_grain_fails(self) -> None:
        rows = [_base_row(), _base_row()]

        self.assertTrue(_violates_revised_uniqueness(rows))

    def test_legacy_duplicate_object_minute_still_fails(self) -> None:
        legacy = _base_row(raw_json={"metric_role": "action_confirmation"})
        rows = [legacy, dict(legacy)]

        self.assertTrue(_violates_revised_uniqueness(rows))

    def test_not_n5_final_proof_false_uses_legacy_object_minute_uniqueness(self) -> None:
        first = _base_row(raw_json={**_base_row()["raw_json"], "not_n5_final_proof": False})
        second = _base_row(
            raw_json={
                **_base_row()["raw_json"],
                "not_n5_final_proof": False,
                "condition_key": "BUY:Q,M,W,D",
                "original_condition_key": "BUY:Q,M,W,D",
                "source_condition_pool_id": 211487,
                "source_minute_target_scope_id": 200000,
            }
        )

        self.assertTrue(_violates_revised_uniqueness([first, second]))

    def test_rollback_restores_original_unique_constraints_exactly(self) -> None:
        sql = ROLLBACK_SQL.read_text()
        upper = sql.upper()

        for forbidden in ("INSERT ", "UPDATE ", "DELETE ", "TRUNCATE ", "COMMON_EVENT_OUTBOX", "COMMON_EVENT_INBOX"):
            self.assertNotIn(forbidden, upper)

        for asset, table in zip(ASSETS, TABLES):
            old_name = LEGACY_UNIQUE_NAMES[asset]
            legacy_index_name, trigger_index_name = POSTGRES_TRUNCATED_INDEX_NAMES[asset]
            self.assertIn(f"DROP INDEX IF EXISTS {legacy_index_name};", sql)
            self.assertIn(f"DROP INDEX IF EXISTS {trigger_index_name};", sql)
            self.assertIn(f"ALTER TABLE {table}\n  ADD CONSTRAINT {old_name} UNIQUE", sql)
            self.assertIn(
                "(projection_run_id, identity_key, trade_date, metric_minute_label, projection_schema_version)",
                sql,
            )


if __name__ == "__main__":
    unittest.main()
