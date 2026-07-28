from __future__ import annotations

from hashlib import sha1, sha256
import json
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
BASELINE_COMMIT = "2eeb05a56663477159c0f60c2a4be3525eae7753"
BASELINE_TREE = "4228bd1efa345d9af5369c08905ac4184e4798fa"
QUOTE_COMMIT = "658ebb3995a7c539ac211258c378af6499635df4"
STOP_087_COMMIT = "edfb66d2a89fd0600a447379f4b0cd532c5d46d7"
STOP_088_COMMIT = "17d30207981de436d11c1467616434853de92b0b"
MANIFEST_PATH = (
    ROOT / "docs/N6_B_TRACK_MIGRATION_IDENTITY_RECONCILIATION_V1.json"
)
REGISTRY_PATH = ROOT / "docs/N6_B_TRACK_BASELINE_REGISTRY_V1.json"
ALLOWLIST = {
    "docs/N6_VIRTUAL_STOP_LOSS_NUMERIC_COALESCE_FIX_087_CONTRACT.json",
    "sql/087_n6_virtual_stop_loss_numeric_coalesce_fix.sql",
    "sql/087_n6_virtual_stop_loss_numeric_coalesce_fix_rollback.sql",
    "tests/test_n6_087_virtual_stop_loss_numeric_coalesce_fix.py",
    "docs/N6_VIRTUAL_STOP_LOSS_EXECUTOR_INSERT_GUARD_088_CONTRACT.json",
    "sql/088_n6_virtual_stop_loss_executor_insert_guard.sql",
    "sql/088_n6_virtual_stop_loss_executor_insert_guard_rollback.sql",
    "tests/test_n6_088_virtual_stop_loss_executor_insert_guard.py",
    "docs/N6_B_TRACK_MIGRATION_IDENTITY_RECONCILIATION_V1.json",
    "tests/test_n6_btrack_service_lineage_convergence.py",
    "docs/N6_B_TRACK_BASELINE_REGISTRY_V1.json",
    "docs/Architecture.md",
    "docs/Roadmap.md",
    "docs/Tasks.md",
    "docs/N6_AI_KNOWLEDGE_BUNDLE_MANIFEST.json",
}


def file_sha256(relative_path: str) -> str:
    return sha256((ROOT / relative_path).read_bytes()).hexdigest()


def file_git_blob(relative_path: str) -> str:
    content = (ROOT / relative_path).read_bytes()
    return sha1(
        b"blob " + str(len(content)).encode("ascii") + b"\0" + content
    ).hexdigest()


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout.strip()


class N6BTrackServiceLineageConvergenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        cls.registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))

    def test_manifest_freezes_exact_gate_baseline_and_allowlist(self) -> None:
        self.assertEqual(
            self.manifest["manifest_version"],
            "N6_B_TRACK_MIGRATION_IDENTITY_RECONCILIATION_V1",
        )
        self.assertEqual(
            self.manifest["gate"],
            "n6_btrack_service_lineage_convergence_v1",
        )
        self.assertEqual(
            self.manifest["canonical_baseline"],
            {"commit": BASELINE_COMMIT, "tree": BASELINE_TREE},
        )
        self.assertEqual(
            set(self.manifest["implementation_allowlist"]), ALLOWLIST
        )
        self.assertEqual(len(self.manifest["implementation_allowlist"]), 15)

    def test_both_historical_087_identities_and_088_are_distinct(self) -> None:
        identities = {
            row["logical_version"]: row
            for row in self.manifest["migration_identities"]
        }
        self.assertEqual(
            set(identities),
            {
                "strategy_center_archive_087_web_v1",
                "virtual_stop_loss_coalesce_087_stop_v1",
                "virtual_stop_loss_guard_088_v1",
            },
        )
        self.assertEqual(
            [
                row["numeric_id"]
                for row in self.manifest["migration_identities"]
            ],
            ["087", "087", "088"],
        )
        policy = self.manifest["identity_rule"]
        self.assertFalse(policy["numeric_prefix_is_unique_identity"])
        self.assertFalse(policy["numeric_glob_execution_allowed"])
        self.assertFalse(policy["silent_renumber_allowed"])
        self.assertFalse(policy["historical_file_rewrite_allowed"])
        self.assertFalse(policy["historical_file_overwrite_allowed"])

    def test_all_identity_files_match_frozen_blob_and_sha256(self) -> None:
        for identity in self.manifest["migration_identities"]:
            for row in identity["files"]:
                with self.subTest(
                    logical_version=identity["logical_version"],
                    path=row["path"],
                ):
                    self.assertTrue((ROOT / row["path"]).is_file())
                    self.assertEqual(
                        file_git_blob(row["path"]), row["git_blob"]
                    )
                    self.assertEqual(
                        file_sha256(row["path"]), row["sha256"]
                    )

    def test_087_and_088_capability_files_are_exact_source_blobs(self) -> None:
        source_by_version = {
            "virtual_stop_loss_coalesce_087_stop_v1": STOP_087_COMMIT,
            "virtual_stop_loss_guard_088_v1": STOP_088_COMMIT,
        }
        identities = {
            row["logical_version"]: row
            for row in self.manifest["migration_identities"]
        }
        for logical_version, source_commit in source_by_version.items():
            for row in identities[logical_version]["files"]:
                with self.subTest(
                    logical_version=logical_version, path=row["path"]
                ):
                    self.assertEqual(
                        git("rev-parse", f"{source_commit}:{row['path']}"),
                        row["git_blob"],
                    )
                    self.assertEqual(
                        file_git_blob(row["path"]), row["git_blob"]
                    )

    def test_web_087_archive_files_remain_exact_baseline_blobs(self) -> None:
        web = next(
            row
            for row in self.manifest["migration_identities"]
            if row["logical_version"]
            == "strategy_center_archive_087_web_v1"
        )
        for row in web["files"]:
            with self.subTest(path=row["path"]):
                self.assertEqual(
                    git("rev-parse", f"{BASELINE_COMMIT}:{row['path']}"),
                    row["git_blob"],
                )
                self.assertEqual(file_git_blob(row["path"]), row["git_blob"])

    def test_preserved_capability_blobs_match_frozen_convergence_commit(
        self,
    ) -> None:
        locks = self.manifest["preserved_blob_locks"]
        for family, rows in locks.items():
            for relative_path, expected_blob in rows.items():
                with self.subTest(family=family, path=relative_path):
                    self.assertEqual(
                        git(
                            "rev-parse",
                            f"{BASELINE_COMMIT}:{relative_path}",
                        ),
                        expected_blob,
                    )

    def test_registry_records_correct_lineage_without_runtime_upgrade(
        self,
    ) -> None:
        lineage = self.registry["lineage"]
        self.assertEqual(lineage["status"], "FRAGMENTED")
        self.assertEqual(lineage["database_state"], "NOT_READ")
        self.assertFalse(lineage["database_accessed"])
        self.assertFalse(lineage["single_release_ready"])
        self.assertEqual(
            lineage["quote_stop_loss_merge_base"], QUOTE_COMMIT
        )
        self.assertTrue(lineage["quote_is_ancestor_of_stop_loss"])
        self.assertFalse(
            self.registry["canonical_integration"][
                "deployment_authorized"
            ]
        )
        self.assertEqual(
            self.manifest["production_state"]["lineage"], "FRAGMENTED"
        )
        self.assertEqual(
            self.manifest["production_state"]["database_state"], "NOT_READ"
        )
        self.assertFalse(
            self.manifest["production_state"]["deployment_authorized"]
        )

    def test_quote_to_stop_merge_base_is_live_git_fact(self) -> None:
        self.assertEqual(
            git("merge-base", QUOTE_COMMIT, STOP_087_COMMIT),
            QUOTE_COMMIT,
        )
        self.assertEqual(
            git("merge-base", "--is-ancestor", QUOTE_COMMIT, STOP_087_COMMIT),
            "",
        )

    def test_control_documents_describe_offline_not_deployed_state(
        self,
    ) -> None:
        for relative_path in (
            "docs/Architecture.md",
            "docs/Roadmap.md",
            "docs/Tasks.md",
        ):
            text = (ROOT / relative_path).read_text(encoding="utf-8")
            with self.subTest(path=relative_path):
                self.assertIn(
                    "n6_btrack_service_lineage_convergence_v1", text
                )
                self.assertIn(
                    "N6_B_TRACK_MIGRATION_IDENTITY_RECONCILIATION_V1",
                    text,
                )
                self.assertIn("FRAGMENTED", text)
                self.assertIn("NOT_READ", text)
                self.assertIn("deployment_authorized=false", text)

    def test_acceptance_remains_offline_and_fail_closed(self) -> None:
        self.assertEqual(
            self.manifest["status"], "OFFLINE_CANDIDATE_NOT_DEPLOYED"
        )
        acceptance = self.manifest["acceptance"]
        self.assertTrue(acceptance["isolated_pg16_required"])
        self.assertFalse(acceptance["active_database_allowed"])
        self.assertTrue(
            acceptance["baseline_aware_complete_test_n6_required"]
        )
        self.assertFalse(acceptance["new_failure_allowed"])
        self.assertFalse(
            acceptance["existing_failure_signature_drift_allowed"]
        )
        self.assertFalse(
            acceptance["deployment_or_runtime_operation_allowed"]
        )


if __name__ == "__main__":
    unittest.main()
