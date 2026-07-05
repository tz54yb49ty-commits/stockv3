# N3 20260605 B1/C1/B2 Projection Refresh Preflight Gate

- result: BLOCKED
- blockers: B2 requires B1 live2 and C1 current-minute execute first; projection enrichment v4 requires B2 execute first
- B1 live2: PREFLIGHT_PASS, expected rows stock=1952 index=9 board=428 total=2389, writes_outbox=false
- C1 current-minute: PREFLIGHT_PASS, latest_closed_minute=10:37, expected rows stock=19028 index=134 board=3752 total=22914
- B2 projection: PREFLIGHT_BLOCKED, expected rows after upstream execute stock=1952 index=9 board=428 total=2389
- projection enrichment v4: PREFLIGHT_BLOCKED, expected context candidates=5118
- required order: B1 live2 -> C1 current-minute -> B2 projection refresh -> projection enrichment v4 refresh -> N4 local trigger dry-run
- no database business rows written by this gate
- no outbox/inbox/checkpoint writes or consumption
- no N4/N5/N6 / worker / delivery / push / voice / mobile / sim / position / real trade
## Rollback Guard Hardening

- result: FIX_PASS
- B1 added guards: stock/index/board_realtime_projection_metric, common_trigger_state
- C1 added guards: common_trigger_state
- hard-fail before first DELETE: true
- delete scope unchanged: true
