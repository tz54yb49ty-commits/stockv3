# N3 Action-Confirmation Projection Facts Schema Readiness Draft

Status: DRAFT_PASS

Generated at: 2026-06-02

Layer role: N3_market_data

This draft implements the N3 side of `docs/V3_N3_N4_N5_ACTION_CONFIRMATION_RULE_SPEC.md`. It does not execute a migration, write database rows, pull market data, consume outbox, enter N4/N5/N6, or start a worker.

## Decision

Use three N3 physical fact tables:

```text
stock_action_confirmation_projection_metric
index_action_confirmation_projection_metric
board_action_confirmation_projection_metric
```

This keeps stock / index / board physically separated and avoids overloading the existing 30m `*_realtime_projection_metric` facts. The existing B2 projection facts remain 30m trigger-marker evidence. These new tables are the canonical N3 metric source for action confirmation.

## Schema Draft

Migration draft:

```text
sql/032_n3_action_confirmation_metric_schema.sql
```

Schema rollback draft:

```text
sql/032_n3_action_confirmation_metric_schema_rollback.sql
```

Business rollback draft:

```text
sql/N3_action_confirmation_projection_metric_business_rollback.sql
```

The schema draft is strictly additive:

```text
CREATE TABLE IF NOT EXISTS only
CREATE INDEX IF NOT EXISTS only
no ALTER old tables
no INSERT / UPDATE / DELETE / TRUNCATE
no outbox / inbox / checkpoint changes
no N4 / N5 / N6 changes
```

## Required Fields Covered

Identity and lineage:

```text
action_confirmation_metric_id
projection_run_id
projection_schema_version
source_condition_run_id
source_subscription_run_id
source_snapshot_run_id
source_snapshot_id
source_snapshot_event_id
source_today_minute_run_id
source_previous_day_minute_run_id
asset_kind
identity_key
for_trade_date
trade_date
metric_time
metric_minute_label
source_fact_ids
source_minute_refs
previous_day_minute_refs
raw_json
```

Current price:

```text
current_price
current_price_source
current_price_time
```

Previous-period body high/low:

```text
previous_120m_body_high / previous_120m_body_low
previous_30m_body_high / previous_30m_body_low
previous_5m_body_high / previous_5m_body_low
previous_1m_body_high / previous_1m_body_low
```

Amount metrics:

```text
current_1m_amount
previous_1m_amount
current_5m_virtual_amount
previous_5m_full_amount
```

First-period boundary fields:

```text
is_first_1m_of_day
is_first_5m_of_day
is_first_30m_of_day
is_first_120m_of_day
first_1m_amount_default_pass
first_5m_amount_default_pass
previous_1m_period_source
previous_5m_period_source
previous_30m_period_source
previous_120m_period_source
boundary_policy_version
```

Quality and readiness:

```text
metric_quality_status
metric_ready
calculation_config_hash
```

Convenience pass flags are nullable and derived only:

```text
buy_120m_price_pass / buy_30m_price_pass / buy_5m_price_pass / buy_5m_amount_pass / buy_1m_price_pass / buy_1m_amount_pass
sell_120m_price_pass / sell_30m_price_pass / sell_5m_price_pass / sell_5m_amount_pass / sell_1m_price_pass / sell_1m_amount_pass
```

## Readiness Gates

Future preflight must block with P0 if:

```text
schema tables missing
source B1 snapshot run not passed
source today minute run not passed
source previous-day minute run not passed
projection_run_id already exists
scoped outbox/inbox/checkpoint refs are nonzero
metric_ready=true rows could not satisfy required current price / previous body / amount / boundary trace fields
source_fact_ids or source_minute_refs are missing for ready metrics
previous_day_minute_refs are missing when a ready metric uses previous_trade_date_last_period
```

## Metric Ready Trace Refs Strategy

Decision: DB hard guard plus preflight P0.

When `metric_ready=true`, the schema CHECK requires:

```text
source_fact_ids is a non-empty JSON object
source_minute_refs is a non-empty JSON array
previous_day_minute_refs is a non-empty JSON array when any previous_*_period_source uses previous_trade_date_last_period
```

Future preflight must still calculate trace completeness and block P0 before execute if a ready candidate cannot satisfy the same trace contract. The DB guard is the final safety net; it is not a substitute for preflight diagnostics.

Future execute may write only:

```text
common_market_data_run
common_market_data_quality_item
stock_action_confirmation_projection_metric
index_action_confirmation_projection_metric
board_action_confirmation_projection_metric
```

Future execute must not write:

```text
common_event_outbox
common_event_inbox
common_event_consumer_checkpoint
realtime_daily_snapshot
minute_bar_1m
realtime_projection_metric
closed_30m_summary
closed_30m_signal_enrichment
trigger/action/user/voice/mobile/sim/position/real-trade tables
```

## N3 Ownership Proof

N3 owns the action-confirmation metric facts because the calculation depends on current price, minute windows, previous-day boundary windows, source fact ids, and metric quality. N4 and N5 must consume these standard metric facts and must not reconstruct 1m / 5m / 30m / 120m values from raw minute rows.

N3 still does not decide:

```text
TriggerMatched
final action confirmation
action_state
action_mark
user display policy
voice/mobile/sim/real trade
```

## Rollback

Schema rollback is allowed only while all three metric tables have row_count=0. The schema rollback SQL uses a `DO $$ ... RAISE EXCEPTION ... $$` guard and hard-fails if any stock / index / board metric table is non-empty.

Business rollback is by `projection_run_id` and clears only:

```text
stock/index/board_action_confirmation_projection_metric
common_market_data_quality_item
common_market_data_run
```

Business rollback must be blocked if scoped outbox, inbox, or checkpoint refs exist. The business rollback SQL uses a `DO $$ ... RAISE EXCEPTION ... $$` guard and hard-fails before any DELETE when scoped outbox / inbox / checkpoint refs are nonzero.

## Next Gate

Allowed next: migration final gate review for `sql/032_n3_action_confirmation_metric_schema.sql`.

Not allowed without separate confirmation: execute migration, write business rows, run N4/N5/N6, consume outbox, or start worker.
