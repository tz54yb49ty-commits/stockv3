# N4 Trigger Rule Spec v4

Status: SPEC_FREEZE_PASS

Layer role: `N4_trigger`

Source: runtime_control approved N4 Trigger Rule Spec v4.

This document is intentionally not summarized. It preserves the v4 rule text and assigns stable rule identifiers for implementation, testing, and runtime_control tracking.

Freeze contract:

```text
trigger_rule_spec_version = N4_TRIGGER_RULE_SPEC_v4
trigger_rule_policy_hash = 3d4b046ea6a02ad8
independent_v4_run_id_required = true
historical_run_reinterpretation = forbidden
approved_changes_artifact = docs/N4_TRIGGER_RULE_SPEC_v4_APPROVED_CHANGES.json
```

Historical runs produced under earlier contracts remain auditable only under their original contracts. They must not be silently interpreted as v4.

## 1. 总原则

N4 只负责把 N2 条件候选和 N3 标准行情事实合成为触发事实。

**N4-001** N4 允许读取 N2 本地化 `trigger_context_snapshot`。

**N4-002** N4 允许读取 N3 标准 `snapshot` / `projection` / `closed summary` / `action-confirmation metric`。

**N4-003** N4 允许判断 `trigger state`。

**N4-004** N4 允许输出 `TriggerMatched` / `TriggerPendingMarketData` / `TriggerStateChanged`。

**N4-005** N4 禁止拉行情。

**N4-006** N4 禁止查 `raw K`。

**N4-007** N4 禁止回查 N1 daily K。

**N4-008** N4 禁止自行聚合 `Y/Q/M/W/D`。

**N4-009** N4 禁止自行拼 `30m bucket`。

**N4-010** N4 禁止自行复权 `qfq/hfq`。

**N4-011** N4 禁止重算 N2 condition。

**N4-012** N4 禁止写 N5 action。

**N4-013** N4 禁止写 N6 user。

**N4-014** N4 禁止写 `voice/mobile/sim/position/real trade`。

**N4-015** N4 使用的所有周期、金额、实体、projection 字段必须来自 `trigger_context_snapshot`、N3 standardized projection facts、N3 closed summary facts、N3 action-confirmation metric facts。

**N4-016** N4 不生产周期、金额、实体、projection 字段，只消费这些字段。

## 2. Canonical Runtime Fields

**N4-017** N4 runtime `signal_type` 只允许 `B_BUY` / `S_SELL`。

**N4-018** 来源差异不进入 `signal_type`，而进入 `trigger_kind`、`original_condition_key`、`trigger_mark_candidate`。

**N4-019** `trigger_kind` 只允许 `trigger` / `hint`。

**N4-020** `original_condition_key` 保留上游 condition provenance，包括 `BUY:D`、`BUY:W,D`、`BUY:Y,Q,M,W,D`、`BUY:FULL`、`BUY_HINT`、`SELL:D`、`SELL:M,W,D`、`SELL:Y,Q,M,W,D`、`SELL:FULL`、`SELL_HINT`。

**N4-021** `trigger_mark_candidate` 只允许 `normal` / `30m_volume` / `30m_shrink`。

**N4-022** N4 不输出最终 `action_mark`。

**N4-023** N4 不输出 `ActionEligible`。

**N4-024** N4 不输出 `ActionExecuted`。

**N4-025** N4 输出标准触发事件，并在触发 outcome payload / fact guard 中携带 `n5_entry_allowed`，含义是 N4 是否允许 N5 开始动作确认。

**N4-026** `n5_entry_allowed` 不表示动作是否合格、是否买卖、是否展示、是否模拟、是否交易。

## 3. Trigger Kind

**N4-027** 普通周期触发和 FULL 触发使用 `trigger_kind=trigger`。

**N4-028** `trigger_kind=trigger` 对应 `BUY:D` / `BUY:W,D` / `BUY:Y,Q,M,W,D` / `BUY:FULL` / `SELL:D` / `SELL:M,W,D` / `SELL:Y,Q,M,W,D` / `SELL:FULL`。

**N4-029** 超跌 / 超涨提示型触发使用 `trigger_kind=hint`。

**N4-030** `trigger_kind=hint` 对应 `BUY_HINT` / `SELL_HINT`。

**N4-031** `BUY_HINT` 的 runtime signal 仍然是 `signal_type=B_BUY`。

**N4-032** `SELL_HINT` 的 runtime signal 仍然是 `signal_type=S_SELL`。

## 4. 周期体系

**N4-033** 正式周期只包括 `Y / Q / M / W / D`。

**N4-034** 周期优先级为 `Y > Q > M > W > D`。

**N4-035** `triggered_periods` 表示本次事件中实际触发的 `Y/Q/M/W/D` 周期。

**N4-036** `all_trigger_periods` 表示当日累计已经触发的 `Y/Q/M/W/D` 周期。

**N4-037** `primary_trigger_period` 表示 `all_trigger_periods` 中最高周期。

**N4-038** `30m` 不属于 `primary_trigger_period`。

**N4-039** `30m` 不进入 `triggered_periods`。

