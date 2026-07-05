# N5 / N3T Action Confirmation Fastlane Contract

Status: contract and load-safe launchd plan draft.
Layer ownership: `runtime_control`, `N5_action`, `N3_market_data`.

This fastlane is a sidecar lane for low-latency N5 action confirmation. It does
not replace or modify existing N3 A1, B1, B2, N3P, or N4 runtime paths.

## Pipeline

```text
N4 TriggerMatched
-> N5 ActionEligible + active tracking
-> N5 active scope artifact
-> N3-C1 scoped closed 1m
-> N3T_C1_CLOSED metric
-> N5 ActionExecuted
```

## Launchd Labels

Only these new labels belong to the fastlane:

```text
com.ashare-v3.n5.action-intake-poller
com.ashare-v3.n3.c1-n3t-action-confirmation-poller
com.ashare-v3.n5.action-executed-poller
```

Existing labels remain protected and must not be reused or modified by this
lane:

```text
com.ashare-v3.n3.intraday-proof-poller
com.ashare-v3.n3.intraday-proof-poller.n3p
com.ashare-v3.n3.intraday-proof-poller.hint
com.ashare-v3.n4.proof-discovery-poller
```

Generated install/load launchd plan artifacts must keep:

```text
no Disabled=true
RunAtLoad=false
KeepAlive=false
no StartInterval before explicit activation
activation guard command shape only
```

The install/load plan is intentionally not the active runtime schedule. It only
registers the three protected labels in a load-safe guard shape. `Disabled=true`
is forbidden because it prevents bootstrap in the user launchd domain. Activation
requires a later explicit gate that provides real runtime inputs or a runner-side
runtime config parser. Launchd plists must not contain unresolved placeholders
such as `__FOR_TRADE_DATE__`, `__SOURCE_TRIGGER_RUN_ID__`,
`__SOURCE_METRIC_RUN_ID__`, `__ACTION_RUN_ID__`, `__CONSUMER_NAME__`, or
`__MAX_EVENTS__`.

Load-safe guard plists also must not embed `ASHARE_V3_POSTGRES_DSN` or any real
DSN/secret. The guard command does not need database access. A later activation
gate must define explicit config/env injection before enabling any DB-writing
runtime path.

## Active Activation Config

The active launchd plan is generated only from an explicit
`n5_n3t_fastlane_activation_config_v1` artifact. Active plists may pass the
activation config path and the lane phase, but must not embed dynamic source
identifiers:

```text
source_trigger_run_id
source_metric_run_id
action_run_id
consumer_name
```

The bounded runners must resolve those values from the activation config or a
future explicitly authorized safe resolver. If a required value is missing, the
runner fails closed before DB/runtime execution. Active plists still must not
contain unresolved `__...__` placeholders, DSN secrets, old N3/N4 labels, or old
N3/N4 runner paths.

Runtime activation uses a runner-side resolver:

```text
explicit runtime_inputs in activation config
-> safe read-only discovery when DSN is supplied by runtime env
-> fail closed with writes_enabled=false
```

The resolver may fill `source_trigger_run_id`, `source_metric_run_id`,
`action_run_id`, and `consumer_name`, but it must not open the write path.
`n5_action_intake` may run without a ready `source_metric_run_id` because it only
creates `ActionEligible` / active tracking and emits an N5 active-scope artifact.
Its read-only discovery may select the earliest pending N4 source run with either
formal `TriggerMatched` rows or inactive `TriggerStateChanged(trigger_live=false)`
rows. `TriggerMatched` remains the only `ActionEligible` entry. Inactive
`TriggerStateChanged` rows may only expire/remove matching active tracking by
state key; `TriggerStateChanged(trigger_live=true)` remains ignored.
`n5_action_executed` must resolve a matching N3T run before planning
`ActionExecuted`; if no `N3T_C1_CLOSED` metric is available, it fails closed and
does not fall back to N3P, B1, B2, time-ordered backlog, or legacy realtime
metrics. The discovered metric run id must match the same `for_trade_date`,
same `until_HHMM`, the same source-run lineage hash, and the Fastlane N3T run
family
`n3t_action_confirmation_metric_<YYYYMMDD>_until_<HHMM>__fastlane_sr_<source_run_hash>...`.

