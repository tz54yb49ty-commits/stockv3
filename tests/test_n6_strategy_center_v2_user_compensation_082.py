from __future__ import annotations

from pathlib import Path
import re
import unittest

from tests.test_n6_strategy_center_temporal_confluence_v2_catalog_081 import (
    MIGRATION as MIGRATION_081,
    POSTGRES_FIXTURE_SQL,
)
from tests.test_n6_strategy_worker_canonical_acl_079 import (
    _temporary_postgres,
)


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/082_n6_strategy_center_v2_user_compensation.sql"
ROLLBACK = (
    ROOT
    / "sql/082_n6_strategy_center_v2_user_compensation_rollback.sql"
)
FUNCTION_SIGNATURE = (
    "public.n6_strategy_center_compensate_revision_v1("
    "bigint,text,bigint,bigint,bigint,text,bigint,date,text)"
)
ABANDON_FUNCTION_SIGNATURE = (
    "public.n6_strategy_center_abandon_pending_v2("
    "bigint,text,bigint,bigint,bigint,date,text)"
)


def _prepare(postgres: object) -> None:
    for role in (
        "n6_btrack_web",
        "n6_virtual_executor",
        "n6_quote_writer",
        "n6_ai_agent",
    ):
        postgres.sql(
            f"CREATE ROLE {role} LOGIN NOINHERIT;",
            database="postgres",
            user="cluster_admin",
        )
    postgres.sql(POSTGRES_FIXTURE_SQL)
    result_081 = postgres.file(MIGRATION_081, check=False)
    if result_081.returncode != 0:
        raise AssertionError(result_081.stderr)


def _insert_active_v2(postgres: object, *, user_id: int = 1) -> None:
    postgres.sql(
        f"""
        INSERT INTO user_account VALUES ({user_id}, 'active');
        INSERT INTO n6_user_strategy_selection_revision (
          principal_id, principal_type, user_id, revision_no,
          selection_status, replay_status, request_id,
          effective_trade_date, selection_policy_hash, created_by_user_id,
          activated_at, superseded_at
        )
        SELECT {user_id}, 'human_user', {user_id}, 1,
               'superseded', 'passed', 'historical-v1-user-{user_id}',
               CURRENT_DATE,
               encode(sha256(convert_to(
                 'package_1:v1:' || catalog.policy_hash,
                 'UTF8'
               )), 'hex'),
               {user_id}, clock_timestamp() - interval '1 second',
               clock_timestamp()
        FROM n6_strategy_package_catalog catalog
        WHERE catalog.package_key='package_1'
          AND catalog.package_version='v1';
        INSERT INTO n6_user_strategy_selection_item (
          selection_revision_id, package_key, package_version
        )
        SELECT revision.selection_revision_id, 'package_1', 'v1'
        FROM n6_user_strategy_selection_revision revision
        WHERE revision.user_id = {user_id} AND revision.revision_no = 1;
        INSERT INTO n6_user_strategy_selection_revision (
          principal_id, principal_type, user_id, revision_no,
          selection_status, replay_status, request_id,
          effective_trade_date, previous_revision_id,
          selection_policy_hash, created_by_user_id, activated_at
        )
        SELECT {user_id}, 'human_user', {user_id}, 2,
               'active', 'passed', 'active-v2-user-{user_id}',
               CURRENT_DATE, (
                 SELECT predecessor.selection_revision_id
                 FROM n6_user_strategy_selection_revision predecessor
                 WHERE predecessor.user_id = {user_id}
                   AND predecessor.revision_no = 1
               ),
               encode(sha256(convert_to(string_agg(
                 catalog.package_key || ':' || catalog.package_version || ':' ||
                 catalog.policy_hash,
                 '|' ORDER BY catalog.package_key
               ), 'UTF8')), 'hex'),
               {user_id}, clock_timestamp()
        FROM n6_strategy_package_catalog catalog
        WHERE catalog.package_version='v2'
          AND catalog.package_key IN ('package_1','package_2');
        INSERT INTO n6_user_strategy_selection_item (
          selection_revision_id, package_key, package_version
        )
        SELECT revision.selection_revision_id, package.package_key, 'v2'
        FROM n6_user_strategy_selection_revision revision
        CROSS JOIN (VALUES ('package_1'), ('package_2')) package(package_key)
        WHERE revision.user_id = {user_id} AND revision.revision_no = 2;
        """
    )


