from __future__ import annotations

from pathlib import Path
import re
import unittest

from tests.test_n6_strategy_center_temporal_confluence_v2_catalog_081 import (
    MIGRATION as MIGRATION_081,
    POSTGRES_FIXTURE_SQL,
)
from tests.test_n6_strategy_center_v2_user_compensation_082 import (
    MIGRATION as MIGRATION_082,
)
from tests.test_n6_strategy_worker_canonical_acl_079 import (
    _temporary_postgres,
)


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/083_n6_strategy_center_v2_catalog_activation.sql"
ROLLBACK = (
    ROOT / "sql/083_n6_strategy_center_v2_catalog_activation_rollback.sql"
)


def _prepare(postgres: object, *, include_082: bool = True) -> None:
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
    forward_081 = postgres.file(MIGRATION_081, check=False)
    if forward_081.returncode != 0:
        raise AssertionError(forward_081.stderr)
    if include_082:
        forward_082 = postgres.file(MIGRATION_082, check=False)
        if forward_082.returncode != 0:
            raise AssertionError(forward_082.stderr)


def _insert_active_v1(postgres: object, *, user_id: int = 1) -> None:
    postgres.sql(
        f"""
        INSERT INTO user_account VALUES ({user_id}, 'active');
        INSERT INTO n6_principal (
          principal_id, principal_type, owner_user_id, principal_status
        ) VALUES (
          {user_id}, 'human_user', {user_id}, 'active'
        );
        INSERT INTO n6_user_strategy_selection_revision (
          principal_id, principal_type, user_id, revision_no,
          selection_status, replay_status, request_id,
          effective_trade_date, selection_policy_hash, created_by_user_id,
          selection_metadata_json, activated_at
        )
        SELECT {user_id}, 'human_user', {user_id}, 1,
               'active', 'passed', 'active-v1-user-{user_id}',
               CURRENT_DATE, catalog.policy_hash, {user_id},
               jsonb_build_object(
                 'source', '083-test-existing-v1',
                 'package_version', 'v1'
               ),
               clock_timestamp()
        FROM n6_strategy_package_catalog catalog
        WHERE catalog.package_key='package_1'
          AND catalog.package_version='v1';
        INSERT INTO n6_user_strategy_selection_item (
          selection_revision_id, package_key, package_version
        )
        SELECT revision.selection_revision_id, 'package_1', 'v1'
        FROM n6_user_strategy_selection_revision revision
        WHERE revision.user_id={user_id} AND revision.revision_no=1;
        """
    )


def _selection_snapshot(postgres: object) -> str:
    return postgres.scalar(
        """
        WITH frozen AS (
          SELECT 'revision:' || row_to_json(revision)::text AS authority
          FROM n6_user_strategy_selection_revision revision
          UNION ALL
          SELECT 'item:' || row_to_json(item)::text AS authority
          FROM n6_user_strategy_selection_item item
        )
        SELECT md5(COALESCE(
          string_agg(authority, '|' ORDER BY authority), ''
        ))
        FROM frozen;
        """
    )


def _acl_snapshot(postgres: object) -> str:
    return postgres.scalar(
        """
        WITH authority AS (
          SELECT 'relation:' || relation.oid::text || ':' ||
                 COALESCE(relation.relacl::text, '') AS value
          FROM pg_class relation
          JOIN pg_namespace namespace
            ON namespace.oid = relation.relnamespace
          WHERE namespace.nspname = 'public'
          UNION ALL
          SELECT 'function:' || procedure.oid::text || ':' ||
                 COALESCE(procedure.proacl::text, '') AS value
          FROM pg_proc procedure
          JOIN pg_namespace namespace
            ON namespace.oid = procedure.pronamespace
          WHERE namespace.nspname = 'public'
        )
        SELECT md5(COALESCE(string_agg(value, '|' ORDER BY value), ''))
        FROM authority;
        """
    )


def _catalog_state(postgres: object) -> str:
    return postgres.scalar(
        """
        SELECT string_agg(
          package_version || ':' || package_key || ':' ||
          package_status || ':' || default_selected::text,
          ',' ORDER BY package_version, package_key
        )
        FROM n6_strategy_package_catalog
        WHERE package_key IN ('package_1', 'package_2');
        """
    )


