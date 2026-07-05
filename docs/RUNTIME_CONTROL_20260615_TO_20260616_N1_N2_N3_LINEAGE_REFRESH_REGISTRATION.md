# Runtime Control 20260615 -> 20260616 N1/N2/N3 Lineage Refresh Registration

Result: `REGISTRATION_PASS`

This gate is documentation-only registration. It did not execute N1/N2/N3, did not write database rows, did not consume or update outbox/inbox/checkpoint, did not enter N4/N5/N6, did not start workers, and did not execute rollback SQL.

## Active Lineage Summary

- Source trade date: `20260615`
- For trade date: `20260616`
- Active N1 financial source: `stock_financial_20260615_v3`
- Active N2 condition run: `condition_layer_20260615_source_20260615_for_20260616_v4`
- Active N3 subscription run: `market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4`
- Active N3 A1 preload run: `previous_day_minute_preload_20260615_for_20260616__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4`

## N1 Proof

- N1 post-review: `POST_REVIEW_PASS`
- Active financial source version: `stock_financial_20260615_v3`
- Rows: `5504`
- Changed semantic row: `stock:SZ:002831`
- `active_v3=1`

002831 target row summary:

```text
source_type=tdx_financial_package
interest_expense=19744658
report_core_profit=341586050
core_profit_ttm=1940382164
pe_core=20.2506996374
score=87
```

## N2 Proof

- N2 post-review: `POST_REVIEW_PASS`
- Active condition run: `condition_layer_20260615_source_20260615_for_20260616_v4`
- v4 status: `passed_active`
- v3 status: `superseded`
- Active run count: `1`

Row counts:

```text
condition_basis stock/index/board=5504/83/427
condition_pool stock/index/board=4215/183/307
minute_target_scope stock/index/board=4194/183/307
condition_display_basis stock/index/board=1822/83/127
```

## N3 Proof

- N3 post-review: `POST_REVIEW_PASS`
- Subscription run: `market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4`
- Subscription status: `passed`
- Candidate/subscription/pull_plan: `5924/3272/9`
- Subscription objects: `2032`

A1 preload:

```text
run_id=previous_day_minute_preload_20260615_for_20260616__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4
status=passed
objects stock/index/board=550/17/53
minute rows stock/index/board=132000/4080/12720
```

## Prior Lineage Preservation

- N2 v1/v2/v3 evidence remains preserved.
- N3 v1/v2 evidence remains preserved.
- N3 v3 had no persisted subscription/preload rows to mutate.
- This runtime_control registration did not mutate any lineage.

## Rollback Strategy

- N1 rollback: `sql/N1_stock_financial_002831_tdx_parity_repair_20260615_rollback.sql` restores active financial source to v2 if authorized later.
- N2 rollback: `sql/N2_condition_source_refresh_for_stock_financial_20260615_v3_rollback.sql` restores N2 v3 `passed_active` if authorized later.
- N3 rollback: `sql/N3_lineage_refresh_for_N2_20260615_v4_rollback.sql` deletes only scoped v4 N3 rows if authorized later.
- If rollback is ever authorized, reverse order is required: N3 v4 -> N2 v4 -> N1 financial v3.
- No rollback SQL was executed in this gate.

## Forbidden Scope Proof

```text
database_written_by_this_gate=false
n1_n2_n3_executed_by_this_gate=false
common_event_outbox_inbox_checkpoint_consumed_or_updated=false
n3_b_c_b2_executed_by_this_gate=false
n4_n5_n6_entered=false
worker_started=false
rollback_executed=false
```

## Status / Dashboard Caveat

The existing post-close one-shot status for `20260616` is `EXECUTE_PASS`, but it may still describe earlier lineage generated before the manual v4 refresh. The current effective lineage is the manual v4 refresh registered here.

If the 8786 status page or `docs/post_close_fastlane/20260616` should display v4 as the current effective lineage, use a separate status refresh artifact gate. Do not silently rewrite the original one-shot evidence.

Recommended next gate:

`RUNTIME_CONTROL_20260615_TO_20260616_POST_CLOSE_FASTLANE_STATUS_REFRESH_GATE`
