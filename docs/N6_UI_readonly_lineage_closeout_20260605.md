# RUNTIME_20260605_READONLY_LINEAGE_CLOSEOUT_GATE

Status: `POST_REVIEW_PASS`  
Layer role: `runtime_control`  
Generated at: `2026-06-06T10:49:25+08:00`

## Scope

本报告只读收口 20260605 N2/N3/N4/N5/N6/UI 全链路 lineage。所有 DB probe 使用 PostgreSQL `default_transaction_read_only=on`，未执行 N2-N6 command，未写业务数据，未消费/update outbox 或 inbox，未启动 worker，未触发 delivery/push/voice/mobile/sim/position/pnl/real_trade。

主线 lineage：

| Layer | Run |
|---|---|
| N2 condition | `condition_layer_20260604_source_20260604_v1` |
| N2 context enrichment / N4 context snapshot | `trigger_context_snapshot_20260605_condition_layer_20260604_source_20260604_v1` |
| N3 snapshot | `realtime_snapshot_20260605_live2_market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1` |
| N3 realtime projection | `realtime_projection_metric_20260605_live2_compat__realtime_snapshot_20260605_live2_market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1` |
| N3 action metric | `action_confirmation_projection_metric_20260605__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1` |
| N4 execute | `trigger_execute_20260605_condition_layer_20260604_source_20260604_v1` |
| N5 action | `action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1` |
| N6 projection | `user_projection_shadow_20260605__action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1` |

## P0/P1/P2

Closeout findings: `P0=0 / P1=0 / P2=2`.

| Severity | Item | Explanation | Blocking |
|---|---|---|---|
| P2 | accepted classification trace gap | N2 dry-run retained legacy classification trace gap `73/25590` period entries, `47/5118` rows affected. It was previously accepted by runtime_control because `trigger_*` semantic coverage is complete and N4 trigger baselines do not use legacy `previous_*`. | No |
| P2 | N6 standalone execute report artifact absent | No separate `N6_ACTION_PROJECTION_EXECUTE_REPORT.json` was found. Contract/preflight/traceability/runner alignment plus live DB `user_projection_run` proof cover this closeout. | No |

Source layer quality counters remain visible and accepted: N2 condition run `0/6/3`, N3 realtime projection `0/4/0`, N3 action metric `0/2/0`, N4 execute `0/1/0`, N6 projection run `0/5/2`. These are prior-gate quality counters, not closeout blockers.

## Artifact Consistency

Artifact JSON parse: `PASS`.

| Gate / Artifact | Status |
|---|---|
| `docs/N2_N4_TRIGGER_CONTEXT_REFRESH_DRY_RUN.json` | classification gap accepted exception |
| `docs/N2_N4_TRIGGER_CONTEXT_REFRESH_EXECUTE_CONTRACT.json` | planned context rows `4186/20/912 = 5118` |
| `docs/N2_N4_TRIGGER_CONTEXT_REFRESH_EXECUTE_PREFLIGHT.json` | no remaining blockers |
| `docs/N2_N4_TRIGGER_CONTEXT_REFRESH_N4_EXECUTE_REPORT.json` | context run exists |
| `docs/N4_CONTEXT_REFRESH_READER_ALIGNMENT_DRY_RUN.json` | `DRY_RUN_PASS` |
| `docs/N4_CONTEXT_REFRESH_POST_REVIEW_REPAIR.json` | `REPAIR_PASS` |
| `docs/N4_20260605_V4_REPAIRED_CONTEXT_CORRECTED_DRY_RUN.json` | `DRY_RUN_PASS` |
| `docs/N4_20260605_V4_REPAIRED_CONTEXT_CORRECTED_EXECUTE_CONTRACT.json` | `CONTRACT_PASS`, planned TriggerMatched `605` |
| `docs/N4_20260605_V4_REPAIRED_CONTEXT_CORRECTED_EXECUTE_PREFLIGHT.json` | `PREFLIGHT_PASS` |
| `docs/N4_20260605_V4_CORRECTED_EXECUTE_REPORT.json` | `EXECUTE_PASS` |
| `docs/N3_20260605_REPAIRED_CONTEXT_ACTION_CONFIRMATION_METRIC_PREFLIGHT.json` | `PREFLIGHT_PASS` |
| `docs/N3_20260605_repaired_context_action_confirmation_metric_dry_run_report.json` | `DRY_RUN_PASS` |
| `docs/N5_ACTION_PIPELINE_EXECUTE_CONTRACT.json` | `CONTRACT_PASS`, planned action events/outbox `605` |
| `docs/N5_ACTION_PIPELINE_EXECUTE_PREFLIGHT.json` | `PREFLIGHT_PASS` |
| `docs/N5_ACTION_PIPELINE_EXECUTE_REPORT.json` | `EXECUTED` |
| `docs/N6_SHADOW_PROJECTION_DRY_RUN.json` | `DRY_RUN_PASS` |
| `docs/N6_ACTION_PROJECTION_EXECUTE_CONTRACT.json` | `CONTRACT_PASS`, planned projection/card `605/605`, queue `0` |
| `docs/N6_ACTION_PROJECTION_EXECUTE_PREFLIGHT.json` | `EXECUTE_PREFLIGHT_PASS` |
| `docs/N6_ACTION_PROJECTION_RUNNER_QUEUE_DEFERRED_ALIGNMENT.json` | `ALIGNMENT_PASS` |
| `docs/N6_ACTION_PROJECTION_TRACEABILITY.json` | `TRACEABILITY_PASS` |
| `docs/N6_UI_READONLY_ACTION_CARD_ADAPTER_CONTRACT.json` | `CONTRACT_PASS` |
| `docs/N6_UI_READONLY_ACTION_CARD_ADAPTER_DRY_RUN.json` | superseded old-implementation blocker |
| `docs/N6_UI_READONLY_ACTION_CARD_ADAPTER_IMPLEMENTATION.json` | `IMPLEMENTATION_PASS`, remaining blockers `[]` |