class StrategyCenterV2CatalogActivation083StaticTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.migration = MIGRATION.read_text(encoding="utf-8")
        cls.rollback = ROLLBACK.read_text(encoding="utf-8")

    def test_activation_is_owner_only_catalog_only_and_fail_closed(self) -> None:
        for required in (
            "083 owner migration identity rejected",
            "083 required 081/082 lineage missing",
            "083 current open trade date required",
            "083 selection write window not quiesced",
            "083 active principal selection coverage drift",
            "idx_081_n6_strategy_match_v2_grain",
            "idx_082_n6_strategy_selection_live_previous_revision",
            "0030c7218da533704a69405bc74682d22d318ee127837c42b6a40dc9a5185d58",
            "12d6d2da725b1496a451cd6e02b9403b633ee33eee900b58870ed4b116fa52bb",
            "LOCK TABLE public.n6_principal IN SHARE MODE",
            "LOCK TABLE public.n6_user_strategy_selection_revision IN SHARE MODE",
            "package_status = 'grandfathered'",
            "package_status = 'active'",
            "catalog.package_key = 'package_1'",
        ):
            self.assertIn(required, self.migration)
        update_targets = re.findall(
            r"(?i)UPDATE\s+(public\.[a-z0-9_]+)", self.migration
        )
        self.assertEqual(
            update_targets,
            [
                "public.n6_strategy_package_catalog",
                "public.n6_strategy_package_catalog",
            ],
        )
        self.assertNotRegex(
            self.migration,
            r"(?i)\b(?:INSERT\s+INTO|DELETE\s+FROM|TRUNCATE)\s+public\.",
        )
        for forbidden in (
            "GRANT ",
            "REVOKE ",
            "CREATE FUNCTION",
            "ALTER TABLE",
            "DROP ",
        ):
            self.assertNotIn(forbidden, self.migration.upper())

    def test_rollback_preserves_history_and_rejects_v2_selection_history(
        self,
    ) -> None:
        for required in (
            "083 rollback owner migration identity rejected",
            "083 rollback blocked by V2 selection history",
            "package_status = 'selectable'",
            "package_status = 'active'",
            "LOCK TABLE public.n6_user_strategy_selection_revision IN SHARE MODE",
        ):
            self.assertIn(required, self.rollback)
        update_targets = re.findall(
            r"(?i)UPDATE\s+(public\.[a-z0-9_]+)", self.rollback
        )
        self.assertEqual(
            update_targets,
            [
                "public.n6_strategy_package_catalog",
                "public.n6_strategy_package_catalog",
            ],
        )
        self.assertNotRegex(
            self.rollback,
            r"(?i)\b(?:INSERT\s+INTO|DELETE\s+FROM|TRUNCATE)\s+public\.",
        )


