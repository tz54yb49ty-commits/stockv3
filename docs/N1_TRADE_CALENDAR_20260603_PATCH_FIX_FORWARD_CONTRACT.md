# N1 Trade Calendar 20260603 Patch Fix-Forward Contract

Result: `DESIGN_PASS`

This repair is a fix-forward calendar patch: `common_trade_calendar(20260603)`
is missing, but downstream N2/N3/A1 refs already exist.

Source proof:

```text
source = tushare.trade_cal
fallback_used = false
is_open = true
prev_trade_date = 20260602
next_trade_date = 20260604
```

Existing downstream refs:

```text
N2 = condition_layer_20260602_source_20260602_v1
N3 = market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1
A1 = previous_day_minute_preload_20260602_for_20260603__market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1
```

Quality:

```text
P0/P1/P2 = 0/1/0
P1 = fix_forward_downstream_refs_present
```

Future write scope:

```text
common_ingest_batch
common_trade_calendar
common_active_source_version
common_quality_gate_result
```

Forbidden:

```text
daily fact
condition source
outbox/inbox/checkpoint
N2/N3/N4/N5/N6
worker
old system
real trading
```

Rollback policy:

```text
rollback_sql = sql/N1_trade_calendar_20260603_patch_rollback.sql
hard_fail_before_delete = true
calendar patch rollback hard-fails while downstream refs exist
```

If calendar rollback is required, first rollback A1 previous-day minute preload,
N3 subscription, and N2 condition layer, or open a dedicated rollback plan. The
calendar patch itself does not delete or update N2/N3/A1 rows.

Final gate recommendation: `PASS_WITH_RISK_ACCEPTANCE`.
