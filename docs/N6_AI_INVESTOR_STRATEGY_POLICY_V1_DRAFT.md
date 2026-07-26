# N6 AI 投资员策略政策 V1（草稿）

```text
document_id=N6_AI_INVESTOR_STRATEGY_POLICY_V1
document_status=DRAFT
authority_status=SESSION_CONFIRMED_NOT_YET_PROMOTED
layer_role=N6_user
intended_path=docs/N6_AI_INVESTOR_STRATEGY_POLICY_V1_DRAFT.md
source_authority_commit=f03417c248d7931b2a797ab49c747be37a779330
current_research_bundle=N6_AI_KNOWLEDGE_BUNDLE_V2
current_research_bundle_sha256=565217fd5afb1eb95b0b9347a94d566713e136ff88009e14d8ed0908689e18b3
highest_migration=058
implementation_status=documented_not_active
autonomous_trading_authorized=false
real_trading_authorized=false
unresolved_semantic_count=0
```

## 1. 目的

本文冻结 N6 AI 投资员的候选策略语义，包括：

- 只能做多；
- 量价买卖信号的理解边界；
- 周期对称性及目标价候选；
- 财务综合分的候选排序用途；
- 目标价减仓；
- 周期匹配清仓；
- T+1和100股整手；
- 指数/板块 `BUY_HINT/SELL_HINT` 对个股决策评分的边界。

本文是候选策略草稿，不是运行授权、交易授权或数据库迁移合同。

权威来源：`[A1][A2][A3][A4][A5][U1]`

## 2. 非目标

本文不授权：

```text
修改N1–N5事实
重新计算N1财务指标
重新计算N2对称性目标价
直接读取N4/N5裸表
模型提交价格或数量
绕过T+1或100股规则
创建真实订单
连接真实券商
开启autonomous trading
启动或修改runtime
```

本文不证明策略已经写入代码、Shadow 已经采用或生产 runtime 已经激活。

权威来源：`[A1][A2][A4][A5][A7][A8]`

## 3. 市场和持仓方向

系统面向中国 A 股市场，只允许做多。

```text
BUY  = 建立或增加多头持仓
SELL = 减仓或清仓已有多头持仓
```

无持仓时，SELL 最多形成解释、观察或风险提示，不得产生负持仓。

AI 可交易身份只允许：

```text
stock:SH:NNNNNN
stock:SZ:NNNNNN
```

指数和板块不是可交易身份。

权威来源：`[A1][A2][A3][U1]`

## 4. N6信号输入边界

N6 不重新判断价格突破或成交额变化，不从展示文本、筛选结果、裸代码、指数或板块成员关系制造个股信号。

N6 的个股交易决策入口必须来自：

```text
当前开放交易日
+ active
+ passed
+ 经过净化的N5_action来源shared stock signal
+ exchange-qualified SH/SZ stock identity
```

N5 `ActionExecuted` 只表示动作确认事实成立，不代表已经下单、成交、写入模拟持仓或完成N6展示。

权威来源：`[A1][A2][A4][A5][A6][A8]`

## 5. 量价基础假设

### 5.1 周期集合

量价判断按以下五个正式周期分别进行：

```text
Y > Q > M > W > D
```

### 5.2 上涨

对周期 `P`：

```text
current_price_or_close
> previous_period_entity_high[P]
```

表示价格突破上一周期K线实体上沿。

如果同时：

```text
current_period_avg_with_today[P]
> previous_avg_amount[P]
```

则为：

```text
volume_up
```

即放量上涨。

如果价格突破实体上沿，但：

```text
current_period_avg_with_today[P]
< previous_avg_amount[P]
```

则为：

```text
low_volume_up
```

即缩量上涨。

### 5.3 下跌

上涨方向完全对称。

```text
current_price_or_close
< previous_period_entity_low[P]
```

表示价格跌破上一周期K线实体下沿。

如果同时：

```text
current_period_avg_with_today[P]
< previous_avg_amount[P]
```

则为：

