# N6 Phase 3 Order Proposal Spec

Status: SPEC_PASS

Layer role: N6_user

Date: 2026-06-05

This gate freezes the N6 virtual order proposal specification. It defines the
boundary from reviewed N5/N6 signals to a virtual order candidate proposal. It
does not write database rows, execute runners, generate `n6_virtual_order`
rows, generate `n6_virtual_trade` rows, materialize positions or PnL, consume
or update outbox rows, start workers, modify N6_UI_v1, modify existing APIs,
modify projection or shadow pipelines, deliver notifications, push to voice or
mobile, run sim, materialize positions, or place real trades.

## 1. Basis

Authoritative inputs:

```text
docs/N6_PHASE3_VIRTUAL_ACCOUNT_OPERATION_POLICY_DESIGN.md
docs/N6_PHASE3_VIRTUAL_ACCOUNT_OPERATION_POLICY_DESIGN.json
docs/N6_PHASE3_VIRTUAL_ACCOUNT_OPERATION_POLICY_TRACEABILITY.md
docs/N6_PHASE3_VIRTUAL_ACCOUNT_OPERATION_POLICY_TRACEABILITY.json
Phase 3 admin virtual account seed POST_REVIEW_PASS
Phase 3 virtual account schema foundation CLOSEOUT_PASS
```

Current baseline:

```text
admin virtual account exists
initial_cash = 1000000.0000 CNY
n6_virtual_order = 0
n6_virtual_trade = 0
n6_virtual_position = 0
n6_virtual_position_event = 0
n6_virtual_pnl_snapshot = 0
```

## 2. Proposal Concept

A proposal is a candidate intent. It is not an order.

Proposal must not:

```text
freeze cash
reserve cash
change cash ledger
change cash snapshot
change virtual position
write n6_virtual_order
write n6_virtual_trade
consume N5 outbox
update N5 outbox status
imply real order
imply real fill
imply investment advice
```

Proposal may only become input to a future virtual order runner after it has
been reviewed and accepted by the allowed reviewer policy.

## 3. Signal Eligibility

Signal-to-proposal eligibility:

| Source state | Proposal behavior |
|---|---|
| `ActionBlocked` | Display only by default. No proposal. |
| `ActionExecuted` | Eligible to become proposal candidate after review policy checks. |
| `ActionEligible` | Eligible to become proposal candidate if user policy permits. |
| `ActionSkipped` | Informational only. No proposal. |

Important semantics:

```text
ActionExecuted does not mean placed order.
ActionExecuted does not mean filled trade.
ActionExecuted does not mean real trading.
ActionExecuted only means N5 market action confirmation succeeded.
```

Notification states are not proposal triggers:

```text
N6 queued_only does not trigger proposal.
N6 notification preview does not trigger proposal.
delivery preview does not trigger proposal.
```

## 4. Data Boundary

Allowed read sources:

```text
reviewed / approved N5 action events or reviewed N5 action artifacts
N6 shadow projection
N6 user_signal_projection
N6 user_signal_card
N6 reviewed dashboard artifact
admin virtual account and current approved cash snapshot
approved N3 / N6 display price snapshot or reviewed valuation policy
```

Forbidden read sources:

```text
raw K
N1 raw facts
N3 raw facts
N4 raw facts
N5 raw facts used to bypass reviewed events/artifacts
direct live market data
broker account
broker funds
broker position
broker order API
```

Price source policy:

```text
proposal_price_policy must name an approved N3 reviewed snapshot or N6 reviewed valuation policy.
proposal generation must not pull live market data.
proposal generation must not infer price from raw K.
proposal generation must not read N1 raw facts.
```

## 5. Lifecycle

Canonical proposal lifecycle:

```text
candidate
reviewed
accepted
rejected
expired
superseded
```

Lifecycle rules:

