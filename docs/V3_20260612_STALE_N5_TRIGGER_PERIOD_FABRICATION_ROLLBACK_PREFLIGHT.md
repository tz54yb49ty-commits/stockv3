# V3 20260612 Stale N5 Trigger Period Fabrication Rollback Preflight

Result: `PREFLIGHT_PASS`

## Planned Cleanup

- `common_action_run`: `2`
- `common_action_quality_item`: `4449`
- `stock_action_fact`: `22226`
- `index_action_fact`: `975`
- `board_action_fact`: `1831`
- `common_action_event`: `25032`
- N5 `common_event_outbox`: `25032`
- scoped unique stale consumer inbox/checkpoint: `25282/2078`

## Safety Proof

- N5 outbox delivered/delivering: `0`
- N5 downstream inbox refs: `0`
- N5 downstream checkpoint refs: `0`
- N6/user refs: `0`
- position refs: `0`
- voice/mobile/sim/order/real_trade refs: `0`
- ambiguous shared `n5_action_consumer_v1` inbox/checkpoint refs for the hint-basis source: `0`

## Rollback SQL

```text
sql/V3_20260612_stale_n5_trigger_period_fabrication_rollback.sql
```

Static contract:

- hard-fail before first DELETE
- delete only scoped N5 rows
- preserve N4/N3 historical evidence
- do not consume/update outbox/inbox/checkpoint in this gate
- do not enter N4/N6 or start scheduler/worker

## Next Final Gate Prompt

```text
layer_role=N5_action。

进入 V3_20260612_STALE_N5_TRIGGER_PERIOD_FABRICATION_ROLLBACK_FINAL_GATE_REVIEW。

目标：只读复核是否允许执行 scoped rollback：
- v3_n5_action_replay_20260612_after_n4_state_machine_v3
- v3_n5_hint_basis_aligned_replay_20260612_from_n4_action_confirmation_metric_after_hint_basis_fix_v1

依据：
- docs/V3_20260612_STALE_N5_TRIGGER_PERIOD_FABRICATION_ROLLBACK_DRY_RUN.md/json
- docs/V3_20260612_STALE_N5_TRIGGER_PERIOD_FABRICATION_ROLLBACK_CONTRACT.md/json
- docs/V3_20260612_STALE_N5_TRIGGER_PERIOD_FABRICATION_ROLLBACK_PREFLIGHT.md/json
- sql/V3_20260612_stale_n5_trigger_period_fabrication_rollback.sql

请确认：
- N5 outbox delivered/delivering=0
- N5 downstream inbox/checkpoint refs=0
- N6/user/voice/mobile/sim/position/order/real_trade refs=0
- rollback SQL hard-fail before first DELETE
- 删除范围仅 scoped N5 rows 和 reviewed unique stale consumer inbox/checkpoint
- 保留 N4/N3 historical evidence

输出 PASS/BLOCKED、风险、允许执行命令和 execute 后 post-review 要求。
```
