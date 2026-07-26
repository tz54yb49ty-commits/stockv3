#!/usr/bin/env python3
"""Build the reviewed N6 AI knowledge mirror for the private research room."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from typing import Any
from uuid import uuid4


DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VAULT_ROOT = Path(
    "/Users/chuanfuchen/Documents/Obsidian Vault/A股监控系统v3"
)
MANIFEST_RELATIVE_PATH = Path(
    "docs/N6_AI_KNOWLEDGE_BUNDLE_MANIFEST.json"
)
FIELD_DICTIONARY_DOCUMENT_ID = "ai-approved-field-dictionary"
MAX_MANIFEST_BYTES = 2_000_000
MAX_DOCUMENT_BYTES = 2_000_000
MAX_DOCUMENTS = 100
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DOCUMENT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,199}$")
GENERATED_PREFIXES = frozenset(
    {
        ("40-AI投资员", "10-字段字典"),
        ("40-AI投资员", "20-知识包"),
        ("40-AI投资员", "30-决策与日报"),
    }
)
NOTES_PREFIX = ("80-我的笔记",)


class MirrorError(ValueError):
    """A stable fail-closed mirror error."""


@dataclass(frozen=True, slots=True)
class MirrorFile:
    source: Path | None
    destination: Path
    sha256_hex: str
    content: bytes | None = None


@dataclass(frozen=True, slots=True)
class MirrorPlan:
    project_root: Path
    vault_root: Path
    manifest_sha256: str
    bundle_sha256: str
    bundle_version: str
    files: tuple[MirrorFile, ...]
    generated_directories: tuple[Path, ...]
    notes_directories: tuple[Path, ...]

    def summary(self) -> dict[str, Any]:
        return {
            "ok": True,
            "mode": "obsidian_one_way_mirror",
            "project_root": str(self.project_root),
            "vault_root": str(self.vault_root),
            "manifest_sha256": self.manifest_sha256,
            "bundle_sha256": self.bundle_sha256,
            "bundle_version": self.bundle_version,
            "file_count": len(self.files),
            "files": [
                {
                    "destination": str(item.destination),
                    "sha256": item.sha256_hex,
                }
                for item in self.files
            ],
            "notes_directories": [
                str(path) for path in self.notes_directories
            ],
            "notes_write_enabled": False,
        }


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def build_plan(
    *,
    project_root: Path,
    vault_root: Path,
    expected_manifest_sha256: str,
) -> MirrorPlan:
    if not SHA256_RE.fullmatch(expected_manifest_sha256):
        raise MirrorError("expected_manifest_hash_invalid")
    project = _existing_safe_directory(project_root, "project")
    vault = _existing_safe_directory(vault_root, "vault")
    manifest_path = project / MANIFEST_RELATIVE_PATH
    manifest_bytes = _read_safe_source(
        project,
        MANIFEST_RELATIVE_PATH,
        max_bytes=MAX_MANIFEST_BYTES,
    )
    if sha256(manifest_bytes).hexdigest() != expected_manifest_sha256:
        raise MirrorError("manifest_external_hash_mismatch")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise MirrorError("manifest_invalid") from exc
    if not isinstance(manifest, dict):
        raise MirrorError("manifest_invalid")
    bundle_sha256 = str(manifest.get("bundle_sha256") or "")
    bundle_version = str(manifest.get("bundle_version") or "")
    documents = manifest.get("documents")
    if (
        not SHA256_RE.fullmatch(bundle_sha256)
        or not bundle_version
        or not isinstance(documents, list)
        or not 1 <= len(documents) <= MAX_DOCUMENTS
    ):
        raise MirrorError("manifest_invalid")
    hash_payload = {
        key: value
        for key, value in manifest.items()
        if key != "bundle_sha256"
    }
    if _canonical_sha256(hash_payload) != bundle_sha256:
        raise MirrorError("manifest_bundle_hash_mismatch")

    field_dir = vault / "40-AI投资员" / "10-字段字典"
    knowledge_dir = vault / "40-AI投资员" / "20-知识包"
    decisions_dir = vault / "40-AI投资员" / "30-决策与日报"
    notes_candidate_dir = (
        vault / "80-我的笔记" / "AI投资员" / "10-候选经验"
    )
    notes_review_dir = (
        vault / "80-我的笔记" / "AI投资员" / "20-人工审核"
    )
    files: list[MirrorFile] = []
    destination_names: set[Path] = set()
    document_ids: set[str] = set()
    for document in documents:
        if not isinstance(document, dict):
            raise MirrorError("manifest_document_invalid")
        document_id = str(document.get("document_id") or "")
        root_id = str(document.get("root") or "")
        relative_text = str(document.get("path") or "")
        expected_sha256 = str(document.get("sha256") or "")
        pure = PurePosixPath(relative_text)
        if (
            not DOCUMENT_ID_RE.fullmatch(document_id)
            or document_id in document_ids
            or root_id != "git"
            or pure.is_absolute()
            or not pure.parts
            or pure.parts[0] != "docs"
            or any(
                part in {"", ".", ".."} or part.startswith(".")
                for part in pure.parts
            )
            or not SHA256_RE.fullmatch(expected_sha256)
        ):
            raise MirrorError("manifest_document_invalid")
        document_ids.add(document_id)
        relative_path = Path(*pure.parts)
        payload = _read_safe_source(
            project,
            relative_path,
            max_bytes=MAX_DOCUMENT_BYTES,
        )
        if sha256(payload).hexdigest() != expected_sha256:
            raise MirrorError("manifest_document_hash_mismatch")
        destination_dir = (
            field_dir
            if document_id == FIELD_DICTIONARY_DOCUMENT_ID
            else knowledge_dir
        )
        destination = destination_dir / pure.name
        if destination in destination_names:
            raise MirrorError("mirror_destination_collision")
        destination_names.add(destination)
        files.append(
            MirrorFile(
                source=project / relative_path,
                destination=destination,
                sha256_hex=expected_sha256,
            )
        )

    manifest_destination = knowledge_dir / manifest_path.name
    if manifest_destination in destination_names:
        raise MirrorError("mirror_destination_collision")
    files.append(
        MirrorFile(
            source=manifest_path,
            destination=manifest_destination,
            sha256_hex=expected_manifest_sha256,
        )
    )
    empty_state = (
        "# AI投资员决策与日报\n\n"
        "当前仅建立只读镜像目录。AI V1 尚未发布，"
        "不得在此目录伪造账户、决策、成交或日报事实。\n"
    ).encode("utf-8")
    files.append(
        MirrorFile(
            source=None,
            destination=decisions_dir / "README.md",
            sha256_hex=sha256(empty_state).hexdigest(),
            content=empty_state,
        )
    )
    return MirrorPlan(
        project_root=project,
        vault_root=vault,
        manifest_sha256=expected_manifest_sha256,
        bundle_sha256=bundle_sha256,
        bundle_version=bundle_version,
        files=tuple(files),
        generated_directories=(
            field_dir,
            knowledge_dir,
            decisions_dir,
        ),
        notes_directories=(
            notes_candidate_dir,
            notes_review_dir,
        ),
    )


def apply_plan(plan: MirrorPlan) -> dict[str, Any]:
    _validate_plan_scope(plan)
    current_vault = _existing_safe_directory(
        plan.vault_root, "vault"
    )
    if current_vault != plan.vault_root:
        raise MirrorError("vault_root_drift")
    frozen_payloads: list[tuple[MirrorFile, bytes]] = []
    for item in plan.files:
        payload = (
            item.content
            if item.content is not None
            else _read_safe_source(
                plan.project_root,
                item.source.relative_to(plan.project_root),
                max_bytes=MAX_DOCUMENT_BYTES,
            )
            if item.source is not None
            else None
        )
        if payload is None or sha256(payload).hexdigest() != item.sha256_hex:
            raise MirrorError("mirror_source_drift")
        frozen_payloads.append((item, payload))

    for directory in (
        *plan.generated_directories,
        *plan.notes_directories,
    ):
        _mkdir_owner_only(directory, vault_root=plan.vault_root)
    for item, payload in frozen_payloads:
        _atomic_write_generated(
            item.destination,
            payload,
            vault_root=plan.vault_root,
        )
    result = plan.summary()
    result["applied"] = True
    return result


def _validate_plan_scope(plan: MirrorPlan) -> None:
    expected_generated = {
        plan.vault_root.joinpath(*prefix)
        for prefix in GENERATED_PREFIXES
    }
    expected_notes = {
        plan.vault_root
        / "80-我的笔记"
        / "AI投资员"
        / "10-候选经验",
        plan.vault_root
        / "80-我的笔记"
        / "AI投资员"
        / "20-人工审核",
    }
    if (
        set(plan.generated_directories) != expected_generated
        or set(plan.notes_directories) != expected_notes
    ):
        raise MirrorError("mirror_plan_directory_scope_invalid")
    for item in plan.files:
        try:
            destination_parts = item.destination.relative_to(
                plan.vault_root
            ).parts
        except ValueError as exc:
            raise MirrorError(
                "mirror_destination_outside_vault"
            ) from exc
        if (
            destination_parts[:1] == NOTES_PREFIX
            or destination_parts[:2] not in GENERATED_PREFIXES
            or len(destination_parts) != 3
            or destination_parts[2] in {"", ".", ".."}
            or destination_parts[2].startswith(".")
            or not SHA256_RE.fullmatch(item.sha256_hex)
        ):
            raise MirrorError("mirror_destination_scope_invalid")
        if item.source is None:
            if (
                item.destination
                != plan.vault_root
                / "40-AI投资员"
                / "30-决策与日报"
                / "README.md"
                or item.content is None
            ):
                raise MirrorError("mirror_generated_content_invalid")
            continue
        if item.content is not None:
            raise MirrorError("mirror_source_contract_invalid")
        try:
            source_parts = item.source.relative_to(
                plan.project_root
            ).parts
        except ValueError as exc:
            raise MirrorError(
                "mirror_source_outside_project"
            ) from exc
        if (
            not source_parts
            or source_parts[0] != "docs"
            or item.source.name != item.destination.name
        ):
            raise MirrorError("mirror_source_scope_invalid")


def _existing_safe_directory(path: Path, label: str) -> Path:
    lexical = Path(path).absolute()
    if lexical.is_symlink():
        raise MirrorError(f"{label}_root_symlink_not_allowed")
    try:
        resolved = lexical.resolve(strict=True)
    except OSError as exc:
        raise MirrorError(f"{label}_root_unavailable") from exc
    metadata = resolved.stat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        raise MirrorError(f"{label}_root_unsafe")
    return resolved


def _read_safe_source(
    root: Path,
    relative_path: Path,
    *,
    max_bytes: int,
) -> bytes:
    if (
        not relative_path.parts
        or relative_path.is_absolute()
        or any(
            part in {"", ".", ".."}
            for part in relative_path.parts
        )
    ):
        raise MirrorError("source_outside_project")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    directory_flags = flags | getattr(os, "O_DIRECTORY", 0)
    current_fd: int | None = None
    try:
        current_fd = os.open(root, directory_flags)
        for part in relative_path.parts[:-1]:
            next_fd = os.open(
                part, directory_flags, dir_fd=current_fd
            )
            os.close(current_fd)
            current_fd = next_fd
        file_fd = os.open(
            relative_path.parts[-1],
            flags | getattr(os, "O_NONBLOCK", 0),
            dir_fd=current_fd,
        )
        try:
            metadata = os.fstat(file_fd)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_size > max_bytes
            ):
                raise MirrorError("source_file_invalid")
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = os.read(
                    file_fd,
                    min(65_536, max_bytes + 1 - total),
                )
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > max_bytes:
                    raise MirrorError("source_file_invalid")
            return b"".join(chunks)
        finally:
            os.close(file_fd)
    except MirrorError:
        raise
    except OSError as exc:
        raise MirrorError("source_unavailable") from exc
    finally:
        if current_fd is not None:
            os.close(current_fd)


def _mkdir_owner_only(path: Path, *, vault_root: Path) -> None:
    relative = path.relative_to(vault_root)
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    current_fd: int | None = None
    try:
        current_fd = os.open(vault_root, flags)
        for part in relative.parts:
            try:
                os.mkdir(part, mode=0o700, dir_fd=current_fd)
            except FileExistsError:
                pass
            next_fd = os.open(part, flags, dir_fd=current_fd)
            metadata = os.fstat(next_fd)
            if (
                not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) & 0o022
            ):
                os.close(next_fd)
                raise MirrorError("mirror_directory_unsafe")
            os.close(current_fd)
            current_fd = next_fd
    except MirrorError:
        raise
    except OSError as exc:
        raise MirrorError(
            "mirror_directory_symlink_not_allowed"
        ) from exc
    finally:
        if current_fd is not None:
            os.close(current_fd)


def _atomic_write_generated(
    destination: Path,
    payload: bytes,
    *,
    vault_root: Path,
) -> None:
    parent_fd = _open_safe_destination_parent(
        vault_root, destination.parent
    )
    temporary_name = f".{destination.name}.pending-{uuid4().hex}"
    descriptor: int | None = None
    try:
        try:
            metadata = os.stat(
                destination.name,
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            metadata = None
        if metadata is not None and not stat.S_ISREG(metadata.st_mode):
            raise MirrorError(
                "mirror_destination_symlink_not_allowed"
            )
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
            dir_fd=parent_fd,
        )
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise MirrorError("mirror_write_failed")
            offset += written
        os.fchmod(descriptor, 0o444)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.replace(
            temporary_name,
            destination.name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        os.fsync(parent_fd)
    except MirrorError:
        raise
    except OSError as exc:
        raise MirrorError("mirror_write_failed") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            os.unlink(temporary_name, dir_fd=parent_fd)
        except FileNotFoundError:
            pass
        os.close(parent_fd)


def _open_safe_destination_parent(
    vault_root: Path, parent: Path
) -> int:
    try:
        parts = parent.relative_to(vault_root).parts
    except ValueError as exc:
        raise MirrorError("mirror_destination_outside_vault") from exc
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    current_fd: int | None = None
    try:
        current_fd = os.open(vault_root, flags)
        for part in parts:
            next_fd = os.open(part, flags, dir_fd=current_fd)
            os.close(current_fd)
            current_fd = next_fd
        metadata = os.fstat(current_fd)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) & 0o022
        ):
            raise MirrorError("mirror_directory_unsafe")
        return current_fd
    except OSError as exc:
        if current_fd is not None:
            os.close(current_fd)
        raise MirrorError("mirror_directory_unavailable") from exc
    except Exception:
        if current_fd is not None:
            os.close(current_fd)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--project-root",
        type=Path,
        default=DEFAULT_PROJECT_ROOT,
    )
    parser.add_argument(
        "--vault-root",
        type=Path,
        default=DEFAULT_VAULT_ROOT,
    )
    parser.add_argument(
        "--expected-manifest-sha256",
        required=True,
    )
    parser.add_argument("--apply", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        plan = build_plan(
            project_root=args.project_root,
            vault_root=args.vault_root,
            expected_manifest_sha256=args.expected_manifest_sha256,
        )
        result = apply_plan(plan) if args.apply else plan.summary()
        result["applied"] = bool(args.apply)
    except (OSError, MirrorError):
        return 2
    json.dump(result, sys.stdout, ensure_ascii=False, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
