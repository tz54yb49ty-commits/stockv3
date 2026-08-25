# N5 -> N6 Trigger Status Forward Contract v1

Status: registered_by_user_plan

Registered at: 2026-08-02

Ownership:

```text
governance_layer_role = runtime_control
producer_layer_role = N5_action
consumer_layer_role = N6_user
delivery_lane = n6_btrack_delivery_l2_n6_business_v1
contract_version = N5-N6-trigger-status-forward-v1
```

This registration is documentation and static-test work only:

```text
code_change=false
schema_migration=false
database_write=false
outbox_write=false
inbox_checkpoint_write=false
runtime_execute=false
service_operation=false
real_trade=false
```

It does not create a one-off runtime policy. The reusable L2 delivery lane owns
the later N6 implementation, PG16 migration, immutable Release, and read-only
acceptance gates.

## 1. User Brief And Scope

```text
page_or_feature = /n6/app/status-monitor current trigger status list
users = authenticated multi-user B-track principals
expected_behavior = ActionEligible inserts; live state change updates; inactive state change removes
affects_virtual_money_proposals_or_positions = false
```

The user-visible scope remains the existing effective monitor scope:

```text
principal monitor objects
UNION realtime monitor scope
UNION current holdings
```

N4 remains unchanged. Existing N6 signal/message/card projection tables,
consumer, inbox, checkpoint, and public behavior remain unchanged.

## 2. Status Forwarding Messages

The canonical N5 action outcomes remain exactly:

```text
ActionEligible
ActionBlocked
ActionExecuted
ActionSkipped
```

N5 may additionally emit these two non-action status-forwarding messages:

```text
TriggerStatusUpdated
TriggerStatusInvalidated
```

Both use:

```text
source_layer = N5_action
message_role = n6_trigger_status_projection_only
action_eligible_entry_allowed = false
```

They are written only to the N5 outbox. They must not write
`common_action_event`, change `action_state`, create action confirmation, or
enter the existing N6 signal/message/card projection consumer.

A status-forwarding message requires a verified earlier `ActionEligible` and
its original `TriggerMatched` entry. `TriggerStateChanged` without that entry
produces no status-forwarding message.

The event id is deterministic over:

```text
event_type
tracking_state_key
entry_trigger_event_id
source_trigger_state_changed_event_id
```

### 2.1 TriggerStatusUpdated

Source:

```text
TriggerStateChanged(trigger_live=true, current_status=matched)
```

It forwards current trigger context only. It must not replace the immutable
entry snapshot in the original `ActionEligible` or `ActionExecuted` event.
It forwards only the latest `trigger_price`, `trigger_period`, and
`triggered_periods` values.

### 2.2 TriggerStatusInvalidated

Source:

```text
TriggerStateChanged(trigger_live=false, current_status=inactive)
```

It is emitted after a verified `ActionEligible` even when N5 action tracking is
already terminal or executed. It does not delete N5/N4 history and does not
replace canonical `ActionSkipped(action_state=expired)` action semantics.
Its only projection effect is deleting the exact episode. The invalidate
operation-specific payload does not require trigger price or period fields,
because deletion depends only on the episode, grain, and audit keys. Source
values may be ignored when present; missing price data must not block
invalidation.

### 2.3 Required Payload

The common identity, episode, and audit payload is:

```text
contract_version
message_role
operation
trade_date
tracking_state_key
entry_trigger_event_id
action_eligible_event_id
source_trigger_event_id
asset_kind
identity_key
asset_code
asset_name
direction
signal_type
condition_key
trigger_time
action_eligible_entry_allowed
```

`operation` is `update` for `TriggerStatusUpdated` and `invalidate` for
`TriggerStatusInvalidated`.

`TriggerStatusUpdated` additionally requires:

```text
trigger_price
trigger_period
triggered_periods
trigger_live
current_status
```

`TriggerStatusInvalidated` has no operation-specific trigger price or period
requirement. For HINT provenance, the public update payload keeps
`trigger_period=30m` and must not expose the internal compatibility-only
`triggered_periods=[30m]`.

