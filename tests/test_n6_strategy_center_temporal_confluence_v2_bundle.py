from __future__ import annotations

import ast
from contextlib import contextmanager
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = (
    ROOT
    / "scripts/build_n6_strategy_center_temporal_confluence_v2_bundle.py"
)
BUNDLE_PATH = (
    ROOT
    / "config/n6_strategy_center/"
    "N6_SC_TEMPORAL_CONFLUENCE_V2_SHADOW_BUNDLE_20260723.json"
)
EXPECTED_CANONICAL_SHA256 = (
    "17c655213243a820955fe154ac981f1d2b9f16e580bc93a1042d0d9e846986f9"
)
EXPECTED_IMPLEMENTATION_COMMIT = (
    "5c2c38d184385a317afe69b6397f7d98393ff24f"
)
EXPECTED_IMPLEMENTATION_TREE = (
    "0a02ac53513946ca530d3420b2bd06c60630388e"
)
EXPECTED_BUNDLE_SHA256 = (
    "119296de69f27b840cf743f2d6aad04fe56bd7f1ca80991dbdf5be3f547ca1e0"
)
EXPECTED_BUNDLE_FILE_SHA256 = (
    "6efda6309d8e6ebb2d8e91d4a961a0855a76a239c8dd36c45534a50778a190d8"
)


