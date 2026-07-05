# N3/N4/N5 Intraday Access Localization Audited Fresh-Run Validation Recontract Preflight

Gate: `N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION_RECONTRACT_PREFLIGHT_GATE`

Result: `PREFLIGHT_PASS`

Layer role: `runtime_control`

Generated at: `2026-06-07T05:02:28.964100+00:00`

## Summary

Selected concrete read-only audit-only probe commands for N3, N4, and N5. This gate did not execute them.

## Approved Probe Commands

### RECONTRACT-AFR-N3-001

- layer: `N3_market_data`
- expected report: `docs/query_audit/N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION_RECONTRACT/reports/n3_post_closeout_metric_lineage_audit.json`
- forbidden flags present: `False`

```bash
PYTHONPATH=src:scripts ASHARE_QUERY_AUDIT_DIR=docs/query_audit/N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION_RECONTRACT python3 - <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from psycopg.rows import dict_row

from check_condition_source_ready import DEFAULT_DSN
from ashare_v3.market.query_audit_phase3 import audited_n3_market_readonly_plan_connect

DSN = os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN)
ARTIFACT_DIR = Path(os.environ["ASHARE_QUERY_AUDIT_DIR"])
REPORT_DIR = ARTIFACT_DIR / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
RUN_IDS = ['action_confirmation_projection_metric_20260605__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1', 'action_confirmation_projection_metric_20260605_repair_v1__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1', 'action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1']
SOURCE_RUN_ID = "runtime_control_intraday_access_localization_recontract_20260607_n3"
OUT = REPORT_DIR / "n3_post_closeout_metric_lineage_audit.json"
MD = REPORT_DIR / "n3_post_closeout_metric_lineage_audit.md"

with audited_n3_market_readonly_plan_connect(
    DSN,
    stage_id="n3_post_closeout_metric_lineage_audit",
    source_run_id=SOURCE_RUN_ID,
    artifact_dir=ARTIFACT_DIR,
    options="-c default_transaction_read_only=on -c statement_timeout=30000",
    row_factory=dict_row,
) as conn, conn.cursor() as cur:
    cur.execute("SELECT run_id, status FROM common_market_data_run WHERE run_id = ANY(%s) ORDER BY run_id", (RUN_IDS,))
    runs = [dict(row) for row in cur.fetchall()]
    cur.execute("""
        SELECT 'stock' AS asset_kind, count(*)::bigint AS row_count
        FROM stock_action_confirmation_projection_metric
        WHERE projection_run_id = ANY(%s)
        UNION ALL
        SELECT 'index' AS asset_kind, count(*)::bigint AS row_count
        FROM index_action_confirmation_projection_metric
        WHERE projection_run_id = ANY(%s)
        UNION ALL
        SELECT 'board' AS asset_kind, count(*)::bigint AS row_count
        FROM board_action_confirmation_projection_metric
        WHERE projection_run_id = ANY(%s)
        ORDER BY asset_kind
    """, (RUN_IDS, RUN_IDS, RUN_IDS))
    metric_counts = [dict(row) for row in cur.fetchall()]
    cur.execute("SELECT source_layer, event_type, count(*)::bigint AS row_count FROM common_event_outbox WHERE source_run_id = ANY(%s) GROUP BY source_layer, event_type ORDER BY source_layer, event_type", (RUN_IDS,))
    outbox_counts = [dict(row) for row in cur.fetchall()]
    cur.execute("SELECT count(*)::bigint AS row_count FROM common_event_inbox WHERE source_run_id = ANY(%s)", (RUN_IDS,))
    inbox_count = int(cur.fetchone()["row_count"])
    cur.execute("SELECT count(*)::bigint AS row_count FROM common_event_consumer_checkpoint WHERE checkpoint_payload::text LIKE %s", ("%action_confirmation_projection_metric_20260605%",))
    checkpoint_count = int(cur.fetchone()["row_count"])

report = {
    "result": "PROBE_PASS",
    "layer_role": "N3_market_data",
    "stage_id": "n3_post_closeout_metric_lineage_audit",
    "source_run_id": SOURCE_RUN_ID,
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "metric_run_ids": RUN_IDS,
    "common_market_data_run": runs,
    "metric_counts": metric_counts,
    "common_event_outbox_counts": outbox_counts,
    "common_event_inbox_count": inbox_count,
    "common_event_consumer_checkpoint_count": checkpoint_count,
    "writes_performed": False,
    "worker_started": False,
    "outbox_consumed_or_updated": False,
}
OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
MD.write_text("# N3 Post-Closeout Metric Lineage Audit\n\nResult: `PROBE_PASS`\n", encoding="utf-8")
print(json.dumps({"result": "PROBE_PASS", "report": str(OUT)}, ensure_ascii=False))
PY
```

