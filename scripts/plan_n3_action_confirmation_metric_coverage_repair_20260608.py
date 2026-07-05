#!/usr/bin/env python3
"""Generate 20260608 N3 action metric scoped coverage repair artifacts."""

from __future__ import annotations

import argparse
import os

from ashare_v3.market.action_confirmation_metric_20260608_scoped_repair import (
    write_a1_c1_artifacts,
    write_metric_artifacts,
    write_subscription_artifacts,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dsn",
        default=os.environ.get("ASHARE_V3_POSTGRES_DSN")
        or "host=127.0.0.1 port=5432 dbname=ashare_v3 user=ashare_v3_user",
        help="v3 runtime PostgreSQL DSN; defaults to local ashare_v3 without printing secrets",
    )
    parser.add_argument("--subscription", action="store_true", help="refresh scoped subscription artifacts")
    parser.add_argument("--a1-c1", action="store_true", help="refresh A1/C1 minute pull artifacts")
    parser.add_argument("--metric", action="store_true", help="refresh additive metric materialization artifacts")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    run_all = not (args.subscription or args.a1_c1 or args.metric)
    if run_all or args.subscription:
        result = write_subscription_artifacts(args.dsn)
        dry_run = result["dry_run"]
        print(
            "SUBSCRIPTION_ARTIFACTS_PASS "
            f"scope={dry_run['source_scope_row_count']} "
            f"subscriptions={dry_run['subscription_row_count']} "
            f"pull_plan={dry_run['market_data_pull_plan_row_count']} "
            f"preflight={result['preflight']['result']}"
        )
    if run_all or args.a1_c1:
        result = write_a1_c1_artifacts(args.dsn)
        print(
            "A1_C1_ARTIFACTS_PASS "
            f"a1={result['a1_preflight']['result']} "
            f"c1_expected={result['c0'].get('expected_minute_rows')}"
        )
    if run_all or args.metric:
        result = write_metric_artifacts(args.dsn)
        payload = result["payload"]
        print(
            "METRIC_ARTIFACTS_PASS "
            f"rows={(payload.get('expected_rows') or {}).get('total')} "
            f"preflight={result['preflight']['result']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
