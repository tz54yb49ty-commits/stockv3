from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "sql/073_n6_strategy_center_schema.sql"
ROLLBACK = ROOT / "sql/073_n6_strategy_center_schema_rollback.sql"


def function_definition(sql: str, name: str) -> str:
    marker = f"CREATE FUNCTION public.{name}"
    start = sql.index(marker)
    end = sql.index("$function$;", start) + len("$function$;")
    return sql[start:end]


class N6StrategyCenterSchema073Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = SCHEMA.read_text(encoding="utf-8")
        cls.rollback = ROLLBACK.read_text(encoding="utf-8")
        cls.schema_lower = cls.schema.lower()
        cls.state_function = function_definition(
            cls.schema, "n6_btrack_strategy_center_state"
        )
        cls.changes_function = function_definition(
            cls.schema, "n6_btrack_strategy_center_changes"
        )
        cls.selection_function = function_definition(
            cls.schema, "n6_btrack_strategy_selection_put"
        )

    def test_exact_five_n6_owned_tables_and_no_cross_layer_fact_table(self) -> None:
        tables = re.findall(
            r"(?im)^CREATE TABLE public\.([a-z0-9_]+) \(", self.schema
        )
        self.assertEqual(
            tables,
            [
                "n6_strategy_package_catalog",
                "n6_user_strategy_selection_revision",
                "n6_user_strategy_selection_item",
                "n6_strategy_match_projection",
                "n6_strategy_match_change",
            ],
        )
        for forbidden in (
            "public.common_action_event",
            "public.stock_action_fact",
            "public.index_action_fact",
            "public.board_action_fact",
            "public.common_event_outbox",
            "public.common_event_inbox",
            "public.common_event_consumer_checkpoint",
            "public.common_trigger_match",
            "public.n6_virtual_trade_proposal",
            "public.n6_virtual_order",
            "public.n6_virtual_trade",
            "n6_executor_apply",
        ):
            self.assertNotIn(forbidden, self.schema_lower)
        self.assertIn("public.user_signal_projection", self.schema_lower)

    def test_package_catalog_freezes_truth_table_and_board_allowlist(self) -> None:
        for required in (
            "'package_1'::text",
            "'package_2'::text",
            "'index_and_board_executed'::text",
            "'board_executed'::text",
            "'trade_date_scope', 'whole_trade_date'",
            "'direction_match_required', false",
            "'stock_states', pg_catalog.jsonb_build_array('eligible', 'executed')",
            "'index_any_executed_required', true",
            "'index_any_executed_required', false",
            "'board_any_executed_required', true",
            "'display_only', true",
            "'tdx_industry', 'tdx_concept', 'tdx_region'",
        ):
            self.assertIn(required, self.schema)
        self.assertNotIn("tdx_other", self.schema)
        self.assertRegex(
            self.schema,
            r"(?s)'package_1'::text,.*?'v1'::text,.*?true,",
        )
        self.assertRegex(
            self.schema,
            r"(?s)'package_2'::text,.*?'v1'::text,.*?false,",
        )

    def test_default_selection_is_audited_package_1_revision(self) -> None:
        for required in (
            "migration-073-default-package-1-",
            "'source', 'migration_073_default_selection'",
            "'default_package', 'package_1'",
            "'requires_current_trade_date_replay', true",
            "principal.principal_type IN ('admin', 'human_user')",
            "principal.owner_user_id",
            "account.status = 'active'",
        ):
            self.assertIn(required, self.schema)
        self.assertIn(
            "item.package_key <> 'package_1'", self.schema
        )
        self.assertIn(
            "expected_principal_count <> seeded_revision_count", self.schema
        )

    def test_new_principal_gets_default_package_1_in_same_transaction(self) -> None:
        trigger_function = function_definition(
            self.schema, "n6_strategy_default_selection_on_principal_insert"
        )
        for required in (
            "AFTER INSERT ON public.n6_principal",
            "FOR EACH ROW",
            "n6_strategy_default_selection_on_principal_insert()",
            "NEW.owner_user_id",
            "'principal-default-package-1-' || NEW.principal_id::text",
            "'active'",
            "'pending'",
            "'package_1'",
            "'v1'",
            "requires_current_trade_date_replay",
        ):
            self.assertIn(required, self.schema)
        self.assertIn("SECURITY DEFINER", trigger_function)
        self.assertIn("SET search_path = pg_catalog", trigger_function)
        self.assertNotRegex(trigger_function, r"(?im)^\s*COMMIT\b")
        self.assertNotRegex(trigger_function, r"(?im)^\s*ROLLBACK\b")

    def test_selection_revision_is_append_only_and_requires_nonempty_unique_keys(self) -> None:
        body = self.selection_function
        self.assertIn(
            "pg_catalog.cardinality(p_selected_package_keys) NOT BETWEEN 1 AND 2",
            body,
        )
        self.assertIn("strategy_selection_package_keys_duplicate", body)
        self.assertIn("strategy_selection_replay_pending", body)
        self.assertIn("strategy_selection_revision_conflict", body)
        self.assertIn("strategy_selection_idempotency_conflict", body)
        self.assertIn(
            "selection_catalog_count <> pg_catalog.cardinality(normalized_keys)",
            body,
        )
        self.assertIn("selection_status", body)
        self.assertIn("'pending'", body)
        self.assertIn("previous_revision_id", body)
        self.assertNotRegex(body, r"(?im)^\s*UPDATE\s+")
        self.assertNotRegex(body, r"(?im)^\s*DELETE\s+FROM\s+")

    def test_positive_authority_uses_session_resolver_and_owned_principal(self) -> None:
        for body in (self.state_function, self.selection_function):
            self.assertIn(
                "public.n6_btrack_resolve_authority(p_session_token_hash)", body
            )
            self.assertIn("SECURITY DEFINER", body)
            self.assertIn("SET search_path = pg_catalog", body)
        for scoped in (
            "revision.principal_id = (authority->>'principal_id')::bigint",
            "revision.principal_type = authority->>'principal_type'",
            "revision.user_id = (authority->>'user_id')::bigint",
        ):
            self.assertIn(scoped, self.schema)

    def test_negative_pollution_cannot_supply_user_or_principal_identity(self) -> None:
        signature = self.selection_function.split("RETURNS jsonb", 1)[0]
        self.assertNotIn("p_user_id", signature)
        self.assertNotIn("p_principal_id", signature)
        self.assertNotIn("p_principal_type", signature)
        self.assertIn("p_session_token_hash text", signature)
        self.assertIn("p_selected_package_keys text[]", signature)
        self.assertIn("p_expected_revision bigint", signature)
        self.assertIn("p_request_id text", signature)

    def test_missing_authority_fails_closed_without_fallback(self) -> None:
        self.assertIn("IF authority IS NULL THEN", self.selection_function)
        self.assertIn(
            "RAISE EXCEPTION 'strategy_selection_unauthorized'",
            self.selection_function,
        )
        self.assertIn(
            "WHEN (SELECT value FROM authority) IS NULL THEN NULL",
            self.state_function,
        )
        for forbidden in (
            "current_user_id",
            "default_user_id",
            "min(user_id)",
            "min(principal_id)",
        ):
            self.assertNotIn(forbidden, self.schema_lower)

    def test_match_projection_freezes_scope_mapping_signal_and_episode(self) -> None:
        for required in (
            "stock_identity_key text NOT NULL",
            "action_episode_key text NOT NULL",
            "action_state IN ('eligible', 'executed')",
            "source_signal_projection_id bigint NOT NULL",
            "matched_packages text[] NOT NULL",
            "scope_sources text[] NOT NULL",
            "'monitor', 'realtime_scope', 'virtual_position'",
            "indices_json jsonb NOT NULL",
            "matched_boards_json jsonb NOT NULL",
            "signal_json jsonb NOT NULL",
            "state_timeline_json jsonb NOT NULL",
            "membership_source_trade_date = trade_date",
            "mapping_quality IN ('passed', 'missing_index', 'degraded')",
        ):
            self.assertIn(required, self.schema)
        self.assertIn(
            "matched_packages = ARRAY['package_1', 'package_2']::text[]",
            self.schema,
        )

    def test_change_ledger_supports_sse_cursor_and_stable_dedup(self) -> None:
        change_table = self.schema.split(
            "CREATE TABLE public.n6_strategy_match_change (", 1
        )[1].split("CREATE INDEX idx_073_n6_strategy_change_stream", 1)[0]
        for required in (
            "strategy_match_change_id bigint GENERATED ALWAYS AS IDENTITY",
            "change_type IN ('upsert', 'remove', 'reset')",
            "UNIQUE (principal_id, principal_type, user_id, dedup_key)",
            "payload_hash ~ '^[0-9a-f]{64}$'",
            "idx_073_n6_strategy_change_stream",
            "'watermark'",
        ):
            self.assertIn(required, self.schema)
        self.assertIn(
            "A remove change is\n  -- an append-only tombstone",
            change_table,
        )
        self.assertNotIn(
            "REFERENCES public.n6_strategy_match_projection",
            change_table,
        )
        self.assertIn(
            "change_type IN ('upsert', 'remove')\n     AND strategy_match_projection_id IS NOT NULL",
            change_table,
        )
        for required in (
            "public.n6_btrack_resolve_authority(p_session_token_hash)",
            "change.strategy_match_change_id > normalized.after_change_id",
            "COALESCE(p_after_change_id, 0::bigint), 0::bigint",
            "LEAST(\n             GREATEST(COALESCE(p_limit, 100), 1), 500",
            "'change_id', row.strategy_match_change_id",
            "'event', row.change_type",
            "'has_more'",
            "LIMIT (SELECT row_limit + 1 FROM normalized)",
            "SELECT pg_catalog.count(*) > (SELECT row_limit FROM normalized)",
        ):
            self.assertIn(required, self.changes_function)
        self.assertIn("SECURITY DEFINER", self.changes_function)
        self.assertIn("SET search_path = pg_catalog", self.changes_function)

    def test_state_reports_authoritative_three_source_union_counts(self) -> None:
        for required in (
            "current_stock_approved_batch AS",
            "FROM public.user_monitor_stock monitor",
            "FROM public.user_realtime_monitor_scope realtime",
            "FROM public.n6_virtual_account account",
            "JOIN public.n6_virtual_position position",
            "position.quantity > 0",
            "'mode', 'monitor_union_realtime_scope_union_virtual_position'",
            "'stock_count'",
            "'monitor_count'",
            "'realtime_scope_count'",
            "'virtual_position_count'",
            "'multi_source_count'",
        ):
            self.assertIn(required, self.state_function)
        self.assertNotIn("monitor.direction", self.state_function)

    def test_acl_keeps_web_function_only_and_worker_least_privilege(self) -> None:
        self.assertIn("('n6_strategy_worker'::text)", self.schema)
        self.assertIn("073 required role missing", self.schema)
        self.assertNotRegex(self.schema, r"(?im)^\s*CREATE\s+ROLE\b")
        self.assertNotRegex(self.schema, r"(?im)^\s*ALTER\s+ROLE\b")
        self.assertRegex(
            self.schema,
            r"(?s)REVOKE ALL ON TABLE.*?FROM PUBLIC, n6_btrack_web, "
            r"n6_strategy_worker, n6_virtual_executor,",
        )
        self.assertRegex(
            self.schema,
            r"(?s)GRANT EXECUTE ON FUNCTION.*?TO n6_btrack_web;",
        )
        function_grant = self.schema.split("GRANT EXECUTE ON FUNCTION", 1)[1].split(
            "GRANT USAGE ON SCHEMA public TO n6_strategy_worker;", 1
        )[0]
        self.assertNotIn("TO n6_strategy_worker", function_grant)
        worker_grants = self.schema.split(
            "GRANT USAGE ON SCHEMA public TO n6_strategy_worker;", 1
        )[1]
        for required in (
            "public.user_signal_projection",
            "public.user_signal_card",
            "public.user_monitor_stock",
            "public.user_realtime_monitor_scope",
            "public.n6_virtual_position",
            "public.v_n6_stock_condition_display_basis",
            "public.v_n6_index_membership_fact",
            "public.v_n6_board_membership_fact",
            "public.n6_strategy_match_projection",
            "public.n6_strategy_match_change",
            "GRANT UPDATE (",
            "selection_status",
            "replay_status",
            "GRANT INSERT, UPDATE, DELETE ON TABLE\n  public.n6_strategy_match_projection",
            "GRANT INSERT ON TABLE public.n6_strategy_match_change",
            "GRANT USAGE, SELECT ON SEQUENCE",
        ):
            self.assertIn(required, worker_grants)
        for forbidden in (
            "GRANT INSERT ON TABLE public.n6_user_strategy_selection_revision",
            "GRANT DELETE ON TABLE public.n6_strategy_match_change",
            "GRANT UPDATE ON TABLE public.n6_strategy_match_change",
            "common_action_event",
            "common_event_outbox",
        ):
            self.assertNotIn(forbidden, worker_grants)

    def test_rollback_is_exact_and_never_cascades_or_touches_older_objects(self) -> None:
        dropped_tables = re.findall(
            r"(?im)^DROP TABLE public\.([a-z0-9_]+);", self.rollback
        )
        self.assertEqual(
            dropped_tables,
            [
                "n6_strategy_match_change",
                "n6_strategy_match_projection",
                "n6_user_strategy_selection_item",
                "n6_user_strategy_selection_revision",
                "n6_strategy_package_catalog",
            ],
        )
        self.assertNotIn("CASCADE", self.rollback)
        self.assertNotRegex(self.rollback, r"(?im)^\s*DELETE\s+FROM\s+")
        self.assertNotRegex(self.rollback, r"(?im)^\s*UPDATE\s+")
        for required in (
            "DROP FUNCTION public.n6_btrack_strategy_selection_put(",
            "DROP FUNCTION public.n6_btrack_strategy_center_state(text);",
            "DROP FUNCTION public.n6_btrack_strategy_center_changes(text,bigint,integer);",
            "DROP TRIGGER trg_073_n6_strategy_default_selection ON public.n6_principal;",
            "DROP FUNCTION public.n6_strategy_default_selection_on_principal_insert();",
            "073 rollback left strategy center objects behind",
        ):
            self.assertIn(required, self.rollback)
        for forbidden in (
            "user_signal_projection;",
            "n6_principal;",
            "user_account;",
            "n6_virtual_position;",
        ):
            self.assertNotIn(f"DROP TABLE public.{forbidden}", self.rollback)


if __name__ == "__main__":
    unittest.main()
