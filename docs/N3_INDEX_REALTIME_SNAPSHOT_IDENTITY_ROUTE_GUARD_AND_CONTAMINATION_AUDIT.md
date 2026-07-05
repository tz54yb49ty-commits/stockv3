# N3 Index Realtime Snapshot Identity Route Guard And Contamination Audit

## Result

- gate_result: `BLOCKED`
- guard_implementation_result: `FIX_PASS`
- layer_role: `N3_market_data`

The code guard is fixed, but the historical 20260611 contaminated lineage is not safe to continue into N5. The affected standard outbox run already has N4 inbox/checkpoint refs and a production semantic replay derived from it.

## Root Cause

`IndexMarketDataAdapter` accepted naked-code mootdx quote rows whose raw route did not match the index subscription identity.

Example:

- expected: `index:SH:000009 / 上证380`
- observed raw quote: `market=0`, `code=000009`, `price=6.85`
- contaminating identity: `stock:SZ:000009 / 中国宝安`

## Guard Proof

Implemented in `src/ashare_v3/market/realtime_snapshot_execute.py`:

- new evidence function: `build_snapshot_identity_route_evidence`
- P0 gate: `n3_b1_identity_route_mismatch`
- handling: `P0_BLOCK_NO_SNAPSHOT_NO_OUTBOX`
- run-level atomic precheck now includes `identity_route_mismatch_count`
- successful snapshot raw_json now keeps expected/actual route trace fields

## Contamination Proof

Read-only DB audit:

- all 20260611 index snapshot rows: `5146`
- all 20260611 route mismatch rows: `1550`
- all 20260611 SH index rows with raw SZ market: `992`
- all 20260611 raw code mismatch rows: `558`

Standard outbox run:

`realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`

- index rows: `83`
- route mismatch rows: `25`
- affected index identities: `25`
- SH raw SZ market rows: `16`
- raw code mismatch rows: `9`
- same-code same-price stock/index pairs: `9`
- identical raw payload stock/index pairs: `9`

Samples:

- `index:SH:000001 / 上证指数`: raw `market=0`, raw `code=000001`
- `index:SH:000009 / 上证380`: raw `market=0`, raw `code=000009`
- `index:SH:000016 / 上证50`: raw `market=0`, raw `code=000016`
- `index:SH:000688 / 科创50`: raw `market=0`, raw `code=000688`

## Downstream Ref Proof

The standard outbox remains pending but has already been referenced:

- MarketSnapshotUpdated rows: `2100`
- pending: `2100`
- delivered/delivering: `0`
- inbox refs: `6306`
- checkpoint refs: `6306`

Refs by consumer:

- `n4_trigger_production_semantic_replay_20260611_market_snapshot_updated_v1`: `2100`
- `n4_trigger_worker_v1_bounded_polling_20260611`: `2100`
- `n4_trigger_worker_v1_bounded_smoke_20260611_day_scope_probe`: `2100`
- `n4_trigger_worker_v1_bounded_smoke_20260611_trigger_semantic_probe`: `6`

B2 projection refs from the standard snapshot run:

- stock/index/board: `1890/83/127`

N4 production semantic replay:

- run_id: `n4_production_semantic_replay_20260611_market_snapshot_updated_v1`
- status: `passed`
- trigger_state / trigger_match / trigger_event_outbox: `799/548/799`

## Decision

Direct rollback is not safe because the standard outbox has inbox/checkpoint refs and N4 production semantic replay facts derived from the contaminated lineage.

Decision:

`BLOCK_N5_AND_DOWNSTREAM_USE_OF_INDEX_TRIGGER_MATCHED_FROM_CONTAMINATED_LINEAGE`

Recommended route:

`SUPERSEDE_CONTAMINATED_20260611_N3_B1_B2_N4_LINEAGE_THEN_REPLAY_AFTER_GUARD`

Next gate:

`N3_N4_20260611_CONTAMINATED_INDEX_LINEAGE_SUPERSESSION_AND_REPAIR_POLICY_GATE`

## Scheduler Safety

The N3 chain LaunchAgent was scoped paused to prevent additional automatic writes while this P0 guard was being implemented.

- label: `com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll`
- `launchctl bootout` exit code: `0`
- post-check `launchctl print` exit code: `113`
- state: `not_loaded`

## Forbidden Scope

- no DB write by this gate
- no rollback SQL executed
- no outbox/inbox/checkpoint consume or update
- no worker started
- no N4/N5/N6 execute by this gate
- no trade/sim/position/voice/mobile touched
- old system untouched
