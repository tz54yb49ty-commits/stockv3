# v3 Symmetry Target Price Canonical Spec

Status: canonical

Frozen at: 2026-05-31

layer_role: `runtime_control`

Scope: documentation-only canonical freeze for symmetric target-price semantics, field ownership, and layer boundaries.

This freeze does not authorize schema migration, code changes, database writes, execute runs, worker startup, outbox consumption, or old-system access.

```text
execute=false
schema_migration=false
database_write=false
outbox_write=false
inbox_checkpoint_write=false
worker_started=false
old_system_touched=false
```

## 1. Purpose

This document freezes the canonical interpretation of N2 symmetric target-price fields and their downstream ownership.

The goal is to separate three concepts that were historically easy to mix:

```text
N2 condition-layer target candidates
N4/N5 runtime trigger/action facts
N6/position holding target and clear strategy
```

N2 may compute auditable symmetric target-price candidates. N4/N5 may carry those values as immutable context. N6/position is the first boundary allowed to interpret a target as a holding target, lock a target, or apply clear-position policy.

## 2. Field Ownership

Canonical ownership:

| Field / concept | Canonical owner | Meaning |
|---|---|---|
| `symmetry_anchor` | N2 | Structural anchor used to identify the A segment. |
| `amplitude_source_period` | N2 | Period used to measure the A-segment amplitude. |
| A segment recognition | N2 | Static condition-layer structure, based on N1 official facts. |
| `base_price_policy` | N2 | Policy used to choose the base price for symmetric projection. |
| `reference_target_price` | N2 | Primary symmetric target-price candidate. |
| `secondary_target_price` | N2 | Optional secondary target-price candidate. |
| `up_sell_reference_period` | N2 | Canonical buy-side later-sell reference period. |
| `down_buy_reference_period` | N2 | Canonical sell-side later-buy reference period. |
| `clear_sell_ref_period` | Legacy alias only | Compatibility alias equal to `up_sell_reference_period`. |
| `locked_target_price` | N6/position | Holding-context locked target, never an N2 field. |
| `target_lock_status` | N6/position | User/position target lock state, never an N2 field. |

N4/N5 ownership:

```text
N4 does not recompute target prices.
N4 does not lock target prices.
N4 does not decide clear-position policy.
N5 does not recompute target prices.
N5 does not lock target prices.
N5 does not decide clear-position policy.
N5 may only copy source target fields into action context for trace/audit.
```

N6/position ownership:

```text
N6/position interprets holding target price.
N6/position may choose locked_target_price.
N6/position may maintain target_lock_status.
N6/position owns clear-position display and strategy policy.
N6/position must not rewrite N2/N4/N5 facts.
```

## 3. A Segment Recognition

The A segment is a condition-layer static structure, not a runtime trigger/action decision.

N2 identifies A segments from N1 official daily facts and freezes the result in condition-layer outputs. N4/N5/N6 must not identify a new A segment during runtime.

Canonical directional mapping:

```text
buy-side / up symmetry:
  symmetry_anchor = main_up_anchor
  amplitude_source_period = up_reference_period
  amplitude field = up_amplitude
  reference period for later sell = up_sell_reference_period

sell-side / down symmetry:
  symmetry_anchor = main_down_anchor
  amplitude_source_period = down_reference_period
  amplitude field = down_amplitude
  reference period for later buy = down_buy_reference_period
```

A segment recognition must produce auditable trace:

```text
asset_kind
identity_key
direction
condition_key
symmetry_anchor
amplitude_source_period
base_price_policy
amplitude_value
source_period_start/end when available
source_run_id
quality status
```

If N2 cannot identify the required A segment or amplitude source period for a target-required policy, it must emit an explicit quality item or a null target with reason. It must not let N4/N5 fill the missing target by recomputing from runtime data.

## 4. Base Price Policy

`base_price_policy` records how N2 selected the base price used for symmetric projection.

Canonical v0 policy:

```text
base_price_policy = MIN_CLOSE_AFTER_LAST_LOWER_UP_SEGMENT_PLUS_TRIGGER_OPEN
```

Meaning:

```text
MIN_CLOSE_AFTER_LAST_LOWER_UP_SEGMENT_PLUS_TRIGGER_OPEN is the only canonical
database enum value for v0. It names the N2 compatibility policy that selects
the symmetric base price from the lower-period post-segment close boundary plus
trigger-open context.

The exact selected numeric value must be stored in base_price and explained in
target_price_trace_json. Runtime layers must not infer or switch the policy from
direction, condition_key, signal_type, user policy, or position state.
```

`reference_body_boundary` is a legacy descriptive phrase from earlier docs. It
may be used only to explain the old intent in prose; it is not a canonical
database enum and must not be accepted or persisted as `base_price_policy`.

The base price policy is part of N2 static condition semantics. Runtime layers may read it only as trace/context.

Forbidden:

```text
N4 must not switch base_price_policy during trigger matching.
N5 must not switch base_price_policy during action confirmation.
N6 must not rewrite N2 base_price_policy.
```

