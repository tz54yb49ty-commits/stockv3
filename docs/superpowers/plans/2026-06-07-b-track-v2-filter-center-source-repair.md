# B Track V2 Filter Center Source Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair B Track V2 filter center so it reads the current official `v_n6_*` readonly views and preserves N2 display_basis rows without local fanout.

**Architecture:** B-track filter center must treat `v_n6_*` views as the official read boundary, while `n6_display_*_cache` remains only a UI source label. The existing local cache physical tables are ignored for filter-center until a separate cache contract is approved.

**Tech Stack:** Python 3.11, FastAPI repository layer in `src/ashare_v3/web/n6_user_app.py`, UI model helpers in `src/ashare_v3/web/n6_app_v1.py`, unittest tests in `tests/test_n6_user_app.py`.

---

### Task 1: Add Failing Tests For Official View Sources

**Files:**
- Modify: `tests/test_n6_user_app.py`

- [ ] **Step 1: Add test that filter APIs use `v_n6_*` source names and preserve arrays**

Add a test near the existing B Track V2 filter tests:

```python
def test_b_track_v2_filter_apis_use_n6_readonly_views_without_local_cache_fanout(self) -> None:
    client, repo, _, _ = build_client()
    repo.app_filter_cache_ready = {"stock": True, "index": True, "board": True}
    client.post("/api/n6/auth/login", json={"login_name": "admin", "password": "correct-password"})

    response = client.get("/api/n6/app/v2/filter/stocks")

    self.assertEqual(response.status_code, 200)
    payload = response.json()
    self.assertEqual(payload["status"], "ready")
    self.assertEqual(payload["items"][0]["physical_source"], "v_n6_stock_condition_display_basis")
    self.assertEqual(payload["items"][0]["source_table"], "n6_display_stock_condition_cache")
    self.assertIn("selected_directions", payload["items"][0])
    self.assertIn("selected_condition_keys", payload["items"][0])
    self.assertNotIn("n6_stock_display_cache", json.dumps(payload, ensure_ascii=False))
```

- [ ] **Step 2: Add test that period filters use direct period columns**

```python
def test_b_track_v2_filter_period_filters_use_direct_period_grade_columns(self) -> None:
    client, repo, _, _ = build_client()
    repo.app_filter_cache_ready = {"stock": True, "index": True, "board": True}
    client.post("/api/n6/auth/login", json={"login_name": "admin", "password": "correct-password"})

    response = client.get("/api/n6/app/v2/filter/stocks?year_overheat_level=low_volume_down")

    self.assertEqual(response.status_code, 200)
    payload = response.json()
    self.assertEqual(payload["status"], "ready")
    self.assertEqual(payload["items"][0]["year_overheat_level"], "low_volume_down")
    self.assertEqual(repo.app_filter_reads[0], (1, "admin", 1, "stock", {"year_overheat_level": "low_volume_down"}))
```

- [ ] **Step 3: Run tests and confirm failure**

Run:

```bash
PYTHONPATH=src:scripts python3 -m unittest discover -s tests -p 'test_n6_user_app.py'
```

Expected: FAIL because current repository reads local cache physical tables and item model does not expose `physical_source` / preserved selected arrays.

### Task 2: Repair Repository Source Reads

**Files:**
- Modify: `src/ashare_v3/web/n6_user_app.py`

- [ ] **Step 1: Replace filter source map with official views**

In `PostgresN6UserRepository.fetch_app_filter_items`, replace the local cache table map with:

```python
view_by_asset = {
    "stock": "v_n6_stock_condition_display_basis",
    "index": "v_n6_index_condition_display_basis",
    "board": "v_n6_board_condition_display_basis",
}
display_label_by_asset = {
    "stock": "n6_display_stock_condition_cache",
    "index": "n6_display_index_condition_cache",
    "board": "n6_display_board_condition_cache",
}
view_name = view_by_asset.get(asset_kind)
if view_name is None or not self._app_v2_relation_exists(view_name):
    return {"cache_ready": False, "items": []}
```

- [ ] **Step 2: Select one row per N2 display_basis row**

Use direct view columns:

```sql
SELECT %(physical_source)s AS physical_source,
       %(display_source_label)s AS source_table,
       asset_kind,
       identity_key,
       stock_identity_key,
       index_identity_key,
       board_identity_key,
       code,
       name,
       display_code,
       display_name,
       display_title,
       display_summary,
       selected_directions,
       selected_condition_keys,
       selected_signal_types,
       selected_lanes,
       selected_monitor_types,
       period_grade_y AS year_overheat_level,
       period_grade_q AS quarter_overheat_level,
       period_grade_m AS month_overheat_level,
       period_grade_w AS week_overheat_level,
       period_grade_d AS day_overheat_level,
       period_grade_summary_json AS period_summary_json,
       quality_status,
       run_id AS source_run_id,
       NULL::text AS projection_run_id,
       board_type,
       updated_at AS source_updated_at
FROM {view_name}
WHERE {where_sql}
ORDER BY updated_at DESC NULLS LAST, identity_key ASC
LIMIT %(limit)s
```

- [ ] **Step 3: Update membership source reads**

In `fetch_app_filter_members`, use:

