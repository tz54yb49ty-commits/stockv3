# A股监控系统 v3 条件层开发文档

版本：V0.1
日期：2026-05-23
阶段：N2 条件层

## 1. 目标

v3 已完成原始数据入库层后，下一阶段进入条件层。

条件层的职责是：基于已经入库并通过质量闸门的 stock / index / board 官方事实数据，计算“哪些对象有资格进入后续触发观察”。

条件层只回答三个问题：

```text
1. 哪些对象今天需要进入条件池。
2. 它们允许哪些方向：buy / sell。
3. 它们对应哪些条件周期、目标价、清仓周期、上下文元数据。
4. 它们后续允许进入哪些 v3 标准信号候选范围。
```

条件层不负责：

```text
实时行情触发
一分钟 K 拉取
动作生成
语音播报
移动端卡片
模拟账户
真实交易
长期 worker
```

一句话边界：

```text
条件层是资格池，不是触发层，也不是动作层。
```

实时行情边界：

```text
条件层只生成行情订阅范围和前一日分钟 K 预加载需求。
实时行情层统一拉取 realtime_daily_snapshot、minute_bar_1m 和 previous_day_minute_bar_1m。
触发层普通 BUY/SELL/FULL 只读实时日 K / 快照，不依赖实时一分钟 K；N2 不在 `allowed_signal_types` 中表达 30m 语义。后续如需 projection / 30m 动作标记，由 N4 基于 N3 标准 projection 指标转换为 action_mark。N4 不得直接拉行情。
动作层才读取今日一分钟 K 和前一日一分钟 K。
```

## 2. 必读输入文档

进入条件层开发前，v3 会话必须先读取：

```text
AGENTS.md
docs/V3_RAW_DATA_INGESTION_DESIGN.md
docs/V3_EXISTING_RAW_TO_INGESTION_MAPPING.md
docs/V3_CONDITION_LAYER_DEVELOPMENT_DESIGN.md
```

本设计参考了目标机已验证过的条件层文档和代码。目标机路径如下，仅作为只读规则参考，不允许 v3 直接写旧系统：

```text
/Users/chuanfuchen/stock_monitor_isolated/docs/LAYERED_SIGNAL_ARCHITECTURE.md
/Users/chuanfuchen/stock_monitor_isolated/docs/TRADING_SIGNAL_RULEBOOK.md
/Users/chuanfuchen/stock_monitor_isolated/docs/RUNTIME_OPERATION_RULEBOOK.md
/Users/chuanfuchen/stock_monitor_isolated/docs/TARGET_LAYERED_FULL_STACK_RUNBOOK.md
/Users/chuanfuchen/stock_monitor_isolated/services/signal_precompute_service.py
/Users/chuanfuchen/stock_monitor_isolated/run_signal_precompute.py
/Users/chuanfuchen/stock_monitor_isolated/run_layered_signal_pools.py
```

## 3. 与目标机条件层的对应关系

目标机当前条件层实际是两步：

```text
signal_precompute_cache -> signal_condition_pool
```

其中：

```text
signal_precompute_cache：冻结上一交易日的周期分级、金额基准、监控对象、持仓上下文、目标价、清仓参考周期。
signal_condition_pool：从 precompute 中抽取可进入今日观察的 BUY_COND / SELL_COND / HINT 条件池。
```

v3 不照搬旧表名，但必须保留这两个逻辑阶段：

```text
condition_basis：条件基础快照，对应目标机 signal_precompute_cache。
condition_pool：条件池，对应目标机 signal_condition_pool。
```

### 3.1 v3 统一标准信号口径

N2 条件层输出的 `allowed_signal_types` / `selected_signal_types_json` 只表达 canonical 条件语义。指数、行业/板块、个股统一使用同一套 N2 canonical signal_type：

```text
BUY
BUY:FULL
SELL
SELL:FULL
BUY_HINT
SELL_HINT
```

条件层仍然不生成 trigger/action。`condition_key` 不等于 `signal_type`：`condition_key` 保留完整周期组合用于 trace / audit / analytics；`allowed_signal_types` 只保留上述 6 类 canonical 条件语义。

建议字段：

```text
allowed_signal_types
is_hint_scope
daily_snapshot_required
minute_required
previous_day_minute_required
previous_day_minute_date
minute_scope_reason
market_data_consumer
```

对应关系：

```text
BUY:*      -> BUY
SELL:*     -> SELL
BUY:FULL   -> BUY:FULL
SELL:FULL  -> SELL:FULL
BUY_HINT   -> BUY_HINT
SELL_HINT  -> SELL_HINT
```

`BUY_HINT` 和 `SELL_HINT` 保留为正式 signal_type，不限制在指数和板块，也覆盖个股。

N2 不再输出 `B_BUY_30M_VOL / S_SELL_30M_SHRINK`。30m / projection 语义不在 N2 表达，后续由 N4 根据 N3 projection 转成 action_mark。

方向字段只表达：

```text
buy
sell
```

其中：

```text
BUY_HINT -> direction=buy
SELL_HINT -> direction=sell
```

不得再把 hint 作为独立 direction。是否属于超跌/超涨条件族由 `condition_key`、`allowed_signal_types` 或兼容字段 `is_hint_scope` 表达；该字段不得被解释为“非正式触发”。

asset_kind / lane 决定用户层如何处理：

```text
index + market_alert：只提示，不进入模拟账户。
board + market_alert：只提示，不进入模拟账户。
stock + stock_trade：可以进入模拟账户。
stock + stock_alert：只提示，不进入模拟账户。
```

以下不再作为 v3 底层标准信号类型输出：

```text
POS_CLEAR
BUY_FAIL_CLEAR
ADD_BUY_FAIL_REDUCE
POS_REDUCE
POS_REDUCE_TARGET
POS_REDUCE_SECONDARY
```

这些属于用户层 / 持仓策略层解释：

```text
SELL / SELL:FULL + 持仓 + 清仓参考周期 -> 用户层解释为清仓或减仓。
BUY / BUY:FULL + 买入失败生命周期 -> 用户层解释为买入失败止损。
加仓生命周期 -> 用户层解释为加仓失败减仓。
```

一句话：

```text
v3 底层只产出统一标准信号，用户层负责展示、播报、模拟账户、清仓/减仓/失败止损解释。
```

### 3.2 条件层必要条件集合

v3 条件层必须同时定义三类必要条件，不能只生成普通次日买卖条件。

```text
1. 次日普通买卖必要条件：BUY:周期 / SELL:周期
2. FULL 必要条件：BUY:FULL / SELL:FULL
3. 超跌超涨提示必要条件：BUY_HINT / SELL_HINT
```

三类必要条件都只表示“允许后续观察”，不是触发、不是动作。

建议在 condition_basis 中保留以下布尔/文本字段：

```text
buy_necessary_base
buy_necessary_key
buy_necessary_periods

sell_necessary_base
sell_necessary_key
sell_necessary_periods

buy_full_necessary_base
buy_full_necessary_key
sell_full_necessary_base
sell_full_necessary_key

oversold_hint_necessary_base
oversold_hint_key
overbought_hint_necessary_base
overbought_hint_key
```

落入 condition_pool 时，建议统一为多行 condition_key：

```text
BUY:Y,Q,M,W,D 子集
SELL:Y,Q,M,W,D 子集
BUY:FULL
SELL:FULL
BUY_HINT
SELL_HINT
```

必要条件与 N2 canonical signal_type 的关系：

```text
BUY:*      -> BUY
SELL:*     -> SELL
BUY:FULL   -> BUY:FULL
SELL:FULL  -> SELL:FULL
BUY_HINT   -> BUY_HINT
SELL_HINT  -> SELL_HINT
```

质量要求：

```text
普通 BUY/SELL、FULL、Hint 必须分别可诊断、可计数、可追溯到 condition_basis。
不得把 BUY_HINT/SELL_HINT 混进普通 BUY/SELL 条件周期。
不得把 BUY:FULL/SELL:FULL 拆成普通 BUY:D/SELL:D。
```

### 3.3 条件层静态结构字段

目标价、主锚、参考周期、上涨卖出参考周期、下跌买入参考周期都属于条件层静态结构字段。

核心原则：

```text
只在条件层计算完整。
一旦生成当日 condition_basis / condition_pool，就不再由触发层、动作层、用户层重算。
后续层只能只读引用、复制、展示和审计。
```

上涨结构字段：

```text
main_up_anchor
up_reference_period
up_amplitude
up_base_price
buy_target_price
buy_expected_return_pct
up_sell_reference_period
up_trend_start_date
up_trend_end_date
up_reference_window_start
up_reference_window_end
```

下跌结构字段：

```text
main_down_anchor
down_reference_period
down_amplitude
down_base_price
sell_target_price
sell_expected_return_pct
down_buy_reference_period
down_trend_start_date
down_trend_end_date
down_reference_window_start
down_reference_window_end
```

计算公式：

```text
buy_target_price  = up_base_price + up_amplitude
sell_target_price = down_base_price - down_amplitude
```

参考周期映射：

```text
Y -> Q
Q -> M
M -> W
W -> D
```

上涨结构：

```text
从 Y/Q/M/W 中寻找连续“放量上涨”主锚。
main_up_anchor 取该连续上涨段的最低级别周期。
第二段连续“放量上涨”为 up_secondary_anchor。
up_reference_period 取 main_up_anchor 的下一低周期。
up_amplitude = A 段目标机调整上沿 - A 段目标机调整下沿。
amplitude_price_policy = OFFICIAL_HIGH_LOW。
当前 v3 N1 日线事实中，能复现目标机 golden 的有效边界为调整后实体边界：
max(open, close) / min(open, close)。不得把 raw intraday high/low 静默替换进目标价公式。
stock 日线必须先按 `row_adj_factor / current_adj_factor` 归一到 source_trade_date 的当前复权基准：
adjustment_policy = ROW_ADJ_FACTOR_TO_CURRENT_ADJ_FACTOR。
trace 必须记录 current_adj_factor；index/board 无 adj_factor 时按 active daily fact 已存边界计算。
A 段 = main_up_anchor 自身聚合周期当前正在延续的上涨段；不得把 unknown 首段自动并入，也不得用 parent period current window 替代。
找 up_reference_period 自身聚合周期最近已完成上涨段结束点。
up_base_price = 结束点下一交易日到 source_trade_date 的参考窗口最低收盘价。
buy_target_price = up_base_price + up_amplitude。
up_secondary_target_price 使用 up_secondary_anchor 重复同一套公式，不是主目标折扣。
```

下跌结构：

```text
从 Y/Q/M/W 中寻找连续“缩量下跌”主锚。
main_down_anchor 取该连续下跌段的最低级别周期。
第二段连续“缩量下跌”为 down_secondary_anchor。
down_reference_period 取 main_down_anchor 的下一低周期。
down_amplitude = A 段目标机调整上沿 - A 段目标机调整下沿。
amplitude_price_policy = OFFICIAL_HIGH_LOW。
stock 日线同样按 `row_adj_factor / current_adj_factor` 归一；下跌侧不得绕过复权归一后直接比较历史实体价。
A 段 = main_down_anchor 自身聚合周期当前正在延续的下跌段；不得把 unknown 首段自动并入，也不得用 parent period current window 替代。
找 down_reference_period 自身聚合周期最近已完成下跌段结束点。
down_base_price = 结束点下一交易日到 source_trade_date 的参考窗口最高收盘价。
sell_target_price = down_base_price - down_amplitude。
down_secondary_target_price 使用 down_secondary_anchor 重复同一套公式，不是主目标折扣。
```

000027 / source_trade_date=20260528 的 N2 golden regression：

```text
main_up_anchor = W
up_reference_period = D
A 段 = 20260506 -> 20260528
segment_low = 6.88
segment_high = 8.05
up_amplitude = 1.17
trend_break_date = 20260519
base_window = 20260520 -> 20260528
up_base_price = 7.25
buy_target_price = reference_target_price = 8.42
```

20260529 目标机对齐 golden regression：

```text
000543.SZ:
main_up_anchor = W
up_reference_period = D
A 段 = 20260506 -> 20260529
segment_low = 8.09
segment_high = 9.80
up_amplitude = 1.71
trend_break_date = 20260526
base_window = 20260527 -> 20260529
up_base_price = 9.11
buy_target_price = reference_target_price = 10.82

000027.SZ:
buy_target_price = reference_target_price = 8.45
```

上涨/下跌参考周期字段在 N2 定稿，且必须非空：

```text
up_sell_reference_period 从 main_up_anchor 的下一低周期开始，向更低周期寻找第一个风险态周期。
风险态 = 震荡 / 缩量下跌 / 放量下跌。
兜底：computed_up_sell_ref or up_reference_period or main_up_anchor or D。

down_buy_reference_period 从 main_down_anchor 的下一低周期开始，向更低周期寻找第一个机会态周期。
机会态 = 震荡 / 缩量上涨 / 放量上涨。
兜底：computed_down_buy_ref or down_reference_period or main_down_anchor or D。
```

兼容字段：

```text
clear_sell_ref_period = up_sell_reference_period
```

