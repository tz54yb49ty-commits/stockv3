import plistlib
import unittest
from pathlib import Path


N3_AUTO_POLL_PLIST = Path(
    "/Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll.plist"
)
SAFE_RUNNER = "scripts/run_n3_intraday_b1_c1_b2_auto_poll_once.py"
UNSAFE_TOKENS = (
    "scripts/run_n3_n4_n5_realtime_chain_once.py",
    "run_n4",
    "run_n5",
    "run_n6",
)


class N3LaunchdConfigSafetyTest(unittest.TestCase):
    def _plist(self):
        self.assertTrue(N3_AUTO_POLL_PLIST.exists(), f"missing plist: {N3_AUTO_POLL_PLIST}")
        return plistlib.loads(N3_AUTO_POLL_PLIST.read_bytes())

    def test_n3_auto_poll_plist_uses_n3_only_runner(self) -> None:
        payload = self._plist()
        args = [str(value) for value in payload["ProgramArguments"]]
        joined = " ".join(args)

        self.assertIn(SAFE_RUNNER, args)
        for token in UNSAFE_TOKENS:
            self.assertNotIn(token, joined)
        self.assertIn("--for-trade-date", args)
        self.assertIn("20260701", args)
        self.assertIn("--source-condition-run-id", args)
        self.assertIn("condition_layer_20260630_source_20260630_for_20260701_v1", args)
        self.assertIn("--subscription-run-id", args)
        self.assertIn("market_data_subscription_20260701_condition_layer_20260630_source_20260630_for_20260701_v1", args)
        self.assertIn("--preload-run-id", args)
        self.assertIn(
            "previous_day_minute_preload_20260630_for_20260701__market_data_subscription_20260701_condition_layer_20260630_source_20260630_for_20260701_v1",
            args,
        )

    def test_n3_auto_poll_plist_is_disabled_until_launch_gate(self) -> None:
        payload = self._plist()

        self.assertEqual(payload["Label"], "com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll")
        self.assertFalse(payload.get("RunAtLoad"))
        self.assertFalse(payload.get("KeepAlive"))
        self.assertEqual(payload.get("StartInterval"), 60)

    def test_n3_auto_poll_plist_has_no_event_consumer_args(self) -> None:
        payload = self._plist()
        joined = " ".join(str(value) for value in payload["ProgramArguments"]).lower()

        for forbidden in ("outbox", "inbox", "checkpoint", "consume"):
            self.assertNotIn(forbidden, joined)


if __name__ == "__main__":
    unittest.main()
