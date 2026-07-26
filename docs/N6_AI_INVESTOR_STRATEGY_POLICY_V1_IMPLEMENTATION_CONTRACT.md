# N6 AI 投资员策略政策 V1 实现合同

```text
document_id=N6_AI_INVESTOR_STRATEGY_POLICY_V1_IMPLEMENTATION_CONTRACT
layer_role=N6_user
implementation_status=implemented_not_migrated
runtime_status=inactive
shadow_runtime_authorized=false
autonomous_trading_authorized=false
real_trading_authorized=false
highest_live_migration=058
candidate_migration=059
source_commit=2c01a08154a1292e70470df8d70d002916872e7c
policy_document_sha256=56082554c4f1099c9fa265d80f0233fde7459d2748be4c85f69fc198bddfc9e7
knowledge_bundle_version=N6_AI_KNOWLEDGE_BUNDLE_V3
knowledge_bundle_sha256=95098b11e8cc9296d243c54a8a7954aaf42f7fa4771f251b537522e1ff94332b
context_loader_bundle_sha256=1a873d69ef8f14e329b744460d549bcb3c35d99bb6af5fd10c16fc1a9dda15bc
promoted_knowledge_bundle_sha256=95098b11e8cc9296d243c54a8a7954aaf42f7fa4771f251b537522e1ff94332b
```

## 1. 状态与边界

本合同登记 059 的离线实现边界，不证明 migration 已执行、Shadow
LaunchAgent 已安装或生产策略已激活。当前 publishing、Shadow、
autonomous 和真实交易均保持 inactive。

059 只属于 N6。它遵守：

```text
no N1-N5 direct access to private/raw facts
shared common_trade_calendar is used only for the open-day fail-closed gate
no proposal/order/trade/position/cash DML in Shadow
no browser/model supplied price or quantity
no real broker or real trade
no runtime or LaunchAgent mutation in this implementation gate
```

生产激活必须通过 `separate future activation gate`。实现提交、059
migration、Shadow runtime、自治交易是四个独立 gate。

## 2. 新增关系

059 仅新增三张 N6 关系：

1. `n6_ai_position_strategy_episode`
   - 冻结 AI 自有账户、持仓、`holding_episode_no`；
   - 同一 episode 的 `locked_target_price`、来源、质量、
     `up_sell_reference_period` 和策略身份不可变；
   - `pending_clear` 只表示 059 策略 episode 的待续清状态，不修改
     `n6_virtual_position`。
2. `n6_ai_strategy_action`
   - action 仅为 `target_reduce`、`period_clear` 或
     `pending_clear_continue`；
   - 本版本只能写 `shadow_recorded`；
   - `execution_authorized=false` 是数据库约束，不是调用者提示；
   - 目标价减仓幂等边界为账户、持仓、episode、锁定目标价。
3. `n6_ai_candidate_rank_audit`
   - 保存财务分、HINT证据、membership证据、冲突归零和最终排序；
   - 每个 context snapshot 还保存一条
     `source_signal_projection_id=NULL / identity_key=NULL` 的唯一
     `strategy_workset_anchor`；该行不是候选，不计入 candidate count；
   - candidate/anchor 分类 `CHECK` 的完整 OR 表达式必须显式
     `IS TRUE`，不得让缺失 JSON key、NULL identity 或其他 PostgreSQL
     三值逻辑结果以 NULL 通过约束；
   - anchor 必须冻结
     `financial_score_raw=NULL / financial_rank_score=0 /
     score_status=missing`、四个 evidence/membership 数组均精确为 `[]`、
     两个 adjustment 均为 0、两个 conflict flag 均为 false、
     `candidate_qualified=false`，且 payload source 必须精确为
     `strategy_workset_anchor`、workset hash 必须为合法 64 位小写十六进制；
   - candidate 必须使用非 NULL source ID、非 NULL 且符合 SH/SZ stock
     regex 的 identity，并将 payload source 精确冻结为
     `approved_n6_strategy_context`；评分一致性继续由独立约束保证；
   - 不保存隐藏推理、prompt、凭据或真人私有数据。

## 3. 净化字段与来源

059 在 `n6_ai_shared_signal_projection` 上增加版本化字段：

```text
strategy_context_version
reference_target_price
target_quality_status
up_sell_reference_period
financial_score_raw
```

