"""N6-owned, one-shot persistence for virtual-position stock quotes."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
import json
from typing import Any, Protocol

import psycopg
from psycopg.rows import dict_row

from ashare_v3.n3n6q import QuoteBatch, QuoteIdentity


MAX_PROVIDER_BATCH_SIZE = 80
ALLOWED_PRINCIPAL_TYPES = frozenset({"admin", "human_user", "ai_user"})
LATEST_QUOTE_COLUMNS = (
    "virtual_quote_snapshot_id",
    "identity_key",
    "exchange",
    "stock_code",
    "quote_minute",
    "provider_batch_id",
    "provider_contract_version",
    "source_adapter",
    "source_version",
    "source_time_semantics",
    "requested_at",
    "completed_at",
    "batch_status",
    "market",
    "current_price",
    "last_close",
    "day_open",
    "day_high",
    "day_low",
    "source_time_text",
    "fetched_at",
    "quality_status",
    "quality_reason",
    "created_at",
)


class VirtualQuoteProvider(Protocol):
    def fetch_quotes(self, identities: Sequence[QuoteIdentity]) -> QuoteBatch:
        ...


class VirtualQuoteRepository(Protocol):
    def list_active_principal_stock_scopes(
        self, *, quote_minute: datetime
    ) -> dict[tuple[int, str], Sequence[QuoteIdentity]]:
        ...

    def list_open_stock_identities(
        self, *, principal_id: int, principal_type: str
    ) -> Sequence[QuoteIdentity]:
        ...

    def save_quote_run_and_batches(
        self,
        *,
        principal_id: int,
        principal_type: str,
        quote_minute: datetime,
        run_status: str,
        scoped_identity_count: int,
        passed_count: int,
        not_ready_count: int,
        started_at: datetime,
        completed_at: datetime,
        batches: Sequence[QuoteBatch],
        scope_identity_keys: Sequence[str] | None = None,
    ) -> int:
        ...

    def fetch_latest_for_principal(
        self, *, principal_id: int, principal_type: str
    ) -> list[dict[str, Any]]:
        ...


@dataclass(frozen=True, slots=True)
class VirtualQuoteRunResult:
    status: str
    principal_id: int
    principal_type: str
    quote_minute: str
    requested_count: int
    batch_count: int
    passed_count: int
    not_ready_count: int
    inserted_count: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class MultiPrincipalVirtualQuoteRunResult:
    status: str
    quote_minute: str
    principal_count: int
    unique_identity_count: int
    provider_batch_count: int
    results: tuple[VirtualQuoteRunResult, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "quote_minute": self.quote_minute,
            "principal_count": self.principal_count,
            "unique_identity_count": self.unique_identity_count,
            "provider_batch_count": self.provider_batch_count,
            "results": [result.to_dict() for result in self.results],
        }


class PostgresVirtualQuoteRepository:
    """The only database boundary; it reads and writes N6-owned objects only."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def list_open_stock_identities(
        self, *, principal_id: int, principal_type: str
    ) -> tuple[QuoteIdentity, ...]:
        _validate_principal(principal_id, principal_type)
        with psycopg.connect(
            self._dsn,
            connect_timeout=10,
            options="-c default_transaction_read_only=on",
            row_factory=dict_row,
        ) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT p.identity_key
                FROM n6_virtual_position p
                JOIN n6_virtual_account a
                  ON a.virtual_account_id = p.virtual_account_id
                 AND a.principal_id = p.principal_id
                 AND a.principal_type = p.principal_type
                 AND a.virtual_account_status = 'active'
                WHERE p.principal_id = %s
                  AND p.principal_type = %s
                  AND p.asset_kind = 'stock'
                  AND p.position_status = 'open_virtual'
                  AND p.quantity > 0
                ORDER BY p.identity_key
                """,
                (principal_id, principal_type),
            )
            return tuple(_identity_from_key(str(row["identity_key"])) for row in cur.fetchall())

    def list_active_principal_stock_scopes(
        self, *, quote_minute: datetime
    ) -> dict[tuple[int, str], tuple[QuoteIdentity, ...]]:
        _validate_quote_minute(quote_minute)
        with psycopg.connect(
            self._dsn,
            connect_timeout=10,
            options="-c default_transaction_read_only=on",
            row_factory=dict_row,
        ) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT principal_id, principal_type, identity_key
                FROM public.n6_quote_writer_pending_scope(%s)
                ORDER BY principal_id, principal_type, identity_key
                """,
                (quote_minute,),
            )
            scopes: dict[tuple[int, str], dict[str, QuoteIdentity]] = {}
            for row in cur.fetchall():
                key = (int(row["principal_id"]), str(row["principal_type"]))
                identity = _identity_from_key(str(row["identity_key"]))
                scopes.setdefault(key, {})[identity.identity_key] = identity
        return {key: tuple(items.values()) for key, items in scopes.items()}

    def save_quote_run_and_batches(
        self,
        *,
        principal_id: int,
        principal_type: str,
        quote_minute: datetime,
        run_status: str,
        scoped_identity_count: int,
        passed_count: int,
        not_ready_count: int,
        started_at: datetime,
        completed_at: datetime,
        batches: Sequence[QuoteBatch],
        scope_identity_keys: Sequence[str] | None = None,
    ) -> int:
        _validate_run_record(
            principal_id=principal_id,
            quote_minute=quote_minute,
            run_status=run_status,
            scoped_identity_count=scoped_identity_count,
            passed_count=passed_count,
            not_ready_count=not_ready_count,
            started_at=started_at,
            completed_at=completed_at,
        )
        _validate_principal(principal_id, principal_type)
        _validate_quote_minute(quote_minute)
        payload = json.dumps(
            [batch.to_dict() for batch in batches],
            ensure_ascii=True,
            separators=(",", ":"),
        )
        scope_payload = json.dumps(
            list(scope_identity_keys or ()),
            ensure_ascii=True,
            separators=(",", ":"),
        )
        with psycopg.connect(self._dsn, connect_timeout=10, row_factory=dict_row) as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT public.n6_quote_writer_save_run(
                      %s, %s, %s, %s, %s, %s, %s, %s, %s,
                      %s::jsonb, %s::jsonb
                    ) AS inserted_snapshot_count
                    """,
                    (
                        principal_id,
                        principal_type,
                        quote_minute,
                        run_status,
                        scoped_identity_count,
                        passed_count,
                        not_ready_count,
                        started_at,
                        completed_at,
                        scope_payload,
                        payload,
                    ),
                )
                row = cur.fetchone()
        if row is None:
            raise RuntimeError("quote writer persistence returned no result")
        return int(row["inserted_snapshot_count"])

    def fetch_latest_for_principal(
        self, *, principal_id: int, principal_type: str
    ) -> list[dict[str, Any]]:
        _validate_principal(principal_id, principal_type)
        with psycopg.connect(
            self._dsn,
            connect_timeout=10,
            options="-c default_transaction_read_only=on",
            row_factory=dict_row,
        ) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT q.virtual_quote_snapshot_id,
                       q.identity_key,
                       q.exchange,
                       q.stock_code,
                       q.quote_minute,
                       q.provider_batch_id,
                       q.provider_contract_version,
                       q.source_adapter,
                       q.source_version,
                       q.source_time_semantics,
                       q.requested_at,
                       q.completed_at,
                       q.batch_status,
                       q.market,
                       q.current_price,
                       q.last_close,
                       q.day_open,
                       q.day_high,
                       q.day_low,
                       q.source_time_text,
                       q.fetched_at,
                       q.quality_status,
                       q.quality_reason,
                       q.created_at
                FROM v_n6_virtual_quote_latest q
                WHERE EXISTS (
                  SELECT 1
                  FROM n6_virtual_position p
                  JOIN n6_virtual_account a
                    ON a.virtual_account_id = p.virtual_account_id
                   AND a.principal_id = p.principal_id
                   AND a.principal_type = p.principal_type
                   AND a.virtual_account_status = 'active'
                  WHERE p.principal_id = %s
                    AND p.principal_type = %s
                    AND p.asset_kind = 'stock'
                    AND p.position_status = 'open_virtual'
                    AND p.quantity > 0
                    AND p.identity_key = q.identity_key
                )
                ORDER BY q.identity_key
                """,
                (principal_id, principal_type),
            )
            return [dict(row) for row in cur.fetchall()]


