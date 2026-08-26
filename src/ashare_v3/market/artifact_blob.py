"""Content-addressed N3 JSON artifact blobs.

This module is intentionally filesystem-only.  It neither opens a database nor
knows about N4/N5 consumers.  Producers may replace bulky inline payload
members with an ``artifact_blob_v1`` reference; readers must hydrate and verify
the complete reference closure before replaying the payload.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping, Sequence


ARTIFACT_BLOB_SCHEMA = "artifact_blob_v1"
ARTIFACT_BLOB_COMPRESSION = "gzip"
N3P_OVERLAY_BLOB_FIELDS = (
    "candidates",
    "n4_context_snapshot_rows",
    "previous_day_cumulative_rows",
)
INTRADAY_BLOB_REF_FIELDS = (
    "artifact_blob_refs",
    "retained_artifact_blob_refs",
    "archive_artifact_blob_refs",
    "active_artifact_blob_refs",
)


class ArtifactBlobBlocked(RuntimeError):
    """Raised when an artifact blob is missing, malformed, or inconsistent."""


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    except (TypeError, ValueError) as exc:  # pragma: no cover - json protects this in normal callers
        raise ArtifactBlobBlocked(f"artifact_blob_json_invalid:{type(exc).__name__}") from exc


def deterministic_gzip_bytes(value: Any) -> bytes:
    return gzip.compress(canonical_json_bytes(value), compresslevel=9, mtime=0)


def build_artifact_blob_ref(*, value: Any, relative_path: str) -> dict[str, Any]:
    raw = canonical_json_bytes(value)
    compressed = gzip.compress(raw, compresslevel=9, mtime=0)
    return {
        "schema": ARTIFACT_BLOB_SCHEMA,
        "encoding": "json",
        "compression": ARTIFACT_BLOB_COMPRESSION,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "compressed_sha256": hashlib.sha256(compressed).hexdigest(),
        "bytes": len(raw),
        "compressed_bytes": len(compressed),
        "row_count": len(value) if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else 1,
        "path": relative_path,
    }


def write_artifact_blob(*, value: Any, blob_root: str | Path, relative_prefix: str = "artifact_blobs") -> dict[str, Any]:
    raw = canonical_json_bytes(value)
    digest = hashlib.sha256(raw).hexdigest()
    relative_path = f"{relative_prefix}/{digest}.json.gz"
    root = Path(blob_root)
    target = root / f"{digest}.json.gz"
    compressed = gzip.compress(raw, compresslevel=9, mtime=0)
    root.mkdir(parents=True, exist_ok=True)
    temp_path = ""
    try:
        descriptor, temp_path = tempfile.mkstemp(prefix=f".{digest}.", suffix=".tmp", dir=root)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(compressed)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temp_path, target)
        except FileExistsError:
            if target.is_symlink() or not target.is_file() or target.read_bytes() != compressed:
                raise ArtifactBlobBlocked("artifact_blob_existing_content_mismatch")
    except OSError as exc:
        raise ArtifactBlobBlocked(f"artifact_blob_write_failed:{type(exc).__name__}") from exc
    finally:
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)
    return build_artifact_blob_ref(value=value, relative_path=relative_path)


def read_artifact_blob(reference: Mapping[str, Any], *, base_path: str | Path) -> Any:
    if str(reference.get("schema") or "") != ARTIFACT_BLOB_SCHEMA:
        raise ArtifactBlobBlocked("artifact_blob_schema_invalid")
    if str(reference.get("encoding") or "") != "json" or str(reference.get("compression") or "") != ARTIFACT_BLOB_COMPRESSION:
        raise ArtifactBlobBlocked("artifact_blob_encoding_invalid")
    raw_path = str(reference.get("path") or "")
    if not raw_path or Path(raw_path).is_absolute():
        raise ArtifactBlobBlocked("artifact_blob_path_invalid")
    base = Path(base_path).resolve()
    target = (base / raw_path).resolve()
    if not target.is_relative_to(base) or target.is_symlink() or not target.is_file():
        raise ArtifactBlobBlocked("artifact_blob_path_unavailable")
    compressed = target.read_bytes()
    if hashlib.sha256(compressed).hexdigest() != str(reference.get("compressed_sha256") or ""):
        raise ArtifactBlobBlocked("artifact_blob_compressed_hash_mismatch")
    try:
        raw = gzip.decompress(compressed)
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArtifactBlobBlocked(f"artifact_blob_decode_invalid:{type(exc).__name__}") from exc
    if canonical_json_bytes(value) != raw:
        raise ArtifactBlobBlocked("artifact_blob_not_canonical")
    if hashlib.sha256(raw).hexdigest() != str(reference.get("sha256") or ""):
        raise ArtifactBlobBlocked("artifact_blob_hash_mismatch")
    if len(raw) != int(reference.get("bytes") or -1):
        raise ArtifactBlobBlocked("artifact_blob_bytes_mismatch")
    row_count = len(value) if isinstance(value, list) else 1
    if row_count != int(reference.get("row_count") or -1):
        raise ArtifactBlobBlocked("artifact_blob_row_count_mismatch")
    return value


def externalize_payload_fields(
    payload: Mapping[str, Any], *, fields: Sequence[str], blob_root: str | Path
) -> dict[str, Any]:
    output = dict(payload)
    refs = dict(output.get("artifact_blob_refs") or {})
    for field in fields:
        if field in output:
            refs[field] = write_artifact_blob(value=output.pop(field), blob_root=blob_root)
    if refs:
        output["artifact_blob_refs"] = refs
    return output


def write_n3p_overlay_blob(*, overlay: Mapping[str, Any], blob_root: str | Path) -> dict[str, Any]:
    """Store the three N3P contract-overlay row sets as one v2 reference."""

    unexpected = set(overlay) - set(N3P_OVERLAY_BLOB_FIELDS)
    missing = set(N3P_OVERLAY_BLOB_FIELDS) - set(overlay)
    if unexpected or missing:
        raise ArtifactBlobBlocked("n3p_overlay_blob_fields_invalid")
    return write_artifact_blob(value=dict(overlay), blob_root=blob_root)


def write_n3p_source_payload_refs(*, overlay: Mapping[str, Any], blob_root: str | Path) -> dict[str, dict[str, Any]]:
    """Externalize exactly the repeated N3P source row sets as individual blobs."""

    missing = set(N3P_OVERLAY_BLOB_FIELDS) - set(overlay)
    if missing:
        raise ArtifactBlobBlocked("n3p_source_payload_refs_fields_missing")
    return {
        field: write_artifact_blob(value=overlay[field], blob_root=blob_root)
        for field in N3P_OVERLAY_BLOB_FIELDS
    }


def hydrate_payload_blob_refs(payload: Mapping[str, Any], *, base_path: str | Path) -> dict[str, Any]:
    output = dict(payload)
    for ref_field in INTRADAY_BLOB_REF_FIELDS:
        refs = output.get(ref_field)
        if refs is None:
            continue
        if not isinstance(refs, Mapping):
            raise ArtifactBlobBlocked(f"artifact_blob_refs_invalid:{ref_field}")
        for field, reference in refs.items():
            if not isinstance(reference, Mapping):
                raise ArtifactBlobBlocked(f"artifact_blob_ref_invalid:{ref_field}:{field}")
            value = read_artifact_blob(reference, base_path=base_path)
            if field in output and output[field] != value:
                raise ArtifactBlobBlocked(f"artifact_blob_inline_conflict:{field}")
            output[field] = value
    return output


def validate_artifact_blob_reference_closure(payload: Mapping[str, Any], *, base_path: str | Path) -> dict[str, Any]:
    hydrated = hydrate_payload_blob_refs(payload, base_path=base_path)
    refs = sum(len(dict(payload.get(name) or {})) for name in INTRADAY_BLOB_REF_FIELDS)
    return {"status": "passed", "reference_count": refs, "hydrated_payload": hydrated}