字段只从已通过 055 捕获边界的 N6 `user_signal_projection`
`display_payload_json` 和现有净化列复制。canonical 嵌套来源是
`display_payload_json.condition_projection_context.fields`；兼容的平铺
display 字段只能作为同一 N6 投影内的 fallback。它们不是 N2/N4/N5
裸事实，不得回写上游，也不得将缺失或失败质量解释为 `passed`。
目标价与财务分文本必须先同时通过格式检查和 PostgreSQL 16
`pg_input_is_valid(..., numeric(p,s))`，强转只能发生在已验证的 `CASE`
分支；超长或溢出数字一律净化为 NULL，不能中断 projection 写入或 059
历史回填。
059 每次读取 shared projection 时仍必须重新关联其
`user_projection_run_id`，且 run 必须同时满足
`source_layer=N5_action / status=passed /
quality_summary_json.b_track_signal_projection=passed`；`ready` 或 active
shared 行本身不能替代批准 run 证明。

059 strategy context 必须重新读取 058 已冻结 snapshot 的
`source_signal_projection_ids_json` 和 `workset_hash`。stock candidate、
index HINT 和 board HINT 的每一条 projection 都必须包含在该 source ID
数组中；相同 snapshot 重放不得吸收后来新增的 live projection。
context 返回的 `base_snapshot_workset_hash` 必须等于 058
`snapshot.workset_hash`；`strategy_workset_hash` 必须是下列确定性 JSONB
对象 canonical text 的 SHA-256：

```text
{
  base_snapshot_workset_hash,
  strategy_candidates
}
```

其中 `strategy_candidates` 按本合同固定全序聚合，HINT 与 membership
证据也按完整 JSONB 对象固定排序。evaluator 的 DB authority check 只能将
`snapshot.workset_hash` 与 `base_snapshot_workset_hash` 比较；
candidate audit 与成功返回继续保存 `strategy_workset_hash`。

HINT membership 使用：

```text
latest approved membership <= for_trade_date
```

来源仅限批准的 N6 `v_n6_index_membership_fact` 和
`v_n6_board_membership_fact`，按股票与 context identity 分组，选择不晚于
目标交易日的最新行。两类 membership 都必须先要求 stock identity 匹配
`^stock:(SH|SZ):[0-9]{6}$`；index identity 必须匹配
`^index:(SH|SZ):[0-9]{6}$`，board identity 必须非 NULL 且去除首尾空白后
非空。`created_at IS NULL` 以及 NULL/空白 `source_version` 同样拒绝；排名固定使用
`trade_date DESC NULLS LAST, created_at DESC NULLS LAST,
source_version DESC NULLS LAST`。如果同一
`(stock_identity_key, context_identity_key, trade_date, created_at,
source_version)` 仍有多行完全并列，则该 membership 作为歧义 lineage
fail-closed，不得进入 HINT 上下文。HINT evidence 与 membership evidence
分别按完整 JSONB 对象确定性排序后聚合，保证相同输入形成 byte-stable
冻结上下文。index/board 仍是 `context_only`，不能制造个股信号。

## 4. HINT V0

每个通道独立封顶：

```text
仅 BUY_HINT  = +1
仅 SELL_HINT = -1
BUY/SELL同时 = 0
无有效HINT   = 0
```

`condition_key` 与 `original_condition_key` 任一命中目标 HINT 才可作为
证据；如果另一字段同时命中相反 HINT，则该行冲突并拒绝，不得靠其中一个
alias 进入任一方向。

多个指数或板块不重复累加：

```text
hint_adjustment
= index_hint_adjustment + board_hint_adjustment

hint_adjustment in [-2,+2]
decision_rank_score
= financial_rank_score + hint_adjustment
```

财务 NULL 仅在 N6 排序上下文按 0 处理，同时保留
`score_status=missing`；非 NULL 值使用 `score_status=available`。
数据库中的 `decision_rank_score` 使用比输入财务分更宽的精度，保证
合法最大财务分再叠加 `+2` 也不会发生 typmod overflow。HINT 只调整
已经合格的 Shadow 买入候选排序，不产生交易授权，不改变预算、数量或
仓位。排序固定按
`decision_rank_score DESC, identity_key, source_signal_projection_id`
执行，确保相同冻结输入不受传入顺序影响。

## 5. 目标价减仓