**N4-040** `30m` 不进入 `all_trigger_periods`。

**N4-041** `30m` 单独表达为 `projection_period=30m`。

**N4-042** `30m` 单独表达为 `projection_30m_type=volume_up / shrink_down / none`。

## 5. 放量上涨 / 缩量下跌

**N4-043** N4 可以使用公式判断当前周期状态，但公式输入必须来自 `trigger_context_snapshot.period_trigger_baseline_json`、N3 projection、N3 closed summary、N3 action-confirmation metric。

**N4-044** N4 禁止自己查 raw K 或回算周期 K。

**N4-045** `previous_entity_high = max(previous_open, previous_close)`。

**N4-046** `previous_entity_low = min(previous_open, previous_close)`。

**N4-047** `transition_amount_pass` 是第一层金额判断，用于周期分级。

**N4-048** BUY 侧 `transition_amount_pass = current_amount_metric > previous_amount_baseline`。

**N4-049** SELL 侧 `transition_amount_pass = current_amount_metric < previous_amount_baseline`。

**N4-050** 放量上涨定义为 `current_price_or_close > previous_entity_high AND transition_amount_pass=true => current_transition=volume_up`。

**N4-051** 缩量下跌定义为 `current_price_or_close < previous_entity_low AND transition_amount_pass=true => current_transition=low_volume_down`。

**N4-052** 其他状态包括 `low_volume_up`、`volume_down`、`flat`、`unknown`。

## 6. Trigger Amount Chain

**N4-053** `trigger_amount_chain_pass` 是第二层金额链路。

**N4-054** `trigger_amount_chain_pass` 独立于 `transition_amount_pass`，用于判断触发是否成立。

**N4-055** BUY D 金额链为 `today_virt_amount >= weekly_avg_with_today >= prev_weekly_avg`。

**N4-056** BUY W 金额链为 `weekly_virt_amount >= monthly_avg_with_today >= prev_monthly_avg`。

**N4-057** BUY M 金额链为 `monthly_virt_amount >= quarterly_avg_with_today >= prev_quarterly_avg`。

**N4-058** BUY Q 金额链为 `quarterly_virt_amount >= yearly_avg_with_today >= prev_yearly_avg`。

**N4-059** BUY Y 金额链为 `true`。

**N4-060** SELL D 金额链为 `today_virt_amount <= weekly_avg_with_today <= prev_weekly_avg`。

**N4-061** SELL W 金额链为 `weekly_virt_amount <= monthly_avg_with_today <= prev_monthly_avg`。

**N4-062** SELL M 金额链为 `monthly_virt_amount <= quarterly_avg_with_today <= prev_quarterly_avg`。

**N4-063** SELL Q 金额链为 `quarterly_virt_amount <= yearly_avg_with_today <= prev_yearly_avg`。

**N4-064** SELL Y 金额链为 `true`。

**N4-065** N4 不自行计算这些链路字段；必须由 N2/N3 标准化提供，或作为 context/projection trace 本地化。

## 7. 普通 BUY

**N4-066** 普通 BUY 适用 `BUY:D` / `BUY:W,D` / `BUY:Y,Q,M,W,D`。

**N4-067** 普通 BUY 对 condition_key 中每个周期 P 独立判断。

**N4-068** 普通 BUY 周期 P 触发要求 P 在 condition_key 周期集合中。

**N4-069** 普通 BUY 周期 P 触发要求 `previous_transition[P] != volume_up`。

**N4-070** 普通 BUY 周期 P 触发要求 `current_transition[P] == volume_up`。

**N4-071** 普通 BUY 周期 P 触发要求 `transition_amount_pass[P] == true`。

**N4-072** 普通 BUY 周期 P 触发要求 `trigger_amount_chain_pass[P] == true`。

**N4-073** 普通 BUY 至少一个周期触发时输出 `event_type=TriggerMatched`。

**N4-074** 普通 BUY 至少一个周期触发时输出 `signal_type=B_BUY`。

**N4-075** 普通 BUY 至少一个周期触发时输出 `trigger_kind=trigger`。

**N4-076** 普通 BUY 至少一个周期触发时输出 `trigger_mark_candidate=normal`。

**N4-077** 普通 BUY 至少一个周期触发时输出 `current_status=matched`。

**N4-078** 普通 BUY 至少一个周期触发时输出 `trigger_live=true`。

**N4-079** 普通 BUY 至少一个周期触发时输出 `n5_entry_allowed=true`。

**N4-080** 普通 BUY 至少一个周期触发时输出 `triggered_periods=[本次触发周期]`。

**N4-081** 普通 BUY 至少一个周期触发时输出 `all_trigger_periods=[当日累计触发周期]`。

**N4-082** 普通 BUY 至少一个周期触发时输出 `primary_trigger_period=最高周期`。

**N4-083** 普通 BUY 至少一个周期触发时输出 `trigger_price=当前价格`。

**N4-084** 普通 BUY 无周期触发且证据完整时 outcome 为 `no_op`。

**N4-085** 普通 BUY 证据不足时 outcome 为 `pending_market_data`。

**N4-086** 普通 BUY 有质量问题时 outcome 为 `quality_blocked`。

