from decimal import Decimal
import json
import tempfile
import unittest
from pathlib import Path

from ashare_v3.user.virtual_account_seed import (
    PHASE3_TABLES,
    PLANNED_ROWS,
    AdminPrincipalSummary,
    VirtualAccountSeedPreflightSnapshot,
    build_parser,
    run_virtual_account_seed,
    validate_contract_artifact,
)


class FakeVirtualAccountSeedRepository:
    def __init__(self, snapshot: VirtualAccountSeedPreflightSnapshot) -> None:
        self.snapshot = snapshot
        self.fetch_calls = 0
        self.commit_calls = 0
        self.committed_args: dict[str, object] | None = None

    def fetch_preflight_snapshot(self, seed_run_id: str) -> VirtualAccountSeedPreflightSnapshot:
        self.fetch_calls += 1
        self.snapshot.seed_run_id = seed_run_id
        return self.snapshot

    def commit_seed(
        self,
        *,
        seed_run_id: str,
        admin_principal_id: int,
        initial_cash: Decimal,
        trade_date: int,
    ) -> dict[str, object]:
        self.commit_calls += 1
        self.committed_args = {
            "seed_run_id": seed_run_id,
            "admin_principal_id": admin_principal_id,
            "initial_cash": initial_cash,
            "trade_date": trade_date,
        }
        return {
            "committed": True,
            "n6_virtual_account_rows_inserted": 1,
            "n6_virtual_cash_ledger_rows_inserted": 1,
            "n6_virtual_cash_snapshot_rows_inserted": 1,
            "n6_virtual_order_rows_inserted": 0,
            "n6_virtual_trade_rows_inserted": 0,
            "n6_virtual_position_rows_inserted": 0,
            "n6_virtual_position_event_rows_inserted": 0,
            "n6_virtual_pnl_snapshot_rows_inserted": 0,
            "virtual_account_id": 101,
            "cash_ledger_id": 201,
            "cash_snapshot_id": 301,
            "current_cash_snapshot_id_updated": True,
        }


