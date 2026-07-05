# N2 Web Policy Default / Execute Governance Plan

日期：2026-06-07
layer_role：`N2_condition`
review_target：`runtime_control`
状态：draft for 总控审核

## 1. 用户需求理解

用户希望在 8782 N2 条件层控制台完成一条闭环：

```text
调整筛选策略
-> Dry-run 预览
-> 保存为默认策略草案
-> 生成 N2 execute gate
-> 经总控审核
-> 明确确认 overwrite execute
-> 生成新的 active condition run
-> 以后每日默认 N2 execute 继续使用该新策略
```

核心诉求不是“只保存一个 JSON”，而是同时满足两件事：

```text
1. 当前生效：通过 overwrite execute 生成新的 active condition run。
2. 未来生效：把同一份策略作为后续每日 N2 runner 的默认 policy。
```

## 2. 当前实现事实

8782 控制台当前已有以下能力：

```text
Dry-run
保存为默认策略草案
生成 N2 execute gate
Overwrite 按钮占位 / disabled
```

当前默认策略草案路径：

```text
configs/n2_policy/default_policy_draft.json
```

N2 execute runner 当前策略解析规则：

```text
scripts/run_condition_layer_execute.py
```

如果执行时没有显式传入其他 `--policy`，runner 会优先读取：

```text
configs/n2_policy/default_policy_draft.json
```

因此：

```text
保存为默认策略草案 = 修改后续默认 N2 runner 的 policy 输入。
生成 N2 execute gate = 生成正式执行前的审查包和候选命令。
overwrite execute = 写新的 condition run，并让新 run 成为 active。
```

三者不能混为一步。

## 3. 生效语义

### 3.1 Dry-run

Dry-run 只读数据库并计算预览结果：

```text
writes_performed = false
database_written = false
active run 不变
默认策略草案不变
未来每日策略不变
```

Dry-run 的用途是确认：

```text
selected_count
excluded_count
reason_counts
selected_samples
excluded_samples
pool / scope rows
P0/P1/P2
N2-R4 baseline gate
```

### 3.2 保存为默认策略草案

保存为默认策略草案写入本地策略 artifact：

```text
configs/n2_policy/default_policy_draft.json
```

它的语义是：

```text
当前 active run 不变。
当前 N3/N4/N5/N6 lineage 不自动改变。
以后每日 N2 runner 若未显式传入其他 --policy，则默认读取该草案。
```

因此它只让“未来默认 policy 输入”发生变化，不让“当前 active condition run”立即变化。

### 3.3 生成 N2 execute gate

生成 N2 execute gate 会：

```text
先保存默认策略草案
运行当前策略 dry-run
生成 proposed_run_id
生成 expected rows
生成 rollback SQL
生成 execute command candidate
生成 gate JSON / Markdown artifact
```

它的语义是：

```text
gate_result = PASS / BLOCKED
execute_allowed_candidate = true / false
execute_authorized = false
writes_performed = false
database_written = false
```

生成 gate 仍不等于 execute。

### 3.4 overwrite execute

overwrite execute 是唯一会让当前策略成为新的 active condition run 的步骤。

执行必须发生在 `layer_role=N2_condition` 会话内，并且必须有用户明确确认。候选命令形态：

```bash
PYTHONPATH=src python3 scripts/run_condition_layer_execute.py \
  --source-trade-date <YYYYMMDD> \
  --policy configs/n2_policy/default_policy_draft.json \
  --run-id <proposed_run_id> \
  --execute \
  --user-confirmed \
  --overwrite \
  --operator <operator> \
  --confirmation-note <human_confirmation_note> \
  --report-path docs/<N2_execute_report>.json
```

overwrite execute 的语义：

```text
写新的 condition_basis / condition_pool / minute_target_scope / condition_display_basis。
同一 source_trade_date / for_trade_date 的旧 active run 在 postcheck 后标记 superseded。
新 run 成为 active。
不自动 rebuild N3 subscription。
不自动进入 N4/N5/N6。
不拉行情。
不启动 worker。
```

### 3.5 以后每日默认生效

保存草案后，只要未来每日 N2 execute 满足以下条件，新策略会继续生效：

```text
N2 每日任务使用 scripts/run_condition_layer_execute.py。
每日任务没有显式传入另一份 --policy 覆盖默认草案。
configs/n2_policy/default_policy_draft.json 没有被回滚、删除或再次保存为其他策略。
N1 source readiness passed。
N2 execute gate / manual confirmation 按当日 SOP 执行。
```

如果每日任务显式传入其他 `--policy`，则其他 policy 优先，默认草案不会生效。

## 4. 推荐审核状态机

建议总控把 N2 Web policy 发布拆成 5 个状态：

```text
DRAFT_EDITING
DRY_RUN_PASSED
DEFAULT_DRAFT_SAVED
EXECUTE_GATE_READY
WAIT_MANUAL_CONFIRM
EXECUTED_ACTIVE
```

状态含义：

| 状态 | 写数据库 | active run 变化 | 未来默认策略变化 | 总控动作 |
|---|---:|---:|---:|---|
| `DRAFT_EDITING` | no | no | no | 只看 UI 草案 |
| `DRY_RUN_PASSED` | no | no | no | 审核 reason_counts / P0 |
| `DEFAULT_DRAFT_SAVED` | no | no | yes | 登记 policy hash / diff |
| `EXECUTE_GATE_READY` | no | no | yes | 登记 command / rollback |
| `WAIT_MANUAL_CONFIRM` | no | no | yes | 等用户切换到 N2_condition 明确授权 |
| `EXECUTED_ACTIVE` | yes | yes | yes | post-review 登记 active run |

