#!/usr/bin/env python3
"""Bounded backfill for the N6 projection typed/slim read model.

The default mode is read-only preflight. Execute mode requires two exact
confirmation tokens, acquires the production writer advisory lock, and commits
each 250-500 row batch independently. It never creates indexes or deploys code.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from typing import Any, Iterator, Sequence

import psycopg
from psycopg.rows import dict_row


DEFAULT_DSN = os.environ.get(
    "ASHARE_V3_POSTGRES_DSN",
    "postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3",
)
READ_MODEL_VERSION = "n6_projection_list_v1"
MIN_BATCH_SIZE = 250
MAX_BATCH_SIZE = 500
DEFAULT_BATCH_SIZE = 500
EXECUTE_CONFIRM_TOKEN = "N6_PROJECTION_READ_MODEL_BACKFILL_CONFIRMED"
WRITER_STOPPED_CONFIRM_TOKEN = "N6_PROJECTION_WRITER_STOPPED_CONFIRMED"
POLLER_ADVISORY_LOCK_KEY = -8342571444709044287

STATUS_SQL = """
SELECT
  count(*)::bigint AS projection_count,
  count(*) FILTER (
    WHERE p.for_trade_date IS NULL
       OR p.list_payload_version IS DISTINCT FROM %(read_model_version)s
       OR p.list_payload_json IS NULL
       OR pg_catalog.jsonb_typeof(p.list_payload_json) <> 'object'
  )::bigint AS incomplete_count,
  count(*) FILTER (
    WHERE shared.source_signal_projection_id IS NULL
  )::bigint AS missing_shared_projection_count,
  count(*) FILTER (
    WHERE p.for_trade_date IS NOT NULL
      AND shared.for_trade_date IS NOT NULL
      AND p.for_trade_date IS DISTINCT FROM shared.for_trade_date
  )::bigint AS trade_date_mismatch_count,
  count(*) FILTER (
    WHERE shared.user_projection_run_id IS NOT NULL
      AND p.user_projection_run_id IS DISTINCT FROM shared.user_projection_run_id
  )::bigint AS projection_run_mismatch_count,
  count(DISTINCT p.user_projection_run_id)::bigint AS projection_run_count
FROM public.user_signal_projection p
LEFT JOIN public.n6_ai_shared_signal_projection shared
  ON shared.source_signal_projection_id = p.user_signal_projection_id
"""

RUN_DATE_CLOSURE_SQL = """
SELECT count(*)::bigint AS invalid_run_date_count
FROM (
  SELECT p.user_projection_run_id
  FROM public.user_signal_projection p
  JOIN public.n6_ai_shared_signal_projection shared
    ON shared.source_signal_projection_id = p.user_signal_projection_id
  GROUP BY p.user_projection_run_id
  HAVING count(DISTINCT shared.for_trade_date) <> 1
) invalid_runs
"""

BACKFILL_BATCH_SQL = """
WITH batch AS (
  SELECT p.user_signal_projection_id
  FROM public.user_signal_projection p
  JOIN public.n6_ai_shared_signal_projection shared
    ON shared.source_signal_projection_id = p.user_signal_projection_id
  WHERE p.for_trade_date IS DISTINCT FROM shared.for_trade_date
     OR p.list_payload_version IS DISTINCT FROM %(read_model_version)s
     OR p.list_payload_json IS NULL
     OR pg_catalog.jsonb_typeof(p.list_payload_json) <> 'object'
  ORDER BY p.user_signal_projection_id
  LIMIT %(batch_size)s
  FOR UPDATE OF p SKIP LOCKED
)
UPDATE public.user_signal_projection p
SET for_trade_date = shared.for_trade_date,
    list_payload_version = %(read_model_version)s,
    list_payload_json = NULL
FROM batch
JOIN public.n6_ai_shared_signal_projection shared
  ON shared.source_signal_projection_id = batch.user_signal_projection_id
