"""Guarded N6 human virtual-account provisioning runner support."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Iterable
from typing import Any

import psycopg
from psycopg.rows import dict_row


RUN_ID = "n6_human_virtual_account_provisioning_074_v1"
INITIAL_CASH = "100000000.0000"
BACKFILL_TARGETS = {8: "csl666", 9: "csl888"}
PROVISION_SQL = "SELECT public.n6_provision_human_virtual_account(%s) AS result"


class ProvisioningGateError(RuntimeError):
    """Raised when a provisioning request fails closed."""


def _normalize_targets(principal_ids: Iterable[int] | None) -> tuple[int, ...]:
    source = BACKFILL_TARGETS if principal_ids is None else principal_ids
    values = tuple(sorted({int(value) for value in source}))
    if not values or any(value <= 0 for value in values):
        raise ProvisioningGateError("invalid_principal_allowlist")
    return values


def _inspect(cur: Any, principal_id: int) -> dict[str, Any]:
    cur.execute(
        """
        SELECT p.principal_id,
               p.principal_type,
               p.principal_status,
               u.user_id,
               u.login_name,
               u.role,
               u.status AS user_status,
               (SELECT count(*) FROM public.n6_virtual_account a
                 WHERE a.principal_id = p.principal_id)::int AS account_count,
               (SELECT count(*) FROM public.n6_principal_account m
                 WHERE m.principal_id = p.principal_id)::int AS mapping_count,
               (SELECT count(*) FROM public.n6_virtual_cash_ledger l
                 JOIN public.n6_virtual_account a
                   ON a.virtual_account_id = l.virtual_account_id
                 WHERE a.principal_id = p.principal_id)::int AS ledger_count,
               (SELECT count(*) FROM public.n6_virtual_cash_snapshot s
                 JOIN public.n6_virtual_account a
                   ON a.virtual_account_id = s.virtual_account_id
                 WHERE a.principal_id = p.principal_id)::int AS snapshot_count,
               (SELECT count(*)
                  FROM public.n6_virtual_account a
                  JOIN public.n6_principal_account m
                    ON m.principal_id = p.principal_id
                   AND m.virtual_account_id = a.virtual_account_id
                   AND m.account_type = 'virtual'
                   AND m.virtual_account_source = 'future_virtual_account'
                   AND m.account_status = 'active'
                  JOIN public.n6_virtual_cash_snapshot current_snapshot
                    ON current_snapshot.cash_snapshot_id = a.current_cash_snapshot_id
                   AND current_snapshot.virtual_account_id = a.virtual_account_id
                   AND current_snapshot.snapshot_status = 'active'
                 WHERE a.principal_id = p.principal_id
                   AND a.principal_type = 'human_user'
                   AND a.virtual_account_status = 'active'
                   AND a.base_currency = 'CNY'
                   AND a.initial_cash = 100000000.0000
                   AND EXISTS (
                     SELECT 1
                     FROM public.n6_virtual_cash_ledger initial_ledger
                     JOIN public.n6_virtual_cash_snapshot initial_snapshot
                       ON initial_snapshot.virtual_account_id = initial_ledger.virtual_account_id
                      AND initial_snapshot.source_ledger_max_id = initial_ledger.cash_ledger_id
                      AND initial_snapshot.available_cash = 100000000.0000
                      AND initial_snapshot.frozen_cash = 0.0000
                      AND initial_snapshot.total_cash = 100000000.0000
                      AND initial_snapshot.currency = 'CNY'
                     WHERE initial_ledger.virtual_account_id = a.virtual_account_id
                       AND initial_ledger.ledger_type = 'initial_deposit'
                       AND initial_ledger.amount = 100000000.0000
                       AND initial_ledger.currency = 'CNY'
                   ))::int AS complete_chain_count
        FROM public.n6_principal p
        JOIN public.user_account u ON u.user_id = p.owner_user_id
        WHERE p.principal_id = %s
        """,
        (principal_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise ProvisioningGateError(f"principal_not_found:{principal_id}")
    result = dict(row)
    expected_login = BACKFILL_TARGETS.get(principal_id)
    if (
        expected_login is None
        or result["login_name"] != expected_login
        or result["principal_type"] != "human_user"
        or result["principal_status"] != "active"
        or result["role"] != "user"
        or result["user_status"] != "active"
    ):
        raise ProvisioningGateError(f"principal_identity_drift:{principal_id}")
    counts = tuple(result[key] for key in ("account_count", "mapping_count", "ledger_count", "snapshot_count"))
    if counts == (0, 0, 0, 0):
        result["decision"] = "create"
    elif counts[0:2] == (1, 1) and all(value >= 1 for value in counts[2:]) and result["complete_chain_count"] == 1:
        result["decision"] = "verify_or_noop"
    else:
        raise ProvisioningGateError(f"partial_account_chain:{principal_id}")
    return result


def run_provisioning_once(
    *,
    service: str,
    principal_ids: Iterable[int] | None = None,
    execute: bool = False,
    execute_authorized: bool = False,
    connect: Callable[..., Any] = psycopg.connect,
) -> dict[str, Any]:
    """Inspect or atomically provision the fixed 074 backfill allowlist."""

    provided_targets = None if principal_ids is None else tuple(principal_ids)
    targets = _normalize_targets(provided_targets)
    if execute and (
        provided_targets is None
        or not execute_authorized
        or set(targets) != set(BACKFILL_TARGETS)
    ):
        raise ProvisioningGateError("execute_not_authorized_for_exact_allowlist")

    options = "-c default_transaction_read_only=off" if execute else "-c default_transaction_read_only=on"
    with connect(service=service, connect_timeout=10, row_factory=dict_row, options=options) as conn:
        with conn.transaction(), conn.cursor() as cur:
            if not execute:
                cur.execute("SET TRANSACTION READ ONLY")
            inspections = [_inspect(cur, principal_id) for principal_id in targets]
            results: list[dict[str, Any]] = []
            if execute:
                for principal_id in targets:
                    cur.execute(PROVISION_SQL, (principal_id,))
                    row = cur.fetchone()
                    result = dict(row or {}).get("result")
                    if not isinstance(result, dict) or result.get("ok") is not True:
                        raise ProvisioningGateError(f"invalid_function_result:{principal_id}")
                    if result.get("status") not in {"created", "noop"}:
                        raise ProvisioningGateError(f"unexpected_function_status:{principal_id}")
                    results.append(result)

    return {
        "ok": True,
        "mode": "execute" if execute else "dry_run",
        "run_id": RUN_ID,
        "initial_cash": INITIAL_CASH,
        "targets": inspections,
        "results": results,
        "execute_authorized": bool(execute and execute_authorized),
        "proposal_order_trade_position_lot_outbox_writes": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", default="ashare_v3_owner")
    parser.add_argument("--principal-id", type=int, action="append")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--execute-authorized", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = run_provisioning_once(
            service=args.service,
            principal_ids=args.principal_id,
            execute=args.execute,
            execute_authorized=args.execute_authorized,
        )
    except (ProvisioningGateError, psycopg.Error) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