```text
low_volume_down
```

即缩量下跌。

如果价格跌破实体下沿，但：

```text
current_period_avg_with_today[P]
> previous_avg_amount[P]
```

则为：

```text
volume_down
```

即放量下跌。

### 5.4 当前周期平均成交额

当前周期无需等待周期结束。

例如本周只完成三个交易日：

```text
本周当前平均成交额
= 本周已完成三个交易日的成交额之和 / 3
```

再与上一完整周的平均成交额比较。

使用成交额 `amount`，不是成交股数 `volume`。

### 5.5 严格比较

只有严格大于才算放量，严格小于才算缩量。

成交额相等、价格未突破实体边界、字段缺失或质量不通过时，N4 归入 `other/not_ready`，不得形成相应正式买卖触发。

### 5.6 正式触发含义

普通 BUY 和 BUY:FULL 的正式 N4 匹配必须包含放量上涨证明。

普通 SELL 和 SELL:FULL 的正式 N4 匹配必须包含缩量下跌证明。

N6 只消费已通过 N5 标准确认的消息，不重新计算本节公式。

权威来源：`[A4][A9][A10][A13][U1]`

## 6. 周期对称性

### 6.1 N2所有权

以下字段只由 N2 根据截至 `source_trade_date` 的 N1 官方日线计算并冻结：

```text
main_up_anchor
up_reference_period
up_amplitude
reference_target_price
secondary_target_price
up_sell_reference_period

main_down_anchor
down_reference_period
down_amplitude
down_buy_reference_period
```

N4/N5可以透传，不得重算、锁定或决定清仓策略。

N6/position 可以解释目标候选、锁定持仓目标并维护清仓策略，但不得回写N2/N4/N5。

### 6.2 上涨侧

从 `Y → Q → M → W` 扫描连续 `volume_up` 结构，取该连续结构中最细周期作为：

```text
main_up_anchor
```

参考周期固定下移一级：

```text
Y → Q
Q → M
M → W
W → D
```

在 `main_up_anchor` 自身聚合周期识别当前连续上涨A段。

```text
up_amplitude
= A段调整后最高实体边界
- A段调整后最低实体边界
```

实体边界：

```text
upper = max(open, close)
lower = min(open, close)
```

个股历史实体价格按当前复权基准归一。

在 `up_reference_period` 找最近结束的上涨段，从其结束后的下一交易日至 `source_trade_date` 建立基准窗口：

```text
up_base_price
= 基准窗口内min(close)

reference_target_price
= up_base_price + up_amplitude
```

### 6.3 下跌侧

下跌侧按连续 `low_volume_down` 对称计算：

```text
down_amplitude
= A段调整后最高实体边界
- A段调整后最低实体边界

down_base_price
= 基准窗口内max(close)

reference_target_price
= down_base_price - down_amplitude
```

在只能做多的系统中，下跌侧目标候选是未来观察或再买入参考，不是做空获利目标。

### 6.4 目标价性质

N2目标价是静态候选：

```text
不是实时行情
不是成交价
不是保证价格
不是模型可提交价格
不是自动交易授权
```

N6/position 锁定为 `locked_target_price` 后，才允许进入持仓目标策略。

### 6.5 对称性是否为每笔买入的硬门槛

对称性目标价不是买入硬门槛。买入资格仍由正式N5信号、行情质量、账户、现金、T+1、敞口和服务器风险规则决定。

仅当 `reference_target_price` 存在且 `quality_status=passed` 时，N6才可在建仓时将其锁定为：

```text
locked_target_price = reference_target_price
```

该锁定值在同一 `holding_episode` 内保持不变；缺失或quality不通过时，只表示该持仓没有目标价参考，不得将其解释为可买、不可买、自动卖出或交易授权。

权威来源：`[A3][A4][A11][A13][U1]`

## 7. 财务综合分

### 7.1 来源

财务字段由 N1 canonical financial metrics 计算。

N6只读取结果，不重新计算：

