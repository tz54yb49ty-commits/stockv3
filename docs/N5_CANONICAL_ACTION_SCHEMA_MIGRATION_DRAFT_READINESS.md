# N5 Canonical Action Schema Migration Draft Readiness

Status: DRAFT_PASS

Layer role: N5_action

Date: 2026-05-28

This is a schema migration draft only:

```text
migration_executed=false
database_written=false
n4_outbox_consumed=false
inbox_checkpoint_written=false
action_fact_written=false
action_event_written=false
n5_outbox_written=false
n6_touched=false
worker_started=false
real_trade_touched=false
```

## Inputs

Authoritative canonical specs:

```text
docs/V3_TRIGGER_ACTION_RUNTIME_SPEC.md
docs/N4_N5_TRIGGER_ACTION_STATE_FLOW_v0.1.md
docs/N5_CANONICAL_ACTION_FLOW_v0.1.md
```

Dry-run contract gate evidence:

```text
docs/N5_20260528_CANONICAL_ACTION_DRY_RUN_CONTRACT_GATE_REPORT.md
docs/N5_20260528_canonical_action_dry_run_contract_gate_report.json
```

Schema migration review conclusion:

```text
review_pass=true
canonical_execute_blocked_until_schema_alignment=true
```

## Migration Files

```text
sql/025_n5_canonical_action_schema_alignment.sql
sql/025_n5_canonical_action_schema_alignment_rollback.sql
```

The draft is strictly compatible for existing rows: it adds nullable canonical columns, widens old CHECK constraints to a legacy plus canonical compatibility set, and keeps legacy N5 runtime evidence readable.

## Touched Tables

```text
stock_action_fact
index_action_fact
board_action_fact
common_action_event
```

Untouched:

```text
common_action_run
common_action_quality_item
common_event_outbox
common_event_inbox
common_event_consumer_checkpoint
common_position_state
common_position_event
N4/N3/N2/N6 tables
```

`common_action_run` and `common_action_quality_item` do not need new schema fields in this draft. Contract version, canonical mode, and detailed quality evidence can remain in `raw_json` / `details` until a later evidence table requirement appears.

`common_event_outbox` does not need migration. The common outbox schema does not carry a N5-specific event enum; canonical event validation is handled by N5 event models and by `common_action_event.event_type` compatibility.

## Additive Columns

The draft adds these nullable columns to all three action fact tables and to `common_action_event`:

```text
source_trigger_state_id
original_condition_key
trigger_mark_candidate
action_mark
action_state
confirmation_status
tracking_until
last_checked_minute_label
trace_json
action_policy
```

`action_policy` is included because canonical N5 payloads require it, but N5 still must not encode N6 display, voice, sim, mobile, or trade-intent policy.

## Constraints

Action fact `source_trigger_event_type` becomes compatible with:

```text
TriggerMatched
TriggerPendingMarketData
TriggerStateChanged
TriggerCleared
```

`TriggerCleared` remains legacy compatibility only. Canonical N5 runtime entry remains `TriggerMatched` only; `TriggerPendingMarketData` is quality-only and `TriggerStateChanged` is state-gate only.

`common_action_event.event_type` becomes compatible with legacy and canonical N5 events:

```text
ActionEvent
HintEvent
RiskEvent
PositionEvent
ActionEligible
ActionBlocked
ActionExecuted
ActionSkipped
```

Legacy event names are preserved for historical rows. New canonical runtime must use:

```text
ActionEligible
ActionBlocked
ActionExecuted
ActionSkipped
```

Canonical CHECK constraints are added for:

```text
action_state = eligible / blocked / executed / skipped / expired
confirmation_status = pending / passed / failed / expired / quality_only / state_gate / blocked_unclosed / confirmation_failed / pending_confirmation
action_mark = null / normal / 30m_volume / 30m_shrink
trigger_mark_candidate = null / normal / 30m_volume / 30m_shrink
trace_json = null or JSON object
```

`decision_status` is widened as compatibility metadata because current N5 planner still projects internal statuses such as `blocked_unclosed`, `quality_only`, `state_gate`, `confirmation_failed`, and `pending_confirmation`. Canonical truth should be read from `action_state`, `confirmation_status`, and `action_mark`.

## Legacy Signal Compatibility

The schema continues to permit legacy runtime signal strings for old rows:

```text
B_BUY_30M_VOL
S_SELL_30M_SHRINK
BUY_HINT
SELL_HINT
```

This is schema compatibility only. The canonical runner gate must still reject deprecated runtime signal_type values and allow only:

```text
B_BUY
S_SELL
```

`BUY_HINT / SELL_HINT` remain only `condition_key / original_condition_key / trace_json` provenance. N5 must not emit `HintEvent` for canonical runtime work.

## Rollback Strategy

Schema rollback is blocked if canonical event rows exist:

```text
ActionEligible
ActionBlocked
ActionExecuted
ActionSkipped
```

Schema rollback is also blocked if any additive canonical column is non-null in:

```text
stock_action_fact
index_action_fact
board_action_fact
common_action_event
```

If canonical business rows exist, the N5 business rollback by `action_run_id + source_trigger_run_id + consumer_name` must run first under a separate approved gate. The schema rollback draft touches only N5 schema objects and does not touch N4/N3/N2/N6.

## Remaining Gate

This draft does not authorize N5 business execute. After migration review and the migration final gate, N5 execute still requires a fresh execute preflight, a separate final gate, and explicit user confirmation.
