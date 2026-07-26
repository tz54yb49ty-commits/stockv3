from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
FORWARD = ROOT / "sql/065_n6_btrack_current_date_batch_scope_fix.sql"
ROLLBACK = (
    ROOT / "sql/065_n6_btrack_current_date_batch_scope_fix_rollback.sql"
)
CONTRACT = (
    ROOT / "docs/N6_B_TRACK_CURRENT_DATE_BATCH_SCOPE_FIX_065_CONTRACT.json"
)


class N6065CurrentDateBatchScopeFixTest(unittest.TestCase):
    def test_forward_is_exact_current_date_rewrite(self) -> None:
        text = FORWARD.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("-- N6 B-track"))
        self.assertIn("BEGIN;", text)
        self.assertTrue(text.rstrip().endswith("COMMIT;"))
        self.assertIn(
            "WHERE basis.for_trade_date::text = current_trade_date", text
        )
        self.assertIn(
            "065_helper_batch_scope_rewrite_mismatch", text
        )
        self.assertIn(
            "n6_btrack_current_date_batch_scope_fix_065_v1", text
        )
        self.assertIn(
            "a12ae3e8e8040ecb7459d08c69d263feb578b10b86d150fdb11488f6b7779d49",
            text,
        )
        self.assertIn(
            "2229ac23d823d0f27a08ba7aae18ca682594bfc27515b7a3b10b2a5673023a17",
            text,
        )
        for forbidden in (
            "INSERT INTO",
            "UPDATE public.",
            "DELETE FROM",
            "DROP TABLE",
            "ALTER TABLE",
        ):
            self.assertNotIn(forbidden, text)

    def test_rollback_restores_exact_064_bodies(self) -> None:
        text = ROLLBACK.read_text(encoding="utf-8")
        self.assertIn(
            "SELECT max(current_basis.for_trade_date)", text
        )
        self.assertIn(
            "n6_btrack_trade_date_all_day_buy_064_v1", text
        )
        self.assertIn(
            "f79363123d2e822666dad722d3fe61860855437f73d0ac8def81e6b865cce8cb",
            text,
        )
        self.assertIn(
            "beb59b8a4a19fa1c1d0d0508d0c83fe726774581a1e2966442ce5cecd91b5e9c",
            text,
        )
        self.assertTrue(text.rstrip().endswith("COMMIT;"))
        self.assertNotIn("DROP FUNCTION", text)

    def test_contract_freezes_n6_only_boundary(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(contract["layer_role"], "N6_user")
        self.assertFalse(contract["interfaces_changed"])
        self.assertFalse(contract["tables_changed"])
        self.assertFalse(contract["business_rows_written_by_migration"])
        self.assertFalse(contract["real_broker_connected"])
        self.assertEqual(
            contract["behavior"]["executor_policy_version"],
            "n6_btrack_current_date_batch_scope_fix_065_v1",
        )


if __name__ == "__main__":
    unittest.main()
