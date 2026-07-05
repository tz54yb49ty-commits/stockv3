# N2 Web Policy Filter Design

版本：V0.1
日期：2026-05-24
阶段：N2 条件层操作界面方案

## 1. 目标

本文定义 N2 条件层网页筛选控制台的最终方案，用于后续落代码前确认边界。

目标是让用户在 N2 每日默认任务完成后，可以登录界面查看最新条件层结果，调整指数、板块、个股筛选条件，执行 dry-run 预览，确认后生成新的 active condition run。

核心原则：

```text
网页只操作 policy。
网页不直接修改 condition_basis / condition_pool / minute_target_scope 行。
筛选结果必须通过 N2 dry-run / execute 重新生成。
N3 只读最终 active run 的 minute_target_scope。
```

本文只做方案固化，不代表当前阶段允许直接开发前端页面。真正落代码前必须再次确认当前 layer_role、允许范围和执行边界。

## 2. 层级边界

本方案属于 N2 条件层控制台，不改变 N2 核心计算链路。

允许：

```text
读取 N1 active source_version
运行 check_condition_source_ready
运行 condition_basis / condition_pool / minute_target_scope dry-run
按用户确认执行 N2 overwrite，写新的 condition run
生成 N2 报告和 rollback SQL
```

禁止：

```text
外拉行情接口，包括 mootdx / tushare / 实时行情
修复 N1 入库事实
写 N1 ingest 表
进入 N3 market_data_subscription execute
拉 1 分钟 K
写 trigger/action/mobile/voice/sim
启动 worker
```

如果发现 N1 数据缺口，N2 网页或后端必须停止执行，并输出给 N1 会话的提示词，不得在 N2 内补数。

## 3. 不改 N2 核心

本方案不改：

```text
condition_basis 全量计算
condition_pool 生成框架
minute_target_scope 从 condition_pool 生成
stock/index/board 物理分表
active run / superseded / rollback 机制
N3 读取 scope 契约
```

只新增：

```text
policy 配置入口
policy dry-run 预览
policy execute overwrite 控制台
policy 版本、hash、审计和回滚报告
```

## 4. 正确执行流程

每日默认流程：

```text
N1 入库完成并激活 active source_version
-> N2 使用默认 policy 自动生成 active condition run
-> N3 等待读取 active minute_target_scope
```

用户手动筛选流程：

```text
用户登录 N2 网页
-> 查看当前 active condition run
-> 调整 index / board / stock policy
-> 点击 dry-run
-> 查看 selected / excluded / reason_counts / samples
-> 用户确认 overwrite
-> N2 生成新的 active condition run
-> 旧 run 标记 superseded
-> 新 condition_pool 和 minute_target_scope 生效
-> N3 读取新的 active minute_target_scope
```

禁止流程：

```text
N2 execute 后直接手改 stock_minute_target_scope
N2 execute 后直接手改 index_minute_target_scope
N2 execute 后直接手改 board_minute_target_scope
绕过 condition_pool 把对象写入 minute_target_scope
网页直接 update / delete condition_pool 或 minute_target_scope 行
```

## 5. 页面结构

页面名称：

```text
N2 条件层控制台
```

顶部状态区展示：

```text
active run_id
source_trade_date
for_trade_date
prev_trade_date
source_versions
policy_name
policy_hash
P0 / P1 / P2
condition_basis 行数
condition_pool 行数
minute_target_scope 行数
rollback SQL 状态
```

主区域分三个 Tab：

```text
指数筛选
板块筛选
个股筛选
```

全局按钮：

```text
加载默认策略
保存为草稿
Dry-run 预览
确认生成新 active run
查看 rollback SQL
恢复上一 active run
```

## 6. 指数筛选

默认策略：

```text
固定 9 指数：
000905 / 399303 / 000001 / 000852 / 399001 / 399006 / 000300 / 000016 / 000688
```

必须使用 exchange-qualified identity：

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

可配置项：

```text
勾选 / 取消指数
direction: buy / sell
condition_key: BUY:* / SELL:* / BUY:FULL / SELL:FULL / BUY_HINT / SELL_HINT
period_grade_y/q/m/w/d
period_transition_y/q/m/w/d
require_buy_target_price
require_sell_target_price
require_up_sell_reference_period / require_down_buy_reference_period / require_up_sell_reference_period / down_buy_reference_period / clear_sell_ref_period(legacy)(legacy)
```