## 8. 普通 SELL

**N4-087** 普通 SELL 适用 `SELL:D` / `SELL:M,W,D` / `SELL:Y,Q,M,W,D`。

**N4-088** 普通 SELL 对 condition_key 中每个周期 P 独立判断。

**N4-089** 普通 SELL 周期 P 触发要求 P 在 condition_key 周期集合中。

**N4-090** 普通 SELL 周期 P 触发要求 `previous_transition[P] != low_volume_down`。

**N4-091** 普通 SELL 周期 P 触发要求 `current_transition[P] == low_volume_down`。

**N4-092** 普通 SELL 周期 P 触发要求 `transition_amount_pass[P] == true`。

**N4-093** 普通 SELL 周期 P 触发要求 `trigger_amount_chain_pass[P] == true`。

**N4-094** 普通 SELL 至少一个周期触发时输出 `event_type=TriggerMatched`。

**N4-095** 普通 SELL 至少一个周期触发时输出 `signal_type=S_SELL`。

**N4-096** 普通 SELL 至少一个周期触发时输出 `trigger_kind=trigger`。

**N4-097** 普通 SELL 至少一个周期触发时输出 `trigger_mark_candidate=normal`。

**N4-098** 普通 SELL 至少一个周期触发时输出 `current_status=matched`。

**N4-099** 普通 SELL 至少一个周期触发时输出 `trigger_live=true`。

**N4-100** 普通 SELL 至少一个周期触发时输出 `n5_entry_allowed=true`。

**N4-101** 普通 SELL 至少一个周期触发时输出 `triggered_periods=[本次触发周期]`。

**N4-102** 普通 SELL 至少一个周期触发时输出 `all_trigger_periods=[当日累计触发周期]`。

**N4-103** 普通 SELL 至少一个周期触发时输出 `primary_trigger_period=最高周期`。

**N4-104** 普通 SELL 至少一个周期触发时输出 `trigger_price=当前价格`。

**N4-105** 普通 SELL 无周期触发且证据完整时 outcome 为 `no_op`。

**N4-106** 普通 SELL 证据不足时 outcome 为 `pending_market_data`。

**N4-107** 普通 SELL 有质量问题时 outcome 为 `quality_blocked`。

## 9. BUY:FULL

**N4-108** `BUY:FULL` 适用 `condition_key=BUY:FULL`。

**N4-109** `BUY:FULL` 必须由 N2 前置成立：context 中存在 `BUY:FULL`。

**N4-110** `BUY:FULL` 必须由 N2 前置成立：context `quality_status=passed`。

**N4-111** N4 不能自己发现 `BUY:FULL`。

**N4-112** `BUY:FULL` 触发要求 `current_transition[D] == volume_up`。

**N4-113** `BUY:FULL` 触发要求 `transition_amount_pass[D] == true`。

**N4-114** `BUY:FULL` 触发要求 `trigger_amount_chain_pass[D] == true`。

**N4-115** `BUY:FULL` 语义未明确前不得输出 `event_type=TriggerMatched`。

**N4-116** `BUY:FULL` 语义未明确前只保留 `signal_type=B_BUY` 作为 dry-run / quality trace。

**N4-117** `BUY:FULL` 语义未明确前只保留 `trigger_kind=trigger` 作为 dry-run / quality trace。

**N4-118** `BUY:FULL` 语义未明确前只保留 `trigger_mark_candidate=normal` 作为 dry-run / quality trace。

**N4-119** `BUY:FULL` 语义未明确前不得写正式 `triggered_periods` 到 `TriggerMatched`。

**N4-120** `BUY:FULL` 语义未明确前不得写正式 `all_trigger_periods` 到 `TriggerMatched`。

**N4-121** `BUY:FULL` 语义未明确前不得写正式 `primary_trigger_period` 到 `TriggerMatched`。

**N4-122** `BUY:FULL` 语义未明确前不得写 `trigger_live=true` 的正式 matched 事件。

**N4-123** `BUY:FULL` 语义未明确前必须保持 `n5_entry_allowed=false`。

## 10. SELL:FULL

**N4-124** `SELL:FULL` 适用 `condition_key=SELL:FULL`。

**N4-125** `SELL:FULL` 必须由 N2 前置成立：context 中存在 `SELL:FULL`。

**N4-126** `SELL:FULL` 必须由 N2 前置成立：context `quality_status=passed`。

**N4-127** N4 不能自己发现 `SELL:FULL`。

**N4-128** `SELL:FULL` 触发要求 `current_transition[D] == low_volume_down`。

**N4-129** `SELL:FULL` 触发要求 `transition_amount_pass[D] == true`。

**N4-130** `SELL:FULL` 触发要求 `trigger_amount_chain_pass[D] == true`。

**N4-131** `SELL:FULL` 语义未明确前不得输出 `event_type=TriggerMatched`。

**N4-132** `SELL:FULL` 语义未明确前只保留 `signal_type=S_SELL` 作为 dry-run / quality trace。

**N4-133** `SELL:FULL` 语义未明确前只保留 `trigger_kind=trigger` 作为 dry-run / quality trace。

