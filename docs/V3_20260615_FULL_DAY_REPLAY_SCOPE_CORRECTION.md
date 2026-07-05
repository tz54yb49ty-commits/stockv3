# V3 20260615 Full-Day Replay Scope Correction

- result: `SCOPE_CORRECTION_REGISTERED`
- corrected_at: `2026-06-15`
- affected closeout: `docs/V3_20260615_FULL_DAY_N3_N4_N5_N6_AMOUNT_GUARD_REPLAY_CLOSEOUT.md`

## Correction

The previous closeout used `full-day` too broadly.

The executed lineage used `until_1500` source inputs, but the N3
`action_confirmation_projection_metric_20260615_until_1500_after_n4_amount_guard_fix_v1`
run was scoped to the fixed N4 `TriggerMatched` rows only.

It was not a full-universe or full-minute action-confirmation metric materialization.

## Evidence

- N3 action-confirmation metric expected rows: stock/index/board/total = `25/0/0/25`
- N3 action-confirmation metric ready rows: `25/25`
- N4 fixed replay source event read count: `2104`
- N4 fixed replay output: `TriggerMatched=25`, `TriggerPendingMarketData=4203`
- N4 ordinary formal `TriggerMatched`: `0`
- N4 HINT `TriggerMatched`: `25`
- N5 replay output: `ActionBlocked=25`, `ActionExecuted=0`
- N6 projection output: `user_projection_run=1`, ordinary user messages `0`

## Correct Scope Name

Correct description:

```text
20260615 until_1500 fixed N4 matched-scope N3 metric -> N5/N6 replay closeout
```

Incorrect description:

```text
20260615 full-day full-scope N3 metric -> fixed N4 full-day replay -> N5 full-day replay -> N6 projection
```

## Required Follow-Up For True Full Coverage

A true full-day replay requires a new N3 full-scope action-confirmation metric run before N4/N5/N6 replay:

1. Define the full target universe from reviewed V3 N2/N4 context, not from old system.
2. Audit 20260615 1m source coverage for every target object from `09:31` to `15:00`.
3. Materialize N3 action-confirmation metrics for every required object/time, not only N4 matched rows.
4. Rerun fixed N4 from that full metric source.
5. Rerun N5 and N6 from the new fixed N4/N5 lineage.

No DB rollback was executed by this correction. No scheduler, worker, voice, mobile, sim,
position, order, real trade, or old-system path was touched.