展示字段：

```text
index_condition_basis 摘要
index_condition_pool 明细
index_minute_target_scope 明细
prev_up_str / prev_dn_str
period_transition_y/q/m/w/d
buy_target_price
sell_target_price
up_sell_reference_period / down_buy_reference_period / clear_sell_ref_period(legacy)
selected_reason / excluded_reason
```

## 7. 板块筛选

默认策略：

```text
所有 881 开头行业板块
```

可配置项：

```text
board_code_prefix
include_board_codes
exclude_board_codes
direction: buy / sell
condition_key
period_grade_y/q/m/w/d
period_transition_y/q/m/w/d
require_buy_target_price
require_sell_target_price
require_up_sell_reference_period / require_down_buy_reference_period / require_up_sell_reference_period / down_buy_reference_period / clear_sell_ref_period(legacy)(legacy)
main_up_anchor
main_down_anchor
```

展示字段：

```text
board_condition_basis 摘要
board_condition_pool 明细
board_minute_target_scope 明细
入选板块数
剔除板块数
剔除原因分布
selected_reason / excluded_reason
```

## 8. 个股筛选

默认策略：

```text
具备普通 BUY / SELL
BUY:FULL / SELL:FULL
BUY_HINT / SELL_HINT
total_mv >= 100 亿
非 ST / 风险票
official daily 完整
财务基础字段可用
lane / monitor_type 合规
```

可配置项：

```text
min_total_mv_yi / max_total_mv_yi
exclude_st
require_official_daily_proof
require_financial_quality_passed
direction: buy / sell
condition_key
condition_family: ordinary / full / hint
period_grade_y/q/m/w/d
period_transition_y/q/m/w/d
require_buy_target_price
require_sell_target_price
require_up_sell_reference_period / require_down_buy_reference_period / require_up_sell_reference_period / down_buy_reference_period / clear_sell_ref_period(legacy)(legacy)
min_score
recommendation_levels
main_index_code
preferred_board_code
include_codes
exclude_codes
limit
```

展示字段：

```text
candidate_count
selected_count
excluded_count
excluded_reason_counts
selected_reason_counts
入选个股明细
剔除样本
total_mv
period_transition_y/q/m/w/d
buy_target_price
sell_target_price
up_sell_reference_period / down_buy_reference_period / clear_sell_ref_period(legacy)
financial_quality_status
recommendation_level
```

## 9. Policy JSON 草案

最小 policy 结构：

```json
{
  "policy_name": "default_adjusted_by_user",
  "index": {
    "enabled_identities": [
      "index:SH:000905",
      "index:SZ:399303",
      "index:SH:000001",
      "index:SH:000852",
      "index:SZ:399001",
      "index:SZ:399006",
      "index:SH:000300",
      "index:SH:000016",
      "index:SH:000688"
    ],
    "directions": ["buy", "sell"],
    "condition_keys": ["*"],
    "require_buy_target_price": false,
    "require_sell_target_price": false,
    "require_up_sell_reference_period / require_down_buy_reference_period / require_up_sell_reference_period / down_buy_reference_period / clear_sell_ref_period(legacy)(legacy)": false
  },
  "board": {
    "board_code_prefix": "881",
    "include_codes": [],
    "exclude_codes": [],
    "directions": ["buy", "sell"],
    "condition_keys": ["*"],
    "require_buy_target_price": false,
    "require_sell_target_price": false,
    "require_up_sell_reference_period / require_down_buy_reference_period / require_up_sell_reference_period / down_buy_reference_period / clear_sell_ref_period(legacy)(legacy)": false
  },
  "stock": {
    "min_total_mv_yi": 100,
    "exclude_st": true,
    "require_official_daily_proof": true,
    "require_financial_quality_passed": false,
    "directions": ["buy", "sell"],
    "condition_keys": ["*"],
    "period_grade": {},
    "period_transition": {},
    "require_buy_target_price": false,
    "require_sell_target_price": false,
    "require_up_sell_reference_period / require_down_buy_reference_period / require_up_sell_reference_period / down_buy_reference_period / clear_sell_ref_period(legacy)(legacy)": false,
    "min_score": null,
    "recommendation_levels": []
  }
}
```

## 10. 后端接口草案

只读接口：