Active schedulers are read-mostly by default. They may plan from safe read-only
discovery, but they must not write an active-scope artifact unless an explicit
artifact-write authorization is present. In the default `--activation-config`
launchd path:

```text
writes_enabled=false
artifact_writes_enabled=false
active_scope_artifact_write_result.reason=artifact_write_disabled
```

The active worker policy gate must consume the trading-day monitor review before
declaring either bootstrap readiness or final automation verification. A loaded
scheduler or a small end-to-end sample is not sufficient for final verification.
If the monitor reports only exact-cover backlog, such as remaining N4
`TriggerMatched -> ActionEligible` intake rows or remaining
`ActionEligible -> N3T_C1_CLOSED` metric rows, the write-enabled activation may
bootstrap bounded drain workers, but `automatic_chain_verified` remains false
until a later monitor review proves exact cover.

A later write-enabled schedule must be authorized by an explicit
`execute_policy` object in the activation config. The current accepted policy
type is:

```text
n5_n3t_fastlane_write_enabled_execute_policy_v1
```

Generating that write-enabled activation config requires an
active-worker-policy review artifact with `result=PASS`,
`active_worker_write_enabled_ready=true`, no blockers, and no non-actionable
waiting reasons. Exact-cover waiting reasons are allowed because they represent
work for the bounded workers to drain. Non-trading, wrong-date, manual-gate, old
runner, N4 outbox, N6, full-market fallback, or legacy metric risks must still
block local config generation.

During actionable phases (`pre_open_call_auction_after_0925`, `trading`,
`lunch_break`, `post_close`), a review whose only waiting reason is
`waiting_for_n4_triggermatched` may authorize an `idle_open_scheduler`
activation. That state does not prove the final automatic chain and must not be
reported as full-chain verified; it only lets the three bounded workers stay
scheduled and fail closed/no-op until a formal N4 `TriggerMatched` appears. The
same waiting reason remains non-authorizing during `pre_open_before_0925`,
`closed_day_or_non_trading`, or wrong-date sessions.

For installed active schedulers that must be in place before the next actionable
phase, the config may explicitly set
`active_worker_policy_review_path_policy.authorization_timing=runtime_deferred_to_runner`.
That setting only permits local config/active-plan artifact generation while the
current review is still non-actionable. It does not authorize writes. Each
bounded runner must re-read the review path at runtime and fail closed until the
review itself is ready for the current phase.

The review must also surface whether this is final automation or only bootstrap
drain readiness. `active_worker_write_enabled_ready=true` is sufficient to
generate a write-enabled config for an exact-cover backlog drain, but
`full_chain_automatic_worker_ready=true` and
`activation_scope=full_chain_automatic_worker` are required before presenting the
lane as the finished automatic micro-batch worker.

This policy may enable N5 intake with `--execute --user-confirmed` and
`--write-active-scope-artifact` for formal `TriggerMatched` intake or inactive
`TriggerStateChanged(trigger_live=false)` cleanup. Only formal `TriggerMatched`
may create `ActionEligible`; inactive state changes may only expire/remove
matching tracking and update the active-scope artifact. The policy may enable the
N5 executed lane with `--execute --user-confirmed`, and may pass
`--execute --user-confirmed` to the N3 C1/N3T lane. The N3 lane is artifact-first.
Under explicit execute/user-confirmed activation it may materialize a missing
scoped C1 pull plan artifact from the
explicit N5 active scope snapshot. That plan generation is local artifact output
only: it must not pull market data, write DB rows, write canonical
`minute_bar_1m`, write outbox rows, or scan N5 DB. If an explicit current-day
source rows directory is configured, it may also materialize a missing local
`n3_c1_scoped_current_day_staging_v1` artifact from
`n3_c1_scoped_current_day_source_rows_v1`. The source rows must exact-cover the
pull plan scope and required physical/raw labels; extra rows, fake rows, legacy
lunch bridge rows, full-market fallback, DB writes, canonical C1 writes, and
outbox writes are blocked. If current-day staging is ready but metric_context is
missing, the shell may call only an explicitly injected
`n3_c1_n3t_metric_context_builder_adapter_v1`. That adapter must create local
metric_context artifacts from explicit staging and previous-day raw C1 context
and must report all DB, market, canonical C1, outbox, N5 scan, and N6
side-effect flags as false. Without that adapter, or if its output violates the
side-effect contract, the shell must fail closed; it must not synthesize
previous-day context. For launchd active schedules, the same builder contract may
be enabled by explicit activation-config fields:

