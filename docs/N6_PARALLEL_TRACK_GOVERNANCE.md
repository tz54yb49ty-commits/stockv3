# N6 Parallel Track Governance

Result: `PARALLEL_TRACK_PASS`

Layer role: `runtime_control`

Date: `2026-06-04`

This governance artifact allows two N6 work tracks to proceed in parallel while
preserving strict isolation. It does not change code, write database rows,
execute runners, consume outbox rows, start workers, or perform delivery, push,
voice, mobile, sim, position, or real trade side effects.

## Track A: N6_UI_v1

Status: `ACTIVE`

Current basis:

```text
docs/N6_USER_INTERFACE_SPEC_v1.md
docs/N6_USER_INTERFACE_SPEC_v1_TRACEABILITY.md
docs/N6_USER_INTERFACE_SPEC_v1_POST_REVIEW.md
docs/N6_USER_INTERFACE_SPEC_v1_POST_REVIEW.json
docs/N6_USER_INTERFACE_SPEC_v1_DRY_RUN_PREVIEW.md
docs/N6_USER_INTERFACE_SPEC_v1_DRY_RUN_PREVIEW.json
```

Allowed:

```text
implementation
dry-run
preview
shadow
```

Current targets:

```text
Dashboard
Signal List
Signal Detail
Notification Preview
Audit Panel
```

Forbidden:

```text
real trade
push
voice
mobile
sim
position
outbox consumption
worker startup
database writes unless a later N6_user gate explicitly allows them
```

## Track B: N6_MULTI_USER_AND_AI_SPEC_v1

Status: `DESIGN_ONLY`

Current artifact state:

```text
docs/N6_MULTI_USER_AND_AI_SPEC_v1.md = not_started
docs/N6_MULTI_USER_AND_AI_SPEC_v1_TRACEABILITY.md = not_started
```

Allowed:

```text
spec
traceability
architecture
review
```

Design targets:

```text
multi-user
virtual account
AI user
AI strategy
```

Forbidden:

```text
implementation
modifying N6_UI_v1
modifying existing N6 UI APIs
modifying existing N6 projection tables or semantics
modifying existing N6 shadow pipeline
database writes
outbox consumption
worker startup
real delivery / push / voice / mobile / sim / position / real trade
```

## Conflict Items

No active technical conflict is approved. The following potential conflicts are
explicitly isolated:

| Conflict surface | Decision |
|---|---|
| UI API ownership | Track A owns current N6 UI v1 APIs. Track B may only propose future APIs in its own spec. |
| Projection ownership | Track A consumes existing N6 projection/card/queue. Track B may not modify projection semantics. |
| Shadow pipeline | Track A may use current shadow projection evidence. Track B may not alter shadow pipeline behavior. |
| User/account semantics | Track B may design multi-user and virtual-account semantics only. Track A must not absorb them without a future approved gate. |
| AI strategy semantics | Track B may document AI user/strategy concepts only. No implementation, scheduling, execution, or trade intent is allowed. |

## Isolation Proof

```text
track_a_status=ACTIVE
track_a_scope=N6_UI_v1 implementation/dry-run/preview/shadow
track_b_status=DESIGN_ONLY
track_b_scope=spec/traceability/architecture/review only
track_b_can_modify_track_a=false
track_b_can_modify_existing_api=false
track_b_can_modify_existing_projection=false
track_b_can_modify_existing_shadow_pipeline=false
shared_database_write_allowed=false
outbox_consumption_allowed=false
worker_start_allowed=false
real_trade_allowed=false
```

Future condition for Track B implementation:

```text
N6_MULTI_USER_AND_AI_SPEC_v1 status must be SPEC_FREEZE_PASS
runtime_control approval must be APPROVED
then open a separate N6_MULTI_USER_AND_AI_IMPLEMENTATION_GATE
```

## Boundary

This gate only governs track separation. It does not authorize Track A or Track
B to execute, write database rows, consume outbox rows, start workers, or enable
real delivery, push, voice, mobile, sim, position, or real trade.
