# N5 Rollback Before N4 Formal Transition Gate Repair Rerun Post Review

- Result: BLOCKED
- Reason: rollback SQL hard-fail guard found `5331` non-scoped N4 consumer checkpoint refs sharing stale source partitions.
- DELETE executed: `false`
- COMMIT executed: `false`
- stale N5 rows still present: `true`
- old-v1 remains zero: `True`

## Blocking Classification

- total non-scoped checkpoint refs: `5331`
- payload_refs_stale_action_or_trigger: `0`
- payload_refs_old_v1_action_or_trigger: `0`
- payload_refs_other_only: `5331`

Artifacts:
- Execute report: `docs/N5_ROLLBACK_BEFORE_N4_FORMAL_TRANSITION_GATE_REPAIR_RERUN_EXECUTE_REPORT.json`
- Post review JSON: `docs/N5_ROLLBACK_BEFORE_N4_FORMAL_TRANSITION_GATE_REPAIR_RERUN_POST_REVIEW.json`