```text
n3_c1_n3t_current_day_source_artifact_dir=<local explicit current-day source rows dir>
n3_c1_n3t_current_day_source_provider=mootdx_today_minute_adapter_v1
n3_c1_n3t_metric_context_source_artifact_dir=<local explicit source artifact dir>
n3_c1_n3t_previous_day_context_artifact_dir=<local explicit previous-day context dir>
n3_c1_n3t_previous_day_context_provider=postgres_previous_day_raw_c1_context_v1
n3_c1_n3t_n3t_writer_adapter=postgres_n3t_action_confirmation_metric_writer_v1
```

The current-day source provider is N3-owned and scoped by the generated pull
plan. It may pull only the explicit plan rows and required raw source labels, and
must not scan N5 DB, use full-market fallback, write DB rows, write canonical
`minute_bar_1m`, or touch outbox tables.

The runner may read only `n3_c1_n3t_metric_context_source_v1` files from the
metric-context source directory, match by target HHMM, and write the local
`n3_c1_scoped_closed_1m_artifact_v1` metric_context artifact. If the source
artifact is missing and an explicit previous-day context directory is configured,
the runner may first build a local `n3_c1_n3t_metric_context_source_v1` artifact
from the explicit current-day staging artifact plus
`n3_c1_n3t_previous_day_context_v1` rows. It must not query DB, pull market data,
scan N5 DB, or touch outbox tables while doing this local artifact construction.
When `postgres_previous_day_raw_c1_context_v1` is explicitly configured, the N3
lane may first prewarm a local `n3_c1_n3t_previous_day_context_v1` artifact by
reading only N3-owned previous-day preload rows from
`stock/index/board_minute_bar_1m` for the explicit active scope identities and
the physical labels already present in the scoped current-day staging artifact.
That prewarm must use read-only transaction semantics and must not write DB rows,
write canonical `minute_bar_1m`, touch outbox/inbox/checkpoint tables, scan N5
DB, call N4/N5/N6, use full-market fallback, or synthesize fake rows. The
generated rows must preserve raw source close label to physical C1 label trace
and inherit the lunch-boundary source-label policy.
If metric_context is ready but no real N3T writer adapter is injected, it must
return a no-write handoff:

```text
adapter_type=n3t_action_confirmation_metric_writer_handoff_v1
verdict=N3_C1_N3T_FASTLANE_N3T_WRITER_HANDOFF_READY
db_write_executed=false
writes_enabled=false
```

This prevents the active launchd schedule from silently treating the
artifact-first shell as a real N3T table writer while still letting the worker
advance to a deterministic handoff once all local inputs are ready. A later N3T
writer adapter patch must prove the N3T table write boundary before automatic N3T
DB writes are allowed.

If `n3_c1_n3t_n3t_writer_adapter=postgres_n3t_action_confirmation_metric_writer_v1`
is explicitly configured under the write-enabled execute policy, the N3 lane may
write only:

```text
stock_n3t_action_confirmation_metric
index_n3t_action_confirmation_metric
board_n3t_action_confirmation_metric
```