Future policies, if introduced, must be explicit enum values and must pass a migration/alignment gate. They must not be inferred from `condition_key`, `signal_type`, asset kind, user policy, or position state.

## 5. Target Price Candidates

N2 owns target-price candidates. They are candidates, not locked holding targets.

Canonical fields:

```text
reference_target_price
secondary_target_price
```

`reference_target_price` is the primary symmetric target-price candidate:

```text
buy-side / up symmetry:
  reference_target_price = base_price + up_amplitude

sell-side / down symmetry:
  reference_target_price = base_price - down_amplitude
```

N2 canonical target-machine alignment uses symmetric A-segment math:

```text
Up side:
  scan Y -> Q -> M -> W for the first continuous volume_up run
  symmetry_anchor = the finest period in that run
  reference_period = lower(symmetry_anchor)
  A segment = the current continuing up segment of symmetry_anchor
  A segment must be identified on symmetry_anchor itself, not by expanding to
    the parent period current window. For W anchor, aggregate daily facts into
    weekly bars and walk backward from the current week until the continuous
    weekly volume_up run breaks. The first unknown aggregate bar is not merged
    into the A segment automatically.
  amplitude_price_policy = OFFICIAL_HIGH_LOW
  amplitude = target-machine adjusted upper boundary over A segment - target-machine adjusted lower boundary over A segment
  trend_break_date = latest completed lower(reference_period) aggregate up segment end
  base window = next trade date after trend_break_date through source_trade_date
  base_price = min(close) over base window
  reference_target_price = base_price + amplitude

Down side:
  scan Y -> Q -> M -> W for the first continuous low_volume_down run
  symmetry_anchor = the finest period in that run
  reference_period = lower(symmetry_anchor)
  A segment = the current continuing down segment of symmetry_anchor
  A segment must be identified on symmetry_anchor itself. The first unknown
    aggregate bar is not merged into the A segment automatically.
  amplitude_price_policy = OFFICIAL_HIGH_LOW
  amplitude = target-machine adjusted upper boundary over A segment - target-machine adjusted lower boundary over A segment
  trend_break_date = latest completed lower(reference_period) aggregate down segment end
  base window = next trade date after trend_break_date through source_trade_date
  base_price = max(close) over base window
  reference_target_price = base_price - amplitude
```

For current v3 N1 stock daily facts, the target-machine adjusted A-segment
boundary that reproduces the frozen target-machine golden values is the
adjusted body boundary (`max(open, close)` / `min(open, close)`). Raw intraday
`high` / `low` may differ and must not be silently substituted without a
separate N1/N2 alignment gate.

For stock rows, N2 must normalize historical A-segment body boundaries to the
current `source_trade_date` adjusted-price baseline before computing amplitude:

```text
adjustment_policy = ROW_ADJ_FACTOR_TO_CURRENT_ADJ_FACTOR
adjusted_price = raw_body_boundary_price * row_adj_factor / current_adj_factor
```

The normalized boundary is rounded to the N1 daily price precision before the
A-segment high/low comparison. `target_price_trace_json` must carry
`adjustment_policy` and `current_adj_factor` whenever `adj_factor` is available.
Index and board rows do not currently carry `adj_factor`; their target-machine
boundary remains the adjusted body boundary as stored in their active daily
facts.

Golden regression:

```text
stock:SZ:000027 / source_trade_date=20260528
symmetry_anchor = W
reference_period = D
A segment = 20260506 -> 20260528
segment_low = 6.88
segment_high = 8.05
amplitude = 1.17
trend_break_date = 20260519
base window = 20260520 -> 20260528
base_price = 7.25
reference_target_price = 8.42

stock:SZ:000543 / source_trade_date=20260529
symmetry_anchor = W
reference_period = D
A segment = 20260506 -> 20260529
segment_low = 8.09
segment_high = 9.80
amplitude = 1.71
trend_break_date = 20260526
base window = 20260527 -> 20260529
base_price = 9.11
reference_target_price = 10.82

stock:SZ:000600 / source_trade_date=20260529
symmetry_anchor = W
reference_period = D
A segment = 20260518 -> 20260529
segment_low = 9.75
segment_high = 12.55
amplitude = 2.80
trend_break_date = 20260519
base window = 20260520 -> 20260529
base_price = 10.13
reference_target_price = 12.93

stock:SZ:000027 / source_trade_date=20260529
reference_target_price = 8.45

stock:SZ:300327 / source_trade_date=20260529
symmetry_anchor = Y
reference_period = Q
adjustment_policy = ROW_ADJ_FACTOR_TO_CURRENT_ADJ_FACTOR
current_adj_factor = 3.1316
segment_low = 19.25
segment_high = 34.28
amplitude = 15.03
reference_target_price = 38.27
secondary_symmetry_anchor = W
secondary_target_price = 33.04
```