**N4-134** `SELL:FULL` 语义未明确前只保留 `trigger_mark_candidate=normal` 作为 dry-run / quality trace。

**N4-135** `SELL:FULL` 语义未明确前不得写正式 `triggered_periods` 到 `TriggerMatched`。

**N4-136** `SELL:FULL` 语义未明确前不得写正式 `all_trigger_periods` 到 `TriggerMatched`。

**N4-137** `SELL:FULL` 语义未明确前不得写正式 `primary_trigger_period` 到 `TriggerMatched`。

**N4-138** `SELL:FULL` 语义未明确前不得写 `trigger_live=true` 的正式 matched 事件。

**N4-139** `SELL:FULL` 语义未明确前必须保持 `n5_entry_allowed=false`。

## 11. BUY_HINT

**N4-140** `BUY_HINT` 适用 `condition_key=BUY_HINT`。

**N4-141** `BUY_HINT` 必须由 N2 前置证明超跌结构。

**N4-142** `BUY_HINT` 必须在 context 中存在 `BUY_HINT`。

**N4-143** `BUY_HINT` context `quality_status=passed`。

**N4-144** N4 不重新证明超跌。

**N4-145** N4 只确认 N3 标准 30m 放量上涨 projection。

**N4-146** `BUY_HINT` 30m 放量上涨 projection 要求当前 30m bucket 虚拟额 > 昨日同 30m bucket 全额。

**N4-147** `BUY_HINT` 30m 放量上涨 projection 要求当前价 > 参考 30m 实体上沿。

**N4-148** `BUY_HINT` 30m 判断必须来自 N3 标准事实。

**N4-149** `BUY_HINT` 触发成立输出 `event_type=TriggerMatched`。

**N4-150** `BUY_HINT` 触发成立输出 `signal_type=B_BUY`。

**N4-151** `BUY_HINT` 触发成立输出 `trigger_kind=hint`。

**N4-152** `BUY_HINT` 触发成立输出 `condition_key=BUY_HINT`。

**N4-153** `BUY_HINT` 触发成立输出 `trigger_mark_candidate=30m_volume`。

**N4-154** `BUY_HINT` 触发成立输出 `projection_period=30m`。

**N4-155** `BUY_HINT` 触发成立输出 `projection_30m_flag=true`。

**N4-156** `BUY_HINT` 触发成立输出 `projection_30m_type=volume_up`。

**N4-157** `BUY_HINT` 触发成立输出 `triggered_periods=[]`。

**N4-158** `BUY_HINT` 触发成立输出 `all_trigger_periods=[]`。

**N4-159** `BUY_HINT` 触发成立输出 `primary_trigger_period=null`。

**N4-160** `BUY_HINT` 触发成立输出 `current_status=matched`。

**N4-161** `BUY_HINT` 触发成立输出 `trigger_live=true`。

**N4-162** `BUY_HINT` 触发成立输出 `n5_entry_allowed=true`。

**N4-163** `BUY_HINT` 缺证据时 outcome 为 `pending_market_data`。

**N4-164** `BUY_HINT` 证据完整但不满足时 outcome 为 `no_op`。

**N4-165** `BUY_HINT` 有质量问题时 outcome 为 `quality_blocked`。

## 12. SELL_HINT

**N4-166** `SELL_HINT` 适用 `condition_key=SELL_HINT`。

**N4-167** `SELL_HINT` 必须由 N2 前置证明超涨结构。

**N4-168** `SELL_HINT` 必须在 context 中存在 `SELL_HINT`。

**N4-169** `SELL_HINT` context `quality_status=passed`。

**N4-170** N4 不重新证明超涨。

**N4-171** N4 只确认 N3 标准 30m 缩量下跌 projection。

**N4-172** `SELL_HINT` 30m 缩量下跌 projection 要求当前 30m bucket 虚拟额 < 昨日同 30m bucket 全额。

**N4-173** `SELL_HINT` 30m 缩量下跌 projection 要求当前价 < 参考 30m 实体下沿。

**N4-174** `SELL_HINT` 30m 判断必须来自 N3 标准事实。

**N4-175** `SELL_HINT` 触发成立输出 `event_type=TriggerMatched`。

**N4-176** `SELL_HINT` 触发成立输出 `signal_type=S_SELL`。

**N4-177** `SELL_HINT` 触发成立输出 `trigger_kind=hint`。

**N4-178** `SELL_HINT` 触发成立输出 `condition_key=SELL_HINT`。

**N4-179** `SELL_HINT` 触发成立输出 `trigger_mark_candidate=30m_shrink`。

**N4-180** `SELL_HINT` 触发成立输出 `projection_period=30m`。

**N4-181** `SELL_HINT` 触发成立输出 `projection_30m_flag=true`。

**N4-182** `SELL_HINT` 触发成立输出 `projection_30m_type=shrink_down`。

**N4-183** `SELL_HINT` 触发成立输出 `triggered_periods=[]`。

**N4-184** `SELL_HINT` 触发成立输出 `all_trigger_periods=[]`。

**N4-185** `SELL_HINT` 触发成立输出 `primary_trigger_period=null`。

