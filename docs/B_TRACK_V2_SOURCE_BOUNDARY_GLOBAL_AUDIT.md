# B Track V2 Source Boundary Global Audit

Gate: `B_TRACK_V2_SOURCE_BOUNDARY_GLOBAL_AUDIT_GATE`  
Layer role: `runtime_control`  
Result: `AUDIT_PASS`  
Date: `2026-06-07`

This is a read-only global source-boundary audit for B-track V2 app routes and pages. It does not modify code, write database rows, execute migrations or sync, consume/update outbox, start workers, rollback local display cache, generate proposal/order/trade, update position/PnL, submit real trade, or mutate N3/N4/N5/N6 action flow.

## Scanned Scope

### B-track app API routes

```text
GET /api/n6/app/v1/me
GET /api/n6/app/v1/account
GET /api/n6/app/v1/dashboard
GET /api/n6/app/v1/watchlist
GET /api/n6/app/v1/signals
GET /api/n6/app/v1/signals/{user_signal_projection_id}
GET /api/n6/app/v1/status-monitor
GET /api/n6/app/v1/proposals
GET /api/n6/app/v1/portfolio
GET /api/n6/app/v1/pnl
GET /api/n6/app/v1/ai-users
GET /api/n6/app/v1/leaderboard
GET /api/n6/app/v2/filter/stocks
GET /api/n6/app/v2/filter/boards
GET /api/n6/app/v2/filter/indexes
GET /api/n6/app/v2/filter/board-members
GET /api/n6/app/v2/filter/index-members
GET /api/n6/app/v2/monitor
```

### B-track app pages

```text
GET /n6/app
GET /n6/app/{page_key}
```

Allowed page keys:

```text
dashboard
account
watchlist
signals
filter-center
my-monitor
status-monitor
proposals
portfolio
pnl
ai-users
leaderboard
home
```

## Read-Path Summary

| B-track surface | Repository path | Source status |
|---|---|---|
| `me` | `fetch_app_principals` | N6 principal/account scope only |
| `account` | `fetch_app_virtual_account`, `fetch_app_cash_snapshot` | N6 virtual-account/cash tables only |
| `dashboard` / `home` | `fetch_app_signals` | N6 reviewed projection/card only |
| `watchlist` | `fetch_app_signals` | N6 reviewed projection/card only |
| `signals` | `fetch_app_signals` / `fetch_app_signal_detail` | N6 reviewed projection/card only |
| `status-monitor` | `fetch_app_signals` | N6 reviewed projection/card only |
| `filter-center` | `fetch_app_filter_items`, `fetch_app_filter_members` | `v_n6_*` readonly views only |
| `my-monitor` | `fetch_app_monitor_items` | currently returns readiness-only empty result |
| `proposals` | locked shell model | no DB write / no proposal generation |
| `portfolio` | locked shell model | no DB write / no position generation |
| `pnl` | locked shell model | no DB write / no PnL materialization |
| `ai-users` | static/read-only shell model | no DB write / no AI profile generation |
| `leaderboard` | static/read-only shell model | no DB write / no leaderboard materialization |

## Allowed Source Proof

B-track app code reads these approved source classes:

```text
N6 app identity/session/principal tables:
  user_account
  user_session
  n6_principal

N6 virtual account read-only tables:
  n6_virtual_account
  n6_virtual_cash_snapshot

N6 reviewed projection/card artifacts:
  user_projection_run
  user_signal_projection
  user_signal_card

Current official N6 readonly views for display/filter:
  v_n6_stock_condition_display_basis
  v_n6_index_condition_display_basis
  v_n6_board_condition_display_basis
  v_n6_index_membership_fact
  v_n6_board_membership_fact
```

The B-track app signal paths read from reviewed N6 projection/card rows. They may expose trace fields already embedded in N6 projection rows, but they do not query N4/N5 raw fact tables or unreviewed outbox as source.

## Forbidden Source Findings

No B-track app route/page read-path finding remains for:

```text
FROM stock_condition_display_basis
FROM index_condition_display_basis
FROM board_condition_display_basis
FROM n6_stock_display_cache
FROM n6_index_display_cache
FROM n6_board_display_cache
FROM n6_index_membership_display_cache
FROM n6_board_membership_display_cache
FROM stock_condition_basis / index_condition_basis / board_condition_basis
FROM stock_condition_pool / index_condition_pool / board_condition_pool
FROM stock_minute_target_scope / index_minute_target_scope / board_minute_target_scope
raw K
direct live market
N4 raw facts bypass
N5 raw facts bypass
unreviewed outbox source
```

## A-track / B-track Separation Proof

A-track admin console and legacy UI endpoints remain separate:

```text
/api/n6/ui/v1/...
/n6/action-events
/n6/status-monitor
```

Those paths may read admin/audit sources such as:

```text
common_event_outbox
common_trigger_run
common_action_run
user_notification_queue
```

They are not B-track `/api/n6/app/...` or `/n6/app/...` read paths and are not reported as B-track violations in this audit.

## Superseded Historical Artifacts

Historical B-track V2 filter/monitor artifacts may still mention experimental local cache physical table names. They are superseded by:

```text
B_TRACK_V2_FILTER_CENTER_CLOSEOUT_GATE = CLOSEOUT_PASS
B_TRACK_V2_DASHBOARD_SOURCE_BOUNDARY_CLEANUP_CLOSEOUT_GATE = CLOSEOUT_PASS
```

Current source-boundary authority is:

```text
filter-center -> v_n6_* readonly views
dashboard/home helpers -> v_n6_* readonly views where display-basis summary is needed
n6_display_*_cache -> B-track UI/API logical source labels only
n6_*_display_cache -> experimental/tainted local cache physical tables, not a B-track source
```

## Out-of-Scope Legacy Method Note

`fetch_cards` still contains a legacy join to `stock_condition_display_basis`, but this method is not called by `/api/n6/app/v1/*`, `/api/n6/app/v2/*`, or `/n6/app/...` routes in the current B-track app code path. It is therefore not a blocker for this B-track V2 app source-boundary audit.

Recommended later cleanup:

```text
N6_LEGACY_USER_CARD_SOURCE_BOUNDARY_CLEANUP_GATE
```

## Residual Risks

- Full Excel/base-table field coverage is not guaranteed by current `v_n6_*` views. If required, use a separate readonly view widening gate.
- Experimental local display cache remains present but should not be used by B-track app surfaces until redesigned and re-approved.
- A-track admin/message/status reads remain intentionally separate and should be governed by A-track gates, not B-track source-boundary gates.

## Next Recommended Gate

```text
B_TRACK_V2_SOURCE_BOUNDARY_GLOBAL_CLOSEOUT_GATE
```

Optional future gates:

```text
N6_READONLY_VIEW_FIELD_WIDENING_GATE
N6_LOCAL_DISPLAY_CACHE_SEMANTIC_TAINTED_ROLLBACK_FINAL_GATE
N6_LEGACY_USER_CARD_SOURCE_BOUNDARY_CLEANUP_GATE
```