This change is limited to the new trigger-status branch. The immutable
`trigger_pct` in existing `ActionEligible` events and the existing
Signals/Messages/Cards projection contracts remain unchanged.

## 3. N6 Current-State Read Model

The L2 implementation adds one N6-owned relation:

```text
n6_trigger_status_current
```

The N6 current table, API, and page fields are fixed to:

```text
trigger_time
asset_kind
asset_code
asset_name
direction
trigger_price
trigger_period
triggered_periods
```

Storage grain is one trigger episode. The episode key contains the canonical
N4 lifecycle grain plus `entry_trigger_event_id`. It contains no principal or
user id; visibility is resolved at read time through the existing effective
monitor-scope query.

Mutation rules:

```text
ActionEligible -> idempotent insert
TriggerStatusUpdated -> update trigger_price, trigger_period,
                        triggered_periods and audit watermark only
TriggerStatusInvalidated -> delete the exact episode; missing delete is idempotent
missing update target -> fail closed; do not advance inbox/checkpoint
ActionExecuted -> no current-trigger-status mutation
```

The public list groups active episodes by:

```text
asset_kind + identity_key + direction
```

`trigger_time` is the earliest active entry time. Mutable values come from the
most recently updated active episode with a stable episode-key tie-breaker.
`triggered_periods` is the ordered union of active episodes. The visible row is
removed only after the last active episode in the group is invalidated.

The existing GET routes are reused:

```text
GET /api/n6/app/v1/status-monitor
GET /n6/app/status-monitor
```

The page label is `触发状态`. Its columns are trigger time, asset kind, code,
name, direction, trigger price, trigger period, and triggered periods. It
remains read-only and has no proposal, order, trade, voice, mobile, sim,
executor, or real-broker control.

## 4. Gate Sequence And Rollback Boundary

```text
runtime_control contract registration
-> independent N5_action implementation/offline tests
-> independent N6_user implementation/PG16 tests
-> independent N6_user full-filename migration with exact rollback
-> independent runtime_control immutable Web Release rebind
-> read-only acceptance
```

The first release has no scheduler, LaunchAgent, SSE, or persistent worker. N5
and N6 status processing is bounded run-once only.

### 4.1 Current-Day Bounded Recovery For 20260803

The explicitly authorized recovery identifier is:

```text
policy_id=n5_n6_trigger_status_current_day_bounded_recovery_20260803_v1
for_trade_date=20260803
n5_action_run_id=n5_trigger_status_forward_20260803_recovery_v1
n5_consumer_name=n5_trigger_status_forward_20260803_recovery_v1
n6_consumer_name=n6_trigger_status_projection_v1
n6_partition_key=trigger-status:20260803
n6_projection_run_id=n6_trigger_status_projection_20260803_recovery_v1
```

This is an exact recovery phase within the reusable L2 delivery lane; it does
not change the feature contract or authorize a general one-off runtime policy.
The `runtime_control` registration gate cannot execute either business-layer
step. An independent `N5_action` gate must pass first and may write only the two
status messages to `common_event_outbox`. A later independent `N6_user` gate may
consume at most 5000 frozen inputs into `n6_trigger_status_current` and its own
inbox/checkpoint. Both gates require fresh equality of the Web current date,
event trade date, and requested date. Date or lineage drift fails closed.

The recovery does not authorize migration, Release/Web/service/browser work,
LaunchAgent, scheduler, SSE, persistent worker, existing signal/message/card
projection changes, outbox status updates, Strategy Center, executor, voice,
mobile, sim, position, cash, or trade behavior. A transport `systemError` is not
retry authority; zero commit must be proven read-only before a separately
authorized supersession.

N5 rollback is scoped by action run, source trigger run, consumer, contract
version, and the two new event types. It must not touch N4 or existing Action*
facts/events.

N6 rollback is scoped by the complete migration filename, projection run,
consumer, and new relation. It must freeze a pre-rollback backup and prove the
existing signal/message/card tables and checkpoint are unchanged.

