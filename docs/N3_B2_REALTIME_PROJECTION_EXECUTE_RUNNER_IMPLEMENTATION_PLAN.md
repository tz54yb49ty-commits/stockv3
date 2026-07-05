# N3-B2 Realtime Projection Execute Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a run-once B2 execute runner that writes formal realtime projection facts from the passed dry-run contract without writing outbox or entering downstream layers.

**Architecture:** Reuse the B2 dry-run calculation contract and persist one projection fact per B1 snapshot row into stock/index/board physical tables. The runner requires `--execute` and `--user-confirmed`, blocks unless the preflight is pass, writes only the allowed N3 projection tables plus run/quality rows, then exits.

**Tech Stack:** Python, psycopg, PostgreSQL runtime, unittest.

---

## Files

- Create: `/Users/chuanfuchen/Documents/A股监控系统v3/scripts/run_realtime_projection_metric_once.py`
- Create: `/Users/chuanfuchen/Documents/A股监控系统v3/src/ashare_v3/market/realtime_projection_execute.py`
- Create: `/Users/chuanfuchen/Documents/A股监控系统v3/tests/test_realtime_projection_execute.py`
- Read: `/Users/chuanfuchen/Documents/A股监控系统v3/docs/N3_B2_realtime_projection_execute_contract.json`
- Read: `/Users/chuanfuchen/Documents/A股监控系统v3/docs/N3_B2_realtime_projection_execute_preflight.json`

### Task 1: Runner Guard Tests

- [ ] Add tests that verify the runner blocks unless both `--execute` and `--user-confirmed` are present.
- [ ] Add tests that verify `projection_run_id` must match the contract.
- [ ] Add tests that verify preflight result must be `PREFLIGHT_PASS`.
- [ ] Run `PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_realtime_projection_execute.py'` and confirm the new guard tests fail before implementation.

### Task 2: Execute Service

- [ ] Implement read-only prechecks: lineage passed, projection_run_id absent, projection tables have zero rows for the run, outbox rows for projection_run_id are zero.
- [ ] Implement projection fact construction with the same calculation config as the dry-run: ready stock/index rows, not_ready board/BJ rows, trace fields, source_fact_ids, snapshot_event_id, subscription_id, pull_plan_id.
- [ ] Write `common_market_data_run`, projection facts, and summary quality items in one transaction.
- [ ] Explicitly avoid writes to `common_event_outbox` and any downstream table.

### Task 3: CLI

- [ ] Add `scripts/run_realtime_projection_metric_once.py` with arguments:
  - `--contract-path`
  - `--preflight-path`
  - `--projection-run-id`
  - `--for-trade-date`
  - `--execute`
  - `--user-confirmed`
  - optional `--dsn`
- [ ] CLI prints EXECUTED / BLOCKED / FAILED, rows by asset/status, quality summary, outbox rows, rollback SQL path.

### Task 4: Verification

- [ ] Run `python3 -m compileall scripts src tests`.
- [ ] Run `PYTHONPATH=src python3 -m unittest discover -s tests`.
- [ ] Run `git diff --check`.
- [ ] Do not execute B2 until the user explicitly confirms the run-once command.
