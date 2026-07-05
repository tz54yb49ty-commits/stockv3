# N4 Trigger Rule v4 Enforcement Contract

Status: CONTRACT_PASS

Layer role: `N4_trigger`

Scope: strict pre-write validation for N4 `TriggerMatched` persistence.

Authoritative spec:

- `docs/N4_TRIGGER_RULE_SPEC_v4.md`
- `docs/N4_TRIGGER_RULE_SPEC_v4_TRACEABILITY.md`
- `docs/N4_TRIGGER_RULE_SPEC_v4_APPROVED_CHANGES.json`

This contract does not authorize N4 execute. It only defines P0 enforcement
that every future N4 v4 execute path must pass before any DB write.

## P0 Guards

### N4-V4-P0-001 Required TriggerMatched Fields

Every persisted `TriggerMatched` plan must contain:

- `trigger_price`
- `trigger_kind`
- `triggered_periods`
- `all_trigger_periods`
- `primary_trigger_period`
- `n5_entry_allowed`
- `trigger_live`
- `current_status`
- `data_quality_status`
- `match_basis`

Missing or blank required fields BLOCK before DB write.

### N4-V4-P0-002 Time Boundary

The validator must BLOCK before DB write when:

- `event_time > created_at`
- `trigger_time > source_confirmed_time`
- projection `trigger_time > approved_projection_closed_label_used`

### N4-V4-P0-003 FULL Semantic Whitelist

`BUY:FULL` and `SELL:FULL` may write `TriggerMatched` only when all FULL
semantic whitelist fields are valid:

- `condition_key` and `original_condition_key` are the same FULL key.
- `trigger_kind=trigger`.
- `trigger_period=D`.
- `triggered_periods=["D"]`.
- `all_trigger_periods=["D"]`.
- `primary_trigger_period=D`.
- `trigger_mark_candidate=normal`.
- `projection_30m_flag=false`.
- `projection_30m_type=none`.
- `trigger_price` is non-null and traceable to an approved N3 source.

Any FULL payload outside this whitelist BLOCKS before DB write. N4 still must
not discover FULL from ordinary BUY/SELL rows by itself; the FULL key must come
from N2-localized context.

### N4-V4-P0-004 N5 Entry Contract

N5 entry is valid only when all are true:

- `event_type=TriggerMatched`
- `signal_type in (B_BUY, S_SELL)`
- `current_status=matched`
- `trigger_live=true`
- `n5_entry_allowed=true`

Any other combination BLOCKS before DB write.

### N4-V4-P0-005 Price Source

`trigger_price` must be materialized as a first-class plan/fact field and must
be traceable to an approved N3 source:

- N3 reviewed realtime snapshot, or
- approved N3 projection fact.

It is not enough for price to exist only inside `raw_json` or UI payload.

### N4-V4-P0-006 Runtime Signal Type

Runtime `signal_type` only allows:

- `B_BUY`
- `S_SELL`

`BUY_HINT`, `SELL_HINT`, `B_BUY_30M_VOL`, and `S_SELL_30M_SHRINK` are trace
only and must not be persisted as runtime `signal_type`.

### N4-V4-P0-007 30m / Hint Boundary

`BUY_HINT` and `SELL_HINT` must be represented through:

- `condition_key`
- `original_condition_key`
- `trigger_kind=hint`

30m evidence must be represented through:

- `projection_30m_type`
- `trigger_mark_candidate`

30m and hint semantics must not be encoded as runtime `signal_type`.

## Enforcement Points

- `src/ashare_v3/trigger/v4_enforcement.py`
- `scripts/run_n4_20260605_matched_only_execute_once.py`
- `src/ashare_v3/trigger/rule_v4_execute.py`
- `src/ashare_v3/trigger/standard_trigger_execute.py`

## Write Boundary

This contract does not permit any write by itself. Future execute gates remain
separate and must still require:

- clean preflight,
- scoped rollback SQL,
- user final confirmation,
- `--execute --user-confirmed`.

## Current 20260605 Status

The previously rolled-back 20260605 matched-only execute path is now blocked by
the new enforcement checks until a corrected dry-run regenerates compliant v4
plans.

Current stale candidate evidence:

- candidate matched plans: `1537`
- persisted write plans after strict N5 entry guard: `0`
- invalid N5 entry candidates: `1537`
- stale violations include missing `trigger_price`, missing `trigger_kind`,
  missing `triggered_periods`, missing `n5_entry_allowed`, historical FULL
  candidates that predate the FULL whitelist repair, and future `event_time`
  candidates.

Next allowed gate: `N4 corrected dry-run gate`.
