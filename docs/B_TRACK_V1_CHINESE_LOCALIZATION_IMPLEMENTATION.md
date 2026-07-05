# B_TRACK_V1_CHINESE_LOCALIZATION_IMPLEMENTATION

Status: IMPLEMENTATION_PASS

Layer role: N6_user

Scope: B-track V1 user-facing UI wording, display labels, and tests only.

## Implemented

- Navigation localized to Chinese: 首页、账户、关注池、信号、状态监控、方案、组合、收益、AI助手、排行榜、退出登录.
- Page titles localized:
  - `/n6/app` and `/n6/app/dashboard`: B轨首页
  - `/n6/app/account`: 我的账户
  - `/n6/app/watchlist`: 关注池
  - `/n6/app/signals`: 信号中心
  - `/n6/app/status-monitor`: 状态监控
  - `/n6/app/ai-users`: AI助手
  - `/n6/app/proposals`: 方案
  - `/n6/app/portfolio`: 组合
  - `/n6/app/pnl`: 收益
  - `/n6/app/leaderboard`: 排行榜
- Safety wording localized:
  - 只读模式 · 不下单 · 不更新持仓 · 不构成投资建议
  - 本页仅展示已审核的系统投影和证据链，不代表交易建议
  - 该入口为未来功能预留，当前不会生成方案、订单、交易或持仓变化
- Event labels added as bilingual display labels:
  - 市场动作确认成立 (ActionExecuted)
  - 市场动作未确认 (ActionBlocked)
  - 触发成立 (TriggerMatched)
  - 等待行情证据 (TriggerPendingMarketData)
  - 状态变化 (TriggerStateChanged)
  - 动作待确认 (ActionEligible)
  - 动作已跳过 (ActionSkipped)
- State, direction, blocked_reason, asset_kind display labels added without changing raw API fields.
- Forbidden wording remediation completed:
  - Replaced `非真实收益` with `非实际业绩`.
- Tests updated to assert Chinese UI wording, forbidden wording absence, API/internal field stability, and readonly boundaries.

## API/Internal Enum Boundary

Unchanged raw fields and enum values:

- `identity_key`
- `condition_key`
- `original_condition_key`
- `projection_run_id`
- `source_run_id`
- `event_id`
- `dedup_key`
- `partition_key`
- `quality_status`
- `asset_kind`
- `action_state`
- `action_mark`
- `blocked_reason`
- `principal_id`
- `principal_type`

Added display-only fields:

- `component_label`
- `event_label`
- `asset_kind_label`
- `direction_label`
- `action_state_label`
- `blocked_reason_label`
- `status_label`
- `current_status_label`
- `role_label`

## Forbidden Scope Proof

No database business facts are written. No N4/N5/N6 facts are changed. No outbox is consumed. No worker is started. No proposal/order/trade/position/PnL/real-trade capability is enabled.

## Modified Files

- `src/ashare_v3/web/n6_app_v1.py`
- `src/ashare_v3/web/templates/n6_app_shell.html`
- `tests/test_n6_user_app.py`

## Verification

- `PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_n6_user_app.py'` PASS
- JSON parse PASS
- UI wording scan PASS
- Forbidden wording scan PASS
- Route scan GET-only PASS
- `PYTHONPATH=src python3 -m compileall src/ashare_v3/web/n6_app_v1.py src/ashare_v3/web/n6_user_app.py tests/test_n6_user_app.py` PASS
- `git diff --check` PASS

## Next Gate

Allowed next gate: B_TRACK_V1_CHINESE_LOCALIZATION_POST_REVIEW_GATE