```text
report_core_profit
cash_realization_rate
core_profit_ttm
pe_core
revenue_yoy_pct
core_profit_yoy_pct
core_gt_revenue_yoy
revenue_growth_streak_q
core_growth_streak_q
core_gt_revenue_streak_q
score
```

只采用：

```text
announcement_date <= source_trade_date
```

的已公告数据。

`core_profit_ttm` 是最近连续四个单季度 `report_core_profit` 之和，不是相减。

### 7.2 排序用途

三个基础假设和正式N5信号决定是否具备买卖资格。

当同一时点合格买入候选较多时，财务分数只用于买入候选排序：

```text
financial_rank_score
= COALESCE(score, 0)
```

排序：

```text
financial_rank_score DESC
```

### 7.3 NULL语义

N1原始事实必须保留：

```text
score=NULL
```

不得把上游NULL静默改写成0。

只允许在N6排序上下文中按0处理：

```text
score=NULL
→ financial_rank_score=0
→ score_status=missing
```

`score=0` 与 `score=NULL` 排序权重相同，但审计和解释含义不同。

### 7.4 禁止解释

财务分数：

```text
不是买入信号
不是概率
不是预期收益率
不是成交授权
不是仓位大小
```

高分不得：

- 把无信号股票变成买入；
- 绕过行情质量和新鲜度；
- 绕过现金、敞口、T+1或风险规则；
- 阻止有效SELL、止损、周期清仓或风险清算；
- 直接扩大买入资金。

现阶段所有候选继续使用相同的服务器端预算和风险规则。

权威来源：`[A1][A2][A3][A8][A12][U1]`

## 8. 目标价减仓

### 8.1 适用范围

只适用于AI自有、正数量、未关闭的SH/SZ虚拟多头持仓。

模型不得提交价格或数量。

价格必须由N6服务器使用身份匹配、有限、正数、fresh、passed的N3N6Q报价判断。

### 8.2 可卖数量

本策略中的 `available_quantity` 必须解释为：

```text
server_sellable_quantity
= 同一virtual_account
+ 同一virtual_position
+ 同一holding_episode
+ remaining_quantity > 0
+ available_trade_date <= current_trade_date
+ lot_status允许出售
的成熟lot数量之和
```

不得把可能滞后的 `n6_virtual_position.available_quantity` 列作为跨日卖出权威。

### 8.3 触发条件

目标价到达的服务器端定义为：

```text
fresh
+ passed
+ N3N6Q quote
+ quote.identity_key与持仓一致
+ quote.current_price >= locked_target_price
```

不要求证明首次穿越；持续满足条件不得突破同一目标价减仓的幂等边界。

### 8.4 数量

设：

```text
S = server_sellable_quantity
```

当 `S >= 100`：

```text
base_reduce_quantity
= floor(S / 3 / 100) * 100

target_reduce_quantity
= min(
    S,
    max(100, base_reduce_quantity)
  )
```

示例：

```text
S=100  → 100
S=200  → 100
S=300  → 100
S=600  → 200
S=1000 → 300
```

当 `0 < S < 100` 时，允许一次性卖出全部 `S` 股零碎股；该例外只适用于服务器确认的可卖数量，不得绕过T+1、身份、报价质量或持仓episode边界。

### 8.5 幂等

同一：

```text
virtual_account_id
+ virtual_position_id
+ holding_episode_no
+ locked_target_price
```

只允许成功执行一次目标价减仓。

价格持续高于目标价时不得重复减仓。

目标价变化是否允许形成新的减仓episode，必须由独立策略版本明确，不得隐式触发。

### 8.6 与清仓的关系

目标价减仓与周期清仓相互独立。

周期清仓不要求此前已经达到目标价或完成1/3减仓。

权威来源：`[A1][A2][A3][A7][A8][U1]`

## 9. 周期清仓

### 9.1 输入

清仓判断只读取当前、passed、N5_action来源的净化卖方向消息和N6自有持仓。

N6不直接查询N4 trigger裸表。

### 9.2 周期匹配