Browser acceptance requires a separate explicit authorization for the existing
logged-in tab. This contract does not grant browser control.

### 4.2 Scheduled Current-Day Convergence

After the bounded recovery and authenticated read-only page acceptance pass,
the reusable scheduler policy is:

```text
policy_id=n5_n6_trigger_status_scheduled_convergence_30s_v1
n5_label=com.ashare-v3.n5.trigger-status-forward-v1
n6_label=com.ashare-v3.n6.trigger-status-projection-v1
StartInterval=30
RunAtLoad=false
KeepAlive=false
```

Each tick is a bounded run-once from an immutable Release and owns an exact
singleton lock, report, and append-only history file. N5 reads the current
stable intraday lineage, proves the local date is open and equal to its
`for_trade_date`, and requires exactly one ActionEligible source authority. It
then invokes the existing status-forward-only contract and may only insert
idempotent `TriggerStatusUpdated` / `TriggerStatusInvalidated` rows into
`common_event_outbox`. N6 reads the same date authority and invokes only the
independent `n6_trigger_status_projection_v1` consumer and its per-date
checkpoint.

A closed local date is `NOOP`. An open-date mismatch, stale lineage, ambiguous
ActionEligible authority, invalid Release, or singleton contract failure is
`BLOCKED` with no database write. N5 activation and observation must pass before
N6 activation. The two asynchronous tasks may differ by one tick; steady-state
convergence target is at most 60 seconds.

This policy does not authorize migrations, Web rebind, SSE, modification of
existing Signals/Messages/Cards or their consumers/checkpoints, outbox status
updates, N1-N4 writes, Strategy Center, executor, voice, mobile, sim, position,
cash, proposal, order, broker, or real-trade effects. Rollback stops only the
two exact labels and preserves already projected status data.

### 4.3 N5 Scheduled Timeout Recovery

The exact one-time recovery policy is:

```text
policy_id=n5_trigger_status_scheduler_timeout_recovery_20260804_v1
label=com.ashare-v3.n5.trigger-status-forward-v1
incident_started_at=2026-08-03T15:06:15.521903+08:00
incident_reason=QueryCanceled:canceling statement due to statement timeout
recovery_trade_date=20260804
```

Read-only evidence proves that the incident happened with no new N4 lifecycle
input after the preceding zero-write PASS and no N5 status row in the incident
window. The current-day offline plan remains valid and includes the exact
`TriggerStatusInvalidated` for `board:TDX:881139`. This is a correction of a
failure-phase classification, not retry authority derived from `systemError`.

The N5 implementation must classify plan-provider failures before any writer
call as `BLOCKED_CORE_PLAN_READ` with `requires_post_check=false`. Only an
exception raised by the writer/commit phase may become
`BLOCKED_COMMIT_UNKNOWN` with `requires_post_check=true`. A real write-phase
ambiguity must create a separate immutable incident artifact; ordinary rolling
reports may reference but never overwrite it.

The implementation diff is limited to the two N5 status-forward runners and
their focused test. No schema, index, migration, N6 code, Web/API, scheduler
shape, or status payload changes are allowed. A later independent `N5_action`
gate may build one immutable Release and perform one bootout/bootstrap of the
exact N5 label, with no kickstart or retry. The first natural tick may emit only
the two idempotent status message types. N6 is acceptance-only and remains a
separate gate.

### 4.4 20260804 Recovery Closeout Registration

The separately gated recovery is closed with result `PASS`:

```text
policy_id=n5_trigger_status_scheduler_timeout_recovery_20260804_v1
n5_commit=aed4a306c8bc520fa5679af58781a59253d8436a
n5_tree=6e26dd8f3dd3ea8f6f219074f3fc13a58f801cd0
n5_first_tick=241 (TriggerStatusUpdated=31, TriggerStatusInvalidated=210)
n5_second_tick=0
exact_881139_invalidation_outbox_id=4114073
exact_881139_invalidation_event_id=evt_6f8fd9464fbfc0f4ecc385273d96ce94843557be
n6_checkpoint=4114149
n6_eligible_highwater=4114149
n6_lag=0
n6_convergence_seconds=21.411721
n6_current_episode_881139=0
```

