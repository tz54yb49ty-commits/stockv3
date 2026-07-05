# N3 20260611 B1 Board MarketSnapshotUpdated Event Route Decision

Gate: `N3_20260611_B1_BOARD_MARKET_SNAPSHOT_UPDATED_EVENT_ROUTE_DECISION_GATE`

Result: `DECISION_PASS`

Mode: read-only policy decision. This gate did not execute B1, did not write the database, did not consume or update outbox/inbox/checkpoint, did not start a worker, and did not enter N4/N5/N6.

## Current Blocker Proof

- Run-level atomic source-time guard post-review: `POST_REVIEW_PASS`.
- Board source-time semantics fix post-review: `POST_REVIEW_PASS`.
- Current B1 board adapter: `BoardMarketDataAdapter`.
- Current board source path: `mootdx.quotes.index(frequency=9)`.
- The returned `datetime` is classified as `tdx_index_frequency_9_period_label`, not a trusted realtime update timestamp.
- Trace fields are available: `raw_snapshot_time_label`, `raw_snapshot_time_semantics`, `source_time_trust_level`, `observed_at`, `fetched_at`.
- Current default policy is `P0_BLOCK_NO_OUTBOX`.
- `normalize_to_observed_at_enabled=false`.
- Board raw `15:00` before 15:00 is `source_time_untrusted_label`, not `source_time_future` and not `source_time_confirmed`.
- Run-level atomic precheck prevents stock/index partial writes before any snapshot/outbox insert.

Direct retry under the current contract is expected to be safe but blocked: `BLOCKED_NO_WRITE`.

## Route Analysis

| Route | Decision | Risk | Write Impact | N4 Impact |
|---|---|---:|---|---|
| Reviewed `observed_at` normalization | Recommended next route | Medium | Full B1 standard outbox scope: stock/index/board `1890/83/127`, total `2100`; board event_time uses `observed_at`, raw `15:00` remains trace only | N4 receives full stock/index/board `MarketSnapshotUpdated`; board evidence is quality-visible |
| Trusted alternate board realtime source | Not selected until source is proven | Low if proven, high if unproven | No immediate write; requires source/adapter proof first | Best semantic route after proof, but currently blocked by no proven wired source |
| Stock/index-only outbox with explicit board exclusion | Fallback only with explicit approval | Medium-high | Writes stock/index only: `1890/83/0`, total `1973`; board explicitly excluded | N4 can test stock/index, but board remains intentionally pending/missing |

## Recommended Route

Recommended route: `reviewed_observed_at_normalization`.

Rationale:

- No trusted alternate board realtime source is currently proven or wired for B1 in the reviewed repository evidence.
- The active goal is to provide N4 a full stock/index/board `MarketSnapshotUpdated` input. Stock/index-only output would be partial and would require a separate N4 board-exclusion acceptance policy.
- The code now separates raw board period labels from `observed_at/fetched_at`; it can support an explicit reviewed normalization policy without using the raw `15:00` label as event time.
- Run-level atomic precheck remains the safety backstop: if the normalization contract is not satisfied, the run must block before any DB write.

## Contract And Preflight Impact

For the recommended route, the next contract/preflight refresh must:

- Set `source_time_policy.board_source_time_label_handling=NORMALIZE_TO_OBSERVED_AT`.
- Set `board_source_time_semantics_policy.normalize_to_observed_at_enabled=true`.
- Set `board_source_time_semantics_policy.event_time_policy=event_time_observed_at_raw_label_trace_only`.
- Keep `run_level_atomic_source_time_precheck.enabled=true`.
- Keep expected rows as stock/index/board/total `1890/83/127/2100`.
- Require payload trace fields:
  - `subscription_id`
  - `pull_plan_id`
  - `run_id`
  - `source_adapter`
  - `data_quality_status`
  - `snapshot_id`
  - `raw_snapshot_time_label`
  - `raw_snapshot_time_semantics`
  - `source_time_trust_level`
  - `observed_at`
  - `fetched_at`
  - `source_time_label_normalized`

Board normalized rows must be quality-visible. The raw `15:00` label must remain trace-only and must not become `MarketSnapshotUpdated.event_time`.

## Rollback And Quality Requirements

- Rollback SQL remains `sql/N3_20260611_B1_market_snapshot_updated_standard_outbox_rollback.sql`.
- Rollback must hard-fail before DELETE/UPDATE.
- Rollback must guard outbox/inbox/checkpoint and N4/N5/N6/user/sim/virtual downstream refs.
- Delete scope remains only the target `snapshot_run_id` rows:
  - stock/index/board realtime snapshot rows
  - target `MarketSnapshotUpdated` outbox rows
  - quality rows
  - common_market_data_run row
- Rollback must preserve existing fact-only B1/C1/B2 runs.
- No `CASCADE`, `DROP`, or `TRUNCATE`.
- Quality must count and sample `board_source_time_label_normalized`; it must not silently mark the raw board period label as trusted source time.

## Forbidden Scope Proof

- B1 execute: not run.
- Database writes: none.
- Rollback SQL: not executed.
- Outbox/inbox/checkpoint consume or update: none.
- Worker: not started.
- N4/N5/N6 execute: none.
- Delivery/push/voice/mobile: none.
- Proposal/order/trade/sim/position/PnL/real trade: none.
- Old system: not touched.

## Next Prompt

```text
layer_role=N3_market_data。

进入 N3_20260611_B1_BOARD_OBSERVED_AT_NORMALIZATION_CONTRACT_PREFLIGHT_GATE。

目标：
只读刷新 20260611 B1 MarketSnapshotUpdated standard outbox 的 contract/preflight/dry-run/rollback proof，采用 reviewed observed_at normalization：
- board_source_time_label_handling=NORMALIZE_TO_OBSERVED_AT
- board raw 15:00 只进 trace
- event_time 使用 observed_at/fetched_at
- quality 标记 board_source_time_label_normalized

要求：
- 不 execute
- 不写数据库
- 不消费/update outbox/inbox/checkpoint
- 不启动 worker
- 不进入 N4/N5/N6

必须输出：
- CONTRACT_PREFLIGHT_PASS / BLOCKED
- expected rows stock/index/board/total=1890/83/127/2100
- payload trace proof
- rollback proof
- forbidden scope proof
- 是否允许回 runtime_control 做 execute final gate review
```
