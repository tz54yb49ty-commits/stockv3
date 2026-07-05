# N6 Action Projection 20260608 V13 Index-All Until 09:52 V4 Repair Retry Execute Report

Status: EXECUTED

Layer role: N6_user

Projection run:
`user_projection_shadow_20260608_v13_index_all_until_0952_v4_repair_retry__action_consumer_execute_20260608_v13_index_all_until_0952_v4_repair_retry`

Source action run:
`action_consumer_execute_20260608_v13_index_all_until_0952_v4_repair_retry__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry`

## Execute Summary

The reviewed N6 v4 repair retry shadow projection execute command completed with `result=EXECUTED`.

The runner report shows:

- `preflight_result=PREFLIGHT_PASS`
- `committed=true`
- `notification_queue_policy=deferred`
- `blockers=[]`
- `P0/P1/P2=0/5/2`
- `n5_outbox_unchanged=true`

Report path:

- `docs/N6_ACTION_PROJECTION_20260608_V13_INDEX_ALL_UNTIL_0952_V4_REPAIR_RETRY_EXECUTE_REPORT.json`

## Write Counts

Allowed N6 write scope:

| table | expected | actual |
| --- | ---: | ---: |
| `user_projection_run` | 1 | 1 |
| `user_signal_projection` | 119 | 119 |
| `user_signal_card` | 119 | 119 |
| `user_notification_queue` | 0 | 0 |

No notification queue rows were written.

Note: the JSON report's `side_effects.writes_database` field retains the dry-run side-effect model, but `write_summary.committed=true`, `write_summary.write_tables`, `write_summary.write_counts`, and live DB scoped counts are the execution proof.

## Input Event Proof

N5 source events consumed for planning/projection:

| event_type | status | count |
| --- | --- | ---: |
| `ActionEligible` | `pending` | 119 |

The N5 outbox stayed unchanged after execute:

| event_type | status | count |
| --- | --- | ---: |
| `ActionEligible` | `pending` | 119 |

Delivered/delivering rows for this source run remained zero.

## HINT 30m Projection/Card Proof

Projection rows:

| proof item | count |
| --- | ---: |
| `condition_key IN (BUY_HINT, SELL_HINT)` | 119 |
| `trigger_period=30m` | 119 |
| `primary_trigger_period IS NULL` | 119 |
| `triggered_periods=[]` | 119 |
| `all_trigger_periods=[]` | 119 |
| `action_state=eligible` | 119 |
| `action_mark IS NULL` | 119 |
| `trigger_mark_candidate` present | 119 |

Card rows:

| proof item | count |
| --- | ---: |
| `condition_key IN (BUY_HINT, SELL_HINT)` | 119 |
| direct `card_payload_json.trigger_period=30m` | 119 |
| `action_state=eligible` | 119 |
| `action_mark IS NULL` | 119 |
| direct `source_event_type=ActionEligible` | 119 |
| direct `projection_policy` present | 119 |
| direct `trace_json.trigger_mark_candidate/candidate_action_mark` present | 119 |

Card rows are linked to their projection rows by `user_signal_projection_id`. The linked projection payload preserves:

| linked projection proof item | count |
| --- | ---: |
| `trigger_period=30m` | 119 |
| `primary_trigger_period IS NULL` | 119 |
| `triggered_periods=[]` | 119 |
| `all_trigger_periods=[]` | 119 |
| `trigger_mark_candidate` present through payload/trace | 119 |

Condition key distribution:

| condition_key | count |
| --- | ---: |
| `BUY_HINT` | 116 |
| `SELL_HINT` | 3 |

## Forbidden Scope Proof

Live scoped checks:

| scope | count |
| --- | ---: |
| `user_notification_queue` scoped rows | 0 |
| linked `user_signal_decision` refs | 0 |
| linked `user_sim_order/user_sim_trade/user_sim_position` refs | 0 / 0 / 0 |
| linked `n6_virtual_order/trade/position/position_event/pnl` refs | 0 / 0 / 0 / 0 / 0 |
| `common_event_inbox` refs for this projection/action run | 0 |
| `common_event_consumer_checkpoint` refs for this projection run | 0 |

Optional voice/mobile delivery tables were absent:

- `user_voice_delivery`
- `user_mobile_delivery`
- `user_notification_delivery`

The runner report also records:

- `n5_outbox_consumed=false`
- `updates_n5_outbox_status=false`
- `writes_n5_inbox_or_checkpoint=false`
- `starts_worker=false`
- `actual_push=false`
- `voice_mobile_push=false`
- `real_trade=false`
- `old_system_touched=false`

## Rollback Proof

Rollback SQL path:

- `sql/N6_projection_20260608_v13_index_all_until_0952_v4_repair_retry_rollback.sql`

Static review:

- hard-fail guards run before the first `DELETE`
- linked decision/sim/voice/mobile/position refs block rollback
- delete order is `user_notification_queue -> user_signal_card -> user_signal_projection -> user_projection_run`
- no `CASCADE`, `DROP`, or `TRUNCATE`
- no N5/N4/N3/N2/N1 mutation

Rollback was not executed in this gate.

## Next Gate

Allowed next gate:

- `runtime_control` -> `N6_ACTION_PROJECTION_20260608_V13_INDEX_ALL_UNTIL_0952_V4_REPAIR_RETRY_POST_REVIEW_GATE`
