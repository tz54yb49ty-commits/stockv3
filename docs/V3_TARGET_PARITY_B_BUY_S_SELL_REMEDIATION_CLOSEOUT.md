# V3 Target Parity B_BUY / S_SELL Remediation Closeout

Result: `CLOSEOUT_PASS`

Trade date: `20260612`

Mode: `offline_remediation_and_target_machine_compare`

## Summary

This closeout freezes the first V3 remediation baseline against the target machine for `B_BUY` and `S_SELL`.

Target machine golden set:

```text
B_BUY=76
S_SELL=24
```

V3 canonical replay:

```text
B_BUY=76
S_SELL=20
```

Diagnostic replay using target action price:

```text
B_BUY=76
S_SELL=22
```

Diagnostic replay using target action price plus legacy `stock_board` alert amount compatibility:

```text
B_BUY=76
S_SELL=24
```

## Diagnosis

`B_BUY` is aligned at `76/76`.

`S_SELL` is not silently forced to `24/24` under V3 canonical rules. Two missing rows are explained by the target machine using `action_fact_cache.price` rather than the 1m close as the action-time price source. The final two rows are `stock_board` alert-lane amount compatibility differences.

The important policy point:

```text
Do not silently change N5 canonical rules.
```

If production parity must match the target machine exactly, the next gate must add a reviewed, scoped `stock_board` alert compatibility policy. It must not alter stock/index ordinary N5 canonical action confirmation.

## Artifacts

- `src/ashare_v3/market/b_buy_s_sell_replay_compare.py`
- `scripts/run_v3_b_buy_s_sell_replay_compare_20260612.py`
- `tests/test_v3_b_buy_s_sell_replay_compare.py`
- `docs/V3_20260612_B_BUY_S_SELL_REPLAY_COMPARE.json`
- `docs/V3_20260612_B_BUY_S_SELL_REPLAY_COMPARE.md`
- `docs/V3_20260612_B_BUY_S_SELL_REPLAY_COMPARE_DIFF.csv`

## Forbidden Scope

```text
target_machine_modified=false
runtime_db_written=false
scheduler_started=false
worker_started=false
outbox_consumed_or_updated=false
n6_entered=false
voice_mobile_sim_trade_touched=false
```

## Next Prompt

```text
layer_role=N3_market_data。

进入 V3_TARGET_PARITY_B_BUY_S_SELL_PRODUCTIONIZATION_CONTRACT_GATE。

目标：把当前离线 V3 B_BUY/S_SELL 目标机对比整改推进到生产化 contract/preflight。保持 N4/N5 当前业务规则不变，N3 负责产出标准 action-confirmation metric；不启动 worker，不写生产 DB，不进入 N6/voice/mobile/sim/trade。

依据：
- docs/V3_TARGET_PARITY_B_BUY_S_SELL_REMEDIATION_CLOSEOUT.md/json
- docs/V3_20260612_B_BUY_S_SELL_REPLAY_COMPARE.md/json/csv
- src/ashare_v3/market/b_buy_s_sell_replay_compare.py
- tests/test_v3_b_buy_s_sell_replay_compare.py

请完成：
1. 制定 N3 action-confirmation metric production contract：current_price_source 支持 reviewed realtime snapshot/action-price source，并保留 minute_close trace。
2. 制定 stock_board alert compatibility policy 决策：若追平目标机 S_SELL=24，必须 scoped 为 board alert compatibility，不改变 stock/index/N5 canonical 普通确认规则。
3. 生成 production dry-run/preflight/rollback registry 草案。
4. 明确 N4/N5 仍只消费 canonical metric/event，不自行拼 raw minute。
5. 输出是否允许进入 production implementation gate。
```
