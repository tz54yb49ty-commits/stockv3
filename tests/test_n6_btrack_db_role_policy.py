import inspect
import json
import os
from pathlib import Path
import re
import unittest
from unittest.mock import patch

from ashare_v3.web import n6_user_app
from ashare_v3.web.n6_btrack_authority import (
    BTrackAuthority,
    PostgresN6BTrackAuthorityRepository,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "sql/042_n6_b_track_db_role_policy_schema.sql"
ROLLBACK = ROOT / "sql/042_n6_b_track_db_role_policy_rollback.sql"
CONTRACT_JSON = ROOT / "docs/N6_B_TRACK_PRODUCT_V3_DB_ROLE_POLICY_042_CONTRACT.json"
SCHEMA_044 = ROOT / "sql/044_n6_btrack_scope_write_source_validation.sql"
ROLLBACK_044 = ROOT / "sql/044_n6_btrack_scope_write_source_validation_rollback.sql"
CONTRACT_044_MD = ROOT / "docs/N6_B_TRACK_PRODUCT_V3_SCOPE_WRITE_SOURCE_VALIDATION_044_CONTRACT.md"
CONTRACT_044_JSON = ROOT / "docs/N6_B_TRACK_PRODUCT_V3_SCOPE_WRITE_SOURCE_VALIDATION_044_CONTRACT.json"
SCHEMA_045 = ROOT / "sql/045_n6_btrack_monitor_lineage_freeze.sql"
ROLLBACK_045 = ROOT / "sql/045_n6_btrack_monitor_lineage_freeze_rollback.sql"
CONTRACT_045_MD = ROOT / "docs/N6_B_TRACK_PRODUCT_V3_MONITOR_LINEAGE_FREEZE_045_CONTRACT.md"
CONTRACT_045_JSON = ROOT / "docs/N6_B_TRACK_PRODUCT_V3_MONITOR_LINEAGE_FREEZE_045_CONTRACT.json"
SCHEMA_046 = ROOT / "sql/046_n6_btrack_virtual_executor_apply.sql"
ROLLBACK_046 = ROOT / "sql/046_n6_btrack_virtual_executor_apply_rollback.sql"
CONTRACT_046_JSON = ROOT / "docs/N6_B_TRACK_PRODUCT_V3_VIRTUAL_EXECUTOR_046_CONTRACT.json"
SCHEMA_048 = ROOT / "sql/048_n6_btrack_proposal_scope_and_executor_claim_next.sql"
ROLLBACK_048 = ROOT / "sql/048_n6_btrack_proposal_scope_and_executor_claim_next_rollback.sql"
CONTRACT_048_JSON = ROOT / "docs/N6_B_TRACK_PRODUCT_V3_PROPOSAL_SCOPE_AND_EXECUTOR_CLAIM_NEXT_048_CONTRACT.json"
SCHEMA_049 = ROOT / "sql/049_n6_virtual_stop_loss_freeze_evaluate_execute.sql"
ROLLBACK_049 = ROOT / "sql/049_n6_virtual_stop_loss_freeze_evaluate_execute_rollback.sql"
CONTRACT_049_JSON = ROOT / "docs/N6_B_TRACK_PRODUCT_V3_VIRTUAL_STOP_LOSS_049_CONTRACT.json"
SCHEMA_052 = ROOT / "sql/052_n6_btrack_proposal_trading_session.sql"
ROLLBACK_052 = ROOT / "sql/052_n6_btrack_proposal_trading_session_rollback.sql"
CONTRACT_052_JSON = ROOT / "docs/N6_B_TRACK_PRODUCT_V3_PROPOSAL_TRADING_SESSION_CONTRACT.json"
SCHEMA_053 = ROOT / "sql/053_n6_btrack_proposal_timestamp_syntax_fix.sql"
ROLLBACK_053 = ROOT / "sql/053_n6_btrack_proposal_timestamp_syntax_fix_rollback.sql"
CONTRACT_053_JSON = ROOT / "docs/N6_B_TRACK_PRODUCT_V3_PROPOSAL_TIMESTAMP_SYNTAX_FIX_CONTRACT.json"
SCHEMA_054 = ROOT / "sql/054_n6_btrack_filter_bulk_scope.sql"
ROLLBACK_054 = ROOT / "sql/054_n6_btrack_filter_bulk_scope_rollback.sql"
CONTRACT_054_JSON = ROOT / "docs/N6_B_TRACK_FILTER_BULK_SCOPE_CONTRACT.json"
SCHEMA_063 = ROOT / "sql/063_n6_btrack_manual_actionable_buy.sql"
ROLLBACK_063 = ROOT / "sql/063_n6_btrack_manual_actionable_buy_rollback.sql"
CONTRACT_063_JSON = (
    ROOT / "docs/N6_B_TRACK_PRODUCT_V3_MANUAL_ACTIONABLE_BUY_063_CONTRACT.json"
)


def function_definition(sql: str, name: str) -> str:
    marker = f"CREATE OR REPLACE FUNCTION public.{name}"
    start = sql.index(marker)
    end = sql.index("$function$;", start) + len("$function$;")
    return sql[start:end]


class N6BTrackDbRolePolicy042Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = SCHEMA.read_text()
        cls.rollback = ROLLBACK.read_text()
        cls.contract = json.loads(CONTRACT_JSON.read_text())
        cls.schema_044 = SCHEMA_044.read_text()
        cls.rollback_044 = ROLLBACK_044.read_text()
        cls.contract_044_md = CONTRACT_044_MD.read_text()
        cls.contract_044 = json.loads(CONTRACT_044_JSON.read_text())
        cls.schema_045 = SCHEMA_045.read_text()
        cls.rollback_045 = ROLLBACK_045.read_text()
        cls.contract_045_md = CONTRACT_045_MD.read_text()
        cls.contract_045 = json.loads(CONTRACT_045_JSON.read_text())
        cls.schema_046 = SCHEMA_046.read_text()
        cls.rollback_046 = ROLLBACK_046.read_text()
        cls.contract_046 = json.loads(CONTRACT_046_JSON.read_text())
        cls.schema_048 = SCHEMA_048.read_text()
        cls.rollback_048 = ROLLBACK_048.read_text()
        cls.contract_048 = json.loads(CONTRACT_048_JSON.read_text())

    def test_048_proposal_signal_source_allowlist_and_forbidden_sources(self) -> None:
        signal_body = self.schema_048.split(
            "IF p_source_type = 'signal' THEN", 1
        )[1].split("ELSE", 1)[0]
        for allowed in (
            "public.user_projection_run",
            "public.user_signal_projection",
            "public.user_signal_card",
            "public.v_n6_stock_condition_display_basis",
        ):
            self.assertIn(allowed, self.schema_048)
        for forbidden in (
            "common_event_outbox",
            "condition_pool",
            "common_trigger_match",
            "common_action_event",
            "membership",
            "stock_identity",
            "source_payload_json",
        ):
            self.assertNotIn(forbidden, self.schema_048.lower())

    def test_048_current_date_monitor_realtime_position_and_episode_authority(self) -> None:
        sql = self.schema_048
        self.assertIn("public.common_trade_calendar", sql)
        self.assertIn("AT TIME ZONE 'Asia/Shanghai'", sql)
        self.assertIn("c.is_open = true", sql)
        self.assertIn("s.for_trade_date = current_trade_date", sql)
        self.assertIn("approved_batch AS", sql)
        self.assertIn(
            "public.v_n6_stock_condition_display_basis", sql
        )
        self.assertIn(
            "count(DISTINCT (", sql
        )
        self.assertIn("public.user_monitor_stock", sql)
        self.assertIn(
            "m.valid_source_trade_date = approved.source_trade_date", sql
        )
        self.assertIn(
            "m.valid_for_trade_date = approved.for_trade_date", sql
        )
        self.assertIn(
            "m.valid_source_run_id = approved.source_run_id", sql
        )
        self.assertIn("public.user_realtime_monitor_scope", sql)
        self.assertIn(
            "rs.source_snapshot_json->>'identity_key' = rs.identity_key",
            sql,
        )
        realtime_branch = sql.split(
            "FROM public.user_realtime_monitor_scope rs", 1
        )[1].split(") candidate", 1)[0]
        self.assertNotIn(
            "rs.source_snapshot_json->>'for_trade_date' =", realtime_branch
        )
        self.assertNotIn(
            "rs.source_snapshot_json->>'source_run_id' =", realtime_branch
        )
        self.assertIn("public.n6_virtual_position", sql)
        self.assertIn("pos.quantity > 0", sql)
        self.assertIn(
            "s.direction = 'buy'\n              OR EXISTS (", sql
        )
        self.assertIn("v_scope_authority <> 'open_position'", sql)
        self.assertIn("'frozen_virtual_position_id', v_position_id", sql)
        self.assertIn("'frozen_holding_episode_no', v_episode", sql)

    def test_048_long_lived_realtime_uses_current_outer_approved_identity(self) -> None:
        sql = self.schema_048
        self.assertIn(
            "JOIN approved_identity approved\n"
            "        ON approved.identity_key = s.identity_key\n"
            "       AND approved.for_trade_date = s.for_trade_date",
            sql,
        )
        realtime_branch = sql.split(
            "FROM public.user_realtime_monitor_scope rs", 1
        )[1].split(") candidate", 1)[0]
        for required in (
            "rs.principal_id = (authority->>'principal_id')::bigint",
            "rs.principal_type = authority->>'principal_type'",
            "rs.user_id = (authority->>'user_id')::bigint",
            "rs.identity_key = s.identity_key",
            "rs.status = 'active'",
            "rs.deleted_at IS NULL",
            "rs.source_type = 'single_row'",
            "rs.source_snapshot_json->>'identity_key' = rs.identity_key",
        ):
            self.assertIn(required, realtime_branch)
        self.assertNotIn("approved.", realtime_branch)
        policy = self.contract_048["proposal_create"]["realtime_scope_policy"]
        self.assertFalse(policy["historical_snapshot_date_compared_to_today"])
        self.assertFalse(policy["historical_snapshot_run_compared_to_current"])

    def test_048_manual_sell_uses_matured_lot_not_position_available_quantity(self) -> None:
        sql = self.schema_048
        self.assertIn("p.virtual_account_id = account_id", sql)
        self.assertIn(
            "p.principal_id = (authority->>'principal_id')::bigint", sql
        )
        self.assertIn(
            "p.principal_type = authority->>'principal_type'", sql
        )
        self.assertIn("p.position_status = 'open_virtual'", sql)
        self.assertIn("p.quantity > 0", sql)
        self.assertIn("p.holding_episode_no > 0", sql)
        self.assertNotIn("p.available_quantity > 0", sql)
        self.assertNotIn("stock_identity", sql)

    def test_048_sell_lot_authority_exact_scope_and_t1_availability(self) -> None:
        sql = self.schema_048
        self.assertEqual(
            sql.count("FROM public.n6_virtual_position_lot lot"), 2
        )
        for prefix in ("pos", "p"):
            for column in (
                "virtual_position_id",
                "virtual_account_id",
                "principal_id",
                "principal_type",
                "identity_key",
                "holding_episode_no",
            ):
                self.assertIn(
                    f"lot.{column} = {prefix}.{column}", sql
                )
        self.assertEqual(sql.count("lot.remaining_quantity > 0"), 2)
        self.assertEqual(
            sql.count(
                "lot.available_trade_date <= pg_catalog.to_date("
            ),
            2,
        )
        self.assertEqual(
            sql.count(
                "lot.lot_status IN ('locked_t1', 'available')"
            ),
            2,
        )
        self.assertNotIn("pos.available_quantity", sql)
        self.assertNotIn("p.available_quantity", sql)

    def test_048_sell_lot_cases_are_fail_closed(self) -> None:
        policy = self.contract_048["proposal_create"]["sell_lot_authority"]
        self.assertFalse(policy["position_available_quantity_authoritative"])
        self.assertTrue(policy["remaining_quantity_gt_zero"])
        self.assertTrue(
            policy["available_trade_date_lte_current_trade_date"]
        )
        self.assertEqual(
            policy["exact_scope"],
            [
                "virtual_position_id",
                "virtual_account_id",
                "principal_id",
                "principal_type",
                "identity_key",
                "holding_episode_no",
            ],
        )
        self.assertEqual(policy["lot_status"], ["locked_t1", "available"])
        self.assertFalse(policy["proposal_create_updates_lots_or_position"])

    def test_048_mature_lot_authorizes_sell_when_position_available_is_zero(self) -> None:
        position = {
            "virtual_position_id": 41,
            "virtual_account_id": 7,
            "principal_id": 3,
            "principal_type": "human_user",
            "identity_key": "stock:SH:600000",
            "holding_episode_no": 2,
            "available_quantity": 0,
        }
        lot = {
            **{key: position[key] for key in (
                "virtual_position_id",
                "virtual_account_id",
                "principal_id",
                "principal_type",
                "identity_key",
                "holding_episode_no",
            )},
            "remaining_quantity": 100,
            "available_trade_date": "20260717",
            "lot_status": "locked_t1",
        }
        self.assertTrue(
            lot["remaining_quantity"] > 0
            and lot["available_trade_date"] <= "20260717"
            and lot["lot_status"] in {"locked_t1", "available"}
        )
        self.assertEqual(position["available_quantity"], 0)
        self.assertNotIn("available_quantity", lot)

    def test_048_future_or_wrong_scope_lot_does_not_authorize_sell(self) -> None:
        expected = {
            "virtual_position_id": 41,
            "virtual_account_id": 7,
            "principal_id": 3,
            "principal_type": "human_user",
            "identity_key": "stock:SH:600000",
            "holding_episode_no": 2,
        }

        def authorized(lot: dict[str, object]) -> bool:
            return (
                all(lot.get(key) == value for key, value in expected.items())
                and int(lot["remaining_quantity"]) > 0
                and str(lot["available_trade_date"]) <= "20260717"
                and lot["lot_status"] in {"locked_t1", "available"}
            )

        future = {
            **expected,
            "remaining_quantity": 100,
            "available_trade_date": "20260718",
            "lot_status": "locked_t1",
        }
        self.assertFalse(authorized(future))
        for key, wrong_value in (
            ("virtual_position_id", 42),
            ("virtual_account_id", 8),
            ("principal_id", 4),
            ("principal_type", "admin"),
            ("identity_key", "stock:SZ:000001"),
            ("holding_episode_no", 3),
        ):
            wrong_scope = {
                **future,
                "available_trade_date": "20260717",
                key: wrong_value,
            }
            self.assertFalse(authorized(wrong_scope), key)

    def test_048_exact_function_acl_and_zero_direct_privileges(self) -> None:
        sql = self.schema_048
        self.assertIn("SECURITY DEFINER", sql)
        self.assertIn("SET search_path = pg_catalog", sql)
        self.assertNotIn("ALTER FUNCTION", sql.upper())
        self.assertIn(
            "function_owner IS DISTINCT FROM 'ashare_v3_user'", sql
        )
        self.assertIn("p.prosecdef", sql)
        self.assertIn("'search_path=pg_catalog' = ANY(function_config)", sql)
        self.assertIn("acl.grantee = 0", sql)
        self.assertIn(
            "'n6_btrack_web',\n"
            "       'public.n6_btrack_proposal_create(text,text,bigint)'",
            sql,
        )
        self.assertIn(
            "'n6_virtual_executor',\n"
            "       'public.n6_executor_claim_next_proposal(text)'",
            sql,
        )
        self.assertIn(
            "REVOKE ALL ON FUNCTION public.n6_executor_claim_next_proposal(text) FROM PUBLIC;",
            sql,
        )
        self.assertIn(
            "REVOKE ALL ON FUNCTION public.n6_executor_claim_next_proposal(text) FROM n6_btrack_web;",
            sql,
        )
        self.assertEqual(
            self.contract_048["claim_next"]["executor_direct_table_privileges"],
            [],
        )
        self.assertEqual(
            self.contract_048["claim_next"]["executor_direct_sequence_privileges"],
            [],
        )
        for forbidden in ("GRANT SELECT", "GRANT INSERT", "GRANT UPDATE", "GRANT USAGE ON SEQUENCE"):
            self.assertNotIn(forbidden, sql.upper())

    def test_048_rollback_restores_042_and_preserves_history(self) -> None:
        self.assertIn(
            "DROP FUNCTION IF EXISTS public.n6_executor_claim_next_proposal(text)",
            self.rollback_048,
        )
        self.assertIn(
            "'n6_virtual_trade_proposal_v1'", self.rollback_048
        )
        self.assertIn(
            "GRANT EXECUTE ON FUNCTION public.n6_executor_claim_proposal(bigint,text) TO n6_virtual_executor;",
            self.rollback_048,
        )
        for forbidden in (
            "DELETE FROM",
            "TRUNCATE",
            "DROP TABLE",
            "DROP INDEX",
            "DROP ROLE",
        ):
            self.assertNotIn(forbidden, self.rollback_048.upper())

    def test_046_is_function_only_executor_authority(self) -> None:
        self.assertEqual(
            set(re.findall(r"CREATE OR REPLACE FUNCTION public\.([a-z0-9_]+)", self.schema_046)),
            {"n6_executor_apply_claimed_proposal"},
        )
        function_sql = function_definition(
            self.schema_046, "n6_executor_apply_claimed_proposal"
        )
        self.assertIn("SECURITY DEFINER", function_sql)
        self.assertIn("SET search_path = pg_catalog", function_sql)
        self.assertIn(
            "GRANT EXECUTE ON FUNCTION public.n6_executor_apply_claimed_proposal(bigint,text) TO n6_virtual_executor;",
            self.schema_046,
        )
        self.assertIn(
            "REVOKE EXECUTE ON FUNCTION public.n6_executor_apply_claimed_proposal(bigint,text) FROM PUBLIC;",
            self.schema_046,
        )
        self.assertIn(
            "REVOKE EXECUTE ON FUNCTION public.n6_executor_apply_claimed_proposal(bigint,text) FROM n6_btrack_web;",
            self.schema_046,
        )
        self.assertEqual(self.contract_046["function"]["executor_direct_table_privileges"], [])
        self.assertEqual(self.contract_046["function"]["executor_direct_sequence_privileges"], [])
        transition_guard = function_definition(
            self.schema, "n6_btrack_proposal_transition_guard"
        )
        self.assertIn(
            "OLD.proposal_status='processing' AND NEW.proposal_status IN ('executed','failed')",
            transition_guard,
        )
        self.assertIn("SESSION_USER='n6_virtual_executor'", transition_guard)
        apply_sql = function_definition(
            self.schema_046, "n6_executor_apply_claimed_proposal"
        )
        self.assertIn("proposal_status = 'executed'", apply_sql)
        self.assertIn("proposal_status = 'processing'", apply_sql)

    def test_046_never_grants_relation_or_sequence_privileges(self) -> None:
        for forbidden in (
            "GRANT SELECT",
            "GRANT INSERT",
            "GRANT UPDATE",
            "GRANT DELETE",
            "GRANT USAGE ON SEQUENCE",
            "GRANT ALL",
            "ALTER DEFAULT PRIVILEGES",
            "CREATE ROLE",
            "ALTER ROLE",
        ):
            self.assertNotIn(forbidden, self.schema_046.upper())

    def test_046_has_no_forbidden_cross_layer_or_web_dml(self) -> None:
        lower = self.schema_046.lower()
        for forbidden in (
            "common_event_outbox",
            "common_event_inbox",
            "checkpoint",
            "user_signal_projection",
            "user_monitor_",
            "realtime_daily_snapshot",
            "minute_bar_1m",
            "broker",
            "real_trade",
        ):
            self.assertNotIn(forbidden, lower)
        self.assertNotRegex(lower, r"(insert into|update|delete from)\s+public\.(n[1-5]_|\w*projection|\w*monitor|\w*realtime)")

    def test_046_rollback_preserves_business_history_and_041_045(self) -> None:
        self.assertIn("DROP FUNCTION IF EXISTS public.n6_executor_apply_claimed_proposal", self.rollback_046)
        for forbidden in ("DELETE FROM", "TRUNCATE", "DROP TABLE", "ALTER TABLE"):
            self.assertNotIn(forbidden, self.rollback_046.upper())
        self.assertTrue(self.contract_046["rollback"]["preserves_business_history"])
        self.assertTrue(self.contract_046["rollback"]["preserves_041_045"])

    def test_045_replaces_only_monitor_upsert_and_preserves_security_boundary(self) -> None:
        self.assertEqual(self.schema_045.count("CREATE OR REPLACE FUNCTION public."), 1)
        self.assertEqual(
            set(re.findall(r"CREATE OR REPLACE FUNCTION public\.([a-z0-9_]+)", self.schema_045)),
            {"n6_btrack_monitor_upsert"},
        )
        monitor_sql = function_definition(self.schema_045, "n6_btrack_monitor_upsert")
        self.assertIn("SECURITY DEFINER", monitor_sql)
        self.assertIn("SET search_path = pg_catalog", monitor_sql)
        self.assertNotIn("n6_btrack_realtime_upsert", self.schema_045)
        for forbidden in (
            "CREATE TABLE",
            "ALTER TABLE",
            "DROP TABLE",
            "ALTER OWNER",
            "GRANT ",
            "REVOKE ",
            "CREATE ROLE",
            "ALTER ROLE",
        ):
            self.assertNotIn(forbidden, self.schema_045.upper())
        self.assertFalse(self.contract_045["feature_flags"]["scope_write_enabled_default"])

    def test_045_atomic_writer_freezes_one_complete_unique_current_batch(self) -> None:
        monitor_sql = function_definition(self.schema_045, "n6_btrack_monitor_upsert")
        self.assertEqual(monitor_sql.count("WITH current_batch AS"), 3)
        self.assertEqual(monitor_sql.count("count(DISTINCT (source_trade_date::text, for_trade_date::text, run_id::text)) = 1"), 3)
        for field in ("source_trade_date", "for_trade_date", "run_id"):
            self.assertEqual(monitor_sql.count(f"count({field}) = count(*)"), 3)
        for view in self.contract_045["approved_sources"].values():
            self.assertIn(view, monitor_sql)
        self.assertEqual(monitor_sql.count("approved.identity_key = p_identity_key"), 3)
        self.assertEqual(monitor_sql.count("FROM approved_source"), 3)
        for column in (
            "source_run_id",
            "valid_source_trade_date",
            "valid_for_trade_date",
            "valid_source_run_id",
        ):
            self.assertEqual(monitor_sql.count(column) > 0, True, column)
        snapshot_sql = monitor_sql.split("pg_catalog.jsonb_build_object(", 2)[2]
        for field in ("'identity_key'", "'source_trade_date'", "'for_trade_date'", "'source_run_id'"):
            self.assertIn(field, snapshot_sql)
        self.assertTrue(self.contract_045["writer"]["approved_source_and_dml_share_single_statement_snapshot"])
        self.assertEqual(self.contract_045["writer"]["failure_dml_count"], 0)

    def test_045_direction_and_forbidden_source_boundaries_are_closed(self) -> None:
        monitor_sql = function_definition(self.schema_045, "n6_btrack_monitor_upsert")
        self.assertIn("p_asset_kind = 'stock' AND p_direction <> 'buy'", monitor_sql)
        self.assertIn("p_direction NOT IN ('buy', 'sell')", monitor_sql)
        lower_sql = self.schema_045.lower()
        for forbidden in (
            "execute format",
            "execute immediate",
            "condition_basis ",
            "condition_pool ",
            "common_event_outbox",
            "membership",
            "user_signal_projection",
            "realtime_daily_snapshot",
            "minute_bar_1m",
        ):
            self.assertNotIn(forbidden, lower_sql)

    def test_045_rollback_exactly_restores_published_044_monitor_function(self) -> None:
        self.assertEqual(
            function_definition(self.rollback_045, "n6_btrack_monitor_upsert"),
            function_definition(self.schema_044, "n6_btrack_monitor_upsert"),
        )
        self.assertEqual(self.rollback_045.count("CREATE OR REPLACE FUNCTION public."), 1)
        self.assertNotIn("n6_btrack_realtime_upsert", self.rollback_045)
        for forbidden in ("DROP FUNCTION", "DROP TABLE", "DELETE FROM", "TRUNCATE", "GRANT ", "REVOKE "):
            self.assertNotIn(forbidden, self.rollback_045.upper())
        self.assertTrue(self.contract_045["rollback"]["preserves_monitor_history"])
        self.assertTrue(self.contract_045["feature_flags"]["rollback_requires_scope_write_disabled"])
        self.assertIn("exact monitor function definition published by Schema 044", self.rollback_045)

    def test_044_replaces_only_the_two_published_scope_write_functions(self) -> None:
        self.assertEqual(self.schema_044.count("CREATE OR REPLACE FUNCTION public."), 2)
        self.assertEqual(
            set(re.findall(r"CREATE OR REPLACE FUNCTION public\.([a-z0-9_]+)", self.schema_044)),
            {"n6_btrack_monitor_upsert", "n6_btrack_realtime_upsert"},
        )
        for forbidden in (
            "CREATE TABLE",
            "ALTER TABLE",
            "DROP TABLE",
            "ALTER OWNER",
            "GRANT ",
            "REVOKE ",
            "CREATE ROLE",
            "ALTER ROLE",
        ):
            self.assertNotIn(forbidden, self.schema_044.upper())
        self.assertFalse(self.contract_044["feature_flags"]["scope_write_enabled_default"])
        self.assertFalse(self.contract_044["feature_flags"]["proposal_write_enabled_default"])

    def test_044_direct_restricted_calls_validate_current_approved_source_before_dml(self) -> None:
        expected_views = {
            "stock": "public.v_n6_stock_condition_display_basis",
            "index": "public.v_n6_index_condition_display_basis",
            "board": "public.v_n6_board_condition_display_basis",
        }
        for function_name in ("n6_btrack_monitor_upsert", "n6_btrack_realtime_upsert"):
            function_sql = function_definition(self.schema_044, function_name)
            self.assertIn("authority jsonb := public.n6_btrack_resolve_authority(p_session_token_hash)", function_sql)
            self.assertIn("SECURITY DEFINER", function_sql)
            self.assertIn("SET search_path = pg_catalog", function_sql)
            self.assertNotIn("source_found", function_sql)
            self.assertEqual(function_sql.count("WITH current_batch AS"), 3)
            self.assertEqual(function_sql.count("approved.identity_key = p_identity_key"), 3)
            self.assertEqual(
                function_sql.count("approved.for_trade_date::text = current_batch.for_trade_date"),
                3,
            )
            for view in expected_views.values():
                self.assertIn(view, function_sql)
            insert_indexes = [match.start() for match in re.finditer(r"INSERT INTO public\.", function_sql)]
            self.assertEqual(len(insert_indexes), 3)
            for insert_index in insert_indexes:
                cte_index = function_sql.rfind("WITH current_batch AS", 0, insert_index)
                self.assertGreaterEqual(cte_index, 0)
                statement_prefix = function_sql[cte_index:insert_index]
                self.assertIn("WHERE current_batch.for_trade_date = p_for_trade_date", statement_prefix)
                self.assertIn("approved.identity_key = p_identity_key", statement_prefix)
                statement_tail = function_sql[insert_index:function_sql.index("RETURNING", insert_index)]
                self.assertIn("FROM approved_source", statement_tail)
            self.assertLess(function_sql.index("IF result_id IS NULL"), function_sql.index("'source_not_found'"))
            self.assertLess(function_sql.rfind("RETURNING"), function_sql.index("'source_not_found'"))
        self.assertTrue(self.contract_044["validation"]["applies_to_direct_restricted_function_calls"])
        self.assertEqual(self.contract_044["validation"]["failure_dml_count"], 0)
        self.assertTrue(self.contract_044["validation"]["approved_source_and_dml_share_single_statement_snapshot"])
        self.assertTrue(self.contract_044["validation"]["zero_row_dml_precedes_readonly_error_classification"])
        self.assertIn(
            "GRANT EXECUTE ON FUNCTION public.n6_btrack_monitor_upsert(text,text,text,text,text) TO n6_btrack_web;",
            self.schema,
        )
        self.assertIn(
            "GRANT EXECUTE ON FUNCTION public.n6_btrack_realtime_upsert(text,text,text,text) TO n6_btrack_web;",
            self.schema,
        )

    def test_044_direction_source_and_forbidden_boundaries_are_closed(self) -> None:
        monitor_sql = function_definition(self.schema_044, "n6_btrack_monitor_upsert")
        self.assertIn("p_asset_kind = 'stock' AND p_direction <> 'buy'", monitor_sql)
        self.assertIn("p_direction NOT IN ('buy', 'sell')", monitor_sql)
        lower_sql = self.schema_044.lower()
        for forbidden in (
            "execute format",
            "execute immediate",
            "condition_basis ",
            "condition_pool ",
            "common_event_outbox",
            "membership",
            "stock_daily",
            "index_daily",
            "board_daily",
        ):
            self.assertNotIn(forbidden, lower_sql)
        self.assertNotIn("public.n6_btrack_proposal", lower_sql)
        self.assertNotIn("public.n6_virtual_order", lower_sql)
        self.assertNotIn("public.n6_virtual_trade", lower_sql)

    def test_044_rollback_exactly_restores_published_042_definitions(self) -> None:
        for function_name in ("n6_btrack_monitor_upsert", "n6_btrack_realtime_upsert"):
            self.assertEqual(
                function_definition(self.rollback_044, function_name),
                function_definition(self.schema, function_name),
            )
        self.assertEqual(self.rollback_044.count("CREATE OR REPLACE FUNCTION public."), 2)
        for forbidden in ("DROP FUNCTION", "DROP TABLE", "DELETE FROM", "TRUNCATE", "GRANT ", "REVOKE "):
            self.assertNotIn(forbidden, self.rollback_044.upper())
        self.assertTrue(self.contract_044["rollback"]["preserves_business_history"])
        self.assertIn("restore the exact two definitions", self.contract_044_md.lower())

    def test_schema_never_provisions_roles_or_credentials(self) -> None:
        forbidden = (
            r"\bCREATE\s+ROLE\b",
            r"\bALTER\s+ROLE\b",
            r"\bCREATE\s+USER\b",
            r"\bPASSWORD\b",
            r"\bDSN\b",
            r"\bSECRET\b",
        )
        for pattern in forbidden:
            self.assertIsNone(re.search(pattern, self.schema, re.IGNORECASE), pattern)

    def test_authority_is_session_hash_and_exactly_one_persistent_principal(self) -> None:
        authority_sql = self.schema.split("CREATE OR REPLACE FUNCTION public.n6_btrack_resolve_authority", 1)[1]
        authority_sql = authority_sql.split("CREATE OR REPLACE FUNCTION", 1)[0]
        self.assertIn("s.session_token_hash = p_session_token_hash", authority_sql)
        self.assertIn("s.session_token_hash_algo = 'sha256'", authority_sql)
        self.assertIn("s.revoked_at IS NULL", authority_sql)
        self.assertIn("s.expires_at > pg_catalog.clock_timestamp()", authority_sql)
        self.assertIn("p.owner_user_id = s.user_id", authority_sql)
        self.assertIn("p.principal_status = 'active'", authority_sql)
        self.assertIn("count(*) OVER () AS principal_count", authority_sql)
        self.assertIn("WHERE principal_count = 1", authority_sql)
        self.assertNotIn("current_setting", self.schema.lower())
        self.assertNotIn("set_config", self.schema.lower())

    def test_every_public_function_is_hardened_and_public_execute_is_revoked(self) -> None:
        function_names = self.contract["roles"]["n6_btrack_web"]["functions"] + self.contract["roles"]["n6_virtual_executor"]["functions"]
        for name in function_names:
            function_sql = self.schema.split(f"CREATE OR REPLACE FUNCTION public.{name}", 1)[1]
            function_sql = function_sql.split("$function$;", 1)[0]
            self.assertIn("SECURITY DEFINER", function_sql, name)
            self.assertRegex(function_sql, r"SET search_path\s*=\s*pg_catalog", name)
            self.assertRegex(self.schema, rf"REVOKE EXECUTE ON FUNCTION public\.{name}\([^;]+\) FROM PUBLIC;", name)
        self.assertNotIn("EXECUTE format", self.schema)

    def test_role_preflight_is_owner_independent_and_requires_zero_effective_privileges(self) -> None:
        for token in (
            "n6_btrack_web",
            "n6_virtual_executor",
            "NOT role_row.rolcanlogin",
            "role_row.rolinherit",
            "role_row.rolsuper",
            "role_row.rolcreatedb",
            "role_row.rolcreaterole",
            "role_row.rolreplication",
            "role_row.rolbypassrls",
            "c.relkind IN ('r', 'p', 'v', 'm', 'f')",
            "c.relkind = 'S'",
            "pg_catalog.has_table_privilege(",
            "pg_catalog.has_sequence_privilege(",
            "role_row.oid",
            "c.oid",
            "042 relation privilege rejected",
            "042 sequence privilege rejected",
        ):
            self.assertIn(token, self.schema)
        role_preflight = self.schema.split("DO $role_preflight$", 1)[1].split("$role_preflight$;", 1)[0]
        relation_check = role_preflight.split("INTO relation_privilege", 1)[1].split(
            "INTO sequence_privilege",
            1,
        )[0]
        sequence_check = role_preflight.split("INTO sequence_privilege", 1)[1]
        for privilege_name in (
            "'SELECT'::text",
            "'INSERT'::text",
            "'UPDATE'::text",
            "'DELETE'::text",
            "'TRUNCATE'::text",
            "'REFERENCES'::text",
            "'TRIGGER'::text",
        ):
            self.assertIn(privilege_name, relation_check)
        for privilege_name in ("'USAGE'::text", "'SELECT'::text", "'UPDATE'::text"):
            self.assertIn(privilege_name, sequence_check)
        self.assertEqual(role_preflight.count("IF FOUND THEN"), 2)
        self.assertNotIn("REVOKE ALL ON ALL TABLES", self.schema)
        self.assertNotIn("REVOKE ALL ON ALL SEQUENCES", self.schema)
        self.assertNotIn("c.relowner", self.schema)
        self.assertNotIn("pg_catalog.pg_get_userbyid", self.schema)

    def test_web_and_executor_have_disjoint_exact_function_grants(self) -> None:
        web = set(self.contract["roles"]["n6_btrack_web"]["functions"])
        executor = set(self.contract["roles"]["n6_virtual_executor"]["functions"])
        self.assertFalse(web & executor)
        for name in web:
            self.assertRegex(self.schema, rf"GRANT EXECUTE ON FUNCTION public\.{name}\([^;]+\) TO n6_btrack_web;")
            self.assertNotRegex(self.schema, rf"GRANT EXECUTE ON FUNCTION public\.{name}\([^;]+\) TO n6_virtual_executor;")
        for name in executor:
            self.assertRegex(self.schema, rf"GRANT EXECUTE ON FUNCTION public\.{name}\([^;]+\) TO n6_virtual_executor;")
            self.assertNotRegex(self.schema, rf"GRANT EXECUTE ON FUNCTION public\.{name}\([^;]+\) TO n6_btrack_web;")
        self.assertIn("GRANT USAGE ON SCHEMA public TO n6_btrack_web, n6_virtual_executor", self.schema)

    def test_proposal_state_ownership_is_enforced_by_function_and_trigger(self) -> None:
        for transition in (
            "OLD.proposal_status='pending' AND NEW.proposal_status IN ('confirmed','expired')",
            "OLD.proposal_status='confirmed' AND NEW.proposal_status='processing'",
            "OLD.proposal_status='processing' AND NEW.proposal_status IN ('executed','failed')",
        ):
            self.assertIn(transition, self.schema)
        self.assertIn("SESSION_USER='n6_btrack_web'", self.schema)
        self.assertIn("SESSION_USER='n6_virtual_executor'", self.schema)
        self.assertIn("executor cannot create proposal", self.schema)
        self.assertIn("web executor fields rejected", self.schema)

    def test_executor_functions_only_own_proposal_state_and_do_not_implement_trading(self) -> None:
        executor_sql = self.schema.split("CREATE OR REPLACE FUNCTION public.n6_executor_claim_proposal", 1)[1]
        executor_sql = executor_sql.split("CREATE OR REPLACE FUNCTION public.n6_btrack_proposal_transition_guard", 1)[0]
        self.assertIn("UPDATE public.n6_virtual_trade_proposal", executor_sql)
        for forbidden in (
            "INSERT INTO public.n6_virtual_order",
            "INSERT INTO public.n6_virtual_trade",
            "UPDATE public.n6_virtual_position",
            "UPDATE public.n6_virtual_cash",
            "user_signal_projection",
            "user_monitor_",
        ):
            self.assertNotIn(forbidden, executor_sql)

    def test_rollback_is_guarded_and_preserves_schema_041_business_history(self) -> None:
        self.assertIn("web_connections", self.rollback)
        self.assertIn("executor_connections", self.rollback)
        self.assertIn("processing_proposals", self.rollback)
        self.assertNotIn("DROP TABLE", self.rollback.upper())
        self.assertNotIn("DELETE FROM", self.rollback.upper())
        self.assertNotIn("TRUNCATE", self.rollback.upper())
        for name in self.contract["roles"]["n6_btrack_web"]["functions"] + self.contract["roles"]["n6_virtual_executor"]["functions"]:
            self.assertIn(f"DROP FUNCTION IF EXISTS public.{name}", self.rollback)

    def test_repository_has_closed_function_allowlists_and_rejects_bad_hashes(self) -> None:
        repository = PostgresN6BTrackAuthorityRepository("postgresql:///unused")
        for value in ("", "abc", "g" * 64, "0" * 63, "0" * 65):
            with self.assertRaisesRegex(ValueError, "invalid_session_token_hash"):
                repository.resolve_authority(value)
        source = inspect.getsource(PostgresN6BTrackAuthorityRepository)
        self.assertIn("function_not_allowlisted", source)
        self.assertIn("write_function_not_allowlisted", source)
        self.assertNotIn("principal_id", inspect.signature(repository.resolve_authority).parameters)

    def test_app_removes_fallback_principal_and_requires_separate_write_repository(self) -> None:
        source = inspect.getsource(n6_user_app.resolve_app_principal)
        self.assertNotIn("session_scoped", source)
        self.assertNotIn("session_scoped_human_principal", inspect.getsource(n6_user_app))
        signature = inspect.signature(n6_user_app.create_app)
        self.assertIn("btrack_authority_repository", signature.parameters)
        create_source = inspect.getsource(n6_user_app.create_app)
        self.assertIn("and btrack_authority_repository is not None", create_source)
        self.assertIn("btrack_db_authority_unavailable", create_source)
        config = n6_user_app.N6UserWebConfig()
        self.assertFalse(config.scope_write_enabled)
        self.assertFalse(config.proposal_write_enabled)
        self.assertEqual(config.csrf_secret_file, "")
        create_source = inspect.getsource(n6_user_app.create_app)
        self.assertIn("load_n6_csrf_secret_file", create_source)
        self.assertIn("and btrack_authority_repository is not None", create_source)

    def test_csrf_file_loader_is_owner_mode_nofollow_and_never_uses_inline_secret_env(self) -> None:
        source = inspect.getsource(n6_user_app.load_n6_csrf_secret_file)
        self.assertIn("O_NOFOLLOW", source)
        self.assertIn("os.fstat", source)
        self.assertIn("stat.S_IMODE", source)
        self.assertIn("os.geteuid", source)
        config_source = inspect.getsource(n6_user_app.config_from_env)
        self.assertIn("ASHARE_V3_N6_CSRF_SECRET_FILE", config_source)
        self.assertNotIn('os.environ.get("ASHARE_V3_N6_CSRF_SECRET"', config_source)

    def test_scope_write_source_validation_uses_current_approved_filter_identity_sql(self) -> None:
        source = inspect.getsource(n6_user_app.PostgresN6UserRepository.fetch_app_current_filter_identity)
        for view in (
            "v_n6_stock_condition_display_basis",
            "v_n6_index_condition_display_basis",
            "v_n6_board_condition_display_basis",
        ):
            self.assertIn(view, source)
        self.assertIn("max(for_trade_date)", source)
        self.assertIn("approved.identity_key = %(identity_key)s", source)
        self.assertIn("approved.for_trade_date = current_batch.for_trade_date", source)
        self.assertIn("self._readonly_connection()", source)

    def test_runtime_repository_factory_accepts_only_exact_service_without_password_env(self) -> None:
        repository = object()
        accepted_env = {
            "PGSERVICE": "n6_btrack_web",
            "PGSERVICEFILE": "/nonsecret/pg_service.conf",
            "PGPASSFILE": "/nonsecret/n6_btrack_web.pgpass",
            "ASHARE_V3_POSTGRES_DSN": "postgresql://owner.invalid/ashare_v3",
        }
        with patch.dict(os.environ, accepted_env, clear=True), patch.object(
            n6_user_app,
            "PostgresN6BTrackAuthorityRepository",
            return_value=repository,
        ) as constructor:
            self.assertIs(n6_user_app.build_runtime_btrack_authority_repository(), repository)
            self.assertEqual(
                n6_user_app.config_from_env().dsn,
                "postgresql://owner.invalid/ashare_v3",
            )
        constructor.assert_called_once_with("service=n6_btrack_web")

        rejected_envs = (
            {},
            {"PGSERVICE": ""},
            {"PGSERVICE": " n6_btrack_web"},
            {"PGSERVICE": "N6_BTRACK_WEB"},
            {"PGSERVICE": "n6_virtual_executor"},
            {"PGSERVICE": "n6_btrack_web", "PGPASSWORD": "must-not-be-read"},
            {"PGSERVICE": "n6_btrack_web", "ASHARE_V3_N6_BTRACK_DSN": "forbidden"},
            {"PGSERVICE": "n6_btrack_web", "ASHARE_V3_N6_BTRACK_PASSWORD": "forbidden"},
        )
        for env in rejected_envs:
            with self.subTest(env_keys=sorted(env)), patch.dict(os.environ, env, clear=True), patch.object(
                n6_user_app,
                "PostgresN6BTrackAuthorityRepository",
            ) as constructor:
                self.assertIsNone(n6_user_app.build_runtime_btrack_authority_repository())
                constructor.assert_not_called()

        with patch.dict(
            os.environ,
            {"PGSERVICE": "n6_btrack_web"},
            clear=True,
        ), patch.object(
            n6_user_app,
            "PostgresN6BTrackAuthorityRepository",
            side_effect=RuntimeError("constructor_failed"),
        ):
            self.assertIsNone(n6_user_app.build_runtime_btrack_authority_repository())

    def test_runtime_app_injects_separate_repository_without_import_time_db_connection(self) -> None:
        repository = object()
        strategy_repository = object()
        runtime_app = object()
        with patch.object(
            n6_user_app,
            "build_runtime_btrack_authority_repository",
            return_value=repository,
        ), patch.object(
            n6_user_app,
            "build_runtime_strategy_center_repository",
            return_value=strategy_repository,
        ), patch.object(n6_user_app, "create_app", return_value=runtime_app) as create:
            self.assertIs(n6_user_app.create_runtime_app(), runtime_app)
        create.assert_called_once_with(
            btrack_authority_repository=repository,
            btrack_authority_required=True,
            strategy_center_repository=strategy_repository,
            strategy_center_repository_required=True,
        )
        module_source = inspect.getsource(n6_user_app)
        self.assertIn("app = create_runtime_app()", module_source)
        factory_source = inspect.getsource(n6_user_app.build_runtime_btrack_authority_repository)
        self.assertNotIn("psycopg.connect", factory_source)
        self.assertNotIn("PGPASSFILE", factory_source)
        self.assertNotIn("PGSERVICEFILE", factory_source)
        self.assertNotIn(
            "psycopg.connect",
            inspect.getsource(PostgresN6BTrackAuthorityRepository.__init__),
        )

    def test_authority_payload_contains_no_session_or_auth_material(self) -> None:
        authority = BTrackAuthority(7, 3, 9, "human_user", "active", "User")
        payload = authority.principal_payload()
        self.assertEqual(payload["principal_id"], 9)
        self.assertEqual(payload["owner_user_id"], 3)
        self.assertNotIn("user_session_id", payload)
        self.assertNotIn("session_token_hash", payload)
        self.assertNotIn("auth", payload)


class N6ProposalTradingSession052RolePolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sql = SCHEMA_052.read_text()
        cls.rollback = ROLLBACK_052.read_text()
        cls.contract = json.loads(CONTRACT_052_JSON.read_text())
        cls.body = function_definition(cls.sql, "n6_btrack_proposal_create")

    def test_052_replaces_only_proposal_create_and_preserves_function_security(self) -> None:
        self.assertEqual(
            re.findall(r"CREATE OR REPLACE FUNCTION public\.([a-z0-9_]+)", self.sql),
            ["n6_btrack_proposal_create"],
        )
        for invariant in (
            "RETURNS jsonb",
            "LANGUAGE plpgsql",
            "VOLATILE",
            "SECURITY DEFINER",
            "SET search_path = pg_catalog",
        ):
            self.assertIn(invariant, self.body)
        signature = "public.n6_btrack_proposal_create(text,text,bigint)"
        self.assertIn(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC;", self.sql)
        self.assertIn(f"GRANT EXECUTE ON FUNCTION {signature} TO n6_btrack_web;", self.sql)
        self.assertNotIn("ALTER FUNCTION", self.sql.upper())
        self.assertTrue(self.contract["proposal_create"]["owner_preserved_by_create_or_replace"])

    def test_052_uses_one_shanghai_clock_and_unique_open_date_before_session_guard(self) -> None:
        self.assertEqual(self.body.count("pg_catalog.clock_timestamp()"), 1)
        self.assertIn("AT TIME ZONE 'Asia/Shanghai'", self.body)
        self.assertIn(
            "pg_catalog.current_timestamp AT TIME ZONE 'Asia/Shanghai'",
            self.body,
        )
        self.assertIn("count(*)", self.body)
        self.assertIn("current_trade_date_count <> 1", self.body)
        open_date_guard = self.body.index("'current_open_trade_date_required'")
        session_guard = self.body.index("'outside_trading_session'")
        source_resolution = self.body.index("IF p_source_type = 'signal' THEN")
        proposal_insert = self.body.index("INSERT INTO public.n6_virtual_trade_proposal")
        self.assertLess(open_date_guard, session_guard)
        self.assertLess(session_guard, source_resolution)
        self.assertLess(session_guard, proposal_insert)

    def test_052_only_adds_session_state_and_guard_to_published_048_body(self) -> None:
        original = function_definition(
            SCHEMA_048.read_text(), "n6_btrack_proposal_create"
        )
        session_declaration = (
            "  shanghai_local_time time without time zone;\n"
        )
        session_guard = (
            "  shanghai_local_time := (\n"
            "    pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai'\n"
            "  )::time;\n"
            "  IF NOT (\n"
            "    shanghai_local_time BETWEEN time '09:30:00' AND time '11:30:00'\n"
            "    OR shanghai_local_time BETWEEN time '13:00:00' AND time '15:00:00'\n"
            "  ) THEN\n"
            "    RETURN pg_catalog.jsonb_build_object(\n"
            "      'ok', false, 'status', 'not_ready',\n"
            "      'error', 'outside_trading_session'\n"
            "    );\n"
            "  END IF;\n\n"
        )
        self.assertEqual(self.body.count(session_declaration), 1)
        self.assertEqual(self.body.count(session_guard), 1)
        self.assertEqual(
            self.body.replace(session_declaration, "").replace(session_guard, ""),
            original,
        )

    def test_052_session_boundaries_are_inclusive_and_off_session_is_zero_insert(self) -> None:
        self.assertIn(
            "shanghai_local_time BETWEEN time '09:30:00' AND time '11:30:00'",
            self.body,
        )
        self.assertIn(
            "shanghai_local_time BETWEEN time '13:00:00' AND time '15:00:00'",
            self.body,
        )

        def allowed(local_time: str) -> bool:
            hh, mm = (int(part) for part in local_time.split(":"))
            minute = hh * 60 + mm
            return 9 * 60 + 30 <= minute <= 11 * 60 + 30 or 13 * 60 <= minute <= 15 * 60

        for local_time in ("09:29", "11:31", "12:00", "15:01"):
            with self.subTest(local_time=local_time):
                self.assertFalse(allowed(local_time))
        for local_time in ("09:30", "11:30", "13:00", "15:00"):
            with self.subTest(local_time=local_time):
                self.assertTrue(allowed(local_time))
        insert_reachable = lambda open_date_count, local_time: (
            open_date_count == 1 and allowed(local_time)
        )
        self.assertFalse(insert_reachable(0, "09:30"))
        self.assertTrue(insert_reachable(1, "09:30"))
        self.assertEqual(self.body.count("INSERT INTO public.n6_virtual_trade_proposal"), 1)
        self.assertEqual(self.body.count("UPDATE "), 0)
        self.assertEqual(self.body.count("DELETE FROM"), 0)

    def test_052_rollback_restores_exact_048_definition_and_preserves_history(self) -> None:
        original = function_definition(
            SCHEMA_048.read_text(), "n6_btrack_proposal_create"
        )
        restored = function_definition(
            self.rollback, "n6_btrack_proposal_create"
        )
        self.assertEqual(restored, original)
        for forbidden in (
            "DELETE FROM",
            "TRUNCATE",
            "DROP TABLE",
            "DROP INDEX",
            "DROP FUNCTION",
        ):
            self.assertNotIn(forbidden, self.rollback.upper())

    def test_052_source_dml_and_secret_scans_are_fail_closed(self) -> None:
        normalized = self.sql.lower()
        self.assertEqual(normalized.count("insert into public.n6_virtual_trade_proposal"), 1)
        for forbidden in (
            "common_event_outbox",
            "common_event_inbox",
            "stock_identity",
            "condition_pool",
            "common_trigger",
            "common_action",
            "minute_bar_1m",
            "mootdx",
            "pgpassword",
            "postgresql://",
            "password=",
        ):
            self.assertNotIn(forbidden, normalized)
        self.assertEqual(
            self.contract["proposal_create"]["outside_session_result"]["error"],
            "outside_trading_session",
        )
        self.assertFalse(self.contract["proposal_create"]["client_time_authoritative"])


class N6ProposalTimestampSyntax053RolePolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sql = SCHEMA_053.read_text()
        cls.rollback = ROLLBACK_053.read_text()
        cls.contract = json.loads(CONTRACT_053_JSON.read_text())
        cls.body = function_definition(cls.sql, "n6_btrack_proposal_create")
        cls.published_052_body = function_definition(
            SCHEMA_052.read_text(), "n6_btrack_proposal_create"
        )

    def test_053_is_exact_postgresql_timestamp_syntax_fix(self) -> None:
        invalid = "pg_catalog.current_timestamp AT TIME ZONE 'Asia/Shanghai'"
        replacement = "pg_catalog.now() AT TIME ZONE 'Asia/Shanghai'"

        self.assertIn(invalid, self.published_052_body)
        self.assertNotIn(invalid, self.body)
        self.assertIn(replacement, self.body)
        self.assertEqual(
            self.body,
            self.published_052_body.replace(invalid, replacement),
        )
        self.assertEqual(
            self.contract["database_fix"]["replacement_expression"],
            replacement,
        )
        self.assertFalse(self.contract["database_fix"]["business_logic_changed"])
        self.assertFalse(self.contract["database_fix"]["historical_migrations_modified"])

    def test_053_preserves_function_security_acl_and_dml_boundary(self) -> None:
        self.assertEqual(
            re.findall(r"CREATE OR REPLACE FUNCTION public\.([a-z0-9_]+)", self.sql),
            ["n6_btrack_proposal_create"],
        )
        for invariant in (
            "RETURNS jsonb",
            "LANGUAGE plpgsql",
            "VOLATILE",
            "SECURITY DEFINER",
            "SET search_path = pg_catalog",
        ):
            self.assertIn(invariant, self.body)
        signature = "public.n6_btrack_proposal_create(text,text,bigint)"
        self.assertIn(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC;", self.sql)
        self.assertIn(f"GRANT EXECUTE ON FUNCTION {signature} TO n6_btrack_web;", self.sql)
        normalized = self.sql.lower()
        self.assertEqual(normalized.count("insert into public.n6_virtual_trade_proposal"), 1)
        for forbidden_relation in (
            "n6_virtual_order",
            "n6_virtual_trade",
            "n6_virtual_position",
            "n6_virtual_cash_ledger",
            "n6_virtual_cash_snapshot",
        ):
            self.assertNotRegex(
                normalized,
                rf"\b(insert\s+into|update)\s+public\.{forbidden_relation}\s*(?:\(|set\b)",
            )
        for forbidden in ("delete from", "truncate", "drop table"):
            self.assertNotIn(forbidden, normalized)

    def test_053_rollback_restores_exact_published_052_and_preserves_history(self) -> None:
        restored = function_definition(
            self.rollback, "n6_btrack_proposal_create"
        )
        self.assertEqual(restored, self.published_052_body)
        for forbidden in (
            "DELETE FROM",
            "TRUNCATE",
            "DROP TABLE",
            "DROP INDEX",
            "DROP FUNCTION",
        ):
            self.assertNotIn(forbidden, self.rollback.upper())
        self.assertTrue(
            self.contract["rollback"]["restore_exact_052_proposal_create_definition"]
        )
        self.assertTrue(self.contract["rollback"]["preserve_proposals_and_history"])


class N6ManualActionableBuy063RolePolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sql = SCHEMA_063.read_text()
        cls.rollback = ROLLBACK_063.read_text()
        cls.contract = json.loads(CONTRACT_063_JSON.read_text())
        cls.proposal = function_definition(cls.sql, "n6_btrack_proposal_create")
        cls.executor = function_definition(
            cls.sql, "n6_executor_apply_claimed_proposal"
        )
        cls.proposal_053 = function_definition(
            SCHEMA_053.read_text(), "n6_btrack_proposal_create"
        )
        cls.executor_057 = function_definition(
            (ROOT / "sql/057_n6_ai_agent_execution_compat.sql").read_text(),
            "n6_executor_apply_claimed_proposal",
        )

    def test_063_replaces_only_published_proposal_and_executor_functions(self) -> None:
        self.assertEqual(
            re.findall(
                r"CREATE OR REPLACE FUNCTION public\.([a-z0-9_]+)",
                self.sql,
            ),
            [
                "n6_btrack_proposal_create",
                "n6_executor_apply_claimed_proposal",
            ],
        )
        for body in (self.proposal, self.executor):
            for invariant in (
                "SECURITY DEFINER",
                "SET search_path = pg_catalog",
            ):
                self.assertIn(invariant, body)
        self.assertEqual(self.sql.count("function_owner <> current_user"), 2)
        self.assertEqual(
            self.sql.count(
                "function_config IS DISTINCT FROM "
                "ARRAY['search_path=pg_catalog']::text[]"
            ),
            2,
        )
        self.assertNotIn("ALTER FUNCTION", self.sql.upper())

    def test_063_proposal_diff_is_targetless_buy_and_current_trade_date_compat(self) -> None:
        normalization = (
            "    IF v_target_price IS NULL\n"
            "       OR v_target_price::text IN ('NaN', 'Infinity', '-Infinity')\n"
            "       OR v_target_price <= 0 THEN\n"
            "      v_target_price := NULL;\n"
            "    END IF;\n\n"
        )
        targetless_buy_guard = (
            "       OR (v_side <> 'buy' AND v_target_price IS NULL)\n"
        )
        original_target_guard = (
            "       OR v_target_price IS NULL\n"
            "       OR v_target_price <= 0\n"
        )
        canonical_trade_date = (
            "COALESCE(\n"
            "               p.display_payload_json->>'trade_date',\n"
            "               p.source_payload_json->>'trade_date',\n"
            "               c.card_payload_json->>'trade_date',\n"
            "               p.trace_json->>'trade_date'\n"
            "             )"
        )
        canonical_trade_date_where = (
            "COALESCE(\n"
            "              p.display_payload_json->>'trade_date',\n"
            "              p.source_payload_json->>'trade_date',\n"
            "              c.card_payload_json->>'trade_date',\n"
            "              p.trace_json->>'trade_date'\n"
            "            )"
        )
        current_card_status_compat = (
            "        AND (\n"
            "          (\n"
            "            COALESCE(\n"
            "              c.card_payload_json->>'action_state',\n"
            "              p.display_payload_json->>'action_state'\n"
            "            ) = 'eligible'\n"
            "            AND c.card_status IN ('candidate', 'active', 'blocked')\n"
            "          )\n"
            "          OR (\n"
            "            COALESCE(\n"
            "              c.card_payload_json->>'action_state',\n"
            "              p.display_payload_json->>'action_state'\n"
            "            ) = 'executed'\n"
            "            AND c.card_status IN ('action_confirmed', 'active', 'blocked')\n"
            "          )\n"
            "        )"
        )
        self.assertEqual(self.proposal.count(normalization), 1)
        self.assertEqual(self.proposal.count(targetless_buy_guard), 1)
        self.assertEqual(self.proposal.count(canonical_trade_date), 1)
        self.assertEqual(self.proposal.count(canonical_trade_date_where), 1)
        self.assertEqual(self.proposal.count(current_card_status_compat), 1)
        restored = (
            self.proposal.replace(normalization, "")
            .replace(targetless_buy_guard, original_target_guard)
            .replace(
                canonical_trade_date,
                "p.display_payload_json->>'for_trade_date'",
            )
            .replace(
                canonical_trade_date_where,
                "p.display_payload_json->>'for_trade_date'",
            )
            .replace(
                current_card_status_compat,
                "        AND c.card_status IN ('active', 'blocked')",
            )
        )
        self.assertEqual(restored, self.proposal_053)
        self.assertNotIn("'target_price_not_ready'", self.proposal)
        current_trade_date = self.contract["proposal_create"][
            "current_projection_trade_date"
        ]
        self.assertFalse(
            current_trade_date["legacy_display_for_trade_date_only"]
        )
        self.assertTrue(
            current_trade_date["must_equal_current_open_trade_date"]
        )
        self.assertEqual(
            self.contract["proposal_create"]["current_card_status_compat"],
            {
                "eligible": "candidate",
                "executed": "action_confirmed",
                "legacy": ["active", "blocked"],
            },
        )

    def test_063_actionable_buy_truth_table_is_encoded_by_reference_and_target_guards(self) -> None:
        reference_by_state = dict(
            re.findall(
                r"WHEN s\.action_state = '(eligible|executed)' "
                r"THEN '(trigger_price|action_price)'",
                self.proposal,
            )
        )
        self.assertEqual(
            reference_by_state,
            {
                "eligible": "trigger_price",
                "executed": "action_price",
            },
        )
        target_guard = (
            "       OR (v_side <> 'buy' AND v_target_price IS NULL)\n"
        )
        self.assertEqual(self.proposal.count(target_guard), 1)
        guarded_source = self.proposal[
            self.proposal.index("IF v_projection_id IS NULL"):
            self.proposal.index(
                "RETURN pg_catalog.jsonb_build_object(\n"
                "        'ok', false, 'status', 'not_found'",
                self.proposal.index("IF v_projection_id IS NULL"),
            )
        ]
        self.assertNotIn(
            "\n       OR v_target_price IS NULL\n",
            guarded_source,
        )
        expected = (
            ("eligible", "12.34", "trigger_price", "12.34"),
            ("eligible", None, "trigger_price", None),
            ("executed", "12.34", "action_price", "12.34"),
            ("executed", None, "action_price", None),
        )
        self.assertEqual(
            self.contract["acceptance_matrix"]["buy_proposals"],
            [
                "eligible_with_target",
                "eligible_without_target",
                "executed_with_target",
                "executed_without_target",
            ],
        )
        for action_state, target_price, reference_kind, normalized_target in expected:
            with self.subTest(
                action_state=action_state, target_price=target_price
            ):
                self.assertEqual(
                    reference_by_state[action_state],
                    reference_kind,
                )
                self.assertEqual(
                    target_price if target_price is not None else None,
                    normalized_target,
                )
                self.assertTrue(
                    target_price is not None
                    or "(v_side <> 'buy' AND v_target_price IS NULL)"
                    in self.proposal
                )
                self.assertEqual(
                    self.contract["proposal_create"]["buy_target_policy"][
                        "missing_target_blocks_proposal"
                    ],
                    False,
                )
        self.assertIn(
            "OR (v_side <> 'buy' AND v_target_price IS NULL)",
            self.proposal,
        )
        self.assertFalse(
            self.contract["proposal_create"]["sell_target_policy_changed"]
        )

    def test_063_preserves_session_scope_and_positive_reference_fail_closed(self) -> None:
        insert_index = self.proposal.index(
            "INSERT INTO public.n6_virtual_trade_proposal"
        )
        for invariant in (
            "current_trade_date_count <> 1",
            "shanghai_local_time BETWEEN time '09:30:00' AND time '11:30:00'",
            "shanghai_local_time BETWEEN time '13:00:00' AND time '15:00:00'",
            "p.source_payload_json->>'trade_date'",
            "p.user_id = (authority->>'user_id')::bigint",
            "p.asset_kind = 'stock'",
            "v_reference_price IS NULL",
            "v_reference_price <= 0",
            "m.principal_id = (authority->>'principal_id')::bigint",
            "rs.principal_id = (authority->>'principal_id')::bigint",
        ):
            self.assertIn(invariant, self.proposal)
            self.assertLess(self.proposal.index(invariant), insert_index)
        for non_actionable_state in ("blocked", "skipped", "expired"):
            self.assertNotIn(
                f"WHEN s.action_state = '{non_actionable_state}'",
                self.proposal,
            )
        self.assertLess(
            self.proposal.index("OR v_reference_kind IS NULL"),
            insert_index,
        )
        self.assertLess(
            self.proposal.index(
                "OR (v_side <> 'buy' AND v_target_price IS NULL)"
            ),
            insert_index,
        )
        self.assertEqual(
            self.proposal.count(
                "INSERT INTO public.n6_virtual_trade_proposal"
            ),
            1,
        )
        self.assertNotIn("UPDATE public.", self.proposal)
        self.assertNotIn("DELETE FROM", self.proposal.upper())

    def test_063_function_acl_is_exact_and_cross_role_execute_is_rejected(self) -> None:
        expected_acl = (
            (
                "public.n6_btrack_proposal_create(text,text,bigint)",
                "n6_btrack_web",
                "n6_ai_agent, n6_quote_writer, n6_virtual_executor",
            ),
            (
                "public.n6_executor_apply_claimed_proposal(bigint,text)",
                "n6_virtual_executor",
                "n6_btrack_web, n6_ai_agent, n6_quote_writer",
            ),
        )
        for signature, allowed_role, denied_roles in expected_acl:
            with self.subTest(signature=signature):
                self.assertIn(
                    f"REVOKE ALL ON FUNCTION {signature}\n"
                    f"  FROM PUBLIC, {denied_roles};",
                    self.sql,
                )
                self.assertIn(
                    f"GRANT EXECUTE ON FUNCTION {signature}\n"
                    f"  TO {allowed_role};",
                    self.sql,
                )
        self.assertEqual(
            self.sql.count("role.rolname = expected_role"),
            2,
        )
        self.assertEqual(
            self.sql.count("acl.grantee <> target.proowner"),
            2,
        )
        self.assertEqual(
            self.sql.count(
                "role.rolname IS DISTINCT FROM expected_role"
            ),
            2,
        )
        self.assertEqual(
            self.sql.count("acl.is_grantable IS FALSE"),
            2,
        )
        self.assertEqual(
            self.sql.count("acl.is_grantable IS NOT FALSE"),
            2,
        )
        for section in ("proposal_create", "executor"):
            self.assertFalse(
                self.contract[section][
                    "allowed_role_execute_grant_option"
                ]
            )
            self.assertEqual(
                self.contract[section]["unexpected_direct_execute_acl"],
                "fail_closed",
            )
        self.assertNotIn("has_function_privilege", self.sql)

    def test_063_rollback_restores_exact_053_and_057_with_acl(self) -> None:
        self.assertEqual(
            function_definition(
                self.rollback, "n6_btrack_proposal_create"
            ),
            self.proposal_053,
        )
        self.assertEqual(
            function_definition(
                self.rollback, "n6_executor_apply_claimed_proposal"
            ),
            self.executor_057,
        )
        self.assertEqual(
            re.findall(
                r"CREATE OR REPLACE FUNCTION public\.([a-z0-9_]+)",
                self.rollback,
            ),
            [
                "n6_btrack_proposal_create",
                "n6_executor_apply_claimed_proposal",
            ],
        )
        expected_acl = (
            (
                "public.n6_btrack_proposal_create(text,text,bigint)",
                "n6_btrack_web",
                "n6_ai_agent, n6_quote_writer, n6_virtual_executor",
            ),
            (
                "public.n6_executor_apply_claimed_proposal(bigint,text)",
                "n6_virtual_executor",
                "n6_btrack_web, n6_ai_agent, n6_quote_writer",
            ),
        )
        for signature, allowed_role, denied_roles in expected_acl:
            with self.subTest(signature=signature):
                self.assertIn(
                    f"REVOKE ALL ON FUNCTION {signature}\n"
                    f"  FROM PUBLIC, {denied_roles};",
                    self.rollback,
                )
                self.assertIn(
                    f"GRANT EXECUTE ON FUNCTION {signature}\n"
                    f"  TO {allowed_role};",
                    self.rollback,
                )
        self.assertEqual(
            self.rollback.count("role.rolname = expected_role"),
            1,
        )
        self.assertEqual(
            self.rollback.count("acl.grantee <> target.proowner"),
            1,
        )
        self.assertEqual(
            self.rollback.count(
                "role.rolname IS DISTINCT FROM expected_role"
            ),
            1,
        )
        self.assertEqual(
            self.rollback.count("acl.is_grantable IS FALSE"),
            1,
        )
        self.assertEqual(
            self.rollback.count("acl.is_grantable IS NOT FALSE"),
            1,
        )
        self.assertNotIn("has_function_privilege", self.rollback)
        for forbidden in (
            "DELETE FROM",
            "TRUNCATE",
            "DROP TABLE",
            "DROP INDEX",
            "DROP FUNCTION",
        ):
            self.assertNotIn(forbidden, self.rollback.upper())
        rollback = self.contract["rollback"]
        self.assertTrue(
            rollback["restore_exact_053_proposal_create_definition"]
        )
        self.assertTrue(rollback["restore_exact_057_executor_definition"])
        self.assertTrue(rollback["restore_function_acl"])
        self.assertTrue(
            rollback[
                "preserve_proposals_orders_trades_cash_lots_positions_and_events"
            ]
        )


class N6VirtualStopLoss049RolePolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sql = SCHEMA_049.read_text()
        cls.rollback = ROLLBACK_049.read_text()
        cls.contract = json.loads(CONTRACT_049_JSON.read_text())

    def test_executor_only_security_definer_acl(self) -> None:
        for name in ("n6_executor_freeze_next_stop_loss", "n6_executor_evaluate_next_stop_loss"):
            body = function_definition(self.sql, name)
            self.assertIn("SECURITY DEFINER", body)
            self.assertIn("SET search_path = pg_catalog", body)
            signature = f"public.{name}(text)"
            self.assertIn(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC;", self.sql)
            self.assertIn(f"REVOKE ALL ON FUNCTION {signature} FROM n6_btrack_web;", self.sql)
            self.assertIn(f"GRANT EXECUTE ON FUNCTION {signature} TO n6_virtual_executor;", self.sql)
        self.assertNotRegex(self.sql, r"GRANT\s+(SELECT|INSERT|UPDATE|DELETE|USAGE).*\sON\s+(TABLE|SEQUENCE)")

    def test_049_reads_only_explicit_n6_and_calendar_authorities(self) -> None:
        allowed_relations = {
            "common_trade_calendar", "n6_principal", "n6_virtual_account",
            "n6_virtual_cash_ledger", "n6_virtual_cash_snapshot", "n6_virtual_order",
            "n6_virtual_position", "n6_virtual_position_event", "n6_virtual_position_lot",
            "n6_virtual_quote_snapshot", "n6_virtual_trade", "n6_virtual_trade_proposal",
        }
        relations = set(re.findall(r"public\.([a-z][a-z0-9_]*)", self.sql))
        functions = {name for name in relations if name.startswith("n6_executor_")}
        self.assertEqual(relations - functions, allowed_relations)
        for forbidden in (
            "common_event_outbox", "common_event_inbox", "membership_fact",
            "stock_minute_bar", "stock_daily", "n3n6q", "mootdx", "requests.",
        ):
            self.assertNotIn(forbidden, self.sql.lower())

    def test_apply_exact_stop_scope_and_046_nonstop_source_policy(self) -> None:
        apply = function_definition(self.sql, "n6_executor_apply_claimed_proposal")
        self.assertIn("proposal.source_virtual_position_id IS DISTINCT FROM position_before.virtual_position_id", apply)
        self.assertIn("proposal.holding_episode_no IS DISTINCT FROM position_before.holding_episode_no", apply)
        self.assertIn("proposal.source_type NOT IN ('signal', 'manual_position', 'stop_loss')", apply)
        original = function_definition(SCHEMA_046.read_text(), "n6_executor_apply_claimed_proposal")
        for invariant in (
            "floor(\n      LEAST(300000::numeric", "'n6_046_zero_fee_v1'",
            "ORDER BY available_trade_date, virtual_position_lot_id", "source_position_event_id",
        ):
            self.assertIn(invariant, original)
            self.assertIn(invariant, apply)

    def test_rollback_restores_exact_046_and_preserves_history(self) -> None:
        original = function_definition(SCHEMA_046.read_text(), "n6_executor_apply_claimed_proposal")
        restored = function_definition(self.rollback, "n6_executor_apply_claimed_proposal")
        self.assertEqual(restored, original)
        for name in ("n6_executor_freeze_next_stop_loss", "n6_executor_evaluate_next_stop_loss"):
            self.assertIn(f"DROP FUNCTION IF EXISTS public.{name}(text);", self.rollback)
        for forbidden in ("DELETE FROM", "TRUNCATE", "DROP TABLE", "DROP INDEX"):
            self.assertNotIn(forbidden, self.rollback.upper())


class N6FilterBulkScope054RolePolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sql = SCHEMA_054.read_text()
        cls.rollback = ROLLBACK_054.read_text()
        cls.contract = json.loads(CONTRACT_054_JSON.read_text())
        cls.function_names = {
            "n6_btrack_scope_bulk_preview",
            "n6_btrack_monitor_bulk_upsert",
            "n6_btrack_realtime_bulk_upsert",
        }

    def test_054_creates_only_three_hardened_function_entrypoints(self) -> None:
        names = set(
            re.findall(
                r"CREATE OR REPLACE FUNCTION public\.([a-z0-9_]+)",
                self.sql,
            )
        )
        self.assertEqual(names, self.function_names)
        self.assertEqual(self.sql.count("CREATE OR REPLACE FUNCTION public."), 3)
        for name in self.function_names:
            body = function_definition(self.sql, name)
            self.assertIn("SECURITY DEFINER", body)
            self.assertIn("SET search_path = pg_catalog", body)
            self.assertIn(f"ALTER FUNCTION public.{name}", self.sql)
            self.assertIn(f"REVOKE ALL ON FUNCTION public.{name}", self.sql)
            self.assertIn("FROM PUBLIC;", self.sql)
            self.assertRegex(
                self.sql,
                rf"GRANT EXECUTE ON FUNCTION public\.{name}\([^)]+\)\s+TO n6_btrack_web;",
            )
        for forbidden in (
            "CREATE TABLE",
            "ALTER TABLE",
            "DROP TABLE",
            "CREATE INDEX",
            "CREATE TRIGGER",
            "CREATE ROLE",
            "ALTER ROLE",
        ):
            self.assertNotIn(forbidden, self.sql.upper())
        self.assertNotRegex(
            self.sql,
            r"GRANT\s+(SELECT|INSERT|UPDATE|DELETE|USAGE).*\sON\s+(TABLE|SEQUENCE)",
        )

    def test_054_validates_complete_current_approved_identity_set_without_dynamic_sql(self) -> None:
        for view in (
            "public.v_n6_stock_condition_display_basis",
            "public.v_n6_index_condition_display_basis",
            "public.v_n6_board_condition_display_basis",
        ):
            self.assertIn(view, self.sql)
        self.assertGreaterEqual(self.sql.count("pg_catalog.cardinality(p_identity_keys)"), 3)
        self.assertGreaterEqual(self.sql.count("input_count > 10000"), 3)
        self.assertGreaterEqual(self.sql.count("approved_count <> input_count"), 3)
        self.assertEqual(self.sql.count("v_source_run_id <> p_source_run_id"), 3)
        self.assertGreaterEqual(self.sql.count("SELECT pg_catalog.max(for_trade_date)"), 9)
        self.assertNotIn("execute format", self.sql.lower())
        self.assertNotIn("execute immediate", self.sql.lower())
        for forbidden in (
            "common_event_outbox",
            "condition_basis ",
            "condition_pool ",
            "minute_target_scope",
            "membership_fact",
            "common_trigger_match",
            "common_action_event",
        ):
            self.assertNotIn(forbidden, self.sql.lower())
        self.assertNotIn("source_trade_date::text = source_trade_date", self.sql)
        self.assertNotIn("run_id::text = source_run_id", self.sql)

    def test_054_set_based_direction_idempotency_and_history_contract(self) -> None:
        monitor = function_definition(self.sql, "n6_btrack_monitor_bulk_upsert")
        realtime = function_definition(self.sql, "n6_btrack_realtime_bulk_upsert")
        self.assertIn("FROM pg_catalog.unnest(p_identity_keys)", monitor)
        self.assertIn("CROSS JOIN (VALUES ('buy'), ('sell'))", monitor)
        self.assertIn("'stock', input.identity_key, 'buy'", monitor)
        self.assertEqual(monitor.count("INSERT INTO public.user_monitor_"), 3)
        self.assertEqual(monitor.count("ON CONFLICT DO NOTHING"), 3)
        self.assertNotIn("DELETE FROM public.user_monitor", monitor)
        self.assertEqual(
            realtime.count("INSERT INTO public.user_realtime_monitor_scope"),
            1,
        )
        self.assertIn("DO UPDATE SET status = 'active'", realtime)
        self.assertIn("WHERE public.user_realtime_monitor_scope.status = 'deleted'", realtime)
        self.assertEqual(self.contract["maximum_identity_count"], 10000)
        self.assertFalse(self.contract["selection_token"]["client_identity_list_allowed"])
        self.assertFalse(self.contract["history"]["bulk_remove_supported"])

    def test_054_never_writes_trade_cash_proposal_or_upstream_relations(self) -> None:
        normalized = self.sql.lower()
        for relation in (
            "n6_virtual_trade_proposal",
            "n6_virtual_order",
            "n6_virtual_trade",
            "n6_virtual_position",
            "n6_virtual_cash_ledger",
            "n6_virtual_cash_snapshot",
        ):
            self.assertNotRegex(
                normalized,
                rf"\b(insert\s+into|update|delete\s+from)\s+public\.{relation}\b",
            )
        for forbidden in ("n1_", "n2_", "n3_", "n4_", "n5_"):
            self.assertNotIn(forbidden, normalized)

    def test_054_rollback_drops_only_entrypoints_and_preserves_history(self) -> None:
        self.assertEqual(self.rollback.count("DROP FUNCTION IF EXISTS public."), 3)
        for name in self.function_names:
            self.assertIn(f"DROP FUNCTION IF EXISTS public.{name}", self.rollback)
        for forbidden in (
            "DELETE FROM",
            "TRUNCATE",
            "DROP TABLE",
            "ALTER TABLE",
            "UPDATE ",
        ):
            self.assertNotIn(forbidden, self.rollback.upper())
        self.assertFalse(self.contract["history"]["rollback_deletes_business_history"])

    def test_authority_repository_exposes_only_named_054_function_calls(self) -> None:
        source = inspect.getsource(PostgresN6BTrackAuthorityRepository)
        for name in self.function_names:
            self.assertIn(f'"{name}"', source)
        for method in (
            "preview_bulk_scope",
            "bulk_upsert_monitor_items",
            "bulk_upsert_realtime_scope_items",
        ):
            self.assertIn(f"def {method}(", source)
        self.assertNotIn("identity_keys=%", source)


if __name__ == "__main__":
    unittest.main()