目标价只能来自同一 episode 已冻结且质量为 `passed` 的
`reference_target_price`。到达条件必须是同 identity 的 fresh、passed、
有限、正数 N3N6Q 行情，且：

```text
current_price >= locked_target_price
```

evaluation、quote 和 fetched 时间必须同属目标交易日，并落在上海
`09:30–11:30` 或 `13:00–15:00` 交易时段；调用方提供的
`session_status` 不能替代服务端时间检查。

可卖数量权威来自同账户、同持仓、同 episode、`remaining_quantity > 0`、
`available_trade_date <= for_trade_date` 的成熟 lot。不得使用可能滞后的
position `available_quantity` 替代。

令 `S=server_sellable_quantity`：

```text
S >= 100:
  floor(S / 3 / 100) * 100
  下限100股，上限S

0 < S < 100:
  卖出全部S股零碎股
```

同一账户、持仓、episode、锁定目标价只能生成一次有效目标减仓审计。

## 6. 周期清仓与续清

仅当当前、active、passed 的净化股票 SELL message 满足：

```text
primary_trigger_period == up_sell_reference_period
```

才进入 `period_clear` 并设置 059 episode 的 `pending_clear=true`。
如果同一轮同时达到目标价与周期条件，固定使用
`period_clear_priority`，不另生成目标减仓。

周期清仓与后续续清遵守 T+1。对于当前成熟可卖数量：

```text
S >= 100:
  floor(server_sellable_quantity / 100) * 100

0 < S < 100:
  一次卖出 remaining 1..99 股
```

首轮或续清后仍有未成熟 lot 时继续保持 `pending_clear`。固定 one-shot
设计频率为开放交易日交易时段每 300 秒一次；非开放交易日和非交易时段
安全 no-op。`pending_clear=true` 时未来自治路径必须阻止同一 AI 账户再次
买入同一股票；即使 position 的数量字段暂时显示为零，也只能在下述
服务端归零证明完成并清除 episode 的 `pending_clear` 后解除。
Shadow 候选审计也必须使用相同 AI、账户、principal 与 identity 检查
当前 open episode，不得用当前 `strategy_id` 排除旧策略留下的待续清
episode；命中时保留候选审计行但写
`candidate_qualified=false /
qualification_reason=pending_clear_same_account_identity`，不得把被阻断候选
统计为合格买入候选。每轮必须先完成已经满足下述归零证明的 episode，
再处理持仓并写入本轮新产生的 pending-clear 状态，最后才冻结候选资格，
避免同一 context snapshot 留下不可变的陈旧阻断。
策略切换不能改变 episode 冻结的 `strategy_id`，也不能中断旧 episode
的续清或归零完成；续清 action 继续登记 episode 的原始 strategy，并在
审计中另记本轮 evaluator 的 active strategy。旧 episode 的
`pending_clear_source_signal_projection_id` 必须写入续清 action，不得
只留在不可反解的 idempotency hash 中。

归零完成只能由服务端同时证明：同账户、principal、股票、持仓和 episode
的 position 已为 `closed_virtual`，三类数量均为零、质量为 `passed`，
至少存在一条该 episode 的 lot，且全部 lot 身份匹配并满足
`remaining_quantity=0 / lot_status=closed`。059 one-shot 对 position
加共享锁后，只更新 059 episode 为 `pending_clear=false /
episode_status=closed` 并记录 `pending_clear_completed_at`；缺 lot、残余
数量、身份漂移或并发状态变化均不完成，也不修改 position 或 lot。
归零完成不依赖当前 active strategy 或当前 policy/hash；这些不可变字段
仍作为 episode 来源审计保留，但不得使已经严格证明归零的旧 episode
永久阻断同账户同股票。
离线回放还必须逐项绑定 positive `ai_user_id / strategy_id / principal_id /
virtual_account_id / virtual_position_id / holding_episode_no`、`ai_user`
principal type、SH/SZ stock identity、冻结 policy version/hash，并要求同
episode 的 `virtual_position_lot_id` 全部为正且唯一。

clear action 的幂等边界统一使用 `action_family=clear`，并绑定冻结的
成熟 lot 状态 hash；clear key 不包含交易日，因此相同 lot 状态跨日仍是
同一个幂等边界。相同 lot 状态下 `period_clear` 与
`pending_clear_continue` 不得形成重复有效审计；执行导致 lot 状态变化后，
下一 one-shot 才能形成新的续清审计。

