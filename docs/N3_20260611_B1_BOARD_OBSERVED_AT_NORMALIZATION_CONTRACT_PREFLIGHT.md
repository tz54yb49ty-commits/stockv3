# N3 20260611 B1 Board Observed-At Normalization Contract Preflight

Gate: `N3_20260611_B1_BOARD_OBSERVED_AT_NORMALIZATION_CONTRACT_PREFLIGHT_GATE`

Result: `DRY_RUN_PREFLIGHT_PASS`

Mode: contract/preflight refresh only. This gate did not execute B1, did not write the database, did not consume or update outbox/inbox/checkpoint, did not start a worker, and did not enter N4/N5/N6.

## Normalization Contract Proof

Route decision: `reviewed_observed_at_normalization`.

The refreshed B1 standard outbox contract now uses:

- `board_source_time_label_handling=NORMALIZE_TO_OBSERVED_AT`
- `normalize_to_observed_at_enabled=true`
- `source_time_trust_level=untrusted_period_label`
- `event_time_policy=observed_at_for_board_untrusted_period_label`
- `quality_gate=n3_b1_board_source_time_label_normalized`

Board raw `15:00` remains trace-only. It must not be used as `MarketSnapshotUpdated.event_time`.

## Payload Trace Proof

Required `MarketSnapshotUpdated.payload_json` fields now include:

- `subscription_id`
- `pull_plan_id`
- `run_id`
- `source_adapter`
- `data_quality_status`
- `snapshot_id`
- `raw_snapshot_time_label`
- `raw_snapshot_time_semantics`
- `source_time_trust_level`
- `observed_at`
- `fetched_at`
- `normalized_event_time_reason`

The fact writer trace payload path has been extended to pass through these source-time trace fields when present on snapshot `raw_json`.

## Expected Rows

| asset | snapshot rows |
|---|---:|
| stock | 1890 |
| index | 83 |
| board | 127 |
| total | 2100 |

Expected `MarketSnapshotUpdated`: `2100`.

## Live Baseline Proof

Read-only target DB proof:

- database: `ashare_v3`
- user: `ashare_v3_user`
- host/port: `127.0.0.1/32:5432`
- read-only `db_now`: `2026-06-11T15:21:12.434884+08:00`

Target scoped rows:

| target | rows |
|---|---:|
| `common_market_data_run` | 0 |
| `common_market_data_quality_item` | 0 |
| stock snapshot | 0 |
| index snapshot | 0 |
| board snapshot | 0 |
| scoped `common_event_outbox` | 0 |
| scoped pending `common_event_outbox` | 0 |

Global 20260611 `MarketSnapshotUpdated` total/pending: `0/0`.

Scoped inbox/checkpoint refs: `0/0`.

N4/N5/N6 refs: `0`.

## Rollback Proof

Rollback SQL: `sql/N3_20260611_B1_market_snapshot_updated_standard_outbox_rollback.sql`.

- hard-fail before DELETE/UPDATE: yes
- guards outbox/inbox/checkpoint: yes
- guards N3-B/C/B2 refs: yes
- guards N4/N5/N6/user/sim/virtual refs: yes
- guards worker/downstream flags: yes
- delete scope: only target `snapshot_run_id`
- no `DROP`, `TRUNCATE`, or `CASCADE`
- rollback was not executed

## Quality

- P0/P1/P2: `0/1/0`
- P1: `board_source_time_label_normalized`, expected board count `127`

## Forbidden Scope Proof

- B1 execute: not run
- DB writes: none
- market data pull: none
- rollback SQL: not executed
- outbox/inbox/checkpoint consume or update: none
- worker: not started
- N4/N5/N6: not entered
- delivery/push/voice/mobile: none
- proposal/order/trade/sim/position/PnL/real trade: none
- old system: not touched

## Next Prompt

```text
layer_role=runtime_control。

进入 N3_20260611_B1_MARKET_SNAPSHOT_UPDATED_STANDARD_OUTBOX_RETRY_FINAL_GATE_REVIEW_AFTER_BOARD_OBSERVED_AT_NORMALIZATION。

请只读复核 N3 observed_at normalization contract/preflight：
- expected rows stock/index/board/total=1890/83/127/2100
- MarketSnapshotUpdated=2100
- board raw 15:00 trace-only
- event_time=observed_at/fetched_at
- quality P0/P1/P2=0/1/0
- target baseline=0
- rollback hard-fail before DELETE/UPDATE

禁止：
- 不 execute
- 不写 DB
- 不消费/update outbox/inbox/checkpoint
- 不启动 worker
- 不进入 N4/N5/N6
```