```text
N5 sell message.primary_trigger_period
== position.up_sell_reference_period
```

时，N6可以进入清仓策略。

比较字段是：

```text
up_sell_reference_period
```

不是：

```text
up_reference_period
```

`clear_sell_ref_period` 仅为兼容别名，必须等于 `up_sell_reference_period`。

### 9.3 独立性

以下两条规则独立：

```text
达到锁定目标价 → 目标价减仓
周期精确匹配   → 清仓
```

即使未达到目标价，只要卖出消息和周期清仓条件成立，也可以进入清仓。

### 9.4 pending_clear

进入清仓策略后：

```text
pending_clear=true
```

服务器卖出当前全部 `server_sellable_quantity`。

T+1未成熟lot不得卖出。只要仍有未成熟持仓，`pending_clear`保持有效。

固定 one-shot 在开放交易日的交易时段每300秒检查一次；当原episode的未成熟lot变为成熟时，它自动续清该部分，无须新的SELL信号。其他日期或时段安全no-op。

`pending_clear=true` 期间，同一AI账户不得再次买入同一 `identity_key`，直至旧 `holding_episode` 完全清仓。持仓总数量归零后，清仓完成。

`pending_clear` 的物理字段、状态表、one-shot实现和幂等键均为 documented_not_active；本草稿冻结业务语义，不声称已有schema或runtime实现。

权威来源：`[A3][A4][A5][A6][A8][U1]`

## 10. T+1和整手

T+1与100股规则始终高于候选策略。

```text
available_trade_date > current_trade_date
→ 不可卖
```

目标价减仓、周期清仓、HINT、模型信心或用户解释均不得绕过该限制。

目标价减仓和清仓的数量规则收口为：

```text
server_sellable_quantity >= 100
→ 目标价减仓按100股整手计算

0 < server_sellable_quantity < 100
→ 允许一次性卖出全部服务器确认的零碎股
```

零碎股例外不得绕过T+1、holding_episode、身份、报价质量或幂等边界。清仓时应卖出服务器当前确认的成熟lot数量；未成熟部分保留，不得形成负持仓。

模型、浏览器和研究室不得提交或覆盖数量。

权威来源：`[A1][A2][A3][A8][U1]`

## 11. BUY_HINT/SELL_HINT边界

### 11.1 资产范围

正式 `BUY_HINT/SELL_HINT` 只适用于：

```text
index
board
```

不对个股生成正式N4 HINT触发。

### 11.2 交易权限

指数和板块是 `context_only`：

```text
不能交易
不能制造个股shared signal
不能替代个股当前交易日买卖信号
不能单独创建proposal
```

### 11.3 对个股的影响

用户已确认：

```text
指数/板块BUY_HINT/SELL_HINT
→ 调整个股决策评分
→ 不提供交易授权
```

HINT评分V0固定为：

| 通道 | 仅BUY_HINT有效 | 仅SELL_HINT有效 | BUY_HINT与SELL_HINT同时有效 | 无有效HINT |
|---|---:|---:|---:|---:|
| index | +1 | -1 | 0 | 0 |
| board | +1 | -1 | 0 | 0 |

多指数或多板块不按数量重复累加；每个通道最多贡献一次。每个HINT只有同时满足以下全部条件时才有效：

```text
与当前个股存在批准的index/board membership
+ for_trade_date等于当前目标交易日
+ status=active
+ quality/status=passed
+ 来源为批准的N6 index/board上下文
```

N6不得读取N1–N5裸表或自行推导HINT。总调整及排序公式固定为：

```text
hint_adjustment
= index_hint_adjustment
+ board_hint_adjustment

hint_adjustment ∈ [-2, +2]
decision_rank_score = financial_rank_score + hint_adjustment
```

Shadow中已经合格的买入候选按 `decision_rank_score DESC` 排序。该调整不制造个股信号、不提供交易授权、不改变资金或仓位，也不影响SELL、止损、目标价减仓、周期清仓或风险清算；不进入autonomous。生产排序继续使用未调整的 `financial_rank_score`。