`clear_sell_ref_period` 只作为 N5 持仓/动作层迁移期兼容 alias；N2 canonical 字段是 `up_sell_reference_period`。

#### 3.3.1 五周期过渡分级排序码

N2 额外冻结两个只用于排序、筛选和展示优先级的辅助字段：

```text
level_up_score
level_down_score
```

它们都必须基于 `period_transition_y/q/m/w/d` 计算，不得使用 `period_grade_y/q/m/w/d`。空值、未知值或非法值按 `flat=震荡` 处理。

`level_up_score` 映射：

```text
low_volume_down = 0
volume_down     = 1
flat            = 2
low_volume_up   = 3
volume_up       = 4
```

`level_down_score` 为对称映射：

```text
volume_up       = 0
low_volume_up   = 1
flat            = 2
volume_down     = 3
low_volume_down = 4
```

两者公式相同：

```text
score = Y * 625 + Q * 125 + M * 25 + W * 5 + D
```

语义边界：

```text
level_up_score 越高，表示五周期过渡结构越偏上涨。
level_down_score 越高，表示五周期过渡结构越偏下跌。
它们不是 signal_type，不直接决定 BUY / SELL / FULL / HINT。
condition_basis 负责计算；condition_pool / minute_target_scope / condition_display_basis 只透传。
```

golden：

```text
000543 / 20260529: level_up_score=3124, level_down_score=0
000600 / 20260529: level_up_score=3124, level_down_score=0
300327 / 20260529: level_up_score=2999, level_down_score=125
```

#### 3.3.2 周期触发阈值冻结字段

N2-R4 起，条件层必须显式冻结 N4 真实触发所需的周期阈值：

```text
period_trigger_baseline_json
```

该字段不是用户展示字段，而是交易链路合同字段。N4 不得回查 N1 历史 K，也不得在盘中重算上一周期实体上沿/下沿；N4 只能读取 N2 冻结的 baseline 或 N4 本地化副本。

JSON 每个可计算周期 Y/Q/M/W/D 至少包含：

```text
current_open_seed
current_close_seed
current_amount_seed
current_trade_days_seed
previous_open
previous_close
previous_entity_high
previous_entity_low
previous_amount
previous_avg_amount
amount_metric
current_window_start
current_window_end
previous_window_start
previous_window_end
```

口径：

```text
D 周期 amount_metric = amount。
W/M/Q/Y 周期 amount_metric = avg_amount。
previous_entity_high = max(previous_open, previous_close)。
previous_entity_low = min(previous_open, previous_close)。
```

该字段必须贯通：

```text
condition_basis -> condition_pool -> minute_target_scope -> N4 trigger_context_snapshot
```

#### 3.3.3 ordinary 周期升级前置上下文

`period_trigger_baseline_json` 还承载版本化子对象：

```text
period_escalation_context
contract_version = N2-period-escalation-context-v1
generation_mode = N2-period-escalation-daily-incremental-v1
```

它只服务 N4 ordinary `BUY:*` / `SELL:*` 的 W/M/Q/Y 周期升级，不改变 D、`BUY:FULL` / `SELL:FULL` 或 HINT。

```text
W <- D：本周 D 已出现同方向 transition
M <- W：本月 W 已出现同方向 transition
Q <- M：本季 M 已出现同方向 transition
Y <- Q：本年 Q 已出现同方向 transition

buy  只认 volume_up
sell 只认 low_volume_down
```

窗口以 `for_trade_date` 定义，观察日期使用 `source_trade_date`；若服务日进入下一周/月/季/年，对应窗口在生成该日 context 前重置。每个方向和目标周期必须保存 `status`（`ready` / `not_seen` / `not_ready`）、`seen`、窗口 key、覆盖状态、缺失交易日、first/last source date、latest source run/basis ref、计数和稳定 hash。

N2 采用前一交易日增量状态与当日 D/W/M/Q transition 合并，不扫描或回算窗口内历史 condition rows。前态必须来自精确前一交易日 `passed_active` run，且 generation mode、日期链路、identity、窗口和 context/entry hash 全部有效；没有 generation mode 的旧 context 只能只读兼容，不得作为增量前态。

状态语义固定为：

```text
previous_seen OR today_match = true
-> status=ready, seen=true

没有正向证据且 coverage 完整
-> status=not_seen, seen=false

没有正向证据且 coverage 不完整
-> status=not_ready, seen=false
```

正向存在性证据不依赖完整负向覆盖：`ready + seen=true` 可以同时保留 `coverage_status=incomplete` 和缺失交易日用于审计。后续未命中日必须保留首次/最近命中日期及 latest source ref；负向结论只有覆盖完整时才允许成为 `not_seen`。N2 禁止从 N3/N4/N5 状态累积或反推，N4 只能消费该冻结 JSON 或本地化副本，不得回查 N1 或自行重算。


不允许事项：

```text
触发层不得根据盘中 snapshot 重算 main_up_anchor / main_down_anchor。
动作层不得根据分钟 K 重算 buy_target_price / sell_target_price。
用户层不得把展示字段反写 condition_basis / condition_pool。
如果 source_version 变化，必须生成新的 condition_run，而不是原地漂移。
```

## 4. 输入数据边界

条件层只能读取 v3 入库层已经定稿的数据。

### 4.1 通用输入

```text
common_trade_calendar
common_ingest_batch
common_source_version
```

### 4.2 个股输入

```text
stock_identity
stock_daily_bar_fact
stock_daily_basic
stock_financial_metrics_fact
stock_board_membership_fact 或 board_membership_fact 中的 stock 反查关系
```

### 4.3 指数输入

```text
index_identity
index_daily_bar_fact
index_membership_fact
```

### 4.4 板块输入

```text
board_identity
board_daily_bar_fact
board_membership_fact
```

### 4.5 监控对象输入

条件层需要一个 v3 自己的监控对象表，不能直接读取旧系统 `monitor_list`。

建议 N2 先设计 schema：

```text
stock_monitor_target
index_monitor_target
board_monitor_target
```

最低字段：

```text
trade_date
identity_key
code
name
monitor_type
lane
status
direction_scope
source
source_version
created_at
updated_at
raw_json
```

其中 lane 必须明确：

```text
stock_trade：仅个股真实交易观察线
stock_alert：个股提示观察线，不进入 sim/action
market_alert：指数/板块提示线，不进入 sim/action
```

## 5. 条件层字段保留原则

条件层只保留“资格判断、静态结构、后续只读引用、质量审计”所必需的字段。

必须保留的字段族：

```text
1. 日期与版本：source_trade_date / for_trade_date / prev_trade_date / source_version / source_batch_id / run_id。
2. 身份与隔离：identity_key / asset_kind / exchange / ts_code / display_code / code / name / lane / monitor_type。
3. 周期分级：Y/Q/M/W/D 的 grade、transition、prev_up_str、prev_dn_str。
4. 成交额基准：day、prev_day、week、prev_week、month、prev_month、quarter、prev_quarter、year、prev_year。
5. 静态结构：up/down anchor、reference_period、amplitude、base_price、buy_target_price、sell_target_price、clear_sell_ref_period。
6. 必要条件：普通 BUY/SELL、FULL、Hint 三类必要条件。
7. 财务评分：pe_core、total_mv、circ_mv、score、recommendation_level、financial_asof_date。
8. 上下文：主指数、首选板块、关联板块 identity 与必要展示名。
9. 输出范围：allowed_signal_types、is_hint_scope、daily_snapshot_required、minute_required、previous_day_minute_required、previous_day_minute_date、minute_scope_reason、market_data_consumer。
10. 质量审计：quality_status、quality_reason、missing_fields_json、raw_json、created_at、updated_at。
```

不得放入条件层的字段族：

```text
触发层字段：trigger_time / trigger_period / trigger_live / signal_time。
动作层字段：action_id / action_status / write_once / selected_write_count。
语音字段：voice_status / voice_level / tts_text / played_at。
模拟账户字段：sim_trade_id / filled_quantity / position_id / lot_id。
用户层解释字段：POS_CLEAR / BUY_FAIL_CLEAR / ADD_BUY_FAIL_REDUCE / user_policy_hint。
盘中锁定字段：locked_target_price / target_lock_status。
```

说明：

```text
buy_target_price / sell_target_price 在条件层定稿，后续层只读引用。
如果后续层需要根据触发时点生成执行价或展示文案，应写入触发/动作/用户层自己的表，不回写 condition_basis / condition_pool。
```

## 6. 物理分表要求

v3 已规定 stock / index / board 必须物理隔离。条件层继续遵守，不允许先混表再靠 asset_kind 过滤。

建议表族：

```text
common_condition_run
common_condition_quality_item
stock_condition_basis
index_condition_basis
board_condition_basis
stock_condition_pool
index_condition_pool
board_condition_pool
stock_minute_target_scope
index_minute_target_scope
board_minute_target_scope
stock_condition_display_basis
index_condition_display_basis
board_condition_display_basis
```

说明：

```text
condition_basis：冻结上一交易日条件基础。
condition_pool：今日条件资格池。
minute_target_scope：下一阶段一分钟 K 拉取范围，只写范围，不拉行情。
condition_display_basis：N6 展示输入，由 N2 从同一 run 的 basis/pool/scope 派生，不进入 N3/N4/N5。
```

## 7. 条件基础表设计

### 7.1 common_condition_run

用途：记录一次条件层计算。

建议字段：

```text
run_id
source_trade_date
for_trade_date
prev_trade_date
source_version
source_batch_id
mode
status
p0_count
p1_count
p2_count
started_at
finished_at
raw_json
```

### 7.2 stock_condition_basis

用途：个股条件基础快照。

建议字段：

```text
run_id
source_trade_date
for_trade_date
prev_trade_date
identity_key
asset_kind
exchange
ts_code
display_code
code
name
is_st
stock_status
official_daily_proof
lane
monitor_type
status

period_grade_y
period_grade_q
period_grade_m
period_grade_w
period_grade_d
period_transition_y
period_transition_q
period_transition_m
period_transition_w
period_transition_d
prev_up_str
prev_dn_str

amount_day
amount_prev_day
amount_week
amount_prev_week
amount_month
amount_prev_month
amount_quarter
amount_prev_quarter
amount_year
amount_prev_year
amount_source
amount_quality_status

period_trigger_baseline_json

main_up_anchor
up_reference_period
up_amplitude
up_base_price
buy_target_price
buy_expected_return_pct
up_sell_reference_period
up_trend_start_date
up_trend_end_date
up_reference_window_start
up_reference_window_end

main_down_anchor
down_reference_period
down_amplitude
down_base_price
sell_target_price
sell_expected_return_pct
down_buy_reference_period
down_trend_start_date
down_trend_end_date
down_reference_window_start
down_reference_window_end

clear_sell_ref_period
pe_core
total_mv
circ_mv
score
recommendation_level
recommendation_reason
financial_asof_date
financial_quality_status
financial_source_version
main_index_identity_key
main_index_code
main_index_name
main_index_expected_return_pct
preferred_board_identity_key
preferred_board_code
preferred_board_name
preferred_board_expected_return_pct
linked_board_identity_keys

buy_necessary_base
buy_necessary_key
buy_necessary_periods
sell_necessary_base
sell_necessary_key
sell_necessary_periods
buy_full_necessary_base
buy_full_necessary_key
sell_full_necessary_base
sell_full_necessary_key
oversold_hint_necessary_base
oversold_hint_key
overbought_hint_necessary_base
overbought_hint_key

source_version
source_batch_id
quality_status
quality_reason
missing_fields_json
raw_json
created_at
updated_at
```

### 7.3 index_condition_basis / board_condition_basis

指数和板块条件基础字段与个股类似，但不需要真实交易字段。

指数/板块也必须保留条件层静态结构字段：

```text
main_up_anchor / up_reference_period / up_amplitude / up_base_price / buy_target_price
main_down_anchor / down_reference_period / down_amplitude / down_base_price / sell_target_price
clear_sell_ref_period
```

这些字段用于提示、卡片和审计；指数/板块默认仍为 market_alert，不进入模拟账户。

必须包含：

```text
run_id
source_trade_date
for_trade_date
prev_trade_date
identity_key
asset_kind
exchange
ts_code
display_code
code
name
lane = market_alert
monitor_type
period_grade_y/q/m/w/d
period_transition_y/q/m/w/d
prev_up_str
prev_dn_str
amount_day / prev_day / week / prev_week / month / prev_month / quarter / prev_quarter / year / prev_year / amount_source / amount_quality_status
period_trigger_baseline_json
buy_necessary_base
buy_necessary_key
buy_necessary_periods
sell_necessary_base
sell_necessary_key
sell_necessary_periods
buy_full_necessary_base
buy_full_necessary_key
sell_full_necessary_base
sell_full_necessary_key
oversold_hint_necessary_base
oversold_hint_key
overbought_hint_necessary_base
overbought_hint_key
source_version
quality_status
quality_reason
missing_fields_json
raw_json
```

## 8. 条件池表设计

### 8.1 stock_condition_pool

用途：今日个股条件资格池。

建议字段：

