# N6 Active Checkout LaunchAgent Auto Hot Execution Control Event Registration

登记日期：2026-07-15
登记时间：2026-07-15T14:20:17+08:00
layer_role：`runtime_control`
gate：`N6_ACTIVE_CHECKOUT_LAUNCHAGENT_AUTO_HOT_EXECUTION_CONTROL_EVENT_REGISTRATION_GATE`

## 1. 登记结论

```text
FINAL_VERDICT=BLOCKED_N6_PROJECTION_MESSAGE_NOT_READY_FAIL_CLOSED_RUNTIME_CONTROL_PREFLIGHT_ALREADY_AUTO_EXECUTED
LIVE_FUNCTIONAL_POSTCHECK=PASS
```

本事件不是 N6 fail-closed 功能失败，而是发布控制面失败：一个已经 loaded 的 LaunchAgent
以 3 秒间隔直接执行 mutable active checkout 中的相对脚本路径，并携带
`--execute --user-confirmed`。因此修复代码在 commit、最终 POST_REVIEW 和预期
runtime_control preflight 之前已经进入真实 N6 写路径。

正常的：

```text
isolated development
-> review
-> commit
-> runtime_control preflight
-> explicit canary authorization
-> promotion / reactivation
```

顺序已经被 active checkout auto hot execution 越过。本修复不得再登记为
`canary-ready`，也不得追加手工 canary、reload、replay 或 backfill。

## 2. 控制面事件身份

| 字段 | 登记值 |
|---|---|
| LaunchAgent label | `com.ashare-v3.n6.b-track-signal-poller` |
| plist | `/Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n6.b-track-signal-poller.plist` |
| StartInterval | `3` 秒 |
| WorkingDirectory | `/Users/chuanfuchen/Documents/A股监控系统v3` |
| runner | `scripts/run_n6_b_track_signal_projection_poller_once.py` |
| execute flags | `--execute --user-confirmed` |
| report | `tmp/N6_b_track_signal_projection_poller_launchd_report.json` |
| history | `tmp/N6_b_track_signal_projection_poller_history.jsonl` |
| stderr | `tmp/com.ashare-v3.n6.b-track-signal-poller.err.log` |
| active branch | `codex/new-demand-n2-n5-20260710` |
| repair commit | `7c209394786c4d5810c00de34baaffe4f86beb4b` |
| repair parent | `81647fdecad551a02bb079ff6ecf9ce00958b8bf` |
| repair commit time | `2026-07-15T14:00:58+08:00` |

本 gate 只读观察时，LaunchAgent 仍 loaded；`launchctl print` 显示间隔态
`state=not running`、`runs=92756`、`last exit code=0`。`not running` 仅表示两次
3 秒调度之间当前没有子进程，不表示 LaunchAgent 已隔离或卸载。

## 3. 自动执行时间线

| 时间 | 证据与含义 |
|---|---|
| `2026-07-15T13:45:35+08:00` | stderr 最后写入时间；最后错误是旧代码对 null `name` 尝试写 `user_signal_projection` 触发 `NotNullViolation`。此后 stderr 未新增。 |
| `2026-07-15T13:45:43.558231+08:00` | history 中第一条新 fail-closed 自动 execute 开始；selected=100、projectable=0、skipped=100、inbox=100、projection/card=0。 |
| `2026-07-15T13:45:45.909367+08:00` | 第一条新 fail-closed 自动 execute 完成，结果 `EXECUTE_PASS`。 |
| `2026-07-15T13:56:24+08:00` | checkpoint-shape 最终修复脚本文件 mtime。 |
| `2026-07-15T13:57:25.375145+08:00` | history 记录最终脚本形状后仍有自然 `EXECUTE_PASS`，证明 loaded LaunchAgent 持续读取 active checkout。 |
| `2026-07-15T14:00:58+08:00` | repair commit `7c209394` 创建。 |
| `2026-07-15T14:11:52+08:00` | 用户提供的当时最新报告为 `NOOP / no_unconsumed_n5_action_events`。 |
| `2026-07-15T14:18:57.707992+08:00` | 本 gate 读取的更新报告开始。 |
| `2026-07-15T14:18:58.310954+08:00` | 更新报告完成，仍为 `NOOP / no_unconsumed_n5_action_events`，全部 side-effect flags=false。 |
| `2026-07-15T14:20:17.460530+08:00` | 本 gate 读取的 history 最新一次开始。 |
| `2026-07-15T14:20:17.479253+08:00` | history 最新一次完成，仍为 `NOOP / no_unconsumed_n5_action_events`。 |

结论：`13:45:43 < 13:56:24 < 14:00:58`。新 fail-closed 代码确实在最终
checkpoint-shape 修复和 commit 之前被真实 LaunchAgent 自动执行。

## 4. 事后功能核验登记

以下业务行级结果来自用户提供的事后只读审计快照。本 runtime_control gate 不连接数据库，
不重新执行 SQL，也不把本地 history 的 writer summary 当作实际 distinct row count。

| 检查项 | 用户提供的只读审计结果 |
|---|---|
| N5 not-ready | `952` |
| not-ready inbox | `952/952`，`projection_status=skipped_fail_closed` |
| not-ready projection | `0` |
| 原阻塞事件 | `evt_066fa...` 已记录完整原因，projection=`0` |
| N5 ready | `318` |
| ready projection/card | `318/318` |
| ready 字段审计 | context/version/hash/marker/价格/百分比 `issue_count=0` |
| 原有 projection/card | `13/13` 完整保留 |
| duplicate projection | `0` |
| checkpoint payload keys | 精确为 `event_count`、`projection_policy` |
| N5 outbox | 保持 `pending`，未消费、未改状态 |
| 新 notification | `0` |
| push/voice/mobile/sim/real trade | 均未触发 |

