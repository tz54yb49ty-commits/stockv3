#!/usr/bin/env python3
"""Execute N3-A1 previous-day minute preload.

This script pulls previous-day 1 minute bars and writes only N3 market-data
facts/status/quality rows. It does not write common_event_outbox, start
workers, or enter downstream layers.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from ashare_v3.market.previous_day_preload_execute import (
    DEFAULT_N3_A1_JSON_REPORT_PATH,
    DEFAULT_N3_A1_MD_REPORT_PATH,
    DEFAULT_N3_A1_POST_BACKUP_PATH,
    DEFAULT_N3_A1_PRE_BACKUP_PATH,
    PreviousDayMinutePreloadExecuteError,
    ensure_execute_authorized,
    run_previous_day_minute_preload_execute,
)
from ashare_v3.market.preload_execute_contract import DEFAULT_A1_CONTRACT_JSON_PATH, read_json
from check_condition_source_ready import DEFAULT_DSN


def direct_alias_mode_enabled(args: argparse.Namespace) -> bool:
    return any(
        (
            args.historical_preload,
            args.source_subscription_run_id,
            args.preload_run_id,
            args.data_trade_date,
        )
    )


def validate_direct_alias_contract(args: argparse.Namespace) -> None:
    """Validate optional direct aliases against the reviewed contract artifact.

    The runner remains contract-first for compatibility. Direct aliases provide
    an explicit operator-facing guard and must match the contract before any DB
    access or market-data adapter path is entered.
    """

    if not direct_alias_mode_enabled(args):
        return

    missing = []
    if not args.historical_preload:
        missing.append("--historical-preload")
    if not args.source_subscription_run_id:
        missing.append("--source-subscription-run-id")
    if not args.preload_run_id:
        missing.append("--preload-run-id")
    if not args.data_trade_date:
        missing.append("--data-trade-date")
    if missing:
        raise PreviousDayMinutePreloadExecuteError(
            "direct alias mode requires " + ", ".join(missing)
        )

    contract = read_json(args.contract_path)
    source_subscription_run_id = str(
        contract.get("source_subscription_run_id") or contract.get("source_run_id") or ""
    )
    preload_run_id = str(contract.get("preload_run_id") or "")
    data_trade_date = str(contract.get("data_trade_date") or contract.get("previous_day_minute_date") or "")
    required_data_kind = str(contract.get("required_data_kind") or "previous_day_minute_bar_1m")
    historical_preload = bool(contract.get("historical_preload", required_data_kind == "previous_day_minute_bar_1m"))

    mismatches = []
    if args.source_subscription_run_id != source_subscription_run_id:
        mismatches.append(
            f"--source-subscription-run-id expected {source_subscription_run_id} actual {args.source_subscription_run_id}"
        )
    if args.preload_run_id != preload_run_id:
        mismatches.append(f"--preload-run-id expected {preload_run_id} actual {args.preload_run_id}")
    if args.data_trade_date != data_trade_date:
        mismatches.append(f"--data-trade-date expected {data_trade_date} actual {args.data_trade_date}")
    if not historical_preload or required_data_kind != "previous_day_minute_bar_1m":
        mismatches.append(
            "--historical-preload requires contract historical_preload=true and "
            "required_data_kind=previous_day_minute_bar_1m"
        )
    if mismatches:
        raise PreviousDayMinutePreloadExecuteError("; ".join(mismatches))


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute N3-A1 previous-day minute preload.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--contract-path", default=DEFAULT_A1_CONTRACT_JSON_PATH)
    parser.add_argument("--pre-backup-path", default=DEFAULT_N3_A1_PRE_BACKUP_PATH)
    parser.add_argument("--post-backup-path", default=DEFAULT_N3_A1_POST_BACKUP_PATH)
    parser.add_argument("--json-report-path", default=DEFAULT_N3_A1_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_N3_A1_MD_REPORT_PATH)
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument("--execute", action="store_true", help="Required explicit execute authorization.")
    parser.add_argument("--user-confirmed", action="store_true", help="Required operator confirmation.")
    parser.add_argument("--historical-preload", action="store_true", help="Require historical previous-day preload semantics.")
    parser.add_argument("--source-subscription-run-id", help="Alias guard for the source market-data subscription run.")
    parser.add_argument("--preload-run-id", help="Alias guard for the target previous-day preload run.")
    parser.add_argument("--data-trade-date", help="Alias guard for the previous-day minute data trade date.")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    args = parser.parse_args()

    try:
        ensure_execute_authorized(execute=args.execute, user_confirmed=args.user_confirmed)
        validate_direct_alias_contract(args)
        report = run_previous_day_minute_preload_execute(
            dsn=args.dsn,
            contract_path=args.contract_path,
            pre_backup_path=args.pre_backup_path,
            post_backup_path=args.post_backup_path,
            json_report_path=args.json_report_path,
            markdown_report_path=args.markdown_report_path,
            progress_callback=print,
            progress_every=args.progress_every,
            execute=args.execute,
            user_confirmed=args.user_confirmed,
        )
    except PreviousDayMinutePreloadExecuteError as exc:
        blocked = {
            "result": "BLOCKED",
            "stage": "N3-A1",
            "layer_role": "N3_market_data",
            "reason": str(exc),
            "writes_performed": False,
            "market_data_pulled": False,
            "market_data_fact_written": False,
            "event_outbox_written": False,
            "downstream_layers_touched": False,
            "worker_started": False,
        }
        print(json.dumps(blocked, ensure_ascii=False, indent=2))
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if int(report["quality"]["p0_count"]) == 0 else 2


def format_summary(report: dict[str, Any]) -> str:
    quality = report["quality"]
    write = report["write_result"]
    return "\n".join(
        [
            "previous-day minute preload execute",
            f"  stage={report['stage']}",
            f"  layer_role={report['layer_role']}",
            f"  source_run_id={report['source_run_id']}",
            f"  preload_run_id={report['preload_run_id']}",
            f"  previous_day_minute_date={report['previous_day_minute_date']}",
            f"  objects_processed={write['objects_processed']}",
            f"  minute_rows_written={write['minute_rows_written']}",
            f"  preload_status_rows_written={write['preload_status_rows_written']}",
            f"  quality_item_rows_written={write['quality_item_rows_written']}",
            f"  event_outbox_rows_written={write['event_outbox_rows_written']}",
            f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']}",
            "  "
            f"market_data_pulled={report['side_effects']['market_data_pulled']} "
            f"market_data_fact_written={report['side_effects']['market_data_fact_written']} "
            "event_outbox_written=false downstream_layers_touched=false worker_started=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