It must read the DSN only from runtime env, use idempotent insert semantics for
the deterministic N3T run id, and must not write canonical C1 tables,
common_event_outbox/inbox/checkpoint, N4/N5/N6 outbox rows, or N6 artifacts.

When the shell fails closed because local components are not ready, it must
still return a no-write `n3_c1_n3t_fastlane_scoped_executor_plan_v1` manifest.
The manifest lists the explicit active scope artifact path, target HHMM, planned
scoped C1 pull plan, current-day staging artifact, metric_context artifact, and
deterministic N3T metric run id. This gives runtime-control an auditable handoff
to the future scoped executor without pulling market data or writing DB/outbox
rows.
If those local artifacts already exist, the manifest also reports component
readiness:

```text
waiting_for_scoped_c1_plan
waiting_for_scoped_pull_staging
waiting_for_metric_context_artifact
metric_context_ready_for_n3t_execute_gate
blocked_local_component_contract_mismatch
```

This readiness check is artifact-only. It may hash and validate local JSON
artifacts, but it must not query DB state, pull market data, write N3T tables, or
update outbox/inbox/checkpoint rows.
When metric_context is ready, the manifest may also include an
`n3t_writer_plan_summary` produced by the pure N3T scoped metric helper. That
summary may contain plan status, row counts by target N3T table, and lineage
fields, but it must not include a DB adapter, launchd operation, market adapter,
or N3/N4/N5/N6 outbox write.
The runner may execute only when an explicit `n3t_action_confirmation_metric_writer_adapter_v1`
adapter is injected by a later execute gate. The adapter input is limited to
metric_context artifact path/hash, deterministic N3T run id, target table
counts, and lineage fields. The runner must validate that adapter output writes
only `stock/index/board_n3t_action_confirmation_metric`, keeps
`source_basis=N3T_C1_CLOSED`, `metric_role=action_confirmation`,
`proof_consumer=N5`, `not_n5_final_proof=false`, and does not write canonical C1
or any common outbox/inbox/checkpoint table.

When a later explicit gate authorizes local artifact output, artifact filenames
must be short and stable. They may include `for_trade_date`, the target
`until_HHMM`, and a short `source_run_hash`, but must not embed the full
`source_trigger_run_id` or full `action_run_id` in the filename. Fastlane N5
active-scope artifacts, N3 scoped C1 pull plans, current-day source rows,
staging artifacts, metric-context source artifacts, metric-context artifacts,
and N3T metric run ids must all be source-run scoped:

```text
for_trade_date + until_HHMM + source_run_hash
```

HHMM-only artifact or run-id names are forbidden for newly generated Fastlane
artifacts because ordinary and B2/hint-projection source runs can share the same
minute.

## Source-Run-Scoped Bounded Drain Orchestrator

Post-close Fastlane drain must be driven by a bounded one-shot orchestrator, not
by manual per-minute gates. The orchestrator artifact type is:

```text
n5_n3t_fastlane_source_run_scoped_bounded_drain_plan_v1
```

The orchestrator accepts:

```text
for_trade_date
consumer_name
source_run_family=ordinary
start_after
first_source_run
max_source_runs
max_runtime_seconds
```

`max_source_runs` and `max_runtime_seconds` are mandatory hard bounds. Missing
or non-positive bounds must fail before any child command is invoked. For the
20260703 post-close drain, ordinary source runs are processed in:

```text
event_time ASC, source_run_id ASC
```

Only formal N4 `TriggerMatched` source runs in the ordinary family are eligible.
B2 / hint-projection source runs must be excluded from the ordinary drain batch
even when they share the same HHMM. `TriggerStateChanged(trigger_live=true)` and
dead-letter N4 rows remain ignored. N4 outbox status is read-only and must never
be updated by the orchestrator or by the N5 Fastlane consumer.

Each selected source run expands to the fixed lane sequence:

```text
N5 intake
-> N5 active scope artifact
-> N3 C1/N3T from the explicit active scope artifact path
-> N5 executed from the matching source-run-scoped N3T_C1_CLOSED metric run id
```

