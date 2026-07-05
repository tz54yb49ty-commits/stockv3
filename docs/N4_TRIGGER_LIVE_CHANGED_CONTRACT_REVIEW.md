# N4 TriggerLiveChanged Contract And Schema Impact Review

Status: CONTRACT_REVIEW_PASS_WITH_IMPLEMENTATION_BLOCKERS

Layer role: N4_trigger

Scope:

- Contract review only
- Schema impact review only
- Implementation plan only
- No database writes
- No migration execution
- No N4 execute
- No N5/N6
- No worker

## Inputs Reviewed

- `docs/V3_TRIGGER_ACTION_RUNTIME_SPEC.md`
- `docs/V3_N4_TRIGGER_LAYER_DEVELOPMENT_DESIGN.md`
- `sql/008_common_event_infra_schema.sql`
- `sql/010_trigger_layer_schema.sql`
- `src/ashare_v3/events/models.py`
- `src/ashare_v3/events/ids.py`
- `src/ashare_v3/trigger/event_factory.py`
- `src/ashare_v3/trigger/local_trigger_dry_run.py`
- `src/ashare_v3/trigger/standard_trigger_execute.py`
- `src/ashare_v3/trigger/projection_matcher_execute.py`
- `scripts/check_n4_contract.py`

## Review Result

`TriggerLiveChanged` is canonical in `docs/V3_TRIGGER_ACTION_RUNTIME_SPEC.md`, but it is not yet implemented in the N4 runtime contract.

Current implemented N4 event support:

```text
TriggerMatched
TriggerCleared
TriggerPendingMarketData
```

Canonical future N4 event support:

```text
TriggerMatched
TriggerPendingMarketData
TriggerLiveChanged
```

`TriggerCleared` is legacy for future canonical runtime work. It may remain in historical artifacts and compatibility paths, but new 20260528 canonical v2 execute should not rely on it as the primary live=false event.

## Schema Impact

### common_event_outbox

Runtime database constraint review:

```text
common_event_outbox allows TriggerLiveChanged.
```

The actual outbox constraints do not enforce a fixed N4 event-type enum. They enforce:

- `event_type !~ '^User'`
- N3-specific event-type allowlist only when `source_layer='N3_market_data'`
- stable non-empty ids / dedup / partition fields

Therefore the initial `TriggerLiveChanged` implementation does not require a `common_event_outbox` schema migration.

### common_trigger_state

`common_trigger_state` can express the canonical current state using existing fields:

```text
current_status in inactive / pending_market_data / matched / cleared
```

For canonical v2, new code should treat:

```text
inactive = not live
pending_market_data = live
matched = live
cleared = legacy compatibility only
```

No additive column is strictly required for v1 implementation. `trigger_live` can be derived:

```text
trigger_live = current_status IN ('pending_market_data', 'matched')
```

The runner must read previous state before upsert, then emit `TriggerLiveChanged` only if the derived live boolean changes.

Optional future additive columns, not required for first implementation:

```text
last_live_changed_event_id
last_live_changed_at
last_live_status
```

### common_trigger_match

`common_trigger_match.output_event_type` currently allows only:

```text
TriggerMatched
TriggerCleared
TriggerPendingMarketData
```

Recommendation:

```text
Do not record TriggerLiveChanged in common_trigger_match.
```

Reason:

- `common_trigger_match` is a trigger outcome fact table for matched/pending/legacy clear facts.
- `TriggerLiveChanged` is a state transition event derived from `common_trigger_state`.
- Adding `TriggerLiveChanged` to `common_trigger_match.output_event_type` would require a constraint change and blur match fact vs live-state notification.

Initial implementation should write:

```text
common_trigger_state
common_trigger_match for TriggerMatched / TriggerPendingMarketData only
common_event_outbox for TriggerMatched / TriggerPendingMarketData / TriggerLiveChanged
```

## TriggerLiveChanged Payload Contract

Required payload fields:

```text
run_id
source_event_id
source_event_type
source_run_id
source_output_event_id
source_output_event_type
source_trigger_match_id
trigger_state_id
trigger_live
previous_trigger_live
current_status
previous_status
signal_type
action_mark
original_condition_key
condition_key
direction
asset_kind
identity_key
trade_date
trigger_time
source_event_time
trigger_period
trigger_bucket
data_quality_status
match_basis
trace_json
```

Canonical payload rules:

- `signal_type` must be one of `B_BUY`, `S_SELL`, `BUY_HINT`, `SELL_HINT`.
- `action_mark` must be one of `normal`, `30m_volume`, `30m_shrink`.
- Deprecated runtime signal types `B_BUY_30M_VOL` and `S_SELL_30M_SHRINK` must not appear in `signal_type`.
- Original condition lineage remains in `original_condition_key` / `condition_key` / `trace_json`.

## Live Transition Rules

Derived live status:

```text
current_status=inactive             -> trigger_live=false
current_status=pending_market_data  -> trigger_live=true
current_status=matched              -> trigger_live=true
current_status=cleared              -> trigger_live=false, legacy compatibility only
```

