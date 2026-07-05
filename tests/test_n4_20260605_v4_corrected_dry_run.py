import json
import unittest
from datetime import datetime
from pathlib import Path

from ashare_v3.trigger.v4_corrected_dry_run import (
    build_corrected_v4_dry_run_report,
    correct_trigger_matched_candidate,
)
from ashare_v3.trigger.v4_enforcement import collect_v4_trigger_matched_plan_violations


def _candidate() -> dict:
    return {
        "output_event_type": "TriggerMatched",
        "source_event_id": "evt_source",
        "source_event_type": "MarketSnapshotUpdated",
        "asset_kind": "stock",
        "identity_key": "stock:SH:600000",
        "direction": "buy",
        "signal_type": "B_BUY",
        "condition_key": "BUY:Y,Q,M,W,D",
        "original_condition_key": "BUY:Y,Q,M,W,D",
        "match_basis": "realtime_snapshot",
        "trigger_period": "D",
        "all_trigger_periods": ["D"],
        "primary_trigger_period": "D",
        "trigger_mark_candidate": "normal",
        "trigger_live": True,
        "current_status": "matched",
        "data_quality_status": "passed",
        "snapshot_trace": {
            "snapshot_run_id": "snapshot_run",
            "snapshot_id": 1,
            "snapshot_time": "2026-06-05T14:30:00+08:00",
            "current_price": "10.50",
            "quality_status": "passed",
        },
    }


def _full_candidate() -> dict:
    candidate = _candidate()
    candidate.update(
        {
            "condition_key": "BUY:FULL",
            "original_condition_key": "BUY:FULL",
            "trigger_period": "D",
            "all_trigger_periods": ["D"],
            "primary_trigger_period": "D",
            "trigger_mark_candidate": "normal",
            "projection_30m_flag": False,
            "projection_30m_type": "none",
        }
    )
    candidate.pop("triggered_periods", None)
    return candidate


class N420260605V4CorrectedDryRunTests(unittest.TestCase):
    def test_corrected_candidate_adds_v4_fields_and_passes_enforcement(self) -> None:
        corrected = correct_trigger_matched_candidate(
            _candidate(),
            created_at=datetime.fromisoformat("2026-06-05T14:31:00+08:00"),
        )

        self.assertEqual(corrected["trigger_price"], "10.50")
        self.assertEqual(corrected["trigger_kind"], "trigger")
        self.assertEqual(corrected["triggered_periods"], ["D"])
        self.assertTrue(corrected["n5_entry_allowed"])
        self.assertEqual(
            collect_v4_trigger_matched_plan_violations(
                corrected,
                created_at=datetime.fromisoformat("2026-06-05T14:31:00+08:00"),
            ),
            [],
        )

    def test_corrected_candidate_blocks_future_time(self) -> None:
        candidate = _candidate()
        candidate["snapshot_trace"]["snapshot_time"] = "2026-06-05T15:00:00+08:00"

        corrected = correct_trigger_matched_candidate(
            candidate,
            created_at=datetime.fromisoformat("2026-06-05T14:31:00+08:00"),
        )

        violations = collect_v4_trigger_matched_plan_violations(
            corrected,
            created_at=datetime.fromisoformat("2026-06-05T14:31:00+08:00"),
        )
        self.assertIn("event_time_after_created_at", violations)

    def test_corrected_report_separates_compliant_and_blocked_candidates(self) -> None:
        future = _candidate()
        future["identity_key"] = "stock:SH:600001"
        future["snapshot_trace"]["snapshot_time"] = "2026-06-05T15:00:00+08:00"
        report = build_corrected_v4_dry_run_report(
            local_plans=[_candidate(), future],
            projection_plans=[],
            metadata={
                "trigger_context_run_id": "ctx",
                "snapshot_run_id": "snapshot",
                "projection_run_id": "projection",
                "source_condition_run_id": "condition",
                "for_trade_date": "20260605",
            },
            created_at=datetime.fromisoformat("2026-06-05T14:31:00+08:00"),
        )

        self.assertEqual(report["result"], "DRY_RUN_PASS")
        self.assertEqual(report["candidate_plans_before_strict_guard"], 2)
        self.assertEqual(report["persisted_plans_after_strict_guard"], 1)
        self.assertEqual(report["blocked_count"], 1)
        self.assertEqual(report["blocked_counts_by_reason"]["future event_time"], 1)
        self.assertEqual(report["n5_entry_eligibility_proof"]["invalid_n5_entry_count"], 0)

    def test_corrected_full_candidate_is_compliant_when_d_payload_is_valid(self) -> None:
        report = build_corrected_v4_dry_run_report(
            local_plans=[_full_candidate()],
            projection_plans=[],
            metadata={
                "trigger_context_run_id": "ctx",
                "snapshot_run_id": "snapshot",
                "projection_run_id": "projection",
                "source_condition_run_id": "condition",
                "for_trade_date": "20260605",
            },
            created_at=datetime.fromisoformat("2026-06-05T14:31:00+08:00"),
        )

        self.assertEqual(report["persisted_plans_after_strict_guard"], 1)
        self.assertEqual(report["blocked_count"], 0)
        self.assertEqual(report["compliant_trigger_matched_sample"][0]["condition_key"], "BUY:FULL")
        self.assertEqual(report["compliant_trigger_matched_sample"][0]["triggered_periods"], ["D"])

    def test_corrected_full_candidate_with_30m_marker_is_semantic_blocked(self) -> None:
        invalid = _full_candidate()
        invalid["trigger_mark_candidate"] = "30m_volume"
        invalid["projection_30m_flag"] = True
        report = build_corrected_v4_dry_run_report(
            local_plans=[invalid],
            projection_plans=[],
            metadata={
                "trigger_context_run_id": "ctx",
                "snapshot_run_id": "snapshot",
                "projection_run_id": "projection",
                "source_condition_run_id": "condition",
                "for_trade_date": "20260605",
            },
            created_at=datetime.fromisoformat("2026-06-05T14:31:00+08:00"),
        )

        self.assertEqual(report["persisted_plans_after_strict_guard"], 0)
        self.assertEqual(report["blocked_counts_by_reason"]["FULL semantic blocked"], 1)
        self.assertEqual(report["full_semantic_proof"]["full_semantic_blocked_count"], 1)

    def test_corrected_artifact_paths_parse_when_present(self) -> None:
        for path in [
            Path("docs/N4_TRIGGER_RULE_V4_ENFORCEMENT_CONTRACT.json"),
            Path("docs/N4_TRIGGER_RULE_V4_ENFORCEMENT_PREFLIGHT.json"),
        ]:
            self.assertIsInstance(json.loads(path.read_text()), dict)


if __name__ == "__main__":
    unittest.main()
