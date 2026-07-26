"""Static migration contract for the N6 Shadow 071 nine-slot schedule."""

from hashlib import sha256
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/071_n6_ai_shadow_nine_slot_schedule_preflight.sql"
ROLLBACK = (
    ROOT / "sql/071_n6_ai_shadow_nine_slot_schedule_preflight_rollback.sql"
)
HISTORICAL_067 = ROOT / "sql/067_n6_ai_shadow_schedule_preflight.sql"

FUNCTION_MARKER = (
    "CREATE OR REPLACE FUNCTION\n"
    "public.n6_ai_agent_shadow_schedule_preflight("
)
CONTEXT_LOAD_SHA256 = (
    "1d4283cd96f34032e51049aa6f4c1305"
    "dabe37cf0c62e1b2ba7594091290cc5a"
)
CONTEXT_LOAD_V2_SHA256 = (
    "ae000e4593d0de425dce168640740e118"
    "6dc7bd8d007e1a3677608cbf3940730"
)
STRATEGY_CONTEXT_LOAD_SHA256 = (
    "4865a77cc5940fb1230dad18339c05d9e"
    "8eefc4aadb535b21e52d16689dc4d14"
)
OBSERVATION_RECORD_SHA256 = (
    "c1e431a4de6af0e7ca9cc22a35b9b39"
    "aa889621713e5c1412db0e500a1022e69"
)
SCHEDULE_067_SOURCE_BODY_SHA256 = (
    "42458c1606168f3f9f9218b57522ee14"
    "c1361e4987088ee5af6064647cc7d936"
)
SCHEDULE_067_PG_PROC_SHA256 = (
    "1ec882400c5cb95e1743e7f8829327d6"
    "cf42e3bfb7ea68a64c70795a1d73731d"
)
SCHEDULE_071_SOURCE_BODY_SHA256 = (
    "7ed76e5653bfca7e5a741bb03c0a3325"
    "4ae05fca368fc5f2322ebbe65fc08186"
)
SCHEDULE_071_PG_PROC_SHA256 = (
    "e3b625acaa39cecc7ac41614ea3a3a12"
    "9968e19efd8cd8e1cdc41fedbb287aa9"
)


def source_file_function_body(path: Path) -> str:
    sql = path.read_text(encoding="utf-8")
    try:
        function_start = sql.index(FUNCTION_MARKER)
        body_start = sql.index("AS $function$\n", function_start)
        body_start += len("AS $function$\n")
        body_end = sql.index("\n$function$;", body_start)
    except ValueError as exc:
        raise ValueError("schedule_function_source_missing") from exc
    return sql[body_start:body_end]


def pg_proc_prosrc_sha256(source_file_body: str) -> str:
    return sha256(f"\n{source_file_body}\n".encode("utf-8")).hexdigest()


