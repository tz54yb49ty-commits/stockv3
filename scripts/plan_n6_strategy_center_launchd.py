#!/usr/bin/env python3
"""Build a plan-only immutable LaunchAgent plist for N6 strategy evaluation."""

from __future__ import annotations

if __name__ == "__main__":
    raise SystemExit("strategy_center_retired")

import argparse
import hashlib
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import plistlib
import re
import stat
from typing import Any


LABEL = "com.ashare-v3.n6.strategy-center-evaluator-v1"
WORKER_SERVICE = "n6_strategy_worker"
START_INTERVAL_SECONDS = 5
# The evaluator still starts every 5 seconds; this is the per-run bounded
# ceiling, not the scheduler interval.  A pass may hold the singleton lock
# across ticks, which are intentionally observed as lock-held no-ops.
MAX_RUNTIME_SECONDS = 12
SIGNAL_SOURCE_USER_ID = 1
DEFAULT_STATE_ROOT = Path("/Users/chuanfuchen/.local/state/ashare-v3/n6-b-track")
RELEASE_ROOT = Path(
    "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track"
)
RUNTIME_ENV_ROOT = Path(
    "/Users/chuanfuchen/.local/share/ashare-v3/runtime-envs/n6-b-track"
)
MANIFEST_ROOT = DEFAULT_STATE_ROOT / "manifests"
DEFAULT_SERVICE_FILE = Path(
    "/Users/chuanfuchen/.config/ashare-v3/postgresql/pg_service.conf"
)
DEFAULT_PASS_FILE = Path(
    "/Users/chuanfuchen/.config/ashare-v3/postgresql/n6_strategy_worker.pgpass"
)
RELEASE_ID_PATTERN = re.compile(r"^[0-9]{8}_[0-9]{6}__[0-9a-f]{40}$")