```text
GET /api/n2/active-run
GET /api/n2/policy/default
GET /api/n2/policy/{policy_id}
GET /api/n2/runs/{run_id}/summary
GET /api/n2/runs/{run_id}/pool?asset=index|board|stock
GET /api/n2/runs/{run_id}/scope?asset=index|board|stock
GET /api/n2/runs/{run_id}/rollback-sql
```

写入或执行接口：

```text
POST /api/n2/policy/save
POST /api/n2/policy/dry-run
POST /api/n2/policy/execute-overwrite
```

接口边界：

```text
dry-run 不写 condition 正式表。
execute-overwrite 必须要求用户确认。
execute-overwrite 只能调用 N2 条件层执行合同。
任何接口都不得调用 mootdx / tushare / 实时行情接口。
任何接口都不得写 N1 ingest 表。
任何接口都不得写 N3 / trigger / action / mobile / voice / sim。
```

## 11. 后端执行语义

dry-run：

```text
读取 active source_version
读取 policy
运行 check_condition_source_ready
运行 condition_basis dry-run
运行 condition_pool dry-run
运行 minute_target_scope dry-run
返回 candidate / selected / excluded / reason_counts / samples / policy_hash
不写正式表
不拉行情
```

execute-overwrite：

```text
要求 user_confirmed=true
执行前生成 preflight
执行前生成 active run 快照
执行 N2 overwrite
写 common_condition_run
写 common_condition_quality_item
写 stock/index/board condition_basis
写 stock/index/board condition_pool
写 stock/index/board minute_target_scope
旧 active run -> superseded
新 run -> passed active
生成 rollback SQL
执行后审计 P0=0
```

## 12. Policy 存储建议

MVP 可以先使用 JSON 文件：

```text
configs/n2_policy/default.json
configs/n2_policy/manual_YYYYMMDD.json
```

正式版本建议增加 PostgreSQL 表：

```text
common_condition_policy
```

建议字段：

```text
policy_id
policy_name
asset_scope
policy_json
policy_hash
is_default
status
created_by
created_at
updated_at
raw_json
```

可选 dry-run 报告表：

```text
common_condition_policy_dry_run_report
```

建议字段：

```text
policy_id
source_trade_date
for_trade_date
run_preview_id
candidate_count_json
selected_count_json
excluded_count_json
excluded_reason_counts_json
report_json
created_at
```

## 13. N3 交接契约

N2 网页筛选完成并 execute 后，N3 只读取新的 active run：

```text
common_condition_run
stock_minute_target_scope
index_minute_target_scope
board_minute_target_scope
```

N3 可只读追溯：

```text
stock_condition_pool / index_condition_pool / board_condition_pool
stock_condition_basis / index_condition_basis / board_condition_basis
```

N3 不读取 policy 草稿，不读取 dry-run 临时结果，不根据网页状态自行改变订阅范围。

## 14. 验收标准

未来落代码时，至少满足：

```text
页面可看到当前 active run 摘要。
页面可看到 index / board / stock 最新 pool 和 scope 明细。
页面可加载默认 policy。
页面可保存自定义 policy。
页面可执行 policy dry-run。
dry-run 返回 selected / excluded / reason_counts。
execute-overwrite 必须二次确认。
execute-overwrite 后生成新的 active condition run。
旧 active run 标记 superseded。
新 run 生成 rollback SQL。
N3 只读新 active run 的 minute_target_scope。
```

边界验收：

```text
不外拉 mootdx / tushare / 实时行情。
不修复 N1 fact。
不写 common_ingest_batch / common_active_source_version / N1 fact 表。
不进入 N3 execute。
不拉 1 分钟 K。
不写 trigger/action/mobile/voice/sim。
不启动 worker。
```

## 15. 技术建议

MVP 技术栈：

```text
FastAPI + Jinja2 + HTMX
```

原因：

```text
实现轻
适合内部控制台
可以复用现有 Python N2 脚本
不需要先引入复杂前端工程
后续可升级 React / Vue
```

如果当前项目阶段仍禁止前端页面，则先实现 CLI / JSON policy / API dry-run，页面开发必须等待用户明确确认。

## 16. N2-Web-1 控制台改造约束

N2-Web-1 进入实现阶段后，控制台默认界面不再以 JSON 编辑器为主，而是采用三段筛选页签：

```text
指数筛选
板块筛选
个股筛选
```