## 7. Function-only 权限

AI role 继续保持零基础表、视图和序列权限。它只获得：

```text
public.n6_ai_strategy_shadow_evaluate(date,text,text)
```

三个参数固定为：

```text
for_trade_date
five_minute_run_bucket
policy_document_sha256
```

非交易时段由 runner 在连接数据库前安全 no-op；工作日但
`common_trade_calendar` 未登记为开放交易日时，服务端函数在加载 context
和任何 059 DML 前返回 `not_open_trade_date`，runner 回滚只读事务并作为
安全 no-op 记录。

函数内部加载批准的 N6 context、计算 HINT/排序、聚合成熟 lot、检查行情和
写入三张 059 审计关系。返回值必须明确证明：

```text
proposal_created=false
order_created=false
trade_created=false
position_mutated=false
cash_mutated=false
```

evaluator 必须重新证明 snapshot 对应的 strategy 属于同一 AI principal
且为 active，并在任何 059 DML 前以 `FOR UPDATE OF account` 锁定 AI
账户行。同账户的并发 evaluator 因此串行；锁定不授权修改账户、cash、
position 或 lot。账户锁定后、任何 completion/position/candidate 059 DML
前，evaluator 必须读取同一 `ai_context_snapshot_id` 已有 candidate audit
的 `audit_payload_json.strategy_workset_hash`。若任一历史 audit 的 hash
缺失、为 NULL、为空串或与本次 hash 不同，必须 fail-closed 返回
`reason=strategy_context_replay_drift`，全部 mutation flags 为 false，
且本次零 DML。若尚无历史 audit，或已有 audit 全部绑定相同 hash，
evaluator 必须在 completion、position、action 和 candidate DML 前先
`INSERT ... ON CONFLICT DO NOTHING` 固化唯一
`strategy_workset_anchor`。因此首次 0 候选也会留下 context 级 hash
锚点；之后相同 snapshot 的 live candidate/membership 变化会在任何新
059 DML 前被上述 drift guard 阻断。anchor 写入本身不增加
`candidate_rank_audit_count`。

058 已发布 context loader 仍以
`context_loader_bundle_sha256=1a873d69ef8f14e329b744460d549bcb3c35d99bb6af5fd10c16fc1a9dda15bc`
校验其冻结快照；059 策略结果、公开返回和 candidate audit 则绑定
`promoted_knowledge_bundle_sha256=95098b11e8cc9296d243c54a8a7954aaf42f7fa4771f251b537522e1ff94332b`。
两者不得互相冒充：candidate audit 的 `knowledge_bundle_hash` 保存 V3
晋级包，`audit_payload_json.context_knowledge_bundle_sha256` 保存本次
实际调用 058 context loader 的 hash。

内部 context helper 不授予 AI role。proposal/executor 函数只授予
`n6_virtual_executor`，但 `execution_activated=false`，因此始终返回
`strategy_execution_not_activated`。Web 与 PUBLIC 没有 059 执行权限。

059 postflight 必须以 effective privilege 和直接 ACL 双重证明下列精确
函数矩阵：

| 函数 | 唯一允许的受限角色 |
|---|---|
| `n6_ai_strategy_context_load_v1(text,date,integer,text)` | 无 |
| `n6_ai_strategy_shadow_evaluate(date,text,text)` | `n6_ai_agent` |
| `n6_ai_strategy_proposal_create_confirm_v1(jsonb)` | `n6_virtual_executor` |
| `n6_ai_executor_strategy_action_apply_v1(bigint,text)` | `n6_virtual_executor` |
| `n6_ai_shared_strategy_fields_capture_v1()` | 无 |
| `n6_ai_strategy_episode_locked_fields_immutable_v1()` | 无 |

PUBLIC 必须通过
`aclexplode(coalesce(proacl,acldefault('f',proowner)))` 证明没有 EXECUTE。
完整 ACL 展开后的 grantee allowlist 只能是函数 owner 加上矩阵中唯一允许的
角色；矩阵为“无”时只能出现 owner。允许角色只能拥有直接 EXECUTE 且
`is_grantable=false`，任何未知角色、其他 privilege 或 grant option 都必须
阻断，不能只检查三个已知受限角色。
对 `n6_ai_agent / n6_btrack_web / n6_virtual_executor`，允许项必须同时满足
`has_function_privilege(...,'EXECUTE')=true`、存在精确一条直接 EXECUTE
ACL 且 `is_grantable=false`；禁止项必须同时没有 effective/inherited
EXECUTE 和直接 EXECUTE ACL。任一函数、角色、合法 grant 缺失，出现错误
grant、PUBLIC grant 或 grant option 都必须阻断提交。

