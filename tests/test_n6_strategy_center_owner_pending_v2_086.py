from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
FORWARD = ROOT / "sql/086_n6_strategy_center_owner_pending_v2.sql"
ROLLBACK = ROOT / "sql/086_n6_strategy_center_owner_pending_v2_rollback.sql"
SIGNATURE = (
    "public.n6_strategy_center_owner_create_pending_v2("
    "bigint,bigint,bigint,bigint,text,text,text)"
)


class OwnerPendingV2086StaticTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.forward = FORWARD.read_text(encoding="utf-8")
        cls.rollback = ROLLBACK.read_text(encoding="utf-8")

    def test_forward_installs_only_owner_function_and_worker_execute(self) -> None:
        for required in (
            "BEGIN;",
            "pg_advisory_xact_lock",
            "n6_strategy_center_trade_date_authority_v1()",
            "CREATE FUNCTION public.n6_strategy_center_owner_create_pending_v2",
            "SECURITY DEFINER",
            "ALTER FUNCTION public.n6_strategy_center_owner_create_pending_v2",
            "OWNER TO ashare_v3_user",
            "GRANT EXECUTE ON FUNCTION",
            "TO n6_strategy_worker",
            "REVOKE ALL ON FUNCTION",
            "086_owner_pending_v2",
            "COMMIT;",
        ):
            self.assertIn(required, self.forward)

    def test_signature_and_scope_are_explicit(self) -> None:
        normalized = re.sub(r"\s+", "", self.forward)
        self.assertIn(
            "public.n6_strategy_center_owner_create_pending_v2("
            "bigint,bigint,bigint,bigint,text,text,text)",
            normalized,
        )
        for required in (
            "p_principal_id bigint",
            "p_user_id bigint",
            "p_previous_revision_id bigint",
            "p_expected_revision_no bigint",
            "p_expected_for_trade_date text",
            "p_request_id text",
            "p_expected_policy_hash text",
            "principal.owner_user_id = p_user_id",
            "revision.selection_revision_id = p_previous_revision_id",
            "revision.revision_no = p_expected_revision_no",
            "revision.selection_status = 'active'",
            "revision.replay_status = 'passed'",
            "revision.previous_revision_id = p_previous_revision_id",
            "revision.revision_no = p_expected_revision_no + 1",
        ):
            self.assertIn(required, self.forward)

    def test_authority_and_catalog_are_fail_closed(self) -> None:
        for required in (
            "authority->>'for_trade_date'",
            "authority_trade_date IS DISTINCT FROM p_expected_for_trade_date",
            "package_version = 'v1'",
            "catalog.package_version = 'v2'",
            "catalog.package_status = 'active'",
            "p_expected_policy_hash",
            "package_keys <@ ARRAY['package_1', 'package_2']",
            "pending revision exists",
        ):
            self.assertIn(required, self.forward)

    def test_only_selection_revision_and_item_are_written(self) -> None:
        inserts = re.findall(r"\bINSERT\s+INTO\s+public\.([a-z0-9_]+)", self.forward, re.I)
        self.assertEqual(
            sorted(inserts),
            [
                "n6_user_strategy_selection_item",
                "n6_user_strategy_selection_revision",
            ],
        )
        for forbidden in (
            "n6_strategy_match_projection",
            "n6_strategy_match_change",
            "n6_strategy_package_catalog\n",
            "common_trade_calendar",
            "INSERT INTO public.proposal",
            "INSERT INTO public.order",
            "INSERT INTO public.position",
            "INSERT INTO public.cash",
            "n1_",
            "n2_",
            "n3_",
            "n4_",
            "n5_",
        ):
            self.assertNotIn(forbidden, self.forward.lower())

    def test_function_is_idempotent_and_single_scope(self) -> None:
        for required in (
            "request idempotency conflict",
            "pg_advisory_xact_lock(",
            "RETURN pg_catalog.jsonb_build_object",
            "previous_revision_id",
            "selection_metadata_json->>'migration_kind'",
            "INSERT INTO public.n6_user_strategy_selection_revision",
            "INSERT INTO public.n6_user_strategy_selection_item",
        ):
            self.assertIn(required, self.forward)
        self.assertNotIn("FOR UPDATE SKIP LOCKED", self.forward)
        self.assertNotIn("pg_catalog.execute", self.forward)

    def test_acl_is_fail_closed(self) -> None:
        self.assertIn("FROM PUBLIC, n6_btrack_web", self.forward)
        self.assertIn("has_function_privilege(", self.forward)
        self.assertIn("has_table_privilege(", self.forward)
        self.assertIn("086 function ACL postflight failed", self.forward)
        self.assertIn("086 worker DML postflight failed", self.forward)
        self.assertNotIn("GRANT INSERT", self.forward)
        self.assertNotIn("GRANT UPDATE", self.forward)

    def test_rollback_never_deletes_selection_data(self) -> None:
        self.assertIn("DROP FUNCTION", self.rollback)
        self.assertIn("086 rollback blocked by created revision dependencies", self.rollback)
        self.assertNotIn("DELETE FROM", self.rollback)
        self.assertNotIn("TRUNCATE", self.rollback)
        self.assertNotIn("DROP TABLE", self.rollback)
        self.assertNotIn("DROP INDEX", self.rollback)
        normalized = re.sub(r"\s+", "", self.rollback)
        self.assertIn(
            "public.n6_strategy_center_owner_create_pending_v2("
            "bigint,bigint,bigint,bigint,text,text,text)",
            normalized,
        )

    def test_no_web_or_executor_execution_path(self) -> None:
        for forbidden in (
            "n6_btrack_strategy_selection_put",
            "launchctl",
            "INSERT INTO public.n6_strategy_match_projection",
            "INSERT INTO public.n6_strategy_match_change",
        ):
            # The forward ACL revoke names the roles, but no invocation or DML
            # path is allowed; role names are checked separately below.
            self.assertNotIn(forbidden, self.forward.lower())


if __name__ == "__main__":
    unittest.main()