**N4-186** `SELL_HINT` 触发成立输出 `current_status=matched`。

**N4-187** `SELL_HINT` 触发成立输出 `trigger_live=true`。

**N4-188** `SELL_HINT` 触发成立输出 `n5_entry_allowed=true`。

**N4-189** `SELL_HINT` 缺证据时 outcome 为 `pending_market_data`。

**N4-190** `SELL_HINT` 证据完整但不满足时 outcome 为 `no_op`。

**N4-191** `SELL_HINT` 有质量问题时 outcome 为 `quality_blocked`。

## 13. Outcome 分类

**N4-192** `matched` 条件为至少一个正式周期触发，或 HINT 30m 标准确认成立。

**N4-193** `matched` 输出 `TriggerMatched`。

**N4-194** `matched` 输出 `TriggerStateChanged`。

**N4-195** `matched` 状态为 `current_status=matched`。

**N4-196** `matched` 状态为 `trigger_live=true`。

**N4-197** `matched` 状态为 `n5_entry_allowed=true`。

**N4-198** N5 可以消费 `matched` 的 `TriggerMatched`。

**N4-199** `pending_market_data` 条件为 N2 候选存在，但 N3 标准证据不足或尚未 ready。

**N4-200** `pending_market_data` 输出 `TriggerPendingMarketData`。

**N4-201** `pending_market_data` 输出 `TriggerStateChanged`。

**N4-202** `pending_market_data` 状态为 `current_status=pending_market_data`。

**N4-203** `pending_market_data` 状态为 `trigger_live=false`。

**N4-204** `pending_market_data` 状态为 `n5_entry_allowed=false`。

**N4-205** N5 不得对 `pending_market_data` 开始动作确认。

**N4-206** `no_op` 条件为证据完整但没有周期触发。

**N4-207** `no_op` 示例包括没有升级到 `volume_up`。

**N4-208** `no_op` 示例包括没有降级到 `low_volume_down`。

**N4-209** `no_op` 示例包括 `trigger_amount_chain_pass=false`。

**N4-210** `no_op` 示例包括 projection ready 但 HINT 不满足。

**N4-211** `no_op` 默认不写 `TriggerMatched`。

**N4-212** `no_op` 默认不写 `TriggerPendingMarketData`。

**N4-213** `no_op` 如果已有状态失效，则写 `TriggerStateChanged(current_status=inactive, trigger_live=false)`。

**N4-214** N5 对 `no_op` 无动作入口。

**N4-215** `quality_blocked` 条件包括 identity 冲突。

**N4-216** `quality_blocked` 条件包括 asset_kind 通道错配。

**N4-217** `quality_blocked` 条件包括 baseline 缺失。

**N4-218** `quality_blocked` 条件包括 `baseline_ready=false`。

**N4-219** `quality_blocked` 条件包括 amount source stale。

**N4-220** `quality_blocked` 条件包括 projection lineage mismatch。

**N4-221** `quality_blocked` 条件包括 projection quality failed。

**N4-222** `quality_blocked` 条件包括 source_run_id 不在 allowlist。

**N4-223** `quality_blocked` 条件包括 N2/N3 lineage 不一致。

**N4-224** `quality_blocked` 输出 quality item。

**N4-225** P0 `quality_blocked` 默认不写 N4 outbox。

**N4-226** P1/P2 `quality_blocked` 是否写 pending 必须由 contract 明确。

**N4-227** N5 不得对 `quality_blocked` 开始动作确认。

**N4-228** `inactive` 条件为已有 matched / pending 状态失效。

**N4-229** `inactive` 输出 `TriggerStateChanged`。

**N4-230** `inactive` 状态为 `current_status=inactive`。

**N4-231** `inactive` 状态为 `trigger_live=false`。

**N4-232** `inactive` 状态为 `n5_entry_allowed=false`。

## 14. N5 入口规则

**N4-233** N5 只允许消费 `event_type=TriggerMatched`。

**N4-234** N5 只允许消费 `signal_type=B_BUY / S_SELL`。

**N4-235** N5 只允许消费 `current_status=matched`。

**N4-236** N5 只允许消费 `trigger_live=true`。

**N4-237** N5 只允许消费 `n5_entry_allowed=true`。

**N4-238** N5 不得把 `TriggerPendingMarketData` 作为动作确认入口。

**N4-239** N5 不得把 `TriggerStateChanged` 作为动作确认入口。

**N4-240** N5 不得把 `quality_blocked` 作为动作确认入口。

**N4-241** N5 不得把 `no_op` 作为动作确认入口。

**N4-242** N5 不得把 `inactive` 作为动作确认入口。

**N4-243** 普通 trigger 和 hint 进入 N5 后规则一致。

**N4-244** 普通 trigger 和 hint 的差异只保留在 `trigger_kind`、`original_condition_key`、`trigger_mark_candidate`、`projection_30m_type`、trace。

## 15. Required Payload

**N4-245** N4 `TriggerMatched` / `TriggerPendingMarketData` payload 至少包含 `event_type`。