### 11.4 已知文档差异

当前 `V3_CONDITION_LAYER_DEVELOPMENT_DESIGN.md` 仍存在“HINT覆盖个股”的旧文字。

最新 `AGENTS.md` 和N4 atomic rule规定：

```text
BUY_HINT/SELL_HINT只适用于index/board
stock is not applicable
```

本草稿采用最新AGENTS、N4 atomic rule和用户本会话确认的index/board-only规则。旧N2文档必须通过独立对齐gate修正，不能静默改写历史证据。

权威来源：`[A1][A2][A9][A10][A13][U1]`

## 12. 候选决策顺序

当前已确认的决策顺序为：

```text
1. 当前交易日和exchange-qualified身份有效
2. 当前、active、passed的N5来源shared stock signal存在
3. 行情质量、新鲜度和身份匹配通过
4. 账户、持仓、现金、T+1、敞口和风险规则通过
5. 生产候选买入股票较多时，按financial_rank_score DESC排序
6. Shadow候选按decision_rank_score DESC排序；该分数只适用于已经合格的买入候选
7. 价格和数量由服务器决定
```

卖出、止损、周期清仓和风险清算不得因财务高分而被延迟或取消。

同分候选在策略语义上等价；任何实现级稳定排序不得改变资格、资金、仓位或交易授权。

权威来源：`[A1][A2][A3][A8][U1]`

## 13. 审计要求

每项候选决策必须保留：

```text
identity_key
for_trade_date
direction
source_signal_projection_id
source_virtual_position_id
financial_score_raw
financial_rank_score
score_status
approved index/board context references
index_hint_evidence_refs
board_hint_evidence_refs
index_hint_adjustment
board_hint_adjustment
index_hint_conflict_zeroed
board_hint_conflict_zeroed
hint_adjustment
decision_rank_score
membership引用
HINT for_trade_date
HINT quality/status
evidence
counter_evidence
reason_summary
strategy_version
strategy_hash
knowledge_bundle_version
knowledge_bundle_hash
```

隐藏推理、原始prompt、凭据和真人私有数据不得保存。

新策略不得自行晋级。正式晋级至少需要：

```text
确定性历史回放
不少于10个开放交易日Shadow观察
管理员明确批准
新版本Git知识包
独立runtime activation gate
```

权威来源：`[A1][A2][A3]`

## 14. 当前状态

```text
knowledge_status=draft_only
code_implemented=false
schema_implemented=false
shadow_adopted=false
autonomous_authorized=false
real_trade_authorized=false
runtime_changed=false
```

本文被写入Git并加入Manifest，也只表示语义知识已版本化，不表示执行逻辑已经实现或激活。

权威来源：`[A0][A1][A2][A16]`

## 附录A：权威来源