WHERE p.user_signal_projection_id = batch.user_signal_projection_id
RETURNING p.user_signal_projection_id
"""


@dataclass(frozen=True)
class BackfillConfig:
    dsn: str
    batch_size: int = DEFAULT_BATCH_SIZE
    max_batches: int = 0

    def validate(self) -> None:
        if not MIN_BATCH_SIZE <= self.batch_size <= MAX_BATCH_SIZE:
            raise ValueError(f"batch_size_must_be_{MIN_BATCH_SIZE}_to_{MAX_BATCH_SIZE}")
        if self.max_batches < 0:
            raise ValueError("max_batches_must_be_non_negative")


def read_status(dsn: str) -> dict[str, int]:
    with psycopg.connect(
        dsn,
        row_factory=dict_row,
        connect_timeout=10,
        options="-c default_transaction_read_only=on -c statement_timeout=30000",
    ) as conn, conn.cursor() as cur:
        cur.execute(STATUS_SQL, {"read_model_version": READ_MODEL_VERSION})
        status = dict(cur.fetchone() or {})
        cur.execute(RUN_DATE_CLOSURE_SQL)
        closure = dict(cur.fetchone() or {})
    status.update(closure)
    return {key: int(value or 0) for key, value in status.items()}


def status_blockers(status: dict[str, int], *, require_complete: bool) -> list[str]:
    blockers: list[str] = []
    for key in (
        "missing_shared_projection_count",
        "trade_date_mismatch_count",
        "projection_run_mismatch_count",
        "invalid_run_date_count",
    ):
        if int(status.get(key) or 0):
            blockers.append(f"{key}:{status[key]}")
    if require_complete and int(status.get("incomplete_count") or 0):
        blockers.append(f"incomplete_count:{status['incomplete_count']}")
    return blockers


@contextmanager
def writer_guard(dsn: str) -> Iterator[None]:
    conn = psycopg.connect(dsn, row_factory=dict_row, connect_timeout=10, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_catalog.pg_try_advisory_lock(%s::bigint) AS acquired",
                (POLLER_ADVISORY_LOCK_KEY,),
            )
            row = cur.fetchone() or {}
            if not bool(row.get("acquired")):
                raise RuntimeError("n6_projection_writer_advisory_lock_not_acquired")
        yield
    finally:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT pg_catalog.pg_advisory_unlock(%s::bigint)",
                    (POLLER_ADVISORY_LOCK_KEY,),
                )
        finally:
            conn.close()


def execute_one_batch(config: BackfillConfig) -> list[int]:
    with psycopg.connect(
        config.dsn,
        row_factory=dict_row,
        connect_timeout=10,
        options="-c lock_timeout=2000 -c statement_timeout=30000",
    ) as conn:
        with conn.transaction(), conn.cursor() as cur:
            cur.execute(
                BACKFILL_BATCH_SQL,
                {
                    "read_model_version": READ_MODEL_VERSION,
                    "batch_size": config.batch_size,
                },
            )
            return [int(row["user_signal_projection_id"]) for row in cur.fetchall()]


def run_backfill(config: BackfillConfig) -> dict[str, Any]:
    config.validate()
    before = read_status(config.dsn)
    blockers = status_blockers(before, require_complete=False)
    if blockers:
        return build_report("BLOCKED", config=config, before=before, after=before, blockers=blockers)

    batch_sizes: list[int] = []
    with writer_guard(config.dsn):
        while config.max_batches == 0 or len(batch_sizes) < config.max_batches:
            projection_ids = execute_one_batch(config)
            if not projection_ids:
                break
            batch_sizes.append(len(projection_ids))
        after = read_status(config.dsn)

    remaining = int(after.get("incomplete_count") or 0)
    result = "EXECUTE_PASS" if remaining == 0 else "PARTIAL_PASS"
    blockers = status_blockers(after, require_complete=result == "EXECUTE_PASS")
    if blockers:
        result = "BLOCKED"
    return build_report(
        result,
        config=config,
        before=before,
        after=after,
        blockers=blockers,
        batch_sizes=batch_sizes,
    )


def build_report(
    result: str,
    *,
    config: BackfillConfig,
    before: dict[str, int],
    after: dict[str, int],
    blockers: Sequence[str],
    batch_sizes: Sequence[int] = (),
) -> dict[str, Any]:
    return {
        "stage": "N6_PROJECTION_READ_MODEL_BACKFILL",
        "result": result,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "read_model_version": READ_MODEL_VERSION,
        "batch_size": config.batch_size,
        "max_batches": config.max_batches,
        "batch_count": len(batch_sizes),
        "batch_sizes": list(batch_sizes),
        "updated_row_count": sum(batch_sizes),
        "before": before,
        "after": after,
        "blockers": list(blockers),
        "writer_guard": {
            "advisory_lock_key": POLLER_ADVISORY_LOCK_KEY,
            "required": True,
        },
        "next_gate": (
            "create_concurrent_indexes_and_finalize_073"
            if result == "EXECUTE_PASS"
            else "resume_bounded_backfill"
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--max-batches", type=int, default=0)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-token", default="")
    parser.add_argument("--writer-stopped-confirm-token", default="")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = BackfillConfig(
        dsn=str(args.dsn),
        batch_size=int(args.batch_size),
        max_batches=int(args.max_batches),
    )
    try:
        config.validate()
    except ValueError as exc:
        print(json.dumps({"result": "BLOCKED", "blockers": [str(exc)]}, sort_keys=True))
        return 2

    if not args.execute:
        status = read_status(config.dsn)
        report = build_report(
            "PREFLIGHT_PASS" if not status_blockers(status, require_complete=False) else "BLOCKED",
            config=config,
            before=status,
            after=status,
            blockers=status_blockers(status, require_complete=False),
        )
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0 if report["result"] == "PREFLIGHT_PASS" else 2

    confirmation_blockers = []
    if args.confirm_token != EXECUTE_CONFIRM_TOKEN:
        confirmation_blockers.append("invalid_execute_confirm_token")
    if args.writer_stopped_confirm_token != WRITER_STOPPED_CONFIRM_TOKEN:
        confirmation_blockers.append("invalid_writer_stopped_confirm_token")
    if confirmation_blockers:
        print(json.dumps({"result": "BLOCKED", "blockers": confirmation_blockers}, sort_keys=True))
        return 2

    report = run_backfill(config)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["result"] == "EXECUTE_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
