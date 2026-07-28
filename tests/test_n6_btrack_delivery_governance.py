from __future__ import annotations

import importlib.util
import json
import plistlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "docs" / "N6_B_TRACK_DELIVERY_GOVERNANCE_V1.json"
REGISTRY_PATH = ROOT / "docs" / "N6_B_TRACK_BASELINE_REGISTRY_V1.json"
SCRIPT_PATH = ROOT / "scripts" / "plan_n6_btrack_delivery.py"
SPEC = importlib.util.spec_from_file_location("plan_n6_btrack_delivery", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def request_payload(**profile: object) -> dict[str, object]:
    return {
        "page_or_feature": "B轨筛选中心",
        "users": "N6 human users",
        "expected_behavior": "更清晰地筛选本人监控对象",
        "affects_virtual_money_proposals_or_positions": False,
        "change_profile": profile,
    }


class N6BTrackDeliveryGovernanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        cls.registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))

    def test_contract_has_three_reusable_lanes(self) -> None:
        self.assertEqual(
            {
                lane: row["policy_id"]
                for lane, row in self.contract["lanes"].items()
            },
            {
                "L1": "n6_btrack_delivery_l1_web_readonly_v1",
                "L2": "n6_btrack_delivery_l2_n6_business_v1",
                "L3": "n6_btrack_delivery_l3_virtual_runtime_v1",
            },
        )
        self.assertFalse(
            self.contract["policy_lifecycle"][
                "new_one_off_policy_for_normal_n6_delivery_allowed"
            ]
        )

    def test_l1_ui_read_only_classification(self) -> None:
        result = MODULE.classify_request(
            request_payload(ui_only=True, read_only_query_only=True),
            self.contract,
        )
        self.assertEqual(result["decision"], "ACCEPT")
        self.assertEqual(result["lane"], "L1")
        self.assertNotIn("migration", result["required_sequence"])

    def test_l2_business_or_scope_write_classification(self) -> None:
        result = MODULE.classify_request(
            request_payload(monitor_scope_write=True),
            self.contract,
        )
        self.assertEqual(result["decision"], "ACCEPT")
        self.assertEqual(result["lane"], "L2")

    def test_l3_virtual_money_or_runtime_classification(self) -> None:
        payload = request_payload(executor_change=True)
        payload["affects_virtual_money_proposals_or_positions"] = True
        result = MODULE.classify_request(payload, self.contract)
        self.assertEqual(result["decision"], "ACCEPT")
        self.assertEqual(result["lane"], "L3")
        self.assertIn("bounded_virtual_smoke", result["required_sequence"])

    def test_real_trading_and_upstream_writeback_rejected(self) -> None:
        for profile, reason in (
            ({"real_broker": True}, "real_trading_forbidden"),
            ({"writes_n1_n5": True}, "n6_upstream_writeback_forbidden"),
            (
                {"automatic_proposal_creation": True},
                "automatic_proposal_creation_or_confirmation_forbidden",
            ),
        ):
            with self.subTest(profile=profile):
                result = MODULE.classify_request(
                    request_payload(**profile),
                    self.contract,
                )
                self.assertEqual(result["decision"], "REJECT")
                self.assertEqual(result["reason"], reason)

    def test_missing_or_ambiguous_input_blocks(self) -> None:
        result = MODULE.classify_request({}, self.contract)
        self.assertEqual(result["decision"], "BLOCK")
        self.assertEqual(set(result["missing_fields"]), set(MODULE.REQUIRED_BRIEF_FIELDS))
        ambiguous = MODULE.classify_request(request_payload(), self.contract)
        self.assertEqual(ambiguous["decision"], "BLOCK")
        self.assertEqual(ambiguous["reason"], "ambiguous_change_profile")

    def test_mixed_lane_and_new_one_off_policy_are_rejected(self) -> None:
        mixed = MODULE.classify_request(
            request_payload(ui_only=True, n6_schema_change=True),
            self.contract,
        )
        self.assertEqual(mixed["decision"], "BLOCK")
        self.assertEqual(mixed["reason"], "mixed_delivery_lanes")
        one_off = MODULE.classify_request(
            request_payload(
                ui_only=True,
                requested_new_one_off_policy=True,
            ),
            self.contract,
        )
        self.assertEqual(one_off["decision"], "REJECT")
        self.assertEqual(
            one_off["reason"],
            "normal_delivery_must_reuse_lane_policy",
        )

    def test_baseline_registry_is_honest_about_fragmentation(self) -> None:
        self.assertEqual(self.registry["lineage"]["status"], "FRAGMENTED")
        self.assertFalse(self.registry["lineage"]["single_release_ready"])
        self.assertFalse(
            self.registry["canonical_integration"]["deployment_authorized"]
        )
        self.assertEqual(
            self.registry["convergence"]["required_next_gate"],
            "n6_btrack_service_lineage_convergence_v1",
        )
        self.assertEqual(
            self.registry["migration_identity_anomalies"][0]["numeric_id"],
            "087",
        )

    def test_plist_inspection_is_read_only_and_extracts_release(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "service.plist"
            payload = {
                "WorkingDirectory": (
                    "/tmp/20260727_174450__"
                    "081bd74ae07c327452b2a1fc67bf7df3d73a4b6c"
                )
            }
            with path.open("wb") as handle:
                plistlib.dump(payload, handle)
            fake_git = mock.Mock(returncode=0, stdout="tree-sha\n", stderr="")
            with mock.patch.object(MODULE, "run_git", return_value=fake_git):
                result = MODULE.release_id_from_plist(path)
        self.assertTrue(result["present"])
        self.assertEqual(
            result["commit"],
            "081bd74ae07c327452b2a1fc67bf7df3d73a4b6c",
        )
        self.assertEqual(result["tree"], "tree-sha")

    def test_governance_is_synchronized_across_control_documents(self) -> None:
        policy_ids = {
            row["policy_id"] for row in self.contract["lanes"].values()
        }
        paths = (
            ROOT / "AGENTS.md",
            ROOT / "docs/EXECUTION_COMPILER.md",
            ROOT / "docs/EXECUTION_KERNEL.md",
            ROOT / "docs/EXECUTION_RUNTIME_GATE.md",
            ROOT / "docs/EXECUTION_SANDBOX.md",
            ROOT / "docs/EXECUTION_TEST_SUITE.md",
            ROOT / "docs/EXECUTION_TRACE_SYSTEM.md",
            ROOT / "docs/Architecture.md",
            ROOT / "docs/Roadmap.md",
            ROOT / "docs/Tasks.md",
            ROOT / "docs/RUNTIME_PIPELINE_CONTROL_V0.md",
        )
        for path in paths:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path):
                for policy_id in policy_ids:
                    self.assertIn(policy_id, text)

    def test_planner_has_no_database_or_launchctl_mutation_surface(self) -> None:
        text = SCRIPT_PATH.read_text(encoding="utf-8")
        for forbidden in (
            "psycopg",
            "psql",
            '["launchctl"',
            "['launchctl'",
            "bootout",
            "bootstrap",
            "INSERT INTO",
            "UPDATE ",
            "DELETE FROM",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
