# N2 Symmetry Secondary Anchor 20260529 V5 Execute Post-Review

Status: **POST_REVIEW_PASS**

## Run Status

- new_run_id: `condition_layer_20260529_source_20260529_v5`
- new_status: `passed_active`
- previous_active_run_id: `condition_layer_20260529_source_20260529_v4`
- previous_status: `superseded`
- active_passed_active_count: `1`
- P0/P1/P2: `0/6/3`

## Row Counts

- condition_basis: stock=`5506` index=`83` board=`428`
- condition_pool: stock=`4106` index=`187` board=`942`
- minute_target_scope: stock=`4087` index=`187` board=`942`
- condition_display_basis: stock=`1862` index=`83` board=`428`
- monitor_target: stock=`5506` index=`83` board=`428`
- common_condition_quality_item: `106`

## Golden Proof

- 300327 中颖电子: reference=`38.27`, secondary=`33.04`, secondary segment `20260525 -> 20260529`
- 000600 建投能源: reference=`12.93`
- 000543 皖能电力: reference=`10.82`
- 000027 深圳能源: reference=`8.45`

## Boundary Proof

- common_market_data_run refs: `0`
- common_trigger_run refs: `0`
- common_action_run refs: `0`
- common_event_outbox refs: `0`
- common_event_inbox refs: `0`
- common_event_consumer_checkpoint refs: `0`
- N3/N4/N5/N6 auto switch: `false`
- market data pulled: `false`
- worker started: `false`

## Rollback

- rollback_sql: `sql/N2_symmetry_secondary_anchor_20260529_v5_rollback.sql`
- rollback_safe: `True`
- guard: rollback must be blocked if v5 has N3/N4/N5/N6 downstream refs.
