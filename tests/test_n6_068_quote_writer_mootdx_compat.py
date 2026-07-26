"""Static contract tests for N6 quote writer Mootdx compatibility 068."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
FORWARD_PATH = ROOT / "sql/068_n6_quote_writer_mootdx_compat.sql"
ROLLBACK_PATH = ROOT / "sql/068_n6_quote_writer_mootdx_compat_rollback.sql"
CONTRACT_PATH = ROOT / "docs/N6_QUOTE_WRITER_MOOTDX_COMPAT_068_CONTRACT.json"
FORWARD = FORWARD_PATH.read_text(encoding="utf-8")
ROLLBACK = ROLLBACK_PATH.read_text(encoding="utf-8")
CONTRACT = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _function_source(sql: str) -> str:
    match = re.search(
        r"CREATE OR REPLACE FUNCTION public\.n6_quote_writer_scope\(.*?"
        r"AS \$function\$(.*?)\$function\$;",
        sql,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError("missing n6_quote_writer_scope function")
    return match.group(1)


class N6068QuoteWriterMootdxCompatTests(unittest.TestCase):
    def test_contract_keeps_shared_n3n6q_frozen(self) -> None:
        self.assertEqual(CONTRACT["layer_role"], "N6_user")
        self.assertTrue(CONTRACT["n3n6q_boundary"]["shared_contract_frozen"])
        self.assertFalse(
            CONTRACT["n3n6q_boundary"]["shared_source_files_modified"]
        )
        self.assertTrue(CONTRACT["n3n6q_boundary"]["n6_owned_adapter_only"])

    def test_confirmed_manual_current_scope_is_the_only_expiry_bypass(self) -> None:
        source = _function_source(FORWARD)
        self.assertIn("proposal.proposal_status = 'pending'", source)
        self.assertIn("proposal.proposal_status = 'confirmed'", source)
        self.assertIn("proposal.expires_at > pg_catalog.clock_timestamp()", source)
        self.assertIn("n6_btrack_manual_signal_buy_current_scope", source)
        self.assertIn("a.principal_type IN ('admin', 'human_user')", source)
        self.assertIn("proposal.actor_ai_user_id IS NULL", source)
        self.assertIn("proposal.source_ai_decision_id IS NULL", source)
        self.assertNotIn("n6_btrack_manual_signal_buy_current_scope", _function_source(ROLLBACK))
        self.assertTrue(
            CONTRACT["quote_scope"][
                "human_confirmed_current_day_manual_signal_buy_survives_expiry"
            ]
        )
        self.assertTrue(
            CONTRACT["quote_scope"]["ai_confirmed_proposal_requires_unexpired"]
        )

    def test_forward_and_rollback_are_definition_and_acl_pinned(self) -> None:
        forward_source_sha = sha256(
            _function_source(FORWARD).encode("utf-8")
        ).hexdigest()
        rollback_source_sha = sha256(
            _function_source(ROLLBACK).encode("utf-8")
        ).hexdigest()
        self.assertEqual(
            forward_source_sha,
            "856bfc57439d85e9f1cab84a93f25dfcf4e4a50274e30c60cfac0e7110b527b1",
        )
        self.assertEqual(
            rollback_source_sha,
            "205c61bdcabb966203eb022f61666d8c79a090ab6ac12bcf7a0e8bfb9da0fe72",
        )
        self.assertIn(forward_source_sha, ROLLBACK)
        self.assertIn(rollback_source_sha, FORWARD)
        for sql in (FORWARD, ROLLBACK):
            self.assertIn("SECURITY DEFINER", sql)
            self.assertIn("SET search_path = pg_catalog", sql)
            self.assertIn("FROM PUBLIC, n6_btrack_web, n6_ai_agent", sql)
            self.assertIn("TO n6_quote_writer", sql)
            self.assertIn("pg_catalog.aclexplode", sql)
            self.assertIn("acl.grantee = 0", sql)
            self.assertNotIn("has_function_privilege('PUBLIC'", sql)
            self.assertNotIn("pg_catalog.coalesce", sql)

    def test_migration_has_no_business_row_dml(self) -> None:
        for sql in (FORWARD, ROLLBACK):
            for forbidden in (
                "INSERT INTO public.n6_",
                "UPDATE public.n6_",
                "DELETE FROM public.n6_",
                "TRUNCATE ",
            ):
                self.assertNotIn(forbidden, sql)
        self.assertFalse(CONTRACT["migration"]["business_row_dml"])
        self.assertFalse(CONTRACT["migration"]["deployment_authorized_by_this_contract"])

    def test_proposals_5_6_7_require_explicit_deployment_gate(self) -> None:
        self.assertEqual(CONTRACT["proposal_impact"]["proposal_ids"], [5, 6, 7])
        self.assertTrue(
            CONTRACT["proposal_impact"]["deployment_requires_explicit_authorization"]
        )
        self.assertFalse(
            CONTRACT["proposal_impact"]["automatic_execution_authorized_by_this_contract"]
        )


if __name__ == "__main__":
    unittest.main()