`secondary_target_price` is optional. It is computed by taking the second
continuous anchor run and repeating the same A-segment, reference-period
breakpoint, base-window, and target-price formula. It is not a discount of the
primary target and is not another runtime state snapshot. If the second anchor
is absent, N2 must leave it null with a reason rather than letting N4/N5 derive
it.

N2 persists explicit direction-specific secondary fields:

```text
up_secondary_anchor
up_secondary_reference_period
up_secondary_trend_start_date
up_secondary_trend_end_date
up_secondary_amplitude
up_secondary_base_price
up_secondary_target_price
up_secondary_expected_return_pct

down_secondary_anchor
down_secondary_reference_period
down_secondary_trend_start_date
down_secondary_trend_end_date
down_secondary_amplitude
down_secondary_base_price
down_secondary_target_price
down_secondary_expected_return_pct
```

Compatibility fields remain direction-dependent:

```text
secondary_symmetry_anchor = current row direction's secondary anchor
secondary_target_price = current row direction's secondary target price
```

Compatibility mapping:

```text
existing buy_target_price  -> buy-side reference_target_price
existing sell_target_price -> sell-side reference_target_price
```

This freeze does not rename existing schema columns. It freezes canonical semantics for future schema/code alignment.

## 6. Reference Period And Legacy Alias

`up_sell_reference_period` is the canonical field for buy-side later-sell reference.

`down_buy_reference_period` is the canonical field for sell-side later-buy reference.

`clear_sell_ref_period` is a legacy alias only:

```text
clear_sell_ref_period = up_sell_reference_period
```

Rules:

```text
New N2 semantics must use up_sell_reference_period as canonical.
New N2 semantics must not treat clear_sell_ref_period as a primary field.
N4/N5 may read clear_sell_ref_period only for compatibility and must prefer up_sell_reference_period when both exist.
N6/position may use up_sell_reference_period to interpret clear-position strategy, but must not write it back to N2.
```

## 7. Locked Target Price Boundary

`locked_target_price` does not belong to N2.

`locked_target_price` requires user/position context:

```text
holding state
entry context
user policy
position policy
projection/display policy
confirmation state
```

Therefore it is owned only by N6/position. It may be derived from N2 target candidates plus N5 action context, but the derivation result is a user/position projection or position-state value.

Forbidden in N2:

```text
locked_target_price
target_lock_status
position clear decision
user policy hint
```

Forbidden in N4/N5:

```text
locking target price
choosing holding target price
deciding clear-position policy
rewriting N2 target candidates
```

## 8. Runtime Layer Rules

N4:

```text
reads N2-localized target context
may include reference_target_price / secondary_target_price in trace payload
does not recompute target candidates
does not lock target price
does not decide clear-position policy
```

N5:

```text
reads N4 payload / N5 action context target fields for audit/action context
may copy target candidates into action facts for trace
does not recompute target candidates
does not lock target price
does not decide clear-position policy
does not convert ActionExecuted into real trade or sim intent
```

N6/position:

```text
interprets target candidates for user display
may choose locked_target_price
may maintain target_lock_status
may display clear-position strategy
may derive user-facing target cards and queued notifications
does not rewrite N2/N4/N5 facts
```

## 9. Divergence List

Current known divergences to address in later schema/code alignment gates:

1. Existing condition-layer docs and schemas mainly expose `buy_target_price` / `sell_target_price`; canonical semantics now distinguish `reference_target_price` and optional `secondary_target_price`.
2. Existing N4/N5 context field lists include `buy_target_price`, `sell_target_price`, and `clear_sell_ref_period`; future alignment should add/pass through `reference_target_price`, `secondary_target_price`, `symmetry_anchor`, `amplitude_source_period`, `base_price_policy`, and canonical `up_sell_reference_period`.
3. Some historical docs require `clear_sell_ref_period` to be carried through N2 tables. This remains allowed only as compatibility alias; canonical logic must prefer `up_sell_reference_period`.
4. Existing code/schema may not yet persist `symmetry_anchor`, `amplitude_source_period`, `base_price_policy`, `reference_target_price`, or `secondary_target_price`.
5. Existing docs mention `locked_target_price` as a forbidden N2 field, but downstream ownership is now explicitly frozen: it belongs only to N6/position.
6. Existing N4/N5 reports may contain target fields in payloads. These are trace/context only and must not be interpreted as runtime lock or clear decisions.

## 10. Alignment Gate Recommendations

Future alignment should be split into separate gates:

```text
N2 schema/code alignment:
  add canonical target candidate fields or compatibility views
  preserve buy_target_price/sell_target_price mapping
  add quality checks for symmetry_anchor/amplitude_source_period/base_price_policy

N4/N5 context alignment:
  pass through target candidate fields without recompute
  prefer up_sell_reference_period over clear_sell_ref_period
  assert no locked_target_price / target_lock_status writes

N6/position alignment:
  define locked_target_price derivation policy
  define target_lock_status lifecycle
  define clear-position display/strategy policy
  prove no upstream rewrites
```

Each alignment gate must have its own preflight, rollback, and explicit layer_role authorization.
