#!/usr/bin/env python3
"""Windows N1 bootstrap entrypoint; plan is safe, execute is fail-closed."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ashare_v3.ingestion.windows_n1_bootstrap import N1_BOOTSTRAP_STAGES, WindowsN1BootstrapConfig, execute_bootstrap
from ashare_v3.ingestion.windows_n1_postgres import WindowsN1PostgresRepository
from ashare_v3.ingestion.windows_n1_production import WindowsN1ProductionHandlers
from ashare_v3.ingestion.windows_n1_sources import EltdxWindowsSource, TQHttpClient, TQWindowsSource
from ashare_v3.ingestion.windows_n1_db_setup import PASSWORDLESS_APP_DSN


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", default=r"C:\AshareV3\artifacts\n1")
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--schema-only", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if sum((args.plan, args.schema_only, args.execute)) != 1:
        parser.error("choose exactly one of --plan, --schema-only, or --execute")
    config = WindowsN1BootstrapConfig.for_today(artifact_root=Path(args.artifact_root), today=date.today())
    if args.plan:
        print(json.dumps({
        "mode": "plan",
        "layer_role": "N1_ingestion",
        "start_date": config.start_date,
        "end_date": config.end_date,
        "tq_url": config.tq_url,
        "stages": list(N1_BOOTSTRAP_STAGES),
        "calendar_external": True,
        "writes_common_trade_calendar": False,
        "starts_scheduler": False,
        "touches_n2_n6": False,
        }, ensure_ascii=False, indent=2))
        return 0
    import psycopg
    with psycopg.connect(PASSWORDLESS_APP_DSN, connect_timeout=8) as connection:
        repository = WindowsN1PostgresRepository(connection)
        if args.schema_only:
            repository.verify_authority()
            counts = repository.business_row_counts()
            if any(counts.values()):
                raise SystemExit(f"schema-only row-count invariant failed: {counts}")
            print(json.dumps({"result": "SCHEMA_READY", "business_row_counts": counts, "database_written": False, "business_rows_written": 0, "calendar_rows_written": 0, "downstream_rows_written": 0}, ensure_ascii=False))
            return 0
        from eltdx import TdxClient
        tq = TQWindowsSource(TQHttpClient(base_url=config.tq_url))
        with TdxClient(timeout=8) as eltdx_client:
            production = WindowsN1ProductionHandlers(config=config, tq=tq, eltdx=EltdxWindowsSource(eltdx_client), repository=repository)
            result = execute_bootstrap(config=config, stage_handlers=production.handlers())
        if not result.n1_data_ready:
            raise SystemExit(2)
        print(json.dumps({"result": "N1_DATA_READY", "run_id": result.run_id, "artifact": str(config.artifact_root / result.run_id / "windows_n1_run.json")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
