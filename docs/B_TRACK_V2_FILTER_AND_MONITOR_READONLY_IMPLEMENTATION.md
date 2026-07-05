# B_TRACK_V2_FILTER_AND_MONITOR_READONLY_IMPLEMENTATION

Status: `IMPLEMENTATION_PASS`

Layer role: `N6_user`

Date: `2026-06-07`

Scope: B轨 V2 “筛选中心 + 我的监控”只读实现。本 gate 只新增 GET-only 页面/API 和只读 display cache 适配；不创建 `user_monitor_*` 表，不写数据库，不开放加入/移除/暂停监控。

## 1. Modified Files

```text
src/ashare_v3/web/n6_app_v1.py
src/ashare_v3/web/n6_user_app.py
src/ashare_v3/web/templates/n6_app_shell.html
tests/test_n6_user_app.py
docs/B_TRACK_V2_FILTER_AND_MONITOR_READONLY_IMPLEMENTATION.md
docs/B_TRACK_V2_FILTER_AND_MONITOR_READONLY_IMPLEMENTATION.json
```

## 2. Routes Added

Pages:

```text
GET /n6/app/filter-center
GET /n6/app/my-monitor
```

APIs:

```text
GET /api/n6/app/v2/filter/stocks
GET /api/n6/app/v2/filter/boards
GET /api/n6/app/v2/filter/indexes
GET /api/n6/app/v2/filter/board-members
GET /api/n6/app/v2/filter/index-members
GET /api/n6/app/v2/monitor
```

No V2 POST/PATCH/DELETE route is registered.

## 3. Display Cache Allowlist

The V2 adapter allowlist is:

```text
reviewed N6 projections
reviewed signal cards
n6_stock_display_cache
n6_index_display_cache
n6_board_display_cache
n6_index_membership_display_cache
n6_board_membership_display_cache
```

If any display cache table is missing, the API returns:

```text
status=data_not_ready
empty_state=筛选数据尚未准备完成
items=[]
```

No fallback to N1/N2 raw/source tables is implemented.

## 4. UI Behavior

`/n6/app/filter-center` contains:

```text
个股筛选
板块筛选
指数筛选
年过度分级 / 季过度分级 / 月过度分级 / 周过度分级 / 日过度分级
买向观察 / 卖向观察
加入个股监控（暂未开放）
加入板块监控（暂未开放）
加入指数监控（暂未开放）
查看成分股
```

`/n6/app/my-monitor` contains locked empty sections:

```text
我的个股监控：暂未开放
我的板块监控：暂未开放
我的指数监控：暂未开放
监控对象保存功能将在 B_TRACK_V2_USER_MONITOR_WRITE_CONTRACT_GATE 后开放
当前不会写入用户监控池
暂停监控（暂未开放）
移除监控（暂未开放）
```

Safety banner:

```text
只读模式 · 不下单 · 不构成投资建议 · principal scoped
```

## 5. Locked Write Proof

V2 write route status:

```text
/api/n6/app/v2/monitor/write = not_registered
POST/PATCH/DELETE = 404 or 405
add_monitor_enabled = false
pause_monitor_enabled = false
remove_monitor_enabled = false
write_route_registered = false
write_route_enabled = false
```

## 6. Forbidden Scope Proof

No implementation path performs:

```text
create user_monitor_* table
database business write
outbox/inbox/checkpoint consume or update
worker start
proposal/order/trade generation
position/PnL generation
raw K read
direct live market read
N4/N5 raw fact bypass
condition_basis / condition_pool / minute_target_scope read
unreviewed outbox read
```

## 7. Verification

```text
JSON parse PASS
route scan GET-only PASS
static scan no POST/PATCH/DELETE under /api/n6/app/v2 PASS
cache-missing behavior test PASS
principal scope test PASS
test_n6_user_app.py PASS
compileall PASS
git diff --check PASS
```

## 8. Next Gate

```text
B_TRACK_V2_FILTER_AND_MONITOR_READONLY_POST_REVIEW_GATE
```
