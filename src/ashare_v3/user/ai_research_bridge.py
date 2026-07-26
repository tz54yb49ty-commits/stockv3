"""Constrained stdio bridge for the private N6 AI research room.

Knowledge and the public AI snapshot are read-only.  Candidate memories may
only be appended as new files below one fixed owner-controlled directory.
The bridge has no database, network, subprocess, overwrite, delete, or
promotion capability.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import errno
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any, BinaryIO, Mapping
import unicodedata
from uuid import uuid4


MAX_MANIFEST_BYTES = 2_000_000
MAX_DOCUMENT_BYTES = 1_000_000
MAX_DOCUMENTS = 5_000
MAX_QUERY_CHARS = 300
MAX_FETCH_CHARS = 100_000
MAX_SEARCH_LIMIT = 20
MAX_SEARCH_TOTAL_BYTES = 20_000_000
MAX_RPC_LINE_BYTES = 1_000_000
MAX_CANDIDATE_BYTES = 64_000
MAX_CANDIDATE_LIST_LIMIT = 100
MAX_CANDIDATE_TITLE_CHARS = 200
MAX_CANDIDATE_TEXT_CHARS = 4_000
MAX_CANDIDATE_REFERENCE_CHARS = 500
MAX_CANDIDATE_REFERENCES = 50
MAX_CANDIDATE_FILES = 5_000
ALLOWED_SUFFIXES = frozenset({".md", ".json", ".txt"})
DENIED_SUFFIXES = frozenset(
    {".db", ".sqlite", ".sqlite3", ".jsonl", ".pgpass", ".env"}
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_OID_RE = re.compile(r"^[0-9a-f]{40}$")
MIGRATION_RE = re.compile(r"^[0-9]{3}$")
DOCUMENT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,199}$")
MEMORY_ID_RE = re.compile(r"^memory_[0-9a-f]{64}$")
CANDIDATE_FILE_RE = re.compile(r"^memory_[0-9a-f]{64}\.json$")
CANDIDATE_RELATIVE_PARTS = ("AI投资员", "10-候选经验")
CANDIDATE_LOCK_FILE = ".append.lock"
EVIDENCE_DOCUMENT_RE = re.compile(
    r"^bundle:document:([a-z0-9][a-z0-9._:-]{0,199})"
    r"(?:#[A-Za-z0-9_.:-]{1,200})?$"
)
AI_PUBLIC_SNAPSHOT_ROOT_ID = "obsidian"
AI_PUBLIC_SNAPSHOT_RELATIVE_PATH = (
    "40-AI投资员/30-决策与日报/ai_public_snapshot.json"
)
AI_PUBLIC_SNAPSHOT_MODE = "dynamic_owner_0600_v1"
APPROVED_ROOT_PREFIXES = {
    "git": frozenset({"docs"}),
    "obsidian": frozenset(
        {
            "00-总控首页.md",
            "01-权威文档",
            "02-会话精华",
            "03-索引",
            "40-AI投资员",
        }
    ),
    "notes": frozenset({"AI投资员"}),
}
DENIED_NAME_RE = re.compile(
    r"(?:^|[._-])(?:secret|credential|session|token|password|"
    r"pgpass|api[._-]?key)s?(?:$|[._-])",
    re.IGNORECASE,
)
DENIED_PUBLIC_KEY_RE = re.compile(
    r"(?:^|_)(?:api_key|private_key|secret|password|credential|pgpass|"
    r"dsn|access_token|refresh_token)(?:$|_)",
    re.IGNORECASE,
)
SECRET_MATERIAL_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bpostgres(?:ql)?://[^:\s/]+:[^@\s/]+@"),
    re.compile(
        r"(?im)^\s*(?:PGPASSWORD|OPENAI_API_KEY|DATABASE_PASSWORD)"
        r"\s*[:=]\s*[\"']?[^\s\"'<>{}]{8,}"
    ),
)
CANDIDATE_FORBIDDEN_CONTENT_RE = re.compile(
    r"(?:chain[ _-]?of[ _-]?thought|hidden[ _-]?reasoning|"
    r"raw[ _-]?prompt|system[ _-]?prompt|session[ _-]?token|"
    r"access[ _-]?token|refresh[ _-]?token|credential|"
    r"private[ _-]?key|database[ _-]?dsn|dsn|api[ _-]?key|"
    r"password|pgpass|secret|隐藏推理|隐含推理|思维链|"
    r"系统提示词|原始提示词|访问令牌|刷新令牌|凭据|"
    r"私钥|数据库连接串|密码|密钥)",
    re.IGNORECASE,
)
CANDIDATE_COMPACT_FORBIDDEN_RE = re.compile(
    r"(?:chainofthought|hiddenreasoning|rawprompt|systemprompt|"
    r"sessiontoken|accesstoken|refreshtoken|credential|"
    r"privatekey|databasedsn|apikey|password|pgpass|secret|"
    r"隐藏推理|隐含推理|思维链|系统提示词|原始提示词|"
    r"访问令牌|刷新令牌|凭据|私钥|数据库连接串|密码|密钥)",
    re.IGNORECASE,
)
SEARCH_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")
PUBLIC_SNAPSHOT_DENIED_KEYS = frozenset(
    {
        "chain_of_thought",
        "credential",
        "model_credential",
        "owner_user_id",
        "password",
        "pgpass",
        "principal_id",
        "raw_prompt",
        "session_token",
        "session_token_hash",
        "system_prompt",
    }
)
PUBLIC_SNAPSHOT_TOP_FIELDS = frozenset(
    {
        "ok",
        "component",
        "component_label",
        "contract_version",
        "status",
        "profile",
        "account",
        "positions",
        "trades",
        "decisions",
        "daily_summaries",
        "performance",
        "strategy",
        "runtime",
        "public_scope",
        "readonly",
        "empty_state",
        "controls",
        "disclaimer",
        "safety_banner",
        "side_effects",
    }
)
PUBLIC_PROFILE_FIELDS = frozenset(
    {
        "ai_user_id",
        "display_name",
        "status",
        "mode",
        "model_label",
        "model_version",
        "strategy_version",
        "last_success_at",
        "pause_reason",
    }
)
PUBLIC_ACCOUNT_FIELDS = frozenset(
    {
        "virtual_account_id",
        "account_name",
        "account_status",
        "currency",
        "initial_cash",
        "cash_balance",
        "available_cash",
        "frozen_cash",
        "market_value",
        "total_equity",
        "net_pnl",
        "total_return_pct",
        "max_drawdown_pct",
        "valuation_status",
        "not_ready_position_count",
        "as_of",
    }
)
PUBLIC_POSITION_FIELDS = frozenset(
    {
        "virtual_position_id",
        "identity_key",
        "stock_code",
        "display_name",
        "quantity",
        "sellable_quantity",
        "t1_locked_quantity",
        "average_cost",
        "current_price",
        "market_value",
        "unrealized_pnl",
        "unrealized_return_pct",
        "quote_status",
        "target_price",
        "target_price_status",
        "stop_loss_price",
        "stop_loss_status",
        "holding_episode_no",
        "first_open_trade_date",
        "updated_at",
    }
)
PUBLIC_TRADE_FIELDS = frozenset(
    {
        "virtual_trade_id",
        "ai_decision_id",
        "trade_time",
        "identity_key",
        "display_name",
        "trade_side",
        "filled_quantity",
        "filled_price",
        "gross_amount",
        "total_fee_amount",
        "net_amount",
        "trade_status",
        "reason_summary",
    }
)
PUBLIC_DECISION_FIELDS = frozenset(
    {
        "ai_decision_id",
        "trade_date",
        "event_time",
        "decision_type",
        "identity_key",
        "display_name",
        "confidence",
        "reason_summary",
        "evidence",
        "counter_evidence",
        "risk_status",
        "risk_reason",
        "risk_assessment",
        "proposal_status",
        "execution_status",
        "source_signal_projection_id",
        "source_virtual_position_id",
        "source_virtual_trade_proposal_id",
        "ai_decision_run_id",
        "ai_context_snapshot_id",
        "strategy_version",
    }
)
PUBLIC_RISK_ASSESSMENT_FIELDS = frozenset(
    {"trigger", "level", "summary", "server_policy"}
)
PUBLIC_SERVER_POLICY_FIELDS = frozenset(
    {
        "allowed",
        "buy_budget_cny",
        "computed_by",
        "max_daily_new_buys",
        "max_identity_exposure_cny",
        "max_total_exposure_ratio",
        "pause_drawdown_pct",
        "policy_version",
        "reason",
    }
)
PUBLIC_DAILY_SUMMARY_FIELDS = frozenset(
    {
        "ai_daily_summary_id",
        "trade_date",
        "summary_text",
        "decision_count",
        "trade_count",
        "net_return_pct",
        "max_drawdown_pct",
        "turnover_pct",
        "risk_adjusted_score",
        "total_asset_value",
        "current_cash",
        "position_market_value",
        "daily_net_pnl",
        "success_reasons",
        "lessons",
        "next_day_watch_plan",
        "strategy_version",
        "strategy_hash",
        "knowledge_bundle_version",
        "knowledge_bundle_hash",
        "generated_at",
    }
)
PUBLIC_PERFORMANCE_FIELDS = frozenset(
    {
        "trade_date",
        "total_asset_value",
        "current_cash",
        "position_market_value",
        "daily_net_pnl",
        "net_return_pct",
        "max_drawdown_pct",
        "turnover_pct",
        "risk_adjusted_score",
        "total_trade_count",
        "winning_trade_count",
        "as_of",
    }
)
PUBLIC_STRATEGY_FIELDS = frozenset(
    {
        "strategy_id",
        "strategy_name",
        "policy_version",
        "policy_hash",
        "status",
        "risk_labels",
    }
)
PUBLIC_RUNTIME_FIELDS = frozenset(
    {
        "latest_run_id",
        "run_mode",
        "run_status",
        "model_adapter",
        "model_version",
        "last_started_at",
        "last_finished_at",
    }
)
PUBLIC_CONTROL_FIELDS = frozenset(
    {
        "proposal_enabled",
        "confirm_enabled",
        "pause_enabled",
        "strategy_edit_enabled",
        "account_edit_enabled",
        "real_trade_enabled",
    }
)
PUBLIC_SIDE_EFFECT_FIELDS = frozenset(
    {
        "writes_database",
        "database_written",
        "outbox_consumed",
        "outbox_status_updates",
        "outbox_status_updated",
        "proposal_generated",
        "order_generated",
        "trade_generated",
        "position_updated",
        "pnl_generated",
        "leaderboard_materialized",
        "delivery_triggered",
        "push_triggered",
        "voice_triggered",
        "mobile_triggered",
        "sim_written",
        "position_written",
        "real_trade_submitted",
    }
)
SUPPORTED_PROTOCOL_VERSIONS = frozenset({"2024-11-05", "2025-06-18"})
CURRENT_PROTOCOL_VERSION = "2025-06-18"


class ResearchBridgeError(ValueError):
    """A stable fail-closed bridge error."""


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    document_id: str
    root_id: str
    relative_path: str
    sha256_hex: str
    title: str
    kind: str


@dataclass(frozen=True, slots=True)
class DynamicSnapshotEntry:
    root_id: str
    relative_path: str
    mode: str


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(payload).hexdigest()


class ReadOnlyResearchBridge:
    """Serve immutable knowledge plus append-only candidate memories."""

    def __init__(
        self,
        *,
        manifest_path: Path,
        roots: Mapping[str, Path],
        expected_manifest_sha256: str,
    ) -> None:
        if not SHA256_RE.fullmatch(expected_manifest_sha256):
            raise ResearchBridgeError(
                "expected_manifest_hash_invalid"
            )
        self._expected_manifest_sha256 = expected_manifest_sha256
        if not roots:
            raise ResearchBridgeError("knowledge_roots_required")
        lexical_roots: dict[str, Path] = {}
        normalized_roots: dict[str, Path] = {}
        for root_id, root_path in roots.items():
            if root_id not in {"git", "obsidian", "notes"}:
                raise ResearchBridgeError("knowledge_root_not_allowed")
            path = Path(root_path)
            if path.is_symlink():
                raise ResearchBridgeError("knowledge_root_symlink_not_allowed")
            try:
                resolved = path.resolve(strict=True)
            except OSError as exc:
                raise ResearchBridgeError(
                    "knowledge_root_unavailable"
                ) from exc
            if not resolved.is_dir():
                raise ResearchBridgeError("knowledge_root_not_directory")
            lexical_roots[root_id] = (
                path if path.is_absolute() else Path.cwd() / path
            ).absolute()
            normalized_roots[root_id] = resolved
        self._lexical_roots = lexical_roots
        self._roots = normalized_roots
        self._manifest_path = self._safe_manifest_path(
            Path(manifest_path)
        )
        self._manifest = self._load_manifest()
        self._entries = self._load_entries()
        self._snapshot_entry = self._load_snapshot_entry()

    def _safe_manifest_path(self, path: Path) -> Path:
        git_root = self._roots.get("git")
        lexical_git_root = self._lexical_roots.get("git")
        if git_root is None or lexical_git_root is None:
            raise ResearchBridgeError("manifest_outside_git_root")
        lexical_path = path if path.is_absolute() else Path.cwd() / path
        try:
            relative = lexical_path.absolute().relative_to(
                lexical_git_root
            )
        except ValueError as exc:
            raise ResearchBridgeError(
                "manifest_outside_git_root"
            ) from exc
        current = lexical_git_root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise ResearchBridgeError("manifest_symlink_not_allowed")
        if path.is_symlink():
            raise ResearchBridgeError("manifest_symlink_not_allowed")
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise ResearchBridgeError("knowledge_manifest_unavailable") from exc
        if not resolved.is_relative_to(git_root):
            raise ResearchBridgeError("manifest_outside_git_root")
        if not resolved.is_file():
            raise ResearchBridgeError("knowledge_manifest_not_file")
        if resolved.stat().st_size > MAX_MANIFEST_BYTES:
            raise ResearchBridgeError("knowledge_manifest_too_large")
        self._manifest_parts = relative.parts
        return resolved

    def _load_manifest(self) -> dict[str, Any]:
        try:
            payload = _read_relative_regular_file(
                self._roots["git"],
                self._manifest_parts,
                max_bytes=MAX_MANIFEST_BYTES,
            )
            if sha256(payload).hexdigest() != self._expected_manifest_sha256:
                raise ResearchBridgeError(
                    "knowledge_manifest_external_hash_mismatch"
                )
            value = json.loads(payload.decode("utf-8"))
        except ResearchBridgeError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ResearchBridgeError("knowledge_manifest_invalid") from exc
        if not isinstance(value, dict):
            raise ResearchBridgeError("knowledge_manifest_invalid")
        required_fields = {
            "bundle_version",
            "bundle_sha256",
            "git_commit",
            "git_tree",
            "highest_migration",
            "relation_signature_sha256",
            "function_signature_sha256",
            "field_dictionary_sha256",
            "allowed_sources_sha256",
            "forbidden_sources_sha256",
            "reviewed_by",
            "supersedes",
            "documents",
        }
        if not required_fields.issubset(value):
            raise ResearchBridgeError(
                "knowledge_manifest_required_field_missing"
            )
        if not str(value.get("bundle_version") or "").strip():
            raise ResearchBridgeError("knowledge_bundle_version_missing")
        if (
            not GIT_OID_RE.fullmatch(str(value.get("git_commit") or ""))
            or not GIT_OID_RE.fullmatch(str(value.get("git_tree") or ""))
            or not MIGRATION_RE.fullmatch(
                str(value.get("highest_migration") or "")
            )
        ):
            raise ResearchBridgeError("knowledge_bundle_git_identity_invalid")
        for field in (
            "relation_signature_sha256",
            "function_signature_sha256",
            "field_dictionary_sha256",
            "allowed_sources_sha256",
            "forbidden_sources_sha256",
        ):
            if not SHA256_RE.fullmatch(str(value.get(field) or "")):
                raise ResearchBridgeError(
                    "knowledge_bundle_component_hash_invalid"
                )
        reviewed_by = value.get("reviewed_by")
        if (
            not isinstance(reviewed_by, list)
            or not reviewed_by
            or len(reviewed_by) > 20
            or any(
                not isinstance(item, str)
                or not item.strip()
                or len(item) > 200
                for item in reviewed_by
            )
        ):
            raise ResearchBridgeError("knowledge_bundle_reviewer_invalid")
        supersedes = value.get("supersedes")
        if supersedes is not None and not SHA256_RE.fullmatch(
            str(supersedes)
        ):
            raise ResearchBridgeError("knowledge_bundle_supersedes_invalid")
        declared_hash = str(value.get("bundle_sha256") or "")
        if not SHA256_RE.fullmatch(declared_hash):
            raise ResearchBridgeError("knowledge_bundle_hash_invalid")
        hash_payload = {
            key: item for key, item in value.items() if key != "bundle_sha256"
        }
        if _canonical_sha256(hash_payload) != declared_hash:
            raise ResearchBridgeError("knowledge_bundle_hash_mismatch")
        return value

    def _load_entries(self) -> dict[str, ManifestEntry]:
        values = self._manifest.get("documents")
        if not isinstance(values, list) or len(values) > MAX_DOCUMENTS:
            raise ResearchBridgeError("knowledge_documents_invalid")
        entries: dict[str, ManifestEntry] = {}
        for value in values:
            if not isinstance(value, dict):
                raise ResearchBridgeError("knowledge_document_invalid")
            entry = ManifestEntry(
                document_id=str(value.get("document_id") or ""),
                root_id=str(value.get("root") or ""),
                relative_path=str(value.get("path") or ""),
                sha256_hex=str(value.get("sha256") or ""),
                title=str(value.get("title") or "").strip(),
                kind=str(value.get("kind") or "").strip(),
            )
            if (
                not DOCUMENT_ID_RE.fullmatch(entry.document_id)
                or entry.document_id in entries
                or entry.root_id not in self._roots
                or not SHA256_RE.fullmatch(entry.sha256_hex)
                or not entry.title
                or not entry.kind
            ):
                raise ResearchBridgeError("knowledge_document_invalid")
            self._resolve_entry(entry)
            entries[entry.document_id] = entry
        return entries

    def _load_snapshot_entry(self) -> DynamicSnapshotEntry | None:
        value = self._manifest.get("ai_public_snapshot")
        if value is None:
            return None
        if (
            not isinstance(value, dict)
            or set(value) != {"root", "path", "mode"}
        ):
            raise ResearchBridgeError("ai_public_snapshot_invalid")
        entry = DynamicSnapshotEntry(
            root_id=str(value.get("root") or ""),
            relative_path=str(value.get("path") or ""),
            mode=str(value.get("mode") or ""),
        )
        if (
            entry.root_id != AI_PUBLIC_SNAPSHOT_ROOT_ID
            or entry.relative_path != AI_PUBLIC_SNAPSHOT_RELATIVE_PATH
            or entry.mode != AI_PUBLIC_SNAPSHOT_MODE
        ):
            raise ResearchBridgeError("ai_public_snapshot_invalid")
        pure = PurePosixPath(entry.relative_path)
        if (
            pure.is_absolute()
            or pure.suffix.lower() != ".json"
            or not pure.parts
            or any(part in {"", ".", ".."} for part in pure.parts)
            or any(part.startswith(".") for part in pure.parts)
            or pure.parts[0]
            not in APPROVED_ROOT_PREFIXES[entry.root_id]
            or any(DENIED_NAME_RE.search(part) for part in pure.parts)
        ):
            raise ResearchBridgeError("ai_public_snapshot_invalid")
        return entry

    def _resolve_entry(self, entry: ManifestEntry) -> Path:
        pure = PurePosixPath(entry.relative_path)
        if (
            pure.is_absolute()
            or not pure.parts
            or any(part in {"", ".", ".."} for part in pure.parts)
            or any(part.startswith(".") for part in pure.parts)
        ):
            raise ResearchBridgeError("knowledge_path_not_allowed")
        lowered_name = pure.name.lower()
        suffix = PurePosixPath(lowered_name).suffix
        if (
            pure.parts[0] not in APPROVED_ROOT_PREFIXES[entry.root_id]
            or suffix not in ALLOWED_SUFFIXES
            or suffix in DENIED_SUFFIXES
            or DENIED_NAME_RE.search(lowered_name)
            or any(DENIED_NAME_RE.search(part) for part in pure.parts)
        ):
            raise ResearchBridgeError("knowledge_file_not_allowed")
        root = self._roots[entry.root_id]
        candidate = root.joinpath(*pure.parts)
        current = root
        for part in pure.parts:
            current = current / part
            if current.is_symlink():
                raise ResearchBridgeError(
                    "knowledge_symlink_not_allowed"
                )
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as exc:
            raise ResearchBridgeError(
                "knowledge_document_unavailable"
            ) from exc
        if not resolved.is_relative_to(root) or not resolved.is_file():
            raise ResearchBridgeError("knowledge_path_not_allowed")
        size = resolved.stat().st_size
        if size > MAX_DOCUMENT_BYTES:
            raise ResearchBridgeError("knowledge_document_too_large")
        return resolved

    def _read_entry(
        self,
        entry: ManifestEntry,
        *,
        max_bytes: int = MAX_DOCUMENT_BYTES,
    ) -> str:
        if not 0 < max_bytes <= MAX_DOCUMENT_BYTES:
            raise ResearchBridgeError("knowledge_read_budget_invalid")
        try:
            self._resolve_entry(entry)
            payload = _read_relative_regular_file(
                self._roots[entry.root_id],
                PurePosixPath(entry.relative_path).parts,
                max_bytes=max_bytes,
            )
        except (OSError, ResearchBridgeError) as exc:
            if isinstance(exc, ResearchBridgeError):
                raise
            raise ResearchBridgeError(
                "knowledge_document_unavailable"
            ) from exc
        if sha256(payload).hexdigest() != entry.sha256_hex:
            raise ResearchBridgeError("knowledge_document_hash_mismatch")
        try:
            text = payload.decode("utf-8")
        except UnicodeError as exc:
            raise ResearchBridgeError(
                "knowledge_document_not_utf8"
            ) from exc
        if any(pattern.search(text) for pattern in SECRET_MATERIAL_PATTERNS):
            raise ResearchBridgeError(
                "knowledge_document_contains_secret_material"
            )
        return text

    def manifest_summary(self) -> dict[str, Any]:
        return {
            "bundle_version": self._manifest["bundle_version"],
            "bundle_sha256": self._manifest["bundle_sha256"],
            "git_commit": self._manifest["git_commit"],
            "git_tree": self._manifest["git_tree"],
            "highest_migration": self._manifest["highest_migration"],
            "field_dictionary_sha256": self._manifest[
                "field_dictionary_sha256"
            ],
            "document_count": len(self._entries),
            "snapshot_available": self._snapshot_entry is not None,
            "snapshot_mode": (
                self._snapshot_entry.mode
                if self._snapshot_entry is not None
                else None
            ),
            "readonly": True,
            "memory_candidate_append_only": True,
        }

    def knowledge_search(
        self, *, query: str, limit: int = 8
    ) -> dict[str, Any]:
        if not isinstance(query, str):
            raise ResearchBridgeError("knowledge_query_invalid")
        normalized_query = query.strip()
        if not normalized_query or len(normalized_query) > MAX_QUERY_CHARS:
            raise ResearchBridgeError("knowledge_query_invalid")
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise ResearchBridgeError("knowledge_limit_invalid")
        normalized_limit = limit
        if not 1 <= normalized_limit <= MAX_SEARCH_LIMIT:
            raise ResearchBridgeError("knowledge_limit_invalid")
        query_lower = normalized_query.lower()
        tokens = [
            token.lower()
            for token in SEARCH_TOKEN_RE.findall(normalized_query)
            if token
        ]
        ranked: list[tuple[int, str, ManifestEntry, str]] = []
        searched_bytes = 0
        for entry in self._entries.values():
            remaining_bytes = MAX_SEARCH_TOTAL_BYTES - searched_bytes
            if remaining_bytes <= 0:
                raise ResearchBridgeError(
                    "knowledge_search_budget_exceeded"
                )
            try:
                text = self._read_entry(
                    entry,
                    max_bytes=min(
                        remaining_bytes, MAX_DOCUMENT_BYTES
                    ),
                )
            except ResearchBridgeError as exc:
                if (
                    str(exc) == "knowledge_document_too_large"
                    and remaining_bytes < MAX_DOCUMENT_BYTES
                ):
                    raise ResearchBridgeError(
                        "knowledge_search_budget_exceeded"
                    ) from exc
                raise
            searched_bytes += len(text.encode("utf-8"))
            haystack = (
                f"{entry.document_id} {entry.title} "
                f"{entry.kind} {text}"
            ).lower()
            score = 20 if query_lower in haystack else 0
            score += sum(3 for token in tokens if token in haystack)
            if score:
                ranked.append(
                    (
                        score,
                        entry.document_id,
                        entry,
                        self._excerpt(text, tokens),
                    )
                )
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return {
            **self.manifest_summary(),
            "query": normalized_query,
            "results": [
                {
                    "document_id": entry.document_id,
                    "title": entry.title,
                    "kind": entry.kind,
                    "sha256": entry.sha256_hex,
                    "excerpt": excerpt,
                }
                for _, _, entry, excerpt in ranked[:normalized_limit]
            ],
        }

    def knowledge_fetch(self, *, document_id: str) -> dict[str, Any]:
        if not isinstance(document_id, str):
            raise ResearchBridgeError("knowledge_document_id_invalid")
        entry = self._entries.get(document_id)
        if entry is None:
            raise ResearchBridgeError("knowledge_document_not_found")
        text = self._read_entry(entry)
        if len(text) > MAX_FETCH_CHARS:
            raise ResearchBridgeError("knowledge_fetch_too_large")
        return {
            **self.manifest_summary(),
            "document_id": entry.document_id,
            "title": entry.title,
            "kind": entry.kind,
            "sha256": entry.sha256_hex,
            "content": text,
        }

    def ai_public_snapshot_get(self) -> dict[str, Any]:
        if self._snapshot_entry is None:
            return {
                **self.manifest_summary(),
                "available": False,
                "snapshot": None,
            }
        payload = _read_relative_regular_file(
            self._roots[self._snapshot_entry.root_id],
            PurePosixPath(
                self._snapshot_entry.relative_path
            ).parts,
            max_bytes=MAX_DOCUMENT_BYTES,
            expected_owner_uid=os.getuid(),
            expected_mode=0o600,
            require_nonempty=True,
            allow_missing=True,
            error_prefix="ai_public_snapshot",
        )
        if payload is None:
            return {
                **self.manifest_summary(),
                "available": False,
                "snapshot": None,
            }
        try:
            value = json.loads(payload.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ResearchBridgeError(
                "ai_public_snapshot_invalid"
            ) from exc
        sanitized = validate_public_ai_snapshot(value)
        if (
            not isinstance(sanitized, dict)
            or sanitized.get("public_scope")
            != "shared_ai_virtual_account"
            or sanitized.get("readonly") is not True
        ):
            raise ResearchBridgeError("ai_public_snapshot_invalid")
        return {
            **self.manifest_summary(),
            "available": True,
            "snapshot_sha256": sha256(payload).hexdigest(),
            "snapshot": sanitized,
        }

    def memory_candidate_append(
        self,
        *,
        title: str,
        summary: str,
        evidence_refs: list[str],
        counter_evidence: list[str],
        candidate_rule: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        request = _validate_candidate_request(
            title=title,
            summary=summary,
            evidence_refs=evidence_refs,
            counter_evidence=counter_evidence,
            candidate_rule=candidate_rule,
            idempotency_key=idempotency_key,
        )
        self._validate_evidence_references(request["evidence_refs"])
        memory_id = f"memory_{idempotency_key}"
        file_name = f"{memory_id}.json"
        payload = {
            "memory_id": memory_id,
            "status": "candidate_unreviewed",
            "knowledge_bundle_sha256": self._manifest["bundle_sha256"],
            "knowledge_bundle_version": self._manifest["bundle_version"],
            **request,
            "created_at": datetime.now(timezone.utc)
            .isoformat()
            .removesuffix("+00:00")
            + "Z",
        }
        encoded = (
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
        if len(encoded) > MAX_CANDIDATE_BYTES:
            raise ResearchBridgeError("memory_candidate_too_large")

        directory_fd = self._open_candidate_directory()
        try:
            lock_fd = self._open_candidate_lock(directory_fd)
        except Exception:
            os.close(directory_fd)
            raise
        temp_name = f".pending-{memory_id}-{uuid4().hex}"
        temp_created = False
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            existing_names = {
                name
                for name in os.listdir(directory_fd)
                if CANDIDATE_FILE_RE.fullmatch(name)
            }
            if (
                file_name not in existing_names
                and len(existing_names) >= MAX_CANDIDATE_FILES
            ):
                raise ResearchBridgeError(
                    "memory_candidate_quota_exceeded"
                )
            flags = (
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0)
            )
            file_fd = os.open(
                temp_name,
                flags,
                0o600,
                dir_fd=directory_fd,
            )
            temp_created = True
            try:
                os.fchmod(file_fd, 0o600)
                offset = 0
                while offset < len(encoded):
                    written = os.write(file_fd, encoded[offset:])
                    if written <= 0:
                        raise ResearchBridgeError(
                            "memory_candidate_write_failed"
                        )
                    offset += written
                os.fsync(file_fd)
            finally:
                os.close(file_fd)
            try:
                os.link(
                    temp_name,
                    file_name,
                    src_dir_fd=directory_fd,
                    dst_dir_fd=directory_fd,
                    follow_symlinks=False,
                )
                created = True
            except FileExistsError:
                created = False
            finally:
                os.unlink(temp_name, dir_fd=directory_fd)
                temp_created = False
            os.fsync(directory_fd)
            stored = self._read_candidate(
                directory_fd, memory_id=memory_id
            )
        except ResearchBridgeError:
            raise
        except OSError as exc:
            raise ResearchBridgeError(
                "memory_candidate_append_failed"
            ) from exc
        finally:
            if temp_created:
                try:
                    os.unlink(temp_name, dir_fd=directory_fd)
                except OSError:
                    pass
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
            os.close(directory_fd)

        for field, expected in request.items():
            if stored.get(field) != expected:
                raise ResearchBridgeError(
                    "memory_candidate_idempotency_conflict"
                )
        return {
            **self.manifest_summary(),
            "created": created,
            "memory": stored,
        }

    def memory_candidate_list(self, *, limit: int = 20) -> dict[str, Any]:
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= MAX_CANDIDATE_LIST_LIMIT
        ):
            raise ResearchBridgeError("memory_candidate_limit_invalid")
        directory_fd = self._open_candidate_directory()
        try:
            names = [
                name
                for name in os.listdir(directory_fd)
                if CANDIDATE_FILE_RE.fullmatch(name)
            ]
            ranked_names: list[tuple[int, str]] = []
            for name in names:
                metadata = os.stat(
                    name,
                    dir_fd=directory_fd,
                    follow_symlinks=False,
                )
                ranked_names.append(
                    (metadata.st_mtime_ns, name)
                )
            ranked_names.sort(reverse=True)
            values = [
                self._read_candidate(
                    directory_fd, memory_id=name[:-5]
                )
                for _, name in ranked_names[:limit]
            ]
        except ResearchBridgeError:
            raise
        except OSError as exc:
            raise ResearchBridgeError(
                "memory_candidate_list_failed"
            ) from exc
        finally:
            os.close(directory_fd)
        values.sort(
            key=lambda item: (
                str(item.get("created_at") or ""),
                str(item.get("memory_id") or ""),
            ),
            reverse=True,
        )
        return {
            **self.manifest_summary(),
            "memories": values[:limit],
            "candidate_count": len(names),
            "truncated": len(names) > limit,
        }

    def memory_candidate_get(self, *, memory_id: str) -> dict[str, Any]:
        if (
            not isinstance(memory_id, str)
            or not MEMORY_ID_RE.fullmatch(memory_id)
        ):
            raise ResearchBridgeError("memory_candidate_id_invalid")
        directory_fd = self._open_candidate_directory()
        try:
            value = self._read_candidate(
                directory_fd, memory_id=memory_id
            )
        finally:
            os.close(directory_fd)
        return {
            **self.manifest_summary(),
            "memory": value,
        }

    def _open_candidate_directory(self) -> int:
        root = self._roots.get("notes")
        if root is None:
            raise ResearchBridgeError(
                "memory_candidate_root_unavailable"
            )
        flags = (
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        current_fd: int | None = None
        try:
            current_fd = os.open(root, flags)
            self._validate_candidate_directory_fd(current_fd)
            for part in CANDIDATE_RELATIVE_PARTS:
                next_fd = os.open(part, flags, dir_fd=current_fd)
                try:
                    self._validate_candidate_directory_fd(next_fd)
                except Exception:
                    os.close(next_fd)
                    raise
                os.close(current_fd)
                current_fd = next_fd
            return current_fd
        except OSError as exc:
            if current_fd is not None:
                os.close(current_fd)
            raise ResearchBridgeError(
                "memory_candidate_directory_unavailable"
            ) from exc
        except Exception:
            if current_fd is not None:
                os.close(current_fd)
            raise

    @staticmethod
    def _validate_candidate_directory_fd(directory_fd: int) -> None:
        metadata = os.fstat(directory_fd)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) & 0o022
        ):
            raise ResearchBridgeError(
                "memory_candidate_directory_unsafe"
            )

    @staticmethod
    def _open_candidate_lock(directory_fd: int) -> int:
        base_flags = (
            os.O_RDWR
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            try:
                lock_fd = os.open(
                    CANDIDATE_LOCK_FILE,
                    base_flags | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=directory_fd,
                )
            except FileExistsError:
                lock_fd = os.open(
                    CANDIDATE_LOCK_FILE,
                    base_flags,
                    dir_fd=directory_fd,
                )
            os.fchmod(lock_fd, 0o600)
            metadata = os.fstat(lock_fd)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600
            ):
                os.close(lock_fd)
                raise ResearchBridgeError(
                    "memory_candidate_lock_unsafe"
                )
            return lock_fd
        except ResearchBridgeError:
            raise
        except OSError as exc:
            raise ResearchBridgeError(
                "memory_candidate_lock_unavailable"
            ) from exc

    def _validate_evidence_references(
        self, evidence_refs: list[str]
    ) -> None:
        for reference in evidence_refs:
            matched = EVIDENCE_DOCUMENT_RE.fullmatch(reference)
            if (
                matched is None
                or matched.group(1) not in self._entries
            ):
                raise ResearchBridgeError(
                    "memory_candidate_evidence_ref_invalid"
                )

    def _read_candidate(
        self, directory_fd: int, *, memory_id: str
    ) -> dict[str, Any]:
        if not MEMORY_ID_RE.fullmatch(memory_id):
            raise ResearchBridgeError("memory_candidate_id_invalid")
        file_name = f"{memory_id}.json"
        flags = (
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
        )
        try:
            file_fd = os.open(file_name, flags, dir_fd=directory_fd)
            try:
                metadata = os.fstat(file_fd)
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or metadata.st_uid != os.getuid()
                    or stat.S_IMODE(metadata.st_mode) != 0o600
                    or metadata.st_size > MAX_CANDIDATE_BYTES
                ):
                    raise ResearchBridgeError(
                        "memory_candidate_file_unsafe"
                    )
                chunks: list[bytes] = []
                total = 0
                while True:
                    chunk = os.read(
                        file_fd,
                        min(
                            65_536,
                            MAX_CANDIDATE_BYTES + 1 - total,
                        ),
                    )
                    if not chunk:
                        break
                    chunks.append(chunk)
                    total += len(chunk)
                    if total > MAX_CANDIDATE_BYTES:
                        raise ResearchBridgeError(
                            "memory_candidate_too_large"
                        )
            finally:
                os.close(file_fd)
            value = json.loads(b"".join(chunks).decode("utf-8"))
        except FileNotFoundError as exc:
            raise ResearchBridgeError(
                "memory_candidate_not_found"
            ) from exc
        except ResearchBridgeError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ResearchBridgeError(
                "memory_candidate_invalid"
            ) from exc
        return _validate_stored_candidate(
            value,
            expected_memory_id=memory_id,
            current_bundle_sha256=self._manifest["bundle_sha256"],
            current_bundle_version=self._manifest["bundle_version"],
        )

    @staticmethod
    def _excerpt(text: str, tokens: list[str]) -> str:
        lower = text.lower()
        positions = [lower.find(token) for token in tokens]
        positions = [position for position in positions if position >= 0]
        start = max((min(positions) if positions else 0) - 160, 0)
        return " ".join(text[start : start + 520].split())


def _validate_candidate_request(
    *,
    title: Any,
    summary: Any,
    evidence_refs: Any,
    counter_evidence: Any,
    candidate_rule: Any,
    idempotency_key: Any,
) -> dict[str, Any]:
    values = {
        "title": title,
        "summary": summary,
        "candidate_rule": candidate_rule,
    }
    normalized: dict[str, Any] = {}
    for field, value in values.items():
        maximum = (
            MAX_CANDIDATE_TITLE_CHARS
            if field == "title"
            else MAX_CANDIDATE_TEXT_CHARS
        )
        if not isinstance(value, str):
            raise ResearchBridgeError(
                f"memory_candidate_{field}_invalid"
            )
        candidate_text = _normalize_candidate_text(value)
        if (
            not candidate_text
            or len(candidate_text) > maximum
        ):
            raise ResearchBridgeError(
                f"memory_candidate_{field}_invalid"
            )
        normalized[field] = candidate_text
    for field, value in (
        ("evidence_refs", evidence_refs),
        ("counter_evidence", counter_evidence),
    ):
        if (
            not isinstance(value, list)
            or (field == "evidence_refs" and not value)
            or len(value) > MAX_CANDIDATE_REFERENCES
        ):
            raise ResearchBridgeError(
                f"memory_candidate_{field}_invalid"
            )
        items: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ResearchBridgeError(
                    f"memory_candidate_{field}_invalid"
                )
            candidate_text = _normalize_candidate_text(item)
            if (
                not candidate_text
                or len(candidate_text)
                > MAX_CANDIDATE_REFERENCE_CHARS
            ):
                raise ResearchBridgeError(
                    f"memory_candidate_{field}_invalid"
                )
            items.append(candidate_text)
        if field == "evidence_refs" and any(
            EVIDENCE_DOCUMENT_RE.fullmatch(item) is None
            for item in items
        ):
            raise ResearchBridgeError(
                "memory_candidate_evidence_ref_invalid"
            )
        normalized[field] = items
    if (
        not isinstance(idempotency_key, str)
        or not SHA256_RE.fullmatch(idempotency_key)
    ):
        raise ResearchBridgeError(
            "memory_candidate_idempotency_key_invalid"
        )
    normalized["idempotency_key"] = idempotency_key
    text = "\n".join(
        (
            normalized["title"],
            normalized["summary"],
            normalized["candidate_rule"],
            *normalized["evidence_refs"],
            *normalized["counter_evidence"],
        )
    )
    compact_text = "".join(
        character
        for character in unicodedata.normalize("NFKD", text)
        if unicodedata.category(character)[0] in {"L", "N"}
    )
    if (
        CANDIDATE_FORBIDDEN_CONTENT_RE.search(text)
        or CANDIDATE_COMPACT_FORBIDDEN_RE.search(compact_text)
        or any(
        pattern.search(text) for pattern in SECRET_MATERIAL_PATTERNS
        )
    ):
        raise ResearchBridgeError(
            "memory_candidate_forbidden_content"
        )
    return normalized


def _normalize_candidate_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return "".join(
        character
        for character in normalized
        if unicodedata.category(character) != "Cf"
    ).strip()


def _validate_stored_candidate(
    value: Any,
    *,
    expected_memory_id: str,
    current_bundle_sha256: str,
    current_bundle_version: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ResearchBridgeError("memory_candidate_invalid")
    required = {
        "memory_id",
        "status",
        "knowledge_bundle_sha256",
        "knowledge_bundle_version",
        "title",
        "summary",
        "evidence_refs",
        "counter_evidence",
        "candidate_rule",
        "idempotency_key",
        "created_at",
    }
    if set(value) != required:
        raise ResearchBridgeError("memory_candidate_invalid")
    request = _validate_candidate_request(
        title=value.get("title"),
        summary=value.get("summary"),
        evidence_refs=value.get("evidence_refs"),
        counter_evidence=value.get("counter_evidence"),
        candidate_rule=value.get("candidate_rule"),
        idempotency_key=value.get("idempotency_key"),
    )
    stored_bundle_sha256 = value.get("knowledge_bundle_sha256")
    stored_bundle_version = value.get("knowledge_bundle_version")
    if (
        value.get("memory_id") != expected_memory_id
        or value.get("status") != "candidate_unreviewed"
        or not isinstance(stored_bundle_sha256, str)
        or not SHA256_RE.fullmatch(stored_bundle_sha256)
        or not isinstance(stored_bundle_version, str)
        or not stored_bundle_version.strip()
        or not isinstance(value.get("created_at"), str)
        or not value["created_at"].endswith("Z")
        or value.get("idempotency_key")
        != expected_memory_id.removeprefix("memory_")
    ):
        raise ResearchBridgeError("memory_candidate_invalid")
    return {
        "memory_id": expected_memory_id,
        "status": "candidate_unreviewed",
        "knowledge_bundle_sha256": stored_bundle_sha256,
        "knowledge_bundle_version": stored_bundle_version,
        "knowledge_bundle_current": (
            stored_bundle_sha256 == current_bundle_sha256
            and stored_bundle_version == current_bundle_version
        ),
        **request,
        "created_at": value["created_at"],
    }


def _validate_public_snapshot(value: Any) -> dict[str, Any]:
    snapshot = _public_object(
        value, PUBLIC_SNAPSHOT_TOP_FIELDS, "snapshot"
    )
    _public_scalar_fields(
        snapshot,
        {
            "profile",
            "account",
            "positions",
            "trades",
            "decisions",
            "daily_summaries",
            "performance",
            "strategy",
            "runtime",
            "controls",
            "disclaimer",
            "safety_banner",
            "side_effects",
        },
        "snapshot",
    )
    for field, allowed in (
        ("profile", PUBLIC_PROFILE_FIELDS),
        ("account", PUBLIC_ACCOUNT_FIELDS),
        ("performance", PUBLIC_PERFORMANCE_FIELDS),
        ("strategy", PUBLIC_STRATEGY_FIELDS),
        ("runtime", PUBLIC_RUNTIME_FIELDS),
        ("controls", PUBLIC_CONTROL_FIELDS),
        ("side_effects", PUBLIC_SIDE_EFFECT_FIELDS),
    ):
        if field in snapshot:
            nested = _public_object(snapshot[field], allowed, field)
            complex_fields = (
                {"risk_labels"} if field == "strategy" else set()
            )
            _public_scalar_fields(
                nested, complex_fields, field
            )
    for field, allowed in (
        ("positions", PUBLIC_POSITION_FIELDS),
        ("trades", PUBLIC_TRADE_FIELDS),
        ("decisions", PUBLIC_DECISION_FIELDS),
        ("daily_summaries", PUBLIC_DAILY_SUMMARY_FIELDS),
    ):
        if field in snapshot:
            rows = snapshot[field]
            if not isinstance(rows, list) or len(rows) > 1_000:
                raise ResearchBridgeError(
                    "ai_public_snapshot_invalid"
                )
            for row in rows:
                nested = _public_object(row, allowed, field)
                complex_fields: set[str] = set()
                if field == "decisions":
                    complex_fields = {
                        "evidence",
                        "counter_evidence",
                        "risk_assessment",
                    }
                elif field == "daily_summaries":
                    complex_fields = {
                        "success_reasons",
                        "lessons",
                        "next_day_watch_plan",
                    }
                _public_scalar_fields(
                    nested, complex_fields, field
                )
    for field in ("disclaimer", "safety_banner"):
        if field in snapshot:
            _public_string_list(snapshot[field], field)
    strategy = snapshot.get("strategy")
    if isinstance(strategy, dict) and "risk_labels" in strategy:
        _public_string_list(strategy["risk_labels"], "risk_labels")
    for row in snapshot.get("decisions") or []:
        for field in ("evidence", "counter_evidence"):
            if field in row:
                _public_string_list(row[field], field)
        if "risk_assessment" in row:
            risk_assessment = _public_object(
                row["risk_assessment"],
                PUBLIC_RISK_ASSESSMENT_FIELDS,
                "risk_assessment",
            )
            _public_scalar_fields(
                risk_assessment,
                {"server_policy"},
                "risk_assessment",
            )
            if "server_policy" in risk_assessment:
                _validate_public_server_policy(
                    risk_assessment["server_policy"]
                )
    for row in snapshot.get("daily_summaries") or []:
        for field in (
            "success_reasons",
            "lessons",
            "next_day_watch_plan",
        ):
            if field in row:
                _public_string_list(row[field], field)
    _validate_public_value(snapshot, depth=0)
    return snapshot


def validate_public_ai_snapshot(value: Any) -> dict[str, Any]:
    """Validate one sanitized public AI snapshot without widening its schema."""

    return _validate_public_snapshot(value)


def _public_object(
    value: Any, allowed: frozenset[str], label: str
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ResearchBridgeError("ai_public_snapshot_invalid")
    keys = {str(key) for key in value}
    if keys - allowed:
        raise ResearchBridgeError(
            f"ai_public_snapshot_unknown_{label}_field"
        )
    if any(
        key.lower() in PUBLIC_SNAPSHOT_DENIED_KEYS
        or DENIED_PUBLIC_KEY_RE.search(key.lower())
        for key in keys
    ):
        raise ResearchBridgeError("ai_public_snapshot_private_field")
    return value


def _public_string_list(value: Any, label: str) -> None:
    if (
        not isinstance(value, list)
        or len(value) > 1_000
        or any(not isinstance(item, str) for item in value)
    ):
        raise ResearchBridgeError(
            f"ai_public_snapshot_invalid_{label}"
        )


def _public_scalar_fields(
    value: dict[str, Any],
    complex_fields: set[str],
    label: str,
) -> None:
    for key, item in value.items():
        if key in complex_fields:
            continue
        if item is not None and not isinstance(
            item, (bool, int, float, str)
        ):
            raise ResearchBridgeError(
                f"ai_public_snapshot_invalid_{label}_field_type"
            )


def _validate_public_server_policy(value: Any) -> None:
    policy = _public_object(
        value,
        PUBLIC_SERVER_POLICY_FIELDS,
        "server_policy",
    )
    if set(policy) != PUBLIC_SERVER_POLICY_FIELDS:
        raise ResearchBridgeError(
            "ai_public_snapshot_incomplete_server_policy"
        )
    if type(policy["allowed"]) is not bool:
        raise ResearchBridgeError(
            "ai_public_snapshot_invalid_server_policy_field_type"
        )
    for field in (
        "buy_budget_cny",
        "max_daily_new_buys",
        "max_identity_exposure_cny",
        "max_total_exposure_ratio",
        "pause_drawdown_pct",
    ):
        if (
            isinstance(policy[field], bool)
            or not isinstance(policy[field], (int, float))
        ):
            raise ResearchBridgeError(
                "ai_public_snapshot_invalid_server_policy_field_type"
            )
    for field in ("computed_by", "policy_version", "reason"):
        if not isinstance(policy[field], str):
            raise ResearchBridgeError(
                "ai_public_snapshot_invalid_server_policy_field_type"
            )


def _validate_public_value(value: Any, *, depth: int) -> None:
    if depth > 8:
        raise ResearchBridgeError("ai_public_snapshot_too_deep")
    if value is None or isinstance(value, (bool, int, float)):
        return
    if isinstance(value, str):
        if len(value) > 10_000:
            raise ResearchBridgeError("ai_public_snapshot_value_too_large")
        return
    if isinstance(value, list):
        if len(value) > 1_000:
            raise ResearchBridgeError("ai_public_snapshot_value_too_large")
        for item in value:
            _validate_public_value(item, depth=depth + 1)
        return
    if isinstance(value, dict):
        for item in value.values():
            _validate_public_value(item, depth=depth + 1)
        return
    raise ResearchBridgeError("ai_public_snapshot_invalid")


def _read_relative_regular_file(
    root: Path,
    parts: tuple[str, ...],
    *,
    max_bytes: int,
    expected_owner_uid: int | None = None,
    expected_mode: int | None = None,
    require_nonempty: bool = False,
    allow_missing: bool = False,
    error_prefix: str = "knowledge_document",
) -> bytes | None:
    """Open each component relative to its parent without following symlinks."""
    if not parts:
        raise ResearchBridgeError("knowledge_path_not_allowed")
    cloexec = getattr(os, "O_CLOEXEC", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    nonblock = getattr(os, "O_NONBLOCK", 0)
    current_fd = os.open(
        root,
        os.O_RDONLY | directory | cloexec | nofollow,
    )
    try:
        for part in parts[:-1]:
            next_fd = os.open(
                part,
                os.O_RDONLY | directory | cloexec | nofollow,
                dir_fd=current_fd,
            )
            os.close(current_fd)
            current_fd = next_fd
        file_fd = os.open(
            parts[-1],
            os.O_RDONLY | cloexec | nofollow | nonblock,
            dir_fd=current_fd,
        )
        try:
            metadata = os.fstat(file_fd)
            if not stat.S_ISREG(metadata.st_mode):
                raise ResearchBridgeError(
                    f"{error_prefix}_not_regular_file"
                )
            if (
                expected_owner_uid is not None
                and metadata.st_uid != expected_owner_uid
            ):
                raise ResearchBridgeError(
                    f"{error_prefix}_owner_mismatch"
                )
            if (
                expected_mode is not None
                and stat.S_IMODE(metadata.st_mode) != expected_mode
            ):
                raise ResearchBridgeError(
                    f"{error_prefix}_mode_mismatch"
                )
            if require_nonempty and metadata.st_size <= 0:
                raise ResearchBridgeError(f"{error_prefix}_empty")
            if metadata.st_size > max_bytes:
                raise ResearchBridgeError(
                    f"{error_prefix}_too_large"
                )
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = os.read(
                    file_fd, min(65_536, max_bytes + 1 - total)
                )
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > max_bytes:
                    raise ResearchBridgeError(
                        f"{error_prefix}_too_large"
                    )
            return b"".join(chunks)
        finally:
            os.close(file_fd)
    except OSError as exc:
        if allow_missing and exc.errno == errno.ENOENT:
            return None
        raise ResearchBridgeError(
            f"{error_prefix}_symlink_or_file_type_not_allowed"
        ) from exc
    finally:
        os.close(current_fd)


def tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "knowledge_search",
            "description": "Search frozen N6 AI knowledge artifacts.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "maxLength": MAX_QUERY_CHARS},
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": MAX_SEARCH_LIMIT,
                        "default": 8,
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
        {
            "name": "knowledge_fetch",
            "description": "Fetch one manifest-bound knowledge artifact.",
            "inputSchema": {
                "type": "object",
                "properties": {"document_id": {"type": "string"}},
                "required": ["document_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "ai_public_snapshot_get",
            "description": (
                "Read the current publisher-owned sanitized public "
                "AI-account snapshot."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
        {
            "name": "memory_candidate_append",
            "description": (
                "Atomically append one unreviewed candidate memory."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "maxLength": MAX_CANDIDATE_TITLE_CHARS,
                    },
                    "summary": {
                        "type": "string",
                        "maxLength": MAX_CANDIDATE_TEXT_CHARS,
                    },
                    "evidence_refs": {
                        "type": "array",
                        "maxItems": MAX_CANDIDATE_REFERENCES,
                        "items": {
                            "type": "string",
                            "maxLength": MAX_CANDIDATE_REFERENCE_CHARS,
                        },
                    },
                    "counter_evidence": {
                        "type": "array",
                        "maxItems": MAX_CANDIDATE_REFERENCES,
                        "items": {
                            "type": "string",
                            "maxLength": MAX_CANDIDATE_REFERENCE_CHARS,
                        },
                    },
                    "candidate_rule": {
                        "type": "string",
                        "maxLength": MAX_CANDIDATE_TEXT_CHARS,
                    },
                    "idempotency_key": {
                        "type": "string",
                        "pattern": "^[0-9a-f]{64}$",
                    },
                },
                "required": [
                    "title",
                    "summary",
                    "evidence_refs",
                    "counter_evidence",
                    "candidate_rule",
                    "idempotency_key",
                ],
                "additionalProperties": False,
            },
        },
        {
            "name": "memory_candidate_list",
            "description": "List append-only unreviewed candidate memories.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": MAX_CANDIDATE_LIST_LIMIT,
                        "default": 20,
                    }
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "memory_candidate_get",
            "description": "Fetch one unreviewed candidate memory by id.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "memory_id": {
                        "type": "string",
                        "pattern": "^memory_[0-9a-f]{64}$",
                    }
                },
                "required": ["memory_id"],
                "additionalProperties": False,
            },
        },
    ]


def call_tool(
    bridge: ReadOnlyResearchBridge,
    name: str,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    normalized_arguments = dict(arguments)
    missing_meta = object()
    request_meta = normalized_arguments.pop("_meta", missing_meta)
    if request_meta is not missing_meta and not isinstance(
        request_meta, dict
    ):
        raise ResearchBridgeError("tool_arguments_invalid")
    arguments = normalized_arguments
    if name == "knowledge_search":
        allowed = {"query", "limit"}
        if (
            set(arguments) - allowed
            or "query" not in arguments
            or not isinstance(arguments["query"], str)
            or (
                "limit" in arguments
                and (
                    isinstance(arguments["limit"], bool)
                    or not isinstance(arguments["limit"], int)
                )
            )
        ):
            raise ResearchBridgeError("tool_arguments_invalid")
        return bridge.knowledge_search(
            query=arguments["query"],
            limit=arguments.get("limit", 8),
        )
    if name == "knowledge_fetch":
        if (
            set(arguments) != {"document_id"}
            or not isinstance(arguments["document_id"], str)
        ):
            raise ResearchBridgeError("tool_arguments_invalid")
        return bridge.knowledge_fetch(
            document_id=arguments["document_id"]
        )
    if name == "ai_public_snapshot_get":
        if arguments:
            raise ResearchBridgeError("tool_arguments_invalid")
        return bridge.ai_public_snapshot_get()
    if name == "memory_candidate_append":
        required = {
            "title",
            "summary",
            "evidence_refs",
            "counter_evidence",
            "candidate_rule",
            "idempotency_key",
        }
        if set(arguments) != required:
            raise ResearchBridgeError("tool_arguments_invalid")
        return bridge.memory_candidate_append(**arguments)
    if name == "memory_candidate_list":
        if set(arguments) - {"limit"}:
            raise ResearchBridgeError("tool_arguments_invalid")
        return bridge.memory_candidate_list(
            limit=arguments.get("limit", 20)
        )
    if name == "memory_candidate_get":
        if (
            set(arguments) != {"memory_id"}
            or not isinstance(arguments["memory_id"], str)
        ):
            raise ResearchBridgeError("tool_arguments_invalid")
        return bridge.memory_candidate_get(
            memory_id=arguments["memory_id"]
        )
    raise ResearchBridgeError("tool_not_found")


def serve_stdio(
    bridge: ReadOnlyResearchBridge,
    *,
    input_stream: BinaryIO,
    output_stream: BinaryIO,
    max_line_bytes: int = MAX_RPC_LINE_BYTES,
) -> None:
    """Serve newline-delimited JSON-RPC 2.0 used by stdio MCP clients."""
    lifecycle = "new"
    while True:
        line = input_stream.readline(max_line_bytes + 1)
        if not line:
            return
        if len(line) > max_line_bytes or not line.endswith(b"\n"):
            while line and not line.endswith(b"\n"):
                line = input_stream.readline(max_line_bytes + 1)
            _write_rpc_error(output_stream, None, -32700, "request_too_large")
            continue
        try:
            request = json.loads(line.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            _write_rpc_error(output_stream, None, -32700, "parse_error")
            continue
        if not isinstance(request, dict):
            _write_rpc_error(output_stream, None, -32600, "invalid_request")
            continue
        if request.get("jsonrpc") != "2.0":
            _write_rpc_error(output_stream, None, -32600, "invalid_request")
            continue
        method = request.get("method")
        if "id" not in request:
            if method == "notifications/initialized":
                params = request.get("params", {})
                if (
                    lifecycle == "initialize_responded"
                    and isinstance(params, dict)
                ):
                    lifecycle = "initialized"
                continue
            continue
        request_id = request.get("id")
        if (
            isinstance(request_id, bool)
            or not isinstance(request_id, (int, str))
            or not isinstance(method, str)
        ):
            _write_rpc_error(
                output_stream, None, -32600, "invalid_request"
            )
            continue
        try:
            if method == "initialize":
                if lifecycle != "new":
                    raise ResearchBridgeError("already_initialized")
                params = request.get("params")
                if (
                    not isinstance(params, dict)
                    or not isinstance(params.get("protocolVersion"), str)
                    or not isinstance(params.get("capabilities"), dict)
                    or not isinstance(params.get("clientInfo"), dict)
                    or not isinstance(
                        params["clientInfo"].get("name"), str
                    )
                    or not params["clientInfo"]["name"].strip()
                    or not isinstance(
                        params["clientInfo"].get("version"), str
                    )
                    or not params["clientInfo"]["version"].strip()
                ):
                    raise ResearchBridgeError(
                        "initialize_params_invalid"
                    )
                requested_version = params["protocolVersion"]
                negotiated_version = (
                    requested_version
                    if requested_version in SUPPORTED_PROTOCOL_VERSIONS
                    else CURRENT_PROTOCOL_VERSION
                )
                result = {
                    "protocolVersion": negotiated_version,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {
                        "name": "n6-ai-research-readonly",
                        "version": "1.0.0",
                    },
                }
                lifecycle = "initialize_responded"
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                if lifecycle != "initialized":
                    raise ResearchBridgeError("not_initialized")
                result = {"tools": tool_definitions()}
            elif method == "tools/call":
                if lifecycle != "initialized":
                    raise ResearchBridgeError("not_initialized")
                params = request.get("params")
                if (
                    not isinstance(params, dict)
                    or set(params) - {"name", "arguments", "_meta"}
                    or not isinstance(params.get("name"), str)
                    or (
                        "_meta" in params
                        and not isinstance(params["_meta"], dict)
                    )
                ):
                    raise ResearchBridgeError("tool_arguments_invalid")
                name = params["name"]
                arguments = params.get("arguments", {})
                if not isinstance(arguments, dict):
                    raise ResearchBridgeError("tool_arguments_invalid")
                if name not in {
                    "knowledge_search",
                    "knowledge_fetch",
                    "ai_public_snapshot_get",
                    "memory_candidate_append",
                    "memory_candidate_list",
                    "memory_candidate_get",
                }:
                    raise ResearchBridgeError(
                        "tool_arguments_invalid"
                    )
                try:
                    payload = call_tool(bridge, name, arguments)
                except ResearchBridgeError as exc:
                    if str(exc) == "tool_arguments_invalid":
                        raise
                    result = _tool_call_result(
                        {"error": str(exc)}, is_error=True
                    )
                else:
                    result = _tool_call_result(
                        payload, is_error=False
                    )
            else:
                _write_rpc_error(
                    output_stream, request_id, -32601, "method_not_found"
                )
                continue
            _write_rpc_result(output_stream, request_id, result)
        except ResearchBridgeError as exc:
            message = str(exc)
            _write_rpc_error(
                output_stream,
                request_id,
                (
                    -32602
                    if message
                    in {
                        "initialize_params_invalid",
                        "tool_arguments_invalid",
                    }
                    else -32000
                ),
                message,
            )
        except Exception:
            _write_rpc_error(
                output_stream, request_id, -32603, "internal_error"
            )


def _write_rpc_result(
    output_stream: BinaryIO, request_id: Any, result: Any
) -> None:
    _write_rpc(
        output_stream,
        {"jsonrpc": "2.0", "id": request_id, "result": result},
    )


def _tool_call_result(
    payload: Mapping[str, Any], *, is_error: bool
) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    payload,
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            }
        ],
        "isError": is_error,
    }


def _write_rpc_error(
    output_stream: BinaryIO,
    request_id: Any,
    code: int,
    message: str,
) -> None:
    _write_rpc(
        output_stream,
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        },
    )


def _write_rpc(output_stream: BinaryIO, payload: Any) -> None:
    output_stream.write(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True
        ).encode("utf-8")
        + b"\n"
    )
    output_stream.flush()
