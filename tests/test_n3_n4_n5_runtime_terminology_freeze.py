import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


FREEZE_JSON = DOCS / "N3_N4_N5_RUNTIME_TERMINOLOGY_AND_RESPONSIBILITY_FREEZE.json"
RULE_SPEC = DOCS / "V3_N3_N4_N5_ACTION_CONFIRMATION_RULE_SPEC.md"


class N3N4N5RuntimeTerminologyFreezeTest(unittest.TestCase):
    def load_freeze(self):
        with FREEZE_JSON.open(encoding="utf-8") as handle:
            return json.load(handle)

    def test_freeze_registry_defines_canonical_authority_and_terms(self):
        freeze = self.load_freeze()

        self.assertEqual(freeze["result"], "FREEZE_PASS")
        self.assertEqual(
            freeze["canonical_authority_order"],
            [
                "docs/V3_TRIGGER_ACTION_RUNTIME_SPEC.md",
                "docs/V3_N3_N4_N5_ACTION_CONFIRMATION_RULE_SPEC.md",
                "docs/N4_N5_TRIGGER_ACTION_STATE_FLOW_v0.1.md",
                "docs/N5_CANONICAL_ACTION_FLOW_v0.1.md",
            ],
        )
        self.assertEqual(freeze["runtime_signal_type"]["allowed"], ["B_BUY", "S_SELL"])
        self.assertEqual(
            sorted(freeze["runtime_signal_type"]["deprecated_as_runtime_signal_type"]),
            ["BUY_HINT", "B_BUY_30M_VOL", "SELL_HINT", "S_SELL_30M_SHRINK"],
        )
        self.assertEqual(
            freeze["n4_events"]["canonical"],
            ["TriggerMatched", "TriggerPendingMarketData", "TriggerStateChanged"],
        )
        self.assertIn("TriggerCleared", freeze["n4_events"]["historical_superseded"])
        self.assertEqual(
            freeze["n5_events"]["canonical"],
            ["ActionEligible", "ActionBlocked", "ActionExecuted", "ActionSkipped"],
        )
        for event_type in ["ActionEvent", "HintEvent", "RiskEvent", "PositionEvent"]:
            self.assertIn(event_type, freeze["n5_events"]["historical_superseded"])

        hint_semantics = freeze["hint_semantics"]
        self.assertIn("N2 proves BUY_HINT / SELL_HINT prerequisite structure", hint_semantics)
        self.assertIn("N5 maps BUY_HINT / SELL_HINT to B_BUY / S_SELL action confirmation", hint_semantics)
        self.assertIn("N6 owns user display / voice / sim / trade-intent policy", hint_semantics)

    def test_action_confirmation_rule_spec_declares_n3_metric_ownership(self):
        text = RULE_SPEC.read_text(encoding="utf-8")

        required_markers = [
            "N3 owns action-confirmation projection facts.",
            "N4 must not read raw minute bars and assemble 1m/5m/30m/120m indicators itself.",
            "N5 must not pull market data.",
            "N5 must not read raw minute bars and assemble 1m/5m/30m/120m indicators itself.",
        ]
        for marker in required_markers:
            self.assertIn(marker, text)

    def test_legacy_design_docs_are_marked_historical_superseded(self):
        legacy_docs = [
            DOCS / "V3_N4_TRIGGER_LAYER_DEVELOPMENT_DESIGN.md",
            DOCS / "V3_N5_ACTION_LAYER_DEVELOPMENT_DESIGN.md",
            DOCS / "N5_0_ACTION_EVENT_CONTRACT.md",
        ]

        for path in legacy_docs:
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                head = "\n".join(text.splitlines()[:40])
                self.assertIn("historical/superseded", head)
                self.assertIn("docs/V3_TRIGGER_ACTION_RUNTIME_SPEC.md", head)
                self.assertIn("docs/V3_N3_N4_N5_ACTION_CONFIRMATION_RULE_SPEC.md", head)
                self.assertIn("Historical run evidence must not be silently rewritten.", head)

    def test_freeze_registry_records_forbidden_scope(self):
        freeze = self.load_freeze()

        self.assertEqual(
            freeze["forbidden_scope_proof"],
            {
                "n4_executed": False,
                "n5_executed": False,
                "database_written": False,
                "outbox_inbox_checkpoint_consumed_or_updated": False,
                "worker_started": False,
                "n6_entered": False,
                "voice_mobile_sim_position_pnl_real_trade_touched": False,
                "historical_run_evidence_modified": False,
            },
        )


if __name__ == "__main__":
    unittest.main()