```text
run_id
source_trade_date
for_trade_date
prev_trade_date
identity_key
asset_kind
exchange
ts_code
display_code
code
name
lane
direction
condition_key
condition_periods
allowed_signal_types
is_hint_scope
daily_snapshot_required
minute_required
previous_day_minute_required
previous_day_minute_date
previous_day_minute_quality_required
minute_scope_reason
market_data_consumer
monitor_type
policy_name
policy_hash
selected_reason
excluded_reason
period_trigger_baseline_json
main_up_anchor
up_reference_period
buy_target_price
buy_expected_return_pct
main_down_anchor
down_reference_period
sell_target_price
sell_expected_return_pct
clear_sell_ref_period
recommendation_level
recommendation_reason
main_index_identity_key
main_index_code
main_index_name
main_index_expected_return_pct
preferred_board_identity_key
preferred_board_code
preferred_board_name
preferred_board_expected_return_pct
linked_board_identity_keys
source_condition_basis_id
period_trigger_baseline_json
source_version
active_target
quality_status
quality_reason
missing_fields_json
raw_json
created_at
updated_at
```

### 8.2 index_condition_pool / board_condition_pool

用途：指数/板块 market_alert 条件池。

建议字段：

```text
run_id
source_trade_date
for_trade_date
prev_trade_date
identity_key
asset_kind
exchange
ts_code
display_code
code
name
lane = market_alert
direction
condition_key
condition_periods
allowed_signal_types
is_hint_scope
daily_snapshot_required
minute_required
previous_day_minute_required
previous_day_minute_date
previous_day_minute_quality_required
minute_scope_reason
market_data_consumer
monitor_type
policy_name
policy_hash
selected_reason
excluded_reason
source_condition_basis_id
source_version
active_target
quality_status
quality_reason
raw_json
created_at
updated_at
```

## 9. 条件规则

### 9.0 必要条件总览

条件层输出的 condition_key 必须覆盖三类必要条件：

```text
普通周期条件：BUY:周期 / SELL:周期
FULL 条件：BUY:FULL / SELL:FULL
Hint 条件：BUY_HINT / SELL_HINT
```

三类条件互相独立：

```text
BUY:FULL 不等于 BUY:D。
SELL:FULL 不等于 SELL:D。
BUY_HINT / SELL_HINT 不参与普通买卖周期集合。
```

### 9.1 周期集合

条件周期统一按：

```text
Y > Q > M > W > D
```

### 9.1.1 周期分级计算口径

N2-R 起，condition_basis 的 Y/Q/M/W/D 分级必须对齐目标机已验证口径：

```text
价格方向：
close_now > max(open_prev, close_prev) -> 上涨类
close_now < min(open_prev, close_prev) -> 下跌类
其余 -> 震荡

成交额比较：
D 周期使用当日 amount vs 上一交易日 amount。
Y/Q/M/W 非 D 周期使用当前周期 avg_amount vs 上一周期 avg_amount。
不得使用周期 sum(amount) 参与分级比较。
```

五类英文枚举：

```text
volume_up       = 放量上涨
low_volume_up   = 缩量上涨 / 非放量上涨
volume_down     = 放量下跌
low_volume_down = 缩量下跌
flat            = 震荡
unknown         = 缺数据 / 不可计算
```

transition 口径：

```text
period_transition_* 不得简单等于 period_grade_*。
Y/Q/M/W 使用目标机 transition window：Y=66, Q=22, M=5, W=1。
若当前 grade 已是 volume_up 或 low_volume_down，则 transition 直接取当前 grade。
若仍在过渡窗口内：
  previous seed = volume_up 且 current grade 为 low_volume_up/flat -> transition=volume_up
  previous seed = low_volume_down 且 current grade 为 volume_down/flat -> transition=low_volume_down
D 周期不做过渡平滑，transition=grade。
```

UP/DN 串必须基于 `period_transition_*` 生成，而不是基于 `period_grade_*`：

```text
prev_up_str：固定 5 位位置串，Y/Q/M/W/D 中 transition=volume_up 的位置写大写周期，否则写 '-'
示例：YQM--

prev_dn_str：固定 5 位位置串，Y/Q/M/W/D 中 transition=low_volume_down 的位置写小写周期，否则写 '-'
示例：---w-
```

### 9.2 普通买入必要条件

普通买入条件不是触发。买入条件表示：该对象今天允许被后续触发层观察买入。

规则：

```text
BUY 条件周期 = Y/Q/M/W/D 中所有“非放量上涨”的周期。
```

计算输入必须使用 `period_transition_y/q/m/w/d`，不得直接使用当前 `period_grade_*`。

也就是说：

```text
缩量上涨：允许买入条件
放量下跌：允许买入条件
缩量下跌：允许买入条件
震荡：允许买入条件
放量上涨：不生成普通买入条件
缺分级：不生成该周期条件
```

### 9.3 普通卖出必要条件

普通卖出条件不是触发。卖出条件表示：该对象今天允许被后续触发层观察卖出。

规则：

```text
SELL 条件周期 = Y/Q/M/W/D 中所有“非缩量下跌”的周期。
```

计算输入必须使用 `period_transition_y/q/m/w/d`，不得直接使用当前 `period_grade_*`。

也就是说：

```text
放量上涨：允许卖出条件
缩量上涨：允许卖出条件
放量下跌：允许卖出条件
震荡：允许卖出条件
缩量下跌：不生成普通卖出条件
缺分级：不生成该周期条件
```

### 9.4 BUY:FULL 必要条件

BUY:FULL 是买入必要条件，不是动作，也不是 BUY:D。

成立前提：

```text
昨日 UP 串 = YQMWD
不再要求开盘类型
```

后续触发层才判断：

```text
当日 D = 放量上涨
D 买入金额条件通过
```

触发周期固定：

```text
D
```

### 9.5 SELL:FULL 必要条件

SELL:FULL 是卖出必要条件，不是动作，也不是 SELL:D。

成立前提：

```text
昨日 DN 串 = yqmwd
不再要求开盘类型
```

后续触发层才判断：

```text
当日 D = 缩量下跌
D 卖出金额条件通过
```

触发周期固定：

```text
D
```

### 9.6 超跌 / 超涨正式信号必要条件

v3 中 `BUY_HINT / SELL_HINT` 名称保留 Hint，但语义是统一标准买卖触发信号类型，不是触发层、动作层或用户层的内部例外类型。

```text
BUY_HINT：超跌必要条件成立后，30 分钟放量上涨确认的正式买入触发信号类型。
SELL_HINT：超涨必要条件成立后，30 分钟缩量下跌确认的正式卖出触发信号类型。
```

`BUY_HINT / SELL_HINT` 可以用于指数、行业/板块、个股观察线，覆盖 `stock_trade` / `stock_alert` / `market_alert`。其中 `BUY_HINT` 按买入方向处理，`SELL_HINT` 按卖出方向处理。

条件层不得因为对象是个股而过滤 `BUY_HINT / SELL_HINT`。是否进入模拟账户、是否改变持仓、是否参与用户层解释，不在条件层决定，由后续动作层 / 用户层按 lane、标准信号类型和持仓策略处理。

条件层只声明 `BUY_HINT / SELL_HINT` 资格；N4 在消费 N3 标准行情事实、闭合分钟事件或 N3 30 分钟确认摘要后，分别按 `30分钟放量上涨 / 30分钟缩量下跌` 生成正式 `TriggerMatched`。

超跌 / 超涨必要条件不得用 `any(UP/DOWN)` 简化：

```text
BUY_HINT：
上一交易日 UP 串存在最小上涨趋势周期。
该最小上涨趋势周期以下的小周期，period_transition 全部为 volume_down 或 low_volume_down。

SELL_HINT：
上一交易日 DN 串存在最小下跌趋势周期。
该最小下跌趋势周期以下的小周期，period_transition 全部为 volume_up 或 low_volume_up。
```

## 10. lane 和方向准入

### 10.1 stock_trade

允许：

```text
stock_buy_monitor -> buy
stock_sell_monitor/open_position -> sell
BUY_HINT -> buy
SELL_HINT -> sell
```

禁止：

```text
88xxxx 板块代码进入 stock_trade
index 进入 stock_trade
board 进入 stock_trade
market_alert 进入 sim/action
```

### 10.2 market_alert

允许：

```text
index_monitor -> buy/sell，包括 BUY_HINT / SELL_HINT
board_monitor -> buy/sell，包括 BUY_HINT / SELL_HINT
```

只能提示，不进入 sim/action。

### 10.3 stock_alert

stock_alert 是观察线，只有明确配置时才允许。

禁止默认把不合格 stock_trade 对象自动塞进 stock_alert，除非用户或规则明确选择。

stock_alert 也可以观察 `BUY_HINT / SELL_HINT`，但它们仍按 `direction=buy/sell` 进入条件池，不使用独立 `hint` 方向。

## 11. 条件层与用户层查询边界

条件层是 v3 中唯一允许用户层在交易时段主动查询的决策前置层。

允许用户层只读查询：

```text
condition_basis 摘要
condition_pool 摘要
coverage / quality / missing reason
目标价、清仓参考周期、推荐、指数/板块上下文
```

禁止用户层：

```text
修改 condition_basis / condition_pool。
查询触发层 trigger_event / trigger_state 裸表。
查询动作层 action_event 裸表。
根据条件层数据自行生成动作或语音。
```

触发层和动作层与用户层隔离：

```text
触发层只向动作层提供内部触发事件。
动作层只向用户层单向投递标准 ActionEvent / HintEvent / RiskEvent / PositionEvent。
用户层只能被动接收动作事件，再生成 mobile / voice / sim / replay projection。
```

质量闸门：

```text
P0: 用户层直接读取 trigger/action 裸表。
P0: 用户层回写条件层字段。
P0: 用户层根据条件层数据自行生成动作、语音或模拟成交。
```

## 12. 条件层输出给下一阶段

条件层可以生成行情订阅范围，但不能拉行情。

建议输出：

```text
stock_minute_target_scope
index_minute_target_scope
board_minute_target_scope
```

更准确地说，`minute_target_scope` 是历史沿用名称，v3 中语义为“行情范围层”：

```text
1. 给实时行情层声明需要实时日 K / 快照的对象。
2. 给实时行情层声明动作层可能需要今日一分钟 K 的对象。
3. 给实时行情层声明盘前需要预加载前一交易日一分钟 K 的对象。
4. 不代表触发层可以外拉或扫描非标准分钟 K；四类 30 分钟确认信号只能消费 N3 标准闭合分钟事件或 N3 30 分钟确认摘要。
5. 它是条件来源明细表，不等于最终行情拉取任务表。
```

字段：

```text
source_trade_date
for_trade_date
identity_key
asset_kind
exchange
ts_code
display_code
code
name
lane
direction
condition_key
condition_periods
allowed_signal_types
daily_snapshot_required
minute_required
previous_day_minute_required
previous_day_minute_date
previous_day_minute_quality_required
market_data_consumer
source_condition_pool_id
total_mv（仅 stock_minute_target_scope）
market_value_threshold（仅 stock_minute_target_scope）
reason
created_at
```

condition_basis / condition_pool / minute_target_scope 默认关系：

```text
condition_basis：
保留 stock / index / board 全量条件基础，不在 basis 阶段按行情范围收窄。

index_condition_pool：
从 index_condition_basis 中筛选固定 9 个指数的合格条件：
000905、399303、000001、000852、399001、399006、000300、000016、000688。
默认 universe 必须使用 exchange-qualified identity，不得只用裸 code：

```text
index:SH:000905
index:SZ:399303
index:SH:000001
index:SH:000852
index:SZ:399001
index:SZ:399006
index:SH:000300
index:SH:000016
index:SH:000688
```

任一固定指数缺少 condition_basis 来源，必须记为 P0；不得在 condition_pool / minute_target_scope 阶段静默忽略。
任一固定指数虽然有当日 basis 但缺少上一日/上一周/月/季/年金额基准，导致 `amount_quality_status != passed`，也必须记为 P0；不得生成看似完整但 transition 全 unknown 的指数条件层结果。

board_condition_pool：
从 board_condition_basis 中筛选所有 `board_type=tdx_industry` 的行业板块合格条件。板块类别以 N1 `board_identity/board_daily_bar_fact` 中的 `board_type` 为主口径：`tdx_industry` 为行业，`tdx_concept` 为概念，`tdx_region` 为地区；不得用 board_code 前缀推断概念/地区。

stock_condition_pool：
从 stock_condition_basis 中筛选已经具备条件池资格的个股。
条件资格包括普通 BUY/SELL、BUY:FULL/SELL:FULL、BUY_HINT/SELL_HINT。
默认策略下必须满足总市值 total_mv >= 100 亿、非 ST/风险票、official daily 证明存在、
财务快照基础字段可用、lane/monitor_type 合规。

minute_target_scope：
只从对应 stock/index/board condition_pool 或等价 dry-run 结果生成。
不得绕过 condition_pool 把 index / board / stock 对象直接写入 minute_target_scope。
允许保留 asset_kind + identity_key + direction + condition_key 粒度，用于审计和追溯。
```

说明：