**N4-246** N4 `TriggerMatched` / `TriggerPendingMarketData` payload 至少包含 `run_id`。

**N4-247** N4 `TriggerMatched` / `TriggerPendingMarketData` payload 至少包含 `source_event_id`。

**N4-248** N4 `TriggerMatched` / `TriggerPendingMarketData` payload 至少包含 `source_event_type`。

**N4-249** N4 `TriggerMatched` / `TriggerPendingMarketData` payload 至少包含 `asset_kind`。

**N4-250** N4 `TriggerMatched` / `TriggerPendingMarketData` payload 至少包含 `identity_key`。

**N4-251** N4 `TriggerMatched` / `TriggerPendingMarketData` payload 至少包含 `direction`。

**N4-252** N4 `TriggerMatched` / `TriggerPendingMarketData` payload 至少包含 `signal_type`。

**N4-253** N4 `TriggerMatched` / `TriggerPendingMarketData` payload 至少包含 `trigger_kind`。

**N4-254** N4 `TriggerMatched` / `TriggerPendingMarketData` payload 至少包含 `condition_key`。

**N4-255** N4 `TriggerMatched` / `TriggerPendingMarketData` payload 至少包含 `original_condition_key`。

**N4-256** N4 `TriggerMatched` / `TriggerPendingMarketData` payload 至少包含 `trigger_live`。

**N4-257** N4 `TriggerMatched` / `TriggerPendingMarketData` payload 至少包含 `current_status`。

**N4-258** N4 `TriggerMatched` / `TriggerPendingMarketData` payload 至少包含 `n5_entry_allowed`。

**N4-259** N4 `TriggerMatched` / `TriggerPendingMarketData` payload 至少包含 `trigger_price`。

**N4-260** N4 `TriggerMatched` / `TriggerPendingMarketData` payload 至少包含 `trigger_time`。

**N4-261** N4 `TriggerMatched` / `TriggerPendingMarketData` payload 至少包含 `triggered_periods`。

**N4-262** N4 `TriggerMatched` / `TriggerPendingMarketData` payload 至少包含 `all_trigger_periods`。

**N4-263** N4 `TriggerMatched` / `TriggerPendingMarketData` payload 至少包含 `primary_trigger_period`。

**N4-264** N4 `TriggerMatched` / `TriggerPendingMarketData` payload 至少包含 `projection_period`。

**N4-265** N4 `TriggerMatched` / `TriggerPendingMarketData` payload 至少包含 `projection_30m_flag`。

**N4-266** N4 `TriggerMatched` / `TriggerPendingMarketData` payload 至少包含 `projection_30m_type`。

**N4-267** N4 `TriggerMatched` / `TriggerPendingMarketData` payload 至少包含 `trigger_mark_candidate`。

**N4-268** N4 `TriggerMatched` / `TriggerPendingMarketData` payload 至少包含 `data_quality_status`。

**N4-269** N4 `TriggerMatched` / `TriggerPendingMarketData` payload 至少包含 `match_basis`。

**N4-270** N4 `TriggerMatched` / `TriggerPendingMarketData` payload 至少包含 `source_condition_run_id`。

**N4-271** N4 `TriggerMatched` / `TriggerPendingMarketData` payload 至少包含 `source_market_data_run_id`。

**N4-272** N4 `TriggerMatched` / `TriggerPendingMarketData` payload 至少包含 `context_snapshot_id`。

**N4-273** N4 `TriggerMatched` / `TriggerPendingMarketData` payload 至少包含 `period_trigger_baseline_trace`。

**N4-274** N4 `TriggerMatched` / `TriggerPendingMarketData` payload 至少包含 `n3_trace`。

**N4-275** `triggered_period_details` 每个周期至少包含 `period`。

**N4-276** `triggered_period_details` 每个周期至少包含 `previous_transition`。

**N4-277** `triggered_period_details` 每个周期至少包含 `current_transition`。

**N4-278** `triggered_period_details` 每个周期至少包含 `previous_entity_high`。

**N4-279** `triggered_period_details` 每个周期至少包含 `previous_entity_low`。

**N4-280** `triggered_period_details` 每个周期至少包含 `current_price_or_close`。

**N4-281** `triggered_period_details` 每个周期至少包含 `current_amount_metric`。

**N4-282** `triggered_period_details` 每个周期至少包含 `previous_amount_baseline`。

**N4-283** `triggered_period_details` 每个周期至少包含 `transition_amount_pass`。

**N4-284** `triggered_period_details` 每个周期至少包含 `trigger_amount_chain_pass`。

**N4-285** `triggered_period_details` 每个周期至少包含 `amount_metric`。

**N4-286** `triggered_period_details` 每个周期至少包含 `source_field_trace`。

**N4-287** `TriggerStateChanged` payload 必须包含 `previous_trigger_live`。

**N4-288** `TriggerStateChanged` payload 必须包含 `previous_status`。

**N4-289** `TriggerStateChanged` payload 必须包含 `previous_triggered_periods`。

**N4-290** `TriggerStateChanged` payload 必须包含 `previous_all_trigger_periods`。

**N4-291** `TriggerStateChanged` payload 必须包含 `previous_primary_trigger_period`。

