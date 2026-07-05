import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import run_v3_20260615_full_universe_replay_once as runner


class V320260615FullUniverseReplayOnceTest(unittest.TestCase):
    def test_midday_normalization_maps_source_1130_to_v3_1300(self) -> None:
        rows = [
            {"bar_time": datetime.fromisoformat("2026-06-15T11:29:00+08:00"), "raw_payload": {"label": "11:29"}},
            {"bar_time": datetime.fromisoformat("2026-06-15T11:30:00+08:00"), "raw_payload": {"label": "11:30"}},
            {"bar_time": datetime.fromisoformat("2026-06-15T13:01:00+08:00"), "raw_payload": {"label": "13:01"}},
        ]

        normalized = runner.normalize_midday_source_labels(rows)

        labels = [row["bar_time"].strftime("%H:%M") for row in normalized]
        self.assertEqual(labels, ["11:29", "13:00", "13:01"])
        bridge = normalized[1]
        self.assertEqual(bridge["raw_payload"]["source_label_time"], "11:30")
        self.assertEqual(bridge["raw_payload"]["v3_normalized_label_time"], "13:00")
        self.assertEqual(bridge["raw_payload"]["midday_bridge_policy"], "source_1130_label_normalized_to_v3_1300")

    def test_script_is_runtime_control_plan_only(self) -> None:
        plan = runner.build_layer_separated_plan(for_trade_date="20260615")

        self.assertEqual(plan["result"], "PLAN_ONLY")
        self.assertEqual(plan["orchestration_mode"], "runtime_control_plan_only")
        self.assertFalse(plan["cross_layer_execution_allowed"])
        self.assertEqual(
            [step["layer_role"] for step in plan["layer_separated_steps"]],
            ["N3_market_data", "N4_trigger", "N5_action", "N6_user"],
        )

    def test_execute_attempt_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "report.json"
            md_path = Path(tmpdir) / "report.md"
            rc = runner.main(
                [
                    "--execute",
                    "--user-confirmed",
                    "--json-report-path",
                    str(json_path),
                    "--markdown-report-path",
                    str(md_path),
                ]
            )

            self.assertEqual(rc, 2)
            self.assertIn("cross_layer_full_universe_replay_removed", json_path.read_text(encoding="utf-8"))

    def test_only_reviewed_bj_index_missing_source_is_tolerated(self) -> None:
        fetch_results = [
            {"asset_kind": "index", "identity_key": "index:BJ:899050", "status": "missing", "row_count": 0},
            {"asset_kind": "index", "identity_key": "index:BJ:899601", "status": "missing", "row_count": 0},
            {"asset_kind": "stock", "identity_key": "stock:SH:600000", "status": "missing", "row_count": 0},
        ]

        classified = runner.classify_full_universe_fetch_results(fetch_results)

        self.assertEqual(
            [row["identity_key"] for row in classified["tolerated_missing"]],
            ["index:BJ:899050", "index:BJ:899601"],
        )
        self.assertEqual(
            [row["identity_key"] for row in classified["blocking_fetches"]],
            ["stock:SH:600000"],
        )
        self.assertEqual(classified["tolerated_missing_policy"], "quality_visible_no_fabricated_minute_rows")


if __name__ == "__main__":
    unittest.main()