```text
total_mv 沿用入库层 stock_daily_basic.total_mv 口径，单位为万元。
100 亿 = 1,000,000 万元。
默认策略下，个股缺少 total_mv、total_mv < 1,000,000 万元、ST/风险票、缺 official daily 证明、
缺财务快照基础字段、lane/monitor_type 不合规时，不得进入 stock_condition_pool，也就不得进入 stock_minute_target_scope。
固定 9 个指数、`board_type=tdx_industry` 行业板块、个股 total_mv >= 100 亿是 condition_pool 默认筛选策略，不是 scope 直写策略。
condition_pool 必须可解释：入池行保留 policy_name、policy_hash、selected_reason、source_condition_basis_id；
被剔除候选在 dry-run/report/quality 中保留 excluded_reason 分布和样本。
```

因此 scope 来源统一要求：

```text
scope_source=condition_pool：来自条件池，必须追溯 source_condition_pool_id。
source_condition_pool_id：正式 execute 时必须指向同一 run 的对应 stock/index/board condition_pool 行。
dry-run 阶段可用 source_condition_pool_ref 表示等价追溯。
```

消费口径统一要求：

```text
condition_pool / minute_target_scope：条件来源口径，粒度为 object + direction + condition_key。
market_data_subscription：行情拉取口径，粒度为 asset_kind + identity_key + required_data_kind + for_trade_date。
实时行情层消费 minute_target_scope 时必须先去重生成 market_data_subscription，不得按 scope 明细行重复拉行情。
```

### 12.1 condition_pool policy、scope candidate 与 selection policy

N2-D1 起保留 policy 接口。默认策略先作用在 `condition_pool`，未来界面可编辑 `condition_pool_selection_policy`；`scope_selection_policy` 只负责在 pool 结果上继续收窄行情范围。

N2 网页筛选控制台的页面、接口、执行流程和硬边界，见：

```text
docs/N2_WEB_POLICY_FILTER_DESIGN.md
```

推荐流程：

```text
condition_basis
-> condition_pool_candidate
-> condition_pool_selection_policy
-> condition_pool
-> minute_scope_candidate
-> scope_selection_policy
-> minute_target_scope
```

其中：

```text
condition_pool_candidate：
从 condition_basis 生成所有具备普通 BUY/SELL、BUY:FULL/SELL:FULL、BUY_HINT/SELL_HINT 必要条件的候选。

condition_pool_selection_policy：
按 index / board / stock 分段筛选 condition_pool。
默认策略：
- index 只保留固定 9 个指数的合格条件。
- board 默认只保留 `board_type=tdx_industry` 行业板块的合格条件；概念/地区需通过 policy 显式加入 `tdx_concept` / `tdx_region`。
- stock 只保留 total_mv >= 1,000,000 万元、非 ST/风险票、official daily 证明存在、
  财务快照基础字段可用、lane/monitor_type 合规且具备条件资格的个股。
未来界面编辑的是这一层策略，不直接修改 condition_basis。

condition_pool：
保存 policy 命中的条件资格池。

minute_scope_candidate：
生成可进入行情范围的候选。
index 候选必须来自 index_condition_pool 或等价 dry-run 结果。
board 候选必须来自 board_condition_pool 或等价 dry-run 结果。
stock 候选必须来自 stock_condition_pool 或等价 dry-run 结果。

scope_selection_policy：
对 index / board / stock 的 pool 候选继续筛选。
N2-D1 先支持 JSON policy + CLI dry-run；后续界面可保存 policy。
未来前端只操作 policy，不直接操作 condition_pool / minute_target_scope 行。

minute_target_scope：
只保存 policy 命中的最终行情范围。
```

默认 condition_pool policy 必须等价于当前自动规则：

```text
index_policy：
enabled=true
source=condition_pool_candidate
include_codes=000905,399303,000001,000852,399001,399006,000300,000016,000688
directions=buy,sell

board_policy：
enabled=true
source=condition_pool_candidate
board_types=tdx_industry
directions=buy,sell

stock_policy：
enabled=true
source=condition_pool_candidate
directions=buy,sell
include_condition_families=ordinary,full,hint
min_total_mv_wan=1000000
market_value_compare=>=
exclude_st_or_risk_name=true
allowed_stock_statuses=active
require_official_daily_proof=true
require_financial_snapshot=true
require_financial_key_field=true
blocked_financial_quality_statuses=failed
allowed_lanes=stock_alert,stock_trade
allowed_monitor_types=source_universe_preview
```

policy JSON 推荐结构：

```json
{
  "policy_name": "manual_20260525",
  "index": {
    "enabled": true,
    "source": "condition_pool_candidate",
    "include_codes": ["000905", "399303", "000001", "000852", "399001", "399006", "000300", "000016", "000688"],
    "directions": ["buy", "sell"]
  },
  "board": {
    "enabled": true,
    "source": "condition_pool_candidate",
    "board_types": ["tdx_industry"],
    "directions": ["buy", "sell"]
  },
  "stock": {
    "enabled": true,
    "source": "condition_pool_candidate",
    "directions": ["buy", "sell"],
    "include_condition_families": ["ordinary", "full", "hint"],
    "include_condition_keys": [],
    "min_total_mv_wan": 1000000,
    "market_value_compare": ">=",
    "exclude_st_or_risk_name": true,
    "allowed_stock_statuses": ["active"],
    "require_official_daily_proof": true,
    "require_financial_snapshot": true,
    "require_financial_key_field": true,
    "blocked_financial_quality_statuses": ["failed"],
    "allowed_lanes": ["stock_alert", "stock_trade"],
    "allowed_monitor_types": ["source_universe_preview"],
    "require_buy_target_price": false,
    "require_sell_target_price": false,
    "require_clear_sell_ref_period": false,
    "limit": null
  }
}
```

可扩展筛选字段：

```text
index_policy：
include_codes / exclude_codes
directions
include_condition_keys
period_grade_y/q/m/w/d
period_transition_y/q/m/w/d
require_buy_target_price / require_sell_target_price
main_up_anchor / main_down_anchor

board_policy：
include_board_codes / exclude_board_codes
board_types（tdx_industry / tdx_concept / tdx_region）
directions
include_condition_keys
period_grade_y/q/m/w/d
period_transition_y/q/m/w/d
require_buy_target_price / require_sell_target_price
main_up_anchor / main_down_anchor
amount_day / amount_week / amount_month

stock_policy：
include_codes / exclude_codes
directions
include_condition_families
include_condition_keys
lane
monitor_type
min_total_mv_wan / max_total_mv_wan
is_st / stock_status / official_daily_proof / financial_quality_status / financial_asof_date
period_grade_y/q/m/w/d
period_transition_y/q/m/w/d
require_buy_target_price / require_sell_target_price
require_clear_sell_ref_period
recommendation_level / score / pe_core
main_index_code / preferred_board_code
limit
```

硬边界：

```text
condition_pool_selection_policy 只能从 condition_basis 候选中筛选，不得修改 condition_basis。
scope_selection_policy 只能收窄 condition_pool 候选范围，不得绕过 condition_pool 把对象塞进 minute_target_scope。
未来前端只操作 policy，不直接操作 condition_pool / minute_target_scope 行。
policy 不得引入 v3 标准信号白名单外 signal_type。
policy 不得直接修改 condition_basis；正式 condition_pool / minute_target_scope 必须由同一 run 生成。
policy dry-run 必须输出 candidate_count、selected_count、excluded_count、excluded_reason_counts、selected_reason_counts、样本和 policy_hash。
policy dry-run 不写库、不拉行情、不进入触发/动作/用户层。
如未来需要手动强制加入不在 condition_pool 的个股，必须走单独 manual_override，并带 operator/reason/expires_at/quality_level；N2-D1 不实现 manual_override。
```

### 12.2 scope policy 诊断报告

N2-D2 在 N2-D1 的 policy dry-run 基础上增强诊断报告，方便没有界面时通过 JSON 文件手动筛选。

报告必须按 index / board / stock 分段输出：

```text
candidate_count
selected_count
excluded_count
excluded_reason_counts
selected_samples
excluded_samples
distribution
```

其中 stock distribution 至少包含：

```text
condition_key_counts
direction_counts
total_mv_bucket_counts
preferred_board_code_counts
recommendation_level_counts
lane_counts
```

policy 校验要求：

```text
stock.min_total_mv_wan 不得低于 1,000,000 万元。
stock.include_condition_keys 和 include_condition_families 同时存在时，以 include_condition_keys 为准，并在 policy_warnings 中提示。
policy 报告必须说明 selected/excluded 的样本原因，方便后续界面复用同一套解释。
```

### 12.3 execute 前置计划

N2-D3 只增加 `plan-execute` 前置计划，不真正 execute。

目的：

```text
1. 提前确认将来 execute 会写哪些条件层表。
2. 提前确认每张表的 planned row count。
3. 提前确认 common_condition_run / common_condition_quality_item 的写入顺序。
4. 提前确认按 run_id 回滚的删除顺序。
5. 提前暴露 P0/P1/P2 对 execute 的影响。
```

CLI：

```text
scripts/export_minute_target_scope.py --source-trade-date YYYYMMDD --policy configs/minute_scope/manual_YYYYMMDD.json --plan-execute --dry-run
```

输出必须包含：

```text
plan_mode=plan_execute
writes_performed=false
will_connect_database=false
will_execute_sql=false
policy_hash
write_order
would_write row counts
execute_guards
rollback_plan
```

计划写入顺序：

```text
1. common_condition_run
2. common_condition_quality_item
3. index_minute_target_scope
4. board_minute_target_scope
5. stock_minute_target_scope
```

回滚顺序必须反向按 `run_id` 删除：

```text
1. stock_minute_target_scope WHERE run_id = :run_id
2. board_minute_target_scope WHERE run_id = :run_id
3. index_minute_target_scope WHERE run_id = :run_id
4. common_condition_quality_item WHERE run_id = :run_id
5. common_condition_run WHERE run_id = :run_id
```

execute 守门：

```text
P0 > 0：阻断 execute。
source_ready_passed=false：阻断 execute。
P1 > 0：不阻断 dry-run，但 execute 必须用户确认。
for_trade_calendar_row_missing：保持 P1，不在条件层硬造交易日。
N2-D3 自身不执行 SQL，execute_supported=false。
```

硬边界：

```text
plan-execute 只能读取 dry-run 报告并生成写入计划。
不得连接数据库执行写入。
不得写 condition_pool / minute_target_scope 正式表。
不得拉实时行情或一分钟 K。
不得进入触发/动作/语音/mobile/sim/worker。
```

### 12.4 条件层整体 execute readiness plan

N2-E0 只生成条件层整体 execute readiness plan，不真正 execute。

背景：

```text
单独执行 minute_target_scope 会依赖真实 source_condition_pool_id。
因此不能跳过 condition_basis / condition_pool 直接写 scope。
整体 readiness plan 必须把 basis -> pool -> scope 三段按同一个 planned_run_id 串起来。
```

目标：

```text
1. 汇总 condition_basis / condition_pool / minute_target_scope 三段 dry-run。
2. 输出三段 planned row count。
3. 输出统一 planned_run_id 和 policy_hash。
4. 明确 source_condition_basis_id / source_condition_pool_id 的同批次生成依赖。
5. 输出全链路 P0/P1/P2 守门。
6. 输出全链路写入顺序和按 run_id 回滚顺序。
7. 判断是否可以进入“用户确认 execute”讨论。
```

CLI：

```text
scripts/plan_condition_layer_execute.py --source-trade-date YYYYMMDD --policy configs/minute_scope/manual_YYYYMMDD.json --dry-run
```

计划写入顺序：

```text
1. common_condition_run
2. common_condition_quality_item
3. stock_condition_basis
4. index_condition_basis
5. board_condition_basis
6. stock_condition_pool
7. index_condition_pool
8. board_condition_pool
9. index_minute_target_scope
10. board_minute_target_scope
11. stock_minute_target_scope
```

ID 依赖：

```text
condition_pool.source_condition_basis_id 来自同 run 的 condition_basis 写入结果。
stock/index/board minute_target_scope.source_condition_pool_id 来自同 run 的对应 condition_pool 写入结果。
未来真正 execute 时必须使用 RETURNING 或等价映射，不能用 dry-run ref 伪造真实 id。
```

execute readiness 守门：

```text
P0 > 0：阻断 execute。
source_ready_passed=false：阻断 execute。
source_trade_date / for_trade_date / prev_trade_date 三段不一致：阻断 execute。
P1 > 0：不阻断 dry-run，但 execute 必须用户确认或先修复。
for_trade_calendar_row_missing：保持 P1，不在条件层硬造交易日。
N2-E0 自身不执行 SQL，execute_ready=false，writes_performed=false。
```

输出必须包含：

```text
planned_run_id
source_trade_date / for_trade_date / prev_trade_date
policy_name / policy_hash
stage_counts
would_write
dependency_plan
execute_guards
blocked_reasons
not_ready_reasons
rollback_plan
```

硬边界：

```text
N2-E0 可以只读调用入库层 ready check 和条件层 dry-run。
N2-E0 不写 common_condition_run。
N2-E0 不写 condition_basis / condition_pool / minute_target_scope。
N2-E0 不执行 migration。
N2-E0 不拉行情、不拉一分钟 K。
N2-E0 不进入触发/动作/语音/mobile/sim/worker。
```