class StrategyCenterV2CatalogActivation083PostgresTest(unittest.TestCase):
    def test_forward_and_safe_rollback_preserve_v1_revisions_and_acl(
        self,
    ) -> None:
        with _temporary_postgres() as postgres:
            _prepare(postgres)
            _insert_active_v1(postgres)
            selection_before = _selection_snapshot(postgres)
            acl_before = _acl_snapshot(postgres)

            forward = postgres.file(MIGRATION, check=False)
            self.assertEqual(forward.returncode, 0, forward.stderr)
            self.assertEqual(
                _catalog_state(postgres),
                (
                    "v1:package_1:grandfathered:false,"
                    "v1:package_2:grandfathered:false,"
                    "v2:package_1:active:true,"
                    "v2:package_2:active:false"
                ),
            )
            self.assertEqual(_selection_snapshot(postgres), selection_before)
            self.assertEqual(_acl_snapshot(postgres), acl_before)

            rollback = postgres.file(ROLLBACK, check=False)
            self.assertEqual(rollback.returncode, 0, rollback.stderr)
            self.assertEqual(
                _catalog_state(postgres),
                (
                    "v1:package_1:active:true,"
                    "v1:package_2:active:false,"
                    "v2:package_1:selectable:false,"
                    "v2:package_2:selectable:false"
                ),
            )
            self.assertEqual(_selection_snapshot(postgres), selection_before)
            self.assertEqual(_acl_snapshot(postgres), acl_before)

            repeated_rollback = postgres.file(ROLLBACK, check=False)
            self.assertNotEqual(repeated_rollback.returncode, 0)
            self.assertIn(
                "083 rollback catalog authority drift",
                repeated_rollback.stderr,
            )
            self.assertEqual(_selection_snapshot(postgres), selection_before)

    def test_new_principal_default_and_selection_put_both_target_v2(
        self,
    ) -> None:
        with _temporary_postgres() as postgres:
            _prepare(postgres)
            _insert_active_v1(postgres, user_id=1)
            self.assertEqual(
                postgres.file(MIGRATION, check=False).returncode,
                0,
            )
            postgres.sql(
                """
                CREATE TRIGGER trg_083_test_default_selection
                AFTER INSERT ON n6_principal
                FOR EACH ROW EXECUTE FUNCTION
                  n6_strategy_default_selection_on_principal_insert();
                INSERT INTO user_account VALUES (2, 'active');
                INSERT INTO n6_principal (
                  principal_id, principal_type, owner_user_id,
                  principal_status
                ) VALUES (2, 'human_user', 2, 'active');
                """
            )
            self.assertEqual(
                postgres.scalar(
                    """
                    SELECT revision.selection_status || ':' ||
                           revision.replay_status || ':' ||
                           item.package_key || ':' || item.package_version ||
                           ':' ||
                           (revision.selection_metadata_json->>
                              'package_version')
                    FROM n6_user_strategy_selection_revision revision
                    JOIN n6_user_strategy_selection_item item
                      ON item.selection_revision_id =
                         revision.selection_revision_id
                    WHERE revision.user_id=2;
                    """
                ),
                "active:pending:package_1:v2:v2",
            )

            postgres.sql(
                """
                CREATE OR REPLACE FUNCTION n6_btrack_resolve_authority(text)
                RETURNS jsonb LANGUAGE sql STABLE
                AS $$
                  SELECT jsonb_build_object(
                    'principal_id', 1,
                    'principal_type', 'human_user',
                    'user_id', 1
                  )
                $$;
                """
            )
            selection_put = postgres.sql(
                """
                SELECT n6_btrack_strategy_selection_put(
                  '083-session-token',
                  ARRAY['package_1','package_2']::text[],
                  1,
                  '083-selection-put-v2-user-1'
                );
                """,
                user="n6_btrack_web",
                check=False,
            )
            self.assertEqual(
                selection_put.returncode, 0, selection_put.stderr
            )
            self.assertEqual(
                postgres.scalar(
                    """
                    SELECT revision.selection_status || ':' ||
                           revision.replay_status || ':' ||
                           string_agg(
                             item.package_key || ':' || item.package_version,
                             ',' ORDER BY item.package_key
                           )
                    FROM n6_user_strategy_selection_revision revision
                    JOIN n6_user_strategy_selection_item item
                      ON item.selection_revision_id =
                         revision.selection_revision_id
                    WHERE revision.user_id=1 AND revision.revision_no=2
                    GROUP BY revision.selection_status,
                             revision.replay_status;
                    """
                ),
                "pending:pending:package_1:v2,package_2:v2",
            )
            rollback = postgres.file(ROLLBACK, check=False)
            self.assertNotEqual(rollback.returncode, 0)
            self.assertIn(
                "083 rollback blocked by V2 selection history",
                rollback.stderr,
            )
            self.assertEqual(
                _catalog_state(postgres),
                (
                    "v1:package_1:grandfathered:false,"
                    "v1:package_2:grandfathered:false,"
                    "v2:package_1:active:true,"
                    "v2:package_2:active:false"
                ),
            )

    def test_prior_open_effective_date_can_activate_and_roll_back(self) -> None:
        with _temporary_postgres() as postgres:
            _prepare(postgres)
            _insert_active_v1(postgres)
            postgres.sql(
                """
                UPDATE n6_strategy_package_catalog
                SET effective_from_trade_date=CURRENT_DATE - 1
                WHERE package_version='v2';
                """
            )
            forward = postgres.file(MIGRATION, check=False)
            self.assertEqual(forward.returncode, 0, forward.stderr)
            self.assertEqual(
                postgres.scalar(
                    """
                    SELECT count(*)
                    FROM n6_strategy_package_catalog
                    WHERE package_version='v2'
                      AND package_status='active'
                      AND effective_from_trade_date=CURRENT_DATE - 1;
                    """
                ),
                "2",
            )
            rollback = postgres.file(ROLLBACK, check=False)
            self.assertEqual(rollback.returncode, 0, rollback.stderr)
            self.assertEqual(
                postgres.scalar(
                    """
                    SELECT count(*)
                    FROM n6_strategy_package_catalog
                    WHERE package_version='v2'
                      AND package_status='selectable'
                      AND effective_from_trade_date=CURRENT_DATE - 1;
                    """
                ),
                "2",
            )

    def test_owner_lineage_policy_date_and_write_window_drift_fail_closed(
        self,
    ) -> None:
        with _temporary_postgres() as postgres:
            _prepare(postgres)
            _insert_active_v1(postgres)
            initial_state = _catalog_state(postgres)

            non_owner = postgres.sql(
                MIGRATION.read_text(encoding="utf-8"),
                user="n6_btrack_web",
                check=False,
            )
            self.assertNotEqual(non_owner.returncode, 0)
            self.assertIn(
                "083 owner migration identity rejected", non_owner.stderr
            )
            self.assertEqual(_catalog_state(postgres), initial_state)

            postgres.sql(
                """
                UPDATE n6_strategy_package_catalog
                SET policy_hash=repeat('0',64)
                WHERE package_key='package_1' AND package_version='v2';
                """
            )
            policy_drift = postgres.file(MIGRATION, check=False)
            self.assertNotEqual(policy_drift.returncode, 0)
            self.assertIn(
                "083 catalog authority or activation date drift",
                policy_drift.stderr,
            )
            postgres.sql(
                """
                UPDATE n6_strategy_package_catalog
                SET policy_hash =
                  '0030c7218da533704a69405bc74682d22d318ee127837c42b6a40dc9a5185d58'
                WHERE package_key='package_1' AND package_version='v2';
                """
            )

            postgres.sql(
                """
                UPDATE n6_strategy_package_catalog
                SET effective_from_trade_date=CURRENT_DATE + 1
                WHERE package_version='v2';
                """
            )
            date_drift = postgres.file(MIGRATION, check=False)
            self.assertNotEqual(date_drift.returncode, 0)
            self.assertIn(
                "083 catalog authority or activation date drift",
                date_drift.stderr,
            )
            postgres.sql(
                """
                UPDATE n6_strategy_package_catalog
                SET effective_from_trade_date=CURRENT_DATE
                WHERE package_version='v2';
                """
            )

            postgres.sql(
                """
                INSERT INTO n6_user_strategy_selection_revision (
                  principal_id, principal_type, user_id, revision_no,
                  selection_status, replay_status, request_id,
                  effective_trade_date, previous_revision_id,
                  selection_policy_hash, created_by_user_id
                )
                SELECT 1, 'human_user', 1, 2, 'pending', 'pending',
                       '083-unquiesced-pending-v1', CURRENT_DATE,
                       selection_revision_id, selection_policy_hash, 1
                FROM n6_user_strategy_selection_revision
                WHERE user_id=1 AND revision_no=1;
                INSERT INTO n6_user_strategy_selection_item (
                  selection_revision_id, package_key, package_version
                )
                SELECT pending.selection_revision_id, 'package_1', 'v1'
                FROM n6_user_strategy_selection_revision pending
                WHERE pending.user_id=1 AND pending.revision_no=2;
                """
            )
            pending_drift = postgres.file(MIGRATION, check=False)
            self.assertNotEqual(pending_drift.returncode, 0)
            self.assertIn(
                "083 selection write window not quiesced",
                pending_drift.stderr,
            )
            self.assertEqual(_catalog_state(postgres), initial_state)

    def test_missing_082_and_repeated_forward_are_rejected_without_partial_flip(
        self,
    ) -> None:
        with _temporary_postgres() as postgres:
            _prepare(postgres, include_082=False)
            _insert_active_v1(postgres)
            missing_082 = postgres.file(MIGRATION, check=False)
            self.assertNotEqual(missing_082.returncode, 0)
            self.assertIn(
                "083 required 081/082 lineage missing",
                missing_082.stderr,
            )
            self.assertEqual(
                _catalog_state(postgres),
                (
                    "v1:package_1:active:true,"
                    "v1:package_2:active:false,"
                    "v2:package_1:selectable:false,"
                    "v2:package_2:selectable:false"
                ),
            )

        with _temporary_postgres() as postgres:
            _prepare(postgres)
            _insert_active_v1(postgres)
            first = postgres.file(MIGRATION, check=False)
            self.assertEqual(first.returncode, 0, first.stderr)
            activated_state = _catalog_state(postgres)
            repeated = postgres.file(MIGRATION, check=False)
            self.assertNotEqual(repeated.returncode, 0)
            self.assertIn(
                "083 catalog authority or activation date drift",
                repeated.stderr,
            )
            self.assertEqual(_catalog_state(postgres), activated_state)


if __name__ == "__main__":
    unittest.main()
