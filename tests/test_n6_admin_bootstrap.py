import unittest

from ashare_v3.user.admin_bootstrap import (
    EXPECTED_N5_OUTBOX_COUNTS,
    AdminAccountSummary,
    HashResult,
    PreflightSnapshot,
    build_parser,
    hash_password,
    run_admin_bootstrap,
    validate_password,
)


class FakeRepository:
    def __init__(self, snapshot: PreflightSnapshot) -> None:
        self.snapshot = snapshot
        self.insert_calls: list[dict[str, object]] = []
        self.outbox_after_insert = dict(snapshot.n5_outbox_counts)

    def fetch_preflight_snapshot(self) -> PreflightSnapshot:
        return self.snapshot

    def insert_admin_and_default_profile(
        self,
        *,
        password_hash: str,
        password_hash_algo: str,
    ) -> dict[str, object]:
        self.insert_calls.append(
            {
                "password_hash": password_hash,
                "password_hash_algo": password_hash_algo,
                "tables": ["user_account", "user_filter_profile"],
            }
        )
        self.snapshot = empty_snapshot(
            user_account_count=1,
            user_filter_profile_count=1,
            admin_accounts=[AdminAccountSummary(user_id=1, login_name="admin", role="admin", status="active")],
        )
        self.snapshot.n5_outbox_counts = dict(self.outbox_after_insert)
        return {
            "user_account_rows_inserted": 1,
            "user_filter_profile_rows_inserted": 1,
            "user_session_rows_inserted": 0,
            "user_projection_rows_inserted": 0,
            "user_notification_rows_inserted": 0,
            "user_sim_rows_inserted": 0,
        }


class FixedHasher:
    def __call__(self, password: str) -> HashResult:
        return HashResult(password_hash="redacted-test-hash", password_hash_algo="argon2id")


def test_password() -> str:
    return "p" * 12


class N6AdminBootstrapTest(unittest.TestCase):
    def test_parser_has_no_password_argument(self) -> None:
        parser = build_parser()
        option_strings = {
            option
            for action in parser._actions
            for option in action.option_strings
        }

        self.assertIn("--execute", option_strings)
        self.assertIn("--user-confirmed", option_strings)
        self.assertNotIn("--password", option_strings)
        self.assertNotIn("--admin-password", option_strings)

    def test_missing_execute_blocks_without_writes(self) -> None:
        repo = FakeRepository(empty_snapshot())

        report = run_admin_bootstrap(
            repository=repo,
            execute=False,
            user_confirmed=True,
            password=test_password(),
            hasher=FixedHasher(),
        )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("missing_execute_flag", report["blockers"])
        self.assertEqual(repo.insert_calls, [])

    def test_missing_user_confirmed_blocks_without_writes(self) -> None:
        repo = FakeRepository(empty_snapshot())

        report = run_admin_bootstrap(
            repository=repo,
            execute=True,
            user_confirmed=False,
            password=test_password(),
            hasher=FixedHasher(),
        )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("missing_user_confirmed_flag", report["blockers"])
        self.assertEqual(repo.insert_calls, [])

    def test_missing_password_source_blocks_final_gate(self) -> None:
        repo = FakeRepository(empty_snapshot())

        report = run_admin_bootstrap(
            repository=repo,
            execute=True,
            user_confirmed=True,
            password=None,
            hasher=FixedHasher(),
        )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("missing_password_source", report["blockers"])
        self.assertEqual(repo.insert_calls, [])

    def test_admin_active_exists_blocks(self) -> None:
        repo = FakeRepository(
            empty_snapshot(
                user_account_count=1,
                admin_accounts=[AdminAccountSummary(user_id=7, login_name="admin", role="admin", status="active")],
            )
        )

        report = run_admin_bootstrap(
            repository=repo,
            execute=True,
            user_confirmed=True,
            password=test_password(),
            hasher=FixedHasher(),
        )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("admin_active_exists", report["blockers"])
        self.assertEqual(repo.insert_calls, [])

    def test_admin_disabled_or_deleted_exists_blocks(self) -> None:
        for status in ("disabled", "deleted"):
            with self.subTest(status=status):
                repo = FakeRepository(
                    empty_snapshot(
                        user_account_count=1,
                        admin_accounts=[AdminAccountSummary(user_id=7, login_name="admin", role="admin", status=status)],
                    )
                )

                report = run_admin_bootstrap(
                    repository=repo,
                    execute=True,
                    user_confirmed=True,
                    password=test_password(),
                    hasher=FixedHasher(),
                )

                self.assertEqual(report["result"], "BLOCKED")
                self.assertIn("admin_disabled_or_deleted_exists", report["blockers"])
                self.assertEqual(repo.insert_calls, [])

    def test_hash_password_is_not_plaintext(self) -> None:
        password = test_password()

        hashed = hash_password(password)

        self.assertNotEqual(hashed.password_hash, password)
        self.assertIn(hashed.password_hash_algo, {"argon2id", "bcrypt"})

    def test_six_digit_numeric_password_is_allowed(self) -> None:
        self.assertEqual(validate_password("123456"), [])

    def test_execute_uses_allowed_write_scope_only_and_creates_no_session(self) -> None:
        repo = FakeRepository(empty_snapshot())

        report = run_admin_bootstrap(
            repository=repo,
            execute=True,
            user_confirmed=True,
            password=test_password(),
            hasher=FixedHasher(),
        )

        self.assertEqual(report["result"], "EXECUTED")
        self.assertEqual(len(repo.insert_calls), 1)
        self.assertEqual(repo.insert_calls[0]["tables"], ["user_account", "user_filter_profile"])
        self.assertEqual(report["write_result"]["user_session_rows_inserted"], 0)
        self.assertEqual(report["write_result"]["user_projection_rows_inserted"], 0)
        self.assertEqual(report["write_result"]["user_notification_rows_inserted"], 0)
        self.assertEqual(report["write_result"]["user_sim_rows_inserted"], 0)

    def test_execute_does_not_consume_n5_outbox(self) -> None:
        repo = FakeRepository(empty_snapshot())

        report = run_admin_bootstrap(
            repository=repo,
            execute=True,
            user_confirmed=True,
            password=test_password(),
            hasher=FixedHasher(),
        )

        self.assertEqual(report["n5_outbox_before"], EXPECTED_N5_OUTBOX_COUNTS)
        self.assertEqual(report["n5_outbox_after"], EXPECTED_N5_OUTBOX_COUNTS)
        self.assertTrue(report["n5_outbox_unchanged"])


def empty_snapshot(
    *,
    user_account_count: int = 0,
    user_filter_profile_count: int = 0,
    admin_accounts: list[AdminAccountSummary] | None = None,
) -> PreflightSnapshot:
    table_counts = {
        "user_account": user_account_count,
        "user_filter_profile": user_filter_profile_count,
        "user_session": 0,
        "user_watchlist": 0,
        "user_watchlist_item": 0,
        "user_projection_run": 0,
        "user_signal_projection": 0,
        "user_signal_card": 0,
        "user_signal_decision": 0,
        "user_notification_queue": 0,
        "user_sim_account": 0,
        "user_sim_order": 0,
        "user_sim_trade": 0,
        "user_sim_position": 0,
    }
    return PreflightSnapshot(
        table_counts=table_counts,
        admin_accounts=admin_accounts or [],
        admin_default_profile_count=0,
        n5_outbox_counts=dict(EXPECTED_N5_OUTBOX_COUNTS),
        password_columns=["password_hash", "password_hash_algo", "password_updated_at"],
        plaintext_password_columns=[],
    )


if __name__ == "__main__":
    unittest.main()
