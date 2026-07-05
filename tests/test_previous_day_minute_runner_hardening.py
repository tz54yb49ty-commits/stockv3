import unittest

from ashare_v3.market.previous_day_preload_execute import (
    PreviousDayMinutePreloadExecuteError,
    ensure_execute_authorized,
)


class PreviousDayMinuteRunnerHardeningTest(unittest.TestCase):
    def test_missing_execute_flag_blocks_before_fetch_or_commit_path(self) -> None:
        with self.assertRaisesRegex(PreviousDayMinutePreloadExecuteError, "--execute"):
            ensure_execute_authorized(execute=False, user_confirmed=True)

    def test_missing_user_confirmed_flag_blocks_before_fetch_or_commit_path(self) -> None:
        with self.assertRaisesRegex(PreviousDayMinutePreloadExecuteError, "--user-confirmed"):
            ensure_execute_authorized(execute=True, user_confirmed=False)

    def test_double_confirmation_allows_fetch_or_commit_path(self) -> None:
        self.assertIsNone(ensure_execute_authorized(execute=True, user_confirmed=True))


if __name__ == "__main__":
    unittest.main()
