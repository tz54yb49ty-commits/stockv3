# N4 Projection Matcher v4 Enforcement Repair Contract

- result: `REPAIR_CONTRACT_PASS`
- layer_role: `runtime_control`
- generated_at: `2026-06-08T13:41:18+08:00`
- readonly_contract_only: `true`

## Breach Classification

`BLOCKED_V4_NONCOMPLIANT_P0`

Root cause: Legacy N4 projection matcher persisted active 30m projection window as trigger_period / primary_trigger_period / all_trigger_periods and emitted TriggerMatched without required v4 payload fields.

Rules breached:

- 30m must not enter trigger_period / triggered_periods / all_trigger_periods / primary_trigger_period
- 30m may only enter projection_period / projection_30m_type / trigger_mark_candidate
- TriggerMatched must include trigger_price / trigger_kind / n5_entry_allowed
- N5 may create action facts only from valid TriggerMatched

## Affected Runs

- `n4_projection_matcher_run_id`: `trigger_projection_matcher_execute_20260608_v13_index_all_until_0952`
- `n5_action_run_id`: `action_consumer_execute_20260608_v13_index_all_until_0952__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952`
- `n6_projection_run_id`: `user_projection_shadow_20260608_v13_index_all_until_0952__action_consumer_execute_20260608_v13_index_all_until_0952`

## Affected Counts

| scope | count |
|---|---:|
| N4 `TriggerMatched` | 320 |
| N4 `TriggerPendingMarketData` | 3600 |
| N4 `TriggerMatched_trigger_price_missing` | 320 |
| N4 `TriggerMatched_trigger_kind_missing` | 320 |
| N4 `TriggerMatched_n5_entry_allowed_missing` | 320 |
| N4 `TriggerMatched_payload_trigger_period_30m` | 320 |
| N4 `common_trigger_state_total` | 3920 |
| N4 `state_trigger_period_30m` | 3920 |
| N4 `state_primary_trigger_period_30m` | 3920 |
| N4 `state_all_trigger_periods_only_30m` | 3920 |
| N5 `ActionEligible` | 201 |
| N5 `ActionBlocked` | 0 |
| N5 `ActionExecuted` | 0 |
| N5 `ActionSkipped` | 0 |
| N5 `action_events_period_30m` | 201 |
| N5 `action_events_payload_trigger_price_missing` | 201 |
| N6 `user_signal_projection` | 201 |
| N6 `user_signal_card` | 201 |

## Rollback Chain Plan

Rollback order is mandatory: `N6 -> N5 -> N4`.

### Step 1: N6_user

- gate: `N6_ACTION_PROJECTION_20260608_V13_INDEX_ALL_UNTIL_0952_ROLLBACK_FINAL_GATE_REVIEW`
- rollback_sql_path: `sql/N6_projection_20260608_v13_index_all_until_0952_rollback.sql`
- expected delete scope:
  - user_notification_queue scoped rows=0
  - user_signal_card scoped rows=201
  - user_signal_projection scoped rows=201
  - user_projection_run scoped rows=1
- must block if:
  - user_signal_decision refs exist
  - user_sim_order/trade/position refs exist
  - voice/mobile/position refs exist

### Step 2: N5_action

- gate: `N5_ACTION_CONFIRMATION_20260608_V13_INDEX_ALL_UNTIL_0952_ROLLBACK_FINAL_GATE_REVIEW_AFTER_N6`
- rollback_sql_path: `sql/N5_action_confirmation_20260608_v13_index_all_until_0952_rollback.sql`
- expected delete scope:
  - common_action_run=1
  - common_action_quality_item=3600
  - stock_action_fact=195
  - index_action_fact=6
  - board_action_fact=0
  - common_action_event=201
  - N5 common_event_outbox=201
  - N5 consumer inbox/checkpoint rows for scoped N4 source
- must block if:
  - scoped N5 outbox delivered/delivering
  - downstream N6/user/sim/position refs exist
  - non-scoped consumer refs for source N4 run exist

### Step 3: N4_trigger

- gate: `N4_PROJECTION_MATCHER_20260608_V13_INDEX_ALL_UNTIL_0952_ROLLBACK_SQL_REGENERATION_GATE`
- current_rollback_sql_path: `sql/N4_projection_matcher_20260608_v13_index_all_until_0952_rollback.sql`
- required_new_rollback_sql_path: `sql/N4_projection_matcher_20260608_v13_index_all_until_0952_v4_breach_repair_rollback.sql`
- current_status: BLOCKED: current rollback is manual hard-fail only and lacks executable downstream-aware guard/delete plan.
- expected delete scope:
  - N4 common_event_outbox=3920
  - common_trigger_match=3920
  - common_trigger_state=3920
  - common_trigger_quality_item=10
  - N4 consumer inbox/checkpoint rows for N3 source events
  - common_trigger_run=1
