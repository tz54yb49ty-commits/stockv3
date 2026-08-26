import unittest

from ashare_v3.user.owner_principal_initialization import (
    AdminUserSummary,
    OwnerPrincipalPreflightSnapshot,
    build_parser,
    run_owner_principal_initialization,
)


class FakeRepository:
    def __init__(self, snapshot: OwnerPrincipalPreflightSnapshot) -> None:
        self.snapshot = snapshot
        self.insert_calls: list[dict[str, object]] = []

    def fetch_preflight_snapshot(self, seed_run_id: str) -> OwnerPrincipalPreflightSnapshot:
        self.last_seed_run_id = seed_run_id
        return self.snapshot

    def insert_seed_principals(self, *, seed_run_id: str, admin_user_id: int) -> dict[str, object]:
        self.insert_calls.append({"seed_run_id": seed_run_id, "admin_user_id": admin_user_id})
        return {
            "n6_principal_rows_inserted": 2,
            "n6_ai_user_rows_inserted": 0,
            "n6_principal_account_rows_inserted": 0,
            "n6_watchlist_ownership_rows_inserted": 0,
            "n6_strategy_rows_inserted": 0,
            "inserted_principals": [
                {"principal_id": 10, "principal_type": "admin", "owner_user_id": admin_user_id},
                {"principal_id": 11, "principal_type": "system", "owner_user_id": None},
            ],
        }


class N6OwnerPrincipalInitializationTest(unittest.TestCase):
    def test_parser_requires_execute_and_user_confirmed_flags(self) -> None:
        parser = build_parser()
        option_strings = {option for action in parser._actions for option in action.option_strings}

        self.assertIn("--execute", option_strings)
        self.assertIn("--user-confirmed", option_strings)
        self.assertIn("--seed-run-id", option_strings)
        self.assertIn("--contract-path", option_strings)

    def test_missing_execute_blocks_before_repository_write(self) -> None:
        repo = FakeRepository(passing_snapshot())

        report = run_owner_principal_initialization(
            repository=repo,
            seed_run_id="n6_phase2_owner_principal_initialization_20260605_v1",
            execute=False,
            user_confirmed=True,
            contract_path="docs/N6_PHASE2_OWNER_PRINCIPAL_INITIALIZATION_execute_contract.json",
        )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("missing_execute_flag", report["blockers"])
        self.assertEqual(repo.insert_calls, [])

    def test_missing_user_confirmed_blocks_before_repository_write(self) -> None:
        repo = FakeRepository(passing_snapshot())

        report = run_owner_principal_initialization(
            repository=repo,
            seed_run_id="n6_phase2_owner_principal_initialization_20260605_v1",
            execute=True,
            user_confirmed=False,
            contract_path="docs/N6_PHASE2_OWNER_PRINCIPAL_INITIALIZATION_execute_contract.json",
        )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("missing_user_confirmed_flag", report["blockers"])
        self.assertEqual(repo.insert_calls, [])

    def test_preflight_blocks_duplicate_seed_without_write(self) -> None:
        snapshot = passing_snapshot()
        snapshot.seed_scoped_counts["n6_principal"] = 2
        repo = FakeRepository(snapshot)

        report = run_owner_principal_initialization(
            repository=repo,
            seed_run_id="n6_phase2_owner_principal_initialization_20260605_v1",
            execute=True,
            user_confirmed=True,
            contract_path="docs/N6_PHASE2_OWNER_PRINCIPAL_INITIALIZATION_execute_contract.json",
        )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("seed_scoped_baseline_nonzero", report["blockers"])
        self.assertEqual(repo.insert_calls, [])

    def test_execute_writes_only_two_principal_rows(self) -> None:
        repo = FakeRepository(passing_snapshot())

        report = run_owner_principal_initialization(
            repository=repo,
            seed_run_id="n6_phase2_owner_principal_initialization_20260605_v1",
            execute=True,
            user_confirmed=True,
            contract_path="docs/N6_PHASE2_OWNER_PRINCIPAL_INITIALIZATION_execute_contract.json",
        )

        self.assertEqual(report["result"], "EXECUTED")
        self.assertEqual(len(repo.insert_calls), 1)
        self.assertEqual(report["planned_rows"]["n6_principal"], 2)
        self.assertEqual(report["planned_rows"]["n6_principal_account"], 0)
        self.assertEqual(report["planned_rows"]["n6_ai_user"], 0)
        self.assertEqual(report["planned_rows"]["n6_watchlist_ownership"], 0)
        self.assertEqual(report["planned_rows"]["n6_strategy"], 0)
        self.assertEqual(report["write_result"]["n6_principal_rows_inserted"], 2)
        self.assertEqual(report["write_result"]["n6_principal_account_rows_inserted"], 0)
        self.assertEqual(report["write_result"]["n6_ai_user_rows_inserted"], 0)

    def test_preflight_blocks_if_readonly_role_has_base_table_grant(self) -> None:
        snapshot = passing_snapshot()
        snapshot.readonly_role_base_table_grants = [{"table_name": "n6_principal", "privilege_type": "SELECT"}]
        repo = FakeRepository(snapshot)

        report = run_owner_principal_initialization(
            repository=repo,
            seed_run_id="n6_phase2_owner_principal_initialization_20260605_v1",
            execute=True,
            user_confirmed=True,
            contract_path="docs/N6_PHASE2_OWNER_PRINCIPAL_INITIALIZATION_execute_contract.json",
        )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("readonly_role_has_base_table_grants", report["blockers"])
        self.assertEqual(repo.insert_calls, [])


def passing_snapshot() -> OwnerPrincipalPreflightSnapshot:
    return OwnerPrincipalPreflightSnapshot(
        table_exists={
            "n6_principal": True,
            "n6_ai_user": True,
            "n6_principal_account": True,
            "n6_watchlist_ownership": True,
            "n6_strategy": True,
        },
        view_exists={
            "v_n6_stock_condition_display_basis": True,
            "v_n6_index_condition_display_basis": True,
            "v_n6_board_condition_display_basis": True,
            "v_n6_index_membership_fact": True,
            "v_n6_board_membership_fact": True,
        },
        table_counts={
            "n6_principal": 0,
            "n6_ai_user": 0,
            "n6_principal_account": 0,
            "n6_watchlist_ownership": 0,
            "n6_strategy": 0,
        },
        seed_scoped_counts={
            "n6_principal": 0,
            "n6_ai_user": 0,
            "n6_principal_account": 0,
            "n6_watchlist_ownership": 0,
            "n6_strategy": 0,
        },
        admin_users=[AdminUserSummary(user_id=1, login_name="admin", role="admin", status="active")],
        readonly_role_exists=True,
        readonly_role_view_grants=[
            {"table_name": "v_n6_stock_condition_display_basis", "privilege_type": "SELECT"},
            {"table_name": "v_n6_index_condition_display_basis", "privilege_type": "SELECT"},
            {"table_name": "v_n6_board_condition_display_basis", "privilege_type": "SELECT"},
            {"table_name": "v_n6_index_membership_fact", "privilege_type": "SELECT"},
            {"table_name": "v_n6_board_membership_fact", "privilege_type": "SELECT"},
        ],
        readonly_role_base_table_grants=[],
        view_trigger_count=0,
        duplicate_admin_principal_count=0,
        duplicate_system_principal_count=0,
        active_ai_without_profile_count=0,
        outbox_ref_count=0,
        side_effect_ref_count=0,
    )


if __name__ == "__main__":
    unittest.main()