| ID | 来源 | SHA256 | 用途 |
|---|---|---|---|
| A0 | `docs/N6_AI_KNOWLEDGE_BUNDLE_MANIFEST.json` | `2ff08080b17c2aabaa36494bbf8608629082fd34730955ac0e4affc9cf174f5f` | V2知识包边界 |
| A1 | `docs/N6_AI_AGENT_V1_SYSTEM_GUIDE.md` | `8f6ac5741a343a9ee72e9f755bf724f963d01e94e95030c3b6d30d0af1e65ffb` | AI读取、报价、T+1、模型边界 |
| A2 | `docs/N6_AI_AGENT_V1_CONTRACT.json` | `038099b3695b1f7e6a17ac016dd44fc9bf4e7d5f30d6edd1ed54184db17de452` | 模型输出、风险和proposal合同 |
| A3 | `docs/N6_AI_APPROVED_FIELD_DICTIONARY_V1.json` | `41bca8878d011580b7c06ac0d09e4c82bc5772964e46f1e169d96579392e927b` | 批准字段及禁止解释 |
| A4 | `docs/V3_TRIGGER_ACTION_RUNTIME_SPEC.md` | `8210da0e06e4b316488f209135643c7e5fb03893c03c5931b410373f4b8ec499` | N4/N5/N6 runtime边界 |
| A5 | `docs/N4_N5_TRIGGER_ACTION_STATE_FLOW_v0.1.md` | `6a22383b16e26d84863a1762c0831619eb6e3fbb021e2e6c61e49b3d82632635` | primary period和状态流 |
| A6 | `docs/N5_CANONICAL_ACTION_FLOW_v0.1.md` | `c4e3912290e77dafc0d564dc27da57b5a78988e841257db5c9e6c7b6ec2a4de5` | N5消息与ActionExecuted语义 |
| A7 | `docs/N3N6Q_FOR_N6_VIRTUAL_ACCOUNT_QUOTE_CONTRACT.md` | `0904ff58fd304274212837e152a9f506dc3437565c3a4f76cbd2dc876289f6b7` | N6成交报价边界 |
| A8 | `docs/N6_B_TRACK_PRODUCT_V3_PROPOSAL_SCOPE_AND_EXECUTOR_CLAIM_NEXT_048_CONTRACT.md` | `cbe0e1c8990af9d8925ece6155adcbc15e489efaaebc8f269d8f60d095ab1b78` | lot成熟度与executor权限 |
| A9 | `/Users/chuanfuchen/Documents/A股监控系统v3/AGENTS.md` | `a97cd439581d1ebf4d85e2c747863460f38a160ea2b4716e8f2fd3c7b342feef` | 最新项目级canonical规则 |
| A10 | `/Users/chuanfuchen/Documents/A股监控系统v3/docs/N4_TRIGGER_RULE_SPEC_ATOMIC_REVISED.md` | `363fd46a77b8149e53d5fbd89441efb2140b8316e915f8872824f65713f2e717` | 严格量价和HINT资产范围 |
| A11 | `/Users/chuanfuchen/Documents/A股监控系统v3/docs/V3_SYMMETRY_TARGET_PRICE_SPEC.md` | `972667c3e98586098ca4de783133b22da2eb5adbf26a79df68a45d53b18291fd` | 对称性目标价 |
| A12 | `/Users/chuanfuchen/Documents/A股监控系统v3/src/ashare_v3/ingestion/stock_financial_canonical_metrics.py` | `cade6793cd46e387b6c95a15bfe0d5c2b1219bc8d54344932218107d818a467c` | 财务公式与score |
| A13 | `/Users/chuanfuchen/Documents/A股监控系统v3/docs/V3_CONDITION_LAYER_DEVELOPMENT_DESIGN.md` | `84439cdf653142b201fd6bfa0ea7ad67d90804ebe6954815bda5c0a5a69084e2` | N2条件与已知HINT差异 |
| A14 | `docs/N6_MULTI_USER_AND_AI_ARCHITECTURE_v1.md` | `2f4b7d58ec5afe1a1815df4217429a2ab0954956b478685181bc6e53586d8e91` | AI/用户/账户所有权 |
| A15 | `docs/N6_PROJECTION_CONTRACT.md` | `3b97a2b5f2544810803a45b29059855a7912855a3cf0fbdd9b60099eea36bd5a` | N6净化投影边界 |
| A16 | `docs/N6_AI_AGENT_V1_055_058_RUNTIME_ACTIVATION_CLOSEOUT.json` | `6f9a6fff15b59ce072b046dfb9035ea91945ba5cb7537aee7d0b993bf27cb227` | 055–058历史激活证据 |
| U1 | 本会话用户逐项确认 | `NO_GIT_HASH` | 新增策略语义，尚未晋级 |

## 附录B：来源优先级

```text
最新AGENTS及专门canonical spec
> Git V2正式AI合同/指南/字段字典
> 当前实现代码及已审核N6合同
> 本会话用户确认的新候选策略
> 历史报告和旧文档
> Obsidian V1/054镜像
```

本会话新增策略在管理员审核并进入新版Git Manifest前，不具有正式生产知识主权。
