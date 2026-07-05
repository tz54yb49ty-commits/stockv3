# N6 UI Readonly Action Card Adapter Dry Run

Status: DRY_RUN_BLOCKED_BY_CURRENT_IMPLEMENTATION

Layer role: N6_user

Date: 2026-06-06

This dry-run is read-only. It probes the current DB and current Track A UI read
path without writing business data, consuming or updating N5 outbox, creating
notification queue rows, starting workers, delivering/pushing/voice/mobile,
running sim/position/PnL/real trade, generating proposal/order/trade, or
modifying B-track.

## 1. DB Card Proof

```text
target_database=ashare_v3
target_user=ashare_v3_user
target_host=127.0.0.1
target_port=5432
user_projection_run.status=passed
user_projection_run=1
user_signal_projection=605
user_signal_card=605
user_notification_queue=0
```

Action-card distribution:

```text
ActionExecuted / executed / action_confirmed = 1
ActionBlocked / blocked / blocked = 604
```

Blocked reason distribution:

```text
price_confirmation_failed=305
metric_missing=289
amount_confirmation_failed=10
```

N5 outbox proof:

```text
ActionExecuted pending=1
ActionBlocked pending=604
delivered=0
delivering=0
status_updated=false
```

Forbidden refs:

```text
delivery_attempt_refs=0
N6 projection-run outbox refs=0
user_signal_decision=0
user_sim_order/trade/position=0/0/0
n6_virtual_order/trade/position/pnl refs=0/0/0/0
proposal tables absent
```

## 2. Current API Probe

Current implementation result:

```text
GET /api/n6/ui/v1/signals equivalent repository read with empty filters:
  result=BLOCKED
  error=AmbiguousParameter could not determine data type of parameter $2

GET /api/n6/ui/v1/signals equivalent repository read with normal filters:
  action_state=blocked
  blocked_reason=price_confirmation_failed
  result=BLOCKED
  error=AmbiguousParameter could not determine data type of parameter $2
```

The probe confirms the P0 is in the read query, not in the projection rows.

## 3. Current Detail Wording Probe

Current implementation state:

```text
proposal_eligibility_model(ActionExecuted/executed).behavior=proposal_candidate
```

This is a P1 wording blocker for Track A. It must be changed to
`projection_only`, `display_only`, or `no_order_no_trade` for the administrator
read-only console.

## 4. Planned Adapter Dry Run Expectations

After implementation, the same dry-run must show:

```text
empty filters result=PASS
normal filters result=PASS
unfiltered cards returned=605
ActionExecuted cards=1
ActionBlocked cards=604
blocked_reason distribution=305/289/10
proposal_eligibility behavior for ActionExecuted != proposal_candidate
proposal_generated=false
order_generated=false
trade_generated=false
position_updated=false
pnl_updated=false
```

## 5. Route Method Scan Expectations

Track A UI v1 must remain GET-only for read APIs:

```text
GET /api/n6/ui/v1/signals
GET /api/n6/ui/v1/signals/{user_signal_projection_id}
GET /api/n6/ui/v1/dashboard/metrics
GET /api/n6/ui/v1/artifacts
GET /api/n6/ui/v1/rollback-summary
GET /api/n6/ui/v1/virtual-account
GET /api/n6/ui/v1/cash-snapshot
GET /api/n6/ui/v1/cash-ledger
```

No POST/PUT/PATCH/DELETE may be added under `/api/n6/ui/v1/...`.

## 6. Safety Proof

```text
database_written=false
write_notification_queue=false
consume_n5_outbox=false
update_n5_outbox_status=false
start_worker=false
delivery=false
push=false
voice=false
mobile=false
sim=false
position=false
pnl=false
real_trade=false
proposal=false
order=false
trade=false
modify_b_track=false
```

## 7. Dry-Run Result

```text
dry_run_result=DRY_RUN_BLOCKED_BY_CURRENT_IMPLEMENTATION
P0=1 ui_v1_signals_ambiguous_parameter
P1=1 track_a_action_executed_proposal_candidate_wording
P2=0
contract_ready=true
implementation_required=true
allow_implementation_gate=true
next_allowed_gate=N6_UI_READONLY_ACTION_CARD_ADAPTER_IMPLEMENTATION_GATE
```
