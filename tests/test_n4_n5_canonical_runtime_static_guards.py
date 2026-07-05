import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class N4N5CanonicalRuntimeStaticGuardTest(unittest.TestCase):
    def test_n5_schema_contract_uses_only_canonical_runtime_events_and_signals(self) -> None:
        schema = (ROOT / "sql" / "011_action_layer_schema.sql").read_text(encoding="utf-8")

        for legacy in (
            "TriggerCleared",
            "ActionEvent",
            "HintEvent",
            "RiskEvent",
            "PositionEvent",
            "B_BUY_30M_VOL",
            "S_SELL_30M_SHRINK",
            "'BUY_HINT'",
            "'SELL_HINT'",
        ):
            self.assertNotIn(legacy, schema)
        for canonical in (
            "TriggerMatched",
            "TriggerPendingMarketData",
            "TriggerStateChanged",
            "ActionEligible",
            "ActionBlocked",
            "ActionExecuted",
            "ActionSkipped",
            "source_trigger_state_id",
            "original_condition_key",
            "action_state",
            "confirmation_status",
            "action_policy",
            "trace_json",
        ):
            self.assertIn(canonical, schema)

    def test_current_n5_entry_gate_text_supersedes_trigger_cleared(self) -> None:
        current_runtime_paths = [
            ROOT / "src" / "ashare_v3" / "action" / "preflight.py",
            ROOT / "src" / "ashare_v3" / "action" / "consumer_dry_run.py",
            ROOT / "src" / "ashare_v3" / "action" / "run_once_dry_run.py",
            ROOT / "scripts" / "plan_action_consumer_run_once_dry_run.py",
        ]

        for path in current_runtime_paths:
            with self.subTest(path=path.relative_to(ROOT)):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("TriggerCleared", text)
                self.assertIn("TriggerStateChanged", text)

    def test_n4_projection_matcher_preserves_legacy_selector_only_as_provenance(self) -> None:
        matcher = (ROOT / "src" / "ashare_v3" / "trigger" / "projection_matcher.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("legacy_signal_type = signal_type", matcher)
        self.assertIn("canonical_signal_type = mapping.signal_type", matcher)
        self.assertIn("trigger_mark_candidate = mapping.trigger_mark_candidate", matcher)
        self.assertIn('"signal_type": canonical_signal_type', matcher)
        self.assertIn('"runtime_signal_type": canonical_signal_type', matcher)
        self.assertIn('"legacy_signal_type": legacy_signal_type', matcher)


if __name__ == "__main__":
    unittest.main()