Ten natural N5 ticks and ten natural N6 ticks all passed. After the first
recovery tick, subsequent ticks were idempotent zero-write/zero-select ticks;
there was no post-check requirement or checkpoint regression. The 20260804
Signals, Cards, Decisions, and non-trigger checkpoint fingerprints were
unchanged, as were the accepted 20260731 history baseline. Authenticated
GET/reload/read-only DOM acceptance showed 145 visible rows, the fixed eight
columns, no `881139`, and no `trigger_pct`.

The frozen RAG artifact is:

```text
docs/N5_N6_TRIGGER_STATUS_20260804_TIMEOUT_RECOVERY_CLOSEOUT.json
```

Its source report hashes are the evidence identity. This registration records
the accepted historical closeout only. It does not authorize a rerun, database
connection, Release/plist/service operation, browser action, N1-N6 write, or
trade operation, and it does not replace fresh read-only verification for a
future live-runtime status question.

### 4.7 20260824 881002 Authenticated Browser Acceptance Supplement

After the runtime closeout above, the user separately authorized only the
existing logged-in Safari N6 tab, GET/reload, and read-only DOM inspection. The
tab was switched into view and reloaded exactly once. The refreshed
`/n6/app/status-monitor` page resolved trade date `20260824`, displayed
`admin · 管理员`, and reported 189 current trigger rows. Its exact eight-cell row
for `board:TDX:881002` was:

```text
2026-08-24 09:34:00+08 | 板块 | 881002 | 煤炭开采 | 买向观察 |
2550.000000 | D | D
```

The page retained the fixed eight-column contract and exposed no
`trigger_pct` column. The browser operation budget was one tab switch and one
reload, with zero business-button clicks, POST requests, form submissions, or
DOM mutations. This acceptance performed no database, Release/plist, service,
runtime execute, N1-N6 business, or trade operation.

The original closeout artifact remains byte-preserved and correctly records
that browser acceptance had not yet run at the time it was created. The later
append-only supplement is:

```text
docs/N5_N6_TRIGGER_STATUS_20260824_881002_AUTHENTICATED_BROWSER_ACCEPTANCE_SUPPLEMENT.json
```

The combined status is
`authenticated_browser_acceptance=PASS`, `recovery_status=CLOSED`, and
`rerun_required=false`. This supplement does not authorize another browser
session or replace fresh live verification for a future runtime question.

### 4.5 20260824 N6 Late-Commit Gap Recovery Registration

The exact forward-only recovery policy is:

```text
policy_id=n6_trigger_status_late_commit_gap_recovery_20260824_v1
phase_id=trigger_status_n6_late_commit_gap_recovery_20260824
for_trade_date=20260824
consumer_name=n6_trigger_status_projection_v1
partition_key=trigger-status:20260824
label=com.ashare-v3.n6.trigger-status-projection-v1
```

The registered read-only incident snapshot shows that
`board:TDX:881002` has N4 `TriggerMatched` outbox `4221256` and N5
`ActionEligible` outbox `4221622`, but no N6 trigger-status inbox/current row.
The consumer checkpoint had already advanced to `4221894`. There are 249
unprocessed `ActionEligible` rows at or below that checkpoint in the frozen
snapshot (`4221396..4221644`). This is a batch completeness defect: outbox
sequence allocation order is not transaction commit-visibility order.

The N6 implementation must select the same-date, N5-owned, six allowed event
types that do not yet have a `processed` inbox row for this consumer, ordered
by `outbox_id ASC`. Checkpoint advancement is audit-only and must be monotonic:
processing a lower-id gap must not lower the existing checkpoint.
`missing_status_update_target` remains a whole-batch fail-closed condition.

A deterministic `TriggerStatusProjectionError` must be reported as:

```text
failure_phase=projection_rolled_back
verdict=BLOCKED_CORE_PROJECTION_INPUT
requires_post_check=false
```