### 12.5 execute contract 与 rollback contract

N2-E1 只设计 execute 前合同和回滚合同，不真正 execute。

背景：

```text
N2-E0 已能判断整条条件层链路是否具备 execute 前提。
N2-E1 不负责写库，而是把真正 execute 前必须确认的合同固定下来。
```

execute contract 必须包含：

```text
source_trade_date
for_trade_date
prev_trade_date
source_versions
policy_name
policy_hash
planned row_count
pre_execute_expected_hash
P0/P1/P2 policy
user_confirmation_required
overwrite policy
active run switch policy
rollback contract
post_execute verification contract
forbidden write domains
```

run_id 规则：

```text
readiness plan 可以使用稳定 planned_run_id 方便对账。
真正 execute 每次都必须生成新的 execute_run_id。
推荐模板：
condition_layer_{source_trade_date}_to_{for_trade_date}_{yyyymmddHHMMSS}_execute
同一次 transaction 内 basis / pool / scope 共享同一个 execute_run_id。
不得复用已经存在的 run_id。
```

source_version 绑定：

```text
execute contract 必须冻结 source_versions。
写入 common_condition_run.source_versions 后，basis / pool / scope 均引用同一个 run_id。
如果 execute 前 active source_version 发生变化，必须重新跑 N2-E0/N2-E1。
```

重复 execute 策略：

```text
默认 reject_if_active_exists：
同 source_trade_date + for_trade_date 已存在 active run 时拒绝 execute。
active run 判定优先 status=passed_active；legacy status=passed 仅作为兼容读。

显式 overwrite：
必须同时满足 --overwrite 和 user_confirmation=true。
overwrite 不复用旧 run_id，而是生成新 execute_run_id。
overwrite 表示 lineage supersede，不表示删除或覆盖旧 run 行。
overwrite 成功后，previous active run 标记为 status=superseded，新 run 标记为 status=passed_active。
previous active run_id 必须写入新 run 的 raw_json，供 rollback 恢复。
如果 common_condition_run.status CHECK 尚未支持 passed_active，execute preflight 必须 P0 阻断，不得写入 running/new run。
```

P0/P1/P2 策略：

```text
P0 > 0：禁止 execute。
P1 > 0：允许进入确认环节，但 user_confirmation 必须为 true。
P2 > 0：仅记录，不阻断。
for_trade_calendar_row_missing 属于 P1；条件层不得硬造交易日。
```

active 指针切换：

```text
canonical active run 由 common_condition_run.status='passed_active' 表示。
legacy common_condition_run.status='passed' 仅保留为兼容读取口径，不立即批量迁移。
active selection 优先 passed_active，其次 legacy passed。
同一 source_trade_date + for_trade_date 只能有一个 canonical passed_active run，schema 通过 partial unique index 约束。
overwrite 时旧 active run 先记录为 previous_active_run_id，再在新 run 验收通过后标记 superseded。
如果新 run 验收失败，新 run 标记 failed，旧 active run 保持原 active 状态。
rollback 新 run 后，可将 previous active run 恢复为 status=passed_active。
```

写入策略：

```text
1. 插入 common_condition_run(status=running)。
2. 写入 common_condition_quality_item。
3. 写入 stock/index/board monitor_target 执行快照，用 source_version=execute_run_id 作为回滚锚点。
4. 写入 stock/index/board condition_basis，并用 RETURNING 建立 source_monitor_target_id 映射。
5. 写入 stock/index/board condition_pool，并用 RETURNING 建立 source_condition_basis_id 映射。
6. 写入 index/board/stock minute_target_scope，并用 RETURNING 或等价映射填充 stock/index/board source_condition_pool_id。
7. 执行 post_execute verification。
8. overwrite=true 时，在同一事务中将 previous active run 标记 superseded。
9. 验收通过后将新 run 标记 passed_active。
```

回滚策略：

```text
rollback 必须按 run_id 处理。
默认回滚顺序：
1. stock_minute_target_scope WHERE run_id = :run_id
2. board_minute_target_scope WHERE run_id = :run_id
3. index_minute_target_scope WHERE run_id = :run_id
4. board_condition_pool WHERE run_id = :run_id
5. index_condition_pool WHERE run_id = :run_id
6. stock_condition_pool WHERE run_id = :run_id
7. board_condition_basis WHERE run_id = :run_id
8. index_condition_basis WHERE run_id = :run_id
9. stock_condition_basis WHERE run_id = :run_id
10. board_monitor_target WHERE source_version = :run_id
11. index_monitor_target WHERE source_version = :run_id
12. stock_monitor_target WHERE source_version = :run_id
13. common_condition_quality_item WHERE run_id = :run_id
14. common_condition_run WHERE run_id = :run_id
```

如果 overwrite 曾经切换 active run：

```text
1. 删除/回滚新 run 的 basis/pool/scope/quality/run。
2. 将 previous_active_run_id 从 superseded 恢复为 passed。
3. 写 rollback report，记录 operator、reason、started_at、finished_at、row_count/hash。
```

验证策略：

```text
execute 前：
- N2-E0 readiness plan hash
- expected row_count
- expected source_versions
- policy_hash
- P0=0
- user_confirmation=true
- active run conflict check

execute 后：
- common_condition_run row_count=1
- common_condition_quality_item row_count 与计划一致
- stock/index/board monitor_target row_count 与计划一致
- stock/index/board condition_basis row_count 与计划一致
- stock/index/board condition_pool row_count 与计划一致
- stock/index/board minute_target_scope row_count 与计划一致
- source_versions 未漂移
- policy_hash 未漂移
- forbidden field scan 通过
- stock/index/board 物理隔离检查通过
- trigger/action/mobile/voice/sim 表无写入
```

硬边界：

```text
N2-E1 只输出合同和 SQL 模板。
N2-E1 不连接写库事务。
N2-E1 不执行 migration。
N2-E1 不写 condition_basis / condition_pool / minute_target_scope。
N2-E1 不拉行情、不拉一分钟 K。
N2-E1 不进入触发/动作/语音/mobile/sim/worker。
```

### 12.6 execute preflight

N2-E2 是真正 execute 前的最后只读预演，不真正 execute。

目标：

```text
1. 重新跑 condition_basis / condition_pool / minute_target_scope dry-run。
2. 重新生成 N2-E0 readiness plan。
3. 重新生成 N2-E1 execute contract。
4. 只读检查开发库是否已经 migration 出条件层表。
5. 只读检查同 source_trade_date + for_trade_date 是否已有 active condition run。
6. 输出 rollback SQL preview。
7. 输出是否允许进入 N2-E3 execute 讨论。
```

CLI：

```text
scripts/plan_condition_execute_preflight.py --source-trade-date YYYYMMDD --policy configs/minute_scope/manual_YYYYMMDD.json --dry-run
```

schema readiness 必须检查：

```text
common_condition_run
common_condition_quality_item
stock_monitor_target
index_monitor_target
board_monitor_target
stock_condition_basis
index_condition_basis
board_condition_basis
stock_condition_pool
index_condition_pool
board_condition_pool
stock_minute_target_scope
index_minute_target_scope
board_minute_target_scope
```

说明：

```text
monitor_target 表不是 N2-E3 的默认写入对象，但当前 condition_basis schema 有 source_monitor_target_id 外键，所以 preflight 必须确认这些表已经 migration。
如果 schema 未 migration，只输出 migration readiness，不自动执行 migration。
```

active run 检查：

```text
默认策略：
同 source_trade_date + for_trade_date 已存在 status=passed 的 common_condition_run 时，blocked。

overwrite dry-run：
只有显式 --overwrite 且 user_confirmation=true 时，允许进入 overwrite 合同讨论。
N2-E2 仍然不执行 overwrite，不修改旧 active run。
```

preflight report 必须包含：

```text
source_trade_date
for_trade_date
prev_trade_date
run_id_preview
expected row counts
P0/P1/P2
schema_status
active_run_status
source_version_status
rollback_sql_preview
execute_allowed
user_confirmation_required
blocked_reasons
```

execute_allowed 语义：

```text
execute_allowed=true 只表示“可以向用户申请进入 N2-E3 execute”。
execute_allowed=false 时不得进入 N2-E3。
无论 true/false，N2-E2 自身始终 will_execute_sql=false。
```

硬边界：

```text
N2-E2 可使用 read-only 数据库连接检查 schema 和 active run。
N2-E2 不执行 migration。
N2-E2 不写 condition_basis / condition_pool / minute_target_scope。
N2-E2 不拉行情、不拉一分钟 K。
N2-E2 不进入触发/动作/语音/mobile/sim/worker。
N2-E2 不触碰旧系统。
```

### 12.7 condition schema migration readiness

N2-E2A 用于解释 N2-E2 的 `schema_not_migrated` 阻塞原因，并确认 `sql/002_condition_layer_schema.sql` 是否已经具备进入人工 migration 审核的条件。

N2-E2A 仍然不是 migration：

```text
不执行 SQL。
不创建表。
不写 condition_basis / condition_pool / minute_target_scope。
不切换 active run。
不拉行情。
不进入触发/动作/语音/mobile/sim/worker。
```

CLI：

```text
scripts/plan_condition_schema_migration.py --schema sql/002_condition_layer_schema.sql --check-database
```

静态检查必须覆盖：

```text
1. 条件层 required tables 是否完整。
2. stock/index/board monitor_target、condition_basis、condition_pool、minute_target_scope 是否物理分表。
3. required columns 是否存在。
4. 是否出现未分表 condition_basis / condition_pool / minute_target_scope。
5. 是否出现下游运行对象 SQL。
6. 是否声明入库层 FK 依赖：common_ingest_batch、stock_identity、index_identity、board_identity。
7. allowed_signal_types 是否只包含 6 类 v3 标准信号候选。
8. previous_day_minute_date 是否受 prev_trade_date 约束。
9. stock_minute_target_scope 是否保留 total_mv >= market_value_threshold 约束。
10. source_trade_date 是否等于 prev_trade_date。
11. SQL 是否被单一 BEGIN / COMMIT 包裹。
```

只读数据库检查必须覆盖：

```text
1. 条件层 14 张 required tables 当前是否已存在。
2. FK 依赖表是否已存在。
3. common_active_source_version、common_condition_active_source_version_view、common_trade_calendar 等运行依赖对象是否存在。
4. 条件层表全缺失且 FK 依赖存在时，标记 ready_for_first_apply=true。
5. 条件层表部分存在或 FK 依赖缺失时，标记 manual_review_required=true。
```

N2-E2A 输出：

```text
schema_hash
table_count
index_count
static_ready
database_status
condition_tables_existing
condition_tables_missing
fk_dependency_missing
runtime_dependency_missing
ready_for_first_apply
manual_review_required
ready_for_user_migration_review
will_execute_sql=false
migration_performed=false
writes_performed=false
```

解释：

```text
ready_for_user_migration_review=true 只表示“可以把 migration 交给用户确认/开发库 migration 阶段讨论”。
它不表示 N2-E3 execute 已允许。
真实 migration 必须另开阶段，且必须由用户明确确认。
```

前一日一分钟 K 预加载规则：

```text
previous_day_minute_required=true：表示该对象在动作层可能需要前一交易日一分钟 K。
previous_day_minute_date=prev_trade_date：固定为 for_trade_date 的上一交易日。
previous_day_minute_quality_required=true：盘前必须验收 loaded_count / expected_count。
```

职责边界：

```text
条件层负责计算并写出 previous_day_minute_required / previous_day_minute_date。
条件层负责定义验收口径和 P0/P1 缺口。
实时行情层负责实际拉取、入库和补拉 previous_day_minute_bar_1m。
条件层不得直接调用行情接口。
```

`market_data_consumer` 建议只允许：

```text
trigger_daily_snapshot
action_minute_bar
both
```

下一阶段分工：

```text
实时行情层读取该 scope，先去重生成 market_data_subscription，再统一拉取 realtime_daily_snapshot / minute_bar_1m，并在盘前预加载 previous_day_minute_bar_1m。
触发层只读 realtime_daily_snapshot / 实时日 K 快照。
动作层只读 minute_bar_1m / previous_day_minute_bar_1m。
用户层只读用户投影和必要行情展示投影。
```

禁止：

```text
触发层直接拉一分钟 K。
条件层直接调用行情接口拉前一日一分钟 K。
动作层直接调用外部行情接口。
用户层直接调用外部行情接口并影响交易判断。
实时行情层按 minute_target_scope 明细行逐行重复拉取同一 identity_key 行情。
行情缺失时越层补抓；应写 pending / missing_market_data。
```

## 13. 质量闸门

N2 条件层必须至少检查：