class N6VirtualAccountSeedTest(unittest.TestCase):
    def test_parser_requires_execute_and_user_confirmed_flags(self) -> None:
        parser = build_parser()
        option_strings = {option for action in parser._actions for option in action.option_strings}

        self.assertIn("--execute", option_strings)
        self.assertIn("--user-confirmed", option_strings)
        self.assertIn("--seed-run-id", option_strings)
        self.assertIn("--contract-path", option_strings)

    def test_missing_execute_blocks_before_repository_read_or_write(self) -> None:
        repo = FakeVirtualAccountSeedRepository(passing_snapshot())

        report = run_virtual_account_seed(
            repository=repo,
            seed_run_id="n6_phase3_virtual_account_seed_20260605_v1",
            execute=False,
            user_confirmed=True,
            contract_path=contract_path(),
        )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("missing_execute_flag", report["blockers"])
        self.assertFalse(report["database_written"])
        self.assertEqual(repo.fetch_calls, 0)
        self.assertEqual(repo.commit_calls, 0)

    def test_missing_user_confirmed_blocks_before_repository_read_or_write(self) -> None:
        repo = FakeVirtualAccountSeedRepository(passing_snapshot())

        report = run_virtual_account_seed(
            repository=repo,
            seed_run_id="n6_phase3_virtual_account_seed_20260605_v1",
            execute=True,
            user_confirmed=False,
            contract_path=contract_path(),
        )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("missing_user_confirmed_flag", report["blockers"])
        self.assertFalse(report["database_written"])
        self.assertEqual(repo.fetch_calls, 0)
        self.assertEqual(repo.commit_calls, 0)

    def test_contract_requires_exact_planned_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "contract.json"
            path.write_text(
                json.dumps(
                    {
                        "result": "CONTRACT_PASS",
                        "seed_run_id": "n6_phase3_virtual_account_seed_20260605_v1",
                        "planned_rows": {**PLANNED_ROWS, "n6_virtual_order": 1},
                    }
                ),
                encoding="utf-8",
            )

            blockers = validate_contract_artifact(str(path), "n6_phase3_virtual_account_seed_20260605_v1")

        self.assertIn("contract_planned_rows_mismatch", blockers)

    def test_preflight_blocks_nonzero_phase3_baseline(self) -> None:
        snapshot = passing_snapshot()
        snapshot.table_counts["n6_virtual_cash_ledger"] = 1
        repo = FakeVirtualAccountSeedRepository(snapshot)

        report = run_virtual_account_seed(
            repository=repo,
            seed_run_id="n6_phase3_virtual_account_seed_20260605_v1",
            execute=True,
            user_confirmed=True,
            contract_path=contract_path(),
        )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("phase3_table_baseline_nonzero", report["blockers"])
        self.assertEqual(repo.commit_calls, 0)

    def test_preflight_blocks_missing_admin_principal(self) -> None:
        snapshot = passing_snapshot()
        snapshot.admin_principals = []
        repo = FakeVirtualAccountSeedRepository(snapshot)

        report = run_virtual_account_seed(
            repository=repo,
            seed_run_id="n6_phase3_virtual_account_seed_20260605_v1",
            execute=True,
            user_confirmed=True,
            contract_path=contract_path(),
        )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("admin_principal_not_exactly_one", report["blockers"])
        self.assertEqual(repo.commit_calls, 0)

    def test_preflight_blocks_existing_admin_virtual_account(self) -> None:
        snapshot = passing_snapshot()
        snapshot.admin_active_virtual_account_count = 1
        repo = FakeVirtualAccountSeedRepository(snapshot)

        report = run_virtual_account_seed(
            repository=repo,
            seed_run_id="n6_phase3_virtual_account_seed_20260605_v1",
            execute=True,
            user_confirmed=True,
            contract_path=contract_path(),
        )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("admin_active_virtual_account_exists", report["blockers"])
        self.assertEqual(repo.commit_calls, 0)

    def test_execute_commits_only_account_ledger_snapshot(self) -> None:
        repo = FakeVirtualAccountSeedRepository(passing_snapshot())

        report = run_virtual_account_seed(
            repository=repo,
            seed_run_id="n6_phase3_virtual_account_seed_20260605_v1",
            execute=True,
            user_confirmed=True,
            contract_path=contract_path(),
        )

        self.assertEqual(report["result"], "EXECUTED")
        self.assertEqual(report["preflight_result"], "PREFLIGHT_PASS")
        self.assertTrue(report["database_written"])
        self.assertEqual(repo.commit_calls, 1)
        self.assertEqual(report["planned_rows"], PLANNED_ROWS)
        self.assertEqual(report["write_result"]["n6_virtual_account_rows_inserted"], 1)
        self.assertEqual(report["write_result"]["n6_virtual_cash_ledger_rows_inserted"], 1)
        self.assertEqual(report["write_result"]["n6_virtual_cash_snapshot_rows_inserted"], 1)
        self.assertEqual(report["write_result"]["n6_virtual_order_rows_inserted"], 0)
        self.assertEqual(report["write_result"]["n6_virtual_trade_rows_inserted"], 0)
        self.assertEqual(report["write_result"]["n6_virtual_position_rows_inserted"], 0)
        self.assertEqual(report["write_result"]["n6_virtual_pnl_snapshot_rows_inserted"], 0)
        self.assertTrue(report["write_result"]["current_cash_snapshot_id_updated"])
        self.assertEqual(repo.committed_args["initial_cash"], Decimal("1000000.0000"))

    def test_forbidden_side_effects_remain_false(self) -> None:
        repo = FakeVirtualAccountSeedRepository(passing_snapshot())

        report = run_virtual_account_seed(
            repository=repo,
            seed_run_id="n6_phase3_virtual_account_seed_20260605_v1",
            execute=True,
            user_confirmed=True,
            contract_path=contract_path(),
        )

        self.assertFalse(report["outbox_consumed_or_updated"])
        self.assertFalse(report["worker_started"])
        self.assertFalse(report["delivery_push_voice_mobile_sim_position_real_trade"])

    def test_rollback_sql_hard_fails_before_first_delete(self) -> None:
        sql = Path("sql/N6_phase3_virtual_account_seed_rollback.sql").read_text(encoding="utf-8")
        upper = sql.upper()
        first_delete = upper.find("DELETE FROM")
        first_raise = upper.find("RAISE EXCEPTION")

        self.assertGreaterEqual(first_delete, 0)
        self.assertGreaterEqual(first_raise, 0)
        self.assertLess(first_raise, first_delete)
        self.assertNotIn("CASCADE", upper)
        self.assertNotIn("DROP TABLE", upper)
        for table in (
            "n6_virtual_order",
            "n6_virtual_trade",
            "n6_virtual_position",
            "n6_virtual_position_event",
            "n6_virtual_pnl_snapshot",
        ):
            self.assertIn(table, sql)


def contract_path() -> str:
    tmp = Path(tempfile.mkdtemp()) / "contract.json"
    tmp.write_text(
        json.dumps(
            {
                "result": "CONTRACT_PASS",
                "seed_run_id": "n6_phase3_virtual_account_seed_20260605_v1",
                "planned_rows": PLANNED_ROWS,
            }
        ),
        encoding="utf-8",
    )
    return str(tmp)


def passing_snapshot() -> VirtualAccountSeedPreflightSnapshot:
    return VirtualAccountSeedPreflightSnapshot(
        seed_run_id="n6_phase3_virtual_account_seed_20260605_v1",
        table_exists={table: True for table in PHASE3_TABLES},
        table_counts={table: 0 for table in PHASE3_TABLES},
        seed_scoped_counts={table: 0 for table in PHASE3_TABLES},
        admin_principals=[
            AdminPrincipalSummary(
                principal_id=10,
                principal_type="admin",
                principal_status="active",
                owner_user_id=1,
                login_name="admin",
            )
        ],
        system_principal_count=1,
        admin_active_virtual_account_count=0,
        readonly_role_exists=True,
        readonly_role_view_select_only=True,
        readonly_role_base_table_grants=[],
        view_trigger_count=0,
        outbox_ref_count=0,
        worker_or_downstream_ref_count=0,
    )


if __name__ == "__main__":
    unittest.main()
