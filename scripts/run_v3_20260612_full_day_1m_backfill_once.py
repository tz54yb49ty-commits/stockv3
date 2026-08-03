#!/usr/bin/env python3
"""Execute V3-only 20260612 full-day N3 1m backfill once.

This runner never reads the old target-machine database.  It builds a new
scoped N3 market-data run from V3 retained minute facts where complete, and
from the approved N3 mootdx 1m adapter for missing/partial context objects.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path
from collections.abc import Callable
from typing import Any, Mapping, Sequence

from ashare_v3.market.mootdx_batch_attempt import (
    MootdxBatchObjectTracker,
    build_mootdx_minute_semantic_probe,
    run_mootdx_batch_attempt,
)
from ashare_v3.market.today_minute_execute import MootdxTodayMinuteAdapter
from ashare_v3.market import v3_full_day_replay_plan as plan
from ashare_v3.mootdx_client import EndpointSelection, MootdxEndpointManager

try:
    from check_condition_source_ready import DEFAULT_DSN
except ModuleNotFoundError:  # pragma: no cover
    from scripts.check_condition_source_ready import DEFAULT_DSN


DEFAULT_REPORT_JSON = "docs/V3_20260612_N3_FULL_DAY_1M_BACKFILL_EXECUTE_REPORT.json"
DEFAULT_REPORT_MD = "docs/V3_20260612_N3_FULL_DAY_1M_BACKFILL_EXECUTE_REPORT.md"
MINUTE_PROBE_REQUIRED_CHECKS = ("minute_scope_sentinels",)


def winning_transport_provenance(
    fetch_results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    for row in fetch_results:
        batch = row.get("endpoint_attempt")
        if not isinstance(batch, Mapping):
            continue
        winning_attempt_id = str(batch.get("winning_attempt_id") or "")
        winning = next(
            (
                dict(attempt)
                for attempt in batch.get("attempts") or []
                if str(attempt.get("attempt_id") or "") == winning_attempt_id
            ),
            None,
        )
        if winning is None:
            continue
        return {
            "batch_id": batch.get("batch_id"),
            "winning_attempt_id": winning_attempt_id,
            "attempt_id": winning.get("attempt_id"),
            "endpoint_pool_version": winning.get("endpoint_pool_version"),
            "endpoint_id": winning.get("endpoint_id"),
            "endpoint_host": winning.get("endpoint_host"),
            "endpoint_port": winning.get("endpoint_port"),
            "transport": winning.get("transport"),
            "source_transport": winning.get("source_transport") or winning.get("transport"),
            "pool_probe_summary": winning.get("pool_probe_summary"),
            "endpoint_probe_results": winning.get("endpoint_probe_results"),
        }
    return {}


def _identity_groups(context_rows: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {asset: [] for asset in plan.ASSET_CONFIG}
    seen: set[str] = set()
    for row in context_rows:
        identity = str(row["identity_key"])
        if identity in seen:
            continue
        seen.add(identity)
        grouped.setdefault(str(row["asset_kind"]), []).append(identity)
    return grouped


def _dedupe_context_rows(context_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in context_rows:
        identity = str(row["identity_key"])
        if identity in seen:
            continue
        seen.add(identity)
        output.append(dict(row))
    return output


def build_adapter_rows(
    *,
    context_rows: Sequence[Mapping[str, Any]],
    retained_rows_by_identity: Mapping[str, Sequence[Mapping[str, Any]]],
    minute_trade_date: str,
    progress_every: int,
    endpoint_manager: MootdxEndpointManager | None = None,
    endpoint_probe: Callable[..., Mapping[str, Any]] | None = None,
    endpoint_client_factory: Callable[[EndpointSelection], Any] | None = None,
    adapter_factory: Callable[[Any], Any] | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    fetch_results: list[dict[str, Any]] = []
    unique_context = _dedupe_context_rows(context_rows)
    missing_context: list[dict[str, Any]] = []
    for row in unique_context:
        identity = str(row["identity_key"])
        retained_count = len(retained_rows_by_identity.get(identity) or [])
        if retained_count >= plan.FULL_DAY_EXPECTED_1M_BAR_COUNT:
            fetch_results.append(
                {
                    "asset_kind": row["asset_kind"],
                    "identity_key": identity,
                    "source": "retained_v3_minute_fact",
                    "row_count": retained_count,
                    "status": "skipped_fetch",
                }
            )
            continue
        missing_context.append(row)

    if not missing_context:
        return {}, fetch_results

    resolved_adapter_factory = adapter_factory or (
        lambda client: MootdxTodayMinuteAdapter(
            client=client,
            offset=800,
            intraday_trade_date=minute_trade_date,
        )
    )
    manager = endpoint_manager or MootdxEndpointManager.from_toml()

    def fetch_batch(client: Any, selection: EndpointSelection) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
        adapter = resolved_adapter_factory(client)
        tracker = MootdxBatchObjectTracker(manager, selection)
        adapter_rows: dict[str, list[dict[str, Any]]] = {}
        attempt_results: list[dict[str, Any]] = []
        total = len(missing_context)
        for index, row in enumerate(missing_context, start=1):
            identity = str(row["identity_key"])
            retained_count = len(retained_rows_by_identity.get(identity) or [])
            if index == 1 or index == total or index % max(progress_every, 1) == 0:
                print(f"full-day 1m adapter fetch {index}/{total} {row['asset_kind']} {identity}", flush=True)
            fetched = adapter.fetch_minute_bars(row, minute_trade_date)
            classified = tracker.record(identity_key=identity, value=fetched, empty=not fetched)
            adapter_rows[identity] = fetched
            status = "passed" if len(fetched) >= plan.FULL_DAY_EXPECTED_1M_BAR_COUNT else "missing"
            attempt_results.append(
                {
                    "asset_kind": row["asset_kind"],
                    "identity_key": identity,
                    "source": "mootdx_full_day_backfill",
                    "retained_row_count": retained_count,
                    "row_count": len(fetched),
                    "status": status,
                    "object_result_status": classified.status,
                }
            )
        return adapter_rows, attempt_results

    outcome = run_mootdx_batch_attempt(
        manager=manager,
        batch_id=f"full_day_1m_backfill:{minute_trade_date}",
        probe=endpoint_probe
        or build_mootdx_minute_semantic_probe(
            subscriptions=missing_context,
            trade_date=minute_trade_date,
            adapter_factory=resolved_adapter_factory,
        ),
        fetch_batch=fetch_batch,
        client_factory=endpoint_client_factory,
        required_checks=MINUTE_PROBE_REQUIRED_CHECKS,
    )
    if outcome.status != "passed" or outcome.result is None:
        for row in missing_context:
            fetch_results.append(
                {
                    "asset_kind": row["asset_kind"],
                    "identity_key": row["identity_key"],
                    "source": "mootdx_full_day_backfill",
                    "retained_row_count": len(retained_rows_by_identity.get(str(row["identity_key"])) or []),
                    "row_count": 0,
                    "status": "failed",
                    "endpoint_attempt": outcome.to_provenance(),
                }
            )
        return {}, fetch_results

    adapter_rows, attempt_results = outcome.result
    provenance = outcome.to_provenance()
    fetch_results.extend({**row, "endpoint_attempt": provenance} for row in attempt_results)
    return adapter_rows, fetch_results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--for-trade-date", default=plan.FOR_TRADE_DATE)
    parser.add_argument("--source-condition-run-id", default=plan.SOURCE_CONDITION_RUN_ID)
    parser.add_argument("--trigger-context-run-id", default=plan.TRIGGER_CONTEXT_RUN_ID)
    parser.add_argument("--backfill-run-id", default=plan.FULL_DAY_1M_BACKFILL_RUN_ID)
    parser.add_argument("--source-trade-date", default="20260611")
    parser.add_argument("--prev-trade-date", default="20260611")
    parser.add_argument("--minute-trade-date", default=None)
    parser.add_argument("--previous-day-preload", action="store_true")
    parser.add_argument("--json-report-path", default=DEFAULT_REPORT_JSON)
    parser.add_argument("--markdown-report-path", default=DEFAULT_REPORT_MD)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--progress-every", type=int, default=100)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        plan.require_full_day_backfill_execute_flags(execute=args.execute, user_confirmed=args.user_confirmed)
        minute_trade_date = args.minute_trade_date or args.for_trade_date
        context_rows = plan.fetch_full_day_backfill_context_rows(
            dsn=args.dsn,
            trigger_context_run_id=args.trigger_context_run_id,
            for_trade_date=args.for_trade_date,
        )
        identities_by_asset = _identity_groups(context_rows)
        retained_rows = plan.fetch_retained_today_minute_rows_by_identity(
            dsn=args.dsn,
            for_trade_date=args.for_trade_date,
            minute_trade_date=minute_trade_date,
            is_previous_day_preload=args.previous_day_preload,
            identities_by_asset=identities_by_asset,
        )
        adapter_rows, fetch_results = build_adapter_rows(
            context_rows=context_rows,
            retained_rows_by_identity=retained_rows,
            minute_trade_date=minute_trade_date,
            progress_every=args.progress_every,
        )
        blocking_fetches = [row for row in fetch_results if row.get("status") == "failed"]
        transport_provenance = winning_transport_provenance(fetch_results)
        if blocking_fetches:
            report = {
                "stage": "V3_20260612_N3_FULL_DAY_1M_BACKFILL",
                "result": "BLOCKED",
                "blocked_reason": "adapter_fetch_failed_before_db_write",
                "backfill_run_id": args.backfill_run_id,
                "for_trade_date": args.for_trade_date,
                "minute_trade_date": minute_trade_date,
                "is_previous_day_preload": args.previous_day_preload,
                "fetch_status_counts": dict(Counter(str(row.get("status")) for row in fetch_results)),
                "blocking_fetch_sample": blocking_fetches[:50],
                "database_written": False,
                "forbidden_scope_proof": plan.forbidden_scope_proof(),
            }
            plan.write_json(args.json_report_path, report)
            plan.write_text(args.markdown_report_path, plan.format_full_day_backfill_execute_report(report))
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
            return 2

        records_by_asset, object_results = plan.build_full_day_backfill_records_for_context(
            context_rows=context_rows,
            retained_rows_by_identity=retained_rows,
            adapter_rows_by_identity=adapter_rows,
            backfill_run_id=args.backfill_run_id,
            source_condition_run_id=args.source_condition_run_id,
            for_trade_date=args.for_trade_date,
            minute_trade_date=minute_trade_date,
            is_previous_day_preload=args.previous_day_preload,
            transport_provenance=transport_provenance,
        )
        write_result = plan.write_full_day_backfill_to_db(
            dsn=args.dsn,
            backfill_run_id=args.backfill_run_id,
            source_condition_run_id=args.source_condition_run_id,
            for_trade_date=args.for_trade_date,
            minute_trade_date=minute_trade_date,
            is_previous_day_preload=args.previous_day_preload,
            source_trade_date=args.source_trade_date,
            prev_trade_date=args.prev_trade_date,
            records_by_asset=records_by_asset,
            object_results=object_results,
            transport_provenance=transport_provenance,
        )
        report: dict[str, Any] = {
            "stage": "V3_20260612_N3_FULL_DAY_1M_BACKFILL",
            "result": "EXECUTE_PASS",
            "backfill_run_id": args.backfill_run_id,
            "for_trade_date": args.for_trade_date,
            "minute_trade_date": minute_trade_date,
            "is_previous_day_preload": args.previous_day_preload,
            "source_condition_run_id": args.source_condition_run_id,
            "trigger_context_run_id": args.trigger_context_run_id,
            "records_planned": write_result["records_planned"],
            "P0_P1_P2": write_result["p_counts"],
            "fetch_status_counts": dict(Counter(str(row.get("status")) for row in fetch_results)),
            "object_status_counts": dict(Counter(str(row.get("status")) for row in object_results)),
            "source_policy_counts": dict(Counter(str(row.get("source_policy")) for row in object_results)),
            "transport_provenance": transport_provenance,
            "pre_counts": write_result["pre_counts"],
            "post_counts": write_result["post_counts"],
            "quality_item_count": len(write_result["quality_items"]),
            "side_effects": {
                "database_written": True,
                "event_outbox_written": False,
                "outbox_inbox_checkpoint_consumed_or_updated": False,
                "n4_executed": False,
                "n5_executed": False,
                "n6_voice_mobile_sim_trade_touched": False,
                "old_system_read": False,
            },
        }
        plan.write_json(args.json_report_path, report)
        plan.write_text(args.markdown_report_path, plan.format_full_day_backfill_execute_report(report))
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI reports scoped blockers.
        report = {
            "stage": "V3_20260612_N3_FULL_DAY_1M_BACKFILL",
            "result": "BLOCKED",
            "blocked_reason": f"{type(exc).__name__}: {exc}",
            "backfill_run_id": args.backfill_run_id,
            "for_trade_date": args.for_trade_date,
            "minute_trade_date": args.minute_trade_date or args.for_trade_date,
            "is_previous_day_preload": args.previous_day_preload,
            "database_written": False,
            "forbidden_scope_proof": plan.forbidden_scope_proof(),
        }
        plan.write_json(args.json_report_path, report)
        plan.write_text(args.markdown_report_path, plan.format_full_day_backfill_execute_report(report))
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
