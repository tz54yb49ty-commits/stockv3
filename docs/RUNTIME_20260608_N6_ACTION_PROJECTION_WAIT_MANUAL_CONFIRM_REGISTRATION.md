# Runtime 20260608 N6 Action Projection Wait Manual Confirm Registration

Status: `WAIT_MANUAL_CONFIRM`

This runtime-control registration is read-only. It did not execute N6, did not write N6 projection/card rows, did not consume or update N5 outbox, and did not start a worker.

## Source

- source action run: `action_consumer_execute_20260608_v13_index_all_until_0952__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952`
- source trigger run: `trigger_projection_matcher_execute_20260608_v13_index_all_until_0952`
- projection run: `user_projection_shadow_20260608_v13_index_all_until_0952__action_consumer_execute_20260608_v13_index_all_until_0952`
- required execute layer role: `N6_user`

## Baseline

- N5 outbox: `ActionEligible pending=201`
- delivered/delivering: `0/0`
- scoped `user_projection_run`: `0`
- scoped `user_signal_projection`: `0`
- scoped `user_signal_card`: `0`
- scoped `user_notification_queue`: `0`
- linked decision/sim refs: `0`

## Approved Scope

- `user_projection_run=1`
- `user_signal_projection=201`
- `user_signal_card=201`
- `user_notification_queue=0`
- notification queue policy: `deferred`

## Blocked Scope

No runtime_control execute, no N5 outbox consumption/update, no N5 inbox/checkpoint writes, no notification queue, no delivery/push/voice/mobile, no sim/position/PnL/real trade, no proposal/order/trade, no worker, and no old-system touch.

## Execute Command

Run only after switching to `layer_role=N6_user`:

```bash
PYTHONPATH=src:scripts python3 scripts/run_n6_projection_once.py --projection-run-id user_projection_shadow_20260608_v13_index_all_until_0952__action_consumer_execute_20260608_v13_index_all_until_0952 --source-action-run-id action_consumer_execute_20260608_v13_index_all_until_0952__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952 --contract-json-path docs/N6_ACTION_PROJECTION_20260608_V13_INDEX_ALL_UNTIL_0952_EXECUTE_CONTRACT.json --preflight-json-path docs/N6_ACTION_PROJECTION_20260608_V13_INDEX_ALL_UNTIL_0952_EXECUTE_PREFLIGHT.json --expected-n5-outbox-count ActionEligible:pending=201 --execute --user-confirmed --json > docs/N6_ACTION_PROJECTION_20260608_V13_INDEX_ALL_UNTIL_0952_EXECUTE_REPORT.json
```

Return to runtime_control after execute:

`N6_ACTION_PROJECTION_20260608_V13_INDEX_ALL_UNTIL_0952_POST_REVIEW_GATE`