Before the first selected source run, the orchestrator must run the configured
`n5_closeout_registration` pre-drain step. For the 20260703 ordinary backlog this
step registers the missing 09:43 Fastlane closeout artifact before 09:48 can
start. A plan that only records closeout metadata but has no executable
`pre_drain_steps` entry is not a valid bounded drain plan.

The N3 lane must receive the explicit `n5_active_scope_snapshot_v1` artifact path
for the selected source run. Passing only a directory is not sufficient for the
drain orchestrator, because it can accidentally re-scan older Fastlane scope
artifacts. The N3 lane still receives the artifact directory for compatibility,
but source-run-scoped drain commands must include the exact artifact path.

The deterministic N3T run id shape is:

```text
n3t_action_confirmation_metric_<YYYYMMDD>_until_<HHMM>__fastlane_sr_<source_run_hash>_raw_prevday_c1_amount_v1
```

The orchestrator may invoke existing layer-owned bounded runners under an
explicit execute gate, but it must not call old N3 A1/B1/B2/N3P/N4 runtime
runners, must not call `launchctl`, and must not touch N6.

Plan generation must not call `launchctl`, install plists, start workers, write
DB rows, or update outbox status. Loading the install-safe plists must not start
N3/N4/N5/N6 runtime work; if a label is manually invoked before activation, the
guard exits with `FASTLANE_ACTIVATION_REQUIRED`.

## Session Phase Policy

The fastlane runtime schedule is governed by:

```text
fastlane_session_phase_policy_v1
```

The policy is classified from:

```text
for_trade_date
trigger_time
current_exchange_time
trade_calendar.is_open
trading session boundary
```

The supported phases are:

```text
pre_open_before_0925
pre_open_call_auction_after_0925
trading
lunch_break
post_close
closed_day_or_non_trading
```

`pre_open_before_0925` is no-write for N5 intake. It may do read-only discovery,
plan-only checks, or fail-closed manifests, but it must not write
`ActionEligible`, active tracking, C1/N3T artifacts, or N3T metrics.

`pre_open_call_auction_after_0925` starts at 09:25. If N4 has already produced a
formal `TriggerMatched`, N5 intake may create `ActionEligible` and active
tracking under an explicit write-enabled gate. It may also export an N5 active
scope artifact. N3-C1/N3T must still wait for a closed current-day minute before
producing `source_basis=N3T_C1_CLOSED`, so N5 `ActionExecuted` remains blocked
until a matching N3T metric exists.

`trading` covers the active exchange sessions before the close. The intended
bounded schedule is:

```text
N5 intake: every 3 seconds
N3 C1/N3T: every 5 seconds, only from explicit N5 active scope artifact
N5 executed: every 3 seconds, only from matching N3T_C1_CLOSED metric
```

`lunch_break` may keep N5 intake active, but N3-C1/N3T must keep:

```text
source_gap_policy=session_boundary_source_gap_excluded_v1
```

It must not generate a fake raw 11:30 row and must not use a raw
13:00 -> physical 11:30 bridge.

`post_close` is drain mode. It processes remaining N4 pending rows in:

```text
event_time ASC, source_run_id ASC
```

Each source run must use an explicit scoped C1/N3T pass. Full-market fallback
remains forbidden.

`closed_day_or_non_trading` is read-only / fail-closed for current-day C1/N3T.
It must not pull market data, write N3T metrics, or write N5 action output.

N4 `common_event_outbox.status` is not the consumption-completion source for this
lane because N5 is not allowed to update N4 outbox rows. Completion must be
measured only through N5-owned evidence:

```text
common_event_inbox
common_event_consumer_checkpoint
common_action_tracking_state
common_event_outbox
```

Fastlane intake discovery must therefore exclude N4 events already present in
`common_event_inbox` for the Fastlane `consumer_name`; pending N4 outbox rows
remain read-only upstream evidence, not unconsumed proof by themselves.

## Active Worker Policy

The active scheduler must apply:

