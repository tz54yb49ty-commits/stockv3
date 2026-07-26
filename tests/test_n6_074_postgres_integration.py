from __future__ import annotations

import os
import unittest

import psycopg
from psycopg.rows import dict_row


@unittest.skipUnless(
    os.environ.get("ASHARE_V3_TEST_PG_DISPOSABLE") == "1" and os.environ.get("ASHARE_V3_TEST_PG_SERVICE"),
    "requires an explicitly marked disposable PostgreSQL service with migration 074 installed",
)
class ProvisioningPostgresIntegrationTest(unittest.TestCase):
    def test_function_authority_is_fixed_in_disposable_database(self) -> None:
        service = os.environ["ASHARE_V3_TEST_PG_SERVICE"]
        with psycopg.connect(
            service=service,
            connect_timeout=10,
            row_factory=dict_row,
            options="-c default_transaction_read_only=on",
        ) as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY")
                cur.execute(
                    """
                    SELECT current_database() AS database_name,
                           p.prosecdef,
                           p.proconfig,
                           pg_get_userbyid(p.proowner) AS owner_name,
                           has_function_privilege('public', p.oid, 'EXECUTE') AS public_execute
                    FROM pg_proc p
                    WHERE p.oid = to_regprocedure('public.n6_provision_human_virtual_account(bigint)')
                    """
                )
                row = cur.fetchone()
        self.assertIsNotNone(row)
        self.assertNotEqual(row["database_name"], "ashare_v3", "live database is never a disposable test target")
        self.assertTrue(row["prosecdef"])
        self.assertEqual(row["owner_name"], "ashare_v3_user")
        self.assertIn("search_path=pg_catalog", row["proconfig"])
        self.assertFalse(row["public_execute"])


if __name__ == "__main__":
    unittest.main()
