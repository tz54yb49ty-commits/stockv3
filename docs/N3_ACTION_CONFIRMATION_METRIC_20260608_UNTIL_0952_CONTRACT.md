# N3 Action-Confirmation Metric 20260608 Until 09:52 Contract

Result: CONTRACT_PASS

Metric run id: `action_confirmation_metric_20260608_until_0952__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry`

## Source Proof

- N4 run: `trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry` passed
- legal TriggerMatched: 119 (`stock=113`, `index=6`, `board=0`)
- condition_key: `BUY_HINT=116`, `SELL_HINT=3`
- A1/C1/B2 source runs: passed
- C1 latest closed minute: `2026-06-08T09:52:00+08:00`
- existing target metric run rows: 0

## Planned Write Scope

Future execute may write only:

- `common_market_data_run`
- `common_market_data_quality_item`
- `stock_action_confirmation_projection_metric`
- `index_action_confirmation_projection_metric`
- `board_action_confirmation_projection_metric`

Expected metric rows: `stock=113 index=6 board=0 total=119`.

## Execute Candidate

Canonical existing runner:

```bash
PYTHONPATH=src:scripts python3 scripts/run_n3_action_confirmation_metric_materialization_execute.py --payload-path docs/N3_action_confirmation_metric_20260608_until_0952_payload.json --contract-path docs/N3_ACTION_CONFIRMATION_METRIC_20260608_UNTIL_0952_CONTRACT.json --execute --user-confirmed
```

The requested alias command is recorded in JSON as `requested_alias_command_draft`; that script is not required for this artifact gate.

## Quality

P0/P1/P2: 0/0/0

Rollback SQL: `sql/N3_action_confirmation_metric_20260608_until_0952_rollback.sql`