def _active_v2_hash(postgres: object, *, user_id: int = 1) -> str:
    return postgres.scalar(
        "SELECT selection_policy_hash "
        "FROM n6_user_strategy_selection_revision "
        f"WHERE user_id={user_id} AND selection_status='active';"
    )


def _insert_active_v1_pending_v2(
    postgres: object, *, user_id: int = 1
) -> None:
    _insert_active_v2(postgres, user_id=user_id)
    postgres.sql(
        f"""
        UPDATE n6_user_strategy_selection_revision
        SET selection_status='pending', replay_status='pending',
            activated_at=NULL
        WHERE user_id={user_id} AND revision_no=2;
        UPDATE n6_user_strategy_selection_revision
        SET selection_status='active', superseded_at=NULL
        WHERE user_id={user_id} AND revision_no=1;
        """
    )


def _revision_id(
    postgres: object, *, user_id: int, revision_no: int
) -> int:
    return int(
        postgres.scalar(
            "SELECT selection_revision_id "
            "FROM n6_user_strategy_selection_revision "
            f"WHERE user_id={user_id} AND revision_no={revision_no};"
        )
    )


def _abandon_call(
    *,
    principal_id: int,
    user_id: int,
    pending_revision_id: int,
    active_revision_id: int,
    request_id: str,
) -> str:
    return (
        "SELECT public.n6_strategy_center_abandon_pending_v2("
        f"{principal_id},'human_user',{user_id},{pending_revision_id},"
        f"{active_revision_id},CURRENT_DATE,'{request_id}');"
    )


class StrategyCenterV2UserCompensation082StaticTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.migration = MIGRATION.read_text(encoding="utf-8")
        cls.rollback = ROLLBACK.read_text(encoding="utf-8")

    def test_owner_only_append_only_contract(self) -> None:
        for required in (
            "strategy_compensation_owner_only",
            "strategy_compensation_current_open_trade_date_required",
            "strategy_compensation_active_v2_revision_drift",
            "strategy_compensation_pending_revision_exists",
            "strategy_compensation_v1_catalog_authority_missing",
            "'pending', 'pending'",
            "previous_revision_id",
            "n6_strategy_center_v2_to_v1_compensation_gate",
            "requires_current_trade_date_replay",
            "REVOKE ALL ON FUNCTION",
            "selection_status IN ('pending', 'active', 'superseded', 'abandoned')",
            "n6_strategy_center_abandon_pending_v2",
            "idx_082_n6_strategy_selection_live_previous_revision",
            "strategy_pending_abandon_active_v1_items_invalid",
            "strategy_pending_abandon_active_v1_catalog_drift",
            "strategy_pending_abandon_v2_items_invalid",
            "strategy_pending_abandon_v2_catalog_drift",
            "strategy_pending_abandon_reserved_metadata_drift",
            "preserved_active_v1_policy_hash",
            "abandoned_pending_v2_policy_hash",
            "abandoned_pending_v2_package_keys",
        ):
            self.assertIn(required, self.migration)
        self.assertNotIn("GRANT EXECUTE", self.migration)
        self.assertEqual(
            len(
                re.findall(
                    r"(?i)UPDATE\s+public\.n6_user_strategy_selection_revision",
                    self.migration,
                )
            ),
            1,
        )
        self.assertNotRegex(
            self.migration,
            r"(?i)DELETE\s+FROM\s+public\.n6_user_strategy",
        )

    def test_rollback_preserves_append_only_audit(self) -> None:
        self.assertIn(
            "082 rollback blocked by compensation audit history",
            self.rollback,
        )
        self.assertNotRegex(self.rollback, r"(?i)DELETE\s+FROM")
        self.assertNotRegex(self.rollback, r"(?i)UPDATE\s+public\.")