## Data Proof

### N2

| Table family | Stock | Index | Board | Total |
|---|---:|---:|---:|---:|
| condition_basis | 5511 | 9 | 428 | 5948 |
| condition_pool | 4207 | 20 | 912 | 5139 |
| minute_target_scope | 4186 | 20 | 912 | 5118 |
| condition_context_enrichment | 4186 | 20 | 912 | 5118 |

N2 context enrichment status is `passed`, `P0/P1/P2=0/0/0`.

Trigger baseline semantic checks:

| Check | Count |
|---|---:|
| calculable period entries | 25517 |
| trigger high/low missing | 0 |
| trigger amount baseline missing | 0 |
| baseline_source_trade_date mismatch | 0 |
| trigger high not max(current_open_seed,current_close_seed) | 0 |
| trigger low not min(current_open_seed,current_close_seed) | 0 |
| trigger amount not current_amount_seed | 0 |

Semantic samples:

| Asset | D trigger high | D trigger low | current_open_seed | current_close_seed |
|---|---:|---:|---:|---:|
| `stock:SZ:002399` | 9.66 | 9.45 | 9.66 | 9.45 |
| `index:SZ:399006` | 4088.88 | 4072.55 | 4072.55 | 4088.88 |

### N3

| Run | Status | P0/P1/P2 | Stock | Index | Board | Total | Outbox | Worker |
|---|---|---|---:|---:|---:|---:|---|---|
| B1 snapshot | passed | 0/0/0 | 1952 | 9 | 428 | 2389 | false | false |
| B2 realtime projection | passed | 0/4/0 | 1952 | 9 | 428 | 2389 | false | false |
| action-confirmation metric | passed | 0/2/0 | 316 | 0 | 0 | 316 | false | false |

N3 action-confirmation metric ready rows: `316`.

### N4

N4 context snapshot rows: stock/index/board=`4186/20/912`, total=`5118`.

N4 execute run status: `passed`, `P0/P1/P2=0/1/0`.

| Output | Count |
|---|---:|
| common_trigger_state | 605 |
| common_trigger_match | 605 |
| common_event_outbox TriggerMatched pending | 605 |
| TriggerPendingMarketData | 0 |
| TriggerStateChanged | 0 |

By asset: stock=`572`, board=`33`, index=`0`.  
By signal: `B_BUY=573`, `S_SELL=32`.

N4 side-effect flags: action layer touched=false, user layer touched=false, voice=false, sim=false, real_trade=false, worker=false.

### N5

N5 action run status: `passed`, `P0/P1/P2=0/0/0`.

| Output | Count |
|---|---:|
| stock_action_fact | 572 |
| index_action_fact | 0 |
| board_action_fact | 33 |
| common_action_event | 605 |
| common_event_outbox | 605 |
| position_event | 0 |