```text
P0: stock/index/board 物理隔离被破坏
P0: identity_key 缺失
P0: 裸 code 跨资产 join
P0: 88xxxx 进入 stock_trade
P0: index/board 非 market_alert
P0: stock_trade 非 stock
P0: active monitor 无 condition_basis
P0: condition_basis 使用未激活 source_version
P0: period_key_d != prev_trade_date
P0: official daily 缺失仍生成 condition
P0: condition_pool 来源 basis 缺失
P0: 条件层 schema 含触发/动作/语音/模拟账户执行字段
P0: 用户层直接读取 trigger/action 裸表
P0: 用户层回写 condition_basis / condition_pool
P0: 用户层根据条件层数据自行生成动作、语音或模拟成交
P0: 条件层使用 user_policy_hint / locked_target_price / target_lock_status 作为正式字段
P0: 缺少普通 BUY/SELL、FULL、Hint 三类必要条件的独立诊断
P0: BUY:FULL/SELL:FULL 被降级或混写成 BUY:D/SELL:D
P0: BUY_HINT/SELL_HINT 被混写进普通 BUY/SELL 周期条件
P0: BUY_HINT/SELL_HINT 被限制为仅指数/板块可用，或被排除在个股条件范围外
P0: BUY_HINT/SELL_HINT 被写成 direction=hint，而不是 BUY_HINT=buy / SELL_HINT=sell
P0: 条件层静态结构字段被触发层/动作层/用户层回写或重算
P0: source_version 不变但 condition_basis / condition_pool 的目标价或锚字段发生漂移
P0: 触发层直接拉取外部行情，或绕过 N3 使用未闭合/非标准分钟 K；四类 30 分钟确认信号没有使用 N3 标准事实/事件/确认摘要
P0: 动作层绕过实时行情层直接调用外部行情接口
P0: 条件层直接拉取前一日一分钟 K
P0: previous_day_minute_required=true 但 previous_day_minute_date != prev_trade_date
P0: stock_minute_target_scope 个股缺少 total_mv 或不满足 active scope policy 的市值阈值
P0: scope_selection_policy 绕过 condition_pool 扩张行情范围
P0: 实时行情层未先按 asset_kind + identity_key + required_data_kind + for_trade_date 去重生成 market_data_subscription
P0: 行情层按 minute_target_scope 明细行逐行重复拉取同一对象行情
P0: market_data_subscription 缺少 source_scope_ids / source_condition_pool_ids 追溯
P1: stock_trade 条件缺 buy_target_price / clear_sell_ref_period 且未给出可解释缺口
P1: sell 方向缺 sell_target_price 但仍需要展示下跌目标价
P0: alert-only 对象进入 sim/action 范围
P0: condition_pool / minute_target_scope 出现 v3 标准信号白名单外 signal_type
P0: 条件层输出 POS_CLEAR / BUY_FAIL_CLEAR / ADD_BUY_FAIL_REDUCE 等用户层解释类型
P1: active monitor 无 condition_pool
P1: condition_pool stale after monitor change
P1: 财务指标缺失但仍参与评分
P1: 指数/行业上下文缺失
P2: 历史兼容字段缺失但不影响条件生成
```

硬规则：

```text
P0 不允许 execute。
P1 可以 dry-run 报告，但 execute 需用户确认。
P2 仅说明。
```

## 14. 开发阶段建议

### N2-A：schema 草案

只生成 SQL，不连接数据库。

输出：

```text
sql/002_condition_layer_schema.sql
```

### N2-B：basis dry-run

实现：

```text
scripts/build_condition_basis.py --trade-date YYYYMMDD --source-version VERSION --dry-run
```

只读入库事实表，输出报告，不写库。

### N2-C：pool dry-run

实现：

```text
scripts/build_condition_pool.py --trade-date YYYYMMDD --run-id RUN --dry-run
```

从 basis 生成 pool 预览，不写库。

### N2-D：minute_target_scope dry-run

生成行情范围 dry-run，不写库、不拉行情。

### N2-D1：scope policy dry-run

在 N2-D 基础上增加 policy 接口：

```text
scripts/export_minute_target_scope.py --source-trade-date YYYYMMDD --policy configs/minute_scope/manual_YYYYMMDD.json --dry-run
```

要求：

```text
1. 不传 --policy 时使用默认 policy，等价于当前自动规则。
2. 传 --policy 时按 index / board / stock 三段分别筛选。
3. 输出 selected / excluded 统计和样本。
4. policy 只能收窄候选范围，不能绕过 condition_pool 扩张行情范围。
5. dry-run 不写库、不拉行情、不进入触发/动作/用户层。
```

### N2-D3：execute 前置计划

在 N2-D2 诊断基础上增加 `--plan-execute`：

```text
scripts/export_minute_target_scope.py --source-trade-date YYYYMMDD --policy configs/minute_scope/manual_YYYYMMDD.json --plan-execute --dry-run
```

要求：

```text
1. 只输出 future execute 写入计划，不执行 SQL。
2. common_condition_run / common_condition_quality_item / stock/index/board minute_target_scope row count 必须可见。
3. policy_hash 必须稳定，便于后续确认 policy 是否被改动。
4. P0 阻断 execute；P1 需要用户确认；P2 仅说明。
5. 输出按 run_id 回滚的删除顺序。
6. 完成后停下，不进入真正 execute。
```

### N2-E0：条件层整体 execute readiness plan

在 N2-B/N2-C/N2-D3 基础上增加整体计划：

```text
scripts/plan_condition_layer_execute.py --source-trade-date YYYYMMDD --policy configs/minute_scope/manual_YYYYMMDD.json --dry-run
```

要求：

```text
1. 串联 basis / pool / scope 三段 dry-run。
2. 输出 basis / pool / scope 三段 planned row count。
3. 输出统一 planned_run_id、policy_hash、write_order、rollback_plan。
4. 明确 source_condition_basis_id / source_condition_pool_id 只能由真实 execute 同批生成。
5. P0 阻断 execute；P1 需要用户确认或修复；P2 仅说明。
6. 只读生成计划，不执行 SQL、不写库、不拉行情。
7. 完成后停下，不进入真正 execute。
```

### N2-E1：execute contract / rollback plan

在 N2-E0 基础上增加 execute 合同：

```text
scripts/plan_condition_execute_contract.py --source-trade-date YYYYMMDD --policy configs/minute_scope/manual_YYYYMMDD.json --dry-run
```

要求：

```text
1. 只输出 execute contract / rollback contract，不执行 SQL。
2. run_id 规则必须说明每次 execute 生成新 run_id。
3. 默认 reject_if_active_exists；overwrite 必须显式 --overwrite 且 user_confirmation=true。
4. 明确 active run 切换：passed -> superseded，新 run 验收通过后才 passed。
5. 明确 rollback 顺序和 previous_active_run 恢复规则。
6. 明确 execute 前后 row_count/hash 验证。
7. 明确 forbidden write domains：trigger/action/mobile/voice/sim/worker/old_system。
8. 完成后停下，不进入真正 execute。
```

### N2-E2：condition layer execute preflight

在 N2-E1 基础上增加最后只读预演：

```text
scripts/plan_condition_execute_preflight.py --source-trade-date YYYYMMDD --policy configs/minute_scope/manual_YYYYMMDD.json --dry-run
```

要求：

```text
1. 只读检查开发库 schema 是否具备条件层表。
2. 只读检查是否已有同 source_trade_date + for_trade_date 的 active run。
3. 重跑 basis / pool / scope dry-run、readiness plan、execute contract。
4. 输出 run_id preview、expected row counts、P0/P1/P2、schema_status、active_run_status、rollback_sql_preview。
5. schema 未 migration 时只输出 migration readiness，不执行 migration。
6. active run 已存在且未 --overwrite 时 blocked。
7. --overwrite 只影响 dry-run 合同，不执行 overwrite。
8. 完成后停下，不进入 N2-E3 execute。
```

### N2-E2A：condition schema migration readiness

当 N2-E2 输出 `schema_not_migrated` 时，先进入 N2-E2A：

```text
scripts/plan_condition_schema_migration.py --schema sql/002_condition_layer_schema.sql --check-database
```

要求：

```text
1. 只检查 schema SQL 和开发库对象状态。
2. 可使用 read-only 数据库连接检查对象是否存在。
3. 不执行 migration。
4. 不写 condition_basis / condition_pool / minute_target_scope。
5. 不修改 active run。
6. 输出 static_ready、ready_for_first_apply、manual_review_required、ready_for_user_migration_review。
7. 如果条件层表全缺失且 FK 依赖存在，可进入用户确认 migration 阶段讨论。
8. 如果条件层表部分存在或 FK 依赖缺失，必须先人工复核。
9. 完成后停下，不进入 N2-E3 execute。
```

### N2-D execute 到开发库

只有用户明确确认后，才允许写 v3 开发库。

仍禁止：

```text
触发层
action
voice
mobile
sim
真实交易
worker
旧系统写入
```

### N2-E3：condition layer execute

N2-E3 在用户明确确认后，允许把同一个 source_trade_date / for_trade_date 的条件层结果写入 v3 开发库。

CLI：

```text
scripts/run_condition_layer_execute.py --source-trade-date YYYYMMDD --user-confirmed --execute
```

写入范围仅限：

```text
common_condition_run
common_condition_quality_item
stock_monitor_target / index_monitor_target / board_monitor_target
stock_condition_basis / index_condition_basis / board_condition_basis
stock_condition_pool / index_condition_pool / board_condition_pool
stock_minute_target_scope / index_minute_target_scope / board_minute_target_scope
```

说明：

```text
monitor_target 是 condition_basis.source_monitor_target_id 的外键来源，因此 N2-E3 必须在同一事务内先写 monitor_target 执行快照。
monitor_target.source_version 使用 execute_run_id，便于按本次 run 回滚。
```

硬边界：

```text
不执行 migration。
不拉行情。
不拉一分钟 K。
不进入触发/动作/语音/mobile/sim/worker。
不触碰旧系统。
```

### N2-E4：condition_pool 默认范围审计

N2-E4 在 N2-E3 execute 后，对当前 active run 做只读审计，确认 `condition_pool` 是否已经按默认对象范围收口。

CLI：

```text
scripts/audit_condition_pool_scope.py --source-trade-date YYYYMMDD --for-trade-date YYYYMMDD
```

审计对象：

```text
index_condition_pool
board_condition_pool
stock_condition_pool
index_minute_target_scope
board_minute_target_scope
stock_minute_target_scope
```

默认对象范围：

```text
index_condition_pool：
对象 universe 必须只包含固定 9 个指数：
000905、399303、000001、000852、399001、399006、000300、000016、000688。
如果某个固定指数当日没有合格 condition_pool 条件，可以没有 pool 行；但不得出现固定 9 个之外的指数。
index_minute_target_scope 必须来自 index_condition_pool 或等价 dry-run 结果，不再绕过 pool 直接按固定 9 个指数生成。

board_condition_pool：
默认对象 universe 必须只包含 `board_type=tdx_industry` 行业板块；若 policy 显式加入概念/地区，则以 `tdx_concept` / `tdx_region` 扩展。
board_minute_target_scope 必须来自 board_condition_pool 或等价 dry-run 结果，不再绕过 pool 直接按板块代码前缀生成。

stock_condition_pool：
对象 universe 必须只包含具备普通 BUY/SELL、BUY:FULL/SELL:FULL、BUY_HINT/SELL_HINT 条件，
且 total_mv >= 1,000,000 万元、非 ST/风险票、official daily 证明存在、财务快照基础字段可用、
lane/monitor_type 合规的个股。
stock_minute_target_scope 必须来自 stock_condition_pool 或等价 dry-run 结果。
```

报告必须区分：

```text
object_count：对象数量。
row_count：对象 + direction + condition_key 后的条件行数量。
```

如果某次 `index_minute_target_scope = 18`，标准解释是：

```text
index_object_count = 9
direction_count = 2
index_scope_rows = 9 * 2 = 18
```

这表示 18 行“指数方向订阅项”，不是 18 个指数。
但 18 不是强制固定值；如果固定 9 个指数中某些对象没有进入 index_condition_pool，scope 行数应随 pool 结果减少。

审计输出：

```text
index/board/stock condition_pool object_count
index/board/stock condition_pool row_count
index/board/stock out_of_range_row_count
index/board/stock minute_target_scope object_count
index/board/stock minute_target_scope row_count
scope object_count 与 row_count 解释
P0/P1/P2
remediation_plan
```

硬边界：

```text
只读数据库。
不 overwrite。
不删除或 supersede 当前 active run。
不拉行情。
不拉一分钟 K。
不进入触发/动作/语音/mobile/sim/worker。
不触碰旧系统。
如果发现越界，只生成整改计划和 overwrite dry-run 建议，不在 N2-E4 执行。
如果发现 minute_target_scope 绕过 condition_pool 生成 index/board/stock 行，也必须记为 P0 并生成整改计划。
```

### N2-E5：condition_pool 默认策略 dry-run 修正

N2-E5 把默认对象筛选策略前移到 `condition_pool` dry-run，并让 `minute_target_scope` 统一从对应 pool 结果生成。

目标口径：

```text
condition_basis：继续全量。
condition_pool_candidate：从 basis 生成所有具备必要条件的候选。
condition_pool：按默认 policy 收口。
minute_target_scope：只从 condition_pool 或等价 dry-run 结果生成。
```

默认 condition_pool policy：