class N6AIShadowSchedule071SQLTest(unittest.TestCase):
    def test_forward_keeps_original_signature_and_exact_authority(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        self.assertEqual(sql.count("\nBEGIN;"), 1)
        self.assertEqual(sql.count("\nCOMMIT;"), 1)
        self.assertEqual(sql.count(FUNCTION_MARKER), 1)
        self.assertIn(
            "RETURNS jsonb\n"
            "LANGUAGE plpgsql\n"
            "STABLE\n"
            "SECURITY DEFINER\n"
            "SET search_path = pg_catalog",
            sql,
        )
        self.assertIn(
            "public.n6_ai_agent_shadow_schedule_preflight(text,date)\n"
            "OWNER TO ashare_v3_user;",
            sql,
        )
        self.assertIn(
            "FROM PUBLIC, n6_btrack_web, n6_virtual_executor, "
            "n6_quote_writer;",
            sql,
        )
        self.assertIn(
            "public.n6_ai_agent_shadow_schedule_preflight(text,date)\n"
            "TO n6_ai_agent;",
            sql,
        )
        self.assertNotIn("DROP FUNCTION", sql.upper())

    def test_forward_freezes_exact_nine_half_open_windows(self):
        body = source_file_function_body(MIGRATION)
        windows = (
            ("09:30:00", "09:35:00"),
            ("10:00:00", "10:05:00"),
            ("10:30:00", "10:35:00"),
            ("11:00:00", "11:05:00"),
            ("11:30:00", "11:31:00"),
            ("13:30:00", "13:35:00"),
            ("14:00:00", "14:05:00"),
            ("14:30:00", "14:35:00"),
            ("15:00:00", "15:01:00"),
        )
        self.assertEqual(body.count("WHEN local_now::time >="), 9)
        for lower, upper in windows:
            with self.subTest(lower=lower, upper=upper):
                self.assertIn(
                    f"WHEN local_now::time >= time '{lower}'\n"
                    f"     AND local_now::time < time '{upper}'",
                    body,
                )
                self.assertIn(
                    f"WHEN time '{lower}' THEN "
                    f"local_trade_date + time '{upper}'",
                    body,
                )
        self.assertNotIn("slot_start + interval '5 minutes'", body)
        self.assertIn(
            "'T' || pg_catalog.to_char(slot_start, 'HH24MI') || "+
            "'+0800'",
            body,
        )

    def test_forward_has_open_date_duplicate_and_budget_gates(self):
        body = source_file_function_body(MIGRATION)
        for relation in (
            "public.common_trade_calendar",
            "public.n6_ai_context_snapshot",
            "public.n6_ai_decision_run",
            "public.n6_ai_shadow_observation_run_audit",
        ):
            self.assertIn(relation, body)
        for status in (
            "open_slot_ready",
            "outside_shadow_slot",
            "not_open_trade_date",
            "already_processed",
            "daily_request_budget_exceeded",
            "daily_identity_probe_budget_exhausted",
            "daily_decision_call_budget_exhausted",
        ):
            self.assertIn(status, body)
        self.assertIn(
            "p_run_bucket IS DISTINCT FROM expected_run_bucket", body
        )
        self.assertIn("calendar.is_open = true", body)
        self.assertIn("identity_probe_succeeded = true", body)
        self.assertIn("decision_call_attempted = true", body)
        self.assertIn("daily_identity_probe_count > 9", body)
        self.assertIn("daily_decision_call_count > 9", body)
        self.assertIn(
            "daily_decision_call_count > daily_identity_probe_count", body
        )
        self.assertIn("daily_identity_probe_count >= 9", body)
        self.assertIn("daily_decision_call_count >= 9", body)
        self.assertIn("'identity_probe_remaining'", body)
        self.assertIn("'decision_call_remaining'", body)
        self.assertIsNone(
            re.search(
                r"\b(?:INSERT|UPDATE|DELETE|MERGE|TRUNCATE|LOCK)\b"
                r"|pg_(?:try_)?advisory",
                body,
                flags=re.IGNORECASE,
            )
        )

    def test_forward_locks_exact_dependency_and_catalog_hashes(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        for dependency_hash in (
            CONTEXT_LOAD_SHA256,
            CONTEXT_LOAD_V2_SHA256,
            STRATEGY_CONTEXT_LOAD_SHA256,
            OBSERVATION_RECORD_SHA256,
        ):
            self.assertEqual(sql.count(dependency_hash), 2)
        self.assertEqual(sql.count(SCHEDULE_067_PG_PROC_SHA256), 1)
        self.assertEqual(sql.count(SCHEDULE_071_PG_PROC_SHA256), 2)
        self.assertNotIn(SCHEDULE_071_SOURCE_BODY_SHA256, sql)
        self.assertEqual(
            sql.count("ARRAY['search_path=pg_catalog']::text[]"), 2
        )
        self.assertEqual(
            sql.count(
                "function_proc.provolatile::text = "
                "expected.expected_volatility"
            ),
            2,
        )
        self.assertEqual(sql.count("function_proc.proparallel = 'u'"), 2)
        self.assertEqual(sql.count("actual_sha <> expected.expected_sha"), 2)

    def test_forward_locks_distinct_source_and_pg_proc_hashes(self):
        body = source_file_function_body(MIGRATION)
        source_sha = sha256(body.encode("utf-8")).hexdigest()
        prosrc_sha = pg_proc_prosrc_sha256(body)
        self.assertEqual(source_sha, SCHEDULE_071_SOURCE_BODY_SHA256)
        self.assertEqual(prosrc_sha, SCHEDULE_071_PG_PROC_SHA256)
        self.assertNotEqual(source_sha, prosrc_sha)

    def test_rollback_restores_exact_067_body_without_drop(self):
        sql = ROLLBACK.read_text(encoding="utf-8")
        rollback_body = source_file_function_body(ROLLBACK)
        historical_body = source_file_function_body(HISTORICAL_067)
        self.assertEqual(sql.count("\nBEGIN;"), 1)
        self.assertEqual(sql.count("\nCOMMIT;"), 1)
        self.assertEqual(sql.count(FUNCTION_MARKER), 1)
        self.assertNotIn("DROP FUNCTION", sql.upper())
        self.assertEqual(rollback_body, historical_body)
        self.assertEqual(
            sha256(rollback_body.encode("utf-8")).hexdigest(),
            SCHEDULE_067_SOURCE_BODY_SHA256,
        )
        self.assertEqual(
            pg_proc_prosrc_sha256(rollback_body),
            SCHEDULE_067_PG_PROC_SHA256,
        )
        self.assertIsNone(
            re.search(
                r"\b(?:INSERT|UPDATE|DELETE|MERGE|TRUNCATE|LOCK)\b",
                sql,
                flags=re.IGNORECASE,
            )
        )

    def test_rollback_depends_on_071_and_preserves_070_and_062(self):
        sql = ROLLBACK.read_text(encoding="utf-8")
        self.assertEqual(sql.count(SCHEDULE_071_PG_PROC_SHA256), 1)
        self.assertEqual(sql.count(SCHEDULE_067_PG_PROC_SHA256), 1)
        for dependency_hash in (
            CONTEXT_LOAD_SHA256,
            CONTEXT_LOAD_V2_SHA256,
            STRATEGY_CONTEXT_LOAD_SHA256,
            OBSERVATION_RECORD_SHA256,
        ):
            self.assertEqual(sql.count(dependency_hash), 2)
        self.assertNotIn(SCHEDULE_071_SOURCE_BODY_SHA256, sql)
        self.assertEqual(
            sql.count("ARRAY['search_path=pg_catalog']::text[]"), 2
        )
        self.assertEqual(
            sql.count(
                "function_proc.provolatile::text = "
                "expected.expected_volatility"
            ),
            2,
        )
        self.assertEqual(sql.count("function_proc.proparallel = 'u'"), 2)
        self.assertEqual(sql.count("actual_sha <> expected.expected_sha"), 2)


if __name__ == "__main__":
    unittest.main()