Action distribution:

| Event | Count |
|---|---:|
| ActionExecuted | 1 |
| ActionBlocked | 604 |
| ActionSkipped | 0 |
| ActionEligible | 0 |

Blocked reasons:

| Reason | Count |
|---|---:|
| price_confirmation_failed | 305 |
| metric_missing | 289 |
| amount_confirmation_failed | 10 |

N5 outbox remains pending: ActionExecuted=`1`, ActionBlocked=`604`, delivering=`0`, delivered=`0`.

### N6

N6 projection run status: `passed`, `P0/P1/P2=0/5/2`.

| Output | Count |
|---|---:|
| user_signal_projection | 605 |
| user_signal_card | 605 |
| user_notification_queue | 0 |
| user_signal_decision refs scoped to run | 0 |

Projected card distribution: ActionExecuted=`1`, ActionBlocked=`604`.

## Sample Proof

N4 TriggerMatched samples:

| Event | Asset | Signal | Condition | Period | Price | Mark |
|---|---|---|---|---|---:|---|
| `evt_dc7e6ef5c43c377d6f27ceaec85aa4cb8cf129e1` | `stock:SH:600009` | B_BUY | `BUY:Y,Q,M,W,D` | D | 23.63 | normal |
| `evt_2e7c4b44e258dcc77c1fbaebf8d7ac59fb563312` | `stock:SH:600010` | B_BUY | `BUY:Q,M,W,D` | D | 2.43 | normal |

N5 Action samples:

| Event | Type | Asset | Signal | State | Mark | Blocked reason |
|---|---|---|---|---|---|---|
| `evt_14581cc071ab335b100a3abeb83464021137446a` | ActionExecuted | `stock:SZ:300910` | B_BUY | executed | normal |  |
| `evt_c125c176141d0598e0a3a4599015c3bc3786289e` | ActionBlocked | `board:TDX:880202` | S_SELL | blocked |  | metric_missing |

N6 projection/card sample:

| Projection | Card | Source event | Asset | Signal | State | Title |
|---:|---:|---|---|---|---|---|
| 5666 | 5666 | `evt_c125c176141d0598e0a3a4599015c3bc3786289e` | `board:TDX:880202` | S_SELL | blocked | `board:TDX:880202 S_SELL` |

## UI Readonly Proof

| Check | Result |
|---|---:|
| `/api/n6/ui/v1/signals` empty filters | 605 |
| `action_state=blocked&blocked_reason=price_confirmation_failed` | 305 |
| ActionExecuted | 1 |
| ActionBlocked | 604 |
| price_confirmation_failed | 305 |
| metric_missing | 289 |
| amount_confirmation_failed | 10 |

ActionExecuted detail proof:

- `proposal_eligibility.behavior=projection_only`
- `future_eligible=false`
- `proposal_candidate` not displayed
- proposal/order/trade/position/PnL/real_trade generated flags are all false
- display text: `管理员只读投影，不生成 proposal / order / trade / position / PnL`

A轨 readonly route scan: `PASS`, GET-only for N6_UI_v1 readonly adapter routes. Disabled/hidden scopes remain delivery, push, voice, mobile, sim, position, pnl, real_trade, monitor filter, portfolio.

## Forbidden Scope Proof

| Forbidden scope | Proof |
|---|---:|
| N5 outbox pending | 605 |
| N5 outbox delivering/delivered | 0 / 0 |
| N5 delivery attempt refs | 0 |
| inbox refs to N5 outbox | 0 |
| user_notification_queue for projection run | 0 |
| common_position_state/event | 0 / 0 |
| user_sim_order/trade/position | 0 / 0 / 0 |
| n6_virtual_order/trade/position/position_event/pnl_snapshot | 0 / 0 / 0 / 0 / 0 |
| user_signal_decision | 0 |

No proposal/order/trade/position/PnL/real_trade was generated by UI. No delivery/push/voice/mobile/sim path was triggered.

## Decision

`RUNTIME_20260605_READONLY_LINEAGE_CLOSEOUT_GATE` is `POST_REVIEW_PASS`.

`N6_UI_v1 readonly action card adapter` can remain marked complete.

Recommended next gate: `RUNTIME_20260605_FINAL_ARCHIVE_AND_ROLLBACK_REGISTRY_REVIEW_GATE`.