class StrategyCenterV2UserCompensation082PostgresTest(unittest.TestCase):
    def test_forward_creates_one_idempotent_pending_v1_revision(self) -> None:
        with _temporary_postgres() as postgres:
            _prepare(postgres)
            forward = postgres.file(MIGRATION, check=False)
            self.assertEqual(forward.returncode, 0, forward.stderr)
            _insert_active_v2(postgres)
            active_v2_hash = _active_v2_hash(postgres)
            call = (
                "SELECT public.n6_strategy_center_compensate_revision_v1("
                f"1,'human_user',1,2,2,'{active_v2_hash}',1,CURRENT_DATE,"
                "'compensate-v2-user-1');"
            )
            first = postgres.scalar(call)
            second = postgres.scalar(call)
            self.assertEqual(first, second)
            idempotency_conflict = postgres.sql(
                "SELECT public.n6_strategy_center_compensate_revision_v1("
                f"1,'human_user',1,2,2,'{active_v2_hash}',999,CURRENT_DATE,"
                "'compensate-v2-user-1');",
                check=False,
            )
            self.assertNotEqual(idempotency_conflict.returncode, 0)
            self.assertIn(
                "strategy_compensation_idempotency_conflict",
                idempotency_conflict.stderr,
            )
            self.assertEqual(
                postgres.scalar(
                    """
                    SELECT count(*) || '|' ||
                           max(selection_status) || '|' ||
                           max(replay_status) || '|' ||
                           max(previous_revision_id)::text
                    FROM n6_user_strategy_selection_revision
                    WHERE revision_no = 3;
                    """
                ),
                "1|pending|pending|2",
            )
            self.assertEqual(
                postgres.scalar(
                    """
                    SELECT string_agg(
                      package_key || ':' || package_version,
                      ',' ORDER BY package_key
                    )
                    FROM n6_user_strategy_selection_item
                    WHERE selection_revision_id = 3;
                    """
                ),
                "package_1:v1",
            )
            self.assertEqual(
                postgres.scalar(
                    """
                    SELECT selection_status || '|' || replay_status
                    FROM n6_user_strategy_selection_revision
                    WHERE selection_revision_id = 2;
                    """
                ),
                "active|passed",
            )
            self.assertEqual(
                postgres.scalar(
                    """
                    SELECT (selection_metadata_json->>'source') || '|' ||
                           (selection_metadata_json->>'compensates_revision_id') ||
                           '|' ||
                           (selection_metadata_json->>'target_v1_revision_id')
                    FROM n6_user_strategy_selection_revision
                    WHERE selection_revision_id = 3;
                    """
                ),
                "n6_strategy_center_v2_to_v1_compensation_gate|2|1",
            )
            self.assertEqual(
                postgres.scalar(
                    """
                    SELECT EXISTS (
                      SELECT 1
                      FROM pg_proc procedure,
                           LATERAL aclexplode(COALESCE(
                             procedure.proacl,
                             acldefault('f', procedure.proowner)
                           )) privilege
                      WHERE procedure.oid =
                            'public.n6_strategy_center_compensate_revision_v1('
                            'bigint,text,bigint,bigint,bigint,text,bigint,date,text)'
                              ::regprocedure
                        AND privilege.grantee = 0
                        AND privilege.privilege_type = 'EXECUTE'
                    );
                    """
                ),
                "f",
            )
            for role in ("n6_btrack_web", "n6_strategy_worker"):
                self.assertEqual(
                    postgres.scalar(
                        "SELECT has_function_privilege("
                        f"'{role}','{FUNCTION_SIGNATURE}','EXECUTE');"
                    ),
                    "f",
                )

    def test_scope_pending_and_catalog_drift_fail_without_partial_revision(self) -> None:
        with _temporary_postgres() as postgres:
            _prepare(postgres)
            self.assertEqual(
                postgres.file(MIGRATION, check=False).returncode,
                0,
            )
            _insert_active_v2(postgres)
            active_v2_hash = _active_v2_hash(postgres)
            bad_hash = postgres.sql(
                "SELECT public.n6_strategy_center_compensate_revision_v1("
                "1,'human_user',1,2,2,'" + ("0" * 64) + "',1,"
                "CURRENT_DATE,'bad-hash-request');",
                check=False,
            )
            self.assertNotEqual(bad_hash.returncode, 0)
            self.assertIn(
                "strategy_compensation_active_v2_revision_drift",
                bad_hash.stderr,
            )
            bad_scope = postgres.sql(
                "SELECT public.n6_strategy_center_compensate_revision_v1("
                f"1,'human_user',1,999,2,'{active_v2_hash}',1,"
                "CURRENT_DATE,'bad-scope-request');",
                check=False,
            )
            self.assertNotEqual(bad_scope.returncode, 0)
            self.assertIn(
                "strategy_compensation_active_v2_revision_drift",
                bad_scope.stderr,
            )
            postgres.sql(
                "UPDATE n6_strategy_package_catalog "
                "SET package_status='selectable' "
                "WHERE package_key='package_1' AND package_version='v1';"
            )
            catalog_drift = postgres.sql(
                "SELECT public.n6_strategy_center_compensate_revision_v1("
                f"1,'human_user',1,2,2,'{active_v2_hash}',1,CURRENT_DATE,"
                "'catalog-drift-request');",
                check=False,
            )
            self.assertNotEqual(catalog_drift.returncode, 0)
            self.assertIn(
                "strategy_compensation_v1_catalog_authority_missing",
                catalog_drift.stderr,
            )
            self.assertEqual(
                postgres.scalar(
                    "SELECT count(*) FROM n6_user_strategy_selection_revision;"
                ),
                "2",
            )

    def test_rollback_drops_unused_function_and_rejects_audit_history(self) -> None:
        with _temporary_postgres() as postgres:
            _prepare(postgres)
            self.assertEqual(
                postgres.file(MIGRATION, check=False).returncode,
                0,
            )
            rollback = postgres.file(ROLLBACK, check=False)
            self.assertEqual(rollback.returncode, 0, rollback.stderr)
            self.assertEqual(
                postgres.scalar(
                    f"SELECT to_regprocedure('{FUNCTION_SIGNATURE}') IS NULL;"
                ),
                "t",
            )

        with _temporary_postgres() as postgres:
            _prepare(postgres)
            self.assertEqual(
                postgres.file(MIGRATION, check=False).returncode,
                0,
            )
            _insert_active_v2(postgres)
            active_v2_hash = _active_v2_hash(postgres)
            postgres.scalar(
                "SELECT public.n6_strategy_center_compensate_revision_v1("
                f"1,'human_user',1,2,2,'{active_v2_hash}',1,CURRENT_DATE,"
                "'rollback-blocked-request');"
            )
            rollback = postgres.file(ROLLBACK, check=False)
            self.assertNotEqual(rollback.returncode, 0)
            self.assertIn(
                "082 rollback blocked by compensation audit history",
                rollback.stderr,
            )
            self.assertEqual(
                postgres.scalar(
                    f"SELECT to_regprocedure('{FUNCTION_SIGNATURE}') IS NOT NULL;"
                ),
                "t",
            )

    def test_pending_v2_can_be_abandoned_without_replacing_active_v1(self) -> None:
        with _temporary_postgres() as postgres:
            _prepare(postgres)
            self.assertEqual(
                postgres.file(MIGRATION, check=False).returncode,
                0,
            )
            _insert_active_v1_pending_v2(postgres)
            call = (
                "SELECT public.n6_strategy_center_abandon_pending_v2("
                "1,'human_user',1,2,1,CURRENT_DATE,"
                "'abandon-pending-v2-user-1');"
            )
            first = postgres.scalar(call)
            second = postgres.scalar(call)
            self.assertEqual(first, second)
            self.assertEqual(
                postgres.scalar(
                    """
                    SELECT string_agg(
                      revision_no::text || ':' || selection_status || ':' ||
                      replay_status,
                      ',' ORDER BY revision_no
                    )
                    FROM n6_user_strategy_selection_revision;
                    """
                ),
                "1:active:passed,2:abandoned:failed",
            )
            self.assertEqual(
                postgres.scalar(
                    "SELECT count(*) FROM n6_user_strategy_selection_revision "
                    "WHERE selection_status='pending';"
                ),
                "0",
            )
            postgres.sql(
                """
                INSERT INTO n6_user_strategy_selection_revision (
                  principal_id, principal_type, user_id, revision_no,
                  selection_status, replay_status, request_id,
                  effective_trade_date, previous_revision_id,
                  selection_policy_hash, created_by_user_id
                )
                SELECT 1, 'human_user', 1, 3, 'pending', 'pending',
                       'replacement-v2-user-1', CURRENT_DATE, 1,
                       selection_policy_hash, 1
                FROM n6_user_strategy_selection_revision
                WHERE selection_revision_id=2;
                INSERT INTO n6_user_strategy_selection_item (
                  selection_revision_id, package_key, package_version
                )
                SELECT 3, package_key, package_version
                FROM n6_user_strategy_selection_item
                WHERE selection_revision_id=2;
                """
            )
            self.assertEqual(
                postgres.scalar(
                    "SELECT previous_revision_id::text || '|' || "
                    "selection_status FROM n6_user_strategy_selection_revision "
                    "WHERE selection_revision_id=3;"
                ),
                "1|pending",
            )
            for role in ("n6_btrack_web", "n6_strategy_worker"):
                self.assertEqual(
                    postgres.scalar(
                        "SELECT has_function_privilege("
                        f"'{role}','{ABANDON_FUNCTION_SIGNATURE}','EXECUTE');"
                    ),
                    "f",
                )
            rollback = postgres.file(ROLLBACK, check=False)
            self.assertNotEqual(rollback.returncode, 0)
            self.assertIn(
                "082 rollback blocked by compensation audit history",
                rollback.stderr,
            )

    def test_abandon_rejects_item_hash_and_catalog_authority_drift(self) -> None:
        with _temporary_postgres() as postgres:
            _prepare(postgres)
            self.assertEqual(
                postgres.file(MIGRATION, check=False).returncode,
                0,
            )
            _insert_active_v1_pending_v2(postgres)
            call = _abandon_call(
                principal_id=1,
                user_id=1,
                pending_revision_id=2,
                active_revision_id=1,
                request_id="abandon-authority-user-1",
            )
            pending_hash = postgres.scalar(
                "SELECT selection_policy_hash "
                "FROM n6_user_strategy_selection_revision "
                "WHERE selection_revision_id=2;"
            )
            active_hash = postgres.scalar(
                "SELECT selection_policy_hash "
                "FROM n6_user_strategy_selection_revision "
                "WHERE selection_revision_id=1;"
            )

            postgres.sql(
                """
                ALTER TABLE n6_user_strategy_selection_item
                  DISABLE TRIGGER ALL;
                INSERT INTO n6_user_strategy_selection_item (
                  selection_revision_id, package_key, package_version
                ) VALUES (2, 'package_x', 'v2');
                ALTER TABLE n6_user_strategy_selection_item
                  ENABLE TRIGGER ALL;
                """,
                user="cluster_admin",
            )
            illegal_key = postgres.sql(call, check=False)
            self.assertNotEqual(illegal_key.returncode, 0)
            self.assertIn(
                "strategy_pending_abandon_v2_items_invalid",
                illegal_key.stderr,
            )
            postgres.sql(
                "DELETE FROM n6_user_strategy_selection_item "
                "WHERE selection_revision_id=2 AND package_key='package_x';",
                user="cluster_admin",
            )

            postgres.sql(
                "UPDATE n6_user_strategy_selection_revision "
                f"SET selection_policy_hash=repeat('0',64) "
                "WHERE selection_revision_id=2;"
            )
            forged_pending_hash = postgres.sql(call, check=False)
            self.assertNotEqual(forged_pending_hash.returncode, 0)
            self.assertIn(
                "strategy_pending_abandon_v2_catalog_drift",
                forged_pending_hash.stderr,
            )
            postgres.sql(
                "UPDATE n6_user_strategy_selection_revision "
                f"SET selection_policy_hash='{pending_hash}' "
                "WHERE selection_revision_id=2;"
            )

            postgres.sql(
                "UPDATE n6_strategy_package_catalog "
                "SET effective_from_trade_date=CURRENT_DATE + 1 "
                "WHERE package_key='package_1' AND package_version='v2';"
            )
            catalog_drift = postgres.sql(call, check=False)
            self.assertNotEqual(catalog_drift.returncode, 0)
            self.assertIn(
                "strategy_pending_abandon_v2_catalog_drift",
                catalog_drift.stderr,
            )
            postgres.sql(
                "UPDATE n6_strategy_package_catalog "
                "SET effective_from_trade_date=CURRENT_DATE "
                "WHERE package_key='package_1' AND package_version='v2';"
            )

            postgres.sql(
                "UPDATE n6_user_strategy_selection_revision "
                "SET selection_policy_hash=repeat('f',64) "
                "WHERE selection_revision_id=1;"
            )
            active_v1_drift = postgres.sql(call, check=False)
            self.assertNotEqual(active_v1_drift.returncode, 0)
            self.assertIn(
                "strategy_pending_abandon_active_v1_catalog_drift",
                active_v1_drift.stderr,
            )
            postgres.sql(
                "UPDATE n6_user_strategy_selection_revision "
                f"SET selection_policy_hash='{active_hash}' "
                "WHERE selection_revision_id=1;"
            )
            self.assertEqual(
                postgres.scalar(
                    "SELECT selection_status || '|' || replay_status "
                    "FROM n6_user_strategy_selection_revision "
                    "WHERE selection_revision_id=2;"
                ),
                "pending|pending",
            )

    def test_abandon_idempotency_freezes_scope_items_hash_and_metadata(
        self,
    ) -> None:
        with _temporary_postgres() as postgres:
            _prepare(postgres)
            self.assertEqual(
                postgres.file(MIGRATION, check=False).returncode,
                0,
            )
            _insert_active_v1_pending_v2(postgres)
            call = _abandon_call(
                principal_id=1,
                user_id=1,
                pending_revision_id=2,
                active_revision_id=1,
                request_id="abandon-idempotent-user-1",
            )
            first = postgres.scalar(call)
            self.assertEqual(first, postgres.scalar(call))
            different_request = postgres.sql(
                _abandon_call(
                    principal_id=1,
                    user_id=1,
                    pending_revision_id=2,
                    active_revision_id=1,
                    request_id="abandon-conflict-user-1",
                ),
                check=False,
            )
            self.assertNotEqual(different_request.returncode, 0)
            self.assertIn(
                "strategy_pending_abandon_idempotency_conflict",
                different_request.stderr,
            )

            active_hash = postgres.scalar(
                "SELECT selection_policy_hash "
                "FROM n6_user_strategy_selection_revision "
                "WHERE selection_revision_id=1;"
            )
            postgres.sql(
                """
                UPDATE n6_user_strategy_selection_revision
                SET selection_metadata_json = pg_catalog.jsonb_set(
                  selection_metadata_json,
                  '{preserved_active_v1_policy_hash}',
                  pg_catalog.to_jsonb(repeat('0',64)::text)
                )
                WHERE selection_revision_id=2;
                """
            )
            metadata_drift = postgres.sql(call, check=False)
            self.assertNotEqual(metadata_drift.returncode, 0)
            self.assertIn(
                "strategy_pending_abandon_idempotency_conflict",
                metadata_drift.stderr,
            )
            postgres.sql(
                """
                UPDATE n6_user_strategy_selection_revision
                SET selection_metadata_json = pg_catalog.jsonb_set(
                  selection_metadata_json,
                  '{preserved_active_v1_policy_hash}',
                  pg_catalog.to_jsonb(%s::text)
                )
                WHERE selection_revision_id=2;
                """
                % ("'" + active_hash + "'")
            )
            postgres.sql(
                "DELETE FROM n6_user_strategy_selection_item "
                "WHERE selection_revision_id=2 AND package_key='package_2';"
            )
            one_package_hash = postgres.scalar(
                """
                SELECT encode(sha256(convert_to(
                  catalog.package_key || ':' || catalog.package_version || ':' ||
                  catalog.policy_hash,
                  'UTF8'
                )), 'hex')
                FROM n6_strategy_package_catalog catalog
                WHERE catalog.package_key='package_1'
                  AND catalog.package_version='v2';
                """
            )
            postgres.sql(
                "UPDATE n6_user_strategy_selection_revision "
                f"SET selection_policy_hash='{one_package_hash}' "
                "WHERE selection_revision_id=2;"
            )
            frozen_item_drift = postgres.sql(call, check=False)
            self.assertNotEqual(frozen_item_drift.returncode, 0)
            self.assertIn(
                "strategy_pending_abandon_idempotency_conflict",
                frozen_item_drift.stderr,
            )

    def test_abandon_isolated_to_exact_principal_user_revision(self) -> None:
        with _temporary_postgres() as postgres:
            _prepare(postgres)
            self.assertEqual(
                postgres.file(MIGRATION, check=False).returncode,
                0,
            )
            _insert_active_v1_pending_v2(postgres, user_id=1)
            _insert_active_v1_pending_v2(postgres, user_id=2)
            user_1_active = _revision_id(
                postgres, user_id=1, revision_no=1
            )
            user_1_pending = _revision_id(
                postgres, user_id=1, revision_no=2
            )
            user_2_active = _revision_id(
                postgres, user_id=2, revision_no=1
            )
            user_2_pending = _revision_id(
                postgres, user_id=2, revision_no=2
            )
            wrong_scope = postgres.sql(
                _abandon_call(
                    principal_id=1,
                    user_id=1,
                    pending_revision_id=user_2_pending,
                    active_revision_id=user_1_active,
                    request_id="abandon-cross-user-blocked",
                ),
                check=False,
            )
            self.assertNotEqual(wrong_scope.returncode, 0)
            self.assertIn(
                "strategy_pending_abandon_v2_revision_drift",
                wrong_scope.stderr,
            )
            postgres.scalar(
                _abandon_call(
                    principal_id=1,
                    user_id=1,
                    pending_revision_id=user_1_pending,
                    active_revision_id=user_1_active,
                    request_id="abandon-isolated-user-1",
                )
            )
            self.assertEqual(
                postgres.scalar(
                    """
                    SELECT string_agg(
                      user_id::text || ':' || revision_no::text || ':' ||
                      selection_status || ':' || replay_status,
                      ',' ORDER BY user_id, revision_no
                    )
                    FROM n6_user_strategy_selection_revision;
                    """
                ),
                (
                    "1:1:active:passed,1:2:abandoned:failed,"
                    "2:1:active:passed,2:2:pending:pending"
                ),
            )
            self.assertEqual(
                postgres.scalar(
                    "SELECT selection_metadata_json ? 'abandon_request_id' "
                    "FROM n6_user_strategy_selection_revision "
                    f"WHERE selection_revision_id={user_2_pending};"
                ),
                "f",
            )
            self.assertGreater(user_2_active, user_1_active)


if __name__ == "__main__":
    unittest.main()
