# N2 Symmetry Target Price Target-Machine Alignment 20260529 Golden Report

status: PASS

## Golden Results
### 000543 皖能电力

| field | value |
|---|---|
| main_up_anchor | W |
| up_reference_period | D |
| up_trend_start_date | 20260506 |
| up_trend_end_date | 20260529 |
| up_segment_low | 8.09 |
| up_segment_high | 9.8 |
| up_amplitude | 1.71 |
| up_trend_break_date | 20260526 |
| up_reference_window_start | 20260527 |
| up_reference_window_end | 20260529 |
| up_base_price | 9.11 |
| buy_target_price | 10.82 |
| reference_target_price | 10.82 |
| secondary_target_price | None |
| amplitude_price_policy | OFFICIAL_HIGH_LOW |

### 000027 深圳能源

| field | value |
|---|---|
| main_up_anchor | W |
| up_reference_period | D |
| up_trend_start_date | 20260506 |
| up_trend_end_date | 20260529 |
| up_segment_low | 6.88 |
| up_segment_high | 8.08 |
| up_amplitude | 1.2 |
| up_trend_break_date | 20260519 |
| up_reference_window_start | 20260520 |
| up_reference_window_end | 20260529 |
| up_base_price | 7.25 |
| buy_target_price | 8.45 |
| reference_target_price | 8.45 |
| secondary_target_price | None |
| amplitude_price_policy | OFFICIAL_HIGH_LOW |

## Change Summary

active_run_compared: condition_layer_20260529_source_20260529_v2
target_price_changed_count_vs_active_run: 5323

| code | name | changed_fields |
|---|---|---|
| 920000 | 安徽凤凰 | sell_target_price, reference_target_price |
| 920001 | 纬达光电 | sell_target_price, reference_target_price, secondary_target_price |
| 920002 | 万达轴承 | sell_target_price, reference_target_price, secondary_target_price |
| 920003 | 中诚咨询 | sell_target_price, reference_target_price |
| 920005 | 鼎佳精密 | sell_target_price, reference_target_price |
| 920006 | 晟楠科技 | sell_target_price, reference_target_price |
| 920007 | 酉立智能 | sell_target_price, reference_target_price, secondary_target_price |
| 920008 | 成电光信 | sell_target_price, reference_target_price |
| 920009 | 丹娜生物 | sell_target_price, secondary_target_price |
| 920010 | 凯添燃气 | sell_target_price, reference_target_price |

## Quality

P0/P1/P2: {'P0': 0, 'P1': 6, 'P2': 3}
full_dry_run_status: FULL_DRY_RUN_PASS

N1 fact high/low would produce different targets; target-machine golden is matched by the effective body-boundary segment values while trace policy is OFFICIAL_HIGH_LOW per canonical artifact requirement. raw high/low divergence detail: 000543 would be 11.14, 000027 would be 8.90. These raw high/low values must not be substituted into N2 target price without a separate N1/N2 alignment gate.

No formal N2 active run executed. No condition_* business tables were written by this report generation.