## 5. 总控审核清单

生成 gate 后，总控审核至少检查：

```text
policy_path = configs/n2_policy/default_policy_draft.json
policy_hash 与 gate hash 一致
policy_diff_summary 明确展示 index / board / stock 改动
source_trade_date 正确
proposed_run_id 正确
dry_run.ok = true
p0_count = 0
N2-R4 baseline gate passed
expected row counts 非空且合理
rollback_sql_path 已生成
execute_authorized = false
execute_command_candidate 只登记不执行
forbidden_scopes 覆盖 N3/N4/N5/N6、market_data_pull、worker、old_system
n3_lineage_auto_switch = false
```

人工确认 execute 前再检查：

```text
用户明确说允许 N2 overwrite execute。
当前会话 layer_role=N2_condition。
命令中的 --policy 指向 configs/n2_policy/default_policy_draft.json。
命令中的 --run-id 与 gate proposed_run_id 一致。
命令包含 --execute --user-confirmed --overwrite。
不会执行 N3/N4/N5/N6。
不会拉行情或分钟 K。
不会启动 worker。
```

execute 后 post-review 检查：

```text
new run status = passed_active
同一 source_trade_date / for_trade_date active run 唯一
previous active run = superseded
policy_hash matches saved default draft
condition_basis / condition_pool / minute_target_scope / condition_display_basis row counts match expected
P0 = 0
required_period_not_ready_rows = 0
outbox/inbox/checkpoint delta = 0/0/0
N3/N4/N5/N6 refs = 0/0/0/0 for new N2 run at execute time
market_data_pulled = false
worker_started = false
rollback_safe = true
```

## 6. 8782 UI 建议

为避免用户误解，建议后续把按钮和提示调整为：

```text
Dry-run
保存为以后每日默认策略草案
生成总控审核用 N2 execute gate
Overwrite 当前 active run
```

Overwrite 按钮保持 disabled，直到满足：

```text
latest gate exists
gate_result = PASS
gate policy_hash = current saved draft policy_hash
gate source_trade_date = 当前 active source_trade_date 或用户选择的待执行 source_trade_date
用户打开二次确认页
用户输入 proposed_run_id 或 policy_hash 确认
```

Overwrite 二次确认页必须展示：

```text
当前 active run_id
proposed_run_id
policy_version
policy_hash
policy_diff_summary
expected row counts
rollback_sql_path
明确说明 N3 不自动 rebuild
明确说明 N4/N5/N6 不自动重放
```

## 7. 数据与审计建议

当前 `common_condition_run` 表没有独立 `policy_hash` 列。为了总控更容易审核，建议后续至少在 execute report / run raw_json 中稳定记录：

```text
policy_source = 8782_console
policy_id = n2_default_policy
policy_version
policy_hash
previous_policy_hash
policy_diff_summary
policy_path
scope_delta_summary
n3_rebuild_required = true
n3_lineage_auto_switch = false
```

如果未来允许 schema migration，可再评估是否为 `common_condition_run` 增加 policy metadata 列。该项不是本方案的前置条件。

## 8. 边界

本方案不授权：

```text
直接执行 overwrite
执行 migration
写 N1 ingest 表
修 N1 fact
外拉 Tushare / mootdx / 实时行情
拉 1 分钟 K
进入 N3/N4/N5/N6
启动 worker
消费 outbox
写 voice / mobile / sim / real trade
触碰旧系统
```

本方案允许：

```text
生成 policy 草案
生成 dry-run 预览
生成 execute gate artifact
生成 rollback SQL artifact
把 command 登记给总控审核
在用户明确确认后，另行进入 N2_condition 执行 N2 overwrite
```

## 9. 风险与待总控确认

待确认项：

```text
1. 每日 N2 调度是否始终不显式传其他 --policy。
2. 保存草案是否需要总控登记 policy_version / policy_hash。
3. overwrite 按钮是否允许在 8782 内触发，还是只生成可复制命令。
4. execute 后是否自动生成 N3 subscription rebuild gate，默认建议只提示，不自动生成或执行。
5. 用户口径“个股 >= 90”具体字段是 min_score >= 90，还是其他评分/排名字段。
```

建议默认答案：

```text
8782 可以保存默认策略草案和生成 execute gate。
8782 不直接执行 overwrite，除非总控批准二次确认页和 N2_condition 明确授权机制。
N3 rebuild 只生成 next gate，不自动执行。
```

## 10. 审核结论模板

总控审核可使用以下结论模板：

```text
review_target=N2_web_policy_default_execute_governance
review_result=APPROVED / NEEDS_CHANGE / BLOCKED
approved_scope=
  - save default policy draft
  - generate N2 execute gate
  - register command and rollback path
  - optional N2 overwrite only after explicit N2_condition confirmation
blocked_scope=
  - automatic N3/N4/N5/N6 rebuild
  - market data pull
  - worker
  - outbox consumption
required_changes=...
next_layer_role=N2_condition / runtime_control
```
