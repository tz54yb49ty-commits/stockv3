import plistlib
import tempfile
import unittest
from pathlib import Path


FOR_TRADE_DATE = "20260701"
SOURCE_TRADE_DATE = "20260630"
SOURCE_CONDITION_RUN_ID = "condition_layer_20260630_source_20260630_for_20260701_v1"
SUBSCRIPTION_RUN_ID = "market_data_subscription_20260701_condition_layer_20260630_source_20260630_for_20260701_v1"
PRELOAD_RUN_ID = (
    "previous_day_minute_preload_20260630_for_20260701__"
    "market_data_subscription_20260701_condition_layer_20260630_source_20260630_for_20260701_v1"
)
CONTEXT_RUN_ID = "trigger_context_snapshot_20260701_condition_layer_20260630_source_20260630_for_20260701_v1__atomic_rule_v1"
EXPECTED_PYTHON = "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3"
LINEAGE_CONFIG_PATH = "docs/runtime/current_intraday_worker_lineage.json"


class N3N4IntradayWorkerLaunchdPlanTest(unittest.TestCase):
    def test_builds_safe_n3_n4_proof_poller_plists(self) -> None:
        from scripts.plan_n3_n4_intraday_worker_launchd import build_launchd_plan

        plan = build_launchd_plan(
            for_trade_date=FOR_TRADE_DATE,
            source_trade_date=SOURCE_TRADE_DATE,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            subscription_run_id=SUBSCRIPTION_RUN_ID,
            preload_run_id=PRELOAD_RUN_ID,
            trigger_context_run_id=CONTEXT_RUN_ID,
            working_directory="/Users/chuanfuchen/Documents/A股监控系统v3",
        )

        self.assertEqual(plan["n3"]["plist"]["Label"], "com.ashare-v3.n3.intraday-proof-poller")
        self.assertEqual(plan["n4"]["plist"]["Label"], "com.ashare-v3.n4.proof-discovery-poller")
        self.assertEqual(plan["n3"]["plist"]["StartInterval"], 15)
        self.assertEqual(plan["n4"]["plist"]["StartInterval"], 10)
        self.assertFalse(plan["n3"]["plist"]["RunAtLoad"])
        self.assertFalse(plan["n4"]["plist"]["RunAtLoad"])
        self.assertFalse(plan["n3"]["plist"]["KeepAlive"])
        self.assertFalse(plan["n4"]["plist"]["KeepAlive"])

        n3_args = plan["n3"]["plist"]["ProgramArguments"]
        n4_args = plan["n4"]["plist"]["ProgramArguments"]
        self.assertEqual(n3_args[0], EXPECTED_PYTHON)
        self.assertEqual(n4_args[0], EXPECTED_PYTHON)
        self.assertNotEqual(n3_args[0], "python3")
        self.assertNotEqual(n4_args[0], "python3")
        self.assertIn("scripts/run_n3_intraday_proof_poller_once.py", n3_args)
        self.assertIn("scripts/run_n4_intraday_proof_discovery_poll_once.py", n4_args)
        self.assertIn("--execute", n3_args)
        self.assertIn("--user-confirmed", n3_args)
        self.assertIn("--execute", n4_args)
        self.assertIn("--user-confirmed", n4_args)
        self.assertIn("--python-executable", n3_args)
        self.assertEqual(n3_args[n3_args.index("--python-executable") + 1], EXPECTED_PYTHON)
        self.assertIn("--python-executable", n4_args)
        self.assertEqual(n4_args[n4_args.index("--python-executable") + 1], EXPECTED_PYTHON)
        self.assertIn("--lineage-config", n3_args)
        self.assertEqual(n3_args[n3_args.index("--lineage-config") + 1], LINEAGE_CONFIG_PATH)
        self.assertIn("--lineage-config", n4_args)
        self.assertEqual(n4_args[n4_args.index("--lineage-config") + 1], LINEAGE_CONFIG_PATH)
        self.assertIn("--dsn", n4_args)
        self.assertIn("__ASHARE_V3_POSTGRES_DSN__", n4_args)
        self.assertIn("--selection-mode", n4_args)
        self.assertEqual(n4_args[n4_args.index("--selection-mode") + 1], "realtime_latest_only")
        self.assertNotIn(FOR_TRADE_DATE, n3_args)
        self.assertNotIn(FOR_TRADE_DATE, n4_args)
        self.assertNotIn(SOURCE_TRADE_DATE, n3_args)
        self.assertNotIn(SOURCE_TRADE_DATE, n4_args)
        self.assertNotIn(SOURCE_CONDITION_RUN_ID, n3_args)
        self.assertNotIn(SOURCE_CONDITION_RUN_ID, n4_args)
        self.assertNotIn("--for-trade-date", n3_args)
        self.assertNotIn("--for-trade-date", n4_args)

        self.assertNotIn("ASHARE_V3_POSTGRES_DSN", plan["n3"]["plist"]["EnvironmentVariables"])
        self.assertNotIn("__ASHARE_V3_POSTGRES_DSN__", n3_args)
        self.assertEqual(
            plan["n4"]["plist"]["EnvironmentVariables"]["ASHARE_V3_POSTGRES_DSN"],
            "__ASHARE_V3_POSTGRES_DSN__",
        )
        self.assertEqual(plan["forbidden_operation_proof"]["launchd_loaded_or_started"], False)
        self.assertEqual(plan["forbidden_operation_proof"]["database_written"], False)

        joined = " ".join(n3_args + n4_args).lower()
        for forbidden in (
            "run_n3_n4_n5_realtime_chain_once.py",
            "run_n5",
            "run_n6",
            "consume",
            "checkpoint",
            "rollback",
            "schema",
            "migration",
            "launchctl",
        ):
            self.assertNotIn(forbidden, joined)

    def test_materialized_plists_are_valid_and_report_redacts_dsn(self) -> None:
        from scripts.plan_n3_n4_intraday_worker_launchd import write_launchd_plan

        with tempfile.TemporaryDirectory() as tmpdir:
            report = write_launchd_plan(
                output_dir=Path(tmpdir),
                for_trade_date=FOR_TRADE_DATE,
                source_trade_date=SOURCE_TRADE_DATE,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                trigger_context_run_id=CONTEXT_RUN_ID,
                working_directory="/Users/chuanfuchen/Documents/A股监控系统v3",
                dsn="postgresql://ashare_v3_user:secret@127.0.0.1:5432/ashare_v3",
            )

            for key in ("n3", "n4"):
                plist_path = Path(report[key]["plist_path"])
                self.assertTrue(plist_path.exists())
                plistlib.loads(plist_path.read_bytes())

            self.assertIn("postgresql://ashare_v3_user:***@127.0.0.1:5432/ashare_v3", str(report))
            self.assertNotIn("secret", str(report))

    def test_builds_split_n3_branch_proof_poller_plan(self) -> None:
        from scripts.plan_n3_n4_intraday_worker_launchd import build_launchd_plan

        plan = build_launchd_plan(
            for_trade_date=FOR_TRADE_DATE,
            source_trade_date=SOURCE_TRADE_DATE,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            subscription_run_id=SUBSCRIPTION_RUN_ID,
            preload_run_id=PRELOAD_RUN_ID,
            trigger_context_run_id=CONTEXT_RUN_ID,
            working_directory="/Users/chuanfuchen/Documents/A股监控系统v3",
            split_n3_branches=True,
        )

        self.assertEqual(plan["n3p"]["plist"]["Label"], "com.ashare-v3.n3.intraday-proof-poller.n3p")
        self.assertEqual(plan["hint"]["plist"]["Label"], "com.ashare-v3.n3.intraday-proof-poller.hint")
        self.assertEqual(plan["n4"]["plist"]["Label"], "com.ashare-v3.n4.proof-discovery-poller")
        self.assertEqual(plan["n4_hint"]["plist"]["Label"], "com.ashare-v3.n4.proof-discovery-poller.hint")
        self.assertEqual(plan["n3p"]["plist"]["StartInterval"], 60)
        self.assertEqual(plan["hint"]["plist"]["StartInterval"], 180)
        self.assertEqual(plan["n4"]["plist"]["StartInterval"], 10)
        self.assertEqual(plan["n4_hint"]["plist"]["StartInterval"], 10)

        n3p_args = plan["n3p"]["plist"]["ProgramArguments"]
        hint_args = plan["hint"]["plist"]["ProgramArguments"]
        n4_args = plan["n4"]["plist"]["ProgramArguments"]
        n4_hint_args = plan["n4_hint"]["plist"]["ProgramArguments"]
        self.assertEqual(n3p_args[0], EXPECTED_PYTHON)
        self.assertEqual(hint_args[0], EXPECTED_PYTHON)
        self.assertEqual(n4_hint_args[0], EXPECTED_PYTHON)
        self.assertIn("--branch", n3p_args)
        self.assertEqual(n3p_args[n3p_args.index("--branch") + 1], "n3p_only")
        self.assertIn("--branch", hint_args)
        self.assertEqual(hint_args[hint_args.index("--branch") + 1], "hint_only")
        self.assertNotIn("--branch", n4_args)
        self.assertNotIn("--branch", n4_hint_args)
        self.assertIn("tmp/N3_intraday_proof_poller_n3p_launchd_report.json", n3p_args)
        self.assertIn("tmp/N3_intraday_proof_poller_hint_launchd_report.json", hint_args)
        self.assertIn("tmp/N4_intraday_proof_discovery_poller_launchd_report.json", n4_args)
        self.assertIn("tmp/N4_intraday_proof_discovery_poller_hint_launchd_report.json", n4_hint_args)
        self.assertIn("--mode", n4_args)
        self.assertEqual(n4_args[n4_args.index("--mode") + 1], "ordinary")
        self.assertIn("--mode", n4_hint_args)
        self.assertEqual(n4_hint_args[n4_hint_args.index("--mode") + 1], "hint")
        self.assertIn("--selection-mode", n4_args)
        self.assertEqual(n4_args[n4_args.index("--selection-mode") + 1], "realtime_latest_only")
        self.assertIn("--selection-mode", n4_hint_args)
        self.assertEqual(n4_hint_args[n4_hint_args.index("--selection-mode") + 1], "realtime_latest_only")
        self.assertFalse(plan["n3p"]["plist"]["RunAtLoad"])
        self.assertFalse(plan["hint"]["plist"]["RunAtLoad"])
        self.assertFalse(plan["n4_hint"]["plist"]["RunAtLoad"])
        self.assertFalse(plan["n3p"]["plist"]["KeepAlive"])
        self.assertFalse(plan["hint"]["plist"]["KeepAlive"])
        self.assertFalse(plan["n4_hint"]["plist"]["KeepAlive"])

        joined = " ".join(n3p_args + hint_args + n4_args + n4_hint_args).lower()
        self.assertNotIn("com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll", joined)
        self.assertNotIn("com.ashare-v3.n4.bounded-polling", joined)
        for forbidden in (
            "run_n3_n4_n5_realtime_chain_once.py",
            "run_n5",
            "run_n6",
            "consume",
            "checkpoint",
            "rollback",
            "schema",
            "migration",
            "launchctl",
        ):
            self.assertNotIn(forbidden, joined)

    def test_materialized_split_branch_plists_are_valid(self) -> None:
        from scripts.plan_n3_n4_intraday_worker_launchd import write_launchd_plan

        with tempfile.TemporaryDirectory() as tmpdir:
            report = write_launchd_plan(
                output_dir=Path(tmpdir),
                for_trade_date=FOR_TRADE_DATE,
                source_trade_date=SOURCE_TRADE_DATE,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                trigger_context_run_id=CONTEXT_RUN_ID,
                working_directory="/Users/chuanfuchen/Documents/A股监控系统v3",
                split_n3_branches=True,
            )

            for key in ("n3p", "hint", "n4", "n4_hint"):
                plist_path = Path(report[key]["plist_path"])
                self.assertTrue(plist_path.exists())
                plistlib.loads(plist_path.read_bytes())


if __name__ == "__main__":
    unittest.main()
