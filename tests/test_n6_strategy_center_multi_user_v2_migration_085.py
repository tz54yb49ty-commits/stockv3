from __future__ import annotations

import re
import unittest
from pathlib import Path

from tests.test_n6_strategy_center_n6_trade_date_authority_084 import (
    _insert_complete_authority,
    _prepare as prepare_084,
)
from tests.test_n6_strategy_center_v2_catalog_activation_083 import (
    _insert_active_v1,
)
from tests.test_n6_strategy_worker_canonical_acl_079 import _temporary_postgres


ROOT = Path(__file__).resolve().parents[1]
FORWARD = ROOT / "sql/085_n6_strategy_center_multi_user_v2_selection_migration.sql"
ROLLBACK = ROOT / "sql/085_n6_strategy_center_multi_user_v2_selection_migration_rollback.sql"


class MultiUserV2Migration085Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.forward = FORWARD.read_text(encoding="utf-8")
        cls.rollback = ROLLBACK.read_text(encoding="utf-8")

    def test_forward_is_tooling_only_and_owner_isolated(self) -> None:
        sql = self.forward
        self.assertIn("n6_strategy_center_multi_user_v2_selection_migration_085_v1", sql)
        self.assertIn(
            "n6_strategy_center_migrate_v2_selection_v1(", sql
        )
        self.assertIn("SECURITY DEFINER", sql)
        self.assertIn("ALTER FUNCTION", sql)
        self.assertIn("OWNER TO ashare_v3_user", sql)
        self.assertIn("REVOKE ALL ON FUNCTION", sql)
        self.assertNotIn("common_trade_calendar", sql)
        self.assertNotIn("n6_strategy_match_projection", sql)
        self.assertNotIn("n6_strategy_match_change", sql)
        self.assertNotIn("n6_strategy_observation_projection", sql)

    def test_forward_has_single_v1_to_v2_scope_and_cas(self) -> None:
        sql = self.forward
        for needle in (
            "p_principal_id bigint",
            "p_user_id bigint",
            "p_expected_revision_id bigint",
            "p_expected_revision_no bigint",
            "p_request_id text",
            "principal.owner_user_id = p_user_id",
            "revision.selection_revision_id = p_expected_revision_id",
            "revision.revision_no = p_expected_revision_no",
            "active_revision.selection_revision_id",
            "package_version = 'v1'",
            "package_version = 'v2'",
            "previous_revision_id",
            "'projection_change_write', false",
        ):
            self.assertIn(needle, sql)
        self.assertRegex(sql, r"selection_status, replay_status, request_id")
        self.assertEqual(sql.count("INSERT INTO public.n6_user_strategy_selection_revision"), 1)
        self.assertEqual(sql.count("INSERT INTO public.n6_user_strategy_selection_item"), 1)

    def test_idempotency_and_fail_closed_guards_are_present(self) -> None:
        sql = self.forward
        for marker in (
            "085 idempotency conflict",
            "085 predecessor CAS mismatch",
            "085 pending revision already exists",
            "085 V2 package authority invalid",
            "idempotent_replay",
            "p_request_id !~",
            "pg_advisory_xact_lock",
        ):
            self.assertIn(marker, sql)

    def test_rollback_never_deletes_created_revision(self) -> None:
        sql = self.rollback
        self.assertIn("DROP FUNCTION", sql)
        self.assertIn("085 rollback requires no created revision", sql)
        self.assertNotRegex(sql, r"DELETE\s+FROM\s+public\.n6_user_strategy")
        self.assertNotIn("common_trade_calendar", sql)

    def test_no_trade_or_upstream_writes(self) -> None:
        sql = self.forward + "\n" + self.rollback
        for forbidden in (
            "n6_proposal",
            "n6_order",
            "n6_trade",
            "n6_position",
            "n6_cash",
            "stock_condition_",
            "index_condition_",
            "board_condition_",
        ):
            self.assertNotIn(forbidden, sql.lower())

    def test_temporary_postgres_forward_and_same_request_replay(self) -> None:
        with _temporary_postgres() as postgres:
            prepare_084(postgres)
            _insert_complete_authority(postgres)
            _insert_active_v1(postgres, user_id=1)
            self.assertEqual(
                postgres.file(
                    ROOT / "sql/083_n6_strategy_center_v2_catalog_activation.sql",
                    check=False,
                ).returncode,
                0,
            )
            self.assertEqual(
                postgres.file(
                    ROOT / "sql/084_n6_strategy_center_n6_trade_date_authority.sql",
                    check=False,
                ).returncode,
                0,
            )
            forward = postgres.file(FORWARD, check=False)
            self.assertEqual(forward.returncode, 0, forward.stderr)
            first = postgres.scalar(
                "SELECT n6_strategy_center_migrate_v2_selection_v1("
                "1,1,1,1,'migrate-user-1-20260724');"
            )
            second = postgres.scalar(
                "SELECT n6_strategy_center_migrate_v2_selection_v1("
                "1,1,1,1,'migrate-user-1-20260724');"
            )
            self.assertIn('"idempotent_replay": false', first)
            self.assertIn('"idempotent_replay": true', second)
            self.assertEqual(
                postgres.scalar(
                    "SELECT count(*) FROM n6_user_strategy_selection_revision "
                    "WHERE selection_status='pending';"
                ),
                "1",
            )
            self.assertEqual(
                postgres.scalar("SELECT count(*) FROM n6_strategy_match_projection;"),
                "0",
            )
            self.assertEqual(
                postgres.scalar("SELECT count(*) FROM n6_strategy_match_change;"),
                "0",
            )


if __name__ == "__main__":
    unittest.main()