def _absolute(value: Path, name: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(f"{name} must be absolute")
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _parse_git_manifest(path: Path) -> dict[str, tuple[str, str]]:
    raw = path.read_bytes()
    if not raw or not raw.endswith(b"\0"):
        raise ValueError("release manifest must be nonempty NUL-delimited data")
    result: dict[str, tuple[str, str]] = {}
    for record in raw[:-1].split(b"\0"):
        try:
            authority, raw_path = record.split(b"\t", 1)
            mode, object_type, object_id = authority.decode("ascii").split(" ")
            file_rel = raw_path.decode("utf-8")
        except (UnicodeDecodeError, ValueError) as exc:
            raise ValueError("release manifest record invalid") from exc
        if mode not in {"100644", "100755"} or object_type != "blob":
            raise ValueError("release manifest contains unsupported Git object")
        if not re.fullmatch(r"[0-9a-f]{40}", object_id):
            raise ValueError("release manifest blob SHA-1 invalid")
        normalized = PurePosixPath(file_rel)
        if (
            not file_rel
            or normalized.is_absolute()
            or ".." in normalized.parts
            or str(normalized) != file_rel
        ):
            raise ValueError("release manifest path invalid")
        if file_rel in result:
            raise ValueError("release manifest duplicate path")
        result[file_rel] = (mode, object_id)
    return result


def _git_blob_sha1(path: Path, expected_stat: os.stat_result) -> str:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened_stat = os.fstat(descriptor)
        if (
            opened_stat.st_dev != expected_stat.st_dev
            or opened_stat.st_ino != expected_stat.st_ino
            or opened_stat.st_size != expected_stat.st_size
            or opened_stat.st_mtime_ns != expected_stat.st_mtime_ns
        ):
            raise ValueError("release file changed before blob validation")
        digest = hashlib.sha1()
        digest.update(f"blob {opened_stat.st_size}\0".encode("ascii"))
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            digest.update(block)
        final_stat = os.fstat(descriptor)
        if (
            final_stat.st_size != opened_stat.st_size
            or final_stat.st_mtime_ns != opened_stat.st_mtime_ns
        ):
            raise ValueError("release file changed during blob validation")
        return digest.hexdigest()
    finally:
        os.close(descriptor)


def _validate_release_entity(
    release: Path,
    expected_files: dict[str, tuple[str, str]],
) -> dict[str, Any]:
    release_stat = release.lstat()
    if (
        not stat.S_ISDIR(release_stat.st_mode)
        or release_stat.st_uid != os.getuid()
        or stat.S_IMODE(release_stat.st_mode) != 0o555
        or release.resolve(strict=True) != release
    ):
        raise ValueError("release root authority/read-only mode invalid")
    actual_files: dict[str, tuple[str, str]] = {}
    directory_count = 0
    for current_root, directory_names, file_names in os.walk(
        release,
        topdown=True,
        followlinks=False,
    ):
        current = Path(current_root)
        current_stat = current.lstat()
        if (
            not stat.S_ISDIR(current_stat.st_mode)
            or current_stat.st_uid != os.getuid()
            or stat.S_IMODE(current_stat.st_mode) != 0o555
        ):
            raise ValueError("release directory authority/read-only mode invalid")
        if current != release:
            directory_count += 1
        for directory_name in directory_names:
            directory = current / directory_name
            if stat.S_ISLNK(directory.lstat().st_mode):
                raise ValueError("release symlink directory forbidden")
        for file_name in file_names:
            file_path = current / file_name
            file_stat = file_path.lstat()
            if not stat.S_ISREG(file_stat.st_mode):
                raise ValueError("release non-regular file forbidden")
            if file_stat.st_uid != os.getuid() or file_stat.st_nlink != 1:
                raise ValueError("release file owner/hardlink authority invalid")
            file_rel = file_path.relative_to(release).as_posix()
            expected = expected_files.get(file_rel)
            if expected is None:
                raise ValueError(f"release extra file: {file_rel}")
            expected_mode, expected_blob = expected
            required_mode = 0o555 if expected_mode == "100755" else 0o444
            if stat.S_IMODE(file_stat.st_mode) != required_mode:
                raise ValueError(f"release file read-only/Git mode drift: {file_rel}")
            actual_blob = _git_blob_sha1(file_path, file_stat)
            if actual_blob != expected_blob:
                raise ValueError(f"release Git blob SHA-1 drift: {file_rel}")
            actual_files[file_rel] = (expected_mode, actual_blob)
    missing = sorted(set(expected_files) - set(actual_files))
    if missing:
        raise ValueError(f"release missing file: {missing[0]}")
    mode_counts = {
        mode: sum(
            1
            for actual_mode, _blob in actual_files.values()
            if actual_mode == mode
        )
        for mode in ("100644", "100755")
    }
    return {
        "directory_count": directory_count,
        "file_count": len(actual_files),
        "git_mode_counts": mode_counts,
    }


def _validate_evidence_file(path: Path) -> None:
    file_stat = path.lstat()
    if not stat.S_ISREG(file_stat.st_mode):
        raise ValueError(f"release evidence must be regular: {path}")
    if file_stat.st_uid != os.getuid():
        raise ValueError(f"release evidence owner mismatch: {path}")
    if file_stat.st_nlink != 1:
        raise ValueError(f"release evidence hardlink forbidden: {path}")
    if stat.S_IMODE(file_stat.st_mode) & 0o022:
        raise ValueError(f"release evidence must not be group/world writable: {path}")


def _validate_authority_directory(directory: Path) -> None:
    directory_stat = directory.lstat()
    if not stat.S_ISDIR(directory_stat.st_mode):
        raise ValueError(f"authority path must be a directory: {directory}")
    if directory_stat.st_uid != os.getuid():
        raise ValueError(f"authority directory owner mismatch: {directory}")
    if stat.S_IMODE(directory_stat.st_mode) & 0o022:
        raise ValueError(f"authority directory is group/world writable: {directory}")
    if directory.resolve(strict=True) != directory:
        raise ValueError(f"authority directory symlink forbidden: {directory}")


def _validate_immutable_release(release: Path) -> dict[str, Any]:
    if release.parent != RELEASE_ROOT:
        raise ValueError("release_path must use fixed n6-b-track release root")
    _validate_authority_directory(RELEASE_ROOT)
    _validate_authority_directory(MANIFEST_ROOT)
    validation_path = MANIFEST_ROOT / f"{release.name}.release-validation.json"
    manifest_path = MANIFEST_ROOT / f"{release.name}.git-ls-tree.nul"
    _validate_evidence_file(validation_path)
    _validate_evidence_file(manifest_path)
    try:
        validation = json.loads(validation_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("release validation JSON invalid") from exc
    if not isinstance(validation, dict):
        raise ValueError("release validation payload invalid")
    commit = release.name.rsplit("__", 1)[-1]
    required = {
        "status": "PASS",
        "atomic_rename_completed": True,
        "read_only": True,
        "release_id": release.name,
        "final_path": str(release),
        "commit": commit,
        "missing_count": 0,
        "extra_count": 0,
        "symlink_count": 0,
    }
    drift = {
        key: {"expected": expected, "actual": validation.get(key)}
        for key, expected in required.items()
        if validation.get(key) != expected
    }
    if drift:
        raise ValueError(f"release validation drift: {drift}")
    tree = str(validation.get("tree") or "")
    if not re.fullmatch(r"[0-9a-f]{40}", tree):
        raise ValueError("release tree hash invalid")
    if int(validation.get("file_count") or 0) < 1:
        raise ValueError("release file_count invalid")
    manifest_sha256 = _sha256(manifest_path)
    if validation.get("manifest_sha256") != manifest_sha256:
        raise ValueError("release manifest SHA256 mismatch")
    expected_files = _parse_git_manifest(manifest_path)
    entity = _validate_release_entity(release, expected_files)
    if entity["file_count"] != int(validation["file_count"]):
        raise ValueError("release validation file_count drift")
    expected_mode_counts = {
        str(key): int(value)
        for key, value in dict(validation.get("git_mode_counts") or {}).items()
    }
    if entity["git_mode_counts"] != expected_mode_counts:
        raise ValueError("release validation Git mode counts drift")
    if "directory_count" in validation and entity["directory_count"] != int(
        validation["directory_count"]
    ):
        raise ValueError("release validation directory_count drift")
    runner = release / "scripts/run_n6_strategy_center_auto_once.py"
    if runner.relative_to(release).as_posix() not in expected_files:
        raise ValueError("strategy auto runner missing from release manifest")
    return {
        "validation_path": str(validation_path),
        "manifest_path": str(manifest_path),
        "manifest_sha256": manifest_sha256,
        "commit": commit,
        "tree": tree,
        "file_count": int(validation["file_count"]),
        "directory_count": entity["directory_count"],
        "git_mode_counts": entity["git_mode_counts"],
        "entity_validation": "file-set+git-blob-sha1+git-mode+read-only",
    }


def build_launchd_plan(
    *,
    release_path: Path,
    runtime_env_path: Path,
    state_root: Path = DEFAULT_STATE_ROOT,
    service_file: Path = DEFAULT_SERVICE_FILE,
    pass_file: Path = DEFAULT_PASS_FILE,
) -> dict[str, Any]:
    release = _absolute(release_path, "release_path")
    runtime_env = _absolute(runtime_env_path, "runtime_env_path")
    state = _absolute(state_root, "state_root")
    pg_service = _absolute(service_file, "service_file")
    pg_pass = _absolute(pass_file, "pass_file")
    if not RELEASE_ID_PATTERN.fullmatch(release.name):
        raise ValueError("release_path must end with <YYYYMMDD_HHMMSS>__<40hex>")
    if state != DEFAULT_STATE_ROOT:
        raise ValueError("state_root must equal fixed n6-b-track state root")
    if pg_service != DEFAULT_SERVICE_FILE:
        raise ValueError("service_file must equal fixed worker service file")
    if pg_pass != DEFAULT_PASS_FILE:
        raise ValueError("pass_file must equal fixed worker pass file")
    if runtime_env.parent != RUNTIME_ENV_ROOT:
        raise ValueError("runtime_env_path must use fixed n6-b-track runtime root")
    immutable_attestation = _validate_immutable_release(release)

    runner = release / "scripts/run_n6_strategy_center_auto_once.py"
    strategy_state = state / "strategy-center"
    python_executable = runtime_env / "bin/python3.11"
    arguments = [
        "/usr/bin/env",
        "-i",
        f"PGPASSFILE={pg_pass}",
        f"PGSERVICE={WORKER_SERVICE}",
        f"PGSERVICEFILE={pg_service}",
        "PYTHONDONTWRITEBYTECODE=1",
        "PYTHONNOUSERSITE=1",
        "PYTHONPATH=" + ":".join(
            (str(release / "src"), str(release / "scripts"), str(release))
        ),
        str(python_executable),
        str(runner),
        "--state-path",
        str(strategy_state / "evaluator-state.json"),
        "--singleton-lock-path",
        str(strategy_state / "evaluator.lock"),
        "--json-report-path",
        str(strategy_state / "latest-report.json"),
        "--history-path",
        str(strategy_state / "history.jsonl"),
        "--release-id",
        release.name,
        "--signal-source-user-id",
        str(SIGNAL_SOURCE_USER_ID),
        "--max-runtime-seconds",
        str(MAX_RUNTIME_SECONDS),
        "--execute",
        "--runtime-authorized",
    ]
    plist = {
        "Label": LABEL,
        "ProgramArguments": arguments,
        "WorkingDirectory": str(strategy_state),
        "RunAtLoad": False,
        "KeepAlive": False,
        "ProcessType": "Background",
        "StartInterval": START_INTERVAL_SECONDS,
        "ThrottleInterval": START_INTERVAL_SECONDS,
        "Umask": 0o077,
        "StandardOutPath": str(strategy_state / "evaluator.out.log"),
        "StandardErrorPath": str(strategy_state / "evaluator.err.log"),
    }
    _assert_safe(
        plist,
        release_path=release,
        runtime_env_path=runtime_env,
        state_root=state,
        service_file=pg_service,
        pass_file=pg_pass,
    )
    return {
        "stage": "N6_STRATEGY_CENTER_EVALUATOR_LAUNCHD_PLAN",
        "result": "PLAN_ONLY_PASS",
        "release_id": release.name,
        "immutable_release_attestation": immutable_attestation,
        "hard_preconditions": {
            "strategy_state_directory": str(strategy_state),
            "strategy_state_directory_owner_uid": os.getuid(),
            "strategy_state_directory_mode": "0700",
            "runtime_python": str(python_executable),
            "runtime_python_must_exist_before_install": True,
            "launchagent_install_authorized": False,
        },
        "launchd_plist_keys": ["strategy_center_evaluator"],
        "strategy_center_evaluator": {"label": LABEL, "plist": plist},
        "runtime_write_scope": [
            "n6_user_strategy_selection_revision.replay_status",
            "n6_user_strategy_selection_revision.selection_status",
            "n6_user_strategy_selection_revision.activated_at",
            "n6_user_strategy_selection_revision.superseded_at",
            "n6_strategy_match_projection",
            "n6_strategy_match_change",
        ],
        "side_effects": {
            "launchd_mutated": False,
            "worker_started": False,
            "runtime_executed": False,
            "writes_database": False,
            "web_switched": False,
            "projection_writer_switched": False,
            "schema_migrated": False,
        },
    }


def _assert_safe(
    plist: dict[str, Any],
    *,
    release_path: Path,
    runtime_env_path: Path,
    state_root: Path,
    service_file: Path,
    pass_file: Path,
) -> None:
    expected = build_expected_arguments(
        release_path=release_path,
        runtime_env_path=runtime_env_path,
        state_root=state_root,
        service_file=service_file,
        pass_file=pass_file,
    )
    arguments = [str(value) for value in plist.get("ProgramArguments", [])]
    if arguments != expected:
        raise ValueError("ProgramArguments drift from reviewed strategy contract")
    if "EnvironmentVariables" in plist:
        raise ValueError(
            "strategy evaluator must use env -i, not inherited environment"
        )
    if plist.get("Label") != LABEL:
        raise ValueError("unexpected LaunchAgent label")
    if plist.get("RunAtLoad") is not False or plist.get("KeepAlive") is not False:
        raise ValueError("strategy evaluator must remain a non-resident one-shot")
    if int(plist.get("StartInterval") or 0) != START_INTERVAL_SECONDS:
        raise ValueError("StartInterval must be 5")
    if int(plist.get("ThrottleInterval") or 0) != START_INTERVAL_SECONDS:
        raise ValueError("ThrottleInterval must be 5")
    if int(plist.get("Umask") or 0) != 0o077:
        raise ValueError("strategy evaluator Umask must be 077")
    if plist.get("ProcessType") != "Background":
        raise ValueError("strategy evaluator ProcessType must be Background")
    joined = " ".join(arguments).lower()
    forbidden = (
        "--trade-date",
        "--evaluator-run-id",
        "--dsn",
        "pgpassword=",
        "database_url",
        "run_n1",
        "run_n2",
        "run_n3",
        "run_n4",
        "run_n5",
        "proposal",
        "executor",
        "launchctl",
        "rollback",
        ";",
        "&&",
        "|",
    )
    found = [token for token in forbidden if token in joined]
    if found:
        raise ValueError(f"unsafe ProgramArguments token(s): {found}")


def build_expected_arguments(
    *,
    release_path: Path,
    runtime_env_path: Path,
    state_root: Path,
    service_file: Path,
    pass_file: Path,
) -> list[str]:
    strategy_state = state_root / "strategy-center"
    return [
        "/usr/bin/env",
        "-i",
        f"PGPASSFILE={pass_file}",
        f"PGSERVICE={WORKER_SERVICE}",
        f"PGSERVICEFILE={service_file}",
        "PYTHONDONTWRITEBYTECODE=1",
        "PYTHONNOUSERSITE=1",
        "PYTHONPATH=" + ":".join(
            (
                str(release_path / "src"),
                str(release_path / "scripts"),
                str(release_path),
            )
        ),
        str(runtime_env_path / "bin/python3.11"),
        str(release_path / "scripts/run_n6_strategy_center_auto_once.py"),
        "--state-path",
        str(strategy_state / "evaluator-state.json"),
        "--singleton-lock-path",
        str(strategy_state / "evaluator.lock"),
        "--json-report-path",
        str(strategy_state / "latest-report.json"),
        "--history-path",
        str(strategy_state / "history.jsonl"),
        "--release-id",
        release_path.name,
        "--signal-source-user-id",
        str(SIGNAL_SOURCE_USER_ID),
        "--max-runtime-seconds",
        str(MAX_RUNTIME_SECONDS),
        "--execute",
        "--runtime-authorized",
    ]


def write_launchd_plan(
    *,
    output_dir: Path,
    release_path: Path,
    runtime_env_path: Path,
    state_root: Path = DEFAULT_STATE_ROOT,
    service_file: Path = DEFAULT_SERVICE_FILE,
    pass_file: Path = DEFAULT_PASS_FILE,
) -> dict[str, Any]:
    report = build_launchd_plan(
        release_path=release_path,
        runtime_env_path=runtime_env_path,
        state_root=state_root,
        service_file=service_file,
        pass_file=pass_file,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    for key in report["launchd_plist_keys"]:
        path = output_dir / f"{report['release_id']}.{report[key]['label']}.plist"
        with path.open("wb") as handle:
            plistlib.dump(report[key]["plist"], handle, sort_keys=True)
        report[key]["plist_path"] = str(path)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="tmp/n6_strategy_launchd_plan")
    parser.add_argument("--release-path", required=True)
    parser.add_argument("--runtime-env-path", required=True)
    parser.add_argument("--state-root", default=str(DEFAULT_STATE_ROOT))
    parser.add_argument("--service-file", default=str(DEFAULT_SERVICE_FILE))
    parser.add_argument("--pass-file", default=str(DEFAULT_PASS_FILE))
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = write_launchd_plan(
        output_dir=Path(args.output_dir),
        release_path=Path(args.release_path),
        runtime_env_path=Path(args.runtime_env_path),
        state_root=Path(args.state_root),
        service_file=Path(args.service_file),
        pass_file=Path(args.pass_file),
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"PLAN_ONLY_PASS label={LABEL} release_id={report['release_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
