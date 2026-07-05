# N6 A-Track Post-Close Fast Lane Status Overlay UI Readiness

- gate: `N6_A_TRACK_POST_CLOSE_FASTLANE_STATUS_OVERLAY_UI_READINESS_GATE`
- result: `READINESS_PASS`
- layer_role: `N6_user`
- mode: `readiness_only`
- for_trade_date: `20260616`

## Scope

This gate only evaluates whether the 8786 A-track "收盘后 Fast Lane 状态" UI should prefer the manual lineage overlay artifact when it exists.

No web server was started, no database was read or written, no N1/N2/N3 command was executed, no N4/N5 path was entered, and no worker was started.

## Overlay Status Proof

- status refresh result: `STATUS_REFRESH_PASS`
- overlay JSON exists: `docs/post_close_fastlane/20260616/02_manual_lineage_refresh_status.json`
- overlay JSON parse: `PASS`
- overlay result: `EXECUTE_PASS`
- status_source: `manual_lineage_refresh_overlay`
- current_effective_lineage: `v4`
- source_trade_date: `20260615`
- for_trade_date: `20260616`
- n1_active_financial_source: `stock_financial_20260615_v3`
- n2_active_condition_run: `condition_layer_20260615_source_20260615_for_20260616_v4`
- n3_subscription_run: `market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4`
- n3_a1_preload_run: `previous_day_minute_preload_20260615_for_20260616__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4`

Original status/report are preserved:

- `docs/post_close_fastlane/20260616/00_status.json`
- `docs/post_close_fastlane/20260616/01_oneshot_execute_report.json`

## Current UI Behavior Proof

Static inspection shows current helper behavior:

- `src/ashare_v3/web/post_close_fastlane_status.py` reads `00_status.json` as the current status.
- It does not probe `02_manual_lineage_refresh_status.json`.
- Returned artifacts currently list `00_status.json`, `01_oneshot_execute_report.json`, and N3-A1 report files, but not the manual overlay.
- `src/ashare_v3/web/n6_ui_v1.py` normalizes status to result/source_trade_date/for_trade_date/failed_step_id/updated_at only.
- `src/ashare_v3/web/templates/n6_post_close_fastlane_status.html` does not display `status_source` or `current_effective_lineage`.

Live helper read against local artifacts confirmed:

- `raw_status_source=None`
- `raw_current_effective_lineage=None`
- artifact_files exclude `02_manual_lineage_refresh_status.json`

Therefore implementation is required.

## Required Implementation Scope

1. Update `read_post_close_fastlane_status()` to prefer:
   `docs/post_close_fastlane/<for_trade_date>/02_manual_lineage_refresh_status.json`
   when present and valid.
2. Preserve fallback to `00_status.json` when overlay is missing or invalid.
3. Return overlay as current status when selected.
4. Include original one-shot metadata:
   - `original_oneshot_result`
   - `original_oneshot_status_path`
   - `original_oneshot_report_path`
   - `superseded_for_display_by_manual_overlay=true`
5. Extend `post_close_fastlane_status_model()` to surface:
   - `status_source`
   - `current_effective_lineage`
   - N1/N2/N3 effective run IDs
6. Update the page to display status source and effective lineage.
7. Add tests for:
   - overlay preferred when present
   - fallback to `00_status.json` when overlay missing
   - response includes original one-shot metadata
   - no execute controls, no DB writes, no worker triggers

## Proposed API Behavior

`GET /api/n6/ui/v1/post-close-fastlane-status?for_trade_date=20260616`

When overlay exists:

- current status should be the overlay.
- `status.status_source=manual_lineage_refresh_overlay`
- `status.current_effective_lineage=v4`
- `status.original_oneshot_result=EXECUTE_PASS`
- `status.superseded_for_display_by_manual_overlay=true`

When overlay is absent:

- current status remains `00_status.json`.
- response behavior remains backward compatible.

## Safety Requirements

- read local docs artifacts only
- no DB connection or write
- no execute/retry/rollback buttons
- no N1/N2/N3 execution
- no N4/N5 execution
- no outbox/inbox/checkpoint mutation
- no worker/scheduler start
- no delivery/push/voice/mobile/sim/position/order/real trade

## P0 / P1 / P2

- P0: `0`
- P1: `1` - current UI does not prefer manual overlay when present
- P2: `1` - tests should be expanded for overlay/fallback behavior

## Decision

`READINESS_PASS`

Next recommended gate:

`N6_A_TRACK_POST_CLOSE_FASTLANE_STATUS_OVERLAY_UI_IMPLEMENTATION_GATE`
