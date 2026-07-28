from __future__ import annotations

import ast
from hashlib import sha1, sha256
import json
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_PATH = (
    ROOT
    / "docs/N6_B_TRACK_PRESERVED_CAPABILITY_BLOB_LOCK_FORWARD_SCOPE_CLOSEOUT_V1.json"
)
HISTORICAL_MANIFEST_PATH = (
    ROOT / "docs/N6_B_TRACK_MIGRATION_IDENTITY_RECONCILIATION_V1.json"
)
CONVERGENCE_TEST_PATH = (
    ROOT / "tests/test_n6_btrack_service_lineage_convergence.py"
)
HISTORICAL_COMMIT = "2eeb05a56663477159c0f60c2a4be3525eae7753"
FUNCTIONAL_CANDIDATE = "75470cc4ee06e94c79fb925b74e28bb7e2f5a617"
CANONICAL_BASELINE = "09718870086ff2611b7e19ab741b636bae542d97"
OLD_MANIFEST_SHA256 = (
    "97a9e5e182b38dadee139179cc138b6d2a145406a23742f13b9b353354150047"
)
OLD_MANIFEST_BLOB = "afb01d3eafc4ac95acf8f2b16740836fb7e414fc"


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode:
        raise AssertionError(result.stderr.decode("utf-8", errors="replace"))
    return result


def git_text(*args: str) -> str:
    return git(*args).stdout.decode("utf-8").strip()


def git_bytes(commit: str, relative_path: str) -> bytes:
    return git("show", f"{commit}:{relative_path}").stdout


def blob_for_bytes(content: bytes) -> str:
    return sha1(
        b"blob " + str(len(content)).encode("ascii") + b"\0" + content
    ).hexdigest()