**N4-292** `TriggerStateChanged` payload 必须包含 `previous_trigger_mark_candidate`。

**N4-293** `TriggerStateChanged` payload 必须包含 `state_change_reason`。

**N4-294** `TriggerStateChanged` payload 必须包含 `source_outcome_event_id`。

**N4-295** `TriggerStateChanged` payload 必须包含 `source_outcome_event_type`。

## 16. N4 整改方案

### Stage 0: Spec Freeze

**N4-296** Stage 0 目标是冻结 N4 Trigger Rule Spec v4。

**N4-297** Stage 0 必须同步 `docs/V3_TRIGGER_ACTION_RUNTIME_SPEC.md`。

**N4-298** Stage 0 必须同步 `docs/N4_N5_TRIGGER_ACTION_STATE_FLOW_v0.1.md`。

**N4-299** Stage 0 必须新增 `docs/N4_TRIGGER_RULE_SPEC_v4.md`。

**N4-300** Stage 0 不改代码，不写 DB。

### Stage 1: Schema / Contract Impact Review

**N4-301** Stage 1 检查是否需要新增字段 `trigger_kind`。

**N4-302** Stage 1 检查是否需要新增字段 `n5_entry_allowed`。

**N4-303** Stage 1 检查是否需要新增字段 `triggered_periods`。

**N4-304** Stage 1 检查是否需要新增字段 `previous_triggered_periods`。

**N4-305** Stage 1 检查是否需要新增字段 `projection_period`。

**N4-306** Stage 1 检查是否需要新增字段 `triggered_period_details`。

**N4-307** Stage 1 检查是否需要新增字段 `outcome_classification`。

**N4-308** Stage 1 优先策略是先 raw_json 兼容。

**N4-309** Stage 1 必要时才使用 additive columns。

**N4-310** Stage 1 不改历史 rows。

**N4-311** Stage 1 不清洗 legacy artifacts。

**N4-312** Stage 1 输出 schema compatibility review。

**N4-313** Stage 1 如需要则输出 migration artifact。

**N4-314** Stage 1 输出 rollback plan。

### Stage 2: Context Readiness Review

**N4-315** Stage 2 确认 `trigger_context_snapshot` 是否已本地化 `previous_transition`。

**N4-316** Stage 2 确认 `trigger_context_snapshot` 是否已本地化 `period_trigger_baseline_json`。

**N4-317** Stage 2 确认 `trigger_context_snapshot` 是否已本地化 `previous_entity_high / low`。

**N4-318** Stage 2 确认 `trigger_context_snapshot` 是否已本地化 `amount_metric`。

**N4-319** Stage 2 确认 `trigger_context_snapshot` 是否已本地化 `trigger_amount_chain source fields`。

**N4-320** Stage 2 确认 `trigger_context_snapshot` 是否已本地化 N2 FULL 前置 trace。

**N4-321** Stage 2 确认 `trigger_context_snapshot` 是否已本地化 N2 HINT 前置 trace。

**N4-322** Stage 2 如果缺 N2 字段，输出 `blocked_by_layer=N2_condition`。

**N4-323** Stage 2 如果缺 N3 字段，输出 `blocked_by_layer=N3_market_data`。

**N4-324** Stage 2 N4 不补算缺失字段。

### Stage 3: Matcher Dry-Run Implementation

**N4-325** Stage 3 只改 dry-run，不 execute。

**N4-326** Stage 3 实现 ordinary BUY/SELL 逐周期 matcher。

**N4-327** Stage 3 实现 FULL blocked / trace matcher，不写 FULL `TriggerMatched`。

**N4-328** Stage 3 实现 HINT matcher with `trigger_kind=hint`。

**N4-329** Stage 3 实现 `outcome_classification`。

**N4-330** Stage 3 实现 `triggered_periods / details`。

**N4-331** Stage 3 实现 `no_op / quality_blocked`。

**N4-332** Stage 3 测试 `BUY:Y,Q,M,W,D` 只 W,D 触发。

**N4-333** Stage 3 测试 `primary_trigger_period=W`。

**N4-334** Stage 3 测试 BUY 无升级 -> `no_op`。

**N4-335** Stage 3 测试 SELL 降级 -> `matched`。

**N4-336** Stage 3 测试 FULL 无 N2 前置 -> `quality_blocked/no_op`。

**N4-337** Stage 3 测试 `BUY_HINT` projection 成立 -> `B_BUY + trigger_kind=hint`。

**N4-338** Stage 3 测试 `SELL_HINT` projection 成立 -> `S_SELL + trigger_kind=hint`。

**N4-339** Stage 3 测试 30m 不进入 `primary_trigger_period`。

### Stage 4: Execute Contract / Preflight Refresh

**N4-340** Stage 4 刷新 execute contract。

**N4-341** Stage 4 刷新 preflight。

**N4-342** Stage 4 刷新 rollback SQL。

**N4-343** Stage 4 刷新 event payload contract。

**N4-344** Stage 4 刷新 N5 entry contract。

**N4-345** Stage 4 必须确认 `TriggerMatched` only when `n5_entry_allowed=true`。

