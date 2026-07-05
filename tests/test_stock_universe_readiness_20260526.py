import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

from ashare_v3.ingestion.stock_universe_readiness_20260526 import (
    DAILY_MISSING_ACTIVE_IDENTITIES,
    STALE_IDENTITY_KEY,
    SUPERSEDED_BY_IDENTITY_KEY,
    TRADE_DATE,
    build_readiness_report,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "plan_stock_universe_readiness_20260526.py"


def load_runner_module():
    spec = importlib.util.spec_from_file_location("n1_stock_universe_readiness_20260526", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def identity_row(identity_key: str, *, name: str = "样本", is_st: bool = False, source: str = "tushare.stock_basic") -> dict:
    _, exchange, code = identity_key.split(":")
    return {
        "stock_identity_key": identity_key,
        "identity_key": identity_key,
        "ts_code": f"{code}.{exchange}",
        "code": code,
        "exchange": exchange,
        "name": name,
        "listed_date": "20200101",
        "delisted_date": None,
        "is_st": is_st,
        "status": "active",
        "source": source,
        "source_version": "stock_identity_20260526_v1",
    }


def base_db_snapshot() -> dict:
    stock_rows = [identity_row(key, is_st=("*ST" in key)) for key in DAILY_MISSING_ACTIVE_IDENTITIES]
    stock_rows.append(
        identity_row(
            STALE_IDENTITY_KEY,
            name="中航成飞",
            source="tushare.namechange+bak_basic.identity_supplement",
        )
    )
    stock_rows.append(identity_row(SUPERSEDED_BY_IDENTITY_KEY, name="中航成飞"))
    return {
        "trade_date": TRADE_DATE,
        "raw_active_universe": 5523,
        "candidate_rows": stock_rows,
        "read_only_database_checks": True,
    }


def base_tushare_snapshot() -> dict:
    daily_present = []
    adj_present = [key_to_ts_code(key) for key in DAILY_MISSING_ACTIVE_IDENTITIES]
    stock_basic = {
        key_to_ts_code(key): {"ts_code": key_to_ts_code(key), "list_status": "L", "name": "样本"}
        for key in DAILY_MISSING_ACTIVE_IDENTITIES
    }
    stock_basic[key_to_ts_code(SUPERSEDED_BY_IDENTITY_KEY)] = {
        "ts_code": key_to_ts_code(SUPERSEDED_BY_IDENTITY_KEY),
        "list_status": "L",
        "name": "中航成飞",
    }
    return {
        "trade_date": TRADE_DATE,
        "daily_present_ts_codes": daily_present,
        "adj_factor_present_ts_codes": adj_present,
        "stock_basic_by_ts_code": stock_basic,
        "source": "tushare.readonly",
    }


def key_to_ts_code(identity_key: str) -> str:
    _, exchange, code = identity_key.split(":")
    return f"{code}.{exchange}"


class StockUniverseReadiness20260526Tests(unittest.TestCase):
    def test_report_blocks_unresolved_source_gaps_and_marks_stale_identity(self) -> None:
        tdx_snapshot = {
            "source_available": True,
            "presence_by_identity_key": {},
            "source": "mootdx.stock_daily.readonly",
        }

        report = build_readiness_report(
            db_snapshot=base_db_snapshot(),
            tushare_snapshot=base_tushare_snapshot(),
            tdx_snapshot=tdx_snapshot,
        )

        self.assertEqual(report["result"], "READINESS_BLOCKED")
        self.assertEqual(report["raw_active_universe"], 5523)
        self.assertEqual(report["effective_active_universe"], 5522)
        self.assertEqual(report["tushare_daily_matched"], 5504)
        self.assertEqual(report["unresolved_daily_missing_active"], 18)
        self.assertEqual(report["quality"]["p0_count"], 18)
        self.assertGreaterEqual(report["quality"]["p1_count"], 1)
        self.assertEqual(
            report["stale_identity_candidates"][0]["superseded_by_identity_key"],
            SUPERSEDED_BY_IDENTITY_KEY,
        )

    def test_report_allows_v2_contract_when_all_missing_have_tdx_supplement(self) -> None:
        tdx_snapshot = {
            "source_available": True,
            "presence_by_identity_key": {
                identity_key: {"present": True, "source": "mootdx.stock_daily", "evidence": {"trade_date": TRADE_DATE}}
                for identity_key in DAILY_MISSING_ACTIVE_IDENTITIES
            },
            "source": "mootdx.stock_daily.readonly",
        }

        report = build_readiness_report(
            db_snapshot=base_db_snapshot(),
            tushare_snapshot=base_tushare_snapshot(),
            tdx_snapshot=tdx_snapshot,
        )

        self.assertEqual(report["result"], "READINESS_PASS")
        self.assertEqual(report["expected_daily_bar_scope"]["stock"], 5522)
        self.assertEqual(report["unresolved_daily_missing_active"], 0)
        self.assertEqual(report["supplemental_source_available"], 18)
        self.assertEqual(report["quality"]["p0_count"], 0)
        self.assertEqual(report["quality"]["p1_count"], 19)

    def test_tdx_unavailable_keeps_gate_blocked(self) -> None:
        tdx_snapshot = {
            "source_available": False,
            "source_unavailable_reason": "mootdx import failed",
            "presence_by_identity_key": {},
            "source": "mootdx.stock_daily.readonly",
        }

        report = build_readiness_report(
            db_snapshot=base_db_snapshot(),
            tushare_snapshot=base_tushare_snapshot(),
            tdx_snapshot=tdx_snapshot,
        )

        self.assertEqual(report["result"], "READINESS_BLOCKED")
        self.assertIn("tdx_mootdx_unavailable", report["blockers"])
        self.assertGreaterEqual(report["quality"]["p0_count"], 1)

    def test_cli_execute_is_rejected_before_dependencies_run(self) -> None:
        runner = load_runner_module()
        called = {"planner": False}

        def forbidden_planner(*args, **kwargs):
            called["planner"] = True
            return {}

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = runner.main(["--execute"], dependencies={"run_planner": forbidden_planner})

        self.assertEqual(result, 2)
        self.assertFalse(called["planner"])

    def test_cli_writes_json_and_markdown_report_with_injected_planner(self) -> None:
        runner = load_runner_module()
        report = build_readiness_report(
            db_snapshot=base_db_snapshot(),
            tushare_snapshot=base_tushare_snapshot(),
            tdx_snapshot={"source_available": True, "presence_by_identity_key": {}, "source": "mootdx.stock_daily.readonly"},
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "report.json"
            md_path = Path(tmpdir) / "report.md"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                result = runner.main(
                    ["--json-path", str(json_path), "--md-path", str(md_path), "--json"],
                    dependencies={"run_planner": lambda **kwargs: report},
                )

            self.assertEqual(result, 0)
            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())
            parsed = json.loads(json_path.read_text())
            self.assertEqual(parsed["result"], "READINESS_BLOCKED")
            self.assertIn("READINESS_BLOCKED", md_path.read_text())
            self.assertEqual(json.loads(stdout.getvalue())["result"], "READINESS_BLOCKED")


if __name__ == "__main__":
    unittest.main()
