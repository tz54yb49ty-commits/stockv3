# N3N6Q for N6 Virtual Account Quote Contract

```text
contract_name=N3N6Q_FOR_N6_VIRTUAL_ACCOUNT_QUOTE_CONTRACT
contract_version=1.0.0
status=CONTRACT_REGISTERED_DESIGN_ONLY
base_commit=97b0b7c41370f12d923683033882e7afb59ab6bc
provider_owner=N3_market_data
consumer_owner=N6_user
governance_owner=runtime_control
```

## 1. Purpose and non-goals

N3N6Q 是仅向 B轨 N6 虚拟账户提供 Mootdx 股票批量报价的同步、stateless facade。它只承担外部报价和请求/响应股票身份一致性校验。

N3N6Q 不是现有 N3 poller/worker 的扩展，不是 N3 event producer，不开放 public HTTP route，不是浏览器接口，也不拥有 N6 的 scope、调度、持久化、freshness、估值或止损策略。

## 2. Authority matrix

| Capability | runtime_control | N3N6Q / N3_market_data | N6_user | A轨/admin/status | N4/N5 |
|---|---:|---:|---:|---:|---:|
| 合同登记与发布治理 | owner | read | read | none | none |
| Mootdx batch fetch | none | owner | invoke facade only | forbidden | forbidden |
| request/response identity validation | none | owner | revalidate | forbidden | forbidden |
| virtual-position scope and cross-account dedup | none | forbidden | owner | forbidden | forbidden |
| minute scheduling and market-session policy | none | forbidden | owner | forbidden | forbidden |
| trade-date/freshness classification | none | forbidden | owner | forbidden | forbidden |
| N6 quote persistence and valuation | none | forbidden | owner | forbidden | forbidden |
| stop-loss freeze/proposal/virtual sell | none | forbidden | owner | forbidden | forbidden |
| N3/N6 DB write or N3 event | forbidden | forbidden | N6-owned tables only in later gate | forbidden | forbidden |

本合同本身不授权任何 provider execute、live probe、DB migration、runtime scheduling、虚拟成交或服务发布。

## 3. QuoteIdentity v1 request

一次调用接收 `QuoteIdentity[]`，数组长度必须为 `1..80`。每项只允许以下三个字段，不允许 additional properties：

| Field | Type | Contract |
|---|---|---|
| `identity_key` | string | 必须为 canonical `stock:<EXCHANGE>:<CODE>`，并与另两字段一致 |
| `exchange` | enum string | `SH` / `SZ` / `BJ` |
| `stock_code` | six-digit string | `^[0-9]{6}$` |

请求禁止包含：

```text
principal_id / principal / user_id / account_id / position_id
holding_episode_no / quantity / available_quantity / cost / pnl
stop_loss_price / stop_loss_status / proposal_id
trade_date / quote_minute / freshness / order / trade / action_price
```

N6 必须在调用前从 N6-owned virtual-position scope 生成并按 `identity_key` 去重；N3N6Q 不得接触持仓表来发现 scope。

## 4. QuoteBatch v1 response

响应顶层字段严格为：

```text
contract_version
batch_id
source_adapter
source_version
source_time_semantics
requested_at
completed_at
batch_status
item_count
items
```

约束：

- `contract_version` 固定为 `1.0.0`。
- `batch_id` 是本次进程内调用生成的稳定 UUID，不代表 DB run 或 N3 lineage。
- `source_adapter` 固定为 `mootdx.std`；`source_version` 是已加载 adapter/package 版本字符串。
- `source_time_semantics` 固定为 `provider_intraday_time_without_trade_date`。N3N6Q 不推断交易日。
- `requested_at` / `completed_at` 是带时区 ISO-8601 时间。
- `batch_status` 只能为 `passed / partial / failed`。
- `item_count` 等于请求项数；`items` 必须按请求顺序一一返回，包括 fail-closed 项。

每个 `items[]` 字段严格为：

```text
identity_key
exchange
market
stock_code
current_price
last_close
day_open
day_high
day_low
source_time_text
fetched_at
quality_status
quality_reason
```

字段语义：