```text
fastlane_active_worker_policy_v1
```

The policy maps each `fastlane_session_phase_policy_v1` phase to one decision
per lane:

```text
n5_action_intake
n3_c1_n3t_action_confirmation
n5_action_executed
```

The default active scheduler state remains:

```text
writes_enabled=false
artifact_writes_enabled=false
```

Writes require a separate explicit execute/write gate with operator
confirmation. The policy never allows N5 to call N3 directly, never allows N3 to
scan N5 DB internals, never treats N4 outbox status as the consumed proof, and
never accepts legacy realtime/N3P/B1/B2 metric lineage as `ActionExecuted`
proof.

Phase-to-lane behavior:

```text
pre_open_before_0925:
  n5_action_intake = read_only_discovery
  n3_c1_n3t_action_confirmation = disabled
  n5_action_executed = disabled

pre_open_call_auction_after_0925:
  n5_action_intake = write_enabled_bounded only if formal TriggerMatched exists
  n3_c1_n3t_action_confirmation = wait_first_closed_minute
  n5_action_executed = wait_matching_n3t_metric

trading:
  n5_action_intake = write_enabled_bounded with formal TriggerMatched
  n3_c1_n3t_action_confirmation = write_enabled_bounded after closed minute
  n5_action_executed = write_enabled_bounded with matching N3T_C1_CLOSED metric

lunch_break:
  n5_action_intake = write_enabled_bounded
  n3_c1_n3t_action_confirmation = write_enabled_bounded with session gap policy
  n5_action_executed = write_enabled_bounded with matching N3T_C1_CLOSED metric

post_close:
  n5_action_intake = time_ordered drain by event_time ASC, source_run_id ASC
  n3_c1_n3t_action_confirmation = time_ordered scoped drain
  n5_action_executed = time_ordered metric drain only with matching N3T_C1_CLOSED metric

closed_day_or_non_trading:
  all lanes = fail_closed
```

Runner-side activation config resolver must fail closed before planning when a
requested write is outside the current phase decision. For example, before
09:25, an explicit active-scope artifact write request returns
`fastlane_worker_pre_open_before_0925_no_write`; during 09:25 call auction, the
N3 C1/N3T lane returns `first_closed_minute_not_available` until the first
closed minute is available. A call-auction active scope labeled `until_0925`
through `until_0929` is not a C1 physical minute target; once the first closed
minute is available, the N3 C1/N3T runner normalizes it to target `0930`.

After the lane is phase-allowed, the N3 C1/N3T runner must still apply a
per-artifact target-minute close gate. An active scope artifact for `until_HHMM`
is not eligible for scoped C1/N3T materialization until that target minute is
closed (`HHMM+1` for normal intraday minutes, with the 15:00 close-label treated
as the exchange close boundary). If the target is not closed, the scheduler
returns `target_minute_not_closed` as a quiet no-op and writes no pull plan,
staging artifact, metric context artifact, DB row, or outbox row.

Scheduled runners must keep expected phase-gate no-op output silent. For
`closed_day_or_non_trading` or waiting-for-closed-minute states, the launchd
path exits 0 without stdout when `--scheduler-quiet` is set, preventing a safe
fail-closed state from growing unbounded stdout/stderr logs. Non-noop blocked
states and actual execute manifests still print normally for diagnosis.

The trading-day monitor review can build chain evidence directly from read-only
DB summaries and explicit artifact directories. This replaces manual stitching
of `db_summary -> artifact_summary -> chain_evidence` during review, but it
does not authorize runtime execution, DB writes, or N4/N5 outbox status changes.

If the activation config does not contain a static `session_context`, runners
may use an explicit runtime policy:

```text
fastlane_runtime_clock_session_context_v1
```

That policy derives `current_exchange_time` from the runtime clock, or from a
test-only override in local contract tests. It must not embed DSN or secrets.
`trade_calendar_is_open` must be provided by explicit safe config or a later
approved read-only discovery policy; if it is missing, the runner fails closed
instead of guessing the exchange calendar. This keeps the active scheduler
phase-aware without requiring a hand-authored per-minute `session_context`.

