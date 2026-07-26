from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re
import stat
import unittest


ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "requirements/n6_strategy_evaluator_py311.lock.txt"
MANIFEST_PATH = (
    ROOT
    / "requirements/n6_strategy_evaluator_py311.wheel-manifest.v1.json"
)
BASELINE_COMMIT = "dfb5b04a9fd771377369344c6d27da9292ef496f"
BASELINE_TREE = "59716932610edea635c8088c091b5a50d5374051"
FIXED_WHEELHOUSE_ROOT = Path(
    "/Users/chuanfuchen/.local/share/ashare-v3/wheelhouses/n6-b-track"
)
FIXED_EVIDENCE_ROOT = Path(
    "/Users/chuanfuchen/.local/state/ashare-v3/n6-b-track/manifests"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PIN_RE = re.compile(
    r"^([A-Za-z0-9_.-]+)(?:\[([A-Za-z0-9_.-]+)\])?==([^\s]+) \\\n"
    r"    --hash=sha256:([0-9a-f]{64})$",
    re.MULTILINE,
)


def canonical_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def parse_lock(lock_text: str) -> dict[str, dict[str, str]]:
    if lock_text.count("--only-binary=:all:") != 1:
        raise ValueError("lock_only_binary_directive_missing_or_duplicate")
    if lock_text.count("--require-hashes") != 1:
        raise ValueError("lock_require_hashes_directive_missing_or_duplicate")

    package_lines = [
        line
        for line in lock_text.splitlines()
        if "==" in line and not line.lstrip().startswith("#")
    ]
    rows: dict[str, dict[str, str]] = {}
    for match in PIN_RE.finditer(lock_text):
        name = canonical_name(match.group(1))
        if name in rows:
            raise ValueError(f"lock_duplicate_package:{name}")
        rows[name] = {
            "version": match.group(3),
            "sha256": match.group(4),
            "extras": match.group(2) or "",
        }
    if len(rows) != len(package_lines):
        raise ValueError("lock_pin_without_hash")
    if not rows:
        raise ValueError("lock_empty")
    return rows


def payload_sha256(payload: dict[str, object]) -> str:
    body = copy.deepcopy(payload)
    body.pop("integrity", None)
    encoded = json.dumps(
        body,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def refresh_integrity(payload: dict[str, object]) -> None:
    payload["integrity"] = {
        "canonicalization": (
            "sha256(json_utf8_sort_keys_compact_without_integrity)"
        ),
        "payload_sha256": payload_sha256(payload),
    }


def validate_contract(payload: dict[str, object], lock_text: str) -> None:
    blockers: list[str] = []
    try:
        lock_rows = parse_lock(lock_text)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc

    integrity = payload.get("integrity")
    if not isinstance(integrity, dict):
        blockers.append("manifest_integrity_missing")
    elif integrity.get("payload_sha256") != payload_sha256(payload):
        blockers.append("manifest_integrity_mismatch")

    if payload.get("contract") != (
        "n6-strategy-evaluator-dependency-wheel-manifest-v1"
    ):
        blockers.append("manifest_contract_invalid")
    if payload.get("status") != (
        "PASS_DEPENDENCY_LOCK_WHEELHOUSE_PREPARED_NOT_RUNTIME_ENV"
    ):
        blockers.append("manifest_status_invalid")

    application_source = payload.get("application_source") or {}
    if application_source.get("commit") != BASELINE_COMMIT:
        blockers.append("application_commit_drift")
    if application_source.get("tree") != BASELINE_TREE:
        blockers.append("application_tree_drift")
    if application_source.get("existing_blob_changes_allowed") is not False:
        blockers.append("application_blob_change_not_forbidden")

    resolver = payload.get("resolver") or {}
    if resolver.get("index_url") != "https://pypi.org/simple":
        blockers.append("resolver_index_not_official")
    if resolver.get("allowed_hosts") != [
        "files.pythonhosted.org",
        "pypi.org",
    ]:
        blockers.append("resolver_hosts_not_official")
    if resolver.get("pip_version") != "22.3.1":
        blockers.append("resolver_version_drift")
    if resolver.get("pip_wheel_current_user_writable") is not False:
        blockers.append("resolver_wheel_writable")
    if not SHA256_RE.fullmatch(str(resolver.get("pip_wheel_sha256") or "")):
        blockers.append("resolver_wheel_sha_invalid")
    for key in ("report_path", "roots_path"):
        evidence_path = Path(str(resolver.get(key) or ""))
        if evidence_path.parent != FIXED_EVIDENCE_ROOT:
            blockers.append(f"resolver_{key}_outside_evidence_root")
    for key in ("report_sha256", "roots_sha256"):
        if not SHA256_RE.fullmatch(str(resolver.get(key) or "")):
            blockers.append(f"resolver_{key}_invalid")

    closure = payload.get("closure") or {}
    direct_roots = closure.get("direct_roots") or []
    direct_root_map = {
        canonical_name(str(item.get("name") or "")): item
        for item in direct_roots
        if isinstance(item, dict)
    }
    expected_roots = {"fastapi", "jinja2", "openpyxl", "psycopg"}
    if set(direct_root_map) != expected_roots:
        blockers.append("direct_root_set_mismatch")
    if (
        direct_root_map.get("openpyxl", {}).get("authority")
        != "explicit_user_import_closure_authorization"
    ):
        blockers.append("openpyxl_authority_missing")
    if direct_root_map.get("psycopg", {}).get("extras") != ["binary"]:
        blockers.append("psycopg_binary_extra_missing")
    for key in ("missing_count", "extra_count", "sdist_count"):
        if closure.get(key) != 0:
            blockers.append(f"closure_{key}_nonzero")

    lock = payload.get("lock") or {}
    if lock.get("repo_path") != str(LOCK_PATH.relative_to(ROOT)):
        blockers.append("lock_repo_path_invalid")
    if lock.get("sha256") != hashlib.sha256(lock_text.encode()).hexdigest():
        blockers.append("lock_sha_mismatch")
    if lock.get("package_count") != len(lock_rows):
        blockers.append("lock_package_count_mismatch")
    if lock.get("only_binary_required") is not True:
        blockers.append("lock_only_binary_not_required")
    if lock.get("require_hashes") is not True:
        blockers.append("lock_hashes_not_required")

    wheelhouse = payload.get("wheelhouse") or {}
    wheels = wheelhouse.get("wheels") or []
    wheel_rows: dict[str, dict[str, object]] = {}
    for item in wheels:
        if not isinstance(item, dict):
            blockers.append("wheel_record_invalid")
            continue
        name = canonical_name(str(item.get("name") or ""))
        if not name or name in wheel_rows:
            blockers.append(f"wheel_name_duplicate_or_invalid:{name}")
            continue
        wheel_rows[name] = item
        filename = str(item.get("filename") or "")
        if not filename.endswith(".whl"):
            blockers.append(f"non_wheel_artifact:{name}")
        if item.get("mode") != "0444":
            blockers.append(f"wheel_mode_invalid:{name}")
        for key in ("sha256", "metadata_sha256"):
            if not SHA256_RE.fullmatch(str(item.get(key) or "")):
                blockers.append(f"wheel_{key}_invalid:{name}")
        if not isinstance(item.get("size_bytes"), int) or item["size_bytes"] <= 0:
            blockers.append(f"wheel_size_invalid:{name}")
        if not item.get("wheel_tags"):
            blockers.append(f"wheel_tags_missing:{name}")

    if set(wheel_rows) != set(lock_rows):
        blockers.append("wheel_package_set_mismatch")
    for name in sorted(set(wheel_rows) & set(lock_rows)):
        wheel = wheel_rows[name]
        locked = lock_rows[name]
        if wheel.get("version") != locked["version"]:
            blockers.append(f"wheel_version_mismatch:{name}")
        if wheel.get("sha256") != locked["sha256"]:
            blockers.append(f"wheel_sha_mismatch:{name}")
    requested_roots = {
        name for name, item in wheel_rows.items() if item.get("requested_root")
    }
    if requested_roots != expected_roots:
        blockers.append("requested_root_set_mismatch")

    wheelhouse_id = str(wheelhouse.get("id") or "")
    wheelhouse_path = Path(str(wheelhouse.get("path") or ""))
    if wheelhouse_path.parent != FIXED_WHEELHOUSE_ROOT:
        blockers.append("wheelhouse_outside_fixed_root")
    if wheelhouse_path.name != wheelhouse_id:
        blockers.append("wheelhouse_id_path_mismatch")
    if not wheelhouse_id.endswith(str(lock.get("sha256") or "")):
        blockers.append("wheelhouse_id_not_bound_to_lock")
    if wheelhouse.get("root_mode") != "0555":
        blockers.append("wheelhouse_root_mode_invalid")
    if wheelhouse.get("file_mode") != "0444":
        blockers.append("wheelhouse_file_mode_invalid")
    for key in (
        "missing_count",
        "extra_count",
        "sdist_count",
        "symlink_count",
        "hardlink_reuse_count",
    ):
        if wheelhouse.get(key) != 0:
            blockers.append(f"wheelhouse_{key}_nonzero")
    for key in ("wheel_count", "package_count"):
        if wheelhouse.get(key) != len(lock_rows):
            blockers.append(f"wheelhouse_{key}_mismatch")
    if not SHA256_RE.fullmatch(str(wheelhouse.get("fileset_sha256") or "")):
        blockers.append("wheelhouse_fileset_sha_invalid")

    offline = payload.get("offline_validation") or {}
    for key in ("status", "pip_check", "strategy_worker_import", "auto_runner_import"):
        if offline.get(key) != "PASS":
            blockers.append(f"offline_{key}_not_pass")
    if offline.get("database_connect_attempt_count") != 0:
        blockers.append("offline_database_connect_attempted")
    if offline.get("bytecode_count") != 0:
        blockers.append("offline_bytecode_created")
    if offline.get("installed_package_count") != len(lock_rows):
        blockers.append("offline_package_count_mismatch")
    evidence_path = Path(str(offline.get("evidence_path") or ""))
    if evidence_path.parent != FIXED_EVIDENCE_ROOT:
        blockers.append("offline_evidence_outside_fixed_root")
    if not SHA256_RE.fullmatch(str(offline.get("evidence_sha256") or "")):
        blockers.append("offline_evidence_sha_invalid")

    boundaries = payload.get("runtime_boundaries") or {}
    expected_boundary_keys = {
        "application_release_built",
        "database_connected",
        "database_written",
        "launchd_modified",
        "runtime_env_built",
        "schema_modified",
        "web_modified",
        "writer_modified",
    }
    if set(boundaries) != expected_boundary_keys:
        blockers.append("runtime_boundary_keys_mismatch")
    if any(value is not False for value in boundaries.values()):
        blockers.append("runtime_boundary_side_effect_true")

    if blockers:
        raise ValueError(";".join(sorted(set(blockers))))


class N6StrategyEvaluatorDependencyLockTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.lock_text = LOCK_PATH.read_text(encoding="utf-8")
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_exact_hash_locked_wheel_closure(self) -> None:
        validate_contract(self.manifest, self.lock_text)
        self.assertEqual(len(parse_lock(self.lock_text)), 16)

    def test_import_authority_matches_locked_application_source(self) -> None:
        worker = (
            ROOT / "src/ashare_v3/user/strategy_center_worker.py"
        ).read_text(encoding="utf-8")
        web = (ROOT / "src/ashare_v3/web/n6_user_app.py").read_text(
            encoding="utf-8"
        )
        auto = (ROOT / "scripts/run_n6_strategy_center_auto_once.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("import psycopg", worker)
        self.assertIn(
            "from ashare_v3.web.n6_user_app import PostgresN6UserRepository",
            worker,
        )
        self.assertIn("from fastapi import FastAPI", web)
        self.assertIn("from openpyxl import Workbook", web)
        self.assertIn("Jinja2Templates(directory=str(TEMPLATE_DIR))", web)
        self.assertIn(
            "from ashare_v3.user.strategy_center_worker import (", auto
        )

    def test_polluted_sources_sdists_and_extra_wheels_fail_closed(self) -> None:
        mutations: list[tuple[str, dict[str, object], str]] = []

        non_official = copy.deepcopy(self.manifest)
        non_official["resolver"]["index_url"] = "https://example.invalid/simple"
        refresh_integrity(non_official)
        mutations.append(
            ("non_official", non_official, "resolver_index_not_official")
        )

        sdist = copy.deepcopy(self.manifest)
        sdist["wheelhouse"]["wheels"][0]["filename"] = "polluted.tar.gz"
        refresh_integrity(sdist)
        mutations.append(("sdist", sdist, "non_wheel_artifact"))

        extra = copy.deepcopy(self.manifest)
        rogue = copy.deepcopy(extra["wheelhouse"]["wheels"][0])
        rogue.update(
            {
                "name": "rogue-package",
                "filename": "rogue_package-1.0-py3-none-any.whl",
                "version": "1.0",
                "requested_root": False,
            }
        )
        extra["wheelhouse"]["wheels"].append(rogue)
        refresh_integrity(extra)
        mutations.append(("extra", extra, "wheel_package_set_mismatch"))

        for label, payload, expected in mutations:
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError, expected):
                    validate_contract(payload, self.lock_text)

    def test_missing_openpyxl_hash_or_manifest_authority_fails_closed(self) -> None:
        missing_root = copy.deepcopy(self.manifest)
        missing_root["closure"]["direct_roots"] = [
            item
            for item in missing_root["closure"]["direct_roots"]
            if item["name"] != "openpyxl"
        ]
        refresh_integrity(missing_root)
        with self.assertRaisesRegex(ValueError, "direct_root_set_mismatch"):
            validate_contract(missing_root, self.lock_text)

        missing_hash = re.sub(
            r"openpyxl==3\.1\.5 \\\n"
            r"    --hash=sha256:[0-9a-f]{64}",
            "openpyxl==3.1.5",
            self.lock_text,
        )
        with self.assertRaisesRegex(ValueError, "lock_pin_without_hash"):
            parse_lock(missing_hash)

        missing_integrity = copy.deepcopy(self.manifest)
        missing_integrity.pop("integrity")
        with self.assertRaisesRegex(ValueError, "manifest_integrity_missing"):
            validate_contract(missing_integrity, self.lock_text)

    def test_local_wheelhouse_matches_manifest_when_present(self) -> None:
        wheelhouse = Path(self.manifest["wheelhouse"]["path"])
        if not wheelhouse.exists():
            self.skipTest("versioned wheelhouse is host-local evidence")

        self.assertFalse(wheelhouse.is_symlink())
        self.assertEqual(stat.S_IMODE(wheelhouse.stat().st_mode), 0o555)
        expected = {
            item["filename"]: item
            for item in self.manifest["wheelhouse"]["wheels"]
        }
        actual_entries = sorted(wheelhouse.iterdir(), key=lambda item: item.name)
        self.assertEqual({item.name for item in actual_entries}, set(expected))

        fileset = []
        for wheel in actual_entries:
            self.assertFalse(wheel.is_symlink())
            info = wheel.stat()
            self.assertTrue(wheel.is_file())
            self.assertEqual(stat.S_IMODE(info.st_mode), 0o444)
            self.assertEqual(info.st_nlink, 1)
            digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
            record = expected[wheel.name]
            self.assertEqual(digest, record["sha256"])
            self.assertEqual(info.st_size, record["size_bytes"])
            fileset.append(
                {
                    "filename": wheel.name,
                    "mode": "0444",
                    "sha256": digest,
                    "size_bytes": info.st_size,
                }
            )
        fileset_sha = hashlib.sha256(
            json.dumps(
                fileset, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
        self.assertEqual(
            fileset_sha, self.manifest["wheelhouse"]["fileset_sha256"]
        )


if __name__ == "__main__":
    unittest.main()