| Field | Type | Contract |
|---|---|---|
| `identity_key` / `exchange` / `stock_code` | string | 回显请求身份；不得用 provider 错码覆盖请求身份 |
| `market` | integer or null | Mootdx 原始 market code；必须参与身份校验 |
| `current_price` / `last_close` / `day_open` / `day_high` / `day_low` | decimal string or null | 有效值使用十进制定点字符串；不得传 binary float |
| `source_time_text` | string or null | provider `servertime` 原文；不得补造 trade_date |
| `fetched_at` | string | 带时区 ISO-8601 接收时间 |
| `quality_status` | enum | `passed / not_ready` |
| `quality_reason` | enum | `ok / missing / identity_mismatch / invalid_price / invalid_source_time / provider_error / unsupported_exchange` |

不得返回 provider raw row、盘口、成交量、反向字节、principal/account/position、stop-loss、order/trade 或任何 N3 lineage/event 字段。

## 5. Validation and fail-closed rules

1. 请求重复 `identity_key`、identity 三字段不一致、非股票 identity、批量为空或超过 80：整批拒绝，不调用 provider。
2. provider 返回的 `code/market` 必须匹配请求身份；错码、重复响应和未证明的 exchange-market 映射均返回该项 `not_ready`。
3. `current_price <= 0` 或 `day_low <= 0` 时，该项为 `not_ready/invalid_price`；不输出可用于估值或止损的有效价格。
4. provider `servertime` 缺失或无法解析时，该项为 `not_ready/invalid_source_time`。
5. 单项缺失不得用相邻项、last_close、N3 fact、N3P/N3T 或 N2-N5 数据补值。
6. SH/SZ/BJ 身份映射必须在后续 read-only live probe 中逐类证明；BJ 未证明前为 `not_ready/unsupported_exchange`。
7. N6 必须重新校验身份、交易日、market session 和 freshness；N3N6Q 的 `passed` 不等于 N6 的 `fresh`。

## 6. Frozen N3 boundary

以下模块及其文件、配置、测试、进程和数据结构全部冻结：

```text
N3-A1
N3-B1
N3-B2
N3-C1
N3P
N3T
all existing N3 poller / worker / LaunchAgent
all existing N3 schema / migration / fact / quality table
all existing N3 outbox / inbox / checkpoint / event contract
```

N3N6Q 不得 import/call 这些模块，不得读取 `minute_target_scope`、`market_data_subscription` 或任意 N3/N6 table，也不得使用现有 poller lineage 伪装自己的 source trace。

后续 provider gate 的候选代码 allowlist 仅为：

```text
src/ashare_v3/n3n6q/__init__.py
src/ashare_v3/n3n6q/contract.py
src/ashare_v3/n3n6q/provider.py
src/ashare_v3/n3n6q/mootdx_adapter.py
tests/test_n3n6q_quote_provider.py
```

上述 allowlist 只是后续 gate 候选范围，不是当前修改授权。

## 7. Side-effect contract

N3N6Q 的以下能力全部固定为 `false`：

```text
reads_n3_database
reads_n6_database
writes_database
writes_n3_fact
writes_n6_fact
generates_event
writes_outbox
consumes_inbox
updates_checkpoint
starts_poller
starts_worker
installs_launch_agent
opens_http_route
connects_broker
creates_real_trade
```

## 8. A/B track isolation

- 唯一 caller 是 N6-owned internal one-shot；B轨页面 GET 请求不得直接同步拉 Mootdx。
- A轨 `/api/n6/ui/v1/*`、admin/status 和 runtime dashboard 不得 import 或 invoke N3N6Q。
- N6 quote snapshot 只能在后续 `N6_user` persistence gate 中写入 N6-owned schema；不得混入 A轨 source 或 response。
- N3N6Q 故障时 B轨必须展示 `not_ready/stale`，不得回退现有 N3 facts、cache、N2-N5 裸表或浏览器直拉。

## 9. Independent next gates

1. `N3N6Q_PROVIDER_AND_FAKE_ADAPTER_IMPLEMENTATION_GATE`，`layer_role=N3_market_data`：仅实现新目录和 fake adapter tests；不拉行情、不写 DB。
2. `N3N6Q_MOOTDX_READONLY_LIVE_PROBE_GATE`，`layer_role=N3_market_data`：只读证明 SH/SZ/BJ identity mapping 和响应语义；不持久化。
3. `N6_VIRTUAL_QUOTE_SCHEMA_AND_PERSISTENCE_GATE`，`layer_role=N6_user`：N6-owned schema、去重、调度、freshness 和 snapshot；不修改 N3N6Q provider。
4. 后续 portfolio、stop-loss freeze、proposal、confirm/virtual sell 和 runtime release 必须继续拆成独立 gate。

任一 gate 通过都不自动授权下一 gate；真实交易和券商连接始终不在本合同范围内。
