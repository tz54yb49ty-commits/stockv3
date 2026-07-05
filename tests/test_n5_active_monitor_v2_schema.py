from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MIGRATION_SQL = ROOT / "sql" / "N5_20260626_active_monitor_v2_additive_schema_migration.sql"
ROLLBACK_SQL = ROOT / "sql" / "N5_20260626_active_monitor_v2_additive_schema_rollback.sql"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8").lower()


class N5ActiveMonitorV2SchemaTest(unittest.TestCase):
    def test_migration_adds_required_columns_and_preserves_state_key_compat(self) -> None:
        sql = _read(MIGRATION_SQL)

        self.assertIn("alter table public.common_action_tracking_state", sql)
        for column in (
            "monitor_window_id text",
            "trigger_type text",
            "triggered_periods jsonb not null default '[]'::jsonb",
            "trigger_context_version text",
            "last_seen_metric_key jsonb",
            "last_final_evaluated_metric_key jsonb",
        ):
            with self.subTest(column=column):
                self.assertIn(column, sql)

        self.assertIn("state_key remains the legacy-compatible persistence key", sql)
        self.assertIn("monitor_window_id is added as the active-monitor v2 primary window key", sql)
        self.assertNotIn("confirmation_metric_run_id", sql)
        self.assertNotIn("confirmation_metric_id", sql)
        self.assertNotIn("source_n4_event_run_id", sql)

    def test_migration_adds_required_constraints_and_indexes(self) -> None:
        sql = _read(MIGRATION_SQL)

        self.assertIn("alter column monitor_window_id set not null", sql)
        self.assertIn("check (btrim(monitor_window_id) <> '')", sql)
        self.assertIn("check (jsonb_typeof(triggered_periods) = 'array')", sql)
        self.assertIn("last_seen_metric_key is null", sql)
        self.assertIn("jsonb_typeof(last_seen_metric_key) = 'object'", sql)
        self.assertIn("last_final_evaluated_metric_key is null", sql)
        self.assertIn("jsonb_typeof(last_final_evaluated_metric_key) = 'object'", sql)
        self.assertIn(
            "trigger_type in ('buy', 'buy:full', 'sell', 'sell:full', 'buy_hint', 'sell_hint')",
            sql,
        )
        self.assertIn("unique (run_id, monitor_window_id)", sql)

        self.assertIn(
            "create index if not exists idx_common_action_tracking_state_run_monitor_window",
            sql,
        )
        self.assertIn(
            "on public.common_action_tracking_state (run_id, monitor_window_id)",
            sql,
        )
        self.assertIn(
            "create index if not exists idx_common_action_tracking_state_run_tracking_time",
            sql,
        )
        self.assertIn(
            "on public.common_action_tracking_state (run_id, tracking_status, latest_n4_event_time)",
            sql,
        )
        self.assertIn(
            "create index if not exists idx_common_action_tracking_state_trade_identity_status",
            sql,
        )
        self.assertIn(
            "on public.common_action_tracking_state (trade_date, asset_kind, identity_key, tracking_status)",
            sql,
        )

    def test_migration_does_not_tighten_legacy_fact_or_event_tables(self) -> None:
        sql = _read(MIGRATION_SQL)

        for table in ("stock_action_fact", "index_action_fact", "board_action_fact", "common_action_event"):
            with self.subTest(table=table):
                self.assertNotIn(f"alter table public.{table}", sql)
                self.assertNotIn(f"create index if not exists idx_{table}", sql)

    def test_rollback_is_additive_only_and_guarded(self) -> None:
        sql = _read(ROLLBACK_SQL)

        self.assertIn("rollback blocked", sql)
        self.assertIn("monitor_window_id is not null and monitor_window_id <> state_key", sql)
        self.assertIn("or trigger_type is not null", sql)
        self.assertIn("or triggered_periods <> '[]'::jsonb", sql)
        self.assertIn("or trigger_context_version is not null", sql)
        self.assertIn("or last_seen_metric_key is not null", sql)
        self.assertIn("or last_final_evaluated_metric_key is not null", sql)

        self.assertIn("drop index if exists public.idx_common_action_tracking_state_run_monitor_window", sql)
        self.assertIn("drop index if exists public.idx_common_action_tracking_state_run_tracking_time", sql)
        self.assertIn("drop index if exists public.idx_common_action_tracking_state_trade_identity_status", sql)
        self.assertIn("drop constraint if exists common_action_tracking_state_run_monitor_window_uniq", sql)
        self.assertIn("alter column monitor_window_id drop not null", sql)
        self.assertIn("drop column if exists monitor_window_id", sql)
        self.assertNotIn("drop table common_action_tracking_state", sql)
        self.assertNotIn("delete from public.common_action_tracking_state", sql)


if __name__ == "__main__":
    unittest.main()
