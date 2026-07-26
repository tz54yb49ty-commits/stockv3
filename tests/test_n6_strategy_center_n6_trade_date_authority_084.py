from __future__ import annotations

import json
from pathlib import Path
import unittest

from tests.test_n6_strategy_center_temporal_confluence_v2_catalog_081 import (
    MIGRATION as MIGRATION_081,
    POSTGRES_FIXTURE_SQL,
)
from tests.test_n6_strategy_center_v2_user_compensation_082 import (
    MIGRATION as MIGRATION_082,
    _insert_active_v1_pending_v2,
    _revision_id,
)
from tests.test_n6_strategy_worker_canonical_acl_079 import (
    _temporary_postgres,
)


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT / "sql/084_n6_strategy_center_n6_trade_date_authority.sql"
)
ROLLBACK = (
    ROOT
    / "sql/084_n6_strategy_center_n6_trade_date_authority_rollback.sql"
)
FUNCTION_SIGNATURES = (
    "n6_strategy_default_selection_on_principal_insert()",
    "n6_btrack_strategy_center_state(text)",
    "n6_btrack_strategy_selection_put(text,text[],bigint,text)",
    "n6_strategy_center_compensate_revision_v1("
    "bigint,text,bigint,bigint,bigint,text,bigint,date,text)",
    "n6_strategy_center_abandon_pending_v2("
    "bigint,text,bigint,bigint,bigint,date,text)",
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
    postgres.sql(
        """
        INSERT INTO common_trade_calendar VALUES ('20260724', true);
        CREATE TABLE index_condition_display_basis (
          identity_key text, source_trade_date text,
          for_trade_date text, run_id text
        );
        CREATE VIEW v_n6_index_condition_display_basis AS
        SELECT * FROM index_condition_display_basis;
        CREATE TABLE board_condition_display_basis (
          identity_key text, source_trade_date text,
          for_trade_date text, run_id text
        );
        CREATE VIEW v_n6_board_condition_display_basis AS
        SELECT * FROM board_condition_display_basis;
        """
    )
    result_081 = postgres.file(MIGRATION_081, check=False)
    if result_081.returncode != 0:
        raise AssertionError(result_081.stderr)
    result_082 = postgres.file(MIGRATION_082, check=False)
    if result_082.returncode != 0:
        raise AssertionError(result_082.stderr)
    postgres.sql(
        """
        GRANT SELECT ON TABLE
          common_trade_calendar,
          v_n6_stock_condition_display_basis,
          v_n6_index_condition_display_basis,
          v_n6_board_condition_display_basis
        TO n6_strategy_worker;
        """
    )


def _insert_complete_authority(postgres: object) -> None:
    postgres.sql(
        """
        INSERT INTO stock_condition_display_basis VALUES
          ('stock:SH:600000','20260722','20260723','stock-old'),
          ('stock:SH:600001','20260723','20260724','stock-current'),
          ('stock:SH:600002','20260723','20260724','stock-current');
        INSERT INTO index_condition_display_basis VALUES
          ('index:SH:000300','20260721','20260723','index-old'),
          ('index:SH:000016','20260723','20260724','index-current');
        INSERT INTO board_condition_display_basis VALUES
          ('board:TDX:881001','20260720','20260723','board-old'),
          ('board:TDX:881002','20260722','20260724','board-current');
        """
    )


def _function_acl_and_attributes(postgres: object) -> str:
    return postgres.scalar(
        """
        SELECT md5(string_agg(
          procedure.oid::regprocedure::text || '|' ||
          pg_get_userbyid(procedure.proowner) || '|' ||
          procedure.prosecdef::text || '|' ||
          procedure.provolatile::text || '|' ||
          COALESCE(procedure.proconfig::text, '') || '|' ||
          COALESCE(procedure.proacl::text, ''),
          E'\\n' ORDER BY procedure.oid::regprocedure::text
        ))
        FROM pg_proc procedure
        JOIN pg_namespace namespace
          ON namespace.oid = procedure.pronamespace
        WHERE namespace.nspname = 'public'
          AND procedure.oid::regprocedure::text = ANY(ARRAY[
            'n6_strategy_default_selection_on_principal_insert()',
            'n6_btrack_strategy_center_state(text)',
            'n6_btrack_strategy_selection_put(text,text[],bigint,text)',
            'n6_strategy_center_compensate_revision_v1('
              'bigint,text,bigint,bigint,bigint,text,bigint,date,text)',
            'n6_strategy_center_abandon_pending_v2('
              'bigint,text,bigint,bigint,bigint,date,text)'
          ]);
        """
    )


class StrategyCenterN6TradeDateAuthority084StaticTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.migration = MIGRATION.read_text(encoding="utf-8")
        cls.rollback = ROLLBACK.read_text(encoding="utf-8")

    def test_forward_is_additive_fail_closed_and_n6_only(self) -> None:
        for required in (
            "n6_strategy_center_trade_date_authority_v1",
            "v_n6_stock_condition_display_basis",
            "v_n6_index_condition_display_basis",
            "v_n6_board_condition_display_basis",
            "count(DISTINCT batch.for_trade_date) = 1",
            "batch.source_trade_date <= batch.for_trade_date",
            "REVOKE SELECT ON TABLE public.common_trade_calendar",
            "084 function rewrite failed",
            "084 worker ACL postflight failed",
        ):
            self.assertIn(required, self.migration)
        for forbidden in (
            "common_condition_run",
            "FROM public.stock_condition_display_basis",
            "FROM public.index_condition_display_basis",
            "FROM public.board_condition_display_basis",
            "common_action",
            "common_trigger",
            "public.n6_virtual_proposal",
            "public.n6_virtual_order",
            "public.n6_virtual_trade",
            "public.n6_virtual_position",
            "public.n6_virtual_cash",
        ):
            self.assertNotIn(forbidden, self.migration)

    def test_rollback_is_dependency_guarded(self) -> None:
        for required in (
            "084 rollback blocked by N6 authority dependencies",
            "revision.effective_trade_date >= authority_trade_date",
            "n6_strategy_match_projection",
            "n6_strategy_observation_projection",
            "n6_strategy_match_change",
            "GRANT SELECT ON TABLE public.common_trade_calendar",
        ):
            self.assertIn(required, self.rollback)

    def test_runtime_python_has_no_calendar_or_raw_layer_dependency(
        self,
    ) -> None:
        sources = (
            ROOT / "src/ashare_v3/user/strategy_center_worker.py",
            ROOT / "scripts/run_n6_strategy_center_auto_once.py",
        )
        for source in sources:
            text = source.read_text(encoding="utf-8")
            for forbidden in (
                "common_trade_calendar",
                "FROM stock_condition_display_basis",
                "FROM index_condition_display_basis",
                "FROM board_condition_display_basis",
                "common_action",
                "common_trigger",
            ):
                self.assertNotIn(forbidden, text)


class StrategyCenterN6TradeDateAuthority084PostgresTest(
    unittest.TestCase
):
    def test_forward_selects_latest_consensus_and_preserves_function_acl(
        self,
    ) -> None:
        with _temporary_postgres() as postgres:
            _prepare(postgres)
            _insert_complete_authority(postgres)
            attributes_before = _function_acl_and_attributes(postgres)

            forward = postgres.file(MIGRATION, check=False)
            self.assertEqual(forward.returncode, 0, forward.stderr)

            authority = json.loads(
                postgres.scalar(
                    "SELECT "
                    "n6_strategy_center_trade_date_authority_v1()::text;"
                )
            )
            installation = json.loads(
                postgres.scalar(
                    "SELECT obj_description("
                    "'n6_strategy_center_trade_date_authority_v1()'"
                    "::regprocedure,'pg_proc');"
                )
            )
            self.assertEqual(authority["for_trade_date"], "20260724")
            self.assertEqual(
                installation,
                {
                    "migration_id":
                        "084_n6_strategy_center_n6_trade_date_authority_v1",
                    "installed_authority": authority,
                },
            )
            self.assertEqual(
                [
                    (
                        item["asset_kind"],
                        item["source_trade_date"],
                        item["source_run_id"],
                        item["row_count"],
                    )
                    for item in authority["batches"]
                ],
                [
                    ("stock", "20260723", "stock-current", 2),
                    ("index", "20260723", "index-current", 1),
                    ("board", "20260722", "board-current", 1),
                ],
            )
            self.assertEqual(
                _function_acl_and_attributes(postgres),
                attributes_before,
            )
            for signature in FUNCTION_SIGNATURES:
                definition = postgres.scalar(
                    "SELECT pg_get_functiondef("
                    f"'public.{signature}'::regprocedure);"
                )
                self.assertIn(
                    "n6_strategy_center_trade_date_authority_v1",
                    definition,
                )
                self.assertNotIn("common_trade_calendar", definition)
            self.assertEqual(
                postgres.scalar(
                    """
                    SELECT concat_ws('|',
                      has_table_privilege(
                        'n6_strategy_worker',
                        'common_trade_calendar', 'SELECT'
                      ),
                      has_table_privilege(
                        'n6_strategy_worker',
                        'v_n6_stock_condition_display_basis', 'SELECT'
                      ),
                      has_table_privilege(
                        'n6_strategy_worker',
                        'v_n6_index_condition_display_basis', 'SELECT'
                      ),
                      has_table_privilege(
                        'n6_strategy_worker',
                        'v_n6_board_condition_display_basis', 'SELECT'
                      ),
                      has_function_privilege(
                        'n6_strategy_worker',
                        'n6_strategy_center_trade_date_authority_v1()',
                        'EXECUTE'
                      ),
                      EXISTS (
                        SELECT 1
                        FROM pg_proc procedure,
                             LATERAL aclexplode(
                               COALESCE(
                                 procedure.proacl,
                                 acldefault('f', procedure.proowner)
                               )
                             ) privilege
                        WHERE procedure.oid =
                              'n6_strategy_center_trade_date_authority_v1()'
                                ::regprocedure
                          AND privilege.grantee = 0
                          AND privilege.privilege_type = 'EXECUTE'
                      )
                    );
                    """
                ),
                "f|t|t|t|f|f",
            )

    def test_rewritten_functions_use_reviewed_authority_at_runtime(
        self,
    ) -> None:
        with _temporary_postgres() as postgres:
            _prepare(postgres)
            _insert_complete_authority(postgres)
            forward = postgres.file(MIGRATION, check=False)
            self.assertEqual(forward.returncode, 0, forward.stderr)
            postgres.sql(
                """
                TRUNCATE common_trade_calendar;
                INSERT INTO common_trade_calendar VALUES ('20260725', true);
                CREATE TRIGGER n6_principal_default_strategy_selection_084
                AFTER INSERT ON n6_principal
                FOR EACH ROW EXECUTE FUNCTION
                  n6_strategy_default_selection_on_principal_insert();
                CREATE OR REPLACE FUNCTION n6_btrack_resolve_authority(text)
                RETURNS jsonb LANGUAGE sql STABLE AS $$
                  SELECT CASE WHEN $1 = 'n6-session-token' THEN
                    jsonb_build_object(
                      'principal_id', 1,
                      'principal_type', 'human_user',
                      'user_id', 1
                    )
                  END
                $$;
                INSERT INTO user_account VALUES (1, 'active');
                INSERT INTO n6_principal VALUES (
                  1, 'human_user', 1, 'active'
                );
                """
            )
            self.assertEqual(
                postgres.scalar(
                    """
                    SELECT effective_trade_date::text
                    FROM n6_user_strategy_selection_revision
                    WHERE principal_id = 1 AND user_id = 1;
                    """
                ),
                "2026-07-24",
            )
            web_state = postgres.sql(
                "SELECT n6_btrack_strategy_center_state("
                "'n6-session-token')->>'trade_date';",
                user="n6_btrack_web",
                check=False,
            )
            self.assertEqual(web_state.returncode, 0, web_state.stderr)
            self.assertIn("2026-07-24", web_state.stdout)
            direct_helper = postgres.sql(
                "SELECT n6_strategy_center_trade_date_authority_v1();",
                user="n6_btrack_web",
                check=False,
            )
            self.assertNotEqual(direct_helper.returncode, 0)
            self.assertIn("permission denied", direct_helper.stderr)

            _insert_active_v1_pending_v2(postgres, user_id=2)
            active_revision_id = _revision_id(
                postgres, user_id=2, revision_no=1
            )
            pending_revision_id = _revision_id(
                postgres, user_id=2, revision_no=2
            )
            abandon = postgres.sql(
                "SELECT n6_strategy_center_abandon_pending_v2("
                f"2,'human_user',2,{pending_revision_id},"
                f"{active_revision_id},DATE '2026-07-24',"
                "'abandon-v2-user-2-reviewed-authority');",
                check=False,
            )
            self.assertEqual(abandon.returncode, 0, abandon.stderr)
            self.assertEqual(
                postgres.scalar(
                    """
                    SELECT selection_status
                    FROM n6_user_strategy_selection_revision
                    WHERE selection_revision_id =
                    """
                    + str(pending_revision_id)
                    + ";"
                ),
                "abandoned",
            )

    def test_forward_failure_is_atomic_for_missing_or_mixed_authority(
        self,
    ) -> None:
        for fault in (
            "missing_board",
            "mixed_stock",
            "dashed_stock_date",
            "impossible_stock_source_date",
            "impossible_stock_for_trade_date",
            "future_stock_source_date",
            "mismatched_board_date",
            "empty_index_run_id",
        ):
            with self.subTest(fault=fault), _temporary_postgres() as postgres:
                _prepare(postgres)
                _insert_complete_authority(postgres)
                if fault == "missing_board":
                    postgres.sql(
                        "TRUNCATE board_condition_display_basis;"
                    )
                elif fault == "mixed_stock":
                    postgres.sql(
                        """
                        INSERT INTO stock_condition_display_basis VALUES (
                          'stock:SH:600003','20260723','20260724',
                          'stock-conflict'
                        );
                        """
                    )
                elif fault == "dashed_stock_date":
                    postgres.sql(
                        """
                        TRUNCATE stock_condition_display_basis;
                        INSERT INTO stock_condition_display_basis VALUES (
                          'stock:SH:600003','2026-07-23','2026-07-24',
                          'stock-dashed'
                        );
                        """
                    )
                elif fault == "impossible_stock_source_date":
                    postgres.sql(
                        """
                        UPDATE stock_condition_display_basis
                        SET source_trade_date = '20260231'
                        WHERE run_id = 'stock-current';
                        """
                    )
                elif fault == "impossible_stock_for_trade_date":
                    postgres.sql(
                        """
                        TRUNCATE stock_condition_display_basis;
                        INSERT INTO stock_condition_display_basis VALUES (
                          'stock:SH:600003','20260228','20260231',
                          'stock-impossible'
                        );
                        """
                    )
                elif fault == "future_stock_source_date":
                    postgres.sql(
                        """
                        UPDATE stock_condition_display_basis
                        SET source_trade_date = '20260725'
                        WHERE run_id = 'stock-current';
                        """
                    )
                elif fault == "mismatched_board_date":
                    postgres.sql(
                        """
                        UPDATE board_condition_display_basis
                        SET for_trade_date = '20260725'
                        WHERE run_id = 'board-current';
                        """
                    )
                elif fault == "empty_index_run_id":
                    postgres.sql(
                        """
                        UPDATE index_condition_display_basis
                        SET run_id = ''
                        WHERE run_id = 'index-current';
                        """
                    )
                before = _function_acl_and_attributes(postgres)
                result = postgres.file(MIGRATION, check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(
                    "n6_strategy_center_trade_date_authority_invalid",
                    result.stderr,
                )
                self.assertEqual(
                    postgres.scalar(
                        "SELECT to_regprocedure("
                        "'n6_strategy_center_trade_date_authority_v1()'"
                        ") IS NULL;"
                    ),
                    "t",
                )
                self.assertEqual(
                    _function_acl_and_attributes(postgres),
                    before,
                )
                self.assertEqual(
                    postgres.scalar(
                        "SELECT has_table_privilege("
                        "'n6_strategy_worker','common_trade_calendar',"
                        "'SELECT');"
                    ),
                    "t",
                )

    def test_safe_rollback_restores_functions_and_calendar_acl(self) -> None:
        with _temporary_postgres() as postgres:
            _prepare(postgres)
            _insert_complete_authority(postgres)
            attributes_before = _function_acl_and_attributes(postgres)
            forward = postgres.file(MIGRATION, check=False)
            self.assertEqual(forward.returncode, 0, forward.stderr)

            rollback = postgres.file(ROLLBACK, check=False)
            self.assertEqual(rollback.returncode, 0, rollback.stderr)
            self.assertEqual(
                postgres.scalar(
                    "SELECT to_regprocedure("
                    "'n6_strategy_center_trade_date_authority_v1()'"
                    ") IS NULL;"
                ),
                "t",
            )
            self.assertEqual(
                _function_acl_and_attributes(postgres),
                attributes_before,
            )
            for signature in FUNCTION_SIGNATURES:
                definition = postgres.scalar(
                    "SELECT pg_get_functiondef("
                    f"'public.{signature}'::regprocedure);"
                )
                self.assertIn("common_trade_calendar", definition)
                self.assertNotIn(
                    "n6_strategy_center_trade_date_authority_v1",
                    definition,
                )
            self.assertEqual(
                postgres.scalar(
                    "SELECT has_table_privilege("
                    "'n6_strategy_worker','common_trade_calendar',"
                    "'SELECT');"
                ),
                "t",
            )

    def test_rollback_uses_installation_date_after_authority_advances(
        self,
    ) -> None:
        with _temporary_postgres() as postgres:
            _prepare(postgres)
            _insert_complete_authority(postgres)
            forward = postgres.file(MIGRATION, check=False)
            self.assertEqual(forward.returncode, 0, forward.stderr)
            postgres.sql(
                """
                INSERT INTO user_account VALUES (1, 'active');
                INSERT INTO n6_user_strategy_selection_revision (
                  principal_id, principal_type, user_id, revision_no,
                  selection_status, replay_status, request_id,
                  effective_trade_date, selection_policy_hash,
                  created_by_user_id
                ) VALUES (
                  1, 'human_user', 1, 1, 'pending', 'pending',
                  'pending-v2-after-084', DATE '2026-07-24',
                  repeat('a', 64), 1
                );
                INSERT INTO stock_condition_display_basis VALUES (
                  'stock:SH:600004','20260724','20260725',
                  'stock-next'
                );
                INSERT INTO index_condition_display_basis VALUES (
                  'index:SH:000300','20260724','20260725',
                  'index-next'
                );
                INSERT INTO board_condition_display_basis VALUES (
                  'board:TDX:881004','20260724','20260725',
                  'board-next'
                );
                """
            )
            self.assertEqual(
                json.loads(
                    postgres.scalar(
                        "SELECT "
                        "n6_strategy_center_trade_date_authority_v1()::text;"
                    )
                )["for_trade_date"],
                "20260725",
            )
            rollback = postgres.file(ROLLBACK, check=False)
            self.assertNotEqual(rollback.returncode, 0)
            self.assertIn(
                "084 rollback blocked by N6 authority dependencies",
                rollback.stderr,
            )
            self.assertEqual(
                postgres.scalar(
                    "SELECT to_regprocedure("
                    "'n6_strategy_center_trade_date_authority_v1()'"
                    ") IS NOT NULL;"
                ),
                "t",
            )