class N6BTrackPreservedCapabilityBlobLockForwardScopeCloseoutTest(
    unittest.TestCase
):
    @classmethod
    def setUpClass(cls) -> None:
        cls.artifact = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
        cls.historical_manifest_bytes = HISTORICAL_MANIFEST_PATH.read_bytes()
        cls.historical_manifest = json.loads(
            cls.historical_manifest_bytes.decode("utf-8")
        )

    def test_artifact_freezes_gate_and_candidate_identity(self) -> None:
        self.assertEqual(
            self.artifact["artifact_version"],
            "N6_B_TRACK_PRESERVED_CAPABILITY_BLOB_LOCK_FORWARD_SCOPE_CLOSEOUT_V1",
        )
        self.assertEqual(
            self.artifact["gate"],
            "n6_btrack_preserved_capability_blob_lock_forward_scope_closeout_v1",
        )
        self.assertEqual(self.artifact["layer_role"], "runtime_control")
        self.assertEqual(self.artifact["execution_mode"], "FULL_MODE")
        candidate = self.artifact["functional_candidate"]
        self.assertEqual(candidate["commit"], FUNCTIONAL_CANDIDATE)
        self.assertEqual(
            candidate["tree"],
            "687db80dca64868f75a449c0780bcab1165eb255",
        )
        self.assertEqual(candidate["parent"], CANONICAL_BASELINE)

    def test_historical_manifest_is_byte_for_byte_unchanged(self) -> None:
        authority = self.artifact["historical_convergence_authority"][
            "manifest"
        ]
        self.assertEqual(len(self.historical_manifest_bytes), 8843)
        self.assertEqual(
            sha256(self.historical_manifest_bytes).hexdigest(),
            OLD_MANIFEST_SHA256,
        )
        self.assertEqual(
            blob_for_bytes(self.historical_manifest_bytes), OLD_MANIFEST_BLOB
        )
        self.assertEqual(authority["sha256"], OLD_MANIFEST_SHA256)
        self.assertEqual(authority["git_blob"], OLD_MANIFEST_BLOB)
        self.assertFalse(authority["rewrite_allowed"])

    def test_historical_locks_resolve_only_from_frozen_commit(self) -> None:
        for family, rows in self.historical_manifest[
            "preserved_blob_locks"
        ].items():
            for relative_path, expected_blob in rows.items():
                with self.subTest(family=family, path=relative_path):
                    frozen = git_bytes(HISTORICAL_COMMIT, relative_path)
                    self.assertEqual(blob_for_bytes(frozen), expected_blob)
                    self.assertEqual(
                        git_text(
                            "rev-parse",
                            f"{HISTORICAL_COMMIT}:{relative_path}",
                        ),
                        expected_blob,
                    )

    def test_moving_candidate_does_not_impersonate_historical_lock(self) -> None:
        locks = {
            path: blob
            for rows in self.historical_manifest[
                "preserved_blob_locks"
            ].values()
            for path, blob in rows.items()
        }
        changed_locked_paths = {
            path
            for path, historical_blob in locks.items()
            if git_text(
                "rev-parse", f"{FUNCTIONAL_CANDIDATE}:{path}"
            )
            != historical_blob
        }
        self.assertEqual(
            changed_locked_paths,
            {
                "src/ashare_v3/web/n6_app_v1.py",
                "src/ashare_v3/web/n6_user_app.py",
                "src/ashare_v3/web/templates/n6_app_shell.html",
            },
        )
        for path in changed_locked_paths:
            self.assertEqual(
                git_text("rev-parse", f"{HISTORICAL_COMMIT}:{path}"),
                locks[path],
            )

    def test_convergence_test_no_longer_reads_checkout_for_historical_locks(
        self,
    ) -> None:
        tree = ast.parse(CONVERGENCE_TEST_PATH.read_text(encoding="utf-8"))
        method = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name
            == "test_preserved_capability_blobs_match_frozen_convergence_commit"
        )
        called_names = {
            node.func.id
            for node in ast.walk(method)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertNotIn("file_git_blob", called_names)
        self.assertIn("git", called_names)

    def test_functional_candidate_four_file_blobs_and_sha256_match(self) -> None:
        candidate = self.artifact["functional_candidate"]
        expected_paths = candidate["original_implementation_allowlist"]
        self.assertEqual(len(expected_paths), 4)
        self.assertEqual(
            [row["path"] for row in candidate["files"]], expected_paths
        )
        for row in candidate["files"]:
            with self.subTest(path=row["path"]):
                content = git_bytes(FUNCTIONAL_CANDIDATE, row["path"])
                self.assertEqual(blob_for_bytes(content), row["git_blob"])
                self.assertEqual(
                    sha256(content).hexdigest(), row["sha256"]
                )
                self.assertEqual(
                    git_text(
                        "rev-parse",
                        f"{FUNCTIONAL_CANDIDATE}:{row['path']}",
                    ),
                    row["git_blob"],
                )

    def test_functional_candidate_diff_is_exact_original_allowlist(
        self,
    ) -> None:
        changed_paths = {
            line.split("\t", 1)[1]
            for line in git_text(
                "diff-tree",
                "--no-commit-id",
                "--name-status",
                "-r",
                FUNCTIONAL_CANDIDATE,
            ).splitlines()
        }
        self.assertEqual(
            changed_paths,
            set(
                self.artifact["functional_candidate"][
                    "original_implementation_allowlist"
                ]
            ),
        )

    def test_candidate_classification_is_l1_get_only_post_review(self) -> None:
        candidate = self.artifact["functional_candidate"]
        self.assertEqual(candidate["delivery_lane"], "L1")
        self.assertEqual(
            candidate["policy_id"],
            "n6_btrack_delivery_l1_web_readonly_v1",
        )
        self.assertEqual(candidate["route_scope"], "GET_ONLY")
        self.assertEqual(
            candidate["review_classification"], "POST_REVIEW_PASS"
        )
        self.assertFalse(candidate["database_write_allowed"])
        self.assertFalse(candidate["runtime_operation_allowed"])

    def test_missing_historical_authority_fails_closed(self) -> None:
        missing = git(
            "show",
            f"{HISTORICAL_COMMIT}:does/not/exist",
            check=False,
        )
        self.assertNotEqual(missing.returncode, 0)
        self.assertEqual(missing.stdout, b"")

    def test_control_docs_register_forward_scope_without_deployment(self) -> None:
        for relative_path in (
            "docs/Architecture.md",
            "docs/Roadmap.md",
            "docs/Tasks.md",
        ):
            text = (ROOT / relative_path).read_text(encoding="utf-8")
            with self.subTest(path=relative_path):
                self.assertIn(
                    "n6_btrack_preserved_capability_blob_lock_forward_scope_closeout_v1",
                    text,
                )
                self.assertIn(FUNCTIONAL_CANDIDATE, text)
                self.assertIn("POST_REVIEW_PASS", text)
                self.assertIn(
                    "n6_btrack_canonical_integration_fast_forward_v1",
                    text,
                )
                self.assertIn("未部署", text)

    def test_closeout_does_not_weaken_acceptance(self) -> None:
        contract = self.artifact["test_classification_contract"]
        self.assertEqual(
            contract["canonical_baseline_commit"], CANONICAL_BASELINE
        )
        self.assertEqual(contract["functional_new_fail_required"], 0)
        self.assertTrue(
            contract[
                "historical_or_environment_failures_must_be_reported_separately"
            ]
        )
        self.assertFalse(contract["skip_or_assertion_weakening_allowed"])


if __name__ == "__main__":
    unittest.main()
