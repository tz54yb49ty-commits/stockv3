"""Frozen historical evidence for the superseded 067 four-slot contract."""

from hashlib import sha256
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/067_n6_ai_shadow_schedule_preflight.sql"
ROLLBACK = ROOT / "sql/067_n6_ai_shadow_schedule_preflight_rollback.sql"
CONTEXT_MIGRATION = ROOT / "sql/058_n6_ai_context_memory_hash_contract.sql"
OBSERVATION_MIGRATION = (
    ROOT / "sql/062_n6_ai_shadow_observation_run_audit.sql"
)
CONTRACT = (
    ROOT
    / "docs/N6_AI_SHADOW_OPEN_TRADE_DATE_FOUR_SLOTS_067_CONTRACT.json"
)
CONTEXT_SOURCE_FILE_BODY_SHA256 = (
    "a61f16e16d7b6011571fd7336b158fe8"
    "992b3876eaf88acbc6ff558ba2cdba77"
)
CONTEXT_PG_PROC_PROSRC_SHA256 = (
    "df2afc2d7583effd10905ed478ab0df7"
    "e2147a854784bfc1b6087ca6d9b04681"
)
OBSERVATION_SOURCE_FILE_BODY_SHA256 = (
    "61b4ac467e5607ee52c94700859470f9"
    "2a0b7ba1e79d2ea7f7e4281088621a81"
)
OBSERVATION_PG_PROC_PROSRC_SHA256 = (
    "c1e431a4de6af0e7ca9cc22a35b9b39"
    "aa889621713e5c1412db0e500a1022e69"
)
SCHEDULE_SOURCE_FILE_BODY_SHA256 = (
    "42458c1606168f3f9f9218b57522ee14"
    "c1361e4987088ee5af6064647cc7d936"
)
SCHEDULE_PG_PROC_PROSRC_SHA256 = (
    "1ec882400c5cb95e1743e7f8829327d6"
    "cf42e3bfb7ea68a64c70795a1d73731d"
)


def source_file_function_body(path: Path, marker: str) -> str:
    sql = path.read_text(encoding="utf-8")
    try:
        function_start = sql.index(marker)
        body_start = sql.index("AS $function$\n", function_start)
        body_start += len("AS $function$\n")
        body_end = sql.index("\n$function$;", body_start)
    except ValueError as exc:
        raise ValueError("function_source_authority_missing") from exc
    return sql[body_start:body_end]