```text
index：只保留固定 9 个指数中的合格条件。
board：默认只保留 `board_type=tdx_industry` 的行业板块合格条件。
stock：只保留 total_mv >= 1,000,000 万元、非 ST/风险票、official daily 证明存在、
财务快照基础字段可用、lane/monitor_type 合规且具备条件资格的个股。
```

N2-E5 dry-run 输出必须能同时看到：

```text
candidate_pool_row_count
policy_selected_count
policy_excluded_count
policy_excluded_reason_counts
policy_selected_reason_counts
policy_hash
selected_samples
excluded_samples
pool_row_count
minute_target_scope scope_source_counts
```

说明：

```text
pool_row_count 是策略命中后的条件行数，不是全量候选行数。
object_count 是对象数，row_count 是对象 + direction + condition_key 后的条件行数。
具体 row_count 随默认 policy、入库源质量和必要条件计算结果变化，不得把历史样本数字写死为验收常量。
```

硬边界：

```text
只做 dry-run。
不写数据库。
不 overwrite 当前 active run。
不拉行情。
不拉一分钟 K。
不进入触发/动作/语音/mobile/sim/worker。
不触碰旧系统。
```

### N2-E6：schema migration gap plan

N2-E6 用于处理开发库已存在条件层表、而 schema 草案继续演进时的差异计划。

目标：

```text
只读对比开发库当前 schema 与 sql/002_condition_layer_schema.sql。
生成最小 additive migration 草案。
不执行 migration。
不写 condition_basis / condition_pool / minute_target_scope 业务数据。
```

CLI：

```text
scripts/plan_condition_schema_gap.py
```

输出文件：

```text
sql/005_condition_layer_policy_columns_migration.sql
```

要求：

```text
1. 只读连接 v3 开发库，检查 condition-layer 表字段。
2. 输出缺失 column、类型差异、NOT NULL 风险、FK/index/enum/status 差异或 deferred note。
3. migration SQL 只允许 ADD COLUMN IF NOT EXISTS。
4. 默认新增列 nullable。
5. 不 drop column。
6. 不 backfill。
7. 不增加 NOT NULL / DEFAULT / CHECK / FK，除非后续单独 review。
8. rollback 只输出手动 DROP COLUMN 清单，不执行。
```

硬边界：

```text
不 execute。
不 overwrite active run。
不执行 migration。
不拉行情。
不进入 N3 / trigger / action / voice / mobile / sim / worker。
不触碰旧系统。
```

### N2-E7：condition layer migration review

N2-E7 是执行 `005` schema migration 前的最后审阅阶段。

目标：

```text
审阅 sql/005_condition_layer_policy_columns_migration.sql 是否可以提交用户确认。
不执行 migration。
不写业务数据。
```

CLI：

```text
scripts/review_condition_migration.py --report-path docs/N2_E7_CONDITION_LAYER_MIGRATION_REVIEW.md
```

review report 必须包含：

```text
migration_safe_to_apply
additive_only
affects_existing_rows
requires_backup
rollback_manual_only
user_confirmation_required
missing_column_count
type_mismatch_count
not_null_risk_count
constraint_deferred_count
nullable compatibility
```

审阅要求：

```text
1. 005 只能包含 ADD COLUMN IF NOT EXISTS。
2. 新增列保持 nullable。
3. 不 drop column。
4. 不 backfill。
5. 不加 NOT NULL / DEFAULT / CHECK / FK enforcement。
6. execute.py / basis.py / pool.py 必须兼容新增列为空。
7. 旧 active run 的新增列为空时，不得阻塞只读审计或后续 dry-run。
8. N2-E8 执行 migration 前必须再次获得用户明确确认。
```

硬边界：

```text
不 execute。
不执行 migration。
不写 condition_basis / condition_pool / minute_target_scope。
不 overwrite active run。
不拉行情。
不进入 N3 / trigger / action / voice / mobile / sim / worker。
不触碰旧系统。
```

### N2-E8：condition layer 005 additive migration

N2-E8 只在用户明确确认后执行 `sql/005_condition_layer_policy_columns_migration.sql`，用于把开发库 schema 追上 N2-E5 的 policy 字段。

目标：

```text
只执行 005 additive migration。
只做 schema 变更。
不写 condition_basis / condition_pool / minute_target_scope 业务数据。
不 overwrite active run。
```

执行前必须：

```text
1. 读取 N2-E7 migration review report。
2. 备份开发库 schema 或导出 schema-only 快照。
3. 记录 missing_column_count、active run count、条件层业务 row count。
4. 用户明确确认执行 005。
```

执行后必须复查：

```text
missing_column_count=0
type_mismatch_count=0
active run count 不变
业务 row count 不变
新增列存在
```

硬边界：

```text
不写业务数据。
不 overwrite。
不拉行情。
不进入 N3 / trigger / action / voice / mobile / sim / worker。
不触碰旧系统。
```

### N2-E9：condition_pool 收口 overwrite preflight

N2-E9 在 N2-E5 逻辑和 N2-E8 schema 均 ready 后，做新口径 overwrite 前的最后只读预演。

目标：

```text
只读验证新 schema + 新 condition_pool 默认 policy 是否可以进入 overwrite 讨论。
不执行 overwrite。
不写 condition_basis / condition_pool / minute_target_scope。
```

必须重跑：

```text
scripts/build_condition_basis.py --source-trade-date YYYYMMDD --dry-run
scripts/build_condition_pool.py --source-trade-date YYYYMMDD --dry-run
scripts/export_minute_target_scope.py --source-trade-date YYYYMMDD --dry-run
scripts/plan_condition_layer_execute.py --source-trade-date YYYYMMDD --dry-run
scripts/plan_condition_execute_contract.py --source-trade-date YYYYMMDD --overwrite --user-confirmed --dry-run
scripts/plan_condition_execute_preflight.py --source-trade-date YYYYMMDD --overwrite --user-confirmed --dry-run
scripts/audit_condition_pool_scope.py --source-trade-date YYYYMMDD --for-trade-date YYYYMMDD
scripts/plan_condition_schema_gap.py
```

N2-E9 检查项：

```text
schema_ready=true
missing_column_count=0
active_run_exists=true
overwrite_allowed 只能存在于 dry-run contract/preflight 中
P0=0
stock_condition_pool 按 total_mv >= 100 亿等默认 policy 收口
index_condition_pool 只包含固定 9 指数中的合格条件
board_condition_pool 默认只包含 `board_type=tdx_industry` 行业板块合格条件
minute_target_scope 全部来自 condition_pool
previous_day_minute_date = prev_trade_date
```

输出：

```text
old active run id
new execute_run_id preview
old/new row count 对比
old run -> superseded plan
rollback SQL preview
P0/P1/P2
```

说明：

```text
N2-E9 可以使用 --overwrite --user-confirmed 走合同分支，但 will_execute_sql 必须为 false。
execute_allowed=true 只表示可以提交用户讨论进入下一阶段，不表示本阶段已经执行。
```

硬边界：

```text
不执行 overwrite。
不执行 migration。
不写业务数据。
不拉行情。
不进入 N3 / trigger / action / voice / mobile / sim / worker。
不触碰旧系统。
```

### N2-E10：condition_pool 收口 overwrite execute

N2-E10 在用户明确确认后，允许执行一次新的 condition layer overwrite run，把 N2-E5 的默认收口 policy 写入开发库。

目标：

```text
写入新口径 condition_basis / condition_pool / minute_target_scope。
旧 active run 在新 run postcheck 通过后标记为 superseded。
新 run 标记为 passed active。
```

执行前必须：

```text
1. 读取 N2-E9 overwrite preflight report。
2. 重新做 execute preflight，确认 schema_ready=true、P0=0、active_run_exists=true、overwrite=true。
3. 导出 active run 状态、条件层表 row count、schema snapshot。
4. 用户明确确认执行 overwrite。
```

执行命令：

```text
scripts/run_condition_layer_execute.py --source-trade-date YYYYMMDD --execute --overwrite --user-confirmed
```

执行后必须验证：

```text
active passed run = 1
old run status = superseded
new run status = passed
new run P0 = 0
stock/index/board condition_pool row count 等于 preflight 预期
stock/index/board minute_target_scope row count 等于 preflight 预期
scope_source 全部来自 condition_pool
active run audit P0=0
rollback SQL 已生成但不执行
```

硬边界：

```text
不执行 migration。
不拉行情。
不拉一分钟 K。
不进入 N3 / trigger / action / voice / mobile / sim / worker。
不启动服务。
不触碰旧系统。
```

### N2-F：scope consumption contract

N2-F 在 N2-E10 overwrite 完成后，明确 `minute_target_scope` 的消费合同，避免把条件来源明细行误解成行情层实际拉取任务。

目标：

```text
只定义合同和文档。
不执行 SQL。
不写业务数据。
不拉行情。
不进入 N3。
```

核心口径：

```text
minute_target_scope = 条件来源明细表
market_data_subscription = 实时行情层去重后的实际拉取任务
```

粒度：

```text
condition_pool / minute_target_scope:
  asset_kind + identity_key + direction + condition_key

market_data_subscription:
  asset_kind + identity_key + required_data_kind + for_trade_date
```

实时行情层消费 scope 时必须：

```text
1. 按 stock / index / board 物理分表读取 scope。
2. 根据 daily_snapshot_required / minute_required / previous_day_minute_required 生成 required_data_kind。
3. 按 asset_kind + identity_key + required_data_kind + for_trade_date 去重。
4. 保留 source_scope_ids 或 source_condition_pool_ids 用于追溯。
5. 输出 source_scope_row_count、subscription_object_count、subscription_row_count。
```

示例：

```text
index_minute_target_scope=26 表示 26 条条件来源明细。
如果只涉及 8 个 index identity_key，行情层实际指数订阅对象数应为 8，而不是 26。
```

硬边界：

```text
N2-F 不执行 migration。
N2-F 不写 condition_basis / condition_pool / minute_target_scope。
N2-F 不拉行情、不拉一分钟 K。
N2-F 不进入 N3 / trigger / action / voice / mobile / sim / worker。
N2-F 不触碰旧系统。
```

## 15. 建议 CLI

```text
scripts/build_condition_basis.py
scripts/build_condition_pool.py
scripts/diagnose_condition_pool.py
scripts/export_minute_target_scope.py
scripts/plan_condition_layer_execute.py
scripts/plan_condition_execute_contract.py
scripts/plan_condition_execute_preflight.py
scripts/plan_condition_schema_migration.py
scripts/plan_condition_schema_gap.py
scripts/review_condition_migration.py
scripts/run_condition_layer_execute.py
scripts/audit_condition_pool_scope.py
```

所有 CLI 必须支持：

```text
--trade-date
--source-version
--dry-run
--execute
--report-path
--json
--policy
--plan-execute
```

默认必须是 dry-run。

## 16. 建议 API

条件层第一阶段不必做 API。

如果后续需要，只允许条件层只读 API，并且允许用户层在交易时段查询：

```text
GET /api/conditions/basis?for_trade_date=YYYYMMDD
GET /api/conditions/pool?for_trade_date=YYYYMMDD
GET /api/conditions/coverage?for_trade_date=YYYYMMDD
GET /api/conditions/quality?run_id=...
```

这些 API 只能返回条件资格、目标价、清仓参考周期、推荐、指数/板块上下文和质量解释，不得返回 trigger/action 内部状态。

禁止在 N2 阶段做：

```text
POST trigger
POST action
POST voice
POST sim
长期 streaming
worker 控制
```

## 17. 与 v3 入库层的关系

条件层不能重新抓原始数据。

如果发现入库事实缺失，条件层只能：

```text
记录 P0/P1
输出缺口报告
停止 execute
```

不能在条件层临时补 raw data。

## 18. 给 v3 条件层会话的提示词

可以直接复制以下提示词给 v3 会话：