def run_virtual_quote_once(
    *,
    repository: VirtualQuoteRepository,
    provider: VirtualQuoteProvider,
    principal_id: int,
    principal_type: str,
    quote_minute: datetime,
    clock: Callable[[], datetime] | None = None,
) -> VirtualQuoteRunResult:
    """Fetch and atomically persist one N6 quote minute without fallbacks."""

    _validate_principal(principal_id, principal_type)
    _validate_quote_minute(quote_minute)
    now = clock or (lambda: datetime.now().astimezone())
    started_at = _aware_now(now)
    raw_identities = repository.list_open_stock_identities(
        principal_id=principal_id,
        principal_type=principal_type,
    )
    identities = _deduplicate_identities(raw_identities)
    if not identities:
        completed_at = _aware_now(now)
        inserted_count = repository.save_quote_run_and_batches(
            principal_id=principal_id,
            principal_type=principal_type,
            quote_minute=quote_minute,
            run_status="no_scope",
            scoped_identity_count=0,
            passed_count=0,
            not_ready_count=0,
            started_at=started_at,
            completed_at=completed_at,
            batches=(),
            scope_identity_keys=(),
        )
        return VirtualQuoteRunResult(
            status="no_scope",
            principal_id=principal_id,
            principal_type=principal_type,
            quote_minute=quote_minute.isoformat(),
            requested_count=0,
            batch_count=0,
            passed_count=0,
            not_ready_count=0,
            inserted_count=inserted_count,
        )

    batches = tuple(
        provider.fetch_quotes(identities[offset : offset + MAX_PROVIDER_BATCH_SIZE])
        for offset in range(0, len(identities), MAX_PROVIDER_BATCH_SIZE)
    )
    _revalidate_batches(identities, batches)
    passed_count = sum(
        item.quality_status == "passed" for batch in batches for item in batch.items
    )
    requested_count = len(identities)
    if passed_count == requested_count:
        status = "passed"
    elif passed_count == 0:
        status = "failed"
    else:
        status = "partial"
    completed_at = _aware_now(now)
    inserted_count = repository.save_quote_run_and_batches(
        principal_id=principal_id,
        principal_type=principal_type,
        quote_minute=quote_minute,
        run_status=status,
        scoped_identity_count=requested_count,
        passed_count=passed_count,
        not_ready_count=requested_count - passed_count,
        started_at=started_at,
        completed_at=completed_at,
        batches=batches,
        scope_identity_keys=tuple(
            identity.identity_key for identity in identities
        ),
    )
    return VirtualQuoteRunResult(
        status=status,
        principal_id=principal_id,
        principal_type=principal_type,
        quote_minute=quote_minute.isoformat(),
        requested_count=requested_count,
        batch_count=len(batches),
        passed_count=passed_count,
        not_ready_count=requested_count - passed_count,
        inserted_count=inserted_count,
    )