每个页签必须通过控件生成 policy JSON，并在高级模式中同步展示最终 JSON。高级模式默认折叠，仅用于查看、粘贴或校验 policy JSON。

三类资产通用控件：

```text
direction
condition_family
condition_key
Y/Q/M/W/D period_grade
Y/Q/M/W/D period_transition
prev_up_str
prev_dn_str
include_codes
exclude_codes
require_buy_target_price
require_sell_target_price
require_up_sell_reference_period / require_down_buy_reference_period / require_up_sell_reference_period / down_buy_reference_period / clear_sell_ref_period(legacy)(legacy)
```

个股额外控件：

```text
min_total_mv_yi
max_total_mv_yi
exclude_st
require_official_daily_proof
require_financial_quality_passed
min_score
recommendation_levels
main_index_code
preferred_board_code
limit
```

摘要数据来源要求：

```text
页面初始摘要只能来自当前 active condition run 的 PostgreSQL 只读查询。
Dry-run 后的结果区只能展示本次 dry-run 返回值。
不得固定读取 docs/N2_E9_pool_dry_run.json / docs/N2_E9_scope_dry_run.json 等旧报告作为页面摘要或 dry-run 替代。
如果数据库不可用，页面必须显式显示 unavailable，而不是使用旧报告兜底。
```

N2-Web-1 仍然保持：

```text
execute-overwrite disabled
dry-run 不写 condition 正式表
不改 condition_basis 核心计算口径
不拉行情
不进入 N3
不启动 worker
```

## 17. N2-Web-1.1 分级多选控件约束

N2-Web-1.1 将 index / board / stock 的 `period_grade` 与 `period_transition` 控件从原生 `<select multiple>` 改为 checkbox chips。

控件要求：

```text
Y/Q/M/W/D 每个周期各有一组 period_grade checkbox chips。
Y/Q/M/W/D 每个周期各有一组 period_transition checkbox chips。
每组都提供“全选 / 清空”快捷操作。
checkbox 的 name 必须保持同名多值格式，例如 stock.period_transition.d。
前端 Dry-run 提交必须使用 FormData / URLSearchParams 保留重复字段。
```

JSON 同步要求：

```json
{
  "stock": {
    "period_transition": {
      "d": ["volume_up", "flat"]
    },
    "period_grade": {
      "w": ["volume_down", "flat"]
    }
  }
}
```

后端要求：

```text
policy_from_control_payload 必须继续接收 parse_qs/FormData 形态的多个同名字段。
dry-run 优先使用 policy_json；当 policy_json 为空时，必须能从同名 checkbox 字段还原 policy JSON。
execute-overwrite 继续 disabled。
```

## 18. N2-Web-1.2 Active Run 全量明细浏览

N2 网页控制台必须支持从当前 active condition run 只读查看三类资产的三类 N2 明细表：

```text
index_condition_basis
index_condition_pool
index_minute_target_scope

board_condition_basis
board_condition_pool
board_minute_target_scope

stock_condition_basis
stock_condition_pool
stock_minute_target_scope
```

默认行为：

```text
页面默认读取当前 active condition run。
index / board 明细按当前筛选全量展示。
stock 明细必须分页展示，默认 page_size=100，禁止一次性把 5000+ / 4000+ 行全部渲染到页面。
所有明细查询都必须使用 PostgreSQL read-only transaction。
数据库不可用时显示 unavailable，不得读取 docs/N2_E9_* 固定报告兜底。
```

筛选能力：

```text
index：code / name / condition_key / direction / period_transition / 是否有目标价
board：board_code / board_name / condition_key / direction / period_transition / 是否有目标价
stock：code / name / condition_key / direction / total_mv / period_transition / 是否有目标价 / up_sell_reference_period / down_buy_reference_period / clear_sell_ref_period(legacy) / score
```

导出能力：

```text
全量明细提供“导出 Excel”按钮。
导出沿用当前 active condition run 和当前明细筛选条件。
stock 页面浏览仍分页，但 Excel 导出当前筛选命中的全部行，不受当前 page 影响。
导出为本地 .xlsx 下载，只读 PostgreSQL，不写 condition_basis / condition_pool / minute_target_scope。
导出默认排除 raw_json / missing_fields_json 等大字段，其余明细列保留到工作簿。
```

实现约束：