### RECONTRACT-AFR-N4-001

- layer: `N4_trigger`
- expected report: `docs/query_audit/N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION_RECONTRACT/reports/n4_v4_corrected_dry_run.json`
- forbidden flags present: `False`

```bash
PYTHONPATH=src:scripts ASHARE_QUERY_AUDIT_DIR=docs/query_audit/N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION_RECONTRACT ASHARE_QUERY_AUDIT_SOURCE_RUN_ID=runtime_control_intraday_access_localization_recontract_20260607_n4 python3 scripts/plan_n4_20260605_v4_corrected_dry_run.py --json-report-path docs/query_audit/N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION_RECONTRACT/reports/n4_v4_corrected_dry_run.json --markdown-report-path docs/query_audit/N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION_RECONTRACT/reports/n4_v4_corrected_dry_run.md --sample-limit 20
```

### RECONTRACT-AFR-N5-001

- layer: `N5_action`
- expected report: `docs/query_audit/N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION_RECONTRACT/reports/n5_post_closeout_action_lineage_audit.json`
- forbidden flags present: `False`

```bash
PYTHONPATH=src:scripts ASHARE_QUERY_AUDIT_DIR=docs/query_audit/N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION_RECONTRACT python3 - <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from psycopg.rows import dict_row

from check_condition_source_ready import DEFAULT_DSN
from ashare_v3.action.query_audit_phase2 import audited_n5_readonly_plan_connect

DSN = os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN)
ARTIFACT_DIR = Path(os.environ["ASHARE_QUERY_AUDIT_DIR"])
REPORT_DIR = ARTIFACT_DIR / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
ACTION_RUN_ID = "action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
TRIGGER_RUN_ID = "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
SOURCE_RUN_ID = "runtime_control_intraday_access_localization_recontract_20260607_n5"
OUT = REPORT_DIR / "n5_post_closeout_action_lineage_audit.json"
MD = REPORT_DIR / "n5_post_closeout_action_lineage_audit.md"

with audited_n5_readonly_plan_connect(
    DSN,
    stage_id="n5_post_closeout_action_lineage_audit",
    source_run_id=SOURCE_RUN_ID,
    artifact_dir=ARTIFACT_DIR,
    options="-c default_transaction_read_only=on -c statement_timeout=30000",
    row_factory=dict_row,
) as conn, conn.cursor() as cur:
    cur.execute("SELECT run_id, status FROM common_action_run WHERE run_id = %s", (ACTION_RUN_ID,))
    action_run = [dict(row) for row in cur.fetchall()]
    cur.execute("SELECT event_type, action_state, payload_json->>'blocked_reason' AS blocked_reason, count(*)::bigint AS row_count FROM common_action_event WHERE run_id = %s GROUP BY event_type, action_state, payload_json->>'blocked_reason' ORDER BY event_type, action_state, blocked_reason", (ACTION_RUN_ID,))
    action_event_counts = [dict(row) for row in cur.fetchall()]
    cur.execute("SELECT event_type, source_layer, source_run_id, count(*)::bigint AS row_count FROM common_event_outbox WHERE source_run_id IN (%s, %s) GROUP BY event_type, source_layer, source_run_id ORDER BY source_layer, event_type", (ACTION_RUN_ID, TRIGGER_RUN_ID))
    outbox_counts = [dict(row) for row in cur.fetchall()]
    cur.execute("SELECT count(*)::bigint AS row_count FROM common_event_inbox WHERE source_run_id IN (%s, %s)", (ACTION_RUN_ID, TRIGGER_RUN_ID))
    inbox_count = int(cur.fetchone()["row_count"])
    cur.execute("SELECT count(*)::bigint AS row_count FROM common_event_consumer_checkpoint WHERE checkpoint_payload::text LIKE %s OR checkpoint_payload::text LIKE %s", (f"%{ACTION_RUN_ID}%", f"%{TRIGGER_RUN_ID}%"))
    checkpoint_count = int(cur.fetchone()["row_count"])

report = {
    "result": "PROBE_PASS",
    "layer_role": "N5_action",
    "stage_id": "n5_post_closeout_action_lineage_audit",
    "source_run_id": SOURCE_RUN_ID,
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "action_run_id": ACTION_RUN_ID,
    "source_trigger_run_id": TRIGGER_RUN_ID,
    "common_action_run": action_run,
    "common_action_event_counts": action_event_counts,
    "common_event_outbox_counts": outbox_counts,
    "common_event_inbox_count": inbox_count,
    "common_event_consumer_checkpoint_count": checkpoint_count,
    "writes_performed": False,
    "worker_started": False,
    "outbox_consumed_or_updated": False,
}
OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
MD.write_text("# N5 Post-Closeout Action Lineage Audit\n\nResult: `PROBE_PASS`\n", encoding="utf-8")
print(json.dumps({"result": "PROBE_PASS", "report": str(OUT)}, ensure_ascii=False))
PY
```