`live=true` generation:

```text
Emit TriggerLiveChanged only when previous_trigger_live=false and trigger_live=true.
```

Examples:

- `inactive -> pending_market_data`: emit `TriggerLiveChanged(live=true)`
- `inactive -> matched`: emit `TriggerLiveChanged(live=true)`
- `pending_market_data -> matched`: do not emit `TriggerLiveChanged`; emit/keep `TriggerMatched`

`live=false` generation:

```text
Emit TriggerLiveChanged only when previous_trigger_live=true and trigger_live=false.
```

The first implementation should define the contract for `live=false` but not execute clear/inactivation unless a separate clear runner/preflight is approved.

## Dedup / Idempotency Impact

Current N4 helper `build_n4_trigger_dedup_key` does not include transition status. It is safe for `TriggerMatched` and `TriggerPendingMarketData`, but not sufficient for both `TriggerLiveChanged(live=true)` and future `TriggerLiveChanged(live=false)` at the same trigger grain.

Implementation must add a dedicated live-change dedup key helper, for example:

```text
N4_trigger
TriggerLiveChanged
asset_kind
identity_key
trade_date
direction
signal_type
action_mark
condition_key
trigger_bucket
previous_status
current_status
trigger_live
source_output_event_id
```

This prevents future `live=false` from overwriting the earlier `live=true` through `common_event_outbox` idempotency.

## N5 / N6 Consumption Boundary

Initial compatibility recommendation:

```text
N5 continues to consume TriggerMatched only for action eligibility.
N5 does not consume TriggerLiveChanged until a separate N5 contract is approved.
TriggerLiveChanged is emitted for user/display state consumers or future N5 live-state handling, but no N6 consume execute is authorized by this review.
```

This preserves existing N5 compatibility while adding canonical state notification.

## Rollback Boundary

Future execute rollback must be scoped by `trigger_execute_run_id` and must guard:

```text
no delivered/delivering TriggerLiveChanged outbox rows
no downstream inbox rows for the execute run
no downstream checkpoint refs for the execute run
```

Rollback may delete only N4 execute-run artifacts:

```text
common_event_outbox rows where source_layer='N4_trigger' and source_run_id=<execute_run_id>
common_trigger_match rows for <execute_run_id>
common_trigger_state rows for <execute_run_id>
common_trigger_quality_item rows for <execute_run_id>
common_trigger_run row for <execute_run_id>
```

Rollback must not touch:

```text
N2 condition tables
N3 facts / outbox
N5/N6/action/user/voice/mobile/sim/position
old synthetic outbox
```

## Implementation Plan

1. Update event contract code:
   - Add `TriggerLiveChanged` to N4 event validation.
   - Add payload validation for live fields.
   - Keep `TriggerCleared` as legacy compatibility only where historical code requires it.

2. Add a dedicated builder:
   - `build_n4_trigger_live_changed_event`
   - Dedicated live-change dedup key helper.

3. Update dry-run / preflight artifacts:
   - Report planned `TriggerLiveChanged` count separately.
   - For 20260528 v2 dry-run, expected first live count is likely equal to candidate state rows transitioning from inactive into pending/matched, but implementation must calculate from baseline state.

4. Update standard execute runner:
   - Read previous state before upsert.
   - Upsert `common_trigger_state`.
   - Insert `common_trigger_match` only for matched/pending.
   - Insert `TriggerMatched` / `TriggerPendingMarketData`.
   - Insert `TriggerLiveChanged` only when derived live boolean changes.

5. Update contract checker:
   - `scripts/check_n4_contract.py` should recognize canonical `TriggerLiveChanged`.
   - It should not require `TriggerLiveChanged` inside `common_trigger_match.output_event_type`.

6. Add tests:
   - `TriggerLiveChanged` accepted by N4 event model.
   - Payload missing `trigger_live` / previous status fails.
   - Deprecated runtime signal types rejected in canonical payload.
   - `inactive -> matched` emits live=true.
   - `inactive -> pending_market_data` emits live=true.
   - `pending_market_data -> matched` does not emit another live change.
   - Future `matched -> inactive` contract emits live=false only when clear runner is implemented.
   - `common_trigger_match` is not written for `TriggerLiveChanged`.
   - N5 consumer does not accept/consume `TriggerLiveChanged` in the initial compatibility path.

## Migration Recommendation

No schema migration is required for initial `TriggerLiveChanged` event-only implementation, because:

- `common_event_outbox` can store the event.
- `common_trigger_state` can express the live source state.
- `common_trigger_match` should not store live-change events.

No additive migration draft is created in this review.

If a future design insists on recording `TriggerLiveChanged` in `common_trigger_match.output_event_type`, that would require changing an existing CHECK constraint and should be handled as a separate schema migration review. That path is not recommended for the first implementation.

## Next Gate

Allowed next step:

```text
N4 TriggerLiveChanged implementation
```

Still blocked:

```text
20260528 N4 v2 standard trigger execute
N5/N6
worker
real trading
```
