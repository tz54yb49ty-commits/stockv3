#!/usr/bin/env python3
"""Build a read-only condition_display_basis dry-run report.

N2-Display-3 boundary: this script reads an existing N2 active run and builds
display-basis preview rows only. It does not write display tables, overwrite
condition runs, execute 014b, enter downstream layers, or start workers.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from ashare_v3.condition.display_basis import build_condition_display_basis_dry_run
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(description="Build N2 condition_display_basis dry-run preview.")
    parser.add_argument("--run-id", required=True, help="Existing active N2 condition run id.")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Dry-run mode. This is the only supported mode.")
    parser.add_argument("--execute", action="store_true", help="Rejected. Display basis execute requires later confirmation.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--report-path", default="", help="Optional JSON report path.")
    parser.add_argument("--summary-path", default="", help="Optional Markdown summary path.")
    parser.add_argument("--no-rows", action="store_true", help="Omit preview rows from JSON report.")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    args = parser.parse_args()

    if args.execute:
        parser.error("N2-Display-3 only supports --dry-run. Execute/overwrite is forbidden in this stage.")

    report = build_condition_display_basis_dry_run(
        dsn=args.dsn,
        run_id=args.run_id,
        include_rows=not args.no_rows,
    )
    if args.report_path:
        path = Path(args.report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    if args.summary_path:
        path = Path(args.summary_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(format_markdown_report(report), encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if report["passed"] else 2


def format_summary(report: dict[str, Any]) -> str:
    quality = report["quality"]
    preview = report["display_preview"]
    lines = [
        "condition_display_basis dry-run",
        f"  run_id={report['run_id']}",
        f"  source_trade_date={report['source_trade_date']}",
        f"  for_trade_date={report['for_trade_date']}",
        f"  prev_trade_date={report['prev_trade_date']}",
        f"  stock_preview_rows={preview['stock']['row_count']}",
        f"  index_preview_rows={preview['index']['row_count']}",
        f"  board_preview_rows={preview['board']['row_count']}",
        f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']}",
        f"  display_table_row_counts_before={report['display_table_row_counts_before']}",
        f"  display_table_row_counts_after={report['display_table_row_counts_after']}",
        f"  passed={report['passed']}",
        "  writes_performed=false display_basis_written=false overwrite_performed=false",
    ]
    return "\n".join(lines)


def format_markdown_report(report: dict[str, Any]) -> str:
    preview = report["display_preview"]
    quality = report["quality"]
    lines = [
        "# N2-Display-3 Condition Display Basis Dry-run Report",
        "",
        "layer_role = N2_condition",
        f"status = {'DRY_RUN_PASS' if report['passed'] else 'DRY_RUN_BLOCKED'}",
        "",
        "## Run",
        "",
        "```text",
        f"run_id = {report['run_id']}",
        f"source_trade_date = {report['source_trade_date']}",
        f"for_trade_date = {report['for_trade_date']}",
        f"prev_trade_date = {report['prev_trade_date']}",
        "writes_performed = false",
        "display_basis_written = false",
        "overwrite_performed = false",
        "downstream_layers_touched = false",
        "```",
        "",
        "## Preview Row Counts",
        "",
        "| Domain | Display table | Rows | Objects |",
        "|---|---|---:|---:|",
    ]
    for domain in ("stock", "index", "board"):
        section = preview[domain]
        lines.append(f"| {domain} | {section['display_table']} | {section['row_count']} | {section['object_count']} |")
    lines.extend(
        [
            "",
            "## Validation",
            "",
            "| Domain | Duplicate keys | Missing basis trace | Invalid condition keys | Invalid signal types | Invalid baseline shape | Reference mismatches | Invalid reference period | Forbidden fields | Empty scope trace |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for domain in ("stock", "index", "board"):
        section = preview[domain]
        uniqueness = section["uniqueness"]
        integrity = section["field_integrity"]
        traceability = section["traceability"]
        forbidden = section["forbidden_field_check"]
        lines.append(
            "| {domain} | {duplicate} | {basis_missing} | {bad_keys} | {bad_signals} | {bad_baseline} | {clear_mismatch} | {bad_ref} | {forbidden} | {empty_scope} |".format(
                domain=domain,
                duplicate=uniqueness["duplicate_count"],
                basis_missing=integrity["source_condition_basis_ids_missing"],
                bad_keys=integrity["selected_condition_keys_invalid"],
                bad_signals=integrity["selected_signal_types_invalid"],
                bad_baseline=integrity["period_trigger_baseline_invalid_shape"],
                clear_mismatch=integrity["clear_sell_ref_period_mismatch"],
                bad_ref=integrity["invalid_reference_period"],
                forbidden=forbidden["forbidden_field_count"],
                empty_scope=traceability["source_minute_target_scope_ids_empty_count"],
            )
        )
    lines.extend(
        [
            "",
            "## Display Table Row Counts",
            "",
            "| Table | Before | After |",
            "|---|---:|---:|",
        ]
    )
    for table, before in report["display_table_row_counts_before"].items():
        after = report["display_table_row_counts_after"].get(table)
        lines.append(f"| {table} | {before} | {after} |")
    lines.extend(
        [
            "",
            "## Quality",
            "",
            "```text",
            f"p0_count = {quality['p0_count']}",
            f"p1_count = {quality['p1_count']}",
            f"p2_count = {quality['p2_count']}",
            f"can_enter_n2_full_dry_run = {str(report['can_enter_n2_full_dry_run']).lower()}",
            "```",
            "",
            "## Samples",
        ]
    )
    for domain in ("stock", "index", "board"):
        lines.extend(["", f"### {domain}", "", "```json"])
        lines.append(json.dumps(preview[domain]["sample_rows"], ensure_ascii=False, indent=2, default=str))
        lines.append("```")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