def run_virtual_quote_all_active_accounts_once(
    *,
    repository: VirtualQuoteRepository,
    provider: VirtualQuoteProvider,
    quote_minute: datetime,
    clock: Callable[[], datetime] | None = None,
) -> MultiPrincipalVirtualQuoteRunResult:
    """Fetch each scoped identity once, then persist principal-scoped run evidence."""

    _validate_quote_minute(quote_minute)
    now = clock or (lambda: datetime.now().astimezone())
    started_at = _aware_now(now)
    raw_scopes = repository.list_active_principal_stock_scopes(
        quote_minute=quote_minute
    )
    scopes = {
        (int(principal_id), str(principal_type)): _deduplicate_identities(tuple(identities))
        for (principal_id, principal_type), identities in raw_scopes.items()
    }
    for principal_id, principal_type in scopes:
        _validate_principal(principal_id, principal_type)
        if principal_type == "ai_user":
            raise ValueError("ai_user virtual quote scope is not supported in V3")
    global_identities = _deduplicate_identities(
        tuple(identity for identities in scopes.values() for identity in identities)
    )
    if not global_identities:
        return MultiPrincipalVirtualQuoteRunResult(
            status="no_scope",
            quote_minute=quote_minute.isoformat(),
            principal_count=0,
            unique_identity_count=0,
            provider_batch_count=0,
            results=(),
        )
    identity_by_key = {
        identity.identity_key: identity for identity in global_identities
    }
    memberships: dict[str, set[tuple[int, str]]] = {
        identity.identity_key: set() for identity in global_identities
    }
    for principal, identities in scopes.items():
        for identity in identities:
            memberships[identity.identity_key].add(principal)
    membership_groups: dict[
        frozenset[tuple[int, str]], list[QuoteIdentity]
    ] = {}
    for identity_key, principals in memberships.items():
        membership_groups.setdefault(frozenset(principals), []).append(
            identity_by_key[identity_key]
        )
    principal_batches: dict[tuple[int, str], list[QuoteBatch]] = {
        principal: [] for principal in scopes
    }
    global_batch_list: list[QuoteBatch] = []
    for principal_group, grouped_identities in sorted(
        membership_groups.items(),
        key=lambda item: tuple(sorted(item[0])),
    ):
        ordered_identities = tuple(
            sorted(grouped_identities, key=lambda item: item.identity_key)
        )
        for offset in range(0, len(ordered_identities), MAX_PROVIDER_BATCH_SIZE):
            batch = provider.fetch_quotes(
                ordered_identities[offset : offset + MAX_PROVIDER_BATCH_SIZE]
            )
            global_batch_list.append(batch)
            for principal in principal_group:
                principal_batches[principal].append(batch)
    global_batches = tuple(global_batch_list)
    _revalidate_batches(global_identities, global_batches)
    completed_at = _aware_now(now)
    results: list[VirtualQuoteRunResult] = []
    for (principal_id, principal_type), identities in sorted(scopes.items()):
        identity_keys = {identity.identity_key for identity in identities}
        scoped_batches = tuple(principal_batches[(principal_id, principal_type)])
        passed_count = sum(
            item.quality_status == "passed" for batch in scoped_batches for item in batch.items
        )
        requested_count = len(identities)
        status = (
            "passed"
            if passed_count == requested_count
            else "failed"
            if passed_count == 0
            else "partial"
        )
        inserted_count = repository.save_quote_run_and_batches(
            principal_id=principal_id,
            principal_type=principal_type,
            quote_minute=quote_minute,
            run_status=status,
            scoped_identity_count=requested_count,
            passed_count=passed_count,
            not_ready_count=requested_count - passed_count,
            started_at=started_at,
            completed_at=completed_at,
            batches=scoped_batches,
            scope_identity_keys=tuple(sorted(identity_keys)),
        )
        results.append(
            VirtualQuoteRunResult(
                status=status,
                principal_id=principal_id,
                principal_type=principal_type,
                quote_minute=quote_minute.isoformat(),
                requested_count=requested_count,
                batch_count=len(scoped_batches),
                passed_count=passed_count,
                not_ready_count=requested_count - passed_count,
                inserted_count=inserted_count,
            )
        )
    aggregate_status = (
        "passed"
        if all(result.status == "passed" for result in results)
        else "failed"
        if all(result.status == "failed" for result in results)
        else "partial"
    )
    return MultiPrincipalVirtualQuoteRunResult(
        status=aggregate_status,
        quote_minute=quote_minute.isoformat(),
        principal_count=len(results),
        unique_identity_count=len(global_identities),
        provider_batch_count=len(global_batches),
        results=tuple(results),
    )