```text
进入 A股监控系统 v3 的 N2 条件层开发。

项目路径：/Users/chuanfuchen/Documents/A股监控系统v3

先读取：
1. AGENTS.md
2. docs/V3_RAW_DATA_INGESTION_DESIGN.md
3. docs/V3_EXISTING_RAW_TO_INGESTION_MAPPING.md
4. docs/V3_LAYERED_SYSTEM_ARCHITECTURE.md
5. docs/V3_CONDITION_LAYER_DEVELOPMENT_DESIGN.md

边界：
- 只在 v3 项目内工作。
- 不碰目标机旧系统数据库。
- 不启动 8866/8868/8869/8871。
- 不改 LaunchAgent。
- 不做触发层、动作层、语音、mobile、sim、真实交易、worker。
- 条件层只生成 condition_basis / condition_pool / minute_target_scope 的 schema、dry-run、诊断。

第一步任务：
N2-A 生成 PostgreSQL 条件层 schema 草案。

要求：
1. stock / index / board 必须物理分表。
2. 生成 sql/002_condition_layer_schema.sql。
3. 包含 common_condition_run、common_condition_quality_item、stock_condition_basis、index_condition_basis、board_condition_basis、stock_condition_pool、index_condition_pool、board_condition_pool、stock_minute_target_scope、index_minute_target_scope、board_minute_target_scope。
4. condition_basis 对齐目标机 signal_precompute_cache 的逻辑，但不要照搬旧库裸 code join。
5. condition_pool 对齐目标机 signal_condition_pool 的资格池逻辑，但继续物理分表。
6. condition_pool / minute_target_scope 必须声明 allowed_signal_types，并限制在 6 类 N2 canonical signal_type：BUY、BUY:FULL、SELL、SELL:FULL、BUY_HINT、SELL_HINT。
   BUY_HINT 和 SELL_HINT 与其他 B/S 标准信号一样覆盖指数、板块和个股；BUY_HINT 必须按 direction=buy，SELL_HINT 必须按 direction=sell，不得使用 direction=hint。
7. condition_basis / condition_pool 必须只保留条件层必要字段：日期版本、身份隔离、周期分级、成交额基准、静态目标、必要条件、财务评分、指数/板块上下文、输出范围、质量审计。
8. 不得把触发/动作/语音/模拟账户执行字段放入条件层 schema，例如 trigger_time、action_id、voice_status、sim_trade_id、locked_target_price、target_lock_status、user_policy_hint。
9. condition_basis / condition_pool 必须包含三类必要条件：普通 BUY/SELL、BUY:FULL/SELL:FULL、BUY_HINT/SELL_HINT。三类必须独立诊断、独立计数、独立追溯。
10. BUY:FULL/SELL:FULL 不得混写成 BUY:D/SELL:D；BUY_HINT/SELL_HINT 不得混入普通 BUY/SELL 周期集合。
11. condition_basis / condition_pool 必须包含条件层静态结构字段：main_up_anchor、up_reference_period、up_amplitude、buy_target_price、main_down_anchor、down_reference_period、down_amplitude、sell_target_price、clear_sell_ref_period。
12. 上述字段只在条件层计算；触发层、动作层、用户层只能只读引用，不得重算或回写。
13. 不允许在条件层输出 POS_CLEAR / BUY_FAIL_CLEAR / ADD_BUY_FAIL_REDUCE；这些交给用户层/持仓策略层解释。
14. 设计时必须遵守用户边界：用户层可以只读查询条件层，但不能查询 trigger/action 裸表；用户层只能被动接收动作层投递事件。
15. 设计时必须遵守实时行情边界：条件层只输出行情范围和前一日分钟 K 预加载需求；实时行情层统一拉取 realtime_daily_snapshot / minute_bar_1m / previous_day_minute_bar_1m；触发层普通 BUY/SELL/FULL 只读实时日 K / 快照，四类 30 分钟确认信号可消费 N3 标准闭合分钟事件或 N3 30 分钟确认摘要；动作层读取今日一分钟 K 和前一日一分钟 K 作为动作上下文。
16. condition_pool 默认范围：index_condition_pool 只从固定 9 个指数中筛选合格条件；board_condition_pool 默认只从 `board_type=tdx_industry` 行业板块中筛选合格条件，概念/地区需 policy 显式加入 `tdx_concept` / `tdx_region`；stock_condition_pool 只从已具备普通 BUY/SELL、BUY:FULL/SELL:FULL、BUY_HINT/SELL_HINT 条件，且默认 total_mv >= 100 亿、非 ST/风险票、official daily 证明存在、财务快照基础字段可用、lane/monitor_type 合规的个股中筛选。condition_pool 必须保留 policy_name、policy_hash、selected_reason，并在 dry-run/report/quality 中保留 excluded_reason 分布和样本。minute_target_scope 必须来自对应 stock/index/board condition_pool 或等价 dry-run 结果；N2-D1 可以通过 scope_selection_policy 继续收窄 index / board / stock 范围，但不得绕过 condition_pool 扩张行情范围。scope 必须包含 previous_day_minute_required / previous_day_minute_date，由行情层按 scope 预加载前一交易日一分钟 K。
17. 写入 docs 或报告说明质量闸门。
18. 不连接数据库，不执行 migration。
19. 完成后运行静态检查，输出修改文件、验证结果、回滚方式，然后停下。
```

## 19. 回滚原则

N2 文档和 schema 都必须可回滚。

如果只改文档或 SQL：

```text
git diff 或备份文件恢复即可。
```

如果未来写开发库：

```text
必须有 dry-run 报告
必须有 source_version
必须有 run_id
必须有 rollback SQL 或可重建策略
```


## N2-R2 静态参考周期整改记录

本节为 2026-05-24 口径修正：

```text
上涨目标价 buy_target_price 对应 up_sell_reference_period（上涨卖出参考周期）。
下跌目标价 sell_target_price 对应 down_buy_reference_period（下跌买入参考周期）。
up_sell_reference_period / down_buy_reference_period 必须有值，缺失为 P0。
clear_sell_ref_period 仅保留为兼容 alias，值等于 up_sell_reference_period。
```

N5 后续真实持仓仍可沿用目标机兜底哲学：

```text
position.clear_sell_ref_period = up_sell_reference_period or D
```

但 N2 新 run 应保证 `up_sell_reference_period` 非空，因此 N5 兜底只应作为防御性保护，不应成为常态。


## N2-R3 静态参考周期全链路整改记录

本节为 2026-05-24 后续口径修正：

```text
up_sell_reference_period / down_buy_reference_period / clear_sell_ref_period 必须贯通 N2 三段：
condition_basis -> condition_pool -> minute_target_scope
```

覆盖表：

```text
stock_condition_basis / index_condition_basis / board_condition_basis
stock_condition_pool / index_condition_pool / board_condition_pool
stock_minute_target_scope / index_minute_target_scope / board_minute_target_scope
```

字段规则：

```text
up_sell_reference_period = computed_up_sell_ref or up_reference_period or main_up_anchor or D
down_buy_reference_period = computed_down_buy_ref or down_reference_period or main_down_anchor or D
clear_sell_ref_period = up_sell_reference_period
```

验收规则：

```text
up_sell_reference_period missing = 0
down_buy_reference_period missing = 0
clear_sell_ref_period missing = 0
clear_sell_ref_period != up_sell_reference_period = 0
invalid_reference_period = 0
```

`minute_target_scope` 继续是条件来源明细表，不等于最终行情拉取任务表；这些参考周期字段只用于 N3/N4/N5/N6 后续只读追溯，不允许后续层重算。


## N2-R4 周期触发阈值冻结方案

本节为 N2-R3 后续方案，目标是让 N2 为 N4 真实盘中触发提供完整、冻结、可追溯的周期阈值。

核心判断：

```text
N2 可以在计算 period_grade_* / period_transition_* 时使用上一周期实体上沿/下沿。
但如果这些阈值不落库，N4 在真实盘中判断“周/月/季/年实时升级”时就会缺少阈值。
N4 不允许回查 N1 历史 K，也不允许自己重算这些历史周期。
```

新增 canonical 字段：

```text
period_trigger_baseline_json
```

贯通范围：

```text
stock/index/board_condition_basis
stock/index/board_condition_pool
stock/index/board_minute_target_scope
N4 stock/index/board_trigger_context_snapshot
```

字段用途：

```text
condition_basis：全量审计根，保存所有对象的周期阈值。
condition_pool：筛选后的条件资格池，继承 baseline 方便解释与追溯。
minute_target_scope：交易链路范围表，语义上等价 trigger_target_scope，承接 baseline 给 N4 本地化。
N4 context：盘中只读本地 baseline，不访问外接盘 N2/N1。
```

最小验收：

```text
period_trigger_baseline_json missing = 0（basis/pool/scope 三段，对进入链路对象）
JSON 至少包含 condition_key 涉及周期的 previous_entity_high / previous_entity_low / previous_avg_amount 或 previous_amount。
fixed 9 index baseline 完整。
common_event_outbox 不变。
N3/N4/N5/N6 不进入。
```

### N2-R4 baseline completeness 整改

013 migration 后，`period_trigger_baseline_json` 的验收分为两层：

```text
1. JSON 存在且 shape 合法。
2. condition_key 必要周期的 baseline_ready=true。
```

`condition_basis` 是全量审计根，可以保留历史窗口不足导致的周期阈值缺口，但必须在每个周期节点写入：

```text
baseline_ready
baseline_missing_fields
```

其中 `baseline_ready=false` 代表该周期缺少 N4 真实触发所需的上一周期实体上沿/下沿或成交额基准。basis dry-run 必须输出缺口统计和样本；该缺口在 basis 层可以作为质量 warning 保留，不直接删除全量 basis 行。

`condition_pool` 是交易链路资格池，必须按 `condition_key` 解析必要周期并阻断缺口行：

```text
普通 BUY/SELL：只校验 condition_key 内涉及周期。
BUY:FULL / SELL:FULL：只校验 D 周期。
BUY_HINT / SELL_HINT：不依赖周期实体阈值，不因 previous_entity_high / previous_entity_low 缺失被剔除。
```

被剔除候选必须保留可解释原因：

```text
excluded_reason = missing_period_trigger_baseline
missing_period_trigger_baseline_periods = [...]
```

`minute_target_scope` 只能继承已通过 pool policy 的 selected 行，不允许再出现 condition_key 必要周期 `baseline_ready=false` 的交易链路行。

### N2 context enrichment for N4 v4

N4 v4 不允许回查 N2/N1，也不允许重算周期阈值、金额链路、FULL/HINT 前置条件。N2 必须在 context enrichment gate 中把 N4 所需的上下文作为冻结 JSON contract 输出。

当前阶段优先扩展 JSON，不新增物理列：

```text
period_trigger_baseline_json.context_enrichment
period_trigger_baseline_json.periods.*.previous_transition
period_trigger_baseline_json.periods.*.previous_amount_baseline
period_trigger_baseline_json.periods.*.period_baseline_ready
period_trigger_baseline_json.periods.*.baseline_source_trade_date
period_trigger_baseline_json.periods.*.source_version
period_trigger_baseline_json.periods.*.freshness_status
raw_json.trigger_amount_chain_baseline_json
raw_json.FULL_prerequisite_trace_json
raw_json.HINT_prerequisite_trace_json
```

目标字段：

```text
previous_transition
previous_entity_high / previous_entity_low
previous_amount_baseline
period_baseline_ready
baseline_source_trade_date / source_version / freshness_status
trigger_amount_chain_baseline_json
trigger_amount_chain_formula_hash
FULL_prerequisite_trace_json
FULL_prerequisite_quality_status
HINT_prerequisite_trace_json
HINT_prerequisite_quality_status
context_enrichment_version
context_enrichment_hash
```

FULL 规则：

```text
BUY:FULL / SELL:FULL 在 N2 只输出 prerequisite trace。
N4 v4 execute matcher 不允许把 FULL trace 作为正式触发依据。
FULL_prerequisite_quality_status = blocked_trace_only 表示 trace 存在但执行匹配仍阻断。
```

HINT 规则：

```text
BUY_HINT / SELL_HINT 由 N2 证明前置结构。
N4 只能基于 N3 标准化 projection 指标确认 30m 条件，不得回算 N2 前置结构。
```

dry-run artifact：

```text
docs/N2_CONTEXT_ENRICHMENT_CONTRACT.md
docs/N2_context_enrichment_contract.json
docs/N2_CONTEXT_ENRICHMENT_SCHEMA_CONTRACT_DRY_RUN_REPORT.md
docs/N2_context_enrichment_schema_contract_dry_run_report.json
```

## N2-Display-0 condition_display_basis 设计决策

N2 正式采用四表输出：

```text
condition_basis          全量审计根
condition_pool           策略筛选后的条件行
minute_target_scope      N3/N4/N5 交易链路 scope
condition_display_basis  N6 展示输入
```

`condition_display_basis` 的目标是把 N6 展示查询从交易链路中拆出来。它由 N2 生成，N6 只读，N3/N4/N5 不读取。

物理表：

```text
stock_condition_display_basis
index_condition_display_basis
board_condition_display_basis
```

推荐粒度：一对象一行。若一个对象有多个 condition_pool / minute_target_scope 条件行，display basis 应聚合为 JSON 数组追溯：

```text
source_condition_pool_ids_json
source_minute_target_scope_ids_json
selected_directions_json
selected_condition_keys_json
selected_signal_types_json
```

推荐继承字段：

```text
period_grade_y/q/m/w/d
period_transition_y/q/m/w/d
prev_up_str / prev_dn_str
buy_target_price / sell_target_price
up_sell_reference_period / down_buy_reference_period / clear_sell_ref_period
period_trigger_baseline_json
main_up_anchor / main_down_anchor
total_mv / score / recommendation_level
official_daily_proof / financial_quality_status
policy_name / policy_hash / display_scope_reason
```

禁止字段：

```text
trigger_time / trigger_period / action_id / action_status
voice_status / tts_text / sim_trade_id / position_id
user_id / device_id
```

生命周期规则：正式写入 `condition_display_basis` 必须生成新的 N2 run_id，并与同一 run_id 的 `condition_basis / condition_pool / minute_target_scope` 一起写入、一起回滚。不得在旧 active run 上补写 display basis。

对下游影响：N3/N4/N5 输入合同不变，仍只依赖 `minute_target_scope / market_data_subscription / 标准事件`。N6 优先读取 `condition_display_basis`，不直接 join N2 内部三表，也不读 trigger/action 裸表。
