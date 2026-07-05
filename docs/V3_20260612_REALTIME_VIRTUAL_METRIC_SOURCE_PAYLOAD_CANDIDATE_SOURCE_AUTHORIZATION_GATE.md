# V3 20260612 Realtime Virtual Metric Source Payload Candidate Source Authorization

- result: `PASS`
- layer_role: `runtime_control`
- target next owner: `N3_market_data`

## Decision

允许下一步 N3 只读参考旧系统 SQLite：

```text
/Users/chuanfuchen/stock_monitor_isolated/data/monitor.db
```

授权范围仅限：

```text
action_fact_cache
minute_kline
```

用途仅限重建 20260612 `B_BUY=76 / S_SELL=24` 的完整 100 条候选清单，并生成：

```text
docs/V3_20260612_realtime_virtual_metric_writer_payload.json
docs/V3_20260612_realtime_virtual_metric_writer_payload.md
```

## Required Boundaries

- SQLite 必须使用 read-only URI / `mode=ro`。
- 不修改旧系统数据库或文件。
- 不读取旧系统其它表。
- 不启动或检查旧系统服务 / LaunchAgent。
- 旧系统只作为 diagnostic candidate source，不得登记为 v3 active lineage。
- 不写 V3 DB。
- 不 execute writer。
- 不启动 scheduler / worker。
- 不进入 N4/N5/N6。
- 不消费或更新 outbox / inbox / checkpoint。
- 不触碰 voice / mobile / sim / position / PnL / real trade / proposal / order / trade。

## Next N3 Proofs

下一步 N3 必须证明：

- candidate count = `100`
- B_BUY / S_SELL = `76 / 24`
- source records sufficient
- D/W/M/Q/Y context coverage complete
- old-system reference trace is diagnostic only
- writer execute = `false`
- database written = `false`

## Next Gate

`V3_20260612_REALTIME_VIRTUAL_METRIC_SOURCE_PAYLOAD_CONTRACT_PREFLIGHT_GATE`