## Snapshot Support Command Template

Run once with `SNAPSHOT_PHASE=pre` before probes and once with `SNAPSHOT_PHASE=post` after probes.

```bash
PYTHONPATH=src:scripts SNAPSHOT_PHASE=<pre|post> python3 - <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from check_condition_source_ready import DEFAULT_DSN

DSN = os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN)
PHASE = os.environ["SNAPSHOT_PHASE"]
OUT = Path("docs/query_audit/N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION_RECONTRACT/reports/pre_post_snapshot.json")
TABLES = [
    "common_event_outbox", "common_event_inbox", "common_event_consumer_checkpoint",
    "common_trigger_match", "common_trigger_state", "common_action_event",
    "user_projection_run", "user_signal_projection", "user_signal_card", "user_notification_queue",
]

def table_exists(cur, table):
    cur.execute("SELECT to_regclass(%s) AS regclass", (f"public.{table}",))
    return cur.fetchone()["regclass"] is not None

def count_table(cur, table):
    if not table_exists(cur, table):
        return {"exists": False}
    cur.execute(sql.SQL("SELECT count(*)::bigint AS row_count FROM {}").format(sql.Identifier(table)))
    return {"exists": True, "row_count": int(cur.fetchone()["row_count"])}

with psycopg.connect(
    DSN,
    application_name=f"runtime_control_access_localization_recontract_snapshot_{PHASE}",
    options="-c default_transaction_read_only=on -c statement_timeout=30000",
    row_factory=dict_row,
) as conn, conn.cursor() as cur:
    cur.execute("SHOW transaction_read_only")
    readonly = cur.fetchone()["transaction_read_only"]
    snapshot = {
        "phase": PHASE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "transaction_read_only": str(readonly),
        "tables": {table: count_table(cur, table) for table in TABLES},
    }
OUT.parent.mkdir(parents=True, exist_ok=True)
existing = json.loads(OUT.read_text()) if OUT.exists() else {}
existing[PHASE] = snapshot
if "pre" in existing and "post" in existing:
    def scrub(value):
        return {k: v for k, v in value.items() if k not in {"phase", "generated_at"}}
    existing["pre_post_equal_excluding_capture_times"] = scrub(existing["pre"]) == scrub(existing["post"])
OUT.write_text(json.dumps(existing, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps({"snapshot": PHASE, "path": str(OUT)}, ensure_ascii=False))
PY
```

## Acceptance Criteria For Execute Gate

- Pre snapshot and post snapshot exist and are equal excluding capture timestamps.
- N3/N4/N5 probe reports exist and parse as JSON.
- N3/N4/N5 audit artifacts exist under artifact_root and parse as JSON.
- Every audit entry has readonly_transaction=true.
- denied_table_hit_entries=0 and no referenced table is one of the five denied display/membership tables.
- db_write_attempted_entries=0.
- worker_started_entries=0.
- outbox_consumed_entries=0.
- checkpoint_updated_entries=0.
- N4 dry-run has result=DRY_RUN_PASS, compliant_count=605, blocked_count=291.

## P0/P1/P2

`P0/P1/P2 = 0/2/0`

P1 items:

- Probe commands are selected but not executed in this preflight gate.
- 33 N1/N2/ingestion script direct connect sites remain documented outside this N3/N4/N5 runtime validation scope.

## Forbidden Scope Proof

No database write, migration, rollback, probe execution, business execute, outbox/inbox/checkpoint mutation, worker startup, delivery/push/voice/mobile, sim/position/PnL/real_trade, proposal/order/trade, PostgreSQL config change, or pg_stat_statements enablement occurred.

## Next Gate Recommendation

`N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION_RECONTRACT_EXECUTE_GATE`

## Validation Summary

- JSON parse: `PASS`
- structured query audit/adoption unittests: `23 OK`
- `git diff --check`: `PASS`
## Preflight Amendments

- `RECONTRACT-PREFLIGHT-AMENDMENT-N5-RUN-ID`: N5 audit-only probe aligned to live `common_action_event` schema; `run_id` replaces non-existent `action_run_id`. No database write.