- must block if:
  - N4 outbox delivered/delivering
  - N5 action_run/action_event/action_fact/outbox/inbox/checkpoint refs exist
  - N6/user/notification/sim/position/trade refs exist
  - non-scoped consumer refs exist


## Required SQL Repairs

- `sql/N4_projection_matcher_20260608_v13_index_all_until_0952_v4_breach_repair_rollback.sql`: generate new downstream-aware N4 rollback SQL from the existing manual guard file
  - before first DELETE/UPDATE guards:
    - assert N4 source outbox delivered/delivering count = 0
    - assert no N5 common_action_run/common_action_event/stock_action_fact/index_action_fact/board_action_fact refs for source_trigger_run_id
    - assert no N5 common_event_outbox/inbox/checkpoint refs for source_trigger_run_id after N5 rollback
    - assert no N6/user_signal_projection/user_signal_card/user_projection_run/user_notification_queue refs to N5 or N4
    - assert no delivery/notification/sim/position/order/trade refs
  - forbidden: `CASCADE, DROP, TRUNCATE, N3 fact deletes, N2/N1 mutation`

## Required Code Repairs

- `src/ashare_v3/trigger/projection_matcher.py`: Do not emit legacy projection matcher plans with trigger_period=30m as actionable trigger period. Route projection matching through v4 plan semantics or explicitly emit projection_period/projection_window fields while deriving trigger_period/triggered_periods from v4 Y/Q/M/W/D evidence.
  - acceptance: TriggerMatched plans have trigger_price, trigger_kind, n5_entry_allowed
  - acceptance: 30m absent from triggered_periods/all_trigger_periods/primary_trigger_period
  - acceptance: projection_30m_type and trigger_mark_candidate preserve 30m evidence
- `src/ashare_v3/trigger/projection_matcher_execute.py`: Before any write transaction inserts common_trigger_state/common_trigger_match/common_event_outbox, call v4 enforcement on every planned TriggerMatched row and BLOCK invalid rows before DB execution.
  - acceptance: invalid TriggerMatched raises V4EnforcementBlocked before INSERT/UPDATE
  - acceptance: upsert_trigger_state persists primary/all periods from v4 plan, not plan[trigger_period]=30m
  - acceptance: event envelope payload contains n5_entry_allowed/trigger_kind/trigger_price
- `src/ashare_v3/trigger/v4_enforcement.py`: Extend enforcement so 30m in trigger_period, primary_trigger_period, triggered_periods, or all_trigger_periods is a P0 violation for TriggerMatched.
  - acceptance: matched plan with any 30m trigger period field blocks
  - acceptance: projection_period=30m remains allowed
- `src/ashare_v3/action/execute.py`: Add/strengthen N5 input guard so invalid TriggerMatched is rejected before action fact/event planning: require trigger_price, trigger_kind, n5_entry_allowed=true, trigger_live=true, current_status=matched, runtime signal_type in B_BUY/S_SELL, and no 30m in trigger period fields.
  - acceptance: invalid N4 event produces BLOCKED/P0 or quality-only no action fact before write
  - acceptance: valid TriggerMatched path remains unchanged

## Required Tests

- tests/test_n4_v4_enforcement.py: add 30m trigger_period/primary/all periods blocking cases
- tests/test_trigger_projection_matcher.py or new tests/test_projection_matcher_v4_enforcement.py: projection matcher matched rows include v4 fields and keep 30m only as projection metadata
- tests/test_trigger_projection_matcher_execute.py: invalid plan blocks before cursor INSERT/UPDATE
- tests/test_action_execute.py: N5 rejects invalid TriggerMatched with missing price/n5_entry_allowed or trigger_period=30m before action fact creation
- rollback SQL static test: regenerated N4 rollback hard-fails before first DELETE and includes downstream guard strings

## Blocked Scope

- Direct N4 rollback with current manual guard SQL
- Direct N5 rollback before N6 rollback
- Direct N4/N5/N6 rerun before rollback chain complete
- Any execute in runtime_control

## Forbidden Scope Proof

- `rollback_executed` = `False`
- `n4_n5_n6_execute_performed` = `False`
- `db_business_write_performed` = `False`
- `outbox_inbox_checkpoint_consumed_or_updated` = `False`
- `worker_started` = `False`
- `delivery_push_voice_mobile` = `False`
- `sim_position_pnl_real_trade` = `False`
- `proposal_order_trade` = `False`
- `old_system_touched` = `False`

Recommended next gate: `N6_ACTION_PROJECTION_20260608_V13_INDEX_ALL_UNTIL_0952_ROLLBACK_FINAL_GATE_REVIEW`
