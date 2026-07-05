# N6 Action Projection 20260608 Until 15:00 Unified Output Retry Final Gate Review

- result: `PASS`
- execute performed: `false`
- database write performed: `false`
- allowed next gate: `N6_ACTION_PROJECTION_20260608_UNTIL_1500_UNIFIED_OUTPUT_RETRY_EXECUTE_USER_CONFIRMATION_GATE`

## Source Proof

- readiness=`READINESS_PASS`
- N5 action run status=`passed`
- ActionExecuted pending=`7`
- ActionBlocked pending=`549`
- delivered/delivering=`0/0`
- N6 scoped baseline=`0`
- downstream refs=`0`

## Planned Writes

- user_projection_run=`1`
- user_signal_projection=`556`
- user_signal_card=`556`
- user_notification_queue=`0`

## Semantics

ActionExecuted is display-only market action confirmation, not order/trade/delivery. ActionBlocked preserves blocked_reason and is not an executable recommendation. BUY_HINT/SELL_HINT remain trace/policy context only.

## Allowed Execute Command

```bash
PYTHONPATH=src:scripts python3 scripts/run_n6_projection_once.py \
  --projection-run-id user_projection_shadow_20260608_until_1500_unified_output_retry__action_consumer_execute_20260608_until_1500_unified_output_retry \
  --source-action-run-id action_consumer_execute_20260608_until_1500_unified_output_retry__trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry \
  --contract-json-path docs/N6_ACTION_PROJECTION_20260608_UNTIL_1500_UNIFIED_OUTPUT_RETRY_CONTRACT.json \
  --preflight-json-path docs/N6_ACTION_PROJECTION_20260608_UNTIL_1500_UNIFIED_OUTPUT_RETRY_PREFLIGHT.json \
  --expected-n5-outbox-count ActionExecuted:pending=7 \
  --expected-n5-outbox-count ActionBlocked:pending=549 \
  --execute --user-confirmed --json \
  > docs/N6_ACTION_PROJECTION_20260608_UNTIL_1500_UNIFIED_OUTPUT_RETRY_EXECUTE_REPORT.json
```
