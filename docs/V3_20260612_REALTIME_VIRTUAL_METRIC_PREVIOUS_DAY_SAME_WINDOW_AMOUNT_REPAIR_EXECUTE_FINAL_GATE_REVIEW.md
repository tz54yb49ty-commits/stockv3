# V3 20260612 Previous Day Same Window Amount Repair Execute Final Gate Review

Result: `BLOCKED`

## Final Gate Findings

The N3 repair implementation itself is valid, but the current SQL is not executable in the live lineage state.

- repair result: `REPAIR_PASS`
- payload/writer coverage: `previous_day_same_window_amount=100/100`
- target metric rows: stock/index/board = `62/0/38`
- live schema: all three metric tables still miss `previous_day_same_window_amount`
- repair SQL static safety: `PASS`
- live guard status: `BLOCKED`

Reason:

The repair SQL has conservative downstream guards. Those guards currently find refs to the target `projection_run_id` in N4/N5 rows, so the SQL would hard-fail before `ALTER TABLE` / `UPDATE`.

## Payload Coverage Proof

Source:

- `docs/V3_20260612_REALTIME_VIRTUAL_METRIC_PREVIOUS_DAY_SAME_WINDOW_AMOUNT_REPAIR.json`
- `docs/V3_20260612_realtime_virtual_metric_writer_payload.json`

Counts:

- candidates: `100`
- signal distribution: `B_BUY=76`, `S_SELL=24`
- asset distribution: stock/index/board = `62/0/38`
- `previous_day_same_window_amount_non_null=100`

## Live Schema / Row Proof

Read-only DB probe:

- DB: `ashare_v3`
- user: `ashare_v3_user`
- host: `127.0.0.1:5432`

Target projection run:

`action_confirmation_projection_metric_20260612_realtime_virtual_metric_new_plan__condition_layer_20260611_source_20260611_for_20260612_v1`

Rows and schema:

| table | rows | previous_day_same_window_amount column |
|---|---:|---|
| stock_action_confirmation_projection_metric | 62 | absent |
| index_action_confirmation_projection_metric | 0 | absent |
| board_action_confirmation_projection_metric | 38 | absent |

## Repair SQL Safety Proof

SQL:

`sql/V3_20260612_realtime_virtual_metric_previous_day_same_window_amount_repair.sql`

Static safety:

- default hard-fail before first `ALTER TABLE` / `UPDATE`
- requires session flag: `ashare_v3.allow_v3_20260612_previous_day_same_window_amount_repair=true`
- scoped to one `projection_run_id`
- additive column only
- scoped backfill only
- does not write N4/N5/N6 tables
- does not write outbox/inbox/checkpoint
- no `DROP` / `TRUNCATE` / `CASCADE`

Live guard blocker:

| guard | refs |
|---|---:|
| common_event_outbox | 4497 |
| common_event_inbox | 0 |
| common_event_consumer_checkpoint | 0 |
| common_trigger_match | 4454 |
| common_action_event | 43 |
| user_signal_projection | 0 |

Therefore the current SQL is correctly safe, but it cannot be approved for execution against the current live state.

## Validation Proof

Fresh verification:

- targeted tests: `29 OK`
- JSON parse: `PASS`
- compileall: `PASS`
- repair SQL static check: `PASS`

- `git diff --check`: `PASS`

## Execute Command

No execute command is authorized by this gate.

Blocked draft for after policy clearance only:

```bash
psql "postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3" -v ON_ERROR_STOP=1 <<'SQL'
SET ashare_v3.allow_v3_20260612_previous_day_same_window_amount_repair = 'true';
\i sql/V3_20260612_realtime_virtual_metric_previous_day_same_window_amount_repair.sql
SQL
```

## Forbidden Scope Proof

This gate did not:

- execute repair SQL
- write database rows
- execute writer/N3/N4/N5
- execute rollback
- consume/update outbox/inbox/checkpoint
- start worker
- enter N6
- touch voice/mobile/sim/position/order/trade
- modify old system

## Repair After Route

Recommended next step:

`V3_20260612_PREVIOUS_DAY_SAME_WINDOW_AMOUNT_REPAIR_DOWNSTREAM_REF_POLICY_GATE`

This should decide whether to:

1. scoped rollback/supersede stale N5 first, then refresh repair SQL to allow reviewed N4 refs for additive backfill;
2. rollback N4/N5 refs before executing the original SQL;
3. generate a new projection run instead of modifying already referenced facts.

## Next Prompt

```text
layer_role=runtime_control。

进入 V3_20260612_PREVIOUS_DAY_SAME_WINDOW_AMOUNT_REPAIR_DOWNSTREAM_REF_POLICY_GATE。

目标：只读决策 previous_day_same_window_amount additive schema/backfill repair 在当前已有 N4/N5 refs 下的执行路线。当前 repair SQL 静态安全，但 live guard 会因 common_event_outbox_refs=4497、common_trigger_match_refs=4454、common_action_event_refs=43 阻断。请决定：1）先 scoped rollback/supersede stale N5，再调整 repair SQL 允许 N4 refs 的 additive backfill；2）先 rollback N4/N5 后执行原 SQL；3）重新生成新 projection_run_id 避免改写已引用事实。不得执行 SQL、不得写 DB、不得消费/update outbox/inbox/checkpoint、不得进入 N4/N5/N6/voice/mobile/sim/trade。输出 POLICY_PASS/BLOCKED、recommended route、next prompt。
```
