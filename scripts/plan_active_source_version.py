#!/usr/bin/env python3
"""Print an active source version activation/rollback dry-run plan."""

from __future__ import annotations

import argparse
import json

from ashare_v3.ingestion.active_source_version import ALLOWED_ACTIVE_DATA_TYPES, build_active_source_version_plan
from ashare_v3.ingestion.common import QualityGateResult


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-domain", required=True, choices=sorted(ALLOWED_ACTIVE_DATA_TYPES))
    parser.add_argument("--data-type", required=True)
    parser.add_argument("--scope-key", default="global")
    parser.add_argument("--source-version", required=True)
    parser.add_argument("--source-batch-id", required=True)
    parser.add_argument("--previous-source-version")
    parser.add_argument("--previous-source-batch-id")
    parser.add_argument("--activated-by", default="ingestion")
    parser.add_argument("--quality-status", default="passed", choices=("passed", "failed", "warning"))
    parser.add_argument("--quality-gate-name", default="sample_quality_gate")
    args = parser.parse_args()

    plan = build_active_source_version_plan(
        data_domain=args.data_domain,
        data_type=args.data_type,
        scope_key=args.scope_key,
        source_version=args.source_version,
        source_batch_id=args.source_batch_id,
        previous_source_version=args.previous_source_version,
        previous_source_batch_id=args.previous_source_batch_id,
        activated_by=args.activated_by,
        quality_gates=[
            QualityGateResult(
                gate_name=args.quality_gate_name,
                status=args.quality_status,
                expected_value="passed",
                actual_value=args.quality_status,
            )
        ],
    )
    print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2))
    return 0 if plan.activation_allowed else 1


if __name__ == "__main__":
    raise SystemExit(main())