本地 history 的保留窗口为最近 500 行。该窗口内 `skipped_projection_message` 累计为
`952`，与用户审计一致；`user_signal_projection` writer summary 累计为 `321`。
后者是 runner write summary，不是数据库 distinct-row 审计口径，不能替代用户提供的
`ready projection=318` 和 `duplicate projection=0` 结果。

因此登记：

```text
functional_behavior=PASS
release_control_sequence=BLOCKED
runtime_control_preflight_retroactively_invalid=true
manual_canary_allowed=false
reload_allowed=false
replay_or_backfill_allowed=false
```

## 5. 发布控制缺陷

根因不是 marker/version/hash 逻辑，而是运行中的 worker 与开发 checkout 没有隔离：

```text
loaded LaunchAgent
  -> WorkingDirectory = mutable active checkout
  -> relative runner path
  -> --execute --user-confirmed
  -> every 3 seconds imports current working-tree source
```

由此产生以下控制面风险：

1. 未提交代码可被自动热执行。
2. review/commit/preflight/canary 的人工 gate 无法形成真实发布边界。
3. 文件保存时间而不是显式 promotion 决定 live 代码版本。
4. checkout 中任何同进程 import 的源码变化都可能在下一次调度中生效。
5. `state=not running` 容易被误读为 worker 已停，但 StartInterval 仍会继续调度。

控制面严重度：`P0_RELEASE_BOUNDARY_BYPASS`。

## 6. 后续隔离不变量

未来 N6 poller 修改和发布必须同时满足：

```text
development_worktree != loaded_worker_working_directory
loaded_worker_release_path is immutable for the lifetime of the loaded job
no loaded worker reads an active developer checkout
worker isolation happens before promotion
promotion names one reviewed commit SHA
promotion never implies canary authorization
canary and reactivation require separate explicit gates
```

推荐发布状态机：

```text
ISOLATED_DEVELOPMENT
-> COMMIT_REVIEWED
-> WORKER_ISOLATION_PREFLIGHT_PASS
-> WORKER_QUIESCED_BY_EXPLICIT_GATE
-> PROMOTION_APPROVED
-> IMMUTABLE_RELEASE_PROMOTED
-> CANARY_EXPLICITLY_AUTHORIZED
-> REACTIVATION_EXPLICITLY_AUTHORIZED
```

任何一步缺失必须 `BLOCK`。不得从 `COMMIT_REVIEWED` 自动跳到 live。

## 7. 后续 gates

### Gate A — 独立 worktree 与 immutable release 边界设计

```text
N6_POLLER_ISOLATED_WORKTREE_AND_IMMUTABLE_RELEASE_BOUNDARY_DESIGN_GATE
```

只允许：

- 设计独立开发 worktree/branch 命名和 exact allowlist；
- 设计 immutable release checkout 或 versioned release directory；
- 设计 LaunchAgent 只引用绝对、不可变 release runner 路径；
- 设计 commit SHA、file hash、plist hash、release path 的 promotion manifest；
- 生成文档、plist draft 和纯测试。

禁止：修改或 reload 当前 loaded LaunchAgent、连接数据库、运行 N6、消费队列。

### Gate B — 发布前 worker 隔离只读 preflight

```text
N6_POLLER_LOADED_WORKER_PRE_PROMOTION_ISOLATION_PREFLIGHT_GATE
```

只读证明：

- 当前 loaded label、WorkingDirectory、ProgramArguments、StartInterval；
- 当前 worker 是否仍指向 active checkout；
- 目标 immutable release path 和 commit SHA；
- 当前 process/interval 状态与最后 report/history 时间；
- promotion 前需要的 quiesce/bootout 动作清单，但不执行动作。

输出只能是 `READY_FOR_EXPLICIT_WORKER_QUIESCE_GATE` 或精确 `BLOCKED`。

### Gate C — 显式 worker quiesce

```text
N6_POLLER_EXPLICIT_WORKER_QUIESCE_GATE
```

该 gate 必须另行获得用户明确授权。它只能执行已审核的 worker 隔离动作和只读 post-check，
不得顺手 promotion、canary、replay、backfill 或 DB 写入。

### Gate D — 显式 promotion

```text
N6_POLLER_EXPLICIT_IMMUTABLE_RELEASE_PROMOTION_GATE
```

前置条件：worker 已由 Gate C 证明 quiesced。promotion 必须锁定 reviewed commit SHA、
exact file scope、release path 和 manifest hash。promotion 不得自动启动 worker。

### Gate E — 独立 canary / reactivation 授权

```text
N6_POLLER_POST_PROMOTION_BOUNDED_CANARY_AUTHORIZATION_GATE
N6_POLLER_POST_CANARY_REACTIVATION_AUTHORIZATION_GATE
```

canary 与 reactivation 必须拆开授权。当前 `7c209394` 修复已经自然运行，禁止再补做
手工 canary；这些 gates 仅适用于完成隔离后的未来 release。

## 8. 本登记 gate 的副作用声明

```text
launchctl_reload=false
launchctl_bootout=false
launchctl_bootstrap=false
manual_canary=false
runner_executed=false
database_connected=false
database_written=false
outbox_consumed_or_updated=false
inbox_or_checkpoint_written=false
replay=false
backfill=false
worker_started_or_reloaded=false
N1_N6_business_fact_modified=false
```

本 gate 唯一写入是本控制面登记 artifact。