```text
筛选只影响网页明细查询结果，不修改 policy JSON。
筛选不得写 condition_basis / condition_pool / minute_target_scope。
pool / scope 表如自身不含 period_transition、目标价、score 等字段，可以只读关联 source_condition_basis_id 进行筛选和展示追溯字段。
execute-overwrite 继续 disabled。
不改 condition_basis 核心计算口径。
不拉行情、不进入 N3、不启动 worker。
```

用户体验要求：

```text
页面顶部提供“策略筛选 / Dry-run 结果 / 全量明细”快速跳转，减少长页滚动成本。
策略筛选中的 Y/Q/M/W/D period_grade 与 period_transition 默认放入可展开区域，避免首屏被低频筛选项占满。
明细表默认聚焦 code/name/direction/condition_key/period_transition/目标价/score 等关键列。
原始数据库仍为全量只读来源；网页可以隐藏低频技术列，但必须显示当前聚焦列数量和隐藏列数量。
空值在表格中显示为 “-”，避免 None / 空字符串干扰扫读。
```


## N2-R2 web policy note

筛选控制台保留 legacy `require_clear_sell_ref_period`，但 canonical 字段改为：

```text
require_up_sell_reference_period
require_down_buy_reference_period
```

展示或筛选时应优先使用 `up_sell_reference_period / down_buy_reference_period`；`clear_sell_ref_period` 仅作为 `up_sell_reference_period` 的兼容 alias。


## N2-R3 web policy note

筛选控制台读取的明细字段必须与 N2 三段链路一致：

```text
condition_basis
condition_pool
minute_target_scope
```

三段都应能展示 / 筛选：

```text
up_sell_reference_period
down_buy_reference_period
clear_sell_ref_period
```

其中 `clear_sell_ref_period` 仅作为 legacy alias 展示，筛选策略应优先使用 `up_sell_reference_period / down_buy_reference_period`。


## N2-Web-2 / N2-R4 period trigger baseline note

8782 控制台必须适配 N2-R4 的触发阈值冻结字段：

```text
period_trigger_baseline_json
baseline_ready
required_period_not_ready
```

界面语义：

```text
minute_target_scope 是正式表名。
页面展示时必须同时标注 trigger_target_scope 语义，表示这些 scope 行是 N3/N4 之后消费的触发目标范围来源。
网页不得把 trigger_target_scope 当成新表写入，也不得绕过 minute_target_scope。
```

明细浏览要求：

```text
condition_basis / condition_pool / minute_target_scope 都应展示 period_trigger_baseline_json 的摘要列。
摘要至少包含 baseline_status、baseline_ready_periods、baseline_not_ready_periods、required_period_not_ready。
period_transition 明细筛选必须支持多选同名字段，不再限制为单选。
支持 baseline_status = ready / partial / missing。
支持 required_period_not_ready = yes / no。
支持 up_sell_reference_period / down_buy_reference_period / clear_sell_ref_period(legacy) 筛选。
```

Dry-run 展示要求：

```text
Dry-run 结果必须展示 N2-R4 baseline 闸口。
reason_counts 中的 missing_period_trigger_baseline 必须显式保留。
quality.items 中 period_trigger_baseline* / required_period_not_ready* 质量项必须在 baseline gate 中汇总。
```

边界：

```text
N2-Web-2 只读 active condition run 或 dry-run 返回值。
不执行 migration。
不 overwrite active condition run。
不写 condition_basis / condition_pool / minute_target_scope。
不进入 N3/N4/N5/N6。
不拉行情或分钟 K。
```

## N2-Web-Display condition_display_basis 展示输入

8782 控制台后续需要支持 `condition_display_basis` 只读展示。该表不是 policy 编辑表，而是 N2 overwrite 后生成的 N6 展示输入。

页面语义：

```text
condition_basis：全量审计根
condition_pool：策略筛选后的条件行
minute_target_scope：交易链路 scope / trigger_target_scope
condition_display_basis：N6 展示输入
```

控制台要求：

```text
策略筛选仍只修改 policy。
Dry-run 需要预览 display_basis 行数、对象数和聚合字段。
Overwrite 仍必须由 N2 execute 统一生成 basis/pool/scope/display_basis。
页面不得直接 insert/update/delete condition_display_basis。
```

展示建议：新增 “展示输入 / N6 display basis” 明细 Tab，默认一对象一行，突出目标价、参考周期、分级、推荐、入选 condition_key、selected_signal_types 和 source id 追溯。JSON 字段默认折叠展示。