| Status | Meaning | May enter virtual order runner |
|---|---|---|
| `candidate` | Generated candidate requiring review. | No |
| `reviewed` | Human/admin review completed, no accept decision yet. | No |
| `accepted` | Explicitly accepted for virtual order materialization. | Yes |
| `rejected` | Reviewer rejected candidate. | No |
| `expired` | Candidate passed its validity window. | No |
| `superseded` | Replaced by newer proposal/source state. | No |

Only `accepted` may enter a future virtual order runner. That runner still
requires its own contract, preflight, rollback, final gate, and explicit user
confirmation.

## 6. Field Draft

Future proposal artifact/table should include at least:

```text
proposal_id
virtual_account_id
principal_id
source_action_event_id
source_projection_id nullable
asset_kind
identity_key
proposal_side
proposal_quantity
proposal_price_policy
proposal_reason
confidence_score nullable
proposal_status
reviewed_by nullable
reviewed_at nullable
accepted_at nullable
expires_at nullable
run_id
policy_version
policy_hash
source_lineage_json
quality_status
```

Recommended additional fields for future schema review:

```text
principal_type
source_action_run_id
source_action_event_type
source_signal_card_id
proposal_quantity_policy
proposal_price_snapshot_id nullable
proposal_price nullable
superseded_by_proposal_id nullable
rollback_scope
created_at
updated_at
```

This spec does not create a proposal table. The next proposal schema draft gate
must decide artifact-only versus table-backed storage.

## 7. Review / Acceptance Rules

Review must be explicit:

```text
accepted_at cannot be set unless proposal_status='accepted'.
reviewed_by is required for reviewed / accepted / rejected.
expired proposals cannot be accepted without a new proposal.
superseded proposals cannot be accepted.
ActionBlocked proposals are blocked by policy unless a separate override gate exists.
```

Acceptance only authorizes the proposal to be considered by a future virtual
order runner. It does not create an order by itself.

## 8. Forbidden Language

Proposal UI, API, reports, and artifacts must not say:

```text
已下单
已成交
已交易
真实交易
投资建议
```

Allowed wording examples:

```text
虚拟订单候选
待复核候选
已接受候选
可进入虚拟订单流程
```

## 9. Quality Gate

Future proposal dry-run/preflight must hard-fail on:

```text
missing admin virtual account
missing current cash snapshot
source signal not reviewed or approved
source action state not eligible for proposal
ActionBlocked without explicit override gate
queued_only / notification preview used as trigger
price source not approved
raw K / live market data / N1 raw fact access
proposal_status outside lifecycle
accepted without reviewed_by
accepted without accepted_at
attempt to write n6_virtual_order
attempt to write n6_virtual_trade
attempt to write cash ledger/snapshot
attempt to write position/PnL
attempt to consume/update outbox
```

Expected quality for this spec:

```text
P0=0
P1=0
P2=0
```

## 10. Rollback Boundary

If future proposal rows are table-backed, rollback must:

```text
delete only proposal rows scoped by proposal_run_id / rollback_scope
hard-fail before first DELETE if any linked n6_virtual_order rows exist
not delete virtual_order/trade/position/pnl rows
not delete admin virtual account seed rows
not touch N5 outbox
not touch N1-N5 facts
```

If proposal remains artifact-only, rollback is artifact supersession:

```text
mark artifact superseded in runtime_control registry
do not touch database rows
```

## 11. Future Gates

Required next gates:

```text
N6_PHASE3_ORDER_PROPOSAL_SCHEMA_DRAFT_GATE
N6_PHASE3_ORDER_PROPOSAL_RUNNER_DRY_RUN_GATE
N6_PHASE3_ORDER_PROPOSAL_REVIEW_ACCEPTANCE_GATE
N6_PHASE3_VIRTUAL_ORDER_RUNNER_GATE
```

Recommended next gate:

```text
N6_PHASE3_ORDER_PROPOSAL_SCHEMA_DRAFT_GATE
```

Alternative allowed gate:

```text
runtime_control order proposal spec review
```

This spec does not authorize any proposal generation or virtual order
materialization.
