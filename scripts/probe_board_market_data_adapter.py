#!/usr/bin/env python3
"""Probe TDX board realtime snapshot paths without writing database rows."""

from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Callable
from typing import Any

import pandas as pd
import psycopg

from ashare_v3.market.realtime_snapshot_execute import build_default_mootdx_endpoint_probe
from ashare_v3.market.query_audit_phase3 import audited_n3_market_readonly_plan_connect
from ashare_v3.mootdx_client import EndpointSelection, MootdxEndpointManager
from ashare_v3.quote_transport import create_quote_transport, resolve_quote_transport_name

try:
    from check_condition_source_ready import DEFAULT_DSN
except ModuleNotFoundError:  # pragma: no cover
    from scripts.check_condition_source_ready import DEFAULT_DSN


DEFAULT_RUN_ID = "market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute"
DIAGNOSTIC_ONLY = True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe board:TDX:881xxx realtime quote paths.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--timeout", type=int, default=5)
    parser.add_argument("--include-ext", action="store_true", help="Also probe ext quote paths for the first code.")
    parser.add_argument("--diagnostic-only-confirmed", action="store_true")
    return parser.parse_args()


def fetch_board_samples(dsn: str, run_id: str, limit: int) -> list[dict[str, Any]]:
    with audited_n3_market_readonly_plan_connect(
        dsn,
        stage_id="n3_board_market_data_adapter_probe",
        source_run_id=run_id,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT subscription_id, identity_key, exchange, code, display_code, name
                FROM common_market_data_subscription
                WHERE run_id = %s
                  AND asset_kind = 'board'
                  AND required_data_kind = 'realtime_daily_snapshot'
                ORDER BY code
                LIMIT %s
                """,
                (run_id, limit),
            )
            columns = ("subscription_id", "identity_key", "exchange", "code", "display_code", "name")
            return [dict(zip(columns, row)) for row in cur.fetchall()]


def summarize_frame(value: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"type": type(value).__name__}
    if isinstance(value, pd.DataFrame):
        result["rows"] = int(len(value))
        result["columns"] = [str(column) for column in value.columns.tolist()]
        if len(value):
            result["head_row"] = {str(key): str(val) for key, val in value.head(1).to_dict("records")[0].items()}
            result["tail_row"] = {str(key): str(val) for key, val in value.tail(1).to_dict("records")[0].items()}
            result["snapshot_mappable"] = all(
                column in value.columns for column in ("open", "close", "high", "low", "amount")
            )
    else:
        result["repr"] = str(value)[:500]
    return result


def run_call(name: str, fn: Callable[[], Any]) -> dict[str, Any]:
    started = time.time()
    try:
        value = fn()
    except Exception as exc:  # noqa: BLE001 - probe records every failure path.
        return {
            "path": name,
            "ok": False,
            "elapsed_sec": round(time.time() - started, 3),
            "error": f"{type(exc).__name__}: {exc}",
        }
    return {
        "path": name,
        "ok": True,
        "elapsed_sec": round(time.time() - started, 3),
        **summarize_frame(value),
    }


def probe_std_paths(
    samples: list[dict[str, Any]],
    selection: EndpointSelection,
    client_factory: Callable[[EndpointSelection, str], Any] | None = None,
) -> list[dict[str, Any]]:
    client_factory = client_factory or _selection_transport_factory
    client = client_factory(selection, "std")
    try:
        results: list[dict[str, Any]] = []
        for sample in samples:
            code = str(sample["code"])
            results.append(run_call(f"std.quotes {code}", lambda code=code: client.quotes(symbol=code)))
            results.append(
                run_call(
                    f"std.index frequency=9 {code}",
                    lambda code=code: client.index(symbol=code, frequency=9, start=0, offset=5),
                )
            )
            results.append(
                run_call(
                    f"std.index_bars frequency=9 {code}",
                    lambda code=code: client.index_bars(symbol=code, frequency=9, start=0, offset=5),
                )
            )
            results.append(run_call(f"std.bars frequency=9 {code}", lambda code=code: client.bars(symbol=code, frequency=9, start=0, offset=5)))
            results.append(run_call(f"std.minute {code}", lambda code=code: client.minute(symbol=code)))
        codes = [str(sample["code"]) for sample in samples]
        results.append(run_call("std.quotes board batch", lambda: client.quotes(symbol=codes)))
        return results
    finally:
        client.close()


def probe_ext_paths(
    first_code: str,
    selection: EndpointSelection,
    client_factory: Callable[[EndpointSelection, str], Any] | None = None,
) -> list[dict[str, Any]]:
    client_factory = client_factory or _selection_transport_factory
    if str(getattr(selection, "transport", "") or "") == "tdxpy":
        return [
            {
                "path": "ext.transport_profile",
                "ok": False,
                "transport": "tdxpy",
                "capability_reason": "transport_profile_unsupported",
                "error": "tdxpy transport supports only the std quote profile",
            }
        ]
    client = client_factory(selection, "ext")
    try:
        results = [run_call("ext.markets", lambda: client.markets())]
        for market in (31, 47, 48, 27, 1):
            results.append(run_call(f"ext.quote market={market} {first_code}", lambda market=market: client.quote(market=market, symbol=first_code)))
        return results
    finally:
        client.close()


def recommended_board_probe_path(selection: EndpointSelection) -> str:
    return (
        "diagnostic-only manager-selected pinned "
        f"{selection.transport} transport index frequency=9"
    )


def main() -> int:
    args = parse_args()
    if not args.diagnostic_only_confirmed:
        print(json.dumps({
            "status": "PROBE_BLOCKED",
            "diagnostic_only": DIAGNOSTIC_ONLY,
            "blocked_reason": "requires --diagnostic-only-confirmed",
        }, ensure_ascii=False, indent=2))
        return 2
    samples = fetch_board_samples(args.dsn, args.run_id, args.limit)
    result: dict[str, Any] = {
        "stage": "N3-B1 BoardMarketDataAdapter probe",
        "layer_role": "N3_market_data",
        "run_id": args.run_id,
        "sample_count": len(samples),
        "samples": samples,
        "business_data_written": False,
        "realtime_snapshot_written": False,
        "event_outbox_written": False,
        "worker_started": False,
        "std_probe_results": [],
        "ext_probe_results": [],
    }
    if not samples:
        result["status"] = "PROBE_BLOCKED"
        result["blocked_reason"] = "no board realtime_daily_snapshot subscriptions found"
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 2

    manager = MootdxEndpointManager.from_toml()
    resolved_transport = resolve_quote_transport_name()

    def transport_factory(selection: EndpointSelection, profile: str) -> Any:
        return create_quote_transport(
            selection,
            profile,
            transport=resolved_transport,
        )

    selection = manager.select_for_batch(
        batch_id=f"diagnostic_board_probe:{args.run_id}",
        probe=build_default_mootdx_endpoint_probe(
            [{**sample, "asset_kind": "board"} for sample in samples]
        ),
        transport=resolved_transport,
        client_factory=transport_factory,
    )
    if not selection.selectable:
        result["status"] = "PROBE_BLOCKED"
        result["blocked_reason"] = "endpoint manager selection failed closed"
        result["endpoint_selection"] = selection.to_provenance()
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 2
    result["endpoint_selection"] = selection.to_provenance()
    result["actual_transport"] = selection.transport
    result["std_probe_results"] = probe_std_paths(samples, selection, transport_factory)
    if args.include_ext:
        result["ext_probe_results"] = probe_ext_paths(
            str(samples[0]["code"]),
            selection,
            transport_factory,
        )

    std_index_ok = [
        row
        for row in result["std_probe_results"]
        if row["path"].startswith("std.index frequency=9")
        and row.get("ok")
        and int(row.get("rows") or 0) > 0
        and row.get("snapshot_mappable")
    ]
    ext_failures = [
        row
        for row in result["ext_probe_results"]
        if not row.get("ok")
    ]
    result["capability_reasons"] = sorted(
        {
            str(row.get("capability_reason"))
            for row in ext_failures
            if row.get("capability_reason")
        }
    )
    result["status"] = (
        "PROBE_PASS"
        if len(std_index_ok) == len(samples) and not ext_failures
        else "PROBE_BLOCKED"
    )
    result["recommended_path"] = recommended_board_probe_path(selection)
    result["field_mapping"] = {
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "current_price": "close",
        "volume": "vol or volume",
        "amount": "amount",
        "snapshot_time": "datetime tail row",
        "extra": "up_count/down_count can remain in raw_json",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result["status"] == "PROBE_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())


def _selection_transport_factory(selection: EndpointSelection, profile: str) -> Any:
    return create_quote_transport(
        selection,
        profile,
        transport=selection.transport,
    )