三张 059 表必须精确存在且 `relkind=r`。PUBLIC 权限必须用
`aclexplode(coalesce(relacl,acldefault('r',relowner)))` 展开验证；
完整表 ACL 的 grantee allowlist 只能包含 relation owner，任何其他 grantee
（包括未知角色和 PUBLIC）都必须阻断；
三个受限角色对每张表的
`SELECT/INSERT/UPDATE/DELETE/TRUNCATE/REFERENCES/TRIGGER` effective 权限
必须全部为 false。三条 identity sequence 必须精确存在且 `relkind=S`；
PUBLIC 权限必须使用 sequence 的
`acldefault('s',relowner)`，完整 sequence ACL 的 grantee allowlist 也只能
包含 relation owner；三个受限角色的 `USAGE/SELECT/UPDATE`
effective 权限必须全部为 false。对象、角色或任何一项权限证明缺失都必须
在 migration COMMIT 前 fail-closed。

Migration preflight 必须证明全部 059 表、序列、索引、列、约束、trigger
和函数均不存在，并证明将被替换的 055 projection trigger 与四个 proposal
约束仍为冻结基线；任何 partial apply、同名对象或 055 provenance 漂移都
必须在首个 DDL 前 fail-closed。

055 provenance 不能使用 `LIKE` / `ILIKE` 关键词匹配近似证明。Preflight
在首个 public DDL 前必须精确核验
`n6_ai_shared_signal_projection_capture()`：

- owner=`ashare_v3_user`、language=`plpgsql`、`prokind=f`、
  return=`trigger`、零参数、`VOLATILE`、`SECURITY DEFINER`；
- `proisstrict=false`、`proleakproof=false`、`proparallel=unsafe`；
- `proconfig` 精确为 `search_path=pg_catalog`；
- `prosrc` SHA-256 精确为
  `6bd08f39b6421840aaa95a8b1f7b6507bba402b5e3b18b499dfdeaa3ec2e1f04`。

对应 055 trigger 必须精确为 `user_signal_projection` 的 enabled ordinary
`AFTER INSERT FOR EACH ROW` trigger，`tgtype=5`，函数 OID 精确绑定上述
capture function，且无参数、列选择、WHEN、constraint/deferral、transition
table 或 parent trigger 状态。

四个 055 proposal CHECK 必须由事务内 `ON COMMIT DROP` 临时表复制 055
精确定义，并使用
`pg_get_constraintdef(actual_oid,false) IS DISTINCT FROM
pg_get_constraintdef(expected_oid,false)` 做逐约束比较。临时和实际目标集合
都必须精确为四项；实际约束还必须是 validated、local、non-inherited 的
CHECK。临时表在 preflight 成功路径内显式删除，然后才允许首个 public DDL。

## 8. Proposal兼容与未激活路径

`n6_virtual_trade_proposal.strategy_action_id` 是 nullable FK。新增 source
type 仅为：

```text
ai_target_reduce
ai_period_clear
ai_pending_clear
```

它们必须绑定 AI actor、AI自有持仓和 059 strategy action。059 Shadow
函数不插入 proposal；executor dormant 函数也不插入。未来 gate 必须再次
验证新鲜报价、T+1、episode、server quantity、pending_clear 和幂等边界，
才能用 `CREATE OR REPLACE` 激活。

## 9. Rollback

Rollback 在事务锁内检查：

- strategy proposal、order、trade 依赖必须为零；
- claimed/processing/proposal_created/executed action 必须为零；
- `pending_clear` 必须为零；
- 三张 059 表任意历史行存在都阻断。

Rollback 不 `DELETE` 或 `TRUNCATE` 业务历史。只有完全未使用的 059
schema 才能撤销；否则保留证据并停止。Rollback 恢复 055 proposal
constraint，保留 055–058、AI身份、账户、decision、summary及所有虚拟交易
历史。