def load_builder():
    spec = importlib.util.spec_from_file_location(
        "build_n6_strategy_center_temporal_confluence_v2_bundle",
        BUILDER_PATH,
    )
    if spec is None or spec.loader is None:
        raise AssertionError("shadow_bundle_builder_import_failed")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_git(root: Path, *args: str) -> str:
    return subprocess.run(
        ("git", "-C", str(root), *args),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()


def copy_path(source_root: Path, target_root: Path, relative_path: str) -> None:
    source = source_root / relative_path
    target = target_root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


@contextmanager
def changed_file(path: Path, content: bytes):
    original = path.read_bytes()
    original_mode = path.stat().st_mode
    path.write_bytes(content)
    try:
        yield
    finally:
        path.write_bytes(original)
        os.chmod(path, original_mode)


class TemporalConfluenceV2ShadowBundleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.builder = load_builder()
        cls.temporary_directory = tempfile.TemporaryDirectory()
        cls.fixture_root = Path(cls.temporary_directory.name).resolve()
        shutil.copytree(
            ROOT / "src/ashare_v3",
            cls.fixture_root / "src/ashare_v3",
        )
        for relative_path in cls.builder.FROZEN_IMPLEMENTATION_FILES:
            if not relative_path.startswith("src/ashare_v3/"):
                copy_path(ROOT, cls.fixture_root, relative_path)
        run_git(cls.fixture_root, "init", "--quiet")
        run_git(cls.fixture_root, "config", "user.name", "Bundle Test")
        run_git(
            cls.fixture_root,
            "config",
            "user.email",
            "bundle-test@example.invalid",
        )
        run_git(
            cls.fixture_root,
            "add",
            "--",
            *cls.builder.FROZEN_IMPLEMENTATION_FILES,
        )
        run_git(
            cls.fixture_root,
            "commit",
            "--quiet",
            "-m",
            "test: freeze temporal confluence fixture",
        )
        cls.implementation_commit = run_git(
            cls.fixture_root, "rev-parse", "HEAD"
        )
        cls.implementation_tree = run_git(
            cls.fixture_root, "rev-parse", "HEAD^{tree}"
        )
        cls.bundle = cls.builder.build_bundle(
            cls.fixture_root,
            implementation_commit=cls.implementation_commit,
            implementation_tree=cls.implementation_tree,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary_directory.cleanup()

    def test_bundle_rebuilds_exactly(self) -> None:
        rebuilt = self.builder.build_bundle(
            self.fixture_root,
            implementation_commit=self.bundle["implementation_commit"],
            implementation_tree=self.bundle["implementation_tree"],
        )
        self.assertEqual(rebuilt, self.bundle)
        without_hash = {
            key: value
            for key, value in self.bundle.items()
            if key != "bundle_sha256"
        }
        self.assertEqual(
            self.bundle["bundle_sha256"],
            self.builder.canonical_hash(without_hash),
        )
        scheduler = self.bundle["scheduler_contract"]
        self.assertEqual(scheduler["max_runtime_seconds"], 12)
        self.assertTrue(
            scheduler["active_replay_pending_precedes_round_robin"]
        )
        self.assertEqual(
            scheduler["future_reviewed_trade_date_status"],
            "WAITING_OPEN_TRADE_DATE",
        )
        self.assertEqual(
            scheduler["stale_reviewed_trade_date_status"],
            "BLOCKED_STALE_TRADE_DATE_AUTHORITY",
        )
        self.assertEqual(
            scheduler["history_persistence"],
            "o1_append_atomic_bounded_size_rotation",
        )

    def test_checked_in_bundle_rebuilds_exactly(self) -> None:
        relative_path = BUNDLE_PATH.relative_to(ROOT).as_posix()
        tracked = subprocess.run(
            (
                "git",
                "-C",
                str(ROOT),
                "ls-files",
                "--error-unmatch",
                "--",
                relative_path,
            ),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).returncode == 0
        if not tracked:
            self.assertFalse(tracked)
            return
        checked_in = json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))
        rebuilt = self.builder.build_bundle(
            ROOT,
            implementation_commit=checked_in["implementation_commit"],
            implementation_tree=checked_in["implementation_tree"],
        )
        self.assertEqual(rebuilt, checked_in)

    def test_checked_in_bundle_attests_v1_fail_closed_implementation(
        self,
    ) -> None:
        checked_in = json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            self.builder.EXPECTED_CANONICAL_SHA256,
            EXPECTED_CANONICAL_SHA256,
        )
        self.assertEqual(
            checked_in["canonical_strategy"]["sha256"],
            EXPECTED_CANONICAL_SHA256,
        )
        self.assertEqual(
            checked_in["implementation_commit"],
            EXPECTED_IMPLEMENTATION_COMMIT,
        )
        self.assertEqual(
            checked_in["implementation_tree"],
            EXPECTED_IMPLEMENTATION_TREE,
        )
        self.assertEqual(
            checked_in["bundle_sha256"],
            EXPECTED_BUNDLE_SHA256,
        )
        self.assertEqual(
            sha256(BUNDLE_PATH.read_bytes()).hexdigest(),
            EXPECTED_BUNDLE_FILE_SHA256,
        )

    def test_fake_zero_one_identity_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            ValueError, "^implementation_commit_not_commit$"
        ):
            self.builder.build_bundle(
                self.fixture_root,
                implementation_commit="0" * 40,
                implementation_tree="1" * 40,
            )

    def test_tree_object_cannot_masquerade_as_commit(self) -> None:
        with self.assertRaisesRegex(
            ValueError, "^implementation_commit_not_commit$"
        ):
            self.builder.build_bundle(
                self.fixture_root,
                implementation_commit=self.implementation_tree,
                implementation_tree=self.implementation_tree,
            )

    def test_implementation_tree_mismatch_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            ValueError, "^implementation_tree_mismatch$"
        ):
            self.builder.build_bundle(
                self.fixture_root,
                implementation_commit=self.implementation_commit,
                implementation_tree="f" * 40,
            )

    def test_dirty_runtime_file_is_rejected(self) -> None:
        relative_path = self.builder.RUNTIME_FILES[0]
        target = self.fixture_root / relative_path
        with changed_file(target, target.read_bytes() + b"\n# dirty\n"):
            with self.assertRaisesRegex(
                ValueError,
                "^git_frozen_file_bytes_mismatch:"
                + re.escape(relative_path)
                + "$",
            ):
                self.builder.build_bundle(
                    self.fixture_root,
                    implementation_commit=self.implementation_commit,
                    implementation_tree=self.implementation_tree,
                )

    def test_candidate_mismatch_is_rejected_before_bundle_generation(
        self,
    ) -> None:
        relative_path = self.builder.CANDIDATE_PATH
        target = self.fixture_root / relative_path
        with changed_file(target, target.read_bytes() + b"\n"):
            with self.assertRaisesRegex(
                ValueError,
                "^git_frozen_file_bytes_mismatch:"
                + re.escape(relative_path)
                + "$",
            ):
                self.builder.build_bundle(
                    self.fixture_root,
                    implementation_commit=self.implementation_commit,
                    implementation_tree=self.implementation_tree,
                )

    def test_frozen_file_mode_mismatch_is_rejected(self) -> None:
        relative_path = self.builder.RUNTIME_FILES[0]
        target = self.fixture_root / relative_path
        original_mode = target.stat().st_mode
        os.chmod(target, original_mode | 0o111)
        try:
            with self.assertRaisesRegex(
                ValueError,
                "^git_frozen_file_mode_mismatch:"
                + re.escape(relative_path)
                + "$",
            ):
                self.builder.build_bundle(
                    self.fixture_root,
                    implementation_commit=self.implementation_commit,
                    implementation_tree=self.implementation_tree,
                )
        finally:
            os.chmod(target, original_mode)

    def test_symlinked_frozen_file_is_rejected(self) -> None:
        relative_path = self.builder.RUNTIME_FILES[0]
        target = self.fixture_root / relative_path
        original = target.read_bytes()
        original_mode = target.stat().st_mode
        target.unlink()
        target.symlink_to(self.fixture_root / self.builder.CANDIDATE_PATH)
        try:
            with self.assertRaisesRegex(
                ValueError,
                "^git_frozen_file_not_regular:"
                + re.escape(relative_path)
                + "$",
            ):
                self.builder.build_bundle(
                    self.fixture_root,
                    implementation_commit=self.implementation_commit,
                    implementation_tree=self.implementation_tree,
                )
        finally:
            target.unlink()
            target.write_bytes(original)
            os.chmod(target, original_mode)

    def test_candidate_and_canonical_are_exactly_frozen(self) -> None:
        candidate = self.bundle["candidate"]
        canonical = self.bundle["canonical_strategy"]
        self.assertEqual(
            candidate["sha256"],
            self.builder.EXPECTED_CANDIDATE_SHA256,
        )
        self.assertEqual(
            canonical["sha256"],
            self.builder.EXPECTED_CANONICAL_SHA256,
        )
        for entry in (candidate, canonical):
            self.assertEqual(
                sha256(
                    (self.fixture_root / entry["path"]).read_bytes()
                ).hexdigest(),
                entry["sha256"],
            )
        payload = json.loads(
            (self.fixture_root / candidate["path"]).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(payload["package_id"], self.builder.PACKAGE_ID)
        self.assertEqual(
            payload["strategy_version"],
            self.builder.STRATEGY_VERSION,
        )
        self.assertEqual(
            payload["package_versions"],
            {"package_1": "v2", "package_2": "v2"},
        )

    def test_runtime_files_and_policy_hash_are_exact(self) -> None:
        self.assertIn(
            "src/ashare_v3/user/strategy_center_repository.py",
            self.builder.RUNTIME_FILES,
        )
        self.assertIn(
            "src/ashare_v3/web/n6_app_v1.py",
            self.builder.RUNTIME_FILES,
        )
        self.assertIn(
            "src/ashare_v3/web/templates/n6_app_shell.html",
            self.builder.RUNTIME_FILES,
        )
        self.assertEqual(
            [entry["path"] for entry in self.bundle["runtime_files"]],
            list(self.builder.RUNTIME_FILES),
        )
        for entry in self.bundle["runtime_files"]:
            self.assertEqual(
                sha256(
                    (self.fixture_root / entry["path"]).read_bytes()
                ).hexdigest(),
                entry["sha256"],
            )
        src = self.fixture_root / "src"
        sys.path.insert(0, str(src))
        try:
            from ashare_v3.user.strategy_center import (
                APPROVED_PACKAGE_POLICY_HASHES,
                EVALUATOR_POLICY_HASH,
            )
        finally:
            sys.path.pop(0)
        self.assertEqual(
            self.bundle["implementation_policy_hash"],
            EVALUATOR_POLICY_HASH,
        )
        self.assertEqual(
            self.bundle["approved_package_policy_hashes"],
            APPROVED_PACKAGE_POLICY_HASHES,
        )

    def test_catalog_and_compensation_artifacts_are_frozen(self) -> None:
        artifacts = self.bundle["catalog_artifacts"]
        expected = {
            "migration": self.builder.MIGRATION_PATH,
            "rollback": self.builder.ROLLBACK_PATH,
            "user_compensation_migration": (
                self.builder.COMPENSATION_MIGRATION_PATH
            ),
            "user_compensation_rollback": (
                self.builder.COMPENSATION_ROLLBACK_PATH
            ),
            "catalog_activation_migration": (
                self.builder.ACTIVATION_MIGRATION_PATH
            ),
            "catalog_activation_rollback": (
                self.builder.ACTIVATION_ROLLBACK_PATH
            ),
            "trade_date_authority_migration": (
                self.builder.TRADE_DATE_AUTHORITY_MIGRATION_PATH
            ),
            "trade_date_authority_rollback": (
                self.builder.TRADE_DATE_AUTHORITY_ROLLBACK_PATH
            ),
        }
        for key, relative_path in expected.items():
            self.assertEqual(artifacts[key]["path"], relative_path)
            self.assertEqual(
                artifacts[key]["sha256"],
                sha256(
                    (self.fixture_root / relative_path).read_bytes()
                ).hexdigest(),
            )
            self.assertFalse(artifacts[key]["applied"])
        self.assertFalse(
            artifacts["single_scope_revision_generated_on_apply"]
        )
        self.assertFalse(artifacts["all_users_transaction"])

    def test_package_v2_authority_is_bound_to_candidate_content(self) -> None:
        candidate = json.loads(
            (
                self.fixture_root / self.bundle["candidate"]["path"]
            ).read_text(encoding="utf-8")
        )
        for package_key in self.builder.ALLOWED_PACKAGE_KEYS:
            package_payload = self.builder._candidate_package_payload(
                candidate, package_key
            )
            self.assertEqual(
                self.builder.canonical_hash(package_payload),
                self.bundle["approved_package_policy_hashes"][package_key],
            )

    def test_scheduler_is_single_scope_pending_first_round_robin(self) -> None:
        contract = self.bundle["scheduler_contract"]
        self.assertEqual(contract["max_scopes_per_tick"], 1)
        self.assertTrue(contract["pending_precedes_active"])
        self.assertEqual(
            contract["pending_scope_order"],
            ["selection_revision_id", "principal_id", "user_id"],
        )
        self.assertEqual(
            contract["active_scope_cursor_mode"],
            "persistent_round_robin",
        )
        self.assertEqual(
            contract["transaction_scope"],
            "single_principal_user_revision",
        )
        self.assertFalse(contract["all_users_transaction"])

        runner_path = (
            ROOT / "scripts/run_n6_strategy_center_auto_once.py"
        )
        tree = ast.parse(runner_path.read_text(encoding="utf-8"))
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "run_strategy_center_once"
        ]
        self.assertEqual(len(calls), 1)
        keywords = {keyword.arg for keyword in calls[0].keywords}
        self.assertIn("scope", keywords)
        self.assertNotIn("selection_revision_ids", keywords)
        self.assertIn("time_tick", runner_path.read_text(encoding="utf-8"))

    def test_evaluation_time_freeze_contract_is_attested(self) -> None:
        worker = (
            ROOT / "src/ashare_v3/user/strategy_center_worker.py"
        ).read_text(encoding="utf-8")
        runner = (
            ROOT / "scripts/run_n6_strategy_center_once.py"
        ).read_text(encoding="utf-8")
        self.assertTrue(
            all(
                marker in worker
                for marker in self.builder.EVALUATION_TIME_CONTRACT_MARKERS[
                    "src/ashare_v3/user/strategy_center_worker.py"
                ]
            )
        )
        self.assertIn("--evaluation-time", runner)

    def test_reviewed_n6_trade_date_authority_is_attested(self) -> None:
        self.assertEqual(
            len(self.builder.FROZEN_IMPLEMENTATION_FILES),
            19,
        )
        contract = self.bundle["trade_date_authority_contract"]
        self.assertEqual(
            contract["authority"],
            "reviewed_n6_display_view_consensus",
        )
        self.assertEqual(
            contract["required_asset_kinds"],
            ["stock", "index", "board"],
        )
        self.assertEqual(
            contract["per_asset_latest_batch"],
            "nonempty_singleton_source_trade_date_for_trade_date_run_id",
        )
        self.assertTrue(
            contract["cross_asset_for_trade_date_consensus_required"]
        )
        self.assertEqual(
            contract["per_asset_lineage_frozen"],
            [
                "source_trade_date",
                "for_trade_date",
                "source_run_id",
                "row_count",
            ],
        )
        self.assertEqual(
            contract["reviewed_current_date_sources"],
            ["user_signal_projection", "user_signal_card"],
        )
        self.assertTrue(
            contract["pending_revision_allowed_without_reviewed_events"]
        )
        self.assertTrue(
            contract["bounded_canary_requires_natural_event_group"]
        )
        self.assertEqual(
            contract["membership_authority"],
            "max_membership_trade_date_lte_event_source_trade_date",
        )
        self.assertFalse(contract["common_trade_calendar_required"])
        for relative_path, markers in (
            self.builder.TRADE_DATE_AUTHORITY_CONTRACT_MARKERS.items()
        ):
            source = (
                self.fixture_root / relative_path
            ).read_text(encoding="utf-8")
            self.assertNotIn("common_trade_calendar", source)
            for marker in markers:
                self.assertIn(marker, source)

    def test_only_four_n6_strategy_tables_are_writable(self) -> None:
        boundary = self.bundle["runtime_boundary"]
        self.assertEqual(
            boundary["allowed_write_tables"],
            list(self.builder.ALLOWED_WRITE_TABLES),
        )
        self.assertTrue(boundary["display_only"])
        self.assertTrue(boundary["shadow_only"])
        self.assertFalse(boundary["deepseek_required"])
        self.assertEqual(
            boundary["forbidden_mutations"],
            list(self.builder.FORBIDDEN_MUTATIONS),
        )

        worker = (
            ROOT / "src/ashare_v3/user/strategy_center_worker.py"
        ).read_text(encoding="utf-8")
        writes = {
            match.group(1).split(".")[-1]
            for match in re.finditer(
                r"(?i)\b(?:insert\s+into|update|delete\s+from)\s+"
                r"(?:public\.)?([a-z0-9_]+)",
                worker,
            )
        }
        self.assertEqual(
            writes,
            set(self.builder.ALLOWED_WRITE_TABLES),
        )
        for forbidden in (
            "n6_virtual_trade_proposal",
            "n6_virtual_order",
            "n6_virtual_trade",
            "n6_virtual_position_lot",
            "n6_virtual_cash_snapshot",
            "n6_virtual_cash_ledger",
        ):
            self.assertNotIn(forbidden, writes)

    def test_bundle_cannot_authorize_activation(self) -> None:
        activation = self.bundle["activation"]
        self.assertEqual(
            activation["status"],
            "BLOCKED_PENDING_SCHEMA_RELEASE_CANARY",
        )
        self.assertFalse(
            activation["current_kernel_policy_update_required"]
        )
        self.assertTrue(
            activation["evaluator_rebind_contract_required"]
        )
        self.assertTrue(
            activation[
                "fresh_current_reviewed_n6_trade_date_exact_release_canary_required"
            ]
        )
        self.assertTrue(activation["v2_package_catalog_required"])
        self.assertTrue(
            activation["single_scope_v2_selection_revision_required"]
        )
        self.assertTrue(
            activation["qualified_and_observation_surfaces_required"]
        )
        self.assertTrue(
            activation["canonical_signal_dto_isolation_build_complete"]
        )
        self.assertTrue(activation["v1_v2_coexistence_build_complete"])
        self.assertTrue(
            activation["per_user_v2_to_v1_compensation_build_complete"]
        )
        self.assertTrue(
            activation["failed_pending_v2_abandonment_build_complete"]
        )
        self.assertTrue(
            activation["v2_catalog_activation_migration_build_complete"]
        )
        self.assertTrue(
            activation["n6_trade_date_authority_migration_build_complete"]
        )
        self.assertTrue(
            activation[
                "selection_write_quiesce_during_schema_release_transition_required"
            ]
        )
        self.assertTrue(
            activation["v1_grandfather_activation_is_separate_gate"]
        )
        self.assertFalse(
            activation["historical_selection_rewrite_authorized"]
        )
        self.assertFalse(
            activation["launch_agent_switch_authorized_by_bundle"]
        )


if __name__ == "__main__":
    unittest.main()
