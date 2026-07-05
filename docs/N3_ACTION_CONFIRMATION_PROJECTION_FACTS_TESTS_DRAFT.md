# N3 Action-Confirmation Projection Facts Tests Draft

Status: DRAFT_PASS

Generated at: 2026-06-02

Layer role: N3_market_data

This tests draft is scoped to N3 artifacts only. It does not execute a migration, write database rows, run N4/N5/N6, consume outbox, or start workers.

## Existing Draft Test

```text
tests/test_market_data_action_confirmation_metric_schema_draft.py
```

The draft test validates the SQL/readiness artifacts without touching the database.

## Required Future Unit Tests

Schema/readiness tests:

```text
three physical tables exist in schema draft
table names are stock/index/board_action_confirmation_projection_metric
required current_price fields exist
required previous 1m/5m/30m/120m body high/low fields exist
required amount fields exist
first-period boundary fields exist
source refs and projection_schema_version fields exist
metric_quality_status and metric_ready fields exist
schema has no outbox/inbox/checkpoint DML
schema has no trigger/action/user/voice/mobile/sim/position references as target tables
metric_ready=true has DB hard guard for source_fact_ids / source_minute_refs / previous_day_minute_refs
schema rollback hard-fails with RAISE EXCEPTION when row_count is nonzero before drop
business rollback is projection_run_id scoped and hard-fails with RAISE EXCEPTION when outbox/inbox/checkpoint refs are nonzero
```

Future planner tests:

```text
missing source snapshot run blocks
missing today minute run blocks
missing previous-day minute run blocks
existing projection_run_id blocks
scoped outbox/inbox/checkpoint refs block
first 1m defaults amount comparison to pass
first 5m defaults amount comparison to pass
first 30m/120m do not default price comparison to pass
non-first periods use same_trade_date_previous_period
first periods use previous_trade_date_last_period
missing previous body high/low makes metric_ready=false
missing amount outside first 1m/5m makes metric_ready=false
metric_ready=true requires trace refs
stock/index/board stay physically separated
```

Future execute tests:

```text
requires --execute
requires --user-confirmed
allowed writes only N3 metric/run/quality
no common_event_outbox writes
no common_event_inbox/checkpoint writes
no realtime snapshot/minute/projection mutation
no N4/N5/N6 writes
no worker
row counts match dry-run
metric_ready distribution matches dry-run
quality P0 blocks commit
P1 not-ready metrics do not get silently promoted
rollback scope does not touch upstream facts or downstream layers
```

Cross-layer boundary tests:

```text
N4 contract may reference source_action_confirmation_metric_id but not raw minute recomputation
N5 contract may consume N3 metric facts plus TriggerMatched but not opaque payload.action_confirmation as proof
N5 may not read raw minute rows to repair missing N3 metrics
```

## Validation Commands For Draft Artifacts

```text
python3 -m compileall scripts src tests
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_market_data_action_confirmation_metric_schema_draft.py'
python3 -m json.tool docs/N3_action_confirmation_projection_facts_schema_readiness.json
python3 -m json.tool docs/N3_action_confirmation_projection_facts_preflight_draft.json
python3 -m json.tool docs/N3_action_confirmation_projection_facts_tests_draft.json
git diff --check
```