def _identity_from_key(identity_key: str) -> QuoteIdentity:
    parts = identity_key.split(":")
    if len(parts) != 3:
        raise ValueError("invalid N6 stock identity_key")
    _, exchange, stock_code = parts
    return QuoteIdentity(
        identity_key=identity_key,
        exchange=exchange,  # type: ignore[arg-type]
        stock_code=stock_code,
    )


def _deduplicate_identities(
    identities: Sequence[QuoteIdentity],
) -> tuple[QuoteIdentity, ...]:
    unique: dict[str, QuoteIdentity] = {}
    for identity in identities:
        validated = QuoteIdentity(
            identity_key=identity.identity_key,
            exchange=identity.exchange,
            stock_code=identity.stock_code,
        )
        previous = unique.setdefault(validated.identity_key, validated)
        if previous != validated:
            raise ValueError("conflicting duplicate identity_key")
    return tuple(unique.values())


def _revalidate_batches(
    identities: tuple[QuoteIdentity, ...], batches: tuple[QuoteBatch, ...]
) -> None:
    requested = [
        (identity.identity_key, identity.exchange, identity.stock_code)
        for identity in identities
    ]
    returned = [
        (item.identity_key, item.exchange, item.stock_code)
        for batch in batches
        for item in batch.items
    ]
    if len(returned) != len(set(returned)) or sorted(returned) != sorted(requested):
        raise ValueError("provider response identity set mismatch")
    for batch in batches:
        if batch.contract_version != "1.0.0" or batch.source_adapter != "mootdx.std":
            raise ValueError("provider response contract mismatch")
        if batch.item_count != len(batch.items):
            raise ValueError("provider response item_count mismatch")


def _validate_principal(principal_id: int, principal_type: str) -> None:
    if isinstance(principal_id, bool) or principal_id <= 0:
        raise ValueError("principal_id must be a positive integer")
    if principal_type not in ALLOWED_PRINCIPAL_TYPES:
        raise ValueError("unsupported principal_type")


def _validate_quote_minute(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("quote_minute must be timezone-aware")
    if value.second != 0 or value.microsecond != 0:
        raise ValueError("quote_minute must be minute-aligned")


def _validate_run_record(
    *,
    principal_id: int,
    quote_minute: datetime,
    run_status: str,
    scoped_identity_count: int,
    passed_count: int,
    not_ready_count: int,
    started_at: datetime,
    completed_at: datetime,
) -> None:
    if isinstance(principal_id, bool) or principal_id <= 0:
        raise ValueError("principal_id must be a positive integer")
    _validate_quote_minute(quote_minute)
    if run_status not in {"no_scope", "passed", "partial", "failed"}:
        raise ValueError("invalid run_status")
    counts = (scoped_identity_count, passed_count, not_ready_count)
    if any(isinstance(value, bool) or value < 0 for value in counts):
        raise ValueError("run counts must be non-negative integers")
    if scoped_identity_count != passed_count + not_ready_count:
        raise ValueError("run counts do not balance")
    _validate_aware_datetime(started_at, "started_at")
    _validate_aware_datetime(completed_at, "completed_at")
    if completed_at < started_at:
        raise ValueError("completed_at precedes started_at")


def _aware_now(clock: Callable[[], datetime]) -> datetime:
    value = clock()
    _validate_aware_datetime(value, "clock")
    return value


def _validate_aware_datetime(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
