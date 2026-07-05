# N3 B2 Live2 Fact-Only Trace Compatibility

Status: **PREFLIGHT_PASS**

B1 live2 wrote snapshot facts with `writes_outbox=false`, so B2 permits missing `snapshot_event_id` only under the explicit fact-only trace policy. Required trace fields are complete for 2389/2389 rows: `snapshot_id`, `subscription_id`, `pull_plan_id`, and `source_adapter`.

No synthetic outbox event id is generated, no common_event_outbox row is backfilled, and B2 remains forbidden from writing or consuming outbox/inbox/checkpoint.
