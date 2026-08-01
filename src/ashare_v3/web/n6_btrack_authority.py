"""N6 B-track database authority boundary.

The browser never supplies a principal.  The web process hashes the opaque
session cookie with the existing application algorithm and passes only that
hash to the 042 SECURITY DEFINER functions.  Those functions resolve the
active user and the exactly-one persistent principal inside PostgreSQL.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, Protocol

import psycopg
from psycopg.rows import dict_row


SESSION_HASH_RE = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class BTrackAuthority:
    user_session_id: int
    user_id: int
    principal_id: int
    principal_type: str
    principal_status: str
    display_name: str

    def principal_payload(self) -> dict[str, Any]:
        return {
            "principal_id": self.principal_id,
            "principal_type": self.principal_type,
            "owner_user_id": self.user_id,
            "principal_status": self.principal_status,
            "display_name": self.display_name,
            "principal_source": "database_session_authority",
        }


class N6BTrackAuthorityRepository(Protocol):
    def resolve_authority(self, session_token_hash: str) -> BTrackAuthority | None:
        ...

    def list_monitor_items(self, session_token_hash: str, *, asset_kind: str | None, limit: int) -> dict[str, Any]:
        ...

    def upsert_monitor_item(
        self,
        session_token_hash: str,
        *,
        asset_kind: str,
        identity_key: str,
        direction: str,
        for_trade_date: str,
    ) -> dict[str, Any]:
        ...

    def remove_monitor_item(self, session_token_hash: str, *, monitor_id: int) -> dict[str, Any]:
        ...

    def list_realtime_scope_items(self, session_token_hash: str, *, limit: int) -> dict[str, Any]:
        ...

    def upsert_realtime_scope_item(
        self,
        session_token_hash: str,
        *,
        asset_kind: str,
        identity_key: str,
        for_trade_date: str,
    ) -> dict[str, Any]:
        ...

    def remove_realtime_scope_item(self, session_token_hash: str, *, realtime_scope_id: int) -> dict[str, Any]:
        ...

    def preview_bulk_scope(
        self,
        session_token_hash: str,
        *,
        target_scope: str,
        asset_kind: str,
        identity_keys: list[str],
        for_trade_date: str,
        source_run_id: str,
        selection_sha256: str,
    ) -> dict[str, Any]:
        ...

    def bulk_upsert_monitor_items(
        self,
        session_token_hash: str,
        *,
        asset_kind: str,
        identity_keys: list[str],
        for_trade_date: str,
        source_run_id: str,
        selection_sha256: str,
    ) -> dict[str, Any]:
        ...

    def bulk_upsert_recommended_monitor_bundle(
        self,
        session_token_hash: str,
        *,
        board_selection: Mapping[str, Any],
        stock_selection: Mapping[str, Any],
    ) -> dict[str, Any]:
        ...

    def bulk_upsert_realtime_scope_items(
        self,
        session_token_hash: str,
        *,
        asset_kind: str,
        identity_keys: list[str],
        for_trade_date: str,
        source_run_id: str,
        selection_sha256: str,
    ) -> dict[str, Any]:
        ...

    def list_trade_proposals(self, session_token_hash: str, *, limit: int) -> dict[str, Any]:
        ...

    def create_trade_proposal(
        self,
        session_token_hash: str,
        *,
        source_type: str,
        source_id: int,
    ) -> dict[str, Any]:
        ...

    def confirm_trade_proposal(
        self,
        session_token_hash: str,
        *,
        proposal_id: int,
        idempotency_key: str,
    ) -> dict[str, Any]:
        ...

    def cancel_trade_proposals(
        self,
        session_token_hash: str,
        *,
        proposal_ids: list[int],
    ) -> dict[str, Any]:
        ...

    def list_virtual_trades(self, session_token_hash: str, *, limit: int) -> dict[str, Any]:
        ...

    def fetch_public_ai_agent_dashboard(
        self,
        session_token_hash: str,
        *,
        decision_limit: int,
        trade_limit: int,
        summary_limit: int,
    ) -> dict[str, Any] | None:
        ...

    def fetch_public_ai_decision_detail(
        self,
        session_token_hash: str,
        *,
        decision_id: int,
    ) -> dict[str, Any] | None:
        ...


class PostgresN6BTrackAuthorityRepository:
    """Function-only repository intended for the restricted B-track role."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    @staticmethod
    def _session_hash(value: str) -> str:
        normalized = str(value or "").strip()
        if SESSION_HASH_RE.fullmatch(normalized) is None:
            raise ValueError("invalid_session_token_hash")
        return normalized

    def _call_one(self, function_name: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
        allowed = {
            "n6_btrack_resolve_authority",
            "n6_btrack_monitor_list",
            "n6_btrack_monitor_upsert",
            "n6_btrack_monitor_remove",
            "n6_btrack_realtime_list",
            "n6_btrack_realtime_upsert",
            "n6_btrack_realtime_remove",
            "n6_btrack_scope_bulk_preview",
            "n6_btrack_proposal_list",
            "n6_btrack_proposal_create",
            "n6_btrack_proposal_confirm",
            "n6_btrack_proposals_cancel",
            "n6_btrack_virtual_trade_list",
            "n6_btrack_ai_public_snapshot",
            "n6_btrack_ai_public_decision_detail",
        }
        if function_name not in allowed:
            raise ValueError("function_not_allowlisted")
        placeholders = ", ".join(["%s"] * len(params))
        with psycopg.connect(
            self.dsn,
            connect_timeout=10,
            options="-c default_transaction_read_only=on",
            row_factory=dict_row,
        ) as conn, conn.cursor() as cur:
            cur.execute(f"SELECT public.{function_name}({placeholders}) AS payload", params)
            row = cur.fetchone()
        if not row or row.get("payload") is None:
            return None
        payload = row["payload"]
        return dict(payload) if isinstance(payload, dict) else None

    def _call_write(self, function_name: str, params: tuple[Any, ...]) -> dict[str, Any]:
        allowed = {
            "n6_btrack_monitor_upsert",
            "n6_btrack_monitor_remove",
            "n6_btrack_realtime_upsert",
            "n6_btrack_realtime_remove",
            "n6_btrack_monitor_bulk_upsert",
            "n6_btrack_realtime_bulk_upsert",
            "n6_btrack_proposal_create",
            "n6_btrack_proposal_confirm",
            "n6_btrack_proposals_cancel",
        }
        if function_name not in allowed:
            raise ValueError("write_function_not_allowlisted")
        placeholders = ", ".join(["%s"] * len(params))
        with psycopg.connect(self.dsn, connect_timeout=10, row_factory=dict_row) as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(f"SELECT public.{function_name}({placeholders}) AS payload", params)
                row = cur.fetchone()
        payload = row.get("payload") if row else None
        return dict(payload) if isinstance(payload, dict) else {"ok": False, "status": "not_ready"}

    def resolve_authority(self, session_token_hash: str) -> BTrackAuthority | None:
        payload = self._call_one(
            "n6_btrack_resolve_authority",
            (self._session_hash(session_token_hash),),
        )
        if not payload:
            return None
        try:
            return BTrackAuthority(
                user_session_id=int(payload["user_session_id"]),
                user_id=int(payload["user_id"]),
                principal_id=int(payload["principal_id"]),
                principal_type=str(payload["principal_type"]),
                principal_status=str(payload["principal_status"]),
                display_name=str(payload.get("display_name") or ""),
            )
        except (KeyError, TypeError, ValueError):
            return None

    def list_monitor_items(self, session_token_hash: str, *, asset_kind: str | None, limit: int) -> dict[str, Any]:
        return self._call_one(
            "n6_btrack_monitor_list",
            (self._session_hash(session_token_hash), asset_kind, max(1, min(int(limit), 1000))),
        ) or {"tables_ready": False, "items": []}

    def upsert_monitor_item(self, session_token_hash: str, *, asset_kind: str, identity_key: str, direction: str, for_trade_date: str) -> dict[str, Any]:
        return self._call_write("n6_btrack_monitor_upsert", (self._session_hash(session_token_hash), asset_kind, identity_key, direction, for_trade_date))

    def remove_monitor_item(self, session_token_hash: str, *, monitor_id: int) -> dict[str, Any]:
        return self._call_write("n6_btrack_monitor_remove", (self._session_hash(session_token_hash), int(monitor_id)))

    def list_realtime_scope_items(self, session_token_hash: str, *, limit: int) -> dict[str, Any]:
        return self._call_one("n6_btrack_realtime_list", (self._session_hash(session_token_hash), max(1, min(int(limit), 1000)))) or {"tables_ready": False, "items": []}

    def upsert_realtime_scope_item(self, session_token_hash: str, *, asset_kind: str, identity_key: str, for_trade_date: str) -> dict[str, Any]:
        return self._call_write("n6_btrack_realtime_upsert", (self._session_hash(session_token_hash), asset_kind, identity_key, for_trade_date))

    def remove_realtime_scope_item(self, session_token_hash: str, *, realtime_scope_id: int) -> dict[str, Any]:
        return self._call_write("n6_btrack_realtime_remove", (self._session_hash(session_token_hash), int(realtime_scope_id)))

    def preview_bulk_scope(
        self,
        session_token_hash: str,
        *,
        target_scope: str,
        asset_kind: str,
        identity_keys: list[str],
        for_trade_date: str,
        source_run_id: str,
        selection_sha256: str,
    ) -> dict[str, Any]:
        return self._call_one(
            "n6_btrack_scope_bulk_preview",
            (
                self._session_hash(session_token_hash),
                target_scope,
                asset_kind,
                list(identity_keys),
                for_trade_date,
                source_run_id,
                selection_sha256,
            ),
        ) or {"ok": False, "status": "not_ready"}

    def bulk_upsert_monitor_items(
        self,
        session_token_hash: str,
        *,
        asset_kind: str,
        identity_keys: list[str],
        for_trade_date: str,
        source_run_id: str,
        selection_sha256: str,
    ) -> dict[str, Any]:
        return self._call_write(
            "n6_btrack_monitor_bulk_upsert",
            (
                self._session_hash(session_token_hash),
                asset_kind,
                list(identity_keys),
                for_trade_date,
                source_run_id,
                selection_sha256,
            ),
        )

    def bulk_upsert_recommended_monitor_bundle(
        self,
        session_token_hash: str,
        *,
        board_selection: Mapping[str, Any],
        stock_selection: Mapping[str, Any],
    ) -> dict[str, Any]:
        session_hash = self._session_hash(session_token_hash)
        selections = (
            ("board", board_selection),
            ("stock", stock_selection),
        )

        class BundleWriteFailed(RuntimeError):
            def __init__(self, asset_kind: str) -> None:
                super().__init__(asset_kind)
                self.asset_kind = asset_kind

        results: dict[str, dict[str, Any]] = {}
        try:
            with psycopg.connect(self.dsn, connect_timeout=10, row_factory=dict_row) as conn:
                with conn.transaction(), conn.cursor() as cur:
                    for asset_kind, selection in selections:
                        identity_keys = list(selection.get("identity_keys") or [])
                        if not identity_keys:
                            results[asset_kind] = {
                                "ok": True,
                                "status": "active",
                                "asset_kind": asset_kind,
                                "matched_count": 0,
                                "direction_row_count": 0,
                                "write_row_count": 0,
                                "added_count": 0,
                                "already_active_count": 0,
                                "reactivated_count": 0,
                            }
                            continue
                        cur.execute(
                            "SELECT public.n6_btrack_monitor_bulk_upsert(%s, %s, %s, %s, %s, %s) AS payload",
                            (
                                session_hash,
                                asset_kind,
                                identity_keys,
                                str(selection.get("for_trade_date") or ""),
                                str(selection.get("source_run_id") or ""),
                                str(selection.get("selection_sha256") or ""),
                            ),
                        )
                        row = cur.fetchone()
                        payload = row.get("payload") if row else None
                        if not isinstance(payload, dict) or not payload.get("ok"):
                            raise BundleWriteFailed(asset_kind)
                        results[asset_kind] = dict(payload)
        except BundleWriteFailed as error:
            return {
                "ok": False,
                "status": "rolled_back",
                "error": "recommended_bundle_rolled_back",
                "failed_asset_kind": error.asset_kind,
            }
        return {
            "ok": True,
            "status": "active",
            "board": results["board"],
            "stock": results["stock"],
        }

    def bulk_upsert_realtime_scope_items(
        self,
        session_token_hash: str,
        *,
        asset_kind: str,
        identity_keys: list[str],
        for_trade_date: str,
        source_run_id: str,
        selection_sha256: str,
    ) -> dict[str, Any]:
        return self._call_write(
            "n6_btrack_realtime_bulk_upsert",
            (
                self._session_hash(session_token_hash),
                asset_kind,
                list(identity_keys),
                for_trade_date,
                source_run_id,
                selection_sha256,
            ),
        )

    def list_trade_proposals(self, session_token_hash: str, *, limit: int) -> dict[str, Any]:
        return self._call_one("n6_btrack_proposal_list", (self._session_hash(session_token_hash), max(1, min(int(limit), 500)))) or {"tables_ready": False, "items": []}

    def create_trade_proposal(self, session_token_hash: str, *, source_type: str, source_id: int) -> dict[str, Any]:
        return self._call_write("n6_btrack_proposal_create", (self._session_hash(session_token_hash), source_type, int(source_id)))

    def confirm_trade_proposal(self, session_token_hash: str, *, proposal_id: int, idempotency_key: str) -> dict[str, Any]:
        return self._call_write("n6_btrack_proposal_confirm", (self._session_hash(session_token_hash), int(proposal_id), idempotency_key))

    def cancel_trade_proposals(
        self,
        session_token_hash: str,
        *,
        proposal_ids: list[int],
    ) -> dict[str, Any]:
        return self._call_write(
            "n6_btrack_proposals_cancel",
            (self._session_hash(session_token_hash), list(proposal_ids)),
        )

    def list_virtual_trades(self, session_token_hash: str, *, limit: int) -> dict[str, Any]:
        return self._call_one("n6_btrack_virtual_trade_list", (self._session_hash(session_token_hash), max(1, min(int(limit), 500)))) or {"tables_ready": False, "items": []}

    def fetch_public_ai_agent_dashboard(
        self,
        session_token_hash: str,
        *,
        decision_limit: int,
        trade_limit: int,
        summary_limit: int,
    ) -> dict[str, Any] | None:
        return self._call_one(
            "n6_btrack_ai_public_snapshot",
            (
                self._session_hash(session_token_hash),
                max(1, min(int(decision_limit), 200)),
                max(1, min(int(trade_limit), 200)),
                max(1, min(int(summary_limit), 200)),
            ),
        )

    def fetch_public_ai_decision_detail(
        self,
        session_token_hash: str,
        *,
        decision_id: int,
    ) -> dict[str, Any] | None:
        if isinstance(decision_id, bool):
            raise ValueError("invalid_ai_decision_id")
        normalized_decision_id = int(decision_id)
        if normalized_decision_id < 1 or normalized_decision_id > 9223372036854775807:
            raise ValueError("invalid_ai_decision_id")
        return self._call_one(
            "n6_btrack_ai_public_decision_detail",
            (
                self._session_hash(session_token_hash),
                normalized_decision_id,
            ),
        )