## N5 Intake Boundary

N5 intake reads N4 pending outbox rows read-only.

Allowed input:

```text
TriggerMatched
TriggerStateChanged(trigger_live=false)
```

Ignored input:

```text
TriggerStateChanged(trigger_live=true)
```

Allowed writes when a later execute gate is explicitly authorized:

```text
common_action_tracking_state
common_event_outbox source_layer=N5_action event_type=ActionEligible
common_event_inbox for N5 consumer
common_event_consumer_checkpoint for N5 consumer
local n5_active_scope_snapshot_v1 artifact
```

Forbidden:

```text
N4 common_event_outbox status update
N3/N4/N6 facts or outbox writes
market data pull
N6 projection / voice / mobile / sim / real trade
```

## N3 C1 / N3T Boundary

N3 C1/N3T fastlane input must be an explicit
`n5_active_scope_snapshot_v1` artifact path/hash or an explicitly configured
artifact directory. N3 must not scan N5 DB internals.
If the active scheduler fires before any explicit active-scope artifact exists,
the N3 lane must fail closed with `active_scope_artifact_missing` and no side
effects.

Allowed N3 market context for N5:

```text
C1 scoped closed 1m context
N3T action-confirmation metric
```

Forbidden as N5 ActionExecuted proof:

```text
A1 previous-day cumulative authority
N3P
B1
B2
legacy realtime_action_confirmation_metric
N4 trigger_mark_candidate / projection_30m_* as final action_mark authority
```

N3T rows consumed by N5 must satisfy:

```text
source_basis=N3T_C1_CLOSED
metric_role=action_confirmation
proof_consumer=N5
not_n5_final_proof=false
metric_ready=true
metric_quality_status=passed
```

Artifact-first C1/N3T gates must not write canonical `minute_bar_1m`, must not
write N3/N4/N5/N6 outbox rows, and must not use full-market fallback.

## N5 Executed Boundary

N5 executed pass reads active N5 tracking from the Fastlane action-run family
only, plus matching N3T metric rows from the same Fastlane N3T run family. A
same-minute time-ordered/backlog N3T run is not valid ActionExecuted proof for
the active Fastlane lane.

Allowed writes when a later execute gate is explicitly authorized:

```text
common_action_tracking_state
common_event_outbox source_layer=N5_action event_type=ActionExecuted
```

It must not write N5 inbox/checkpoint during metric catch-up, must not update N4
outbox status, and must reject stale or non-time-matched N3T metric runs.

If matching `N3T_C1_CLOSED` metric rows are missing, N5 must return
`waiting_for_n3t_metric` and keep tracking active. It must not downgrade to N3P,
B1, B2, or legacy realtime proof.

## Write-Enabled Activation Config

The active launchd plan may only add `--execute` / `--user-confirmed` from an
explicit `n5_n3t_fastlane_activation_config_v1` artifact containing:

```text
session_context_policy=fastlane_runtime_clock_session_context_v1
execute_policy=n5_n3t_fastlane_write_enabled_execute_policy_v1
n3_c1_n3t_current_day_source_artifact_dir=<local explicit current-day source rows dir>
n3_c1_n3t_current_day_source_provider=mootdx_today_minute_adapter_v1
n3_c1_n3t_metric_context_source_artifact_dir=<local explicit source artifact dir>
n3_c1_n3t_previous_day_context_artifact_dir=<local explicit previous-day context dir>
n3_c1_n3t_previous_day_context_provider=postgres_previous_day_raw_c1_context_v1
n3_c1_n3t_n3t_writer_adapter=postgres_n3t_action_confirmation_metric_writer_v1
```

This config artifact is generated locally by the runtime-control helper. It must
not embed a DSN secret, unresolved `__...__` placeholders, launchctl commands, or
old N3/N4 runner references.

