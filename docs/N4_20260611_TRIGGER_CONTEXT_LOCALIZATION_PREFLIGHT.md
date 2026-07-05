# N4 20260611 Trigger Context Localization Preflight

Result: **PREFLIGHT_PASS**

## Target Baseline
- `common_trigger_run`: `0`
- `common_trigger_quality_item`: `0`
- `stock_trigger_context_snapshot`: `0`
- `index_trigger_context_snapshot`: `0`
- `board_trigger_context_snapshot`: `0`
- `common_trigger_state`: `0`
- `common_trigger_match`: `0`
- `common_event_outbox`: `0`
- `common_event_inbox`: `0`
- `common_event_consumer_checkpoint`: `0`
- `common_action_run_refs`: `0`
- `common_action_event_refs`: `0`

## Planned Future Write Scope
Allowed tables:
- `common_trigger_run`
- `common_trigger_quality_item`
- `stock_trigger_context_snapshot`
- `index_trigger_context_snapshot`
- `board_trigger_context_snapshot`

Forbidden tables:
- `common_trigger_state`
- `common_trigger_match`
- `common_event_outbox`
- `common_event_inbox`
- `common_event_consumer_checkpoint`
- `common_action_run/common_action_event`
- N6/user/sim/voice/mobile/order/trade/position tables

## Planned Rows
- stock/index/board/total context rows: `4027/185/268/4480`
- object_count stock/index/board/total: `1890/83/127/2100`
- direction buy/sell: `2215/2265`
- condition signal distribution: `{'BUY': 2067, 'BUY:FULL': 33, 'BUY_HINT': 115, 'SELL': 2081, 'SELL:FULL': 16, 'SELL_HINT': 168}`

## Rollback
- rollback SQL: `sql/N4_20260611_trigger_context_localization_rollback.sql`
- hard-fail before first DELETE/UPDATE: `true`
- guards: outbox/inbox/checkpoint, trigger_state/match, N5 refs, N6/user/sim/order/trade/position refs
- deletes only scoped N4 context localization rows for `trigger_context_snapshot_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`
- no CASCADE/DROP/TRUNCATE

## Future Execute Command Candidate
```bash
PYTHONPATH=src:scripts python3 scripts/run_trigger_context_snapshot_execute.py --condition-run-id condition_layer_20260610_source_20260610_for_20260611_v1 --for-trade-date 20260611 --execute --user-confirmed --json-report-path docs/N4_20260611_TRIGGER_CONTEXT_LOCALIZATION_EXECUTE_REPORT.json --markdown-report-path docs/N4_20260611_TRIGGER_CONTEXT_LOCALIZATION_EXECUTE_REPORT.md --rollback-sql-path sql/N4_20260611_trigger_context_localization_rollback.sql
```

This command is not executed by this gate.

## Remaining Blocker Outside This Gate
The 20260611 N3 event source blocker remains for bounded smoke because the current N3 B1/C1/B2 lineage is fact-only and produced no pending N3 `MarketSnapshotUpdated` outbox rows. This context localization preflight only prepares the N4 context snapshot.

## Boundary
No N4 execute, no DB write, no worker, no N3 outbox consumption/update, no N5/N6, no delivery/push/voice/mobile, no sim/position/pnl/real trade.