```python
view_by_kind = {
    "index": "v_n6_index_membership_fact",
    "board": "v_n6_board_membership_fact",
}
display_label_by_kind = {
    "index": "n6_display_index_membership_cache",
    "board": "n6_display_board_membership_cache",
}
```

Return `source_table` as the display label and `physical_source` as the `v_n6_*` view.

- [ ] **Step 4: Update relation allowlist**

Allow only these relations for filter-center:

```python
allowed_relations = {
    "v_n6_stock_condition_display_basis",
    "v_n6_index_condition_display_basis",
    "v_n6_board_condition_display_basis",
    "v_n6_index_membership_fact",
    "v_n6_board_membership_fact",
}
```

### Task 3: Preserve Arrays In UI Model

**Files:**
- Modify: `src/ashare_v3/web/n6_app_v1.py`

- [ ] **Step 1: Add selected arrays to filter item model**

In `app_v2_filter_item`, include:

```python
"physical_source": _first_text(row, "physical_source"),
"selected_directions": row.get("selected_directions") or [],
"selected_condition_keys": row.get("selected_condition_keys") or [],
"selected_signal_types": row.get("selected_signal_types") or [],
"selected_lanes": row.get("selected_lanes") or [],
"selected_monitor_types": row.get("selected_monitor_types") or [],
```

- [ ] **Step 2: Keep scalar labels as display conveniences only**

Set scalar direction/condition fields from the first selected value only for current template compatibility:

```python
direction = _first_text(row, "direction", default="")
if not direction and row.get("selected_directions"):
    direction = str(row["selected_directions"][0])
condition_key = _first_text(row, "condition_key", default="")
if not condition_key and row.get("selected_condition_keys"):
    condition_key = str(row["selected_condition_keys"][0])
```

The arrays remain canonical; scalar fields are not used for source truth.

### Task 4: Validate Boundaries

**Files:**
- Modify: `tests/test_n6_user_app.py`

- [ ] **Step 1: Add forbidden source scan test**

```python
def test_b_track_v2_filter_center_does_not_read_forbidden_sources(self) -> None:
    source = Path("src/ashare_v3/web/n6_user_app.py").read_text()
    repo_start = source.index("class PostgresN6UserRepository")
    start = source.index("    def fetch_app_filter_items(", repo_start)
    end = source.index("    def fetch_app_monitor_items(", start)
    block = source[start:end]

    for required in [
        "v_n6_stock_condition_display_basis",
        "v_n6_index_condition_display_basis",
        "v_n6_board_condition_display_basis",
        "v_n6_index_membership_fact",
        "v_n6_board_membership_fact",
    ]:
        self.assertIn(required, block)

    for forbidden in [
        "n6_stock_display_cache",
        "n6_index_display_cache",
        "n6_board_display_cache",
        "condition_basis",
        "condition_pool",
        "minute_target_scope",
        "common_trigger_",
        "common_action_",
        "common_event_outbox",
    ]:
        self.assertNotIn(forbidden, block)
```

- [ ] **Step 2: Run targeted tests**

Run:

```bash
PYTHONPATH=src:scripts python3 -m unittest discover -s tests -p 'test_n6_user_app.py'
```

Expected: PASS.

### Task 5: Generate Implementation Artifacts

**Files:**
- Create: `docs/B_TRACK_V2_FILTER_CENTER_SOURCE_REPAIR_IMPLEMENTATION.md`
- Create: `docs/B_TRACK_V2_FILTER_CENTER_SOURCE_REPAIR_IMPLEMENTATION.json`

- [ ] **Step 1: Write implementation report**

The JSON must include:

```json
{
  "gate": "B_TRACK_V2_FILTER_CENTER_SOURCE_REPAIR_IMPLEMENTATION_GATE",
  "status": "IMPLEMENTATION_PASS",
  "official_sources": [
    "v_n6_stock_condition_display_basis",
    "v_n6_index_condition_display_basis",
    "v_n6_board_condition_display_basis",
    "v_n6_index_membership_fact",
    "v_n6_board_membership_fact"
  ],
  "local_cache_physical_tables_used": false,
  "fanout_performed": false,
  "database_written": false,
  "outbox_consumed": false,
  "worker_started": false
}
```

- [ ] **Step 2: Validate artifacts**

Run:

```bash
python3 -m json.tool docs/B_TRACK_V2_FILTER_CENTER_SOURCE_REPAIR_IMPLEMENTATION.json
git diff --check -- src/ashare_v3/web/n6_user_app.py src/ashare_v3/web/n6_app_v1.py tests/test_n6_user_app.py docs/B_TRACK_V2_FILTER_CENTER_SOURCE_REPAIR_IMPLEMENTATION.md docs/B_TRACK_V2_FILTER_CENTER_SOURCE_REPAIR_IMPLEMENTATION.json
```

Expected: both commands PASS.

### Task 6: Stop Before Execute/Post-Review

**Files:**
- None

- [ ] **Step 1: Hand off to runtime_control**

Do not perform post-review or closeout in the implementation turn. Output:

```text
IMPLEMENTATION_PASS
允许回 runtime_control 做 B_TRACK_V2_FILTER_CENTER_SOURCE_REPAIR_POST_REVIEW_GATE。
```
