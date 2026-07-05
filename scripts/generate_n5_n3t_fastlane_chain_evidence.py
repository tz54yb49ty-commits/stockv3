#!/usr/bin/env python3
"""Generate local chain-evidence JSON for the N5/N3T Fastlane monitor."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from ashare_v3.runtime_control.n5_n3t_fastlane import build_fastlane_chain_evidence


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate N5/N3T Fastlane chain evidence from read-only summaries.")
    parser.add_argument("--for-trade-date", required=True)
    parser.add_argument("--session-phase", required=True)
    parser.add_argument("--closed-minute-available", choices=("true", "false"), required=True)
    parser.add_argument("--db-summary-path", required=True)
    parser.add_argument("--artifact-summary-path", required=True)
    parser.add_argument("--output-path", required=True)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(list(argv) if argv is not None else None)
    output_path = Path(args.output_path)
    evidence = build_fastlane_chain_evidence(
        for_trade_date=args.for_trade_date,
        session_phase=args.session_phase,
        closed_minute_available=args.closed_minute_available == "true",
        db_summary=_read_json_object(Path(args.db_summary_path)),
        artifact_summary=_read_json_object(Path(args.artifact_summary_path)),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    output_path.write_text(encoded, encoding="utf-8")
    report = {
        "result": "CHAIN_EVIDENCE_OUTPUT_PASS",
        "output_path": str(output_path),
        "sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
        "forbidden_operation_proof": evidence["forbidden_operation_proof"],
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print(f"result={report['result']} output_path={report['output_path']} sha256={report['sha256']}")
    return 0


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"expected JSON object: {path}")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
