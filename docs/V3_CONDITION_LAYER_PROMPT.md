# v3 条件层会话提示词

复制下面这段给 v3 条件层开发会话：

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
6. condition_pool / minute_target_scope 必须声明 allowed_signal_types，并限制在 6 类 v3 标准信号：B_BUY_30M_VOL、B_BUY、S_SELL_30M_SHRINK、S_SELL、BUY_HINT、SELL_HINT。
   BUY_HINT 和 SELL_HINT 与其他 B/S 标准信号一样覆盖指数、板块和个股；BUY_HINT 必须按 direction=buy，SELL_HINT 必须按 direction=sell，不得使用 direction=hint。
7. condition_basis / condition_pool 必须只保留条件层必要字段：日期版本、身份隔离、周期分级、成交额基准、静态目标、必要条件、财务评分、指数/板块上下文、输出范围、质量审计。
8. 不得把触发/动作/语音/模拟账户执行字段放入条件层 schema，例如 trigger_time、action_id、voice_status、sim_trade_id、locked_target_price、target_lock_status、user_policy_hint。
9. condition_basis / condition_pool 必须包含三类必要条件：普通 BUY/SELL、BUY:FULL/SELL:FULL、BUY_HINT/SELL_HINT。三类必须独立诊断、独立计数、独立追溯。
10. BUY:FULL/SELL:FULL 不得混写成 BUY:D/SELL:D；BUY_HINT/SELL_HINT 不得混入普通 BUY/SELL 周期集合。
11. condition_basis / condition_pool 必须包含条件层静态结构字段：main_up_anchor、up_reference_period、up_amplitude、buy_target_price、main_down_anchor、down_reference_period、down_amplitude、sell_target_price、clear_sell_ref_period。
12. 上述字段只在条件层计算；触发层、动作层、用户层只能只读引用，不得重算或回写。
13. 不允许在条件层输出 POS_CLEAR / BUY_FAIL_CLEAR / ADD_BUY_FAIL_REDUCE；这些交给用户层/持仓策略层解释。
14. 设计时必须遵守用户边界：用户层可以只读查询条件层，但不能查询 trigger/action 裸表；用户层只能被动接收动作层投递事件。
15. 设计时必须遵守实时行情边界：条件层只输出行情范围和前一日分钟 K 预加载需求；实时行情层统一拉取 realtime_daily_snapshot / minute_bar_1m / previous_day_minute_bar_1m；触发层只读实时日 K / 快照；动作层才读今日一分钟 K 和前一日一分钟 K。
16. minute_target_scope 行情范围：指数固定包含 000905、399303、000001、000852、399001、399006、000300、000016、000688；板块包含所有 881 开头行业板块；个股只包含已具备普通 BUY/SELL、BUY:FULL/SELL:FULL、BUY_HINT/SELL_HINT 条件且 total_mv > 100 亿的个股。scope 必须包含 previous_day_minute_required / previous_day_minute_date，由行情层按 scope 预加载前一交易日一分钟 K。
17. 写入 docs 或报告说明质量闸门。
18. 不连接数据库，不执行 migration。
19. 完成后运行静态检查，输出修改文件、验证结果、回滚方式，然后停下。
```
