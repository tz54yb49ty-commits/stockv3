# V3 20260615 HINT 30m Active/Stale Separation Implementation

Result: `IMPLEMENTATION_PASS`

Objective:
- Prevent active N6/UI/projection paths from using stale `30m_volume` lineage for `board:TDX:881470` at `20260615 09:31`.

Changes:
- Added stale lineage registry in `src/ashare_v3/user/stale_active_lineage.py`.
- Active N6 app signal list/detail filters reviewed stale source action runs.
- N6 UI v1 signal query also filters reviewed stale source action runs.
- N4/N5 raw diagnostic message models mark reviewed stale lineage as `STALE` instead of hiding historical rows.
- N6 projection dry-run blocks stale `source_action_run_id`.

Corrected metric:
- `current_30m_virtual_amount=2348930635.56391`
- `previous_day_same_window_amount=2613103496`
- `amount_pass=false`

Historical data policy:
- Mark stale by registry.
- Do not delete historical rows.
- Do not rewrite historical rows.

Validation:
- Focused RED tests were observed before implementation.
- `tests.test_n6_user_app tests.test_n6_projection_plan tests.test_n6_projection_execute`: `177 OK`.

Forbidden scope:
- No database write.
- No rollback.
- No outbox/inbox/checkpoint consume or update.
- No scheduler/worker start.
- No voice/mobile/sim/position/order/real trade path touched.
- No old-system access.
