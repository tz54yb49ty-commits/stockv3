import tempfile
import unittest
from pathlib import Path

from ashare_v3.observability.query_audit import (
    VALID_CONNECTION_SITE_CLASSIFICATIONS,
    build_static_coverage_report,
    inventory_psycopg_connect_sites,
)


class StructuredQueryAuditStaticCoverageTest(unittest.TestCase):
    def test_inventory_finds_psycopg_connect_sites_with_line_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target = root / "src" / "ashare_v3" / "market"
            target.mkdir(parents=True)
            file_path = target / "sample_execute.py"
            file_path.write_text(
                "import psycopg\n\n"
                "def run(dsn):\n"
                "    with psycopg.connect(dsn) as conn:\n"
                "        return conn\n",
                encoding="utf-8",
            )

            sites = inventory_psycopg_connect_sites([target])

        self.assertEqual(len(sites), 1)
        self.assertEqual(sites[0].relative_path, "sample_execute.py")
        self.assertEqual(sites[0].line_number, 4)

    def test_static_report_blocks_unclassified_sites(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            market = root / "src" / "ashare_v3" / "market"
            trigger = root / "src" / "ashare_v3" / "trigger"
            market.mkdir(parents=True)
            trigger.mkdir(parents=True)
            (market / "wrapped.py").write_text("import psycopg\npsycopg.connect('dsn')\n", encoding="utf-8")
            (trigger / "missing.py").write_text("import psycopg\npsycopg.connect('dsn')\n", encoding="utf-8")

            report = build_static_coverage_report(
                [market, trigger],
                classifications={
                    "wrapped.py:2": "must_wrap",
                },
            )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertEqual(report["total_sites"], 2)
        self.assertEqual(report["unclassified_count"], 1)
        self.assertEqual(report["unclassified_sites"][0]["relative_path"], "missing.py")

    def test_static_report_passes_when_all_sites_are_classified(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            action = root / "src" / "ashare_v3" / "action"
            action.mkdir(parents=True)
            (action / "readiness.py").write_text("import psycopg\npsycopg.connect('dsn')\n", encoding="utf-8")

            report = build_static_coverage_report(
                [action],
                classifications={
                    "readiness.py:2": "explicit_bypass_readonly_plan",
                },
            )

        self.assertEqual(report["result"], "PASS")
        self.assertEqual(report["unclassified_count"], 0)
        self.assertEqual(report["classification_counts"]["explicit_bypass_readonly_plan"], 1)

    def test_invalid_classification_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            market = root / "market"
            market.mkdir()
            (market / "sample.py").write_text("import psycopg\npsycopg.connect('dsn')\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                build_static_coverage_report([market], {"sample.py:2": "approved_because_i_said_so"})

        self.assertIn("blocked_until_refactored", VALID_CONNECTION_SITE_CLASSIFICATIONS)


if __name__ == "__main__":
    unittest.main()
