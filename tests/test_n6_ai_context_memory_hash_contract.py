from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "sql/058_n6_ai_context_memory_hash_contract.sql"
ROLLBACK = (
    ROOT / "sql/058_n6_ai_context_memory_hash_contract_rollback.sql"
)
MANIFEST = (
    ROOT
    / "docs/N6_AI_PRODUCTION_KNOWLEDGE_BUNDLE_MANIFEST_V1.json"
)


class N6AiContextMemoryHashContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = SCHEMA.read_text(encoding="utf-8")
        cls.rollback = ROLLBACK.read_text(encoding="utf-8")

    def test_migration_is_single_transaction_and_owner_gated(self) -> None:
        self.assertTrue(self.schema.startswith("BEGIN;\n"))
        self.assertTrue(self.schema.rstrip().endswith("COMMIT;"))
        self.assertEqual(self.schema.count("\nCOMMIT;"), 1)
        self.assertIn("SESSION_USER <> 'ashare_v3_user'", self.schema)
        self.assertIn("CURRENT_USER <> 'ashare_v3_user'", self.schema)
        self.assertIn("058_requires_055", self.schema)
        self.assertIn("058_ai_role_contract_mismatch", self.schema)

    def test_exact_four_hash_columns_are_additive_and_atomic(self) -> None:
        for column in (
            "knowledge_bundle_hash",
            "universe_snapshot_hash",
            "memory_snapshot_hash",
            "workset_hash",
        ):
            self.assertEqual(
                len(
                    re.findall(
                        rf"ADD COLUMN {column} TEXT", self.schema
                    )
                ),
                1,
            )
            self.assertIn(
                f"{column} ~ '^[0-9a-f]{{64}}$'", self.schema
            )
        self.assertIn(
            "n6_ai_context_snapshot_058_hashes_ck", self.schema
        )
        self.assertNotRegex(self.schema, r"CREATE\s+TABLE")
        self.assertNotRegex(self.schema, r"CREATE\s+(?:UNIQUE\s+)?INDEX")

    def test_v2_is_hardened_and_bundle_bound(self) -> None:
        self.assertEqual(
            self.schema.count(
                "CREATE OR REPLACE FUNCTION "
                "public.n6_ai_agent_context_load_v2("
            ),
            1,
        )
        self.assertIn("SECURITY DEFINER", self.schema)
        self.assertIn("SET search_path = pg_catalog", self.schema)
        self.assertIn("SESSION_USER <> 'n6_ai_agent'", self.schema)
        self.assertIn("p_run_bucket IS NULL", self.schema)
        self.assertIn("p_for_trade_date IS NULL", self.schema)
        self.assertIn(
            "pg_catalog.substr(p_run_bucket, 7, 8)", self.schema
        )
        self.assertIn(
            "pg_catalog.substr(p_run_bucket, 1, 8)", self.schema
        )
        validation_position = self.schema.index(
            "SESSION_USER <> 'n6_ai_agent'"
        )
        projection_query_position = self.schema.index(
            "FROM public.n6_ai_shared_signal_projection"
        )
        self.assertLess(validation_position, projection_query_position)
        self.assertIn(
            "1a873d69ef8f14e329b744460d549bcb3c35d99bb6af5fd10c16fc1a9dda15bc",
            self.schema,
        )
        self.assertIn("p_max_signals <> 1000", self.schema)
        self.assertIn("signal_universe_too_large", self.schema)
        self.assertIn("'market_context_count'", self.schema)
        self.assertIn(
            "public.n6_ai_agent_context_load(\n"
            "    p_run_bucket,",
            self.schema,
        )

    def test_universe_memory_and_workset_hashes_are_server_derived(
        self,
    ) -> None:
        signature = self.schema[
            self.schema.index(
                "public.n6_ai_agent_context_load_v2("
            ) : self.schema.index("RETURNS jsonb")
        ]
        self.assertNotIn("p_universe", signature)
        self.assertNotIn("p_memory", signature)
        self.assertNotIn("p_workset", signature)
        for key in (
            "'signals', context_payload->'signals'",
            "'market_context', context_payload->'market_context'",
            "'positions', context_payload->'positions'",
            "'portfolio', context_payload->'portfolio'",
            "'daily_metrics', context_payload->'daily_metrics'",
            "'strategy', context_payload->'strategy'",
        ):
            self.assertIn(key, self.schema)
        self.assertGreaterEqual(self.schema.count("pg_catalog.sha256("), 3)

    def test_post_create_failures_abort_the_statement(self) -> None:
        for failure in (
            "context_v2_created_snapshot_id_missing",
            "context_v2_created_snapshot_authority_mismatch",
            "context_v2_created_snapshot_update_failed",
        ):
            self.assertIn(f"RAISE EXCEPTION '{failure}'", self.schema)
        self.assertIn("IF base_status = 'ready' THEN", self.schema)

    def test_all_signal_count_and_load_share_one_locked_state(
        self,
    ) -> None:
        shared_lock = (
            "LOCK TABLE public.n6_ai_shared_signal_projection "
            "IN SHARE MODE;"
        )
        run_lock = (
            "LOCK TABLE public.user_projection_run IN SHARE MODE;"
        )
        self.assertIn(shared_lock, self.schema)
        self.assertIn(run_lock, self.schema)
        self.assertLess(
            self.schema.index(shared_lock),
            self.schema.index(
                "FROM (\n    SELECT DISTINCT shared.asset_kind"
            ),
        )
        self.assertLess(
            self.schema.index(run_lock),
            self.schema.index(
                "FROM (\n    SELECT DISTINCT shared.asset_kind"
            ),
        )
        self.assertIn(
            "eligible_signal.asset_kind IN ('index', 'board')",
            self.schema,
        )

    def test_snapshot_identity_binds_date_and_bucket(self) -> None:
        self.assertIn(
            "snapshot.for_trade_date = p_for_trade_date", self.schema
        )
        self.assertIn(
            "snapshot.run_bucket = p_run_bucket", self.schema
        )

    def test_principal_and_source_boundaries_fail_closed(self) -> None:
        for required in (
            "public.n6_ai_shared_signal_projection",
            "public.n6_ai_context_snapshot",
            "public.n6_ai_user",
            "public.n6_principal",
            "principal.principal_type = 'ai_user'",
            "principal.owner_user_id IS NULL",
        ):
            self.assertIn(required, self.schema)
        for forbidden in (
            "common_event_outbox",
            "common_event_inbox",
            "common_event_consumer_checkpoint",
            "user_session",
            "user_monitor_",
            "user_realtime_monitor_scope",
            "condition_basis",
            "condition_pool",
            "minute_bar_1m",
        ):
            self.assertNotIn(forbidden, self.schema)

    def test_function_only_acl_replaces_v1_agent_grant(self) -> None:
        self.assertIn(
            "FROM PUBLIC, n6_btrack_web, n6_virtual_executor",
            self.schema,
        )
        self.assertIn(
            "REVOKE EXECUTE ON FUNCTION "
            "public.n6_ai_agent_context_load(\n"
            "  text,date,integer\n) FROM n6_ai_agent;",
            self.schema,
        )
        self.assertIn(
            "GRANT EXECUTE ON FUNCTION "
            "public.n6_ai_agent_context_load_v2(\n"
            "  text,date,integer,text\n) TO n6_ai_agent;",
            self.schema,
        )
        self.assertNotRegex(
            self.schema,
            r"GRANT\s+(?:SELECT|INSERT|UPDATE|DELETE|USAGE)"
            r"\s+ON\s+(?:TABLE|SEQUENCE)",
        )

    def test_rollback_preserves_frozen_history_fail_closed(self) -> None:
        self.assertTrue(self.rollback.startswith("BEGIN;\n"))
        self.assertTrue(self.rollback.rstrip().endswith("COMMIT;"))
        self.assertIn(
            "058_rollback_blocked_by_frozen_context_history",
            self.rollback,
        )
        self.assertIn(
            "DROP FUNCTION public.n6_ai_agent_context_load_v2",
            self.rollback,
        )
        self.assertIn(
            "GRANT EXECUTE ON FUNCTION "
            "public.n6_ai_agent_context_load(",
            self.rollback,
        )
        self.assertNotRegex(self.rollback, r"\bDELETE\s+FROM\b")
        self.assertNotRegex(self.rollback, r"\bTRUNCATE\b")
        self.assertNotRegex(self.rollback, r"\bDROP\s+TABLE\b")

    def test_manifest_bundle_hash_is_the_frozen_function_constant(
        self,
    ) -> None:
        import json

        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["bundle_sha256"],
            "1a873d69ef8f14e329b744460d549bcb3c35d99bb6af5fd10c16fc1a9dda15bc",
        )


if __name__ == "__main__":
    unittest.main()