Only actual writer/commit ambiguity may report `BLOCKED_COMMIT_UNKNOWN` with
`requires_post_check=true` and an immutable incident file. The new Release
must use a fresh rolling-report path so that the reviewed legacy sticky report
remains append-only evidence rather than blocking the corrected runner.

This `runtime_control` gate only registers the contract. A later independent
`N6_user` gate must first prove the 09:43 failed batch has zero committed
checkpoint/inbox/current mutation using SELECT-only evidence. If the local open
date is no longer exactly `20260824`, it must stop and register a historical
bounded recovery instead. If accepted, it may build one immutable Release and
perform one bootout/bootstrap of only the exact N6 trigger-status label, then
observe at most three natural recovery ticks and ten stability ticks. It must
not kickstart, manually invoke the runner, reset a checkpoint, insert an
episode manually, or retry.

No N4/N5 code or data, schema, index, migration, Web/API, existing
Signals/Messages/Cards/Decisions, other consumer/checkpoint, outbox status,
Strategy Center, executor, voice, mobile, sim, cash, position, proposal, order,
broker, or trade path is authorized. Release rollback may restore only the
frozen N6 label once. Valid status data is preserved; database rollback needs
separate authorization and a pre-rollback backup.

The registration evidence artifact is:

```text
docs/N5_N6_TRIGGER_STATUS_20260824_LATE_COMMIT_GAP_RECOVERY_REGISTRATION.json
```

### 4.6 20260824 N6 Late-Commit Gap Recovery Closeout

The independent `N6_user` implementation and bounded recovery gate completed
with the exact status:

```text
FUNCTIONAL_PASS_WITH_ATTRIBUTED_NATURAL_DRIFT_EVIDENCE_GAP
```

The repaired consumer commit/tree are
`e98aa6887dcbbe92d0cdf664ba700fa2f49c9059` /
`41e158492ea7e6c1dc407bf51747c303b9f003dc`. One immutable Release was built
and only `com.ashare-v3.n6.trigger-status-projection-v1` was rebound once.
There was no kickstart, manual runner, retry, N5 operation, Web operation,
schema/index migration, manual checkpoint/episode mutation, browser action, or
trade action.

Natural recovery used two of the three allowed ticks. The first selected 2697
events and advanced checkpoint `4221894 -> 4226270`; the second selected two
events and advanced it to `4226272`. Final read-only evidence at checkpoint
`4226413` records both current-day candidate count and low-ID gap count as zero.
Ten subsequent natural ticks all passed with no post-check requirement, sticky
blocker, replay skip, or checkpoint regression.

While N4 still reported `board:TDX:881002` live, the N6 current projection held
exactly one episode for `煤炭开采`, and the `ccf` effective-scope join count was
one. This is functional recovery acceptance; authenticated browser acceptance
was not run and remains optional after new explicit authorization.

Protected evidence is deliberately bounded. Every frozen pre-existing Signals,
Cards, shared-message, and Decisions prefix hash remained byte-identical. The
mandatory natural observation window also produced 44 independently attributed
Signals, 44 Cards, and 44 shared-message appends and advanced two untouched
consumer checkpoints. Therefore literal whole-table/non-trigger-checkpoint hash
equality is not claimed. The missing `openpyxl` broader-runtime-suite result is
also retained as a test-environment evidence gap; focused system-Python tests
passed 35 and exact-runtime runner tests passed 15.

The frozen RAG closeout artifact is:

```text
docs/N5_N6_TRIGGER_STATUS_20260824_LATE_COMMIT_GAP_RECOVERY_CLOSEOUT.json
```

Its only runtime report authority is the immutable Gate2 report
`/private/tmp/N6_TRIGGER_STATUS_LATE_COMMIT_GAP_RECOVERY_20260824_GATE2_FINAL.json`
with SHA-256
`66aa7e8391a1fb77c251665b8871515d64d7717e56c70db613d5bbb3c7675010`.
`rerun_required=false`. This historical closeout does not authorize a rerun,
database connection, Release/plist/service operation, browser action, N1-N6
write, or trade operation, and it does not replace fresh evidence for a later
live-runtime question.
