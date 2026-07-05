# V3 20260615 Auction Snapshot-Only B2 Repair And Reactivation Closeout

Result: **BLOCKED**

N3 repair result: **FIX_PASS**

Blocked by: **N6_user**

Blocked reason: `n6_user_projection_failed`

## Root Cause

The 09:20 auction chain blocked because the B2 auction/snapshot-only artifact and runner path treated `auction_or_snapshot_only` as requiring `today_minute_run_id`. That made a valid pre-closed-minute B1 auction snapshot path fail at N3-B2 with `b2_auction_mode_runner_requires_today_minute_run`.

No rollback was performed against the already passed N3-B1 auction snapshot; it remains preserved as evidence.

## Repair Proof

Updated files:

- `src/ashare_v3/market/intraday_child_artifacts.py`
- `src/ashare_v3/market/realtime_projection_execute.py`
- `scripts/run_v3_realtime_engine_once.py`
- `scripts/run_n3_n4_n5_realtime_chain_once.py`
- `docs/V3_REALTIME_ENGINE_PRODUCTION_SCHEDULER_LAUNCHD_DRAFT.plist`
- `/Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.v3-realtime-engine.plist`
- `tests/test_n3_intraday_child_artifacts.py`
- `tests/test_realtime_projection_execute.py`
- `tests/test_v3_realtime_engine_once.py`
- `tests/test_n3_n4_n5_realtime_chain_once.py`

Auction 09:27 B2 artifacts now show:

- dry-run: `DRY_RUN_PASS`
- preflight: `PREFLIGHT_PASS`
- `blocked=false`
- `blockers=[]`
- `today_minute_run_id_not_required`
- `snapshot_only_execution_policy.enabled=true`
- `noop_pass_no_write_allowed=true`
- `noop_reason=auction_or_snapshot_only_waiting_for_metric_runner`
- `is_auction_virtual=true`
- `period_source=snapshot_only_no_closed_1m`
- `quality_status=pending_market_data`
- `minute_bar_closed_written=false`

The old blocker `b2_auction_mode_runner_requires_today_minute_run` is absent from the refreshed auction 09:27 B2 artifacts.

## Scheduler Proof

The scheduler was scoped-stopped before repair observation. It was then bootstrapped with approved argv including `--execute`, `--user-confirmed`, and `--allow-overwrite`.

After observation, it was disabled and unloaded again because the latest top-level wrapper reached a downstream N6 blocker repeatedly. Final safety state:

- launchd label disabled: true
- launchctl service loaded: false
- no relevant active wrapper / chain / B1 / C1 / B2 / N4 / N5 process observed

## Latest Chain Proof

N3 auto-poll report:

- path: `docs/N3_INTRADAY_B1_C1_B2_AUTO_POLL_REPORT_20260615.json`
- status: `passed`
- reason: `all_child_steps_passed`
- latest closed minute: `1000`
- projection input mode: `closed_minute`

N3/N4/N5 chain report:

- path: `docs/N3_N4_N5_REALTIME_CHAIN_REPORT_20260615.json`
- result: `EXECUTE_PASS`

Top wrapper report:

- path: `docs/V3_REALTIME_ENGINE_PRODUCTION_RUN_ONCE_REPORT.json`
- result: `BLOCKED`
- blocked reason: `n6_user_projection_failed`

## Row Count Proof

N3 B1 fact run:

- run rows: 1
- quality rows: 11
- snapshot rows stock/index/board/total: `1894/83/127/2104`

N3 C1 fact run:

- run rows: 1
- quality rows: 9
- minute rows stock/index/board/total: `13170/1170/1290/15630`

N3 B2 fact run:

- run rows: 1
- quality rows: 7
- projection rows stock/index/board/total: `1894/83/127/2104`

N3 B1 standard outbox:

- run rows: 1
- quality rows: 11
- `MarketSnapshotUpdated` total/pending: `2104/2104`

N3 B2 trace-aligned projection:

- run rows: 1
- quality rows: 7
- projection rows stock/index/board/total: `1894/83/127/2104`

N4:

- inbox rows: 2104
- outbox rows: 1251
- trigger match rows: 836
- trigger state rows: 1251

N5:

- inbox rows: 836
- outbox rows: 836
- action event rows: 836

N6/user/sim/virtual downstream scoped to the latest N5 run:

- `user_projection_run`: 0
- `user_signal_projection`: 0
- `user_signal_card`: 0
- `user_notification_queue`: 0
- `user_sim_order`: 0
- `user_sim_trade`: 0
- `user_sim_position`: 0
- `n6_virtual_account`: 0
- `n6_virtual_order`: 0
- `n6_virtual_trade`: 0
- `n6_virtual_position`: 0
- `n6_virtual_position_event`: 0
- `n6_virtual_pnl_snapshot`: 0

## Validation

- targeted unittest: PASS, 98 tests
- compileall: PASS
- plist lint: PASS
- JSON parse: PASS
- git diff --check: PASS

## Forbidden Scope

- no old system touch
- no rollback of passed B1 auction snapshot
- no manual rollback SQL executed
- no voice/mobile/sim/position/PnL/real trade touched
- no manual N4/N5/N6 execute outside the authorized scheduler observation path
- scheduler was not left running after the N6 blocker was observed

## Decision

N3 repair is complete and verified. The overall closeout remains blocked by `N6_user` because top-level production wrapper now fails at `n6_user_projection_failed`.

Next recommended gate:

`V3_20260615_REALTIME_ENGINE_N3_REPAIR_CLOSEOUT_AND_N6_BLOCKER_REGISTRATION_GATE`
