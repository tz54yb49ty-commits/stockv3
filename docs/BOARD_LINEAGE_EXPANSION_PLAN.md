# Board Lineage Expansion Plan

## Gate

- stage: `N3_BOARD_LINEAGE_EXPANSION_PLANNING_GATE`
- layer_role: `runtime_control`
- generated_at: `2026-06-06T16:55:29+08:00`
- result: `PLAN_PASS`
- scope: readonly planning only

This plan covers the remaining `board_lineage_missing=28` gap after N3 action-confirmation metric coverage repair. It does not execute N3, does not write database rows, and does not modify N4/N5/N6.

## Current Coverage

- N4 TriggerMatched universe: `605`
- current N3 metric union coverage: `577/605`
- remaining excluded rows: `28`
- remaining excluded reason: `board_lineage_missing`
- missing asset kind: `board`

The 28 missing identities are:

```text
board:TDX:880202
board:TDX:880217
board:TDX:880225
board:TDX:880568
board:TDX:880627
board:TDX:880637
board:TDX:880719
board:TDX:880753
board:TDX:880754
board:TDX:880764
board:TDX:881111
board:TDX:881119
board:TDX:881140
board:TDX:881180
board:TDX:881190
board:TDX:881215
board:TDX:881227
board:TDX:881268
board:TDX:881282
board:TDX:881289
board:TDX:881326
board:TDX:881370
board:TDX:881396
board:TDX:881427
board:TDX:881459
board:TDX:881467
board:TDX:881468
board:TDX:881471
```

## Read-Only Diagnosis

The 28 boards all have N4 TriggerMatched rows and live2 realtime snapshot lineage:

- missing board count: `28`
- missing boards with realtime snapshot rows: `28/28`
- missing boards with today minute rows: `0/28`
- missing boards with previous-day minute rows: `0/28`
- missing boards with base minute subscription: `0/28`
- missing boards with stock/index expansion subscription: `0/28`

Base board subscriptions:

- `realtime_daily_snapshot`: `428` rows / `428` identities
- `minute_bar_1m`: `56` rows / `56` identities
- `previous_day_minute_bar_1m`: `56` rows / `56` identities

N2 board scope flags for the 28 missing identities:

- `daily_snapshot_required=true`
- `minute_required=false`
- `previous_day_minute_required=false`
- `market_data_consumer=trigger_daily_snapshot`

So this is not a failed pull for already-subscribed minute data. The missing boards were never included in board minute subscriptions.

## Why Lineage Is Missing

The N4 trigger path only needed realtime daily snapshot for these boards, so they reached `TriggerMatched`.

The N3 action-confirmation metric path needs traceable today minute refs and previous-day minute refs. Because the 28 boards had only realtime snapshot subscriptions, the metric materializer could not produce action-confirmation metric rows for them.

The previous B2 expansion was scoped to stock/index lineage expansion. It did not add board minute subscriptions.

## Existing Repaired Board Reference

The 5 board rows already materialized by repair v1 show the required shape:

- previous-day minute rows per board: `240`
- today minute rows through `11:27` per board: `187`
- metric trace uses `previous_day_minute_refs_count=120`
- metric trace uses `source_minute_refs_count=37`

This is the reference pattern for the 28 missing boards.

## Needed Source Expansion

### 1. Board Subscription Expansion Contract

Future gate: `N3_BOARD_LINEAGE_EXPANSION_SUBSCRIPTION_CONTRACT_GATE`

Source universe:

- the 28 board identities above
- must be cross-checked against N4 TriggerMatched and N2 `board_minute_target_scope`
- must not include stock/index identities
- must not add new identities outside current N2/N4 lineage

Add required data kinds:

- `previous_day_minute_bar_1m`
- `minute_bar_1m`

Do not add:

- `realtime_daily_snapshot`, already present for all 28
- any N4/N5/N6 rows

Planned subscription rows: `56` for `28` board identities.

### 2. Previous-Day Minute Preload

Future gate: `N3_BOARD_LINEAGE_EXPANSION_PREVIOUS_DAY_MINUTE_EXECUTE_GATE`

- required layer role: `N3_market_data`
- trade_date: `20260604`
- expected status rows: `28`
- expected minute rows: `6720`
- estimate basis: `28 * 240` rows

### 3. Today Minute Fill

Future gate: `N3_BOARD_LINEAGE_EXPANSION_TODAY_MINUTE_EXECUTE_GATE`

- required layer role: `N3_market_data`
- trade_date: `20260605`
- target closed minute: `11:27`
- expected minute rows: `5236`
- estimate basis: `28 * 187` rows

### 4. Additive Metric Materialization V2

Future gate: `N3_BOARD_LINEAGE_EXPANSION_ACTION_CONFIRMATION_METRIC_DRY_RUN_GATE`

- expected additive metric rows: up to `28`
- policy: `metric_trace_complete=true AND db_check_pass=true`
- must be additive only
- must not overwrite original metric run
- must not overwrite repair v1 metric run

### 5. Downstream Revalidation

Future gate: `N5_ACTION_PIPELINE_METRIC_UNION_REPAIR_DRY_RUN_REFRESH_GATE`

Only refresh dry-run/contract first. N5/N6 historical metadata repair remains a separate decision.

## Theoretical Coverage

If all 28 boards receive complete previous-day and today minute lineage, and all 28 pass metric trace completeness plus DB CHECK simulation, coverage can reach:

```text
577 existing covered rows + 28 board rows = 605/605
```

Theoretical full coverage: `605/605`.

This is feasible, but conditional. It depends on TDX board minute availability and duplicate-free minute rows for all 28 identities.

## Risks And Guards

Required guards for future execution gates:

- no duplicate minute keys
- expected previous-day rows present per board
- expected today rows through `11:27` present per board
- source_minute_refs non-empty for every metric row
- previous_day_minute_refs non-empty for every metric row
- duplicate metric join keys = `0`
- N3 additive metric v2 does not touch original or repair v1 metric run
- N4/N5/N6 refs remain untouched unless separately authorized

Failure modes:

- TDX does not return board minute data for one or more identities
- returned minute data is incomplete
- DB CHECK simulation fails for one or more board metrics
- future policy blocks retroactive same-day minute expansion after downstream closeout

## Forbidden Scope Proof

This planning gate did not:

- write database rows
- execute N3/N5/N6 repair
- modify N4/N5/N6
- consume or update outbox
- start workers
- trigger delivery/push/voice/mobile
- enter sim/position/PnL/real trade
- generate proposal/order/trade

## Recommended Next Gate

`N3_BOARD_LINEAGE_EXPANSION_SUBSCRIPTION_CONTRACT_GATE`
