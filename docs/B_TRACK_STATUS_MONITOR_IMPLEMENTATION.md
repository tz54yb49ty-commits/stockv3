# B Track Status Monitor Implementation

Gate: B_TRACK_STATUS_MONITOR_IMPLEMENTATION

Result: IMPLEMENTATION_PASS

Layer role: N6_user

Date: 2026-06-07

## 1. Scope

This implementation adds an independent B Track Status Monitor page and API.
It is GET-only, principal scoped, and readonly. It derives status rows from
reviewed B Track N6 signal projections/cards and their N2 -> N3 -> N4 -> N5 ->
N6 evidence chain. It does not call A Track `fetch_ui_v1_status_monitor`.

Implemented surfaces:

```text
GET /api/n6/app/v1/status-monitor
GET /n6/app/status-monitor
```

## 2. Page/API Content

The API and page show:

```text
asset_kind
identity_key
display_name / display_code
current_status = active / pending_market_data / inactive
trigger_live
N4 event source_run_id / event_id
N5 relationship event_type / action_state / action_mark / blocked_reason
quality_status
source_run_id
projection_run_id
event_time
```

## 3. Write Controls

All write controls are false:

```text
projection_write_enabled = false
card_write_enabled = false
outbox_consume_enabled = false
outbox_status_update_enabled = false
worker_enabled = false
```

## 4. Forbidden Scope Proof

Confirmed false:

```text
A Track status monitor adapter read
N5 outbox read/consume/update
projection/card write
database write
worker start
proposal/order/trade
position update
PnL generation
raw K / direct live market
condition_basis / condition_pool / minute_target_scope
N4/N5 raw facts bypass
```

## 5. Verification

Fresh verification commands:

```text
PYTHONPATH=src:tests python3 -m unittest test_n6_user_app.N6UserAppTest.test_b_track_status_monitor_api_is_readonly_from_reviewed_signals test_n6_user_app.N6UserAppTest.test_b_track_status_monitor_page_renders_n4_n5_relationship_without_mutation_controls test_n6_user_app.N6UserAppTest.test_b_track_pages_render_independent_shell_without_a_track_nav
python3 -m compileall src/ashare_v3/web/n6_app_v1.py src/ashare_v3/web/n6_user_app.py
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_n6_user_app.py'
git diff --check
```

Observed results:

```text
Status Monitor targeted tests: Ran 3 tests, OK
STATUS_MONITOR_ROUTE_SCAN_GET_ONLY_INDEPENDENT_PASS
compileall: exit 0
test_n6_user_app.py: Ran 58 tests, OK before Account page test
test_n6_user_app.py: Ran 59 tests, OK after Account page test
git diff --check: exit 0
```

## 6. Next Gate

```text
B_TRACK_STATUS_MONITOR_POST_REVIEW
```
