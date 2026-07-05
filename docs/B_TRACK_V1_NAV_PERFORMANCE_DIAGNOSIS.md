# B_TRACK_V1_NAV_PERFORMANCE_DIAGNOSIS

Status: `DIAGNOSIS_PASS`  
Layer role: `runtime_control`  
Created at: `2026-06-07T10:05:57+08:00`

## Scope

This gate diagnosed B-track V1 navigation latency for:

- `/n6/app`
- `/n6/app/account`
- `/n6/app/watchlist`
- `/n6/app/signals`
- `/n6/app/status-monitor`
- `/n6/app/ai-users`

This round did not implement optimizations and did not change B-track code.

## Read-Only Boundary

- Database business writes: `false`
- Session DB write: `false`
- Worker started: `false`
- Outbox consumed: `false`
- Order/trade/position/PnL write: `false`
- Implementation changed: `false`
- Artifacts only: `true`

Measurement used an in-memory authenticated diagnostic session to avoid inserting a `user_session` row. Real data reads used `PostgresN6UserRepository` read-only PostgreSQL connections with `default_transaction_read_only=on`.

## Route Latency

| Rank | Route | Avg ms | P50 ms | P95 ms | HTML size |
|---:|---|---:|---:|---:|---:|
| 1 | `/n6/app/status-monitor` | 719.303 | 712.216 | 733.541 | 520087 |
| 2 | `/n6/app/signals` | 716.359 | 708.292 | 733.587 | 531107 |
| 3 | `/n6/app` | 713.285 | 714.561 | 718.698 | 9571 |
| 4 | `/n6/app/watchlist` | 709.627 | 706.119 | 717.867 | 454226 |
| 5 | `/n6/app/account` | 9.625 | 9.715 | 9.982 | 8262 |
| 6 | `/n6/app/ai-users` | 3.940 | 3.988 | 4.040 | 8855 |

Slow pages all share the same pattern: they call `fetch_app_signals(... limit=500)`.

## DB Latency

Average `fetch_app_signals` cost by route:

| Route | Total ms | Connection ms | SQL execute ms | Driver fetch/JSONB decode ms | Row mapping ms | Rows |
|---|---:|---:|---:|---:|---:|---:|
| `/n6/app` | 690.944 | 1.908 | 678.831 | 9.304 | 0.632 | 500 |
| `/n6/app/watchlist` | 680.334 | 1.796 | 671.545 | 6.275 | 0.479 | 500 |
| `/n6/app/signals` | 685.689 | 1.865 | 676.866 | 6.514 | 0.202 | 500 |
| `/n6/app/status-monitor` | 693.620 | 1.769 | 679.511 | 11.878 | 0.227 | 500 |

There is no explicit app-side `json.loads` step in this adapter. JSONB decode is included in driver fetch time.

## Signals Path

Signals scoped read:

- Scoped projection rows: `6270`
- Projection run count: `5`
- Joined card rows: `6270`
- Default limit: `500`
- Effective limit: `500`
- Newest projection created at: `2026-06-06 09:53:16.129524+08`
- Oldest projection created at: `2026-05-26 22:19:54.029967+08`

`EXPLAIN ANALYZE`:

- Planning time: `0.783ms`
- Execution time: `661.049ms`
- Sort node: `top-N heapsort`
- Sort actual total time: `627.85ms`
- Sort rows: `500`
- Sort memory: `2692KB`

Primary evidence: SQL execution and top-N sorting dominate the slow B-track pages.

## Template Latency

| Route | Jinja render ms | HTML size | Items |
|---|---:|---:|---:|
| `/n6/app` | 0.197 | 9571 | 0 |
| `/n6/app/account` | 0.084 | 8262 | 0 |
| `/n6/app/watchlist` | 6.661 | 454226 | 500 |
| `/n6/app/signals` | 6.562 | 531107 | 500 |
| `/n6/app/status-monitor` | 6.427 | 520087 | 500 |
| `/n6/app/ai-users` | 0.099 | 8855 | 1 |

Template render is not the backend bottleneck. Large table HTML can still increase browser-side DOM/paint latency.

## Connection Pattern

`PostgresN6UserRepository._readonly_connection()` creates a new `psycopg.connect(...)` connection. Repository methods call it via `with self._readonly_connection()`.

- `_readonly_connection` call sites in `n6_user_app.py`: `29`
- Connection pool detected: `false`
- Impact: secondary. Signals connection acquire averaged about `1.8-1.9ms`, while SQL execute averaged about `671-680ms`.

## Top Bottlenecks

1. `signals_query_sort_and_json_projection`  
   The signals query scans scoped projection/card rows and spends about `628ms` in top-N sort.

2. `same_500_signal_query_repeated_across_shell_pages`  
   Dashboard, Watchlist, Signals, and Status Monitor all fetch 500 full signal rows.

3. `large_html_payload_for_table_pages`  
   Watchlist, Signals, and Status Monitor render 454KB-531KB HTML with 500 rows.

4. `per_method_postgres_connection_creation`  
   Present, but not the main bottleneck in this sample.

5. `full_page_server_rendered_navigation`  
   Each navigation rebuilds full page data and HTML.

## Route Scan

B-track app/API routes scanned as GET-only:

- `/api/n6/app/v1/me`
- `/api/n6/app/v1/account`
- `/api/n6/app/v1/dashboard`
- `/api/n6/app/v1/watchlist`
- `/api/n6/app/v1/signals`
- `/api/n6/app/v1/signals/{user_signal_projection_id}`
- `/api/n6/app/v1/status-monitor`
- `/api/n6/app/v1/proposals`
- `/api/n6/app/v1/portfolio`
- `/api/n6/app/v1/pnl`
- `/api/n6/app/v1/ai-users`
- `/api/n6/app/v1/leaderboard`
- `/n6/app`
- `/n6/app/{page_key}`

## Optimization Candidates

P0:

- Add read-only route/repository timing instrumentation behind a diagnostic flag.
- Define separate B-track summary read models for dashboard, watchlist, and status-monitor.
- Make Dashboard fetch latest projection, aggregate counts, and latest 5 only.
- Set page-specific effective limits: summary pages should not load 500 full signal rows.

P1:

- Paginate `/n6/app/signals` and `/api/n6/app/v1/signals` with default 50 or 100, preserving hard cap 500.
- Split list/detail payloads so list pages do not select detail-only JSONB evidence fields.
- Review PostgreSQL indexes for `user_signal_projection` ordering/filter path and `user_signal_card` join keys.
- Add readonly PostgreSQL connection pool after query shape is corrected.

P2:

- Add partial navigation or client-side fetch for B-track shell content.
- Add loading states or prefetch for adjacent B-track tabs.
- Virtualize long tables if 500-row views remain necessary.
- Evaluate N6 local readonly display cache/materialized summaries for high-frequency navigation.

## Next Gate

`B_TRACK_V1_NAV_PERFORMANCE_REMEDIATION_CONTRACT_GATE`