The generated config must either carry an `active_worker_policy_review_ref`
summary or carry an `active_worker_policy_review_path` with
`active_worker_policy_review_path_policy=fastlane_active_worker_policy_review_runtime_resolved_v1`.
The path form lets the active scheduler resolve the latest local review artifact
at runtime without embedding secrets or reloading launchd. Unless the path policy
also declares `authorization_timing=runtime_deferred_to_runner`, the resolved
review must still have `result=PASS`, `active_worker_write_enabled_ready=true`,
matching `for_trade_date`, no blockers, and only allowed waiting reasons. With
`runtime_deferred_to_runner`, active launchd plan generation may proceed, but its
report must mark `runtime_write_authorization=deferred_to_runner` and
`activation_scope=runtime_review_path_deferred`; this state must not be reported
as `full_chain_automatic_worker`.

The bounded runners must enforce the same authorization before any write-capable
activation-config path enters planning or execution. A normal write-enabled
`execute_policy` without a ready embedded review reference or ready
runtime-resolved review path must fail closed with `writes_enabled=false`; it
must not fall through to N5 planning, active-scope artifact writes, scoped
C1/N3T execution, DB writes, or outbox writes. When the path policy is
`authorization_timing=runtime_deferred_to_runner`, the runner may pass the
configuration guard after proving the review artifact is readable, date-matched,
secret-free, and blocker-free, but this does not authorize a write by itself.
The runner must then use read-only runtime discovery plus
`fastlane_session_phase_policy_v1` to decide the lane; missing N4 input, missing
closed minute, missing N3T metric, non-trading phase, or stale/mismatched input
must still fail closed with `writes_enabled=false`. Under `--scheduler-quiet`,
these authorization-wait states are clean scheduler no-ops; non-quiet CLI and
preflight still report the precise blocker.

The active plan report must also distinguish full-chain automation from staged
bootstrap. `automatic_worker_activation_ready=true` is allowed only when all of
the following readiness bits are true:

```text
n5_action_intake
n5_active_scope_artifact
n3_c1_n3t_action_confirmation
n5_action_executed
```

If any bit is false, the plan may still be a valid partial bootstrap, but its
`activation_scope` must be `partial_lane_bootstrap`; it must not be presented as
the final automatic Fastlane worker.

Before regenerating an active launchd plan for the final automatic worker, a
read-only full-chain preflight must inspect the write-enabled activation config.
It may pass only when `automatic_chain_verified=true`,
`bootstrap_mode=automatic_chain_verified`, and all four readiness bits above are
true. Exact-cover backlog bootstrap or any partial lane enablement must remain
blocked for automatic worker activation until a separate repair/review gate
promotes it to full-chain readiness.

The active launchd plan generator must support a full-chain guard for the final
automatic worker. With that guard enabled, plan generation must run the read-only
full-chain preflight first and fail closed before writing local plan artifacts if
the config is still a partial bootstrap.

Default generated authorization is staged:

```text
n5_action_intake.execute=true
n5_action_intake.write_active_scope_artifact=true
n5_action_executed.execute=true
n3_c1_n3t_action_confirmation.execute=false
```

N3 C1/N3T execute remains a separate explicit authorization unless the scoped
executor/writer adapter contract has been reviewed for the target runtime.
Generating this config does not install plists, reload launchd, start workers,
write DB rows, update outbox status, or touch N6.

## Implementation Surfaces

Contract and plan helper:

```text
src/ashare_v3/runtime_control/n5_n3t_fastlane.py
scripts/plan_n5_n3t_fastlane_launchd.py
```

N5 intake compatibility:

```text
scripts/run_n5_live_tracking_poller_once.py
```

N3 C1/N3T artifact-first shell:

```text
scripts/run_n3_c1_n3t_action_confirmation_fastlane_once.py
```

The current patch registers the isolated contract and local launchd plan shape.
Installing labels, loading disabled labels, activating scheduled execution,
running bounded smoke, and enabling any DB-writing execute path still require
separate explicit gates.