**N4-346** Stage 4 必须确认 `TriggerPendingMarketData n5_entry_allowed=false`。

**N4-347** Stage 4 必须确认 `TriggerStateChanged` not written to `common_trigger_match`。

**N4-348** Stage 4 必须确认 `no_op` does not create N5 entry。

**N4-349** Stage 4 必须确认 `quality_blocked` does not create N5 entry。

**N4-350** Stage 4 不 execute。

### Stage 5: Execute Runner Alignment

**N4-351** Stage 5 只对齐 runner，不执行。

**N4-352** Stage 5 更新写入 `common_trigger_state raw_json / columns`。

**N4-353** Stage 5 更新写入 `common_trigger_match raw_json / columns`。

**N4-354** Stage 5 更新写入 `common_event_outbox payload_json`。

**N4-355** Stage 5 确保 `trigger_kind` preserved。

**N4-356** Stage 5 确保 `n5_entry_allowed` preserved。

**N4-357** Stage 5 确保 `triggered_periods` preserved。

**N4-358** Stage 5 确保 `triggered_period_details` preserved。

**N4-359** Stage 5 确保 `projection_period` preserved。

**N4-360** Stage 5 测试 missing `--execute` blocked。

**N4-361** Stage 5 测试 missing `--user-confirmed` blocked。

**N4-362** Stage 5 测试 `TriggerMatched` payload includes v4 fields。

**N4-363** Stage 5 测试 `TriggerPendingMarketData n5_entry_allowed=false`。

**N4-364** Stage 5 测试 `no_op` not written as `TriggerMatched`。

**N4-365** Stage 5 测试 `quality_blocked` not written as `TriggerMatched`。

### Stage 6: Dry-Run Refresh

**N4-366** Stage 6 基于目标交易日重新 dry-run。

**N4-367** Stage 6 输出 `matched_count`。

**N4-368** Stage 6 输出 `pending_market_data_count`。

**N4-369** Stage 6 输出 `no_op_count`。

**N4-370** Stage 6 输出 `quality_blocked_count`。

**N4-371** Stage 6 输出 `triggered_period distribution`。

**N4-372** Stage 6 输出 `primary_trigger_period distribution`。

**N4-373** Stage 6 输出 `trigger_kind distribution`。

**N4-374** Stage 6 输出 `n5_entry_allowed count`。

**N4-375** Stage 6 输出 `anomaly count`。

### Stage 7: Final Gate / Execute

**N4-376** Stage 7 只有 runtime_control final gate PASS 后才允许执行。

**N4-377** Stage 7 只有用户明确授权 `--execute` 才允许执行。

**N4-378** Stage 7 只有用户明确授权 `--user-confirmed` 才允许执行。

**N4-379** Stage 7 execute 后 post-review 必须输出 row counts。

**N4-380** Stage 7 execute 后 post-review 必须输出 event distribution。

**N4-381** Stage 7 execute 后 post-review 必须输出 trigger_kind distribution。

**N4-382** Stage 7 execute 后 post-review 必须输出 n5_entry_allowed proof。

**N4-383** Stage 7 execute 后 post-review 必须输出 no invalid N5 entry。

**N4-384** Stage 7 execute 后 post-review 必须输出 rollback_safe。

**N4-385** Stage 7 不进入 N5/N6。

### Stage 8: N5 Contract Alignment

**N4-386** Stage 8 N5 只消费 `TriggerMatched`。

**N4-387** Stage 8 N5 只消费 `n5_entry_allowed=true`。

**N4-388** Stage 8 N5 只消费 `trigger_live=true`。

**N4-389** Stage 8 N5 只消费 `current_status=matched`。

**N4-390** Stage 8 N5 trace 保留 `trigger_kind`。

**N4-391** Stage 8 N5 trace 保留 `original_condition_key`。

**N4-392** Stage 8 N5 trace 保留 `trigger_mark_candidate`。

**N4-393** Stage 8 N5 trace 保留 `projection_30m_type`。

**N4-394** Stage 8 N5 trace 保留 `triggered_periods`。

**N4-395** Stage 8 N5 trace 保留 `primary_trigger_period`。

**N4-396** Stage 8 N5 不消费 `TriggerPendingMarketData`。

**N4-397** Stage 8 N5 不消费 `TriggerStateChanged`。

**N4-398** Stage 8 N5 不消费 `quality_blocked`。

**N4-399** Stage 8 N5 不消费 `no_op`。

**N4-400** Stage 8 N5 不消费 `inactive`。

## 17. Final Principle

**N4-401** N4 只输出标准买卖触发事实和标准触发事件。

**N4-402** 普通周期触发和 HINT 触发都统一为 `B_BUY / S_SELL`。

**N4-403** 普通周期触发和 HINT 触发的区别由 `trigger_kind`、`triggered_periods`、`trigger_mark_candidate`、`projection_30m_type` 和 trace 表达。

**N4-404** N4 只通过标准触发事件 payload / fact guard 决定是否允许进入 N5 动作确认。

**N4-405** N4 不决定最终 action eligibility、展示、语音、sim 或交易。