class N6AIShadowSchedule067HistoricalTest(unittest.TestCase):
    def test_migration_freezes_four_windows_and_read_only_authority(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        self.assertEqual(sql.count("\nBEGIN;"), 1)
        self.assertEqual(sql.count("\nCOMMIT;"), 1)
        self.assertIn("LANGUAGE plpgsql\nSTABLE\nSECURITY DEFINER", sql)
        self.assertIn("SET search_path = pg_catalog", sql)
        self.assertIn("OWNER TO ashare_v3_user", sql)
        self.assertIn("TO n6_ai_agent;", sql)
        self.assertIn(
            "FROM PUBLIC, n6_btrack_web, n6_virtual_executor, "
            "n6_quote_writer;",
            sql,
        )
        for status in (
            "open_slot_ready",
            "outside_shadow_slot",
            "not_open_trade_date",
            "already_processed",
        ):
            self.assertIn(status, sql)
        for lower, upper in (
            ("10:25:00", "10:30:00"),
            ("11:25:00", "11:30:00"),
            ("13:55:00", "14:00:00"),
            ("14:55:00", "15:00:00"),
        ):
            self.assertIn(f"time '{lower}'", sql)
            self.assertIn(f"time '{upper}'", sql)

        body = source_file_function_body(
            MIGRATION,
            "CREATE OR REPLACE FUNCTION\n"
            "public.n6_ai_agent_shadow_schedule_preflight(",
        )
        self.assertEqual(
            sha256(body.encode("utf-8")).hexdigest(),
            SCHEDULE_SOURCE_FILE_BODY_SHA256,
        )
        self.assertIsNone(
            re.search(
                r"\b(?:INSERT|UPDATE|DELETE|MERGE|TRUNCATE|LOCK)\b"
                r"|pg_(?:try_)?advisory",
                body,
                flags=re.IGNORECASE,
            )
        )

    def test_source_file_and_pg_proc_hashes_remain_frozen(self):
        cases = (
            (
                CONTEXT_MIGRATION,
                "CREATE OR REPLACE FUNCTION "
                "public.n6_ai_agent_context_load_v2(",
                CONTEXT_SOURCE_FILE_BODY_SHA256,
                CONTEXT_PG_PROC_PROSRC_SHA256,
            ),
            (
                OBSERVATION_MIGRATION,
                "CREATE OR REPLACE FUNCTION\n"
                "public.n6_ai_shadow_observation_run_audit_record(",
                OBSERVATION_SOURCE_FILE_BODY_SHA256,
                OBSERVATION_PG_PROC_PROSRC_SHA256,
            ),
            (
                MIGRATION,
                "CREATE OR REPLACE FUNCTION\n"
                "public.n6_ai_agent_shadow_schedule_preflight(",
                SCHEDULE_SOURCE_FILE_BODY_SHA256,
                SCHEDULE_PG_PROC_PROSRC_SHA256,
            ),
        )
        for path, marker, source_body_sha, pg_proc_prosrc_sha in cases:
            with self.subTest(path=path.name):
                body = source_file_function_body(path, marker)
                self.assertEqual(
                    sha256(body.encode("utf-8")).hexdigest(),
                    source_body_sha,
                )
                self.assertEqual(
                    sha256(f"\n{body}\n".encode("utf-8")).hexdigest(),
                    pg_proc_prosrc_sha,
                )
                self.assertNotEqual(source_body_sha, pg_proc_prosrc_sha)

        with self.assertRaisesRegex(
            ValueError, "function_source_authority_missing"
        ):
            source_file_function_body(
                MIGRATION,
                "CREATE OR REPLACE FUNCTION public.missing_authority(",
            )

    def test_forward_and_rollback_lock_pg_proc_hashes(self):
        pg_proc_hashes = (
            CONTEXT_PG_PROC_PROSRC_SHA256,
            OBSERVATION_PG_PROC_PROSRC_SHA256,
            SCHEDULE_PG_PROC_PROSRC_SHA256,
        )
        source_file_hashes = (
            CONTEXT_SOURCE_FILE_BODY_SHA256,
            OBSERVATION_SOURCE_FILE_BODY_SHA256,
            SCHEDULE_SOURCE_FILE_BODY_SHA256,
        )
        for path in (MIGRATION, ROLLBACK):
            sql = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                for pg_proc_hash in pg_proc_hashes:
                    self.assertEqual(sql.count(pg_proc_hash), 1)
                for source_file_hash in source_file_hashes:
                    self.assertNotIn(source_file_hash, sql)

    def test_rollback_is_exact_drop_only(self):
        sql = ROLLBACK.read_text(encoding="utf-8")
        self.assertEqual(sql.count("\nBEGIN;"), 1)
        self.assertEqual(sql.count("\nCOMMIT;"), 1)
        self.assertEqual(
            sql.count(
                "DROP FUNCTION\n"
                "public.n6_ai_agent_shadow_schedule_preflight(text,date);"
            ),
            1,
        )
        self.assertIsNone(
            re.search(
                r"\b(?:INSERT|UPDATE|DELETE|MERGE|TRUNCATE)\b",
                sql,
                flags=re.IGNORECASE,
            )
        )

    def test_contract_remains_historical_and_not_current_runtime(self):
        payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(
            payload["schedule_policy_version"],
            "n6_ai_shadow_open_trade_date_four_slots_067_v1",
        )
        self.assertEqual(
            [item["slot"] for item in payload["deepseek_slots"]],
            ["10:25", "11:25", "13:55", "14:55"],
        )
        self.assertEqual(
            payload["provider_budget"][
                "maximum_identity_probes_per_open_trade_date"
            ],
            4,
        )
        self.assertEqual(
            payload["provider_budget"][
                "maximum_decision_calls_per_open_trade_date"
            ],
            4,
        )
        self.assertFalse(
            payload["deployment"]["authorized_by_this_contract"]
        )
        self.assertTrue(
            payload["idempotency_limit"][
                "simultaneous_manual_invocations_are_not_strongly_serializable"
            ]
        )


if __name__ == "__main__":
    unittest.main()
